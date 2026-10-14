from fashion_recommendation_v2.module_compat import import_module as _role_module
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from io import BytesIO
import json
from threading import Event
from threading import Thread

import pytest

from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference import ItemSnapshot
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_base as RecommendationResponse
from fashion_recommendation_v2.server.preference_http import PreferenceAPI
from fashion_recommendation_v2.server.preference_runtime import PreferenceRuntime
from fashion_recommendation_v2.server.preference_runtime import UpdateOutput
from fashion_recommendation_v2.server.preference_service import PreferenceService
from fashion_recommendation_v2.storage import StoreConflict
from test_summary_schema import summary_input

T = datetime(2026, 9, 21, tzinfo=timezone.utc)
ORIGIN = 'http://127.0.0.1:8765'


class Client:
    def __init__(self, app):
        self.app, self.cookie, self.csrf = app, '', ''

    def call(self, path, data=None, method='POST', *, csrf=True, origin=ORIGIN, raw=None):
        body = raw if raw is not None else json.dumps(data or {}).encode()
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'CONTENT_TYPE': 'application/json',
               'CONTENT_LENGTH': str(len(body)), 'wsgi.input': BytesIO(body),
               'HTTP_COOKIE': self.cookie, 'HTTP_ORIGIN': origin}
        if csrf:
            env['HTTP_X_CSRF_TOKEN'] = self.csrf
        captured = {}
        def start(status, headers):
            captured.update(status=int(status.split()[0]), headers=dict(headers))
        result = json.loads(b''.join(self.app(env, start)))
        if 'Set-Cookie' in captured['headers']:
            self.cookie = captured['headers']['Set-Cookie'].split(';')[0]
        if 'csrf_token' in result:
            self.csrf = result['csrf_token']
        return captured['status'], result, captured['headers']


@pytest.fixture
def context(tmp_path):
    now = [T]
    service = PreferenceService(tmp_path/'db.sqlite3', artifact_root=tmp_path/'artifacts', clock=lambda: now[0])
    runtime = PreferenceRuntime(service)
    app = PreferenceAPI(service, secure_cookie=True, runtime=runtime)
    client = Client(app)
    status, identity, _ = client.call('/api/preference/bootstrap')
    assert status == 201
    _, session, _ = client.call('/api/preference/sessions')
    yield service, runtime, client, now, identity['user_id'], session['session_id']
    runtime.stop()


def publish(context, source):
    service, _, _, _, user, session = context
    request = service.register_request(user, session, 'shirt')
    response = RecommendationResponse(response_id='rec', intro='eBay 추천입니다', source_notice='eBay',
        outro='완료', recommendations=[dict(item_id=c.item.item_id, rank=i+1,
            title=c.item.title, item_web_url=c.item.item_web_url, image_url=c.item.image_url,
            recommendation_reason='꽃무늬', key_features=[]) for i,c in enumerate(source.candidate_set.candidates)])
    snapshots = service.publish_recommendation(user, request.request_id, source, response)
    return request, response, snapshots


def send_event(context, snapshot, name='e'):
    _, _, client, now, _, _ = context
    now[0] += timedelta(seconds=1)
    payload = {'event_id':name, 'item_snapshot_id':snapshot, 'action':'like', 'occurred_at':now[0].isoformat()}
    return client.call('/api/preference/events', payload), payload


def processor(source):
    # Test-only processor. Real semantic interpretation will be supplied by Preference Agent.
    return UpdateOutput(PreferenceProfile(user_id=source.job.user_id,
        profile_version=(source.previous_profile.profile_version if source.previous_profile else 0)+1,
        processed_event_cursor=source.job.target_cursor, updated_at=source.as_of, as_of=source.as_of), [])


def test_cookie_revisit_fixed_expiration_and_hash(context):
    service, _, client, now, user, _ = context
    cookie = client.cookie
    now[0] += timedelta(days=1)
    status, body, headers = client.call('/api/preference/bootstrap')
    assert status == 200 and body['user_id'] == user
    assert 'Set-Cookie' not in headers and client.cookie == cookie
    with service.store() as store:
        row = store.db.execute('SELECT * FROM cookie_tokens').fetchone()
        assert row['token_hash'] not in cookie
        assert cookie.split('=')[1] not in row['token_hash']
    new = Client(client.app)
    status, other, headers = new.call('/api/preference/bootstrap')
    assert other['user_id'] != user
    for flag in ('HttpOnly', 'SameSite=Lax', 'Max-Age=7776000', 'Secure'):
        assert flag in headers['Set-Cookie']


def test_expired_cookie_cannot_mutate_and_bootstrap_rotates(context):
    _, _, client, now, user, _ = context
    now[0] += timedelta(days=90)
    assert client.call('/api/preference/sessions')[0] == 401
    status, identity, _ = client.call('/api/preference/bootstrap')
    assert status == 201 and identity['user_id'] != user


def test_csrf_origin_validation_and_client_user_forgery(context):
    _, _, client, _, _, _ = context
    assert client.call('/api/preference/sessions', csrf=False)[0] == 403
    assert client.call('/api/preference/sessions', origin='https://evil.example')[0] == 403
    assert client.call('/api/preference/sessions', {'user_id':'other'})[0] == 422
    assert client.call('/api/preference/snapshots', {})[0] == 404
    assert client.call('/api/preference/events', raw=b'broken')[0] == 422
    assert client.call('/api/preference/events', raw=b' ' * 65537)[0] == 413


def test_publish_events_and_idempotency(context, summary_input):
    service, _, client, _, user, _ = context
    request, response, snapshots = publish(context, summary_input)
    again = service.publish_recommendation(user, request.request_id, summary_input, response)
    assert again == snapshots
    (status, body, _), payload = send_event(context, snapshots[0]['item_snapshot_id'])
    assert status == 200 and body['inserted'] and not body['profile_updated']
    assert client.call('/api/preference/events', payload)[1]['inserted'] is False
    assert client.call('/api/preference/events', {**payload, 'event_id':'purchase', 'action':'purchase'})[0] == 422
    other = Client(client.app)
    other.call('/api/preference/bootstrap')
    assert other.call('/api/preference/events', {**payload, 'event_id':'stolen'})[0] == 409
    with service.store() as store:
        assert len(store.events(user, now=service.clock())) == 1


def test_session_end_beacon_and_missing_processor(context, summary_input):
    service, runtime, client, _, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    status, body, _ = client.call('/api/preference/sessions/end',
        {'session_id':session, 'csrf_token':client.csrf}, csrf=False)
    assert status == 202 and body['queued']
    assert runtime.worker_once() == 'processor_not_configured'
    with service.store() as store:
        job = store.db.execute('SELECT * FROM jobs').fetchone()
        assert job['status'] == 'pending' and job['attempts'] == 0
        assert store.lookup_profile(user, now=service.clock()).status == 'not_found'


def test_transition_closes_old_session_without_wait(context, summary_input):
    service, _, client, _, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    status, new, _ = client.call('/api/preference/sessions', {'previous_session_id':session})
    assert status == 201 and new['session_id'] != session
    with service.store() as store:
        assert store.get_session(user, session, now=service.clock()).ended_at is not None
        assert store.db.execute('SELECT status FROM jobs').fetchone()[0] == 'pending'


def test_maintenance_cadence_and_missed_exit(context, summary_input):
    service, runtime, _, now, user, _ = context
    runtime.maintenance_once()
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    assert runtime.maintenance_once() == {}
    now[0] = T+timedelta(seconds=60)
    assert runtime.maintenance_once()['queued']
    assert 'purge' not in runtime.maintenance_once()
    now[0] = T+timedelta(seconds=3600)
    assert 'purge' in runtime.maintenance_once()
    now[0] = T+timedelta(days=90)
    assert runtime.maintenance_once()['purge']['users_deleted'] == 1
    with service.store() as store:
        assert store.db.execute('SELECT COUNT(*) FROM cookie_tokens').fetchone()[0] == 0


def test_worker_success_attempt_history_and_reads(context, summary_input):
    service, runtime, client, _, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    service.end_session(user, session)
    runtime.processor = processor
    assert runtime.worker_once() == 'completed'
    assert client.call('/api/preference/profile', method='GET')[1]['status'] == 'empty'
    with service.store() as store:
        assert store.db.execute('SELECT status FROM job_attempts').fetchone()[0] == 'completed'
        assert store.lookup_profile(user, now=service.clock()).preference_profile.profile_version == 1


def test_worker_failure_then_retry_keeps_attempts(context, summary_input):
    service, runtime, _, _, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    service.end_session(user, session)
    def fail(source):
        raise ValueError('private user text must not be logged')
    runtime.processor = fail
    assert runtime.worker_once() == 'failed'
    runtime.processor = processor
    assert runtime.worker_once() == 'completed'
    with service.store() as store:
        rows = store.db.execute('SELECT status,error_code FROM job_attempts ORDER BY rowid').fetchall()
        assert [r['status'] for r in rows] == ['failed','completed']
        assert rows[0]['error_code'] == 'ValueError'


def test_slow_worker_does_not_block_profile_and_stop_prevents_commit(context, summary_input):
    service, runtime, client, _, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    service.end_session(user, session)
    entered, release = Event(), Event()
    def slow(source):
        entered.set()
        assert release.wait(5)
        return processor(source)
    runtime.processor = slow
    result=[]
    thread=Thread(target=lambda: result.append(runtime.worker_once()))
    thread.start()
    assert entered.wait(2)
    assert runtime.worker_once() == 'busy_or_stopped'
    assert client.call('/api/preference/profile', method='GET')[1]['status'] == 'not_found'
    runtime.stop()
    release.set()
    thread.join(3)
    assert result == ['failed']
    with service.store() as store:
        assert store.lookup_profile(user, now=service.clock()).status == 'not_found'


def test_pending_snapshot_batch_atomic(context, summary_input):
    service, _, _, _, user, _ = context
    request, _, refs = publish(context, summary_input)
    with service.store() as store:
        snap=store.get_snapshot(user, refs[0]['item_snapshot_id'], now=service.clock())
        valid=snap.model_copy(update={'item_snapshot_id':'new-valid'})
        invalid=snap.model_copy(update={'item_snapshot_id':'new-invalid','request_id':'missing'})
        with pytest.raises(StoreConflict):
            store.add_snapshots([valid, invalid], now=service.clock())
        with pytest.raises(StoreConflict):
            store.get_snapshot(user, 'new-valid', now=service.clock())


def test_scheduler_start_stop(context):
    _, runtime, _, _, _, _ = context
    runtime.start()
    assert runtime.running
    runtime.stop()
    assert not runtime.running


def test_v1_migration_preserves_identity_and_rows(tmp_path):
    import sqlite3
    from pathlib import Path
    from fashion_recommendation_v2.storage import PreferenceStore
    schema = Path('src/fashion_recommendation_v2/storage/preference.sql').read_text().split('CREATE TABLE IF NOT EXISTS cookie_tokens')[0]
    path = tmp_path/'v1.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript(schema+'PRAGMA user_version=1;')
        db.execute('INSERT INTO users VALUES (?,?,?)', ('old',T.isoformat(),(T+timedelta(days=90)).isoformat()))
        db.execute("INSERT INTO store_settings VALUES ('mode','online')")
    with PreferenceStore(path) as store:
        assert store.get_user('old', now=T).user_id == 'old'
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 5
        assert store.db.execute('SELECT COUNT(*) FROM job_attempts').fetchone()[0] == 0


def test_expiry_during_processing_cannot_recreate(context, summary_input):
    service, runtime, _, now, user, session = context
    _, _, snapshots = publish(context, summary_input)
    send_event(context, snapshots[0]['item_snapshot_id'])
    service.end_session(user, session)
    def expires(source):
        result = processor(source)
        now[0] = T+timedelta(days=90)
        with service.store() as store:
            store.purge_expired(now=now[0])
        return result
    runtime.processor = expires
    assert runtime.worker_once() == 'failed'
    with service.store() as store:
        for table in ('users','profiles','cookie_tokens','job_attempts'):
            assert store.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_late_event_after_session_end_schedules(context, summary_input):
    service, _, _, _, user, session = context
    _, _, refs = publish(context, summary_input)
    assert service.end_session(user, session) is None
    send_event(context, refs[0]['item_snapshot_id'])
    with service.store() as store:
        assert store.db.execute('SELECT status FROM jobs').fetchone()[0] == 'pending'


def test_new_events_during_processing_remain_pending(context, summary_input):
    service, runtime, _, _, user, session = context
    _, _, refs = publish(context, summary_input)
    send_event(context, refs[0]['item_snapshot_id'])
    service.end_session(user, session)
    def arrivals(source):
        send_event(context, refs[1]['item_snapshot_id'], 'second')
        return processor(source)
    runtime.processor = arrivals
    assert runtime.worker_once() == 'completed'
    with service.store() as store:
        assert store.db.execute('SELECT status FROM jobs').fetchone()[0] == 'pending'
        assert store.lookup_profile(user,now=service.clock()).preference_profile.processed_event_cursor == 1
    runtime.processor = processor
    assert runtime.worker_once() == 'completed'


def test_failed_user_does_not_starve_other_job(context, summary_input):
    service, runtime, _, now, user, session = context
    _, _, refs = publish(context, summary_input)
    send_event(context, refs[0]['item_snapshot_id'])
    service.end_session(user, session)
    with service.store() as store:
        first = store.claim_job(now=now[0])
        store.retry_job(first.job_id,first.lease_token,'failed',now=now[0])
        # Existing store test covers ownership; here a second queued user tests selection fairness.
        second_user = store.create_user(now=now[0])
        store.db.execute("INSERT INTO jobs(job_id,user_id,status,target_cursor) VALUES ('other',?,'pending',0)", (second_user.user_id,))
        assert store.claim_job(now=now[0]).job_id == 'other'


def test_runtime_stops_after_three_failures_and_exposes_state(context,summary_input):
    service,runtime,client,now,user,session=context
    _,_,snapshots=publish(context,summary_input)
    send_event(context,snapshots[0]['item_snapshot_id']);service.end_session(user,session)
    calls=[]
    def fail(source):
        calls.append(source)
        raise ValueError('private text')
    runtime.processor=fail
    assert [runtime.worker_once() for _ in range(3)]==['failed','failed','stopped']
    runtime.maintenance_once()
    assert runtime.worker_once()=='idle'
    assert len(calls)==3
    status,body,_=client.call('/api/preference/profile',method='GET')
    assert status==200
    assert body['update_job']['status']=='stopped'
    assert body['update_job']['cycle_attempts']==3
    assert body['update_job']['last_error']=='ValueError'


def test_exhausted_llm_corrections_are_not_retried_by_outer_worker(context,summary_input):
    from fashion_recommendation_v2.agents.preference_runner import PreferenceRunner
    from fashion_recommendation_v2.agents.preference_runner import PreferenceValidationError
    from fashion_recommendation_v2.schemas.preference_agent import PreferenceBatchOutput
    service,runtime,_,_,user,session=context
    _,_,snapshots=publish(context,summary_input)
    send_event(context,snapshots[0]['item_snapshot_id']);service.end_session(user,session)
    class BadBrain:
        calls=0
        def analyze(self,request):
            self.calls+=1
            return PreferenceBatchOutput(units=[])
    brain=BadBrain();runtime.processor=PreferenceRunner(brain)
    assert runtime.worker_once()=='stopped'
    assert brain.calls==3
    runtime.maintenance_once()
    assert runtime.worker_once()=='idle'
    assert brain.calls==3
    with service.store() as store:
        assert store.db.execute('select status,last_error from jobs').fetchone()[:]==('stopped','PreferenceValidationError')
