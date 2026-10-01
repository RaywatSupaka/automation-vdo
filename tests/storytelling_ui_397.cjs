// Actual markup/controllers, isolated Chromium; no live app/Chrome/provider traffic.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const read=f=>fs.readFileSync(f,'utf8');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];let checks=0;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(url.hostname!=='smartflow.test'||route.request().method()!=='GET')throw Error('Unexpected request');
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:read('web_ui/index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'')});
  if(/^\/desktop\/[\w.-]+\.css$/.test(url.pathname))return route.fulfill({contentType:'text/css',body:read('web_ui/'+path.basename(url.pathname))});
  return route.abort();
 });
 await page.goto('http://smartflow.test/');
 await page.evaluate(()=>{
  window.ui={dramaImages:{}};window.toast=()=>{};window.calls=[];
  window.postAction=async(action,payload={})=>{calls.push({action,payload:JSON.parse(JSON.stringify(payload))});return {ok:true};};
  window.renderCreationQueue=state=>{document.querySelector('#creation-form').innerHTML=state.creation_queue.items.map(row=>`<div class="cq-row"><span data-id="${row.queue_id}"></span></div>`).join('');};
  window.showPage=key=>document.querySelectorAll('.page').forEach(n=>n.classList.toggle('active',n.dataset.view===key));
  showPage('drama');const form=document.createElement('div');form.id='creation-form';form.innerHTML='<div class="cq-buttons"></div>';document.body.append(form);
 });
 for(const f of ['media_audio.js','storytelling.js','creator_ux.js','function_controls.js'])await page.addScriptTag({content:read('web_ui/'+f)});
 assert.equal(await page.locator('[data-storytelling]').count(),3);checks++;
 assert.equal(await page.locator('select[name=storytelling-drama]').inputValue(),'narrator');checks++;
 await page.selectOption('[name=storytelling-drama]','dialogue');
 assert(await page.locator('[data-storytelling=drama] .storytelling-warning').isVisible());checks++;
 const rejected=await page.evaluate(()=>postAction('create_drama_series',{render_options:{video_generation_mode:'image_motion'}}).catch(e=>e.message));
 assert.match(rejected,/เลือก/);checks++;
 await page.selectOption('#drama-video-mode','google_flow');
 assert.equal(await page.locator('[data-storytelling=drama] .storytelling-warning').isVisible(),false);checks++;
 await page.getByRole('button',{name:'＋ เพิ่มตัวละคร',exact:true}).click();
 assert(await page.locator('#drama-character-2-name').isVisible());checks++;
 await page.getByRole('button',{name:'＋ เพิ่มตัวละคร',exact:true}).click();
 assert(await page.locator('#drama-character-3-name').isVisible());checks++;
 assert.equal(await page.locator('#drama-character-3-voice').isVisible(),false);checks++;
 await page.evaluate(async()=>{const pending=postAction('create_drama_series',{render_options:{video_generation_mode:'google_flow'},characters:[{name:'มะลิ'},{name:'ต้น'}]});
   const mode=document.querySelector('[name=storytelling-drama]');mode.value='solo';mode.dispatchEvent(new Event('change',{bubbles:true}));await pending;});
 const sent=await page.evaluate(()=>calls.at(-1));assert.equal(sent.payload.storytelling_options.mode,'dialogue');assert.equal(sent.payload.audio_choices.mode,'flow_original');checks+=2;
 assert.equal(sent.payload.audio_choices.video_audio_volume,100);checks++;
 await page.selectOption('[name=storytelling-drama]','dialogue');
 await page.check('[name=audio-mode-drama][value=api]');
 assert(await page.locator('#drama-character-1-voice').isVisible());checks++;
 const dubbed=await page.evaluate(async()=>{await postAction('create_drama_series',{render_options:{video_generation_mode:'google_flow'},characters:[{name:'มะลิ'},{name:'ต้น'}]});return calls.at(-1).payload;});
 assert.equal(dubbed.audio_choices.mode,'api');assert.equal(dubbed.storytelling_options.mode,'dialogue');checks+=2;
 await page.selectOption('[name=storytelling-drama]','visual');
 const audio=await page.evaluate(()=>mediaAudioChoice('drama'));assert.equal(audio.subtitle,false);assert.equal(audio.mode,'none');checks+=2;
 assert.equal(await page.locator('#drama-character-1-voice').isVisible(),false);checks++;
 await page.selectOption('#drama-video-mode','image_motion');
 await page.evaluate(async()=>postAction('create_drama_series',{render_options:{video_generation_mode:'image_motion'},characters:[{name:'มะลิ'}]}));
 assert.equal((await page.evaluate(()=>calls.at(-1))).payload.audio_choices.mode,'none');checks++;
 await page.selectOption('[name=storytelling-drama]','dialogue');
 assert.equal((await page.evaluate(()=>mediaAudioChoice('drama'))).mode,'api');checks++;
 await page.evaluate(()=>showPage('story'));
 await page.selectOption('#story-video-mode','google_flow');await page.selectOption('[name=storytelling-story]','solo');
 await page.evaluate(()=>prepareStoryAudioBatch());
 assert.equal(await page.evaluate(()=>storytellingModeFor('story-batch')),'solo');checks++;
 assert.equal((await page.evaluate(()=>mediaAudioChoice('story-batch'))).mode,'flow_original');checks++;
 assert.equal((await page.evaluate(()=>mediaAudioChoice('story-batch'))).video_audio_volume,100);checks++;
 await page.selectOption('[name=storytelling-story]','narrator');
 await page.evaluate(()=>setMediaAudioChoice('story',{mode:'api',subtitle:true,music:true,sfx:false,keep_video_audio:true,video_audio_volume:22}));
 await page.selectOption('[name=storytelling-story]','solo');
 assert.equal((await page.evaluate(()=>mediaAudioChoice('story'))).video_audio_volume,100);checks++;
 await page.selectOption('[name=storytelling-story]','narrator');
 const restored=await page.evaluate(()=>mediaAudioChoice('story'));
 assert.equal(restored.video_audio_volume,22);assert.equal(restored.keep_video_audio,true);assert.equal(restored.subtitle,true);checks+=3;
 await page.evaluate(()=>postAction('create_story',{job_id:'OLD'}));
 assert.equal((await page.evaluate(()=>calls.at(-1))).payload.storytelling_options,undefined);checks++;
 // Queue summaries use the saved mode, not the current form or legacy actor flag.
 await page.evaluate(()=>renderCreationQueue({creation_queue:{items:['narrator','solo','dialogue','visual'].map(mode=>({queue_id:mode,settings:{storytelling_options:{version:1,mode},actor_dialogue:mode!=='narrator',audio_choices:{mode:'flow_original',subtitle:false}}}))}}));
 for(const [mode,label] of [['narrator','ผู้บรรยายเล่าเรื่อง'],['solo','ตัวละครพูดเอง'],['dialogue','ตัวละครสนทนา'],['visual','เล่าเรื่องด้วยภาพ']]){
  const summary=await page.locator(`[data-id="${mode}"]`).locator('..').locator('.media-audio-queue-summary').textContent();
  assert(summary.startsWith(label+' • '));checks++;
 }
 await page.evaluate(()=>postAction('create_story',{video_generation_mode:'google_flow',creative_context:{kind:'product_story',product_short:true}}));
 assert.equal((await page.evaluate(()=>calls.at(-1))).payload.storytelling_options,undefined);checks++;
 // Sidebar/layout regression at all three representative widths.
 for(const width of [1440,980,600]){
  await page.setViewportSize({width,height:1000});await page.evaluate(()=>showPage('drama'));
  const overflow=await page.locator('[data-storytelling=drama]').evaluate(n=>n.scrollWidth>n.clientWidth+1);
  assert.equal(overflow,false);checks++;
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.selectOption('[name=storytelling-drama]','dialogue');
 const report='build/storytelling-compact-ui';fs.mkdirSync(report,{recursive:true});
 await page.locator('[data-storytelling=drama]').screenshot({path:report+'/storytelling-controls.png'});
 assert.deepEqual(errors,[]);checks++;
 console.log(JSON.stringify({ok:true,checks,errors,providerRequests:0}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
