const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,channel:'msedge'});try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
  await page.evaluate(()=>{const form=document.createElement('form');form.id='creation-form';form.innerHTML='<div class="cq-buttons"></div>';document.body.append(form);window.calls=[];window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};});
  await page.addScriptTag({path:'web_ui/media_audio.js'});await page.addScriptTag({path:'web_ui/flow_motion.js'});
  assert.equal(await page.locator('[data-flow-fictional]').count(),6);
  for(const [key,action,payload] of [['product','create_product',{}],['story','create_story',{}],['story-batch','enqueue_story_batch',{}],['drama','create_drama_series',{}],['long','enqueue_long_video',{}],['product-batch','creation_enqueue',{mode:'product'}]]){
    await page.locator(`[data-flow-fictional="${key}"]`).evaluate(n=>{n.checked=true;});
    await page.evaluate(({action,payload})=>postAction(action,payload),{action,payload});
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.fictional_ai_characters_confirmed),true);
    assert(await page.evaluate(()=>calls.at(-1).payload.audio_choices),'existing sound choices retained');
  }
  await page.evaluate(()=>{prepareAudioQueue({settings:{fictional_ai_characters_confirmed:false}});return postAction('creation_edit',{queue_id:'Q'});});
  assert.equal(await page.evaluate(()=>calls.at(-1).payload.fictional_ai_characters_confirmed),false);
  await page.evaluate(()=>postAction('create_product',{job_id:'OLD'}));
  assert.equal(await page.evaluate(()=>Object.hasOwn(calls.at(-1).payload,'fictional_ai_characters_confirmed')),false);
  assert.deepEqual(errors,[]);console.log('PASS: 6 explicit consent controls, queue snapshot/edit, historical resume unchanged; owned headless browser closed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
