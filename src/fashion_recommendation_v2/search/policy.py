"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- policy ----

"""search.policy: definitions relocated without semantic changes."""
from dataclasses import dataclass
from functools import lru_cache
# Live service defaults; historical evals continue to select their frozen version.
DEFAULT_SEARCH_POLICY_VERSION = 'v26'
DEFAULT_SEARCH_MODEL = 'gpt-5.6-luna'

@_preserve_function('search_default_model', 'fashion_recommendation_v2.search.policy')
def search_default_model(version):
    return 'gpt-6-luna' if version in {'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else DEFAULT_SEARCH_MODEL
V53_PRODUCT_EVALUATION_MAX_WORKERS = 40
V58_PRODUCT_EVALUATION_TIMEOUT_SECONDS = 80

@_preserve_function('search_image_worker_limit', 'fashion_recommendation_v2.search.policy')
def search_image_worker_limit(version):
    return V53_PRODUCT_EVALUATION_MAX_WORKERS if version in {'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 20

@_preserve_function('search_image_batch_settings', 'fashion_recommendation_v2.search.policy')
def search_image_batch_settings(version):
    if version in {'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return (1, search_image_worker_limit(version))
    return (1, 20) if version in {'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52'} else (10, 2)

@_preserve_function('search_timeout_seconds', 'fashion_recommendation_v2.search.policy')
def search_timeout_seconds(version, historical_limit):
    """v29+ general deadline policy; v34 image limits are applied separately."""
    return None if version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else historical_limit

@_preserve_function('search_image_timeout_overrides', 'fashion_recommendation_v2.search.policy')
def search_image_timeout_overrides(execution_version):
    """Integrated image deadlines: v28–v33 unbounded, v34 capped at 180s.

    Exact operation names intentionally exclude text consistency review, planning,
    legacy Ranking/Relation backfills, and all historical execution profiles.
    """
    if execution_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return {f'SearchVisualSlotsV36_{n}': V34_IMAGE_TIMEOUT_SECONDS for n in range(1, 11)}
    if execution_version in {'v34', 'v35'}:
        return {name: V34_IMAGE_TIMEOUT_SECONDS for name in V34_IMAGE_OPERATIONS}
    if execution_version in {'v32', 'v33'}:
        return {f'SearchVisualSlots{execution_version.upper()}_{count}': None for count in range(1, 11)}
    if execution_version in {'v28', 'v29', 'v30', 'v31', 'v32', 'v33'}:
        return {f"SearchVisualSlotsV{('29' if execution_version in {'v29', 'v30', 'v31', 'v32', 'v33'} else '26')}_{count}": None for count in range(1, 11)}
    return {}
V34_IMAGE_TIMEOUT_SECONDS = 180
V34_IMAGE_MAX_OUTPUT_TOKENS = 24000
# v34 intentionally uses the unchanged v32 wire/schema and operation names.
V34_IMAGE_OPERATIONS = frozenset((f'SearchVisualSlotsV32_{count}' for count in range(1, 11)))

@_preserve_function('search_image_call_limits', 'fashion_recommendation_v2.search.policy')
def search_image_call_limits(version, operation):
    """Exact image-call scope; text reviews and all historical releases are unchanged."""
    # Release v58 reuses the v57 product schema/operation. Do not change v57
    # itself, or impose this deadline on queueing, downloads or text reviews.
    if version in {'v58', 'v59', 'v60', 'v61'} and operation == 'SearchVisualSlotsV57_1':
        return dict(timeout_seconds=V58_PRODUCT_EVALUATION_TIMEOUT_SECONDS, max_call_timeout_seconds=V58_PRODUCT_EVALUATION_TIMEOUT_SECONDS)
    if version in {'v34', 'v35'} and operation in V34_IMAGE_OPERATIONS or (version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and operation in {f'SearchVisualSlotsV36_{n}' for n in range(1, 11)}):
        return dict(timeout_seconds=V34_IMAGE_TIMEOUT_SECONDS, max_output_tokens=V34_IMAGE_MAX_OUTPUT_TOKENS, stream_response=True)
    return {}

@_preserve_function('search_image_recovery_attempts', 'fashion_recommendation_v2.search.policy')
def search_image_recovery_attempts(execution_profile):
    """Explicit execution profiles disable image resubmission; older recovery stays frozen."""
    return 0 if execution_profile in {'v28', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 1
TEXT_LIMITS = {'RequirementsStructureV37': (20, 20), 'RequirementsClassificationV37': (15, 10), 'RequirementsStructureV35': (20, 20), 'RequirementsClassificationV35': (15, 10), 'RequirementsStructureV31': (20, 20), 'RequirementsStructureV30': (20, 20), 'RequirementsClassificationV31': (15, 10), 'RequirementsClassificationV30': (15, 10), 'RequirementsStructureV26': (20, 20), 'RequirementsClassificationV26': (15, 10), 'SemanticReviewV24': (20, 15), 'SearchInitialPlansV16': (15, 10), 'RequirementUsageAssessmentV16': (20, 15), 'RequirementsExtractionV15': (20, 20), 'RequirementsExtractionV14': (20, 20), 'RequirementsExtractionV8': (20, 20), 'RequirementsAuditV7': (15, 10), 'RequirementsExtractionAudienceV1': (20, 20), 'SearchQueryPlanLLM': (15, 10), 'SearchCategorySelection': (10, 5), 'FilterOptionSelection': (10, 5), 'RequirementUsageAssessmentV12': (20, 15)}

@_preserve_function('search_model_routes', 'fashion_recommendation_v2.search.policy')
def search_model_routes(version):
    """Per-operation overrides; unlisted calls retain the configured base model.

    Initial plan repair uses SearchQueryPlanLLM. Follow-up strategy/recovery
    uses different schemas and must retain the base model.
    """
    if version not in {'v23', 'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return {}
    routes = {'SearchInitialPlansV16': {'model': 'gpt-6-luna', 'reasoning_effort': 'low'}, 'SearchQueryPlanLLM': {'model': 'gpt-6-luna', 'reasoning_effort': 'low'}, 'SearchCategorySelection': {'model': 'gpt-4.1-nano'}, 'FilterOptionSelection': {'model': 'gpt-4.1-nano'}, 'VisualConsistencyDecisionV5': {'model': 'gpt-5.6-luna'}, 'ItemNormalizationResult': {'model': 'gpt-6-luna', 'reasoning_effort': 'none'}}
    if version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        routes['SearchCategorySelection'] = {'model': 'gpt-6-luna'}
        routes['FilterOptionSelection'] = {'model': 'gpt-6-luna'}
    if version in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        routes.pop('ItemNormalizationResult')
    if version in {'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        routes['VisualConsistencyDecisionV5'] = {'model': search_default_model(version)}
    return routes

@_preserve_function('required_audience', 'fashion_recommendation_v2.search.policy')
def required_audience(context):
    if context.get('unused_requirements_after_current') or not context.get('gender_diversity_required') or context.get('attempts_remaining_after_current', 0) <= 0:
        return None
    shares = context['gender_distribution_after']
    missing = [g for g in ('men', 'women') if shares[g] < context.get('gender_minimum_share', 0.2)]
    return min(missing, key=lambda g: (shares[g], g)) if missing else None
CORE_ATTRIBUTES = {'product_type', 'gender', 'color', 'sleeve_length'}
USER_ATTRIBUTES = CORE_ATTRIBUTES | {'pattern', 'size', 'brand', 'price', 'avoid_product_type', 'detail'}
GENDER_MINIMUM_SHARE = 0.05
MAX_QUERY_RESTRICTIONS = 1
_FEATURE_VERSIONS = {'parallel_item_mapping': frozenset(('v22', 'v23', 'v24', 'v25')), 'canonical_proposal_filters': frozenset(('v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'common_item_mapping': frozenset(('v21', 'v22', 'v23', 'v24', 'v25')), 'separate_plan_review': frozenset(('v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'code_revision_fields': frozenset(('v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'compact_strategy_context': frozenset(('v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'keyed_condition_contract': frozenset(('v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'concise_query_contract': frozenset(('v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'per_item_evidence_contract': frozenset(('v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'code_price_provenance': frozenset(('v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'exact_execution_evidence': frozenset(('v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'revision_intent_contract': frozenset(('v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'supported': frozenset(('v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'parallel_queries': frozenset(('v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'scoped_requirements': frozenset(('v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'bounded_evaluation_recovery': frozenset(('v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'three_query_budget': frozenset(('v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16')), 'legacy_visual_inspection': frozenset(('v3', 'v4', 'v5', 'v6')), 'standalone_evaluation_cache': frozenset(('v5',)), 'three_soft_search_terms': frozenset(('v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'legacy_hard_query_coverage': frozenset(('v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15')), 'fixed_slot_output': frozenset(('v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26')), 'legacy_attribute_output': frozenset(('v3', 'v4', 'v5', 'v6', 'v7')), 'legacy_scoped_output': frozenset(('v8',)), 'legacy_parallel_strategy': frozenset(('v6',)), 'unified_attribute_output': frozenset(('v9',)), 'legacy_intent_output': frozenset(('v7',)), 'slots_without_recovery': frozenset(('v10',)), 'model_product_type_binding': frozenset(('v14',))}

@_preserve_class('SearchPolicy', 'fashion_recommendation_v2.search.policy')
@dataclass(frozen=True)
class SearchPolicy:
    version: str | None
    capabilities: frozenset[str]

    def enabled(self, capability):
        # Explicit memberships preserve historical behavior, including v17 evals using v16.
        if capability not in _FEATURE_VERSIONS:
            raise KeyError(f'Unknown Search capability: {capability}')
        return capability in self.capabilities

    @property
    def max_additional_restrictions(self):
        return 3 if self.enabled('exact_execution_evidence') else MAX_QUERY_RESTRICTIONS

    @property
    def min_additional_restrictions(self):
        return 1 if self.enabled('exact_execution_evidence') else 0

    @property
    def mapper_workers(self):
        return 4 if self.enabled('parallel_item_mapping') else 1

    @property
    def query_budget(self):
        return 4 if self.enabled('per_item_evidence_contract') else 3 if self.enabled('three_query_budget') else 5

    @property
    def strategy_limits(self):
        return (30.0, 20.0) if self.enabled('compact_strategy_context') else (15.0, 10.0)

@_preserve_function('search_policy', 'fashion_recommendation_v2.search.policy')
@lru_cache(maxsize=32)
def search_policy(version):
    inherited = 'v26' if version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else version
    return SearchPolicy(version, frozenset((k for k, versions in _FEATURE_VERSIONS.items() if inherited in versions)))

@_preserve_function('search_default_target_candidate_count', 'fashion_recommendation_v2.search.policy')
def search_default_target_candidate_count(version):
    """Collection stopping target, not a pool truncation limit."""
    return 15 if version in {'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else 20

@_preserve_function('search_llm_call_ceiling', 'fashion_recommendation_v2.search.policy')
def search_llm_call_ceiling(version):
    """Per LLM call only; not a Search-stage or marketplace deadline."""
    return 420 if version in {'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else None
