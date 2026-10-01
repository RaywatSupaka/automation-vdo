const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto').webcrypto;
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8'),bg=fs.readFileSync('browser_extension/background.js','utf8');
function section(source,start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const contentCode=section(content,'  function completedChatGPTMotionSnapshot(', '  function normalizeOptionalCover(');
const backgroundCode=section(bg,'const completedResponseRefreshLocks =','async function refreshStoryChatGPTResult(');
const context={job_id:'STORY-FIXTURE',index:3,context_id:'next-context'};
const value={...context,context_id:'old-context',prompt:'A complete motion prompt showing natural movement in a room.',needs_review:false,reference_compatible:true,material_change:false};
const text=JSON.stringify(value),request=JSON.stringify({...context,context_id:'old-context'});
function fixture(){
 const state={completed:true,ready:true,incomplete:false,busy:false,text}, flags={draft:'',stop:true,progress:false,request,attachments:{count:0}};
 const scope={querySelectorAll:()=>flags.progress?[{}]:[]};
 let now=1000,sends=0;
 const c=vm.createContext({IS_GEMINI:false,activeRepairKey:'',activeCoverRequest:null,cancelRequested:false,
  activeJobId:context.job_id,activeRunId:'RUN-ONE',lastCommittedChatGPTImage:null,completedResponseRefreshGuard:null,
  Date:{now:()=>now},analysisResponseStopButton:()=>flags.stop,composer:()=>({}),composerText:()=>flags.draft,
  chatGPTComposerAttachmentState:()=>flags.attachments,latestAssistantStrictlyAfterLatestUser:()=>scope,
  analysisAnswerNode:x=>x,motionResponseState:()=>state,visible:()=>true,extractMotionJson:()=>JSON.parse(state.text),
  userTurns:()=>[{cloneNode:()=>({textContent:flags.request,querySelectorAll:()=>[]})}],
  analysisContentHash:s=>require('crypto').createHash('sha256').update(s).digest('hex').slice(0,8),
  location:{href:'https://chatgpt.com/c/fixture'},report:async()=>{},
  chrome:{runtime:{sendMessage:async m=>{sends++;assert(c.completedResponseRefreshGuard(m));return {ok:true,refresh_scheduled:true};}}}});
 vm.runInContext(contentCode,c);
 return {c,state,flags,now:n=>{now=n;},sends:()=>sends};
}
(async()=>{
 let cases=0;
 for(const defect of ['', 'gemini','draft','attachment','loading','busy','streaming','partial','wrong_job','wrong_request','no_stop','helper']){
  const f=fixture(),c=f.c;
  if(defect==='gemini')c.IS_GEMINI=true;
  if(defect==='draft')f.flags.draft='unsent';
  if(defect==='attachment')f.flags.attachments.count=1;
  if(defect==='loading')f.flags.attachments.busy=true;
  if(defect==='busy')f.state.busy=true;
  if(defect==='streaming')f.flags.progress=true;
  if(defect==='partial')f.state.incomplete=true;
  if(defect==='wrong_job')f.state.text=JSON.stringify({...value,job_id:'STORY-OTHER'});
  if(defect==='wrong_request')f.flags.request='another request';
  if(defect==='no_stop')f.flags.stop=false;
  if(defect==='helper')c.activeRepairKey='repair';
  assert.equal(Boolean(c.completedChatGPTMotionSnapshot(context)),!defect,defect);cases++;
 }
 const f=fixture(),probe={};
 await f.c.refreshCompletedChatGPTMotion(probe,context,'next prompt');f.now(9000);
 await f.c.refreshCompletedChatGPTMotion(probe,context,'next prompt');assert.equal(f.sends(),0);f.now(17000);
 await assert.rejects(f.c.refreshCompletedChatGPTMotion(probe,context,'next prompt'),e=>e.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED');
 assert.equal(f.sends(),1);f.now(99000);await f.c.refreshCompletedChatGPTMotion(probe,context,'next prompt');assert.equal(f.sends(),1);cases++;
 for(const ready of [true,false]){
  const image=fixture();image.state.text='';image.state.ready=false;
  image.c.lastCommittedChatGPTImage={job_id:context.job_id,index:3,proof:{prompt:'saved-image-request'}};
  image.c.motionRequestMatches=()=>true;
  image.c.chatGPTStoryImageSnapshot=()=>({reason:ready?'image_ready':'image_loading',images:[{}]});
  image.c.storyImageAssetKey=()=> 'saved-asset';
  assert.equal(Boolean(image.c.completedChatGPTMotionSnapshot(context)),ready);cases++;
 }
 for(const defect of ['', 'used','requested','wrong_context','wrong_prompt','cancel','url','late_draft','late_owner','failed_reload']){
  const store={},events=[];let live=0,owners=0,ack=null;
  const message={provider:'chatgpt',job_id:context.job_id,index:3,run_id:'RUN-ONE',conversation_url:'https://chatgpt.com/c/fixture',
   signature:'aabbccdd',context_id:context.context_id,pending_request:'next prompt'};
  const key=`smartflowCompletedResponseRefresh:${context.job_id}:3:aabbccdd`;
  if(defect==='used')store[key]={phase:'claimed'};
  if(defect==='cancel')store[`smartflowChatGPTStoryRefreshCancelled:${context.job_id}`]='RUN-ONE';
  const c=vm.createContext({crypto,BRIDGE:'offline',
   assertStoryCheckpointOwner:async()=>{owners++;if(defect==='late_owner'&&owners===2)throw Error('owner changed');},
   chrome:{storage:{local:{get:async key=>({[key]:store[key]}),set:async values=>Object.assign(store,values)}},
    tabs:{get:async()=>({id:9,url:defect==='url'?'https://chatgpt.com/c/other':message.conversation_url}),
     sendMessage:async(_id,m)=>{live++;return {ok:true,allowed:!(defect==='late_draft'&&live===2),challenge:m.challenge,signature:m.signature};},
     reload:async id=>{assert.equal(id,9);events.push('reload');if(defect==='failed_reload')throw Error('reload failed');}}},
   bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,context:{context_id:defect==='wrong_context'?'different':context.context_id},
    record:{phase:defect==='requested'?'requested':'preparing',request:defect==='wrong_prompt'?'other':'next prompt'}})}),
   waitForAIRefreshReady:async id=>{assert.equal(id,9);events.push('loaded');},
   startAIWebJob:async(job,reuse,provider,fresh,run,guard)=>{
    assert.equal(job,context.job_id);assert.equal(reuse,true);assert.equal(provider,'chatgpt');assert.equal(fresh,false);assert.equal(run,'RUN-ONE');
    await guard(9);events.push('resume');},
   reportWebActionProgress:async()=>events.push('review')});
  const navigation=require('./shared_refresh_fixture_439.cjs').install(c);
  vm.runInContext(backgroundCode,c);
  const action=()=>c.refreshCompletedChatGPTResponse(message,{tab:{id:9}},r=>{ack=r;});
  if(defect&&defect!=='failed_reload'){await assert.rejects(action());assert.deepEqual(events,[]);assert.equal(ack,null);}
  else {await action();assert.equal(ack.refresh_scheduled,true);assert.deepEqual(events,defect?['reload','review']:['reload','loaded','resume']);
   if(defect==='failed_reload'){
    // Reload outcome is unknown: a later committed document reconciles the
    // durable claim without a second Chrome reload or provider submission.
    navigation.setDocument('new-document');await action();assert.equal(store[key].phase,'resumed');
   }else await assert.rejects(action());
   assert.equal(events.filter(x=>x==='reload').length,1);}
  cases++;
 }
 assert(content.includes("if(error?.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED')throw error;"));
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
