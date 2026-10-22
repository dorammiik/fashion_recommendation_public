"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- stylist_comparison_targets_v58 ----

"""Code-owned comparison eligibility; reuse the historical dimension definition."""
from fashion_recommendation_v2.search.stylist_policy import expected_pairs as expected_pairs_stylist_comparison_targets_v58

@_preserve_function('comparison_targets', 'fashion_recommendation_v2.search.stylist_comparison_targets_v58')
def comparison_targets_stylist_comparison_targets_v58(conditions):
    return sorted(expected_pairs_stylist_comparison_targets_v58([c for c in conditions if c.source == 'stylist' and c.role == 'target'], [c for c in conditions if c.source == 'user']))

@_preserve_function('required_pairs', 'fashion_recommendation_v2.search.stylist_comparison_targets_v58')
def required_pairs_stylist_comparison_targets_v58(conditions, applications):
    hard = {r.requirement_id for r in applications if r.kind == 'hard'}
    return {(s, u) for s, u in comparison_targets_stylist_comparison_targets_v58(conditions) if u in hard}

@_preserve_function('comparison_context', 'fashion_recommendation_v2.search.stylist_comparison_targets_v58')
def comparison_context_stylist_comparison_targets_v58(conditions):
    return [dict(stylist_requirement_id=s, user_requirement_id=u) for s, u in comparison_targets_stylist_comparison_targets_v58(conditions)]
