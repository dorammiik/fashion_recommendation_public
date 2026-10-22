"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- streaming_v52 ----

"""Request-local Relation queue fed only by committed, validated Search candidates."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from time import monotonic
from fashion_recommendation_v2.llm.cost_tracking import record_call_context
from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
from fashion_recommendation_v2.relation.relation_evidence import canonical_hash
from fashion_recommendation_v2.schemas.relation import RelationAgentInput
from fashion_recommendation_v2.schemas.relation import RelationRatio

@_preserve_class('StreamingRelation', 'fashion_recommendation_v2.relation.streaming_v52')
class StreamingRelation:

    def __init__(self, agent, *, intent, anchor_item=None, anchor_search_analysis=None):
        self.agent = agent
        self.version = agent.version or 'v6'
        self.contract = get_relation_contract(self.version)
        if self.contract.execution_module and agent.batch_size not in (None, 1):
            raise ValueError('Relation v7 requires one candidate per call.')
        self.fields = dict(intent=intent.model_copy(deep=True), anchor_item=anchor_item.model_copy(deep=True) if anchor_item else None, anchor_search_analysis=anchor_search_analysis.model_copy(deep=True) if anchor_search_analysis else None, evaluation_version=self.version)
        self.max_calls = agent.max_calls if agent.max_calls is not None else agent.max_candidates * 2 if self.contract.execution_module else 10
        self.calls = 0
        self.entries = {}
        self.preparation_errors = []
        self.selected_ids = set()
        self.generation_attempts = []
        self.progress_callback = None
        self.pool = ThreadPoolExecutor(max_workers=agent.max_workers)
        if agent.llm is None:
            from fashion_recommendation_v2.llm.openai_adapter import OpenAIStructuredLLM
            agent.llm = OpenAIStructuredLLM(model=self.contract.default_model)

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def key(source, candidate):
        return canonical_hash(dict(version=source.evaluation_version, intent=source.intent.model_dump(mode='json'), anchor=source.anchor_item.model_dump(mode='json') if source.anchor_item else None, anchor_analysis=source.anchor_search_analysis.model_dump(mode='json') if source.anchor_search_analysis else None, item=candidate.item.model_dump(mode='json'), analysis=candidate.search_analysis.model_dump(mode='json') if candidate.search_analysis else None, evaluation_item=candidate.evaluation_item.model_dump(mode='json') if candidate.evaluation_item else None, requirements=source.candidate_set.resolved_requirements.model_dump(mode='json') if source.candidate_set.resolved_requirements else None))

    def submit(self, candidate_set):
        try:
            source = RelationAgentInput(candidate_set=candidate_set.model_copy(deep=True), **self.fields)
            self._submit(source)
        except Exception as exc:
            # Relation preparation cannot turn a valid Search result into a search failure.
            # The final Relation boundary still validates the complete source normally.
            self.preparation_errors.append(dict(stage='preparation', status='error', error_type=type(exc).__name__, message=str(exc), batch_item_ids=[c.item.item_id for c in candidate_set.candidates]))

    def _submit(self, source):
        for candidate in source.candidate_set.candidates:
            item_id = candidate.item.item_id
            if item_id == source.intent.anchor_item_id:
                continue
            key = self.key(source, candidate)
            if key in self.entries:
                continue
            if item_id not in self.selected_ids and len(self.selected_ids) >= self.agent.max_candidates:
                continue
            self.selected_ids.add(item_id)
            if self.calls >= self.max_calls:
                continue
            frozen = source.model_copy(deep=True)
            frozen.candidate_set.candidates = [candidate.model_copy(deep=True)]
            frozen.candidate_set.candidate_count = 1
            self.calls += 1
            self.entries[key] = dict(source=frozen, records=[], future=self.pool.submit(copy_context().run, self._evaluate, frozen, 0, []))

    def _evaluate(self, source, retry, feedback):
        from fashion_recommendation_v2.agents.relation import RelationAgent
        item_id = source.candidate_set.candidates[0].item.item_id
        started = monotonic()
        with record_call_context(agent='relation', version=self.version, item_id=item_id, stage='correction' if retry else 'generation', retry_count=retry) as costs:
            worker = RelationAgent(llm=self.agent.llm, batch_size=1, max_calls=1)
            try:
                ratio = worker._run_serial(source, only_item=item_id, retry_start=retry, initial_feedback=feedback)
                records = worker.generation_attempts
            except Exception as exc:
                ratio = None
                records = [dict(status='error', retry_count=retry, error_type=type(exc).__name__, message=str(exc), applied=False, **getattr(exc, 'response_snapshot', {}))]
        for record in records:
            record.update(item_id=item_id, batch_item_ids=[item_id], stage='correction' if retry else 'generation', elapsed_seconds=round(monotonic() - started, 6), cost_call_ids=list(costs), cost_records=list(costs.values()))
        return (ratio, records)

    def run(self, input_data):
        source = RelationAgentInput.model_validate(input_data.model_dump())
        # Includes late replacements and detects any changed anchor/intent/evidence.
        self._submit(source)
        entries = {}
        for candidate in source.candidate_set.candidates:
            key = self.key(source, candidate)
            if key in self.entries:
                entries[candidate.item.item_id] = self.entries[key]
        # Search has ended. Finish all initial evaluations before spending correction budget.
        for entry in self.entries.values():
            ratio, records = entry['future'].result()
            entry['ratio'] = ratio
            entry['records'] = records
        for item_id, entry in entries.items():
            ratio = entry['ratio']
            if (ratio is None or not ratio.evaluations) and self.calls < self.max_calls:
                self.calls += 1
                entry['correction'] = self.pool.submit(copy_context().run, self._evaluate, entry['source'], 1, [r['message'] for r in entry['records'] if r.get('status') == 'error'])
        for entry in entries.values():
            if 'correction' in entry:
                ratio, records = entry['correction'].result()
                entry['ratio'] = ratio
                entry['records'].extend(records)
        evaluations, breakdowns, outcomes = ([], {}, {})
        # Retrieval frequency/order and pool bookkeeping are not evaluation evidence.
        for candidate in source.candidate_set.candidates:
            item_id = candidate.item.item_id
            entry = entries.get(item_id)
            ratio = entry['ratio'] if entry else None
            records = entry['records'] if entry else []
            success = ratio is not None and bool(ratio.evaluations)
            if success:
                evaluations.extend(ratio.evaluations)
                if self.contract.scoring_module:
                    breakdowns.update(getattr(ratio, self.contract.breakdown_field))
            status = 'success' if success else 'fail' if len(records) == 2 else 'unevaluated'
            reason = 'evaluated' if success else 'anchor_excluded' if item_id == source.intent.anchor_item_id else 'candidate_budget' if item_id not in self.selected_ids else 'correction_failed' if status == 'fail' else 'correction_budget' if records else 'call_budget'
            outcomes[item_id] = dict(status=status, call_count=len(records), reason=reason, errors=[r['message'] for r in records if r.get('status') == 'error'], cost_call_ids=[k for r in records for k in r.get('cost_call_ids', [])])
        final_keys = {self.key(source, c) for c in source.candidate_set.candidates}
        self.generation_attempts = self.preparation_errors + [dict(r, evidence_key=key, retained_in_final_pool=key in final_keys) for key, entry in self.entries.items() for r in entry['records']]
        self.agent.generation_attempts = self.generation_attempts
        missing = [i for i, status in outcomes.items() if status['status'] != 'success']
        return RelationRatio(evaluation_version=source.evaluation_version, candidate_set_id=source.candidate_set.candidate_set_id, intent=source.intent, anchor_item=source.anchor_item, anchor_search_analysis=source.anchor_search_analysis, evaluations=evaluations, unevaluated_item_ids=missing, warnings=['일부 후보 관계 평가 실패·미평가: 후보별 실행 기록을 확인하세요.'] if missing else [], **dict(evidence_input_sha256=self.contract.evidence().evidence_input_hash(source)) if self.contract.evidence_module else {}, **{self.contract.breakdown_field: breakdowns} if self.contract.scoring_module else {}, **dict(item_statuses_v7=outcomes) if self.contract.execution_module else {}).validate_against(source)
