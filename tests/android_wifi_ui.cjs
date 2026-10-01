const fs = require('fs'), path = require('path'), assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = path.join(__dirname, '..');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const sent = [];
    let state = {busy:false,phase:'selection_required',message:'เลือกมือถือจากรายการ',checked_at:Date.now()/1000,
      devices:[{serial:'192.168.1.103:35157',aliases:['192.168.1.103:35157'],model:'Test Phone',state:'device',transport:'Wi-Fi'}],
      services:[{kind:'pairing',endpoint:'192.168.1.103:36245'},{kind:'connect',endpoint:'192.168.1.103:35157'}]};
    const html = fs.readFileSync(path.join(root,'web_ui/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
    await page.route('http://smartflow.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/') return route.fulfill({contentType:'text/html',body:html});
      if (url.pathname === '/api/desktop/action') {
        const request = route.request().postDataJSON(); sent.push(request);
        if (request.action === 'android_wifi_pair') state = {...state,busy:true,phase:'pairing',message:'กำลังจับคู่'};
        return route.fulfill({json:{ok:true,accepted:true,android_wifi:state}});
      }
      const file = path.join(root,'web_ui',path.basename(url.pathname));
      if (url.pathname.startsWith('/desktop/') && fs.existsSync(file)) {
        return route.fulfill({body:fs.readFileSync(file),contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript'});
      }
      return route.abort();
    });
    await page.goto('http://smartflow.test/');
    await page.evaluate(() => {
      document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.dataset.view==='queue'));
    });
    await page.addScriptTag({path:path.join(root,'web_ui/android_wifi.js')});
    const update = async () => page.evaluate(s=>window.renderAndroidWifi({system:{android_wifi:s}}),state);
    await update();
    assert.equal(await page.locator('#android-wifi-devices .android-device-row').count(),1);
    await page.locator('[data-wifi-action="pairing"]').click();
    assert.equal(await page.locator('#android-wifi-pair-endpoint').inputValue(),'192.168.1.103:36245');
    assert.equal(sent.length,0,'Choosing a discovered port must not pair');
    await page.locator('#android-wifi-code').fill('001234');
    await page.locator('#android-wifi-pair-form button').click();
    await page.waitForFunction(()=>document.querySelector('#android-wifi').getAttribute('aria-busy')==='true');
    assert.equal(sent.length,1); assert.equal(sent[0].action,'android_wifi_pair'); assert.equal(sent[0].payload.code,'001234');
    assert.equal(await page.locator('#android-wifi-code').inputValue(),'');
    assert.equal(await page.locator('#android-wifi-code').getAttribute('type'),'password');
    assert.equal(await page.locator('#android-wifi-connect-form button').isDisabled(),true);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    await page.waitForTimeout(150); assert.equal(sent.length,1,'No automatic retry or secondary Send');
    state = {...state,busy:false,phase:'connected',message:'เชื่อมต่อ Test Phone แล้ว • ยังไม่ได้โพสต์',selected:{serial:'192.168.1.103:35157',model:'Test Phone',android:'16',shopee_installed:true}};
    await update();
    assert.equal(await page.locator('#android-wifi-badge').textContent(),'เชื่อมต่อแล้ว');
    assert.match(await page.locator('#queue-device').textContent(),/เชื่อมต่อ Test Phone แล้ว/);
    assert.equal(await page.locator('[data-wifi-action="select"]').isDisabled(),true);
    await page.locator('[data-wifi-action="connect"]').click();
    assert.equal(await page.locator('#android-wifi-connect-endpoint').inputValue(),'192.168.1.103:35157');
    assert.equal(await page.locator('#android-wifi-pair-endpoint').inputValue(),'192.168.1.103:36245');
    state = {...state,checked_at:Date.now()/1000-90}; await update();
    assert.notEqual(await page.locator('#android-wifi-badge').textContent(),'เชื่อมต่อแล้ว','Stale proof cannot show connected');
    state = {...state,checked_at:Date.now()/1000,phase:'error',selected:null,error:'จับคู่ไม่สำเร็จ ตรวจรหัสใหม่'}; await update();
    assert.equal(await page.locator('#android-wifi-code').inputValue(),'');
    assert.equal(sent.length,1);
    for (const width of [1440,600,360]) {
      await page.setViewportSize({width,height:1000});
      await page.addStyleTag({content:'.sidebar{display:none!important}.app-shell{display:block!important}.main-content{margin:0!important;width:100%!important}'});
      const overflow = await page.locator('#android-wifi').evaluate(el=>el.scrollWidth > el.clientWidth+1);
      assert.equal(overflow,false,`Panel overflow at ${width}`);
      if (process.env.SMARTFLOW_WIFI_SCREENSHOTS) {
        fs.mkdirSync(process.env.SMARTFLOW_WIFI_SCREENSHOTS,{recursive:true});
        await page.locator('#android-wifi').screenshot({path:path.join(process.env.SMARTFLOW_WIFI_SCREENSHOTS,`wifi-${width}.png`)});
      }
    }
    assert.equal(await page.locator('[data-view="queue"] [data-tool="open_scrcpy"]').count(),0);
    assert.ok(sent.every(r=>r.action.startsWith('android_wifi_')));
    console.log('Actual Wi-Fi panel: separate ports, masked/cleared secret, busy guard, stale proof, no replay/post/storage; responsive1440/600/360.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
