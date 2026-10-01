// Explicit isolated EXE only. No pairing, uploads, provider work or Shopee launch.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
  const port = Number(process.env.SMARTFLOW_WIFI_TEST_PORT);
  const expected = Number(process.env.SMARTFLOW_WIFI_TEST_ENGINE);
  const serial = process.env.SMARTFLOW_WIFI_TEST_SERIAL;
  assert.equal(port,19065); assert.ok(expected > 0); assert.ok(serial);
  const origin = `http://127.0.0.1:${port}`;
  const health = await (await fetch(origin+'/health')).json();
  assert.equal(health.engine_pid,expected); assert.equal(health.desktop_ui,'hybrid');
  const browser = await chromium.launch({headless:true});
  const actions = [], errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/desktop/action',async route=>{
      const data=route.request().postDataJSON();
      if(!['android_wifi_status','android_wifi_refresh','android_wifi_select'].includes(data.action)) {
        return route.fulfill({json:{ok:false,error:'Isolated Wi-Fi test: unrelated action blocked'}});
      }
      if(data.action==='android_wifi_select' && data.payload.serial!==serial) {
        return route.fulfill({status:403,json:{ok:false,error:'Test device mismatch'}});
      }
      actions.push(data.action); await route.continue();
    });
    await page.goto(origin+'/desktop/');
    await page.locator('.nav-item[data-page="queue"]').click();
    await page.waitForFunction(()=>document.querySelector('#android-wifi').getAttribute('aria-busy')==='false');
    const button=page.locator('#android-wifi-devices [data-wifi-action="select"]');
    await button.waitFor({state:'visible',timeout:20000});
    assert.equal(await button.count(),1); assert.equal(await button.getAttribute('data-value'),serial);
    if (await button.isEnabled()) await button.click();
    await page.waitForFunction(()=>document.querySelector('#android-wifi-badge').textContent==='เชื่อมต่อแล้ว',null,{timeout:20000});
    const state=await(await fetch(origin+'/api/desktop/state?mode=compact')).json();
    assert.equal(state.system.android_wifi.phase,'connected');
    assert.match(await page.locator('#queue-device').textContent(),/เชื่อมต่อ/);
    assert.equal(state.system.android_wifi.selected.serial,serial);
    assert.ok(state.system.android_wifi.selected.device_id);
    assert.equal(state.product_progress.active,false); assert.equal(state.story_progress.active,false);
    assert.deepEqual(errors,[]);
    if(process.env.SMARTFLOW_WIFI_TEST_SCREENSHOT) {
      await page.locator('#android-wifi-title').scrollIntoViewIfNeeded();
      await page.screenshot({path:process.env.SMARTFLOW_WIFI_TEST_SCREENSHOT,fullPage:false});
    }
    console.log(JSON.stringify({engine_pid:expected,model:state.system.android_wifi.selected.model,
      android:state.system.android_wifi.selected.android,shopee_installed:state.system.android_wifi.selected.shopee_installed,
      actions,js_errors:errors,selected_in_test_config:true,pairing:false,posting:false}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
