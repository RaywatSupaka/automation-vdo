// Offline UI contract: no live Chrome, HTTP requests, saved settings or credits.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:400,height:802}});
  await page.route('**/*',route=>route.abort());
  await page.setContent('<section data-view="settings"><div class="page-intro"></div></section>'+['product-video-provider','creation-product-video-provider','story-video-mode','story-batch-video-mode','drama-video-mode','long-mode','presenter-screen'].map(id=>`<label><select id="${id}"><option value="google_flow">Flow</option><option value="image_motion">Local</option>${id==='product-video-provider'?'<option value="meta_ai">Meta</option>':''}</select></label>`).join('')+'<form id="creation-form"><div class="cq-buttons"></div></form>');
  await page.addScriptTag({content:`window.calls=[];let postAction=async(action,payload)=>{window.calls.push({action,payload});if(action==='flow_settings_get')return {ok:true,settings:{duration:'6s'}};if(action==='flow_settings_save')return {ok:true,settings:payload.settings};if(action==='flow_settings_read')return window.blockFlowRead?{ok:false,blocked:true,error:'หน้า AI/Flow ยังรายงานว่ามีงานค้าง',command_id:null}:{ok:true,command_id:'CMD-1'};if(action==='flow_settings_result')return {ok:true,status:'completed',checked_at:1,capabilities:{model:['Observed'],model_menu_open:true,duration:['4s','6s'],resolution:['360p'],video_type:['Frames'],credit_notice:''}};return {ok:true};};`});
  for(const name of ['media_audio.js','flow_settings.js'])await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../web_ui',name),'utf8')});
  assert.equal(await page.locator('.flow-job-settings').count(),7);
  assert.equal(await page.locator('[data-flow-custom]').count(),0);
  assert.equal(await page.locator('[data-flow-reset]').count(),7);
  const allModels=['Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]'];
  // All five must be available before ANY discovery command, on every form.
  for(const panel of await page.locator('.flow-job-settings').all()){
    const values=await panel.locator('[data-flow-field="model"] option').evaluateAll(items=>items.map(x=>x.value));
    assert.deepEqual(values,['',...allModels]);
  }
  assert.equal(await page.locator('[data-flow-field="display"]').count(),0);
  assert.match(await page.locator('.flow-job-settings').first().locator('[data-flow-field="model"] option[value="Veo 3.1 - Lite [Lower Priority]"]').textContent(),/ยังไม่ตรวจ/);
  await page.locator('[data-flow-save]').click();
  await page.evaluate(()=>postAction('create_product',{}));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),'6s');
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.display),'compact');
  await page.evaluate(()=>postAction('create_product',{job_id:'OLD'}));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),undefined);
  await page.locator('[data-flow-read]').click();
  await page.waitForFunction(()=>document.querySelector('[data-flow-status]').textContent.includes('อ่านล่าสุด'));
  assert.match(await page.locator('[data-flow-status]').innerText(),/ไม่พบยอดเครดิต/);
  assert.match(await page.locator('.flow-job-settings').first().locator('[data-flow-field="model"] option[value="Veo 3.1 - Lite [Lower Priority]"]').textContent(),/ไม่พบในเมนูตอนนี้/);
  const pollCount=await page.evaluate(()=>window.calls.filter(c=>c.action==='flow_settings_result').length);
  await page.evaluate(()=>{window.blockFlowRead=true;});
  await page.locator('[data-flow-read]').click();
  await page.waitForFunction(()=>document.querySelector('[data-flow-status]').textContent.includes('ทำรายการไม่สำเร็จ'));
  assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.action==='flow_settings_result').length),pollCount,'Blocked inspection must not poll a null command');
  assert.equal(await page.locator('[data-flow-read]').isEnabled(),true);
  await page.evaluate(()=>{window.blockFlowRead=false;});
  assert.equal(await page.locator('[data-flow-editor] [data-flow-field="model"] option').count(),7);
  await page.evaluate(()=>window.prepareAudioQueue({settings:{flow_settings:{duration:'4s'}}}));
  await page.locator('[data-flow-editor] [data-flow-field="duration"]').selectOption('6s');await page.locator('[data-flow-save]').click();
  await page.evaluate(()=>postAction('creation_edit',{}));assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),'4s');
  await page.evaluate(()=>window.prepareAudioQueue(null));await page.evaluate(()=>postAction('creation_enqueue',{mode:'product'}));assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),'6s');
  for(const [action,payload] of [['create_story',{}],['enqueue_story_batch',{}],['create_drama_series',{render_options:{video_generation_mode:'google_flow'}}],['enqueue_long_video',{}],['presenter_create',{}],['creation_enqueue',{mode:'story'}]]){
   await page.evaluate(([a,p])=>postAction(a,p),[action,payload]);const last=await page.evaluate(()=>window.calls.at(-1));assert.equal(last.payload.flow_settings.duration,'6s');assert.equal(last.payload.flow_settings.display,'compact');
   if(payload.render_options)assert.equal(last.payload.render_options.flow_settings.duration,'6s');
  }
  // User need not open global settings, read Chrome, or tick custom first.
  const product=page.locator('.flow-job-settings').first();
  assert.equal(await product.getAttribute('open'),null,'Flow controls start compact');
  await product.locator('summary').click();
  assert.equal(await product.locator('[data-flow-field="model"]').isVisible(),true);
  await product.locator('[data-flow-field="model"]').selectOption('Omni 1.1 Flash');
  await product.locator('[data-flow-field="video_type"]').selectOption('Frames');
  await product.locator('[data-flow-field="resolution"]').selectOption('720p');
  await product.locator('[data-flow-field="duration"]').selectOption('10s');
  await page.evaluate(()=>postAction('create_product',{}));
  const direct=await page.evaluate(()=>window.calls.at(-1).payload.flow_settings);
  assert.equal(direct.model,'Omni 1.1 Flash');assert.equal(direct.resolution,'720p');assert.equal(direct.duration,'10s');assert.equal(direct.video_type,'Frames');
  await page.evaluate(()=>window.prepareAudioQueue(null));await page.evaluate(()=>postAction('creation_enqueue',{mode:'product'}));
  assert.deepEqual(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),direct);
  await product.locator('[data-flow-field="model"]').selectOption('Veo 3.1 - Fast');
  assert.equal(await product.locator('[data-flow-field="duration"] option[value="10s"]').count(),0);
  assert.equal(await product.locator('[data-flow-field="resolution"] option[value="360p"]').count(),0);
  await page.evaluate(()=>postAction('create_product',{}));assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),undefined);
  await page.evaluate(()=>postAction('creation_edit',{}));assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),'10s');
  await product.locator('[data-flow-field="model"]').selectOption('Omni 1.1 Flash');
  await product.locator('[data-flow-field="duration"]').selectOption('6s');
  for(const model of allModels){
    await product.locator('[data-flow-field="model"]').selectOption(model);
    await product.locator('[data-flow-field="video_type"]').selectOption('Ingredients');
    await product.locator('[data-flow-field="resolution"]').selectOption('720p');
    await product.locator('[data-flow-field="duration"]').selectOption('6s');
    await page.evaluate(()=>postAction('create_product',{}));
    const requested=await page.evaluate(()=>window.calls.at(-1).payload.flow_settings);
    assert.equal(requested.model,model);assert.equal(requested.duration,'6s');assert.equal(requested.resolution,'720p');
    await page.evaluate(()=>window.prepareAudioQueue(null));await page.evaluate(()=>postAction('creation_enqueue',{mode:'product'}));
    assert.deepEqual(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),requested);
  }
  const queueBeforeReset=await page.evaluate(()=>window.calls.at(-1).payload.flow_settings);
  const callsBeforeReset=await page.evaluate(()=>window.calls.length);
  await product.locator('[data-flow-reset]').click();
  assert.equal(await page.evaluate(()=>window.calls.length),callsBeforeReset,'reset must not write jobs/settings');
  assert.equal(await product.locator('[data-flow-value-status]').innerText(),'ใช้ค่าตั้งต้น');
  assert.equal(await product.locator('[data-flow-reset]').isDisabled(),true);
  await page.evaluate(()=>postAction('creation_edit',{}));
  assert.deepEqual(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),queueBeforeReset,'reset other form must preserve queued snapshot');
  await product.locator('[data-flow-field="model"]').selectOption('Omni 1.1 Flash');
  assert.equal(await product.locator('[data-flow-value-status]').innerText(),'ตั้งค่าเฉพาะงานนี้');
  assert.equal(await product.locator('[data-flow-reset]').isDisabled(),false);
  assert.equal(await page.locator('[data-flow-job-save]').count(),7);
  await product.locator('[data-flow-field="duration"]').selectOption('10s');
  await product.locator('[data-flow-job-save]').click();
  await page.waitForFunction(()=>document.querySelector('[data-flow-save-status]').textContent.startsWith('บันทึกแล้ว'));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).action),'flow_settings_save');
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.settings.duration),'10s');
  assert.equal(await product.locator('[data-flow-value-status]').innerText(),'ใช้ค่าตั้งต้น');
  await page.evaluate(()=>postAction('create_story',{video_generation_mode:'google_flow'}));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings.duration),'10s');
  await page.evaluate(()=>postAction('creation_edit',{}));
  assert.deepEqual(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),queueBeforeReset,'saving defaults must preserve queue edit snapshot');
  if(process.env.SMARTFLOW_CONTROLS_SCREENSHOT){
    await page.addStyleTag({content:fs.readFileSync(path.join(__dirname,'../web_ui/styles.css'),'utf8')+'\n'+fs.readFileSync(path.join(__dirname,'../web_ui/flow_settings.css'),'utf8')});
    await product.screenshot({path:process.env.SMARTFLOW_CONTROLS_SCREENSHOT});
  }
  await page.locator('#story-video-mode').selectOption('image_motion');
  assert.equal(await page.locator('.flow-job-settings').nth(2).isVisible(),false,'Hide irrelevant Flow controls when local motion is selected');
  await page.evaluate(()=>postAction('create_story',{}));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),undefined,'local motion does not inherit Flow settings');
  await page.locator('#product-video-provider').selectOption('meta_ai');
  await page.evaluate(()=>postAction('create_product',{}));
  assert.equal(await page.evaluate(()=>window.calls.at(-1).payload.flow_settings),undefined,'Meta does not inherit Flow settings');
  console.log(JSON.stringify({ok:true,panels:7,routes:9}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
