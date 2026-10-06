const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const html = fs.readFileSync('web_ui/index.html', 'utf8');
  const app = fs.readFileSync('web_ui/app.js', 'utf8');
  const setup = app.slice(app.indexOf('function updateStorySetupPosition()'), app.indexOf('async function clearStoryRecovery()'));
  const style = app.slice(app.indexOf('function mountStoryStylePickers('), app.indexOf('function storyStylePayload('));
  assert(setup.includes('function initStorySetupScroller()'));
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:900}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => route.abort());
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, ''));
    await page.addStyleTag({content:fs.readFileSync('web_ui/styles.css', 'utf8')});
    await page.addScriptTag({content:`
      const $=s=>document.querySelector(s);
      const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      ${setup}
      ${style}
      document.querySelector('[data-view="story"]').classList.add('active');
      mountStoryStylePickers([{value:'auto',label:'ตามเนื้อเรื่อง',description:'ใช้แนวเดียวกัน'}]);
      initStorySetupScroller();
    `});
    assert.equal(await page.locator('#story-visual-style').count(), 1);
    assert.equal(await page.locator('#story-setup-position').textContent(), 'ขั้นที่ 1 จาก 3');
    assert.equal(await page.locator('.story-setup-progress').getAttribute('aria-valuenow'), '1');
    const dimensions = await page.locator('#story-setup-scroll').evaluate(el => ({view:el.clientHeight,content:el.scrollHeight}));
    assert(dimensions.content > dimensions.view, 'Quick Setup must have its own bounded scroll');
    if (process.env.STORY_SETUP_SCREENSHOT) await page.locator('.story-form-panel').screenshot({path:process.env.STORY_SETUP_SCREENSHOT});
    await page.selectOption('#story-provider', 'gemini');
    await page.locator('[data-story-setup="video"]').click();
    await page.waitForFunction(() => document.querySelector('.story-setup-progress').getAttribute('aria-valuenow') === '2');
    assert.equal(await page.locator('[data-story-setup="video"]').getAttribute('aria-current'), 'step');
    await page.locator('[data-story-setup="review"]').click();
    await page.waitForFunction(() => document.querySelector('.story-setup-progress').getAttribute('aria-valuenow') === '3');
    assert.equal(await page.locator('#story-provider').inputValue(), 'gemini');
    assert.equal(await page.locator('#story-scenes').inputValue(), '10');
    await page.locator('[data-story-setup="image"]').click();
    await page.waitForFunction(() => document.querySelector('.story-setup-progress').getAttribute('aria-valuenow') === '1');
    for (const width of [600,360]) {
      await page.setViewportSize({width,height:800});
      const setupRight = await page.locator('.story-form-panel .story-options-card').evaluate(el => Math.round(el.getBoundingClientRect().right));
      assert(setupRight <= width, `Quick Setup overflows at ${width}: right=${setupRight}`);
      assert.equal(await page.locator('#story-setup-scroll').evaluate(el => getComputedStyle(el).overflowY), 'auto');
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ok:true,steps:3,scroll:dimensions,providerSends:0}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exit(1);});
