-- Run inside an exclusive migration transaction with foreign_keys disabled.
-- Keep the v4 base script stable for processes that have not restarted yet.
CREATE TABLE jobs_v5 (
 job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('pending','running','completed','stopped')),
 target_cursor INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until TEXT, last_error TEXT,
 cycle_attempts INTEGER NOT NULL DEFAULT 0
);
INSERT INTO jobs_v5
 SELECT j.*, CASE WHEN j.status='completed' THEN 0 ELSE
  (SELECT COUNT(*) FROM job_attempts a WHERE a.job_id=j.job_id
   AND a.rowid>COALESCE((SELECT MAX(b.rowid) FROM job_attempts b
                       WHERE b.job_id=j.job_id AND b.status='completed'),0)) END
 FROM jobs j;
DROP TABLE jobs;
ALTER TABLE jobs_v5 RENAME TO jobs;
PRAGMA user_version=5;
