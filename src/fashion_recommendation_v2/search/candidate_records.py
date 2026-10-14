"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- candidate_records ----
"""Code-only v30 candidate record validation; never rewrites model responses."""
from hashlib import sha256
import json

from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemEvaluation as SearchItemEvaluation_base
from fashion_recommendation_v2.search.product_validation import validate_analysis as validate_analysis_base
from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear as excluded_childrenswear_base


@_preserve_function('evidence_snapshot', 'fashion_recommendation_v2.search.candidate_records')
def evidence_snapshot_base(item):
    data = item.model_dump(mode='json')
    # Retrieval rank is a source signal, not product/image evidence.
    data.get('raw_metadata', {}).pop('native_order', None)
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@_preserve_function('evaluation_context_snapshot', 'fashion_recommendation_v2.search.candidate_records')
def evaluation_context_snapshot(context):
    data = {key: (value.model_dump(mode='json') if hasattr(value, 'model_dump') else value)
            for key in ('input_data', 'requirements', 'conversion', 'search_policy_version')
            for value in [context.get(key)]}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@_preserve_function('invalid_record', 'fashion_recommendation_v2.search.candidate_records')
def invalid_record_base(outcome, exc, *, item_id=None):
    """Keep the entire invalid code record alongside a serializable error envelope.

    evaluation_recovery is the existing code trace field. The LLM's independently
    recorded model_response is never edited, and no invalid field is discarded.
    """
    raw = outcome.model_dump(mode='json', warnings=False)
    return SearchItemEvaluation_base(item_id=item_id or str(outcome.item_id), batch_id=str(outcome.batch_id),
        status='evaluation_error', reasons=['candidate_record_invalid'],
        evaluation_mode='fresh' if outcome.evaluation_mode == 'fresh' else 'duplicate_unresolved',
        retained_in_pool=outcome.retained_in_pool is True,
        error_type=type(exc).__name__, error_message=str(exc),
        evaluation_recovery=dict(original_record=raw,
            code_validation=dict(status='invalid', error_type=type(exc).__name__, message=str(exc))))


@_preserve_function('validate_record', 'fashion_recommendation_v2.search.candidate_records')
def validate_record_base(outcome, item, representative, requirements, conversion):
    """Validate storage and actual evidence before this product enters the pool."""
    try:
        # Pydantic instances/assignment can bypass nested validation until JSON
        # reload. Exercise that exact storage contract at the item boundary.
        SearchItemEvaluation_base.model_validate_json(outcome.model_dump_json(warnings=False))
        if outcome.status in {'evaluation_error', 'image_fetch_error', 'duplicate_skipped'}:
            return outcome
        if item is None or representative is None or outcome.analysis is None:
            raise ValueError('Product evaluation requires its actual product and analysis.')
        if outcome.item_id != item.item_id or evidence_snapshot_base(item) != evidence_snapshot_base(representative):
            raise ValueError('Evaluation representative differs from the retrieved product evidence.')
        if outcome.evaluation_mode == 'reused':
            if (outcome.evaluation_source_item is None
                    or outcome.evaluation_source_item_id != item.item_id
                    or not outcome.evaluation_source_attempt_id
                    or not outcome.duplicate_match_fields
                    or evidence_snapshot_base(outcome.evaluation_source_item) != evidence_snapshot_base(item)):
                raise ValueError('Reused evaluation has no matching product evidence snapshot.')
        validate_analysis_base(outcome.analysis, item, requirements, conversion)
        hard_ids = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
        expected = 'accepted' if outcome.analysis.passes(hard_ids) else 'rejected'
        if expected == 'accepted' and excluded_childrenswear_base(item, requirements):
            # Admission applies this existing code policy after evaluation. Both
            # the pre-admission result and its cached code exclusion are valid.
            expected = outcome.status
        if outcome.status != expected:
            raise ValueError('Evaluation status disagrees with the validated admission conditions.')
        return outcome
    except (ValueError, TypeError, AttributeError) as exc:
        return invalid_record_base(outcome, exc, item_id=item.item_id if item is not None else None)


@_preserve_function('validate_pool_records', 'fashion_recommendation_v2.search.candidate_records')
def validate_pool_records(pool):
    """Isolate late serialization failures without losing other products/traces."""
    from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import Candidate
    for attempt in pool.search_attempts:
        records = []
        for outcome in attempt.item_evaluations:
            try:
                SearchItemEvaluation_base.model_validate_json(outcome.model_dump_json(warnings=False))
                if outcome.evaluation_mode == 'reused' and outcome.status in {'accepted', 'rejected'}:
                    candidate = next((c for c in pool.candidates if c.item.item_id == outcome.item_id), None)
                    representative = outcome.evaluation_source_item
                    item = candidate.item if candidate else representative
                    outcome = validate_record_base(outcome, item, representative,
                                              pool.resolved_requirements, pool.price_conversion)
                records.append(outcome)
            except (ValueError, TypeError) as exc:
                records.append(invalid_record_base(outcome, exc))
        attempt.item_evaluations = records
    kept = []
    for candidate in pool.candidates:
        try:
            Candidate.model_validate_json(candidate.model_dump_json(warnings=False))
            validate_analysis_base(candidate.search_analysis, candidate.evaluation_item or candidate.item,
                              pool.resolved_requirements, pool.price_conversion)
            kept.append(candidate)
        except (ValueError, TypeError, AttributeError) as exc:
            owner = next(a for a in reversed(pool.search_attempts)
                         if any(s.attempt_id == a.attempt_id for s in candidate.sources))
            first_owner = next(a for a in pool.search_attempts
                               if any(s.attempt_id == a.attempt_id for s in candidate.sources))
            first_owner.added_candidate_count = max(0, first_owner.added_candidate_count - 1)
            owner.item_evaluations.append(SearchItemEvaluation_base(
                item_id=candidate.item.item_id, batch_id='candidate_storage', status='evaluation_error',
                error_type=type(exc).__name__, error_message=str(exc), reasons=['candidate_record_invalid'],
                evaluation_recovery=dict(original_candidate=candidate.model_dump(mode='json', warnings=False),
                    code_validation=dict(status='invalid', error_type=type(exc).__name__, message=str(exc)))))
    pool.candidates = kept
    retained = {c.item.item_id for c in kept}
    for attempt in pool.search_attempts:
        for outcome in attempt.item_evaluations:
            # This flag describes the pool at the original attempt. A later
            # successful evaluation must not rewrite an earlier failed record.
            outcome.retained_in_pool = outcome.retained_in_pool and (
                outcome.evaluation_source_item_id or outcome.item_id) in retained
        for status in ('accepted', 'rejected', 'evaluation_error', 'image_fetch_error'):
            attempt.evaluation_summary[status] = sum(o.status == status for o in attempt.item_evaluations)
        attempt.evaluation_summary['added_candidate_count'] = attempt.added_candidate_count
        attempt.evaluation_summary['reused_evaluation_count'] = sum(
            o.evaluation_mode == 'reused' for o in attempt.item_evaluations)
        attempt.evaluation_summary['duplicate_unresolved_count'] = sum(
            o.evaluation_mode == 'duplicate_unresolved' for o in attempt.item_evaluations)
    for owner in pool.search_attempts:
        if owner.round_summary is not None:
            siblings = [a for a in pool.search_attempts if a.round_id == owner.round_id]
            for key in owner.evaluation_summary:
                owner.round_summary[key] = sum(a.evaluation_summary.get(key, 0) for a in siblings)


# ---- candidate_records_v31 ----
"""Evidence-backed invalidation and conservative partial persistence for v31."""
from copy import deepcopy
evidence_snapshot = evidence_snapshot_base
validate_record = validate_record_base
invalid_record = invalid_record_base
from fashion_recommendation_v2.search.product_validation import validate_analysis
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import Candidate
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemEvaluation
from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear


@_preserve_function('fresh_after_dedup', 'fashion_recommendation_v2.search.candidate_records_v31')
def fresh_after_dedup(manager):
    from fashion_recommendation_v2.search.contracts import SEARCH_RELEASES
    contract = SEARCH_RELEASES.get(getattr(manager, 'search_policy_version', None))
    return contract is not None and contract.candidate_validation == 'fresh_after_dedup'


@_preserve_function('evidence_change', 'fashion_recommendation_v2.search.candidate_records_v31')
def evidence_change(manager, candidate, item, context_snapshot):
    previous = manager.candidate_evaluation_contexts.get(candidate.item.item_id)
    return (evidence_snapshot(candidate.evaluation_item or candidate.item) != evidence_snapshot(item)
            or previous != context_snapshot)


@_preserve_function('invalidate', 'fashion_recommendation_v2.search.candidate_records_v31')
def invalidate(manager, candidate, *, round_id, reason, current_item=None, context_snapshot=None, error=None):
    if not hasattr(manager, 'candidate_invalidations'):
        manager.candidate_invalidations = []
    previous_item = candidate.evaluation_item or candidate.item
    event = dict(invalidation_id=f'invalidation_{len(manager.candidate_invalidations) + 1:04d}',
        item_id=candidate.item.item_id, round_id=round_id, reason=reason,
        original_candidate=candidate.model_dump(mode='json', warnings=False),
        previous_evidence_snapshot=evidence_snapshot(previous_item),
        current_evidence_snapshot=evidence_snapshot(current_item) if current_item is not None else None,
        previous_context_snapshot=getattr(manager, 'candidate_evaluation_contexts', {}).get(candidate.item.item_id),
        current_context_snapshot=context_snapshot,
        current_item=current_item.model_dump(mode='json') if current_item is not None else None,
        error=error)
    if reason == 'product_or_conditions_changed' and not evidence_change(manager, candidate, current_item, context_snapshot):
        raise ValueError('Cannot invalidate unchanged, independently valid candidate evidence.')
    manager.candidate_invalidations.append(deepcopy(event))
    manager.pool.candidates.remove(candidate)
    manager._refresh_counts()
    return event


@_preserve_function('verified_removed_ids', 'fashion_recommendation_v2.search.candidate_records_v31')
def verified_removed_ids(manager, round_id):
    """Only code-observed evidence changes in this round authorize disappearance."""
    return {e['item_id'] for e in getattr(manager, 'candidate_invalidations', [])
        if e['round_id'] == round_id and e['reason'] == 'product_or_conditions_changed'
        and e['original_candidate']['item']['item_id'] == e['item_id']
        and e['current_item'] is not None
        and (e['previous_evidence_snapshot'] != e['current_evidence_snapshot']
             or e['previous_context_snapshot'] != e['current_context_snapshot'])}


@_preserve_function('validate_candidate', 'fashion_recommendation_v2.search.candidate_records_v31')
def validate_candidate(manager, candidate):
    Candidate.model_validate_json(candidate.model_dump_json(warnings=False))
    item = candidate.evaluation_item or candidate.item
    if manager.search_policy_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.contracts import get_search_contracts
        expected = get_search_contracts(manager.search_policy_version).product_evaluation.version
        if candidate.search_analysis.evaluation_policy != expected:
            raise ValueError('Candidate evaluation version differs from its Search contract.')
    latest = getattr(manager, 'latest_evidence', {}).get(candidate.item.item_id)
    if not fresh_after_dedup(manager) and latest and evidence_change(manager, candidate, *latest):
        raise ValueError('Candidate evidence changed without a valid replacement evaluation.')
    if fresh_after_dedup(manager):
        if (candidate.item.item_id, candidate.item.image_url) != (item.item_id, item.image_url):
            raise ValueError('Candidate differs from its evaluated item/image.')
        accepted = [row for attempt in manager.pool.search_attempts
                    if attempt.attempt_id in {s.attempt_id for s in candidate.sources}
                    for row in attempt.item_evaluations
                    if row.item_id == candidate.item.item_id and row.status == 'accepted'
                    and row.evaluation_mode == 'fresh' and row.analysis is not None]
        if not any(row.analysis == candidate.search_analysis for row in accepted):
            raise ValueError('Candidate has no matching fresh accepted evaluation in its sources.')
    validate_analysis(candidate.search_analysis, item, manager.pool.resolved_requirements, manager.pool.price_conversion)
    hard_ids = {r.requirement_id for r in manager.pool.resolved_requirements.requirements if r.kind == 'hard'}
    if not candidate.search_analysis.passes(hard_ids) or (candidate.search_analysis.evaluation_policy not in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and excluded_childrenswear(item, manager.pool.resolved_requirements)):
        raise ValueError('Candidate fails hard requirements/image/acceptance gates.')
    known = {a.attempt_id for a in manager.pool.search_attempts}
    if not candidate.sources or any(s.attempt_id not in known for s in candidate.sources):
        raise ValueError('Candidate has no recorded search source.')


@_preserve_function('sanitize_pool', 'fashion_recommendation_v2.search.candidate_records_v31')
def sanitize_pool(manager):
    """Storage checks isolate items; valid own evidence survives a corrupt reuse row."""
    pool = manager.pool
    # Internal failures must escape as execution errors, never become item rejection.
    record_errors = (ValueError,) if fresh_after_dedup(manager) else (ValueError, TypeError, AttributeError)
    for attempt in pool.search_attempts:
        checked = []
        for outcome in attempt.item_evaluations:
            try:
                SearchItemEvaluation.model_validate_json(outcome.model_dump_json(warnings=False))
                if outcome.evaluation_mode == 'reused' and outcome.status in {'accepted', 'rejected'}:
                    item = outcome.evaluation_source_item
                    outcome = validate_record(outcome, item, item, pool.resolved_requirements, pool.price_conversion)
                checked.append(outcome)
            except record_errors as exc:
                checked.append(invalid_record(outcome, exc))
        attempt.item_evaluations = checked
    for candidate in list(pool.candidates):
        try:
            validate_candidate(manager, candidate)
        except record_errors as exc:
            latest = getattr(manager, 'latest_evidence', {}).get(candidate.item.item_id, (None, None))
            invalidate(manager, candidate, round_id='storage', reason='candidate_validation_failed',
                       current_item=latest[0], context_snapshot=latest[1],
                       error=f'{type(exc).__name__}: {exc}')
    retained = {c.item.item_id for c in pool.candidates}
    for attempt in pool.search_attempts:
        for row in attempt.item_evaluations:
            row.retained_in_pool = row.retained_in_pool and (row.evaluation_source_item_id or row.item_id) in retained
        for status in ('accepted', 'rejected', 'evaluation_error', 'image_fetch_error'):
            attempt.evaluation_summary[status] = sum(e.status == status for e in attempt.item_evaluations)
        attempt.evaluation_summary.update(
            added_candidate_count=attempt.added_candidate_count,
            reused_evaluation_count=sum(e.evaluation_mode == 'reused' for e in attempt.item_evaluations),
            duplicate_unresolved_count=sum(e.evaluation_mode == 'duplicate_unresolved' for e in attempt.item_evaluations))
    for owner in pool.search_attempts:
        if owner.round_summary is not None:
            siblings = [a for a in pool.search_attempts if a.round_id == owner.round_id]
            for key in owner.evaluation_summary:
                owner.round_summary[key] = sum(a.evaluation_summary.get(key, 0) for a in siblings)
    manager._refresh_counts()


@_preserve_function('finish_diagnostics', 'fashion_recommendation_v2.search.candidate_records_v31')
def finish_diagnostics(manager, result):
    from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchCodeValidationV31
    from fashion_recommendation_v2.search.semantic_validation import experiment_records
    inputs = deepcopy(getattr(manager, 'semantic_inspection_inputs', []))
    warnings = {}
    for row in inputs:
        for warning in row['semantic_warnings']:
            target = warnings.setdefault(warning['warning_id'], deepcopy(warning))
            target['attempt_ids'] = list(dict.fromkeys(target['attempt_ids'] + warning['attempt_ids']))
            target['occurrences'] = max(target['occurrences'], warning['occurrences'])
    invalidations = deepcopy(getattr(manager, 'candidate_invalidations', []))
    invalid_ids = {e['item_id'] for e in invalidations}
    kept_ids = {c.item.item_id for c in result.candidates}
    result.code_validation_v31 = SearchCodeValidationV31(
        semantic_observations=deepcopy(experiment_records()), inspection_inputs=inputs,
        semantic_warnings=list(warnings.values()),
        candidate_invalidations=invalidations,
        final_pool_metrics=dict(valid_candidates=len(kept_ids), invalidation_events=len(invalidations),
            invalidated_products=len(invalid_ids), invalidated_without_replacement=len(invalid_ids-kept_ids),
            retained_after_replacement=len(invalid_ids & kept_ids)),
        partial_failure=deepcopy(getattr(manager, 'partial_failure', None)))
    if result.code_validation_v31.partial_failure:
        result.completion_status = 'partial_result' if result.candidate_count else 'failed'
        result.stop_reason = 'no_viable_search_strategy'
    return result


@_preserve_function('settle_partial_attempts', 'fashion_recommendation_v2.search.candidate_records_v31')
def settle_partial_attempts(manager, attempts, before_ids):
    """Finish code accounting if a generator aborts between accepted products."""
    sanitize_pool(manager)
    retained = {c.item.item_id for c in manager.pool.candidates}
    owner_order = {a.attempt_id:index for index,a in enumerate(attempts)}
    new_owners = {}
    for candidate in manager.pool.candidates:
        owners = [s.attempt_id for s in candidate.sources if s.attempt_id in owner_order]
        if candidate.item.item_id not in before_ids and owners:
            new_owners[candidate.item.item_id] = min(owners, key=owner_order.get)
    for attempt in attempts:
        attempt.added_candidate_count = sum(owner == attempt.attempt_id for owner in new_owners.values())
        for row in attempt.item_evaluations:
            row.retained_in_pool = row.item_id in retained
        attempt.evaluation_summary.update(
            added_candidate_count=attempt.added_candidate_count,
            fresh_evaluated_count=sum(e.evaluation_mode == 'fresh' and e.status != 'image_fetch_error'
                                      for e in attempt.item_evaluations),
            visual_batch_count=len({e.batch_id for e in attempt.item_evaluations if e.evaluation_mode == 'fresh'}))
    if attempts:
        owner = attempts[-1]
        owner.round_summary = {**(owner.round_summary or {}), 'partial_failure':1,
            'query_count':len(attempts), 'pool_before':len(before_ids), 'pool_after':len(retained),
            'new_candidates_added':len(retained-before_ids), 'removed_candidates':len(before_ids-retained),
            'net_pool_growth':len(retained)-len(before_ids),
            'search_attempts_used':manager.pool.search_budget.attempts_used,
            'search_attempts_remaining':manager.pool.search_budget.attempts_remaining}


@_preserve_function('notify_committed_candidate', 'fashion_recommendation_v2.search.candidate_records_v31')
def notify_committed_candidate(runner, manager, attempts, item_id):
    callback = getattr(runner, 'candidate_committed_callback', None)
    if runner.search_policy_version not in {'v52', 'v53', 'v54', 'v55', 'v56'} or callback is None:
        return
    candidate = next((c for c in manager.pool.candidates if c.item.item_id == item_id), None)
    if candidate is None:
        return
    # Current attempt rows are not charged to the live pool until the round ends.
    # Validate against a detached view containing those already accepted rows.
    from copy import copy
    from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
    view = copy(manager)
    view.pool = manager.pool.model_copy(deep=True)
    known = {a.attempt_id for a in view.pool.search_attempts}
    view.pool.search_attempts.extend(a.model_copy(deep=True) for a in attempts if a.attempt_id not in known)
    validate_candidate(view, candidate)
    snapshot = CandidateSet(candidate_set_id='streaming_candidate', search_policy_version=runner.search_policy_version,
        target_candidate_count=view.pool.target_candidate_count, candidate_count=1,
        candidates=[candidate.model_copy(deep=True)], resolved_requirements=view.pool.resolved_requirements,
        price_conversion=view.pool.price_conversion, search_attempts=view.pool.search_attempts,
        stop_reason='search_budget_exhausted')
    callback(snapshot)
