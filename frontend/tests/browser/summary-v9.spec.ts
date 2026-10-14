import {test, expect} from '@playwright/test';

test('mock v9 warm badges follow final item selection and remain fixed on reload', async ({page}) => {
  await page.goto('/?mode=mock&profile=warm');
  await page.getByRole('textbox', {name:'추천 요청'}).fill('검은색 팬츠 추천해줘');
  await page.getByRole('button', {name:'추천 요청 전송'}).click();
  await expect(page.locator('.product')).toHaveCount(4, {timeout:15000});
  await expect(page.locator('.preference-badge.personalized')).toHaveCount(2);
  await expect(page.locator('.preference-badge.nonpersonalized_supplement')).toHaveCount(2);
  await expect(page.locator('.intro')).toContainText('취향을 함께 고려한');
  expect(await page.locator('.product-details').first().evaluate(el => el.querySelector('.preference-badge')!.compareDocumentPosition(el.querySelector('h3')!) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  await page.goto('/?mode=mock&profile=cold');
  await expect(page.locator('.preference-badge.personalized')).toHaveCount(2);
  await page.screenshot({path:'/tmp/summary-v9-mock.png',fullPage:true});
});

test('mock cold uses no personalized labels', async ({page}) => {
  await page.goto('/?mode=mock');
  await page.getByRole('textbox', {name:'추천 요청'}).fill('검은색 팬츠 추천해줘');
  await page.getByRole('button', {name:'추천 요청 전송'}).click();
  await expect(page.locator('.preference-badge.nonpersonalized')).toHaveCount(4, {timeout:15000});
  await expect(page.locator('.preference-badge.personalized')).toHaveCount(0);
});
