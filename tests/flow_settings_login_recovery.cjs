// Real UI modules, synthetic local responses, no live browser/account/job writes.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=name=>fs.readFileSync(path.join(__dirname,'../web_ui',name),'utf8');
async function readFailurePage(browser,{timeout=false}={}){
 const page=await browser.newPage();
 await page.route('**/*',route=>route.abort());
 await page.setContent('<section data-view="settings"><div class="page-intro"></div></section><select id="product-video-provider"><option value="google_flow">Flow</option></select><select id="story-video-mode"><option value="google_flow">Flow</option></select>');
 await page.addScriptTag({content:`
  window.calls=[];window.fail='offline';window.delayRead=false;window.duration='6s';
  let postAction=async(action,payload)=>{
   calls.push({action,payload});
   if(action==='flow_settings_get'){
    const saved={model:'Veo 3.1 - Lite [Lower Priority]',duration:window.duration};
    if(window.delayRead)await new Promise(resolve=>window.releaseRead=resolve);
    if(window.fail==='invalid')return {ok:false,error:'incomplete settings'};
    if(window.fail)throw Error(window.fail);
    return {ok:true,settings:saved};
   }
   return {ok:true};
  };
  window.smartflowCreationFormKey=action=>action==='create_product'?'product':action==='create_story'?'story':null;
  ${timeout ? "const realTimer=setTimeout;window.setTimeout=(fn,ms,...args)=>realTimer(fn,ms===12000?100:ms,...args);" : ''}
 `});
 await page.addScriptTag({content:source('flow_settings.js')});
 await page.waitForFunction(()=>document.querySelector('[data-flow-status]').textContent.includes('offline'));
 return page;
}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.abort());
  await page.setContent(`<section id="membership-gate"><form><input><button type="submit">Login</button></form><p data-member-message></p><button data-member-recheck>Check</button><button data-member-update>Update</button></section><button id="membership-account"></button><div class="app-shell"><section data-view="settings"><div class="page-intro"></div></section><select id="product-video-provider"><option value="google_flow">Flow</option></select><select id="story-video-mode"><option value="google_flow">Flow</option></select><form id="creation-form"><div class="cq-buttons"></div></form></div>`);
  await page.addScriptTag({content:`
   window.allowed=false; window.calls=[]; window.readFailure=''; window.delayRead=false;
   window.fetch=async url=>{if(url.endsWith('/login'))window.allowed=true;return {ok:true,json:async()=>({ok:true,required:true,desktop:{allowed:window.allowed}})};};
   let postAction=async(action,payload)=>{
    window.calls.push({action,payload});
    if(action==='flow_settings_get'){
     if(!window.allowed)throw Error('LOGIN_REQUIRED');
     if(window.delayRead)await new Promise(resolve=>window.releaseRead=resolve);
     if(window.readFailure==='invalid')return {ok:false,error:'fixture unavailable'};
     if(window.readFailure)throw Error(window.readFailure);
     return {ok:true,settings:{model:'Veo 3.1 - Lite [Lower Priority]',duration:'6s'}};
    }
    return {ok:true};
   };
   window.smartflowCreationFormKey=(action,payload)=>action==='create_product'?'product':action==='create_story'?'story':action==='creation_edit'?'product-batch':null;
  `});
  await page.addScriptTag({content:source('membership.js')});
  await page.addScriptTag({content:source('flow_settings.js')});
  await page.waitForFunction(()=>document.querySelector('[data-flow-status]').textContent.includes('LOGIN_REQUIRED'));
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='flow_settings_get').length),1);
  // Actual first-login render must wake the failed one-shot settings reader.
  await page.locator('#membership-gate input').fill('synthetic-not-a-real-token');
  await page.locator('#membership-gate [type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#membership-gate').hidden);
  await page.evaluate(()=>postAction('create_product',{}));
  const created=await page.evaluate(()=>calls.filter(c=>c.action==='create_product'));
  assert.equal(created.length,1,'read recovery must never replay creation');
  assert.equal(created[0].payload.flow_settings.duration,'6s');
  assert.equal(created[0].payload.flow_settings.model,'Veo 3.1 - Lite [Lower Priority]');
  await page.waitForFunction(()=>!document.querySelector('[data-flow-save]').disabled);
  assert.equal(await page.locator('[data-flow-status]').innerText().then(t=>t.includes('LOGIN_REQUIRED')),false);
  // Existing jobs never inherit a new defaults snapshot.
  await page.evaluate(()=>postAction('create_product',{job_id:'EXISTING'}));
  assert.equal(await page.evaluate(()=>calls.at(-1).payload.flow_settings),undefined);
  await page.close();
  const delayed=await readFailurePage(browser);
  await delayed.evaluate(()=>{window.fail='invalid';});
  const invalid=await delayed.evaluate(()=>postAction('create_product',{}).then(()=>'',e=>e.message));
  assert.match(invalid,/incomplete settings/);
  assert.equal(await delayed.evaluate(()=>calls.filter(c=>c.action==='create_product').length),0);
  await delayed.evaluate(()=>{window.fail='';window.delayRead=true;window.pendingProduct=postAction('create_product',{});window.pendingStory=postAction('create_story',{});});
  await delayed.waitForFunction(()=>Boolean(window.releaseRead));
  assert.equal(await delayed.evaluate(()=>calls.filter(c=>c.action==='flow_settings_get').length),3,'two intended starts share one settings read');
  await delayed.locator('.flow-job-settings').first().locator('summary').click();
  await delayed.locator('.flow-job-settings').first().locator('[data-flow-field="duration"]').selectOption('4s');
  await delayed.evaluate(async()=>{releaseRead();await Promise.all([pendingProduct,pendingStory]);});
  assert.equal(await delayed.evaluate(()=>calls.find(c=>c.action==='create_product').payload.flow_settings.duration),'4s','late defaults preserve custom selection');
  assert.equal(await delayed.evaluate(()=>calls.find(c=>c.action==='create_story').payload.flow_settings.duration),'6s');
  await delayed.close();
  const timed=await readFailurePage(browser,{timeout:true});
  await timed.evaluate(()=>{window.fail='';window.delayRead=true;window.pendingStart=postAction('create_product',{}).then(()=>'',e=>e.message);});
  assert.match(await timed.evaluate(()=>pendingStart),/ยังไม่ตอบกลับ/);
  assert.equal(await timed.evaluate(()=>calls.filter(c=>c.action==='create_product').length),0,'timed-out defaults must not dispatch');
  await timed.evaluate(async()=>{window.delayRead=false;window.duration='8s';await postAction('create_product',{});releaseRead();});
  await timed.evaluate(()=>postAction('create_story',{}));
  assert.equal(await timed.evaluate(()=>calls.find(c=>c.action==='create_story').payload.flow_settings.duration),'8s','late timed-out read cannot replace recovered defaults');
  await timed.close();
  console.log(JSON.stringify({ok:true,firstLoginRecovery:true,coalescedRead:true,lateReadIgnored:true,preservedChoices:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
