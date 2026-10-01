// Local HTML only. Executes the actual background handler and browser DOM reader.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const bg = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
const flow = fs.readFileSync(path.join(__dirname, '../browser_extension/flow.js'), 'utf8');
const part = (s,a,b) => s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)+a.length));
const handler = part(bg, '    if (message?.type === "CONFIGURE_FLOW_VIDEO_SETTINGS")', '    if (message?.type === "ATTACH_LATEST_FLOW_MEDIA")');
let cases = 0;
const selectorContext={};vm.createContext(selectorContext);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../browser_extension/flow_settings.js'),'utf8'),selectorContext);
const choose=selectorContext.SmartFlowSettings.selectProjectTab;
const projectOne={id:1,url:'https://flow.google.com/project/one'},projectTwo={id:2,url:'https://labs.google/fx/tools/flow/project/two'},extensions={id:3,url:'chrome://extensions/'};
assert.equal(choose([extensions],[projectOne]).id,1);cases++;
assert.equal(choose([projectTwo],[projectOne,projectTwo]).id,2);cases++;
assert.throws(()=>choose([extensions],[projectOne,projectTwo]),/หลายโปรเจกต์/);cases++;
assert.throws(()=>choose([],[{id:4,url:'https://flow.google.com/'}]),/เปิดโปรเจกต์/);cases++;
assert.throws(()=>choose([],[{id:5,url:'https://flow.google.com.attacker.test/project/one'}]),/เปิดโปรเจกต์/);cases++;
const group = (label, labels, active) => `<flow-toggles aria-label="${label}"><div role="radiogroup">${labels.map(text =>
  `<button role="radio" aria-checked="${text === active}"><mat-icon aria-hidden="true">${label === 'Aspect ratio' ? 'crop' : 'movie'}</mat-icon><span>${text}</span></button>`).join('')}</div></flow-toggles>`;
function html({mode='Video', aspect='16:9', count='x4', legacy=false}={}) {
  const modern = group('Mode',['Image','Video'],mode) + group('Video type',['Frames','Ingredients'],'Ingredients')
    + group('Aspect ratio',['16:9','9:16'],aspect)
    + '<button aria-label="Select model family">Omni 1.1 Flash<mat-icon>arrow_drop_down</mat-icon></button>'
    + group('Video resolution',['360p','720p'],'360p') + group('Video duration',['4s','6s','8s','10s'],'8s')
    + group('Output count',['x1','x2','x3','x4'],count) + '<p>Generating will use 6 credits</p>';
  const old = '<h2>Agent settings</h2><label><input id="never" type="radio" value="2" checked>Never</label>'
    + group('default aspect ratio for video',['16:9','9:16'],aspect)
    + group('default number of video outputs',['x1','x2','x3','x4'],count)
    + '<button id="save">Save</button><button id="back" aria-label="Back">Back</button>';
  return `<style>body{margin:0} .base-prompt-box{position:absolute;bottom:10px;width:95%}
    [contenteditable]{height:60px} button{min-width:48px;height:30px} flow-toggles{display:block;margin:4px}
    mat-icon{display:none} #panel{display:block;position:absolute;top:10px;left:10px;width:340px;background:white;z-index:2}
    #panel[hidden]{display:none} [role=radiogroup]{display:flex} h2{margin:4px}</style>
    <button id="global" aria-label="Settings">Settings</button><div class="base-prompt-box"><div contenteditable="true" role="textbox">owned draft</div><button id="settings" aria-label="Settings">Settings</button></div>
    <${legacy ? 'section' : 'flow-prompt-box-settings'} id="panel" hidden>${legacy ? old : modern}</${legacy ? 'section' : 'flow-prompt-box-settings'}>
    <script>window.clicks=[]; window.closeAllowed=true; window.paused=false;
      document.addEventListener('click', e=>{const b=e.target.closest('button');if(!b)return;window.clicks.push(b.id||b.textContent);
        if(b.id==='settings')document.querySelector('#panel').hidden=!document.querySelector('#panel').hidden;
        if(b.id==='back'&&window.closeAllowed)document.querySelector('#panel').hidden=true;
        if(b.getAttribute('role')==='radio'){b.closest('[role=radiogroup]').querySelectorAll('button').forEach(x=>x.setAttribute('aria-checked',String(x===b)));}
      });
      document.addEventListener('keydown',e=>{if(e.key==='Escape'&&window.closeAllowed)document.querySelector('#panel').hidden=true});</script>`;
}
async function run(page, aspect='9:16', requested={}, options={}) {
  const inputSession=await page.context().newCDPSession(page);
  const originalViewport=page.viewportSize(), events=options.events||[];
  const context = {
    message:{type:'CONFIGURE_FLOW_VIDEO_SETTINGS',aspect_ratio:aspect,flow_settings:requested,discovery:options.discovery===true,verify_only:options.verifyOnly===true,
      ...(options.plan ? {job_id:'STORY-PLAN',shot_index:1,run_id:'run',scene_video_plan:options.plan} : {})},sender:{tab:{id:1}},
    sendResponse:r=>{events.push('reply');context.result=r;}, setTimeout:fn=>fn(),
    BRIDGE:'http://fixture.invalid',crypto:require('node:crypto').webcrypto,
    flowRunStorageKey:(job,index)=>`run:${job}:${index}`,
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:{scene_video_plan:options.stalePlan ? {...options.plan,attempt_id:'stale'} : options.plan,flow_settings:requested}})}),
    chrome:{storage:{local:{get:async()=>({smartpostFlowPausedTabs:{1:await page.evaluate(()=>Boolean(window.paused))}})}},
      tabs:{get:async()=>({url:'https://flow.google.com/project/test'}),onUpdated:{addListener:()=>{}},onRemoved:{addListener:()=>{}},update:async()=>{}}, scripting:{executeScript:async({func,args})=>[{result:await page.evaluate(`(${func.toString()})(${JSON.stringify(args[0])})`)}]},
      debugger:{onDetach:{addListener:()=>{}},attach:async()=>{events.push('attach');if(options.attachFails)throw Error('ATTACH_FAILED');},detach:async()=>{events.push('detach');await page.setViewportSize(originalViewport);},sendCommand:async(_d,cmd,p)=>{
        events.push(cmd);
        if(cmd==='Emulation.setDeviceMetricsOverride'){await page.setViewportSize({width:p.width,height:p.height});if(options.overrideFails)throw Error('OVERRIDE_ACK_LOST');}
        if(cmd==='Emulation.clearDeviceMetricsOverride')await page.setViewportSize(originalViewport);
        if(cmd==='Input.dispatchMouseEvent'&&p.type==='mouseReleased') await page.mouse.click(p.x,p.y);
        if(cmd==='Input.dispatchKeyEvent') await inputSession.send(cmd,p);
      }}}
  };
  vm.createContext(context);
  vm.runInContext(part(bg,'function sceneVideoPlanMatches(', 'async function aiProgressOwnership('),context);
  vm.runInContext(part(bg,'function installFlowMobileDebugger(api)', 'let coverPolling'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../browser_extension/flow_settings.js'),'utf8'),context);
  try {
    await vm.runInContext(`(async()=>{${handler}})()`,context);
    return context.result;
  } finally { await inputSession.detach(); }
}
(async()=>{
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    await page.route('**/*',route=>route.abort()); // No network/provider access.
    for(const width of [400,1365]) for(const mode of ['Image','Video']) for(const aspect of ['9:16','16:9']) {
      await page.setViewportSize({width,height:802}); await page.setContent(html({mode}));
      const r = await run(page,aspect); assert.equal(r.ok,true,JSON.stringify(r)); assert.equal(r.videoAspect,aspect); assert.equal(r.videoOutputs,1);
      assert.equal(r.observed.model,'Omni 1.1 Flash'); assert.equal(r.observed.resolution,'360p'); assert.equal(r.observed.duration,'8s');
      assert.equal(r.observed.videoType,'Ingredients'); assert.equal(r.observed.creditNotice,'Generating will use 6 credits');
      assert.equal(await page.locator('[contenteditable]').innerText(),'owned draft');
      const clicked=await page.evaluate(()=>window.clicks); assert(!clicked.includes('global'));
      assert(!clicked.some(t=>/360p|720p|8s|Ingredients|Omni/.test(t))); cases++;
    }
    await page.setContent(html({aspect:'9:16',count:'x1'}));
    assert.equal((await run(page)).changed,false);cases++;
    await page.setContent(html());
    await page.locator('[role=radio]').filter({hasText:'9:16'}).evaluate(b=>b.disabled=true);
    assert.equal((await run(page)).error,'FLOW_VIDEO_SETTINGS_NOT_VERIFIED');cases++;
    await page.setContent(html());
    await page.evaluate(()=>{document.querySelector('#panel').hidden=false; const cover=document.createElement('div');cover.style='position:fixed;inset:0;z-index:99';document.body.appendChild(cover);});
    assert.equal((await run(page)).ok,false);assert.equal((await page.evaluate(()=>window.clicks)).length,0);cases++;
    await page.setContent('<p>No settings</p>');assert.equal((await run(page)).error,'FLOW_VIDEO_SETTINGS_BUTTON_MISSING');cases++;
    await page.setContent(html());
    await page.evaluate(()=>document.querySelector('#settings').addEventListener('keydown',e=>e.preventDefault()));
    assert.equal((await run(page,'9:16',{model:'Omni 1.1 Flash',resolution:'720p',duration:'10s'})).error,'FLOW_SETTINGS_OPEN_NOT_VERIFIED');cases++;
    await page.setContent(html({aspect:'9:16',count:'x1'}));
    await page.evaluate(()=>{document.querySelector('#panel').hidden=false;document.querySelector('#settings').remove();window.closeAllowed=false;});
    assert.equal((await run(page)).error,'FLOW_VIDEO_SETTINGS_NOT_CLOSED');cases++;
    await page.setContent(html({legacy:true}));assert.equal((await run(page)).ok,true);cases++;
    await page.setContent(html());await page.evaluate(()=>window.paused=true);
    await assert.rejects(()=>run(page),/FLOW_PAUSED/);assert.equal((await page.evaluate(()=>window.clicks)).length,0);cases++;
    // Mobile viewport persists after settings and errors; no automatic clear.
    for (const width of [1365,400]) {
      await page.setViewportSize({width,height:802});await page.setContent(html());const events=[];
      const r=await run(page,'9:16',{display:'compact'},{events});assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(page.viewportSize().width,400);assert.equal(events.at(-1),'reply');
      assert(events.includes('Input.dispatchKeyEvent'));assert(!events.includes('Input.dispatchMouseEvent'));
      assert.equal(events.includes('Emulation.clearDeviceMetricsOverride'),false);cases++;
    }
    await page.setViewportSize({width:1365,height:802});await page.setContent('<p>No settings</p>');
    {const events=[];const r=await run(page,'9:16',{display:'compact'},{events});assert.equal(r.ok,false);assert.equal(page.viewportSize().width,400);assert(!events.includes('detach'));cases++;}
    await page.setContent(html());await page.evaluate(()=>window.paused=true);
    {const events=[];await assert.rejects(()=>run(page,'9:16',{display:'compact'},{events}),/FLOW_PAUSED/);assert.equal(events.length,0);cases++;}
    await page.setContent(html());
    {const events=[];await assert.rejects(()=>run(page,'9:16',{display:'compact'},{events,attachFails:true}),/ATTACH_FAILED/);assert.deepEqual(events,['attach']);cases++;}
    {const events=[];await assert.rejects(()=>run(page,'9:16',{display:'compact'},{events,overrideFails:true}),/OVERRIDE_ACK_LOST/);assert.equal(events.at(-1),'detach');assert(!events.includes('reply'));cases++;}
    for(const initiallyOpen of [true,false]) {
      await page.setContent(html());await page.evaluate(open=>document.querySelector('#panel').hidden=!open,initiallyOpen);
      const r=await run(page,'9:16',{display:'compact'},{discovery:true});assert.equal(r.ok,true,JSON.stringify(r));
      assert.equal(r.capabilities.context.aspect_ratio,'16:9');assert.equal(r.capabilities.selected.video_type,'Ingredients');
      assert.equal(r.capabilities.model_menu_open,false);
      assert.equal(await page.locator('#panel').isVisible(),initiallyOpen);assert.equal(page.viewportSize().width,400);
      assert.equal(await page.locator('[contenteditable]').innerText(),'owned draft');cases++;
    }
    // Verify-only must never repair an unexpected setting and proceed to Send.
    await page.setContent(html({aspect:'9:16',count:'x1'}));
    {const r=await run(page,'9:16',{model:'Omni 1.1 Flash',resolution:'720p'},{verifyOnly:true});
      assert.equal(r.error,'FLOW_REQUESTED_SETTINGS_RESET');
      assert(!(await page.evaluate(()=>window.clicks)).some(label=>label==='720p'));cases++;}
    await page.setContent(html({aspect:'9:16',count:'x1'}));
    {const events=[],plan={version:1,scene_index:1,plan_revision:1,selection_id:'s',attempt_id:'a',provider:'google_flow',settings_sha256:'a'.repeat(64)};
      await assert.rejects(()=>run(page,'9:16',{}, {plan,stalePlan:true,events}),/FLOW_SCENE_PLAN_STALE/);
      assert.equal(events.length,0);assert.equal((await page.evaluate(()=>window.clicks)).length,0);cases++;}
    // The actual document watch survives composer edits, but rejects a settings
    // change, a reopened menu, a different token, and reuse after consumption.
    await page.setContent(html({aspect:'9:16',count:'x1'}));
    await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../browser_extension/flow_settings.js'),'utf8')});
    assert.equal(await page.evaluate(()=>SmartFlowSettings.watch('exact')),true);
    await page.locator('[contenteditable]').fill('owned draft, still unsent');
    assert.equal(await page.evaluate(()=>SmartFlowSettings.checkWatch('exact')),true);
    assert.equal(await page.evaluate(()=>SmartFlowSettings.checkWatch('other')),false);
    await page.evaluate(()=>document.querySelector('#panel [role="radio"]').setAttribute('aria-checked','false'));
    assert.equal(await page.evaluate(()=>SmartFlowSettings.checkWatch('exact')),false);cases++;
    await page.evaluate(()=>SmartFlowSettings.watch('new'));
    assert.equal(await page.evaluate(()=>SmartFlowSettings.checkWatch('new',true)),true);
    assert.equal(await page.evaluate(()=>SmartFlowSettings.checkWatch('new')),false);cases++;
    for (const width of [400,1365]) {
      await page.setViewportSize({width,height:802});await page.setContent(html());
      const supplied=fs.readFileSync(path.join(__dirname,'fixtures/flow_settings_compact.html'),'utf8');
      await page.evaluate(markup=>{
        document.querySelector('#panel').outerHTML=markup;
        document.querySelector('flow-prompt-box-settings').id='panel';
      },supplied);
      const r=await run(page);assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.observed.model,'Omni 1.1 Flash');
      assert.equal(r.observed.creditNotice,'Generating will use 6 credits');cases++;
    }
    // Caller must not proceed on failed settings; success reports observed values.
    const source=part(flow,'  async function ensureFlowVideoSettings(', '  async function attachExistingMediaToPrompt()');
    for(const ok of [true,false]) {
      const calls=[];const c={pkg:{aspect_ratio:'9:16'},uploadDebug:null,promptHasAttachedMedia:()=>true,
        chrome:{runtime:{sendMessage:async()=>({ok,error:'fixture',observed:{resolution:'360p'}})}},report:async(...a)=>calls.push(a)};
      vm.createContext(c);vm.runInContext(source,c);
      if(ok){assert.equal(await c.ensureFlowVideoSettings(),true);assert(calls[0][1].includes('360p'));}
      else{await assert.rejects(()=>c.ensureFlowVideoSettings(),/FLOW_VIDEO_SETTINGS_REVIEW/);assert.equal(calls[0][2].failure_code,'FLOW_VIDEO_SETTINGS_REVIEW');}
      cases++;
    }
    for(const width of [400,1365]) {
      await page.setViewportSize({width,height:802});await page.setContent(html());
      const r=await run(page,'9:16',{model:'Omni 1.1 Flash',video_type:'Frames',resolution:'720p',duration:'4s'});
      assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.observed.resolution,'720p');assert.equal(r.observed.duration,'4s');assert.equal(r.observed.videoType,'Frames');cases++;
    }
    for(const requested of [{resolution:'1080p'},{model:'Unknown expensive model'},{duration:'90s'}]){
      await page.setContent(html());const r=await run(page,'9:16',requested);assert.equal(r.error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');cases++;
    }
    await page.setContent(html());
    await page.evaluate(()=>{
      const button=document.querySelector('[aria-label="Select model family"]');button.setAttribute('aria-controls','models');
      const menu=document.createElement('div');menu.id='models';menu.role='listbox';menu.hidden=true;menu.innerHTML='<button role="option">Observed second model</button>';document.querySelector('#panel').append(menu);
      button.addEventListener('click',()=>menu.hidden=false);
      menu.querySelector('button').addEventListener('click',()=>{button.textContent='Observed second model';menu.hidden=true;for(const [label,choice] of [['Video resolution','360p'],['Video duration','8s']])document.querySelector(`flow-toggles[aria-label="${label}"]`).querySelectorAll('button').forEach(b=>b.setAttribute('aria-checked',String(b.textContent.includes(choice))));});
    });
    const switched=await run(page,'9:16',{model:'Observed second model',resolution:'720p',duration:'4s'});
    assert.equal(switched.ok,true,JSON.stringify(switched));assert.equal(switched.observed.model,'Observed second model');assert.equal(switched.observed.duration,'4s');cases++;
    await page.setContent(html());assert.equal((await run(page,'9:16',{outputs:4})).error,'FLOW_REQUESTED_SETTINGS_INVALID');assert.deepEqual(await page.evaluate(()=>window.clicks),[]);cases++;
    await page.setContent(html());await page.locator('[role=radio]').filter({hasText:'720p'}).evaluate(e=>e.disabled=true);
    assert.equal((await run(page,'9:16',{resolution:'720p'})).error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');cases++;
    await page.setContent(html());
    await page.evaluate(()=>document.addEventListener('click',e=>{if(e.target.closest('button')?.textContent.includes('x1')){const g=document.querySelector('flow-toggles[aria-label="Video resolution"]');g.querySelectorAll('button').forEach(b=>b.setAttribute('aria-checked',String(b.textContent.includes('360p'))));}}));
    assert.equal((await run(page,'9:16',{resolution:'720p'})).error,'FLOW_REQUESTED_SETTINGS_RESET');cases++;
    await page.setContent(html({legacy:true}));assert.equal((await run(page,'9:16',{resolution:'720p'})).error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');cases++;
    await page.setContent(html());await page.evaluate(()=>document.querySelector('#panel').hidden=false);
    await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'../browser_extension/flow_settings.js'),'utf8')});
    const observed=await page.evaluate(()=>SmartFlowSettings.read());assert.deepEqual(observed.resolution,['360p','720p']);assert.deepEqual(observed.model,['Omni 1.1 Flash']);assert.deepEqual(await page.evaluate(()=>window.clicks),[]);cases++;
    // Live Thai labels: actual settings trigger, translated groups and menu.
    await page.setViewportSize({width:1365,height:802});await page.setContent(html());
    await page.evaluate(()=>{
      document.addEventListener('click',event=>{
        const button=event.target.closest('[aria-label="Select model family"]');if(!button)return;
        button.setAttribute('aria-controls','model-291');
        const menu=document.createElement('div');menu.id='model-291';menu.setAttribute('role','menu');
        menu.style='position:fixed;top:40px;right:0;width:250px;z-index:100;background:white';
        menu.innerHTML='<button role="menuitem">Omni 1.1 Flash</button><button role="menuitem">Veo 3.1 - Fast</button>';
        document.body.append(menu);
      });
      document.addEventListener('keydown',event=>{
        if(event.key==='Escape'&&document.querySelector('#model-291')){document.querySelector('#model-291').remove();event.stopImmediatePropagation();}
      },true);
    });
    const discovery=await run(page,'9:16',{display:'compact'},{discovery:true});
    assert.equal(discovery.ok,true,JSON.stringify(discovery));assert.deepEqual(Array.from(discovery.capabilities.model),['Omni 1.1 Flash','Veo 3.1 - Fast']);
    assert.equal(await page.locator('#model-291').count(),0);assert.equal(await page.locator('#panel').isVisible(),false);cases++;
    const thaiMarkup=()=>html().replace('id="settings" aria-label="Settings"','id="settings" aria-label="ทริกเกอร์การตั้งค่า"')
      .replaceAll('Select model family','เลือกกลุ่มผลิตภัณฑ์โมเดล')
      .replaceAll('Video type','ประเภทวิดีโอ').replaceAll('Video resolution','ความละเอียดของวิดีโอ')
      .replaceAll('Video duration','ระยะเวลาของวิดีโอ').replaceAll('Frames','เฟรม').replaceAll('Ingredients','องค์ประกอบ')
      .replaceAll('Generating will use 6 credits','การสร้างจะใช้ 6 เครดิต')
      .replace(/([468]|10)s/g,'$1 วินาที');
    await page.setContent(thaiMarkup());
    const thai=await run(page,'16:9',{model:'Omni 1.1 Flash',video_type:'Frames',resolution:'720p',duration:'4s'});
    assert.equal(thai.ok,true,JSON.stringify(thai));assert.equal(thai.observed.duration,'4s');assert.equal(thai.observed.videoType,'Frames');cases++;
    await page.setContent(thaiMarkup());
    await page.evaluate(()=>{
      document.querySelector('[aria-label="ความละเอียดของวิดีโอ"]').remove();
      document.querySelector('#settings').innerText='วิดีโอ · 720p · 8 วินาที';
    });
    assert.equal((await run(page,'9:16',{resolution:'720p'})).ok,true);cases++;
    assert.equal((await run(page,'9:16',{resolution:'360p'})).error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');cases++;
    // The saved Lower Priority model is a distinct choice. A new Lite option
    // must not silently replace it while Google has removed the old tier.
    await page.setContent(thaiMarkup());
    await page.evaluate(()=>{
      const modelButton=document.querySelector('[aria-label="เลือกกลุ่มผลิตภัณฑ์โมเดล"]');
      document.addEventListener('click',event=>{
        const button=event.target.closest('button');if(!button)return;
        if(button===modelButton){
          modelButton.setAttribute('aria-controls','lite-menu');
          const menu=document.createElement('div');menu.id='lite-menu';menu.setAttribute('role','menu');
          menu.style='position:fixed;top:0;right:0;width:250px;z-index:100;background:white';
          menu.innerHTML='<button role="menuitem">Veo 3.1 - Lite</button><button role="menuitem">Veo 3.1 - Fast</button>';
          document.body.append(menu);
        }else if(button.closest('#lite-menu')){
          modelButton.textContent=button.textContent;button.closest('#lite-menu').remove();
        }
      });
    });
    const missingLowerPriority=await run(page,'9:16',{model:'Veo 3.1 - Lite [Lower Priority]'});
    assert.equal(missingLowerPriority.error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');
    assert.equal((await page.evaluate(()=>window.clicks)).includes('Veo 3.1 - Lite'),false);cases++;
    await page.setContent(thaiMarkup());
    await page.evaluate(()=>document.querySelector('[aria-label="ความละเอียดของวิดีโอ"] [aria-checked="true"]').disabled=true);
    assert.equal((await run(page,'9:16',{resolution:'360p'})).error,'FLOW_REQUESTED_SETTING_UNAVAILABLE');cases++;
    const fiveModels=['Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]'];
    for(const width of [400,1365])for(const model of fiveModels){
      await page.setViewportSize({width,height:802});await page.setContent(thaiMarkup());
      await page.evaluate(models=>{
        const modelButton=document.querySelector('[aria-label="เลือกกลุ่มผลิตภัณฑ์โมเดล"]');
        const resolution=document.querySelector('[aria-label="ความละเอียดของวิดีโอ"]').cloneNode(true);
        const duration=document.querySelector('[aria-label="ระยะเวลาของวิดีโอ"]');
        const longRadio=[...duration.querySelectorAll('[role=radio]')].find(x=>x.textContent.includes('10 วินาที')).cloneNode(true);
        document.addEventListener('click',event=>{
          const button=event.target.closest('button');if(!button)return;
          if(button===modelButton){
            modelButton.setAttribute('aria-controls','five-model-menu');
            const menu=document.createElement('div');menu.id='five-model-menu';menu.setAttribute('role','menu');
            menu.style='position:fixed;top:0;right:0;width:270px;z-index:100;background:white';
            for(const name of models){const option=document.createElement('button');option.setAttribute('role','menuitem');option.textContent=name;menu.append(option);}
            document.body.append(menu);
          }else if(button.closest('#five-model-menu')){
            const name=button.textContent;modelButton.textContent=name;button.closest('#five-model-menu').remove();
            document.querySelector('[aria-label="ความละเอียดของวิดีโอ"]')?.remove();
            [...duration.querySelectorAll('[role=radio]')].find(x=>x.textContent.includes('10 วินาที'))?.remove();
            if(name==='Omni 1.1 Flash'){duration.before(resolution.cloneNode(true));duration.querySelector('[role=radiogroup]').append(longRadio.cloneNode(true));}
            document.querySelector('#settings').textContent='วิดีโอ · '+(name==='Omni 1.1 Flash'?'360p':'720p')+' · 8 วินาที';
          }
        });
      },fiveModels);
      const result=await run(page,'9:16',{display:'compact',model,video_type:'Ingredients',resolution:'720p',duration:'6s'});
      assert.equal(result.ok,true,JSON.stringify(result));assert.equal(result.observed.model,model);
      assert.equal(result.observed.resolution,'720p');assert.equal(result.observed.duration,'6s');
      assert.equal(await page.locator('[contenteditable]').innerText(),'owned draft');cases++;
    }
    console.log(JSON.stringify({ok:true,cases}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
