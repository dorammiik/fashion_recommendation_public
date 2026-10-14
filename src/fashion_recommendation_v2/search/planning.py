"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- planning_v32 ----
"""v32 verified retrieval hints, outside the schema dependency graph."""
from fashion_recommendation_v2.search.planning_rules import planning_constraints as previous_constraints


@_preserve_function('planning_constraints', 'fashion_recommendation_v2.search.planning_v32')
def planning_constraints(requirements, usages=(), *, version='v24', source=None):
    result = previous_constraints(requirements, usages, version=version if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else None)
    if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.planning import eligible_stylist_v47 as eligible_stylist
        result['stylist_search_ids'] = sorted(eligible_stylist(requirements))
        result['omission_rule'] = 'Every unused stylist_search_id requires a reason in stylist_omissions.'
    if version not in {'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        return result
    optional = verified_similarity_candidates(requirements, source)
    represented = set(result['represented_by_filter_or_category'])
    existing = {r['requirement_id'] for r in result['additional_condition_candidates']}
    result['additional_condition_candidates'] += [r.model_dump(mode='json') for r in optional
        if r.requirement_id not in represented | existing]
    result['optional_similarity_ids'] = [r.requirement_id for r in optional]
    return result


@_preserve_function('verified_similarity_candidates', 'fashion_recommendation_v2.search.planning_v32')
def verified_similarity_candidates(requirements, source):
    """Only resolved target conditions also proven by the supplied reference facts."""
    from types import SimpleNamespace
    from fashion_recommendation_v2.search.reference_roles import target_role_evidence
    if source is None or source.similarity_reference is None:
        return []
    result = []
    for r in requirements.requirements:
        if r.source != 'reference' or r.kind != 'soft' or r.unrestricted:
            continue
        # Prefer directly observable design features, never an inherited price,
        # identity/brand/size, provenance-only clause or paired garment context.
        if r.attribute not in {'color', 'pattern', 'fit', 'sleeve_length', 'detail'}:
            continue
        condition = SimpleNamespace(**r.model_dump(mode='python'), polarity='positive')
        if target_role_evidence(source, condition):
            result.append(r)
    return result


# ---- planning_v47 ----
"""v47 query use/omission accounting for retained Stylist search preferences."""
from fashion_recommendation_v2.schemas.search.planning.search_planning import StylistOmissionV47

STYLIST_GUIDANCE = """
Use retained source=stylist, evaluation_scope=search conditions when forming query
directions. Never retrieve excluded/suppressed original-only proposals. Choose
relevant suggestions within the unchanged query/call budgets; one OR option per
direction, not all alternatives joined as simultaneous mandatory constraints.
Preserve the user's hard boundary and use compatible narrower garment suggestions
as optional retrieval terms. Source=stylist and search scope never mean hard admission.
For EVERY eligible Stylist condition not represented in a plan, put its ID and a
specific reason in that query proposal's stylist_omissions. Use [] if all are used
or none are eligible. Do not list used IDs as omitted. Explain budget selection,
another direction or actual applicability; omission is permitted but must be visible.
The final executable plan is checked against actual usages, not proposal claims.
Generation, repair and review share these rules. No extra calls or larger budgets.
"""


@_preserve_function('eligible_stylist', 'fashion_recommendation_v2.search.planning_v47')
def eligible_stylist_v47(requirements):
    return {r.requirement_id for r in requirements.requirements
            if r.source == 'stylist' and r.evaluation_scope == 'search' and not r.unrestricted}


@_preserve_function('validate_omissions', 'fashion_recommendation_v2.search.planning_v47')
def validate_omissions(requirements, usages, records):
    rows = [StylistOmissionV47.model_validate(r) for r in records]
    eligible = eligible_stylist_v47(requirements)
    used = {u.requirement_id for u in usages} & eligible
    omitted = [r.requirement_id for r in rows]
    if len(omitted) != len(set(omitted)) or set(omitted) != eligible - used:
        raise ValueError('stylist_omissions must explain exactly every unused retained Stylist search condition; '
                         f'expected={sorted(eligible - used)}, actual={omitted}.')
    return dict(used=sorted(used), omitted=[r.model_dump(mode='json') for r in rows])


@_preserve_function('record_plan_use', 'fashion_recommendation_v2.search.planning_v47')
def record_plan_use_v47(brain, plan, requirements, usages):
    records = getattr(brain, '_stylist_omissions_v47', {}).get(plan.query, [])
    try:
        report = validate_omissions(requirements, usages, records)
    except ValueError as exc:
        brain.model_response_history.append(dict(operation='StylistPlanUseV47', model_response=None,
            code_validation=dict(status='failed', errors=[str(exc)]), code_derived=dict(query=plan.query)))
        raise
    brain.last_semantic_review['stylist_use_v47'] = report
    brain.model_response_history.append(dict(operation='StylistPlanUseV47', model_response=None,
        code_validation=dict(status='passed'), code_derived=dict(query=plan.query, **report)))


# ---- planning_v29 ----
"""Code-owned v29 distinctions between uncertain evaluation and search failure."""


@_preserve_function('evaluation_limited', 'fashion_recommendation_v2.search.planning_v29')
def evaluation_limited(context):
    """Stop replenishment when unresolved products can explain the whole deficit.

    This does not pretend those products passed. Keep the partial pool and report
    the evaluation blockage. Deduplicate identities instead of counting repeated
    appearances as independent lost candidates.
    """
    if context.get('search_policy_version') not in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        return False
    metrics = context.get('code_metrics', {})
    count = metrics.get('pool_after', context.get('candidate_count_after', 0))
    deficit = context.get('target_candidate_count', 0) - count
    rows = context.get('item_outcomes')
    if rows is not None:
        errors = len({row['item_id'] for row in rows
            if row['status'] in {'evaluation_error', 'image_fetch_error'} and not row.get('retained_in_pool')})
    else:
        errors = metrics.get('evaluation_error_count', 0) + context.get('image_fetch_error_count', 0)
    return deficit > 0 and errors >= deficit


# ---- planning_v49 ----
"""Non-blocking accounting from validated execution usages; never rewrite responses."""
from collections import Counter
from copy import deepcopy as deepcopy_v49
eligible_stylist = eligible_stylist_v47

REPRESENTATION_GUIDANCE = '''
Representation is determined by validated actual query/category/filter evidence,
not by which condition you intended to select. One expression can represent
multiple conditions. One OR alternative represents its condition; never require
all OR alternatives simultaneously. For example casual may represent both theme
and an occasion OR alternative: record both as used, neither as omitted.
This accounts for retrieval use, NOT product satisfaction.
Omission accounting inconsistencies are warnings only. Preserve original claims;
code derives actual used/unused IDs separately. Do not change a valid query merely
to repair accounting or spend a repair call for accounting alone.
Execution errors still require repair. Follow structured validation_feedback:
fix the specified field, use actual evidence, preserve original hard boundaries,
OR values, code-converted prices and valid sibling plans. Never invent evidence.
'''


@_preserve_function('omission_report', 'fashion_recommendation_v2.search.planning_v49')
def omission_report(requirements, usages, records):
    eligible = eligible_stylist(requirements)
    evidence = {}
    for usage in usages:
        if usage.requirement_id in eligible:
            evidence.setdefault(usage.requirement_id, []).append(usage.model_dump(mode='json'))
    from fashion_recommendation_v2.search.planning_rules import query_covers_alternative
    by_id = {r.requirement_id: r for r in requirements.requirements}
    matched_values = {}
    for rid, citations in evidence.items():
        value = by_id[rid].value
        alternatives = value.values if hasattr(value, 'values') and not isinstance(value, dict) else value if isinstance(value, list) else [value]
        matched_values[rid] = [v for v in alternatives if isinstance(v, str) and any(
            query_covers_alternative(c['evidence'], v) for c in citations)]
    used = set(evidence)
    unused = eligible - used
    counts = Counter(row.get('requirement_id') for row in records)
    warnings, omitted = [], []
    for rid, count in counts.items():
        codes = []
        if count > 1: codes.append('duplicate_omission')
        if rid not in eligible: codes.append('ineligible_omission')
        elif rid in used: codes.append('used_condition_listed_as_omitted')
        for code in codes:
            warnings.append(dict(code=code, requirement_id=rid, actual_count=count,
                matched_evidence=deepcopy_v49(evidence.get(rid, [])), matched_values=matched_values.get(rid, []),
                instruction=('Remove this ID from omission claims: the listed execution expression(s) '
                    'already represent it, including OR alternatives. Keep the executable query unchanged.'
                    if rid in used else 'Report eligible unused IDs once; preserve the executable plan.')))
    for rid in sorted(unused):
        reasons = [row.get('reason') for row in records if row.get('requirement_id') == rid
                   and isinstance(row.get('reason'), str) and row['reason'].strip()]
        omitted.append(dict(requirement_id=rid, reasons=reasons,
                            reason_status='provided' if reasons else '생략 이유 미기재'))
        if not reasons:
            warnings.append(dict(code='missing_omission_reason', requirement_id=rid,
                matched_evidence=[], instruction='Record an actual omission reason if known; do not fabricate one.'))
    return dict(used=sorted(used), unused=sorted(unused), matched_evidence=evidence, matched_values=matched_values,
                omitted=omitted, original_omissions=deepcopy_v49(records), warnings=warnings)


@_preserve_function('record_plan_use', 'fashion_recommendation_v2.search.planning_v49')
def record_plan_use_v49(brain, plan, requirements, usages):
    records = getattr(brain, '_stylist_omissions_v47', {}).get(plan.query, [])
    report = omission_report(requirements, usages, records)
    brain.last_semantic_review['stylist_use_v49'] = report
    brain.model_response_history.append(dict(operation='StylistPlanUseV49', model_response=None,
        code_validation=dict(status='warning' if report['warnings'] else 'passed',
                             errors=[], warnings=report['warnings']),
        code_derived=dict(query=plan.query, **report)))


# ---- planning_v50 ----
"""Request-local condition pool, validated execution history, initial use validation."""
from copy import deepcopy
from fashion_recommendation_v2.schemas.search.planning.search_planning import ConditionPriorityV50
from fashion_recommendation_v2.search.planning_rules import query_covers_alternative

GUIDANCE = '''
V50 CONDITION POOL (generation, repair and review):
Use search_condition_pool for initial directions and new_direction revisions.
Preserve IDs, sources, kind, original value types and OR groups. Choose one OR
alternative per direction. A used condition remains reusable in a new combination.
Preserve required hard retrieval evidence and all hard item constraints.
Priority: source=user first; source=reference (confirmed Relation requests only)
and source=stylist second. Context hard constraints still apply regardless of rank.
Across initial plans, represent at least one applicable Stylist search condition.
If user conflict or existing search constraints prevent this, record the specific
reason in stylist_nonuse_reason. Null otherwise; optional omission alone is not
an exception. A branch repair must consider valid siblings before allocating use.
Importance determines consideration priority; confidence determines concentration,
not a numerical weight. High/high: major initial direction. High/low: explore one
direction, do not repeat in every query. Low/high: auxiliary. Apply these meanings
to medium and other combinations. Missing grades are not low grades. Ungraded
Stylist and raw_evidence suggestions may explore one direction; do not repeat them
in every query. Never invent grades or claim keywords have independent evidence
when they share a profile interpretation. Never expose or infer additional tastes.
For new_direction, consider diagnoses/trigger FIRST, then pool and execution history
for a suitable unexplored combination. Supply shortage does not justify blindly
adding modifiers. Exhausted means no suitable unexplored combination for this
problem, not every Cartesian combination was enumerated. If pool is empty/exhausted,
use existing grounded conditions with different expressions/directions; no new intent.
Preserve the existing 1-3 additional condition rule, OR, no duplicate executable
plan, budget and stopping rules. Explain expected new candidates in the existing
intent reason. An unused pool entry never creates extra calls or completion debt.
'''


@_preserve_function('condition_pool', 'fashion_recommendation_v2.search.planning_v50')
def condition_pool(requirements, source=None):
    rows = []
    relation = bool(getattr(source, 'relation_intent', None) or getattr(source, 'similarity_reference', None))
    result = getattr(source, 'stylist_resolution', None)
    ctx = getattr(result, 'personalization_context', None)
    bundle = getattr(ctx, 'bundle', None) or {}
    profile = bundle.get('profile') or {}
    claims = {r['interpretation_id']: r for r in profile.get('interpretations', [])}
    for r in requirements.requirements:
        if r.evaluation_scope != 'search' or r.unrestricted or (r.source == 'reference' and not relation):
            continue
        row = r.model_dump(mode='json')
        # Whole profile is never projected; only code-selected per-condition grades.
        provenance = getattr(r, 'stylist_provenance', None)
        rid = getattr(provenance, 'preference_interpretation_id', None)
        basis = getattr(provenance, 'preference_basis', 'profile_interpretation' if rid else 'none')
        priority = ConditionPriorityV50(requirement_id=r.requirement_id)
        if r.source == 'stylist' and rid and basis == 'profile_interpretation':
            frozen = getattr(provenance, 'frozen_profile', None)
            if hasattr(frozen, 'model_dump'): frozen = frozen.model_dump(mode='json')
            if frozen != bundle.get('frozen') or rid not in claims:
                raise ValueError('Condition priority must reference the frozen Stylist profile: '+r.requirement_id)
            claim = claims[rid]
            if not set(provenance.preference_evidence_refs) <= set(claim['supporting_evidence_refs']+claim['counter_evidence_refs']):
                raise ValueError('Priority evidence does not belong to interpretation.')
            priority = ConditionPriorityV50(requirement_id=r.requirement_id,
                preference_interpretation_id=rid, importance=claim['importance'], confidence=claim['confidence'])
        row['priority'] = priority.model_dump(mode='json')
        row['source_priority'] = 1 if r.source == 'user' else 2 if r.source in {'reference', 'stylist'} else None
        rows.append(row)
    return rows


@_preserve_function('usage_history', 'fashion_recommendation_v2.search.planning_v50')
def usage_history(pool, attempts):
    """Only actual executed attempts/usages, not model target or omission claims."""
    used = set(); alternatives = []; plans = []
    for attempt in attempts:
        data = attempt.model_dump(mode='json') if hasattr(attempt, 'model_dump') else attempt
        usages = data.get('requirement_usages', [])
        plans.append({k: deepcopy(data.get(k)) for k in ('attempt_id','query','category_ids','aspect_filters','status','added_candidate_count')})
        for row in pool:
            refs = [u for u in usages if u['requirement_id'] == row['requirement_id']]
            if not refs: continue
            used.add(row['requirement_id'])
            value = row['value']; values = value.get('values', []) if isinstance(value,dict) else value if isinstance(value,list) else [value]
            for v in values:
                if isinstance(v,str) and any(query_covers_alternative(u['evidence'],v) for u in refs):
                    entry = {'requirement_id':row['requirement_id'], 'value':v}
                    if entry not in alternatives: alternatives.append(entry)
    return dict(used_requirement_ids=sorted(used), used_alternatives=alternatives, executed_plans=plans)


@_preserve_function('validate_initial_use', 'fashion_recommendation_v2.search.planning_v50')
def validate_initial_use(pool, branches, reason):
    eligible = {r['requirement_id'] for r in pool if r['source']=='stylist'}
    used = {u.requirement_id for b in branches for u in b['usages']} & eligible
    if eligible and not used and not (isinstance(reason,str) and reason.strip()):
        raise ValueError('v50 initial plans must use a Stylist search condition or record stylist_nonuse_reason for a conflict/search constraint.')
    return dict(eligible_stylist_ids=sorted(eligible), used_stylist_ids=sorted(used),
                exception_reason=reason if not used else None)

# Same non-blocking omission accounting; v50 adds pool/coverage alongside it.
record_plan_use = record_plan_use_v49
