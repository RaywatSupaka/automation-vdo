const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,
  ...(process.env.SMARTFLOW_TEST_CHROME?{executablePath:process.env.SMARTFLOW_TEST_CHROME}:{})});try{
 const page=await browser.newPage({viewport:{width:600,height:900}});
 await page.route('http://smartflow.test/**',route=>route.fulfill({contentType:'text/html',body:'<html></html>'}));
 await page.goto('http://smartflow.test/');
 await page.setContent('<button data-page="products"><span>คลิปสินค้า</span></button><button data-page="product-cast">คลัง</button><section data-view="products"><div class="page-intro"><h1></h1><p></p></div><div class="product-form-footer"></div></section><section data-view="settings"></section>');
 await page.evaluate(()=>{window.pageMeta={};window.toast=()=>{};window.showPage=()=>{};window.calls=[];
  window.postAction=async(action,payload)=>{
   const captured=window.productOptionSnapshot?.finish(action,{...payload,audio_choices:payload.audio_choices||{mode:'api',subtitle:true}});
   if(captured)return captured;
   calls.push({action,payload});
   if(action==='product_cast_state')return {ok:true,assets:[{id:'cast1',name:'ตัวละครหนึ่ง',approved:true,preview:'data:image/png;base64,',outfit_preview:'data:image/jpeg;base64,'}]};
   if(action==='product_story_prepare'&&!payload.product_id)return {ok:true,pending:true,product_id:'SOURCE'};
   if(action==='product_story_prepare'){
     if(window.prepareFails)throw Error('Shopee login required • ยังไม่ได้ส่งงานไป AI');
     if(window.prepareHangs)return new Promise(()=>{});
     return {ok:true,creative_context:{kind:'product_story',snapshot_id:'snap'},topic:'กระเป๋า'};
   }
   return {ok:true};};});
 await page.addScriptTag({content:fs.readFileSync('web_ui/product_snapshot.js','utf8')});
 await page.addScriptTag({content:fs.readFileSync('web_ui/product_story.js','utf8')});
 await page.click('[data-page="products"]');await page.waitForFunction(()=>document.querySelector('#ps-cast').options.length===2);
 assert.equal(await page.inputValue('#ps-count'),'3');assert.equal(await page.isDisabled('#ps-count'),false);
 assert.equal(await page.isChecked('#ps-story-first'),false);
 assert.equal(await page.isVisible('#ps-story-first-example'),false);
 await page.check('#ps-story-first');
 assert.equal(await page.evaluate(()=>localStorage.getItem('smartflow.product.script-style.v1')),'story_first_review');
 assert.equal(await page.isVisible('#ps-story-first-example'),true);
 await page.selectOption('#ps-count','6');
 await page.getByText('บันทึกจำนวนฉากใช้ครั้งหน้า',{exact:true}).click();
 assert.equal(await page.evaluate(()=>localStorage.getItem('smartflow.product.scene-count.v1')),'6');
 assert.equal(await page.isVisible('#ps-cast-gallery'),false);
 await page.check('#ps-use-cast');
 assert.equal(await page.isVisible('#ps-cast-gallery'),true);
 await page.check('#ps-cast-gallery [data-cast-choice="cast1"]');await page.fill('#ps-details','เล่าเรื่องการเดินทาง');
 await page.locator('.ps-outfit-options summary').click();
 await page.selectOption('#ps-outfit-mode','saved');
 await page.evaluate(async()=>{const pending=postAction('create_product',{link:'https://example.invalid/item',provider:'gemini'});document.querySelector('#ps-count').value='15';document.querySelector('#ps-story-first').checked=false;await pending;});
 const calls=await page.evaluate(()=>window.calls);
 const prep=calls.find(c=>c.action==='product_story_prepare');assert.equal(prep.payload.cast_id,'cast1');
 assert.equal(prep.payload.outfit_mode,'saved');
 const create=calls.find(c=>c.action==='create_product');assert.equal(create.payload.creative_context.snapshot_id,'snap');assert.equal(create.payload.story_text,'เล่าเรื่องการเดินทาง');assert.equal(create.payload.scene_count,6);
 assert.deepEqual(create.payload.product_script_options,{version:1,style:'story_first_review'});
 await page.evaluate(()=>postAction('create_product',{link:'https://example.invalid/meta',provider:'gemini',video_provider:'meta_ai'}));
 const metaCreate=await page.evaluate(()=>calls.filter(c=>c.action==='create_product').at(-1));
 assert.equal(metaCreate.payload.video_generation_mode,'meta_ai');assert.equal(metaCreate.payload.provider,'gemini');
 assert.equal(metaCreate.payload.product_script_options.style,'standard');
 await page.evaluate(()=>postAction('create_product',{job_id:'JOB-OLD'}));
 assert.equal((await page.evaluate(()=>calls.filter(c=>c.action==='product_story_prepare'))).length,4);
 assert.equal(calls.filter(c=>c.action==='product_story_prepare')[1].payload.product_id,'SOURCE');
 const old=await page.evaluate(()=>calls.find(c=>c.payload.job_id==='JOB-OLD'));
 assert.equal(old.payload.product_script_options,undefined);
 await page.check('#ps-story-first');
 await page.evaluate(async()=>{const pending=postAction('creation_enqueue',{mode:'product',values:['link-one','link-two'],provider:'chatgpt',audio_choices:{mode:'flow_original'}});document.querySelector('#ps-story-first').checked=false;await pending;});
 const queued=await page.evaluate(()=>calls.filter(c=>c.action==='creation_enqueue'));
 assert.equal(queued.length,2);
 assert(queued.every(c=>c.payload.product_script_options.style==='story_first_review'&&c.payload.audio_choices.mode==='flow_original'));
 // Short film is a separate exclusive mode, frozen before import for every link.
 await page.check('#ps-short-film');
 assert.equal(await page.isChecked('#ps-story-first'),false);
 assert.equal(await page.locator('[name="ps-script-style"]:checked').count(),1);
 assert.equal(await page.isVisible('.ps-film-options'),true);
 assert.equal(await page.isChecked('#ps-film-cta'),true);
 await page.selectOption('#ps-film-genre','twist');await page.uncheck('#ps-film-cta');
 assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('smartflow.product.short-film.v2'))),{genre:'twist',ending_cta:false});
 await page.selectOption('#ps-count','3');
 const filmOptions={version:2,style:'short_film_ad',genre:'twist',ending_cta:false};
 await page.evaluate(async()=>{
   const pending=postAction('creation_enqueue',{mode:'product',values:['film-one','film-two'],provider:'gemini',audio_choices:{mode:'api',subtitle:true}});
   document.querySelector('#ps-film-genre').value='comedy';document.querySelector('#ps-film-cta').checked=true;
   document.querySelector('#ps-script-standard').checked=true;await pending;
 });
 const filmQueued=await page.evaluate(()=>calls.filter(c=>c.action==='creation_enqueue').slice(-2));
 assert(filmQueued.every(c=>c.payload.scene_count===3&&c.payload.audio_choices.mode==='api'&&c.payload.audio_choices.subtitle));
 filmQueued.forEach(c=>assert.deepEqual(c.payload.product_script_options,filmOptions));
 await page.check('#ps-short-film');await page.evaluate(()=>postAction('create_product',{link:'film-direct',video_provider:'meta_ai'}));
 const filmDirect=await page.evaluate(()=>calls.filter(c=>c.action==='create_product').at(-1));
 assert.deepEqual(filmDirect.payload.product_script_options,{version:2,style:'short_film_ad',genre:'comedy',ending_cta:true});
 assert.equal(filmDirect.payload.video_generation_mode,'meta_ai');
 await page.check('#ps-script-standard');assert.equal(await page.isVisible('.ps-film-options'),false);
 await page.check('#cast-assets [data-cast-choice="cast1"]');
 assert.equal(await page.isChecked('#ps-use-cast'),true);
 await page.uncheck('#cast-assets [data-cast-choice="cast1"]');
 assert.equal(await page.isChecked('#ps-use-cast'),false);
 // Preparation has durable visible status, rejects duplicate clicks, and does
 // not dispatch AI on capture failure or an uncertain timed-out local call.
 await page.evaluate(()=>{window.prepareFails=true;});
 const beforeFailure=await page.evaluate(()=>calls.filter(c=>c.action==='create_product').length);
 const failed=await page.evaluate(async()=>{
   const pending=postAction('create_product',{link:'failed-capture',provider:'chatgpt'});
   let duplicate='';try{await postAction('create_product',{link:'duplicate'});}catch(e){duplicate=e.message;}
   try{await pending;}catch(e){return {message:e.message,duplicate};}
 });
 assert.match(failed.message,/Shopee login required/);assert.match(failed.duplicate,/ไม่สร้างคำขอซ้ำ/);
 assert.equal(await page.locator('.product-preparation').getAttribute('data-state'),'error');
 assert.match(await page.locator('.product-preparation').innerText(),/Shopee login required/);
 assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='create_product').length),beforeFailure);
 await page.evaluate(()=>{
   window.prepareFails=false;window.prepareHangs=true;
   const native=setTimeout;window.restorePrepareTimer=()=>{window.setTimeout=native;};
   window.setTimeout=(fn,ms,...args)=>native(fn,ms>=45000?5:ms,...args);
 });
 const timed=await page.evaluate(async()=>{try{await postAction('create_product',{link:'hung-capture'});}catch(e){return e.message;}finally{restorePrepareTimer();}});
 assert.match(timed,/คำขอเดิมถูกเก็บไว้/);
 assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='create_product').length),beforeFailure);
 assert.equal(await page.locator('.product-preparation').getAttribute('data-state'),'error');
 const differentLink=await page.evaluate(async()=>{prepareHangs=false;try{await postAction('create_product',{link:'different-link'});return '';}catch(e){return e.message;}});
 assert.match(differentLink,/ลิงก์เดิมก่อน/);
 await page.evaluate(()=>postAction('create_product',{link:'hung-capture',provider:'gemini'}));
 assert.equal(await page.locator('.product-preparation').getAttribute('data-state'),'ready');
 assert.equal(await page.evaluate(()=>calls.filter(c=>c.action==='create_product').length),beforeFailure+1);
 const hungRequests=await page.evaluate(()=>calls.filter(c=>c.action==='product_story_prepare'&&c.payload.link==='hung-capture').map(c=>c.payload.request_id));
 assert.equal(hungRequests.length,2);assert.equal(hungRequests[0],hungRequests[1],'Retry the same pending product request idempotently');
 await page.check('#ps-use-cast');await page.check('#ps-cast-gallery [data-cast-choice="cast1"]');await page.uncheck('#ps-use-cast');
 assert.equal(await page.isChecked('#ps-cast-gallery [data-cast-choice="cast1"]'),false);
 await page.check('#ps-use-cast');
 const error=await page.evaluate(async()=>{try{await postAction('create_product',{link:'https://example.invalid/item'});return '';}catch(e){return e.message;}});
 assert.match(error,/ติ๊กเลือก/);
 await page.evaluate(()=>{
   window.ui={state:{product_preparations:[{id:'JOB-SOURCE',request_id:'PSP-resume',prepare_options:{
     provider:'gemini',ai_web_model:'gemini-fast',video_generation_mode:'meta_ai',scene_count:6,
     product_script_options:{version:2,style:'short_film_ad',genre:'warm',ending_cta:true},
     story_text:'ค่าที่บันทึกไว้',handoff_mode:'immediate',cast_id:'',audio_choices:{mode:'api',subtitle:true}}}]}};
   window.poll=async()=>{};
   window.dispatchEvent(new CustomEvent('smartflow:resume-product-source',{detail:{product_id:'JOB-SOURCE',request_id:'PSP-resume'}}));
 });
 await page.waitForFunction(()=>calls.some(c=>c.action==='create_product'&&c.payload.creative_context?.snapshot_id==='snap'));
 const resumed=await page.evaluate(()=>calls.filter(c=>c.action==='product_story_prepare').at(-1));
 assert.equal(resumed.payload.product_id,'JOB-SOURCE');assert.equal(resumed.payload.retry_capture,true);
 const resumedHandoff=await page.evaluate(()=>calls.filter(c=>c.action==='create_product'&&c.payload.creative_context?.snapshot_id==='snap').at(-1));
 assert.equal(resumedHandoff.payload.link,undefined);assert.equal(resumedHandoff.payload.provider,'gemini');
 assert.equal(resumedHandoff.payload.video_generation_mode,'meta_ai');assert.equal(resumedHandoff.payload.scene_count,6);
 assert.equal(resumedHandoff.payload.story_text,'ค่าที่บันทึกไว้');
 assert.deepEqual(resumedHandoff.payload.product_script_options,{version:2,style:'short_film_ad',genre:'warm',ending_cta:true});
 const app=fs.readFileSync('web_ui/app.js','utf8');
 const steps=app.slice(app.indexOf('function progressSteps('),app.indexOf('function minimizeProgress('));
 await page.addScriptTag({content:steps});
 const progress=await page.evaluate(()=>progressSteps('story',83,{stage:'scene',scene_index:2,scene_total:3,scenes_complete:1,scene_phase:'voice'}));
 assert.match(progress,/ครบ 1\/3 ฉาก/);assert.match(progress,/current[^>]*>ฉาก 2 • เสียง/);assert.doesNotMatch(progress,/done/);
 await page.fill('#cast-name','Model');await page.click('#cast-generate');
 await page.waitForFunction(()=>calls.some(c=>c.action==='product_cast_generate'));
 console.log('Product Story UI: cast selection, optional direction/count, frozen context, old-job bypass and image-only command passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
