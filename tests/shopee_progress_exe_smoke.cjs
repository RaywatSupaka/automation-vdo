// Read-only EXE host smoke. Progress is seeded fixture data, not a real phone run.
const assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
 const origin='http://127.0.0.1:19065', expected=Number(process.env.SMARTFLOW_POST_TEST_ENGINE);
 assert.ok(expected);const health=await(await fetch(origin+'/health')).json();assert.equal(health.engine_pid,expected);
 const browser=await chromium.launch({headless:true});const errors=[],blocked=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/desktop/action',async route=>{
   const d=route.request().postDataJSON();
   if(!['shopee_post_status','shopee_post_library'].includes(d.action)){blocked.push(d.action);return route.fulfill({json:{ok:false,error:'Fixture: all mutations and phone actions blocked'}});}
   return route.continue();
  });
  await page.goto(origin+'/desktop/');await page.waitForFunction(()=>document.querySelector('#sp-run-modal').open);
  assert.match(await page.locator('#sp-run-message').textContent(),/แนบสินค้า/);
  assert.equal(await page.locator('#sp-run-done').textContent(),'2');
  if(process.env.SMARTFLOW_POST_TEST_SCREENSHOT)await page.screenshot({path:process.env.SMARTFLOW_POST_TEST_SCREENSHOT});
  for(const width of [1440,600,360]){await page.setViewportSize({width,height:900});assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);}
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('[data-post-progress="minimize"]').click();await page.locator('.nav-item[data-page="queue"]').click();
  await page.locator('[data-sp="refresh"]').click();await page.locator('#sp-queue-all').check();
  assert.equal(await page.locator('[data-queued]:checked').count(),2);
  await page.locator('#sp-run-pill').click();assert.equal(await page.locator('#sp-run-modal').evaluate(e=>e.open),true);
  await page.reload();await page.waitForFunction(()=>document.querySelector('#sp-run-modal').open);
  assert.equal(await page.locator('#sp-run-done').textContent(),'2');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({engine_pid:expected,progress_fixture:true,persisted_after_reload:true,selection:true,js_errors:errors,blocked,real_post:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
