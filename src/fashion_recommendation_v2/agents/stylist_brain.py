"""Interpret assigned states, validate references, and retry once on failure."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

from pydantic import Field
import json
from fashion_recommendation_v2.compatibility import STYLIST_VERSION
from fashion_recommendation_v2.compatibility import response_record

from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.stylist import STYLIST_PROMPT
from fashion_recommendation_v2.prompts.stylist import STYLIST_COMPATIBILITY_PROMPT
from fashion_recommendation_v2.schemas.stylist import StylistAgentInput_base as StylistAgentInput
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult


class StylistGenerationInput(StylistAgentInput):
    """Internal correction payload; public input stays unchanged."""

    validation_feedback: list[str] = Field(default_factory=list)


class StylistExecutionError(RuntimeError):
    def __init__(self, *, code: str, message: str, attempts: list[dict]):
        self.code = code
        self.retry_count = len(attempts) - 1
        self.attempts = [dict(attempt) for attempt in attempts]
        super().__init__(f"{code}: {message}")


STYLIST_V3_INTERPRETATION_MODEL = 'gpt-6-luna'


class StylistAgent:
    evaluation_version = STYLIST_VERSION
    def __init__(self, *, llm: StructuredLLM, version=STYLIST_VERSION, profile_lookup=None):
        if version not in {STYLIST_VERSION, "v2", "v3", "v4", "v5", "v6"}:
            raise ValueError("Unsupported Stylist version")
        self.evaluation_version = version
        self.profile_lookup = profile_lookup
        self.llm = llm
        self.generation_attempts: list[dict] = []
        self.response_records: list[dict] = []

    def run(self, input_data: StylistAgentInput) -> StylistResult:
        self.generation_attempts = []
        self.response_records = []
        self.personalization_context = None
        if self.evaluation_version in {"v2", "v3", "v4", "v5", "v6"}:
            return self._run_v2(input_data)
        # Revalidate mutable models before any paid call and detach caller data.
        source = StylistAgentInput.model_validate(input_data.model_dump())
        prompt = STYLIST_PROMPT
        if source.relation_intent and source.relation_intent.relation_type == 'compatibility':
            from fashion_recommendation_v2.relation.relation_evidence import source_definition
            from fashion_recommendation_v2.relation.relation_scoring import policy_context
            prompt += '\n' + STYLIST_COMPATIBILITY_PROMPT + '\n' + json.dumps(dict(
                evidence_sources=source_definition(), relation_policy=policy_context()), ensure_ascii=False)
        feedback: list[str] = []
        for retry in range(2):
            # Each attempt gets a fresh payload; LLM adapters cannot mutate the
            # authoritative input used for reference validation or the next call.
            request = StylistGenerationInput(**source.model_dump(), validation_feedback=feedback)
            code = "api_error"
            raw_result = None
            try:
                response = self.llm.generate(
                    system_prompt=prompt,
                    user_input=request,
                    output_schema=StylistResult,
                )
                raw_result = response_record(response)
                code = "invalid_response"
                if not isinstance(response, StylistResult):
                    raise ValueError("Expected a StylistResult structured response.")
                result = StylistResult.model_validate(response.model_dump()).validate_against(source)
            except Exception as exc:
                # Includes Pydantic parsing failures raised inside the adapter.
                if isinstance(exc, (ValueError, TypeError)):
                    code = "invalid_response"
                message = str(exc) or type(exc).__name__
                self.response_records.append(dict(attempt=retry + 1, correction_of=retry or None,
                    state_ids=[s.state_id for s in source.unresolved_states],
                    **(raw_result or response_record(error=exc)),
                    code_validation=dict(status='failed', errors=[message]), applied=False))
                self.generation_attempts.append(dict(
                    retry_count=retry, status="error", code=code,
                    error_type=type(exc).__name__, message=message,
                ))
                if retry == 1:
                    raise StylistExecutionError(
                        code=code, message=message, attempts=self.generation_attempts,
                    ) from exc
                feedback = [message] if code == "invalid_response" else []
            else:
                self.response_records.append(dict(attempt=retry + 1, correction_of=retry or None,
                    state_ids=[s.state_id for s in source.unresolved_states], **raw_result,
                    code_validation=dict(status='passed', errors=[]), applied=True))
                self.generation_attempts.append(dict(retry_count=retry, status="success"))
                return result
        raise AssertionError("unreachable")


    def _run_v2(self, input_data):
        from fashion_recommendation_v2.schemas.stylist import StylistAgentInputV2_v2 as StylistAgentInputV2
        from fashion_recommendation_v2.schemas.stylist import StylistGenerationInputV2_v2 as StylistGenerationInputV2
        from fashion_recommendation_v2.schemas.stylist import StylistCopyV2_v2 as StylistCopyV2
        from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2
        from fashion_recommendation_v2.schemas.stylist import StylistPersonalizationContext
        from fashion_recommendation_v2.prompts.stylist import STYLIST_PROMPT_V2
        from fashion_recommendation_v2.prompts.stylist import STYLIST_COMPATIBILITY_PROMPT_V2
        from fashion_recommendation_v2.stylist_personalization import lookup_context
        from fashion_recommendation_v2.stylist_personalization import GENERATION_ATTEMPTS
        if self.evaluation_version in {'v3', 'v4', 'v5', 'v6'}:
            from fashion_recommendation_v2.schemas.stylist import StylistCopyV3_v3 as StylistCopyV3
            from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3
            from fashion_recommendation_v2.prompts.stylist import STYLIST_PROMPT_V3
            from fashion_recommendation_v2.prompts.stylist import STYLIST_COMPATIBILITY_PROMPT_V3
            copy_schema, result_schema = StylistCopyV3, StylistResultV3
            prompt, compatibility_prompt = STYLIST_PROMPT_V3, STYLIST_COMPATIBILITY_PROMPT_V3
        else:
            copy_schema, result_schema = StylistCopyV2, StylistResultV2
            prompt, compatibility_prompt = STYLIST_PROMPT_V2, STYLIST_COMPATIBILITY_PROMPT_V2
        if self.evaluation_version in {'v4', 'v5', 'v6'}:
            from fashion_recommendation_v2.schemas.stylist import StylistCopyV4
            from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4
            from fashion_recommendation_v2.schemas.stylist import response_schema_v4 as response_schema
            from fashion_recommendation_v2.prompts.stylist import STYLIST_PROMPT_V4
            from fashion_recommendation_v2.prompts.stylist import STYLIST_COMPATIBILITY_PROMPT_V4
            from fashion_recommendation_v2.stylist_personalization import short_reference_input
            from fashion_recommendation_v2.stylist_personalization import resolve_short_references
            copy_schema, result_schema = StylistCopyV4, StylistResultV4
            prompt, compatibility_prompt = STYLIST_PROMPT_V4, STYLIST_COMPATIBILITY_PROMPT_V4
        source = StylistAgentInputV2.model_validate(input_data.model_dump())
        if self.evaluation_version in {'v5', 'v6'}:
            from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5
            from fashion_recommendation_v2.personalization_policy import similarity_input
            result_schema = StylistResultV5
            source = similarity_input(source)
        if self.evaluation_version == 'v6':
            from fashion_recommendation_v2.schemas.stylist import StylistResultV6
            from fashion_recommendation_v2.prompts.stylist import STYLIST_PROMPT_V6
            from fashion_recommendation_v2.prompts.stylist import STYLIST_COMPATIBILITY_PROMPT_V6
            result_schema = StylistResultV6
            prompt, compatibility_prompt = STYLIST_PROMPT_V6, STYLIST_COMPATIBILITY_PROMPT_V6
        ctx = StylistPersonalizationContext(**lookup_context(source, self.llm, self.profile_lookup, version=self.evaluation_version, check_evidence_links=self.evaluation_version in {'v3', 'v4', 'v5', 'v6'}))
        self.personalization_context = ctx.model_copy(deep=True)
        source.profile_lookup_status = 'not_found' if ctx.profile_status == 'not_requested' else ctx.profile_status
        self.response_records.extend(dict(stage='profile_lookup', **a) for a in ctx.lookup_attempts)
        if source.relation_intent and source.relation_intent.relation_type == 'compatibility':
            from fashion_recommendation_v2.relation.relation_evidence import source_definition
            from fashion_recommendation_v2.relation.relation_scoring import policy_context
            prompt += '\n' + compatibility_prompt + '\n' + json.dumps(dict(
                evidence_sources=source_definition(), relation_policy=policy_context()), ensure_ascii=False)
        model_bundle, reference_map, output_schema = ctx.bundle, {}, copy_schema
        if self.evaluation_version in {'v4', 'v5', 'v6'}:
            model_bundle, reference_map = short_reference_input(ctx.bundle)
            if self.evaluation_version == 'v6':
                from fashion_recommendation_v2.schemas.stylist import response_schema as state_response_schema
                output_schema = state_response_schema(reference_map, [s.state_id for s in source.unresolved_states])
            else:
                output_schema = response_schema(reference_map)
        feedback = []
        for attempt in range(GENERATION_ATTEMPTS):
            raw = None
            derived = None
            try:
                request = StylistGenerationInputV2(**source.model_dump(),
                    frozen_preference_bundle=model_bundle, validation_feedback=feedback).model_copy(deep=True)
                response = self.llm.generate(system_prompt=prompt, user_input=request, output_schema=output_schema,
                    **({'call_model_settings': {'model': STYLIST_V3_INTERPRETATION_MODEL}}
                       if self.evaluation_version in {'v3', 'v4', 'v5', 'v6'} else {}))
                raw = response_record(response)
                payload = response.model_dump(mode='json')
                if self.evaluation_version in {'v4', 'v5', 'v6'}:
                    output_schema.model_validate(payload)
                    payload = resolve_short_references(payload, reference_map)
                    derived = payload
                copy = copy_schema.model_validate(payload).validate_against(source, ctx.bundle)
                # Original response stays in response_records; management fields are code-owned.
                result = result_schema(**copy.model_dump(), personalization_context=ctx.model_copy(deep=True))
                result.validate_against(source)
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                record = dict(stage='interpretation', attempt=attempt+1, correction_of=attempt or None,
                    **(raw or response_record(error=exc)),
                    **({'reference_map': reference_map, 'code_derived': derived} if self.evaluation_version in {'v4', 'v5', 'v6'} else {}), code_validation=dict(status='failed', errors=[message]), applied=False)
                self.response_records.append(record)
                self.generation_attempts.append(dict(retry_count=attempt, status='error', message=message))
                if attempt + 1 == GENERATION_ATTEMPTS:
                    raise StylistExecutionError(code='invalid_response' if isinstance(exc, (ValueError, TypeError)) else 'api_error',
                        message=message, attempts=self.generation_attempts) from exc
                feedback = [message] if isinstance(exc, (ValueError, TypeError)) else []
            else:
                self.response_records.append(dict(stage='interpretation', attempt=attempt+1, correction_of=attempt or None,
                    **raw, **({'reference_map': reference_map, 'code_derived': derived} if self.evaluation_version in {'v4', 'v5', 'v6'} else {}), code_validation=dict(status='passed', errors=[]), applied=True))
                self.generation_attempts.append(dict(retry_count=attempt, status='success'))
                return result
