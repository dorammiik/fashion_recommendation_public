// Explicit, non-recommendation smoke check against an already-running local API.
// Creates a browser anonymous user; never submits recommendations or feedback.
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
const frontend = process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const api = process.env.API_BASE_URL || 'http://127.0.0.1:8765';
const browser = await chromium.launch({channel: 'chrome'});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const unexpected = [];
  const allowed = new Set(['/health', '/api/preference/bootstrap', '/api/preference/profile', '/api/recommendations/status']);
  await page.route(`${api}/**`, async route => {
    const path = new URL(route.request().url()).pathname;
    if (!allowed.has(path)) { unexpected.push(path); return route.abort(); }
    return route.continue();
  });
  const bootstrapResponse = () => page.waitForResponse(response => response.url() === `${api}/api/preference/bootstrap` && response.request().method() === 'POST');
  const initial = bootstrapResponse();
  await page.goto(`${frontend}/?mode=live`);
  const firstResponse = await initial;
  assert.equal(firstResponse.status(), 201);
  const first = await firstResponse.json();
  await page.getByRole('textbox', {name: '추천 요청'}).waitFor();
  assert.equal(await page.getByRole('textbox', {name: '추천 요청'}).isEnabled(), true);
  const cookie = (await context.cookies(api)).find(cookie => cookie.name === 'fashion_anon');
  assert.ok(cookie?.httpOnly && cookie.sameSite === 'Lax');
  const restored = bootstrapResponse();
  await page.reload();
  const restoredResponse = await restored;
  assert.equal(restoredResponse.status(), 200);
  const auth = await restoredResponse.json();
  assert.equal(auth.user_id, first.user_id);
  const results = await page.evaluate(async ({api, csrf}) => {
    async function post(token) {
      const response = await fetch(`${api}/api/recommendations/status`, {
        method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json', ...(token ? {'X-CSRF-Token': token} : {})},
        body: JSON.stringify({request_id:'frontend-connection-check-nonexistent'}),
      });
      return {status: response.status, body: await response.json()};
    }
    const health = await fetch(`${api}/health`, {credentials:'include'}).then(r => r.json());
    const profile = await fetch(`${api}/api/preference/profile`, {credentials:'include'});
    return {health, profileStatus: profile.status, missingCSRF: await post(null), authenticatedStatus: await post(csrf)};
  }, {api, csrf: auth.csrf_token});
  assert.equal(results.health.status, 'ok');
  assert.equal(results.profileStatus, 200);
  assert.equal(results.missingCSRF.status, 403);
  assert.equal(results.missingCSRF.body.error, 'invalid_csrf_token');
  // A nonexistent ID safely exercises ownership lookup without creating any job.
  assert.equal(results.authenticatedStatus.status, 409);
  assert.equal(results.authenticatedStatus.body.error, 'invalid_state_or_reference');
  assert.deepEqual(unexpected, []);
  console.log('PASS: browser Origin/CORS, bootstrap 201→200, HttpOnly cookie, same user after reload, profile GET, CSRF protection, authenticated recommendation status route.');
  console.log('No recommendation, feedback, session creation or session end requests were sent.');
  await context.close();
} finally { await browser.close(); }
