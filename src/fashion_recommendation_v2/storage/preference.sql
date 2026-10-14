CREATE TABLE IF NOT EXISTS store_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
 user_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 started_at TEXT NOT NULL, ended_at TEXT
);
CREATE TABLE IF NOT EXISTS requests (
 request_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
 snapshot_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 request_id TEXT NOT NULL REFERENCES requests ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
 user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 snapshot_id TEXT NOT NULL REFERENCES snapshots ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_user_seq ON events(user_id, seq);
CREATE TABLE IF NOT EXISTS profiles (
 user_id TEXT PRIMARY KEY REFERENCES users ON DELETE CASCADE,
 version INTEGER NOT NULL, cursor INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
 job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('pending','running','completed')),
 target_cursor INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until TEXT, last_error TEXT
);
-- Deletion tasks survive user deletion. Only user-exclusive artifacts under artifact_root are accepted.
CREATE TABLE IF NOT EXISTS artifacts (
 artifact_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
 relative_path TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','deleted')),
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT
);
CREATE TABLE IF NOT EXISTS cookie_tokens (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS job_attempts (
 attempt_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 job_id TEXT NOT NULL REFERENCES jobs ON DELETE CASCADE,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 error_code TEXT
);
CREATE TABLE IF NOT EXISTS preference_analyses (
 snapshot_id TEXT PRIMARY KEY REFERENCES snapshots ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_runs (
 request_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users ON DELETE CASCADE,
 revision INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conversation_runs_user ON conversation_runs(user_id);
PRAGMA user_version = 4;
