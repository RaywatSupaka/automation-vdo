const fs=require('fs'),assert=require('assert/strict');const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,channel:'msedge'});try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setContent(fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
 await page.evaluate(()=>{window.ui={};window.showPage=()=>{};window.toast=()=>{};window.fetch=async(url,options)=>{window.sent=JSON.parse(options.body);return {ok:true,json:async()=>({ok:true})};};});
 const source=fs.readFileSync('web_ui/app.js','utf8');const start=source.indexOf('async function postAction('),end=source.indexOf('\n}',start)+2;
 await page.addScriptTag({content:source.slice(start,end)});
 await page.addScriptTag({path:'web_ui/media_audio.js'});
 await page.addScriptTag({path:'web_ui/queue_choice.js'});
 for(const [key,action,payload,expected] of [
 ['product','create_product',{link:'https://s.shopee.co.th/test'},'creation_enqueue'],
 ['story','create_story',{topic:'rabbit',video_generation_mode:'google_flow'},'creation_enqueue'],
 ['long','create_story',{topic:'long',long_video:{duration_seconds:180},video_generation_mode:'google_flow'},'enqueue_long_video'],
 ['drama','create_drama_series',{title:'drama',render_options:{video_generation_mode:'google_flow'}},'create_drama_series']]){
  await page.evaluate(({key})=>document.getElementById(key+'-queue-only').checked=true,{key});
  await page.evaluate(({action,payload})=>postAction(action,payload),{action,payload});
  const sent=await page.evaluate(()=>window.sent);assert.equal(sent.action,expected);assert.equal(sent.payload.queue_only,true);assert.equal(sent.payload.audio_choices.mode,'api');
 }
 await page.evaluate(()=>{const select=document.getElementById('story-video-mode');select.value='google_flow';select.dispatchEvent(new Event('change'));const panel=(select.closest('label')||select).nextElementSibling;panel.querySelector('[data-audio-keep]').checked=true;panel.querySelector('[data-audio-subtitle]').checked=false;});
 await page.evaluate(()=>postAction('create_story',{topic:'mixed',video_generation_mode:'google_flow'}));
 const mixed=await page.evaluate(()=>sent.payload);assert.equal(mixed.audio_choices.keep_video_audio,true);assert.equal(mixed.subtitle,false);
 await page.evaluate(()=>postAction('create_story',{job_id:'OLD'}));assert.equal(await page.evaluate(()=>sent.action),'create_story');assert.equal(await page.evaluate(()=>sent.payload.queue_only),undefined);
 assert.deepEqual(errors,[]);console.log('PASS four queue checkboxes, real postAction routing after audio capture, mix/subtitle preserved, old job unaffected');
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
