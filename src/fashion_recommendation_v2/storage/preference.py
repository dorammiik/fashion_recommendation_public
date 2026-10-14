"""SQLite repository; no network, LLM, cookies, or scheduler side effects.

Use one instance per caller/thread. Writes serialize with BEGIN IMMEDIATE.
All runtime timestamps are supplied by the trusted server, not event clients.
"""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from pathlib import Path
import sqlite3
from uuid import uuid4

from pydantic import ValidationError
from fashion_recommendation_v2.schemas.preference import AnonymousUser
from fashion_recommendation_v2.schemas.preference import InteractionEvent
from fashion_recommendation_v2.schemas.preference import ItemSnapshot
from fashion_recommendation_v2.schemas.preference import PreferenceEvidence
from fashion_recommendation_v2.schemas.preference import PreferenceJob
from fashion_recommendation_v2.schemas.preference import PreferenceRequest
from fashion_recommendation_v2.schemas.preference import PreferenceSession
from fashion_recommendation_v2.schemas.preference import PreferenceStorageConfig
from fashion_recommendation_v2.schemas.preference import ProfileLookup
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference_profile import utc
from fashion_recommendation_v2.schemas.preference_saved import parse_profile
from fashion_recommendation_v2.schemas.preference_saved import parse_evidence
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV1_v1 as PreferenceProfileV1
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence


class StoreConflict(ValueError):
    pass


class UserUnavailable(ValueError):
    pass


def stamp(value: datetime) -> str:
    return utc(value).isoformat(timespec='microseconds')


def dump(value) -> str:
    return value.model_dump_json(by_alias=True)


class PreferenceStore:
    def __init__(self, path: str | Path, *, offline: bool = False,
                 artifact_root: str | Path | None = None,
                 config: PreferenceStorageConfig | None = None):
        self.offline = offline
        self.config = config or PreferenceStorageConfig()
        self.artifact_root = Path(artifact_root).resolve() if artifact_root else None
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2, 3, 4, 5):
            self.db.close()
            raise StoreConflict(f'Unsupported database version {version}')
        # Serialize initialization/migration and recheck after acquiring the lock.
        # Disabling FK actions during table replacement preserves job_attempts.
        self.db.execute('PRAGMA foreign_keys=OFF')
        try:
            with self.transaction():
                version = self.db.execute('PRAGMA user_version').fetchone()[0]
                if version < 5:
                    for statement in Path(__file__).with_suffix('.sql').read_text().split(';'):
                        if statement.strip():
                            self.db.execute(statement)
                    migration = Path(__file__).with_name('preference_v5.sql').read_text()
                    for statement in migration.split(';'):
                        if statement.strip():
                            self.db.execute(statement)
                    if self.db.execute('PRAGMA foreign_key_check').fetchone():
                        raise StoreConflict('Foreign key violation during migration')
        except BaseException:
            self.db.close()
            raise
        finally:
            if self.db:
                try:
                    self.db.execute('PRAGMA foreign_keys=ON')
                except sqlite3.ProgrammingError:
                    pass
        mode = 'offline' if offline else 'online'
        try:
            with self.transaction():
                self.db.execute("INSERT OR IGNORE INTO store_settings VALUES ('mode',?)", (mode,))
                if self.db.execute("SELECT value FROM store_settings WHERE key='mode'").fetchone()[0] != mode:
                    raise StoreConflict('Use separate databases for online and offline histories')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _user(self, user_id: str, now: datetime):
        row = self.db.execute('SELECT * FROM users WHERE user_id=?', (user_id,)).fetchone()
        if row is None or row['expires_at'] <= stamp(now):
            raise UserUnavailable('Unknown or expired user')
        return row

    def get_user(self, user_id: str, *, now: datetime) -> AnonymousUser:
        row = self._user(user_id, now)
        return AnonymousUser(user_id=row['user_id'], created_at=datetime.fromisoformat(row['created_at']),
                             expires_at=datetime.fromisoformat(row['expires_at']))

    def get_session(self, user_id: str, session_id: str, *, now: datetime) -> PreferenceSession:
        self._user(user_id, now)
        row = self.db.execute('SELECT * FROM sessions WHERE session_id=? AND user_id=?',
                              (session_id, user_id)).fetchone()
        if not row:
            raise StoreConflict('Unknown session for user')
        return PreferenceSession(session_id=row['session_id'], user_id=row['user_id'],
            started_at=datetime.fromisoformat(row['started_at']),
            ended_at=datetime.fromisoformat(row['ended_at']) if row['ended_at'] else None)

    def get_conversation(self, user_id, request_id, *, now):
        from fashion_recommendation_v2.schemas.conversation import ConversationRecord
        self._user(user_id, now)
        row = self.db.execute('SELECT payload FROM conversation_runs WHERE request_id=? AND user_id=?',
                              (request_id, user_id)).fetchone()
        if not row:
            raise StoreConflict('Unknown conversation request')
        return ConversationRecord.model_validate_json(row['payload'])

    def save_conversation(self, record, *, expected_revision=None, now):
        from fashion_recommendation_v2.schemas.conversation import ConversationRecord
        record = ConversationRecord.model_validate_json(dump(record))
        with self.transaction():
            self._user(record.user_id, now)
            if expected_revision is None:
                self.db.execute('INSERT INTO conversation_runs VALUES (?,?,?,?)',
                    (record.request_id, record.user_id, record.revision, dump(record)))
            else:
                if record.revision != expected_revision + 1:
                    raise StoreConflict('Conversation revision must advance once')
                changed = self.db.execute('UPDATE conversation_runs SET revision=?,payload=? WHERE request_id=? AND user_id=? AND revision=?',
                    (record.revision, dump(record), record.request_id, record.user_id, expected_revision)).rowcount
                if changed != 1:
                    raise StoreConflict('Conversation already advanced')

    def begin_conversation_execution(self, record, *, now):
        """Assign session + register request + advance confirmation atomically."""
        with self.transaction():
            current = self.get_conversation(record.user_id, record.request_id, now=now)
            if current.revision != record.revision or current.status != 'classifying':
                raise StoreConflict('Conversation already advanced')
            previous = (self.get_conversation(record.user_id, record.previous_request_id, now=now)
                        if record.previous_request_id else None)
            if record.decision.kind == 'followup':
                if previous is None or previous.status not in ('completed', 'blocked', 'failed', 'interrupted'):
                    raise StoreConflict('Followup requires a finished previous request')
                if previous.session_id:
                    session = self.get_session(record.user_id, previous.session_id, now=now)
                    if session.ended_at is not None:
                        raise StoreConflict('Followup session has ended; start a new request')
                    record.session_id = session.session_id
                else:
                    # Routing may fail before any session was allocated. Preserve the
                    # conversation parent while allocating its first execution session.
                    record.session_id = uuid4().hex
                    self.db.execute('INSERT INTO sessions VALUES (?,?,?,NULL)',
                        (record.session_id, record.user_id, stamp(now)))
            elif record.decision.kind == 'new':
                if previous and previous.session_id:
                    self.db.execute('UPDATE sessions SET ended_at=COALESCE(ended_at,?) WHERE session_id=? AND user_id=?',
                        (stamp(now), previous.session_id, record.user_id))
                    self._enqueue(record.user_id)
                record.session_id = uuid4().hex
                self.db.execute('INSERT INTO sessions VALUES (?,?,?,NULL)',
                    (record.session_id, record.user_id, stamp(now)))
            else:
                raise StoreConflict('Unconfirmed request cannot execute')
            request = PreferenceRequest(request_id=record.request_id, user_id=record.user_id,
                session_id=record.session_id, user_query=record.user_query, kind=record.decision.kind,
                parent_request_id=record.previous_request_id if record.decision.kind == 'followup' else None,
                created_at=now)
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?)',
                (request.request_id, request.user_id, request.session_id, dump(request)))
            record.status = 'running'
            record.question = None
            record.revision += 1
            self.db.execute('UPDATE conversation_runs SET revision=?,payload=? WHERE request_id=?',
                (record.revision, dump(record), record.request_id))
        return record

    def get_request(self, user_id: str, request_id: str, *, now: datetime) -> PreferenceRequest:
        self._user(user_id, now)
        row = self.db.execute('SELECT payload FROM requests WHERE request_id=? AND user_id=?',
                              (request_id, user_id)).fetchone()
        if not row:
            raise StoreConflict('Unknown request for user')
        return PreferenceRequest.model_validate_json(row['payload'])

    def create_user(self, *, now: datetime) -> AnonymousUser:
        now = utc(now)
        user = AnonymousUser(user_id=uuid4().hex, created_at=now,
                             expires_at=now + timedelta(days=self.config.cookie_days))
        with self.transaction():
            self.db.execute('INSERT INTO users VALUES (?,?,?)',
                            (user.user_id, stamp(now), stamp(user.expires_at)))
        return user

    def create_cookie_identity(self, token_hash: str, *, now: datetime) -> AnonymousUser:
        user = AnonymousUser(user_id=uuid4().hex, created_at=now,
                             expires_at=utc(now) + timedelta(days=90))
        with self.transaction():
            self.db.execute('INSERT INTO users VALUES (?,?,?)',
                            (user.user_id, stamp(now), stamp(user.expires_at)))
            self.db.execute('INSERT INTO cookie_tokens VALUES (?,?)', (token_hash, user.user_id))
        return user

    def resolve_cookie(self, token_hash: str, *, now: datetime) -> AnonymousUser:
        row = self.db.execute('SELECT user_id FROM cookie_tokens WHERE token_hash=?', (token_hash,)).fetchone()
        if not row:
            raise UserUnavailable('Unknown cookie')
        return self.get_user(row['user_id'], now=now)

    def transition_session(self, user_id: str, previous_session_id: str | None, *, now: datetime):
        session = PreferenceSession(session_id=uuid4().hex, user_id=user_id, started_at=now)
        with self.transaction():
            self._user(user_id, now)
            if previous_session_id:
                row = self.db.execute('SELECT user_id FROM sessions WHERE session_id=?', (previous_session_id,)).fetchone()
                if not row or row['user_id'] != user_id:
                    raise StoreConflict('Unknown previous session')
                self.db.execute('UPDATE sessions SET ended_at=COALESCE(ended_at,?) WHERE session_id=?',
                                (stamp(now), previous_session_id))
                self._enqueue(user_id)
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,NULL)',
                            (session.session_id, user_id, stamp(now)))
        return session

    def create_session(self, user_id: str, *, now: datetime) -> PreferenceSession:
        session = PreferenceSession(session_id=uuid4().hex, user_id=user_id, started_at=now)
        with self.transaction():
            self._user(user_id, now)
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,NULL)',
                            (session.session_id, user_id, stamp(now)))
        return session

    def add_request(self, request: PreferenceRequest, *, now: datetime):
        request = PreferenceRequest.model_validate_json(dump(request))
        with self.transaction():
            self._user(request.user_id, now)
            session = self.db.execute('SELECT * FROM sessions WHERE session_id=?', (request.session_id,)).fetchone()
            if not session or session['user_id'] != request.user_id or session['ended_at']:
                raise StoreConflict('Request requires own open session')
            if request.kind == 'new' and self.db.execute(
                    'SELECT 1 FROM requests WHERE session_id=?', (request.session_id,)).fetchone():
                raise StoreConflict('New independent request requires a new session')
            if request.parent_request_id:
                parent = self.db.execute('SELECT * FROM requests WHERE request_id=?', (request.parent_request_id,)).fetchone()
                if not parent or parent['user_id'] != request.user_id or parent['session_id'] != request.session_id:
                    raise StoreConflict('Followup parent must belong to same user/session')
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?)',
                            (request.request_id, request.user_id, request.session_id, dump(request)))

    def add_snapshot(self, snapshot: ItemSnapshot, *, now: datetime):
        self.add_snapshots([snapshot], now=now)

    def add_snapshots(self, snapshots: list[ItemSnapshot], *, now: datetime):
        """Publish a recommendation's snapshots atomically and idempotently."""
        snapshots = [ItemSnapshot.model_validate_json(dump(s)) for s in snapshots]
        with self.transaction():
            for snapshot in snapshots:
                self._user(snapshot.user_id, now)
                request = self.db.execute('SELECT * FROM requests WHERE request_id=?', (snapshot.request_id,)).fetchone()
                if not request or request['user_id'] != snapshot.user_id or request['session_id'] != snapshot.session_id:
                    raise StoreConflict('Snapshot request ownership mismatch')
                old = self.db.execute('SELECT payload FROM snapshots WHERE snapshot_id=?', (snapshot.item_snapshot_id,)).fetchone()
                if old:
                    original = ItemSnapshot.model_validate_json(old['payload'])
                    if original.model_dump(exclude={'captured_at'}) != snapshot.model_dump(exclude={'captured_at'}):
                        raise StoreConflict('Snapshot ID reused with different contents')
                    continue
                self.db.execute('INSERT INTO snapshots VALUES (?,?,?,?)',
                                (snapshot.item_snapshot_id, snapshot.user_id, snapshot.request_id, dump(snapshot)))

    def get_snapshot(self, user_id: str, snapshot_id: str, *, now: datetime) -> ItemSnapshot:
        self._user(user_id, now)
        row = self.db.execute('SELECT payload FROM snapshots WHERE snapshot_id=? AND user_id=?',
                              (snapshot_id, user_id)).fetchone()
        if row is None:
            raise StoreConflict('Unknown snapshot for user')
        return ItemSnapshot.model_validate_json(row['payload'])

    def get_analyses(self, user_id, *, now):
        from fashion_recommendation_v2.schemas.preference_agent import CachedAnalysis
        self._user(user_id, now)
        return {r['snapshot_id']: CachedAnalysis.model_validate_json(r['payload']) for r in self.db.execute(
            'SELECT snapshot_id,payload FROM preference_analyses WHERE user_id=?', (user_id,))}

    def get_evidence(self, user_id: str, *, now: datetime) -> list[PreferenceEvidence]:
        self._user(user_id, now)
        return [parse_evidence(r['payload']) for r in self.db.execute(
            'SELECT payload FROM evidence WHERE user_id=? ORDER BY evidence_id', (user_id,))]

    def append_event(self, event: InteractionEvent, *, now: datetime) -> tuple[int, bool]:
        """Returns (receipt sequence, inserted). Retry reception time may differ."""
        event = InteractionEvent.model_validate_json(dump(event))
        with self.transaction():
            user = self._user(event.user_id, now)
            old = self.db.execute('SELECT * FROM events WHERE event_id=?', (event.event_id,)).fetchone()
            if old:
                original = InteractionEvent.model_validate_json(old['payload'])
                if original.model_dump(exclude={'received_at'}) != event.model_dump(exclude={'received_at'}):
                    raise StoreConflict('event_id reused with different contents')
                return old['seq'], False
            if event.action == 'purchase' and not self.offline:
                raise StoreConflict('Purchase is offline-only')
            if not (user['created_at'] <= stamp(event.occurred_at) <= stamp(now)):
                raise StoreConflict('Event time outside user lifetime or in future')
            # Server acceptance controls received_at, never trust a client value.
            event = event.model_copy(update={'received_at': utc(now)})
            row = self.db.execute('SELECT payload FROM snapshots WHERE snapshot_id=?', (event.item_snapshot_id,)).fetchone()
            if not row:
                raise StoreConflict('Missing item snapshot')
            snap = ItemSnapshot.model_validate_json(row['payload'])
            fields = ('user_id', 'session_id', 'request_id', 'recommendation_id', 'rank')
            if any(getattr(snap, f) != getattr(event, f) for f in fields) or snap.item.item_id != event.item_id:
                raise StoreConflict('Event does not match recommended item')
            if event.occurred_at < snap.captured_at:
                raise StoreConflict('Event predates recommendation')
            # Targets can arrive late. Unresolved targets remain pending in effective_events.
            target = self.db.execute('SELECT payload FROM events WHERE event_id=?', (event.target_event_id,)).fetchone()
            if target:
                self._check_target(event, InteractionEvent.model_validate_json(target['payload']))
            self.db.execute('INSERT INTO events(event_id,user_id,snapshot_id,payload) VALUES (?,?,?,?)',
                            (event.event_id, event.user_id, event.item_snapshot_id, dump(event)))
            return self.db.execute('SELECT last_insert_rowid()').fetchone()[0], True

    @staticmethod
    def _check_target(event, target):
        if (target.user_id != event.user_id or target.item_id != event.item_id
                or target.operation == 'cancel' or target.occurred_at > event.occurred_at):
            raise StoreConflict('Invalid correction/cancellation target')
        if event.operation == 'cancel' and event.action != target.action:
            raise StoreConflict('Cancellation action must match target')

    def events(self, user_id: str, *, now: datetime, through: int | None = None):
        self._user(user_id, now)
        return [(r['seq'], InteractionEvent.model_validate_json(r['payload'])) for r in self.db.execute(
            'SELECT seq,payload FROM events WHERE user_id=? AND seq<=? ORDER BY seq',
            (user_id, through if through is not None else 9223372036854775807))]

    def effective_events(self, user_id: str, *, now: datetime, through: int | None = None):
        """Replay event time, with event_id tie-break. Cancel never revives an older reaction."""
        return replay_events([e for _, e in self.events(user_id, now=now, through=through)])

    def _cursor(self, user_id):
        return self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE user_id=?', (user_id,)).fetchone()[0]

    def _enqueue(self, user_id):
        cursor = self._cursor(user_id)
        profile = self.db.execute('SELECT cursor FROM profiles WHERE user_id=?', (user_id,)).fetchone()
        if cursor <= (profile['cursor'] if profile else 0):
            return None
        job = self.db.execute('SELECT * FROM jobs WHERE user_id=?', (user_id,)).fetchone()
        if job is None:
            job_id = uuid4().hex
            self.db.execute("INSERT INTO jobs(job_id,user_id,status,target_cursor) VALUES (?,?,'pending',?)",
                            (job_id, user_id, cursor))
        else:
            job_id = job['job_id']
            if job['status'] == 'stopped':
                return None
            if job['status'] != 'running':
                self.db.execute("UPDATE jobs SET status='pending',target_cursor=? WHERE job_id=?", (cursor, job_id))
        return job_id

    def end_session(self, user_id: str, session_id: str, *, now: datetime):
        with self.transaction():
            self._user(user_id, now)
            row = self.db.execute('SELECT * FROM sessions WHERE session_id=? AND user_id=?', (session_id, user_id)).fetchone()
            if row is None:
                raise StoreConflict('Unknown session')
            self.db.execute('UPDATE sessions SET ended_at=COALESCE(ended_at,?) WHERE session_id=?', (stamp(now), session_id))
            return self._enqueue(user_id)

    def enqueue_pending(self, *, now: datetime) -> list[str]:
        with self.transaction():
            result = []
            for row in self.db.execute('SELECT user_id FROM users WHERE expires_at>?', (stamp(now),)).fetchall():
                job_id = self._enqueue(row['user_id'])
                if job_id:
                    result.append(job_id)
            return result

    def claim_job(self, *, now: datetime) -> PreferenceJob | None:
        with self.transaction():
            # Expired leases count toward the same durable attempt budget.
            exhausted = self.db.execute(
                "SELECT job_id FROM jobs WHERE cycle_attempts>=? AND "
                "(status='pending' OR (status='running' AND lease_until<=?))",
                (self.config.job_max_attempts, stamp(now))).fetchall()
            for stopped in exhausted:
                self.db.execute("UPDATE job_attempts SET status='abandoned',finished_at=?,error_code='lease_expired' "
                                "WHERE job_id=? AND status='running'", (stamp(now), stopped['job_id']))
                self.db.execute("UPDATE jobs SET status='stopped',lease_token=NULL,lease_until=NULL,"
                                "last_error=COALESCE(last_error,'attempt_limit_reached') WHERE job_id=?",
                                (stopped['job_id'],))
            row = self.db.execute("""SELECT j.* FROM jobs j JOIN users u USING(user_id)
                WHERE u.expires_at>? AND (j.status='pending' OR (j.status='running' AND j.lease_until<=?))
                ORDER BY j.attempts, j.rowid LIMIT 1""", (stamp(now), stamp(now))).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE job_attempts SET status='abandoned',finished_at=?,error_code='lease_expired' WHERE job_id=? AND status='running'",
                            (stamp(now), row['job_id']))
            token = uuid4().hex
            until = utc(now) + timedelta(seconds=self.config.job_lease_seconds)
            self.db.execute("""UPDATE jobs SET status='running',attempts=attempts+1,cycle_attempts=cycle_attempts+1,lease_token=?,lease_until=?,
                target_cursor=? WHERE job_id=?""", (token, stamp(until), self._cursor(row['user_id']), row['job_id']))
            self.db.execute("INSERT INTO job_attempts VALUES (?,?,?,?,NULL,'running',NULL)",
                            (token, row['user_id'], row['job_id'], stamp(now)))
            return self._job(row['job_id'])

    def lookup_update_job(self, user_id, *, now):
        self._user(user_id, now)
        row = self.db.execute('SELECT job_id,status,cycle_attempts,last_error FROM jobs WHERE user_id=?',
                              (user_id,)).fetchone()
        return {**dict(row), 'max_attempts': self.config.job_max_attempts} if row else None

    def _job(self, job_id):
        row = dict(self.db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone())
        if row['lease_until']:
            row['lease_until'] = datetime.fromisoformat(row['lease_until'])
        return PreferenceJob(**row)

    def _lease(self, job_id, token, now):
        row = self.db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        if not row or row['status'] != 'running' or row['lease_token'] != token or row['lease_until'] <= stamp(now):
            raise StoreConflict('Lost or expired job lease')
        self._user(row['user_id'], now)
        return row

    def renew_job(self, job_id: str, token: str, *, now: datetime):
        with self.transaction():
            self._lease(job_id, token, now)
            self.db.execute('UPDATE jobs SET lease_until=? WHERE job_id=?',
                            (stamp(utc(now) + timedelta(seconds=self.config.job_lease_seconds)), job_id))

    def retry_job(self, job_id: str, token: str, error: str, *, now: datetime, exhausted: bool = False):
        with self.transaction():
            job = self._lease(job_id, token, now)
            self.db.execute("UPDATE job_attempts SET status='failed',finished_at=?,error_code=? WHERE attempt_id=?",
                            (stamp(now), error, token))
            status = 'stopped' if exhausted or job['cycle_attempts'] >= self.config.job_max_attempts else 'pending'
            self.db.execute("UPDATE jobs SET status=?,lease_token=NULL,lease_until=NULL,last_error=? WHERE job_id=?",
                            (status, error, job_id))
            return status

    def save_profile(self, profile: PreferenceProfile, evidence: list[PreferenceEvidence], *,
                     job_id: str, lease_token: str, expected_version: int, now: datetime, analyses=None):
        """Full evidence replacement + profile + cursor + job completion in one transaction.

        Worker must reassemble the full effective evidence through target_cursor. Events
        arriving after that boundary are queued for the next job, never marked processed.
        """
        profile = parse_profile(dump(profile))
        evidence = [parse_evidence(dump(e)) for e in evidence]
        with self.transaction():
            job = self._lease(job_id, lease_token, now)
            previous = self.db.execute('SELECT version,payload FROM profiles WHERE user_id=?', (profile.user_id,)).fetchone()
            version = previous['version'] if previous else 0
            if previous and isinstance(parse_profile(previous['payload']), PreferenceProfileV1) and not isinstance(profile, PreferenceProfileV1):
                raise StoreConflict('Cannot downgrade an interpretation profile to v0')
            if previous and parse_profile(previous['payload']).schema_version == '3.0' and profile.schema_version != '3.0':
                raise StoreConflict('Cannot downgrade a v2 interpretation profile')
            if previous and getattr(parse_profile(previous['payload']), 'interpretation_version', None) == 'preference-interpretation-v3' and getattr(profile, 'interpretation_version', None) not in {'preference-interpretation-v3', 'preference-interpretation-v4'}:
                raise StoreConflict('Cannot downgrade a v3 interpretation profile')
            if previous and getattr(parse_profile(previous['payload']), 'interpretation_version', None) == 'preference-interpretation-v4' and getattr(profile, 'interpretation_version', None) != 'preference-interpretation-v4':
                raise StoreConflict('Cannot downgrade a v4 interpretation profile')
            if (job['user_id'] != profile.user_id or version != expected_version
                    or profile.profile_version != version + 1 or not (0 <= profile.processed_event_cursor <= job['target_cursor'])):
                raise StoreConflict('Profile version/user/cursor mismatch')
            old_cursor = self.db.execute('SELECT cursor FROM profiles WHERE user_id=?', (profile.user_id,)).fetchone()
            if profile.processed_event_cursor <= (old_cursor['cursor'] if old_cursor else 0):
                raise StoreConflict('Refresh must advance the receipt cursor')
            if not self.db.execute('SELECT 1 FROM events WHERE user_id=? AND seq=?',
                                   (profile.user_id, profile.processed_event_cursor)).fetchone():
                raise StoreConflict('Cursor must end at an owned event')
            if profile.updated_at > utc(now) or profile.as_of > utc(now):
                raise StoreConflict('Profile timestamp is in the future')
            ids = {e.evidence_id for e in evidence}
            if len(ids) != len(evidence) or not profile.evidence_ids() <= ids:
                raise StoreConflict('Missing or duplicate evidence')
            effective = {e.event_id: e for e in self.effective_events(profile.user_id, now=now, through=profile.processed_event_cursor)}
            v1 = isinstance(profile, PreferenceProfileV1)
            if v1:
                if analyses:
                    raise StoreConflict('v1 must not overwrite v0 feature caches')
                from fashion_recommendation_v2.preference.interpretation_sources import event_evidence
                from fashion_recommendation_v2.preference.interpretation_sources import category
                from fashion_recommendation_v2.preference.interpretation_sources import validate_references
                expected_evidence = {}
                categories = set()
                for event in effective.values():
                    snap = self.get_snapshot(profile.user_id, event.item_snapshot_id, now=now)
                    expected_evidence.update({e.evidence_id:e for e in event_evidence(event,snap)})
                    cid, _ = category(snap)
                    if cid:
                        categories.add(cid)
                if {e.evidence_id:e for e in evidence} != expected_evidence:
                    raise StoreConflict('v1 evidence differs from owned effective events and stored sources')
                validate_references(profile.interpretations, evidence, categories)
            for entry in evidence:
                event = effective.get(entry.event_id)
                if (entry.user_id != profile.user_id or not event
                        or entry.item_snapshot_id != event.item_snapshot_id or entry.source_action != event.action):
                    raise StoreConflict('Evidence must reference own effective event and snapshot')
                snap = ItemSnapshot.model_validate_json(self.db.execute(
                    'SELECT payload FROM snapshots WHERE snapshot_id=?', (entry.item_snapshot_id,)).fetchone()[0])
                if v1:
                    continue
                if isinstance(entry, InterpretationEvidence):
                    raise StoreConflict('v0 profile cannot use v1 evidence')
                if not entry.metadata_fields and not entry.image_observations:
                    raise StoreConflict('Evidence needs metadata or an existing image observation')
                from fashion_recommendation_v2.preference.observations import observations
                search_fields = {obs.field for obs in observations(snap)
                                 if obs.field.startswith('search_analysis.')} if snap.search_analysis is not None else set()
                if any(field not in search_fields if field.startswith('search_analysis.')
                       else field.split('.')[0] not in type(snap.item).model_fields
                       for field in entry.metadata_fields):
                    raise StoreConflict('Unknown metadata evidence field')
                if any(observation not in snap.image_observations for observation in entry.image_observations):
                    raise StoreConflict('Image evidence must reuse stored Ranking observations')
            from fashion_recommendation_v2.schemas.preference_agent import CachedAnalysis
            for analysis in analyses or []:
                analysis = CachedAnalysis.model_validate_json(dump(analysis))
                self.get_snapshot(profile.user_id, analysis.snapshot_id, now=now)
                self.db.execute('INSERT INTO preference_analyses VALUES (?,?,?) ON CONFLICT(snapshot_id) DO UPDATE SET payload=excluded.payload',
                                (analysis.snapshot_id, profile.user_id, dump(analysis)))
            if v1:
                # Lazy additive storage extension: preserve old payload/evidence atomically.
                self.db.execute('CREATE TABLE IF NOT EXISTS preference_profile_history ('
                    'user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE, '
                    'version INTEGER NOT NULL, payload TEXT NOT NULL, evidence TEXT NOT NULL, '
                    'PRIMARY KEY(user_id,version))')
                import json
                old = self.db.execute('SELECT * FROM profiles WHERE user_id=?',(profile.user_id,)).fetchone()
                if old:
                    old_evidence = [r['payload'] for r in self.db.execute('SELECT payload FROM evidence WHERE user_id=?',(profile.user_id,))]
                    self.db.execute('INSERT OR IGNORE INTO preference_profile_history VALUES (?,?,?,?)',
                        (profile.user_id, old['version'], old['payload'], json.dumps(old_evidence)))
                self.db.execute('INSERT INTO preference_profile_history VALUES (?,?,?,?)',
                    (profile.user_id,profile.profile_version,dump(profile),json.dumps([dump(e) for e in evidence])))
            self.db.execute('DELETE FROM evidence WHERE user_id=?', (profile.user_id,))
            for entry in evidence:
                self.db.execute('INSERT INTO evidence VALUES (?,?,?,?)',
                                (entry.evidence_id, entry.user_id, entry.event_id, dump(entry)))
            self.db.execute('INSERT INTO profiles VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,cursor=excluded.cursor,payload=excluded.payload',
                            (profile.user_id, profile.profile_version, profile.processed_event_cursor, dump(profile)))
            self.db.execute("UPDATE job_attempts SET status='completed',finished_at=? WHERE attempt_id=?",
                            (stamp(now), lease_token))
            pending = self._cursor(profile.user_id) > profile.processed_event_cursor
            self.db.execute('UPDATE jobs SET status=?,cycle_attempts=0,lease_token=NULL,lease_until=NULL,last_error=NULL WHERE job_id=?',
                            ('pending' if pending else 'completed', job_id))

    def read_profile_evidence_snapshot(self, user_id, *, now):
        """Atomic read for Ranking: no decay, no refresh, errors remain errors."""
        with self.transaction():
            self._user(user_id, now)
            row = self.db.execute('SELECT payload FROM profiles WHERE user_id=?', (user_id,)).fetchone()
            if row is None:
                return None, [], {}
            profile = parse_profile(row['payload'])
            if profile.user_id != user_id:
                raise StoreConflict('Profile owner mismatch')
            evidence = self.get_evidence(user_id, now=now)
            snapshots = {e.item_snapshot_id: self.get_snapshot(user_id, e.item_snapshot_id, now=now)
                         for e in evidence}
            return profile, evidence, snapshots

    def lookup_profile(self, user_id: str, *, now: datetime) -> ProfileLookup:
        """Stored snapshot only. Agent/view layer will compute current-time decay."""
        try:
            with self.transaction():
                self._user(user_id, now)
                row = self.db.execute('SELECT payload FROM profiles WHERE user_id=?', (user_id,)).fetchone()
                if not row:
                    return ProfileLookup(status='not_found')
                profile = parse_profile(row['payload'])
                if profile.user_id != user_id:
                    raise ValueError('Stored profile owner mismatch')
                return ProfileLookup(status='available' if profile.has_features() else 'empty', preference_profile=profile)
        except UserUnavailable:
            return ProfileLookup(status='not_found')
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            return ProfileLookup(status='failed', error=str(exc))

    def lookup_profile_view(self, user_id, *, now):
        """Recalculate from the committed receipt boundary only, without an LLM call."""
        from fashion_recommendation_v2.agents.preference_scoring import build_profile
        try:
            with self.transaction():
                self._user(user_id, now)
                row=self.db.execute('SELECT payload FROM profiles WHERE user_id=?',(user_id,)).fetchone()
                if not row:
                    return ProfileLookup(status='not_found')
                old=parse_profile(row['payload'])
                if old.user_id != user_id:
                    raise StoreConflict('Profile owner mismatch')
                evidence=self.get_evidence(user_id,now=now)
                if old.has_features() and not evidence:
                    raise StoreConflict('Cannot project a profile without evidence')
                if isinstance(old, PreferenceProfileV1):
                    if not old.evidence_ids() <= {e.evidence_id for e in evidence}:
                        raise StoreConflict('Missing v1 interpretation evidence')
                    # Interpretation age is explicit; reads never decay/reinterpret it.
                    return ProfileLookup(status='available' if old.has_features() else 'empty', preference_profile=old)
                effective=self.effective_events(user_id,now=now,through=old.processed_event_cursor)
                view=build_profile(user_id,old.profile_version,old.processed_event_cursor,effective,evidence,
                                   now=now,updated_at=old.updated_at)
                return ProfileLookup(status='available' if view.has_features() else 'empty',preference_profile=view)
        except UserUnavailable:
            return ProfileLookup(status='not_found')
        except (ValueError, sqlite3.Error) as exc:
            return ProfileLookup(status='failed',error=type(exc).__name__)

    def save_agent_artifacts(self, user_id, run_id, files, *, now):
        """Publish registered per-user logs under expiry lock; never recreate an expired user's files."""
        if not self.artifact_root:
            raise StoreConflict('artifact_root required for agent reports')
        paths=[]
        try:
            with self.transaction():
                user=self._user(user_id,now)
                for name, content in files.items():
                    relative=f'{run_id}/{name}'
                    path=self._artifact_path(relative)
                    self.db.execute('INSERT INTO artifacts(artifact_id,user_id,relative_path,expires_at) VALUES (?,?,?,?)',
                        (uuid4().hex,user_id,relative,user['expires_at']))
                    path.parent.mkdir(parents=True,exist_ok=True)
                    paths.append(path)
                    path.write_bytes(content)
        except BaseException:
            for path in paths:
                path.unlink(missing_ok=True)
            raise

    def save_progress_report(self, user_id, run_id, content, *, now):
        """Atomically replace an E2E checkpoint, keeping one expiry registration."""
        relative = f'{run_id}/api_e2e_report.json'
        temporary = None
        try:
            with self.transaction():
                user = self._user(user_id, now)
                path = self._artifact_path(relative)
                existing = self.db.execute('SELECT user_id FROM artifacts WHERE relative_path=?', (relative,)).fetchone()
                if existing and existing['user_id'] != user_id:
                    raise StoreConflict('Report belongs to another user')
                if not existing:
                    self.db.execute('INSERT INTO artifacts(artifact_id,user_id,relative_path,expires_at) VALUES (?,?,?,?)',
                        (uuid4().hex, user_id, relative, user['expires_at']))
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
                temporary.write_bytes(content)
                temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def register_artifact(self, user_id: str, relative_path: str, *, now: datetime) -> str:
        """Only user-exclusive files; shared backups must first be split/rebuilt by their owner."""
        if not self.artifact_root:
            raise StoreConflict('artifact_root required')
        self._artifact_path(relative_path)
        with self.transaction():
            user = self._user(user_id, now)
            artifact_id = uuid4().hex
            self.db.execute('INSERT INTO artifacts(artifact_id,user_id,relative_path,expires_at) VALUES (?,?,?,?)',
                            (artifact_id, user_id, relative_path, user['expires_at']))
            return artifact_id

    def _artifact_path(self, relative_path):
        if not self.artifact_root or Path(relative_path).is_absolute() or '..' in Path(relative_path).parts:
            raise StoreConflict('Artifact must be relative to artifact_root')
        path = self.artifact_root / relative_path
        if path.is_symlink() or self.artifact_root not in path.resolve().parents:
            raise StoreConflict('Unsafe artifact path')
        if path.exists() and not path.is_file():
            raise StoreConflict('Artifact must be a file')
        return path

    def purge_expired(self, *, now: datetime) -> dict:
        with self.transaction():
            count = self.db.execute('SELECT COUNT(*) FROM users WHERE expires_at<=?', (stamp(now),)).fetchone()[0]
            self.db.execute('DELETE FROM users WHERE expires_at<=?', (stamp(now),))
        failed = []
        deleted = 0
        # Durable outbox survives cascade deletion; retry only outstanding files.
        rows = self.db.execute("SELECT * FROM artifacts WHERE expires_at<=? AND status='pending'", (stamp(now),)).fetchall()
        for row in rows:
            try:
                self._artifact_path(row['relative_path']).unlink(missing_ok=True)
            except (OSError, StoreConflict) as exc:
                failed.append(row['artifact_id'])
                self.db.execute('UPDATE artifacts SET attempts=attempts+1,last_error=? WHERE artifact_id=?', (str(exc), row['artifact_id']))
            else:
                deleted += 1
                # No user/path retained once cleanup succeeds.
                self.db.execute('DELETE FROM artifacts WHERE artifact_id=?', (row['artifact_id'],))
        return {'users_deleted': count, 'files_deleted': deleted, 'failed_artifact_ids': failed}

def replay_events(events):
    by_id = {e.event_id: e for e in events}
    active = {}
    reactions = {}
    # At equal timestamps, process records before dependent control events.
    def order(e):
        depth, target, seen = 0, e.target_event_id, set()
        while target in by_id and target not in seen:
            seen.add(target)
            depth += 1
            target = by_id[target].target_event_id
        return e.occurred_at, depth, e.event_id
    for event in sorted(events, key=order):
        if event.operation != 'record':
            target = by_id.get(event.target_event_id)
            if target is None:
                continue
            try:
                PreferenceStore._check_target(event, target)
            except StoreConflict:
                continue  # late invalid target is retained in history but never applied
            active.pop(target.event_id, None)
            if event.operation == 'cancel':
                continue
        if event.action in ('like', 'dislike'):
            previous = reactions.get(event.item_id)
            if previous:
                active.pop(previous, None)
            reactions[event.item_id] = event.event_id
        active[event.event_id] = event
    counts = {}
    result = []
    for e in sorted(active.values(), key=lambda e: (e.occurred_at, e.event_id)):
        if e.action == 'click':
            key = (e.session_id, e.item_id)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > 3:
                continue
        result.append(e)
    return result
