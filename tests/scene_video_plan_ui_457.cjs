// Offline browser fixtures only; all actions mocked, no provider or user profile.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});let checks=0,network=0;
try{
  const page=await browser.newPage({viewport:{width:400,height:900}});
  await page.route('**/*',r=>{network++;return r.abort();});
  await page.setContent('<section data-view="settings" hidden><div class="page-intro"></div></section><main id="fixture" style="padding:12px"><section id="plan"></section></main>');
  const safeError=fs.readFileSync('web_ui/app.js','utf8').match(/function safeUiError\(message\) \{[\s\S]*?\n\}/)?.[0];
  assert(safeError);await page.addScriptTag({content:`${safeError};window.smartflowSafeError=safeUiError;`});
  await page.addStyleTag({content:fs.readFileSync('web_ui/styles.css','utf8')+'\n'+fs.readFileSync('web_ui/studio.css','utf8')});
  await page.addScriptTag({content:`window.calls=[];window.toasts=[];window.saved=[];
    const escapeHtml=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const toast=(message,kind)=>toasts.push({message,kind});
    let postAction=async(action,payload={})=>{calls.push({action,payload:structuredClone(payload)});
      if(action==='flow_settings_get')return {ok:true,settings:{}};
      if(action==='flow_settings_read')return {ok:true,command_id:'owned-fixture'};
      if(action==='flow_settings_result')return {status:'completed',checked_at:1,capabilities:{model_menu_open:true,model:['Observed model'],context:{model:'Observed model',video_type:'Frames'},states:{duration:'selectable'},duration:['4s'],selected:{model:'Observed model'}}};
      if(action==='story_save_video_plan'){
        if(window.failSave)throw Error('Lost ACK');
        if(window.holdSave)await new Promise(resolve=>window.releaseSave=resolve);
        return {ok:true,review:structuredClone(window.review)};
      }
      return {ok:true};
    };
    window.makeReview=(active=false)=>({job_id:'STORY-FIXTURE',active,video_plan:{supported:true,enabled:false,editable:true,revision:2,provider:'google_flow',flow_settings:{model:'Veo 3.1 - Fast',duration:'4s'},remaining_indices:[3,4],kept_indices:[1,2],counts:{completed:2,flow:1,meta:1,pending:2},scenes:[
      {index:1,provider:'google_flow',state:'completed',editable:false},
      {index:2,provider:'meta_ai',state:'completed',editable:false},
      {index:3,provider:'google_flow',state:active?'active':'pending',editable:true},
      {index:4,provider:'google_flow',state:'pending',editable:true}]}});
    window.renderPlan=(active=false)=>{window.review=makeReview(active);window.editor=SmartFlowVideoPlan.mount(document.querySelector('#plan'),review,{onSaved:r=>saved.push(r)});};`});
  for(const name of ['flow_settings.js','scene_video_plan.js'])await page.addScriptTag({content:fs.readFileSync('web_ui/'+name,'utf8')});
  await page.evaluate(()=>renderPlan());
  const panel=page.locator('#plan');
  assert.match(await panel.innerText(),/เก็บคลิปเดิม 2/);checks++;
  assert.equal(await panel.locator('.scene-plan-flow').getAttribute('open'),null);checks++;
  assert.equal(await panel.locator('[data-plan-scene="1"]').isDisabled(),true);checks++;
  await panel.locator('[data-plan-provider]').selectOption('meta_ai');
  assert.equal(await panel.locator('.scene-plan-flow').isVisible(),false);checks++;
  await panel.locator('[data-plan-save]').click();
  assert.match(await panel.locator('[data-plan-confirm-text]').innerText(),/3, 4/);checks++;
  assert.equal(await page.evaluate(()=>calls.some(c=>c.action==='story_save_video_plan')),false);checks++;
  await panel.locator('[data-plan-confirm-save]').click();
  const request=await page.evaluate(()=>calls.find(c=>c.action==='story_save_video_plan'));
  assert.deepEqual(request.payload,{job_id:'STORY-FIXTURE',plan_revision:2,provider:'meta_ai',scene_indices:[3,4],flow_settings:{}});checks++;
  assert.equal(await page.evaluate(()=>calls.some(c=>c.action==='retry_story')),false);checks++;
  await page.evaluate(()=>{calls.length=0;renderPlan();});
  await panel.locator('.scene-plan-scenes summary').click();
  await panel.locator('[data-plan-scene="3"]').uncheck();
  await panel.locator('[data-plan-resume]').click();await panel.locator('[data-plan-confirm-save]').click();
  assert.deepEqual(await page.evaluate(()=>calls.map(c=>c.action)),['story_save_video_plan','retry_story']);checks++;
  assert.deepEqual(await page.evaluate(()=>calls[0].payload.scene_indices),[4]);checks++;
  await page.evaluate(()=>{calls.length=0;renderPlan(true);});
  assert.equal(await panel.locator('[data-plan-resume]').isVisible(),false);checks++;
  assert.equal(await panel.locator('[data-plan-read]').isDisabled(),true);checks++;
  await panel.locator('[data-plan-provider]').selectOption('meta_ai');
  const draft=await page.evaluate(()=>editor.readDraft());
  assert.equal(draft.provider,'meta_ai');checks++;
  await page.evaluate(draft=>{renderPlan(true);editor.restore(draft);},draft);
  assert.equal(await panel.locator('[data-plan-provider]').inputValue(),'meta_ai');checks++;
  await page.evaluate(()=>{calls.length=0;failSave=true;renderPlan();});
  await panel.locator('[data-plan-resume]').click();await panel.locator('[data-plan-confirm-save]').click();
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='retry_story').length),0);checks++;
  assert.match(await panel.locator('[data-plan-status]').innerText(),/ไม่ได้ส่งคำสั่งสร้างซ้ำอัตโนมัติ/);assert.doesNotMatch(await panel.locator('[data-plan-status]').innerText(),/Lost ACK/);checks++;
  await page.evaluate(()=>{failSave=false;calls.length=0;holdSave=true;renderPlan();});
  await panel.locator('[data-plan-save]').click();await panel.locator('[data-plan-confirm-save]').click();
  await page.waitForFunction(()=>typeof window.releaseSave==='function');
  await page.evaluate(()=>document.querySelector('[data-plan-confirm-save]').click());
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='story_save_video_plan').length),1);checks++;
  await page.evaluate(()=>{releaseSave();holdSave=false;});
  await page.waitForFunction(()=>!document.querySelector('[data-plan-save]').disabled);
  await page.evaluate(()=>renderPlan());await panel.locator('.scene-plan-flow summary').click();
  await panel.locator('[data-plan-read]').click();
  await page.waitForFunction(()=>document.querySelector('[data-plan-capabilities]').textContent.includes('อ่านล่าสุด'));
  assert.match(await panel.locator('[data-flow-field="model"] option[value="Veo 3.1 - Fast"]').textContent(),/ไม่พบในเมนู/);checks++;
  await panel.locator('[data-plan-save]').click();assert.match(await panel.locator('[data-plan-status]').innerText(),/ไม่พบในเมนู/);checks++;
  await panel.locator('[data-flow-field="model"]').selectOption('Observed model');
  await panel.locator('[data-flow-field="duration"]').selectOption('4s');
  for(const width of [320,400,900]){
    await page.setViewportSize({width,height:900});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Horizontal overflow '+width);checks++;
  }
  if(process.env.SMARTFLOW_PLAN_SCREENSHOT)await panel.screenshot({path:process.env.SMARTFLOW_PLAN_SCREENSHOT});
  assert.equal(network,0);checks++;
  console.log(JSON.stringify({ok:true,checks,providerRequests:0}));
}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
