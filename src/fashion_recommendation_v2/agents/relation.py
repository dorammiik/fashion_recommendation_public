"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation ----

"""Bounded versioned relationship evaluation with auditable ranking fallback."""
from fashion_recommendation_v2.schemas.relation import RelationAgentInput
from fashion_recommendation_v2.schemas.relation import RelationRatio
from copy import deepcopy
from fashion_recommendation_v2.relation.execution import MAX_WORKERS
from fashion_recommendation_v2.relation.execution import MAX_CANDIDATES
from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract

@_preserve_class('RelationAgent', 'fashion_recommendation_v2.agents.relation')
class RelationAgent:

    def __init__(self, *, llm=None, version=None, batch_size=None, max_candidates=MAX_CANDIDATES, max_calls=None, max_workers=MAX_WORKERS):
        if min(batch_size if batch_size is not None else 10, max_candidates, max_calls if max_calls is not None else 10, max_workers) < 1:
            raise ValueError('Relation budgets must be positive.')
        if max_workers > MAX_WORKERS:
            raise ValueError('Relation supports at most 20 workers.')
        self.version = version
        self.max_workers = max_workers
        self.llm = llm
        self.batch_size, self.max_candidates, self.max_calls = (batch_size, max_candidates, max_calls)
        self.generation_attempts = []
        self.progress_callback = None

    def run(self, input_data):
        if self.llm is None:
            from fashion_recommendation_v2.llm.openai_adapter import OpenAIStructuredLLM
            self.llm = OpenAIStructuredLLM(model=get_relation_contract(input_data.evaluation_version).default_model)
        if get_relation_contract(input_data.evaluation_version).execution_module:
            return self._run_parallel(input_data)
        return self._run_serial(input_data)

    def _run_parallel(self, input_data):
        from fashion_recommendation_v2.relation.execution import run_candidates
        from fashion_recommendation_v2.relation.execution import CALLS_PER_CANDIDATE
        source = RelationAgentInput.model_validate(input_data.model_dump())
        if self.batch_size not in (None, 1):
            raise ValueError('Relation v7 requires one candidate per call.')

        def evaluate(item_id, retry, feedback):
            worker = RelationAgent(llm=self.llm, batch_size=1, max_candidates=self.max_candidates, max_calls=1)
            ratio = worker._run_serial(source, only_item=item_id, retry_start=retry, initial_feedback=feedback)
            return (ratio, worker.generation_attempts)
        results, self.generation_attempts, outcomes = run_candidates(source, evaluate, max_candidates=self.max_candidates, max_calls=self.max_calls if self.max_calls is not None else self.max_candidates * CALLS_PER_CANDIDATE, workers=self.max_workers, progress=self.progress_callback)
        contract = get_relation_contract(source.evaluation_version)
        return RelationRatio(evaluation_version=source.evaluation_version, candidate_set_id=source.candidate_set.candidate_set_id, anchor_item=source.anchor_item, anchor_search_analysis=source.anchor_search_analysis, intent=source.intent, evidence_input_sha256=contract.evidence().evidence_input_hash(source), evaluations=[e for i in outcomes if i in results for e in results[i].evaluations], score_breakdowns_v5={i: ratio.score_breakdowns_v5[i] for i, ratio in results.items()}, unevaluated_item_ids=[i for i, record in outcomes.items() if record['status'] != 'success'], item_statuses_v7=outcomes, warnings=['일부 후보 관계 평가 실패·미평가: 후보별 실행 기록을 확인하세요.'] if any((r['status'] != 'success' for r in outcomes.values())) else []).validate_against(source)

    def _run_serial(self, input_data, *, only_item=None, retry_start=0, initial_feedback=()):
        source = RelationAgentInput.model_validate(input_data.model_dump())
        self.generation_attempts = []
        all_items = [c.item for c in source.candidate_set.candidates]
        items = [i for i in all_items if i.item_id != source.intent.anchor_item_id and (only_item is None or i.item_id == only_item)][:self.max_candidates]
        batch_size = self.batch_size or 10
        max_calls = self.max_calls if self.max_calls is not None else 10
        evaluations, warnings = ([], [])
        version_fields = {}
        contract = get_relation_contract(source.evaluation_version)
        prompt = contract.prompt()
        input_schema = contract.schema(contract.input_name)
        output_schema = contract.schema(contract.output_name)
        score_breakdowns = {}
        if contract.evidence_module:
            evidence = contract.evidence()
            anchor_evidence, candidate_evidence = evidence.packets(source)
            version_fields = dict(evaluation_version=source.evaluation_version, anchor_search_analysis=source.anchor_search_analysis, evidence_input_sha256=evidence.evidence_input_hash(source))
        calls = 0
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            feedback = list(initial_feedback)
            for retry in range(retry_start, 2):
                if calls >= max_calls:
                    break
                calls += 1
                rejected_response = None
                raw_snapshot = {}
                try:
                    payload = input_schema(intent=source.intent.model_dump(mode='json'), anchor=anchor_evidence, items=[candidate_evidence[i.item_id] for i in batch], validation_feedback=feedback) if contract.evidence_module else input_schema(intent=source.intent, anchor_item=source.anchor_item, items=batch, validation_feedback=feedback)
                    if contract.output_schema_builder:
                        scorer = contract.scorer()
                        output_schema = contract.schema(contract.output_schema_builder)(payload, {name: scorer.FACETS[name] for name in scorer.WEIGHTS[source.intent.relation_type]})
                    result = self.llm.generate(system_prompt=prompt, user_input=payload.model_copy(deep=True), output_schema=output_schema)
                    # Snapshot before validation discards a response, and before a retry.
                    rejected_response = result.model_dump(mode='json') if hasattr(result, 'model_dump') else deepcopy(result)
                    if contract.capture_response:
                        original = getattr(result, '_model_response', None)
                        raw_snapshot = dict(model_response=deepcopy(original if original is not None else rejected_response), model_response_text=getattr(result, '_model_response_text', None))
                    result = output_schema.model_validate(rejected_response)
                    ids = [e.item_id for e in result.evaluations]
                    if len(ids) != len(batch) or set(ids) != {i.item_id for i in batch}:
                        raise ValueError('Batch must return each input item exactly once.')
                    if contract.scoring_module:
                        applied_evaluations, batch_breakdowns = contract.scorer().derive(source, result)
                        derived_fields = {contract.breakdown_field: batch_breakdowns}
                    else:
                        applied_evaluations, batch_breakdowns, derived_fields = (result.evaluations, {}, {})
                    RelationRatio(**version_fields, anchor_item=source.anchor_item, candidate_set_id=source.candidate_set.candidate_set_id, intent=source.intent, evaluations=applied_evaluations, **derived_fields, unevaluated_item_ids=[i.item_id for i in all_items if i.item_id not in ids]).validate_against(source, require_execution=source.evaluation_version not in {'v7', 'v8', 'v9'})
                except Exception as exc:
                    feedback = [str(exc) or type(exc).__name__]
                    if contract.capture_response:
                        raw_snapshot.update(deepcopy(getattr(exc, 'response_snapshot', {})))
                        raw_snapshot.update(code_validation=dict(valid=False, errors=feedback), stage='generation' if retry == 0 else 'correction', applied=False)
                    self.generation_attempts.append(dict(batch_start=start, retry_count=retry, status='error', error_type=type(exc).__name__, message=feedback[0], batch_item_ids=[item.item_id for item in batch], validation_issues=getattr(exc, 'issues', []), rejected_response=rejected_response, **raw_snapshot))
                else:
                    evaluations.extend(applied_evaluations)
                    score_breakdowns.update(batch_breakdowns)
                    if contract.capture_response:
                        raw_snapshot.update(code_validation=dict(valid=True, errors=[]), stage='generation' if retry == 0 else 'correction', applied=True, batch_item_ids=[item.item_id for item in batch])
                        if contract.scoring_module:
                            raw_snapshot['code_derived_result'] = dict(evaluations=[e.model_dump(mode='json') for e in applied_evaluations], **{contract.breakdown_field: {k: v.model_dump(mode='json') for k, v in batch_breakdowns.items()}})
                    self.generation_attempts.append(dict(batch_start=start, retry_count=retry, status='success', **raw_snapshot))
                    break
            if self.progress_callback:
                self.progress_callback(dict(stage='relation', completed_batches=start // batch_size + 1, total_batches=(len(items) + batch_size - 1) // batch_size))
        done = {e.item_id for e in evaluations}
        missing = [i.item_id for i in all_items if i.item_id not in done]
        if missing:
            warnings.append('관계 평가 실패·예산 제한·기준 상품 제외로 일부 후보의 관계 점수를 사용하지 않았습니다.')
        return RelationRatio(**version_fields, anchor_item=source.anchor_item, candidate_set_id=source.candidate_set.candidate_set_id, intent=source.intent, evaluations=evaluations, unevaluated_item_ids=missing, warnings=warnings, **{contract.breakdown_field: score_breakdowns} if contract.scoring_module else {}).validate_against(source, require_execution=source.evaluation_version not in {'v7', 'v8', 'v9'})
