"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- execution_v7 ----
"""Candidate-isolated execution; initial calls take priority over corrections."""
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from contextvars import copy_context
from time import monotonic
from fashion_recommendation_v2.llm.cost_tracking import record_call_context

MAX_WORKERS = 20
MAX_CANDIDATES = 50
CALLS_PER_CANDIDATE = 2


@_preserve_function('default_settings', 'fashion_recommendation_v2.relation.execution_v7')
def default_settings():
    return dict(batch_size=1, max_candidates=MAX_CANDIDATES,
                max_calls=MAX_CANDIDATES * CALLS_PER_CANDIDATE, max_workers=MAX_WORKERS)


@_preserve_function('run_candidates', 'fashion_recommendation_v2.relation.execution_v7')
def run_candidates(source, evaluate, *, max_candidates, max_calls, workers, progress=None):
    ids = [c.item.item_id for c in source.candidate_set.candidates]
    selected = [i for i in ids if i != source.intent.anchor_item_id][:max_candidates]
    initial = selected[:max_calls]
    results, attempts = {}, {i: [] for i in ids}

    def call(item_id, retry):
        started = monotonic()
        with record_call_context(agent='relation', version=source.evaluation_version, item_id=item_id,
                                 stage='correction' if retry else 'generation', retry_count=retry) as costs:
            try:
                ratio, records = evaluate(item_id, retry, [a['message'] for a in attempts[item_id] if a.get('status') == 'error'])
            except Exception as exc:
                # One worker failure must never cancel unrelated candidates.
                ratio = None
                records = [dict(item_id=item_id, retry_count=retry, status='error',
                    stage='correction' if retry else 'generation', error_type=type(exc).__name__,
                    message=str(exc), code_validation=dict(valid=False, errors=[str(exc)]),
                    applied=False, **getattr(exc, 'response_snapshot', {}))]
        for record in records:
            record.update(item_id=item_id, batch_item_ids=[item_id],
                elapsed_seconds=round(monotonic()-started, 6), cost_records=list(costs.values()),
                cost_call_ids=list(costs))
        return ratio, records

    with ThreadPoolExecutor(max_workers=workers) as pool:
        def phase(item_ids, retry):
            pending = {pool.submit(copy_context().run, call, i, retry): i for i in item_ids}
            for future in as_completed(pending):
                i = pending[future]
                ratio, records = future.result()
                attempts[i].extend(records)
                if ratio is not None and any(e.item_id == i for e in ratio.evaluations):
                    results[i] = ratio
                if progress:
                    progress(dict(stage='relation', phase='correction' if retry else 'generation',
                        item_id=i, completed_items=len(results), total_items=len(selected)))
        phase(initial, 0)
        failed = [i for i in initial if i not in results]
        phase(failed[:max(0, max_calls-len(initial))], 1)
    outcomes = {}
    for i in ids:
        records = attempts[i]
        success = i in results
        status = 'success' if success else 'fail' if len(records) == 2 else 'unevaluated'
        reason = ('evaluated' if success else 'anchor_excluded' if i == source.intent.anchor_item_id
                  else 'candidate_budget' if i not in selected else 'correction_failed' if status == 'fail'
                  else 'correction_budget' if records else 'call_budget')
        outcomes[i] = dict(status=status, call_count=len(records), reason=reason,
            errors=[a['message'] for a in records if a.get('status') == 'error'],
            cost_call_ids=[k for a in records for k in a.get('cost_call_ids', [])])
    # Completion order never changes output order or candidate attribution.
    return results, [a for i in ids for a in attempts[i]], outcomes
