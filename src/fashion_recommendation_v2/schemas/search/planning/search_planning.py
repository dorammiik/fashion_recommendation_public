"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- search_planning_legacy ----
"""schemas.search.planning.search_planning_legacy: definitions relocated without semantic changes."""

from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import AspectFilterValue
from pydantic import Field as Field_legacy
from typing import Literal as Literal_legacy
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysis
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_legacy
from fashion_recommendation_v2.schemas.search._model_utils import _common_schema

# ============================================================
# Internal Search Agent Output
# ============================================================


@_preserve_class('AspectFilterEntry', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class AspectFilterEntry_legacy(StrictBaseModel_legacy):
    __qualname__ = 'AspectFilterEntry'
    name: str

    # 문자열형 필터: Condition, Size 등
    string_values: list[str]

    # 가격은 통화 보존을 위해 별도 price_constraint를 사용한다.
    numeric_value: float | None


@_preserve_class('RequirementUsage', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class RequirementUsage_legacy(StrictBaseModel_legacy):
    __qualname__ = 'RequirementUsage'
    requirement_id: str
    location: Literal_legacy["query", "filter", "category"]
    evidence: str = Field_legacy(min_length=1)


@_preserve_class('RequirementUsageAssessment', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class RequirementUsageAssessment(StrictBaseModel_legacy):
    __qualname__ = 'RequirementUsageAssessment'
    usages: list[RequirementUsage_legacy]


@_preserve_class('RequirementUsageAssessmentV7', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class RequirementUsageAssessmentV7(RequirementUsageAssessment):
    __qualname__ = 'RequirementUsageAssessmentV7'
    explanation_matches_execution: bool
    hard_conditions_preserved: bool
    assessed_audience_scope: Literal_legacy['men', 'women', 'all', 'unknown']
    issues: list[str]


@_preserve_class('SearchQueryPlanLLM', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchQueryPlanLLM_legacy(StrictBaseModel_legacy):
    """
    OpenAI Structured Output 전용 Query Planning Schema.

    자유로운 dict를 사용하지 않고
    aspect filter를 명시적인 list 형태로 받는다.
    """
    __qualname__ = 'SearchQueryPlanLLM'

    query: str
    category_ids: list[str]
    aspect_filters: list[AspectFilterEntry_legacy]
    price_constraint: PriceConstraint | None = None


@_preserve_class('SearchCategoryOption', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchCategoryOption(StrictBaseModel_legacy):
    """eBay 검색 결과에서 실제 관찰한 말단 카테고리."""
    __qualname__ = 'SearchCategoryOption'

    category_id: str
    category_name: str
    example_titles: list[str] = Field_legacy(default_factory=list)
    category_path: str | None = None
    category_id_path: str | None = None
    gender_scope: Literal_legacy['men', 'women', 'all', 'unknown'] = 'unknown'
    scope_evidence: str | None = None


@_preserve_class('SearchCategorySelection', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchCategorySelection(StrictBaseModel_legacy):
    """LLM은 관찰된 카테고리 중 하나를 선택한다. 적합한 것이 없으면 None."""
    __qualname__ = 'SearchCategorySelection'

    category_id: str | None


@_preserve_class('FilterOptionSelection', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class FilterOptionSelection(StrictBaseModel_legacy):
    """LLM이 lookup 목록에서 선택한 옵션 또는 검색어로 보존할 조건."""
    __qualname__ = 'FilterOptionSelection'

    selected_options: list[str]
    # No matching option: an English query phrase such as "size L" or "new".
    query_terms: str


@_preserve_class('FilterResolutionTrace', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class FilterResolutionTrace(StrictBaseModel_legacy):
    """필터별 lookup/선택/fallback 기록. 외부 API로 전송하지 않는다."""
    __qualname__ = 'FilterResolutionTrace'

    plan_query: str
    category_ids: list[str] = Field_legacy(default_factory=list)
    filter_name: Literal_legacy["Condition", "Size"]
    requested_values: list[str]
    available_options: list[str]
    selected_options: list[str]
    query_terms: str
    lookup_limits: list[int]


@_preserve_class('StrategyRevisionLLM', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class StrategyRevisionLLM_legacy(StrictBaseModel_legacy):
    """
    OpenAI Structured Output 전용 Strategy Revision Schema.
    """
    __qualname__ = 'StrategyRevisionLLM'

    preference_evidence_refs: list[str] = Field_legacy(default_factory=list)
    issue_disposition: Literal_legacy["correct", "resolved", "not_applicable"] = "correct"
    disposition_reason: str = ""

    trigger: Literal_legacy[
        "unused_requirements",
        "gender_diversity",
        "minimum_search_attempts_not_met",
        "too_broad",
        "irrelevant_results",
        "too_few_results",
        "wrong_gender_or_category",
    ]
    action: str
    revised_query: str
    category_ids: list[str]
    aspect_filters: list[AspectFilterEntry_legacy]


@_preserve_class('SearchQueryPlan', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchQueryPlan(StrictBaseModel_legacy):
    __qualname__ = 'SearchQueryPlan'
    query: str
    price_constraint: PriceConstraint | None = None
    price_conversion: PriceConversion | None = None

    category_ids: list[str] = Field_legacy(
        default_factory=list
    )

    # 예:
    # {
    #     "Condition": ["New with tags"],
    #     "Size": ["M"],
    #     "PriceMax": 30.0
    # }
    aspect_filters: dict[
        str,
        AspectFilterValue,
    ] = Field_legacy(
        default_factory=dict
    )


    def validate_for_execution(self) -> None:
        """초안은 빈 카테고리를 허용하지만, 필터 검색 실행 시에는 필수다."""
        if (self.aspect_filters or self.price_constraint is not None) and (
            not self.category_ids
            or any(not value.strip() for value in self.category_ids)
        ):
            raise ValueError("category_ids is required for a search plan with filters.")


@_preserve_class('StrategyRevision', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class StrategyRevision(StrictBaseModel_legacy):
    # The original budget is inherited by code, never rewritten by the LLM.
    __qualname__ = 'StrategyRevision'
    price_constraint: PriceConstraint | None = None

    preference_evidence_refs: list[str] = Field_legacy(default_factory=list)
    issue_disposition: Literal_legacy["correct", "resolved", "not_applicable"] = "correct"
    disposition_reason: str = ""

    trigger: Literal_legacy[
        "unused_requirements",
        "gender_diversity",
        "minimum_search_attempts_not_met",
        "too_broad",
        "irrelevant_results",
        "too_few_results",
        "wrong_gender_or_category",
    ]

    action: str

    revised_query: str

    category_ids: list[str] = Field_legacy(
        default_factory=list
    )

    aspect_filters: dict[
        str,
        AspectFilterValue,
    ] = Field_legacy(
        default_factory=dict
    )


@_preserve_class('SearchVisualDecision', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchVisualDecision(StrictBaseModel_legacy):
    __qualname__ = 'SearchVisualDecision'
    items: list[SearchItemAnalysis]
    continue_query: bool
    issues: list[str]
    revision: StrategyRevisionLLM_legacy | None = None
    decision_reason: str


@_preserve_class('SearchVisualRevisionRepair', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchVisualRevisionRepair(StrictBaseModel_legacy):
    __qualname__ = 'SearchVisualRevisionRepair'
    revision: StrategyRevisionLLM_legacy
    decision_reason: str


@_preserve_class('SearchVisualStrategy', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchVisualStrategy(StrictBaseModel_legacy):
    __qualname__ = 'SearchVisualStrategy'
    continue_query: bool
    issues: list[str]
    revision: StrategyRevisionLLM_legacy | None = None
    decision_reason: str


@_preserve_class('SearchParallelRevision', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchParallelRevision(StrictBaseModel_legacy):
    __qualname__ = 'SearchParallelRevision'
    target_requirement_ids: list[str] = Field_legacy(default_factory=list)
    revision: StrategyRevisionLLM_legacy


@_preserve_class('SearchVisualStrategyV6', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchVisualStrategyV6(StrictBaseModel_legacy):
    __qualname__ = 'SearchVisualStrategyV6'
    continue_query: bool
    issues: list[str]
    revisions: list[SearchParallelRevision] = Field_legacy(default_factory=list, max_length=2)
    decision_reason: str


@_preserve_class('SearchRevisionIntent', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchRevisionIntent_legacy(StrictBaseModel_legacy):
    __qualname__ = 'SearchRevisionIntent'
    change_type: Literal_legacy['broaden_by_removal', 'synonym_replacement', 'new_direction']
    audience_scope: Literal_legacy['men', 'women', 'all', 'unspecified']
    changed_dimensions: list[Literal_legacy['query', 'category', 'filter']]
    expected_new_candidates_reason: str = Field_legacy(min_length=1)


@_preserve_class('SearchParallelRevisionV7', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchParallelRevisionV7_legacy(SearchParallelRevision):
    __qualname__ = 'SearchParallelRevisionV7'
    intent: SearchRevisionIntent_legacy


@_preserve_class('SearchInspectionMetricsV7', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchInspectionMetricsV7(StrictBaseModel_legacy):
    __qualname__ = 'SearchInspectionMetricsV7'
    pool_before: int
    pool_after: int
    new_candidates_added: int
    net_pool_growth: int
    removed_candidates: int
    retrieved_count: int
    fresh_evaluated_count: int
    reused_evaluation_count: int
    duplicate_unresolved_count: int
    relevance_rejection_count: int
    thumbnail_rejection_count: int
    evaluation_error_count: int
    search_attempts_used: int
    search_attempts_remaining: int


@_preserve_class('SearchVisualStrategyV7', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchVisualStrategyV7_legacy(StrictBaseModel_legacy):
    __qualname__ = 'SearchVisualStrategyV7'
    continue_query: bool
    issues: list[str]
    diagnoses: list[Literal_legacy['retrieval_shortage', 'duplicate_excess', 'relevance_rejection',
                            'thumbnail_rejection', 'evaluation_error']]
    revisions: list[SearchParallelRevisionV7_legacy] = Field_legacy(default_factory=list, max_length=2)
    decision_reason: str
    # Filled by code after generation; LLM must return null.
    code_metrics: SearchInspectionMetricsV7 | None = None


# ============================================================
# Result Inspection
# ============================================================


@_preserve_class('SearchInspection', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchInspection(StrictBaseModel_legacy):
    __qualname__ = 'SearchInspection'
    inspected_count: int = Field_legacy(ge=0)

    relevant_result_ratio: float = Field_legacy(
        ge=0,
        le=1,
    )

    relevance_quality: float = Field_legacy(
        ge=0,
        le=1,
    )

    continue_query: bool
    # Only meaningful for an attempt correcting one queued issue.
    corrected_issue_resolved: bool | None = None

    issues: list[str] = Field_legacy(
        default_factory=list
    )


# ============================================================
# Search Attempt
# ============================================================


@_preserve_class('SearchInspectionDecision', 'fashion_recommendation_v2.schemas.search.planning.search_planning_legacy')
class SearchInspectionDecision(StrictBaseModel_legacy):
    """v1: inspect and propose the next strategy in one model response."""
    __qualname__ = 'SearchInspectionDecision'

    inspection: SearchInspection
    accepted_item_ids: list[str]
    revision: StrategyRevisionLLM_legacy | None
    decision_reason: str
CommonSearchInspection = _common_schema('CommonSearchInspection', SearchInspection,
    ('inspected_count', 'relevant_result_ratio', 'relevance_quality', 'continue_query', 'issues'))
CommonStrategyRevision = _common_schema('CommonStrategyRevision', StrategyRevision,
    ('trigger', 'action', 'revised_query', 'category_ids', 'aspect_filters'))


# ---- search_planning_v21 ----
"""schemas.search.planning.search_planning_v21: definitions relocated without semantic changes."""

AspectFilterEntry = AspectFilterEntry_legacy
from pydantic import BaseModel as BaseModel_v21
from typing import Literal as Literal_v21
from pydantic import create_model as create_model_v21
from pydantic import field_validator
from typing import get_args as get_args_v21
from typing import get_origin as get_origin_v21
from functools import lru_cache as lru_cache_v21
from copy import deepcopy as deepcopy_v21

@_preserve_function('canonical_filter_name', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v21')
def canonical_filter_name(value):
    if isinstance(value, str):
        return {'condition': 'Condition', 'size': 'Size'}.get(value.strip().casefold(), value)
    return value


@_preserve_class('ModelAspectFilter', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v21')
class ModelAspectFilter(AspectFilterEntry):
    __qualname__ = 'ModelAspectFilter'
    name: Literal_v21['Condition', 'Size']

    @field_validator('name', mode='before')
    @classmethod
    def normalize_name(cls, value):
        return canonical_filter_name(value)


@_preserve_function('canonical_filter_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v21')
@lru_cache_v21(maxsize=64)
def canonical_filter_schema_v21(schema):
    """Narrow nested proposal filter entries without altering legacy schemas."""
    if schema is AspectFilterEntry:
        return ModelAspectFilter
    fields = {}
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        if get_origin_v21(annotation) is list:
            child = get_args_v21(annotation)[0]
            if isinstance(child, type) and issubclass(child, BaseModel_v21):
                replacement = canonical_filter_schema_v21(child)
                if replacement is not child:
                    fields[name] = (list[replacement], deepcopy_v21(field))
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel_v21):
            replacement = canonical_filter_schema_v21(annotation)
            if replacement is not annotation:
                fields[name] = (replacement, deepcopy_v21(field))
    return create_model_v21(schema.__name__ + 'CanonicalFilters', __base__=schema, **fields) if fields else schema


# ---- search_planning_v11 ----
"""schemas.search.planning.search_planning_v11: definitions relocated without semantic changes."""

from pydantic import Field as Field_v11
from typing import Literal as Literal_v11
SearchRevisionIntent_v11 = SearchRevisionIntent_legacy
SearchVisualStrategyV7_v11 = SearchVisualStrategyV7_legacy
StrategyRevisionLLM_v11 = StrategyRevisionLLM_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v11
from pydantic import create_model as create_model_v11
from copy import deepcopy as deepcopy_v11
from typing import get_args as get_args_v11

@_preserve_function('strategy_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v11')
def strategy_schema_v11(context, *, recovery=False):
    unused = tuple(sorted(set(context.get('unused_requirements_after_current', []))
                          - set(context.get('assigned_target_requirement_ids', []))))
    triggers = ('unused_requirements',) if unused else tuple(
        t for t in get_args_v11(StrategyRevisionLLM_v11.model_fields['trigger'].annotation)
        if t != 'unused_requirements')
    revision = create_model_v11('SearchRevisionV11', __base__=StrategyRevisionLLM_v11,
                            trigger=(Literal_v11[triggers], ...))
    fields = {'revision': (revision, ...), 'intent': (SearchRevisionIntent_v11, ...)}
    if unused:
        fields['target_requirement_ids'] = (list[Literal_v11[unused]], Field_v11(min_length=1))
    branch = create_model_v11('SearchParallelRevisionV11', __base__=StrictBaseModel_v11, **fields)
    if recovery:
        return branch
    fields = {key: (field.annotation, deepcopy_v11(field))
              for key, field in SearchVisualStrategyV7_v11.model_fields.items()}
    fields['revisions'] = (list[branch], Field_v11(default_factory=list, max_length=2))
    fields['code_metrics'] = (type(None), None)
    return create_model_v11('SearchVisualStrategyV11', __base__=StrictBaseModel_v11, **fields)


# ---- search_planning_v16 ----
"""schemas.search.planning.search_planning_v16: definitions relocated without semantic changes."""

from pydantic import Field as Field_v16
from typing import Literal as Literal_v16
SearchParallelRevisionV7 = SearchParallelRevisionV7_legacy
SearchQueryPlanLLM = SearchQueryPlanLLM_legacy
SearchVisualStrategyV7 = SearchVisualStrategyV7_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v16
from typing import Union as Union_v16
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields
from pydantic import create_model as create_model_v16

@_preserve_class('SearchInitialPlansV16', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v16')
class SearchInitialPlansV16_v16(StrictBaseModel_v16):
    __qualname__ = 'SearchInitialPlansV16'
    plans: list[SearchQueryPlanLLM] = Field_v16(min_length=1, max_length=2)


@_preserve_function('plan_review_schema_v16', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v16')
def plan_review_schema_v16_v16(requirements, *, has_revision_intent, version='v16'):
    from fashion_recommendation_v2.schemas.search.planning.search_planning import plan_review_schema
    from fashion_recommendation_v2.schemas.search.planning.search_planning import IntentViolation
    from fashion_recommendation_v2.schemas.search.planning.search_planning import HardViolation
    from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids
    base = plan_review_schema(requirements)
    fields = {} if has_revision_intent else {
        'intent_violations': (list[IntentViolation], Field_v16(max_length=0))}
    hard_ids = tuple(r.requirement_id for r in requirements.requirements if r.kind == 'hard')
    core_ids = tuple(sorted(required_retrieval_ids(requirements, version)))
    if hard_ids:
        contradiction = create_model_v16('HardContradictionV16', __base__=HardViolation,
            requirement_id=(Literal_v16[hard_ids], ...), violation_type=(Literal_v16['contradiction'], ...))
        allowed = contradiction
        if core_ids:
            missing = create_model_v16('MissingCoreRetrievalV16', __base__=HardViolation,
                requirement_id=(Literal_v16[core_ids], ...), violation_type=(Literal_v16['missing'], ...))
            allowed = Union_v16[missing, contradiction]
        fields['hard_violations'] = (list[allowed], ...)
    return create_model_v16('RequirementUsageAssessmentV16', __base__=base, **fields)


@_preserve_function('strategy_schema_v16', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v16')
def strategy_schema_v16_v16(context, *, recovery=False):
    revision_fields = copy_fields(SearchParallelRevisionV7.model_fields['revision'].annotation,
        exclude={'issue_disposition', 'preference_evidence_refs'})
    intent_fields = copy_fields(SearchParallelRevisionV7.model_fields['intent'].annotation, exclude={'changed_dimensions'})
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.planning_rules import strategy_trigger_contract
        choices = strategy_trigger_contract(context)
        if not choices:
            if recovery:
                raise ValueError('No diagnosis-supported strategy trigger remains for recovery.')
            return create_model_v16('SearchVisualStrategyV16', __base__=StrictBaseModel_v16,
                **copy_fields(SearchVisualStrategyV7, exclude={'continue_query', 'revisions', 'code_metrics'}),
                continue_query=(Literal_v16[False], ...), revisions=(list[type(None)], Field_v16(max_length=0)),
                code_metrics=(type(None), None))
        revision_fields['trigger'] = (Literal_v16[tuple(choices)], ...)
        intent_fields['change_type'] = (Literal_v16[tuple(sorted({v for values in choices.values() for v in values}))], ...)
    revision = create_model_v16('ExecutableRevisionV16', __base__=StrictBaseModel_v16,
        **revision_fields)
    intent = create_model_v16('SearchIntentV16', __base__=StrictBaseModel_v16,
        **intent_fields)
    branch = create_model_v16('SearchParallelRevisionV16', __base__=StrictBaseModel_v16,
        target_requirement_ids=(list[str], ...), revision=(revision, ...), intent=(intent, ...))
    if recovery:
        return branch
    fields = copy_fields(SearchVisualStrategyV7, exclude={'revisions', 'code_metrics'})
    return create_model_v16('SearchVisualStrategyV16', __base__=StrictBaseModel_v16, **fields,
        revisions=(list[branch], Field_v16(max_length=min(2, context.get('max_parallel_queries', 2)))),
        code_metrics=(type(None), None))


# ---- search_planning_v12 ----
"""schemas.search.planning.search_planning_v12: definitions relocated without semantic changes."""

from pydantic import Field as Field_v12
from typing import Literal as Literal_v12
RequirementUsage_v12 = RequirementUsage_legacy
SearchRevisionIntent = SearchRevisionIntent_legacy
StrategyRevisionLLM = StrategyRevisionLLM_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v12
from pydantic import create_model as create_model_v12
strategy_schema = strategy_schema_v11

@_preserve_class('HardViolation', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v12')
class HardViolation(StrictBaseModel_v12):
    __qualname__ = 'HardViolation'
    requirement_id: str
    violation_type: Literal_v12['missing', 'contradiction']
    location: Literal_v12['query', 'filter', 'category']
    evidence: str = Field_v12(min_length=1)
    reason: str = Field_v12(min_length=1)


@_preserve_class('IntentViolation', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v12')
class IntentViolation(StrictBaseModel_v12):
    __qualname__ = 'IntentViolation'
    violation_type: Literal_v12['audience_intent_mismatch', 'change_type_mismatch']
    location: Literal_v12['query', 'filter', 'category']
    evidence: str = Field_v12(min_length=1)
    reason: str = Field_v12(min_length=1)


@_preserve_class('PlanReviewV12', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v12')
class PlanReviewV12(StrictBaseModel_v12):
    __qualname__ = 'PlanReviewV12'
    usages: list[RequirementUsage_v12]
    hard_violations: list[HardViolation]
    intent_violations: list[IntentViolation]
    assessed_audience_scope: Literal_v12['men', 'women', 'all', 'unknown']


@_preserve_function('plan_review_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v12')
def plan_review_schema(requirements):
    ids = tuple(r.requirement_id for r in requirements.requirements if r.kind == 'hard')
    if not ids:
        return create_model_v12('RequirementUsageAssessmentV12', __base__=PlanReviewV12,
                            hard_violations=(list[HardViolation], Field_v12(max_length=0)))
    violation = create_model_v12('HardViolationV12', __base__=HardViolation,
                             requirement_id=(Literal_v12[ids], ...))
    return create_model_v12('RequirementUsageAssessmentV12', __base__=PlanReviewV12,
                        hard_violations=(list[violation], ...))


@_preserve_function('strategy_schema_v12', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v12')
def strategy_schema_v12_v12(context, *, recovery=False):
    base = strategy_schema(context, recovery=recovery)
    branch = base if recovery else base.model_fields['revisions'].annotation.__args__[0]
    audience = context.get('code_required_audience')
    if audience:
        revision = create_model_v12('GenderRevisionV12', __base__=StrategyRevisionLLM,
                                trigger=(Literal_v12['gender_diversity'], ...))
        intent = create_model_v12('GenderIntentV12', __base__=SearchRevisionIntent,
                              audience_scope=(Literal_v12[audience], ...))
        branch = create_model_v12('GenderBranchV12', __base__=branch,
                              revision=(revision, ...), intent=(intent, ...))
    if recovery:
        return create_model_v12('SearchParallelRevisionV12', __base__=branch)
    fields = {'revisions': (list[branch], Field_v12(min_length=1 if audience else 0, max_length=2))}
    if audience:
        fields['continue_query'] = (Literal_v12[True], ...)
    return create_model_v12('SearchVisualStrategyV12', __base__=base, **fields)


# ---- search_planning_v24 ----
"""schemas.search.planning.search_planning_v24: definitions relocated without semantic changes."""

from pydantic import BaseModel as BaseModel_v24
from pydantic import Field as Field_v24
from typing import Literal as Literal_v24
RequirementUsage = RequirementUsage_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v24
from typing import Union
from pydantic import create_model as create_model_v24
from typing import get_args as get_args_v24
from typing import get_origin as get_origin_v24
from functools import lru_cache
from copy import deepcopy as deepcopy_v24

@_preserve_class('SemanticDecisionV24', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v24')
class SemanticDecisionV24(StrictBaseModel_v24):
    __qualname__ = 'SemanticDecisionV24'
    requirement_id: str
    verdict: Literal_v24['supported', 'contradicted', 'omitted', 'uncertain']
    location: Literal_v24['query', 'filter', 'category'] | None
    evidence: str | None
    reason: str = Field_v24(min_length=1)


@_preserve_class('SemanticReviewV24', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v24')
class SemanticReviewV24(StrictBaseModel_v24):
    __qualname__ = 'SemanticReviewV24'
    decisions: list[SemanticDecisionV24]
    assessed_audience_scope: Literal_v24['men', 'women', 'all', 'unknown']


@_preserve_function('evidence_proposal_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v24')
@lru_cache(maxsize=64)
def evidence_proposal_schema_v24(schema):
    """V24 only: keep operation names/model routes, add claims to query drafts."""
    from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsage_legacy as RequirementUsage
    fields = {}
    if 'query' in schema.model_fields or 'revised_query' in schema.model_fields:
        fields['requirement_usages'] = (list[RequirementUsage], ...)
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        if get_origin_v24(annotation) is list:
            child = get_args_v24(annotation)[0]
            if isinstance(child, type) and issubclass(child, BaseModel_v24):
                replacement = evidence_proposal_schema_v24(child)
                if replacement is not child:
                    fields[name] = (list[replacement], deepcopy_v24(field))
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel_v24):
            replacement = evidence_proposal_schema_v24(annotation)
            if replacement is not annotation:
                fields[name] = (replacement, deepcopy_v24(field))
    return create_model_v24(schema.__name__, __base__=schema, **fields) if fields else schema


@_preserve_function('semantic_review_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v24')
def semantic_review_schema(question_ids, category_ids=()):
    ids = tuple(question_ids)
    # Bind location and evidence together in JSON Schema, not just a Python
    # validator. A category response can only cite one selected ID, never its
    # serialized array or a category label. With no selected IDs that branch
    # does not exist at all.
    text = create_model_v24('TextSemanticDecisionV24', __base__=SemanticDecisionV24,
        requirement_id=(Literal_v24[ids], ...), location=(Literal_v24['query', 'filter'], ...),
        evidence=(str, Field_v24(min_length=1)))
    absent = create_model_v24('AbsentSemanticDecisionV24', __base__=SemanticDecisionV24,
        requirement_id=(Literal_v24[ids], ...), verdict=(Literal_v24['omitted', 'uncertain'], ...),
        location=(type(None), ...), evidence=(type(None), ...))
    variants = [text, absent]
    selected = tuple(dict.fromkeys(category_ids))
    if selected:
        variants.append(create_model_v24('CategorySemanticDecisionV24', __base__=SemanticDecisionV24,
            requirement_id=(Literal_v24[ids], ...), location=(Literal_v24['category'], ...),
            evidence=(Literal_v24[selected], ...)))
    decision = Union[tuple(variants)]
    return create_model_v24('SemanticReviewV24', __base__=SemanticReviewV24,
                        decisions=(list[decision], Field_v24(min_length=len(ids), max_length=len(ids))))

# These operations retain their original names/model routing in this release.
SearchInitialPlansV16_v24 = SearchInitialPlansV16_v16
plan_review_schema_v16 = plan_review_schema_v16_v16
strategy_schema_v16 = strategy_schema_v16_v16
canonical_filter_schema = canonical_filter_schema_v21


# ---- search_planning_v13 ----
"""schemas.search.planning.search_planning_v13: definitions relocated without semantic changes."""

from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v13
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields as copy_fields_v13
from pydantic import create_model as create_model_v13
from copy import deepcopy as deepcopy_v13
strategy_schema_v12 = strategy_schema_v12_v12

@_preserve_function('strategy_schema_v13', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v13')
def strategy_schema_v13(context, *, recovery=False):
    previous = strategy_schema_v12(context, recovery=recovery)
    old_branch = previous if recovery else previous.model_fields['revisions'].annotation.__args__[0]
    revision = create_model_v13('ExecutableRevisionV13', __base__=StrictBaseModel_v13,
        **copy_fields_v13(old_branch.model_fields['revision'].annotation,
                      exclude={'issue_disposition', 'preference_evidence_refs'}))
    intent = create_model_v13('SearchIntentV13', __base__=StrictBaseModel_v13,
        **copy_fields_v13(old_branch.model_fields['intent'].annotation, exclude={'changed_dimensions'}))
    fields = copy_fields_v13(old_branch)
    fields.update(revision=(revision, ...), intent=(intent, ...))
    branch = create_model_v13('SearchParallelRevisionV13', __base__=StrictBaseModel_v13, **fields)
    if recovery:
        return branch
    fields = copy_fields_v13(previous)
    info = deepcopy_v13(previous.model_fields['revisions'])
    fields['revisions'] = (list[branch], info)
    return create_model_v13('SearchVisualStrategyV13', __base__=StrictBaseModel_v13, **fields)


# ---- search_planning_v25 ----
"""v25 preserves proposal/review fields and operation names from v24.
The registered v25 contract selects these factories for generation and repair.
"""
BaseModel_search_planning_v25 = BaseModel_v24
Field_search_planning_v25 = Field_v24
Literal_search_planning_v25 = Literal_v24
RequirementUsage_search_planning_v25 = RequirementUsage
SearchInitialPlansV16_search_planning_v25 = SearchInitialPlansV16_v24
SemanticDecisionV24_search_planning_v25 = SemanticDecisionV24
SemanticReviewV24_search_planning_v25 = SemanticReviewV24
StrictBaseModel_search_planning_v25 = StrictBaseModel_v24
Union_search_planning_v25 = Union
annotations_search_planning_v25 = annotations
canonical_filter_schema_search_planning_v25 = canonical_filter_schema
create_model_search_planning_v25 = create_model_v24
deepcopy_search_planning_v25 = deepcopy_v24
evidence_proposal_schema_v25 = evidence_proposal_schema_v24
get_args_search_planning_v25 = get_args_v24
get_origin_search_planning_v25 = get_origin_v24
lru_cache_search_planning_v25 = lru_cache
plan_review_schema_v16_search_planning_v25 = plan_review_schema_v16
semantic_review_schema_search_planning_v25 = semantic_review_schema
strategy_schema_v16_search_planning_v25 = strategy_schema_v16  # noqa: F401,F403
_proposal_schema = evidence_proposal_schema_v24
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v25


@_preserve_function('evidence_proposal_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v25')
def evidence_proposal_schema_v25(schema):
    return preserve_response_schema_v25(_proposal_schema(schema))


# ---- search_planning_v29 ----
"""v29 keeps the typed planning contract; policy is shared with its code consumer."""
BaseModel_search_planning_v29 = BaseModel_search_planning_v25
Field_search_planning_v29 = Field_search_planning_v25
Literal_search_planning_v29 = Literal_search_planning_v25
RequirementUsage_search_planning_v29 = RequirementUsage_search_planning_v25
SearchInitialPlansV16_search_planning_v29 = SearchInitialPlansV16_search_planning_v25
SemanticDecisionV24_search_planning_v29 = SemanticDecisionV24_search_planning_v25
SemanticReviewV24_search_planning_v29 = SemanticReviewV24_search_planning_v25
StrictBaseModel_search_planning_v29 = StrictBaseModel_search_planning_v25
Union_search_planning_v29 = Union_search_planning_v25
annotations_search_planning_v29 = annotations_search_planning_v25
canonical_filter_schema_search_planning_v29 = canonical_filter_schema_search_planning_v25
create_model_search_planning_v29 = create_model_search_planning_v25
deepcopy_search_planning_v29 = deepcopy_search_planning_v25
evidence_proposal_schema_search_planning_v29 = evidence_proposal_schema_v25
get_args_search_planning_v29 = get_args_search_planning_v25
get_origin_search_planning_v29 = get_origin_search_planning_v25
lru_cache_search_planning_v29 = lru_cache_search_planning_v25
plan_review_schema_v16_search_planning_v29 = plan_review_schema_v16_search_planning_v25
preserve_response_schema_search_planning_v29 = preserve_response_schema_v25
semantic_review_schema_search_planning_v29 = semantic_review_schema_search_planning_v25
strategy_schema_v16_search_planning_v29 = strategy_schema_v16_search_planning_v25  # noqa: F401,F403


# ---- search_planning_v31 ----
"""v31 uses the existing planning response; warnings are inspection input only."""
from typing import Literal as Literal_v31
from pydantic import Field as Field_v31
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v31
BaseModel_search_planning_v31 = BaseModel_search_planning_v29
Field_v31 = Field_search_planning_v29
Literal_v31 = Literal_search_planning_v29
RequirementUsage_search_planning_v31 = RequirementUsage_search_planning_v29
SearchInitialPlansV16_search_planning_v31 = SearchInitialPlansV16_search_planning_v29
SemanticDecisionV24_search_planning_v31 = SemanticDecisionV24_search_planning_v29
SemanticReviewV24_search_planning_v31 = SemanticReviewV24_search_planning_v29
StrictBaseModel_v31 = StrictBaseModel_search_planning_v29
Union_search_planning_v31 = Union_search_planning_v29
annotations_search_planning_v31 = annotations_search_planning_v29
canonical_filter_schema_search_planning_v31 = canonical_filter_schema_search_planning_v29
create_model_search_planning_v31 = create_model_search_planning_v29
deepcopy_search_planning_v31 = deepcopy_search_planning_v29
evidence_proposal_schema_search_planning_v31 = evidence_proposal_schema_search_planning_v29
get_args_search_planning_v31 = get_args_search_planning_v29
get_origin_search_planning_v31 = get_origin_search_planning_v29
lru_cache_search_planning_v31 = lru_cache_search_planning_v29
plan_review_schema_v16_search_planning_v31 = plan_review_schema_v16_search_planning_v29
preserve_response_schema_search_planning_v31 = preserve_response_schema_search_planning_v29
semantic_review_schema_search_planning_v31 = semantic_review_schema_search_planning_v29
strategy_schema_v16_search_planning_v31 = strategy_schema_v16_search_planning_v29  # noqa: F401,F403


@_preserve_class('SemanticWarningV31', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v31')
class SemanticWarningV31(StrictBaseModel_v31):
    __qualname__ = 'SemanticWarningV31'
    warning_id: str
    rule: Literal_v31['attribute_meaning', 'source_meaning', 'query_conditions',
                  'additional_condition_count', 'item_soft_query']
    stage: str
    message: str
    evidence: dict
    attempt_ids: list[str]
    occurrences: int = Field_v31(ge=1)


# ---- search_planning_v32 ----
"""v32 keeps planning transport/budgets; verified similarity hints are code inputs."""
BaseModel_search_planning_v32 = BaseModel_search_planning_v31
Field_search_planning_v32 = Field_v31
Literal_search_planning_v32 = Literal_v31
RequirementUsage_search_planning_v32 = RequirementUsage_search_planning_v31
SearchInitialPlansV16_search_planning_v32 = SearchInitialPlansV16_search_planning_v31
SemanticDecisionV24_search_planning_v32 = SemanticDecisionV24_search_planning_v31
SemanticReviewV24_search_planning_v32 = SemanticReviewV24_search_planning_v31
SemanticWarningV31_search_planning_v32 = SemanticWarningV31
StrictBaseModel_search_planning_v32 = StrictBaseModel_v31
Union_search_planning_v32 = Union_search_planning_v31
annotations_search_planning_v32 = annotations_search_planning_v31
canonical_filter_schema_search_planning_v32 = canonical_filter_schema_search_planning_v31
create_model_search_planning_v32 = create_model_search_planning_v31
deepcopy_search_planning_v32 = deepcopy_search_planning_v31
evidence_proposal_schema_search_planning_v32 = evidence_proposal_schema_search_planning_v31
get_args_search_planning_v32 = get_args_search_planning_v31
get_origin_search_planning_v32 = get_origin_search_planning_v31
lru_cache_search_planning_v32 = lru_cache_search_planning_v31
plan_review_schema_v16_search_planning_v32 = plan_review_schema_v16_search_planning_v31
preserve_response_schema_search_planning_v32 = preserve_response_schema_search_planning_v31
semantic_review_schema_search_planning_v32 = semantic_review_schema_search_planning_v31
strategy_schema_v16_search_planning_v32 = strategy_schema_v16_search_planning_v31  # noqa: F401,F403


# ---- search_planning_v47 ----
"""v47 query proposals explain omitted searchable Stylist conditions."""
from copy import deepcopy as deepcopy_v47
from typing import get_args as get_args_v47
from typing import get_origin as get_origin_v47
from pydantic import BaseModel as BaseModel_v47
from pydantic import Field
from pydantic import create_model as create_model_v47
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v47
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v47
BaseModel_v47 = BaseModel_search_planning_v32
Field = Field_search_planning_v32
Literal_search_planning_v47 = Literal_search_planning_v32
RequirementUsage_search_planning_v47 = RequirementUsage_search_planning_v32
SearchInitialPlansV16_search_planning_v47 = SearchInitialPlansV16_search_planning_v32
SemanticDecisionV24_search_planning_v47 = SemanticDecisionV24_search_planning_v32
SemanticReviewV24_search_planning_v47 = SemanticReviewV24_search_planning_v32
SemanticWarningV31_search_planning_v47 = SemanticWarningV31_search_planning_v32
StrictBaseModel_v47 = StrictBaseModel_search_planning_v32
Union_search_planning_v47 = Union_search_planning_v32
annotations_search_planning_v47 = annotations_search_planning_v32
canonical_filter_schema_search_planning_v47 = canonical_filter_schema_search_planning_v32
create_model_v47 = create_model_search_planning_v32
deepcopy_v47 = deepcopy_search_planning_v32
evidence_proposal_schema_v47 = evidence_proposal_schema_search_planning_v32
get_args_v47 = get_args_search_planning_v32
get_origin_v47 = get_origin_search_planning_v32
lru_cache_search_planning_v47 = lru_cache_search_planning_v32
plan_review_schema_v16_search_planning_v47 = plan_review_schema_v16_search_planning_v32
preserve_response_schema_v47 = preserve_response_schema_search_planning_v32
semantic_review_schema_search_planning_v47 = semantic_review_schema_search_planning_v32
strategy_schema_v16_search_planning_v47 = strategy_schema_v16_search_planning_v32  # noqa: F401,F403
previous_schema = evidence_proposal_schema_search_planning_v32


@_preserve_class('StylistOmissionV47', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v47')
class StylistOmissionV47(StrictBaseModel_v47):
    __qualname__ = 'StylistOmissionV47'
    requirement_id: str
    reason: str = Field(min_length=1, pattern=r'\S', description='Why this usable Stylist condition was not represented, e.g. query budget or another direction.')


@_preserve_function('_with_omissions', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v47')
def _with_omissions(schema):
    fields = {}
    if 'query' in schema.model_fields or 'revised_query' in schema.model_fields:
        fields['stylist_omissions'] = (list[StylistOmissionV47], ...)
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        if get_origin_v47(annotation) is list:
            child = get_args_v47(annotation)[0]
            if isinstance(child, type) and issubclass(child, BaseModel_v47):
                replacement = _with_omissions(child)
                if replacement is not child:
                    fields[name] = (list[replacement], deepcopy_v47(field))
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel_v47):
            replacement = _with_omissions(annotation)
            if replacement is not annotation:
                fields[name] = (replacement, deepcopy_v47(field))
    return create_model_v47(schema.__name__, __base__=schema, **fields) if fields else schema


@_preserve_function('evidence_proposal_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v47')
def evidence_proposal_schema_v47(schema):
    return preserve_response_schema_v47(_with_omissions(previous_schema(schema)))


# ---- search_planning_v49 ----
"""v49 shares execution schemas; omission accounting is non-blocking metadata."""
from copy import deepcopy
from typing import get_args
from typing import get_origin
from pydantic import BaseModel
from pydantic import create_model
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v49
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema
BaseModel = BaseModel_v47
Field_search_planning_v49 = Field
Literal_search_planning_v49 = Literal_search_planning_v47
RequirementUsage_search_planning_v49 = RequirementUsage_search_planning_v47
SearchInitialPlansV16_search_planning_v49 = SearchInitialPlansV16_search_planning_v47
SemanticDecisionV24_search_planning_v49 = SemanticDecisionV24_search_planning_v47
SemanticReviewV24_search_planning_v49 = SemanticReviewV24_search_planning_v47
SemanticWarningV31_search_planning_v49 = SemanticWarningV31_search_planning_v47
StrictBaseModel_v49 = StrictBaseModel_v47
StylistOmissionV47_search_planning_v49 = StylistOmissionV47
Union_search_planning_v49 = Union_search_planning_v47
annotations_search_planning_v49 = annotations_search_planning_v47
canonical_filter_schema_search_planning_v49 = canonical_filter_schema_search_planning_v47
create_model = create_model_v47
deepcopy = deepcopy_v47
evidence_proposal_schema_v49 = evidence_proposal_schema_v47
get_args = get_args_v47
get_origin = get_origin_v47
lru_cache_search_planning_v49 = lru_cache_search_planning_v47
plan_review_schema_v16_search_planning_v49 = plan_review_schema_v16_search_planning_v47
preserve_response_schema = preserve_response_schema_v47
previous_schema_search_planning_v49 = previous_schema
semantic_review_schema_search_planning_v49 = semantic_review_schema_search_planning_v47
strategy_schema_v16_search_planning_v49 = strategy_schema_v16_search_planning_v47  # noqa: F401,F403
base_schema = evidence_proposal_schema_search_planning_v32


@_preserve_class('StylistOmissionV49', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v49')
class StylistOmissionV49(StrictBaseModel_v49):
    __qualname__ = 'StylistOmissionV49'
    requirement_id: str
    reason: str | None = None


@_preserve_function('_with_accounting', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v49')
def _with_accounting(schema):
    fields = {}
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        child = get_args(annotation)[0] if get_origin(annotation) is list else annotation
        if isinstance(child, type) and issubclass(child, BaseModel):
            updated = _with_accounting(child)
            if updated is not child:
                fields[name] = (list[updated] if get_origin(annotation) is list else updated, deepcopy(field))
    if 'query' in schema.model_fields or 'revised_query' in schema.model_fields:
        fields['stylist_omissions'] = (list[StylistOmissionV49], [])
    return create_model(schema.__name__, __base__=schema, **fields) if fields else schema


@_preserve_function('evidence_proposal_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v49')
def evidence_proposal_schema_v49(schema):
    return preserve_response_schema(_with_accounting(base_schema(schema)))


@_preserve_class('PlanFeedbackV49', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v49')
class PlanFeedbackV49(StrictBaseModel_v49):
    __qualname__ = 'PlanFeedbackV49'
    code: str
    plan_id: str
    field: str
    requirement_ids: list[str]
    rule: str
    actual: dict
    expected: dict
    instruction: str
    preserve: list[str]


# ---- search_planning_v50 ----
"""v50 adds one initial-plan exception reason; execution contracts remain shared."""
BaseModel_search_planning_v50 = BaseModel
Field_search_planning_v50 = Field_search_planning_v49
Literal = Literal_search_planning_v49
PlanFeedbackV49_search_planning_v50 = PlanFeedbackV49
RequirementUsage_search_planning_v50 = RequirementUsage_search_planning_v49
SearchInitialPlansV16 = SearchInitialPlansV16_search_planning_v49
SemanticDecisionV24_search_planning_v50 = SemanticDecisionV24_search_planning_v49
SemanticReviewV24_search_planning_v50 = SemanticReviewV24_search_planning_v49
SemanticWarningV31_search_planning_v50 = SemanticWarningV31_search_planning_v49
StrictBaseModel = StrictBaseModel_v49
StylistOmissionV47_search_planning_v50 = StylistOmissionV47_search_planning_v49
StylistOmissionV49_search_planning_v50 = StylistOmissionV49
Union_search_planning_v50 = Union_search_planning_v49
annotations_search_planning_v50 = annotations_search_planning_v49
base_schema_search_planning_v50 = base_schema
canonical_filter_schema_search_planning_v50 = canonical_filter_schema_search_planning_v49
create_model_search_planning_v50 = create_model
deepcopy_search_planning_v50 = deepcopy
evidence_proposal_schema = evidence_proposal_schema_v49
get_args_search_planning_v50 = get_args
get_origin_search_planning_v50 = get_origin
lru_cache_search_planning_v50 = lru_cache_search_planning_v49
plan_review_schema_v16_search_planning_v50 = plan_review_schema_v16_search_planning_v49
preserve_response_schema_search_planning_v50 = preserve_response_schema
previous_schema_search_planning_v50 = previous_schema_search_planning_v49
semantic_review_schema_search_planning_v50 = semantic_review_schema_search_planning_v49
strategy_schema_v16_search_planning_v50 = strategy_schema_v16_search_planning_v49  # noqa: F401,F403
PreviousInitialPlans = SearchInitialPlansV16_search_planning_v49
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from typing import Literal


@_preserve_class('SearchInitialPlansV16', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v50')
class SearchInitialPlansV16(PreviousInitialPlans):
    __qualname__ = 'SearchInitialPlansV16'
    stylist_nonuse_reason: str | None = None


@_preserve_class('ConditionPriorityV50', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v50')
class ConditionPriorityV50(StrictBaseModel):
    __qualname__ = 'ConditionPriorityV50'
    requirement_id: str
    preference_interpretation_id: str | None = None
    importance: Literal['high', 'medium', 'low'] | None = None
    confidence: Literal['high', 'medium', 'low'] | None = None


@_preserve_function('evidence_proposal_schema', 'fashion_recommendation_v2.schemas.search.planning.search_planning_v50')
def evidence_proposal_schema(schema):
    """Single initial-branch correction can report the same nonuse exception."""
    from fashion_recommendation_v2.schemas.search.planning.search_planning import evidence_proposal_schema_v49 as previous
    from pydantic import create_model
    from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema
    result = previous(schema)
    if 'query' in result.model_fields:
        result = create_model(result.__name__, __base__=result, stylist_nonuse_reason=(str | None, None))
    return preserve_response_schema(result)


# ---- search_planning_v51 ----
"""v51 retains the complete v50 planning wire and correction contracts.

Keyword composition is a semantic instruction, not a new field or a lexical
blacklist. Generation and repair reuse proposal schemas; review keeps its own
verdict schema. No response is rewritten to satisfy the instruction.
"""
BaseModel_search_planning_v51 = BaseModel_search_planning_v50
ConditionPriorityV50_search_planning_v51 = ConditionPriorityV50
Field_search_planning_v51 = Field_search_planning_v50
Literal_search_planning_v51 = Literal
PlanFeedbackV49_search_planning_v51 = PlanFeedbackV49_search_planning_v50
PreviousInitialPlans_search_planning_v51 = PreviousInitialPlans
RequirementUsage_search_planning_v51 = RequirementUsage_search_planning_v50
SearchInitialPlansV16_search_planning_v51 = SearchInitialPlansV16
SemanticDecisionV24_search_planning_v51 = SemanticDecisionV24_search_planning_v50
SemanticReviewV24_search_planning_v51 = SemanticReviewV24_search_planning_v50
SemanticWarningV31_search_planning_v51 = SemanticWarningV31_search_planning_v50
StrictBaseModel_search_planning_v51 = StrictBaseModel
StylistOmissionV47_search_planning_v51 = StylistOmissionV47_search_planning_v50
StylistOmissionV49_search_planning_v51 = StylistOmissionV49_search_planning_v50
Union_search_planning_v51 = Union_search_planning_v50
annotations_search_planning_v51 = annotations_search_planning_v50
base_schema_search_planning_v51 = base_schema_search_planning_v50
canonical_filter_schema_search_planning_v51 = canonical_filter_schema_search_planning_v50
create_model_search_planning_v51 = create_model_search_planning_v50
deepcopy_search_planning_v51 = deepcopy_search_planning_v50
evidence_proposal_schema_search_planning_v51 = evidence_proposal_schema
get_args_search_planning_v51 = get_args_search_planning_v50
get_origin_search_planning_v51 = get_origin_search_planning_v50
lru_cache_search_planning_v51 = lru_cache_search_planning_v50
plan_review_schema_v16_search_planning_v51 = plan_review_schema_v16_search_planning_v50
preserve_response_schema_search_planning_v51 = preserve_response_schema_search_planning_v50
previous_schema_search_planning_v51 = previous_schema_search_planning_v50
semantic_review_schema_search_planning_v51 = semantic_review_schema_search_planning_v50
strategy_schema_v16_search_planning_v51 = strategy_schema_v16_search_planning_v50  # noqa: F401,F403


# ---- search_planning_v52 ----
"""v52 preserves v51 planning wire contracts."""
BaseModel_search_planning_v52 = BaseModel_search_planning_v51
ConditionPriorityV50_search_planning_v52 = ConditionPriorityV50_search_planning_v51
Field_search_planning_v52 = Field_search_planning_v51
Literal_search_planning_v52 = Literal_search_planning_v51
PlanFeedbackV49_search_planning_v52 = PlanFeedbackV49_search_planning_v51
PreviousInitialPlans_search_planning_v52 = PreviousInitialPlans_search_planning_v51
RequirementUsage_search_planning_v52 = RequirementUsage_search_planning_v51
SearchInitialPlansV16_search_planning_v52 = SearchInitialPlansV16_search_planning_v51
SemanticDecisionV24_search_planning_v52 = SemanticDecisionV24_search_planning_v51
SemanticReviewV24_search_planning_v52 = SemanticReviewV24_search_planning_v51
SemanticWarningV31_search_planning_v52 = SemanticWarningV31_search_planning_v51
StrictBaseModel_search_planning_v52 = StrictBaseModel_search_planning_v51
StylistOmissionV47_search_planning_v52 = StylistOmissionV47_search_planning_v51
StylistOmissionV49_search_planning_v52 = StylistOmissionV49_search_planning_v51
Union_search_planning_v52 = Union_search_planning_v51
annotations_search_planning_v52 = annotations_search_planning_v51
base_schema_search_planning_v52 = base_schema_search_planning_v51
canonical_filter_schema_search_planning_v52 = canonical_filter_schema_search_planning_v51
create_model_search_planning_v52 = create_model_search_planning_v51
deepcopy_search_planning_v52 = deepcopy_search_planning_v51
evidence_proposal_schema_search_planning_v52 = evidence_proposal_schema_search_planning_v51
get_args_search_planning_v52 = get_args_search_planning_v51
get_origin_search_planning_v52 = get_origin_search_planning_v51
lru_cache_search_planning_v52 = lru_cache_search_planning_v51
plan_review_schema_v16_search_planning_v52 = plan_review_schema_v16_search_planning_v51
preserve_response_schema_search_planning_v52 = preserve_response_schema_search_planning_v51
previous_schema_search_planning_v52 = previous_schema_search_planning_v51
semantic_review_schema_search_planning_v52 = semantic_review_schema_search_planning_v51
strategy_schema_v16_search_planning_v52 = strategy_schema_v16_search_planning_v51  # noqa: F401,F403


# ---- search_planning_v54 ----
"""v54 reuses the planning wire contract; only keyword guidance changes."""
BaseModel_search_planning_v54 = BaseModel_search_planning_v52
ConditionPriorityV50_search_planning_v54 = ConditionPriorityV50_search_planning_v52
Field_search_planning_v54 = Field_search_planning_v52
Literal_search_planning_v54 = Literal_search_planning_v52
PlanFeedbackV49_search_planning_v54 = PlanFeedbackV49_search_planning_v52
PreviousInitialPlans_search_planning_v54 = PreviousInitialPlans_search_planning_v52
RequirementUsage_search_planning_v54 = RequirementUsage_search_planning_v52
SearchInitialPlansV16_search_planning_v54 = SearchInitialPlansV16_search_planning_v52
SemanticDecisionV24_search_planning_v54 = SemanticDecisionV24_search_planning_v52
SemanticReviewV24_search_planning_v54 = SemanticReviewV24_search_planning_v52
SemanticWarningV31_search_planning_v54 = SemanticWarningV31_search_planning_v52
StrictBaseModel_search_planning_v54 = StrictBaseModel_search_planning_v52
StylistOmissionV47_search_planning_v54 = StylistOmissionV47_search_planning_v52
StylistOmissionV49_search_planning_v54 = StylistOmissionV49_search_planning_v52
Union_search_planning_v54 = Union_search_planning_v52
annotations_search_planning_v54 = annotations_search_planning_v52
base_schema_search_planning_v54 = base_schema_search_planning_v52
canonical_filter_schema_search_planning_v54 = canonical_filter_schema_search_planning_v52
create_model_search_planning_v54 = create_model_search_planning_v52
deepcopy_search_planning_v54 = deepcopy_search_planning_v52
evidence_proposal_schema_search_planning_v54 = evidence_proposal_schema_search_planning_v52
get_args_search_planning_v54 = get_args_search_planning_v52
get_origin_search_planning_v54 = get_origin_search_planning_v52
lru_cache_search_planning_v54 = lru_cache_search_planning_v52
plan_review_schema_v16_search_planning_v54 = plan_review_schema_v16_search_planning_v52
preserve_response_schema_search_planning_v54 = preserve_response_schema_search_planning_v52
previous_schema_search_planning_v54 = previous_schema_search_planning_v52
semantic_review_schema_search_planning_v54 = semantic_review_schema_search_planning_v52
strategy_schema_v16_search_planning_v54 = strategy_schema_v16_search_planning_v52  # noqa: F401,F403
