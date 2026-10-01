// Actual content receipt/reminder functions; isolated storage and virtual DOM/time.
// No Chrome profile, provider request or local user job is touched.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i);return source.slice(i,j);};
const code=part('  function sameStoryImageReceipt(', '  function storyLocalRefusalFallbackAllowed(')
  +part('  function storyImagePostRefreshEvidenceValid(', '  function storyImageWaitObservation(')
  +part('  function storySameChatReminderIdle(', '  function createStoryImageWaitMonitor(');
let cases=0;
const check=(a,b,label)=>{assert.deepEqual(a,b,label);cases++;};
const clone=value=>structuredClone(value);
function fixture(){
  let time=100000,draft='',sendCount=0,childFound=false,mode='accepted',sleeps=0;
  const key='smartpostStoryGeneratedImage:chatgpt:STORY-FIXTURE:9',url='https://chatgpt.com/c/fixture';
  const pkg={job:{id:'STORY-FIXTURE'},request:{image_files:['saved/reference.png']},image_urls:['http://bridge/ref'],
    browser_recovery:{version:1,image_post_refresh_redo:{version:1}}};
  const promptIdentity=['original','','',''],identity=JSON.stringify([promptIdentity,pkg.request.image_files,1]);
  const parent={version:1,provider:'chatgpt',job_id:'STORY-FIXTURE',run_id:'run',scene_index:9,identity,
    created_at:80000,review_revision:0,status:'awaiting_result',send_phase:'accepted',send_nonce:'original-nonce',
    result_proof:{prompt:'original',conversation_url:url,request_turn_id:'turn-original',request_message_id:'message-original'},
    refresh_recovery:{version:1,phase:'checking',document_fence_version:1,document_id:'new-doc',previous_document_id:'old-doc',
      tab_id:1,send_nonce:'original-nonce',conversation_url:url,claimed_at:30000,ready_at:40000}};
  const error={code:'STORY_IMAGE_POST_REFRESH_REDO',retryKind:'missing_after_refresh',postRefreshEvidence:{version:1,
    receipt_identity:identity,send_nonce:parent.send_nonce,conversation_url:url,refresh_claimed_at:30000,
    observed_at:100000,stable_since:60000,stable_samples:8,signature:'stable',result_reason:'waiting_response',
    page_ready:true,history_ready:true,at_end:true,reload_completed:true,response_active:false,draft_present:false}};
  let owned=clone(parent);
  const db={[key]:clone(parent)},events=[],claims=[];
  const reference={complete:true,naturalWidth:941,naturalHeight:1672};
  const frame={querySelectorAll:()=>[reference]},editor={};
  let frames=[frame],ready=true,files={count:0,busy:false,failed:false};
  let observation={busy:false,state:{reason:'waiting_response',images:[]},request:{frame}};
  const c=vm.createContext({Date:{now:()=>time},Math,Number,Boolean,String,Error,JSON,Set,HTMLTextAreaElement:class{},
    IS_GEMINI:false,PROVIDER_KEY:'chatgpt',activeJobId:parent.job_id,activeRunId:'run',cancelRequested:false,
    storyImageReminderGuard:null,location:{href:url},crypto:require('node:crypto').webcrypto,
    composer:()=>editor,composerText:()=>draft,storyImageWaitObservation:()=>observation,
    chatGPTComposerAttachmentState:()=>files,chatGPTConversationFrames:()=>frames,chatGPTFrameUser:f=>f,
    storyImagePostRefreshPageReady:()=>ready,storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),
    assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancelled');},
    report:async(...args)=>events.push(args),waitForComposer:async()=>editor,setChatGPTImageTool:async()=>{},
    setComposerText:async(e,text)=>{draft=text;if(mode==='late_draft')observation={...observation,state:{reason:'image_ready',images:[{}]}};return editor;},sendButton:()=>({}),
    userTurns:()=>frames,lastUserTurnSignature:()=>'',assistantTurns:()=>[],
    chatGPTStoryRequest:(prompt,proof)=>childFound?{owner:{conversation_url:url,request_turn_id:'turn-child',request_message_id:'message-child'}}:{reason:'request_missing'},
    sleep:async()=>{time+=5000;sleeps++;if(sleeps>12)throw Error('fixture passive wait');},
    chrome:{storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,clone(db[k])])),
      set:async rows=>Object.assign(db,clone(rows))}},runtime:{sendMessage:async()=>{throw Error('unexpected browser action');}}},
    sendAndVerify:async(button,e,u,s,a,m,ctx)=>{
      sendCount++;check(ctx.sameChatReminder,true,'distinct child Send transport');
      const baseline={conversation_url:url,before_message_ids:['message-original'],before_frame_ids:['turn-original'],before_turn:9};
      const claim=await ctx.onDispatch(draft,baseline);claims.push(claim);
      check(c.storyImageReminderGuard({story_reminder_claim:claim}),true,'original idle prepress proof');
      if(mode==='prepress_veto')throw Object.assign(Error('not pressed'),{notDispatched:true});
      db[claim.key+':dispatch']=claim.nonce;draft='';
      if(mode==='late_prepress'){
        observation={...observation,state:{reason:'image_ready',images:[{}]}};
        throw Object.assign(Error('late original before press'),{notDispatched:true});
      }
      if(mode==='ambiguous')throw Error('ACK lost');
      childFound=true;return {conversation_url:url,request_turn_id:'turn-child',request_message_id:'message-child'};
    }});
  vm.runInContext(code,c);
  const make=()=>c.createStorySameChatReminder(key,()=>owned,async()=>clone(db[key]),async row=>{
    assert(c.sameStoryImageReceipt(db[key],owned),'parent CAS');owned=clone(row);db[key]=clone(row);
  },9,8);
  return {c,db,key,pkg,promptIdentity,error,reference,frame,events,claims,make,
    get owned(){return owned;},get sends(){return sendCount;},get sleeps(){return sleeps;},
    setDraft:text=>draft=text,setMode:value=>mode=value,setChildFound:value=>{childFound=value;sleeps=0;},
    setObservation:value=>observation={...observation,...value},setReady:value=>ready=value,
    setFiles:value=>files={...files,...value},setFrames:value=>frames=value,
    setParent:value=>{owned={...owned,...value};db[key]=clone(owned);},setSleep:fn=>c.sleep=fn};
}
(async()=>{
  let f=fixture(),r=f.make();
  check(await r.prepare(f.error),true,'accepted original qualifies without recovery_protocol on parent');
  const childKey=f.owned.same_chat_reminder.key,original=clone(f.owned.result_proof);
  check(f.db[childKey].send_phase,'prepared');
  check(f.owned.status,'awaiting_result','no original terminal/reset');
  check(f.owned.post_refresh_evidence,undefined,'redo evidence does not terminalize original');
  check(f.db[childKey].original_result_proof,original,'original proof retained exactly');
  await r.resume();
  check(f.sends,1);check(f.owned.send_nonce,'original-nonce');
  check(f.owned.result_proof.request_message_id,'message-child','effective result follows accepted child');
  check(f.owned.result_proof.prompt,f.db[childKey].prompt);
  check(f.db[childKey].result_proof.before_message_ids,['message-original']);
  check(f.db[childKey].result_proof.before_frame_ids,['turn-original']);
  check(f.c.storyImageReminderGuard,null,'no leaked prepress guard');
  await f.make().resume();check(f.sends,1,'worker restart never repeats accepted child');
  check(await f.make().prepare(f.error),true,'duplicate evidence reuses child');
  await f.make().resume();check(f.sends,1,'duplicate ticks never repeat child');
  for(const mutation of [
    {send_phase:'dispatching'},{image_url:'saved.png'},{run_id:'other'},
    {result_proof:{prompt:'original',conversation_url:'https://chatgpt.com/c/foreign',request_message_id:'message-original'}},
    {result_proof:{prompt:'original',conversation_url:'https://chatgpt.com/c/fixture'}},
    {refresh_recovery:{phase:'checking'}}
  ]){f=fixture();f.setParent(mutation);check(await f.make().prepare(f.error),false,'unsafe original does not authorize reminder');check(f.sends,0);}
  for(const change of ['busy','image','loading','text','reference','draft','upload','ready','latest']){
    f=fixture();
    if(change==='busy')f.setObservation({busy:true});
    if(change==='image')f.setObservation({state:{reason:'image_ready',images:[{}]}});
    if(change==='loading')f.setObservation({state:{reason:'image_loading',images:[{}]}});
    if(change==='text')f.setObservation({state:{reason:'no_image',images:[]}});
    if(change==='reference')f.reference.complete=false;
    if(change==='draft')f.setDraft('user draft');
    if(change==='upload')f.setFiles({busy:true});
    if(change==='ready')f.setReady(false);
    if(change==='latest')f.setFrames([f.frame,{}]);
    check(await f.make().prepare(f.error),false,change+' veto');check(f.sends,0);
  }
  f=fixture();r=f.make();await r.prepare(f.error);
  f.setObservation({state:{reason:'image_ready',images:[{}]}});
  await r.resume();check(f.sends,0,'late original image wins');check(f.owned.same_chat_reminder,null);
  f=fixture();r=f.make();await r.prepare(f.error);f.setObservation({busy:true});
  f.setSleep(async()=>f.setObservation({busy:false,state:{reason:'image_ready',images:[{}]}}));
  await r.resume();check(f.sends,0,'busy late generation waits for original');
  f=fixture();r=f.make();await r.prepare(f.error);f.setObservation({busy:false,state:{reason:'image_loading',images:[{}]}});
  f.setSleep(async()=>f.setObservation({state:{reason:'image_ready',images:[{}]}}));
  await r.resume();check(f.sends,0,'loading original without busy marker waits, never errors or reminds');
  check(f.owned.same_chat_reminder,null,'decoded original keeps original owner');
  for(const mode of ['late_draft','late_prepress']){
    f=fixture();r=f.make();await r.prepare(f.error);f.setMode(mode);
    await r.resume();check(f.owned.same_chat_reminder,null,mode+' uses original result');
    check(f.db[f.key].result_proof.prompt,'original');check(f.c.storyImageReminderGuard,null);
    if(mode==='late_prepress')check(Object.keys(f.db).some(k=>k.endsWith(':dispatch')),true,'spent prepress latch retained');
  }
  f=fixture();r=f.make();await r.prepare(f.error);f.setMode('prepress_veto');await r.resume();
  check(f.db[f.owned.same_chat_reminder.key].send_phase,'vetoed','proven no press does not wait for nonexistent child');
  await f.make().resume();check(f.sends,1,'vetoed child never dispatches again');
  f=fixture();r=f.make();await r.prepare(f.error);await r.resume();f.c.activeRunId='later-run';
  await f.make().resume();check(f.sends,1,'new Continue may read an accepted prior-run result');
  f=fixture();r=f.make();await r.prepare(f.error);f.c.activeRunId='later-run';
  await assert.rejects(f.make().resume(),/หลักฐานข้อความย้ำ/);cases++;check(f.sends,0,'new run cannot send old prepared child');
  f=fixture();r=f.make();await r.prepare(f.error);f.setMode('ambiguous');
  await assert.rejects(r.resume(),/fixture passive wait/);cases++;
  check(f.sends,1);check(f.db[f.owned.same_chat_reminder.key].send_phase,'dispatching','lost ACK kept pending');
  f.setChildFound(true);await f.make().resume();check(f.sends,1,'restart reconciles exact pending child without Send');
  check(f.owned.result_proof.request_message_id,'message-child');
  for(const corruption of ['prompt','url','original','nonce','run']){
    f=fixture();r=f.make();await r.prepare(f.error);await r.resume();
    const child=f.db[f.owned.same_chat_reminder.key];
    if(corruption==='prompt')child.result_proof.prompt='foreign';
    if(corruption==='url')child.result_proof.conversation_url='https://chatgpt.com/c/foreign';
    if(corruption==='original'){child.original_result_proof.prompt='foreign';f.setParent({result_proof:{prompt:'other'}});}
    if(corruption==='nonce')child.parent_nonce='changed';
    if(corruption==='run')child.run_id='other';
    await assert.rejects(f.make().resume(),/หลักฐานข้อความย้ำ/);cases++;check(f.sends,1,'corrupt child never resends');
  }
  f=fixture();r=f.make();await r.prepare(f.error);f.c.cancelRequested=true;
  await assert.rejects(r.resume(),/cancelled/);cases++;check(f.sends,0,'cancel before Send');
  // Actual parent restore -> typed evidence -> reminder -> child result -> saved data.
  f=fixture();let reads=0;
  Object.assign(f.c,{imageDataFromUrl:async()=> 'data:image/png;base64,actual-owned-fixture',
    recoverOwnedStoryImage:async(proof,owner,context)=>{
      if(!reads++){throw f.error;}
      check(proof.request_message_id,'message-child','parent collector switches ownership');
      check(context.postRefreshRedo,true,'accepted reminder enables its own fenced v3 result recovery');
      return {src:'https://chatgpt.com/backend-api/estuary/content?id=child'};
    }});
  vm.runInContext(part('  function createStoryImageReceipt(', '  function largeAssistantImages('),f.c);
  const receipt=f.c.createStoryImageReceipt(f.pkg,9,f.promptIdentity,8);
  check(await receipt.restore(),'data:image/png;base64,actual-owned-fixture','normal receipt download continues');
  check(f.db[f.key].status,'generated');check(f.sends,1);check(reads,2);
  check(f.db[f.key].send_nonce,'original-nonce','original claim remains intact');
  // Delayed original acceptance must leave the original submit reader after a child handoff.
  f=fixture();let prime=true;
  f.c.recoverOwnedStoryImage=async()=>{if(prime){prime=false;throw Error('prime receipt read');}throw f.error;};
  vm.runInContext(part('  function createStoryImageReceipt(', '  function largeAssistantImages('),f.c);
  const delayed=f.c.createStoryImageReceipt(f.pkg,9,f.promptIdentity,8);
  await assert.rejects(delayed.restore(),/prime receipt read/);cases++;
  await assert.rejects(delayed.acceptanceTimeout('original',f.owned.result_proof),error=>error.code==='STORY_IMAGE_REMINDER_HANDOFF');cases++;
  check(f.sends,1);check(f.db[f.key].result_proof.request_message_id,'message-child');
  // A known technical failure of the reminder must retry the full scene, never
  // carry a context-dependent short reminder into a new image request.
  f=fixture();r=f.make();await r.prepare(f.error);await r.resume();
  f.db[f.key].status='completed_no_image';f.db[f.key].response_excerpt='Something went wrong';
  Object.assign(f.c,{confirmedStoryImageServiceError:()=>true,retryableCompletedImageText:()=>true,
    waitStoryImageServiceRetry:async()=>{}});
  vm.runInContext(part('  function createStoryImageReceipt(', '  function largeAssistantImages('),f.c);
  const technical=f.c.createStoryImageReceipt(f.pkg,9,f.promptIdentity,8);
  check(await technical.restore(),null,'completed technical failure keeps existing sequential retry');
  check(technical.retryInstruction(),'original','full original scene instruction survives reminder failure');
  check(f.db[f.key].same_chat_reminder,null,'next original attempt does not inherit spent reminder link');
  // Actual sendAndVerify selects the separate trusted-reminder claim, not original Send.
  f=fixture();let sent;
  Object.assign(f.c,{AI_NAME:'ChatGPT Web',HTMLTextAreaElement:class {},SmartFlowSingleAnswer:{has:()=>true},
    waitForStableSendDraft:async()=>({button:{},editor:{textContent:'reminder'}}),
    storyTurnNumber:()=>9,chatGPTUserMessageId:()=> 'message-original',chatGPTFrameId:()=> 'turn-original',
    chatGPTStoryRequest:()=>({reason:'request_found',owner:{conversation_url:'https://chatgpt.com/c/fixture',request_message_id:'message-child'}})});
  f.c.chrome.runtime.sendMessage=async message=>{sent=message;return {ok:true,method:'single_trusted_ai_send'};};
  vm.runInContext(part('  async function sendAndVerify(', '  async function '),f.c);
  const wire={key:'child',parent_key:f.key,parent_nonce:'original-nonce',nonce:'child-nonce',scene_index:9};
  f.setDraft('reminder');
  await f.c.sendAndVerify({}, {},0,'',0,false,{sameChatReminder:true,scene_index:9,onDispatch:async()=>wire});
  check(sent.story_reminder_claim,wire,'actual trusted-send reminder transport');
  check(sent.story_send_claim,undefined,'original image claim untouched');
  process.stdout.write(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
