const fs = require('fs');
const assert = require('assert/strict');
const {chromium} = require('playwright');

(async () => {
  const html = fs.readFileSync('web_ui/index.html', 'utf8');
  const app = fs.readFileSync('web_ui/app.js', 'utf8');
  assert(!html.includes('/desktop/flow_smoke.js'), 'Legacy Flow test script must not load in the customer UI');
  assert(!app.includes('routeFlowTest'), 'Ordinary creation must not be redirected to Flow test');
  assert(!app.includes('prepareFlowTestPage'), 'Flow test page must not replace the long-video page');

  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, ''));
    assert.equal(await page.locator('#sidebar [data-page="longvideo"]').count(), 1);
    assert.equal(await page.locator('#sidebar').getByText('คลิปยาว', {exact: true}).count(), 1);
    assert.equal(await page.locator('[role="menuitem"][data-page="longvideo"]').count(), 1);
    assert.equal(await page.locator('[data-view="longvideo"] #create-longvideo').count(), 1);
    assert.equal(await page.locator('[data-page="flowtest"], [data-view="flowtest"]').count(), 0);
    assert.equal(await page.getByText('ทดสอบ AI → Flow', {exact: true}).count(), 0);
    console.log('PASS long-video navigation is visible; Flow test mode is absent from the customer UI');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
