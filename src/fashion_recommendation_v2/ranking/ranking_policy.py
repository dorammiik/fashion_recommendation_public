"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_policy_v9 ----

"""Single authority for v9 numeric condition and consistency policy."""
CONDITION_SCORES = {'met': 1.0, 'mostly_met': 0.75, 'partial': 0.5, 'unknown': 0.4, 'unmet': 0.0}
CONSISTENCY_DEDUCTIONS = {'consistent': 0.0, 'partially_consistent': 0.1, 'inconsistent': 0.25, 'visually_indeterminate': 0.05, 'metadata_missing': 0.0, 'not_applicable': 0.0, 'observation_unavailable': 0.05}
# All v9 relation modes retain similarity diagnostics without a ranking penalty.
DIVERSITY_ENABLED = False


# ---- ranking_weights_v17 ----

"""Frozen experimental weights; evidence, eligibility and v9 views stay intact.

Generation and validation both apply this deterministic transform before tier
composition. Historical score views are evidence records, not v17 rankings.
"""
import random as random_ranking_weights_v17
WEIGHT_SETS_ranking_weights_v17 = {'A9': dict(R=0.4, Q=0.5, T=0.1, P=0.0, Relation=0.0), 'B11': dict(R=0.34375, Q=0.1375, T=0.06875, P=0.45, Relation=0.0), 'C12': dict(R=0.0, Q=0.0, T=0.05, P=0.0, Relation=0.95)}

@_preserve_function('selected_set', 'fashion_recommendation_v2.ranking.ranking_weights_v17')
def selected_set_ranking_weights_v17(row, mode):
    scores = row.scores
    app = scores.application_v8
    if mode == 'cold' and scores.request_relevance_score is None and (app.reason in {'r_inactive_relation_numeric', 'r_inactive_relation_null'}) and (app.relation_type == 'similarity'):
        return 'C12'
    if app.relation_type is None and app.reason == 'no_relation' and (scores.request_relevance_score is not None):
        if mode == 'cold':
            return 'A9'
        # Only the pure similarity path tested in C: no independent request R.
        if mode == 'warm' and scores.preference_score is not None:
            return 'B11'
    # Warm null-P supplement, other relations and inactive-R fallback.
    return None

@_preserve_function('weighted_view', 'fashion_recommendation_v2.ranking.ranking_weights_v17')
def weighted_view_ranking_weights_v17(view, record):
    """Return an internal view copy; never relabel/overwrite stored v9 evidence."""
    from fashion_recommendation_v2.agents.ranking_runner import pair_similarity
    result = view.model_copy(deep=True)
    changed = False
    for row in result.ranked_items:
        key = selected_set_ranking_weights_v17(row, record['personalization_mode'])
        if key is None:
            continue
        changed = True
        w = dict(WEIGHT_SETS_ranking_weights_v17[key])
        s = row.scores
        if s.diversity_penalty or s.application_v8.diversity_enabled:
            raise ValueError('v17 refinement requires the frozen no-diversity policy')
        value = w['R'] * (s.request_relevance_score or 0.0) + w['Q'] * s.thumbnail_quality_score + w['T'] * s.ebay_best_match_score + w['P'] * (s.preference_score or 0.0) + w['Relation'] * (s.relation_score or 0.0)
        app = s.application_v8
        app.component_weights_v37 = w
        app.relation_weight = w['Relation']
        app.base_weight = 1.0 - w['Relation']
        app.relation_contribution = w['Relation'] * (s.relation_score or 0.0)
        app.original_base_score = (w['Q'] * s.thumbnail_quality_score + w['T'] * s.ebay_best_match_score) / app.base_weight if key == 'C12' else value
        s.base_score = s.final_score = value
    if not changed:
        return result
    rng = random_ranking_weights_v17.Random(view.random_seed)
    tie = {iid: rng.random() for iid in sorted((r.item_id for r in result.ranked_items))}
    result.ranked_items.sort(key=lambda r: (-r.scores.final_score, -(r.scores.request_relevance_score or 0.0), tie[r.item_id]))
    previous = []
    for position, row in enumerate(result.ranked_items, 1):
        row.rank = row.base_rank = position
        row.scores.max_selected_similarity = max((pair_similarity(row.diversity_features, p) for p in previous), default=0.0)
        previous.append(row.diversity_features)
    return result
