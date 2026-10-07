const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const html = fs.readFileSync('web_ui/index.html', 'utf8');
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*>/gi, ''));
    const visible = await page.locator('body').innerText();
    assert.doesNotMatch(visible, /Checkpoint|Product Job|Token SOT|reference_id|UI Hierarchy|วิดีโอ AI ×3|Google Flow ×3/);
    for (const button of await page.locator('[data-tool="dump_ui"]').all()) {
      assert.equal(await button.locator('xpath=ancestor::details').count(), 1);
      assert.equal(await button.isVisible(), false);
    }
    const loaded = [...html.matchAll(/<script\s+src="\/desktop\/([^"?]+)/g)].map(match => match[1]);
    for (const file of loaded) {
      const script = fs.readFileSync(`web_ui/${file}`, 'utf8');
      assert.doesNotMatch(script, /(?<![.\w])(?:confirm|alert)\s*\(/, `${file} still uses native dialog`);
    }
    const app = fs.readFileSync('web_ui/app.js', 'utf8');
    const pageMeta = app.match(/const pageMeta = \{[\s\S]*?\n\};/)?.[0];
    assert(pageMeta);
    const headings = Function(`${pageMeta}; return Object.values(pageMeta).map(value => value[0]);`)();
    assert(headings.every(label => /[ก-๙]/u.test(label)), 'every route heading needs Thai wording');
    const safeError = app.match(/function safeUiError\(message\) \{[\s\S]*?\n\}/)?.[0];
    assert(safeError, 'safe error boundary absent');
    const classify = Function(`${safeError}; return safeUiError;`)();
    assert.doesNotMatch(classify('Traceback (most recent call last): C:\\private\\secret.py'), /Traceback|private|secret/);
    assert.equal(classify('กรุณาเลือกรูปภาพก่อน'), 'กรุณาเลือกรูปภาพก่อน');
    const stepsSource = app.slice(app.indexOf('function progressSteps('), app.indexOf('function minimizeProgress('));
    const steps = Function(`${stepsSource}; return progressSteps;`)();
    for (const label of ['สร้างภาพ', 'เสียงพากย์', 'ประกอบฉาก', 'ปกและบันทึก']) {
      assert(steps('story', 65).includes(label));
      assert(steps('story', 65, {pipeline_phase:'compose',audio_mode:'api'}).includes(label));
    }
    console.log('UI wording, support-only diagnostics, native dialog removal and safe error boundary passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
