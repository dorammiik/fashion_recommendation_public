import { afterEach, describe, expect, it, vi } from 'vitest';
import { Store } from '../src/store';
import { APIError } from '../src/api';
import type { API, Run } from '../src/types';
class MemoryStorage implements Storage {
  data = new Map<string,string>(); length = 0;
  getItem(k: string) { return this.data.get(k) ?? null; }
  setItem(k: string,v: string) { this.data.set(k,v); }
  removeItem(k: string) { this.data.delete(k); }
  clear() { this.data.clear(); }
  key() { return null; }
}
const run = (status: Run['status'] = 'completed'): Run => ({request_id:'r1',session_id:'s1',status,question:null,response:null,item_snapshots:[],error_type:null,progress:{},updated_at:null,resumable:false,recovery_reason:null});
function fixture() {
  const api: API = {bootstrap: vi.fn(async () => ({user_id:'u1',csrf_token:'secret',expires_at:'2099-01-01'})),submit:vi.fn(async () => run()),status:vi.fn(async () => run()),confirm:vi.fn(async () => run('queued')),event:vi.fn(async input => ({event_id:input.event_id,inserted:true,receipt_sequence:1,profile_updated:false})),end:vi.fn(async () => ({}))};
  const storage = new MemoryStorage(); const store = new Store(api,storage,'test'); stores.push(store); return {api,storage,store};
}
const stores: Store[] = [];
afterEach(() => {stores.forEach(s => s.dispose()); stores.length=0; vi.useRealTimers();});
describe('request and feedback lifecycle', () => {
  it('persists a submission before sending and reuses exact input after response loss and reload', async () => {
    const {api,storage,store} = fixture(); await store.init();
    vi.mocked(api.submit).mockRejectedValueOnce(new TypeError('offline'));
    await store.submit('검은 바지'); const first = vi.mocked(api.submit).mock.calls[0][0];
    expect(storage.getItem('test')).not.toContain('secret');
    const restored = new Store(api,storage,'test'); stores.push(restored); await restored.init();
    expect(api.submit).toHaveBeenCalledTimes(1); await restored.retry();
    expect(vi.mocked(api.submit).mock.calls[1][0]).toEqual(first);
    expect(restored.getSnapshot().turns[0].run.status).toBe('completed');
  });
  it('ends the old session before a new screen and creates no recommendation until submit', async () => {
    const {api,store} = fixture(); await store.init(); await store.submit('첫 요청'); await store.startNew();
    expect(api.end).toHaveBeenCalledWith('s1'); expect(api.submit).toHaveBeenCalledTimes(1); expect(store.getSnapshot().turns).toEqual([]);
    await store.submit('새 요청'); expect(vi.mocked(api.submit).mock.calls[1][0]).toMatchObject({new_request:true});
  });
  it('sends a followup with the previous request and no explicit new flag', async () => {
    const {api,store} = fixture(); await store.init(); await store.submit('첫 요청'); await store.submit('비슷한 옷');
    expect(vi.mocked(api.submit).mock.calls[1][0]).toMatchObject({new_request:false,previous_request_id:'r1'});
  });
  it('restores reactions and targets the right successful event when cancelling or switching', async () => {
    const {api,storage,store} = fixture(); await store.init(); await store.react('snapshot','like');
    const first = vi.mocked(api.event).mock.calls[0][0];
    const restored = new Store(api,storage,'test'); stores.push(restored); await restored.init();
    expect(restored.getSnapshot().reactions.snapshot.action).toBe('like');
    await restored.react('snapshot','dislike'); const corrected = vi.mocked(api.event).mock.calls[1][0];
    expect(corrected).toMatchObject({operation:'correct',target_event_id:first.event_id,action:'dislike'});
    await restored.react('snapshot','dislike');
    expect(vi.mocked(api.event).mock.calls[2][0]).toMatchObject({operation:'cancel',target_event_id:corrected.event_id});
    expect(restored.getSnapshot().reactions.snapshot).toBeUndefined();
  });
  it('keeps failed feedback pending, retries its exact event and confirms selection only on success', async () => {
    const {api,store} = fixture(); await store.init(); vi.mocked(api.event).mockRejectedValueOnce(new TypeError());
    await store.react('snapshot','like'); expect(store.getSnapshot().reactions.snapshot).toBeUndefined();
    const original = vi.mocked(api.event).mock.calls[0][0]; await store.react('snapshot','dislike'); expect(api.event).toHaveBeenCalledTimes(1);
    await store.retryEvent('snapshot'); expect(vi.mocked(api.event).mock.calls[1][0]).toEqual(original); expect(store.getSnapshot().reactions.snapshot.action).toBe('like');
  });
  it('bootstraps on 401 without replaying another user’s events', async () => {
    const {api,store} = fixture(); await store.init(); await store.submit('옷');
    vi.mocked(api.event).mockRejectedValueOnce(new APIError(401,'bootstrap_required'));
    await store.react('snapshot','like'); expect(api.bootstrap).toHaveBeenCalledTimes(2); expect(api.event).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().events).toEqual({}); expect(store.getSnapshot().turns).toEqual([]);
  });
  it('clears a different owner’s stored request without submitting or fetching it', async () => {
    const {api,storage,store} = fixture(); await store.init(); await store.submit('옷');
    vi.mocked(api.bootstrap).mockResolvedValue({user_id:'u2',csrf_token:'new',expires_at:'2099'});
    const restored = new Store(api,storage,'test'); stores.push(restored); await restored.init();
    expect(restored.getSnapshot().turns).toEqual([]); expect(api.status).not.toHaveBeenCalled();
  });
  it('serializes polling, stops at confirmation, and confirms the same request', async () => {
    vi.useFakeTimers(); const {api,store} = fixture(); await store.init(); vi.mocked(api.submit).mockResolvedValue(run('queued')); await store.submit('옷');
    let resolve!: (value:Run) => void; vi.mocked(api.status).mockImplementationOnce(() => new Promise(r => {resolve=r;}));
    await vi.advanceTimersByTimeAsync(5000); await vi.advanceTimersByTimeAsync(20000); expect(api.status).toHaveBeenCalledTimes(1);
    resolve(run('awaiting_confirmation')); await vi.advanceTimersByTimeAsync(0); await vi.advanceTimersByTimeAsync(20000); expect(api.status).toHaveBeenCalledTimes(1);
    await store.confirm('followup'); expect(api.confirm).toHaveBeenCalledWith('r1','followup'); expect(api.submit).toHaveBeenCalledTimes(1);
  });
  it('locks a confirmation answer after response loss and retries only that answer', async () => {
    const {api,store} = fixture(); await store.init(); vi.mocked(api.submit).mockResolvedValue(run('awaiting_confirmation')); await store.submit('옷');
    vi.mocked(api.confirm).mockRejectedValueOnce(new TypeError()); await store.confirm('new'); await store.confirm('followup');
    expect(api.confirm).toHaveBeenCalledTimes(1); await store.retry(); expect(vi.mocked(api.confirm).mock.calls).toEqual([['r1','new'],['r1','new']]);
  });
  it('never automatically restarts an interrupted request', async () => {
    vi.useFakeTimers(); const {api,store} = fixture(); await store.init(); vi.mocked(api.submit).mockResolvedValue(run('interrupted')); await store.submit('옷');
    await vi.advanceTimersByTimeAsync(60000); expect(api.submit).toHaveBeenCalledTimes(1); expect(api.status).not.toHaveBeenCalled();
  });
  it('does not send when the idempotency key cannot be durably stored', async () => {
    const {api,storage,store} = fixture(); await store.init(); storage.setItem = () => {throw new Error('quota');}; await store.submit('옷');
    expect(api.submit).not.toHaveBeenCalled(); expect(store.getSnapshot().error).toContain('저장 공간');
  });
});

it('submitting from a new screen after failure explicitly starts a new request', async () => {
  const {api,store} = fixture(); await store.init();
  vi.mocked(api.submit).mockResolvedValueOnce(run('failed'));
  await store.submit('실패 요청'); await store.startNew();
  expect(store.getSnapshot().turns).toEqual([]);
  await store.submit('새 추천');
  expect(vi.mocked(api.submit).mock.calls[1][0]).toMatchObject({new_request:true});
});
it('refreshes automatic profile update availability and stops polling on disposal', async () => {
  vi.useFakeTimers();
  const {api, store} = fixture();
  const health = vi.fn().mockResolvedValueOnce(true).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(true);
  api.profileUpdatesEnabled = health;
  await store.init();
  expect(store.getSnapshot().profileUpdatesEnabled).toBe(true);
  await vi.advanceTimersByTimeAsync(15000);
  expect(store.getSnapshot().profileUpdatesEnabled).toBe(false);
  await vi.advanceTimersByTimeAsync(15000);
  expect(store.getSnapshot().profileUpdatesEnabled).toBe(true);
  store.dispose();
  await vi.advanceTimersByTimeAsync(30000);
  expect(health).toHaveBeenCalledTimes(3);
});
it.each(['queued', 'running', 'awaiting_confirmation', 'completed', 'blocked', 'failed', 'interrupted'] as const)('returns home from %s without carrying a previous request into the next submission', async status => {
  const {api, store, storage} = fixture();
  vi.mocked(api.submit).mockResolvedValue(run(status));
  vi.mocked(api.end).mockRejectedValue(new Error('offline'));
  await store.init(); await store.submit('첫 요청');
  store.goHome();
  expect(store.getSnapshot()).toMatchObject({turns: [], busy: false, error: '', pending: undefined, previousId: undefined});
  expect(JSON.parse(storage.getItem('test')!).turns).toEqual([]);
  await store.submit('새 요청');
  expect(vi.mocked(api.submit).mock.calls[1][0]).toMatchObject({new_request: true});
  expect(vi.mocked(api.submit).mock.calls[1][0]).not.toHaveProperty('previous_request_id');
});
it('ignores an old submission arriving after returning home and starting a new request', async () => {
  const {api, store} = fixture();
  let finish!: (value: Run) => void;
  vi.mocked(api.submit).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  await store.init();
  const old = store.submit('이전 요청');
  store.goHome();
  vi.mocked(api.submit).mockResolvedValue({...run(), request_id: 'new'});
  await store.submit('새 요청');
  finish(run()); await old;
  expect(store.getSnapshot().turns.map(turn => turn.run.request_id)).toEqual(['new']);
});
it('returns home even when saving browser state fails', async () => {
  const {store, storage} = fixture();
  await store.init(); await store.submit('첫 요청');
  vi.spyOn(storage, 'setItem').mockImplementation(() => {throw new Error('quota');});
  store.goHome();
  expect(store.getSnapshot()).toMatchObject({turns: [], pending: undefined, busy: false});
  expect(storage.getItem('test')).toBeNull();
});
it('leaves immediately without waiting for the session-end receipt', async () => {
  const {api, store} = fixture(); await store.init(); await store.submit('옷');
  vi.mocked(api.end).mockImplementation(() => new Promise(() => {}));
  await store.startNew();
  expect(store.getSnapshot()).toMatchObject({turns:[], busy:false, pending:undefined});
  await store.submit('새 요청');
  expect(vi.mocked(api.submit).mock.calls[1][0]).not.toHaveProperty('previous_request_id');
});
it('closes the prior session when leaving an unanswered confirmation without a session ID', async () => {
  const {api, store} = fixture(); await store.init(); await store.submit('옷');
  vi.mocked(api.submit).mockResolvedValue({...run('awaiting_confirmation'),request_id:'r2',session_id:null});
  await store.submit('다른 옷'); store.goHome();
  expect(api.end).toHaveBeenCalledWith('s1');
});
it('retries a lost exit receipt on reentry without restoring the old conversation', async () => {
  const {api, store, storage} = fixture(); await store.init(); await store.submit('옷');
  vi.mocked(api.end).mockRejectedValueOnce(new TypeError('offline'));
  store.goHome(); await Promise.resolve(); store.dispose();
  const restored = new Store(api, storage, 'test'); stores.push(restored); await restored.init();
  expect(api.end).toHaveBeenCalledTimes(2);
  expect(restored.getSnapshot().turns).toEqual([]);
  expect(storage.getItem('test.exits')).not.toContain('secret');
});
it('never replays another user’s exit queue after bootstrap', async () => {
  const {api, store, storage} = fixture(); await store.init(); await store.submit('옷');
  vi.mocked(api.end).mockRejectedValueOnce(new TypeError('offline'));
  store.goHome(); await Promise.resolve(); store.dispose();
  vi.mocked(api.bootstrap).mockResolvedValue({user_id:'u2',csrf_token:'new',expires_at:'2099'});
  const restored = new Store(api, storage, 'test'); stores.push(restored); await restored.init();
  expect(api.end).toHaveBeenCalledTimes(1);
});
it('preserves a session on disposal and normal reentry, but clears a mode-switch destination', async () => {
  const {api, store, storage} = fixture(); await store.init(); await store.submit('옷'); store.dispose();
  const restored = new Store(api, storage, 'test'); stores.push(restored); await restored.init();
  expect(restored.getSnapshot().turns).toHaveLength(1); expect(api.end).not.toHaveBeenCalled();
  restored.dispose();
  const fresh = new Store(api, storage, 'test', 5000, true); stores.push(fresh); await fresh.init();
  expect(fresh.getSnapshot().turns).toEqual([]); expect(api.end).toHaveBeenCalledWith('s1');
});
it('resolves a known queued request only to close its late-assigned session', async () => {
  vi.useFakeTimers();
  const {api, store} = fixture(); await store.init();
  vi.mocked(api.submit).mockResolvedValue({...run('queued'),session_id:null});
  vi.mocked(api.status).mockResolvedValue(run('running'));
  await store.submit('옷'); store.goHome();
  await vi.advanceTimersByTimeAsync(5000);
  expect(api.end).toHaveBeenCalledWith('s1'); expect(store.getSnapshot().turns).toEqual([]);
});
it('queues an offline restored session exit until bootstrap authenticates its owner', async () => {
  const {api, store, storage} = fixture(); await store.init(); await store.submit('옷'); store.dispose();
  let authenticate!: (auth: {user_id:string;csrf_token:string;expires_at:string}) => void;
  vi.mocked(api.bootstrap).mockImplementation(() => new Promise(resolve => {authenticate=resolve;}));
  const restored = new Store(api, storage, 'test'); stores.push(restored);
  restored.goHome();
  expect(api.end).not.toHaveBeenCalled();
  authenticate({user_id:'u1',csrf_token:'csrf',expires_at:'2099'});
  await Promise.resolve(); await Promise.resolve();
  expect(api.end).toHaveBeenCalledWith('s1');
  expect(restored.getSnapshot().turns).toEqual([]);
});

it('freezes Warm mode in the persisted submission and retries it unchanged', async () => {
  const {api,storage,store} = fixture(); await store.init();
  vi.mocked(api.submit).mockRejectedValueOnce(new TypeError('offline'));
  await store.submit('셔츠', 'warm');
  const first = vi.mocked(api.submit).mock.calls[0][0];
  expect(first.personalization_mode).toBe('warm');
  const restored = new Store(api,storage,'test'); stores.push(restored); await restored.init();
  await restored.retry();
  expect(vi.mocked(api.submit).mock.calls[1][0]).toEqual(first);
});

it('keeps the quick-start preset through response loss and blocks double submission', async () => {
  const {api, storage, store} = fixture(); await store.init();
  vi.mocked(api.submit).mockRejectedValueOnce(new TypeError('response lost'));
  await Promise.all([store.submit('주말에 편하게 입을 티셔츠 찾아줘', 'warm', 'profile_a'), store.submit('다른 요청', 'cold', 'complex')]);
  expect(api.submit).toHaveBeenCalledTimes(1);
  const first = vi.mocked(api.submit).mock.calls[0][0];
  expect(first).toMatchObject({quick_start:'profile_a',personalization_mode:'warm',new_request:true});
  const restored = new Store(api,storage,'test'); stores.push(restored); await restored.init(); await restored.retry();
  expect(vi.mocked(api.submit).mock.calls[1][0]).toEqual(first);
});
