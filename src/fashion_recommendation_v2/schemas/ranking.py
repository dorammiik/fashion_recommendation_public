"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_v0 ----

"""Ranking eval v0: deterministic thumbnail scoring from saved Search observations."""
from math import isclose as isclose_v0
from typing import Self
from pydantic import Field as Field_v0
from pydantic import model_validator as model_validator_v0
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v0
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV8_legacy as ThumbnailObservationV8_v0
RANKING_V0 = 'ranking_eval_v0'
RANKING_V0_RELATION = 'ranking_eval_v0_relation'
RANKING_V0_POLICIES = {RANKING_V0, RANKING_V0_RELATION}
THUMBNAIL_WEIGHTS = {'photo_type': 0.4, 'product_focus': 0.25, 'support': 0.125, 'background': 0.125, 'view_angle': 0.1}
THUMBNAIL_SCORES = {'photo_type': {'person': 1.0, 'product_only': 0.6, 'unknown': 0.0}, 'product_focus': {'full': 1.0, 'partial': 0.5, 'unknown': 0.0}, 'support': {'mannequin': 1.0, 'flat_lay': 1.0, 'hanger': 0.5, 'unknown': 0.0}, 'background': {'solid': 1.0, 'two_color': 0.75, 'three_color': 0.5, 'multicolor': 0.25, 'unknown': 0.0}, 'view_angle': {'front': 1.0, 'side': 0.7, 'back': 0.3, 'unknown': 0.0}}

@_preserve_function('v0_thumbnail_observation', 'fashion_recommendation_v2.schemas.ranking_v0')
def v0_thumbnail_observation(observation: ThumbnailObservationV8_v0):
    # The v0 formula uses only its original fields, even on newer Search records.
    return ThumbnailObservationV8_v0.model_validate({key: getattr(observation, key) for key in ThumbnailObservationV8_v0.model_fields})

@_preserve_function('thumbnail_components', 'fashion_recommendation_v2.schemas.ranking_v0')
def thumbnail_components(observation: ThumbnailObservationV8_v0):
    observation = v0_thumbnail_observation(observation)
    weights = {key: weight for key, weight in THUMBNAIL_WEIGHTS.items() if not (key == 'support' and observation.photo_type == 'person')}
    scores = {key: THUMBNAIL_SCORES[key][getattr(observation, key)] for key in weights}
    score = sum((weights[key] * scores[key] for key in weights)) / sum(weights.values())
    return (scores, weights, score)

@_preserve_class('ThumbnailQualityAssessment', 'fashion_recommendation_v2.schemas.ranking_v0')
class ThumbnailQualityAssessment(StrictBaseModel_v0):
    observation: ThumbnailObservationV8_v0
    attribute_scores: dict[str, float]
    applied_weights: dict[str, float]
    score: float = Field_v0(ge=0, le=1)

    @classmethod
    def from_observation(cls, observation: ThumbnailObservationV8_v0) -> Self:
        observation = v0_thumbnail_observation(observation)
        scores, weights, score = thumbnail_components(observation)
        return cls(observation=observation.model_copy(deep=True), attribute_scores=scores, applied_weights=weights, score=score)

    @model_validator_v0(mode='after')
    def validate_calculation(self) -> Self:
        scores, weights, score = thumbnail_components(self.observation)
        if self.attribute_scores != scores or self.applied_weights != weights:
            raise ValueError('Thumbnail attribute scores and weights must follow Ranking eval v0.')
        if not isclose_v0(self.score, score, abs_tol=1e-12):
            raise ValueError('Thumbnail quality must equal the normalized weighted score.')
        return self

@_preserve_function('validate_ranking_v0_against', 'fashion_recommendation_v2.schemas.ranking_v0')
def validate_ranking_v0_against(result, input_data):
    """Validate v0 provenance and arithmetic without reapplying Search gates."""
    from fashion_recommendation_v2.agents.ranking_runner import SCORE_MAPPING
    from fashion_recommendation_v2.agents.ranking_runner import saved_v0_evidence
    from fashion_recommendation_v2.agents.ranking_runner import retrieval_scores
    from fashion_recommendation_v2.agents.ranking_runner import pair_similarity
    from fashion_recommendation_v2.agents.ranking_preferences import request_profile
    from fashion_recommendation_v2.agents.ranking_preferences import validate_ranked_preference
    from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear
    from fashion_recommendation_v2.tools.ranking_observations import observation_assessments
    source = input_data.candidate_set
    candidates = {c.item.item_id: c for c in source.candidates}
    if len(candidates) != len(source.candidates) or source.candidate_count != len(candidates):
        raise ValueError('Candidate counts and unique item IDs must match.')
    attempts = [a.attempt_id for a in source.search_attempts]
    successful = {a.attempt_id for a in source.search_attempts if a.status == 'success'}
    if len(attempts) != len(set(attempts)) or any((entry.attempt_id not in successful for c in candidates.values() for entry in c.sources)):
        raise ValueError('Candidate sources require unique, successful Search attempts.')
    profile = request_profile(input_data)
    soft_requirements = [r for r in source.resolved_requirements.requirements if r.kind == 'soft']
    confirmations = {item_id: observation_assessments(c, source.resolved_requirements)[0] if result.scoring_policy_version in RANKING_V7_POLICIES | RANKING_V8_POLICIES else require_visual_confirmation(c, source.resolved_requirements) for item_id, c in candidates.items()} if result.scoring_policy_version in RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES else {}
    expected = {}
    derivations = {} if result.scoring_policy_version in RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES else None
    excluded_ids = set()
    for item_id, candidate in candidates.items():
        if result.scoring_policy_version in RANKING_V4_POLICIES | RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES | RANKING_V9_POLICIES:
            exposure = require_exposure(candidate)
            if exposure.status == 'restricted':
                expected[item_id] = {'restricted': True}
                excluded_ids.add(item_id)
                continue
        if excluded_childrenswear(candidate.item, source.resolved_requirements) if result.scoring_policy_version not in RANKING_V9_POLICIES else not candidate.search_analysis.admission_checks.childrenswear_pass:
            expected[item_id] = {'child': True}
            excluded_ids.add(item_id)
            continue
        if source.search_policy_version is None:
            raise ValueError('Ranking eval v0 requires saved Search evidence.')
        judgments, thumbnail = saved_v0_evidence(candidate, source, profile, policy_version=result.scoring_policy_version, derivations=derivations)
        by_id = {j.requirement_id: j for j in judgments.judgments}
        if result.scoring_policy_version in RANKING_V9_POLICIES:
            from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
            assessments = scoring_for_policy(result.scoring_policy_version).assessments(candidate, source)
        else:
            assessments = [RequirementAssessment(**by_id[r.requirement_id].model_dump(), match_score=SCORE_MAPPING[by_id[r.requirement_id].status][0], penalty=SCORE_MAPPING[by_id[r.requirement_id].status][1]) for r in soft_requirements]
        relevance = sum((max(0.0, a.match_score - a.penalty) for a in assessments)) / len(assessments) if assessments else 1.0
        if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and (not assessments):
            relevance = None
        base_relevance = relevance
        if item_id in confirmations:
            relevance *= confirmations[item_id].score
        expected[item_id] = dict(base_relevance=base_relevance, child=False, judgments=judgments, thumbnail=thumbnail, assessments=assessments, relevance=relevance)
        if relevance is not None and relevance < 0.5:
            excluded_ids.add(item_id)
    if result.requirement_derivations_v6 != derivations:
        raise ValueError('Ranking v6 derivations must match the frozen requirements and saved evidence.')
    if {i.item_id for i in result.excluded_items} != excluded_ids:
        raise ValueError('Ranking exclusions must match relevance, age and the active exposure policy.')
    if result.returned_count != min(input_data.requested_count, len(candidates) - len(excluded_ids)):
        raise ValueError('Ranking must fill the requested count from eligible candidates.')
    selected_features = []
    for output in [*sorted(result.ranked_items, key=lambda i: i.rank), *result.excluded_items]:
        if output.item_id not in candidates:
            raise ValueError('Output item ID is absent from the input CandidateSet.')
        candidate = candidates[output.item_id]
        entry = expected[output.item_id]
        if result.scoring_policy_version in RANKING_V4_POLICIES | RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES | RANKING_V9_POLICIES:
            if output.exposure_suitability != require_exposure(candidate):
                raise ValueError('Exposure suitability must preserve the exact saved Search evidence.')
        if entry.get('restricted'):
            if isinstance(output, RankedItem) or output.reason_codes != ['exposure_restricted'] or output.hard_constraint_assessments or output.requirement_assessments or (output.request_relevance_score is not None) or output.conflicts or output.evaluation_issues:
                raise ValueError('Restricted exposure must be excluded before scoring with no fallback.')
            continue
        if output.hard_constraint_assessments:
            raise ValueError('Ranking eval v0 must not repeat hard-condition checks.')
        if entry['child']:
            if isinstance(output, RankedItem) or output.reason_codes != ['unrequested_childrenswear'] or output.requirement_assessments or (output.request_relevance_score is not None) or output.conflicts or output.evaluation_issues:
                raise ValueError('Age exclusions must preserve the existing policy contract.')
            continue
        if output.requirement_assessments != entry['assessments']:
            raise ValueError('Ranking assessments must match saved soft judgments under the active policy.')
        if output.conflicts != entry['judgments'].conflicts:
            raise ValueError('Ranking conflicts must preserve saved Search evidence.')
        relevance = entry['relevance']
        if result.scoring_policy_version in RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES:
            if output.visual_confirmation_assessment != confirmations[output.item_id]:
                raise ValueError('Visual confirmation must preserve the saved reviewed Search observation.')
            base = output.scores.request_relevance_base_score if isinstance(output, RankedItem) else output.request_relevance_base_score
            if base is None or not isclose_v0(base, entry['base_relevance'], abs_tol=1e-12):
                raise ValueError('Base relevance must average soft judgments under the active policy.')
            if not isinstance(output, RankedItem) and output.thumbnail_quality_assessment != entry['thumbnail']:
                raise ValueError('Excluded Q must preserve the reviewed v5 observation.')
        if isinstance(output, RankedItem):
            if relevance is not None and relevance < 0.5:
                raise ValueError('Selected items must meet the minimum request relevance of 0.50.')
            s = output.scores
            if (s.request_relevance_score is None) != (relevance is None) or (relevance is not None and (not isclose_v0(s.request_relevance_score, relevance, abs_tol=1e-12))):
                raise ValueError('Request relevance must follow the active policy and saved evidence.')
            if s.request_relevance_active != (relevance is not None if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else None):
                raise ValueError('Relevance activation must match the input contract, not an output claim.')
            if output.thumbnail_quality_assessment != entry['thumbnail']:
                raise ValueError('Thumbnail quality assessment must match the saved Search observation.')
            if s.thumbnail_quality_score is None or not isclose_v0(s.thumbnail_quality_score, entry['thumbnail'].score, abs_tol=1e-12):
                raise ValueError('Thumbnail quality score must match the saved Search observation.')
            if output.diversity_features != entry['judgments'].diversity_features or output.preference_observations != entry['judgments'].preference_features:
                raise ValueError('Ranking features must preserve saved Search evidence.')
            n, f, retrieval = retrieval_scores(candidate, source)
            if not all((isclose_v0(actual, wanted, abs_tol=1e-12) for actual, wanted in [(s.native_order_score, n), (s.appearance_score, f), (s.ebay_best_match_score, retrieval)])):
                raise ValueError('Retrieval scores must match the saved Search sources.')
            similarity = max((pair_similarity(output.diversity_features, prior) for prior in selected_features), default=0.0)
            penalty = 0.1 * similarity
            if result.scoring_policy_version in RANKING_V8_POLICIES | RANKING_V9_POLICIES:
                from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
                if not scoring_for_policy(result.scoring_policy_version).diversity_enabled(input_data):
                    penalty = 0.0
            if not isclose_v0(s.max_selected_similarity, similarity, abs_tol=1e-12) or not isclose_v0(s.diversity_penalty, penalty, abs_tol=1e-12):
                raise ValueError('Diversity penalty must match previously selected items.')
            validate_ranked_preference(output, input_data, candidate.evaluation_item or candidate.item, scoring_policy_version=result.scoring_policy_version)
            selected_features.append(output.diversity_features)
        elif relevance is None or relevance >= 0.5 or output.reason_codes != ['below_minimum_relevance'] or (output.request_relevance_score is None) or (not isclose_v0(output.request_relevance_score, relevance, abs_tol=1e-12)) or output.evaluation_issues:
            raise ValueError('Ranking eval v0 relevance exclusions must match the saved soft judgments.')
    return result


# ---- ranking_v1 ----

"""Ranking v1: six-attribute thumbnail score with product-only presentation quality."""
from math import isclose as isclose_v1
from pydantic import Field as Field_v1
from pydantic import model_validator as model_validator_v1
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v1
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1_v1
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV8_legacy as ThumbnailObservationV8
V0_SCORES = THUMBNAIL_SCORES
RANKING_V1 = 'ranking_eval_v1'
RANKING_V1_RELATION = 'ranking_eval_v1_relation'
RANKING_V1_POLICIES = {RANKING_V1, RANKING_V1_RELATION}
THUMBNAIL_WEIGHTS_V1 = {'photo_type': 0.35, 'product_focus': 0.2, 'thum_quality': 0.2, 'support': 0.1, 'background': 0.1, 'view_angle': 0.05}
THUMBNAIL_SCORES_V1_v1 = {**V0_SCORES, 'thum_quality': {'met': 1.0, 'mostly_met': 0.75, 'partial': 0.5, 'unknown': 0.4, 'unmet': 0.0}}

@_preserve_function('observation_v1', 'fashion_recommendation_v2.schemas.ranking_v1')
def observation_v1_v1(observation):
    data = observation.model_dump()
    if not isinstance(observation, ThumbnailObservationV1_v1):
        if observation.photo_type == 'product_only':
            raise ValueError('Ranking v1 requires Search thum_quality for product_only; enrich the frozen input first.')
        # Inactive fields are deterministically null; no observation is invented.
        data.update(thum_quality=None, thum_quality_evidence=None)
    return ThumbnailObservationV1_v1.model_validate(data)

@_preserve_function('thumbnail_components_v1', 'fashion_recommendation_v2.schemas.ranking_v1')
def thumbnail_components_v1(observation):
    observation = observation_v1_v1(observation)
    weights = {key: weight for key, weight in THUMBNAIL_WEIGHTS_V1.items() if not (key == 'support' and observation.photo_type == 'person') and (not (key == 'thum_quality' and observation.photo_type != 'product_only'))}
    scores = {key: THUMBNAIL_SCORES_V1_v1[key][getattr(observation, key)] for key in weights}
    return (scores, weights, sum((weights[k] * scores[k] for k in weights)) / sum(weights.values()))

@_preserve_class('ThumbnailQualityAssessmentV1', 'fashion_recommendation_v2.schemas.ranking_v1')
class ThumbnailQualityAssessmentV1(StrictBaseModel_v1):
    observation: ThumbnailObservationV1_v1
    attribute_scores: dict[str, float]
    applied_weights: dict[str, float]
    score: float = Field_v1(ge=0, le=1)

    @classmethod
    def from_observation(cls, observation: ThumbnailObservationV8):
        observation = observation_v1_v1(observation)
        scores, weights, score = thumbnail_components_v1(observation)
        return cls(observation=observation, attribute_scores=scores, applied_weights=weights, score=score)

    @model_validator_v1(mode='after')
    def validate_calculation(self):
        scores, weights, score = thumbnail_components_v1(self.observation)
        if self.attribute_scores != scores or self.applied_weights != weights:
            raise ValueError('Thumbnail attribute scores and weights must follow Ranking eval v1.')
        if not isclose_v1(self.score, score, abs_tol=1e-12):
            raise ValueError('Thumbnail quality must equal the v1 normalized weighted score.')
        return self


# ---- ranking_v5 ----

"""Ranking v5 applies saved visual confirmability to R and reviewed observations to Q."""
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationAssessmentV5
RANKING_V5 = 'ranking_eval_v5'
RANKING_V5_RELATION = 'ranking_eval_v5_relation'
RANKING_V5_POLICIES = {RANKING_V5, RANKING_V5_RELATION}

@_preserve_function('require_visual_confirmation', 'fashion_recommendation_v2.schemas.ranking_v5')
def require_visual_confirmation(candidate, requirements):
    from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import SearchImageObservationsOutputV5
    from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import validate_reviewed_observation
    exposure = require_exposure(candidate)
    analysis = candidate.search_analysis
    if analysis.ranking_visual_error_v5 or analysis.ranking_thumbnail_observation_v5 is None or analysis.visual_confirmation_v5 is None or (analysis.visual_consistency_v5 is None):
        raise ValueError('Ranking v5 requires complete Search image observations with validated code/semantic audit.')
    observation = SearchImageObservationsOutputV5(ranking_thumbnail_observation_v5=analysis.ranking_thumbnail_observation_v5, visual_confirmation_v5=analysis.visual_confirmation_v5, exposure_suitability=exposure)
    validate_reviewed_observation(candidate.evaluation_item or candidate.item, requirements, observation, analysis.visual_consistency_v5)
    return VisualConfirmationAssessmentV5.from_observation(observation.visual_confirmation_v5)


# ---- ranking_v6 ----

"""Ranking v6: evidence-derived soft judgments; Q/V retain the v5 contract."""
from typing import Literal as Literal_v6
from pydantic import Field as Field_v6
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v6
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment as RequirementJudgment_v6
RANKING_V6 = 'ranking_eval_v6'
RANKING_V6_RELATION = 'ranking_eval_v6_relation'
RANKING_V6_POLICIES = {RANKING_V6, RANKING_V6_RELATION}

@_preserve_class('RequirementDerivationV6', 'fashion_recommendation_v2.schemas.ranking_v6')
class RequirementDerivationV6(StrictBaseModel_v6):
    requirement_sha256: str = Field_v6(pattern=r'^[0-9a-f]{64}$')
    source_judgment: RequirementJudgment_v6
    derived_judgment: RequirementJudgment_v6
    reasons: list[Literal_v6['saved_judgment', 'absent_metadata_path', 'insufficient_evidence', 'unresolved_conflict', 'not_observable', 'or_aggregation', 'incomplete_or_evidence']]


# ---- ranking_v7 ----

"""v7 availability is code-derived, distinct from a model's visual unknown."""
from math import isclose as isclose_v7
from typing import Literal as Literal_v7
from pydantic import Field as Field_v7
from pydantic import model_validator as model_validator_v7
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v7
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationV5
from fashion_recommendation_v2.schemas.visual_confirmation import VISIBILITY_SCORES
RANKING_V7 = 'ranking_eval_v7'
RANKING_V7_RELATION = 'ranking_eval_v7_relation'
RANKING_V7_POLICIES = {RANKING_V7, RANKING_V7_RELATION}
VISIBILITY_SCORES_V7 = {**VISIBILITY_SCORES, 'unavailable': 0.6}
VisibilityStatusV7 = Literal_v7['met', 'mostly_met', 'partial', 'unknown', 'unavailable']

@_preserve_class('ObservationUnavailableV7', 'fashion_recommendation_v2.schemas.ranking_v7')
class ObservationUnavailableV7(StrictBaseModel_v7):
    code: Literal_v7['observation_unavailable'] = 'observation_unavailable'
    reason: Literal_v7['missing_response', 'validation_failed']
    details: list[str] = Field_v7(min_length=1)
    affected: list[Literal_v7['Q', 'V']] = Field_v7(min_length=1)
    origin: Literal_v7['code'] = 'code'

@_preserve_class('VisualConfirmationAssessmentV7', 'fashion_recommendation_v2.schemas.ranking_v7')
class VisualConfirmationAssessmentV7(StrictBaseModel_v7):
    observation: VisualConfirmationV5 | None
    status: VisibilityStatusV7
    score: float = Field_v7(ge=0.4, le=1)
    availability: ObservationUnavailableV7 | None

    @classmethod
    def from_observation(cls, observation):
        score = observation.score
        status = next((s for s, value in VISIBILITY_SCORES.items() if value == score))
        return cls(observation=observation, status=status, score=score, availability=None)

    @classmethod
    def unavailable(cls, diagnostic):
        return cls(observation=None, status='unavailable', score=VISIBILITY_SCORES_V7['unavailable'], availability=diagnostic)

    @model_validator_v7(mode='after')
    def validate_score(self):
        if not isclose_v7(self.score, VISIBILITY_SCORES_V7[self.status], abs_tol=1e-12):
            raise ValueError('V must use the frozen v7 status table.')
        if self.status == 'unavailable':
            if self.observation is not None or self.availability is None or 'V' not in self.availability.affected:
                raise ValueError('Unavailable V requires a code diagnostic and no invented observation.')
        elif self.observation is None or self.availability is not None or (not isclose_v7(self.score, self.observation.score, abs_tol=1e-12)):
            raise ValueError('Observed V must preserve the minimum of the actual visual checks.')
        return self


# ---- ranking_v9 ----

"""v9 condition-local source consistency deductions; no visibility multiplier."""
from typing import Literal as Literal_v9
from pydantic import Field as Field_v9
from pydantic import model_validator as model_validator_v9
from math import isclose
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v9
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ConsistencyStatus
RANKING_V9 = 'ranking_eval_v9'
RANKING_V9_RELATION = 'ranking_eval_v9_relation'
RANKING_V9_POLICIES = {RANKING_V9, RANKING_V9_RELATION}

@_preserve_class('ConsistencyDeduction', 'fashion_recommendation_v2.schemas.ranking_v9')
class ConsistencyDeduction(StrictBaseModel_v9):
    attribute_key: str
    status: ConsistencyStatus
    deduction: float = Field_v9(ge=0, le=1)
    source_path: str

@_preserve_class('RequirementAssessmentV9', 'fashion_recommendation_v2.schemas.ranking_v9')
class RequirementAssessmentV9(RequirementJudgment):
    score_policy: Literal_v9['v9'] = 'v9'
    match_score: float = Field_v9(ge=0, le=1)
    penalty: float = Field_v9(ge=0, le=1)
    consistency_deductions: list[ConsistencyDeduction]
    deduction_reason: Literal_v9['applied', 'no_linked_attributes', 'uncertainty_already_scored', 'unmet_floor']
    selected_alternative: str | None

    @model_validator_v9(mode='after')
    def check_arithmetic(self):
        from fashion_recommendation_v2.ranking.ranking_policy import CONDITION_SCORES
        from fashion_recommendation_v2.ranking.ranking_policy import CONSISTENCY_DEDUCTIONS
        if not isclose(self.match_score, CONDITION_SCORES[self.status]):
            raise ValueError('v9 condition score differs from policy.')
        if any((not isclose(d.deduction, CONSISTENCY_DEDUCTIONS[d.status]) for d in self.consistency_deductions)):
            raise ValueError('v9 attribute deduction differs from policy.')
        expected = max((d.deduction for d in self.consistency_deductions), default=0.0) if self.deduction_reason == 'applied' else 0.0
        if not isclose(self.penalty, expected):
            raise ValueError('v9 condition deduction differs from policy.')
        return self


# ---- ranking_v8 ----

"""Code-only v8 score application record; Search observations retain v7 schemas."""
from typing import Literal as Literal_v8
from pydantic import Field as Field_v8
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v8
RANKING_V8 = 'ranking_eval_v8'
RANKING_V8_RELATION = 'ranking_eval_v8_relation'
RANKING_V8_POLICIES = {RANKING_V8, RANKING_V8_RELATION}

@_preserve_class('ScoreApplicationV8', 'fashion_recommendation_v2.schemas.ranking_v8')
class ScoreApplicationV8(StrictBaseModel_v8):
    relation_type: Literal_v8['similarity', 'compatibility'] | None
    evidence_coverage: float | None = Field_v8(default=None, ge=0, le=1)
    reason: Literal_v8['no_relation', 'unevaluated', 'null_fallback', 'compatibility_numeric', 'similarity_insufficient_coverage', 'similarity_partial_coverage', 'similarity_full_coverage', 'r_inactive_relation_numeric', 'r_inactive_relation_null', 'r_inactive_no_relation']
    component_weights_v37: dict[str, float] | None = None

    @model_serializer(mode='wrap')
    def serialize_components(self, handler):
        data = handler(self)
        if self.component_weights_v37 is None:
            data.pop('component_weights_v37', None)
        return data
    original_base_score: float = Field_v8(ge=0, le=1)
    base_weight: float = Field_v8(ge=0, le=1)
    relation_weight: float = Field_v8(ge=0, le=1)
    relation_contribution: float = Field_v8(ge=0, le=1)
    diversity_enabled: bool


# ---- ranking_v4 ----

"""Ranking v4: saved exposure eligibility, with unchanged v2 scoring weights."""
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability
RANKING_V4 = 'ranking_eval_v4'
RANKING_V4_RELATION = 'ranking_eval_v4_relation'
RANKING_V4_POLICIES = {RANKING_V4, RANKING_V4_RELATION}

@_preserve_function('require_exposure', 'fashion_recommendation_v2.schemas.ranking_v4')
def require_exposure(candidate):
    analysis = candidate.search_analysis
    item = candidate.item
    evidence_item = candidate.evaluation_item or item
    if analysis is None or analysis.exposure_suitability is None or analysis.item_id != item.item_id or (analysis.image_url != item.image_url) or (evidence_item.item_id != item.item_id) or (evidence_item.image_url != item.image_url) or (not item.image_url):
        raise ValueError('Ranking v4 requires saved exposure suitability for the exact candidate/image snapshot.')
    return ExposureSuitability.model_validate(analysis.exposure_suitability.model_dump())


# ---- ranking_v2 ----

"""Ranking v2: balanced photo-type/presentation weighting and cold scoring."""
from math import isclose as isclose_v2
from pydantic import Field as Field_v2
from pydantic import model_validator as model_validator_v2
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v2
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1
THUMBNAIL_SCORES_V1 = THUMBNAIL_SCORES_V1_v1
observation_v1 = observation_v1_v1
RANKING_V2 = 'ranking_eval_v2'
RANKING_V2_RELATION = 'ranking_eval_v2_relation'
RANKING_V2_POLICIES = {RANKING_V2, RANKING_V2_RELATION}
THUMBNAIL_WEIGHTS_V2 = {'photo_type': 0.35, 'product_focus': 0.15, 'thum_quality': 0.35, 'support': 0.06, 'background': 0.06, 'view_angle': 0.03}

@_preserve_function('thumbnail_components_v2', 'fashion_recommendation_v2.schemas.ranking_v2')
def thumbnail_components_v2(observation):
    observation = observation_v1(observation)
    weights = {key: weight for key, weight in THUMBNAIL_WEIGHTS_V2.items() if not (key == 'support' and observation.photo_type == 'person') and (not (key == 'thum_quality' and observation.photo_type != 'product_only'))}
    scores = {key: THUMBNAIL_SCORES_V1[key][getattr(observation, key)] for key in weights}
    return (scores, weights, sum((weights[k] * scores[k] for k in weights)) / sum(weights.values()))

@_preserve_class('ThumbnailQualityAssessmentV2', 'fashion_recommendation_v2.schemas.ranking_v2')
class ThumbnailQualityAssessmentV2(StrictBaseModel_v2):
    observation: ThumbnailObservationV1
    attribute_scores: dict[str, float]
    applied_weights: dict[str, float]
    score: float = Field_v2(ge=0, le=1)

    @classmethod
    def from_observation(cls, observation):
        observation = observation_v1(observation)
        scores, weights, score = thumbnail_components_v2(observation)
        return cls(observation=observation, attribute_scores=scores, applied_weights=weights, score=score)

    @model_validator_v2(mode='after')
    def validate_calculation(self):
        scores, weights, score = thumbnail_components_v2(self.observation)
        if self.attribute_scores != scores or self.applied_weights != weights:
            raise ValueError('Thumbnail attribute scores and weights must follow Ranking eval v2.')
        if not isclose_v2(self.score, score, abs_tol=1e-12):
            raise ValueError('Thumbnail quality must equal the v2 normalized weighted score.')
        return self


# ---- ranking_thumbnail_v57 ----

"""Search v57 photo policy; older Search observations retain their original Q."""
from math import isclose as isclose_ranking_thumbnail_v57
from typing import Literal as Literal_ranking_thumbnail_v57
from pydantic import model_validator as model_validator_ranking_thumbnail_v57
THUMBNAIL_SCORES_V1_ranking_thumbnail_v57 = THUMBNAIL_SCORES_V1_v1
observation_v1_ranking_thumbnail_v57 = observation_v1_v1
ThumbnailQualityAssessmentV2_ranking_thumbnail_v57 = ThumbnailQualityAssessmentV2
THUMBNAIL_WEIGHTS_V2_ranking_thumbnail_v57 = THUMBNAIL_WEIGHTS_V2
THUMBNAIL_SCORES_V57_ranking_thumbnail_v57 = {**THUMBNAIL_SCORES_V1_ranking_thumbnail_v57, 'background': {**THUMBNAIL_SCORES_V1_ranking_thumbnail_v57['background'], 'two_color': 0.4, 'three_color': 0.25, 'multicolor': 0.1}}

@_preserve_function('thumbnail_components_v57', 'fashion_recommendation_v2.schemas.ranking_thumbnail_v57')
def thumbnail_components_v57_ranking_thumbnail_v57(observation):
    observation = observation_v1_ranking_thumbnail_v57(observation)
    excluded = {'support', 'background'} if observation.photo_type == 'person' else set()
    if observation.photo_type != 'product_only':
        excluded.add('thum_quality')
    weights = {k: v for k, v in THUMBNAIL_WEIGHTS_V2_ranking_thumbnail_v57.items() if k not in excluded}
    scores = {k: THUMBNAIL_SCORES_V57_ranking_thumbnail_v57[k][getattr(observation, k)] for k in weights}
    score = sum((weights[k] * scores[k] for k in weights)) / sum(weights.values())
    return (scores, weights, score)

@_preserve_class('ThumbnailQualityAssessmentV57', 'fashion_recommendation_v2.schemas.ranking_thumbnail_v57')
class ThumbnailQualityAssessmentV57_ranking_thumbnail_v57(ThumbnailQualityAssessmentV2_ranking_thumbnail_v57):
    # Required marker prevents old serialized assessments from selecting this schema.
    scoring_policy: Literal_ranking_thumbnail_v57['search_v57']

    @classmethod
    def from_observation(cls, observation):
        observation = observation_v1_ranking_thumbnail_v57(observation)
        scores, weights, score = thumbnail_components_v57_ranking_thumbnail_v57(observation)
        return cls(scoring_policy='search_v57', observation=observation, attribute_scores=scores, applied_weights=weights, score=score)

    @model_validator_ranking_thumbnail_v57(mode='after')
    def validate_calculation(self):
        scores, weights, score = thumbnail_components_v57_ranking_thumbnail_v57(self.observation)
        if self.attribute_scores != scores or self.applied_weights != weights:
            raise ValueError('Thumbnail components must follow Search v57.')
        if not isclose_ranking_thumbnail_v57(self.score, score, abs_tol=1e-12):
            raise ValueError('Thumbnail quality must equal the v57 normalized weighted score.')
        return self


# ---- ranking_v10 ----

"""v10 upstream failure reporting; score arithmetic stays v9."""
from typing import Literal as Literal_v10
from pydantic import Field as Field_v10
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v10
RANKING_V10 = 'ranking_eval_v10'
RANKING_V10_RELATION = 'ranking_eval_v10_relation'
RANKING_V10_POLICIES = {RANKING_V10, RANKING_V10_RELATION}

@_preserve_class('UpstreamFailureV10', 'fashion_recommendation_v2.schemas.ranking_v10')
class UpstreamFailureV10(StrictBaseModel_v10):
    stage: Literal_v10['search', 'relation']
    status: Literal_v10['fail', 'unevaluated']
    reason: str = Field_v10(min_length=1)
    source_paths: list[str] = Field_v10(min_length=1)

    @property
    def reason_code(self):
        return self.stage + ('_evaluation_failed' if self.status == 'fail' else '_unevaluated')


# ---- ranking ----

"""Ranking contracts, including unified v0.3 analysis and legacy output validation.

The scoring implementation owns score calculation and evidence generation.
Use FinalRanking.validate_against(input_data) to validate input references before
publishing an output; standalone model validation cannot resolve those references.
"""
from fashion_recommendation_v2.validation_reuse import validated_once
from math import isclose as isclose_base
from typing import Literal as Literal_base
from typing import Self as Self_base
from pydantic import Field as Field_base
from pydantic import model_validator as model_validator_base
from pydantic import model_serializer as model_serializer_base
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.relation import RelationRatio as RelationRatio_base
from fashion_recommendation_v2.schemas.relation import RelationAgentInput
from fashion_recommendation_v2.schemas.relation import RelationEvaluation
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent as RelationIntent_base
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference_profile import Attribute
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet as CandidateSet_base
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.stylist import StylistAttribute
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.stylist import NonBlankText_base as NonBlankText
from fashion_recommendation_v2.schemas.stylist import Alternatives
RANKING_V0_POLICIES_base = RANKING_V0_POLICIES
RANKING_V0_RELATION_base = RANKING_V0_RELATION
ThumbnailQualityAssessment_base = ThumbnailQualityAssessment
RANKING_V1_POLICIES_base = RANKING_V1_POLICIES
RANKING_V1_RELATION_base = RANKING_V1_RELATION
ThumbnailQualityAssessmentV1_base = ThumbnailQualityAssessmentV1
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability as ExposureSuitability_base
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationAssessmentV5 as VisualConfirmationAssessmentV5_base
RANKING_V5_POLICIES_base = RANKING_V5_POLICIES
RANKING_V5_RELATION_base = RANKING_V5_RELATION
RANKING_V6_base = RANKING_V6
RANKING_V6_RELATION_base = RANKING_V6_RELATION
RANKING_V6_POLICIES_base = RANKING_V6_POLICIES
RANKING_V7_base = RANKING_V7
RANKING_V7_RELATION_base = RANKING_V7_RELATION
RANKING_V7_POLICIES_base = RANKING_V7_POLICIES
RANKING_V9_base = RANKING_V9
RANKING_V9_RELATION_base = RANKING_V9_RELATION
RANKING_V9_POLICIES_base = RANKING_V9_POLICIES
RequirementAssessmentV9_base = RequirementAssessmentV9
RANKING_V8_base = RANKING_V8
RANKING_V8_RELATION_base = RANKING_V8_RELATION
RANKING_V8_POLICIES_base = RANKING_V8_POLICIES
RequirementDerivationV6_base = RequirementDerivationV6
VisualConfirmationAssessmentV7_base = VisualConfirmationAssessmentV7
RANKING_V4_POLICIES_base = RANKING_V4_POLICIES
RANKING_V4_RELATION_base = RANKING_V4_RELATION
ThumbnailQualityAssessmentV57_ranking = ThumbnailQualityAssessmentV57_ranking_thumbnail_v57
RANKING_V2_POLICIES_base = RANKING_V2_POLICIES
RANKING_V2_RELATION_base = RANKING_V2_RELATION
ThumbnailQualityAssessmentV2_base = ThumbnailQualityAssessmentV2

@_preserve_class('RankingAgentInput', 'fashion_recommendation_v2.schemas.ranking')
class RankingAgentInput_base(StrictBaseModel_base):
    candidate_set: CandidateSet_base
    user_request: str = Field_base(min_length=1)
    preference_profile: PreferenceProfile | None = None
    ralationRatio: RelationRatio_base | None = None
    preference_category: str | None = None
    relation_intent: RelationIntent_base | None = None

    @model_serializer_base(mode="wrap")
    def serialize_relation_context(self, handler):
        data = handler(self)
        if self.relation_intent is None:
            data.pop("relation_intent", None)
        return data
    requested_count: int = Field_base(ge=1)

    @model_validator_base(mode="before")
    @classmethod
    def read_legacy_null_stylist(cls, data):
        if isinstance(data, dict) and data.get('relation_result', 'absent') is None:
            data = {key: value for key, value in data.items() if key != 'relation_result'}
        # Historical smoke inputs carried an unused null. Do not emit it again.
        if isinstance(data, dict) and 'stylist_resolution' in data and (data['stylist_resolution'] is None):
            return {key: value for key, value in data.items() if key != 'stylist_resolution'}
        return data

    @model_validator_base(mode="after")
    def validate_v01_input(self) -> Self_base:
        if self.candidate_set.resolved_requirements is None:
            raise ValueError("Ranking requires candidate_set.resolved_requirements.")
        if self.ralationRatio is not None and self.ralationRatio.omitted:
            raise ValueError('Omitted relation conditions must not enter Ranking.')
        if self.ralationRatio is not None:
            if self.relation_intent is not None and self.relation_intent != self.ralationRatio.intent:
                raise ValueError("Ranking relation context must match the supplied Relation intent.")
            self.ralationRatio.validate_against(RelationAgentInput(candidate_set=self.candidate_set, intent=self.ralationRatio.intent, anchor_item=self.ralationRatio.anchor_item, evaluation_version=self.ralationRatio.evaluation_version, anchor_search_analysis=self.ralationRatio.anchor_search_analysis))
        return self
from fashion_recommendation_v2.schemas.product_evidence import HardConstraintAssessment
from fashion_recommendation_v2.schemas.product_evidence import ImageEvidence
from fashion_recommendation_v2.schemas.product_evidence import EvidenceConflict
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment as RequirementJudgment_base
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature

@_preserve_class('RequirementAssessment', 'fashion_recommendation_v2.schemas.ranking')
class RequirementAssessment(RequirementJudgment_base):
    """Judgment plus deterministic score mapping, including hard conditions."""
    match_score: float = Field_base(ge=0, le=1)
    penalty: float = Field_base(ge=0, le=1)

    @model_validator_base(mode="after")
    def validate_score_mapping(self) -> Self_base:
        score, penalty = {"met": (1.0, 0.0), "mostly_met": (0.75, 0.0), "partial": (0.5, 0.0), "unknown": (0.5, 0.1), "unmet": (0.0, 0.3)}[self.status]
        if not isclose_base(self.match_score, score) or not isclose_base(self.penalty, penalty):
            raise ValueError("Condition score/penalty must match the frozen judgment mapping.")
        return self

@_preserve_class('RankingEvaluationFailure', 'fashion_recommendation_v2.schemas.ranking')
class RankingEvaluationFailure(StrictBaseModel_base):
    """Execution failure after retry, not a product-level unknown assessment."""
    batch_id: str
    item_ids: list[str] = Field_base(min_length=1)
    code: Literal_base["api_error", "image_loading_error", "invalid_response", "missing_assessments"]
    message: str = Field_base(min_length=1)
    retry_count: int = Field_base(ge=0, le=1)
from fashion_recommendation_v2.schemas.product_evidence import RankingItemIssue
from fashion_recommendation_v2.schemas.product_evidence import PreferenceObservation
ScoreApplicationV8_base = ScoreApplicationV8

@_preserve_class('RankingScoreBreakdown', 'fashion_recommendation_v2.schemas.ranking')
class RankingScoreBreakdown(StrictBaseModel_base):
    application_v8: ScoreApplicationV8_base | None = None
    request_relevance_active: bool | None = None

    @model_serializer_base(mode="wrap")
    def serialize_application(self, handler):
        data = handler(self)
        if self.application_v8 is None:
            data.pop("application_v8", None)
        if self.request_relevance_active is None:
            data.pop('request_relevance_active', None)
        return data
    request_relevance_base_score: float | None = Field_base(default=None, ge=0, le=1)
    visual_confirmation_score: float | None = Field_base(default=None, ge=0.4, le=1)
    request_relevance_score: float | None = Field_base(ge=0, le=1)
    thumbnail_quality_score: float | None = Field_base(default=None, ge=0, le=1)
    native_order_score: float = Field_base(ge=0, le=1)
    appearance_score: float = Field_base(ge=0, le=1)
    ebay_best_match_score: float = Field_base(ge=0, le=1)
    preference_score: float | None = Field_base(default=None, ge=0, le=1)
    compatibility_score: float | None = Field_base(default=None, ge=0, le=1)
    relation_score: float | None = Field_base(default=None, ge=0, le=1)
    base_score: float = Field_base(ge=0, le=1)
    max_selected_similarity: float = Field_base(ge=0, le=1)
    diversity_penalty: float = Field_base(ge=0, le=0.1)
    # Selection-time score; consumers must order items by rank.
    final_score: float = Field_base(ge=0, le=1)

    @model_validator_base(mode="after")
    def validate_v01_scores(self) -> Self_base:
        if (self.request_relevance_score is None) != (self.request_relevance_active is False):
            raise ValueError('Only explicitly inactive relevance may have a null score.')
        if self.compatibility_score is not None:
            raise ValueError("Compatibility score requires Relation integration.")
        return self

@_preserve_class('RankedItem', 'fashion_recommendation_v2.schemas.ranking')
class RankedItem(StrictBaseModel_base):
    visual_confirmation_assessment: VisualConfirmationAssessmentV7_base | VisualConfirmationAssessmentV5_base | None = None
    exposure_suitability: ExposureSuitability_base | None = None
    thumbnail_quality_assessment: ThumbnailQualityAssessmentV57_ranking | ThumbnailQualityAssessmentV2_base | ThumbnailQualityAssessmentV1_base | ThumbnailQualityAssessment_base | None = None
    relation_evaluation: RelationEvaluation | None = None
    preference_observations: list[PreferenceObservation] = Field_base(default_factory=list)
    preference_attribute_scores: dict[str, float] = Field_base(default_factory=dict)
    preference_evidence_refs: list[str] = Field_base(default_factory=list)
    conflicts: list[EvidenceConflict] = Field_base(default_factory=list)
    item_id: str
    diversity_features: list[DiversityFeature] = Field_base(default_factory=list)
    base_rank: int = Field_base(ge=1)
    rank: int = Field_base(ge=1)
    scores: RankingScoreBreakdown
    hard_constraint_assessments: list[HardConstraintAssessment]
    requirement_assessments: list[RequirementAssessment | RequirementAssessmentV9_base]
    ranking_reasons: list[str] = Field_base(min_length=1)
    uncertainties: list[str] = Field_base(default_factory=list)

@_preserve_class('ExcludedItem', 'fashion_recommendation_v2.schemas.ranking')
class ExcludedItem(StrictBaseModel_base):
    visual_confirmation_assessment: VisualConfirmationAssessmentV7_base | VisualConfirmationAssessmentV5_base | None = None
    request_relevance_base_score: float | None = Field_base(default=None, ge=0, le=1)
    thumbnail_quality_assessment: ThumbnailQualityAssessmentV57_ranking | ThumbnailQualityAssessmentV2_base | None = None
    exposure_suitability: ExposureSuitability_base | None = None
    conflicts: list[EvidenceConflict] = Field_base(default_factory=list)
    """Failed a hard requirement or relevance threshold, not simply outside Top K."""
    item_id: str
    reason_codes: list[Literal_base["hard_requirement_unmet", "hard_requirement_unknown", "below_minimum_relevance", "hard_requirement_conflict", "evaluation_failed", "preference_evaluation_failed", "preference_not_evaluated", "search_evaluation_failed", "search_unevaluated", "relation_evaluation_failed", "relation_unevaluated", "unrequested_childrenswear", "exposure_restricted"]] = Field_base(min_length=1)
    hard_constraint_assessments: list[HardConstraintAssessment]
    requirement_assessments: list[RequirementAssessment | RequirementAssessmentV9_base]
    request_relevance_score: float | None = Field_base(default=None, ge=0, le=1)
    evaluation_issues: list[RankingItemIssue] = Field_base(default_factory=list)

@_preserve_function('validate_metadata_only_evidence', 'fashion_recommendation_v2.schemas.ranking')
def validate_metadata_only_evidence(entries) -> None:
    """URLs are identifiers, not visual observations in a text-only evaluation."""
    for entry in entries:
        if entry.image_evidence or 'image_url' in entry.evidence_fields:
            raise ValueError('Metadata-only Ranking cannot create image evidence or use image_url as product evidence.')
RANKING_V10_POLICIES_base = RANKING_V10_POLICIES
UpstreamFailureV10_base = UpstreamFailureV10

@_preserve_class('FinalRanking', 'fashion_recommendation_v2.schemas.ranking')
class FinalRanking(StrictBaseModel_base):
    personalization_v12: dict | None = None
    personalization_v11: dict | None = None
    upstream_exclusions_v10: dict[str, UpstreamFailureV10_base] | None = None
    relation_context_v8: RelationIntent_base | None = None
    requirement_derivations_v6: dict[str, list[RequirementDerivationV6_base]] | None = None
    analysis_source: Literal_base['ranking_llm', 'ranking_metadata_llm', 'search_v2', 'search_v3', 'search_v4', 'search_v5', 'search_v6', 'search_v7', 'search_v8', 'search_v9', 'search_v10', 'search_v11', 'search_v12', 'search_v13', 'search_v14', 'search_v15', 'search_v16', 'search_v18', 'search_v19', 'search_v20', 'search_v21', 'search_v22', 'search_v23', 'search_v24', 'search_v25', 'search_v26', 'search_v29', 'search_v30', 'search_v31', 'search_v32', 'search_v33', 'search_v34', 'search_v35', 'search_v36', 'search_v37', 'search_v40', 'search_v41', 'search_v42', 'search_v43', 'search_v44', 'search_v45', 'search_v46', 'search_v47', 'search_v48', 'search_v49', 'search_v50', 'search_v51', 'search_v52', 'search_v53', 'search_v54', 'search_v55', 'search_v56', 'search_v57', 'search_v58', 'search_v59', 'search_v60', 'search_v61'] = 'ranking_llm'
    ranking_id: str
    candidate_set_id: str
    requirements_id: str
    scoring_policy_version: str
    random_seed: int = Field_base(ge=0)
    requested_count: int = Field_base(ge=1)
    returned_count: int = Field_base(ge=0)
    status: Literal_base["complete", "partial", "empty"]
    ranked_items: list[RankedItem]
    excluded_items: list[ExcludedItem] = Field_base(default_factory=list)
    shortfall_reasons: list[str] = Field_base(default_factory=list)
    warnings: list[str] = Field_base(default_factory=list)

    @model_serializer_base(mode="wrap")
    def serialize_versioned_derivations(self, handler):
        data = handler(self)
        if self.personalization_v12 is None:
            data.pop('personalization_v12', None)
        if self.personalization_v11 is None:
            data.pop('personalization_v11', None)
        if self.upstream_exclusions_v10 is None:
            data.pop('upstream_exclusions_v10', None)
        if self.requirement_derivations_v6 is None:
            data.pop('requirement_derivations_v6', None)
        if self.relation_context_v8 is None:
            data.pop('relation_context_v8', None)
        return data

    @model_validator_base(mode="after")
    @validated_once
    def validate_output(self) -> Self_base:
        if self.scoring_policy_version in {'ranking_eval_v12', 'ranking_eval_v12_relation', 'ranking_eval_v13', 'ranking_eval_v13_relation', 'ranking_eval_v14', 'ranking_eval_v14_relation', 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17', 'ranking_eval_v15_relation', 'ranking_eval_v16_relation', 'ranking_eval_v17_relation'}:
            from fashion_recommendation_v2.ranking.personalization import validate_output
            return validate_output(self)
        if self.personalization_v12 is not None:
            raise ValueError('Personalization v12 record requires v12')
        if self.scoring_policy_version in {'ranking_eval_v11', 'ranking_eval_v11_relation'}:
            from fashion_recommendation_v2.ranking.personalization import validate_output_v11 as validate_output
            return validate_output(self)
        if self.personalization_v11 is not None:
            raise ValueError('Personalization record requires v11')
        if self.scoring_policy_version in RANKING_V10_POLICIES_base:
            from fashion_recommendation_v2.ranking.partial_evaluation import validate_output
            return validate_output(self)
        if self.upstream_exclusions_v10 is not None:
            raise ValueError('Upstream exclusion accounting requires Ranking v10.')
        for row in self.ranked_items:
            if self.analysis_source not in {'search_v37', 'search_v40', 'search_v41', 'search_v42', 'search_v43', 'search_v44', 'search_v45', 'search_v46', 'search_v47', 'search_v48', 'search_v49', 'search_v50', 'search_v51', 'search_v52', 'search_v53', 'search_v54', 'search_v55', 'search_v56', 'search_v57', 'search_v58', 'search_v59', 'search_v60', 'search_v61'} and row.scores.request_relevance_active is not None:
                raise ValueError('Explicit R activation belongs only to the Search v37 handoff.')
        if self.analysis_source in {'search_v37', 'search_v40', 'search_v41', 'search_v42', 'search_v43', 'search_v44', 'search_v45', 'search_v46', 'search_v47', 'search_v48', 'search_v49', 'search_v50', 'search_v51', 'search_v52', 'search_v53', 'search_v54', 'search_v55', 'search_v56', 'search_v57', 'search_v58', 'search_v59', 'search_v60', 'search_v61'} and self.scoring_policy_version not in RANKING_V9_POLICIES_base:
            raise ValueError('Search v37 requires Ranking v9 routing support.')
        if (self.scoring_policy_version in RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | RANKING_V8_POLICIES_base) != (self.requirement_derivations_v6 is not None):
            raise ValueError('Ranking v6 alone requires separate requirement derivations.')
        for row in self.ranked_items:
            if (self.scoring_policy_version in RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base) != (row.scores.application_v8 is not None):
                raise ValueError("Ranking v8 requires its separate score application record.")
        if self.returned_count != len(self.ranked_items) or self.returned_count > self.requested_count:
            raise ValueError("returned_count must equal len(ranked_items) and not exceed requested_count.")
        expected = "complete" if self.returned_count == self.requested_count else "empty" if self.returned_count == 0 else "partial"
        if self.status != expected:
            raise ValueError("status does not match returned_count/requested_count.")
        if self.status != "complete" and (not any((reason.strip() for reason in self.shortfall_reasons))):
            raise ValueError("Incomplete rankings require shortfall_reasons.")
        ids = [item.item_id for item in [*self.ranked_items, *self.excluded_items]]
        if len(ids) != len(set(ids)):
            raise ValueError("Selected and excluded item IDs must be unique and disjoint.")
        if sorted((item.rank for item in self.ranked_items)) != list(range(1, self.returned_count + 1)):
            raise ValueError("Final ranks must be contiguous starting at 1.")
        base_ranks = [item.base_rank for item in self.ranked_items]
        if len(base_ranks) != len(set(base_ranks)):
            raise ValueError("base_rank must be unique among selected items.")
        for item in [*self.ranked_items, *self.excluded_items]:
            if self.scoring_policy_version in RANKING_V9_POLICIES_base:
                if item.visual_confirmation_assessment is not None:
                    raise ValueError('v9 must not use the old visibility multiplier.')
                for a in item.requirement_assessments:
                    if not isinstance(a, RequirementAssessmentV9_base):
                        raise ValueError('v9 requires condition-local consistency assessments.')
                if isinstance(item, RankedItem) or item.reason_codes == ["below_minimum_relevance"]:
                    expected_r = sum((max(0.0, a.match_score - a.penalty) for a in item.requirement_assessments)) / len(item.requirement_assessments) if item.requirement_assessments else 1.0
                    actual_r = item.scores.request_relevance_score if isinstance(item, RankedItem) else item.request_relevance_score
                    inactive = isinstance(item, RankedItem) and item.scores.request_relevance_active is False
                    if inactive and (item.requirement_assessments or actual_r is not None) or (not inactive and (actual_r is None or not isclose_base(actual_r, expected_r))):
                        raise ValueError('v9 R must average condition scores after deductions.')
                    if isinstance(item, RankedItem) and (item.scores.visual_confirmation_score is not None or item.scores.request_relevance_base_score is not None):
                        raise ValueError('v9 must not emit old V score fields.')
            elif self.scoring_policy_version in RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | RANKING_V8_POLICIES_base:
                assessed = isinstance(item, RankedItem) or item.reason_codes == ["below_minimum_relevance"]
                if assessed:
                    v = item.visual_confirmation_assessment
                    if v is None:
                        raise ValueError('Ranking v5 scored items require visual confirmation evidence.')
                    expected = VisualConfirmationAssessmentV7_base if self.scoring_policy_version in RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base) else VisualConfirmationAssessmentV5_base
                    if not isinstance(v, expected):
                        raise ValueError('Visual assessment must match its Ranking policy.')
                    v.validate_score()
                    scores = item.scores if isinstance(item, RankedItem) else item
                    base = scores.request_relevance_base_score
                    if base is None or scores.request_relevance_score is None or (not isclose_base(scores.request_relevance_score, base * v.score, abs_tol=1e-12)):
                        raise ValueError('Ranking v5 R must equal base relevance multiplied by V.')
                    if isinstance(item, RankedItem) and item.scores.visual_confirmation_score != v.score:
                        raise ValueError('Visual confirmation score must match its assessment.')
                elif item.visual_confirmation_assessment is not None or item.request_relevance_base_score is not None or item.thumbnail_quality_assessment is not None:
                    raise ValueError('Early exclusions must not invent relevance or thumbnail scores.')
            elif item.visual_confirmation_assessment is not None or (isinstance(item, RankedItem) and (item.scores.request_relevance_base_score is not None or item.scores.visual_confirmation_score is not None)) or (isinstance(item, ExcludedItem) and (item.request_relevance_base_score is not None or item.thumbnail_quality_assessment is not None)):
                raise ValueError('Visual confirmation scoring fields require Ranking v5.')
            if self.scoring_policy_version in RANKING_V4_POLICIES_base | RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base):
                exposure = item.exposure_suitability
                if exposure is None:
                    raise ValueError('Ranking v4 outputs require exposure suitability evidence.')
                exposure = ExposureSuitability_base.model_validate(exposure.model_dump())
                if isinstance(item, RankedItem) and exposure.status != 'allowed':
                    raise ValueError('Restricted items can never be recommended.')
                if isinstance(item, ExcludedItem) and (exposure.status == 'restricted') != (item.reason_codes == ["exposure_restricted"]):
                    raise ValueError('Restricted exposure requires the dedicated exclusion reason.')
            elif isinstance(item, ExcludedItem) and "exposure_restricted" in item.reason_codes:
                raise ValueError('Exposure exclusions require Ranking v4.')
            if self.scoring_policy_version in RANKING_V0_POLICIES_base | RANKING_V1_POLICIES_base | RANKING_V2_POLICIES_base | RANKING_V4_POLICIES_base | RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base):
                if item.hard_constraint_assessments:
                    raise ValueError('Ranking eval v0 must not repeat hard-condition checks.')
                if isinstance(item, ExcludedItem) and (not set(item.reason_codes) <= {"below_minimum_relevance", "unrequested_childrenswear"} | ({"exposure_restricted"} if self.scoring_policy_version in RANKING_V4_POLICIES_base | RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base) else set())):
                    raise ValueError('Ranking eval v0 must not exclude by hard-condition judgments.')
                if isinstance(item, RankedItem):
                    if item.thumbnail_quality_assessment is None or item.scores.thumbnail_quality_score is None:
                        raise ValueError('Ranking eval v0 requires thumbnail quality scores and observations.')
                    expected_type = ThumbnailQualityAssessmentV57_ranking if self.analysis_source in {'search_v57', 'search_v58', 'search_v59', 'search_v60', 'search_v61'} else ThumbnailQualityAssessmentV2_base if self.scoring_policy_version in RANKING_V2_POLICIES_base | RANKING_V4_POLICIES_base | RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base) else ThumbnailQualityAssessmentV1_base if self.scoring_policy_version in RANKING_V1_POLICIES_base else ThumbnailQualityAssessment_base
                    if type(item.thumbnail_quality_assessment) is not expected_type:
                        raise ValueError('Thumbnail assessment version must match the Ranking scoring policy.')
                    item.thumbnail_quality_assessment.validate_calculation()
                    if not isclose_base(item.scores.thumbnail_quality_score, item.thumbnail_quality_assessment.score, abs_tol=1e-12):
                        raise ValueError('Thumbnail quality score must match its assessment.')
            elif isinstance(item, RankedItem) and (item.thumbnail_quality_assessment is not None or item.scores.thumbnail_quality_score is not None):
                raise ValueError('Thumbnail quality scores require the Ranking eval v0 policy.')
            if self.analysis_source == 'ranking_metadata_llm':
                validate_metadata_only_evidence([*item.requirement_assessments, *item.conflicts, *(item.diversity_features if isinstance(item, RankedItem) else []), *(item.preference_observations if isinstance(item, RankedItem) else [])])
            for entries in (item.hard_constraint_assessments, item.requirement_assessments):
                refs = [assessment.requirement_id for assessment in entries]
                if len(refs) != len(set(refs)):
                    raise ValueError("Each stage may assess a requirement only once per item.")
        return self

    @validated_once
    def validate_against(self, input_data: RankingAgentInput_base) -> Self_base:
        """Resolve cross-model references; call after standalone model validation."""
        self.validate_output()
        if self.scoring_policy_version in {'ranking_eval_v12', 'ranking_eval_v12_relation', 'ranking_eval_v13', 'ranking_eval_v13_relation', 'ranking_eval_v14', 'ranking_eval_v14_relation', 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17', 'ranking_eval_v15_relation', 'ranking_eval_v16_relation', 'ranking_eval_v17_relation'}:
            from fashion_recommendation_v2.ranking.personalization import validate_against
            return validate_against(self, input_data)
        if self.scoring_policy_version in {'ranking_eval_v11', 'ranking_eval_v11_relation'}:
            from fashion_recommendation_v2.ranking.personalization import validate_against_v11 as validate_against
            return validate_against(self, input_data)
        if self.scoring_policy_version in RANKING_V10_POLICIES_base:
            from fashion_recommendation_v2.ranking.partial_evaluation import validate_against
            return validate_against(self, input_data)
        if self.scoring_policy_version in RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base:
            expected_context = input_data.ralationRatio.intent if input_data.ralationRatio else input_data.relation_intent
            if self.relation_context_v8 != expected_context:
                raise ValueError('Ranking v8 must preserve its resolved relation context.')
        elif self.relation_context_v8 is not None:
            raise ValueError('Versioned relation context requires Ranking v8.')
        source = input_data.candidate_set
        snapshot = source.resolved_requirements
        if snapshot is None:
            raise ValueError("Ranking requires a requirements snapshot.")
        if (source.search_policy_version is not None or self.analysis_source.startswith('search_')) and self.analysis_source != f'search_{source.search_policy_version}':
            raise ValueError('Ranking analysis source must match the Search policy version.')
        if self.candidate_set_id != source.candidate_set_id or self.requirements_id != snapshot.requirements_id or self.requested_count != input_data.requested_count:
            raise ValueError("Output source IDs and requested_count must match input.")
        if (self.scoring_policy_version in {'ranking_v0.5_relation', RANKING_V0_RELATION_base, RANKING_V1_RELATION_base, RANKING_V2_RELATION_base, RANKING_V4_RELATION_base, RANKING_V5_RELATION_base, RANKING_V6_RELATION_base, RANKING_V7_RELATION_base, RANKING_V8_RELATION_base, RANKING_V9_RELATION_base}) != (input_data.ralationRatio is not None):
            raise ValueError('Relation scoring policy and input must be present together.')
        if self.scoring_policy_version not in {'ranking_v0.5_relation', RANKING_V0_RELATION_base, RANKING_V1_RELATION_base, RANKING_V2_RELATION_base, RANKING_V4_RELATION_base, RANKING_V5_RELATION_base, RANKING_V6_RELATION_base, RANKING_V7_RELATION_base, RANKING_V8_RELATION_base, RANKING_V9_RELATION_base} and any((item.scores.relation_score is not None or item.relation_evaluation is not None for item in self.ranked_items)):
            raise ValueError('Relation evidence requires the Relation scoring policy.')
        if self.scoring_policy_version in RANKING_V0_POLICIES_base | RANKING_V1_POLICIES_base | RANKING_V2_POLICIES_base | RANKING_V4_POLICIES_base | RANKING_V5_POLICIES_base | RANKING_V6_POLICIES_base | RANKING_V7_POLICIES_base | (RANKING_V8_POLICIES_base | RANKING_V9_POLICIES_base):
            return validate_ranking_v0_against(self, input_data)
        candidate_ids = {candidate.item.item_id for candidate in source.candidates}
        requirements = {entry.requirement_id: entry for entry in snapshot.requirements}
        hard_ids = {key for key, entry in requirements.items() if entry.kind == "hard"}
        unified = self.scoring_policy_version in ("ranking_v0.3_unified", "ranking_v0.4_preference", 'ranking_v0.5_relation')
        code_ids = {key for key in hard_ids if isinstance(requirements[key].value, PriceConstraint)} if unified else hard_ids
        for item in [*self.ranked_items, *self.excluded_items]:
            if item.item_id not in candidate_ids:
                raise ValueError("Output item ID is absent from the input CandidateSet.")
            filters = {entry.requirement_id: entry for entry in item.hard_constraint_assessments}
            assessments = {entry.requirement_id: entry for entry in item.requirement_assessments}
            if set(filters) != code_ids:
                raise ValueError("Code filters must assess exactly the deterministic hard requirements.")
            if not set(assessments) <= requirements.keys():
                raise ValueError("Assessment references an unknown requirement_id.")
            from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear
            original_item = next((c.item for c in source.candidates if c.item.item_id == item.item_id))
            child_excluded = excluded_childrenswear(original_item, source.resolved_requirements)
            recorded_child_exclusion = isinstance(item, ExcludedItem) and "unrequested_childrenswear" in item.reason_codes
            if child_excluded != recorded_child_exclusion:
                raise ValueError("Unrequested childrenswear must be excluded with its policy reason.")
            failed_filter = child_excluded or any((entry.status != "met" for entry in filters.values()))
            if failed_filter and assessments:
                raise ValueError("Code-filtered items must not receive LLM assessments.")
            evaluation_failed = isinstance(item, ExcludedItem) and "evaluation_failed" in item.reason_codes
            if evaluation_failed:
                if failed_filter or assessments or item.request_relevance_score is not None or item.conflicts or (not item.evaluation_issues) or (item.reason_codes != ["evaluation_failed"]):
                    raise ValueError("Evaluation exclusions require issues, passed filters and no scores/assessments.")
                for issue in item.evaluation_issues:
                    if issue.item_id != item.item_id or issue.retry_count != 1 or (issue.requirement_id is not None and issue.requirement_id not in requirements):
                        raise ValueError("Evaluation issue references must match the excluded item and requirements.")
                continue
            if isinstance(item, ExcludedItem) and item.evaluation_issues:
                raise ValueError("Evaluation issues require evaluation_failed exclusion.")
            if not failed_filter and set(assessments) != requirements.keys():
                raise ValueError("Surviving items require LLM assessments for ALL original conditions.")
            original_item = next((candidate.item for candidate in source.candidates if candidate.item.item_id == item.item_id))
            if self.analysis_source.startswith('search_') and (not failed_filter):
                candidate = next((c for c in source.candidates if c.item.item_id == item.item_id))
                analysis = candidate.search_analysis
                if analysis is None:
                    raise ValueError('Search-backed Ranking requires saved Search analysis.')
                saved_entries = [*analysis.judgments, *analysis.known_attributes, *analysis.conflicts]
                saved_images = {(e.image_url, e.observation) for entry in saved_entries for e in entry.image_evidence}
                output_entries = [*item.requirement_assessments, *item.conflicts]
                if isinstance(item, RankedItem):
                    output_entries.extend([*item.diversity_features, *item.preference_observations])
                if any(((e.image_url, e.observation) not in saved_images for entry in output_entries for e in entry.image_evidence)):
                    raise ValueError('Ranking image evidence must come from the saved Search analysis.')
            if unified:
                for key in code_ids:
                    if key in assessments and assessments[key].status != filters[key].status:
                        raise ValueError("Price assessments must preserve the code judgment.")
            if isinstance(item, RankedItem):
                for feature in item.diversity_features:
                    if not set(feature.fixed_by_requirement_ids) <= hard_ids:
                        raise ValueError("Fixed diversity features must reference hard requirements.")
                    if any((e.image_url != original_item.image_url for e in feature.image_evidence)):
                        raise ValueError("Diversity evidence must reference the input item's image URL.")
            for assessment in assessments.values():
                if any((evidence.image_url != original_item.image_url for evidence in assessment.image_evidence)):
                    raise ValueError("Image evidence must reference the input item's image URL.")
            for evidence_conflict in item.conflicts:
                if evidence_conflict.requirement_id is not None and evidence_conflict.requirement_id not in requirements:
                    raise ValueError("Conflict references an unknown requirement_id.")
                if any((evidence.image_url != original_item.image_url for evidence in evidence_conflict.image_evidence)):
                    raise ValueError("Conflict image evidence must reference the input item's image URL.")
            conflict = any((assessments[key].status == "unmet" for key in hard_ids if key in assessments))
            if isinstance(item, RankedItem):
                if failed_filter or conflict:
                    raise ValueError("Selected items must pass code filters and have no hard-condition conflict.")
                if self.scoring_policy_version not in ("ranking_v0.4_preference", 'ranking_v0.5_relation') and item.scores.preference_score is not None:
                    raise ValueError('Preference scores require the preference scoring policy')
                if self.scoring_policy_version in ("ranking_v0.4_preference", 'ranking_v0.5_relation'):
                    from fashion_recommendation_v2.agents.ranking_preferences import validate_ranked_preference
                    validate_ranked_preference(item, input_data, original_item)
                if item.scores.request_relevance_score < 0.5:
                    raise ValueError("Selected items must meet the minimum request relevance of 0.50.")
            else:
                expected_reasons = set()
                if child_excluded:
                    expected_reasons.add("unrequested_childrenswear")
                if any((entry.status == "unmet" for entry in filters.values())):
                    expected_reasons.add("hard_requirement_unmet")
                if any((entry.status == "unknown" for entry in filters.values())):
                    expected_reasons.add("hard_requirement_unknown")
                if conflict:
                    expected_reasons.add("hard_requirement_conflict")
                if not failed_filter and item.request_relevance_score is not None and (item.request_relevance_score < 0.5):
                    expected_reasons.add("below_minimum_relevance")
                if set(item.reason_codes) != expected_reasons:
                    raise ValueError("Exclusion reasons must match filter/conflict/relevance evidence.")
                if failed_filter and item.request_relevance_score is not None:
                    raise ValueError("Code-filtered items must not have a relevance score.")
        return self


# ---- ranking_v11 ----

"""Public v11 input, separate from the historical v0 profile contract."""
from typing import Literal as Literal_v11
from pydantic import Field as Field_v11
from pydantic import PrivateAttr
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v11
RankingAgentInput = RankingAgentInput_base
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.relation import RelationRatio
from fashion_recommendation_v2.schemas.relation import RelationIntent
RANKING_V11 = 'ranking_eval_v11'
RANKING_V11_POLICIES = {RANKING_V11, RANKING_V11 + '_relation'}

@_preserve_class('RankingAgentInputV11', 'fashion_recommendation_v2.schemas.ranking_v11')
class RankingAgentInputV11_v11(StrictBaseModel_v11):
    candidate_set: CandidateSet
    user_request: str = Field_v11(min_length=1)
    requested_count: int = Field_v11(ge=1)
    personalization_mode: Literal_v11['cold', 'warm']
    ralationRatio: RelationRatio | None = None
    relation_intent: RelationIntent | None = None

    def legacy_input(self):
        return RankingAgentInput(**self.model_dump(exclude={'personalization_mode'}))

    @model_validator(mode='after')
    def validate_source(self):
        self.legacy_input()
        return self

@_preserve_class('ScoringInputV11', 'fashion_recommendation_v2.schemas.ranking_v11')
class ScoringInputV11(RankingAgentInput):
    """Internal validated P injection. Never accepted from HTTP or the public input."""
    _personalization: dict = PrivateAttr(default_factory=dict)


# ---- ranking_v12 ----

"""v12 public input preserves the v11 authenticated lookup contract."""
RankingAgentInputV11 = RankingAgentInputV11_v11

@_preserve_class('RankingAgentInputV12', 'fashion_recommendation_v2.schemas.ranking_v12')
class RankingAgentInputV12_v12(RankingAgentInputV11):
    """Personalized-first selection followed by permitted baseline supplements."""
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
SelectionKind = Literal['personalized', 'nonpersonalized_supplement', 'nonpersonalized']

@_preserve_class('SelectionV12', 'fashion_recommendation_v2.schemas.ranking_v12')
class SelectionV12(StrictBaseModel):
    kind: SelectionKind
    position: int = Field(ge=1)
    score_view_rank: int = Field(ge=1)
    score_view_base_rank: int = Field(ge=1)


# ---- ranking_v13 ----

"""v13 retains v12 inputs and disables personalization for similarity."""
RankingAgentInputV12 = RankingAgentInputV12_v12

@_preserve_class('RankingAgentInputV13', 'fashion_recommendation_v2.schemas.ranking_v13')
class RankingAgentInputV13(RankingAgentInputV12):
    pass
