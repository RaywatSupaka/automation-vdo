// Real desktop markup/styles/controllers. No live bridge, Chrome profile or provider.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const html = read('web_ui/index.html').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; let requests = 0, checks = 0;
    page.on('pageerror', e => errors.push(e.message));
    const ok = (condition, message) => {assert(condition, message); checks++;};
    await page.route('**/*', route => {
      const req=route.request(),url=new URL(req.url());
      if(req.method()!=='GET' || url.hostname!=='smartflow.test'){requests++;return route.abort();}
      if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
      if(/^\/desktop\/[\w.-]+\.css$/.test(url.pathname))return route.fulfill({contentType:'text/css',body:read('web_ui/'+path.basename(url.pathname))});
      return route.abort();
    });
    await page.goto('http://smartflow.test/');
    await page.evaluate(() => {
      window.pageMeta={};window.ui={activePage:'products'};window.toast=()=>{};
      window.showPage = key => document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.view===key));
      showPage('products');window.calls=[];
      window.postAction=async (action,payload={})=>{
        calls.push({action,payload:JSON.parse(JSON.stringify(payload))});
        if(action==='flow_settings_get')return {ok:true,settings:{}};
        if(action==='intro_status')return {ok:true,settings:{enabled:false,file:''},assets:[],targets:{}};
        if(action==='green_status')return {ok:true,settings:{enabled:false,clips:[],opacity:.5,fit:'contain'},assets:[],targets:{}};
        return {ok:true,assets:[]};
      };
      const form=document.createElement('form');form.id='creation-form';form.innerHTML='<div class="cq-buttons"></div>';document.body.append(form);
    });
    for(const file of ['media_audio.js','flow_settings.js','ai_cover.js','video_intro.js','green_screen.js','product_story.js'])
      await page.addScriptTag({content:read('web_ui/'+file)});
    const values = () => page.evaluate(() => [...document.querySelectorAll('input,select,textarea')].map(el=>({id:el.id,type:el.type,value:el.value,checked:el.checked,disabled:el.disabled})));
    const before=await values();
    await page.evaluate(()=>{window.originalInputs=[...document.querySelectorAll('input')];window.changeEvents=0;document.addEventListener('change',()=>changeEvents++);});
    const payloads = async () => page.evaluate(async () => {
      const captured=[];
      for(const [action,payload] of [['create_product',{}],['create_story',{video_generation_mode:'google_flow'}],['enqueue_story_batch',{video_generation_mode:'google_flow'}],['create_drama_series',{render_options:{video_generation_mode:'google_flow'}}],['enqueue_long_video',{video_generation_mode:'google_flow'}],['creation_edit',{queue_id:'TEST'}],['create_product',{job_id:'OLD'}]]){
        await postAction(action,payload);captured.push(calls.at(-1));
      }
      return captured;
    });
    const oldPayloads=await payloads();
    await page.addScriptTag({content:read('web_ui/function_controls.js')});
    assert.deepEqual(await values(),before);checks++;
    assert.deepEqual(await payloads(),oldPayloads);checks+=7;
    ok(await page.evaluate(()=>changeEvents===0 && originalInputs.every(el=>el.isConnected)),'decoration preserves input identity and emits no changes');
    ok(await page.locator('.sf-function-row').count()>50,'all mounted creation/settings groups decorated');
    ok(await page.locator('#ps-film-cta').getAttribute('role')==='switch','film CTA switch');
    ok(await page.locator('#ps-story-first').getAttribute('type')==='radio','script styles remain native exclusive choices');
    for(const selector of ['#presenter-consent','#sp-queue-all','.media-audio-controls [data-audio-silent]'])
      ok(await page.locator(selector).first().getAttribute('role')!=='switch','selection/consent excluded: '+selector);
    const count=await page.locator('.sf-function-state').count();
    await page.addScriptTag({content:read('web_ui/function_controls.js')});
    await page.evaluate(()=>smartflowFunctionControls.enhance(document));
    ok(await page.locator('.sf-function-state').count()===count,'idempotent without duplicated state labels');
    const first=page.locator('#ps-use-cast'),row=first.locator('..');
    await row.locator('span').first().click();
    ok(await first.isChecked(),'whole label click selects once');
    ok(await page.evaluate(()=>changeEvents)===1,'no duplicate change handler');
    await first.focus();await page.keyboard.press('Space');
    ok(!(await first.isChecked()),'Space toggles native switch');
    ok(await row.evaluate(el=>getComputedStyle(el).outlineStyle)==='solid','visible keyboard focus');
    const status=()=>row.locator('.sf-function-state').evaluate(el=>getComputedStyle(el,'::before').content);
    await first.evaluate(el=>{el.checked=true;});
    ok((await status()).includes('เปิด'),'programmatic restore updates visual state without events');
    await first.evaluate(el=>{el.disabled=true;});
    const disabledBounds=await row.locator('span').first().boundingBox();
    await page.mouse.click(disabledBounds.x+10,disabledBounds.y+10);
    ok(await first.isChecked(),'disabled cannot toggle through label');
    await first.evaluate(el=>{el.disabled=false;});
    // Late posting rows and native mixed selection are independent of this enhancer.
    await page.evaluate(()=>{
      document.querySelector('#sp-queue').innerHTML='<label class="sp-switch"><input id="test-late-switch" type="checkbox" role="switch" data-option="ai_label"><span>เพิ่มป้ายกำกับ AI</span><strong>ปิด</strong></label>';
      document.querySelector('#sp-queue-all').indeterminate=true;
    });
    await page.waitForFunction(()=>document.querySelector('#test-late-switch').classList.contains('sf-function-input'));
    ok(await page.locator('#test-late-switch').locator('..').locator('.sf-function-state').count()===1,'dynamic row decoration');
    ok(await page.locator('#sp-queue-all').evaluate(el=>el.indeterminate&&!el.classList.contains('sf-function-input')),'mixed selection preserved');
    // All five model choices survive the display layer, not a convenient subset.
    const models=['Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]'];
    await page.locator('[data-view="products"] .flow-job-settings summary').click();
    const modelSelect=page.locator('[data-view="products"] [data-flow-field="model"]');
    for(const model of models){
      await modelSelect.selectOption(model);
      await page.evaluate(()=>postAction('create_product',{}));
      ok(await page.evaluate(()=>calls.at(-1).payload.flow_settings.model)===model,'model payload '+model);
    }
    const audio=page.locator('[data-view="products"] .media-audio-controls');
    await audio.locator('[data-audio-mode][value="flow_original"]').check();
    await audio.locator('[data-audio-music]').check();
    await page.evaluate(()=>postAction('create_product',{}));
    const choices=await page.evaluate(()=>calls.at(-1).payload.audio_choices);
    ok(choices.mode==='flow_original'&&choices.music,'native audio/music payload');
    await audio.locator('[data-audio-mode][value="api"]').focus();await page.keyboard.press('ArrowLeft');
    ok(await audio.locator('[data-audio-mode]:checked').count()===1,'radio keyboard exclusivity');
    await page.evaluate(()=>prepareAudioQueue({settings:{audio_choices:{mode:'none',subtitle:false,music:true,sfx:true}}}));
    await page.evaluate(()=>postAction('creation_edit',{queue_id:'TEST'}));
    const restored=await page.evaluate(()=>calls.at(-1).payload.audio_choices);
    ok(restored.mode==='none'&&restored.music&&restored.sfx&&!restored.subtitle,'queue restore preserves settings');
    await page.evaluate(()=>{showPage('story');const s=document.querySelector('#story-video-mode');s.value='google_flow';s.dispatchEvent(new Event('change'));});
    const storyAudio=page.locator('[data-view="story"] .media-audio-controls');
    await storyAudio.locator('[data-actor-dialogue]').check();
    ok(await storyAudio.locator('[data-audio-subtitle]').isDisabled()&&!(await storyAudio.locator('[data-audio-subtitle]').isChecked()),'dialogue keeps existing no-subtitle constraint');
    const shots=process.env.SF_FUNCTION_SCREENSHOTS;
    if(shots){
      fs.mkdirSync(shots,{recursive:true});
      // Component captures omit fixed app chrome; do not capture page-entry fades.
      await page.addStyleTag({content:'.topbar,.app-header{visibility:hidden!important}.page{animation:none!important}'});
    }
    await page.evaluate(()=>showPage('products'));
    await page.locator('#ps-short-film').check();
    for(const width of [1440,600,390]){
      await page.setViewportSize({width,height:1000});
      const planning=page.locator('.product-options').filter({has:page.locator('#ps-short-film')});
      ok(await planning.evaluate(el=>el.scrollWidth<=el.clientWidth+2),'film styles fit '+width);
      ok(await page.locator('[name="ps-script-style"]:checked').count()===1,'one script style '+width);
      if(shots)await planning.screenshot({path:path.join(shots,`short-film-${width}.png`),animations:'disabled'});
    }
    for(const width of [1440,1093,960,600,390]){
      await page.setViewportSize({width,height:1000});
      for(const key of ['products','story']){
        await page.evaluate(key=>showPage(key),key);
        const panel=page.locator(`[data-view="${key}"] .media-audio-controls`);
        const geometry=await panel.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth,rows:[...el.querySelectorAll('.sf-function-row')].filter(r=>r.getClientRects().length).map(r=>({width:r.clientWidth,scroll:r.scrollWidth,height:r.getBoundingClientRect().height}))}));
        ok(geometry.scroll<=geometry.width+2,`${key} ${width} no panel overflow`);
        ok(geometry.rows.every(r=>r.scroll<=r.width+2&&r.height>=44),`${key} ${width} switch rows fit with usable targets`);
        if(shots&&[1440,600,390].includes(width))await panel.screenshot({path:path.join(shots,`${key}-${width}.png`),animations:'disabled'});
      }
    }
    await page.emulateMedia({reducedMotion:'reduce'});
    ok(await storyAudio.locator('[data-actor-dialogue]').evaluate(el=>getComputedStyle(el,'::before').transitionDuration)==='0s','reduced motion');
    await page.setViewportSize({width:1440,height:1000});
    await page.evaluate(()=>showPage('queue'));
    // Posting is embedded in the queue page; capture only its settings component.
    if(shots){
      await page.locator('#shopee-posting').evaluate(el=>{for(let p=el;p;p=p.parentElement){if(p.classList.contains('page'))p.classList.add('active');}});
      await page.locator('#shopee-posting .sp-options-panel').screenshot({path:path.join(shots,'posting-options.png')});
    }
    assert.deepEqual(errors,[]);ok(requests===0,'zero external/backend write requests');
    console.log(JSON.stringify({ok:true,checks,models:models.length,externalRequests:requests,pageErrors:errors,installedE2E:false}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
