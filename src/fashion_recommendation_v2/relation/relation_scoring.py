"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation_scoring_v3 ----

"""Code-owned v3 weights, partial-evidence accounting and downstream derivation."""
from fractions import Fraction as Fraction_v3
from fashion_recommendation_v2.schemas.relation_scoring import RelationScoreBreakdown
from fashion_recommendation_v2.schemas.relation_scoring import RelationCriterionScore
POLICY_ID_v3 = 'relation_v3_weighted_v1'
MIN_COVERAGE_v3 = Fraction_v3('0.60')
WEIGHTS_v3 = {'compatibility': {'category_pairing': 0.2, 'color_pattern': 0.2, 'style': 0.2, 'season': 0.2, 'use_context': 0.2}, 'similarity': {'product_type': 0.35, 'color': 0.15, 'length': 0.15, 'pattern': 0.15, 'details': 0.1, 'style': 0.05, 'material': 0.05}}
FACETS_v3 = {'category_pairing': {'category_pairing': 1}, 'color_pattern': {'color': 3, 'pattern_type': 1, 'pattern_scale': 1, 'pattern_distribution': 1}, 'style': {'style': 1}, 'season': {'season': 1}, 'use_context': {'use_context': 1}, 'product_type': {'product_type': 1}, 'color': {'color': 1}, 'length': {'garment_length': 1, 'sleeve_length': 1}, 'pattern': {'pattern_type': 1, 'pattern_scale': 1, 'pattern_distribution': 1}, 'details': {'details': 1}, 'material': {'material': 1}}
REQUIRED = {'compatibility': 'category_pairing', 'similarity': 'product_type'}
NOT_APPLICABLE_FACETS = frozenset({'pattern_scale', 'pattern_distribution', 'sleeve_length'})
FACET_GROUPS = {'color_pattern': [['color'], ['pattern_type', 'pattern_scale', 'pattern_distribution']]}

@_preserve_function('policy_context', 'fashion_recommendation_v2.relation.relation_scoring_v3')
def policy_context_v3():
    return dict(policy=POLICY_ID_v3, weights=WEIGHTS_v3, facet_weights=FACETS_v3, facet_groups=FACET_GROUPS, required_criterion=REQUIRED, minimum_evidence_coverage=float(MIN_COVERAGE_v3), not_applicable_facets=sorted(NOT_APPLICABLE_FACETS))

@_preserve_function('aggregate', 'fashion_recommendation_v2.relation.relation_scoring_v3')
def aggregate_v3(relation_type, judgments, *, weights_by_type=WEIGHTS_v3, minimum=MIN_COVERAGE_v3, policy_id=POLICY_ID_v3, facets_by_criterion=FACETS_v3, facet_groups=FACET_GROUPS):
    weights = weights_by_type[relation_type]
    names = [j.criterion for j in judgments]
    if len(names) != len(set(names)) or set(names) != set(weights):
        raise ValueError(f'Expected each {relation_type} criterion exactly once: {list(weights)}')
    by_name = {j.criterion: j for j in judgments}
    total_weight = Fraction_v3(0)
    total_value = Fraction_v3(0)
    scores = []
    for name, weight in weights.items():
        facets = by_name[name].facets
        keys = [f.facet for f in facets]
        if len(keys) != len(set(keys)) or set(keys) != set(facets_by_criterion[name]):
            raise ValueError(f'{name}: expected facets exactly once: {list(facets_by_criterion[name])}')
        for facet in facets:
            # Facet weights are within a criterion; color/pattern each retain half of their
            # combined compatibility weight. Unknown facets keep their denominator share.
            if facet.state == 'not_applicable' and facet.facet not in NOT_APPLICABLE_FACETS:
                raise ValueError(f'{name}/{facet.facet}: not_applicable is not permitted.')
        facet_weights = {}
        by_facet = {f.facet: f for f in facets}
        for group in facet_groups.get(name, [tuple(facets_by_criterion[name])]):
            share = Fraction_v3(sum((facets_by_criterion[name][f] for f in group)), sum(facets_by_criterion[name].values()))
            applicable = [f for f in group if by_facet[f].state != 'not_applicable']
            denominator = sum((facets_by_criterion[name][f] for f in applicable))
            for facet in applicable:
                facet_weights[facet] = share * Fraction_v3(facets_by_criterion[name][facet], denominator)
        assessed = [f for f in facets if f.score is not None]
        coverage = sum((facet_weights[f.facet] for f in assessed), Fraction_v3(0))
        value = sum((Fraction_v3(str(f.score)) * facet_weights[f.facet] for f in assessed)) / coverage if coverage else None
        effective = Fraction_v3(str(weight)) * coverage
        total_weight += effective
        if value is not None:
            total_value += effective * value
        scores.append(RelationCriterionScore(criterion=name, weight=weight, score=float(value) if value is not None else None, evidence_coverage=float(coverage), effective_weight=float(effective)))
    reasons = []
    if next((s for s in scores if s.criterion == REQUIRED[relation_type])).score is None:
        reasons.append('required_criterion_unavailable')
    if total_weight < minimum:
        reasons.append(f'evidence_coverage_below_{float(minimum):.2f}')
    score = float(total_value / total_weight) if total_weight and (not reasons) else None
    return RelationScoreBreakdown(policy=policy_id, judgments=judgments, criteria=scores, evidence_coverage=float(total_weight), score=score, null_reasons=reasons)

@_preserve_function('evidence_refs', 'fashion_recommendation_v2.relation.relation_scoring_v3')
def evidence_refs(judgments):
    return list(dict.fromkeys((ref for j in judgments for f in j.facets for ref in [*f.anchor_evidence, *f.candidate_evidence])))

@_preserve_function('derive', 'fashion_recommendation_v2.relation.relation_scoring_v3')
def derive_v3(source, result, *, aggregator=aggregate_v3):
    from fashion_recommendation_v2.schemas.relation import RelationEvaluation
    evaluations, breakdowns = ([], {})
    for entry in result.evaluations:
        breakdown = aggregator(source.intent.relation_type, entry.criteria)
        breakdowns[entry.item_id] = breakdown
        limitations = [f'{j.criterion}/{f.facet}: {f.state}: {f.reason}' for j in entry.criteria for f in j.facets if f.state not in {'assessed', 'not_applicable'}]
        limitations += [f'Relation code: {r}' for r in breakdown.null_reasons]
        evaluations.append(RelationEvaluation(item_id=entry.item_id, score=breakdown.score, reasons=entry.reasons, differences=entry.differences, uncertainties=list(dict.fromkeys([*entry.uncertainties, *limitations])), evidence_fields=evidence_refs(entry.criteria)))
    return (evaluations, breakdowns)


# ---- relation_scoring_v4 ----

"""v4 changes only Similarity weights and its minimum evidence coverage."""
from fractions import Fraction
shared_v4 = _role_module('fashion_recommendation_v2.relation.relation_scoring_v3')
POLICY_ID_v4 = 'relation_v4_weighted_v1'
WEIGHTS_v4 = {'compatibility': dict(shared_v4.WEIGHTS['compatibility']), 'similarity': {'product_type': 0.35, 'color': 0.3, 'pattern': 0.1, 'length': 0.1, 'details': 0.1, 'material': 0.05}}
MIN_COVERAGE_v4 = {'compatibility': shared_v4.MIN_COVERAGE, 'similarity': Fraction('.80')}
FACETS_v4 = shared_v4.FACETS

@_preserve_function('policy_context', 'fashion_recommendation_v2.relation.relation_scoring_v4')
def policy_context_v4():
    return {**shared_v4.policy_context(), 'policy': POLICY_ID_v4, 'weights': WEIGHTS_v4, 'minimum_evidence_coverage': {k: float(v) for k, v in MIN_COVERAGE_v4.items()}}

@_preserve_function('aggregate', 'fashion_recommendation_v2.relation.relation_scoring_v4')
def aggregate_v4(relation_type, judgments):
    return shared_v4.aggregate(relation_type, judgments, weights_by_type=WEIGHTS_v4, minimum=MIN_COVERAGE_v4[relation_type], policy_id=POLICY_ID_v4)

@_preserve_function('derive', 'fashion_recommendation_v2.relation.relation_scoring_v4')
def derive_v4(source, result):
    return shared_v4.derive(source, result, aggregator=aggregate_v4)


# ---- relation_scoring_v5 ----

"""v5 changes evidence semantics, preserving v4 weights and coverage thresholds."""
shared = _role_module('fashion_recommendation_v2.relation.relation_scoring_v3')
WEIGHTS = WEIGHTS_v4
FACETS = FACETS_v4
MIN_COVERAGE = MIN_COVERAGE_v4
POLICY_ID = 'relation_v5_weighted_v1'

@_preserve_function('policy_context', 'fashion_recommendation_v2.relation.relation_scoring_v5')
def policy_context():
    return {**shared.policy_context(), 'policy': POLICY_ID, 'weights': WEIGHTS, 'minimum_evidence_coverage': {k: float(v) for k, v in MIN_COVERAGE.items()}}

@_preserve_function('aggregate', 'fashion_recommendation_v2.relation.relation_scoring_v5')
def aggregate(relation_type, judgments):
    return shared.aggregate(relation_type, judgments, weights_by_type=WEIGHTS, minimum=MIN_COVERAGE[relation_type], policy_id=POLICY_ID)

@_preserve_function('derive', 'fashion_recommendation_v2.relation.relation_scoring_v5')
def derive(source, result):
    evaluations, breakdowns = shared.derive(source, result, aggregator=aggregate)
    for entry in result.evaluations:
        breakdowns[entry.item_id].metadata_fallbacks_v5 = entry.metadata_fallbacks
    return (evaluations, breakdowns)


# ---- relation_scoring_v9 ----

"""Compatibility-only integrated pattern policy; historical policies remain unchanged."""
shared_relation_scoring_v9 = _role_module('fashion_recommendation_v2.relation.relation_scoring_v3')
WEIGHTS_relation_scoring_v9 = WEIGHTS_v4
MIN_COVERAGE_relation_scoring_v9 = MIN_COVERAGE_v4
POLICY_ID_relation_scoring_v9 = 'relation_v9_weighted_v1'
FACETS_relation_scoring_v9 = {**shared_relation_scoring_v9.FACETS, 'color_pattern': {'color': 1, 'pattern': 1}}
FACET_GROUPS_relation_scoring_v9 = {'color_pattern': [['color'], ['pattern']]}

@_preserve_function('policy_context', 'fashion_recommendation_v2.relation.relation_scoring_v9')
def policy_context_relation_scoring_v9():
    return {**shared_relation_scoring_v9.policy_context(), 'policy': POLICY_ID_relation_scoring_v9, 'weights': WEIGHTS_relation_scoring_v9, 'facet_weights': FACETS_relation_scoring_v9, 'facet_groups': FACET_GROUPS_relation_scoring_v9, 'minimum_evidence_coverage': {k: float(v) for k, v in MIN_COVERAGE_relation_scoring_v9.items()}}

@_preserve_function('aggregate', 'fashion_recommendation_v2.relation.relation_scoring_v9')
def aggregate_relation_scoring_v9(relation_type, judgments):
    return shared_relation_scoring_v9.aggregate(relation_type, judgments, weights_by_type=WEIGHTS_relation_scoring_v9, minimum=MIN_COVERAGE_relation_scoring_v9[relation_type], policy_id=POLICY_ID_relation_scoring_v9, facets_by_criterion=FACETS_relation_scoring_v9, facet_groups=FACET_GROUPS_relation_scoring_v9)

@_preserve_function('derive', 'fashion_recommendation_v2.relation.relation_scoring_v9')
def derive_relation_scoring_v9(source, result):
    evaluations, breakdowns = shared_relation_scoring_v9.derive(source, result, aggregator=aggregate_relation_scoring_v9)
    for entry in result.evaluations:
        breakdowns[entry.item_id].metadata_fallbacks_v5 = entry.metadata_fallbacks
    return (evaluations, breakdowns)
