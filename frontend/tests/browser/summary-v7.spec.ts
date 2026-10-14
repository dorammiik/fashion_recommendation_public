import {test, expect, type Page} from '@playwright/test';

const prompts = ['1번 추천과 비슷한 원피스 찾아줘.', '1번 추천과 어울리는 가디건 찾아줘.'];
async function fixture(page: Page, status = 'completed', empty = false) {
  const submissions: {previous_request_id?: string; user_query: string}[] = [];
  const runs = new Map<string, object>();
  await page.route('http://127.0.0.1:8765/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    const headers = {'Access-Control-Allow-Origin':'http://127.0.0.1:5173','Access-Control-Allow-Credentials':'true','Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token','Access-Control-Allow-Methods':'POST, OPTIONS'};
    if (request.method() === 'OPTIONS') return route.fulfill({status:200, headers, body:'{}'});
    if (path === '/health') return route.fulfill({status:200,headers,json:{processor_connected:false,scheduler_running:false}});
    if (path.endsWith('/bootstrap')) return route.fulfill({status:201, headers, json:{user_id:'test',csrf_token:'csrf',expires_at:'2099-01-01'}});
    if (path === '/api/recommendations/status') {
      return route.fulfill({status:200, headers, json:runs.get(request.postDataJSON().request_id)});
    }
    if (path === '/api/recommendations') {
      submissions.push(request.postDataJSON());
      const response = status === 'blocked' ? {intro:'정보가 필요해요.', reasons:[{reason:'사진을 제공해주세요.'}]} : {
        intro: empty ? '조건에 맞는 원피스를 찾지 못했어요.' : '원피스 한 개를 찾았어요.',
        remarks: empty ? '후보 상품의 평가 처리에 실패했어요.' : '일부 길이 조건은 확인되지 않았어요. eBay 상품 정보예요.',
        recommendations: empty ? [] : [{rank:1,item_id:'dress',title:'원피스',image_url:null,item_web_url:null,recommendation_reason:'상품 설명이에요.',key_features:[]}],
        outro: empty ? '원하시면 같은 조건으로 다시 검색해볼게요.' : '원하시는 색상도 알려주세요.',
        next_recommendation: empty ? [] : prompts, feedback_notice:null,
      };
      const run = {request_id:`request-${submissions.length}`,session_id:'session',status,response,
        item_snapshots:[],question:null,progress:{},updated_at:null,resumable:false,recovery_reason:null,error_type:null};
      runs.set(run.request_id, run);
      return route.fulfill({status:200,headers,json:run});
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  return submissions;
}

test('v7 remarks, rotating prompts, user input preservation and originating request', async ({page}) => {
  const submissions = await fixture(page);
  await page.clock.install();
  await page.goto('/?mode=live');
  const input = page.getByRole('textbox', {name:'추천 요청'});
  await input.fill('원피스 추천해줘');
  await page.getByRole('button',{name:'추천 요청 전송'}).click();
  await expect(page.locator('.remarks')).toHaveText('일부 길이 조건은 확인되지 않았어요. eBay 상품 정보예요.');
  await expect(page.locator('.intro + .remarks-box')).toHaveCount(1);
  await expect(input).toHaveAttribute('placeholder', prompts[0]);
  await page.clock.fastForward(3000);
  await expect(input).toHaveAttribute('placeholder', prompts[1]);
  await input.fill('작성 중인 요청');
  await page.clock.fastForward(10000);
  await expect(input).toHaveValue('작성 중인 요청');
  expect(submissions).toHaveLength(1);
  await input.fill(prompts[1]);
  await page.getByRole('button',{name:'추천 요청 전송'}).click();
  await expect(page.locator('.turn')).toHaveCount(2);
  await expect(page.locator('.remarks')).toHaveCount(2);
  expect(submissions[1]).toMatchObject({previous_request_id:'request-1',user_query:prompts[1]});
  await page.reload();
  await expect(page.locator('.remarks')).toHaveCount(2);
  await expect(input).toHaveAttribute('placeholder', prompts[0]);
});

for (const status of ['completed', 'blocked']) {
  test(`no invented follow-up anchor for ${status} without products`, async ({page}) => {
    await fixture(page, status, true);
    await page.goto('/?mode=live');
    const input = page.getByRole('textbox',{name:'추천 요청'});
    await input.fill('원피스 추천해줘');
    await page.getByRole('button',{name:'추천 요청 전송'}).click();
    await expect(input).toHaveAttribute('placeholder','');
    if (status === 'completed') {
      await expect(page.locator('.remarks')).toHaveText('후보 상품의 평가 처리에 실패했어요.');
      await expect(page.locator('.outro')).toHaveText('원하시면 같은 조건으로 다시 검색해볼게요.');
      await expect(page.locator('.empty-state')).toHaveCount(0);
    } else {
      await expect(page.getByText('사진을 제공해주세요.')).toBeVisible();
      await expect(page.locator('.remarks')).toHaveCount(0);
    }
  });
}
