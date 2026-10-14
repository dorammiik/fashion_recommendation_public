import {test, expect, type BrowserContext} from '@playwright/test';

async function fakeService(context: BrowserContext) {
  const submissions: Record<string, unknown>[] = [];
  const ended: string[] = [];
  const events: unknown[] = [];
  const runs = new Map<string, object>();
  await context.route('https://product.example/**', route => route.fulfill({contentType:'text/html',body:'<h1>상품</h1>'}));
  await context.route('http://127.0.0.1:8765/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    const headers = {'Access-Control-Allow-Origin':'http://127.0.0.1:5173','Access-Control-Allow-Credentials':'true',
      'Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token','Access-Control-Allow-Methods':'POST, GET, OPTIONS'};
    const reply = (json: unknown, status = 200) => route.fulfill({status,headers,json});
    if (request.method() === 'OPTIONS') return reply({});
    if (path === '/health') return reply({processor_connected:false,scheduler_running:false});
    if (path.endsWith('/bootstrap')) return reply({user_id:'exit-user',csrf_token:'csrf',expires_at:'2099'});
    if (path === '/api/recommendations') {
      const input = request.postDataJSON(); submissions.push(input);
      const id = `r${submissions.length}`;
      const run = {request_id:id,session_id:`s${submissions.length}`,status:'completed',question:null,
        response:{intro:'추천 결과',remarks:'eBay 상품 정보',recommendations:[{rank:1,item_id:'item',title:'상품 제목',price:null,
          image_url:null,item_web_url:'https://product.example/item',recommendation_reason:'설명',key_features:[]}],outro:'다음 요청을 알려주세요.',next_recommendation:[]},
        item_snapshots:[{item_id:'item',rank:1,item_snapshot_id:'snapshot'}],error_type:null,progress:{},updated_at:null,resumable:false,recovery_reason:null};
      runs.set(id, run); return reply(run);
    }
    if (path === '/api/recommendations/status') return reply(runs.get(request.postDataJSON().request_id));
    if (path === '/api/preference/events') { events.push(request.postDataJSON()); return reply({inserted:true,profile_updated:false}); }
    if (path === '/api/preference/sessions/end') {
      expect(request.headers()['x-csrf-token']).toBe('csrf');
      expect(request.headers()['content-type']).toBe('application/json');
      ended.push(request.postDataJSON().session_id); return reply({queued:true,profile_updated:false}, 202);
    }
    throw new Error(`Unexpected fake request: ${path}`);
  });
  return {submissions, ended, events};
}

async function submit(page: import('@playwright/test').Page) {
  await page.getByRole('textbox', {name:'추천 요청'}).fill('옷 추천해줘');
  await page.getByRole('button', {name:'추천 요청 전송'}).click();
  await expect(page.locator('.product')).toHaveCount(1);
}

test('reload, hidden and product popup preserve the session; home and new recommendation end it', async ({page, context}) => {
  const service = await fakeService(context);
  await page.goto('/?mode=live'); await submit(page);
  const snapshot = await page.evaluate(() => JSON.parse(sessionStorage.getItem('fashion.ui.v1.live')!).turns[0].run.session_id);
  await page.reload(); await expect(page.locator('.product')).toHaveCount(1);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem('fashion.ui.v1.live')!).turns[0].run.session_id)).toBe(snapshot);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {configurable:true,get:() => 'hidden'});
    document.dispatchEvent(new Event('visibilitychange'));
    delete (document as unknown as Record<string, unknown>).visibilityState;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', {name:'상품 제목',exact:true}).click();
  const popup = await popupPromise; await popup.waitForLoadState(); await popup.close(); await page.bringToFront();
  await expect.poll(() => service.events.length).toBe(1);
  expect(service.ended).toEqual([]); expect(service.submissions).toHaveLength(1);
  await page.getByRole('button', {name:'홈 돌아가기',exact:true}).click();
  await expect(page.getByRole('heading', {name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
  await expect.poll(() => service.ended).toEqual(['s1']);
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem('fashion.ui.v1.live.exits')!).sessions)).toEqual([]);
  await page.reload(); await submit(page);
  expect(service.submissions[1]).toMatchObject({new_request:true});
  expect(service.submissions[1]).not.toHaveProperty('previous_request_id');
  await page.getByRole('button', {name:'새 추천 시작하기'}).click();
  await expect.poll(() => service.ended).toEqual(['s1','s2']);
});

test('same-tab mode switching ends the departing session and returns to a fresh screen', async ({page, context}) => {
  const service = await fakeService(context);
  await page.goto('/?mode=live'); await submit(page);
  await page.getByText('개발 미리보기', {exact:true}).click();
  await page.getByRole('link', {name:'mock 미리보기로 이동'}).click();
  await expect(page.getByRole('heading', {name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
  await expect.poll(() => service.ended).toEqual(['s1']);
  await page.getByText('개발 미리보기', {exact:true}).click();
  await page.getByRole('link', {name:'실제 API 모드 열기'}).click();
  await expect(page.getByRole('heading', {name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
  await expect(page.locator('.turn')).toHaveCount(0);
  expect(service.submissions).toHaveLength(1);
  await submit(page);
  expect(service.submissions[1]).toMatchObject({new_request:true});
  expect(service.submissions[1]).not.toHaveProperty('previous_request_id');
});
