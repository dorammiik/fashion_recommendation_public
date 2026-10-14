"""Server-owned conversation lifecycle; Preference updates never run on this path."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from uuid import uuid4
from copy import deepcopy
from fashion_recommendation_v2.server.quick_start import resolve
from fashion_recommendation_v2.server.quick_start import snapshot
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fashion_recommendation_v2.llm.cost_tracking import record_run_costs

from fashion_recommendation_v2.schemas.conversation import ConversationInput
from fashion_recommendation_v2.schemas.conversation import ConversationDecision
from fashion_recommendation_v2.schemas.conversation import ConversationRecord
from fashion_recommendation_v2.schemas.orchestrator import PendingRequestState
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.storage import StoreConflict


class RecommendationService:
    def __init__(self, preference_service, *, brain_factory, runner_factory, mode='live', profile_updates_enabled=False, default_personalization_mode=None):
        self.preference = preference_service
        self.brain_factory = brain_factory
        self.runner_factory = runner_factory
        self.default_personalization_mode = default_personalization_mode
        self.mode = mode
        self.profile_updates_enabled = profile_updates_enabled

    def get(self, user_id, request_id):
        with self.preference.store() as store:
            return store.get_conversation(user_id, request_id, now=self.preference.clock())

    def _save(self, record):
        record.updated_at = self.preference.clock().isoformat()
        previous = record.revision
        record.revision += 1
        with self.preference.store() as store:
            store.save_conversation(record, expected_revision=previous, now=self.preference.clock())

    def submit(self, user_id, user_query, *, previous_request_id=None, new_request=False, personalization_mode=None, quick_start=None):
        user_query, personalization_mode, previous_request_id, new_request = resolve(
            quick_start, user_query, personalization_mode, previous_request_id, new_request)
        previous = self.get(user_id, previous_request_id) if previous_request_id else None
        if previous and previous.status not in ('completed', 'blocked', 'failed', 'interrupted'):
            raise StoreConflict('Previous request is not finished')
        record = ConversationRecord(quick_start=quick_start,
            quick_start_snapshot=snapshot(quick_start) if quick_start else None, personalization_mode=personalization_mode, request_id=uuid4().hex, user_id=user_id,
            user_query=user_query, previous_request_id=previous_request_id, status='classifying')
        with self.preference.store() as store:
            store.save_conversation(record, now=self.preference.clock())
        return self._with_costs(record, 'new' if new_request or previous is None else None)

    def resume(self, user_id, request_id, *, kind):
        if kind not in ('new', 'followup'):
            raise ValueError('Confirmation must be new or followup')
        record = self.get(user_id, request_id)
        if record.status != 'awaiting_confirmation':
            return record  # Retried confirmation never launches another recommendation.
        record.status = 'classifying'
        self._save(record)  # Compare-and-swap: only one concurrent confirmation can claim it.
        return self._with_costs(record, kind)

    def _with_costs(self, record, kind):
        from fashion_recommendation_v2.storage import UserUnavailable
        run_id = uuid4().hex
        with TemporaryDirectory(prefix='recommendation-cost-') as directory:
            folder = Path(directory)
            try:
                with record_run_costs(folder, run_id):
                    return self._route(record, confirmed_kind=kind)
            finally:
                if self.preference.artifact_root:
                    try:
                        with self.preference.store() as store:
                            store.save_agent_artifacts(record.user_id, run_id,
                                {'openAI_cost.json': (folder/'openAI_cost.json').read_bytes()},
                                now=self.preference.clock())
                    except UserUnavailable:
                        pass

    def _recommendation_context(self, previous):
        """Find an owned completed recommendation within this conversation lineage."""
        seen = set()
        current = previous
        while current and current.request_id not in seen:
            seen.add(current.request_id)
            if current.status == 'completed' and current.state:
                return current
            if not current.previous_request_id or current.new_request or (
                    current.decision and current.decision.kind == 'new'):
                break
            parent = self.get(previous.user_id, current.previous_request_id)
            if current.session_id and parent.session_id != current.session_id:
                break
            current = parent
        return None

    def _route(self, record, confirmed_kind):
        brain = None
        try:
            if confirmed_kind == 'new':
                decision = ConversationDecision(kind='new', effective_query=record.user_query,
                                                reason='Explicit new request or no previous context')
            else:
                previous = self.get(record.user_id, record.previous_request_id)
                context = self._recommendation_context(previous)
                output = context.state.agent_outputs if context else None
                response = output.recommendation_response if output else None
                source = ConversationInput(user_query=record.user_query,
                    previous_query=(previous.state.request.user_query if previous.state else previous.user_query),
                    previous_response=response.model_dump(mode='json') if response else None,
                    confirmed_kind=confirmed_kind)
                brain = self.brain_factory()
                decision = brain.classify(source)
                record.attempts.extend(brain.generation_attempts)
            record.decision = ConversationDecision.model_validate_json(decision.model_dump_json())
            if decision.kind == 'ambiguous':
                record.status = 'awaiting_confirmation'
                record.question = '이전 추천에 이어서 찾으시는 건가요?'
                self._save(record)
                return record
            with self.preference.store() as store:
                record = store.begin_conversation_execution(record, now=self.preference.clock())
            return self._execute(record)
        except StoreConflict:
            # Do not leave an owned routing attempt stuck after a closed-session error.
            # A CAS loser must never overwrite the winner's state.
            current = self.get(record.user_id, record.request_id)
            if current.revision == record.revision and current.status == 'classifying':
                record.status = 'failed'
                record.error_type = 'StoreConflict'
                self._save(record)
            raise
        except Exception as exc:
            if brain and not record.attempts:
                record.attempts.extend(brain.generation_attempts)
            record.status = 'failed'
            record.error_type = type(exc).__name__
            self._save(record)
            return record

    def _execute(self, record):
        personalization_mode = record.personalization_mode or self.default_personalization_mode
        with self.preference.store() as store:
            store.get_user(record.user_id, now=self.preference.clock())
            if personalization_mode is None:
                lookup = store.lookup_profile_view(record.user_id, now=self.preference.clock())
            else:
                from fashion_recommendation_v2.schemas.preference import ProfileLookup
                lookup = ProfileLookup(status='not_found')
        if lookup.preference_profile and lookup.preference_profile.schema_version != '1.0':
            raise ValueError('Preference v1 interpretation profile is not supported by current recommendation consumers')
        preset = record.quick_start_snapshot
        references = list(preset.reference_items) if preset else []
        if record.decision.kind == 'followup' and record.previous_request_id:
            from fashion_recommendation_v2.schemas.relation import ReferenceItem
            previous = self._recommendation_context(self.get(record.user_id, record.previous_request_id))
            if previous and previous.quick_start_snapshot and previous.quick_start_snapshot.profile_bundle:
                preset = previous.quick_start_snapshot
                record.quick_start_snapshot = preset.model_copy(deep=True)
            if previous and previous.state and previous.state.agent_outputs.final_ranking:
                output = previous.state.agent_outputs
                items = {c.item.item_id: c for c in output.candidate_set.candidates}
                references = [ReferenceItem(request_id=previous.request_id, rank=entry.rank,
                    item=items[entry.item_id].item.model_copy(deep=True),
                    search_analysis=items[entry.item_id].search_analysis) for entry in output.final_ranking.ranked_items]
        bundle = preset.profile_bundle if preset else None
        if bundle is not None:
            from fashion_recommendation_v2.preference.profile_lookup import freeze_bundle
            checked = freeze_bundle(bundle)
            if checked != bundle:
                raise ValueError('Quick-start frozen profile changed')
        # Agent identity describes the fixed demo profile; record.user_id remains the
        # authenticated owner for status, artifacts, sessions and feedback.
        agent_user_id = bundle['profile']['user_id'] if bundle else record.user_id
        request = PendingRequestState(personalization_mode=personalization_mode, reference_items=references,request_id=record.request_id, session_id=record.session_id,
            user_id=agent_user_id, original_user_query=record.user_query,
            parent_request_id=record.previous_request_id if record.decision.kind == 'followup' else None,
            user_query=record.decision.effective_query, current_date=self.preference.clock().date(),
            user_state='unknown', mode=self.mode, interaction_collection_enabled=True,
            profile_updates_enabled=self.profile_updates_enabled,
            preference_profile=lookup.preference_profile.model_copy(deep=True) if lookup.preference_profile else None,
            profile_lookup_status=lookup.status if personalization_mode is None else 'not_requested', profile_lookup_error=lookup.error)
        runner = self.runner_factory()
        if personalization_mode is not None:
            from fashion_recommendation_v2.preference.profile_lookup import ServiceProfileLookup
            lookup_profile = (lambda: deepcopy(bundle)) if bundle else ServiceProfileLookup(self.preference, record.user_id)
            runner.ranking.profile_lookup = lookup_profile
            runner.stylist.profile_lookup = lookup_profile

        if runner.output_dir is not None:
            raise ValueError('Server runner must use registered expiring artifacts, not an unmanaged output_dir')
        def progress(event):
            # Counters belong to their producing stage, not the whole request.
            if event.get('stage') and event['stage'] != record.progress.get('stage'):
                record.progress = {}
            # Only structured counters/stages are exposed; no model text or item data.
            for key in ('stage', 'status', 'completed_batches', 'total_batches', 'completed_searches'):
                if key in event:
                    record.progress[key] = event[key]
            self._save(record)
        runner.progress_callback = progress
        state = runner.run(request)
        record.state = state
        record.status = state.execution.status
        if record.status == 'failed' and state.execution.errors:
            record.error_type = state.execution.errors[-1].error_type
        if self.preference.artifact_root:
            files = {name + '.json': json.dumps(value, ensure_ascii=False).encode()
                     for name, value in runner.artifacts.items()}
            files['events.json'] = json.dumps(runner.events, ensure_ascii=False).encode()
            with self.preference.store() as store:
                store.save_agent_artifacts(record.user_id, record.request_id, files, now=self.preference.clock())
        # No profile mutation: Recommendation only reads the snapshot captured above.
        if state.execution.status == 'completed':
            output = state.agent_outputs
            self.preference.publish_recommendation(record.user_id, record.request_id,
                SummaryAgentInput(user_request=state.request.user_query, candidate_set=output.candidate_set,
                                 final_ranking=output.final_ranking, preference_profile=state.request.usable_preference_profile,
                                 ralationRatio=output.usable_relation,
                                 interaction_collection_enabled=True, profile_updates_enabled=self.profile_updates_enabled), output.recommendation_response)
        self._save(record)
        return record
