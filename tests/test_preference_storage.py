from fashion_recommendation_v2.module_compat import import_module as _role_module
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from fashion_recommendation_v2.schemas.preference import InteractionEvent
from fashion_recommendation_v2.schemas.preference import ItemSnapshot
from fashion_recommendation_v2.schemas.preference import PreferenceEvidence
from fashion_recommendation_v2.schemas.preference import PreferenceRequest
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference_profile import PreferenceWindow
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizedItem
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizationMetadata
from fashion_recommendation_v2.storage.preference import PreferenceStore
from fashion_recommendation_v2.storage.preference import StoreConflict
from fashion_recommendation_v2.storage.preference import UserUnavailable

T = datetime(2026, 9, 21, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path):
    store = PreferenceStore(tmp_path / 'test.sqlite3', artifact_root=tmp_path / 'artifacts')
    user = store.create_user(now=T)
    session = store.create_session(user.user_id, now=T)
    store.add_request(PreferenceRequest(request_id='r', user_id=user.user_id,
        session_id=session.session_id, user_query='shirt', kind='new', created_at=T), now=T)
    snap = ItemSnapshot(item_snapshot_id='snapshot', user_id=user.user_id,
        session_id=session.session_id, request_id='r', recommendation_id='rec', rank=1,
        item=NormalizedItem(item_id='shirt', title='black shirt',
            normalization_metadata=NormalizationMetadata()), captured_at=T)
    store.add_snapshot(snap, now=T)
    yield store, user, session, snap
    store.close()


def event(snap, name='e', action='like', seconds=1, **kw):
    return InteractionEvent(event_id=name, user_id=snap.user_id, session_id=snap.session_id,
        request_id=snap.request_id, recommendation_id=snap.recommendation_id,
        item_id=snap.item.item_id, rank=snap.rank, item_snapshot_id=snap.item_snapshot_id,
        action=action, occurred_at=T+timedelta(seconds=seconds), received_at=T+timedelta(seconds=seconds), **kw)


def add(store, e):
    return store.append_event(e, now=T+timedelta(seconds=100))


def profile(user, job, **kw):
    return PreferenceProfile(user_id=user.user_id, profile_version=1,
        updated_at=T+timedelta(seconds=101), as_of=T+timedelta(seconds=101),
        processed_event_cursor=job.target_cursor, **kw)


def test_event_dedup_and_snapshot_validation(setup):
    store, user, _, snap = setup
    e = event(snap)
    assert add(store, e) == (1, True)
    assert add(store, e.model_copy(update={'received_at': T+timedelta(seconds=90)})) == (1, False)
    with pytest.raises(StoreConflict):
        add(store, e.model_copy(update={'action': 'dislike'}))
    with pytest.raises(StoreConflict):
        add(store, event(snap, 'bad').model_copy(update={'rank': 2}))
    assert len(store.events(user.user_id, now=T+timedelta(seconds=101))) == 1


def test_purchase_online_rejected(setup):
    store, _, _, snap = setup
    with pytest.raises(StoreConflict):
        add(store, event(snap, action='purchase'))


def test_click_cap_and_cancellation(setup):
    store, user, _, snap = setup
    for i in range(5):
        add(store, event(snap, str(i), 'click', i+1))
    add(store, event(snap, 'like', 'like', 8))
    assert len(store.effective_events(user.user_id, now=T+timedelta(seconds=100))) == 4
    add(store, event(snap, 'cancel', 'click', 9, operation='cancel', target_event_id='0'))
    effective = store.effective_events(user.user_id, now=T+timedelta(seconds=100))
    assert {e.event_id for e in effective} == {'1', '2', '3', 'like'}
    assert len(store.events(user.user_id, now=T+timedelta(seconds=100))) == 7


def test_late_reaction_and_cancel_does_not_revive(setup):
    store, user, _, snap = setup
    add(store, event(snap, 'new', 'dislike', 20))
    add(store, event(snap, 'old', 'like', 10))
    assert [e.event_id for e in store.effective_events(user.user_id, now=T+timedelta(seconds=100))] == ['new']
    add(store, event(snap, 'cancel', 'dislike', 30, operation='cancel', target_event_id='new'))
    assert store.effective_events(user.user_id, now=T+timedelta(seconds=100)) == []


def test_late_cancel_target(setup):
    store, user, _, snap = setup
    add(store, event(snap, 'cancel', seconds=20, operation='cancel', target_event_id='target'))
    assert store.effective_events(user.user_id, now=T+timedelta(seconds=100)) == []
    add(store, event(snap, 'target', seconds=10))
    assert store.effective_events(user.user_id, now=T+timedelta(seconds=100)) == []


def test_correction_replaces_target(setup):
    store, user, _, snap = setup
    add(store, event(snap, 'first'))
    add(store, event(snap, 'change', 'dislike', 2, operation='correct', target_event_id='first'))
    assert [e.action for e in store.effective_events(user.user_id, now=T+timedelta(seconds=100))] == ['dislike']


def test_followup_ownership(setup):
    store, user, session, _ = setup
    store.add_request(PreferenceRequest(request_id='follow', user_id=user.user_id,
        session_id=session.session_id, user_query='cheaper', kind='followup', parent_request_id='r', created_at=T), now=T)
    other = store.create_session(user.user_id, now=T)
    with pytest.raises(StoreConflict):
        store.add_request(PreferenceRequest(request_id='bad', user_id=user.user_id,
            session_id=other.session_id, user_query='cheaper', kind='followup', parent_request_id='r', created_at=T), now=T)


def test_job_lease_recovery_and_fencing(setup, tmp_path):
    store, user, session, snap = setup
    add(store, event(snap))
    job_id = store.end_session(user.user_id, session.session_id, now=T+timedelta(seconds=100))
    assert store.enqueue_pending(now=T+timedelta(seconds=100)) == [job_id]
    first = store.claim_job(now=T+timedelta(seconds=101))
    with PreferenceStore(tmp_path/'test.sqlite3') as other:
        assert other.claim_job(now=T+timedelta(seconds=102)) is None
        second = other.claim_job(now=T+timedelta(seconds=402))
        assert second.job_id == first.job_id
        assert second.lease_token != first.lease_token
    with pytest.raises(StoreConflict):
        store.save_profile(profile(user, first), [], job_id=first.job_id,
            lease_token=first.lease_token, expected_version=0, now=T+timedelta(seconds=403))


def test_atomic_profile_and_events_arriving_during_job(setup):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    add(store, event(snap, 'later', 'click', 2))
    p = profile(user, job)
    assert store.lookup_profile(user.user_id, now=T).status == 'not_found'
    store.save_profile(p, [], job_id=job.job_id, lease_token=job.lease_token,
                       expected_version=0, now=T+timedelta(seconds=102))
    assert store.lookup_profile(user.user_id, now=T+timedelta(seconds=103)).status == 'empty'
    next_job = store.claim_job(now=T+timedelta(seconds=104))
    assert next_job.target_cursor == 2
    with pytest.raises(StoreConflict):
        store.save_profile(p, [], job_id=next_job.job_id, lease_token=next_job.lease_token,
                           expected_version=0, now=T+timedelta(seconds=105))
    assert store.lookup_profile(user.user_id, now=T+timedelta(seconds=106)).preference_profile.profile_version == 1


def test_missing_evidence_rolls_back(setup):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    p = profile(user, job, **{'global': {'features': [{'attribute':'color','value':'black','evidence_refs':['missing']}]}})
    with pytest.raises(StoreConflict):
        store.save_profile(p, [], job_id=job.job_id, lease_token=job.lease_token,
                           expected_version=0, now=T+timedelta(seconds=102))
    assert store.lookup_profile(user.user_id, now=T+timedelta(seconds=103)).status == 'not_found'
    assert store._job(job.job_id).status == 'running'


def test_profile_with_evidence_and_corruption_status(setup):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    evidence = PreferenceEvidence(evidence_id='proof', user_id=user.user_id, event_id='e',
        item_snapshot_id=snap.item_snapshot_id, source_action='like', attribute='color',
        value='black', metadata_fields=['title'], explanation='Title says black')
    p = profile(user, job, **{'global': {'features': [{'attribute':'color','value':'black','evidence_refs':['proof']}]}})
    store.save_profile(p, [evidence], job_id=job.job_id, lease_token=job.lease_token,
                       expected_version=0, now=T+timedelta(seconds=102))
    found = store.lookup_profile(user.user_id, now=T+timedelta(seconds=103))
    assert found.status == 'available'
    assert '"global":' in found.preference_profile.model_dump_json(by_alias=True)
    store.db.execute("UPDATE profiles SET payload='broken'")
    assert store.lookup_profile(user.user_id, now=T+timedelta(seconds=104)).status == 'failed'


def test_expiry_cascade_and_artifact_retry(setup, tmp_path, monkeypatch):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    root = tmp_path/'artifacts'
    root.mkdir()
    log = root/'user.log'
    log.write_text('private')
    store.register_artifact(user.user_id, 'user.log', now=T)
    real_unlink = Path.unlink
    def fail(path, *args, **kwargs):
        if path == log:
            raise PermissionError('test failure')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail)
    result = store.purge_expired(now=user.expires_at)
    assert result['users_deleted'] == 1
    assert result['failed_artifact_ids']
    for table in ('users','sessions','requests','snapshots','events','profiles','evidence','jobs'):
        assert store.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert store.lookup_profile(user.user_id, now=user.expires_at).status == 'not_found'
    with pytest.raises(UserUnavailable):
        add(store, event(snap, 'late'))
    with pytest.raises(StoreConflict):
        store.save_profile(profile(user, job), [], job_id=job.job_id,
            lease_token=job.lease_token, expected_version=0, now=user.expires_at)
    monkeypatch.setattr(Path, 'unlink', real_unlink)
    assert store.purge_expired(now=user.expires_at)['files_deleted'] == 1
    assert not log.exists()
    assert store.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 0


def test_expired_user_before_cleanup(setup):
    store, user, _, snap = setup
    with pytest.raises(UserUnavailable):
        store.append_event(event(snap), now=user.expires_at)
    assert store.lookup_profile(user.user_id, now=user.expires_at).status == 'not_found'


def test_safe_file_scope(setup, tmp_path):
    store, user, _, _ = setup
    outside = tmp_path/'outside'
    outside.write_text('keep')
    with pytest.raises(StoreConflict):
        store.register_artifact(user.user_id, '../outside', now=T)
    assert outside.read_text() == 'keep'


def test_strict_time_and_score_contract():
    with pytest.raises(ValidationError):
        PreferenceProfile(user_id='u', profile_version=1, updated_at=datetime(2026,1,1),
                          as_of=T, processed_event_cursor=0)
    with pytest.raises(ValidationError):
        PreferenceWindow(positive_mass=1.0, score=0.9, strength='high')
    assert PreferenceWindow(positive_mass=1.0, score=0.5, strength='medium').score == .5


def test_equal_timestamp_cancel_respects_target(setup):
    store, user, _, snap = setup
    add(store, event(snap, 'z-target'))
    add(store, event(snap, 'a-cancel', operation='cancel', target_event_id='z-target'))
    assert store.effective_events(user.user_id, now=T+timedelta(seconds=100)) == []


def test_cross_user_snapshot_and_event_access(setup):
    store, user, _, snap = setup
    other = store.create_user(now=T)
    with pytest.raises(StoreConflict):
        store.get_snapshot(other.user_id, snap.item_snapshot_id, now=T)
    with pytest.raises(StoreConflict):
        add(store, event(snap).model_copy(update={'user_id': other.user_id}))
    assert store.get_evidence(other.user_id, now=T) == []


def test_offline_database_isolation(tmp_path):
    path = tmp_path/'offline.sqlite3'
    with PreferenceStore(path, offline=True) as store:
        user = store.create_user(now=T)
        session = store.create_session(user.user_id, now=T)
        store.add_request(PreferenceRequest(request_id='r', user_id=user.user_id,
            session_id=session.session_id, user_query='shirt', kind='new', created_at=T), now=T)
        snap = ItemSnapshot(item_snapshot_id='s', user_id=user.user_id, session_id=session.session_id,
            request_id='r', recommendation_id='rec', rank=1, captured_at=T,
            item=NormalizedItem(item_id='item', title='shirt', normalization_metadata=NormalizationMetadata()))
        store.add_snapshot(snap, now=T)
        add(store, event(snap, action='purchase'))
        assert store.effective_events(user.user_id, now=T+timedelta(seconds=100))[0].action == 'purchase'
    with pytest.raises(StoreConflict):
        PreferenceStore(path)


def test_full_transaction_rollback_on_evidence_conflict(setup):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    bad = PreferenceEvidence(evidence_id='bad', user_id=user.user_id, event_id='e',
        item_snapshot_id=snap.item_snapshot_id, source_action='dislike', attribute='color',
        value='black', metadata_fields=['title'], explanation='incorrect action')
    with pytest.raises(StoreConflict):
        store.save_profile(profile(user, job), [bad], job_id=job.job_id,
                           lease_token=job.lease_token, expected_version=0, now=T+timedelta(seconds=102))
    assert store.get_evidence(user.user_id, now=T+timedelta(seconds=102)) == []
    store.retry_job(job.job_id, job.lease_token, 'retry', now=T+timedelta(seconds=103))
    retry = store.claim_job(now=T+timedelta(seconds=104))
    assert retry.attempts == 2
    store.renew_job(retry.job_id, retry.lease_token, now=T+timedelta(seconds=105))
    assert store._job(retry.job_id).lease_until == T+timedelta(seconds=405)


def test_empty_session_does_not_schedule(setup):
    store, user, session, _ = setup
    assert store.end_session(user.user_id, session.session_id, now=T) is None
    assert store.enqueue_pending(now=T) == []
    assert store.claim_job(now=T) is None


def test_read_existing_profile_during_refresh(setup):
    store, user, _, snap = setup
    add(store, event(snap))
    store.enqueue_pending(now=T+timedelta(seconds=100))
    job = store.claim_job(now=T+timedelta(seconds=101))
    store.save_profile(profile(user, job), [], job_id=job.job_id,
        lease_token=job.lease_token, expected_version=0, now=T+timedelta(seconds=102))
    add(store, event(snap, 'second', 'click', 3))
    store.enqueue_pending(now=T+timedelta(seconds=103))
    assert store.claim_job(now=T+timedelta(seconds=104)) is not None
    assert store.lookup_profile(user.user_id, now=T+timedelta(seconds=105)).preference_profile.profile_version == 1


def test_persisted_user_session_and_request_reads(setup, tmp_path):
    store, user, session, _ = setup
    with PreferenceStore(tmp_path/'test.sqlite3') as reopened:
        assert reopened.get_user(user.user_id, now=T) == user
        assert reopened.get_session(user.user_id, session.session_id, now=T) == session
        assert reopened.get_request(user.user_id, 'r', now=T).user_query == 'shirt'
        other = reopened.create_user(now=T)
        with pytest.raises(StoreConflict):
            reopened.get_request(other.user_id, 'r', now=T)
        with pytest.raises(StoreConflict):
            reopened.get_session(other.user_id, session.session_id, now=T)
    store.end_session(user.user_id, session.session_id, now=T+timedelta(seconds=1))
    assert store.get_session(user.user_id, session.session_id, now=T+timedelta(seconds=2)).ended_at is not None


def test_three_failures_stop_durably_and_new_events_do_not_restart(setup):
    store,user,session,snap=setup;add(store,event(snap))
    now=T+timedelta(seconds=101)
    store.end_session(user.user_id,session.session_id,now=now)
    for attempt in range(1,4):
        job=store.claim_job(now=now)
        assert job.cycle_attempts==attempt
        status=store.retry_job(job.job_id,job.lease_token,'ValueError',now=now)
        assert status==('stopped' if attempt==3 else 'pending')
    add(store,event(snap,'later',seconds=2))
    assert store.end_session(user.user_id,session.session_id,now=now) is None
    assert store.enqueue_pending(now=now)==[]
    assert store.claim_job(now=now) is None
    assert store.lookup_profile(user.user_id,now=now).status=='not_found'
    path=store.db.execute('PRAGMA database_list').fetchone()['file']
    with PreferenceStore(path) as reopened:
        assert reopened.enqueue_pending(now=now)==[]
        assert reopened.claim_job(now=now) is None
        assert reopened._job(job.job_id).status=='stopped'
        assert reopened.db.execute('select count(*) from events').fetchone()[0]==2


def test_expired_leases_cannot_bypass_three_attempt_limit(setup):
    store,user,session,snap=setup;add(store,event(snap))
    now=T+timedelta(seconds=101);store.end_session(user.user_id,session.session_id,now=now)
    for i in range(3):
        assert store.claim_job(now=now).cycle_attempts==i+1
        now+=timedelta(seconds=301)
    assert store.claim_job(now=now) is None
    assert store.db.execute('select status from jobs').fetchone()[0]=='stopped'
    assert [r[0] for r in store.db.execute('select status from job_attempts')]==['abandoned']*3


def test_success_resets_failure_budget_but_preserves_attempt_history(setup):
    store,user,session,snap=setup;add(store,event(snap))
    now=T+timedelta(seconds=101);store.end_session(user.user_id,session.session_id,now=now)
    job=store.claim_job(now=now);store.retry_job(job.job_id,job.lease_token,'Error',now=now)
    job=store.claim_job(now=now)
    store.save_profile(profile(user,job),[],job_id=job.job_id,lease_token=job.lease_token,expected_version=0,now=now)
    add(store,event(snap,'new',seconds=2));store.enqueue_pending(now=now)
    new=store.claim_job(now=now)
    assert new.cycle_attempts==1 and new.attempts==3


def test_v4_migration_preserves_rows_foreign_keys_and_failed_attempt_budget(tmp_path):
    import sqlite3
    path=tmp_path/'v4.sqlite3'
    schema=Path('src/fashion_recommendation_v2/storage/preference.sql').read_text()
    with sqlite3.connect(path) as db:
        db.executescript(schema)
        db.execute('INSERT INTO users VALUES (?,?,?)',('u',T.isoformat(),(T+timedelta(days=90)).isoformat()))
        db.execute("INSERT INTO jobs VALUES ('j','u','pending',0,4,NULL,NULL,'Error')")
        for i,status in enumerate(['completed','failed','failed','failed']):
            db.execute('INSERT INTO job_attempts VALUES (?,?,?,?,?,?,?)',(str(i),'u','j',T.isoformat(),T.isoformat(),status,'Error' if status=='failed' else None))
    with PreferenceStore(path) as store:
        assert store.db.execute('PRAGMA user_version').fetchone()[0]==5
        assert store.db.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert store.db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert store._job('j').cycle_attempts==3
        assert store._job('j').attempts==4
        assert store.claim_job(now=T) is None
        assert store._job('j').status=='stopped'
        assert store.db.execute('select count(*) from job_attempts').fetchone()[0]==4
