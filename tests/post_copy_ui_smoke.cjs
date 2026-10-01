// Isolated Chromium UI exercise; synthetic completed job and mocked desktop transport.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const html = fs.readFileSync('web_ui/index.html', 'utf8')
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
  .replace(/<link\b[^>]*>/gi, '');
const app = fs.readFileSync('web_ui/app.js', 'utf8')
  .split('showPage(ui.activePage,false); updateRangeLabels(); updateToolLabels(); poll(true);')[0];

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent(html);
    await page.addScriptTag({ content: app });
    await page.evaluate(() => {
      window.calls = [];
      window.record = {
        item_id: 'story:STORY-POST', job_id: 'STORY-POST', kind: 'story',
        title: 'เรื่องคลิปยาว', kind_label: 'คลิปยาว', aspect_ratio: '16:9',
        description: 'คำอธิบายเก่า', hashtags: '#เดิม #เรื่องเล่า #คลิปยาว',
        post_revision: 'rev-1', post_text: 'เรื่องคลิปยาว\n\nคำอธิบายเก่า\n\n#เดิม #เรื่องเล่า #คลิปยาว',
        updated_at: '2026-09-24T09:00:00', video_url: '',
      };
      ui.state = { library: [window.record] };
      postAction = async (action, payload) => {
        calls.push({ action, payload });
        if (action === 'get_library_detail') return { ok: true, detail: { ...record } };
        if (action === 'save_library_post_metadata') {
          record.description = payload.description;
          record.hashtags = payload.hashtags;
          record.post_revision = 'rev-2';
          record.post_text = `${record.title}\n\n${record.description}\n\n${record.hashtags}`;
        }
        return { ok: true };
      };
      copyText = value => { window.copied = value; };
      document.body.dataset.page = 'library';
    });
    await page.addScriptTag({ path: 'web_ui/library_view.js' });
    await page.evaluate(() => renderLibrary(ui.state.library));
    await page.locator('[data-library-id="story:STORY-POST"]').click();
    await page.getByRole('button', { name: 'แก้ข้อความโพสต์' }).click();
    await page.locator('#post-copy-description').fill('อะไรทำให้ตอนจบพลิกไปอย่างคาดไม่ถึง? ชมเรื่องราวเต็มในคลิป');
    await page.locator('#post-copy-hashtags').fill('#ตัวละคร #เรื่องเล่า #คลิปยาว');
    await page.getByRole('button', { name: 'บันทึกข้อความโพสต์' }).click();
    await page.locator('#detail-modal').waitFor({ state: 'visible' });
    const call = await page.evaluate(() => calls.find(row => row.action === 'save_library_post_metadata'));
    assert.equal(call.payload.revision, 'rev-1');
    assert.equal(call.payload.hashtags, '#ตัวละคร #เรื่องเล่า #คลิปยาว');
    await page.locator('#detail-content [data-copy-key="post_text"]').click();
    assert.match(await page.evaluate(() => window.copied), /อะไรทำให้ตอนจบพลิกไป/);
    assert.deepEqual(errors, []);
    console.log('Post-copy library editor UI passed; no provider calls.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
