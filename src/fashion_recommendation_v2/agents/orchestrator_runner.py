"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_runner ----

"""Deterministic lifecycle, detached agent I/O, validation and reviewable artifacts."""
from fashion_recommendation_v2.validation_reuse import reuse_for
from fashion_recommendation_v2.validation_reuse import measure_processing
from fashion_recommendation_v2.validation_reuse import timed_processing
from datetime import datetime
from datetime import timezone
from fashion_recommendation_v2.personalization_policy import effective_mode
import json
from pathlib import Path
from fashion_recommendation_v2.schemas.orchestrator import PendingRequestState
from fashion_recommendation_v2.schemas.orchestrator import RequestState
from fashion_recommendation_v2.schemas.orchestrator import RequestContext
from fashion_recommendation_v2.schemas.orchestrator import UnresolvedState
from fashion_recommendation_v2.schemas.orchestrator import OrchestratorState
from fashion_recommendation_v2.schemas.orchestrator import ExecutionError
from fashion_recommendation_v2.schemas.planner import PlannerInput
from fashion_recommendation_v2.schemas.planner import PlannerStateSnapshot
from fashion_recommendation_v2.schemas.planner import PlannerUnresolvedState
from fashion_recommendation_v2.schemas.planner import ExecutionPlan
from fashion_recommendation_v2.schemas.stylist import StylistAgentInput_base as StylistAgentInput
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.ranking import RankingAgentInput_base as RankingAgentInput
from fashion_recommendation_v2.schemas.ranking import FinalRanking
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary import BlockedSummaryInput
from fashion_recommendation_v2.schemas.summary import BlockedResponse
from fashion_recommendation_v2.schemas.summary_response import validate_summary_response
from fashion_recommendation_v2.agents.registry import AVAILABLE_AGENTS
from fashion_recommendation_v2.schemas.relation import RelationAgentInput
from fashion_recommendation_v2.schemas.relation import RelationRatio
from fashion_recommendation_v2.agents.orchestrator_preferences import select_profile
from fashion_recommendation_v2.agents.stylist_runner import validate_stylist_requirements
from fashion_recommendation_v2.compatibility import validate_compatibility_assessment
from fashion_recommendation_v2.agents.orchestrator_contracts import stylist_context
from fashion_recommendation_v2.agents.orchestrator_contracts import OUTPUTS
from fashion_recommendation_v2.agents.orchestrator_contracts import REFS
from fashion_recommendation_v2.agents.orchestrator_contracts import validate_plan
from fashion_recommendation_v2.agents.orchestrator_contracts import validate_segmentation
from fashion_recommendation_v2.agents.orchestrator_contracts import project_search_request
from fashion_recommendation_v2.agents.orchestrator_contracts import omitted_conditions

@_preserve_class('SearchUnavailable', 'fashion_recommendation_v2.agents.orchestrator_runner')
class SearchUnavailable(RuntimeError):
    """Every marketplace attempt failed; this is not a successful empty search."""

@_preserve_class('SearchPlanUnavailable', 'fashion_recommendation_v2.agents.orchestrator_runner')
class SearchPlanUnavailable(RuntimeError):
    """Search could not execute a valid plan; this is not an empty search result."""

@_preserve_class('OrchestratorRunner', 'fashion_recommendation_v2.agents.orchestrator_runner')
class OrchestratorRunner:

    def __init__(self, *, brain, planner, stylist, search, ranking, summary, relation=None, output_dir=None):
        self.brain, self.planner, self.stylist = (brain, planner, stylist)
        self.search, self.ranking, self.summary = (search, ranking, summary)
        self.relation = relation
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.progress_callback = None
        self.events = []
        self.artifacts = {}

    @timed_processing('orchestrator.save')
    def _save(self, name, value):
        with measure_processing('orchestrator.save.' + name + '.model_dump'):
            if hasattr(value, 'model_dump'):
                value = value.model_dump(mode='json', by_alias=True)
        # Snapshot before consumers mutate their own data.
        with measure_processing('orchestrator.save.snapshot_json'):
            value = json.loads(json.dumps(value, ensure_ascii=False))
        self.artifacts[name] = value
        if self.output_dir is not None:
            destination = self.output_dir / (name + '.json')
            temporary = destination.with_suffix('.tmp')
            with measure_processing('orchestrator.save.serialize'):
                encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
            with measure_processing('orchestrator.save.write_replace'):
                temporary.write_text(encoded)
                temporary.replace(destination)

    def _event(self, **event):
        event['at'] = datetime.now(timezone.utc).isoformat()
        self.events.append(event)
        if self.progress_callback:
            self.progress_callback(event)
        if self.output_dir is not None:
            with (self.output_dir / 'events.jsonl').open('a') as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')

    @timed_processing('orchestrator.persist')
    def _persist(self):
        with measure_processing('orchestrator.state_dump'):
            payload = self.state.model_dump()
        from fashion_recommendation_v2.orchestrator_policy import assessment_contract
        from fashion_recommendation_v2.validation_reuse import has_validation_proof
        ranking = self.state.agent_outputs.final_ranking
        if assessment_contract(self.brain.evaluation_version).reuse_ranking_handoff and type(ranking) is FinalRanking and has_validation_proof(FinalRanking.validate_output, ranking):
            # Keep the internally validated object; other state fields still parse.
            payload['agent_outputs']['final_ranking'] = ranking
        with measure_processing('orchestrator.state_validation'):
            self.state = OrchestratorState.model_validate(payload)
        self._save('orchestrator_state', self.state)
        if self.state.execution.execution_plan:
            self._save('plan_state', self.state.execution.execution_plan)

    @timed_processing('orchestrator.accept_ranking_and_persist')
    def _accept_ranking_and_persist(self, value, source, step, completed):
        from fashion_recommendation_v2.validation_reuse import has_validation_proof
        from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV12_v12 as RankingAgentInputV12
        from fashion_recommendation_v2.personalization_policy import similarity_input
        with measure_processing('orchestrator.ranking_return_validation'):
            verified = False
            if type(value) is FinalRanking and getattr(self.ranking, 'policy_version', None) in {'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17'}:
                internal = similarity_input(RankingAgentInputV12.model_validate(source.model_dump()))
                verified = has_validation_proof(FinalRanking.validate_against, value, internal)
            self.state.agent_outputs.final_ranking = value if verified else FinalRanking.model_validate(value.model_dump()).validate_against(source)
        personalization = value.personalization_v12 or value.personalization_v11
        if personalization is not None:
            self.state.request.profile_lookup_status = personalization['profile_lookup_status']
        step.status = 'completed'
        completed.add(step.step_id)
        self.state.execution.current_step_id = None
        self._persist()

    def _call(self, stage, agent, source, output_name, *, method='run', **kwargs):
        self.stage = stage
        self._save(stage + '_input', source)
        payload = source.model_copy(deep=True)
        before = payload.model_dump()
        agent.progress_callback = self.progress_callback
        self._event(stage=stage, status='running')
        try:
            result = getattr(agent, method)(payload, **kwargs)
            if payload.model_dump() != before:
                raise ValueError(f'{stage} mutated its input.')
            self._save(output_name, result)
            self._event(stage=stage, status='returned')
            return result
        except Exception as exc:
            self._event(stage=stage, status='error', error_type=type(exc).__name__, message=str(exc))
            raise
        finally:
            if stage == 'ranking' and isinstance(getattr(agent, 'personalization_record', None), dict):
                self.state.request.profile_lookup_status = agent.personalization_record['profile_lookup_status']
            for field in ('generation_attempts', 'evaluation_attempts', 'response_records', 'personalization_record'):
                if hasattr(agent, field):
                    self._save(stage + '_' + field, getattr(agent, field))
            if stage == 'search' and getattr(agent, 'search_policy_version', None) in {'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                self._save('search_requirements_validation', getattr(getattr(agent, 'search_brain', None), 'requirements_validation_history', []))

    def _record_error(self, exc):
        attempts = getattr(exc, 'attempts', None) or [dict(code='invalid_response' if isinstance(exc, (ValueError, TypeError)) else 'execution_error', error_type=type(exc).__name__, message=str(exc) or type(exc).__name__, retry_count=0)]
        for index, entry in enumerate(attempts):
            if entry.get('status') == 'success':
                continue
            self.state.execution.errors.append(ExecutionError(stage=self.stage, step_id=self.state.execution.current_step_id, code=entry.get('code', getattr(exc, 'code', 'execution_error')), error_type=entry.get('error_type', type(exc).__name__), message=entry.get('message') or str(exc) or type(exc).__name__, attempt=entry.get('retry_count', index) + 1))

    def _blocked(self, at):
        self.state.execution.status = 'blocked'
        self.state.execution.blocked_at = at
        self.state.execution.current_step_id = None
        plan = self.state.execution.execution_plan
        if plan:
            for step in plan.steps:
                if step.status == 'pending':
                    step.status = 'skipped'
        self._persist()
        outputs = self.state.agent_outputs
        reasons = [dict(state_id=s.state_id, reason=s.reason) for s in outputs.request_assessment.unresolved_states if s.blocker] if at == 'request_assessment' else [entry.model_dump(include={'state_id', 'reason'}) for entry in outputs.stylist_result.unresolved_states]
        source = BlockedSummaryInput(user_request=self.state.request.user_query, blocked_at=at, unresolved_states=reasons)
        try:
            response = self._call('blocked_summary', self.summary, source, 'blocked_response', method='run_blocked')
            outputs.blocked_response = BlockedResponse.model_validate(response.model_dump()).validate_against(source)
        except Exception as exc:
            self._record_error(exc)
            self._persist()
            outputs = self.state.agent_outputs
            try:
                response = self._call('fallback_summary', self.summary, source, 'fallback_response', method='run_blocked_fallback', failure_context=[f'{entry.code}: {entry.message}' for entry in self.state.execution.errors if entry.stage == 'blocked_summary'])
                outputs.fallback_response = BlockedResponse.model_validate(response.model_dump()).validate_against(source)
            except Exception as fallback_exc:
                self._record_error(fallback_exc)
        self._persist()

    @reuse_for('orchestrator')
    def run(self, request: PendingRequestState) -> OrchestratorState:
        source = PendingRequestState.model_validate(request.model_dump())
        self.events, self.artifacts = ([], {})
        self._stream_relation = None
        previous_commit_callback = getattr(self.search, 'candidate_committed_callback', None)
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            if any(self.output_dir.iterdir()):
                raise ValueError('Use a fresh output directory for each request.')
        versions = {name: agent.evaluation_version for name, agent in (('orchestrator', self.brain), ('planner', self.planner), ('stylist', self.stylist)) if getattr(agent, 'evaluation_version', None)}
        for name, agent, field in (('search', self.search, 'search_policy_version'), ('ranking', self.ranking, 'policy_version')):
            if getattr(agent, field, None):
                versions[name] = getattr(agent, field)
        from fashion_recommendation_v2.validation_reuse import reuse_enabled
        if reuse_enabled('orchestrator', versions.get('orchestrator')):
            for name, agent in (('relation', self.relation), ('summary', self.summary)):
                if getattr(agent, 'version', None):
                    versions[name] = agent.version
        if source.personalization_mode is not None:
            from fashion_recommendation_v2.orchestrator_policy import recorded_version
            versions['orchestrator'] = recorded_version(getattr(self.brain, 'evaluation_version', None), True)
            versions['ranking'] = getattr(self.ranking, 'policy_version', 'ranking_eval_v11')
        self.state = OrchestratorState(request=source, agent_versions=versions)
        self.stage = 'request_assessment'
        self._save('run', source)
        self._persist()
        try:
            from fashion_recommendation_v2.schemas.orchestrator import validate_agent_request
            validate_agent_request(source, versions)
            assessment = self._call('request_assessment', self.brain, source, 'request_assessment')
            assessment = validate_segmentation(assessment, source.user_query, version=versions.get('orchestrator'))
            validate_compatibility_assessment(source, assessment)
            self.state.agent_outputs.request_assessment = assessment
            self.state.unresolved_states = [UnresolvedState(state_id=s.state_id, description=s.description, resolution_agent=s.resolution_agent) for s in assessment.unresolved_states]
            if assessment.decision == 'blocked':
                self._blocked('request_assessment')
            else:
                self.state.request = RequestState(**RequestContext.model_validate(source.model_dump(exclude={'phase', 'goal', 'requested_count'})).model_dump(), goal=assessment.goal, requested_count=assessment.requested_count)
                usable = select_profile(source.preference_profile, assessment)
                self.state.request.usable_preference_profile = usable
                self.state.request.user_state = 'warm' if usable else 'cold'
                self._persist()
                self._execute()
        except Exception as exc:
            self._record_error(exc)
            if self.state.execution.status != 'blocked':
                self.state.execution.status = 'failed'
                plan = self.state.execution.execution_plan
                if plan:
                    for step in plan.steps:
                        if step.step_id == self.state.execution.current_step_id:
                            step.status = 'failed'
                        elif step.status == 'pending':
                            step.status = 'skipped'
            self._persist()
        finally:
            if self._stream_relation is not None:
                self._stream_relation.close()
                self.search.candidate_committed_callback = previous_commit_callback
        self._save('result', dict(status=self.state.execution.status, mode=source.mode, quality_evaluation='NOT_RUN', live_path_exercised=source.mode == 'live' and self.state.agent_outputs.candidate_set is not None, returned_count=self.state.agent_outputs.final_ranking.returned_count if self.state.agent_outputs.final_ranking else None, omitted_state_ids=[s.state_id for s in self.state.unresolved_states if s.status == 'unresolved'], error_count=len(self.state.execution.errors)))
        return self.state.model_copy(deep=True)

    def _execute(self):
        request = self.state.request
        assigned = [PlannerUnresolvedState(state_id=s.state_id, description=s.description, resolution_agent=s.resolution_agent) for s in self.state.unresolved_states]
        planner_input = PlannerInput(request_id=request.request_id, user_query=request.user_query, goal=f'{request.goal}\n최종 추천 개수: {request.requested_count}개', unresolved_states=assigned, state=PlannerStateSnapshot(user_state=request.user_state, product_source='ebay', profile_lookup_status=request.legacy_profile_lookup_status), relation_intent=self.state.agent_outputs.request_assessment.relation_intent, available_agents=[a for a in AVAILABLE_AGENTS if a.name in OUTPUTS and (assigned or a.name != 'stylist_agent') and (self.state.agent_outputs.request_assessment.relation_intent or a.name != 'relation_agent')])
        plan = self._call('planner', self.planner, planner_input, 'execution_plan')
        self.stage = 'plan_validation'
        plan = ExecutionPlan.model_validate(plan.model_dump())
        plan.steps = validate_plan(plan, assigned, require_profile=request.user_state == 'warm', require_relation=planner_input.relation_intent is not None)
        self.state.execution.execution_plan = plan
        self.state.execution.status = 'executing'
        self._persist()
        search_input = None
        completed = set()
        # _persist reconstructs snapshots; always address current plan/output objects.
        for index in range(len(plan.steps)):
            step = self.state.execution.execution_plan.steps[index]
            outputs = self.state.agent_outputs
            self.stage = step.agent.removesuffix('_agent')
            if not set(step.depends_on) <= completed:
                raise ValueError('Unmet plan dependency.')
            for reference in step.required_inputs:
                section, name = reference.split('.')
                value = getattr(getattr(self.state, section), name)
                if value is None and reference != 'request.preference_profile':
                    raise ValueError(f'Unavailable input: {reference}')
            step.status = 'running'
            self.state.execution.current_step_id = step.step_id
            self._persist()
            outputs = self.state.agent_outputs
            step = self.state.execution.execution_plan.steps[index]
            if step.agent == 'stylist_agent':
                if getattr(self.stylist, 'evaluation_version', None) in {'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8'}:
                    from fashion_recommendation_v2.schemas.stylist import StylistAgentInputV2_v2 as StylistAgentInputV2
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2
                    source = StylistAgentInputV2(user_request=request.user_query, unresolved_states=assigned, user_id=request.user_id, personalization_mode=effective_mode(request.personalization_mode, outputs.request_assessment.relation_intent) if self.stylist.evaluation_version in {'v5', 'v6', 'v7', 'v8'} else request.personalization_mode, **stylist_context(request, outputs.request_assessment, include_similarity=self.stylist.evaluation_version in {'v5', 'v6', 'v7', 'v8'}))
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV6
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV7_stylist_v7 as StylistResultV7
                    from fashion_recommendation_v2.schemas.stylist import StylistResultV8_stylist_v8 as StylistResultV8
                    if self.stylist.evaluation_version == 'v8':
                        from fashion_recommendation_v2.stylist_context import scoped_stylist_input
                        source = scoped_stylist_input(request, outputs.request_assessment, assigned)
                    result_schema = {'v8': StylistResultV8, 'v7': StylistResultV7, 'v6': StylistResultV6, 'v2': StylistResultV2, 'v3': StylistResultV3, 'v4': StylistResultV4, 'v5': StylistResultV5}[self.stylist.evaluation_version]
                else:
                    source = StylistAgentInput(user_request=request.user_query, unresolved_states=assigned, preference_profile=request.preference_profile, profile_lookup_status=request.legacy_profile_lookup_status, **stylist_context(request, outputs.request_assessment))
                    result_schema = StylistResult
                value = self._call('stylist', self.stylist, source, 'stylist_result')
                value = result_schema.model_validate(value.model_dump()).validate_against(source)
                outputs.stylist_result = value
                for state in self.state.unresolved_states:
                    state.status = 'resolved' if state.state_id in value.resolved_state_ids else 'unresolved'
                if not value.resolved_state_ids and (not any((unit.kind == 'clear_condition' for unit in outputs.request_assessment.semantic_units))):
                    step.status = 'completed'
                    self._blocked('stylist')
                    return
            elif step.agent == 'search_agent':
                self.stage = 'search_projection'
                search_input = project_search_request(request, outputs.request_assessment, outputs.stylist_result, contextual_audience=getattr(self.search, 'search_policy_version', None) in {'v24', 'v25', 'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}, search_policy_version=getattr(self.search, 'search_policy_version', None), orchestrator_version=self.state.agent_versions.get('orchestrator'))
                self._save('search_projection', search_input)
                if getattr(search_input, 'search_query_composition', None) is not None:
                    self._save('search_query_composition', search_input.search_query_composition)
                intent = outputs.request_assessment.relation_intent
                from fashion_recommendation_v2.agents.relation import RelationAgent
                if getattr(self.search, 'search_policy_version', None) in {'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and intent is not None and (intent.relation_type in {'similarity', 'compatibility'}) and isinstance(self.relation, RelationAgent):
                    from fashion_recommendation_v2.relation.streaming import StreamingRelation
                    anchor_ref = next((r for r in request.reference_items if r.item.item_id == intent.anchor_item_id), None)
                    try:
                        self._stream_relation = StreamingRelation(self.relation, intent=intent, anchor_item=anchor_ref.item if anchor_ref else None, anchor_search_analysis=anchor_ref.search_analysis if anchor_ref else None)
                    except Exception:
                        # Preserve the existing Relation-stage failure/fallback policy.
                        self._stream_relation = None

                    def committed(snapshot):
                        routing = snapshot.resolved_requirements.condition_routing_v37
                        if intent.source_text in search_input.user_query or (routing and any((r.intent == intent for r in routing.relation_conditions))):
                            if self._stream_relation is not None:
                                self._stream_relation.submit(snapshot)
                    if self._stream_relation is not None:
                        self.search.candidate_committed_callback = committed
                value = self._call('search', self.search, search_input, 'candidate_set')
                value = CandidateSet.model_validate(value.model_dump())
                if value.candidate_count != len(value.candidates) or len({c.item.item_id for c in value.candidates}) != value.candidate_count:
                    raise ValueError('Invalid candidate counts or duplicate IDs.')
                if value.resolved_requirements is None:
                    raise ValueError('Search must return resolved requirements.')
                if getattr(self.search, 'search_policy_version', None) in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    from fashion_recommendation_v2.search.requirements import validate_consumed_sources
                    from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchCodeValidationV31
                    observations = validate_consumed_sources(search_input, value.resolved_requirements)
                    if value.code_validation_v31 is None:
                        value.code_validation_v31 = SearchCodeValidationV31()
                    value.code_validation_v31.semantic_observations.extend(observations)
                elif getattr(self.search, 'search_policy_version', None) in {'v25', 'v26', 'v30'}:
                    from fashion_recommendation_v2.search.requirement_sources import validate_field_sources
                    validate_field_sources(search_input, value.resolved_requirements)
                elif any((entry.source != 'context' and entry.source_text not in search_input.user_query for entry in value.resolved_requirements.requirements)):
                    raise ValueError('Search requirement evidence must belong to the projected request.')
                from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import validate_audience_requirements
                audience_context = search_input.audience_context_v1
                if getattr(self.search, 'search_policy_version', None) in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    from fashion_recommendation_v2.search.audience_policy import audience_context_v30
                    audience_context = audience_context_v30(search_input)
                validate_audience_requirements(value.resolved_requirements, audience_context)
                if getattr(self.search, 'search_policy_version', None) in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30
                    validate_stylist_requirements(search_input, value.resolved_requirements, semantic_key=provenance_dimension_v30)
                else:
                    validate_stylist_requirements(search_input, value.resolved_requirements)
                intent = outputs.request_assessment.relation_intent
                if intent and intent.relation_type == 'similarity':
                    value.candidates = [c for c in value.candidates if c.item.item_id != intent.anchor_item_id]
                    value.candidate_count = len(value.candidates)
                outputs.candidate_set = value
                if not value.candidates and value.stop_reason == 'no_viable_search_strategy':
                    self.stage = 'search'
                    raise SearchPlanUnavailable('No executable search strategy; see candidate_set.warnings.')
                if not value.candidates and value.search_attempts and all((attempt.status == 'failed' for attempt in value.search_attempts)):
                    self.stage = 'search'
                    raise SearchUnavailable('All marketplace search attempts failed; see candidate_set.search_attempts.')
            elif step.agent == 'relation_agent':
                intent = outputs.request_assessment.relation_intent
                anchor = next((r.item for r in request.reference_items if r.item.item_id == intent.anchor_item_id), None)
                relation_fields = {}
                if getattr(self.search, 'search_policy_version', None) in {'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    relation_fields = dict(evaluation_version='v0', anchor_search_analysis=next((r.search_analysis for r in request.reference_items if r.item.item_id == intent.anchor_item_id), None))
                preparation_error = None
                if getattr(self.search, 'search_policy_version', None) in {'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    relation_fields['evaluation_version'] = 'v6' if self.search.search_policy_version in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 'v5'
                if getattr(self.relation, 'version', None) and getattr(self.search, 'search_policy_version', None) in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    relation_fields['evaluation_version'] = self.relation.version
                try:
                    source = RelationAgentInput(candidate_set=outputs.candidate_set, intent=intent, anchor_item=anchor, **relation_fields)
                    if relation_fields:
                        from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
                        evidence_input_hash = get_relation_contract(source.evaluation_version).evidence().evidence_input_hash
                        relation_fields['evidence_input_sha256'] = evidence_input_hash(source)
                        if source.evaluation_version in {'v5', 'v6', 'v7', 'v8', 'v9'}:
                            relation_fields['score_breakdowns_v5'] = {}
                except ValueError as exc:
                    if getattr(self.search, 'search_policy_version', None) in {'v37', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                        raise
                    if not relation_fields:
                        # Identity/contract failure must not resurrect raw item facts.
                        raise
                    # Historical anchors may have no Search observation. Keep
                    # the existing Ranking fallback, without scoring raw metadata.
                    preparation_error = exc
                    relation_fields = {}
                    source = RelationAgentInput(candidate_set=outputs.candidate_set, intent=intent, anchor_item=anchor)
                if intent.source_text not in search_input.user_query and (not (getattr(self.search, 'search_policy_version', None) in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and outputs.candidate_set.resolved_requirements.condition_routing_v37 and any((r.intent == intent for r in outputs.candidate_set.resolved_requirements.condition_routing_v37.relation_conditions)))):
                    value = RelationRatio(**relation_fields, omitted=True, candidate_set_id=source.candidate_set.candidate_set_id, intent=intent, anchor_item=anchor, evaluations=[], unevaluated_item_ids=[c.item.item_id for c in source.candidate_set.candidates], warnings=['미해결 관계 조건을 평가에 사용하지 않았습니다.'])
                    self._save('ralationRatio', value)
                else:
                    try:
                        if preparation_error is not None:
                            raise preparation_error
                        if self.relation is None:
                            raise ValueError('Relation Agent is not configured.')
                        value = self._call('relation', self._stream_relation or self.relation, source, 'ralationRatio')
                        value = RelationRatio.model_validate(value.model_dump()).validate_against(source)
                    except Exception as exc:
                        self._record_error(exc)
                        value = RelationRatio(**relation_fields, candidate_set_id=source.candidate_set.candidate_set_id, intent=intent, anchor_item=anchor, evaluations=[], unevaluated_item_ids=[c.item.item_id for c in source.candidate_set.candidates], warnings=['관계 평가 실행에 실패하여 기존 Ranking으로 진행했습니다.'])
                        self._save('ralationRatio', value)
                outputs.ralationRatio = RelationRatio.model_validate(value.model_dump()).validate_against(source)
            elif step.agent == 'ranking_agent':
                from fashion_recommendation_v2.validation_reuse import enable_validation_reuse
                enable_validation_reuse()
                source = RankingAgentInput(candidate_set=outputs.candidate_set, user_request=search_input.user_query, requested_count=request.requested_count, preference_profile=request.usable_preference_profile, ralationRatio=outputs.usable_relation)
                if request.personalization_mode is not None:
                    from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV11_v11 as RankingAgentInputV11
                    input_schema = RankingAgentInputV11
                    if getattr(self.ranking, 'policy_version', None) == 'ranking_eval_v12':
                        from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV12_v12 as RankingAgentInputV12
                        input_schema = RankingAgentInputV12
                    if getattr(self.ranking, 'policy_version', None) in {'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17'}:
                        from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV13
                        input_schema = RankingAgentInputV13
                    source = input_schema(candidate_set=outputs.candidate_set, user_request=request.user_query, requested_count=request.requested_count, personalization_mode=effective_mode(request.personalization_mode, outputs.request_assessment.relation_intent) if self.ranking.policy_version in {'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17'} else request.personalization_mode, ralationRatio=outputs.usable_relation, relation_intent=outputs.request_assessment.relation_intent)
                value = self._call('ranking', self.ranking, source, 'final_ranking')
                from fashion_recommendation_v2.orchestrator_policy import assessment_contract
                if assessment_contract(self.brain.evaluation_version).reuse_ranking_handoff:
                    self._accept_ranking_and_persist(value, source, step, completed)
                    continue
                # Match the exact input used by the current Ranking implementation.
                with measure_processing('orchestrator.ranking_return_validation'):
                    outputs.final_ranking = FinalRanking.model_validate(value.model_dump()).validate_against(source)
                personalization = outputs.final_ranking.personalization_v12 or outputs.final_ranking.personalization_v11
                if personalization is not None:
                    self.state.request.profile_lookup_status = personalization['profile_lookup_status']
            else:
                with measure_processing('orchestrator.summary_input'):
                    source = SummaryAgentInput(user_request=request.user_query, candidate_set=outputs.candidate_set, final_ranking=outputs.final_ranking, preference_profile=request.usable_preference_profile, ralationRatio=outputs.usable_relation, interaction_collection_enabled=request.interaction_collection_enabled, profile_updates_enabled=request.profile_updates_enabled, omitted_conditions=omitted_conditions(outputs.request_assessment, outputs.stylist_result))
                value = self._call('summary', self.summary, source, 'recommendation_response')
                with measure_processing('orchestrator.final_response_validation'):
                    outputs.recommendation_response = validate_summary_response(value, source)
            step.status = 'completed'
            completed.add(step.step_id)
            self.state.execution.current_step_id = None
            self._persist()
        self.state.execution.status = 'completed'
        self._persist()
