// Actual popup DOM, fake broker only; no Chrome profile or live Login.
const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=0;
 try {
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const html=fs.readFileSync('browser_extension/popup.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:html}));await page.goto('https://popup.test/');
  await page.evaluate(()=>{
   window.calls=[];window.state={ok:true,desktop:{allowed:false,restoring:true,message:'กำลังเชื่อมสิทธิ์เดิม'},extension:{allowed:false,source:'desktop',contract_version:1}};
   window.chrome={runtime:{sendMessage:async m=>{
    calls.push(m.type);
    if(window.hold){window.hold=false;return new Promise(resolve=>window.release=resolve);}
    return structuredClone(window.state);
   }}};
   window.timerCallback=null;window.timerCleared=false;
   window.setInterval=fn=>{window.timerCallback=fn;return 17;};window.clearInterval=id=>{window.timerCleared=id===17;};
  });
  const js=fs.readFileSync('browser_extension/popup.js','utf8').split('\nfunction isFlowUrl')[0];
  await page.addScriptTag({content:js});
  await page.locator('#membershipStatus').filter({hasText:'กำลังเชื่อมสิทธิ์เดิม'}).waitFor();checks++;
  assert.equal(await page.locator('input, #membershipForm, #membershipLogout').count(),0);checks++;
  await page.evaluate(async()=>{state.desktop={allowed:true};state.extension.allowed=true;await timerCallback();});
  assert.match(await page.locator('#membershipStatus').textContent(),/พร้อมรับคำสั่ง/);checks++;
  for(const message of ['กรุณาเข้าสู่ระบบใหม่หลังถูกเตะ','สิทธิ์หมดอายุ','บัญชีถูกระงับ']){
   await page.evaluate(async message=>{state.desktop={allowed:false,message};state.extension.allowed=false;await timerCallback();},message);
   assert.match(await page.locator('#membershipStatus').textContent(),/จัดการสิทธิ์ที่โปรแกรม/);checks++;
  }
  await page.evaluate(async()=>{state={ok:false,error:'เปิด SmartFlow AI จาก Desktop แล้วตรวจอีกครั้ง'};await timerCallback();});
  assert.match(await page.locator('#membershipStatus').textContent(),/เปิด SmartFlow/);checks++;
  await page.evaluate(async()=>{state={ok:true,desktop:{allowed:true},extension:{allowed:true}};await timerCallback();});
  assert.match(await page.locator('#membershipStatus').textContent(),/อัปเดต/);checks++;
  await page.evaluate(()=>{window.hold=true;window.pending=timerCallback();});
  assert.equal(await page.locator('#membershipRefresh').isDisabled(),true);
  const before=await page.evaluate(()=>calls.length);await page.evaluate(()=>timerCallback());
  assert.equal(await page.evaluate(()=>calls.length),before);checks++;
  await page.evaluate(async()=>{state={ok:true,desktop:{allowed:true},extension:{allowed:true,source:'desktop',contract_version:1}};release(state);await pending;});
  await page.locator('#membershipRefresh').click();
  assert.equal(await page.evaluate(()=>calls.every(c=>c==='MEMBERSHIP_STATUS')),true);
  assert.deepEqual(await page.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0]);checks++;
  await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
  assert.equal(await page.evaluate(()=>timerCleared),true);assert.deepEqual(errors,[]);checks++;
  console.log(JSON.stringify({ok:true,cases:checks,liveLogins:0}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
