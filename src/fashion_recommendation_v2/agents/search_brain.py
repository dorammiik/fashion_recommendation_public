"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_brain ----

from fashion_recommendation_v2.search.contracts import get_search_contracts
import json
import re
import unicodedata
from uuid import uuid4
from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.search.planning import build_query_planning_prompt
from fashion_recommendation_v2.prompts.search.planning import build_requirement_usage_prompt
from fashion_recommendation_v2.prompts.search.planning import build_category_selection_prompt
from fashion_recommendation_v2.prompts.search.planning import build_filter_option_selection_prompt
from fashion_recommendation_v2.prompts.search.planning import build_result_inspection_prompt
from fashion_recommendation_v2.prompts.search.planning import build_inspection_decision_prompt
from fashion_recommendation_v2.prompts.search.planning import build_strategy_revision_prompt
from fashion_recommendation_v2.prompts.search.requirements import build_requirements_extraction_prompt
from fashion_recommendation_v2.prompts.search.requirements import SIMILARITY_REQUIREMENT_CONTRACT
from fashion_recommendation_v2.schemas.search.planning.search_planning import AspectFilterEntry_legacy as AspectFilterEntry
from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsageAssessmentV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchParallelRevisionV7_legacy as SearchParallelRevisionV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsageAssessment
from fashion_recommendation_v2.schemas.search.planning.search_planning import FilterOptionSelection
from fashion_recommendation_v2.schemas.search.planning.search_planning import FilterResolutionTrace
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspection
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspectionDecision
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchCategorySelection
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlanLLM_legacy as SearchQueryPlanLLM
from fashion_recommendation_v2.schemas.search.planning.search_planning import StrategyRevision
from fashion_recommendation_v2.schemas.search.planning.search_planning import StrategyRevisionLLM_legacy as StrategyRevisionLLM
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtraction
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV3
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV7
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV8_legacy as RequirementsExtractionV8
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsAuditV7
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInput_legacy as SearchAgentInput
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchIssue
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchAttempt
from fashion_recommendation_v2.schemas.common import EBayRawItem
from fashion_recommendation_v2.tools.ebay_search import EBaySearchTool
from fashion_recommendation_v2.agents.stylist_runner import validate_stylist_requirements
from fashion_recommendation_v2.schemas.preference_profile import PreferenceGroup
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
from contextvars import copy_context
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchParallelRevisionV7_legacy as SearchParallelRevisionV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v11 as strategy_schema
from contextvars import ContextVar
from openai import APIConnectionError
from openai import APITimeoutError
from decimal import Decimal
from fashion_recommendation_v2.search.policy import CORE_ATTRIBUTES
from fashion_recommendation_v2.search.policy import USER_ATTRIBUTES
from fashion_recommendation_v2.search.policy import GENDER_MINIMUM_SHARE
from fashion_recommendation_v2.search.policy import MAX_QUERY_RESTRICTIONS
from fashion_recommendation_v2.search.policy import TEXT_LIMITS
from fashion_recommendation_v2.prompts.search.planning import STRATEGY_RULES
from fashion_recommendation_v2.search.policy import search_policy
from fashion_recommendation_v2.prompts.search.requirements import V8_REQUIREMENT_RULES
from fashion_recommendation_v2.prompts.search.planning import V8_PLAN_RULES
from fashion_recommendation_v2.prompts.search.planning import V9_SOFT_PLAN_RULES
from fashion_recommendation_v2.prompts.search.planning import plan_rules
from fashion_recommendation_v2.search.execution import review_image_consistency_v5
from fashion_recommendation_v2.search.execution import without_profile

@_preserve_function('exploration_input', 'fashion_recommendation_v2.agents.search_brain')
def exploration_input(source, requirements):
    result = without_profile(source)
    if source.preference_profile is None or requirements is None:
        return result
    # A user constraint takes precedence even when it was marked soft.
    excluded = {r.attribute for r in requirements.requirements if r.source == 'user'}
    excluded.update({'size', 'category_path'})
    features = [f.model_copy(deep=True) for f in source.preference_profile.global_preferences.features if f.attribute not in excluded and f.evidence_refs and (0.4 * (f.short_term.score or 0) + 0.6 * (f.long_term.score or 0) > 0)]
    if features:
        profile = source.preference_profile.model_copy(deep=True)
        profile.global_preferences = PreferenceGroup(features=features)
        profile.by_category = {}
        profile.summary = None
        result.preference_profile = profile
    return result

@_preserve_function('validate_exploration', 'fashion_recommendation_v2.agents.search_brain')
def validate_exploration(revision, source, current, filters):
    profile = source.preference_profile
    refs = set(revision.preference_evidence_refs)
    if len(refs) != len(revision.preference_evidence_refs):
        raise ValueError('Duplicate search preference citations')
    allowed_refs = {ref for feature in profile.global_preferences.features for ref in feature.evidence_refs} if profile is not None else set()
    if not refs <= allowed_refs:
        raise ValueError('Search exploration must cite only supplied positive feature evidence')
    if profile is not None:
        if revision.category_ids != current.category_ids or filters != {k: v for k, v in current.aspect_filters.items() if k not in ("PriceMin", "PriceMax")}:
            raise ValueError('Preference exploration cannot change category or mandatory filters')
from fashion_recommendation_v2.search.semantic_validation import observed

@_preserve_class('SearchBrain', 'fashion_recommendation_v2.agents.search_brain')
class SearchBrain:
    """
    전체 요구사항 추출, 검색 계획, 옵션 선택, 결과 검사, 전략 수정을 담당한다.

    검색 계획과 수정 전략은 Tool lookup + LLM 옵션 선택을 마친 뒤 반환한다.
    각 계획의 필터별 재조회는 최대 1회이며, 호환 옵션이 없으면
    해당 필터를 제거하고 조건을 검색어에 보존한다.

    상품 검색 실행, CandidatePool, 반복 횟수 관리는 SearchRunner가 담당한다.
    """

    def __init__(self, llm: StructuredLLM, *, search_tool: EBaySearchTool) -> None:
        self.llm = llm
        self.search_tool = search_tool
        self.filter_resolution_history: list[FilterResolutionTrace] = []
        self.category_evidence: list[dict] = []
        self.search_policy_version = 'v2'
        self.last_plan_review = None
        self.model_response_history = []

    # ============================================================
    # ============================================================
    # Query Planning
    def _generate(self, *, recovery=None, **kwargs):
        source = kwargs.get('user_input')
        if getattr(getattr(source, 'stylist_resolution', None), 'contract_version', None) in {'stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6', 'stylist-v7', 'stylist-v8'}:
            from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchLLMInputV49
            from fashion_recommendation_v2.stylist_personalization import search_provenance_view
            kwargs['user_input'] = SearchLLMInputV49(search_provenance_view(source.model_dump(mode='json')))
        if search_policy(getattr(self, 'search_policy_version', None)).enabled('separate_plan_review'):
            kwargs['timeout_seconds'] = text_timeout(kwargs['output_schema'].__name__, recovery)
            if self.search_policy_version in {'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                from fashion_recommendation_v2.search.policy import search_timeout_seconds
                kwargs['timeout_seconds'] = search_timeout_seconds(self.search_policy_version, kwargs['timeout_seconds'])
            if search_policy(self.search_policy_version).enabled('code_revision_fields'):
                kwargs['failure_stage'] = text_failure_stage(kwargs['output_schema'].__name__, recovery)
        from fashion_recommendation_v2.search.contracts import proposal_schemas
        original_schema, kwargs['output_schema'] = proposal_schemas(self.search_policy_version, kwargs['output_schema'])
        if self.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                self._last_received_response = None
            result = generate_with_backoff(self.llm, version=self.search_policy_version, **kwargs)
            if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                from copy import deepcopy
                received = getattr(result, '_model_response', None)
                self._last_received_response = {'operation': kwargs['output_schema'].__name__, 'model_response': deepcopy(received if received is not None else result.model_dump(mode='json')), 'model_response_text': getattr(result, '_model_response_text', None), 'code_validation': {'status': 'pending', 'stage': 'schema_boundary', 'errors': []}}
                self.model_response_history.append(self._last_received_response)
            try:
                result = kwargs['output_schema'].model_validate(result.model_dump())
                bound = original_schema.model_validate(collect_plan_claims(self, result.model_dump()))
            except Exception as exc:
                if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    self._last_received_response['code_validation'].update(status='failed', errors=[str(exc)])
                raise
            if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                self._last_received_response['code_validation']['status'] = 'passed'
            return bound
        return generate_with_backoff(self.llm, version=self.search_policy_version, **kwargs)

    @observed('requirements')
    def extract_requirements(self, input_data: SearchAgentInput, *, search_policy_version='v2') -> ResolvedRequirements:
        """Extract complete intent once, before query selection or tool lookup."""
        if getattr(input_data.stylist_resolution, 'contract_version', None) in {'stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6', 'stylist-v7', 'stylist-v8'} and search_policy_version not in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            raise ValueError('Stylist v2 requires the Search v49 handoff contract.')
        if input_data.audience_context_v1 is not None and search_policy_version not in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            raise ValueError('Contextual audience v1 requires the v24 Search contracts.')
        self.search_policy_version = search_policy_version
        if search_policy_version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            self._stylist_omissions_v47 = {}
        if search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            self._plan_claims = {}
            self._semantic_product_evidence = None
        if search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            self.model_response_history = []
            return self._extract_requirements_v26(input_data) if search_policy_version in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else self._extract_requirements_v25(input_data)
        if search_policy(search_policy_version).enabled('revision_intent_contract'):
            return self._extract_requirements_v7(input_data)
        input_data = without_profile(SearchAgentInput.model_validate(input_data.model_dump()))
        schema = RequirementsExtractionV3 if search_policy(search_policy_version).enabled('legacy_visual_inspection') else RequirementsExtraction
        result = self._generate(system_prompt=build_requirements_extraction_prompt(user_query=input_data.user_query, goal=input_data.goal, contextual_gender=search_policy(search_policy_version).enabled('legacy_visual_inspection'), stylist_resolution=input_data.stylist_resolution.model_dump(mode='json') if input_data.stylist_resolution is not None else None) + (SIMILARITY_REQUIREMENT_CONTRACT if input_data.similarity_reference else ''), user_input=without_profile(input_data), output_schema=schema)
        result = schema.model_validate(result.model_dump())
        validate_reference_requirements(input_data, result)
        if any((entry.source != 'reference' and entry.source_text not in input_data.user_query for entry in result.requirements)):
            raise ValueError('Requirement evidence must quote the current searchable request')
        validate_stylist_requirements(input_data, result)
        policy = getattr(result, 'gender_diversity_policy', None)
        if policy is not None:
            if any((text not in input_data.user_query for text in policy.source_texts)):
                raise ValueError('Gender diversity policy must cite exact current user request excerpts.')
            explicit_gender = any((r.source == 'user' and r.attribute == 'gender' for r in result.requirements))
            if explicit_gender != (policy.exemption == 'explicit_user_gender'):
                raise ValueError('Explicit user gender and diversity exemption must agree.')
        return ResolvedRequirements(gender_diversity_policy=policy.model_copy(deep=True) if policy else None, requirements_id=f'requirements_{uuid4().hex}', requirements=[entry.model_copy(deep=True) for entry in result.requirements])

    @observed('planning')
    def assess_requirement_usage(self, *, input_data, query_plan, resolved_requirements, review_context=None):
        """Assess the FINAL execution plan, after category/filter resolution and FX."""
        if not resolved_requirements.requirements:
            return []
        locations = {"query": query_plan.query, "filter": json.dumps(query_plan.aspect_filters, ensure_ascii=False), "category": json.dumps(query_plan.category_ids, ensure_ascii=False)}
        if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.planning_rules import execution_evidence_contract
            locations = {key: rule['text'] for key, rule in execution_evidence_contract(query_plan).items()}
        if search_policy(self.search_policy_version).enabled('separate_plan_review'):
            return assess_plan(self, input_data, query_plan, resolved_requirements, review_context, locations)
        prompt = build_requirement_usage_prompt(requirements=resolved_requirements.model_dump(mode='json'), final_plan=query_plan.model_dump(mode='json'), observed_categories=self.category_evidence, locations=locations)
        v7 = search_policy(self.search_policy_version).enabled('revision_intent_contract')
        if v7:
            prompt += """
V7 FINAL PLAN REVIEW: also return explanation_matches_execution,
hard_conditions_preserved, assessed_audience_scope, issues. Check the FINAL query,
category ancestors/gender_scope, filters, and the proposed revision's action and
reason together. Dropping 'men' from query does NOT remove a men's category.
An unrestricted category can support a query specifically targeting men or women;
it must not be confused with a category excluding that audience. Assess the combined
query/category/filter meaning, including whether intent.change_type accurately
describes restriction removal, an equivalent synonym, or a genuinely new direction.
A parent Coats category does NOT represent the specific hard type 'trench coat'.
Preserve specificity: trench coat must not become generic coat/peacoat/overcoat.
Other genuinely equivalent spellings or eligible OR alternatives remain allowed.
Report false and explain contradictions; never approve just to meet a candidate target.
Unknown category scope is not proof of gender neutrality. For an initial plan with
no revision explanation, explanation_matches_execution=true unless its scope
contradicts an explicit user condition. All usages must quote actual execution evidence.
Review context:
""" + json.dumps(review_context or {}, ensure_ascii=False)
        if search_policy(self.search_policy_version).enabled('scoped_requirements'):
            prompt += plan_rules(self.search_policy_version)
        schema = RequirementUsageAssessmentV7 if v7 else RequirementUsageAssessment
        result = self._generate(system_prompt=prompt, user_input=without_profile(input_data), output_schema=schema)
        result = schema.model_validate(result.model_dump())
        if v7:
            self.last_plan_review = result.model_dump(mode='json')
            if not result.explanation_matches_execution or not result.hard_conditions_preserved:
                raise ValueError('Final plan semantic mismatch: ' + '; '.join(result.issues))
        ids = {entry.requirement_id for entry in resolved_requirements.requirements}
        for usage in result.usages:
            if usage.requirement_id not in ids:
                raise ValueError(f'Requirement usage cites unknown ID: {usage.requirement_id!r}.')
            if not usage.evidence.strip() or usage.evidence not in locations[usage.location]:
                raise ValueError(f'Requirement usage {usage.requirement_id!r} must cite actual execution evidence (exact {usage.location} evidence): received {usage.evidence!r}; location text is {locations[usage.location]!r}.')
            if usage.location == "filter" and (not query_plan.aspect_filters):
                raise ValueError("Cannot cite an empty filter.")
            if usage.location == "category" and (not query_plan.category_ids):
                raise ValueError("Cannot cite an empty category.")
        if v7:
            validate_specific_product_types(query_plan, resolved_requirements, result.usages, self.category_evidence, singular=search_policy(self.search_policy_version).enabled('scoped_requirements'))
            if search_policy(self.search_policy_version).enabled('scoped_requirements'):
                validate_v8_query_usage(resolved_requirements, result.usages, max_soft=3 if search_policy(self.search_policy_version).enabled('three_soft_search_terms') else 1)
        return result.usages

    def plan_query(self, input_data: SearchAgentInput, *, resolved_requirements: ResolvedRequirements | None=None, validation_feedback: dict | None=None) -> SearchQueryPlan:
        """
        사용자 요청을 기반으로 최초 SearchQueryPlan을 생성한다.

        SearchRunner는 추출·저장한 resolved_requirements를 반드시 전달한다.
        None은 기존 단독 planning 호출의 호환성을 위한 경로다.
        """
        input_data = without_profile(input_data)
        self.filter_resolution_history.clear()
        self.category_evidence.clear()
        prompt = build_query_planning_prompt(user_query=input_data.user_query, goal=input_data.goal, requested_count=input_data.requested_count, stylist_resolution=input_data.stylist_resolution.model_dump(mode='json') if input_data.stylist_resolution is not None else None, preference_profile=input_data.preference_profile.model_dump(mode='json', by_alias=True) if input_data.preference_profile is not None else None, resolved_requirements=resolved_requirements.model_dump(mode='json') if resolved_requirements is not None else None)
        if search_policy(self.search_policy_version).enabled('revision_intent_contract'):
            prompt += V7_HARD_TYPE_RULES
            if search_policy(self.search_policy_version).enabled('scoped_requirements'):
                prompt += V8_REQUIREMENT_RULES + plan_rules(self.search_policy_version)
                if validation_feedback:
                    prompt += '\nINITIAL PLAN TEXT REPAIR (one attempt): ' + json.dumps(validation_feedback, ensure_ascii=False)
        if search_policy(self.search_policy_version).enabled('concise_query_contract'):
            from fashion_recommendation_v2.prompts.search.planning import search_planning_v16__initial_plan_prompt as initial_plan_prompt
            if search_policy(self.search_policy_version).enabled('per_item_evidence_contract'):
                from fashion_recommendation_v2.prompts.search.planning import search_planning_v18__initial_plan_prompt as initial_plan_prompt
            if search_policy(self.search_policy_version).enabled('canonical_proposal_filters'):
                from fashion_recommendation_v2.search.contracts import search_prompts
                initial_plan_prompt = search_prompts(self.search_policy_version).initial_plan_prompt
            if resolved_requirements is None:
                raise ValueError('V16 planning requires the preserved resolved_requirements.')
            if self.search_policy_version in {'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                from functools import partial
                self._planning_source_v32 = input_data
                initial_plan_prompt = partial(initial_plan_prompt, source=input_data)
            prompt = initial_plan_prompt(resolved_requirements, single_plan=True, validation_error=validation_feedback)
        llm_result = self._generate(system_prompt=prompt, user_input=without_profile(input_data), output_schema=SearchQueryPlanLLM)
        return self.complete_initial_plan(input_data, llm_result, resolved_requirements)

    def complete_initial_plan(self, input_data, llm_result, resolved_requirements):
        if search_policy(self.search_policy_version).enabled('concise_query_contract'):
            validate_marketplace_query(llm_result.query)
        llm_result = self._canonical_proposal(llm_result)
        draft_plan = SearchQueryPlan(query=llm_result.query, price_constraint=resolved_requirements.price_constraint if resolved_requirements is not None else llm_result.price_constraint, category_ids=llm_result.category_ids, aspect_filters=self._convert_aspect_filters(llm_result.aspect_filters))
        if search_policy(self.search_policy_version).enabled('revision_intent_contract'):
            if any((f.name not in {'Condition', 'Size'} for f in llm_result.aspect_filters)):
                raise ValueError('v7 initial plan has an unsupported/unverified filter; only Condition/Size are resolved.')
            if draft_plan.category_ids:
                categories = self.search_tool.lookup_categories(query=draft_plan.query, include_context=True)
                self.category_evidence.extend((c.model_dump(mode='json') for c in categories))
                if not set(draft_plan.category_ids) <= {c.category_id for c in categories}:
                    raise ValueError('Initial category IDs must have marketplace evidence.')
        return self._complete_filter_options(input_data=input_data, plan=draft_plan)

    # ============================================================
    # ============================================================
    # Result Inspection
    def evaluate_visual_batch(self, **kwargs):
        from fashion_recommendation_v2.agents.search_visual_analysis import evaluate_visual_batch
        return evaluate_visual_batch(self, **kwargs)

    def inspect_visual_results(self, **kwargs):
        from fashion_recommendation_v2.agents.search_visual_analysis import inspect_visual_results
        return inspect_visual_results(self, **kwargs)

    def repair_visual_revision(self, **kwargs):
        from fashion_recommendation_v2.agents.search_visual_analysis import repair_visual_revision
        return repair_visual_revision(self, **kwargs)

    def inspect_and_revise(self, *, input_data, query_plan, inspected_items, resolved_requirements, previous_attempts, requirement_usages, unused_requirement_ids, candidate_count, target_candidate_count, projected_candidate_count, existing_candidates, completed_search_attempts, minimum_search_attempts, attempts_remaining, quality_met, correcting_issue=None):
        """One model call; category/filter completion is deferred until execution."""
        used_now = {usage.requirement_id for usage in requirement_usages}
        context = {'query_plan': query_plan.model_dump(mode='json'), 'resolved_requirements': resolved_requirements.model_dump(mode='json'), 'inspected_items': [item.model_dump(mode='json') for item in inspected_items], 'previous_attempts': [attempt.model_dump(mode='json', exclude={'inspection_decision'}) for attempt in previous_attempts], 'requirement_usages': [usage.model_dump(mode='json') for usage in requirement_usages], 'unused_requirement_ids_after_current': [i for i in unused_requirement_ids if i not in used_now], 'candidate_count_before': candidate_count, 'projected_candidate_count_if_batch_accepted': min(projected_candidate_count, target_candidate_count), 'existing_candidates': existing_candidates, 'target_candidate_count': target_candidate_count, 'requested_count': input_data.requested_count, 'completed_search_attempts': completed_search_attempts, 'minimum_search_attempts': minimum_search_attempts, 'attempts_remaining_after_current': attempts_remaining, 'previous_quality_gate_met': quality_met, 'correcting_issue': correcting_issue.model_dump(mode='json', exclude={'inspected_items'}) if correcting_issue else None, 'observed_categories': self.category_evidence}
        result = self._generate(system_prompt=build_inspection_decision_prompt(context=context), user_input=without_profile(input_data), output_schema=SearchInspectionDecision)
        result = SearchInspectionDecision.model_validate(result.model_dump())
        supplied = {item.item_id for item in inspected_items}
        accepted = result.accepted_item_ids
        if len(set(accepted)) != len(accepted) or not set(accepted) <= supplied:
            raise ValueError('Inspection accepted_item_ids must be unique IDs from the inspected sample.')
        if result.inspection.inspected_count != len(inspected_items):
            raise ValueError('Inspection inspected_count differs from the supplied sample.')
        # Counts and ratios are mechanically derived from the same per-item judgments.
        result.inspection.relevant_result_ratio = len(accepted) / len(inspected_items) if inspected_items else 0.0
        if result.revision is not None:
            if result.revision.issue_disposition != 'correct':
                raise ValueError('Combined inspection must return an executable draft or null.')
            validate_exploration(result.revision, without_profile(input_data), query_plan, self._convert_aspect_filters(result.revision.aspect_filters))
        return result

    def complete_inspection_revision(self, *, input_data, current_query_plan, revision):
        """Resolve the already chosen draft; never ask for a second strategy."""
        if search_policy(self.search_policy_version).enabled('concise_query_contract'):
            validate_marketplace_query(revision.revised_query)
        revision = self._canonical_proposal(revision)
        completed = self._complete_filter_options(input_data=input_data, plan=SearchQueryPlan(query=revision.revised_query, price_constraint=current_query_plan.price_constraint, category_ids=revision.category_ids, aspect_filters=self._convert_aspect_filters(revision.aspect_filters)))
        return StrategyRevision(trigger=revision.trigger, action=revision.action, revised_query=completed.query, category_ids=completed.category_ids, aspect_filters=completed.aspect_filters, price_constraint=completed.price_constraint)

    def inspect_results(self, *, input_data: SearchAgentInput, query_plan: SearchQueryPlan, inspected_items: list[EBayRawItem], candidate_count: int, target_candidate_count: int, completed_search_attempts: int, minimum_search_attempts: int, correcting_issue: SearchIssue | None=None) -> SearchInspection:
        """
        현재 Search 결과를 검사하고
        현재 검색 방향을 계속 사용할지 판단한다.
        """
        if candidate_count < 0:
            raise ValueError("candidate_count must be greater than or equal to 0.")
        if target_candidate_count < 1:
            raise ValueError("target_candidate_count must be greater than or equal to 1.")
        prompt = build_result_inspection_prompt(user_query=input_data.user_query, goal=input_data.goal, query_plan={**query_plan.model_dump(mode='json'), 'correcting_issue': correcting_issue.model_dump(mode='json') if correcting_issue else None}, inspected_items=[item.model_dump(mode='json') for item in inspected_items], candidate_count=candidate_count, target_candidate_count=target_candidate_count, completed_search_attempts=completed_search_attempts, minimum_search_attempts=minimum_search_attempts)
        prompt += """
Additional query terms may be exploratory preference hypotheses. Judge relevance against
current user requirements and resolved Stylist interpretations, never against stored taste.
Do not reject candidates or report quality issues merely for missing optional exploration terms.
"""
        return self._generate(system_prompt=prompt, user_input=without_profile(input_data), output_schema=SearchInspection)

    def revise_strategy(self, *, input_data: SearchAgentInput, current_query_plan: SearchQueryPlan, inspection: SearchInspection, inspected_items: list[EBayRawItem], previous_attempts: list[SearchAttempt], resolved_requirements: ResolvedRequirements | None=None, unused_requirement_ids: list[str] | None=None, queued_issue: SearchIssue | None=None) -> StrategyRevision:
        """
        검색 방향이 Reject되거나 최소 검색 횟수가 미달한 경우
        다음 Search Strategy를 생성한다.
        """
        primary_issue = inspection.issues[0] if inspection.issues else None
        if inspection.continue_query and primary_issue not in {"minimum_search_attempts_not_met", "unused_requirements"}:
            raise ValueError('Strategy Revision requires continue_query=False unless minimum_search_attempts_not_met requires forced exploration.')
        prompt = build_strategy_revision_prompt(user_query=input_data.user_query, goal=input_data.goal, current_query_plan=current_query_plan.model_dump(mode='json'), inspection=inspection.model_dump(mode='json'), inspected_items=[item.model_dump(mode='json') for item in inspected_items], resolved_requirements=resolved_requirements.model_dump(mode='json') if resolved_requirements is not None else None, unused_requirement_ids=unused_requirement_ids or [], queued_issue=queued_issue.model_dump(mode='json') if queued_issue else None, previous_attempts=[attempt.model_dump(mode='json') for attempt in previous_attempts])
        revision_input = exploration_input(input_data, resolved_requirements) if primary_issue == "minimum_search_attempts_not_met" and (not unused_requirement_ids) else without_profile(input_data)
        prompt += """
Stored preference policy: profile values are optional exploration hypotheses, never user
requirements or candidate rejection rules. If a profile is supplied, preserve category_ids
and all non-price aspect_filters exactly. Do not output PriceMin/PriceMax; code preserves budget.
Only query wording may explore one or more supplied positive features together.
preference_evidence_refs may combine evidence IDs from different supplied positive features.
Copy each ID exactly from the CURRENT input profile and include each ID only once.
Never invent, rename, translate or infer an evidence ID for a feature absent from that profile.
Do not borrow IDs from earlier attempts, example text or excluded profile features.
Every cited ID must support a preference actually used in the revised query. For example,
a supplied cotton preference does not establish a denim preference: do not invent a denim ID
or relabel cotton evidence as denim evidence. Semantic expansion is not new preference evidence.
If no preference is used or no profile is supplied, return an empty list. Never add demographic,
body-size or mandatory conditions from preference. Current request constraints always win.
Profile-free result inspection evaluates request relevance, not similarity to stored taste.
"""
        llm_result = self._generate(system_prompt=prompt, user_input=revision_input, output_schema=StrategyRevisionLLM)
        llm_result = StrategyRevisionLLM.model_validate(llm_result.model_dump())
        validate_exploration(llm_result, revision_input, current_query_plan, self._convert_aspect_filters(llm_result.aspect_filters))
        if queued_issue is not None and llm_result.issue_disposition != 'correct':
            if not llm_result.disposition_reason.strip():
                raise ValueError("Skipping a queued issue requires an evidence-based reason.")
            return StrategyRevision(trigger=primary_issue if resolved_requirements is not None else llm_result.trigger, action=llm_result.action, revised_query=current_query_plan.query, issue_disposition=llm_result.issue_disposition, disposition_reason=llm_result.disposition_reason)
        if revision_input.preference_profile is not None:
            # The previous plan's filters/category are already validated; preserve them byte-for-byte.
            completed_plan = current_query_plan.model_copy(deep=True, update={"query": llm_result.revised_query})
        else:
            completed_plan = self._complete_filter_options(input_data=input_data, plan=SearchQueryPlan(query=llm_result.revised_query, price_constraint=current_query_plan.price_constraint, category_ids=llm_result.category_ids, aspect_filters=self._convert_aspect_filters(llm_result.aspect_filters)))
        return StrategyRevision(preference_evidence_refs=list(llm_result.preference_evidence_refs), issue_disposition='correct', price_constraint=completed_plan.price_constraint, trigger=primary_issue if resolved_requirements is not None else llm_result.trigger, action=llm_result.action, revised_query=completed_plan.query, category_ids=completed_plan.category_ids, aspect_filters=completed_plan.aspect_filters)

    def _complete_filter_options(self, *, input_data: SearchAgentInput, plan: SearchQueryPlan) -> SearchQueryPlan:
        # Select the category first so options come from the execution category.
        plan = self._ensure_filter_category(input_data=input_data, plan=plan)
        completed = plan.model_copy(deep=True)
        traces: list[FilterResolutionTrace] = []
        for filter_name in ('Condition', 'Size'):
            requested = plan.aspect_filters.get(filter_name)
            if not requested:
                continue
            if not isinstance(requested, list):
                raise ValueError(f'{filter_name} must be represented as list[str].')
            lookup = self.search_tool.lookup_filter_options(query=plan.query, category_ids=plan.category_ids, filter_name=filter_name)
            selected: list[str] = []
            query_terms = ''
            # Initial evaluation + at most one resumed lookup/evaluation.
            for evaluation in range(1 if search_policy(self.search_policy_version).enabled('separate_plan_review') else 2):
                selection = self._generate(system_prompt=build_filter_option_selection_prompt(user_query=input_data.user_query, goal=input_data.goal, query_plan=plan.model_dump(mode='json'), filter_name=filter_name, requested_values=requested, available_options=lookup.options, can_retry=not search_policy(self.search_policy_version).enabled('separate_plan_review') and evaluation == 0 and (not lookup.exhausted)), user_input=without_profile(input_data), output_schema=FilterOptionSelection)
                query_terms = selection.query_terms.strip()
                if selection.selected_options and all((value in lookup.options for value in selection.selected_options)):
                    # LLM judges compatibility; code only verifies tool provenance.
                    selected = list(dict.fromkeys(selection.selected_options))
                    break
                if evaluation == 1 or lookup.exhausted or search_policy(self.search_policy_version).enabled('separate_plan_review'):
                    break
                lookup = self.search_tool.lookup_filter_options(query=plan.query, category_ids=plan.category_ids, filter_name=filter_name, previous_result=lookup)
            if selected:
                completed.aspect_filters[filter_name] = selected
                query_terms = ''
            else:
                del completed.aspect_filters[filter_name]
                # Preserve intent even if the LLM omitted fallback wording.
                if not query_terms:
                    values = " or ".join(requested)
                    query_terms = f'size {values}' if filter_name == 'Size' else values
                if query_terms.casefold() not in completed.query.casefold():
                    completed.query = f'{completed.query.rstrip()} {query_terms}'
            traces.append(FilterResolutionTrace(plan_query=completed.query, category_ids=list(completed.category_ids), filter_name=filter_name, requested_values=list(requested), available_options=list(lookup.options), selected_options=selected, query_terms=query_terms, lookup_limits=list(lookup.attempted_limits)))
        for trace in traces:
            trace.plan_query = completed.query
        self.filter_resolution_history.extend(traces)
        completed.validate_for_execution()
        return completed

    def _ensure_filter_category(self, *, input_data: SearchAgentInput, plan: SearchQueryPlan) -> SearchQueryPlan:
        completed = plan.model_copy(deep=True)
        completed.category_ids = [value.strip() for value in plan.category_ids if value.strip()]
        if not (completed.aspect_filters or completed.price_constraint is not None) or completed.category_ids:
            return completed
        categories = self.search_tool.lookup_categories(query=completed.query, **{'include_context': True} if search_policy(self.search_policy_version).enabled('revision_intent_contract') else {})
        self.category_evidence.extend((category.model_dump(mode='json') for category in categories))
        if not categories:
            raise ValueError(f'Cannot complete filtered search plan: no eBay category was found for query={completed.query!r}.')
        selection = self._generate(system_prompt=build_category_selection_prompt(user_query=input_data.user_query, goal=input_data.goal, query_plan=completed.model_dump(mode='json'), categories=[category.model_dump(mode='json') for category in categories]), user_input=without_profile(input_data), output_schema=SearchCategorySelection)
        observed_ids = {category.category_id for category in categories}
        if selection.category_id not in observed_ids:
            raise ValueError('Cannot complete filtered search plan: category selection must match a compatible category returned by eBay.')
        completed.category_ids = [selection.category_id]
        return completed

    def _extract_requirements_v26(self, input_data):
        """Structure once, validate, classify IDs once, bind without rewriting facts."""
        from copy import deepcopy
        from fashion_recommendation_v2.search.contracts import search_schemas
        from fashion_recommendation_v2.search.contracts import search_prompts
        from fashion_recommendation_v2.search.requirements import structure_and_sources_v26 as structure_and_sources
        from fashion_recommendation_v2.search.requirements import bind_applications_v26 as bind_applications
        from fashion_recommendation_v2.search.requirements import assert_preserved
        version = self.search_policy_version if self.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 'v26'
        module = search_schemas(version, purpose='requirements')
        source = without_profile(module.prepare_input(input_data))
        self.requirements_validation_history = []
        conditions = None
        for stage in ('structure', 'classify'):
            from fashion_recommendation_v2.search.semantic_validation import experiment_records
            warning_start = len(experiment_records())
            relation_args = {'relation_conditions': structure.relation_conditions} if version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and stage == 'classify' else {}
            schema = module.extraction_schema(source) if stage == 'structure' else module.classification_schema(conditions, **relation_args)
            record = dict(stage=stage, attempt=1, input=source.model_dump(mode='json'), response_schema=schema.model_json_schema(), model_response=None, model_response_text=None, code_validation=dict(status='pending', checks=[], errors=[], derived={}))
            if conditions is not None:
                record['frozen_conditions'] = [c.model_dump(mode='json') for c in conditions]
                if version in {'v58', 'v59', 'v60', 'v61'}:
                    from fashion_recommendation_v2.search.stylist_comparison_targets import comparison_context_stylist_comparison_targets_v58 as comparison_context
                    record['comparison_targets_v58'] = comparison_context(conditions)
            try:
                self._generate(system_prompt=search_prompts(version, purpose='requirements').requirements_prompt(source, schema, stage=stage, conditions=conditions, **relation_args), user_input=source, output_schema=schema, recovery=False)
                received = self._last_received_response
                record.update(model_response=deepcopy(received['model_response']), model_response_text=received.get('model_response_text'))
                output = schema.model_validate(deepcopy(record['model_response']))
                if stage == 'structure':
                    structure = output
                    if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                        from fashion_recommendation_v2.module_compat import import_module as import_module
                        module_version = get_search_contracts(version).requirements.version if version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 'v31' if version in {'v32', 'v33', 'v34', 'v35', 'v36'} else version
                        prepare_structure = import_module(f'fashion_recommendation_v2.search.requirements_{module_version}').prepare_structure
                        structure, conditions, derived = prepare_structure(source, output)
                        record['code_derived'] = derived
                    else:
                        conditions = structure_and_sources(source, structure)
                    from types import SimpleNamespace
                    validate_english_requirements(SimpleNamespace(requirements=conditions))
                    # The model never authors Stylist copies or these derived joins.
                    record['code_validation']['derived']['conditions'] = [c.model_dump(mode='json') for c in conditions]
                else:
                    if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                        from fashion_recommendation_v2.module_compat import import_module as import_module
                        finalize_conditions = import_module('fashion_recommendation_v2.search.requirements_' + (get_search_contracts(version).requirements.version if version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 'v35' if version in {'v35', 'v36'} else 'v30')).finalize_conditions
                        resolved, derived = finalize_conditions(source, structure, conditions, output)
                        record['code_derived'] = derived
                    else:
                        resolved, derived = bind_applications(source, structure, conditions, output)
                    validate_requirements(source, resolved, version)
                    validate_alternative_inventory(source, resolved, version=version)
                    assert_preserved(conditions, resolved)
                    record['code_validation']['derived'].update(derived, resolved_requirements=resolved.model_dump(mode='json'))
                record['code_validation'].update(status='passed', checks=['schema', 'condition_ids', 'field_sources', 'stylist_originals'] if stage == 'structure' else ['schema', 'exact_id_coverage', 'immutable_originals', 'final_requirements', 'audience_policy'])
                if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    record['code_validation']['warnings'] = deepcopy(record.get('code_derived', {}).get('recoveries', []))
                if version in {'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    warnings = record.get('code_derived', {}).get('warnings', [])
                    record['code_validation'].setdefault('warnings', []).extend(deepcopy(warnings))
                    if warnings:
                        record['code_validation']['status'] = 'passed_with_warnings'
            except Exception as exc:
                received = getattr(exc, 'response_snapshot', None) or getattr(self, '_last_received_response', None)
                if record['model_response'] is None and received and (received.get('operation', schema.__name__) == schema.__name__):
                    record.update(model_response=deepcopy(received.get('model_response')), model_response_text=received.get('model_response_text'))
                record['code_validation'].update(status='failed', errors=[f'{type(exc).__name__}: {exc}'])
                if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and hasattr(exc, 'code_derived'):
                    record['code_derived'] = deepcopy(exc.code_derived)
                exc.requirements_stage = stage
                exc.requirements_validation = deepcopy([*self.requirements_validation_history, record])
                raise
            finally:
                observations = deepcopy(experiment_records()[warning_start:])
                if observations:
                    record['code_validation']['experiment_observations'] = observations
                    if record['code_validation']['status'] == 'passed' and any((row['action'] == 'record_only' for row in observations)):
                        record['code_validation']['status'] = 'passed_with_warnings'
                self.requirements_validation_history.append(deepcopy(record))
        return resolved

    def _extract_requirements_v25(self, input_data):
        """Audit the original response; compile code-owned fields into a separate result."""
        from copy import deepcopy
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import prepare_input_v25 as prepare_input
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsReviewInputV25
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import apply_audience_decision
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV15_v15 as RequirementsExtractionV15
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import bind_requirement_fields
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import decide_audience
        from fashion_recommendation_v2.search.contracts import requirements_schema
        from fashion_recommendation_v2.search.requirement_sources import validate_field_sources
        from fashion_recommendation_v2.prompts.search.requirements import search_requirements_v25__requirements_prompt as requirements_prompt
        source = without_profile(prepare_input(input_data))
        schema = requirements_schema('v25', source)
        self.requirements_validation_history = []
        feedback = None
        for attempt in range(2):
            review = RequirementsReviewInputV25(model_response=None, response_schema=schema.model_json_schema())
            record = {'attempt': attempt + 1, 'input': source.model_dump(mode='json')}
            audit = None
            try:
                model_output = self._generate(system_prompt=requirements_prompt(source, schema, stage='repair' if attempt else 'extraction', feedback=feedback), user_input=source, output_schema=schema, recovery=bool(attempt))
                review.model_response = deepcopy(self._last_received_response['model_response'])
                review.model_response_text = self._last_received_response['model_response_text']
                model_output = schema.model_validate(deepcopy(review.model_response))
                # This derived object is NEVER substituted for model_response in review.
                output = bind_requirement_fields(RequirementsExtractionV15.model_validate(model_output.model_dump(exclude={'audience_interpretation'})))
                review.code_validation.checks = validate_field_sources(source, output, model_output.audience_interpretation)
                validate_requirements(source, output, 'v25')
                validate_alternative_inventory(source, output, version='v25')
                decision = decide_audience(source.audience_context_v1, output, model_output.audience_interpretation)
                resolved = apply_audience_decision(output, decision, requirements_id=f'requirements_{uuid4().hex}')
                validate_requirements(source, resolved, 'v25')
                validate_alternative_inventory(source, resolved, version='v25')
                review.code_validation.status = 'passed'
                review.code_validation.checks += ['schema', 'stylist_preservation', 'reference_preservation', 'alternative_inventory', 'audience_precedence', 'final_requirements']
                review.code_validation.derived = {'resolved_requirements': resolved.model_dump(mode='json')}
                audit = self._generate(system_prompt=requirements_prompt(source, schema, stage='audit', review=review), user_input=source, output_schema=RequirementsAuditV7, recovery=bool(attempt))
                audit = RequirementsAuditV7.model_validate(audit.model_dump())
                if not audit.complete or audit.missing_alternatives or audit.issues:
                    raise ValueError(audit.model_dump_json())
                return resolved
            except Exception as exc:
                if review.code_validation.status != 'passed':
                    review.code_validation.status = 'failed'
                    review.code_validation.errors.append(f'{type(exc).__name__}: {exc}')
                    # Parsing failures may expose a received response via _generate.
                    if review.model_response is None:
                        received = getattr(exc, 'response_snapshot', None) or getattr(self, '_last_received_response', None)
                        if received and received.get('operation', schema.__name__) == schema.__name__:
                            review.model_response = deepcopy(received['model_response'])
                            review.model_response_text = received.get('model_response_text')
                feedback = {'error': str(exc), 'review_input': review.model_dump(mode='json'), 'audit_response': audit.model_dump(mode='json') if audit else None}
                if attempt:
                    exc.requirements_validation = deepcopy(feedback)
                    raise
            finally:
                record.update(review.model_dump(mode='json'))
                record['audit_response'] = audit.model_dump(mode='json') if audit else None
                self.requirements_validation_history.append(deepcopy(record))
        raise RuntimeError('Unreachable extraction state')

    def _extract_requirements_v7(self, input_data):
        source = without_profile(SearchAgentInput.model_validate(input_data.model_dump()))
        feedback = None
        for attempt in range(2):
            prompt = build_requirements_extraction_prompt(user_query=source.user_query, goal=source.goal, contextual_gender=True, stylist_resolution=source.stylist_resolution.model_dump(mode='json') if source.stylist_resolution else None)
            prompt += V7_HARD_TYPE_RULES + """
V7 EXTRACTION INVENTORY: return product_type_alternatives, independently listing
EVERY product type the user permits with its requirement_id, normalized value and
exact source_text. In requirements, put the FULL alternative list in the same
product_type requirement, not multiple simultaneous hard requirements. Do not
choose a search direction yet. 'dress; two-piece is okay; no pants; long skirt'
permits dress OR skirt_set. Never retain only dress while silently losing skirt_set.
Preserve negative preferences as original hard/soft requirements too. Inventory
and gender policy must agree with the complete eligible product types.
"""
            if search_policy(self.search_policy_version).enabled('scoped_requirements'):
                prompt += V8_REQUIREMENT_RULES
            if search_policy(self.search_policy_version).enabled('keyed_condition_contract'):
                from fashion_recommendation_v2.prompts.search.requirements import REQUIREMENT_CONTRACT
                prompt = REQUIREMENT_CONTRACT
            if search_policy(self.search_policy_version).enabled('compact_strategy_context'):
                from fashion_recommendation_v2.search.contracts import search_prompts
                prompt = search_prompts(self.search_policy_version, purpose='extraction').EXTRACTION_CONTRACT
            if source.similarity_reference:
                prompt += SIMILARITY_REQUIREMENT_CONTRACT
            if feedback:
                prompt += '\nRepair this extraction only: ' + json.dumps(feedback, ensure_ascii=False)
            if source.audience_context_v1:
                from fashion_recommendation_v2.prompts.search.requirements import audience_prompt
                prompt = audience_prompt(prompt, source)
            try:
                from fashion_recommendation_v2.search.contracts import requirements_schema
                from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV15_v15 as RequirementsExtractionV15
                schema = requirements_schema(self.search_policy_version, source)
                output = self._generate(system_prompt=prompt, user_input=source, output_schema=schema, recovery=bool(attempt))
                output = schema.model_validate(output.model_dump())
                model_output = output
                if source.audience_context_v1:
                    # Preserve historical extraction schemas. The new field is
                    # audited separately and its effective hard constraint is code-owned.
                    output = RequirementsExtractionV15.model_validate(output.model_dump(exclude={'audience_interpretation'}))
                if search_policy(self.search_policy_version).enabled('compact_strategy_context'):
                    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import bind_requirement_fields
                    output = bind_requirement_fields(output)
                elif search_policy(self.search_policy_version).enabled('model_product_type_binding'):
                    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import bind_product_types
                    output = bind_product_types(output)
                if search_policy(self.search_policy_version).enabled('scoped_requirements'):
                    if search_policy(self.search_policy_version).enabled('concise_query_contract'):
                        validate_requirements(source, output, self.search_policy_version)
                    else:
                        validate_v8_requirements(output)
                validate_stylist_requirements(source, output)
                validate_alternative_inventory(source, output, version=self.search_policy_version)
                audience_decision = None
                if source.audience_context_v1:
                    from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import decide_audience
                    from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import validate_audience_field_sources
                    validate_audience_field_sources(source, output, model_output.audience_interpretation)
                    audience_decision = decide_audience(source.audience_context_v1, output, model_output.audience_interpretation)
                audit_prompt = """
V7 INDEPENDENT REQUIREMENT COMPLETENESS REVIEW. Read the original user request and
Stylist interpretations before reviewing the extraction. Check EVERY permitted
product alternative, including contextual skirt sets, and negative preferences.
Report complete=false with missing_alternatives and issues for any omission,
changed hard/soft status, invented condition or narrowed OR. Each missing alternative
must cite an exact source excerpt and its intended existing product requirement ID.
Do not plan searches. An empty inventory cannot make missing intent disappear.
EXTRACTION:
""" + output.model_dump_json() + (V8_REQUIREMENT_RULES if search_policy(self.search_policy_version).enabled('scoped_requirements') else '')
                if search_policy(self.search_policy_version).enabled('keyed_condition_contract'):
                    from fashion_recommendation_v2.prompts.search.requirements import AUDIT_CONTRACT
                    from fashion_recommendation_v2.prompts.search.requirements import REQUIREMENT_CONTRACT
                    audit_prompt = REQUIREMENT_CONTRACT + AUDIT_CONTRACT + '\nEXTRACTION:\n' + output.model_dump_json()
                if search_policy(self.search_policy_version).enabled('compact_strategy_context'):
                    from fashion_recommendation_v2.search.contracts import search_prompts
                    build_audit = search_prompts(self.search_policy_version, purpose='extraction').audit_prompt
                    ordinary_model_output = RequirementsExtractionV15.model_validate(model_output.model_dump(exclude={'audience_interpretation'})) if audience_decision else model_output
                    audit_prompt = build_audit(ordinary_model_output, output)
                if source.similarity_reference:
                    audit_prompt += SIMILARITY_REQUIREMENT_CONTRACT
                if audience_decision:
                    audit_prompt = audience_prompt(audit_prompt, source, decision=audience_decision)
                audit = self._generate(system_prompt=audit_prompt, user_input=source, output_schema=RequirementsAuditV7, recovery=bool(attempt))
                audit = RequirementsAuditV7.model_validate(audit.model_dump())
                if not audit.complete or audit.missing_alternatives or audit.issues:
                    raise ValueError(audit.model_dump_json())
                if audience_decision:
                    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import apply_audience_decision_v24 as apply_audience_decision
                    resolved = apply_audience_decision(output, audience_decision, requirements_id=f'requirements_{uuid4().hex}')
                    validate_requirements(source, resolved, self.search_policy_version)
                    validate_alternative_inventory(source, resolved, version=self.search_policy_version)
                    return resolved
                return ResolvedRequirements(requirements_id=f'requirements_{uuid4().hex}', requirements=[r.model_copy(deep=True) for r in output.requirements], gender_diversity_policy=output.gender_diversity_policy.model_copy(deep=True), product_type_alternatives=[a.model_copy(deep=True) for a in output.product_type_alternatives])
            except Exception as exc:
                if attempt:
                    raise
                feedback = {'error': str(exc)}
        raise RuntimeError('Unreachable extraction state')

    def repair_v7_revision(self, *, input_data, context):
        if search_policy(self.search_policy_version).enabled('bounded_evaluation_recovery'):
            return generate_strategy(self, input_data, context, recovery=True)
        from fashion_recommendation_v2.prompts.search.planning import build_v7_revision_repair_prompt
        prompt = build_v7_revision_repair_prompt(context)
        if search_policy(self.search_policy_version).enabled('scoped_requirements'):
            prompt += plan_rules(self.search_policy_version)
        output = self._generate(system_prompt=prompt, user_input=without_profile(input_data), output_schema=SearchParallelRevisionV7)
        return SearchParallelRevisionV7.model_validate(output.model_dump())

    def observe_category_context(self, raw_items):
        """Augment inspection evidence with actual full paths from retrieved items."""
        from fashion_recommendation_v2.tools.ebay_search import category_gender_scope
        for item in raw_items:
            if not item.category_id_path or not item.category_path:
                continue
            category_id = item.category_id_path.split('|')[-1].strip()
            matches = [c for c in self.category_evidence if c['category_id'] == category_id]
            if not matches:
                matches = [dict(category_id=category_id, category_name=item.category_path.split('|')[-1], example_titles=[])]
                self.category_evidence.extend(matches)
            for entry in matches:
                entry.update(category_path=item.category_path, category_id_path=item.category_id_path, gender_scope=category_gender_scope(item.category_path), scope_evidence=item.category_path)

    def _canonical_proposal(self, proposal):
        if not search_policy(self.search_policy_version).enabled('canonical_proposal_filters'):
            return proposal
        from fashion_recommendation_v2.schemas.search.planning.search_planning import ModelAspectFilter
        filters = [ModelAspectFilter.model_validate(f.model_dump()) for f in proposal.aspect_filters]
        names = [f.name for f in filters]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate canonical model filter names are not allowed.')
        return proposal.model_copy(update={'aspect_filters': filters})

    @staticmethod
    def _convert_aspect_filters(entries: list[AspectFilterEntry]) -> dict[str, list[str] | float]:
        """
        LLM Structured Output용 list 표현을
        runtime aspect_filters dict로 변환한다.
        """
        result: dict[str, list[str] | float] = {}
        for entry in entries:
            if entry.name in {"PriceMin", "PriceMax"}:
                raise ValueError('LLM price filters must use price_constraint with original currency and amounts, not PriceMin/PriceMax aspect entries.')
            has_strings = bool(entry.string_values)
            has_number = entry.numeric_value is not None
            if has_strings and has_number:
                raise ValueError(f'AspectFilterEntry cannot contain both string_values and numeric_value. name={entry.name}')
            if has_number:
                result[entry.name] = entry.numeric_value
            elif has_strings:
                result[entry.name] = list(entry.string_values)
        return result
V7_HARD_TYPE_RULES = """
V7 HARD REQUIREMENTS ARE IMMUTABLE THROUGHOUT SEARCH. Candidate shortage is never
permission to weaken a hard condition. 'trench coat' must remain trench coat, not
just 'coat'. A broad parent category cannot replace the specific hard product type.
Preserve every user-allowed product alternative in resolved_requirements; choose
only the retrieval direction, not a narrower definition of eligible products.
"""
from fashion_recommendation_v2.search.planning_rules import normalized_type

@_preserve_function('validate_alternative_inventory', 'fashion_recommendation_v2.agents.search_brain')
@observed('requirements')
def validate_alternative_inventory(source, result, *, version=None):
    validate_reference_requirements(source, result, version=version)
    if version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.requirement_sources import validate_field_sources
        validate_field_sources(source, result, observe_semantics=version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'})
    elif source.audience_context_v1:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import validate_audience_field_sources
        validate_audience_field_sources(source, result)
    contextual = getattr(result, 'audience_policy_v1', None)
    policy_query = source.audience_context_v1.user_query if contextual and result.gender_diversity_policy.exemption == 'contextual_audience' else source.user_query
    if version == 'v24':
        invalid = [{'field': 'source_text', 'requirement_id': r.requirement_id, 'value': r.source_text} for r in result.requirements if r.source == 'user' and (not r.source_text.strip() or r.source_text not in source.user_query)]
        invalid += [{'field': 'gender_diversity_policy.source_texts', 'value': text} for text in result.gender_diversity_policy.source_texts if not text.strip() or text not in policy_query]
        if invalid:
            raise ValueError('Source evidence is not a contiguous substring of the original request: ' + json.dumps(invalid, ensure_ascii=False) + '. Do not join excerpts with ellipses; use separate source_texts array entries. For a scalar source_text use one contiguous original span. Preserve Stylist text.')
    if version not in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and any((r.source not in {'reference', 'context'} and r.source_text not in source.user_query for r in result.requirements)):
        raise ValueError('Requirement evidence must quote the current request.')
    policy = result.gender_diversity_policy
    if version not in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and any((text not in policy_query for text in policy.source_texts)):
        raise ValueError('Gender policy evidence must quote the current request.')
    explicit_gender = any((r.source == 'user' and r.attribute == 'gender' for r in result.requirements))
    if explicit_gender != (policy.exemption == 'explicit_user_gender'):
        raise ValueError('Explicit user gender and diversity exemption must agree.')
    types = {r.requirement_id: r for r in result.requirements if r.attribute == 'product_type'}
    expected = {(key, normalized_type(v)) for key, r in types.items() for v in (r.value if isinstance(r.value, list) else [r.value])}
    actual = set()
    for alt in result.product_type_alternatives:
        if alt.requirement_id not in types or (version not in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and alt.source_text not in source.user_query):
            raise ValueError('Alternative must reference its product requirement and exact user excerpt.')
        actual.add((alt.requirement_id, normalized_type(alt.value)))
    if actual != expected or len(actual) != len(result.product_type_alternatives):
        raise ValueError('All permitted product alternatives must be retained exactly once in requirements and inventory.')
    if types and {v for _, v in expected} != {normalized_type(v) for v in policy.interpreted_product_types}:
        raise ValueError('Gender policy product alternatives differ from the full requirement inventory.')
from fashion_recommendation_v2.search.planning_rules import validate_specific_product_types
from fashion_recommendation_v2.search.planning_rules import singular_type

@_preserve_function('validate_v8_requirements', 'fashion_recommendation_v2.agents.search_brain')
def validate_v8_requirements(output):
    for r in output.requirements:
        if r.unrestricted and (r.kind != 'soft' or r.evaluation_scope != 'item'):
            raise ValueError('Unrestricted attributes must be soft item-only conditions.')
        if r.kind == 'hard' and r.attribute != 'price' and (r.evaluation_scope != 'search'):
            raise ValueError('Every non-price hard requirement must be in every query.')
from fashion_recommendation_v2.search.planning_rules import validate_v8_query_usage
from fashion_recommendation_v2.search.planning_rules import requirement_alternatives
from fashion_recommendation_v2.search.execution import generate_strategy
from fashion_recommendation_v2.search.execution import _RECOVERY

@_preserve_function('text_timeout', 'fashion_recommendation_v2.agents.search_brain')
def text_timeout(operation, recovery=None):
    # Unknown operations fail closed instead of silently inheriting a 600s wait.
    return TEXT_LIMITS[operation][int(_RECOVERY.get() if recovery is None else recovery)]
from fashion_recommendation_v2.search.execution import call_in_attempt

@_preserve_function('assess_plan', 'fashion_recommendation_v2.agents.search_brain')
@observed('planning')
def assess_plan(brain, source, plan, requirements, review_context, locations):
    from fashion_recommendation_v2.search.semantic_validation import semantic_failure

    def fail(message):
        if brain.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            semantic_failure('query_conditions', message, plan=plan.model_dump(mode='json'))
        else:
            raise ValueError(message)
    from fashion_recommendation_v2.prompts.search.planning import review_prompt
    from fashion_recommendation_v2.schemas.search.planning.search_planning import plan_review_schema
    schema = plan_review_schema(requirements)
    version = getattr(brain, 'search_policy_version', None)
    v16 = search_policy(version).enabled('concise_query_contract')
    proposal = (review_context or {}).get('proposal')
    if v16:
        from fashion_recommendation_v2.schemas.search.planning.search_planning import plan_review_schema_v16_v16 as plan_review_schema_v16
        if version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.contracts import search_schemas
            plan_review_schema_v16 = search_schemas(version, purpose='planning').plan_review_schema_v16
        validate_marketplace_query(plan.query)
        schema = plan_review_schema_v16(requirements, has_revision_intent=bool(proposal), version=version)
    data = {'requirements': [r.model_dump(mode='json') for r in requirements.requirements], 'execution_strings': locations, 'price_conversion': plan.price_conversion.model_dump(mode='json') if plan.price_conversion else None, 'observed_categories': brain.category_evidence, 'revision_intent': proposal}
    prompt = review_prompt(data)
    if v16:
        from fashion_recommendation_v2.search.contracts import search_prompts
        REVIEW_CONTRACT = search_prompts(version).REVIEW_CONTRACT
        if search_policy(version).enabled('code_price_provenance'):
            data['code_price_filters'] = validated_price_filters(plan, requirements)
        data['retrieval_contract'] = retrieval_contract(requirements, version)
        data['validation_feedback'] = (review_context or {}).get('validation_feedback')
        prompt = REVIEW_CONTRACT + '\nCONTEXT\n' + json.dumps(data, ensure_ascii=False)
    if version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        result = code_first_review(brain, source, plan, requirements, review_context, locations, schema)
    else:
        result = brain._generate(system_prompt=prompt, user_input=without_profile(source), output_schema=schema)
    result = schema.model_validate(result.model_dump())
    brain.last_plan_review = result.model_dump(mode='json')
    ids = {r.requirement_id for r in requirements.requirements}
    if search_policy(version).enabled('exact_execution_evidence'):
        validate_usage_evidence(plan, result.usages)
    if version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.planning_rules import validate_execution_sources
        validate_execution_sources(plan, result.usages)
    for usage in result.usages:
        if usage.requirement_id not in ids or not usage.evidence.strip() or usage.evidence not in locations[usage.location]:
            raise ValueError('Invalid usage ID or execution evidence: ' + usage.model_dump_json())
    for violation in [*result.hard_violations, *result.intent_violations]:
        if not violation.evidence.strip() or violation.evidence not in locations[violation.location]:
            raise ValueError('Violation does not quote actual execution evidence: ' + violation.model_dump_json())
    if result.intent_violations and (not proposal):
        raise ValueError('Initial plan has no revision intent to contradict.')
    if result.hard_violations or result.intent_violations:
        fail('Final plan violations: ' + json.dumps({'hard_violations': [v.model_dump() for v in result.hard_violations], 'intent_violations': [v.model_dump() for v in result.intent_violations]}, ensure_ascii=False))
    # Code requires explicit evidence for every hard condition, even if the model
    # omitted both a usage and a violation. Persist the exact ID and execution text.
    required_ids = required_retrieval_ids(requirements, version) if v16 else {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
    missing = [r for r in requirements.requirements if r.requirement_id in required_ids and (not any((u.requirement_id == r.requirement_id and (u.location == "filter" if r.attribute == 'price' else v16 or u.location == "query") for u in result.usages)))]
    if missing:
        violations = [dict(requirement_id=r.requirement_id, violation_type='missing', location="filter" if r.attribute == 'price' else "query", evidence=locations["filter" if r.attribute == 'price' else "query"], reason='Required execution usage was not supplied.') for r in missing]
        brain.last_plan_review['hard_violations'] = violations
        fail('Final plan hard violations: ' + json.dumps(violations, ensure_ascii=False))
    from fashion_recommendation_v2.search.planning_rules import effective_category_scope
    actual_scope = effective_category_scope(plan, brain.category_evidence)
    for requirement in requirements.requirements:
        if requirement.kind != 'hard' or requirement.attribute != 'gender' or requirement.source not in {'user', 'context'}:
            continue
        values = set(requirement.value if isinstance(requirement.value, list) else [requirement.value])
        requested = 'men' if values & {'men', 'male'} and (not values & {'women', 'female'}) else 'women' if values & {'women', 'female'} and (not values & {'men', 'male'}) else None
        opposite = {'men': 'women', 'women': 'men'}.get(requested)
        if opposite and (actual_scope == opposite or result.assessed_audience_scope == opposite):
            violations = [dict(requirement_id=requirement.requirement_id, violation_type='contradiction', location="category" if actual_scope == opposite else "query", evidence=locations["category" if actual_scope == opposite else "query"], reason=f"{("Explicit user" if requirement.source == 'user' else "Contextual product")} audience {requested} conflicts with executed audience {opposite}.")]
            brain.last_plan_review['hard_violations'] = violations
            fail('Final plan hard violations: ' + json.dumps(violations, ensure_ascii=False))
    try:
        validate_specific_product_types(plan, requirements, result.usages, brain.category_evidence, singular=True, semantic_supported=semantic_product_evidence(brain, plan, requirements))
    except ValueError as exc:
        violations = [dict(requirement_id=r.requirement_id, violation_type='contradiction', location="query", evidence=locations["query"], reason=str(exc)) for r in requirements.requirements if r.kind == 'hard' and r.attribute in {'product_type', "category", 'product_group'}]
        brain.last_plan_review['hard_violations'] = violations
        if brain.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            fail('Final plan hard violations: ' + json.dumps(violations, ensure_ascii=False))
        else:
            raise ValueError('Final plan hard violations: ' + json.dumps(violations, ensure_ascii=False)) from exc
    if v16:
        validate_executable_plan(brain, plan, requirements, result.usages)
    else:
        validate_v8_query_usage(requirements, result.usages, max_soft=3)
    return result.usages
from fashion_recommendation_v2.search.execution import text_failure_stage
from fashion_recommendation_v2.search.execution import generate_with_backoff
from fashion_recommendation_v2.search.planning_rules import core_attributes
from fashion_recommendation_v2.search.planning_rules import validate_marketplace_query
from fashion_recommendation_v2.search.planning_rules import retrieval_contract
from fashion_recommendation_v2.search.planning_rules import plan_signature

@_preserve_function('validate_reference_requirements', 'fashion_recommendation_v2.agents.search_brain')
def validate_reference_requirements(source, output, *, version=None):
    """Do not let expanded anchor prose masquerade as explicit hard user intent."""
    reference = source.similarity_reference
    references = [r for r in output.requirements if r.source == 'reference']
    if not reference:
        if references:
            raise ValueError('Reference requirements require supplied similarity_reference facts.')
        return
    facts = [value for values in reference.attributes.values() for value in values]
    reference_forbidden = {'price'} if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else {'product_type', 'price'}
    for r in output.requirements:
        if r.source == 'reference':
            if r.kind != 'soft' or r.unrestricted or r.attribute in reference_forbidden:
                if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    raise ValueError('Inherited reference attributes must be soft and restricted; price cannot be inherited.')
                raise ValueError('Inherited reference attributes must be soft; product_type is the user target, not a reference preference.')
            if version not in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and (not r.source_text.strip() or not any((r.source_text in fact for fact in facts))):
                raise ValueError(f'{r.requirement_id}: reference evidence must quote a supplied known attribute.')
        elif version not in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and r.source == 'user' and (r.source_text not in reference.user_query):
            raise ValueError(f'{r.requirement_id}: user evidence must quote the latest original request; inherited attributes use source=reference and kind=soft.')
    types = [r for r in output.requirements if r.attribute == 'product_type']
    if version not in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and (not types or any((r.source != 'user' or r.kind != 'hard' for r in types))):
        raise ValueError('Known-product similarity requires the requested product_type as hard/user.')

@_preserve_function('validate_requirements', 'fashion_recommendation_v2.agents.search_brain')
@observed('requirements')
def validate_requirements(source, output, version='v16'):
    from fashion_recommendation_v2.agents.stylist_runner import validate_stylist_requirements
    if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.requirements import semantic_key
        validate_stylist_requirements(source, output, semantic_key=semantic_key)
    else:
        validate_stylist_requirements(source, output)
    if version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.requirement_sources import validate_field_sources
        validate_field_sources(source, output, observe_semantics=version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'})
    validate_reference_requirements(source, output, version=version)
    if isinstance(output, ResolvedRequirements):
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import validate_audience_requirements
        audience_context = source.audience_context_v1
        if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.audience_policy import audience_context_v30
            audience_context = audience_context_v30(source)
        validate_audience_requirements(output, audience_context)
    allowed_attributes = USER_ATTRIBUTES
    if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.requirements import NATIVE_ATTRIBUTES
        allowed_attributes = allowed_attributes | NATIVE_ATTRIBUTES
    for r in output.requirements:
        if r.source in {'user', 'reference', 'context'} and r.attribute not in allowed_attributes:
            raise ValueError(f'User-only canonical attribute rule: {r.requirement_id}: use detail for {r.attribute}. Stylist attributes must stay unchanged.')
        if r.unrestricted and (r.kind != 'soft' or r.evaluation_scope != 'item'):
            raise ValueError('Unrestricted conditions must be soft/item.')
        if r.kind == 'hard' and version not in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            expected = 'search' if r.attribute in core_attributes(version) else 'item'
            if r.evaluation_scope != expected:
                raise ValueError(f'{r.requirement_id}: hard {r.attribute} must use {expected} scope; all hard conditions remain mandatory per item.')
    if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.stylist_policy import validate_scopes
        if version in {'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.requirements_policy import validate_resolved_requirements_policy_v58 as validate_resolved
            validate_resolved(output)
        elif version == 'v57':
            from fashion_recommendation_v2.search.requirements_policy import validate_resolved_requirements_policy_v57 as validate_resolved
            validate_resolved(output)
        elif version in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.requirements import SEARCH_ATTRIBUTES_V50
            validate_scopes(output, search_attributes=SEARCH_ATTRIBUTES_V50)
        else:
            validate_scopes(output)
    if search_policy(version).enabled('per_item_evidence_contract'):
        validate_english_requirements(output)
from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids

@_preserve_function('validate_query_usage', 'fashion_recommendation_v2.agents.search_brain')
@observed('planning')
def validate_query_usage(requirements, usages, version='v16', *, source=None):
    if version in {'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.planning_policy import validate_usages_planning_policy_v57 as validate_usages
        validate_usages(requirements, usages)
    from fashion_recommendation_v2.search.semantic_validation import semantic_failure

    def fail(rule, message):
        if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            semantic_failure(rule, message, usages=[u.model_dump(mode='json') for u in usages])
        else:
            raise ValueError(message)
    by_id = {r.requirement_id: r for r in requirements.requirements}
    used = {u.requirement_id for u in usages}
    if used - by_id.keys():
        raise ValueError('Unknown requirement usage ID.')
    supported = {u.requirement_id for u in usages if by_id[u.requirement_id].attribute != 'price' or u.location == "filter"}
    missing = required_retrieval_ids(requirements, version) - supported
    if missing:
        fail('query_conditions', f'Core hard retrieval evidence missing: {sorted(missing)}')
    optional = additional_restrictions(requirements, usages, version)
    if search_policy(version).enabled('exact_execution_evidence'):
        minimum, maximum = additional_condition_bounds(requirements, usages, version=version if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else None)
        if not minimum <= len(optional) <= maximum:
            fail('additional_condition_count', f'V20 query budget: {minimum} to {maximum} independent additional conditions required; found {len(optional)}: {optional}. Use only eligible original requirements.')
    elif len(optional) > MAX_QUERY_RESTRICTIONS:
        raise ValueError(f'V16 query budget: at most ONE noncore hard/soft condition; rebuild instead of accumulating terms. Independent restrictions: {optional}. Keep one and omit the others from retrieval only.')
    from fashion_recommendation_v2.search.planning import verified_similarity_candidates
    optional_reference = {r.requirement_id for r in verified_similarity_candidates(requirements, source)} if version in {'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else set()
    for u in usages:
        r = by_id[u.requirement_id]
        if u.location == "query" and (r.unrestricted or r.attribute == 'avoid_product_type' or (r.kind == 'soft' and r.evaluation_scope == 'item' and (r.requirement_id not in optional_reference))):
            message = 'Negative/item-only soft/unrestricted conditions cannot be query keywords.'
            if r.unrestricted or r.attribute == 'avoid_product_type':
                raise ValueError(message)
            fail('item_soft_query', message)
    # Explicitly reject multiple OR options where exact normalized evidence exists.
    from fashion_recommendation_v2.search.planning_rules import query_covers_alternative
    for rid in used:
        options = [v for k, v in requirement_alternatives(requirements) if k == rid]
        evidence = ' '.join((u.evidence for u in usages if u.requirement_id == rid and u.location == "query"))
        if sum((query_covers_alternative(evidence, v) for v in options)) > 1:
            fail('query_conditions', f'Query must select one OR alternative: {rid}')
from fashion_recommendation_v2.search.planning_rules import additional_restrictions
from fashion_recommendation_v2.search.planning_rules import alternative_targets
from fashion_recommendation_v2.search.planning_rules import strategy_trigger_contract
from fashion_recommendation_v2.search.planning_rules import StrategyChoiceError
from fashion_recommendation_v2.search.planning_rules import strategy_choice_feedback
from fashion_recommendation_v2.search.planning_rules import validate_strategy_choice

@_preserve_function('validate_revision', 'fashion_recommendation_v2.agents.search_brain')
@observed('planning')
def validate_revision(proposal, context, requirements, usages, *, plan=None):
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        validate_strategy_choice(proposal, context)
    targets = set(proposal.target_requirement_ids)
    if not targets <= {u.requirement_id for u in usages}:
        message = 'Target IDs must be supported by actual execution usages.'
        if context.get('search_policy_version') in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.semantic_validation import semantic_failure
            semantic_failure('query_conditions', message)
        else:
            raise ValueError(message)
    causes = context.get('code_diagnoses', [])
    trigger = proposal.revision.trigger
    if trigger == "unused_requirements":
        new_pairs = alternative_targets(requirements, usages) - {(a['requirement_id'], a['value']) for a in context.get('alternative_coverage', []) if a['searched']}
        if not (targets & set(context.get('unused_requirements_after_current', [])) or new_pairs):
            raise ValueError('Unused trigger needs an actually unsearched requirement/alternative.')
    if context.get('search_policy_version') not in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        # V24 already applies the same count-based contract as its response
        # schema above; preserve historical validation for older policies.
        if trigger == 'too_few_results' and proposal.intent.change_type == 'broaden_by_removal' and ('retrieval_shortage' not in causes):
            raise ValueError('Broadening for shortage needs retrieval shortage evidence; a full page with rejections needs a quality/new-direction response.')
        if trigger in {'irrelevant_results', 'too_broad'} and 'relevance_rejection' not in causes:
            raise ValueError('Relevance revision needs observed rejection evidence.')

@_preserve_function('validate_executable_plan', 'fashion_recommendation_v2.agents.search_brain')
@observed('planning')
def validate_executable_plan(brain, plan, requirements, usages):
    """One deterministic final contract for initial plans, revisions and review."""
    validate_marketplace_query(plan.query)
    version = getattr(brain, 'search_policy_version', 'v16')
    validate_query_usage(requirements, usages, version, source=getattr(brain, '_planning_source_v32', None))
    from fashion_recommendation_v2.search.semantic_validation import semantic_call
    if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        semantic_call('query_conditions', validate_specific_product_types, plan, requirements, usages, brain.category_evidence, singular=True, semantic_supported=semantic_product_evidence(brain, plan, requirements))
    else:
        validate_specific_product_types(plan, requirements, usages, brain.category_evidence, singular=True, semantic_supported=semantic_product_evidence(brain, plan, requirements))
    if search_policy(version).enabled('per_item_evidence_contract'):
        # Validate immutable provenance before applying user-only normalization rules.
        if version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            semantic_call('query_conditions', validate_brand_evidence, plan, requirements, usages)
        else:
            validate_brand_evidence(plan, requirements, usages)

@_preserve_function('validate_english_requirements', 'fashion_recommendation_v2.agents.search_brain')
def validate_english_requirements(output):

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for entry in value:
                yield from strings(entry)
        elif isinstance(value, dict):
            for key, entry in value.items():
                yield from strings(key)
                yield from strings(entry)
    for requirement in output.requirements:
        if requirement.source not in {'user', 'reference', 'context'}:
            continue
        data = requirement.model_dump(mode='json')
        for value in (requirement.attribute, *strings(data['value'])):
            if any((c.isalpha() and 'LATIN' not in unicodedata.name(c, '') for c in value)):
                raise ValueError(f'{requirement.requirement_id}: source=user attribute/value must use English. Translate semantic values, preserving exact source_text and every Stylist entry.')

@_preserve_function('validate_brand_evidence', 'fashion_recommendation_v2.agents.search_brain')
def validate_brand_evidence(plan, requirements, usages):
    for requirement in requirements.requirements:
        if requirement.kind != 'hard' or requirement.attribute != 'brand':
            continue
        values = requirement.value if isinstance(requirement.value, list) else [requirement.value]
        # A product category called Polos is not a brand. Current completion exposes
        # no brand-specific category evidence, so brand must be in query or filter.
        evidence = [u.evidence for u in usages if u.requirement_id == requirement.requirement_id and u.location in {"query", "filter"}]
        if not any((re.search(r'(?<!\w)' + re.escape(normalized_type(v)) + r'(?!\w)', normalized_type(e)) for v in values if isinstance(v, str) for e in evidence)):
            raise ValueError(f'Hard brand {requirement.requirement_id} requires the canonical brand in actual query/filter evidence; a garment-type category does not establish brand.')

@_preserve_function('validated_price_filters', 'fashion_recommendation_v2.agents.search_brain')
def validated_price_filters(plan, requirements):
    original = requirements.price_constraint
    expected = {}
    if original is not None:
        if plan.price_constraint != original or plan.price_conversion is None:
            raise ValueError('Final plan must preserve the required code-converted price constraint.')
        if plan.price_conversion.original != original:
            raise ValueError('Price conversion must belong to the original requirement.')
        for key, amount in [("PriceMin", plan.price_conversion.min_amount), ("PriceMax", plan.price_conversion.max_amount)]:
            if amount is not None:
                expected[key] = amount
    actual = {k: v for k, v in plan.aspect_filters.items() if k in {"PriceMin", "PriceMax"}}
    if actual.keys() != expected.keys() or any((Decimal(str(actual[k])) != Decimal(str(v)) for k, v in expected.items())):
        raise ValueError('Final price filters must match the code conversion exactly.')
    return actual

@_preserve_function('validate_usage_evidence', 'fashion_recommendation_v2.agents.search_brain')
def validate_usage_evidence(plan, usages):
    for usage in usages:
        if usage.location == "category" and usage.evidence not in plan.category_ids:
            raise ValueError('Category usage evidence must be a complete selected category ID string, not a label.')
        if usage.location == "filter":
            fragments = {json.dumps({key: value}, ensure_ascii=False)[1:-1] for key, value in plan.aspect_filters.items()}
            if not any((fragment in usage.evidence for fragment in fragments)):
                raise ValueError('Filter usage evidence must quote a complete executed key/value fragment.')
from fashion_recommendation_v2.search.planning_rules import additional_condition_candidates
from fashion_recommendation_v2.search.planning_rules import additional_condition_bounds
from fashion_recommendation_v2.search.planning import planning_constraints
from fashion_recommendation_v2.search.execution import collect_plan_claims

@_preserve_class('PlanReviewOutputError', 'fashion_recommendation_v2.agents.search_brain')
class PlanReviewOutputError(ValueError):
    """Malformed reviewer response, not a rejected or malformed search plan."""

@_preserve_function('semantic_decision_usages', 'fashion_recommendation_v2.agents.search_brain')
def semantic_decision_usages(decision):
    """Code-derived usages; preserve the original review and its fragment array."""
    from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsage_legacy as RequirementUsage
    fragments = getattr(decision, 'evidence_fragments', None)
    if fragments is None:
        fragments = [decision.evidence] if decision.evidence is not None else []
    return [RequirementUsage(requirement_id=decision.requirement_id, location=decision.location, evidence=fragment) for fragment in fragments]

@_preserve_function('validate_semantic_review_response', 'fashion_recommendation_v2.agents.search_brain')
def validate_semantic_review_response(result, schema, questions, plan, locations):
    from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsage_legacy as RequirementUsage
    try:
        result = schema.model_validate(result.model_dump())
        ids = [d.requirement_id for d in result.decisions]
        if len(ids) != len(set(ids)) or set(ids) != set(questions):
            raise ValueError('Answer each requested ID exactly once; no extra or missing IDs.')
        for decision in result.decisions:
            if hasattr(decision, 'evidence_fragments'):
                for fragment in decision.evidence_fragments:
                    if not fragment.strip() or not re.search(r'(?<!\w)' + re.escape(fragment) + r'(?!\w)', plan.query):
                        raise ValueError(f'Query evidence fragment not found at word boundaries: {fragment!r}; repair only the citation.')
                continue
            if decision.evidence is not None:
                if not decision.evidence.strip() or decision.evidence not in locations[decision.location]:
                    raise ValueError('Evidence must quote actual execution text: ' + decision.model_dump_json())
                validate_usage_evidence(plan, [RequirementUsage(requirement_id=decision.requirement_id, location=decision.location, evidence=decision.evidence)])
    except ValueError as exc:
        raise PlanReviewOutputError(f'Invalid semantic review output; keep the SAME execution plan. Repair IDs/evidence only. category evidence must be one selected ID string, not its JSON array. Selected IDs: {plan.category_ids}. Error: {exc}') from exc
    return result

@_preserve_function('code_first_review', 'fashion_recommendation_v2.agents.search_brain')
def code_first_review(brain, source, plan, requirements, review_context, locations, result_schema):
    """Check exact assertions first; ask only unresolved semantic questions.

    This returns the existing review contract so all final hard, price, audience,
    product-specificity, revision and query-budget checks remain in force.
    """
    from fashion_recommendation_v2.search.semantic_validation import experiment_records
    warning_start = len(experiment_records())
    from fashion_recommendation_v2.schemas.search.planning.search_planning import RequirementUsage_legacy as RequirementUsage
    from fashion_recommendation_v2.search.contracts import search_schemas
    from fashion_recommendation_v2.search.contracts import search_prompts
    semantic_review_schema = search_schemas(brain.search_policy_version, purpose='planning').semantic_review_schema
    from pydantic import ValidationError
    from fashion_recommendation_v2.prompts.search.planning import SEMANTIC_REVIEW_V24
    if brain.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        SEMANTIC_REVIEW_V24 = search_prompts(brain.search_policy_version).SEMANTIC_REVIEW_CONTRACT
    from fashion_recommendation_v2.search.planning_rules import effective_category_scope
    brain._semantic_product_evidence = None
    by_id = {r.requirement_id: r for r in requirements.requirements}
    usages, pending, questions = ([], [], {})
    # Serialize once. The prompt and validator share these exact strings,
    # including spaces, Unicode, escaping and numeric representation.
    local_warnings = []
    residual = plan.query
    validated_price_filters(plan, requirements)
    plan.validate_for_execution()
    known_categories = {c['category_id'] for c in brain.category_evidence}
    if not set(plan.category_ids) <= known_categories:
        raise ValueError('Final category IDs must have marketplace evidence.')

    # ============================================================
    # ============================================================
    # Strategy Revision
    def values(r):
        value = r.model_dump(mode='json')['value']
        return value.get('values', []) if isinstance(value, dict) else value if isinstance(value, list) else [value]

    def match(value, text):
        if not isinstance(value, str) or not value.strip():
            return None
        return re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', text, re.I)

    def add(rid, location, evidence):
        usage = RequirementUsage(requirement_id=rid, location=location, evidence=evidence)
        if usage not in usages:
            usages.append(usage)
    for rid, r in by_id.items():
        for value in values(r):
            found = match(value, plan.query)
            if found:
                add(rid, "query", found.group())
                residual = re.sub(r'(?<!\w)' + re.escape(found.group()) + r'(?!\w)', ' ', residual, flags=re.I)
        for key, val in plan.aspect_filters.items():
            # Keep complete original JSON values, including decimals and arrays.
            fragment = json.dumps({key: val}, ensure_ascii=False)[1:-1]
            if r.attribute == 'price' and key in {"PriceMin", "PriceMax"}:
                add(rid, "filter", fragment)
            elif key.casefold() == r.attribute.casefold() and isinstance(val, list):
                if val and all((any((str(option).casefold() == str(v).casefold() for v in values(r))) for option in val)):
                    add(rid, "filter", fragment)
                else:
                    questions[rid] = 'Does the resolved filter option match or contradict the requested value?'
    ambiguous_category = False
    category_map = {c['category_id']: c for c in brain.category_evidence}
    for category_id in plan.category_ids:
        category = category_map[category_id]
        leaf = (category.get('category_path') or category.get('category_name', '')).split('|')[-1]
        matched = False
        for rid, r in by_id.items():
            if r.attribute == 'product_type' and any((singular_type(leaf) == singular_type(v) for v in values(r) if isinstance(v, str))):
                add(rid, "category", category_id)
                matched = True
        if not matched or category.get('gender_scope', 'unknown') == 'unknown':
            ambiguous_category = True
    unverified_filters = [key for key, val in plan.aspect_filters.items() if key not in {"PriceMin", "PriceMax"} and (not any((u.location == "filter" and u.evidence == json.dumps({key: val}, ensure_ascii=False)[1:-1] for u in usages)))]
    for raw in getattr(brain, '_plan_claims', {}).get(plan.query, []):
        claim = RequirementUsage.model_validate(raw)
        try:
            if claim.requirement_id not in by_id:
                raise ValueError('Unknown proposal requirement ID: ' + claim.requirement_id)
            # Resolved filters/categories can replace draft options. Never accept
            # stale evidence; code discovers new exact evidence or asks about it.
            if claim.location != "query" and claim.evidence not in locations[claim.location]:
                if brain.search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    local_warnings.append(dict(claim=claim.model_dump(), reason='stale_execution_evidence'))
                continue
            validate_usage_evidence(plan, [claim])
            if not claim.evidence.strip() or claim.evidence not in locations[claim.location]:
                raise ValueError('Proposal evidence must quote the actual final execution: ' + claim.model_dump_json())
        except ValueError as exc:
            if brain.search_policy_version not in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                # No extraction audit, correction, or classification regeneration in v26.
                raise
            local_warnings.append(dict(claim=claim.model_dump(), reason=str(exc)))
            # Not usage; literal discovery and mandatory final checks still apply.
            continue
        if claim not in usages and claim.requirement_id not in {u.requirement_id for u in usages}:
            pending.append(claim)
            questions[claim.requirement_id] = 'Does this claimed synonym/indirect expression actually support this condition?'
    # Simple audience/connective words are not extra restrictions. All other
    # unaccounted terms need semantic scrutiny, including unclaimed modifiers.
    residual = re.sub(r"\b(?:men|women|mens|womens|s|with|and|for|size)\b", ' ', residual, flags=re.I)
    residual = re.sub(r"[\W_]+", ' ', residual).strip()
    mixed_audience = bool(re.search(r"\bmen(?:'s|s)?\b", plan.query, re.I) and re.search(r"\bwomen(?:'s|s)?\b", plan.query, re.I))
    confirmed_ids = {u.requirement_id for u in usages}
    if ambiguous_category:
        questions['__category__'] = 'Check ONLY selected category compatibility with the requested product and audience. A broad ancestor can coexist with a specific product already established in query/filter; it need not independently prove that specificity. Do not reassess confirmed conditions.'
        for rid, r in by_id.items():
            if rid not in confirmed_ids and r.attribute == 'product_type':
                questions[rid] = 'Does selected leaf category metadata establish this missing specific product type?'
    if residual or unverified_filters or mixed_audience:
        questions['__query__'] = 'Check ONLY unverified query/filter expressions or mixed audience for invented intent or contradictions, including negation of confirmed hard conditions. Report contradiction here; do not repeat decisions for confirmed conditions.'
        # Match direct positive assertions, not negated/contextual phrases. Such
        # residuals are sent for semantic review before these usages can be accepted.
        for rid, r in by_id.items():
            if rid not in confirmed_ids and (not r.unrestricted) and (r.attribute not in {'price', 'avoid_product_type'}) and (not (r.kind == 'soft' and r.evaluation_scope == 'item')):
                questions[rid] = 'Does an unverified synonym/indirect expression support this still-unresolved condition?'
    proposal = (review_context or {}).get('proposal')
    if proposal and (questions or proposal.get('intent', {}).get('change_type') != 'broaden_by_removal'):
        questions['__revision__'] = 'Does the final execution match this revision intent and change type?'
    # Definitive missing conditions fail before any semantic LLM request. A
    # plausible unresolved expression/category is reviewed instead of rejected.
    constraints = planning_constraints(requirements, usages, version=brain.search_policy_version, source=source)
    if not pending and (not residual) and (not ambiguous_category) and (not unverified_filters):
        try:
            validate_query_usage(requirements, usages, brain.search_policy_version, source=source)
        except ValueError as exc:
            raise ValueError(str(exc) + '\ncode_plan_constraints=' + json.dumps(constraints, ensure_ascii=False) + '\nconfirmed_usages=' + json.dumps([u.model_dump() for u in usages], ensure_ascii=False)) from exc
    scope = effective_category_scope(plan, brain.category_evidence)
    decisions = []
    if questions:
        data = {'questions': [{'requirement_id': rid, 'question': question} for rid, question in questions.items()], 'requirements': [r.model_dump(mode='json') for r in requirements.requirements], 'code_plan_constraints': constraints, 'execution_strings': locations, 'confirmed_literal_usages': [u.model_dump() for u in usages], 'unverified_claims': [u.model_dump() for u in pending], 'unverified_query_terms': residual, 'unverified_filters': unverified_filters, 'observed_categories': brain.category_evidence, 'revision_context': review_context}
        if brain.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from copy import deepcopy
            from fashion_recommendation_v2.search.planning_rules import execution_evidence_contract

            def contains_query(value):
                if isinstance(value, dict):
                    return value.get("query", value.get('revised_query')) == plan.query or any((contains_query(v) for v in value.values()))
                return isinstance(value, list) and any((contains_query(v) for v in value))
            received = next((entry for entry in reversed(brain.model_response_history) if contains_query(entry['model_response'])), None)
            data.update(model_response=deepcopy(received['model_response']) if received else None, code_validation={'execution_plan': plan.model_dump(mode='json'), 'field_sources': execution_evidence_contract(plan, query_fragments=brain.search_policy_version in {'v59', 'v60', 'v61'}), 'confirmed_literal_usages': data['confirmed_literal_usages']})
        schema = semantic_review_schema(questions, plan.category_ids)
        try:
            result = brain._generate(system_prompt=SEMANTIC_REVIEW_V24 + '\nCONTEXT\n' + json.dumps(data, ensure_ascii=False), user_input=without_profile(source), output_schema=schema)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise PlanReviewOutputError('Invalid semantic review output; repair the response for the SAME plan: ' + str(exc)) from exc
        result = validate_semantic_review_response(result, schema, questions, plan, locations)
        if brain.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            from fashion_recommendation_v2.search.planning_rules import validate_execution_sources
            validate_execution_sources(plan, [u for d in result.decisions for u in semantic_decision_usages(d)])
        for decision in result.decisions:
            optional_uncertainty = brain.search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and decision.requirement_id in by_id and (by_id[decision.requirement_id].kind == 'soft') and (decision.verdict in {'omitted', 'uncertain'})
            if optional_uncertainty:
                local_warnings.append(dict(decision=decision.model_dump(), reason='optional_condition_unconfirmed'))
            if not optional_uncertainty and (decision.verdict in {'contradicted', 'uncertain'} or (decision.requirement_id.startswith('__') and decision.verdict != 'supported')):
                message = 'Semantic review rejected plan: ' + decision.model_dump_json() + '\ncode_plan_constraints=' + json.dumps(constraints, ensure_ascii=False)
                if brain.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
                    from fashion_recommendation_v2.search.semantic_validation import semantic_failure
                    semantic_failure('query_conditions', message, decision=decision.model_dump(mode='json'))
                else:
                    raise ValueError(message)
            if decision.requirement_id in by_id:
                # A semantic finding supersedes a literal match in a negated or
                # otherwise ambiguous context; never keep a false positive.
                usages = [u for u in usages if u.requirement_id != decision.requirement_id]
                if decision.verdict == 'supported':
                    for usage in semantic_decision_usages(decision):
                        add(usage.requirement_id, usage.location, usage.evidence)
        scope = result.assessed_audience_scope
        decisions = [d.model_dump() for d in result.decisions]
    # Query direction is also available without a reviewer when there is no
    # selected category. Explicit hard-gender conflicts are checked downstream.
    if not questions and scope in {'all', 'unknown'}:
        men = bool(re.search(r"\bmen(?:'s|s)?\b", plan.query, re.I))
        women = bool(re.search(r"\bwomen(?:'s|s)?\b", plan.query, re.I))
        scope = 'men' if men and (not women) else 'women' if women and (not men) else 'all'
    brain.last_semantic_review = {'llm_called': bool(questions), 'questions': questions, 'decisions': decisions, 'code_plan_constraints': constraints}
    if brain.search_policy_version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.search.contracts import get_search_contracts
        record_plan_use = get_search_contracts(brain.search_policy_version).planning_code.record_plan_use
        record_plan_use(brain, plan, requirements, usages)
    try:
        validate_query_usage(requirements, usages, brain.search_policy_version, source=source)
    except ValueError as exc:
        error = ValueError(str(exc) + '\ncode_plan_constraints=' + json.dumps(planning_constraints(requirements, usages), ensure_ascii=False) + '\nconfirmed_usages=' + json.dumps([u.model_dump() for u in usages], ensure_ascii=False))
        if brain.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
            error.confirmed_usages = usages
        raise error from exc
    if brain.search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        brain.last_semantic_review['code_warnings'] = local_warnings
        experiment_warnings = experiment_records()[warning_start:]
        validation = dict(status='passed_with_warnings' if local_warnings or experiment_warnings else 'passed', warnings=local_warnings)
        if experiment_warnings:
            from copy import deepcopy
            validation['experiment_observations'] = deepcopy(experiment_warnings)
        brain.model_response_history.append(dict(operation='SearchPlanValidationV29', model_response=None, code_validation=validation, code_derived=dict(query=plan.query, confirmed_usages=[u.model_dump() for u in usages])))
    brain._semantic_product_evidence = (plan.model_dump_json(), requirements.model_dump_json(), {(d['requirement_id'], d['location'], fragment) for d in decisions for fragment in d.get('evidence_fragments', [d.get('evidence')]) if d['verdict'] == 'supported' and d['requirement_id'] in by_id and (by_id[d['requirement_id']].attribute == 'product_type')})
    return result_schema.model_validate({'usages': [u.model_dump() for u in usages], 'hard_violations': [], 'intent_violations': [], 'assessed_audience_scope': scope})

@_preserve_function('semantic_product_evidence', 'fashion_recommendation_v2.agents.search_brain')
def semantic_product_evidence(brain, plan, requirements):
    if getattr(brain, 'search_policy_version', None) not in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return ()
    evidence = getattr(brain, '_semantic_product_evidence', None)
    if evidence and evidence[:2] == (plan.model_dump_json(), requirements.model_dump_json()):
        return evidence[2]
    return ()
