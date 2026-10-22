"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- openai_adapter ----

import asyncio
import inspect
import time
import json
import math
from copy import deepcopy
from contextlib import AsyncExitStack
from typing import TypeVar
from typing import cast
from fashion_recommendation_v2.llm.base import ImageInput
from fashion_recommendation_v2.llm.cost_tracking import CostTracker
from openai import OpenAI
from openai import AsyncOpenAI
from openai import AsyncStream
from openai import APITimeoutError
from openai.types.responses import ResponseStreamEvent
from pydantic import BaseModel
DEFAULT_CALL_TIMEOUT_SECONDS = 90
T = TypeVar("T", bound=BaseModel)
StreamEvent = TypeVar('StreamEvent')

@_preserve_class('_ClosingAsyncStream', 'fashion_recommendation_v2.llm.openai_adapter')
class _ClosingAsyncStream(AsyncStream[StreamEvent]):
    """Own the SDK's SSE and HTTP iterators until they have closed in order.

    AsyncStream.close() closes the response, but the installed SDK leaves its
    nested iterators suspended after a terminal event or [DONE]. Retain those
    iterators and close them before event-loop shutdown can finalize them in
    arbitrary order. Event decoding, typed parsing and API errors stay in the SDK.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._iterator_resources = AsyncExitStack()

    def _iter_events(self):
        chunks = self.response.aiter_bytes()
        self._iterator_resources.push_async_callback(chunks.aclose)
        events = self._decoder.aiter_bytes(chunks)
        self._iterator_resources.push_async_callback(events.aclose)
        return events

    async def close(self):
        try:
            await self._iterator_resources.aclose()
        finally:
            try:
                await self._iterator.aclose()
            finally:
                await super().close()

@_preserve_class('OpenAIStructuredLLM', 'fashion_recommendation_v2.llm.openai_adapter')
class OpenAIStructuredLLM:
    """
    OpenAI Responses API를 사용해
    Pydantic schema에 맞는 structured output을 생성한다.
    """
    call_timeout_ceiling_seconds = DEFAULT_CALL_TIMEOUT_SECONDS

    def __init__(self, model: str="gpt-5.6-sol", operation_settings: dict[str, dict[str, str]] | None=None, operation_timeout_overrides: dict[str, float | None] | None=None, call_timeout_ceiling_seconds: float | None=DEFAULT_CALL_TIMEOUT_SECONDS, unbounded_operations: frozenset[str]=frozenset()):
        if call_timeout_ceiling_seconds is not None and (type(call_timeout_ceiling_seconds) not in (int, float) or not math.isfinite(call_timeout_ceiling_seconds) or call_timeout_ceiling_seconds <= 0):
            raise ValueError('call_timeout_ceiling_seconds must be positive and finite, or None for legacy replay.')
        self.configure_unbounded_operations(unbounded_operations)
        self.call_timeout_ceiling_seconds = call_timeout_ceiling_seconds
        self.operation_timeout_overrides = deepcopy(operation_timeout_overrides or {})
        for operation, seconds in self.operation_timeout_overrides.items():
            if not isinstance(operation, str) or not operation or (seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0)):
                raise ValueError('Invalid per-operation timeout override.')
        self.operation_settings = deepcopy(operation_settings or {})
        for operation, settings in self.operation_settings.items():
            if not operation or set(settings) - {'model', 'reasoning_effort'} or (not isinstance(settings.get('model'), str)) or (not settings['model']):
                raise ValueError('Invalid per-operation model settings.')
            if 'reasoning_effort' in settings and (settings['model'] != 'gpt-6-luna' or settings['reasoning_effort'] not in {'none', 'low'}):
                raise ValueError('Configured reasoning effort requires gpt-6-luna none/low.')
        # Retries belong to the caller so one batch retry means exactly two requests.
        self.client = OpenAI(max_retries=0)
        self.model = model
        self.cost_tracker = CostTracker()

    def request_profile_lookup(self, *, model, operation="RankingProfileLookupV11"):
        """One no-argument tool selection; application code owns authenticated scope."""
        record = self.cost_tracker.start(model, operation)
        started = time.monotonic()
        body = None
        try:
            request = dict(model=model, input=[{'role': 'developer', 'content': 'Call lookup_preference_profile to read the saved profile for this authenticated request. The tool takes no user ID and never generates or updates a profile.'}], tools=[{'type': 'function', 'name': 'lookup_preference_profile', 'description': 'Read the frozen saved profile in the server-owned user scope.', 'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}, 'strict': True}], tool_choice={'type': 'function', 'name': 'lookup_preference_profile'}, parallel_tool_calls=False)
            ceiling = self.call_timeout_ceiling_seconds
            record['call_timeout_ceiling_seconds'] = ceiling
            record['timeout_seconds'] = ceiling
            if ceiling is None:
                raw = self.client.responses.with_raw_response.create(**request)
                body = raw.http_response.json()
                self.cost_tracker.received(record, body, raw.headers.get('x-request-id'))
            else:
                body = asyncio.run(self._timed_profile_lookup(request, ceiling, record))
            calls = [o for o in body.get('output', []) if o.get('type') == 'function_call']
            if body.get('status') != 'completed' or len(calls) != 1 or calls[0].get('name') != 'lookup_preference_profile' or (json.loads(calls[0].get('arguments', 'null')) != {}):
                raise ValueError('Expected exactly one no-argument profile lookup tool call')
            record['elapsed_seconds'] = time.monotonic() - started
            self.cost_tracker.finish(record, 'success')
            return body
        except Exception as exc:
            if isinstance(exc, (TimeoutError, APITimeoutError)):
                exc = TimeoutError(f'LLM timeout: operation={operation}; limit_seconds={self.call_timeout_ceiling_seconds}; elapsed_seconds={time.monotonic() - started:.3f}')
                record['local_timeout_reason'] = 'llm_wall_clock_deadline'
                record['failure_stage'] = operation
            record['elapsed_seconds'] = time.monotonic() - started
            exc.response_snapshot = {'model_response': body}
            self.cost_tracker.finish(record, 'error', exc)
            raise exc
        finally:
            record['elapsed_seconds'] = time.monotonic() - started

    async def _timed_profile_lookup(self, request, timeout_seconds, record):
        async with asyncio.timeout(timeout_seconds):
            async with AsyncOpenAI(max_retries=0, timeout=timeout_seconds, api_key=self.client.api_key, base_url=self.client.base_url, organization=self.client.organization, project=self.client.project) as client:
                raw = await client.responses.with_raw_response.create(**request)
                body = raw.http_response.json()
                self.cost_tracker.received(record, body, raw.headers.get('x-request-id'))
                return body

    def configure_unbounded_operations(self, operations):
        """Explicit run-local opt-in; historical adapters keep all deadlines."""
        allowed = {'StylistCopyV6', 'SearchInitialPlansV16'}
        if isinstance(operations, str) or not isinstance(operations, (set, frozenset)) or (not operations <= allowed):
            raise ValueError('Unsupported unbounded generation operation')
        self.unbounded_operations = frozenset(operations)

    def generate(self, *, system_prompt: str, user_input: BaseModel, output_schema: type[T], images: list[ImageInput] | None=None, timeout_seconds: float | None=None, failure_stage: str | None=None, max_call_timeout_seconds: float | None=None, max_output_tokens: int | None=None, stream_response: bool=False, call_model_settings: dict[str, str] | None=None) -> T:
        if max_output_tokens is not None and (type(max_output_tokens) is not int or max_output_tokens <= 0):
            raise ValueError('max_output_tokens must be a positive integer.')
        content: str | list[dict[str, str]] = user_input.model_dump_json(indent=2)
        if images:
            # Labels associate each photo with its item in a multi-item batch.
            content = [{'type': "input_text", "text": content}]
            for attachment in images:
                content.append({'type': "input_text", "text": json.dumps({**({"slot_id": attachment.slot_id} if attachment.slot_id else {}), "image_for_item_id": attachment.item_id, "image_url": attachment.image_url}, ensure_ascii=False)})
                content.append({'type': "input_image", "image_url": attachment.image_data_url or attachment.image_url})
        operation = output_schema.__name__.removesuffix('CanonicalFilters')
        overrides = getattr(self, 'operation_timeout_overrides', {})
        requested_timeout = timeout_seconds
        # Captured streams carry a per-call deadline. They can share the v32
        # operation name without changing a concurrent historical invocation.
        override_applied = operation in overrides and (not stream_response)
        if override_applied:
            timeout_seconds = overrides[operation]
        # Explicit None is reserved for reproducing historical timeout policies.
        if max_call_timeout_seconds is not None:
            if isinstance(max_call_timeout_seconds, bool) or not math.isfinite(max_call_timeout_seconds) or max_call_timeout_seconds <= 0:
                raise ValueError('max_call_timeout_seconds must be positive and finite')
            timeout_seconds = min((value for value in (timeout_seconds, requested_timeout, max_call_timeout_seconds) if value is not None))
        # Apply after operation overrides and Search's ceiling: neither a None
        # override nor 420s can bypass the common limit. Preserve shorter limits.
        ceiling = self.call_timeout_ceiling_seconds
        if ceiling is not None:
            timeout_seconds = min((v for v in (timeout_seconds, requested_timeout, ceiling) if v is not None))
        unbounded = operation in getattr(self, 'unbounded_operations', ())
        if unbounded and stream_response:
            raise ValueError('Unbounded generation does not support captured streaming')
        if unbounded:
            timeout_seconds = None
        if stream_response and (timeout_seconds is None or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError('Captured streaming requires a positive whole-call deadline.')
        settings = call_model_settings if call_model_settings is not None else getattr(self, 'operation_settings', {}).get(operation, {})
        model = settings.get('model', self.model)
        effort = settings.get('reasoning_effort')
        record = self.cost_tracker.start(model, output_schema.__name__)
        record['call_timeout_ceiling_seconds'] = ceiling
        if unbounded:
            record.update(timeout_policy='explicit_unbounded_generation', timeout_seconds=None, effective_call_timeout_ceiling_seconds=None, requested_timeout_seconds=requested_timeout, requested_max_call_timeout_seconds=max_call_timeout_seconds)
        if override_applied:
            record.update(requested_timeout_seconds=requested_timeout, timeout_seconds=timeout_seconds, timeout_overridden=True)
        if effort is not None:
            record['reasoning_effort'] = effort
        started = time.monotonic()
        if timeout_seconds is not None:
            record['timeout_seconds'] = timeout_seconds
        if failure_stage is not None:
            record['failure_stage'] = failure_stage
        request = dict(model=model, input=[{'role': 'developer', 'content': system_prompt}, {'role': 'user', 'content': content}], text_format=output_schema)
        if max_output_tokens is not None:
            request['max_output_tokens'] = max_output_tokens
            record['max_output_tokens'] = max_output_tokens
        if stream_response:
            record['stream_response'] = True
        if (override_applied or unbounded) and timeout_seconds is None:
            # Per-request SDK override; do not mutate the shared client's timeout
            # while image and bounded text calls may execute concurrently.
            request['timeout'] = None
            record['sdk_timeout_seconds'] = None
        if effort is not None:
            request['reasoning'] = {'effort': effort}
        preserve_response = '_model_response' in output_schema.__private_attributes__
        received = {}
        try:
            if stream_response:
                response = asyncio.run(self._timed_stream_response(request, timeout_seconds, record, received))
            elif timeout_seconds is None:
                raw = self.client.responses.with_raw_response.parse(**request)
                body = raw.http_response.json()
                if preserve_response:
                    received.update(structured_response_snapshot(body))
                self.cost_tracker.received(record, body, raw.headers.get('x-request-id'))
                from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV11_v11 as VisualSlotsV11
                from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import parse_visual_slots_v11
                from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV10_v10 as VisualSlotsV10
                if issubclass(output_schema, (VisualSlotsV11, VisualSlotsV36)):
                    payload = validate_slot_response(body, output_schema, validate_schema=False)
                    result = parse_visual_slots_v11(payload, output_schema)
                    if preserve_response and received:
                        result._model_response_text = received['model_response_text']
                    record['elapsed_seconds'] = time.monotonic() - started
                    record['invalid_slot_count'] = len(result._slot_errors)
                    self.cost_tracker.finish(record, 'partial_validation_error' if result._slot_errors else 'success')
                    return result
                if issubclass(output_schema, VisualSlotsV10):
                    validate_slot_response(body, output_schema)
                response = raw.parse()
            else:
                response = asyncio.run(self._timed_response(request, timeout_seconds, record, **{'response_snapshot': received} if preserve_response else {}))
            record['elapsed_seconds'] = time.monotonic() - started
            from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV11_v11 as VisualSlotsV11
            if isinstance(response, (VisualSlotsV11, VisualSlotsV36)):
                record['invalid_slot_count'] = len(response._slot_errors)
                self.cost_tracker.finish(record, 'partial_validation_error' if response._slot_errors else 'success')
                return response
            if stream_response:
                self.cost_tracker.finish(record, 'success')
                return response
        except Exception as exc:
            record['error_message'] = str(exc)
            causes, seen, cause = ([], {id(exc)}, exc.__cause__ or exc.__context__)
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                causes.append({'error_type': type(cause).__name__, 'message': str(cause)})
                cause = cause.__cause__ or cause.__context__
            record['error_causes'] = causes
            if timeout_seconds is not None and isinstance(exc, APITimeoutError):
                exc = TimeoutError('LLM API request timed out.')
            record['elapsed_seconds'] = time.monotonic() - started
            if isinstance(exc, TimeoutError):
                stage = failure_stage or output_schema.__name__
                exc = TimeoutError(f"LLM timeout: operation={output_schema.__name__}; limit_seconds={timeout_seconds}; stage={stage}; elapsed_seconds={record['elapsed_seconds']:.3f}")
                record['failure_stage'] = stage
                record['error_message'] = str(exc)
                record['local_timeout_reason'] = 'strategy_wall_clock_deadline' if 'Strategy' in output_schema.__name__ or 'ParallelRevision' in output_schema.__name__ else 'llm_wall_clock_deadline'
                if stream_response:
                    received['interruption_reason'] = record['local_timeout_reason']
            if received:
                # Attach AFTER timeout wrapping; otherwise the original received
                # text would be lost on the replacement TimeoutError.
                exc.response_snapshot = received
                if received.get('interruption_reason'):
                    record['interruption_reason'] = received['interruption_reason']
            self.cost_tracker.finish(record, 'error', exc)
            raise exc
        # Pydantic으로 parsing된 결과를 찾는다.
        # Responses API output에서
        for output in response.output:
            if output.type != 'message':
                continue
            for content in output.content:
                if content.type == "output_text" and content.parsed is not None:
                    self.cost_tracker.finish(record, 'success')
                    if preserve_response and received:
                        content.parsed._model_response = received['model_response']
                        content.parsed._model_response_text = received['model_response_text']
                    return cast(T, content.parsed)
        self.cost_tracker.finish(record, 'invalid_output')
        raise RuntimeError("LLM returned no valid structured output.")

    async def _timed_stream_response(self, request, timeout_seconds, record, received):
        """Capture actual text deltas, but admit only a completed response.

        No partial JSON repair, whitespace heuristic, resubmission or extra call.
        The same SDK strict schema is sent as in responses.parse; parsing waits
        for the terminal event so normal partial JSON is never treated as failure.
        """
        from openai.lib._parsing._responses import type_to_text_format_param
        schema = request['text_format']
        wire = {key: value for key, value in request.items() if key != 'text_format'}
        wire.update(stream=True, text={'format': type_to_text_format_param(schema)})
        parts, terminal = ({}, None)
        received.update(model_response=None, model_response_text='', response_status=None)
        try:
            async with asyncio.timeout(timeout_seconds):
                async with AsyncOpenAI(max_retries=0, timeout=timeout_seconds, api_key=self.client.api_key, base_url=self.client.base_url, organization=self.client.organization, project=self.client.project) as client:
                    async with client.responses.with_streaming_response.create(**wire) as raw:
                        stream = await raw.parse(to=_ClosingAsyncStream[ResponseStreamEvent])
                        async with stream:
                            record['request_id'] = stream.response.headers.get('x-request-id')
                            async for event in stream:
                                if event.type == 'response.output_text.delta':
                                    parts.setdefault((event.output_index, event.content_index), []).append(event.delta)
                                elif event.type in {'response.created', 'response.in_progress'}:
                                    received.update(response_id=event.response.id, response_status=event.response.status)
                                    record.update(response_id=event.response.id, response_status=event.response.status)
                                elif event.type in {'response.completed', 'response.incomplete', 'response.failed'}:
                                    terminal = event.response.model_dump(mode='json', exclude_unset=True)
                                    received.update(structured_response_snapshot(terminal))
                                    received.update(response_id=terminal.get('id'), response_status=terminal.get('status'), incomplete_details=terminal.get('incomplete_details'), response_error=terminal.get('error'), response_output=terminal.get('output', []))
                                    self.cost_tracker.received(record, terminal, record.get('request_id'))
                                    break
                                elif event.type == 'error':
                                    raise RuntimeError(f'LLM stream error: {event.code}: {event.message}')
        except BaseException as exc:
            # Includes cancellation, so bytes received before the deadline survive.
            received['interruption_reason'] = 'llm_wall_clock_deadline' if isinstance(exc, (TimeoutError, APITimeoutError)) else 'stream_interrupted'
            raise
        finally:
            received['response_text_parts'] = [dict(output_index=key[0], content_index=key[1], text=''.join(chunks)) for key, chunks in parts.items()]
            if terminal is None:
                text = ''.join(next(iter(parts.values()))) if len(parts) == 1 else ''
                received['model_response_text'] = text
                try:
                    payload = json.loads(text)
                except (ValueError, TypeError):
                    payload = None
                received['model_response'] = payload if isinstance(payload, dict) else None
        if terminal is None:
            received['interruption_reason'] = 'stream_ended_without_terminal_response'
            raise ValueError('LLM stream ended without a terminal response.')
        if terminal.get('status') != 'completed':
            received['interruption_reason'] = (terminal.get('incomplete_details') or {}).get('reason') or (terminal.get('error') or {}).get('code') or terminal.get('status')
            raise ValueError(f"LLM response is not completed: {terminal.get('status')}; reason={received['interruption_reason']}")
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV11_v11 as VisualSlotsV11
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import parse_visual_slots_v11
        payload = validate_slot_response(terminal, schema, validate_schema=False)
        result = parse_visual_slots_v11(payload, schema) if issubclass(schema, (VisualSlotsV11, VisualSlotsV36)) else schema.model_validate(payload)
        if '_model_response' in schema.__private_attributes__:
            result._model_response = received.get('model_response')
            result._model_response_text = received.get('model_response_text')
        return result

    async def _timed_response(self, request, timeout_seconds, record, response_snapshot=None):
        # A read timeout alone resets between reads. Cancellation caps the complete
        # asynchronous request, with SDK retries disabled and no orphan worker.
        async with asyncio.timeout(timeout_seconds):
            async with AsyncOpenAI(max_retries=0, timeout=timeout_seconds, api_key=self.client.api_key, base_url=self.client.base_url, organization=self.client.organization, project=self.client.project) as client:
                raw = await client.responses.with_raw_response.parse(**request)
                body = raw.http_response.json()
                if response_snapshot is not None:
                    response_snapshot.update(structured_response_snapshot(body))
                self.cost_tracker.received(record, body, raw.headers.get('x-request-id'))
                if body.get('status') != 'completed':
                    raise ValueError(f"LLM response is not completed: {body.get('status')}")
                from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV11_v11 as VisualSlotsV11
                from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import parse_visual_slots_v11
                schema = request['text_format']
                if issubclass(schema, (VisualSlotsV11, VisualSlotsV36)):
                    payload = validate_slot_response(body, schema, validate_schema=False)
                    result = parse_visual_slots_v11(payload, schema)
                    if response_snapshot:
                        result._model_response_text = response_snapshot['model_response_text']
                    return result
                response = raw.parse()
                return await response if inspect.isawaitable(response) else response

@_preserve_function('structured_response_snapshot', 'fashion_recommendation_v2.llm.openai_adapter')
def structured_response_snapshot(body):
    """Preserve received structure before SDK parsing, including rejected payloads."""
    texts = [content["text"] for output in body.get('output', []) if output.get('type') == 'message' for content in output.get('content', []) if content.get('type') == "output_text"]
    if len(texts) != 1:
        return {}
    try:
        payload = json.loads(texts[0])
    except (ValueError, TypeError):
        payload = None
    return {'model_response': payload if isinstance(payload, dict) else None, 'model_response_text': texts[0]}

@_preserve_function('validate_slot_response', 'fashion_recommendation_v2.llm.openai_adapter')
def validate_slot_response(body, schema, *, validate_schema=True):
    """Reject incomplete, duplicate-key or multi-payload v10 responses, without retry."""
    if body.get('status') != 'completed':
        raise ValueError(f"Visual slot response is not completed: {body.get('status')}")
    texts = [content["text"] for output in body.get('output', []) if output.get('type') == 'message' for content in output.get('content', []) if content.get('type') == "output_text"]
    if len(texts) != 1:
        raise ValueError('Visual slots require exactly one structured response payload.')

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key in visual slot response: {key}')
            result[key] = value
        return result
    payload = json.loads(texts[0], object_pairs_hook=unique_keys)
    if validate_schema:
        schema.model_validate(payload)
    return payload
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import VisualSlotsV36_v36 as VisualSlotsV36
