"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- ranking_policy_v9 ----
"""Single authority for v9 numeric condition and consistency policy."""
CONDITION_SCORES = {'met': 1., 'mostly_met': .75, 'partial': .5, 'unknown': .4, 'unmet': 0.}
CONSISTENCY_DEDUCTIONS = {'consistent': 0., 'partially_consistent': .10,
    'inconsistent': .25, 'visually_indeterminate': .05, 'metadata_missing': 0.,
    'not_applicable': 0., 'observation_unavailable': .05}

# All v9 relation modes retain similarity diagnostics without a ranking penalty.
DIVERSITY_ENABLED = False
