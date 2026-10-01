// Isolated UI component, no app/Extension/provider requests or live ports.
const {chromium}=require('playwright');
const assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<html lang="th"><body><select id="product-video-provider"></select><div id="creation-form"><div class="cq-buttons"></div></div><select id="story-video-mode"></select><select id="story-batch-video-mode"></select><select id="drama-video-mode"></select><select id="long-mode"></select></body></html>');
  await page.evaluate(()=>{
   window.calls=[];window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
   window.smartflowCreationFormKey=action=>action;
  });
  await page.addScriptTag({path:'web_ui/ai_cover.js'});
  assert.equal(await page.locator('.ai-cover-options').count(),6);
  assert.equal(await page.locator('[data-cover-scene][type="number"]').count(),0);
  assert.equal(await page.locator('select[data-cover-scene]').count(),6);
  for(const key of ['product','product-batch','story','story-batch','drama','long']){
   await page.evaluate(key=>postAction(key,{render_options:{subtitle_enabled:false}}),key);
  }
  const calls=await page.evaluate(()=>window.calls);
  assert(calls.every(c=>c.payload.ai_cover_options.enabled===true));
  assert(calls.every(c=>c.payload.render_options.subtitle_enabled===false));
  await page.evaluate(()=>prepareAudioQueue({settings:{ai_cover_options:{enabled:false,headline:'เก่า',scene_index:2}}}));
  await page.evaluate(()=>postAction('product-batch',{}));
  assert.deepEqual((await page.evaluate(()=>calls.at(-1))).payload.ai_cover_options,{enabled:false,headline:'เก่า',scene_index:2});
  await page.locator('.ai-cover-options').nth(1).locator('summary').click();
  await page.locator('.ai-cover-options').nth(1).locator('[data-cover-scene]').selectOption('0');
  await page.evaluate(()=>postAction('product-batch',{}));
  assert.equal((await page.evaluate(()=>calls.at(-1))).payload.ai_cover_options.scene_index,0);
  await page.evaluate(()=>postAction('story',{job_id:'STORY-EXISTING'}));
  assert.equal((await page.evaluate(()=>calls.at(-1))).payload.ai_cover_options,undefined);
  for(const width of [1440,600]){
   await page.setViewportSize({width,height:900});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({ok:true,panels:6,oldJobPreserved:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
