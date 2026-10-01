const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const html=fs.readFileSync('browser_extension/popup.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.route('**/*',r=>r.fulfill({contentType:'text/html',body:html}));await page.goto('https://popup.test/');
  await page.evaluate(()=>{
   window.calls=[];window.http=[];window.online=true;window.paired=true;window.mismatch=false;
   window.fetch=async url=>{http.push(url);if(!online)throw Error('offline');return {ok:true};};
   window.chrome={tabs:{query:async()=>[{id:1,url:'chrome://extensions/'}]},runtime:{sendMessage:async m=>{
    calls.push(m.type);
    if(m.type==='GET_CONNECTION_STATUS')return {ok:true,connection:{reachable:online,paired:online&&paired,
      currentVersion:'fixture-A',requiredVersion:mismatch?'fixture-B':'fixture-A',updateRequired:mismatch}};
    if(m.type!=='GET_FLOW_PACKAGE')throw Error('unexpected request');return {ok:false};
   }}};
  });
  await page.addScriptTag({content:fs.readFileSync('browser_extension/popup.js','utf8')});
  await page.locator('#bridgeStatus').filter({hasText:'เชื่อมต่อโปรแกรม'}).waitFor();
  assert.equal(await page.locator('input,#membershipCard,#membershipRefresh').count(),0);
  await page.evaluate(()=>{online=false;});await page.locator('#refreshButton').click();
  assert.match(await page.locator('#bridgeStatus').textContent(),/กรุณาเปิดโปรแกรม/);
  await page.evaluate(()=>{online=true;});await page.locator('#refreshButton').click();
  assert.match(await page.locator('#bridgeStatus').textContent(),/เชื่อมต่อโปรแกรม/);
  await page.evaluate(()=>{paired=false;});await page.locator('#refreshButton').click();
  assert.match(await page.locator('#bridgeStatus').textContent(),/ยังไม่จับคู่/);
  assert.equal(await page.locator('#bridgeDot').getAttribute('class'),'dot bad');
  await page.evaluate(()=>{mismatch=true;});await page.locator('#refreshButton').click();
  assert.match(await page.locator('#bridgeStatus').textContent(),/fixture-A.*fixture-B/);
  assert.equal(await page.locator('#bridgeDot').getAttribute('class'),'dot bad');
  assert(await page.evaluate(()=>calls.every(x=>['GET_FLOW_PACKAGE','GET_CONNECTION_STATUS'].includes(x))&&http.length===0));
  assert.deepEqual(await page.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0]);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({ok:true,cases:9,providerSubmissions:0}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
