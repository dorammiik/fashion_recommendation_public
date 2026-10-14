import { APIError } from './api';
import { active, type API, type Run } from './types';

type PendingExit = {owner: string; sessions: string[]; requests: string[]};

// Only explicit navigation queues exits. Reload/hidden/dispose never do.
export class SessionExit {
  private pending: PendingExit = {owner: '', sessions: [], requests: []};
  private timer?: ReturnType<typeof setTimeout>;
  private flushing = false;
  private stopped = true;
  private epoch = 0;
  constructor(private api: API, private storage: Storage, private key: string) {}
  start(owner: string) {
    this.stop(); this.stopped = false;
    this.pending = {owner, sessions: [], requests: []};
    try {
      const saved = JSON.parse(this.storage.getItem(this.key) || 'null');
      if (saved?.owner === owner && Array.isArray(saved.sessions) && Array.isArray(saved.requests)) this.pending = saved;
    } catch { /* Storage may be unavailable. */ }
    this.persist(); void this.flush();
  }
  add(runs: Run[], owner: string | null) {
    if (!owner) return;
    // An offline restored screen can queue an exit, but only bootstrap authorizes sending it.
    if (this.pending.owner !== owner) {
      this.stop();
      this.pending = {owner, sessions: [], requests: []};
      try {
        const saved = JSON.parse(this.storage.getItem(this.key) || 'null');
        if (saved?.owner === owner && Array.isArray(saved.sessions) && Array.isArray(saved.requests)) this.pending = saved;
      } catch { /* Keep the exit in memory when storage is unavailable. */ }
    }
    for (const run of runs) {
      if (run.session_id) this.pending.sessions.push(run.session_id);
      else if (active(run)) this.pending.requests.push(run.request_id);
    }
    this.pending.sessions = [...new Set(this.pending.sessions)];
    this.pending.requests = [...new Set(this.pending.requests)];
    this.persist(); void this.flush();
  }
  private persist() {
    try { this.storage.setItem(this.key, JSON.stringify(this.pending)); } catch { /* In-memory exits still proceed. */ }
  }
  private async flush() {
    if (this.stopped || this.flushing || !this.pending.owner) return;
    clearTimeout(this.timer); this.flushing = true;
    const epoch = this.epoch;
    try {
      for (const id of [...this.pending.sessions]) {
        try {
          await this.api.end(id);
          if (epoch !== this.epoch) return;
          this.pending.sessions = this.pending.sessions.filter(value => value !== id); this.persist();
        } catch (error) {
          if (epoch !== this.epoch) return;
          if (error instanceof APIError && [401, 403].includes(error.status)) { this.stop(); return; }
          // Idempotent end can be retried after a lost receipt.
        }
      }
      for (const id of [...this.pending.requests]) {
        try {
          const run = await this.api.status(id);
          if (epoch !== this.epoch) return;
          if (run.session_id) this.pending.sessions = [...new Set([...this.pending.sessions, run.session_id])];
          if (run.session_id || !active(run)) this.pending.requests = this.pending.requests.filter(value => value !== id);
          this.persist();
        } catch (error) {
          if (epoch !== this.epoch) return;
          if (error instanceof APIError && [401, 403].includes(error.status)) { this.stop(); return; }
          if (error instanceof APIError && error.status === 409) {
            this.pending.requests = this.pending.requests.filter(value => value !== id); this.persist();
          }
        }
      }
    } finally {
      if (epoch === this.epoch) {
        this.flushing = false;
        if (!this.stopped && (this.pending.sessions.length || this.pending.requests.length)) this.timer = setTimeout(() => void this.flush(), 5000);
      }
    }
  }
  stop() { ++this.epoch; this.stopped = true; this.flushing = false; clearTimeout(this.timer); }
}
