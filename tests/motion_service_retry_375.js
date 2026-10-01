const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),{webcrypto:crypto}=require('crypto');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8'),background=fs.readFileSync('browser_extension/background.js','utf8');
const part=(s,a,b)=>{const i=s.indexOf(a),j=s.indexOf(b,i+a.length);assert(i>=0&&j>i,a);return s.slice(i,j);};
const helpers=part(source,'  function chatGPTConversationFrames(', '  function assistantTurns(')
  +part(source,'  function chatGPTServiceErrorContainer(', '  function extractMotionJson(');
const bgCode=part(background,'const chatGPTMotionServiceRetryLocks =','const chatGPTStoryResultRefreshLocks =');
const request='Text-only motion planning for scene eight. Return the original context and prompt as JSON.';
const context={job_id:'STORY-375',index:8,context_id:'context-eight'};
const url='https://chatgpt.com/c/fixture';
let cases=0;
function backend(options={}){
 const store=options.store||{},events=[],message={provider:'chatgpt',job_id:context.job_id,run_id:'RUN-375',index:8,
  context_id:context.context_id,request,owner_id:'message-eight',signature:'abcd1234',conversation_url:url};
 let reads=0,clicked=0;
 const c=vm.createContext({crypto,TextEncoder,BRIDGE:'offline',
  assertStoryCheckpointOwner:async()=>{if(options.owner)throw Error('owner');},
  chrome:{storage:{local:{get:async key=>({[key]:options.lostClaim?null:store[key]}),set:async row=>{events.push('persist');Object.assign(store,row);}}},
   tabs:{get:async()=>({id:9,url:options.url?'https://chatgpt.com/c/other':url}),
    sendMessage:async(_id,m)=>{events.push(m.type);
     if(m.type.startsWith('CLICK')&&options.lateGuard)return {ok:true,allowed:false};
     if(m.type.startsWith('CLICK')){clicked++;if(options.lostAck)throw Error('lost ACK');}
     return {ok:true,allowed:!options.guard,challenge:m.challenge,signature:m.signature};}}},
  bridgeFetch:async()=>{reads++;return {ok:true,json:async()=>({ok:true,context:{context_id:options.context?'other':context.context_id},
   record:{phase:options.phase||(options.lateSaved&&reads>1?'ready':'requested'),request:options.request?'other':request,
    conversation_url:options.savedUrl?'https://chatgpt.com/c/other':url}})};}});
 vm.runInContext(bgCode,c);
 return {c,events,store,message,clicks:()=>clicked,run:()=>c.retryChatGPTMotionServiceError(message,{tab:{id:9,url}})};
}
(async()=>{
 for(const defect of ['', 'owner','url','context','request','savedUrl','guard','lateGuard','lateSaved','lostClaim','lostAck','ready','preparing','answered_text']){
  const f=backend(['ready','preparing','answered_text'].includes(defect)?{phase:defect}:{[defect]:true});
  if(defect)await assert.rejects(f.run(),undefined,defect);else{
   assert.equal((await f.run()).clicked,true);assert.equal((await f.run()).already_attempted,true);
   assert(f.events.indexOf('persist')<f.events.indexOf('CLICK_CHATGPT_MOTION_SERVICE_RETRY'));
  }
  assert.equal(f.clicks(),!defect||defect==='lostAck'?1:0,defect);cases++;
  if(defect==='lostAck'){
   const restart=backend({store:f.store});assert.equal((await restart.run()).already_attempted,true);assert.equal(restart.clicks(),0);cases++;
  }
 }
 const f=backend();await Promise.all([f.run(),f.run()]);assert.equal(f.clicks(),1);cases++;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.request().url()===url?route.fulfill({contentType:'text/html',body:'<main></main><div id="draft"></div>'}):route.abort());
  await page.goto(url);
  await page.addScriptTag({content:`
   let IS_GEMINI=false,cancelRequested=false,activeRepairKey='',activeCoverRequest=null,activeJobId='STORY-375',activeRunId='RUN-375';
   let busy=false,attachment={count:0},ticks=1000,clicks=0,claims=0,motionServiceRetryGuard=null,reports=[],mode='';
   const Date={now:()=>ticks},userTurns=()=>[...document.querySelectorAll('[data-message-author-role="user"]')];
   const visible=e=>!!e&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden';
   const composer=()=>document.querySelector('#draft'),composerText=e=>e.textContent;
   const analysisResponseStopButton=()=>busy,chatGPTComposerAttachmentState=()=>attachment;
   const analysisContentHash=s=>{let hash=2166136261;for(const c of s){hash^=c.charCodeAt(0);hash=Math.imul(hash,16777619);}return(hash>>>0).toString(16).padStart(8,'0');};
   const report=async(...args)=>{reports.push(args);};
   globalThis.chrome={runtime:{sendMessage:async message=>{claims++;
    if(mode==='lateDraft')composer().textContent='new draft';
    if(mode==='lateStop')busy=true;
    const allowed=motionServiceRetryGuard({...message,type:'CLICK_CHATGPT_MOTION_SERVICE_RETRY'});
    const again=motionServiceRetryGuard({...message,type:'CLICK_CHATGPT_MOTION_SERVICE_RETRY'});
    if(again)throw Error('double click guard failed');
    return {ok:allowed,clicked:allowed,error:'live veto'};}}};
   ${helpers}
   function setup(kind='user'){
    document.querySelector('main').innerHTML='';composer().textContent='';
    busy=false;attachment={count:0};IS_GEMINI=false;cancelRequested=false;activeRepairKey='';activeCoverRequest=null;
    activeJobId='STORY-375';activeRunId='RUN-375';clicks=0;claims=0;ticks=1000;reports=[];mode='';
    const owner=document.createElement('section');owner.dataset.testid='conversation-turn-8';owner.dataset.turnId='message-eight';
    const user=document.createElement('div');user.dataset.messageAuthorRole='user';user.dataset.messageId='message-eight';
    const prompt=document.createElement('div');prompt.textContent=${JSON.stringify(request)};user.append(prompt);owner.append(user);document.querySelector('main').append(owner);
    const failure=document.createElement('div');failure.innerHTML='<div class="text-orange-600">มีบางอย่างผิดพลาด โปรดลองอีกครั้ง</div><button data-testid="regenerate-thread-error-button"><div><svg></svg>ลองใหม่</div></button>';
    let scope=user;
    if(kind==='assistant'){scope=document.createElement('section');scope.dataset.testid='conversation-turn-9';scope.dataset.turn='assistant';document.querySelector('main').append(scope);}
    scope.append(failure);failure.querySelector('button').onclick=()=>clicks++;
    return {owner,user,prompt,failure,button:failure.querySelector('button'),scope};
   }
  `});
  for(const variant of ['user','assistant','timeout','collapsed','no_button','hidden','disabled','busy','draft','attachments','uploading','cancel','helper','cover','gemini','wrong_job','wrong_request','duplicate_request','old_error','unknown_error','policy','partial_answer','ready_answer','generated_image','streaming','no_identity']){
   const result=await page.evaluate(({variant,request,context})=>{
    const f=setup(variant==='assistant'?'assistant':'user');
    if(variant==='timeout')f.failure.firstElementChild.textContent='หมดเวลาจัดส่งข้อความ โปรดลองอีกครั้ง';
    if(variant==='collapsed'){const b=document.createElement('button');b.textContent='ดูเพิ่มเติม';f.prompt.append(b);}
    if(variant==='no_button')f.button.remove();if(variant==='hidden')f.button.style.display='none';
    if(variant==='disabled')f.button.disabled=true;if(variant==='busy')busy=true;
    if(variant==='draft')composer().textContent='draft';if(variant==='attachments')attachment.count=1;if(variant==='uploading')attachment.busy=true;
    if(variant==='cancel')cancelRequested=true;if(variant==='helper')activeRepairKey='repair';if(variant==='cover')activeCoverRequest={};
    if(variant==='gemini')IS_GEMINI=true;if(variant==='wrong_job')activeJobId='other';if(variant==='wrong_request')f.prompt.textContent='another prompt';
    if(variant==='duplicate_request')document.querySelector('main').prepend(f.owner.cloneNode(true));
    if(variant==='old_error'){const other=f.owner.cloneNode(true);other.querySelector('[data-message-author-role]').firstElementChild.textContent='another prompt';document.querySelector('main').append(other);}
    if(variant==='unknown_error')f.failure.firstElementChild.textContent='Something unexpected but unrecognized';
    if(variant==='policy')f.failure.firstElementChild.textContent='ไม่สามารถช่วยตามคำขอ นโยบาย';
    if(['partial_answer','ready_answer','generated_image','streaming'].includes(variant)){
     const reply=document.createElement('section');reply.dataset.testid='conversation-turn-9';
     reply.innerHTML=variant==='generated_image'?'<img src="data:image/png;base64,aA==">':variant==='streaming'?'<span aria-busy="true">Working</span>':variant==='partial_answer'?'{"prompt":':'{"prompt":"completed answer"}';
     document.querySelector('main').append(reply);
    }
    if(variant==='no_identity'){f.user.removeAttribute('data-message-id');f.owner.removeAttribute('data-turn-id');}
    return {found:!!chatGPTMotionServiceErrorSnapshot(request,context),matches:IS_GEMINI?false:motionRequestMatches(request)};
   },{variant,request,context});
   assert.equal(result.found,['user','assistant','timeout','collapsed'].includes(variant),variant);
   if(['user','timeout','collapsed'].includes(variant))assert.equal(result.matches,true,variant);cases++;
  }
  // 376: ChatGPT may leave the orange service notice AFTER completing its
  // answer, while removing Retry. Ownership must read the submitted bubble.
  for(const variant of ['residual','collapsed_residual','changed','two_bodies','editable','literal_error']){
   const result=await page.evaluate(({variant,request})=>{
    const f=setup();f.button.remove();
    const bubble=document.createElement('div');bubble.className='user-message-bubble-color';
    f.prompt.replaceWith(bubble);bubble.append(f.prompt);f.prompt.className='whitespace-pre-wrap';
    if(variant==='changed')f.prompt.textContent+=' changed';
    if(variant==='two_bodies')bubble.append(f.prompt.cloneNode(true));
    if(variant==='editable')f.prompt.setAttribute('contenteditable','true');
    if(variant==='literal_error')f.prompt.textContent+=' มีบางอย่างผิดพลาด โปรดลองอีกครั้ง';
    if(variant==='collapsed_residual'){const control=document.createElement('button');control.textContent='ดูเพิ่มเติมแสดงน้อยลง';bubble.append(control);}
    return {matches:motionRequestMatches(request),liveError:f.failure.isConnected};
   },{variant,request});
   assert.equal(result.matches,['residual','collapsed_residual'].includes(variant),variant);
   assert.equal(result.liveError,true,'must not mutate live DOM');cases++;
  }
  for(const variant of ['success','lateDraft','lateStop']){
   const result=await page.evaluate(async({variant,request,context})=>{
    setup();mode=variant;const probe={};let error='';
    await recoverChatGPTMotionServiceError(probe,request,context,7);ticks+=1000;
    await recoverChatGPTMotionServiceError(probe,request,context,7);const early=clicks;ticks+=600;
    try{await recoverChatGPTMotionServiceError(probe,request,context,7);}catch(e){error=e.message;}
    ticks+=3000;await recoverChatGPTMotionServiceError(probe,request,context,7);
    return {clicks,claims,early,error,reports};
   },{variant,request,context});
   assert.equal(result.early,0);assert.equal(result.claims,1);assert.equal(result.clicks,variant==='success'?1:0,variant);
   assert.equal(Boolean(result.error),variant!=='success');cases++;
  }
  await page.addScriptTag({content:`
   const AI_NAME='ChatGPT Web',PROVIDER_KEY='chatgpt';
   const revealChatGPTAnswer=async()=>false; // Dedicated DOM-reveal regression lives in result_readiness_392.cjs.
   const refreshPendingChatGPTMotion=async()=>{}; // Dedicated396 pending-refresh contract.
   const assertNotCancelled=()=>{if(cancelRequested||ticks>100000)throw Error('fixture cancelled');};
   const sleep=async ms=>{ticks+=ms;};
   const assistantTurns=()=>[...document.querySelectorAll('[data-message-author-role="assistant"]')];
   const latestAssistantStrictlyAfterLatestUser=()=>assistantTurns().at(-1),analysisAnswerNode=x=>x;
   const extractJson=turn=>JSON.parse(turn.innerText||turn.textContent),analysisStopLabel=()=>'';
   const explicitAnalysisRefusal=()=>false,explicitImageFailure=()=>false;
   const waitForResponseIdle=async()=>{},setChatGPTImageTool=async()=>{},waitForComposer=async()=>composer(),attachSourceImages=async()=>{};
   const setComposerText=async e=>e,sendButton=()=>({}),lastUserTurnSignature=()=>'';
   let ordinarySends=0,actionEvents=[];
   const sendAndVerify=async()=>{ordinarySends++;};
   const requireMembership=async()=>{}; // Licensed service-retry fixture.
   ${part(source,'  function stableOwnedMotionAnswer(', '  async function submitPrompt(')}
   ${part(source,'  function confirmedAnalysisTechnicalFailure(', '  function composerText(')}
   ${part(source,'  function confirmedStoryImageServiceError(', '  function storyImageNoResultReady(')}
   ${part(source,'  async function submitPrompt(', '  function analysisAnswerNode(')}
   ${part(source,'  async function prepareFlowMotionPlan(', '  function sceneRepairRequest(')}
  `});
  for(const residual of [false,true])for(const route of ['initial','resume','owned_wait']){
   const result=await page.evaluate(async({route,request,context,residual})=>{
    const f=setup();ordinarySends=0;actionEvents=[];
    const answer={...context,prompt:'One continuous shot of the hiker walking away from the forest toward the road.',
     needs_review:false,reference_compatible:true,material_change:false};
    f.button.onclick=()=>{
     clicks++;f.failure.remove();
     const frame=document.createElement('section');frame.dataset.testid='conversation-turn-9';
     const text=document.createElement('div');text.dataset.messageAuthorRole='assistant';text.textContent=JSON.stringify(answer);
     frame.append(text);document.querySelector('main').append(frame);
    };
    if(residual){
     f.button.onclick();clicks=0;
     const bubble=document.createElement('div');bubble.className='user-message-bubble-color';
     f.prompt.replaceWith(bubble);bubble.append(f.prompt);f.prompt.className='whitespace-pre-wrap';
     f.button.remove();f.user.append(f.failure);
    }
    let record={phase:'requested',request,conversation_url:location.href};
    chrome.runtime.sendMessage=async message=>{
     if(message.type==='RETRY_CHATGPT_MOTION_SERVICE'){
      claims++;const allowed=motionServiceRetryGuard({...message,type:'CLICK_CHATGPT_MOTION_SERVICE_RETRY'});
      return {ok:true,clicked:allowed};
     }
     actionEvents.push(message.action);
     if(message.action==='review'){record={phase:'answered',request,result:message.result};return {ok:true,record,validation:{errors:[]}};}
     if(message.action==='save'){record={phase:'ready',prompt:message.result.prompt};}
     return {ok:true,claimed:false,context,record};
    };
    let output;
    if(route==='initial')output=await submitPrompt(request,[],'smartflow-motion-fixture',7,null,context);
    else if(route==='resume')output=await prepareFlowMotionPlan({job:{id:context.job_id}},{},8,7);
    else output=await waitForMotionAnswer(request,context,7);
    return {clicks,claims,ordinarySends,actionEvents,output:typeof output==='string'?output:output.innerText};
   },{route,request,context,residual});
   assert.equal(result.clicks,residual?0:1,route);assert.equal(result.claims,residual?0:1,route);
   assert.equal(result.ordinarySends,route==='initial'?1:0,route);
   assert(result.output.includes('One continuous shot'),route);
   if(route==='resume')assert(result.actionEvents.includes('save'));
   cases++;
  }
 }finally{await browser.close();}
 console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
