"""Real SDK/HTTP parser/pool, with only socket I/O replaced; no API calls."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import asyncio
import gc
import json
from types import SimpleNamespace

import pytest
from openai import APIError
from openai import AsyncOpenAI
from openai import DefaultAsyncHttpxClient
from pydantic import BaseModel
from pydantic import ValidationError

try:
    import httpx2 as httpx
    import httpcore2 as httpcore
    from httpcore2._backends.mock import AsyncMockBackend
    from httpcore2._backends.mock import AsyncMockStream
except ImportError:
    import httpx
    import httpcore
    from httpcore._backends.mock import AsyncMockBackend
    from httpcore._backends.mock import AsyncMockStream

from fashion_recommendation_v2.llm.cost_tracking import read_records
from fashion_recommendation_v2.llm.openai_adapter import OpenAIStructuredLLM
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema


class Payload(BaseModel):
    text: str


RAW_TEXT = '{"text": "수신 원문 그대로"}'
PARTIAL_TEXT = '{"text": "수신 중'


def sse(kind, **fields):
    return ('data: ' + json.dumps(dict(type=kind, sequence_number=0, **fields),
                                ensure_ascii=False) + '\n\n').encode()


def response(text=RAW_TEXT, status='completed'):
    return dict(id='resp_cleanup', object='response', created_at=1,
        model='gpt-5.6-sol', status=status,
        output=[dict(id='msg_cleanup', type='message', role='assistant', status='completed',
            content=[dict(type='output_text', text=text, annotations=[])])],
        usage=dict(input_tokens=100, output_tokens=50, total_tokens=150,
            input_tokens_details=dict(cached_tokens=0), output_tokens_details=dict(reasoning_tokens=0)))


def chunk(data):
    return f'{len(data):x}\r\n'.encode() + data + b'\r\n'


class WireStream(AsyncMockStream):
    """Feed HTTP/1.1 bytes through the actual HTTPX/HTTPCore generator chain."""
    def __init__(self, mode):
        self.mode = mode
        self.partial = PARTIAL_TEXT
        self.stalls = 0
        initial = response(status='in_progress')
        initial.update(output=[], usage=None)
        events = [sse('response.created', response=initial)]
        if mode in {'timeout', 'cancel', 'connection_error', 'early_eof'}:
            events.append(sse('response.output_text.delta', output_index=0,
                              content_index=0, delta=PARTIAL_TEXT))
        elif mode == 'event_error':
            events.append(sse('error', code='server_error', message='offline stream failure', param=None))
        elif mode == 'api_error':
            events.append(b'data: {"error":{"message":"offline API failure"}}\n\n')
        elif mode == 'done_without_terminal':
            events.append(sse('response.output_text.delta', output_index=0, content_index=0, delta=RAW_TEXT))
            events.append(b'data: [DONE]\n\n')
        else:
            text = '{"text": ' if mode == 'malformed' else '{"wrong_field": 1}' if mode == 'invalid_schema' else RAW_TEXT
            events.append(sse('response.output_text.delta', output_index=0, content_index=0, delta=text))
            final = response(text)
            if mode in {'incomplete', 'failed'}:
                final['status'] = mode
                if mode == 'incomplete':
                    final['incomplete_details'] = {'reason': 'max_output_tokens'}
                else:
                    final['error'] = {'code': 'server_error', 'message': 'offline response failure'}
            events.append(sse('response.' + final['status'], response=final))
            if mode == 'done':
                events.append(b'data: [DONE]\n\n')
        # Split UTF-8 and SSE delimiters across network reads, without a fake HTTP response.
        data = b''.join(events)
        wire = chunk(data)
        pieces = [wire[i:i + 43] for i in range(0, len(wire), 43)]
        if mode not in {'timeout', 'cancel', 'connection_error', 'stall_after_terminal'}:
            pieces.append(b'0\r\n\r\n')
        headers = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                   b'Transfer-Encoding: chunked\r\nConnection: close\r\n'
                   b'x-request-id: req_cleanup\r\n\r\n')
        super().__init__([headers, *pieces])

    async def read(self, max_bytes, timeout=None):
        if self._buffer or self._closed:
            return await super().read(max_bytes, timeout)
        self.stalls += 1
        if self.mode == 'timeout':
            await asyncio.sleep(.002)
            self.partial += '  \n'
            return chunk(sse('response.output_text.delta', output_index=0, content_index=0, delta='  \n'))
        if self.mode == 'cancel':
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
        if self.mode == 'connection_error':
            raise httpcore.ReadError('offline broken connection')
        if self.mode == 'stall_after_terminal':
            await asyncio.Future()
        return b''


class WireBackend(AsyncMockBackend):
    def __init__(self, mode):
        super().__init__([])
        self.mode = mode
        self.streams = []

    async def connect_tcp(self, *args, **kwargs):
        stream = WireStream(self.mode)
        self.streams.append(stream)
        return stream


@pytest.fixture
def connection_stack(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_COST_DB', str(tmp_path / 'cost.sqlite3'))
    monkeypatch.setattr('socket.socket.connect', lambda *a, **k: pytest.fail('No network'))
    cleanup_errors, requests, backends, pools, clients = [], [], [], [], []
    new_loop = asyncio.events.new_event_loop

    def tracked_loop():
        loop = new_loop()
        loop.set_exception_handler(lambda loop, context: cleanup_errors.append(context))
        return loop

    monkeypatch.setattr(asyncio.events, 'new_event_loop', tracked_loop)
    mode = ['eof']

    async def capture_request(request):
        requests.append(json.loads(request.content))

    def factory(**kwargs):
        backend = WireBackend(mode[0])
        transport = httpx.AsyncHTTPTransport()
        # Keep the real HTTP transport and connection pool; substitute only socket I/O.
        transport._pool = httpcore.AsyncConnectionPool(network_backend=backend)
        client = AsyncOpenAI(**kwargs, http_client=DefaultAsyncHttpxClient(
            transport=transport, event_hooks={'request': [capture_request]}))
        backends.append(backend)
        pools.append(transport._pool)
        clients.append(client)
        return client

    monkeypatch.setattr('fashion_recommendation_v2.llm.openai_adapter.OpenAI', lambda **kwargs:
        SimpleNamespace(api_key='offline-only', base_url='http://offline.invalid', organization=None, project=None))
    monkeypatch.setattr('fashion_recommendation_v2.llm.openai_adapter.AsyncOpenAI', factory)
    state = SimpleNamespace(llm=OpenAIStructuredLLM(), mode=mode, errors=cleanup_errors,
                            requests=requests, backends=backends, pools=pools, clients=clients)
    yield state
    gc.collect()
    assert not cleanup_errors, [str(c.get('exception')) for c in cleanup_errors]
    assert all(c.is_closed() for c in clients)
    assert all(s._closed for b in backends for s in b.streams)
    assert all(not p.connections and not p._requests for p in pools)


@pytest.mark.parametrize('mode', ['eof', 'done', 'stall_after_terminal', 'incomplete', 'failed',
    'event_error', 'api_error', 'malformed', 'invalid_schema', 'early_eof', 'done_without_terminal',
    'connection_error', 'timeout'])
def test_stream_cleanup_through_real_connection_pool(connection_stack, mode):
    state = connection_stack
    state.mode[0] = mode
    schema = preserve_response_schema(Payload)
    valid = mode in {'eof', 'done', 'stall_after_terminal'}
    # Each generate owns a new event loop, just like production image batches.
    # Repetition exposes finalizer ordering errors that a single call can miss.
    for _ in range(6):
        call = dict(system_prompt='offline', user_input=Payload(text='input'), output_schema=schema,
                    stream_response=True, max_output_tokens=24000, timeout_seconds=.05 if mode == 'timeout' else 2)
        if valid:
            result = state.llm.generate(**call)
            assert result._model_response == json.loads(RAW_TEXT)
            assert result._model_response_text == RAW_TEXT
        else:
            expected_error = {'timeout': TimeoutError, 'connection_error': httpx.ReadError,
                'event_error': RuntimeError, 'api_error': APIError,
                'malformed': json.JSONDecodeError, 'invalid_schema': ValidationError}.get(mode, ValueError)
            with pytest.raises(expected_error) as caught:
                state.llm.generate(**call)
            snapshot = caught.value.response_snapshot
            if mode in {'incomplete', 'failed'}:
                assert snapshot['model_response'] == json.loads(RAW_TEXT)
                assert snapshot['interruption_reason'] == ('max_output_tokens' if mode == 'incomplete' else 'server_error')
            elif mode == 'timeout':
                assert snapshot['model_response_text'] == state.backends[-1].streams[0].partial
                assert snapshot['interruption_reason'] == 'llm_wall_clock_deadline'
            elif mode in {'connection_error', 'early_eof'}:
                assert snapshot['model_response_text'] == PARTIAL_TEXT
            elif mode == 'done_without_terminal':
                assert snapshot['model_response_text'] == RAW_TEXT
                assert snapshot['interruption_reason'] == 'stream_ended_without_terminal_response'
            elif mode in {'malformed', 'invalid_schema'}:
                assert snapshot['model_response_text'] == ('{"text": ' if mode == 'malformed' else '{"wrong_field": 1}')
            else:
                assert snapshot['interruption_reason'] == 'stream_interrupted'
        if mode == 'stall_after_terminal':
            assert state.backends[-1].streams[0].stalls == 0
    records = read_records(state.llm.cost_tracker.path)
    assert len(records) == len(state.requests) == len(state.clients) == 6  # No retry.
    assert all(r['status'] == ('success' if valid else 'error') for r in records)
    assert all(r['stream'] and r['max_output_tokens'] == 24000 for r in state.requests)
    assert all(c.max_retries == 0 for c in state.clients)
    assert not state.errors


def test_cancellation_preserves_capture_and_closes_connection(connection_stack):
    state = connection_stack
    state.mode[0] = 'cancel'
    for _ in range(6):
        received, record = {}, {}
        request = dict(model='gpt-5.6-sol', input='offline', text_format=Payload, max_output_tokens=24000)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(state.llm._timed_stream_response(request, 2, record, received))
        assert received['model_response_text'] == PARTIAL_TEXT
        assert received['model_response'] is None
        assert received['interruption_reason'] == 'stream_interrupted'
    assert len(state.requests) == 6
    assert not state.errors
