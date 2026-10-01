const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage();
  const html=fs.readFileSync(path.join(__dirname,'../web_ui/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  const source=fs.readFileSync(path.join(__dirname,'../web_ui/app.js'),'utf8');
  await page.route('**/*',r=>r.abort());
  await page.setContent(html);
  await page.evaluate(()=>{
   window.$=s=>document.querySelector(s);window.ui={};window.poll=async()=>{};window.toast=()=>{};
   window.postAction=async(action,payload)=>{window.sent={action,payload};};
  });
  await page.evaluate(source.split('\n').find(l=>l.startsWith("$('#save-settings').addEventListener")));
  for(const width of [360,600,1440]) {
   await page.setViewportSize({width,height:900});
   for(const encoder of ['auto','gpu','cpu']) {
    await page.evaluate(value=>{
     $('#setting-encoder').value=value;$('#setting-fps').value='60';$('#save-settings').click();
    },encoder);
    let sent=await page.evaluate(()=>window.sent);
    assert.equal(sent.action,'save_quick_settings');assert.equal(sent.payload.encoder,encoder);assert.equal(sent.payload.fps,60);
   }
  }
  await page.evaluate(()=>{$('#setting-fps').value='0';$('#save-settings').click();});
  assert.equal((await page.evaluate(()=>window.sent)).payload.fps,0);
  assert.equal(await page.locator('#setting-encoder option').count(),3);
  assert.match(await page.locator('#setting-encoder').textContent(),/CPU/);
  console.log('Actual settings handler: Auto/GPU/CPU, explicit60 and source0 at360/600/1440; no network writes.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
