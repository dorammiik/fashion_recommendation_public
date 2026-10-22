"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_scoring_v8 ----

"""v8 score policy shared by generation and final-output validation."""
from fashion_recommendation_v2.schemas.ranking import ScoreApplicationV8
SIMILARITY_WEIGHTS = {'insufficient_coverage': (0.75, 0.25), 'partial_coverage': (0.65, 0.35), 'full_coverage': (0.6, 0.4)}
COMPATIBILITY_WEIGHTS = (0.75, 0.25)

@_preserve_function('policy_context', 'fashion_recommendation_v2.ranking.ranking_scoring_v8')
def policy_context():
    return dict(similarity={k: dict(base_weight=b, relation_weight=r) for k, (b, r) in SIMILARITY_WEIGHTS.items()}, compatibility=dict(base_weight=COMPATIBILITY_WEIGHTS[0], relation_weight=COMPATIBILITY_WEIGHTS[1]), similarity_diversity_penalty=False, null_contribution=0.0, failure_fallback='original_base')

@_preserve_function('relation_type', 'fashion_recommendation_v2.ranking.ranking_scoring_v8')
def relation_type(source):
    if source.ralationRatio is not None:
        return source.ralationRatio.intent.relation_type
    # The evaluator passes the SAME resolved intent to both comparison arms.
    if source.relation_intent is not None:
        return source.relation_intent.relation_type
    return None

@_preserve_function('diversity_enabled', 'fashion_recommendation_v2.ranking.ranking_scoring_v8')
def diversity_enabled_v8(source):
    return relation_type(source) != 'similarity'

@_preserve_function('base_score', 'fashion_recommendation_v2.ranking.ranking_scoring_v8')
def base_score_v8(relevance, thumbnail, retrieval, preference):
    return 0.55 * relevance + 0.35 * thumbnail + 0.1 * retrieval if preference is None else 0.5 * relevance + 0.2 * preference + 0.2 * thumbnail + 0.1 * retrieval

@_preserve_function('apply_relation', 'fashion_recommendation_v2.ranking.ranking_scoring_v8')
def apply_relation_v8(base, source, item_id, *, similarity_version='v4', breakdown_field='score_breakdowns_v4'):
    ratio = source.ralationRatio
    kind = relation_type(source)
    entry = next((e for e in ratio.evaluations if e.item_id == item_id), None) if ratio else None
    coverage, bw, rw, contribution = (None, 1.0, 0.0, 0.0)
    reason = 'no_relation' if ratio is None else 'unevaluated' if entry is None else 'null_fallback'
    if ratio is not None and kind == 'similarity':
        if ratio.evaluation_version != similarity_version:
            raise ValueError('Ranking v8 Similarity requires validated Relation v4 coverage.')
        detail = (getattr(ratio, breakdown_field) or {}).get(item_id)
        if detail is not None:
            coverage = detail.evidence_coverage
        if entry is not None and detail is not None:
            if entry.score is None and 'evidence_coverage_below_0.80' in detail.null_reasons:
                bw, rw = SIMILARITY_WEIGHTS['insufficient_coverage']
                reason = 'similarity_insufficient_coverage'
            elif entry.score is not None:
                tier = 'full_coverage' if coverage == 1.0 else 'partial_coverage'
                bw, rw = SIMILARITY_WEIGHTS[tier]
                reason = 'similarity_' + tier
                contribution = rw * entry.score
    elif entry is not None and entry.score is not None:
        bw, rw = COMPATIBILITY_WEIGHTS
        contribution, reason = (rw * entry.score, 'compatibility_numeric')
    record = ScoreApplicationV8(relation_type=kind, evidence_coverage=coverage, reason=reason, original_base_score=base, base_weight=bw, relation_weight=rw, relation_contribution=contribution, diversity_enabled=diversity_enabled_v8(source))
    return (bw * base + contribution, record)


# ---- ranking_scoring_v9 ----

"""Stored v36 evidence to v9 assessments; generation and validation share this function."""
from fashion_recommendation_v2.ranking.ranking_policy import CONDITION_SCORES
from fashion_recommendation_v2.ranking.ranking_policy import CONSISTENCY_DEDUCTIONS
from fashion_recommendation_v2.schemas.ranking import RequirementAssessmentV9
from fashion_recommendation_v2.schemas.ranking import ConsistencyDeduction
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessmentV2
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1
from fashion_recommendation_v2.search.product_evaluation import attribute_key
from fashion_recommendation_v2.search.product_evaluation import validate_analysis
base_score = base_score_v8

@_preserve_function('diversity_enabled', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def diversity_enabled(source):
    from fashion_recommendation_v2.ranking.ranking_policy import DIVERSITY_ENABLED
    return DIVERSITY_ENABLED

@_preserve_function('relation_contract', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def relation_contract(ratio):
    """Version compatibility comes from Relation's existing contract registry."""
    from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
    if ratio is not None:
        contract = get_relation_contract(ratio.evaluation_version)
        if contract.recommended_ranking_policy in {'ranking_eval_v9', 'ranking_eval_v10'}:
            return contract
    return None

@_preserve_function('apply_relation', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def apply_relation(base, source, item_id):
    inherited_application = apply_relation_v8
    kwargs = dict(similarity_version='v5', breakdown_field='score_breakdowns_v5') if source.candidate_set.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else {}
    contract = relation_contract(source.ralationRatio)
    if contract is not None:
        kwargs = dict(similarity_version=source.ralationRatio.evaluation_version, breakdown_field=contract.breakdown_field)
    score, record = inherited_application(base, source, item_id, **kwargs)
    return (score, record.model_copy(update={'diversity_enabled': diversity_enabled(source)}))

@_preserve_function('assessments', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def assessments(candidate, source):
    analysis = candidate.search_analysis
    if source.search_policy_version not in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} or analysis is None or analysis.evaluation_policy not in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v59'}:
        raise ValueError('Ranking v9 requires the source-separated Search v36 contract.')
    from fashion_recommendation_v2.search.contracts import get_search_contracts
    if analysis.evaluation_policy != get_search_contracts(source.search_policy_version).product_evaluation.version:
        raise ValueError('Analysis version differs from the selected Search contract.')
    item = candidate.evaluation_item or candidate.item
    if item.item_id != candidate.item.item_id or item.image_url != candidate.item.image_url:
        raise ValueError('Evaluation snapshot identity mismatch.')
    validate_analysis(analysis, item, source.resolved_requirements, source.price_conversion)
    if not analysis.passes({r.requirement_id for r in source.resolved_requirements.requirements if r.kind == 'hard'}):
        raise ValueError('Ranking v9 requires valid Search admission evidence.')
    rows = {attribute_key(a): (i, a) for i, a in enumerate(analysis.attributes)}
    by_id = {j.requirement_id: j for j in analysis.judgments}
    result = []
    eligible_ids = None
    if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.requirements import ranking_condition_ids
        eligible_ids = ranking_condition_ids(source.resolved_requirements)
    for requirement in source.resolved_requirements.requirements:
        if requirement.kind != 'soft' or (eligible_ids is not None and requirement.requirement_id not in eligible_ids):
            continue
        judgment = by_id[requirement.requirement_id]
        options = [a for a in analysis.alternative_judgments if a.requirement_id == requirement.requirement_id and a.status == 'met']

        def deductions(j):
            return [ConsistencyDeduction(attribute_key=k, status=rows[k][1].metadata_image_consistency.status, deduction=CONSISTENCY_DEDUCTIONS[rows[k][1].metadata_image_consistency.status], source_path=f'search_analysis.attributes.{rows[k][0]}.metadata_image_consistency') for k in j.attribute_keys]
        selected = min(options, key=lambda a: max((d.deduction for d in deductions(a)), default=0.0)) if options else judgment
        values = deductions(selected)
        reason = 'uncertainty_already_scored' if judgment.status == 'unknown' and judgment.uncertainty_reason != 'none' else 'unmet_floor' if judgment.status == 'unmet' else 'no_linked_attributes' if not values else 'applied'
        deduction = max((d.deduction for d in values), default=0.0) if reason == 'applied' else 0.0
        proof = {k: getattr(judgment, k) for k in RequirementJudgment.model_fields}
        result.append(RequirementAssessmentV9(**proof, match_score=CONDITION_SCORES[judgment.status], penalty=deduction, consistency_deductions=values, deduction_reason=reason, selected_alternative=selected.value if options else None))
    return result

@_preserve_function('routed_score', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def routed_score(relevance, thumbnail, retrieval, preference, source, item_id):
    """v37 handoff: inactive is None, distinct from active uncertain/zero R."""
    from fashion_recommendation_v2.schemas.ranking import ScoreApplicationV8
    from fashion_recommendation_v2.search.requirements import ranking_condition_ids
    active = bool(ranking_condition_ids(source.candidate_set.resolved_requirements))
    if active != (relevance is not None):
        raise ValueError('R activation must match ranking-owned soft conditions.')
    if active:
        return apply_relation(base_score(relevance, thumbnail, retrieval, preference), source, item_id)
    routing = source.candidate_set.resolved_requirements.condition_routing_v37
    intent = routing.relation_conditions[0].intent if routing.relation_conditions else None
    warm = preference is not None
    weights = dict(R=0.0, Q=0.2 if warm else 0.35, T=0.1, P=0.2 if warm else 0.0, Relation=0.5 if warm else 0.55)
    rest = weights['Q'] * thumbnail + weights['T'] * retrieval + weights['P'] * (preference or 0.0)
    residual = 1.0 - weights['Relation']
    original = rest / residual
    ratio = source.ralationRatio
    if intent is None:
        if ratio is not None or source.relation_intent is not None:
            raise ValueError('Relation input is not assigned by the v37 request contract.')
        weights = {k: v / residual if k != 'Relation' else 0.0 for k, v in weights.items()}
        return (original, ScoreApplicationV8(relation_type=None, reason='r_inactive_no_relation', original_base_score=original, base_weight=1.0, relation_weight=0.0, relation_contribution=0.0, diversity_enabled=False, component_weights_v37=weights))
    if source.relation_intent is not None and source.relation_intent != intent:
        raise ValueError('Ranking intent differs from frozen Search relation clause.')
    contract = relation_contract(ratio)
    if contract is None or ratio.intent != intent:
        raise ValueError('R inactive relation request requires evaluated Relation compatible with Ranking v9; absence/failure is not normal null.')
    entry = next((e for e in ratio.evaluations if e.item_id == item_id), None)
    detail = (getattr(ratio, contract.breakdown_field) or {}).get(item_id)
    if entry is None or detail is None:
        raise ValueError(f'{item_id}: Relation unevaluated/failure while R inactive; preserve failure, not a fabricated null score.')
    contribution = weights['Relation'] * (entry.score if entry.score is not None else 0.0)
    record = ScoreApplicationV8(relation_type=intent.relation_type, evidence_coverage=detail.evidence_coverage, reason='r_inactive_relation_null' if entry.score is None else 'r_inactive_relation_numeric', original_base_score=original, base_weight=residual, relation_weight=weights['Relation'], relation_contribution=contribution, diversity_enabled=False, component_weights_v37=weights)
    return (rest + contribution, record)

@_preserve_function('thumbnail', 'fashion_recommendation_v2.ranking.ranking_scoring_v9')
def thumbnail(candidate, source):
    analysis = candidate.search_analysis
    review = analysis.semantic_review
    if review is not None:
        from fashion_recommendation_v2.search.observation_review import observation_hash
        item = candidate.evaluation_item or candidate.item
        if review['target_sha256'] != observation_hash(item, source.resolved_requirements, review['target']):
            raise ValueError('v36 original review target hash mismatch.')
        raw = review['target']['model_response'][review['target']['target_slot']]
        if raw['thumbnail_observation_v8'] != analysis.thumbnail_observation_v8.model_dump(mode='json'):
            raise ValueError('Q differs from its original review target.')
    if review is None or review['status'] != 'passed':
        # Preserve v7 Q fallback, without inventing an observed unknown.
        observation = ThumbnailObservationV1(photo_type='unknown', product_focus='unknown', view_angle='unknown', support='unknown', background='unknown', evidence='Code fallback: Q observation review unavailable.', thum_quality=None, thum_quality_evidence=None)
    else:
        observation = analysis.thumbnail_observation_v8
    if source.search_policy_version in {'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessmentV57_ranking_thumbnail_v57 as ThumbnailQualityAssessmentV57
        return ThumbnailQualityAssessmentV57.from_observation(observation)
    return ThumbnailQualityAssessmentV2.from_observation(observation)
