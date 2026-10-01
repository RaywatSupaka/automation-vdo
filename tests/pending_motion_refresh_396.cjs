const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const background=fs.readFileSync('browser_extension/background.js','utf8');
function part(text,start,end){const a=text.indexOf(start),b=text.indexOf(end,a+start.length);assert(a>=0&&b>a);return text.slice(a,b);}
const helper=part(source,'  function chatGPTConversationFrames(', '  function assistantTurns(')
  +part(source,'  function pendingChatGPTMotionSnapshot(', '  function stableOwnedMotionAnswer(');
const bg=part(background,'const completedResponseRefreshLocks =','async function refreshStoryChatGPTResult(');
const context={job_id:'STORY-FIXTURE',index:6,context_id:'a'.repeat(64)};
const request='Exact saved motion question';
const url='https://chatgpt.com/c/12345678-1234-1234-1234-123456789012';
function fixture(){
  let now=0,sends=0;
  const flags={stop:false,draft:'',attachments:{count:0},missing:false,later:false,answer:'',media:false,progress:false};
  const frameAttributes=index=>({getAttribute:name=>name==='data-testid'?`conversation-turn-${index}`:null});
  const user={...frameAttributes(1),querySelector:s=>s==='[data-message-author-role="user"]'?{}:flags.progress?{}:null};
  const reply={...frameAttributes(2),querySelector:s=>s==='img,video,canvas'&&flags.media?{}:null,
    cloneNode:()=>({textContent:flags.answer,querySelectorAll:()=>[]})};
  const later={...frameAttributes(3),querySelector:s=>s==='[data-message-author-role="user"]'?{}:null};
  const frames=()=>[user,...(flags.answer||flags.media?[reply]:[]),...(flags.later?[later]:[])];
  const c=vm.createContext({IS_GEMINI:false,cancelRequested:false,activeRepairKey:'',activeCoverRequest:null,
    activeJobId:context.job_id,activeRunId:'RUN-ONE',pendingMotionRefreshGuard:null,
    analysisResponseStopButton:()=>flags.stop,composer:()=>({}),composerText:()=>flags.draft,
    chatGPTComposerAttachmentState:()=>flags.attachments,revealChatGPTAnswer:()=>{},
    location:{href:url},document:{querySelectorAll:selector=>selector==='[data-testid^="conversation-turn-"]'?frames():[]},Date:{now:()=>now},
    chatGPTStoryRequest:p=>p===request&&!flags.missing?{frame:user,owner:{request_message_id:'owned-message'}}:{},
    analysisContentHash:s=>crypto.createHash('sha256').update(s).digest('hex').slice(0,8),
    report:async()=>{},chrome:{runtime:{sendMessage:async m=>{sends++;assert(c.pendingMotionRefreshGuard(m));return {ok:true,refresh_scheduled:true};}}}});
  vm.runInContext(helper,c);
  return {c,flags,now:n=>now=n,sends:()=>sends};
}
async function main(){
  let cases=0;
  for(const kind of ['', 'gemini','cancel','repair','cover','wrong_job','wrong_context','draft','attachment','upload','failed_upload','stop','progress','answer','partial','refusal','media','missing','later','user_input','temporary_url']){
    const f=fixture();let ctx=context;
    if(kind==='gemini')f.c.IS_GEMINI=true;
    if(kind==='cancel')f.c.cancelRequested=true;
    if(kind==='repair')f.c.activeRepairKey='repair';
    if(kind==='cover')f.c.activeCoverRequest={};
    if(kind==='wrong_job')f.c.activeJobId='STORY-OTHER';
    if(kind==='wrong_context')ctx={...context,context_id:''};
    if(kind==='draft')f.flags.draft='user draft';
    if(kind==='attachment')f.flags.attachments.count=1;
    if(kind==='upload')f.flags.attachments.busy=true;
    if(kind==='failed_upload')f.flags.attachments.failed=true;
    if(kind==='stop')f.flags.stop=true;
    if(kind==='progress')f.flags.progress=true;
    if(kind==='answer')f.flags.answer='{"prompt":"complete"}';
    if(kind==='partial')f.flags.answer='{"prompt":';
    if(kind==='refusal')f.flags.answer='Cannot comply with this request';
    if(kind==='media')f.flags.media=true;
    if(kind==='missing')f.flags.missing=true;
    if(kind==='later')f.flags.later=true;
    if(kind==='user_input')f.c.revealChatGPTAnswer.userUntil=6000;
    if(kind==='temporary_url')f.c.location.href='https://chatgpt.com/c/WEB:123';
    assert.equal(Boolean(f.c.pendingChatGPTMotionSnapshot(request,ctx)),!kind,kind);cases++;
  }
  const f=fixture(),probe={};
  await f.c.refreshPendingChatGPTMotion(probe,request,context);f.now(45000);
  await f.c.refreshPendingChatGPTMotion(probe,request,context);f.now(59999);
  await f.c.refreshPendingChatGPTMotion(probe,request,context);assert.equal(f.sends(),0);
  f.now(60000);await assert.rejects(f.c.refreshPendingChatGPTMotion(probe,request,context),e=>e.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED');
  f.now(999999);await f.c.refreshPendingChatGPTMotion(probe,request,context);assert.equal(f.sends(),1);cases++;
  for(const change of ['stop','answer','missing','draft']){
    const f=fixture(),probe={};await f.c.refreshPendingChatGPTMotion(probe,request,context);f.now(80000);
    f.flags[change]=change==='answer'||change==='draft'?'new content':true;
    await f.c.refreshPendingChatGPTMotion(probe,request,context);f.now(90000);
    f.flags[change]=change==='answer'||change==='draft'?'':false;
    await f.c.refreshPendingChatGPTMotion(probe,request,context);f.now(100000);
    await f.c.refreshPendingChatGPTMotion(probe,request,context);assert.equal(f.sends(),0);cases++;
  }
  const late=fixture(),lateProbe={};await late.c.refreshPendingChatGPTMotion(lateProbe,request,context);
  late.now(45000);await late.c.refreshPendingChatGPTMotion(lateProbe,request,context);late.now(90000);
  late.c.chrome.runtime.sendMessage=async m=>{late.flags.answer='answer arrived';assert.equal(late.c.pendingMotionRefreshGuard(m),false);return {ok:false};};
  await late.c.refreshPendingChatGPTMotion(lateProbe,request,context);cases++;
  for(const purpose of ['pending_motion_answer','unconfirmed_motion_send'])
  for(const defect of ['', 'used','preparing','ready','wrong_context','wrong_request','wrong_chat','repair','cancel','late_busy','late_owner','offline','reload_failure','cancel_after_reload']){
    const store={},events=[];let checks=0,live=0,ack=null;
    const message={purpose,provider:'chatgpt',job_id:context.job_id,index:6,
      context_id:context.context_id,run_id:'RUN-ONE',conversation_url:url,pending_request:request,
      owner_id:'owned-message',signature:'aabbccdd'};
    const key=`${purpose==='unconfirmed_motion_send'?'smartflowUnconfirmedMotionRefresh':'smartflowPendingMotionRefresh'}:${context.job_id}:6:${context.context_id}`;
    if(defect==='used')store[key]={phase:'claimed',run_id:'OLDER-RUN'};
    if(defect==='cancel')store[`smartflowChatGPTStoryRefreshCancelled:${context.job_id}`]='RUN-ONE';
    const record={phase:['preparing','ready'].includes(defect)?defect:'requested',request:defect==='wrong_request'?'other':request,
      conversation_url:defect==='wrong_chat'?url+'/other':url,...(defect==='repair'?{story_visual_repair:{}}:{})};
    const before=JSON.stringify(record);
    const c=vm.createContext({BRIDGE:'offline-fixture',crypto:crypto.webcrypto,
      assertStoryCheckpointOwner:async()=>{checks++;if((defect==='late_owner'&&checks>=2)||(defect==='cancel_after_reload'&&events.includes('reload')))throw Error('owner stopped');},
      bridgeFetch:async(_url,opts)=>{assert.equal(JSON.parse(opts.body).action,'status');if(defect==='offline')throw Error('offline');return {ok:true,json:async()=>({ok:true,context:{context_id:defect==='wrong_context'?'b'.repeat(64):context.context_id},record})};},
      chrome:{storage:{local:{get:async key=>({[key]:store[key]}),set:async values=>Object.assign(store,values)}},
        tabs:{get:async()=>({id:9,url}),sendMessage:async(_id,m)=>{live++;return {ok:true,allowed:!(defect==='late_busy'&&live===2),challenge:m.challenge,signature:m.signature};},
          reload:async id=>{assert.equal(id,9);events.push('reload');if(defect==='reload_failure')throw Error('reload failed');}}},
      waitForAIRefreshReady:async()=>events.push('loaded'),
      startAIWebJob:async(job,reuse,provider,fresh,run,guard)=>{assert.equal(job,context.job_id);assert.equal(reuse,true);assert.equal(provider,'chatgpt');assert.equal(fresh,false);assert.equal(run,'RUN-ONE');await guard(9);events.push('resume_read');},
      reportWebActionProgress:async()=>events.push('review')});
    const navigation=require('./shared_refresh_fixture_439.cjs').install(c);
    vm.runInContext(bg,c);
    const run=()=>c.refreshCompletedChatGPTResponse(message,{tab:{id:9,url}},r=>ack=r);
    if(defect&&!['reload_failure','cancel_after_reload'].includes(defect)){
      await assert.rejects(run());assert.deepEqual(events,[]);assert.equal(ack,null);
    }else{
      await run();assert.equal(ack.refresh_scheduled,true);
      assert.deepEqual(events,['reload_failure','cancel_after_reload'].includes(defect)?['reload','review']:['reload','loaded','resume_read']);
      message.signature='bbccddee';
      if(defect==='reload_failure'){navigation.setDocument('new-document');await run();assert.equal(store[key].phase,'resumed');}
      else await assert.rejects(run());
      assert.equal(events.filter(e=>e==='reload').length,1);
    }
    assert.equal(JSON.stringify(record),before);cases++;
  }
  // Resume after reload: read the already requested result; never submitPrompt.
  const resumeCode=part(source,'  async function prepareFlowMotionPlan(', '  function sceneRepairRequest(');
  let now=0,sends=0;const events=[];
  const answer={...context,prompt:'One continuous shot with natural movement and the saved spoken line.',needs_review:false,reference_compatible:true,material_change:false};
  const turn={innerText:JSON.stringify(answer)};
  const c=vm.createContext({PROVIDER_KEY:'chatgpt',AI_NAME:'ChatGPT',IS_GEMINI:false,activeRunId:'RUN-ONE',Date:{now:()=>now},
    chrome:{runtime:{sendMessage:async m=>{events.push(m.action);return {ok:true,context,record:{phase:m.action==='save'?'ready':'requested',request,conversation_url:url},claimed:false,validation:{errors:[]}};}}},
    report:async()=>{},assertNotCancelled:()=>{},revealChatGPTAnswer:async()=>false,refreshPendingChatGPTMotion:async()=>{},recoverChatGPTMotionServiceError:async()=>false,
    userTurns:()=>[],motionRequestMatches:()=>true,analysisAnswerNode:x=>x,latestAssistantStrictlyAfterLatestUser:()=>turn,
    motionResponseState:()=>({ready:true,text:turn.innerText,busy:false,incomplete:false}),analysisResponseStopButton:()=>null,
    stableOwnedMotionAnswer:()=>null,analysisContentHash:()=>'',sleep:async ms=>{now+=ms;if(now>20000)throw Error('resume stuck');},
    submitPrompt:async()=>{sends++;throw Error('duplicate Send');},extractMotionJson:()=>answer});
  vm.runInContext(resumeCode,c);await c.prepareFlowMotionPlan({job:{id:context.job_id}}, {},6,6);
  assert.equal(sends,0);assert(events.includes('review'));assert(events.includes('save'));cases++;
  assert(source.includes('await refreshPendingChatGPTMotion(pendingRefresh, text, motionContext, completedCount)'));
  assert(source.includes('await refreshPendingChatGPTMotion(pendingRefresh, request, context, completedCount)'));
  // Real isolated Chromium DOM, actual full-prompt owner matcher and snapshot.
  // All requests intercepted; never connect to the user's Chrome/session/site.
  const {chromium}=require('playwright'),browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage();
    await page.route('**/*',route=>route.request().url()===url
      ?route.fulfill({contentType:'text/html',body:'<main></main>'}):route.abort());
    await page.goto(url);
    await page.addScriptTag({content:`
      const IS_GEMINI=false,activeJobId='STORY-FIXTURE',activeRunId='RUN-ONE',activeRepairKey='',activeCoverRequest=null;
      let cancelRequested=false,pendingMotionRefreshGuard=null;
      const analysisResponseStopButton=()=>document.querySelector('[data-testid="stop-button"]');
      const composer=()=>document.querySelector('[contenteditable]'),composerText=e=>e?.textContent||'';
      const chatGPTComposerAttachmentState=()=>({count:document.querySelectorAll('#composer img').length});
      const revealChatGPTAnswer=()=>{},analysisContentHash=t=>String(t.length);
      ${part(source,'  function chatGPTConversationFrames(', '  function assistantTurns(')}
      ${part(source,'  function chatGPTKnownRenderedRequestMatches(', '  function chatGPTMotionRequestText(')}
      ${part(source,'  function storyTurnNumber(', '  function chatGPTStoryImageSnapshot(')}
      ${helper}
    `});
    for(const kind of ['section_blank','article_blank','empty_assistant','completed','hidden_answer','partial','refusal','spinner','stream','native_error','media','duplicate_request','later_user','missing_id']) {
      const result=await page.evaluate(({kind,context,request})=>{
        const main=document.querySelector('main');main.innerHTML='';
        const frame=document.createElement(kind==='article_blank'?'article':'section');frame.dataset.testid='conversation-turn-12';
        const user=document.createElement('div');user.dataset.messageAuthorRole='user';
        if(kind!=='missing_id')user.dataset.messageId='owned-message';
        user.textContent=request;const more=document.createElement('button');more.textContent='ดูเพิ่มเติม';user.append(more);frame.append(user);main.append(frame);
        const next=document.createElement('section');next.dataset.testid='conversation-turn-13';
        const heading=document.createElement('h4');heading.textContent='ChatGPT พูดว่า:';next.append(heading);
        const answer=document.createElement('div');answer.dataset.messageAuthorRole='assistant';next.append(answer);
        if(['completed','hidden_answer','partial','refusal'].includes(kind))answer.textContent=kind==='partial'?'{"prompt":':kind==='refusal'?'Cannot comply':JSON.stringify({job_id:context.job_id,index:6,prompt:'existing answer'});
        if(kind==='hidden_answer')answer.style.display='none';
        if(kind==='spinner')next.setAttribute('aria-busy','true');
        if(kind==='stream')answer.dataset.isStreaming='true';
        if(kind==='native_error'){const retry=document.createElement('button');retry.dataset.testid='regenerate-thread-error-button';frame.append(retry);}
        if(kind==='media')next.append(document.createElement('img'));
        if(!['section_blank','article_blank'].includes(kind))main.append(next);
        if(kind==='duplicate_request')main.append(frame.cloneNode(true));
        if(kind==='later_user'){const other=frame.cloneNode(true);other.dataset.testid='conversation-turn-14';other.querySelector('[data-message-author-role]').textContent='other request';main.append(other);}
        return Boolean(pendingChatGPTMotionSnapshot(request,context));
      },{kind,context,request});
      assert.equal(result,['section_blank','article_blank','empty_assistant'].includes(kind),kind);cases++;
    }
  } finally {await browser.close();}
  console.log(JSON.stringify({ok:true,cases}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
