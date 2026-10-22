"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- evaluation_execution_v36 ----

"""Integrated v36 call, original-response capture and per-product isolation."""
from copy import deepcopy
from fashion_recommendation_v2.search.contracts import get_search_contracts
import json
s = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
from fashion_recommendation_v2.search.product_evaluation import project
from fashion_recommendation_v2.search.product_evaluation import review_questions
from fashion_recommendation_v2.search.execution import generate_with_backoff
from fashion_recommendation_v2.search.execution import without_profile
from fashion_recommendation_v2.search.contracts import search_prompts

@_preserve_function('evaluate_slots', 'fashion_recommendation_v2.search.evaluation_execution_v36')
def evaluate_slots(brain, input_data, items, context, images):
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
    from fashion_recommendation_v2.schemas.price import PriceConversion
    from fashion_recommendation_v2.tools.price_translate import filter_requirement as evaluate_price_requirement
    version = context.get('search_policy_version', 'v36')
    from fashion_recommendation_v2.search.contracts import search_schemas
    schema_module = search_schemas(version, purpose='product_evaluation')
    schema = schema_module.output_schema(len(items), context)
    mapping = {f'item_{i:02d}': item for i, item in enumerate(items, 1)}
    by_id = {item.item_id: slot for slot, item in mapping.items()}
    images = [i.model_copy(update={'slot_id': by_id[i.item_id]}) for i in images]
    context = {**context, 'slot_mapping': {slot: {'item_id': i.item_id, 'image_url': i.image_url} for slot, i in mapping.items()}}
    if context.get('search_policy_version') in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        context['condition_routing_instructions'] = 'Evaluate ONLY resolved_requirements.requirements, never relation_conditions. For relative_requirement_ids compare actual candidate evidence against anchor_comparison for the same attribute. Missing anchor evidence means unknown, never reinterpret as absolute long. Relation later still evaluates full similarity including length; ownership does not weaken hard admission.'
        context['existing_Q_contract_reminder'] = 'thumbnail_observation_v8.photo_type=person OR unknown requires thum_quality=null AND thum_quality_evidence=null. These two fields assess product_only presentation exclusively. Do not grade a person-worn photograph through those two product-only fields; preserve other Q observations.'
    record = dict(operation=schema.__name__, batch_id=context.get('batch_id'), model_response=None, response_schema=schema.model_json_schema(), code_validation=dict(status='pending'))
    if 'execution_settings' in context:
        record['execution_settings'] = deepcopy(context.pop('execution_settings'))
    brain.model_response_history.append(record)
    try:
        response = generate_with_backoff(brain.llm, version=version, system_prompt=search_prompts(version, purpose='product_evaluation').build_visual_batch_prompt(context), user_input=without_profile(input_data), output_schema=schema, images=images, failure_stage='item_evaluation')
        raw = getattr(response, '_model_response', None)
        raw = deepcopy(raw if raw is not None else response.model_dump(mode='json'))
        record.update(model_response=raw, model_response_text=getattr(response, '_model_response_text', None))
    except Exception as exc:
        capture = getattr(exc, 'response_snapshot', {}) or {}
        record.update(model_response=deepcopy(capture.get('model_response')), model_response_text=capture.get('model_response_text'), response_capture=deepcopy(capture), code_validation=dict(status='failed', errors=[str(exc)], error_type=type(exc).__name__))
        raise
    if not isinstance(raw, dict) or set(raw) != set(schema.model_fields):
        record['code_validation'] = dict(status='failed', errors=['Missing/unknown product slots.'])
        raise ValueError('Missing/unknown product slots.')
    if any((raw[k] is not None for k in raw if k not in mapping)):
        record['code_validation'] = dict(status='failed', errors=['Inactive slots must be null.'])
        raise ValueError('Inactive slots must be null.')
    requirements = ResolvedRequirements.model_validate(context['resolved_requirements'])
    conversion = PriceConversion.model_validate_json(json.dumps(context['price_conversion'])) if context.get('price_conversion') else None
    result = schema_module.ProductBatch(items=[])
    record['code_derived'] = {}
    for slot, item in mapping.items():
        try:
            checks = [evaluate_price_requirement(item, r, conversion) for r in requirements.requirements if r.attribute == 'price']
            analysis, diagnostics = project(raw[slot], item, requirements, conversion, checks, **{'evaluation_policy': get_search_contracts(version).product_evaluation.version} if version in {'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else {})
            if analysis.admission_checks.overall_pass:
                review_observation(brain.llm, analysis, item, requirements, raw, schema, slot)
            result.items.append(analysis)
            record['code_derived'][slot] = dict(attribute_diagnostics=diagnostics, analysis=analysis.model_dump(mode='json'))
        except Exception as exc:
            result._slot_errors[item.item_id] = f'{type(exc).__name__}: {exc}'
    record['code_validation'] = dict(status='failed' if result._slot_errors else 'passed', slot_errors=result._slot_errors)
    return result

@_preserve_function('review_observation', 'fashion_recommendation_v2.search.evaluation_execution_v36')
def review_observation(llm, analysis, item, requirements, raw, schema, slot):
    from fashion_recommendation_v2.schemas.visual_confirmation import VisualConsistencyDecisionV5
    from fashion_recommendation_v2.schemas.visual_confirmation import VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5
    from fashion_recommendation_v2.search.observation_review import observation_hash
    questions = review_questions(analysis)
    target = dict(target_slot=slot, model_response=deepcopy(raw), response_schema=schema.model_json_schema())
    trace = dict(questions=questions, source='llm' if questions else 'code', target=target, target_sha256=observation_hash(item, requirements, target), attempts=[], status='passed')
    analysis.semantic_review = trace
    if not questions:
        return
    review_input = dict(item=item.model_dump(mode='json'), requirements=requirements.model_dump(mode='json'), **target, review_questions=questions)
    if analysis.evaluation_policy in {'v57', 'v59'}:
        # Match the adapter's BaseModel input contract without changing the JSON payload.
        from pydantic import RootModel
        review_input = RootModel[dict](review_input)
    for attempt in range(VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5 + 1):
        original, text = (None, None)
        try:
            decision = generate_with_backoff(llm, version=analysis.evaluation_policy, system_prompt=search_prompts(analysis.evaluation_policy, purpose='product_evaluation').build_review_prompt(), user_input=review_input, output_schema=VisualConsistencyDecisionV5, failure_stage='image_consistency_review_v36')
            original = deepcopy(getattr(decision, '_model_response', None))
            original = original if original is not None else decision.model_dump(mode='json')
            text = getattr(decision, '_model_response_text', None)
            decision = VisualConsistencyDecisionV5.model_validate(original)
            trace['attempts'].append(dict(model_response=original, model_response_text=text, code_validation='passed'))
            trace['status'] = 'passed' if decision.status == 'consistent' else 'failed'
            return
        except Exception as exc:
            capture = deepcopy(getattr(exc, 'response_snapshot', None))
            if capture is None and (original is not None or text is not None):
                capture = dict(model_response=original, model_response_text=text)
            trace['attempts'].append(dict(error=f'{type(exc).__name__}: {exc}', response_capture=capture))
            trace['status'] = 'unavailable'
            if not isinstance(exc, TimeoutError) or attempt == VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5:
                return
            from time import sleep
            sleep(1)
