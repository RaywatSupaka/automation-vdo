// The real popup form/controller; fake local status, no Chrome or cloud writes.
const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=0;
 try {
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const html=fs.readFileSync('browser_extension/popup.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:html}));await page.goto('https://popup.test/');
  await page.evaluate(()=>{
   window.calls=[];window.state={ok:true,desktop:{allowed:true},extension:{allowed:false,remembered:true,restoring:true,message:'กำลังเชื่อมสิทธิ์เดิม'}};
   window.chrome={runtime:{sendMessage:async m=>{
    calls.push(m.type);
    if(m.type==='MEMBERSHIP_STATUS'){
     if(window.hold){window.hold=false;return new Promise(resolve=>window.release=resolve);}
     return structuredClone(window.state);
    }
    if(m.type==='MEMBERSHIP_LOGIN'){window.loginCount=(window.loginCount||0)+1;return {ok:false,error:'Token ไม่ถูกต้อง'};}
    if(m.type==='MEMBERSHIP_LOGOUT'){window.state.extension={allowed:false,message:'เข้าสู่ระบบใหม่'};return window.state;}
   }}};
   window.timerCallback=null;window.timerCleared=false;
   window.setInterval=fn=>{window.timerCallback=fn;return 17;};window.clearInterval=id=>{window.timerCleared=id===17;};
  });
  const js=fs.readFileSync('browser_extension/popup.js','utf8').split('\nfunction isFlowUrl')[0];
  await page.addScriptTag({content:js});
  await page.locator('#membershipStatus').filter({hasText:'กำลังเชื่อมสิทธิ์เดิม'}).waitFor();
  assert.equal(await page.locator('#membershipForm').isVisible(),false);checks++;
  await page.evaluate(async()=>{state.extension={allowed:true};await timerCallback();});
  assert.equal(await page.locator('#membershipLogout').isVisible(),true);
  assert.equal(await page.locator('#membershipForm').isVisible(),false);checks++;
  await page.evaluate(async()=>{state={ok:false,error:'bridge offline'};await timerCallback();});
  assert.equal(await page.locator('#membershipForm').isVisible(),false);checks++;
  await page.evaluate(async()=>{state={ok:true,desktop:{allowed:false,restoring:true,message:'กำลังเชื่อมสิทธิ์โปรแกรม'},extension:{allowed:false}};await timerCallback();});
  assert.equal(await page.locator('#membershipForm').isVisible(),false);checks++;
  await page.evaluate(async()=>{state.desktop={allowed:true};state.extension={allowed:false,profile_changed:true,message:'พบ Extension คนละตัว'};await timerCallback();});
  assert.equal(await page.locator('#membershipForm').isVisible(),true);
  assert.match(await page.locator('#membershipStatus').textContent(),/คนละตัว/);checks++;
  await page.evaluate(async()=>{state.extension={allowed:false,message:'กรุณากรอก Token ใหม่หลังถูกเตะ'};await timerCallback();});
  assert.equal(await page.locator('#membershipForm').isVisible(),true);checks++;
  // An older status response must not overwrite the newer explicit Login error.
  await page.evaluate(()=>{window.hold=true;window.pending=timerCallback();});
  await page.locator('#membershipToken').fill('fixture-only-invalid');
  await page.locator('#membershipForm button').click();
  await page.locator('#membershipStatus').filter({hasText:'Token ไม่ถูกต้อง'}).waitFor();
  assert.equal(await page.locator('#membershipToken').inputValue(),'');checks++;
  await page.evaluate(async()=>{release({ok:true,desktop:{allowed:true},extension:{allowed:true}});await pending;});
  assert.match(await page.locator('#membershipStatus').textContent(),/Token ไม่ถูกต้อง/);checks++;
  assert.equal(await page.evaluate(()=>loginCount),1);
  assert.deepEqual(await page.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0]);checks++;
  await page.evaluate(async()=>{state.extension={allowed:true};await timerCallback();});
  await page.locator('#membershipLogout').click();
  await page.locator('#membershipStatus').filter({hasText:'เข้าสู่ระบบใหม่'}).waitFor();
  assert.equal(await page.locator('#membershipForm').isVisible(),true);checks++;
  await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
  assert.equal(await page.evaluate(()=>timerCleared),true);assert.deepEqual(errors,[]);checks++;
  console.log(JSON.stringify({ok:true,cases:checks,liveLogins:0}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
