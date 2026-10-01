// Isolated EXE-backed UI. Explicit fixture-only settings writes; no phone/Post.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
 const origin='http://127.0.0.1:19065', expected=Number(process.env.SMARTFLOW_POST_TEST_ENGINE);
 assert.ok(expected);const health=await(await fetch(origin+'/health')).json();assert.equal(health.engine_pid,expected);
 const browser=await chromium.launch({headless:true});const actions=[],errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/desktop/action',async route=>{
   const d=route.request().postDataJSON();
   if(!['shopee_post_status','shopee_post_library','shopee_post_defaults','shopee_post_edit','shopee_post_apply_options'].includes(d.action))return route.fulfill({json:{ok:false,error:'Isolated test: phone and public writes blocked'}});
   actions.push(d.action);return route.continue();
  });
  await page.goto(origin+'/desktop/');await page.locator('.nav-item[data-page="queue"]').click();
  await page.locator('[data-sp="refresh"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-library').textContent.includes('ไม่พบคลิปสินค้า'));
  assert.equal(await page.locator('[data-sp="start"]').isVisible(),true);
  assert.match(await page.locator('#sp-account').textContent(),/ยังไม่ได้อ่านบัญชี/);
  await page.locator('#sp-default-reuse').check();
  await page.locator('#sp-default-ai').uncheck();
  await page.locator('[data-sp="save-defaults"]').click();
  await page.waitForFunction(()=>!document.querySelector('#sp-default-status').textContent.includes('ยังไม่บันทึก'));
  await page.reload();await page.locator('.nav-item[data-page="queue"]').click();
  await page.locator('[data-sp="refresh"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-default-reuse').checked&&!document.querySelector('#sp-default-ai').checked);
  const rows=page.locator('[data-row]');assert.equal(await rows.count(),2);
  assert.equal(await rows.nth(0).locator('[data-option="allow_reuse"]').isChecked(),false);
  await rows.nth(0).locator('[data-queued]').check();
  page.once('dialog',d=>d.accept());await page.locator('[data-sp="apply-options"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-row] [data-option="allow_reuse"]').checked);
  assert.equal(await rows.nth(0).locator('[data-option="ai_label"]').isChecked(),false);
  assert.equal(await rows.nth(1).locator('[data-option="allow_reuse"]').isChecked(),false);
  assert.equal(await rows.nth(1).locator('[data-option="ai_label"]').isChecked(),true);
  for(const width of [1440,600,360]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await page.locator('#shopee-posting').evaluate(el=>el.scrollWidth>el.clientWidth+2),false);
  }
  await page.setViewportSize({width:1440,height:1000});await page.locator('#shopee-posting').scrollIntoViewIfNeeded();
  if(process.env.SMARTFLOW_POST_TEST_SCREENSHOT)await page.screenshot({path:process.env.SMARTFLOW_POST_TEST_SCREENSHOT});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({engine_pid:expected,actions,settings_persisted:true,selected_only:true,js_errors:errors,real_post:false,phone_actions:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
