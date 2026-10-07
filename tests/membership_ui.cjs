// Actual login HTML/CSS/controller, isolated headless browser. No live bridge.
const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
  const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    let allowed=false,code='LOGIN_REQUIRED',posts=0,logouts=0,restoring=false,devMode=false;
    const state=()=>({ok:true,required:true,dev_mode:devMode,desktop:{allowed,code,restoring,message:allowed?'เชื่อมต่อแล้ว':restoring?'กำลังคืนสิทธิ์เดิม':'กรุณากรอก Token',expires_at:devMode?null:2000000000}});
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/desktop/media')return route.fulfill({contentType:'image/png',body:fs.readFileSync('assets/smartflow_icon.png')});
      if(url.pathname==='/api/membership/status')return route.fulfill({json:state()});
      if(url.pathname==='/api/membership/desktop/login'){
        posts++;assert.equal(route.request().method(),'POST');
        const data=route.request().postDataJSON();
        if(data.token==='fixture-wrong')return route.fulfill({status:403,json:{ok:false,error:'Token ไม่ถูกต้อง'}});
        allowed=true;return route.fulfill({json:state()});
      }
      if(url.pathname==='/api/membership/desktop/logout'){logouts++;allowed=false;return route.fulfill({json:state()});}
      if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
      return route.abort();
    });
    await page.goto('http://membership.test/');
    await page.addStyleTag({path:'web_ui/styles.css'});
    await page.addStyleTag({path:'web_ui/membership.css'});
    const safeError=fs.readFileSync('web_ui/app.js','utf8').match(/function safeUiError\(message\) \{[\s\S]*?\n\}/)?.[0];
    assert(safeError);await page.addScriptTag({content:`${safeError};window.smartflowSafeError=safeUiError;`});
    await page.addScriptTag({path:'web_ui/membership.js'});
    await page.locator('#membership-message').filter({hasText:'กรุณากรอก Token'}).waitFor();
    assert.equal(await page.locator('.app-shell').evaluate(n=>n.inert),true);
    for(const width of [1440,600,360]){
      await page.setViewportSize({width,height:900});
      assert.equal(await page.locator('#membership-gate').isVisible(),true);
      const box=await page.locator('.membership-card').boundingBox();assert(box.x>=0&&box.x+box.width<=width);
    }
    if(process.env.MEMBERSHIP_SCREENSHOT){await page.setViewportSize({width:1440,height:960});await page.screenshot({path:process.env.MEMBERSHIP_SCREENSHOT});}
    await page.locator('#membership-gate input').fill('fixture-wrong');
    await page.locator('#membership-gate [type=submit]').click();
    await page.getByText('Token ไม่ถูกต้อง',{exact:true}).waitFor();
    assert.equal(await page.locator('#membership-gate input').inputValue(),'');
    await page.locator('#membership-gate input').fill('fixture-valid');
    await page.locator('#membership-gate [type=submit]').click();
    await page.locator('#membership-gate').waitFor({state:'hidden'});
    assert.equal(await page.locator('.app-shell').evaluate(n=>n.inert),false);
    assert.equal(posts,2);
    assert.deepEqual(await page.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0]);
    allowed=false;code='LOGIN_REQUIRED';
    await page.locator('#membership-gate').waitFor({state:'visible',timeout:6000});
    restoring=true;
    await page.locator('#membership-gate form').waitFor({state:'hidden',timeout:6000});
    assert.equal(posts,2); // Saved permission is renewed by the broker, not a new Login.
    restoring=false;
    await page.locator('#membership-gate form').waitFor({state:'visible',timeout:6000});
    await page.evaluate(()=>{window.updateClicks=0;window.addEventListener('smartflow-open-updates',()=>window.updateClicks++);});
    await page.locator('[data-member-update]').click();
    assert.equal(await page.evaluate(()=>window.updateClicks),1);
    devMode=true;allowed=true;restoring=false;
    await page.locator('#membership-account').filter({hasText:'DEV MODE'}).waitFor({timeout:6000});
    assert.equal(await page.locator('#membership-gate').isVisible(),false);
    await page.setViewportSize({width:1440,height:900});
    await page.locator('#membership-account').click();
    assert.equal(logouts,0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({ok:true,cases:15}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
