const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=0;
 try{
  for(const scenario of ['current','new-app','new-extension','newer-installed','busy','network']){
   const page=await browser.newPage();await page.route('**/*',r=>r.abort());
   await page.goto('about:blank');
   await page.evaluate(mode=>{
    window.fixture={mode,calls:0,interval:null,timers:[],active:mode==='busy'};
    window.setInterval=(fn,ms)=>{if(ms===15*60*1000)fixture.interval=fn;return 1;};
    window.setTimeout=(fn,ms)=>{if(ms===7000)fixture.timers.push(fn);return 1;};
    window.fetch=async()=>({json:async()=>({system:{extension_online:true,extension_version:mode==='newer-installed'?'0.15.416':mode==='new-extension'?'0.15.414':'0.15.415'},story_progress:{active:fixture.active}})});
    Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>null,setItem:()=>{}}});
    window.pywebview={api:{update_check:async()=>{fixture.calls++;return mode==='network'?{ok:false,error:'Offline',local:{}}:{ok:true,app_update:mode==='new-app'||mode==='busy',local:{version:'0.3.0-beta.12',extension_version:'0.15.415'},release:{version:mode==='new-app'?'0.3.0-beta.13':'0.3.0-beta.12',extension_version:'0.15.415',patch:{},extension:{}}};}}};
   },scenario);
   await page.addScriptTag({content:fs.readFileSync('web_ui/updates.js','utf8')});
   await page.evaluate(async()=>{dispatchEvent(new Event('pywebviewready'));await fixture.timers[0]();});
   await page.waitForFunction(()=>fixture.calls===1);
   await page.waitForFunction(()=>!document.querySelector('[data-status]').textContent.includes('กำลังตรวจสอบ'));
   assert.equal(await page.locator('dialog').evaluate(n=>n.open),['new-app','new-extension'].includes(scenario),scenario);checks++;
   if(scenario==='busy'){
    await page.evaluate(()=>{fixture.active=false;fixture.interval();});
    await page.waitForFunction(()=>document.querySelector('dialog').open);
    assert.equal(await page.evaluate(()=>fixture.calls),2);checks++;
   }
   assert.equal(await page.evaluate(()=>typeof fixture.interval),'function');checks++;
   await page.close();
  }
 }finally{await browser.close();}
 console.log(JSON.stringify({ok:true,checks}));
})().catch(e=>{console.error(e);process.exitCode=1;});
