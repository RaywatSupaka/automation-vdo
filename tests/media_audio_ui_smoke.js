const fs=require('fs'),assert=require('assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,channel:'msedge'});try{
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
await page.setContent(html);await page.evaluate(()=>{const f=document.createElement('form');f.id='creation-form';f.innerHTML='<div class="cq-buttons"></div>';document.body.append(f);window.calls=[];window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};});
await page.addScriptTag({path:'web_ui/media_audio.js'});
assert.equal(await page.locator('.media-audio-controls').count(),6);
await page.evaluate(()=>{prepareAudioQueue({settings:{audio_choices:{mode:'api',keep_video_audio:true,video_audio_volume:15}}});return postAction('creation_edit',{queue_id:'volume'});});
assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.video_audio_volume),15);
assert.equal(await page.locator('[data-audio-volume-wrap]:not([hidden])').count(),1);
for(const [id,action,payload] of [['product-video-provider','create_product',{}],['story-video-mode','create_story',{video_generation_mode:'google_flow'}],['story-batch-video-mode','enqueue_story_batch',{video_generation_mode:'google_flow'}],['drama-video-mode','create_drama_series',{render_options:{video_generation_mode:'google_flow'}}],['long-mode','enqueue_long_video',{video_generation_mode:'google_flow'}]]){
await page.evaluate(({id})=>{const select=document.getElementById(id);if(id!=='product-video-provider'){select.value='google_flow';select.dispatchEvent(new Event('change'));}const panel=(select.closest('label')||select).nextElementSibling;panel.querySelector('[data-main-audio]').value='flow_original';panel.querySelector('[data-main-audio]').dispatchEvent(new Event('change'));},{id});
await page.evaluate(({action,payload})=>postAction(action,payload),{action,payload});
assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'flow_original');
assert.equal(await page.evaluate(()=>calls.at(-1).payload.subtitle),true);
}
await page.evaluate(()=>{prepareAudioQueue({settings:{audio_choices:{mode:'none',subtitle:false,music:true}}});return postAction('creation_edit',{queue_id:'Q'});});
assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.music),true);
await page.evaluate(()=>postAction('create_product',{job_id:'OLD'}));assert.equal(await page.evaluate(()=>Object.hasOwn(calls.at(-1).payload,'audio_choices')),false);
assert.deepEqual(errors,[]);console.log('PASS:6 pre-create/queue panels,5 creation routes,main audio switch preserves subtitle choice,queue edit,legacy resume untouched; browser closed.');
for(const name of ['styles.css','workspace.css','creation_queue.css','usability.css','media_audio.css'])await page.addStyleTag({path:'web_ui/'+name});
fs.mkdirSync('docs/reports/audio-choices-1',{recursive:true});
await page.evaluate(()=>{document.querySelectorAll('.page').forEach(n=>n.classList.toggle('active',n.dataset.view==='products'));});
for(const width of [1400,900,600]){
await page.setViewportSize({width,height:1000});
const panel=page.locator('[data-view="products"] .media-audio-controls');
await panel.screenshot({path:`docs/reports/audio-choices-1/controls-${width}.png`});
assert.equal(await panel.evaluate(n=>n.scrollWidth<=n.clientWidth+2),true);
}
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
