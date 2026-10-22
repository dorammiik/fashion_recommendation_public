"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- planning_feedback_v49 ----

"""Contextual feedback for existing blockers; does not relax or rerun validation."""
from fashion_recommendation_v2.schemas.search.planning.search_planning import PlanFeedbackV49
from fashion_recommendation_v2.search.planning_rules import execution_evidence_contract
from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids
from fashion_recommendation_v2.search.planning_rules import additional_restrictions
from fashion_recommendation_v2.search.planning_rules import additional_condition_bounds
from fashion_recommendation_v2.search.planning_rules import strategy_trigger_contract
from fashion_recommendation_v2.search.planning_rules import plan_signature

@_preserve_function('dump', 'fashion_recommendation_v2.search.planning_feedback_v49')
def dump(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, list):
        return [dump(v) for v in value]
    if isinstance(value, dict):
        return {k: dump(v) for k, v in value.items()}
    return value

@_preserve_function('plan_feedback', 'fashion_recommendation_v2.search.planning_feedback_v49')
def plan_feedback(exc, *, plan_id, stage, plan=None, requirements=None, usages=(), categories=(), valid_plans=(), context=None, proposal=None, version='v49'):
    """Describe only the failed stage; never certify unperformed downstream checks."""
    context = context or {}
    message = str(exc)
    lower = getattr(exc, 'feedback', {}).get('message', message).lower()
    usages = getattr(exc, 'confirmed_usages', usages)
    rows = list(requirements.requirements) if requirements is not None else []
    mentioned = [r.requirement_id for r in rows if r.requirement_id in message]
    actual = dict(error_type=type(exc).__name__, message=message, plan=dump(plan), response_snapshot=dump(getattr(exc, 'response_snapshot', None)), usages=dump(list(usages)), original_claims=context.get('original_claims', []), existing_feedback=dump(getattr(exc, 'feedback', None)))
    expected = {}
    code, field = ('plan_contract_error', stage)
    rule = message
    instruction = 'Correct the reported field under the supplied response schema and execution rules. Do not alter unrelated valid fields.'
    if any((word in lower for word in ('price', 'currency', 'conversion'))):
        code, field = ('price_filter_mismatch', 'aspect_filters')
        conversion = getattr(plan, 'price_conversion', None) or context.get('price_conversion')
        conversion = dump(conversion)
        expected = dict(original_price=dump(getattr(requirements, 'price_constraint', None)), code_conversion=conversion)
        if conversion:
            expected['filters'] = {key: conversion[attr] for key, attr in [('PriceMin', 'min_amount'), ('PriceMax', 'max_amount')] if conversion.get(attr) is not None}
        instruction = 'Preserve the original currency/bounds and use the existing code-converted price filters exactly. Do not recalculate exchange rates. If conversion is unavailable, do not invent it.'
    elif 'distinct' in lower or 'duplicate' in lower:
        code, field = ('duplicate_plan', 'query/category_ids/aspect_filters')
        expected = dict(valid_sibling_plans=dump(list(valid_plans)))
        if plan is not None:
            actual['matching_siblings'] = [dump(p) for p in valid_plans if plan_signature(p) == plan_signature(plan)]
        instruction = 'Choose a different eligible original alternative. Word-order or punctuation changes alone do not make a new direction. Keep valid sibling plans unchanged.'
    elif any((word in lower for word in ('trigger', 'strategy', 'unused', 'change_type', 'target ids'))):
        code, field = ('unsupported_strategy', 'revision')
        actual.update(proposal=dump(proposal), observed_metrics=context.get('code_metrics', {}), diagnoses=context.get('code_diagnoses', []))
        expected = dict(allowed_strategies=strategy_trigger_contract(context))
        instruction = 'Select a strategy supported by the observed diagnosis and allowed choices. Distinguish retrieval shortage from product rejection. Do not invent unsearched alternatives or change valid sibling plans.'
    elif any((word in lower for word in ('budget', 'additional condition', 'restrictions'))):
        code, field = ('additional_condition_limit', 'query')
        if requirements is not None and all((u.requirement_id in {r.requirement_id for r in rows} for u in usages)):
            groups = additional_restrictions(requirements, usages, 'v49')
            minimum, maximum = additional_condition_bounds(requirements, usages, version=version)
            actual.update(condition_groups=groups, count=len(groups))
            expected = dict(minimum=minimum, maximum=maximum)
        instruction = 'Keep mandatory retrieval conditions. Adjust only eligible optional expressions to the supplied bounds; choose which to omit without changing original requirements or OR semantics.'
    elif any((word in lower for word in ('invalid', 'quote', 'evidence must', 'usage id'))) and (not any((word in lower for word in ('hard product', 'hard brand')))):
        code, field = ('invalid_execution_evidence', 'requirement_usages')
        if plan is not None:
            expected = execution_evidence_contract(plan, query_fragments=version in {'v59', 'v60', 'v61'})
        instruction = 'Quote the actual executed query/category/filter fragment for the specified condition. If the condition is already represented, fix only the citation. If a mandatory condition is genuinely absent, repair the plan as well. Never fabricate evidence or claim missing conditions are covered.'
    elif any((word in lower for word in ('hard', 'missing', 'brand', 'product type', 'audience'))):
        code, field = ('required_condition_not_supported', 'query/category_ids/aspect_filters')
        required = required_retrieval_ids(requirements, 'v49') if requirements is not None else set()
        expected = dict(required_conditions=[dump(r) for r in rows if r.requirement_id in required], locations='Product type: specific query/filter/leaf evidence, not broad parent category. Brand: actual query/filter. Price: converted filter.')
        actual['category_evidence'] = dump(list(categories))
        instruction = 'Supply actual evidence for the indicated required condition. If absent, add its permitted value to the executable plan. Preserve specific garment qualifiers and brand identity; an ancestor category does not prove a specific type.'
    elif 'query_language' in lower:
        code, field = ('query_language', 'query')
        expected = dict(language='marketplace English')
        instruction = 'Translate the executable query to marketplace English; preserve original source quotations and condition values.'
    if version in {'v59', 'v60', 'v61'} and type(exc).__name__ == 'PlanReviewOutputError':
        instruction = 'Keep the SAME execution plan and repair only the review IDs/citations. For query evidence_fragments, quote each missing fragment exactly at word boundaries; separate distant expressions and preserve compound phrases. Category/filter evidence is unchanged.'
    return PlanFeedbackV49(code=code, plan_id=plan_id, field=field, requirement_ids=mentioned, rule=rule, actual=actual, expected=expected, instruction=instruction, preserve=['Original requirement IDs, sources, values and OR relations', 'User hard boundaries and code-converted prices', 'Valid sibling plans', 'Original model responses and existing call/repair budgets']).model_dump(mode='json')
