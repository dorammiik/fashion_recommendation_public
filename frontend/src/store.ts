import { APIError, errorMessage } from './api';
import { SessionExit } from './sessionExit';
import { active, type API, type Event, type Kind, type Reaction, type Run, type Submission } from './types';
export interface Turn { query: string; run: Run }
type Pending = {type: 'submit'; input: Submission} | {type: 'confirm'; request_id: string; kind: Kind} | {type: 'end'; session_id: string};
interface Saved { owner: string | null; turns: Turn[]; previousId?: string; pending?: Pending; reactions: Record<string, {action: Reaction; event_id: string}>; events: Record<string, Event> }
export interface View extends Saved { profileUpdatesEnabled: boolean; ready: boolean; busy: boolean; error: string; toast: string; sending: string[] }
const empty = (): Saved => ({owner: null, turns: [], reactions: {}, events: {}});
export class Store {
  private exits: SessionExit;
  private departed = new Set<number>();
  private listeners = new Set<() => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private profileTimer?: ReturnType<typeof setTimeout>;
  private toastTimer?: ReturnType<typeof setTimeout>;
  private generation = 0;
  private polling = false;
  private data: Saved;
  private view: View;
  constructor(private api: API, private storage: Storage, private key: string, private interval = 5000, private freshEntry = false) {
    this.exits = new SessionExit(api, storage, `${key}.exits`);
    let saved = empty(); let error = '';
    try { const raw = storage.getItem(key); if (raw) { const parsed = JSON.parse(raw); if (!Array.isArray(parsed.turns) || !parsed.reactions || !parsed.events) throw new Error(); saved = parsed; } }
    catch { error = '저장된 화면을 복원하지 못했어요. 새 추천을 시작해 주세요.'; }
    this.data = saved; this.view = {...(freshEntry ? empty() : saved), profileUpdatesEnabled: false, ready: false, busy: false, error, toast: '', sending: []};
  }
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => {this.listeners.delete(fn);}; };
  getSnapshot = () => this.view;
  private show(patch: Partial<View>) { this.view = {...this.view, ...patch}; this.listeners.forEach(fn => fn()); }
  private save(patch: Partial<Saved>) {
    const next = {...this.data, ...patch};
    try { this.storage.setItem(this.key, JSON.stringify(next)); }
    catch { throw new Error('storage'); }
    this.data = next; this.show(next);
  }
  private notify(toast: string) { clearTimeout(this.toastTimer); this.show({toast}); this.toastTimer = setTimeout(() => this.show({toast: ''}), 3000); }
  private async fail(error: unknown, epoch: number) {
    if (epoch !== this.generation) return;
    if (error instanceof APIError && error.status === 401) {
      ++this.generation; this.departed.clear(); this.exits.stop(); clearTimeout(this.timer);
      this.data = empty();
      try { this.storage.removeItem(this.key); } catch { /* No automatic replay even if persistence is unavailable. */ }
      this.show({...this.data, pending: undefined, previousId: undefined, ready: false, busy: false, sending: [], error: '사용자 인증이 만료됐어요. 이전 요청과 피드백은 다시 보내지 않아요.'});
      await this.init(); return;
    }
    this.show({error: error instanceof Error && error.message === 'storage' ? '브라우저 저장 공간을 사용할 수 없어요. 저장 설정을 확인한 뒤 다시 시도해 주세요.' : errorMessage(error)});
  }
  private async refreshProfileStatus(epoch: number) {
    if (!this.api.profileUpdatesEnabled) return;
    let enabled = false;
    try { enabled = await this.api.profileUpdatesEnabled(); } catch { /* Stop indicating active updates when health cannot be confirmed. */ }
    if (epoch !== this.generation) return;
    this.show({profileUpdatesEnabled: enabled});
    this.profileTimer = setTimeout(() => void this.refreshProfileStatus(epoch), 15000);
  }
  async init() {
    const epoch = this.generation;
    try {
      const auth = await this.api.bootstrap(); if (epoch !== this.generation) return;
      if (this.data.owner && auth.user_id !== this.data.owner) {
        this.save({...empty(), owner: auth.user_id, pending: undefined, previousId: undefined});
        this.show({error: '사용자가 변경되어 이전 화면을 초기화했어요. 이전 요청은 다시 보내지 않아요.'});
      } else this.save({owner: auth.user_id});
      this.show({ready: true});
      this.exits.start(auth.user_id);
      if (this.freshEntry) { this.freshEntry = false; this.goHome(); return; }
      clearTimeout(this.profileTimer);
      void this.refreshProfileStatus(epoch);
      if (this.data.turns.length) await this.refresh();
    } catch (error) { await this.fail(error, epoch); }
  }
  private accept(run: Run, query?: string) {
    const turns = [...this.data.turns]; const i = turns.findIndex(t => t.run.request_id === run.request_id);
    if (i < 0) turns.push({query: query || '', run}); else turns[i] = {...turns[i], run};
    this.save({turns, pending: undefined}); this.schedule();
  }
  private schedule() { clearTimeout(this.timer); if (active(this.data.turns.at(-1)?.run)) this.timer = setTimeout(() => void this.refresh(), this.interval); }
  async refresh() {
    const run = this.data.turns.at(-1)?.run;
    if (!run || this.polling || !this.view.ready) return;
    this.polling = true; const epoch = this.generation;
    try {
      const next = await this.api.status(run.request_id);
      if (epoch !== this.generation && this.departed.has(epoch)) this.exits.add([next], this.data.owner);
      if (epoch !== this.generation || this.data.turns.at(-1)?.run.request_id !== run.request_id) return;
      // Do not erase an unanswered confirm/end intent while restoring server state.
      const turns = this.data.turns.map(t => t.run.request_id === run.request_id ? {...t, run: next} : t);
      this.save({turns}); this.show({error: ''}); this.schedule();
    } catch (error) { await this.fail(error, epoch); }
    finally { if (epoch === this.generation) this.polling = false; }
  }
  async submit(query: string, personalizationMode: 'cold' | 'warm' = 'cold', quickStart?: Submission['quick_start']) {
    if (!this.view.ready || this.view.busy || this.data.pending || active(this.data.turns.at(-1)?.run) || this.data.turns.at(-1)?.run.status === 'awaiting_confirmation' || !query.trim()) return;
    if (quickStart && this.data.turns.length) return;
    const last = this.data.turns.at(-1)?.run;
    const previous = last?.request_id || this.data.previousId;
    const input: Submission = {...(quickStart ? {quick_start: quickStart} : {}), personalization_mode: personalizationMode, user_query: query.trim(), idempotency_key: crypto.randomUUID(), new_request: !last, ...(previous ? {previous_request_id: previous} : {})};
    try { this.save({pending: {type: 'submit', input}}); await this.sendPending(); } catch (e) { await this.fail(e, this.generation); }
  }
  async confirm(kind: Kind) {
    const run = this.data.turns.at(-1)?.run;
    if (!this.view.ready || this.view.busy || this.data.pending || run?.status !== 'awaiting_confirmation') return;
    try { this.save({pending: {type: 'confirm', request_id: run.request_id, kind}}); await this.sendPending(); } catch(e) { await this.fail(e, this.generation); }
  }
  async startNew() {
    if (!this.view.ready || this.view.busy || this.data.pending || this.view.sending.length || Object.keys(this.data.events).length) return;
    const run = this.data.turns.at(-1)?.run;
    if (active(run) || run?.status === 'awaiting_confirmation') return;
    this.goHome();
  }

  goHome() {
    this.departed.add(this.generation);
    this.exits.add(this.data.turns.map(turn => turn.run), this.data.owner);
    const ready = this.view.ready;
    // Invalidate every outstanding response before clearing the visible conversation.
    const epoch = ++this.generation;
    clearTimeout(this.timer); clearTimeout(this.toastTimer); clearTimeout(this.profileTimer);
    this.polling = false;
    this.data = {...empty(), owner: this.data.owner};
    try { this.storage.setItem(this.key, JSON.stringify(this.data)); }
    catch { try { this.storage.removeItem(this.key); } catch { /* Navigation must still work without storage. */ } }
    this.show({...this.data, previousId: undefined, pending: undefined, busy: false, sending: [], error: '', toast: ''});
    if (ready) void this.refreshProfileStatus(epoch);
    else void this.init();
  }
  private clearConversation() { clearTimeout(this.timer); this.save({previousId: undefined, turns: [], reactions: {}, events: {}, pending: undefined}); this.show({error: ''}); }
  async retry() { if (!this.view.ready) return this.init(); if (this.data.pending) return this.sendPending(); return this.refresh(); }
  private async sendPending() {
    if (!this.view.ready || this.view.busy || !this.data.pending) return;
    const pending = this.data.pending; const epoch = this.generation;
    this.show({busy: true, error: ''});
    try {
      if (pending.type === 'end') { await this.api.end(pending.session_id); if (epoch === this.generation) this.clearConversation(); }
      else {
        const run = pending.type === 'submit' ? await this.api.submit(pending.input) : await this.api.confirm(pending.request_id, pending.kind);
        if (epoch !== this.generation && this.departed.has(epoch)) this.exits.add([run], this.data.owner);
        if (epoch === this.generation) this.accept(run, pending.type === 'submit' ? pending.input.user_query : undefined);
      }
    } catch (error) {
      if (epoch === this.generation && error instanceof APIError && [403, 409, 422].includes(error.status) && pending.type === 'submit') this.save({pending: undefined});
      await this.fail(error, epoch);
    } finally { if (epoch === this.generation) this.show({busy: false}); }
  }
  async react(snapshot: string, action: Reaction) {
    if (!this.view.ready || this.view.sending.includes(snapshot) || this.data.events[snapshot]) return;
    const previous = this.data.reactions[snapshot];
    const event: Event = {event_id: crypto.randomUUID(), item_snapshot_id: snapshot, action, operation: !previous ? 'record' : previous.action === action ? 'cancel' : 'correct', ...(previous ? {target_event_id: previous.event_id} : {}), occurred_at: new Date().toISOString()};
    await this.enqueue(snapshot, event);
  }
  async click(snapshot: string) {
    if (!this.view.ready) return;
    const event: Event = {event_id: crypto.randomUUID(), item_snapshot_id: snapshot, action: 'click', operation: 'record', occurred_at: new Date().toISOString()};
    await this.enqueue(event.event_id, event);
  }
  private async enqueue(key: string, event: Event) {
    try { this.save({events: {...this.data.events, [key]: event}}); await this.retryEvent(key); } catch(e) { await this.fail(e, this.generation); }
  }
  async retryEvent(key: string) {
    const event = this.data.events[key];
    if (!event || !this.view.ready || this.view.sending.includes(key)) return;
    const epoch = this.generation; this.show({sending: [...this.view.sending, key], error: ''});
    try {
      await this.api.event(event); if (epoch !== this.generation) return;
      const events = {...this.data.events}; delete events[key]; const reactions = {...this.data.reactions};
      if (event.action !== 'click') {
        if (event.operation === 'cancel') delete reactions[event.item_snapshot_id];
        else reactions[event.item_snapshot_id] = {action: event.action, event_id: event.event_id};
      }
      this.save({events, reactions});
      if (event.action !== 'click') this.notify(`${event.action === 'like' ? '좋아요' : '싫어요'}${event.operation === 'correct' ? '로 변경됐어요.' : event.operation === 'cancel' ? '가 취소됐어요.' : '가 저장됐어요.'}`);
    } catch (error) { await this.fail(error, epoch); }
    finally { if (epoch === this.generation) this.show({sending: this.view.sending.filter(k => k !== key)}); }
  }
  dispose() { this.exits.stop(); ++this.generation; clearTimeout(this.timer); clearTimeout(this.toastTimer); clearTimeout(this.profileTimer); }
}
