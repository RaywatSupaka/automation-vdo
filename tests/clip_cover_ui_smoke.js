/* Isolated component smoke, not a claim of installed WebView/Extension E2E. */
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const fixture = JSON.parse(fs.readFileSync('docs/reports/clip-cover-272/visual-fixture/fixture.json','utf8'));
(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  try {
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    for (const width of [1440,1024,600]) {
      await page.setViewportSize({width,height:900});
      await page.setContent('<html lang="th"><body><div id="detail-modal"><video class="detail-video"></video></div></body></html>');
      await page.addStyleTag({path:'web_ui/styles.css'});
      await page.addStyleTag({path:'web_ui/clip_cover.css'});
      await page.evaluate(data => {
        window.fixture=data; window.calls=[]; window.item={};
        window.libraryItem=()=>window.item;
        window.postAction=async (action,payload) => {
          window.calls.push({action,payload});
          if(action==='get_cover_editor')return {ok:true,editor:structuredClone(window.fixture.editor)};
          if(action==='preview_library_cover')return {ok:true,preview:window.fixture.preview};
          if(action==='save_library_cover')return {ok:true,revision:'new-revision',cover_path:'covers/new.jpg'};
          if(action==='download_library_cover')return {ok:true,path:'Downloads/SmartFlow-cover-fixture.jpg'};
          throw new Error('Unexpected provider action: '+action);
        };
      },fixture);
      await page.addScriptTag({path:'web_ui/clip_cover.js'});
      await page.evaluate(()=>window.openClipCover('story:TEST-COVER'));
      await page.locator('.cover-preview-box img').waitFor({state:'visible'});
      await page.screenshot({path:`docs/reports/clip-cover-272/cover-editor-${width}.png`});
      assert.equal(await page.locator('.clip-cover-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);
      const before=await page.evaluate(()=>window.calls.length);
      await page.locator('[data-cover-headline]').fill('ความลับหลังประตู');
      assert.equal(await page.evaluate(()=>window.calls.length),before,'Typing must not send requests');
      await page.getByRole('button',{name:'เลือกภาพฉาก 1',exact:true}).click();
      await page.locator('[data-cover-position]').selectOption('top');
      await page.locator('[data-cover-preview]').click();
      await page.locator('[data-cover-save]').click();
      await page.getByRole('status').filter({hasText:'บันทึกปกใหม่แล้ว'}).waitFor();
      const saved=await page.evaluate(()=>window.calls.find(c=>c.action==='save_library_cover'));
      assert.equal(saved.payload.settings.headline,'ความลับหลังประตู');
      assert.equal(saved.payload.settings.scene_index,1);
      assert.equal(saved.payload.settings.position,'top');
      assert.equal(saved.payload.revision,'fixture');
      await page.locator('[data-cover-download]').click();
      await page.getByRole('status').filter({hasText:'ดาวน์โหลดแล้ว'}).waitFor();
      await page.locator('[data-cover-close]').click();
      assert.equal(await page.locator('.clip-cover-dialog').evaluate(el=>el.open),false);
    }
    assert.deepEqual(errors,[]);
    console.log('Cover UI: 3 widths, preview/edit/select/save/download/close passed; no external requests.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
