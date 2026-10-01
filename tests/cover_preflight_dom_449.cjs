// Native Chromium DOM, actual production readiness/parsers/tool helpers.
// All network is intercepted. Only time and the local preparation-event bridge
// are simulated; this fixture cannot upload media or send a provider request.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SMARTFLOW_TEST_PLAYWRIGHT_PACKAGE||'playwright');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'browser_extension/chatgpt.js'),'utf8');
const part=(start,end)=>{
  const from=source.indexOf(start),to=source.indexOf(end,from+start.length);
  assert(from>=0&&to>from,`production helper exists: ${start}`);return source.slice(from,to);
};
const optional=name=>{
  const marker=`  function ${name}(`,from=source.indexOf(marker);
  if(from<0)return '';
  const tail=source.slice(from+marker.length),next=tail.search(/\n  (?:async )?function /);
  assert(next>=0,`production helper boundary: ${name}`);return source.slice(from,from+marker.length+next);
};
const production=[
  part('  function visible(', '  const dismissedDiscoveryCards'),
  part('  function composer(', '  async function waitForComposer('),
  part('  function chatGPTConversationFrames(', '  function lastUserTurnSignature('),
  part('  function composerText(', '  function explicitAnalysisRefusal('),
  part('  function isStopGenerationButton(', '  function imageGenerationSignature('),
  part('  function assertNotCancelled(', '  async function setComposerText('),
  part('  function chatGPTComposerAttachmentState(', '  function sourceAttachmentPreviews('),
  part('  function chatGPTImageToolChip(', '  async function submitImagePrompt('),
  optional('coverPreparationSnapshot'),
  part('  async function prepareCoverImageTool(', '  async function collectCoverImage(')
].join('\n');
let checks=0;const eq=(actual,expected,message)=>{assert.deepEqual(actual,expected,message);checks++;};
const pixel='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/m8cAAAAASUVORK5CYII=';
async function fixture(page,config={}){
  await page.goto('https://chatgpt.com/');
  await page.addScriptTag({content:`
    let IS_GEMINI=false,AI_NAME='ChatGPT Web',PROVIDER_KEY='chatgpt';
    let cancelRequested=false,stopProviderOnCancel=false,activeCoverRequest=null;
    const fixture={clock:0,events:[],messages:[],opens:0,choices:0,stopClicks:0,sleeps:0,config:${JSON.stringify(config)}};
    Date.now=()=>fixture.clock;
    const request={request_id:'449'.repeat(10)+'aa',preparation_id:'owner-449',preparation_attempt:0};
    activeCoverRequest=request;
    const coverEvent=async event=>{
      fixture.events.push(structuredClone(event));
      if(event.preparation_state?.reason==='ready'){
        if(fixture.config.draftDuringReadyAck)document.querySelector('#prompt-textarea').textContent='Human draft';
        if(fixture.config.ownerDuringReadyAck)activeCoverRequest={...request};
        if(fixture.config.remountDuringReadyAck&&!fixture.readyRemounted){fixture.readyRemounted=true;mountComposer();}
      }
      return {phase:event.phase};
    };
    const report=async()=>{};
    globalThis.chrome={runtime:{sendMessage:async message=>{
      fixture.messages.push(structuredClone(message));
      if(message.type!=='RESTART_AI_COVER_PREPARATION')throw Error('fixture forbids provider/network dispatch');
      return {ok:true};
    }}};
    const markup='<form data-chatgpt-composer style="width:500px;min-height:100px"><button type="button" data-composer-navigation-target="add-context" aria-label="เพิ่มไฟล์และอื่นๆ" aria-expanded="false">Tools</button><div id="prompt-textarea" contenteditable="true" style="width:400px;min-height:40px"></div></form>';
    const addChip=()=>{
      const button=document.createElement('button');button.type='button';button.setAttribute('aria-label','Remove Create image');
      button.textContent='Create image';document.querySelector('form').append(button);
    };
    const mountComposer=()=>{
      document.querySelector('form')?.remove();document.querySelector('#composer-host').innerHTML=markup;
      const opener=document.querySelector('[data-composer-navigation-target]');
      opener.disabled=Boolean(fixture.config.disabled);
      opener.onclick=()=>{
        fixture.opens++;opener.setAttribute('aria-expanded','true');
        const option=document.createElement('button');option.type='button';option.setAttribute('role','menuitem');option.textContent='Create image';
        option.onclick=()=>{fixture.choices++;option.remove();addChip();};document.body.append(option);
      };
    };
    const sleep=async ms=>{
      fixture.clock+=ms;if(++fixture.sleeps>1000)throw Error('fixture passive-wait bound exceeded');
      const c=fixture.config;
      if(c.hydrateAt&&fixture.clock>=c.hydrateAt&&!fixture.hydrated){fixture.hydrated=true;fixture.config.disabled=false;mountComposer();}
      if(c.remountAt&&fixture.clock>=c.remountAt&&!fixture.remounted){fixture.remounted=true;fixture.config.disabled=false;mountComposer();}
      if(c.removeAt&&fixture.clock>=c.removeAt&&!fixture.removed){fixture.removed=true;document.querySelector('form')?.remove();}
      if(c.draftAt&&fixture.clock>=c.draftAt)document.querySelector('#prompt-textarea').textContent='Human draft';
      if(c.foreignAt&&fixture.clock>=c.foreignAt)activeCoverRequest={...request};
      if(c.cancelAt&&fixture.clock>=c.cancelAt)cancelRequested=true;
    };
    document.body.innerHTML='<aside id="outside"></aside><main id="conversation"></main><div id="composer-host"></div>';
    if(!fixture.config.noComposer)mountComposer();
    ${production}
    async function inspectPreparation(){
      try{await prepareCoverImageTool(request,'cover fixture',0);return {ok:true};}
      catch(error){return {ok:false,code:error.code||'',reason:error.coverPreparationState?.reason||error.toolReason||'',
        handoff:!!error.coverPreparationHandoff,message:error.message,name:error.name};}
    }
  `});
  await page.evaluate(({config,pixel})=>{
    const outside=document.querySelector('#outside'),form=document.querySelector('form'),conversation=document.querySelector('#conversation');
    if(config.avatar)outside.innerHTML+=`<img alt="Account avatar" width="24" height="24" src="${pixel}">`;
    if(config.globalBusy)outside.innerHTML+='<div role="progressbar" style="width:100px;height:20px">Loading navigation</div>';
    if(config.hiddenStatus)form.insertAdjacentHTML('beforeend','<span hidden>upload failed</span><div style="display:none" aria-busy="true">uploading</div>');
    if(config.uploadBusy)form.insertAdjacentHTML('beforeend','<div role="progressbar" style="width:100px;height:20px">Uploading</div>');
    if(config.uploadFailed)form.insertAdjacentHTML('beforeend','<div role="alert" style="width:100px;height:20px">upload failed</div>');
    if(config.attachment)form.insertAdjacentHTML('beforeend',`<div data-testid="attachment" style="width:80px;height:80px"><img width="32" height="32" src="${pixel}"></div>`);
    if(config.draft)document.querySelector('#prompt-textarea').textContent='Human draft';
    if(config.user)conversation.innerHTML='<div data-chatgpt-search-unit-key="native:0:user"><div data-user-message-bubble="true">Prior user</div></div>';
    if(config.assistant)conversation.innerHTML='<div data-chatgpt-search-unit-key="native:1:assistant"><div data-markdown-text-style="assistant-message">Prior answer</div></div>';
    if(config.stop){const stop=document.createElement('button');stop.type='button';stop.setAttribute('aria-label','Stop generating');stop.textContent='Stop';stop.onclick=()=>fixture.stopClicks++;document.body.append(stop);}
    if(config.foreignOwner)activeCoverRequest={...request};
  },{config,pixel});
  return {
    run:()=>page.evaluate(()=>inspectPreparation()),
    state:()=>page.evaluate(()=>({clock:fixture.clock,opens:fixture.opens,choices:fixture.choices,stopClicks:fixture.stopClicks,
      events:fixture.events,messages:fixture.messages,users:userTurns().length,assistants:assistantTurns().length,
      draft:composerText(composer()),chip:!!chatGPTImageToolChip()})),
    snapshot:()=>page.evaluate(()=>typeof coverPreparationSnapshot==='function'?coverPreparationSnapshot(request):null)
  };
}
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.SMARTFLOW_TEST_CHROMIUM||undefined});
  try{
    const page=await browser.newPage();
    let networkRequests=0;
    await page.route('**/*',route=>{
      if(route.request().isNavigationRequest()&&route.request().url()==='https://chatgpt.com/')
        return route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'});
      networkRequests++;return route.abort();
    });
    let f=await fixture(page,{noComposer:true,avatar:true,globalBusy:true,hydrateAt:500});
    const initial=await f.run();
    if(process.argv.includes('--reproduce-448')){
      eq(initial.reason,'owner_changed','448 falsely treats unrelated Home DOM during hydration as changed owner');
      eq((await f.state()).clock,0,'initial preflight bypasses image-tool passive hydration');
      console.log(JSON.stringify({ok:true,reproduced:'448 initial false owner_changed',checks,result:initial,state:await f.state()}));return;
    }
    eq(initial.ok,true,'empty Home must wait for composer; global avatar/spinner cannot become attachments');
    let state=await f.state();eq(state.clock,500,'same preparation waits for hydration');eq(state.choices,1,'choose image tool once');eq(state.messages,[],'hydrated Home does not refresh');
    for(const config of [{},{avatar:true,globalBusy:true},{hiddenStatus:true}]){
      f=await fixture(page,config);eq((await f.run()).ok,true,'hydrated scoped composer is usable');
      state=await f.state();eq(state.choices,1);eq(state.stopClicks,0);eq(state.messages,[]);
    }
    f=await fixture(page,{disabled:true,avatar:true,globalBusy:true,removeAt:250,hydrateAt:750});
    eq((await f.run()).ok,true,'form unmount/remount passively retains same owner');state=await f.state();eq(state.clock,750);eq(state.choices,1);
    f=await fixture(page,{disabled:true,remountAt:250});eq((await f.run()).ok,true);eq((await f.state()).choices,1,'remounted form binds its own opener once');
    for(const [config,reason] of [
      [{attachment:true},'attachment_present'],[{uploadBusy:true},'upload_busy'],[{uploadFailed:true},'upload_failed'],
      [{draft:true},'draft_changed'],[{user:true},'conversation_not_empty'],[{assistant:true},'conversation_not_empty'],
      [{stop:true},'response_active'],[{foreignOwner:true},'owner_changed']
    ]){
      f=await fixture(page,config);const result=await f.run();eq(result.reason,reason,'guard reports the exact actual DOM blocker');
      state=await f.state();eq(state.choices,0,'guard never selects the tool');eq(state.messages,[],'guard never authorizes refresh');eq(state.stopClicks,0,'guard never Stops provider');
      if(config.draft)eq(state.draft,'Human draft','human draft remains intact');
    }
    for(const [config,reason] of [[{disabled:true,draftAt:250},'draft_changed'],[{disabled:true,foreignAt:250},'owner_changed']]){
      f=await fixture(page,config);eq((await f.run()).reason,reason,'guard is rechecked during tool hydration');eq((await f.state()).messages,[]);
    }
    for(const [config,reason] of [[{draftDuringReadyAck:true},'draft_changed'],[{ownerDuringReadyAck:true},'owner_changed']]){
      f=await fixture(page,config);eq((await f.run()).reason,reason,'preparation rechecks page/owner after awaiting its ready-event ACK');
      state=await f.state();eq(state.messages,[]);if(config.draftDuringReadyAck)eq(state.draft,'Human draft');
    }
    f=await fixture(page,{remountDuringReadyAck:true});
    eq((await f.run()).ok,true,'a once-remounted empty form can be prepared passively');
    eq((await f.state()).chip,true,'the current form must retain selected-tool proof at return, including after ready-event ACK');
    f=await fixture(page,{noComposer:true,avatar:true,globalBusy:true});
    eq((await f.run()).handoff,true,'permanently unhydrated but owned Home reaches bounded refresh handoff');
    state=await f.state();eq(state.messages.length,1);eq(state.messages[0].type,'RESTART_AI_COVER_PREPARATION');eq(state.messages[0].attempt,2);eq(state.choices,0);assert(state.clock>=60000);checks++;
    f=await fixture(page,{disabled:true,cancelAt:250});eq((await f.run()).name,'AbortError');eq((await f.state()).messages,[]);
    eq(networkRequests,0,'fixture never sends provider network requests');
    console.log(JSON.stringify({ok:true,checks,networkRequests,nativeDom:true}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
