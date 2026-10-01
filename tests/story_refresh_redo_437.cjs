// Actual content monitor/receipt functions with virtual time and isolated storage.
// No real browser profile, provider request, user receipt or credit is touched.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i);return source.slice(i,j);};
const code=part('  function storyImagePostRefreshPageReady(', '  function storyImageWaitObservation(')
  +part('  function createStoryImageWaitMonitor(', '  async function recoverOwnedStoryImage(')
  +part('  function sameStoryImageReceipt(', '  function storyLocalRefusalFallbackAllowed(');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const validator=background.slice(background.indexOf('function restartableStoryServiceReceipt('),background.indexOf('const storyFreshImageLocks='));
let cases=0;
const check=(a,b,label)=>{assert.deepEqual(a,b,label);cases++;};
function fixture({refreshed=true,kind='missing',ready=true}={}){
  let time=100000,draft='',files={count:0,busy:false,failed:false},readyState=ready?'complete':'loading';
  const url='https://chatgpt.com/c/fixture',frame={parentElement:null};
  let historyBusy=false;
  const editor={},main={matches:()=>historyBusy,querySelectorAll:()=>[]},body={};
  let frames=[frame],answerText=kind==='unusable'?'Something went wrong while generating your image.':'';
  let observation={signature:'abc123',request:kind==='waiting'||kind==='unusable'?{frame}:{},busy:false,completedControl:kind==='unusable',
    missingRequestOwned:true,stalledReason:kind==='waiting'?'idle_answer_wait':'request_dom_missing',
    state:{reason:kind==='unusable'?'no_image':kind==='waiting'?'waiting_response':'request_missing',images:[],turn:{}}};
  const receipt={version:1,job_id:'STORY-FIXTURE',provider:'chatgpt',scene_index:4,status:'awaiting_result',send_phase:'dispatching',identity:'identity',send_nonce:'nonce',
    result_proof:{prompt:'prompt',conversation_url:url,before_turn:99},
    ...(refreshed?{refresh_recovery:{version:1,phase:'checking',send_nonce:'nonce',conversation_url:url,claimed_at:90000,ready_at:95000,
      document_fence_version:1,previous_document_id:'previous-document',document_id:'current-document'}}:{})};
  const events=[],messages=[];
  const c=vm.createContext({Date:{now:()=>time},Math,Number,Boolean,String,Error,JSON,Set,
    activeJobId:'STORY-FIXTURE',activeRunId:'RUN-FIXTURE',cancelRequested:false,storyImageRefreshGuard:null,storyImageRedoGuard:null,
    location:{href:url},composer:()=>editor,composerText:()=>draft,visible:()=>true,
    getComputedStyle:node=>({overflowY:'visible',flexDirection:'column',...node.style}),
    document:{get readyState(){return readyState;},querySelector:()=>main,querySelectorAll:()=>[],body},
    revealChatGPTAnswer:async()=>false,chatGPTConversationFrames:()=>frames,chatGPTFrameUser:node=>node,
    storyUserBody:()=>'',chatGPTKnownRenderedRequestMatches:(a,b)=>a===b,
    chatGPTFrameAssistant:()=>({textContent:answerText}),retryableCompletedImageText:text=>Boolean(text)&&!text.includes('policy'),
    chatGPTComposerAttachmentState:()=>files,storyImageWaitObservation:()=>observation,
    assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancelled');},
    storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),
    report:async(...args)=>events.push(args),
    chrome:{storage:{local:{get:async()=>({'smartpostStoryGeneratedImage:chatgpt:STORY-FIXTURE:4':receipt})}},
      runtime:{sendMessage:async message=>{messages.push(message);return {ok:true,refresh_scheduled:true};}}}});
  vm.runInContext(code+validator+'; monitor=createStoryImageWaitMonitor("prompt",'+JSON.stringify(receipt.result_proof)+',4,3,true);',c);
  return {c,receipt,events,messages,set:(ms,change={})=>{time=ms;observation={...observation,...change};},
    setDraft:value=>draft=value,setFiles:value=>files=value,setReady:value=>readyState=value,setFrames:value=>frames=value,
    setHistoryBusy:value=>historyBusy=value,
    setText:value=>answerText=value,tick:()=>c.monitor.observe(),frame};
}
async function complete(f){await f.tick();f.set(115000);await f.tick();f.set(130001);try{await f.tick();}catch(e){return e;}return null;}
function receiptFixture(f,error,fresh=false){
  const pkg={job:{id:'STORY-FIXTURE'},request:{image_files:['saved/reference.png']},image_urls:['http://bridge/reference'],
    browser_recovery:{version:1,image_post_refresh_redo:{version:1}},scene_repair:{enabled:true},
    ...(fresh?{fresh_image_restart:{index:4,token:'same-successor'}}:{})};
  const promptIdentity=['prompt','','',''],identity=JSON.stringify([promptIdentity,pkg.request.image_files,1]);
  const evidence={...error.postRefreshEvidence,receipt_identity:identity};
  let row={...f.receipt,identity,run_id:'RUN-FIXTURE',created_at:90000,review_revision:0,status:'completed_no_image',
    recovery_protocol:2,retry_kind:error.retryKind,post_refresh_evidence:evidence,previous_scene_reference_index:3,
    ...(fresh?{fresh_restart:{token:'same-successor',run_id:'RUN-FIXTURE',phase:'created',tab_id:99}}:{})};
  Object.assign(f.c,{PROVIDER_KEY:'chatgpt',IS_GEMINI:false,
    waitStoryImageServiceRetry:async()=>{},confirmedStoryImageServiceError:()=>false,
    stopButtonVisible:()=>false,imageDataFromUrl:async()=> 'data:image/png;base64,current',
    crypto:require('node:crypto').webcrypto});
  f.c.chrome.storage.local={get:async()=>({'smartpostStoryGeneratedImage:chatgpt:STORY-FIXTURE:4':row}),
    set:async value=>{row=Object.values(value)[0];}};
  vm.runInContext(part('  function createStoryImageReceipt(', '  function largeAssistantImages('),f.c);
  return {receipt:f.c.createStoryImageReceipt(pkg,4,promptIdentity,3),get row(){return row;},evidence,pkg};
}
(async()=>{
  let f;
  for(const [direction,scrollTop,expected,label] of [
    ['column-reverse',0,true,'observed reverse-column newest end'],
    ['column-reverse',-100,false,'reverse-column older history'],
    ['column-reverse',-4,true,'reverse-column end tolerance'],
    ['column-reverse',-5,false,'reverse-column outside end tolerance'],
    ['column',6023,true,'ordinary column newest end'],
    ['column',0,false,'ordinary column older-history top']
  ]){
    f=fixture();f.frame.parentElement={scrollHeight:6912,clientHeight:889,scrollTop,
      style:{overflowY:'auto',flexDirection:direction},parentElement:f.c.document.body,closest:()=>null};
    check(f.c.storyImagePostRefreshPageReady(),expected,label+' readiness');
    const result=await complete(f);
    check(result?.code||null,expected?'STORY_IMAGE_POST_REFRESH_REDO':null,label+' monitor uses readiness');
    check(f.messages.length,0,label+' never reloads or sends');
  }
  f=fixture();f.frame.parentElement={scrollHeight:6912,clientHeight:889,scrollTop:0,
    style:{overflowY:'auto',flexDirection:'column-reverse'},parentElement:f.c.document.body,closest:()=>null};
  f.c.revealChatGPTAnswer.userUntil=200000;
  check(f.c.storyImagePostRefreshPageReady(),false,'reverse-column end retains user-scroll grace');
  check(await complete(f),null,'user-scroll grace prevents absence retry');
  f=fixture();let error=await complete(f);
  check(error?.code,'STORY_IMAGE_POST_REFRESH_REDO','ready stable no-result enters typed recovery');
  check(error.retryKind,'missing_after_refresh');
  check(f.messages.length,0,'post-refresh checker does not reload/send again');
  const evidence=error.postRefreshEvidence;
  check(f.c.storyImagePostRefreshEvidenceValid({...f.receipt,status:'completed_no_image',recovery_protocol:2,
    retry_kind:error.retryKind,post_refresh_evidence:evidence}),true,'receipt contract proves observation rather than inventing service-error text');
  check(f.c.restartableStoryServiceReceipt({...f.receipt,status:'completed_no_image',recovery_protocol:2,
    retry_kind:error.retryKind,post_refresh_evidence:evidence},'STORY-FIXTURE',4),true,'actual background gate accepts actual monitor evidence');
  const challenge={job_id:'STORY-FIXTURE',run_id:'RUN-FIXTURE',index:4,receipt_identity:'identity',send_nonce:'nonce',post_refresh_evidence:evidence};
  check(f.c.storyImageRedoGuard(challenge),true);
  f.set(130002,{busy:true});check(f.c.storyImageRedoGuard(challenge),false,'late busy vetoes successor');
  f.set(130003,{busy:false,state:{reason:'image_ready',images:[{}]}});check(f.c.storyImageRedoGuard(challenge),false,'late real image vetoes successor');
  f=fixture({kind:'unusable'});error=await complete(f);check(error.retryKind,'unusable_after_refresh');
  f=fixture({kind:'waiting'});error=await complete(f);check(error.retryKind,'missing_after_refresh','owned request with no reply can redo only after check');
  check(f.c.restartableStoryServiceReceipt({...f.receipt,status:'completed_no_image',recovery_protocol:2,
    retry_kind:error.retryKind,post_refresh_evidence:error.postRefreshEvidence},'STORY-FIXTURE',4),true,'waiting_response is compatible across content and background');
  for(const condition of ['loading','history_loading','shell','draft','attachment','busy','image_loading','image_ready','policy']){
    f=fixture();if(condition==='loading')f.setReady('loading');
    if(condition==='shell')f.setFrames([]);
    if(condition==='history_loading')f.setHistoryBusy(true);
    if(condition==='draft')f.setDraft('user draft');
    if(condition==='attachment')f.setFiles({count:1,busy:false,failed:false});
    if(condition==='busy')f.set(100000,{busy:true});
    if(condition==='image_loading')f.set(100000,{request:{frame:f.frame},state:{reason:'image_loading',images:[{}]}});
    if(condition==='image_ready')f.set(100000,{request:{frame:f.frame},state:{reason:'image_ready',images:[{}]}});
    if(condition==='policy'){f.setText('policy refused');f.set(100000,{request:{frame:f.frame},completedControl:true,state:{reason:'no_image',images:[],turn:{}}});}
    check(await complete(f),null,condition+' cannot become no-result retry authority');
    check(f.messages.length,0,condition+' must not submit or reload');
  }
  f=fixture();await f.tick();f.set(115000,{busy:true});await f.tick();f.set(130001,{busy:false});await f.tick();
  f.set(145001);check(await f.tick()!==null,true,'activity resets the stable ready window');
  f=fixture();f.c.cancelRequested=true;await assert.rejects(f.tick(),/cancelled/);cases++;
  f=fixture();await f.tick();f.receipt.send_nonce='new-attempt';f.set(115000);
  await assert.rejects(f.tick(),e=>e.code==='STORY_IMAGE_RECEIPT_REVIEW'&&/OWNER_CHANGED/.test(e.message));cases++;
  check(f.messages.length,0,'old collector cannot act on a successor nonce');
  f=fixture({refreshed:false});await f.tick();f.set(130000);await f.tick();f.set(160001);
  await assert.rejects(f.tick(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');cases++;
  check(f.messages[0].recovery_protocol,2,'dispatching receipt requests read-only refresh using the new protocol');
  check(f.messages.length,1,'one reload before any absence retry');
  f=fixture();delete f.receipt.refresh_recovery.document_fence_version;
  check(await complete(f),null,'legacy unfenced checking is not evidence that a new document was inspected');
  f.set(160001);await assert.rejects(f.tick(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');cases++;
  check(f.messages.length,1,'legacy missing result requests a new guarded fenced reload instead of restarting directly');
  f=fixture();f.receipt.refresh_recovery.document_id=f.receipt.refresh_recovery.previous_document_id;
  check(await complete(f),null,'same-document readiness cannot authorize a post-refresh absence retry');
  f=fixture();error=await complete(f);let r=receiptFixture(f,error,true);
  check(await r.receipt.restore(),null,'actual receipt consumes background-created typed successor');
  check([r.row.status,r.row.send_phase,r.row.fresh_restart.phase,r.row.previous_scene_reference_index],
    ['awaiting_result','prepared','consumed',3],'successor is prepared once with the saved prior-scene reference');
  check(r.row.resume_image_prompt,'prompt','full exact saved prompt retained');
  check(r.row.refresh_recovery,null,'next attempt cannot reuse a previous reload check');
  check(r.row.post_refresh_evidence,null,'next attempt cannot reuse previous absence evidence');
  check(r.row.identity.includes('saved/reference.png'),true);
  await r.receipt.begin();await r.receipt.dispatching('prompt',{conversation_url:'https://chatgpt.com/c/next',before_turn:-1});
  check(r.row.fresh_restart.phase,'consumed','new dispatch retains its already-allocated successor identity');
  // A result arriving during backoff is a safe recheck, not a popup error.
  f=fixture();error=await complete(f);r=receiptFixture(f,error);
  let recovered=0;
  f.c.recoverOwnedStoryImage=async()=>{
    if(!recovered++){const retry=Object.assign(Error('typed absence'),{code:'STORY_IMAGE_POST_REFRESH_REDO',
      retryKind:error.retryKind,postRefreshEvidence:r.evidence});throw retry;}
    return {src:'https://chatgpt.com/backend-api/estuary/content?id=late-current'};
  };
  f.c.chrome.runtime.sendMessage=async()=>({ok:false,refresh_scheduled:false,retry_safe:true,refresh_reason:'live_guard_changed'});
  check(await r.receipt.restore(),'data:image/png;base64,current','late valid result returns to collector after explicit preallocation veto');
  check(r.row.status,'generated','late valid result saved without another Send');
  check(recovered,2,'one redo veto then exact result re-read');
  for(const phase of ['claimed','creating']){
    f=fixture();error=await complete(f);r=receiptFixture(f,error);
    r.row.fresh_restart={token:'retain-allocation',run_id:'RUN-FIXTURE',phase};
    f.c.recoverOwnedStoryImage=async()=>{throw Object.assign(Error('repeat absence check'),{
      code:'STORY_IMAGE_POST_REFRESH_REDO',retryKind:error.retryKind,postRefreshEvidence:r.evidence});};
    f.c.chrome.runtime.sendMessage=async()=>({ok:true,refresh_scheduled:true});
    await assert.rejects(r.receipt.restore(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');cases++;
    check(r.row.fresh_restart.token,'retain-allocation',phase+' allocation survives renewed observation');
  }
  console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
