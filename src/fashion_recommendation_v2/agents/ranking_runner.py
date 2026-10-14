"""Ranking orchestration: saved Search evidence → relevance/thumbnail scores → Top K."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.validation_reuse import reuse_for
from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear

from collections import Counter
from decimal import Decimal
import json
import math
import re
import unicodedata
import random
from uuid import uuid4

from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.agents.ranking_brain import RankingBrain
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationItem
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchInput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchOutput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import ItemJudgments
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.ranking import ExcludedItem
from fashion_recommendation_v2.schemas.ranking import FinalRanking
from fashion_recommendation_v2.schemas.ranking import RankedItem
from fashion_recommendation_v2.schemas.ranking import RankingAgentInput_base as RankingAgentInput
from fashion_recommendation_v2.schemas.ranking import RankingEvaluationFailure
from fashion_recommendation_v2.schemas.ranking import RankingScoreBreakdown
from fashion_recommendation_v2.schemas.ranking import RequirementAssessment
from fashion_recommendation_v2.schemas.ranking import validate_metadata_only_evidence
from fashion_recommendation_v2.schemas.product_evidence import HardConstraintAssessment
from fashion_recommendation_v2.schemas.product_evidence import RankingItemIssue
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import Candidate
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirement_legacy as ResolvedRequirement
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.ranking import RANKING_V0
from fashion_recommendation_v2.schemas.ranking import RANKING_V0_RELATION
from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessment
from fashion_recommendation_v2.schemas.ranking import RANKING_V1
from fashion_recommendation_v2.schemas.ranking import RANKING_V1_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V1_POLICIES
from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessmentV1
from fashion_recommendation_v2.schemas.ranking import RANKING_V2
from fashion_recommendation_v2.schemas.ranking import RANKING_V2_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V2_POLICIES
from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessmentV2
from fashion_recommendation_v2.schemas.ranking import RANKING_V4
from fashion_recommendation_v2.schemas.ranking import RANKING_V4_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V4_POLICIES
from fashion_recommendation_v2.schemas.ranking import require_exposure
from fashion_recommendation_v2.schemas.ranking import RANKING_V5
from fashion_recommendation_v2.schemas.ranking import RANKING_V5_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V5_POLICIES
from fashion_recommendation_v2.schemas.ranking import require_visual_confirmation
from fashion_recommendation_v2.schemas.ranking import RANKING_V6
from fashion_recommendation_v2.schemas.ranking import RANKING_V6_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V6_POLICIES
from fashion_recommendation_v2.schemas.ranking import RANKING_V7
from fashion_recommendation_v2.schemas.ranking import RANKING_V7_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V7_POLICIES
from fashion_recommendation_v2.schemas.ranking import RANKING_V9
from fashion_recommendation_v2.schemas.ranking import RANKING_V9_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V9_POLICIES
from fashion_recommendation_v2.schemas.ranking import RANKING_V8
from fashion_recommendation_v2.schemas.ranking import RANKING_V8_RELATION
from fashion_recommendation_v2.schemas.ranking import RANKING_V8_POLICIES
from fashion_recommendation_v2.tools.ranking_observations import observation_assessments
from fashion_recommendation_v2.agents.ranking_preferences import request_profile
from fashion_recommendation_v2.agents.ranking_preferences import vocabulary as preference_vocabulary
from fashion_recommendation_v2.agents.ranking_preferences import calculate
from fashion_recommendation_v2.search.product_validation import validate_observations


class RankingExecutionError(RuntimeError):
    def __init__(self, failure: RankingEvaluationFailure, attempts: list[dict]):
        self.failure = failure
        self.attempts = list(attempts)
        super().__init__(f'{failure.batch_id}: {failure.code}: {failure.message}')


from fashion_recommendation_v2.search.product_validation import InvalidEvaluation


from fashion_recommendation_v2.search.product_validation import present_field_base as present_field


SCORE_MAPPING = {
    'met': (1.0, 0.0), 'mostly_met': (0.75, 0.0), 'partial': (0.5, 0.0),
    'unknown': (0.5, 0.1), 'unmet': (0.0, 0.3),
}


def normalize(value: str) -> str:
    return ' '.join(re.sub(r"[^\w]+", ' ', unicodedata.normalize('NFKC', value).casefold()).split())


from fashion_recommendation_v2.tools.price_translate import price_gate
from fashion_recommendation_v2.tools.price_translate import filter_requirement


def search_key(attempt) -> str:
    return json.dumps([normalize(attempt.query), sorted(set(attempt.category_ids)),
        {key: sorted({normalize(value) for value in values}) if isinstance(values, list) else values
         for key, values in sorted(attempt.aspect_filters.items())}], ensure_ascii=False, sort_keys=True)


def retrieval_scores(candidate: Candidate, source: CandidateSet) -> tuple[float, float, float]:
    attempts = {attempt.attempt_id: attempt for attempt in source.search_attempts if attempt.status == 'success'}
    directions = {search_key(attempt) for attempt in attempts.values()}
    appearances = {search_key(attempts[entry.attempt_id]) for entry in candidate.sources if entry.attempt_id in attempts}
    orders = [entry.native_order for entry in candidate.sources if entry.attempt_id in attempts]
    n = 1 / math.sqrt(min(orders)) if orders else 0.0
    q, a = len(directions), len(appearances)
    f = max(0.0, min((a - 1) / (min(q, 3) - 1), 1.0)) if q > 1 else 0.0
    return n, f, 0.8 * n + 0.2 * f


DIVERSITY_GROUPS = {'product': 0.25, 'visual': 0.20, 'shape': 0.20,
                    'gender': 0.15, 'material': 0.10, 'style': 0.10}


def diversity_features(features: list[DiversityFeature]) -> dict:
    result = {group: {} for group in DIVERSITY_GROUPS}
    for feature in features:
        if feature.fixed_by_requirement_ids:
            continue
        value = feature.value
        key = feature.attribute
        if isinstance(value, StylistDetailValue):
            key = 'detail.' + normalize(value.key)
            values = value.values
        else:
            values = value if isinstance(value, list) else [value]
        result[feature.group].setdefault(key, set()).update(normalize(v) for v in values)
    return result


def pair_similarity(first: list[DiversityFeature], second: list[DiversityFeature]) -> float:
    a, b = diversity_features(first), diversity_features(second)
    weighted = total = 0.0
    for group, weight in DIVERSITY_GROUPS.items():
        comparisons = [len(a[group][key] & b[group][key]) / len(a[group][key] | b[group][key])
                       for key in sorted(a[group].keys() & b[group].keys()) if a[group][key] and b[group][key]]
        if comparisons:
            weighted += weight * sum(comparisons) / len(comparisons)
            total += weight
    return weighted / total if total else 0.50


def saved_v0_evidence(candidate: Candidate, source: CandidateSet, profile, *, policy_version=RANKING_V0, derivations=None):
    """Validate evidence references, without repeating Search's admission decisions."""
    if policy_version in RANKING_V9_POLICIES:
        from fashion_recommendation_v2.ranking.ranking_contracts import v9_scoring
        scorer = v9_scoring()
        from fashion_recommendation_v2.search.product_evaluation import diversity_features
        from fashion_recommendation_v2.agents.ranking_preferences import observations_from_search
        rows = scorer.assessments(candidate, source)
        analysis = candidate.search_analysis
        item = candidate.evaluation_item or candidate.item
        return ItemJudgments(item_id=item.item_id,
            judgments=[RequirementJudgment(**{k: getattr(a,k) for k in RequirementJudgment.model_fields}) for a in rows],
            conflicts=[], diversity_features=diversity_features(analysis, source.resolved_requirements),
            preference_features=observations_from_search(analysis,item,profile)), scorer.thumbnail(candidate,source)

    from fashion_recommendation_v2.agents.ranking_preferences import observations_from_search

    analysis = candidate.search_analysis
    if analysis is None or analysis.thumbnail_observation_v8 is None:
        raise ValueError('Ranking eval v0 requires saved Search analysis and thumbnail_observation_v8.')
    evidence_item = candidate.evaluation_item or candidate.item
    if (evidence_item.item_id != candidate.item.item_id or evidence_item.image_url != candidate.item.image_url
            or analysis.item_id != candidate.item.item_id or analysis.image_url != candidate.item.image_url):
        raise ValueError('Candidate evaluation snapshot identity mismatch.')
    assessment = (ThumbnailQualityAssessmentV2 if policy_version in RANKING_V2_POLICIES | RANKING_V4_POLICIES | RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES else
                  ThumbnailQualityAssessmentV1 if policy_version in RANKING_V1_POLICIES else ThumbnailQualityAssessment)
    confirmation = None
    if policy_version in RANKING_V7_POLICIES | RANKING_V8_POLICIES:
        confirmation, thumbnail = observation_assessments(candidate, source.resolved_requirements)
    else:
        thumbnail = assessment.from_observation(analysis.ranking_thumbnail_observation_v5
            if policy_version in RANKING_V5_POLICIES | RANKING_V6_POLICIES else analysis.thumbnail_observation_v8)
    soft_ids = {r.requirement_id for r in source.resolved_requirements.requirements if r.kind == 'soft'}
    soft_judgments = [j for j in analysis.judgments if j.requirement_id in soft_ids]
    if policy_version in RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES:
        from fashion_recommendation_v2.tools.ranking_judgments import derive_soft_judgments
        checks = (confirmation.observation.requirement_checks if confirmation.observation else []) if confirmation else None
        soft_judgments, diagnostics = derive_soft_judgments(candidate, source, visual_checks=checks)
        if derivations is not None:
            derivations[candidate.item.item_id] = diagnostics
    judgments = ItemJudgments(item_id=candidate.item.item_id,
        judgments=soft_judgments,
        conflicts=analysis.conflicts, diversity_features=analysis.known_attributes,
        preference_features=observations_from_search(analysis, evidence_item, profile))
    request = EvaluationBatchInput(user_request='Validate saved Search evidence for Ranking eval v0',
        resolved_requirements=source.resolved_requirements, price_conversion=source.price_conversion,
        preference_vocabulary=preference_vocabulary(profile),
        items=[EvaluationItem(item=evidence_item, hard_constraint_assessments=[])])
    RankingRunner._validate_batch(EvaluationBatchOutput(items=[judgments]), request,
                                  judgment_requirement_ids=soft_ids)
    if any(c.attribute == f.attribute for c in judgments.conflicts for f in judgments.diversity_features):
        raise ValueError('Unresolved conflicting attributes must be omitted from observed features.')
    if any(f.attribute in {'material', 'gender'} and not f.evidence_fields for f in judgments.diversity_features):
        raise ValueError('Material and product gender require metadata evidence.')
    return judgments, thumbnail


from fashion_recommendation_v2.search.product_validation import validate_evidence_batch


from fashion_recommendation_v2.schemas.ranking import RANKING_V10


class RankingRunner:
    POLICY_VERSION = RANKING_V6

    def __init__(self, *, llm: StructuredLLM | None = None, brain: RankingBrain | None = None, batch_size: int = 5, random_seed: int = 42,
                 policy_version: str = RANKING_V6, profile_lookup=None):
        if policy_version not in {RANKING_V0, RANKING_V1, RANKING_V2, RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9, RANKING_V10, 'ranking_eval_v11', 'ranking_eval_v12', 'ranking_eval_v13', 'ranking_eval_v14', 'ranking_v0.4_preference', 'ranking_eval_v15'}:
            raise ValueError('Unsupported Ranking policy version.')
        if batch_size < 1 or random_seed < 0:
            raise ValueError('batch_size must be positive and random_seed nonnegative.')
        if (llm is None) == (brain is None):
            raise ValueError("Provide exactly one of llm or brain.")
        self.brain = brain if brain is not None else RankingBrain(llm, policy_version=policy_version)
        self.batch_size = batch_size
        self.random_seed = random_seed
        self.POLICY_VERSION = policy_version
        self.policy_version = policy_version
        self.profile_lookup = profile_lookup
        self.evaluation_attempts: list[dict] = []
        self.item_issues: dict[str, list[RankingItemIssue]] = {}

    @property
    def llm(self):
        return self.brain.llm

    @llm.setter
    def llm(self, value):
        self.brain.llm = value

    @reuse_for('ranking')
    def run(self, input_data: RankingAgentInput) -> FinalRanking:
        self.evaluation_attempts = []
        self.item_issues = {}
        # Revalidate even when a caller mutated an already constructed Pydantic model.
        if self.POLICY_VERSION in {'ranking_eval_v12', 'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15'}:
            self.personalization_record = None
            from fashion_recommendation_v2.ranking.personalization import run
            return run(self, input_data)
        if self.POLICY_VERSION == 'ranking_eval_v11':
            self.personalization_record = None
            from fashion_recommendation_v2.ranking.personalization import run_v11 as run
            return run(self, input_data)
        from fashion_recommendation_v2.schemas.ranking import ScoringInputV11
        if isinstance(input_data, ScoringInputV11):
            original = input_data
            input_data = ScoringInputV11.model_validate(input_data.model_dump())
            input_data._personalization = original._personalization
        else:
            input_data = RankingAgentInput.model_validate(input_data.model_dump())
        if self.POLICY_VERSION == RANKING_V10:
            from fashion_recommendation_v2.ranking.partial_evaluation import run
            scorer = RankingRunner(brain=self.brain, batch_size=self.batch_size, random_seed=self.random_seed, policy_version=RANKING_V9)
            scorer.progress_callback = getattr(self, 'progress_callback', None)
            return run(input_data, scorer.run)
        profile = request_profile(input_data)
        source = input_data.candidate_set
        if (self.POLICY_VERSION == RANKING_V9) != (source.search_policy_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}):
            raise ValueError('Search v36 and Ranking v9 must be selected together; historical contracts remain separate.')
        snapshot = source.resolved_requirements
        assert snapshot is not None
        thumbnail_policy = self.POLICY_VERSION in {RANKING_V0, RANKING_V1, RANKING_V2, RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9}
        scoring_requirements = [r for r in snapshot.requirements if not thumbnail_policy or r.kind == 'soft']
        candidates = sorted(source.candidates, key=lambda candidate: candidate.item.item_id)
        if source.candidate_count != len(candidates) or len({c.item.item_id for c in candidates}) != len(candidates):
            raise ValueError('Candidate counts and unique item IDs must match.')
        if candidates and not snapshot.requirements:
            raise ValueError('Nonempty candidates require at least one resolved requirement.')
        attempt_ids = [attempt.attempt_id for attempt in source.search_attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError('Search attempt IDs must be unique.')
        successful = {attempt.attempt_id for attempt in source.search_attempts if attempt.status == 'success'}
        if any(entry.attempt_id not in successful for candidate in candidates for entry in candidate.sources):
            raise ValueError('Candidate sources must reference successful search attempts.')

        confirmations = ({c.item.item_id: (observation_assessments(c, snapshot)[0] if self.POLICY_VERSION in {RANKING_V7, RANKING_V8, RANKING_V9}
                            else require_visual_confirmation(c, snapshot)) for c in candidates}
                         if self.POLICY_VERSION in {RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8} else {})
        hard = [entry for entry in snapshot.requirements if entry.kind == 'hard']
        filters = {}
        survivors = []
        excluded = []
        for candidate in candidates:
            item = candidate.item
            exposure = require_exposure(candidate) if self.POLICY_VERSION in {RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9} else None
            if exposure is not None and exposure.status == 'restricted':
                excluded.append(ExcludedItem(item_id=item.item_id, reason_codes=['exposure_restricted'],
                    exposure_suitability=exposure, hard_constraint_assessments=[], requirement_assessments=[]))
                continue
            checks = [filter_requirement(item, requirement, source.price_conversion) for requirement in hard
                      if not thumbnail_policy and isinstance(requirement.value, PriceConstraint)]
            filters[item.item_id] = checks
            reasons = []
            if (excluded_childrenswear(item, snapshot) if self.POLICY_VERSION != RANKING_V9 else
                    not candidate.search_analysis.admission_checks.childrenswear_pass):
                reasons.append('unrequested_childrenswear')
            if any(check.status == 'unmet' for check in checks):
                reasons.append('hard_requirement_unmet')
            if any(check.status == 'unknown' for check in checks):
                reasons.append('hard_requirement_unknown')
            if reasons:
                excluded.append(ExcludedItem(item_id=item.item_id, reason_codes=reasons,
                                             exposure_suitability=exposure,
                                             hard_constraint_assessments=checks, requirement_assessments=[]))
            else:
                survivors.append(candidate)

        evaluated = {}
        derivations = {} if self.POLICY_VERSION in {RANKING_V6, RANKING_V7, RANKING_V8} else None
        thumbnail_assessments = {}
        vocabulary = []
        reuse_search = source.search_policy_version in {'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26'}
        reuse_search = reuse_search or (self.POLICY_VERSION in {RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9} and source.search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'})
        if thumbnail_policy and survivors and not reuse_search:
            raise ValueError('Ranking eval v0 requires saved Search analysis and thumbnail_observation_v8.')
        if reuse_search:
            from fashion_recommendation_v2.search.product_validation import validate_analysis
            from fashion_recommendation_v2.agents.ranking_preferences import observations_from_search
            for candidate in survivors:
                if thumbnail_policy:
                    judgments, thumbnail = saved_v0_evidence(candidate, source, profile,
                        policy_version=self.POLICY_VERSION, derivations=derivations)
                    evaluated[candidate.item.item_id] = judgments
                    thumbnail_assessments[candidate.item.item_id] = thumbnail
                    continue
                analysis = candidate.search_analysis
                if analysis is None or not analysis.passes({r.requirement_id for r in hard}):
                    raise ValueError('v2 Ranking requires a passing Search analysis for every candidate.')
                if source.search_policy_version in {'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26'} and analysis.thumbnail_observation is None and analysis.thumbnail_observation_v8 is None:
                    raise ValueError('v3 Ranking requires saved thumbnail observations.')
                evidence_item = candidate.evaluation_item or candidate.item
                if evidence_item.item_id != candidate.item.item_id or evidence_item.image_url != candidate.item.image_url:
                    raise ValueError('Candidate evaluation snapshot identity mismatch.')
                validate_analysis(analysis, evidence_item, snapshot, source.price_conversion)
                evaluated[candidate.item.item_id] = ItemJudgments(
                    item_id=candidate.item.item_id, judgments=analysis.judgments,
                    conflicts=analysis.conflicts, diversity_features=analysis.known_attributes,
                    preference_features=observations_from_search(analysis, evidence_item, profile))
        callback = getattr(self, 'progress_callback', None)
        total_batches = 0 if reuse_search else (len(survivors) + self.batch_size - 1) // self.batch_size
        if callback:
            callback(dict(stage='ranking', status='running', completed_batches=0, total_batches=total_batches))
        for start in range(0, 0 if reuse_search else len(survivors), self.batch_size):
            batch = survivors[start:start + self.batch_size]
            request = EvaluationBatchInput(
                user_request=input_data.user_request, resolved_requirements=snapshot,
                price_conversion=source.price_conversion, feature_vocabulary=list(vocabulary),
                preference_vocabulary=preference_vocabulary(profile),
                items=[EvaluationItem(item=c.item, hard_constraint_assessments=filters[c.item.item_id]) for c in batch],
            )
            output = self._evaluate_batch(request, f'batch_{start // self.batch_size + 1:03d}')
            if callback:
                callback(dict(stage='ranking', status='running',
                              completed_batches=start // self.batch_size + 1, total_batches=total_batches))
            evaluated.update({item.item_id: item for item in output.items})
            for output_item in output.items:
                for feature in output_item.diversity_features:
                    token = {'attribute': feature.attribute, 'value': feature.model_dump(mode='json')['value']}
                    if token not in vocabulary:
                        vocabulary.append(token)

        eligible = []
        for candidate in survivors:
            item_id = candidate.item.item_id
            if item_id not in evaluated:
                excluded.append(ExcludedItem(item_id=item_id, reason_codes=['evaluation_failed'],
                    hard_constraint_assessments=filters[item_id], requirement_assessments=[],
                    evaluation_issues=self.item_issues[item_id]))
                continue
            judgments = evaluated[item_id]
            by_id = {entry.requirement_id: entry for entry in judgments.judgments}
            # Legacy policies retain deterministic price judgments; v0 reuses only soft evidence.
            for requirement in snapshot.requirements:
                if not thumbnail_policy and isinstance(requirement.value, PriceConstraint):
                    price_check = filter_requirement(candidate.item, requirement, source.price_conversion)
                    by_id[requirement.requirement_id] = RequirementJudgment(**price_check.model_dump())
            assessments = []
            for requirement in ([] if self.POLICY_VERSION == RANKING_V9 else scoring_requirements):
                judgment = by_id[requirement.requirement_id]
                score, penalty = SCORE_MAPPING[judgment.status]
                assessments.append(RequirementAssessment(**judgment.model_dump(), match_score=score, penalty=penalty))
            relevance = (sum(max(0.0, entry.match_score - entry.penalty) for entry in assessments) / len(assessments)
                         if assessments else 1.0)
            if self.POLICY_VERSION == RANKING_V9:
                from fashion_recommendation_v2.ranking.ranking_contracts import v9_scoring
                assessments = v9_scoring().assessments(candidate, source)
                relevance = sum(max(0., a.match_score - a.penalty) for a in assessments) / len(assessments) if assessments else 1.
                if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and not assessments:
                    relevance = None
            base_relevance = relevance
            confirmation = confirmations.get(item_id)
            if confirmation is not None:
                relevance *= confirmation.score
            reasons = []
            if not thumbnail_policy and any(by_id[requirement.requirement_id].status == 'unmet' for requirement in hard):
                reasons.append('hard_requirement_conflict')
            if relevance is not None and relevance < 0.50:
                reasons.append('below_minimum_relevance')
            if reasons:
                excluded.append(ExcludedItem(item_id=item_id, reason_codes=reasons,
                    request_relevance_base_score=base_relevance if confirmation else None,
                    visual_confirmation_assessment=confirmation,
                    thumbnail_quality_assessment=thumbnail_assessments.get(item_id) if confirmation else None,
                    exposure_suitability=require_exposure(candidate) if self.POLICY_VERSION in {RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9} else None,
                    hard_constraint_assessments=filters[item_id], requirement_assessments=assessments,
                    request_relevance_score=relevance, conflicts=judgments.conflicts))
                continue
            n, f, retrieval = retrieval_scores(candidate, source)
            if isinstance(input_data, ScoringInputV11):
                from fashion_recommendation_v2.ranking.personalization import score_injection
                preference = score_injection(input_data, item_id)
            else:
                preference = calculate(profile, judgments.preference_features, judgments.conflicts)
            pref_score = preference['preference_score']
            base = None if relevance is None else .8 * relevance + .2 * retrieval if pref_score is None else .7 * relevance + .2 * pref_score + .1 * retrieval
            thumbnail = thumbnail_assessments.get(item_id)
            if thumbnail_policy and relevance is not None:
                base = (.5 * relevance + .3 * thumbnail.score + .2 * retrieval if pref_score is None else
                        .5 * relevance + .2 * pref_score + .2 * thumbnail.score + .1 * retrieval)
            if self.POLICY_VERSION in {RANKING_V2, RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9} and pref_score is None and relevance is not None:
                base = .55 * relevance + .35 * thumbnail.score + .10 * retrieval
            relation = next((e for e in input_data.ralationRatio.evaluations if e.item_id == item_id), None) if input_data.ralationRatio else None
            application = None
            if self.POLICY_VERSION in {RANKING_V8, RANKING_V9}:
                from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
                scorer = scoring_for_policy(self.POLICY_VERSION)
                if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                    base, application = scorer.routed_score(relevance, thumbnail.score, retrieval, pref_score, input_data, item_id)
                else:
                    base = scorer.base_score(relevance, thumbnail.score, retrieval, pref_score)
                    base, application = scorer.apply_relation(base, input_data, item_id)
            elif relation is not None and relation.score is not None:
                base = .75 * base + .25 * relation.score
            eligible.append(dict(application=application, confirmation=confirmation, base_relevance=base_relevance, relation=relation, preference=preference, preference_observations=judgments.preference_features, candidate=candidate, assessments=assessments, conflicts=judgments.conflicts,
                                 features=judgments.diversity_features, relevance=relevance, n=n, f=f, retrieval=retrieval,
                                 base=base, thumbnail=thumbnail))

        rng = random.Random(self.random_seed)
        tie_keys = {entry['candidate'].item.item_id: rng.random() for entry in eligible}
        eligible.sort(key=lambda entry: (-entry['base'], -(entry['relevance'] or 0.), tie_keys[entry['candidate'].item.item_id]))
        base_ranks = {entry['candidate'].item.item_id: index + 1 for index, entry in enumerate(eligible)}
        selected_items = []
        ranked = []
        # Scores are selection-time values; always consume outputs by rank.
        while eligible and len(ranked) < input_data.requested_count:
            choices = []
            for entry in eligible:
                item = entry['candidate'].item
                similarity = max((pair_similarity(entry['features'], previous)
                                  for previous in selected_items), default=0.0)
                penalty = 0.10 * similarity
                if self.POLICY_VERSION in {RANKING_V8, RANKING_V9}:
                    from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
                    if not scoring_for_policy(self.POLICY_VERSION).diversity_enabled(input_data):
                        penalty = 0.0
                final = max(0.0, entry['base'] - penalty)
                choices.append((entry, similarity, penalty, final))
            entry, similarity, penalty, final = min(choices, key=lambda choice: (
                -choice[3], -(choice[0]['relevance'] or 0.), tie_keys[choice[0]['candidate'].item.item_id]))
            item = entry['candidate'].item
            explanations = []
            uncertainties = []
            for assessment in entry['assessments']:
                detail = [*assessment.evidence, *[e.observation for e in assessment.image_evidence]]
                explanations.append(f'{assessment.requirement_id}: {assessment.status} '
                                    f'({max(0.0, assessment.match_score - assessment.penalty):.2f}) — ' + '; '.join(detail))
                if assessment.status in {'unknown', 'partial', 'mostly_met'}:
                    uncertainties.append(f'{assessment.requirement_id}: ' + '; '.join(detail))
            uncertainties.extend(conflict.explanation for conflict in entry['conflicts'])
            if item.image_url is None:
                uncertainties.append('이미지가 없어 메타데이터만으로 평가함.')
            relevance_label = '비활성' if entry['relevance'] is None else f'{entry["relevance"]:.3f}'
            explanations.append(f'요청 적합도 {relevance_label}, 검색 신호 {entry["retrieval"]:.3f}, '
                                f'다양성 감점 {penalty:.3f}.')
            if entry['thumbnail'] is not None:
                explanations.append(f"Search 관찰 기반 썸네일 퀄리티 {entry['thumbnail'].score:.3f}.")
            if entry['preference']['preference_score'] is not None:
                explanations.append(f"선호 점수 {entry['preference']['preference_score']:.3f}" + (" (LLM 적합성 등급의 코드 매핑)." if isinstance(input_data, ScoringInputV11) else " (확인되지 않은 속성은 중립)."))
            if entry['relation']:
                uncertainties.extend(entry['relation'].uncertainties)
            if entry['confirmation'] is not None:
                explanations.append(f"기존 R {entry['base_relevance']:.3f} × 시각적 확인 가능성 V {entry['confirmation'].score:.3f} = R {entry['relevance']:.3f}.")
            ranked.append(RankedItem(
                visual_confirmation_assessment=entry['confirmation'],
                exposure_suitability=require_exposure(entry["candidate"]) if self.POLICY_VERSION in {RANKING_V4, RANKING_V5, RANKING_V6, RANKING_V7, RANKING_V8, RANKING_V9} else None,
                thumbnail_quality_assessment=entry['thumbnail'],
                relation_evaluation=entry['relation'].model_dump() if entry['relation'] else None,
                preference_observations=entry['preference_observations'],
                preference_attribute_scores=entry['preference']['attribute_scores'],
                preference_evidence_refs=entry['preference']['evidence_refs'],
                item_id=item.item_id, diversity_features=entry['features'], rank=len(ranked) + 1, base_rank=base_ranks[item.item_id],
                scores=RankingScoreBreakdown(
                    request_relevance_active=(entry['relevance'] is not None) if source.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else None,
                    request_relevance_base_score=entry['base_relevance'] if entry['confirmation'] else None,
                    visual_confirmation_score=entry['confirmation'].score if entry['confirmation'] else None,
                    thumbnail_quality_score=entry['thumbnail'].score if entry['thumbnail'] else None,
                    relation_score=entry['relation'].score if entry['relation'] else None, preference_score=entry['preference']['preference_score'], request_relevance_score=entry['relevance'],
                    native_order_score=entry['n'], appearance_score=entry['f'], ebay_best_match_score=entry['retrieval'],
                    application_v8=entry['application'], base_score=entry['base'], max_selected_similarity=similarity, diversity_penalty=penalty, final_score=final),
                hard_constraint_assessments=filters[item.item_id], requirement_assessments=entry['assessments'],
                ranking_reasons=explanations, uncertainties=uncertainties, conflicts=entry['conflicts'],
            ))
            selected_items.append(entry['features'])
            eligible.remove(entry)

        count = len(ranked)
        shortfall = []
        warnings = [f"평가 응답 검증 실패로 {len(self.item_issues)}개 상품 제외."] if self.item_issues else []
        if input_data.ralationRatio:
            warnings.extend(input_data.ralationRatio.warnings)
        if count < input_data.requested_count:
            shortfall.append(f'요청 {input_data.requested_count}개 중 유효 후보 {count}개만 선정 가능.')
            if not candidates:
                shortfall.append('Search에서 반환한 후보가 없음.')
            for reason, amount in sorted(Counter(reason for item in excluded for reason in item.reason_codes).items()):
                shortfall.append(f'{reason}: {amount}개 (제외 사유 간 중복 가능).')
            # Search inspection is diagnostic only, never an item-level score.
            for attempt in source.search_attempts:
                if attempt.inspection and attempt.inspection.issues:
                    warnings.append(f'검색 참고 {attempt.attempt_id}: ' + '; '.join(attempt.inspection.issues))
        return FinalRanking(
            relation_context_v8=((input_data.ralationRatio.intent if input_data.ralationRatio else input_data.relation_intent)
                                 if self.POLICY_VERSION in {RANKING_V8, RANKING_V9} else None),
            requirement_derivations_v6=derivations,
            analysis_source=f'search_{source.search_policy_version}' if reuse_search else 'ranking_metadata_llm',
            ranking_id=f'ranking_{uuid4().hex}', candidate_set_id=source.candidate_set_id,
            requirements_id=snapshot.requirements_id,
            scoring_policy_version=(RANKING_V9_RELATION if self.POLICY_VERSION == RANKING_V9 else RANKING_V8_RELATION if self.POLICY_VERSION == RANKING_V8 else
                RANKING_V7_RELATION if self.POLICY_VERSION == RANKING_V7 else
                RANKING_V6_RELATION if self.POLICY_VERSION == RANKING_V6 else
                RANKING_V5_RELATION if self.POLICY_VERSION == RANKING_V5 else
                RANKING_V4_RELATION if self.POLICY_VERSION == RANKING_V4 else
                RANKING_V2_RELATION if self.POLICY_VERSION == RANKING_V2 else
                RANKING_V1_RELATION if self.POLICY_VERSION == RANKING_V1 else
                RANKING_V0_RELATION if thumbnail_policy else 'ranking_v0.5_relation') if input_data.ralationRatio else self.POLICY_VERSION,
            random_seed=self.random_seed, requested_count=input_data.requested_count, returned_count=count,
            status='complete' if count == input_data.requested_count else 'partial' if count else 'empty',
            ranked_items=ranked, excluded_items=excluded, shortfall_reasons=shortfall, warnings=warnings,
        ).validate_against(input_data)

    def _evaluate_batch(self, request: EvaluationBatchInput, batch_id: str) -> EvaluationBatchOutput:
        item_ids = [entry.item.item_id for entry in request.items]
        accepted = {}
        for retry in range(2):
            item_ids = [entry.item.item_id for entry in request.items]
            try:
                result = self.brain.analyze(request)
                result = EvaluationBatchOutput.model_validate(result.model_dump())
                actual_ids = [entry.item_id for entry in result.items]
                if set(actual_ids) - set(item_ids):
                    raise InvalidEvaluation('Response contains unknown item IDs.', 'missing_assessments')
                issues = []
                for entry in request.items:
                    item_id = entry.item.item_id
                    matches = [output for output in result.items if output.item_id == item_id]
                    try:
                        if len(matches) != 1:
                            raise InvalidEvaluation('Missing or duplicate item judgments.', 'missing_assessments')
                        # Search also uses _validate_batch to validate its saved visual
                        # evidence. Apply the text-only contract only to Ranking calls.
                        output = matches[0]
                        try:
                            validate_metadata_only_evidence([
                                *output.judgments, *output.diversity_features,
                                *output.conflicts, *output.preference_features,
                            ])
                        except ValueError as exc:
                            raise InvalidEvaluation(str(exc), fields=['image_evidence', 'evidence_fields']) from exc
                        self._validate_batch(EvaluationBatchOutput(items=matches),
                                             request.model_copy(update={'items': [entry]}))
                    except InvalidEvaluation as exc:
                        issues.append(RankingItemIssue(batch_id=batch_id, item_id=item_id,
                            requirement_id=exc.requirement_id, fields=exc.fields, code=exc.code,
                            message=str(exc), retry_count=retry))
                    else:
                        accepted[item_id] = matches[0]
                if issues:
                    self.evaluation_attempts.append(dict(batch_id=batch_id, item_ids=item_ids,
                        retry_count=retry, status='error', code=issues[0].code,
                        issues=[issue.model_dump() for issue in issues]))
                    if retry == 0:
                        failed_ids = {issue.item_id for issue in issues}
                        request = request.model_copy(update={
                            'items': [entry for entry in request.items if entry.item.item_id in failed_ids],
                            'validation_feedback': issues})
                        continue
                    for issue in issues:
                        self.item_issues.setdefault(issue.item_id, []).append(issue)
                    return EvaluationBatchOutput(items=list(accepted.values()))
            except Exception as exc:
                code = getattr(exc, 'code', None)
                if code not in {'missing_assessments', 'invalid_response'}:
                    code = 'invalid_response' if isinstance(exc, (ValueError, TypeError, AttributeError)) else 'api_error'
                self.evaluation_attempts.append(dict(batch_id=batch_id, item_ids=item_ids, retry_count=retry,
                    status='error', code=code, error_type=type(exc).__name__, message=str(exc)))
                if retry == 1:
                    raise RankingExecutionError(RankingEvaluationFailure(batch_id=batch_id, item_ids=item_ids,
                        code=code, message=str(exc) or type(exc).__name__, retry_count=retry), self.evaluation_attempts) from exc
            else:
                self.evaluation_attempts.append(dict(batch_id=batch_id, item_ids=item_ids, retry_count=retry, status='success'))
                return EvaluationBatchOutput(items=list(accepted.values()))
        raise AssertionError('unreachable')

    _validate_batch = staticmethod(validate_evidence_batch)
