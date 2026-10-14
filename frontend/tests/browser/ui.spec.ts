import { test, expect } from '@playwright/test';
test.beforeEach(async ({page}) => {
  // These tests must never reach a live recommendation server.
  await page.route('http://127.0.0.1:8765/**', route => route.abort());
});
test.afterEach(async ({page}) => {
  await expect(page.locator('.composer-hint')).toHaveCount(0);
  await expect(page.getByText('미리보기에서는 예시 상품을 보여드려요.', {exact:true})).toHaveCount(0);
  await expect(page.getByText('Enter로 전송 · Shift + Enter로 줄바꿈', {exact:true})).toHaveCount(0);
  await expect(page.getByText('연결을 준비하고 있어요', {exact:true})).toHaveCount(0);
});
async function submit(page: import('@playwright/test').Page) {
  await page.getByRole('textbox',{name:'추천 요청'}).fill('가을에 입기 좋은 검은색 바지 추천해줘.');
  await page.getByRole('button',{name:'추천 요청 전송'}).click();
}
test('quick start home; results, feedback, reload, correction, cancellation and new screen',async ({page}) => {
  await page.goto('/'); await expect(page.getByRole('textbox')).toBeEnabled();
  await expect(page.locator('.home-example-card')).toHaveCount(4);
  await expect(page.locator('.home-examples .quick-start-trigger')).toHaveCount(4);
  await expect(page.getByRole('textbox')).toHaveValue('');
  await page.screenshot({path:'test-results/desktop-home.png',fullPage:true});
  await submit(page); await expect(page.locator('.product')).toHaveCount(4,{timeout:10000});
  await expect(page.getByRole('heading', {name:'이용 전 참고해주세요'})).toBeVisible();
  await expect(page.locator('.remarks-box')).toHaveCSS('background-color', 'rgb(255, 249, 230)');
  await expect(page.locator('.product').first().locator('.product-price')).toHaveText('29.99 USD');
  await expect(page.getByRole('button', {name:'이전 상품 보기'})).toBeHidden();
  await page.getByRole('button', {name:'다음 상품 보기'}).click();
  await expect(page.getByRole('button', {name:'다음 상품 보기'})).toBeHidden();
  await expect.poll(() => page.locator('.carousel').evaluate(el => el.scrollLeft)).toBeGreaterThan(100);
  await page.getByRole('button', {name:'이전 상품 보기'}).click();
  await expect.poll(() => page.locator('.carousel').evaluate(el => el.scrollLeft)).toBeLessThan(2);
  await page.screenshot({path:'test-results/desktop-results.png',fullPage:true});
  await page.getByRole('button',{name:'1번 상품 좋아요',exact:true}).click(); await expect(page.locator('.toast')).toHaveText('좋아요가 저장됐어요.');
  await page.reload(); await expect(page.getByRole('button',{name:'1번 상품 좋아요',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'1번 상품 싫어요',exact:true}).click(); await expect(page.locator('.toast')).toHaveText('싫어요로 변경됐어요.');
  await page.getByRole('button',{name:'1번 상품 싫어요',exact:true}).click(); await expect(page.locator('.toast')).toHaveText('싫어요가 취소됐어요.');
  await page.getByRole('button',{name:'홈 돌아가기',exact:true}).click(); await expect(page.getByRole('heading',{name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
});
test('ambiguous request resumes using the same request ID',async ({page}) => {
  await page.goto('/'); await page.getByText('개발 미리보기',{exact:true}).click(); await page.getByLabel('화면 시나리오').selectOption('confirmation'); await submit(page);
  await expect(page.getByRole('heading',{name:'이전 추천에 이어서 찾으시는 건가요?'})).toBeVisible();
  const before = await page.evaluate(() => JSON.parse(sessionStorage.getItem('fashion.ui.v1.mock')!).turns[0].run.request_id);
  await page.getByRole('button',{name:'이어서 찾기',exact:true}).click(); await expect(page.locator('.product')).toHaveCount(4);
  const after = await page.evaluate(() => JSON.parse(sessionStorage.getItem('fashion.ui.v1.mock')!).turns[0].run.request_id); expect(after).toBe(before);
});
for (const [scenario, text] of [['empty','조건에 맞는 상품을 찾지 못했어요.'],['blocked','찾으시는 옷의 종류를 확인하지 못해 추천을 진행하지 못했어요.'],['failed','추천을 마치지 못했어요. 요청을 다시 입력해 주세요.'],['interrupted','추천이 중단됐어요.']]) {
  test(`terminal scenario: ${scenario}`,async ({page}) => {await page.goto('/'); await page.getByText('개발 미리보기',{exact:true}).click(); await page.getByLabel('화면 시나리오').selectOption(scenario); await submit(page); await expect(page.getByText(text,{exact:true})).toBeVisible({timeout:10000}); await expect(page.getByRole('button',{name:'새 추천 시작하기'})).toBeEnabled();});
}
test('mobile carousel does not overflow the document and composer stays usable',async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await page.goto('/'); await expect(page.getByRole('textbox')).toBeEnabled(); await page.screenshot({path:'test-results/mobile-home.png',fullPage:true});
  await submit(page); await expect(page.locator('.product')).toHaveCount(4);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('.carousel').evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  await page.screenshot({path:'test-results/mobile-results.png',fullPage:true});
});
test('missing image and product URL display safe placeholders',async ({page}) => {
  await page.goto('/'); await page.getByText('개발 미리보기',{exact:true}).click(); await page.getByLabel('화면 시나리오').selectOption('missing'); await submit(page);
  await expect(page.locator('.product').first().getByText('이미지 준비 중')).toBeVisible(); await expect(page.locator('.product').first().locator('a')).toHaveCount(0);
});
test('null feedback notice is hidden',async ({page}) => {
  await page.goto('/'); await page.getByText('개발 미리보기',{exact:true}).click(); await page.getByLabel('화면 시나리오').selectOption('no_notice'); await submit(page); await expect(page.locator('.product')).toHaveCount(4); await expect(page.locator('.feedback-notice')).toHaveCount(0);
});
test('live adapter retries a lost receipt with identical payload and accepts HTTP 200 without new execution', async ({page}) => {
  const inputs: unknown[] = [];
  await page.route('http://127.0.0.1:8765/**', async route => {
    const url = new URL(route.request().url());
    const headers = {'Access-Control-Allow-Origin':'http://127.0.0.1:5173','Access-Control-Allow-Credentials':'true','Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token','Access-Control-Allow-Methods':'POST, OPTIONS'};
    if (route.request().method() === 'OPTIONS') return route.fulfill({status:200,headers,body:'{}'});
    if (url.pathname === '/health') return route.fulfill({status:200,headers,json:{processor_connected:false,scheduler_running:false}});
    if (url.pathname.endsWith('/bootstrap')) return route.fulfill({status:201,headers,json:{user_id:'test-user',csrf_token:'csrf',expires_at:'2099-01-01'}});
    if (url.pathname === '/api/recommendations') {
      inputs.push(route.request().postDataJSON());
      expect(route.request().headers()['x-csrf-token']).toBe('csrf');
      if (inputs.length === 1) return route.abort('failed');
      return route.fulfill({status:200,headers,json:{request_id:'existing',session_id:'session',status:'completed',response:{intro:'이미 완료된 추천이에요.',recommendations:[],outro:'다른 조건도 알려주세요.',feedback_notice:null},item_snapshots:[],question:null,progress:{},updated_at:null,resumable:false,recovery_reason:null,error_type:null}});
    }
    throw new Error(`Unexpected request: ${url.pathname}`);
  });
  await page.goto('/?mode=live'); await submit(page); await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button',{name:'같은 요청 다시 시도',exact:true}).click();
  await expect(page.getByText('이미 완료된 추천이에요.')).toBeVisible(); expect(inputs).toHaveLength(2); expect(inputs[1]).toEqual(inputs[0]);
});
test('mock does not call the live API on load, submission, feedback or new recommendation', async ({page}) => {
  const apiRequests: string[] = []; page.on('request', request => {if(request.url().includes(':8765')) apiRequests.push(request.url());});
  await page.goto('/'); await submit(page); await expect(page.locator('.product')).toHaveCount(4);
  await page.getByRole('button',{name:'1번 상품 좋아요',exact:true}).click(); await expect(page.locator('.toast')).toHaveText('좋아요가 저장됐어요.');
  await page.getByRole('button',{name:'새 추천 시작하기'}).click(); await expect(page.getByRole('heading',{name:'어떤 옷을 찾고 있나요?'})).toBeVisible(); expect(apiRequests).toEqual([]);
});
test('home navigation confirms ongoing work and restores the welcome screen', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('textbox')).toBeEnabled();
  await page.clock.install();
  await page.clock.pauseAt(new Date());
  await submit(page);
  const home = page.getByRole('button', {name:'홈 돌아가기', exact:true});
  await expect(home).toBeEnabled();
  await expect(page.getByRole('group', {name:'추천 프로필 모드'})).toHaveCount(0);
  page.once('dialog', async dialog => {expect(dialog.type()).toBe('confirm'); await dialog.dismiss();});
  await home.click();
  await expect(home).toBeVisible();
  page.once('dialog', async dialog => {await dialog.accept();});
  await home.click();
  await expect(page.getByRole('heading', {name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
  await expect(page.getByRole('button', {name:'Cold', exact:true})).toHaveAttribute('aria-pressed','true');
  await page.clock.fastForward(10000);
  await expect(page.locator('.turn')).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', {name:'어떤 옷을 찾고 있나요?'})).toBeVisible();
});

for (const [title, id, mode, query] of [
  ['복잡한 조건으로 찾기', 'complex', 'cold', '페스티벌에 입고 가기 좋은 꽃무늬 드레스 추천해줘. 투피스로 된 것도 괜찮은데 바지는 별로야. 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어'],
  ['이전 추천과 비슷하게', 'similar', 'cold', '이전 추천 1번과 비슷한 원피스 찾아줘'],
  ['사용자 A 취향으로', 'profile_a', 'warm', '주말에 편하게 입을 티셔츠 찾아줘'],
  ['사용자 B 취향으로', 'profile_b', 'warm', '주말에 편하게 입을 티셔츠 찾아줘'],
]) {
  test(`quick start sends ${id} immediately`, async ({page}) => {
    const requests: unknown[] = [];
    await page.route('http://127.0.0.1:8765/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/bootstrap')) return route.fulfill({json:{user_id:'demo',csrf_token:'test',expires_at:'2099-01-01'}});
      if (path === '/health') return route.fulfill({json:{processor_connected:false,scheduler_running:false}});
      if (path === '/api/recommendations') requests.push(route.request().postDataJSON());
      return route.fulfill({json:{request_id:'quick-run',session_id:'quick-session',status:'queued',question:null,response:null,item_snapshots:[],error_type:null,progress:{},updated_at:null,resumable:false,recovery_reason:null}});
    });
    await page.goto('/?mode=live');
    const card = page.getByRole('button', {name:title,exact:true});
    await expect(card).toBeEnabled();
    // A preset must override the current toggle and text.
    await page.getByRole('button',{name:mode === 'cold' ? 'Warm' : 'Cold',exact:true}).click();
    await page.getByRole('textbox').fill('다른 검색어');
    if (id === 'profile_a') {
      await card.focus();
      await page.keyboard.press('Enter');
    } else await card.click();
    await expect(page.locator('.user-message')).toHaveText(query);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({quick_start:id,personalization_mode:mode,user_query:query,new_request:true});
    await expect(page.getByRole('button',{name:'추천 요청 전송'})).toBeDisabled();
    await expect(page.locator('.home-examples')).toHaveCount(0);
  });
}
