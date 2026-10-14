"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- partial_evaluation_v10 ----
"""Deterministic eligibility projection; immutable originals remain with the caller.

Only the scoring view is narrowed. Retrieval history and all score policies stay
unchanged. Output validation independently recomputes exclusions from the input.
"""
from fashion_recommendation_v2.schemas.ranking import UpstreamFailureV10
from fashion_recommendation_v2.schemas.ranking import RANKING_V10
from fashion_recommendation_v2.schemas.ranking import RANKING_V10_RELATION
from fashion_recommendation_v2.schemas.relation import RelationAgentInput
from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
from fashion_recommendation_v2.search.contracts import get_search_contracts
from fashion_recommendation_v2.search.product_validation import validate_analysis


@_preserve_function('project', 'fashion_recommendation_v2.ranking.partial_evaluation_v10')
def project(input_data):
    source = input_data.candidate_set
    ratio = input_data.ralationRatio
    routing = source.resolved_requirements.condition_routing_v37
    required = bool(ratio or input_data.relation_intent or routing and routing.relation_conditions)
    failures = {}
    done = {e.item_id for e in ratio.evaluations} if ratio else set()
    for candidate in source.candidates:
        i = candidate.item.item_id
        analysis = candidate.search_analysis
        failure = None
        if analysis is None:
            errors = [(ai, ei, e) for ai, a in enumerate(source.search_attempts)
                      for ei, e in enumerate(a.item_evaluations)
                      if e.item_id == i and e.status in {'evaluation_error', 'image_fetch_error'}]
            failure = UpstreamFailureV10(stage='search', status='fail' if errors else 'unevaluated',
                reason='; '.join(e.error_message or e.status for _, _, e in errors) if errors else 'No saved Search evaluation.',
                source_paths=[f'candidate_set.search_attempts.{ai}.item_evaluations.{ei}' for ai, ei, _ in errors]
                    or [f'candidate_set.candidates[{i}].search_analysis'])
        else:
            try:
                if analysis.evaluation_policy != get_search_contracts(source.search_policy_version).product_evaluation.version:
                    raise ValueError('Search evaluation version differs from its contract.')
                item = candidate.evaluation_item or candidate.item
                if (analysis.item_id, analysis.image_url) != (candidate.item.item_id, candidate.item.image_url):
                    raise ValueError('Search evaluation identity mismatch.')
                validate_analysis(analysis, item, source.resolved_requirements, source.price_conversion)
            except (ValueError, TypeError, AttributeError) as exc:
                failure = UpstreamFailureV10(stage='search', status='fail', reason=str(exc),
                    source_paths=[f'candidate_set.candidates[{i}].search_analysis'])
        if failure is None and required and i not in done:
            execution = (ratio.item_statuses_v7 or {}).get(i) if ratio else None
            failure = UpstreamFailureV10(stage='relation',
                status=execution.status if execution and execution.status == 'fail' else 'unevaluated',
                reason='; '.join([execution.reason, *execution.errors]) if execution else 'Required Relation evaluation is absent or failed (legacy result does not distinguish).',
                source_paths=[f'ralationRatio.item_statuses_v7[{i}]' if execution else
                              'ralationRatio.unevaluated_item_ids' if ratio else 'ralationRatio'])
        if failure is not None:
            failures[i] = failure
    retained = [c for c in source.candidates if c.item.item_id not in failures]
    pool = source.model_copy(deep=True, update={'candidates': retained, 'candidate_count': len(retained)})
    projected = input_data.model_copy(deep=True, update={'candidate_set': pool})
    if ratio is not None:
        ids = {c.item.item_id for c in retained}
        updates = dict(evaluations=[e for e in ratio.evaluations if e.item_id in ids],
            unevaluated_item_ids=[i for i in ratio.unevaluated_item_ids if i in ids])
        for field in ('score_breakdowns_v3', 'score_breakdowns_v4', 'score_breakdowns_v5', 'item_statuses_v7'):
            value = getattr(ratio, field)
            if value is not None:
                updates[field] = {i: r for i, r in value.items() if i in ids}
        contract = get_relation_contract(ratio.evaluation_version)
        if contract.evidence_module:
            relation_source = RelationAgentInput(candidate_set=pool, intent=ratio.intent,
                anchor_item=ratio.anchor_item, anchor_search_analysis=ratio.anchor_search_analysis,
                evaluation_version=ratio.evaluation_version)
            updates['evidence_input_sha256'] = contract.evidence().evidence_input_hash(relation_source)
        projected.ralationRatio = ratio.model_copy(deep=True, update=updates)
    return projected, failures


@_preserve_function('legacy_view', 'fashion_recommendation_v2.ranking.partial_evaluation_v10')
def legacy_view(result):
    """Validate unchanged score fields with their original v9 contract."""
    data = result.model_dump(mode='json')
    failures = data.pop('upstream_exclusions_v10', {}) or {}
    data['scoring_policy_version'] = 'ranking_eval_v9_relation' if result.scoring_policy_version == RANKING_V10_RELATION else 'ranking_eval_v9'
    data['excluded_items'] = [e for e in data['excluded_items'] if e['item_id'] not in failures]
    return result.__class__.model_validate(data)


@_preserve_function('validate_output', 'fashion_recommendation_v2.ranking.partial_evaluation_v10')
def validate_output(result):
    failures = result.upstream_exclusions_v10
    if failures is None:
        raise ValueError('Ranking v10 requires upstream exclusion accounting, including an empty map.')
    ids = [e.item_id for e in [*result.ranked_items, *result.excluded_items]]
    if len(ids) != len(set(ids)):
        raise ValueError('Ranking output IDs must be unique.')
    by_id = {e.item_id: e for e in result.excluded_items}
    for i, failure in failures.items():
        entry = by_id.get(i)
        if entry is None or entry.reason_codes != [failure.reason_code]:
            raise ValueError('Upstream failure requires its exact excluded ID/reason.')
        if (entry.requirement_assessments or entry.hard_constraint_assessments or
                entry.request_relevance_score is not None or entry.thumbnail_quality_assessment is not None):
            raise ValueError('Excluded upstream failures cannot have fabricated assessments.')
    legacy_view(result)
    return result


@_preserve_function('validate_against', 'fashion_recommendation_v2.ranking.partial_evaluation_v10')
def validate_against(result, source):
    projected, failures = project(source)
    if failures != result.upstream_exclusions_v10:
        raise ValueError('Upstream exclusions differ from the original saved input.')
    legacy_view(result).validate_against(projected)
    return result


@_preserve_function('run', 'fashion_recommendation_v2.ranking.partial_evaluation_v10')
def run(input_data, score):
    projected, failures = project(input_data)
    result = score(projected)
    data = result.model_dump(mode='json')
    data['scoring_policy_version'] = RANKING_V10_RELATION if input_data.ralationRatio else RANKING_V10
    data['upstream_exclusions_v10'] = {i: f.model_dump() for i, f in failures.items()}
    data['excluded_items'].extend(dict(item_id=i, reason_codes=[f.reason_code],
        requirement_assessments=[], hard_constraint_assessments=[]) for i, f in failures.items())
    if failures:
        data['warnings'].append(f'Search/Relation 실패·미평가 후보 {len(failures)}개 제외; 원입력과 실패 기록은 보존.')
        if result.status != 'complete':
            data['shortfall_reasons'] = [r for r in data['shortfall_reasons'] if r != 'Search에서 반환한 후보가 없음.']
            data['shortfall_reasons'].extend(f'{i}: {f.reason_code} — {f.reason}' for i, f in failures.items())
    return result.__class__.model_validate(data).validate_against(input_data)
