import { afterEach, expect, it, vi } from 'vitest';
import { LiveAPI } from '../src/api';
afterEach(() => vi.unstubAllGlobals());
it('uses cookies, memory CSRF and exact API bodies including status POST', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({user_id:'u',csrf_token:'token',expires_at:'2099'}),{status:201})).mockResolvedValueOnce(new Response(JSON.stringify({status:'completed'}),{status:200}));
  vi.stubGlobal('fetch',fetch); const api=new LiveAPI('http://127.0.0.1:8765'); await api.bootstrap(); await api.status('request');
  expect(fetch.mock.calls[1][0]).toBe('http://127.0.0.1:8765/api/recommendations/status');
  expect(fetch.mock.calls[1][1]).toMatchObject({method:'POST',credentials:'include',headers:{'X-CSRF-Token':'token'},body:'{"request_id":"request"}'});
});
it('accepts HTTP 200 deduplicated recommendation results', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({request_id:'same',status:'completed'}),{status:200})));
  const api=new LiveAPI(''); expect(await api.submit({user_query:'옷',idempotency_key:'key',new_request:true})).toMatchObject({request_id:'same',status:'completed'});
});
it.each([
  [true, true, true], [true, false, false], [false, true, false], [false, false, false],
])('reports profile updates for processor=%s scheduler=%s', async (processor, scheduler, enabled) => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({processor_connected: processor, scheduler_running: scheduler})));
  vi.stubGlobal('fetch', fetch);
  expect(await new LiveAPI('http://127.0.0.1:8765').profileUpdatesEnabled()).toBe(enabled);
  expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8765/health', expect.objectContaining({cache: 'no-store'}));
});
it('keeps explicit session-end requests alive during navigation with cookies and CSRF', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({user_id:'u',csrf_token:'csrf',expires_at:'2099'})))
    .mockResolvedValueOnce(new Response(JSON.stringify({queued:true}), {status:202}));
  vi.stubGlobal('fetch', fetch);
  const api = new LiveAPI('http://127.0.0.1:8765');
  await api.bootstrap(); await api.end('session');
  expect(fetch.mock.calls[1]).toEqual(['http://127.0.0.1:8765/api/preference/sessions/end', expect.objectContaining({
    keepalive:true, credentials:'include', method:'POST', body:'{"session_id":"session"}',
    headers:{'Content-Type':'application/json','X-CSRF-Token':'csrf'},
  })]);
});
