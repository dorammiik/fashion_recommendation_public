"""Small WSGI JSON API for local prototypes; asynchronous recommendations."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import hmac
import json
import sqlite3
from email.utils import format_datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.cookies import CookieError
from typing import Literal

from pydantic import Field
from pydantic import ValidationError
from fashion_recommendation_v2.schemas.quick_start import QuickStartID
from fashion_recommendation_v2.server.quick_start import QuickStartUnavailable
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference_profile import Identifier
from fashion_recommendation_v2.schemas.preference_profile import UTCDateTime
from fashion_recommendation_v2.storage import StoreConflict
from fashion_recommendation_v2.storage import UserUnavailable
from fashion_recommendation_v2.server.preference_service import csrf_token

COOKIE_NAME = 'fashion_anon'


class EventInput(StrictBaseModel):
    event_id: Identifier
    item_snapshot_id: Identifier
    action: Literal['click', 'like', 'dislike']
    operation: Literal['record', 'cancel', 'correct'] = 'record'
    target_event_id: Identifier | None = None
    occurred_at: UTCDateTime
    csrf_token: str | None = None


class StartSessionInput(StrictBaseModel):
    previous_session_id: Identifier | None = None
    csrf_token: str | None = None


class EndSessionInput(StrictBaseModel):
    session_id: Identifier
    csrf_token: str | None = None


class RecommendationInput(StrictBaseModel):
    quick_start: QuickStartID | None = None
    idempotency_key: Identifier
    user_query: str = Field(min_length=1, max_length=12000)
    previous_request_id: Identifier | None = None
    new_request: bool = False
    personalization_mode: Literal['cold', 'warm'] | None = None
    csrf_token: str | None = None


class ConfirmationInput(StrictBaseModel):
    request_id: Identifier
    kind: Literal['new', 'followup']
    csrf_token: str | None = None


class RequestStatusInput(StrictBaseModel):
    request_id: Identifier
    csrf_token: str | None = None


class PreferenceAPI:
    def __init__(self, service, *, allowed_origins=('http://127.0.0.1:8765',), secure_cookie=True, runtime=None, recommendations=None):
        self.service = service
        self.origins = frozenset(allowed_origins)
        self.secure_cookie = secure_cookie
        self.runtime = runtime
        self.recommendations = recommendations

    def __call__(self, env, start_response):
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff')]
        origin = env.get('HTTP_ORIGIN')
        def respond(status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            start_response(f'{status} {HTTPStatus(status).phrase}', headers + [('Content-Length', str(len(data)))])
            return [data]
        if origin and origin not in self.origins:
            return respond(403, {'error': 'origin_not_allowed'})
        if origin:
            headers.extend([('Access-Control-Allow-Origin', origin), ('Access-Control-Allow-Credentials', 'true'), ('Vary', 'Origin')])
        if env.get('HTTP_SEC_FETCH_SITE') == 'cross-site' and not origin:
            return respond(403, {'error': 'origin_required'})
        method, path = env['REQUEST_METHOD'], env.get('PATH_INFO', '/')
        if method == 'OPTIONS':
            headers.extend([('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
                            ('Access-Control-Allow-Headers', 'Content-Type, X-CSRF-Token')])
            return respond(200, {})
        routes = {('/api/preference/bootstrap', 'POST'), ('/api/preference/sessions', 'POST'),
                  ('/api/preference/sessions/end', 'POST'), ('/api/preference/events', 'POST'),
                  ('/api/preference/profile', 'GET'), ('/health', 'GET'),
                  ('/api/recommendations', 'POST'), ('/api/recommendations/confirm', 'POST'),
                  ('/api/recommendations/status', 'POST')}
        if (path, method) not in routes:
            return respond(404, {'error': 'not_found'})
        try:
            jar = SimpleCookie()
            jar.load(env.get('HTTP_COOKIE', ''))
            cookie = jar[COOKIE_NAME].value if COOKIE_NAME in jar else None
            if path == '/health':
                return respond(200, {'status': 'ok', 'processor_connected': bool(self.runtime and self.runtime.processor),
                                     'scheduler_running': bool(self.runtime and self.runtime.running)})
            raw = b'{}'
            if method == 'POST':
                # JSON beacon requests use Blob(type='application/json') and a body CSRF token.
                if env.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                    return respond(415, {'error': 'application_json_required'})
                length = int(env.get('CONTENT_LENGTH') or 0)
                if length < 0 or length > 65536:
                    return respond(413, {'error': 'body_too_large'})
                raw = env['wsgi.input'].read(length)
                if len(raw) != length:
                    return respond(400, {'error': 'incomplete_body'})
            if path == '/api/preference/bootstrap':
                body = json.loads(raw)
                if body != {}:
                    return respond(422, {'error': 'bootstrap_body_must_be_empty'})
                user, token, created = self.service.bootstrap(cookie)
                if created:
                    value = f'{COOKIE_NAME}={token}; Path=/; Max-Age=7776000; Expires={format_datetime(user.expires_at, usegmt=True)}; HttpOnly; SameSite=Lax'
                    if self.secure_cookie:
                        value += '; Secure'
                    headers.append(('Set-Cookie', value))
                return respond(201 if created else 200, {'user_id': user.user_id,
                    'expires_at': user.expires_at.isoformat(), 'csrf_token': csrf_token(token)})
            user = self.service.authenticate(cookie)
            if method == 'GET':
                with self.service.store() as store:
                    lookup = store.lookup_profile_view(user.user_id, now=self.service.clock())
                    update_job = store.lookup_update_job(user.user_id, now=self.service.clock())
                if lookup.status == 'failed':
                    return respond(503, {'status': 'failed', 'error': 'profile_read_failed'})
                return respond(200, {**lookup.model_dump(mode='json', by_alias=True), 'update_job': update_job})
            schema = {'/api/preference/sessions': StartSessionInput,
                      '/api/preference/sessions/end': EndSessionInput,
                      '/api/preference/events': EventInput,
                      '/api/recommendations': RecommendationInput,
                      '/api/recommendations/confirm': ConfirmationInput,
                      '/api/recommendations/status': RequestStatusInput}[path]
            payload = schema.model_validate_json(raw)
            supplied = env.get('HTTP_X_CSRF_TOKEN') or payload.csrf_token or ''
            if not hmac.compare_digest(supplied.encode(), csrf_token(cookie).encode()):
                return respond(403, {'error': 'invalid_csrf_token'})
            if path.startswith('/api/recommendations'):
                if self.recommendations is None:
                    return respond(503, {'error': 'recommendations_not_connected'})
                if path.endswith('/confirm'):
                    record = self.recommendations.resume(user.user_id, payload.request_id, kind=payload.kind)
                elif path.endswith('/status'):
                    record = self.recommendations.get(user.user_id, payload.request_id)
                else:
                    record = self.recommendations.submit(user.user_id, payload.user_query,
                        previous_request_id=payload.previous_request_id, new_request=payload.new_request,
                        personalization_mode=payload.personalization_mode,
                        idempotency_key=payload.idempotency_key,
                        **({'quick_start': payload.quick_start} if payload.quick_start else {}))
                output = record.state.agent_outputs if record.state else None
                response = (output.recommendation_response or output.blocked_response or output.fallback_response) if output else None
                snapshots = []
                with self.service.store() as store:
                    store.get_user(user.user_id, now=self.service.clock())
                    rows = store.db.execute('SELECT payload FROM snapshots WHERE user_id=? AND request_id=?',
                        (user.user_id, record.request_id)).fetchall()
                    for row in rows:
                        snap = json.loads(row['payload'])
                        snapshots.append({'item_id': snap['item']['item_id'], 'rank': snap['rank'],
                                          'item_snapshot_id': snap['item_snapshot_id']})
                code = 202 if not path.endswith('/status') and record.status in ('queued', 'classifying', 'running') else 200
                return respond(code, {'personalization_mode': record.personalization_mode, 'request_id': record.request_id, 'session_id': record.session_id,
                    'status': record.status, 'question': record.question,
                    'response': response.model_dump(mode='json') if response else None,
                    'item_snapshots': snapshots, 'error_type': record.error_type,
                    'profile_lookup_status': record.state.request.profile_lookup_status if record.state else 'not_requested',
                    'progress': record.progress, 'updated_at': record.updated_at,
                    'resumable': record.resumable, 'recovery_reason': record.recovery_reason})
            if path == '/api/preference/sessions':
                session = self.service.start_session(user.user_id, payload.previous_session_id)
                return respond(201, session.model_dump(mode='json'))
            if path == '/api/preference/sessions/end':
                job = self.service.end_session(user.user_id, payload.session_id)
                return respond(202, {'job_id': job, 'queued': job is not None, 'profile_updated': False})
            return respond(200, self.service.record_event(user.user_id, payload))
        except UserUnavailable:
            return respond(401, {'error': 'bootstrap_required'})
        except StoreConflict:
            return respond(409, {'error': 'invalid_state_or_reference'})
        except QuickStartUnavailable:
            return respond(422, {'error': 'quick_start_data_unavailable'})
        except (ValidationError, ValueError, CookieError):
            return respond(422, {'error': 'invalid_payload'})
        except sqlite3.Error:
            return respond(503, {'error': 'storage_unavailable'})
