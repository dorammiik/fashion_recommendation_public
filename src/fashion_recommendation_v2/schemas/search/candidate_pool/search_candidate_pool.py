"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- search_candidate_pool_v31 ----
"""Code-only v31 diagnostics; never part of a model response contract."""
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.search.planning.search_planning import SemanticWarningV31


@_preserve_class('SearchCodeValidationV31', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool_v31')
class SearchCodeValidationV31(StrictBaseModel):
    __qualname__ = 'SearchCodeValidationV31'
    semantic_observations: list[dict] = Field(default_factory=list)
    inspection_inputs: list[dict] = Field(default_factory=list)
    semantic_warnings: list[SemanticWarningV31] = Field(default_factory=list)
    candidate_invalidations: list[dict] = Field(default_factory=list)
    final_pool_metrics: dict[str, int] = Field(default_factory=dict)
    partial_failure: dict | None = None


# ---- search_candidate_pool ----
"""schemas.search.candidate_pool.search_candidate_pool: definitions relocated without semantic changes."""

from typing import Any
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import AspectFilterValue
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import CommonNormalizedItem
from fashion_recommendation_v2.schemas.search.planning.search_planning import CommonSearchInspection
from fashion_recommendation_v2.schemas.search.planning.search_planning import CommonStrategyRevision
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import EBayRawItem_base as EBayRawItem
from pydantic import Field as Field_base
from pydantic import field_validator
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ItemRetrievalFailure
from typing import Literal
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizedItem
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsage_legacy as RequirementUsage
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspection
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspectionDecision
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysis
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV36_v36 as SearchItemAnalysisV36
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV40_v40 as SearchItemAnalysisV40
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV41_v41 as SearchItemAnalysisV41
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV42
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV43
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV44
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV45
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemEvaluation
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualDecision
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategy
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV6
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import StrategyRevision
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.search._model_utils import _common_schema
from pydantic import model_serializer

# ============================================================
# Candidate
# ============================================================


@_preserve_class('CandidateSource', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class CandidateSource(StrictBaseModel_base):
    __qualname__ = 'CandidateSource'
    attempt_id: str
    native_order: int = Field_base(ge=1)


@_preserve_class('RetrievalSignals', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class RetrievalSignals(StrictBaseModel_base):
    __qualname__ = 'RetrievalSignals'
    best_native_order: int | None = Field_base(
        default=None,
        ge=1,
    )

    appearance_count: int = Field_base(
        default=0,
        ge=0,
    )


@_preserve_class('Candidate', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class Candidate(StrictBaseModel_base):
    # Exact evaluation-time representation for evidence revalidation after mapping.
    __qualname__ = 'Candidate'
    evaluation_item: ProductRecord | None = None
    search_analysis: SearchItemAnalysis | SearchItemAnalysisV36 | SearchItemAnalysisV40 | SearchItemAnalysisV41 | SearchItemAnalysisV42 | SearchItemAnalysisV43 | SearchItemAnalysisV44 | SearchItemAnalysisV45 | None = None
    item: ProductRecord

    sources: list[CandidateSource] = Field_base(
        min_length=1
    )

    retrieval_signals: RetrievalSignals

    @model_serializer(mode='wrap')
    def serialize_evaluation_snapshot(self, handler):
        data = handler(self)
        if self.evaluation_item is None:
            data.pop('evaluation_item', None)
        return data


@_preserve_class('SearchAttempt', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class SearchAttempt(StrictBaseModel_base):
    __qualname__ = 'SearchAttempt'
    round_id: str | None = None
    round_strategy: SearchVisualStrategyV7 | SearchVisualStrategyV6 | None = None
    # Code diagnostics and the evaluation_limited flag share integer metrics.
    # Keep the original paths and values, including already saved v50 results.
    round_summary: dict[str, int | bool | list[dict[str, Any]] | dict[str, Any]] | None = None

    @field_validator('round_summary')
    @classmethod
    def validate_round_summary(cls, summary):
        for key, value in (summary or {}).items():
            if key == 'condition_pool_v50':
                if not isinstance(value, list):
                    raise ValueError('condition_pool_v50 must be a list of condition records')
            elif key == 'condition_usage_history_v50':
                if not isinstance(value, dict):
                    raise ValueError('condition_usage_history_v50 must be an object')
            elif key == 'evaluation_limited':
                # Historical serializers stored this flag as 0/1. Preserve
                # those values, while retaining native bool in current results.
                if type(value) is not bool and not (type(value) is int and value in (0, 1)):
                    raise ValueError('evaluation_limited must be a boolean or historical 0/1 flag')
            elif type(value) is not int:
                raise ValueError(f'round_summary metric {key} must be an integer')
        return summary

    code_required_audience: Literal['men', 'women'] | None = None
    code_preferred_audience: Literal['men', 'women'] | None = None
    planned_revisions: list[StrategyRevision] | None = None
    revision_repair: dict[str, Any] | None = None
    visual_strategy: SearchVisualStrategy | None = None
    item_evaluations: list[SearchItemEvaluation] = Field_base(default_factory=list)
    evaluation_summary: dict[str, int] = Field_base(default_factory=dict)
    visual_inspection: SearchVisualDecision | None = None
    inspection_decision: SearchInspectionDecision | None = None
    item_failures: list[ItemRetrievalFailure] = Field_base(default_factory=list)
    failure_stage: Literal['search', 'item_details', 'visual_evaluation'] | None = None
    attempt_id: str
    requirement_usages: list[RequirementUsage] = Field_base(default_factory=list)
    correcting_issue_id: str | None = None
    price_conversion: PriceConversion | None = None

    query: str

    category_ids: list[str] = Field_base(
        default_factory=list
    )

    aspect_filters: dict[
        str,
        AspectFilterValue,
    ] = Field_base(
        default_factory=dict
    )

    returned_item_count: int = Field_base(ge=0)

    added_candidate_count: int = Field_base(ge=0)

    status: Literal[
        "success",
        "failed",
    ]

    inspection: SearchInspection | None = None

    revision: StrategyRevision | None = None

    error_message: str | None = None


# ============================================================
# Search Budget
# ============================================================


@_preserve_class('SearchBudget', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class SearchBudget(StrictBaseModel_base):
    __qualname__ = 'SearchBudget'
    max_attempts: int = Field_base(ge=1)

    attempts_used: int = Field_base(ge=0)

    attempts_remaining: int = Field_base(ge=0)


# ============================================================
# Candidate Pool
# ============================================================


@_preserve_class('SearchIssue', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class SearchIssue(StrictBaseModel_base):
    __qualname__ = 'SearchIssue'
    issue_id: str
    issue_type: str
    evidence: list[str]
    source_attempt_id: str
    occurrence_attempt_ids: list[str]
    original_plan: SearchQueryPlan
    requirement_usages: list[RequirementUsage]
    inspection: SearchInspection
    inspected_items: list[EBayRawItem]
    status: Literal["pending", "in_progress", "resolved", "not_applicable", "attempted"] = "pending"
    correction_attempts: int = Field_base(default=0, ge=0, le=1)
    disposition_reason: str = ""


@_preserve_class('CandidatePool', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class CandidatePool(StrictBaseModel_base):
    __qualname__ = 'CandidatePool'
    used_requirement_ids: list[str] = Field_base(default_factory=list)
    unused_requirement_ids: list[str] = Field_base(default_factory=list)
    issue_queue: list[SearchIssue] = Field_base(default_factory=list)

    # None identifies legacy payloads; SearchRunner always supplies a snapshot.
    resolved_requirements: ResolvedRequirements | None = None
    price_conversion: PriceConversion | None = None

    target_candidate_count: int = Field_base(ge=1)

    candidates: list[Candidate] = Field_base(
        default_factory=list
    )

    candidate_count: int = Field_base(ge=0)

    remaining_candidate_count: int = Field_base(ge=0)

    search_attempts: list[SearchAttempt] = Field_base(
        default_factory=list
    )

    search_budget: SearchBudget


# ============================================================
# Candidate Set
# ============================================================


@_preserve_class('SearchStrategyFailure', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class SearchStrategyFailure(StrictBaseModel_base):
    __qualname__ = 'SearchStrategyFailure'
    stage: Literal['strategy_revision'] = 'strategy_revision'
    source_attempt_id: str
    trigger: str
    error_type: str
    message: str
    retained_candidate_count: int = Field_base(ge=0)


from pydantic import model_serializer
SearchCodeValidationV31_base = SearchCodeValidationV31


@_preserve_class('CandidateSet', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
class CandidateSet(StrictBaseModel_base):
    __qualname__ = 'CandidateSet'
    code_validation_v31: SearchCodeValidationV31_base | None = None

    @model_serializer(mode='wrap')
    def serialize_release_diagnostics(self, handler):
        data = handler(self)
        if self.code_validation_v31 is None:
            data.pop('code_validation_v31', None)
        return data

    gender_diversity_exemption: Literal['explicit_user_gender', 'dress_or_skirt_product_type', 'contextual_audience'] | None = None
    search_policy_version: Literal['v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'] | None = None
    completion_status: Literal['normal_completion', 'partial_result', 'failed'] | None = None
    alternative_coverage: list[dict] = Field_base(default_factory=list)
    initial_plan_repair: dict | None = None
    gender_distribution: dict[str, float] = Field_base(default_factory=dict)
    coverage_requirements_met: bool | None = None
    strategy_failures: list[SearchStrategyFailure] = Field_base(default_factory=list)
    used_requirement_ids: list[str] = Field_base(default_factory=list)
    unused_requirement_ids: list[str] = Field_base(default_factory=list)
    issue_queue: list[SearchIssue] = Field_base(default_factory=list)

    # None identifies legacy payloads; SearchRunner always supplies a snapshot.
    resolved_requirements: ResolvedRequirements | None = None
    price_conversion: PriceConversion | None = None

    candidate_set_id: str

    target_candidate_count: int = Field_base(ge=1)

    candidate_count: int = Field_base(ge=0)

    candidates: list[Candidate] = Field_base(
        default_factory=list
    )

    search_attempts: list[SearchAttempt] = Field_base(
        default_factory=list
    )

    minimum_relevance_quality_met: bool | None = None

    stop_reason: Literal[
        "target_reached",
        "search_budget_exhausted",
        "no_viable_search_strategy",
    ]

    warnings: list[str] = Field_base(
        default_factory=list
    )
CommonCandidate = _common_schema('CommonCandidate', Candidate,
    ('item', 'sources', 'retrieval_signals'), item=(CommonNormalizedItem, ...))
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import CommonRetrievedProductV26
CommonCandidateV26 = _common_schema('CommonCandidateV26', Candidate,
    ('item', 'sources', 'retrieval_signals', 'search_analysis'), item=(CommonRetrievedProductV26, ...))
CommonSearchAttempt = _common_schema('CommonSearchAttempt', SearchAttempt,
    ('attempt_id', 'query', 'category_ids', 'aspect_filters', 'returned_item_count',
     'added_candidate_count', 'status', 'inspection', 'revision', 'error_message'),
    inspection=(CommonSearchInspection | None, None), revision=(CommonStrategyRevision | None, None))
CommonCandidateSet = _common_schema('CommonCandidateSet', CandidateSet,
    ('candidate_set_id', 'target_candidate_count', 'candidate_count', 'candidates',
     'search_attempts', 'minimum_relevance_quality_met', 'stop_reason', 'warnings'),
    candidates=(list[CommonCandidate | CommonCandidateV26], ...), search_attempts=(list[CommonSearchAttempt], ...))
CommonCandidatePool = _common_schema('CommonCandidatePool', CandidatePool,
    ('target_candidate_count', 'candidates', 'candidate_count', 'remaining_candidate_count',
     'search_attempts', 'search_budget'), candidates=(list[CommonCandidate | CommonCandidateV26], ...),
    search_attempts=(list[CommonSearchAttempt], ...))


@_preserve_function('common_candidate_payload', 'fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool')
def common_candidate_payload(value):
    """Project a complete internal result/pool onto the public common contract."""
    schema = CommonCandidateSet if isinstance(value, CandidateSet) else CommonCandidatePool
    data = value.model_dump(mode='json')
    source_separated = (data.get('search_policy_version') in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} or any(
        (c.get('search_analysis') or {}).get('evaluation_policy') in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} for c in data['candidates']))
    projected = {key: data[key] for key in schema.model_fields}
    projected['candidates'] = []
    for candidate in data['candidates']:
        integrated = candidate['item'].get('record_version') == 'search_product_v26'
        item = {k: candidate['item'][k] for k in (CommonRetrievedProductV26 if integrated else CommonNormalizedItem).model_fields}
        projected['candidates'].append({**{k: candidate[k] for k in ('sources', 'retrieval_signals')}, 'item': item,
            **({'search_analysis': candidate['search_analysis']} if integrated else {})})
    projected['search_attempts'] = []
    for attempt in data['search_attempts']:
        entry = {k: attempt[k] for k in CommonSearchAttempt.model_fields}
        if entry['inspection'] is not None:
            entry['inspection'] = {k: entry['inspection'][k] for k in CommonSearchInspection.model_fields}
        elif attempt.get('round_strategy') is not None and not source_separated:
            decision = attempt['round_strategy']
            evaluated = [e['analysis'] for e in attempt['item_evaluations'] if e.get('analysis')]
            high = sum(a['relavance_quality'] == 'high' for a in evaluated)
            # A code-derived fraction, not a newly invented LLM numeric score.
            ratio = high / len(evaluated) if evaluated else 0.0
            entry['inspection'] = dict(inspected_count=len(evaluated), relevant_result_ratio=ratio,
                relevance_quality=ratio, continue_query=decision['continue_query'], issues=decision['issues'])
        if entry['revision'] is None and len(attempt.get('planned_revisions') or []) == 1:
            entry['revision'] = attempt['planned_revisions'][0]
        if entry['revision'] is not None:
            entry['revision'] = {k: entry['revision'][k] for k in CommonStrategyRevision.model_fields}
        # A singular field cannot represent two parallel plans: retain both in trace.
        projected['search_attempts'].append(entry)
    if isinstance(value, CandidateSet) and projected['minimum_relevance_quality_met'] is None and not source_separated:
        projected['minimum_relevance_quality_met'] = value.coverage_requirements_met
    result = schema.model_validate(projected)
    if result.candidate_count != len(result.candidates):
        raise ValueError('Common candidate count differs from actual candidates.')
    ids = {a.attempt_id for a in result.search_attempts}
    if any(s.attempt_id not in ids for c in result.candidates for s in c.sources):
        raise ValueError('Common candidate source references an absent attempt.')
    if len({c.item.item_id for c in result.candidates}) != result.candidate_count:
        raise ValueError('Common candidate IDs must be unique.')
    for candidate in result.candidates:
        signals = candidate.retrieval_signals
        if signals.appearance_count != len({s.attempt_id for s in candidate.sources}):
            raise ValueError('Common appearance count differs from source attempts.')
        if signals.best_native_order != min(s.native_order for s in candidate.sources):
            raise ValueError('Common best native order differs from source ranks.')
    return result.model_dump(mode='json')
