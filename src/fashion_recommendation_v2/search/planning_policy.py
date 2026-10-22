"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- planning_policy_v57 ----

"""Polarity-aware retrieval checks for the v57 semantic condition scopes."""
import re as re_planning_policy_v57
from fashion_recommendation_v2.search.requirements_policy import detail_key_requirements_policy_v57 as detail_key_planning_policy_v57
from fashion_recommendation_v2.search.requirements_policy import values_requirements_policy_v57 as values_planning_policy_v57

@_preserve_function('negative_search_ids', 'fashion_recommendation_v2.search.planning_policy_v57')
def negative_search_ids_planning_policy_v57(requirements):
    routing = getattr(requirements, 'condition_routing_v37', None)
    policy = getattr(routing, 'stylist_policy_v47', None)
    polarities = policy.polarities if policy else {}
    return {r.requirement_id for r in requirements.requirements if polarities.get(r.requirement_id) == 'negative' and r.evaluation_scope == 'search'}

@_preserve_function('validate_usages', 'fashion_recommendation_v2.search.planning_policy_v57')
def validate_usages_planning_policy_v57(requirements, usages):
    negative = negative_search_ids_planning_policy_v57(requirements)
    by_id = {r.requirement_id: r for r in requirements.requirements}
    for usage in usages:
        if usage.requirement_id not in negative:
            continue
        row = by_id[usage.requirement_id]
        if detail_key_planning_policy_v57(row) not in {'length', 'skirt_length'}:
            continue
        if any((re_planning_policy_v57.search(r'(?<!\w)' + re_planning_policy_v57.escape(value) + r'(?!\w)', usage.evidence, re_planning_policy_v57.I) for value in values_planning_policy_v57(row))):
            raise ValueError('v57 negative length cannot be represented by the excluded positive keyword/filter.')
