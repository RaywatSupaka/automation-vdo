// Regression from installed 402: Flow home + desktop proposal-review checkpoint,
// then exact source project with only its uploaded image (error card disappeared).
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {setup,key}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]
 +';return {setup,key};')(require,__dirname);
const flow=fs.readFileSync('browser_extension/flow.js','utf8');
const background=fs.readFileSync('browser_extension/background.js','utf8');
async function prepared(state='missing'){
 const f=await setup();
 const checkpoint={...f.storage[key],phase:'needs_review',alternative:true,alternative_stage:'proposal',
  error:'ภาพทางเลือกต้องเปลี่ยนสาระหรือยังต้องตรวจ • completed proposal',digest:'review403',helper_tab:0};
 const permit={job_id:'STORY-TEST',token:'fixture-only',index:1,request_id:checkpoint.request_id,
  event_digest:checkpoint.digest,review_checkpoint:checkpoint};
 if(state==='missing')delete f.storage[key];else f.storage[key]={...checkpoint,phase:state};
 const fetch=f.c.bridgeFetch;
 f.c.bridgeFetch=async(url,opts)=>url.includes('/flow-package')?{ok:true,json:async()=>({ok:true,package:{
  job_id:'STORY-TEST',shot_index:1,image_ai_provider:'chatgpt',image_urls:['http://fixture/scene.png'],manual_flow_repair:permit}})}:fetch(url,opts);
 return Object.assign(f,{checkpoint,permit});
}
(async()=>{
 let cases=0;
 for(const state of ['missing','cancelled','needs_review']){
  const f=await prepared(state),before=JSON.stringify(f.storage.smartpostFlowSubmissionReceipts);
  f.sender.tab.url=f.tabs.get(5).url='https://flow.google.com/';
  const redirected=await f.call({action:'manual_restart',token:f.permit.token});
  //405 retires the automatic Home -> failed-project redirect entirely.
  assert.equal(redirected.phase,'fresh_start_pending');
  assert.equal(f.sender.tab.url,'https://flow.google.com/');
  assert.equal(f.events.filter(e=>e==='navigate').length,0);
  // Keep separate coverage for legacy records already at their source page.
  f.sender.tab.url=f.tabs.get(5).url='https://flow.google.com/project/old';
  const resumed=await f.call({action:'manual_restart',token:f.permit.token});
  assert.equal(resumed.phase,'manual_restart');
  assert.equal(resumed.manual_resume_proof.event_digest,'review403');
  assert.equal((await f.call({action:'manual_restart',token:f.permit.token})).manual_resume_proof.event_digest,'review403');
  assert.equal(JSON.stringify(f.storage.smartpostFlowSubmissionReceipts),before);cases++;
 }
 for(const change of ['digest','request','job','path','active','unknown-image','foreign-project']){
  const f=await prepared(change==='active'?'rewrite_sent':change==='unknown-image'?'cancelled':'missing');
  f.sender.tab.url=f.tabs.get(5).url='https://flow.google.com/';
  if(change==='digest')f.permit.event_digest='other';
  if(change==='request')f.permit.request_id='other';
  if(change==='job')f.permit.job_id='STORY-OTHER';
  if(change==='path')f.checkpoint.project_path='//outside.invalid/project/old';
  if(change==='unknown-image'){f.checkpoint.alternative_stage='image_sent';f.storage[key].alternative_stage='image_sent';}
  if(change==='foreign-project')f.sender.tab.url=f.tabs.get(5).url='https://flow.google.com/project/foreign';
  await assert.rejects(f.call({action:'manual_restart',token:f.permit.token}));
  assert(!f.events.includes('navigate'));cases++;
 }
 // Full handoff: restored review -> one new helper -> saved compliant new
 // image/prompt -> fresh Flow project. No fake no-charge proof and no replay.
 {
  const f=await prepared('needs_review');
  const restarted=await f.call({action:'manual_restart',token:f.permit.token});
  const proof=restarted.manual_resume_proof;
  f.storage.smartpostFlowMonitor={jobId:'STORY-TEST',runId:'RUN-1',shotIndex:1,startedAt:403,
   storyPolicyTerminal:{repair_eligible:true,failure_code:'FLOW_REPAIR_REVIEW',failure_card_fingerprint:'fp',
    failure_reason:restarted.reason,projectPath:'/project/old',manual_review_digest:proof.event_digest,
    manual_review_request_id:proof.request_id}};
  const fetch=f.c.bridgeFetch;let begins=0;
  f.c.bridgeFetch=async(url,options)=>{
   const body=JSON.parse(options?.body || '{}');
   if(body.replacement_action==='begin'){
    begins++;assert.equal(body.manual_resume_token,f.permit.token);
    return {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16'},
     replacement:{rebuild_scene:true,revise_story:true,creative_revision_version:1,creative_round:0,phase:'requested'}})};
   }return fetch(url,options);
  };
  const started=await f.call({action:'start_alternative',rebuild_scene:true,revise_story:true,
   creative_revision_version:1,failure_id:'403:fp'});
  assert.equal(started.phase,'rewrite_sent');assert.equal(started.manual_resume_proof.event_digest,'review403');
  await f.call({action:'start_alternative',rebuild_scene:true,revise_story:true,failure_id:'403:fp'});
  assert.equal(begins,1);
  Object.assign(f.storage[key],{phase:'ready',candidate:{prompt:'New benign 9:16 scene with validated revised dialogue.',
   needs_review:false,reference_compatible:true,material_change:false},replacement:{image_url:'http://fixture/new.png'}});
  f.storage.smartpostFlowReferenceFile={jobId:'STORY-TEST',shotIndex:1,replacement_id:started.request_id};
  await f.call({action:'fresh_project',request_id:started.request_id});
  assert.equal(f.sender.tab.url,'https://flow.google.com/');
  assert(f.storage.smartpostFlowSubmissionReceipts.old);cases++;
 }
 //404 supersedes the old-project Desktop routing with a fresh controller.
 // Both real command branches and preserved tabs/receipts are covered by
 // flow_fresh_start_404.js. Keep these legacy handshake guards for old records.
 // Exercise the actual content entry with the observed empty workspace and
 // vanished card. A permit is not authorization to discard an active/draft result.
 for(const block of ['', 'active','render','video','result','approval','draft','attached','loading','digest','project']){
  const f=await prepared('needs_review');
  const reply=await f.call({action:'manual_restart',token:f.permit.token});
  let repairs=0,inspections=0,starts=0;const reports=[],saved={};
  const c=vm.createContext({automationPaused:false,Date,setTimeout:fn=>fn(),
   pkg:{job_id:'STORY-TEST',shot_index:1,run_id:'RUN-1',manual_flow_repair:{...f.permit,
    event_digest:block==='digest'?'wrong':f.permit.event_digest}},
   location:{pathname:block==='project'?'/project/wrong':'/project/old'},document:{body:{innerText:''}},
   confirmationKind:()=>block==='approval'?'credit':'',
   findPromptEditor:()=>block==='loading'?null:{innerText:block==='draft'?'Unsent private draft':' '},
   promptHasAttachedMedia:()=>block==='attached',
   generationSnapshot:()=>({videoCount:block==='video'?1:0,resultCardCount:block==='result'?1:0,
    activeProgress:block==='active',activeRenderControl:block==='render',visibleFailureCards:[]}),
   chrome:{runtime:{sendMessage:async()=>{starts++;return starts<3?{ok:true,phase:'starting'}:reply;}},
    storage:{local:{set:async patch=>Object.assign(saved,patch)}}},
   recoverFlowPolicy:async()=>{repairs++;},inspectGenerationState:async()=>{inspections++;},monitorGeneration:()=>{},
   report:async(...args)=>reports.push(args)});
  vm.runInContext(flow.slice(flow.indexOf('  async function autoPrepare('),flow.indexOf('  function stopGenerationMonitor(')),c);
  await c.autoPrepare();assert.equal(starts,3);assert.equal(repairs,block?0:1,block);
  if(!block){
   const terminal=saved.smartpostFlowMonitor.storyPolicyTerminal;
   assert.equal(terminal.failure_code,'FLOW_REPAIR_REVIEW');
   assert.equal(terminal.confirmed_uncharged_failure,undefined);
   assert(f.c.manualFlowReviewProofMatches(reply,terminal));
   assert(!f.c.manualFlowReviewProofMatches({...reply,manual_token:''},terminal));
   assert(!f.c.manualFlowReviewProofMatches(reply,{...terminal,manual_review_digest:'other'}));
   assert.equal(inspections,1);
  }else assert(reports.some(([step])=>step==='error'));cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
