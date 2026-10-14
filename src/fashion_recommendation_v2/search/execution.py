"""Shared definitions moved unchanged from their former owner."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module


import json
import time
from contextvars import ContextVar
from openai import APIConnectionError
from openai import APITimeoutError
from fashion_recommendation_v2.search.policy import search_policy
from fashion_recommendation_v2.search.policy import search_timeout_seconds
from fashion_recommendation_v2.search.planning_rules import strategy_trigger_contract
from fashion_recommendation_v2.search.planning_rules import StrategyChoiceError
from fashion_recommendation_v2.search.planning_rules import strategy_choice_feedback
from fashion_recommendation_v2.search.planning_rules import validate_strategy_choice
from fashion_recommendation_v2.search.planning import planning_constraints
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchParallelRevisionV7_legacy as SearchParallelRevisionV7
from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v11 as strategy_schema
_RECOVERY = ContextVar('search_recovery_attempt', default=False)
def review_image_consistency_v5(llm, *, item, requirements, observation, review_questions, retry_errors=None,
                                product_target_v26=None):
    """Retry a timed-out text review once, without regenerating image observations."""
    import logging
    import time
    from fashion_recommendation_v2.prompts.search.ranking_observation import VISUAL_CONSISTENCY_V5_CONTRACT
    from fashion_recommendation_v2.schemas.visual_confirmation import VisualConsistencyDecisionV5
    from fashion_recommendation_v2.schemas.visual_confirmation import VISUAL_REVIEW_TIMEOUT_SECONDS_V5
    from fashion_recommendation_v2.schemas.visual_confirmation import VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5
    from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import SearchImageObservationsInputV5
    if not review_questions:
        raise ValueError('Conditional image review requires unresolved code-selected questions.')
    prompt = VISUAL_CONSISTENCY_V5_CONTRACT
    version = None
    if product_target_v26 is None:
        request = SearchImageObservationsInputV5(item=item, resolved_requirements=requirements,
            previous_observation=observation, correction_issues=review_questions)
    else:
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ProductReviewInputV26
        from fashion_recommendation_v2.prompts.search.product_evaluation import search_product_evaluation_v26__build_review_prompt as build_review_prompt
        if product_target_v26['response_schema'].get('title', '').startswith('SearchVisualSlotsV29_'):
            version = 'v29'
            from fashion_recommendation_v2.search.contracts import search_prompts
            build_review_prompt = search_prompts('v29', purpose='product_evaluation').build_review_prompt
        if product_target_v26['response_schema'].get('title', '').startswith('SearchVisualSlotsV32_'):
            version = 'v32'
            from fashion_recommendation_v2.search.contracts import search_prompts
            build_review_prompt = search_prompts('v32', purpose='product_evaluation').build_review_prompt
        if product_target_v26['response_schema'].get('title', '').startswith('SearchVisualSlotsV33_'):
            version = 'v33'
            from fashion_recommendation_v2.search.contracts import search_prompts
            build_review_prompt = search_prompts('v33', purpose='product_evaluation').build_review_prompt
        request = ProductReviewInputV26(item=item, resolved_requirements=requirements,
            **product_target_v26, code_validation=dict(status='passed', review_questions=review_questions))
        prompt = build_review_prompt()
    errors = retry_errors if retry_errors is not None else []
    for attempt in range(VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5 + 1):
        try:
            result = generate_with_backoff(llm, version=version, system_prompt=prompt, user_input=request,
                output_schema=VisualConsistencyDecisionV5, timeout_seconds=search_timeout_seconds(version, VISUAL_REVIEW_TIMEOUT_SECONDS_V5),
                failure_stage='image_consistency_review_v5' if attempt == 0 else 'image_consistency_review_v5_timeout_retry')
            return VisualConsistencyDecisionV5.model_validate(result.model_dump())
        except TimeoutError as exc:
            if attempt == VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5:
                exc.review_retry_errors = list(errors)
                raise
            errors.append(f'TimeoutError: {str(exc) or "Text semantic review timed out."}')
            logging.getLogger(__name__).warning(
                '[v5 review timeout] %s: retry 1/1 in 1s, same observation, limit=%ss; no image regeneration.',
                item.item_id, VISUAL_REVIEW_TIMEOUT_SECONDS_V5)
            time.sleep(1)


def without_profile(source):
    result = source.model_copy(deep=True)
    result.preference_profile = None
    return result


def _strategy_error(context, feedback):
    error = StrategyChoiceError(feedback)
    if context.get('search_policy_version') in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.planning_feedback import plan_feedback
        detail = plan_feedback(error, version=context.get('search_policy_version', 'v49'),
            plan_id=str(context.get('source_attempt_id', context.get('attempt_id', 'strategy_generation'))),
            stage='strategy_validation', context=context)
        error.feedback = {**feedback, 'structured_feedback_v49': detail}
    return error


def generate_strategy(brain, input_data, context, *, recovery):
    from fashion_recommendation_v2.prompts.search.planning import build_visual_strategy_prompt
    from fashion_recommendation_v2.prompts.search.planning import build_v7_revision_repair_prompt
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        choices = strategy_trigger_contract(context)
        context = {**context, 'strategy_trigger_contract': choices, 'expected_triggers': list(choices)}
        if not choices:
            if context.get('_semantic_warning_trace') is not None:
                context['_semantic_warning_trace']['disposition'] = 'skipped_no_supported_direction_or_budget'
            if recovery:
                raise _strategy_error(context, strategy_choice_feedback(context, 'revision.trigger', None))
            return SearchVisualStrategyV7(continue_query=False, revisions=[], issues=[], diagnoses=[],
                decision_reason='No diagnosis-supported next search direction or no remaining budget.')
    from fashion_recommendation_v2.search.contracts import strategy_output_schema
    schema = strategy_output_schema(context, recovery=recovery)
    v13 = search_policy(context.get('search_policy_version')).enabled('code_revision_fields')
    data = {k: v for k, v in context.items() if not k.startswith('_')}
    if search_policy(context.get('search_policy_version')).enabled('compact_strategy_context'):
        # Both first decisions and recovery receive the compact representation.
        added = data.pop('added_candidates', [])
        data['added_candidate_ids'] = data.get('added_candidate_ids', [c['item_id'] for c in added])
        before = data.pop('pool_before', [])
        data['pool_before_ids'] = [c['item_id'] for c in before]
    from fashion_recommendation_v2.search.contracts import build_strategy_decision_prompt
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        data['code_plan_constraints'] = planning_constraints(
            ResolvedRequirements.model_validate(context['resolved_requirements']),
            version=context.get('search_policy_version'), source=input_data)
    prompt = build_strategy_decision_prompt(data, recovery=recovery)
    if context.get('_semantic_warning_trace') is not None:
        context['_semantic_warning_trace']['disposition'] = ('supplied_to_existing_recovery' if recovery
            else 'supplied_to_existing_inspection')
    failure_stage = 'strategy_recovery' if recovery else 'strategy_decision'
    limits = search_policy(context.get('search_policy_version')).strategy_limits
    total_limit = int(sum(limits))
    limit = search_timeout_seconds(context.get('search_policy_version'), limits[1 if recovery else 0])
    deadline = search_timeout_seconds(context.get('search_policy_version'), context.get('_strategy_deadline'))
    if deadline is not None:
        limit = min(limit, deadline - time.monotonic())
    if limit is not None and limit <= 0:
        raise TimeoutError(f'LLM timeout: operation={schema.__name__}; limit_seconds={total_limit}; stage={failure_stage}; reason=round_deadline_exhausted')
    record = None
    try:
        result = generate_with_backoff(brain.llm, version=context.get('search_policy_version'), system_prompt=prompt, user_input=without_profile(input_data),
                                   output_schema=schema, timeout_seconds=limit,
                                   **({'failure_stage': failure_stage} if v13 else {}))
        if context.get('search_policy_version') in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from copy import deepcopy
            original = getattr(result, '_model_response', None)
            record = {'operation': schema.__name__,
                'model_response': deepcopy(original if original is not None else result.model_dump(mode='json')),
                'model_response_text': getattr(result, '_model_response_text', None),
                'code_validation': {'status': 'pending', 'stage': 'strategy_schema', 'errors': []}}
            brain.model_response_history.append(record)
        payload = schema.model_validate(result.model_dump()).model_dump()
    except ValueError as exc:
        if record is not None:
            record['code_validation'].update(status='failed', errors=[str(exc)])
        # Schema enforcement also produces actionable feedback if a client or
        # recorded response returns a now-forbidden trigger/change type.
        if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and hasattr(exc, 'errors'):
            for error in exc.errors():
                field = error['loc'][-1] if error['loc'] else None
                if field in {'trigger', 'change_type'}:
                    path = 'revision.trigger' if field == 'trigger' else 'intent.change_type'
                    feedback = strategy_choice_feedback(context, path, error.get('input'))
                    if record is not None:
                        feedback['review_input'] = deepcopy(record)
                    raise _strategy_error(context, feedback) from exc
        raise
    if record is not None:
        record['code_validation']['status'] = 'passed'
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError(f'LLM timeout: operation={schema.__name__}; limit_seconds={total_limit}; stage={failure_stage}; reason=round_deadline_exhausted')
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        payload = collect_plan_claims(brain, payload)
    branches = [payload] if recovery else payload['revisions']
    for branch in branches:
        branch.setdefault('target_requirement_ids', [])
        if v13:
            branch['revision']['issue_disposition'] = 'correct'
            branch['revision']['preference_evidence_refs'] = []
            # Placeholder until category/filter completion; not a model judgment.
            branch['intent']['changed_dimensions'] = []
    output = (SearchParallelRevisionV7 if recovery else SearchVisualStrategyV7).model_validate(payload)
    if context.get('search_policy_version') in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        for branch in [output] if recovery else output.revisions:
            try:
                validate_strategy_choice(branch, context)
            except StrategyChoiceError as exc:
                raise _strategy_error(context, exc.feedback) from exc
    return output


def call_in_attempt(recovery, function, *args, **kwargs):
    token = _RECOVERY.set(bool(recovery))
    try:
        return function(*args, **kwargs)
    finally:
        _RECOVERY.reset(token)


def text_failure_stage(operation, recovery=None):
    stages = {
        'RequirementsStructureV37': 'requirements_structure',
        'RequirementsClassificationV37': 'requirements_classification',
        'RequirementsStructureV35': 'requirements_structure',
        'RequirementsClassificationV35': 'requirements_classification',
        'RequirementsStructureV31': 'requirements_structure',
        'RequirementsStructureV30': 'requirements_structure',
        'RequirementsClassificationV31': 'requirements_classification',
        'RequirementsClassificationV30': 'requirements_classification',
        'RequirementsStructureV26': 'requirements_structure',
        'RequirementsClassificationV26': 'requirements_classification',
        'SemanticReviewV24': 'plan_validation',
        'SearchInitialPlansV16': 'query_planning',
        'RequirementUsageAssessmentV16': 'plan_validation',
        'RequirementsExtractionV15': 'requirements_extraction', 'RequirementsExtractionV14': 'requirements_extraction', 'RequirementsExtractionV8': 'requirements_extraction',
        'RequirementsExtractionAudienceV1': 'requirements_extraction',
        'RequirementsAuditV7': 'requirements_audit',
        'SearchQueryPlanLLM': 'query_planning',
        'SearchCategorySelection': 'category_selection',
        'FilterOptionSelection': 'filter_selection',
        'RequirementUsageAssessmentV12': 'plan_validation',
    }
    suffix = '_recovery' if (_RECOVERY.get() if recovery is None else recovery) else ''
    return stages[operation] + suffix


def generate_with_backoff(llm, *, version, **kwargs):
    from fashion_recommendation_v2.search.policy import search_image_call_limits
    operation = kwargs['output_schema'].__name__.removesuffix('CanonicalFilters')
    if version in {'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.policy import search_default_model
        from fashion_recommendation_v2.search.policy import search_model_routes
        kwargs['call_model_settings'] = search_model_routes(version).get(operation, {'model': search_default_model(version)})
    image_limits = search_image_call_limits(version, operation)
    if version != 'v56' and not image_limits and search_timeout_seconds(version, 1) is None:
        kwargs['timeout_seconds'] = None
        # Preserve historical timeout handling; v34 image limits are per call,
        # so the shared v32 schema name cannot leak a deadline across releases.
        overrides = getattr(llm, 'operation_timeout_overrides', None)
        if overrides is not None:
            overrides[operation] = kwargs['timeout_seconds']
    kwargs.update(image_limits)
    from fashion_recommendation_v2.search.policy import search_llm_call_ceiling
    ceiling = search_llm_call_ceiling(version)
    if ceiling is not None:
        kwargs['max_call_timeout_seconds'] = ceiling
    try:
        return llm.generate(**kwargs)
    except APIConnectionError as exc:
        if (search_policy(version).enabled('keyed_condition_contract') and not isinstance(exc, APITimeoutError)
                and not (kwargs.get('failure_stage') or '').endswith('_recovery')):
            time.sleep(1.0)
        raise


def collect_plan_claims(brain, payload):
    """Store proposal hints only; execution evidence is rechecked after completion.

    Query-keyed hints never grant acceptance and never replace final filters or
    observed categories. If completion changes a query, deterministic discovery
    and the residual semantic check still apply without stale hints.
    """
    if isinstance(payload, list):
        return [collect_plan_claims(brain, value) for value in payload]
    if not isinstance(payload, dict):
        return payload
    if getattr(brain, 'search_policy_version', None) in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and 'query' in payload and 'stylist_nonuse_reason' in payload:
        if not hasattr(brain, '_stylist_nonuse_v50'):
            brain._stylist_nonuse_v50 = {}
        brain._stylist_nonuse_v50[payload['query']] = payload['stylist_nonuse_reason']
        payload = {k: v for k, v in payload.items() if k != 'stylist_nonuse_reason'}
    v47 = getattr(brain, 'search_policy_version', None) in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}
    result = {key: collect_plan_claims(brain, value) for key, value in payload.items()
              if key != 'requirement_usages' and not (v47 and key == 'stylist_omissions')}
    if v47 and 'stylist_omissions' in payload:
        from copy import deepcopy
        if not hasattr(brain, '_stylist_omissions_v47'):
            brain._stylist_omissions_v47 = {}
        brain._stylist_omissions_v47[payload.get('query', payload.get('revised_query'))] = deepcopy(payload['stylist_omissions'])
    if 'requirement_usages' in payload:
        if not hasattr(brain, '_plan_claims'):
            brain._plan_claims = {}
        brain._plan_claims[payload.get('query', payload.get('revised_query'))] = payload['requirement_usages']
    return result
