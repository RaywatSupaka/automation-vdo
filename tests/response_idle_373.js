const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8'),bg=fs.readFileSync('browser_extension/background.js','utf8');
function section(source,start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const waits=section(content,'  async function waitForResponseIdle(', '  function assertNotCancelled(');
const snapshots=section(content,'  function completedChatGPTMotionSnapshot(', '  function normalizeOptionalCover(');
const generate=section(content,'  async function generateOneImage(', '  async function runProductImages(');
const background=section(bg,'const completedResponseRefreshLocks =','async function refreshStoryChatGPTResult(');
const job='STORY-FIXTURE',url='https://chatgpt.com/c/fixture',run='RUN-ONE';
const result={job_id:job,index:4,context_id:'saved-context',prompt:'The reviewer gently sits in the chair with natural motion and camera movement.',needs_review:false,reference_compatible:true,material_change:false};
const next={job_id:job,index:4,next_image_index:5};
function pageFixture(){
 let now=1000,begin=0,refresh=0;
 const flags={draft:'',stop:true,progress:false,request:JSON.stringify(result),attachments:{count:0}};
 // Observed bug: full motion JSON but NO response action buttons, global Stop.
 const state={completed:false,ready:true,incomplete:false,busy:false,text:JSON.stringify(result)};
 const scope={querySelectorAll:()=>flags.progress?[{}]:[]},reports=[];
 const c=vm.createContext({IS_GEMINI:false,activeProductOutfitMode:'',activeRepairKey:'',activeCoverRequest:null,cancelRequested:false,
  activeJobId:job,activeRunId:run,lastCommittedChatGPTImage:null,completedResponseRefreshGuard:null,
  Date:{now:()=>now},analysisResponseStopButton:()=>flags.stop,stopButtonVisible:()=>flags.stop,
  assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancel');},sleep:async n=>{now+=n;},
  composer:()=>({}),composerText:()=>flags.draft,chatGPTComposerAttachmentState:()=>flags.attachments,
  latestAssistantStrictlyAfterLatestUser:()=>scope,analysisAnswerNode:x=>x,motionResponseState:()=>state,visible:()=>true,
  extractMotionJson:()=>JSON.parse(state.text),userTurns:()=>[{cloneNode:()=>({textContent:flags.request,querySelectorAll:()=>[]})}],
  analysisContentHash:s=>crypto.createHash('sha256').update(s).digest('hex').slice(0,8),location:{href:url},
  report:async(step,_message,count)=>reports.push({step,count}),
  chrome:{runtime:{sendMessage:async m=>{refresh++;assert.equal(m.type,'RELOAD_CHATGPT_COMPLETED_RESPONSE');
   assert.equal(m.next_image_index,5);assert.equal(m.context_id,result.context_id);
   assert.deepEqual(JSON.parse(m.completed_result),result);assert(c.completedResponseRefreshGuard(m));
   return {ok:true,refresh_scheduled:true};}}}});
 vm.runInContext(snapshots+waits+generate,c);
 const receipt={begin:async()=>{begin++;throw Error('BEGIN_REACHED');}};
 return {c,flags,state,reports,receipt,begin:()=>begin,refresh:()=>refresh,now:()=>now};
}
(async()=>{
 let cases=0;
 // Exact production call chain: image5 -> idle wait -> saved-scene refresh.
 let f=pageFixture();
 await assert.rejects(f.c.generateOneImage('next image prompt',[],5,'story',4,'','',null,f.receipt),e=>e.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED');
 assert.equal(f.begin(),0);assert.equal(f.refresh(),1);assert(f.now()>=16000);
 assert(f.reports.length>2);assert(f.reports.every(row=>row.count===4));cases++;
 // Already idle continues to begin, does not unnecessarily reload/send.
 f=pageFixture();f.flags.stop=false;
 await assert.rejects(f.c.generateOneImage('next image prompt',[],5,'story',4,'','',null,f.receipt),/BEGIN_REACHED/);
 assert.equal(f.begin(),1);assert.equal(f.refresh(),0);cases++;
 // Generic first-image/cover/helper calls have no synthetic outer count global.
 for(const provider of [false,true]){
  f=pageFixture();f.c.IS_GEMINI=provider;let sleeps=0;
  f.c.sleep=async()=>{if(++sleeps===3)f.flags.stop=false;};
  await f.c.waitForResponseIdle();assert(f.reports.every(row=>row.count===0));assert.equal(f.refresh(),0);cases++;
 }
 for(const defect of ['gemini','draft','attachment','busy','streaming','partial','wrong_job','wrong_scene','wrong_request','helper','cover','cancel']){
  f=pageFixture();
  if(defect==='gemini')f.c.IS_GEMINI=true;
  if(defect==='draft')f.flags.draft='unsent';
  if(defect==='attachment')f.flags.attachments.count=1;
  if(defect==='busy')f.state.busy=true;
  if(defect==='streaming')f.flags.progress=true;
  if(defect==='partial')f.state.incomplete=true;
  if(defect==='wrong_job')f.state.text=JSON.stringify({...result,job_id:'STORY-OTHER'});
  if(defect==='wrong_scene')f.state.text=JSON.stringify({...result,index:3});
  if(defect==='wrong_request')f.flags.request='different user';
  if(defect==='helper')f.c.activeRepairKey='repair';
  if(defect==='cover')f.c.activeCoverRequest={};
  if(defect==='cancel')f.c.cancelRequested=true;
  assert.equal(f.c.completedChatGPTMotionSnapshot(next),null,defect);cases++;
 }
 // Missing action buttons remain insufficient for the older next-motion path.
 f=pageFixture();assert.equal(f.c.completedChatGPTMotionSnapshot({...next,next_image_index:undefined}),null);cases++;
 // Cancellation during wait, and changing content reset stability instead of refreshing.
 f=pageFixture();f.c.sleep=async()=>{f.c.cancelRequested=true;};
 await assert.rejects(f.c.waitForResponseIdle(1,next,'next',4),/cancel/);assert.equal(f.refresh(),0);cases++;
 f=pageFixture();const probe={};
 for(let i=0;i<40;i++){f.state.text=JSON.stringify({...result,prompt:result.prompt+i});
  await f.c.refreshCompletedChatGPTMotion(probe,next,'next',4);await f.c.sleep(1000);}
 assert.equal(f.refresh(),0);cases++;
 for(const defect of ['', 'used','requested','no_result','wrong_context','wrong_result','review','wrong_url','unfinished',
   'next_prepared','next_accepted','late_claim','late_progress','cancel','bad_next','bad_json','offline','failed_reload']){
  const store={},events=[];let live=0,owners=0,ack=null;
  const message={provider:'chatgpt',job_id:job,index:4,run_id:run,conversation_url:url,signature:'aabbccdd',
   purpose:'next_scene_image',next_image_index:5,context_id:result.context_id,completed_result:JSON.stringify(result),pending_request:'next image prompt'};
  const key=`smartflowCompletedResponseRefresh:${job}:4:aabbccdd:next-image`,receiptKey=`smartpostStoryGeneratedImage:chatgpt:${job}:5`;
  if(defect==='used')store[key]={phase:'claimed'};
  if(defect==='cancel')store[`smartflowChatGPTStoryRefreshCancelled:${job}`]=run;
  if(defect==='next_prepared'||defect==='next_accepted')store[receiptKey]={send_phase:defect.slice(5)};
  if(defect==='bad_next')message.next_image_index=6;
  if(defect==='bad_json')message.completed_result='{';
  const c=vm.createContext({crypto:crypto.webcrypto,BRIDGE:'offline',
   assertStoryCheckpointOwner:async()=>{owners++;if(defect==='late_claim'&&owners===2)store[receiptKey]={send_phase:'accepted'};},
   chrome:{storage:{local:{get:async key=>({[key]:store[key]}),set:async values=>Object.assign(store,values)}},
    tabs:{get:async()=>({id:9,url}),sendMessage:async(_id,m)=>{live++;return {ok:true,allowed:!(defect==='late_progress'&&live===2),challenge:m.challenge,signature:m.signature};},
     reload:async id=>{assert.equal(id,9);events.push('reload');if(defect==='failed_reload')throw Error('reload failed');}}},
   bridgeFetch:async(path,options)=>{
    assert.equal(JSON.parse(options.body).action,'status');if(defect==='offline')throw Error('offline');
    const body=path.endsWith('/scene-gate')?{ok:true,phase:defect==='unfinished'?'voice':'complete'}:
     {ok:true,context:{context_id:defect==='wrong_context'?'other':result.context_id},record:{phase:defect==='requested'?'requested':'ready',
      conversation_url:defect==='wrong_url'?'https://chatgpt.com/c/other':url,
      result:defect==='no_result'?null:{...result,...(defect==='wrong_result'?{prompt:'different'}:defect==='review'?{needs_review:true}:{})}}};
    return {ok:true,json:async()=>body};},
   waitForAIRefreshReady:async()=>events.push('loaded'),startAIWebJob:async(id,reuse,provider,fresh,r,guard)=>{
    assert.equal(id,job);assert.equal(reuse,true);assert.equal(provider,'chatgpt');assert.equal(fresh,false);assert.equal(r,run);
    await guard(9);events.push('resume');},reportWebActionProgress:async()=>events.push('review')});
  const navigation=require('./shared_refresh_fixture_439.cjs').install(c);
  vm.runInContext(background,c);const action=()=>c.refreshCompletedChatGPTResponse(message,{tab:{id:9}},r=>{ack=r;});
  if(defect&&defect!=='failed_reload'){await assert.rejects(action(),undefined,defect);assert.deepEqual(events,[]);assert.equal(ack,null);}
  else{await action();assert(ack.refresh_scheduled);assert.deepEqual(events,defect?['reload','review']:['reload','loaded','resume']);
   if(defect==='failed_reload'){navigation.setDocument('new-document');await action();assert.equal(store[key].phase,'resumed');}
   else await assert.rejects(action());
   assert.equal(events.filter(e=>e==='reload').length,1);}
  cases++;
 }
 // Call-site contracts cover counts without relocating run-local mutable state.
 assert(!waits.includes('lastCompletedImageCount'));
 assert(content.includes('waitForResponseIdle(420000,motionContext,text,completedCount)'));
 assert(content.includes("waitForResponseIdle(420000,null,'',completedCount)"));
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
