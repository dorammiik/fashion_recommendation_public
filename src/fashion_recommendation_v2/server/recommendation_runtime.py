"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- recommendation_runtime ----

"""Durable, single-process recommendation queue for the local SQLite server.

Queued work survives restarts. In-flight paid work is marked interrupted, never
silently replayed: stage progress is diagnostic, not a resumable checkpoint.
"""
import fcntl
import hashlib
import logging
from threading import Event
from threading import Thread
from fashion_recommendation_v2.schemas.conversation import ConversationRecord
from fashion_recommendation_v2.storage import StoreConflict
from fashion_recommendation_v2.storage import UserUnavailable
from fashion_recommendation_v2.server.quick_start import resolve
from fashion_recommendation_v2.server.quick_start import snapshot
log = logging.getLogger(__name__)
ACTIVE = ('queued', 'classifying', 'running')

@_preserve_class('RecommendationRuntime', 'fashion_recommendation_v2.server.recommendation_runtime')
class RecommendationRuntime:

    def __init__(self, service):
        self.service = service
        self.preference = service.preference
        self._stop = Event()
        self._wake = Event()
        self._thread = None
        self._lock_file = None

    def get(self, user_id, request_id):
        return self.service.get(user_id, request_id)

    def submit(self, user_id, user_query, *, idempotency_key, previous_request_id=None, new_request=False, personalization_mode=None, quick_start=None):
        user_query, personalization_mode, previous_request_id, new_request = resolve(quick_start, user_query, personalization_mode, previous_request_id, new_request)
        request_id = hashlib.sha256(f'{user_id}:{idempotency_key}'.encode()).hexdigest()
        with self.preference.store() as store, store.transaction():
            store.get_user(user_id, now=self.preference.clock())
            # Completed/failed historical results are not recovery checkpoints.
            # Do not revalidate them against today's agent contracts at startup.
            row = store.db.execute('SELECT payload FROM conversation_runs WHERE request_id=?', (request_id,)).fetchone()
            if row:
                record = ConversationRecord.model_validate_json(row['payload'])
                if (record.user_query, record.previous_request_id, record.new_request, record.personalization_mode, record.quick_start) != (user_query, previous_request_id, new_request, personalization_mode, quick_start):
                    raise StoreConflict('Idempotency key reused with different input')
                return record
            if previous_request_id:
                previous = store.get_conversation(user_id, previous_request_id, now=self.preference.clock())
                if previous.status not in ('completed', 'blocked', 'failed', 'interrupted'):
                    raise StoreConflict('Previous request is not finished')
            record = ConversationRecord(quick_start=quick_start, quick_start_snapshot=snapshot(quick_start) if quick_start else None, personalization_mode=personalization_mode, request_id=request_id, user_id=user_id, user_query=user_query, previous_request_id=previous_request_id, new_request=new_request, idempotency_key=idempotency_key, confirmed_kind='new' if new_request or previous_request_id is None else None, status='queued', updated_at=self.preference.clock().isoformat(), progress={'stage': 'queued'})
            store.db.execute('INSERT INTO conversation_runs VALUES (?,?,?,?)', (request_id, user_id, record.revision, record.model_dump_json()))
        self._wake.set()
        return record

    def resume(self, user_id, request_id, *, kind):
        if kind not in ('new', 'followup'):
            raise ValueError('Invalid confirmation')
        with self.preference.store() as store, store.transaction():
            record = store.get_conversation(user_id, request_id, now=self.preference.clock())
            if record.status != 'awaiting_confirmation':
                if record.confirmed_kind and record.confirmed_kind != kind:
                    raise StoreConflict('Confirmation already accepted with another kind')
                return record
            record.status = 'queued'
            record.confirmed_kind = kind
            record.question = None
            record.progress = {'stage': 'queued'}
            record.updated_at = self.preference.clock().isoformat()
            record.revision += 1
            store.db.execute('UPDATE conversation_runs SET revision=?,payload=? WHERE request_id=?', (record.revision, record.model_dump_json(), request_id))
        self._wake.set()
        return record

    def recover(self):
        with self.preference.store() as store, store.transaction():
            rows = store.db.execute("SELECT payload FROM conversation_runs WHERE json_extract(payload, '$.status') IN ('classifying', 'running')").fetchall()
            for row in rows:
                record = ConversationRecord.model_validate_json(row['payload'])
                if record.status not in ('classifying', 'running'):
                    continue
                record.status = 'interrupted'
                record.error_type = 'ServerRestarted'
                record.resumable = False
                record.recovery_reason = '서버 재시작으로 추천이 중단됐어요. 요청을 다시 입력해 주세요. 이전 대화를 이어갈지 새로 시작할지 판단할게요.'
                record.updated_at = self.preference.clock().isoformat()
                record.revision += 1
                store.db.execute('UPDATE conversation_runs SET revision=?,payload=? WHERE request_id=?', (record.revision, record.model_dump_json(), record.request_id))

    def worker_once(self):
        with self.preference.store() as store, store.transaction():
            rows = store.db.execute("SELECT c.payload FROM conversation_runs c JOIN users u ON u.user_id=c.user_id WHERE u.expires_at>? AND json_extract(c.payload, '$.status')='queued' ORDER BY c.rowid LIMIT 1", (self.preference.clock().isoformat(),)).fetchall()
            if not rows or self._stop.is_set():
                return False
            record = ConversationRecord.model_validate_json(rows[0]['payload'])
            record.status = 'classifying'
            record.progress['stage'] = 'classifying'
            record.updated_at = self.preference.clock().isoformat()
            record.revision += 1
            store.db.execute('UPDATE conversation_runs SET revision=?,payload=? WHERE request_id=?', (record.revision, record.model_dump_json(), record.request_id))
        try:
            self.service._with_costs(record, record.confirmed_kind)
        except Exception as exc:
            # Cost/artifact writing can fail outside the execution error handler.
            log.warning('Recommendation worker failed (%s)', type(exc).__name__)
            try:
                current = self.get(record.user_id, record.request_id)
                if current.status in ACTIVE:
                    current.status = 'failed'
                    current.error_type = type(exc).__name__
                    self.service._save(current)
            except (StoreConflict, UserUnavailable):
                pass
        return True

    def _loop(self):
        try:
            while not self._stop.is_set():
                self._wake.clear()
                try:
                    if self.worker_once():
                        continue
                except Exception as exc:
                    log.warning('Recommendation queue unavailable (%s)', type(exc).__name__)
                self._wake.wait(1)
        finally:
            self._lock_file.close()

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Create a new recommendation runtime after stopping')
        self._lock_file = open(str(self.preference.db_path.resolve()) + '.recommendations.lock', 'a')
        try:
            # A second server must not mistake the first server's work for a crash.
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.recover()
        except BaseException:
            self._lock_file.close()
            raise
        self._thread = Thread(target=self._loop, daemon=True, name='recommendation-worker')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=2)
# Keep the process lock until an in-flight worker actually exits.
