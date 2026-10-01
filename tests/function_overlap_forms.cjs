// Native regression: load every current index script in its real order.
// Fetch is an in-page inert fixture; no live bridge, profile, provider or jobs.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const html=fs.readFileSync('web_ui/index.html','utf8');
const scripts=[...html.matchAll(/<script\b[^>]*src="([^"?]+)[^"]*"/g)].map(m=>path.basename(m[1]));
const group=process.argv[2]||'all';
let checks=0;
async function fixture(browser,earlyDefaults){
  const page=await browser.newPage(),errors=[],external=[],loaded=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
    window.fixtureCalls=[];window.fixturePaused=true;window.fixtureHoldAction=false;
    window.fetch=async(url,options={})=>{
      const value=String(url);
      if(value.includes('/api/desktop/state'))return new Promise(()=>{}); // explicit delayed hydration below
      if(value.includes('/api/membership/status'))return new Response(JSON.stringify({required:true,desktop:{allowed:true}}));
      if(value.includes('/api/desktop/action')){
        const sent=JSON.parse(options.body);fixtureCalls.push(sent);
        let result={ok:true};
        if(sent.action==='flow_settings_get')result.settings={};
        else if(sent.action==='green_status')Object.assign(result,{settings:{enabled:false,clips:[],opacity:.5,fit:'contain'},targets:{},assets:[]});
        else if(['intro_list','intro_status'].includes(sent.action))Object.assign(result,{settings:{file:'',enabled:false},targets:{},assets:[]});
        else if(sent.action==='product_cast_state')result.assets=[];
        else if(sent.action==='enqueue_long_video'){
          result={ok:true,queued:true,story_queue:{paused:fixturePaused}};
          if(fixtureHoldAction)await new Promise(resolve=>window.fixtureFinishAction=resolve);
        }else if(['create_story','enqueue_story_batch','create_drama_series'].includes(sent.action))result.job_id='STORY-FIXTURE';
        else if(!['presenter_list','presenter_settings','intro_status'].includes(sent.action))throw Error('Unexpected fixture action '+sent.action);
        return new Response(JSON.stringify(result));
      }
      // Read-only startup views; no credentials or actual service access.
      return new Response(JSON.stringify({ok:true,items:[],jobs:[],assets:[],settings:{},targets:{}}));
    };
  });
  await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.hostname!=='smartflow.test'){external.push(url.href);return route.abort();}
    if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
    const name=path.basename(url.pathname),file=path.join('web_ui',name);
    if(/\.(js|css)$/.test(name)&&fs.existsSync(file)){
      if(name.endsWith('.js'))loaded.push(name);
      let body=fs.readFileSync(file,'utf8');
      if(name==='app.js'&&typeof earlyDefaults==='boolean')body+=`;ui.state={settings:{provider:'chatgpt',subtitle_auto:${earlyDefaults}}};hydrateForms(ui.state);`;
      return route.fulfill({contentType:name.endsWith('.js')?'application/javascript':'text/css',body});
    }
    return route.fulfill({status:204,body:''});
  });
  await page.goto('http://smartflow.test/');
  await page.waitForFunction(()=>typeof window.storytellingModeFor==='function'&&typeof window.routeCreationQueue==='function');
  assert.deepEqual(errors,[],'all actual scripts initialize');
  assert.deepEqual([...loaded].sort(),[...scripts].sort(),'all current index scripts loaded');checks+=2;
  // Exercise the real confirmation controls against only this inert transport.
  await page.evaluate(()=>new MutationObserver(()=>{
    const dialog=document.querySelector('#generation-notice');
    if(dialog?.open)dialog.querySelector('[data-notice-start]').click();
  }).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']}));
  return {page,finish:async()=>{assert.deepEqual(errors,[]);assert.deepEqual(external,[]);checks+=2;await page.close();}};
}
async function hydrate(page,value){
  await page.evaluate(value=>{
    ui.state={settings:{provider:'chatgpt',subtitle_auto:value,video_resolution:'1080p',video_fps:30,video_quality:'high',motion_percent:5,transition_ms:500},system:{long_meta_landscape_available:true}};
    hydrateForms(ui.state);
  },value);
}
async function dialogue(browser){
  const f=await fixture(browser),{page}=f;
  for(const key of ['story','story-batch']){
    const old=page.locator(`[data-audio-form="${key}"] [data-actor-dialogue]`);
    assert.equal(await old.evaluate(n=>Boolean(n.closest('[hidden]'))),true,'legacy dialogue must be hidden independent of injected siblings');checks++;
  }
  await hydrate(page,true);
  for(const key of ['story','story-batch','drama']){
    await page.evaluate(key=>{const provider=document.getElementById(key+'-video-mode');provider.value='google_flow';provider.dispatchEvent(new Event('change'));},key);
    for(const mode of ['dialogue','solo','visual','narrator']){
      const state=await page.evaluate(({key,mode})=>{
        const modeInput=document.querySelector(`select[name="storytelling-${key}"]`);
        modeInput.value=mode;modeInput.dispatchEvent(new Event('change',{bubbles:true}));
        const panel=document.querySelector(`[data-audio-form="${key}"]`);
        if(['solo','dialogue'].includes(mode)){
          const subtitle=panel.querySelector('[data-audio-subtitle]');
          subtitle.checked=true;subtitle.dispatchEvent(new Event('change',{bubbles:true}));
        }
        const legacy=panel.querySelector('[data-actor-dialogue]');
        const before=mediaAudioChoice(key);
        if(legacy){legacy.checked=true;legacy.dispatchEvent(new Event('change',{bubbles:true}));}
        return {before,after:mediaAudioChoice(key),invalid:panel.querySelectorAll('[data-audio-mode]:checked:disabled').length};
      },{key,mode});
      assert.deepEqual(state.after,state.before,'hidden legacy adapter must not change new storytelling audio');
      assert.equal(state.invalid,0);checks+=2;
      if(['solo','dialogue'].includes(mode)){
        assert.equal(state.after.subtitle,true,'new speaking modes permit explicitly chosen subtitles');checks++;
      }
    }
  }
  await page.evaluate(()=>postAction('create_story',{job_id:'STORY-LEGACY',actor_dialogue:true}));
  assert.deepEqual(await page.evaluate(()=>fixtureCalls.at(-1).payload),{job_id:'STORY-LEGACY',actor_dialogue:true});checks++;
  await f.finish();
}
async function defaults(browser){
  for(const initial of [false,true]){
    const f=await fixture(browser),{page}=f;await hydrate(page,initial);
    for(const key of ['product','story','story-batch','drama','long']){
      assert.equal(await page.evaluate(key=>mediaAudioChoice(key).subtitle,key),initial,key+' first defaults');checks++;
    }
    // Product snapshot traverses the real decorators but stops before capture/generation.
    const product=await page.evaluate(()=>productOptionSnapshot.capture('create_product',{},postAction));
    assert.equal(product.payload.audio_choices.subtitle,initial);checks++;
    for(const [action,payload] of [['create_story',{topic:'Fixture',video_generation_mode:'image_motion'}],['enqueue_story_batch',{topics:['Fixture'],video_generation_mode:'image_motion'}],['create_drama_series',{characters:[],render_options:{video_generation_mode:'image_motion'}}],['enqueue_long_video',{topic:'Fixture',video_generation_mode:'image_motion',long_video:{version:2,duration_seconds:180}}]]){
      await page.evaluate(({action,payload})=>postAction(action,payload),{action,payload});
      assert.equal(await page.evaluate(()=>fixtureCalls.at(-1).payload.audio_choices.subtitle),initial,action+' payload');checks++;
    }
    await hydrate(page,!initial);
    assert.equal(await page.evaluate(()=>mediaAudioChoice('story').subtitle),initial,'poll/default changes must not overwrite initialized draft');checks++;
    await f.finish();
  }
  const f=await fixture(browser),{page}=f;
  await page.evaluate(()=>{
    const input=document.querySelector('[data-audio-form="story"] [data-audio-subtitle]');
    input.checked=false;input.dispatchEvent(new Event('change',{bubbles:true}));
    prepareAudioQueue({video_generation_mode:'google_flow',settings:{audio_choices:{mode:'api',subtitle:false}}});
    setMediaAudioChoice('drama',{mode:'api',subtitle:false});
  });
  await hydrate(page,true);
  for(const key of ['story','drama','product-batch']){assert.equal(await page.evaluate(key=>mediaAudioChoice(key).subtitle,key),false,'late defaults preserve user/saved '+key);checks++;}
  assert.equal(await page.evaluate(()=>mediaAudioChoice('long').subtitle),true);checks++;
  await f.finish();
  const early=await fixture(browser,false);
  for(const key of ['product','story','story-batch','drama','long']){assert.equal(await early.page.evaluate(key=>mediaAudioChoice(key).subtitle,key),false,'defaults available before module '+key);checks++;}
  await early.finish();
}
async function longQueue(browser){
  const f=await fixture(browser),{page}=f;await hydrate(page,false);
  for(const checked of [true,false])for(const route of ['main','secondary'])for(const paused of [true,false]){
    await page.evaluate(({checked,paused})=>{fixturePaused=paused;fixtureCalls.length=0;document.querySelector('#long-topic').value='Fixture';document.querySelector('#long-queue-only').checked=checked;}, {checked,paused});
    await page.evaluate(route=>route==='main'?submitLongVideo(false):[...document.querySelectorAll('[data-view="longvideo"] button')].find(b=>b.textContent==='เพิ่มลงคิว').click(),route);
    await page.waitForFunction(()=>!document.querySelector('#create-longvideo').disabled);
    const result=await page.evaluate(()=>({sent:fixtureCalls.find(c=>['create_story','enqueue_long_video'].includes(c.action)),message:document.querySelector('#long-status').textContent}));
    assert.equal(result.sent.action,checked||route==='secondary'?'enqueue_long_video':'create_story');
    assert.equal(result.sent.payload.queue_only===true,checked,'both Long buttons honor the same queue-only intent');checks+=2;
    if(route==='secondary'||checked){assert.match(result.message,checked||paused?/กดเริ่มคิว/:/ต่อท้ายคิว/);checks++;}
  }
  await page.evaluate(()=>{fixtureCalls.length=0;fixtureHoldAction=true;document.querySelector('#long-queue-only').checked=true;submitLongVideo(false);submitLongVideo(true);});
  await page.waitForFunction(()=>typeof fixtureFinishAction==='function');
  assert.equal(await page.evaluate(()=>fixtureCalls.filter(c=>c.action==='enqueue_long_video').length),1,'existing primary-button latch covers both buttons');checks++;
  await page.evaluate(()=>{fixtureFinishAction();fixtureHoldAction=false;});
  await page.waitForFunction(()=>!document.querySelector('#create-longvideo').disabled);
  await f.finish();
}
(async()=>{const browser=await chromium.launch({headless:true});let failed=false;
  try{for(const [name,run] of Object.entries({dialogue,defaults,long:longQueue}))if(group==='all'||group===name){try{await run(browser);console.log('PASS '+name);}catch(error){failed=true;console.error('FAIL '+name+': '+error.stack);}}}
  finally{await browser.close();}
  console.log(JSON.stringify({checks,indexScripts:scripts.length,externalRequests:0}));if(failed)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
