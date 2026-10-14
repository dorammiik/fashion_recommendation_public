import {test, expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

// Exercise the actual production bundle with all network requests intercepted.
// Run npm run build before these checks; no real recommendation is submitted.
for (const query of ['', '?mode=live', '?mode=mock']) {
  test(`production remains live at /${query}`, async ({page}) => {
    const submissions: Record<string, unknown>[] = [];
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'https://fashion.test') return route.abort();
      if (url.pathname === '/health') return route.fulfill({json:{processor_connected:true,scheduler_running:true}});
      if (url.pathname.endsWith('/bootstrap')) return route.fulfill({json:{user_id:'demo',csrf_token:'test',expires_at:'2099-01-01'}});
      if (url.pathname === '/api/recommendations') submissions.push(route.request().postDataJSON());
      if (url.pathname.startsWith('/api/')) return route.fulfill({json:{request_id:'r1',session_id:'s1',status:'queued',response:null,item_snapshots:[],progress:{}}});
      const asset = url.pathname.startsWith('/assets/') ? url.pathname.slice(1) : 'index.html';
      return route.fulfill({body:readFileSync(resolve('dist', asset)), contentType:asset.endsWith('.js') ? 'application/javascript' : asset.endsWith('.css') ? 'text/css' : 'text/html'});
    });
    await page.goto(`https://fashion.test/${query}`);
    await expect(page.getByText('mock 모드', {exact:true})).toHaveCount(0);
    await expect(page.locator('.dev-panel')).toHaveCount(0);
    const card = page.getByRole('button', {name:'사용자 A 취향으로',exact:true});
    await expect(card).toBeEnabled();
    await card.click();
    await expect.poll(() => submissions.length).toBe(1);
    expect(submissions[0]).toMatchObject({quick_start:'profile_a',personalization_mode:'warm'});
    await expect(page.locator('.user-message')).toHaveText('주말에 편하게 입을 티셔츠 찾아줘');
    await expect(page).toHaveURL(`https://fashion.test/${query}`);
  });
}
