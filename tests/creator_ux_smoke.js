const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  // No test may dispatch automation or mutate a saved job.
  await page.route('**/api/**',async route=>{
   if(route.request().method()!=='GET')return route.fulfill({status:200,contentType:'application/json',body:'{"ok":true}'});
   return route.continue();
  });
  await page.goto('http://127.0.0.1:19065/desktop/');
  await page.waitForSelector('.creator-review',{state:'attached'});
  assert.equal(await page.locator('#new-job-menu [data-page]').count(),5);
  assert.equal(await page.locator('.creator-review').count(),6);
  await page.locator('.navigation [data-page="products"]').click();
  const panel=page.locator('[data-view="products"] .media-audio-controls');
  await panel.locator('[data-audio-music]').check();
  await panel.locator('[data-audio-sfx]').check();
  await panel.locator('[data-audio-subtitle]').check();
  await panel.locator('[data-main-audio]').selectOption('flow_original');
  assert.equal(await page.locator('#product-subtitle').isVisible(),false);
  for(const key of ['music','sfx','subtitle'])assert.equal(await panel.locator(`[data-audio-${key}]`).isChecked(),true);
  assert.match(await page.locator('[data-view="products"] .creator-review').innerText(),/เสียงต้นฉบับ Flow/);
  await page.locator('#enqueue-product').click();
  assert.equal(await page.locator('#creation-editor').evaluate(n=>n.open),true);
  assert.match(await page.locator('#creation-editor .creator-review').innerText(),/เพิ่มเพลงพื้นหลัง/);
  await page.evaluate(()=>{const select=document.querySelector('#creation-product-video-provider');select.value='meta_ai';select.dispatchEvent(new Event('change',{bubbles:true}));});
  assert.match(await page.locator('#creation-editor .creator-review').innerText(),/Meta AI/,'batch summary must show the selected video provider');
  await page.locator('#creation-editor-close').click();
  await page.evaluate(()=>{
    document.querySelector('#story-topic').value='เรื่องเดี่ยวที่ไม่ควรทับคิว';
    document.querySelector('#story-batch-topics').value='ร่างเรื่องในคิว';
    document.querySelector('#story-batch-video-mode').value='meta_ai';
    document.querySelector('#queue-add-stories').click();
  });
  assert.equal(await page.locator('#story-batch-modal').evaluate(n=>n.open),true);
  assert.equal(await page.locator('#story-batch-topics').inputValue(),'ร่างเรื่องในคิว');
  assert.equal(await page.locator('#story-batch-video-mode').inputValue(),'meta_ai');
  await page.locator('#story-batch-modal').evaluate(n=>n.close());
  await page.evaluate(()=>{
   const state={...ui.state,presenter_progress:{active:false},product_progress:{active:true,job_id:'UI-TEST-ONLY',percent:25,message:'กำลังสร้างภาพ',detail:'รอผู้ให้บริการ'},story_progress:{active:false}};
   renderProgress(state);minimizeProgress();renderProgress(state);
  });
  assert.equal(await page.locator('#progress-modal').evaluate(n=>n.open),false,'heartbeat must not reopen a minimized popup');
  await page.evaluate(()=>{ui.progressWasActive=false;ui.progressResultReady=false;ui.progressMinimized=false;document.querySelector('#progress-minimized').classList.add('hidden');});
  fs.mkdirSync('build/creator-ux-smoke',{recursive:true});
  for(const [width,height] of [[1366,768],[1920,1080],[1093,614],[911,512]]){
   await page.setViewportSize({width,height});
   for(const name of ['products','story','drama','longvideo','library','settings']){
    await page.evaluate(name=>showPage(name),name);
    assert.equal(await page.locator('body').evaluate(n=>n.scrollWidth<=innerWidth+2),true,`${name} horizontal overflow at ${width}`);
    if(width===1366 && ['products','longvideo'].includes(name)){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`build/creator-ux-smoke/${name}.png`});}
   }
  }
  assert.deepEqual(errors,[]);console.log('PASS: menus,6 summaries,audio preservation,queue inheritance,6 pages/4 viewport sizes,no automation POST,closed browser');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
