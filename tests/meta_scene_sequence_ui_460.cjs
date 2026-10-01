const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.resolve(__dirname,'../web_ui/app.js'),'utf8');
const helper=source.slice(source.indexOf('function metaSequenceAction('),source.indexOf('function renderLongVideoRecovery('));
const confirm=source.slice(source.indexOf('function openConfirm('),source.indexOf('async function openDetail('));
const action=source.slice(source.indexOf("  const adoptMeta = event.target.closest('[data-adopt-meta-sequence]');"),source.indexOf("  const retryStory = event.target.closest('[data-retry-story]');"));
assert(helper&&confirm&&action);
(async()=>{
 const browser=await chromium.launch({headless:true});let checks=0;
 try{
  const page=await browser.newPage();
  await page.setContent('<div id="buttons"></div><dialog id="confirm-modal"><h2 id="confirm-title"></h2><p id="confirm-message"></p><button id="confirm-accept"></button></dialog>');
  await page.addScriptTag({content:`const $=s=>document.querySelector(s),ui={};const escapeHtml=s=>String(s).replaceAll('<','&lt;').replaceAll('"','&quot;');
   window.calls=[];window.poll=async()=>{};window.toast=()=>{};window.postAction=async(a,p)=>{calls.push([a,p]);return {ok:true}};
   ${helper}\n${confirm}\ndocument.addEventListener('click',async event=>{${action}});
   $('#confirm-accept').onclick=()=>ui.confirmAction();
   window.show=(patch={},busy=false)=>$('#buttons').innerHTML=metaSequenceAction({id:'STORY-TEST',provider:'chatgpt',video_generation_mode:'meta_ai',status:'failed',...patch},busy);`});
  await page.evaluate(()=>show());assert.equal(await page.locator('[data-adopt-meta-sequence]').count(),1);checks++;
  await page.locator('[data-adopt-meta-sequence]').click();
  assert.equal(await page.locator('#confirm-modal').evaluate(el=>el.open),true);checks++;
  assert.equal(await page.locator('#confirm-accept').innerText(),'เปลี่ยนลำดับ');checks++;
  assert.equal((await page.evaluate(()=>calls)).length,0);checks++;
  await page.locator('#confirm-accept').click();
  assert.deepEqual(await page.evaluate(()=>calls),[['adopt_meta_scene_sequence',{job_id:'STORY-TEST',confirmed:true}]]);checks++;
  for(const patch of [{provider:'gemini'},{video_generation_mode:'google_flow'},{meta_scene_sequence_version:1},
     {content_kind:'product'},{job_type:'drama_episode'},{status:'cancelled'},{video_plan_summary:{}}]){
   await page.evaluate(p=>show(p),patch);assert.equal(await page.locator('[data-adopt-meta-sequence]').count(),0);checks++;
  }
  await page.evaluate(()=>show({},true));assert.equal(await page.locator('[data-adopt-meta-sequence]').count(),0);checks++;
  console.log(JSON.stringify({checks,native_chromium:true,provider_sends:0,live_state_writes:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
