// Actual-source service recovery; all Chrome, provider and file effects are fixtures.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {setup,content,dispatch,key,candidate,source}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]
 +';return {setup,content,dispatch,key,candidate,source};')(require,__dirname);
const proof={failure_code:'FLOW_GENERATION_FAILED',confirmed_uncharged_failure:true,failure_reason:'หมดเวลาสร้าง โปรดลองอีกครั้ง'};
function controller(phase='ready',patch={}){
 const f=content(phase,patch);
 Object.assign(f.c.pkg,{mode:'story',flow_repair:{enabled:true,revise_story:true,fresh_project_on_repair:true,continuous:true}});
 f.c.document={body:{innerText:''}};f.c.confirmationKind=()=>'';
 return f;
}
(async()=>{
 let cases=0;
 for(const provider of ['chatgpt','gemini']){
  const f=await setup(provider,proof);
  await f.call({action:'prepare_reference'});await f.call({action:'prepare_reference'});
  assert.equal(f.events.filter(x=>x==='http://fixture/scene.png').length,1);
  assert.equal(f.storage[key].repair_reference.source,'original');
  await f.call({action:'fresh_project'});await f.call({action:'fresh_project'});
  assert.equal(f.events.filter(x=>x==='navigate').length,1);
  assert.deepEqual(f.storage.smartpostFlowSubmissionReceipts,{old:{clicked:true}});
  assert((await f.call({action:'claim_fresh_project_click'})).claimed);
  assert.equal((await f.call({action:'claim_fresh_project_click'})).claimed,false);
  await assert.rejects(f.call({action:'bind_fresh_project'}));
  f.tabs.get(5).url=f.sender.tab.url='https://flow.google.com/project/new';
  await f.call({action:'bind_fresh_project'});
  f.c.flowRunStorageKey=()=> 'run-key';f.storage['run-key']='RUN-1';
  vm.runInContext(source.slice(source.indexOf('async function getFlowPackage('),source.indexOf('async function pageType(')),f.c);
  const p=(await f.c.getFlowPackage('STORY-TEST',1)).package;
  assert.equal(p.image_urls[0],'http://fixture/scene.png');assert.equal(p.video_prompt,candidate.prompt);
  assert.equal(p.flow_repair_receipt_key,`STORY-TEST:1:RUN-1:repair:${f.message.request_id}`);
  const first=controller('missing');first.c.pkg.image_ai_provider=provider;await first.run(proof);
  const start=first.messages.find(m=>m.action==='start');assert(start);assert.equal(start.provider,provider);
  assert(start.request.includes('exactly one complete prompt'));assert(start.request.includes('needs_review=true'));
  assert(!first.messages.some(m=>m.action==='start_alternative'));cases++;
 }
 for(const phase of ['requested','rewrite_sent','starting','cancelled','completed']){
  const f=controller(phase);await f.run(proof);
  assert(!f.messages.some(m=>['start','start_alternative','fresh_project'].includes(m.action)));cases++;
 }
 for(const patch of [{needs_review:true},{reference_compatible:false},{material_change:true},{prompt:'too short'}]){
  const f=controller('ready',patch);await f.run(proof);
  assert(f.messages.some(m=>m.action==='pause'));
  assert(!f.messages.some(m=>['start_alternative','fresh_project'].includes(m.action)));cases++;
 }
 for(const late of ['thumbnail','video','progress','render','approval','cancel']){
  const f=controller();let prepared=false;
  const send=f.c.chrome.runtime.sendMessage;
  f.c.chrome.runtime.sendMessage=async message=>{
   const reply=await send(message);
   if(message.action==='prepare_reference'){prepared=true;if(late==='cancel')f.c.automationPaused=true;}
   return reply;
  };
  f.c.generationSnapshot=()=>({videoCount:prepared&&late==='video'?1:0,
   resultCardCount:prepared&&late==='thumbnail'?1:0,activeProgress:prepared&&late==='progress',activeRenderControl:prepared&&late==='render'});
  f.c.confirmationKind=()=>prepared&&late==='approval'?'credit':'';
  await f.run(proof);assert(prepared);
  assert(!f.messages.some(m=>m.action==='fresh_project'));
  assert.equal(f.messages.some(m=>m.action==='pause'),late!=='cancel');cases++;
 }
 {
  const f=controller();f.c.generationSnapshot=()=>({videoCount:0,resultCardCount:1});await f.run(proof);
  assert(f.messages.some(m=>m.action==='pause'));assert(!f.messages.some(m=>m.action==='prepare_reference'));cases++;
 }
 {
  const f=controller();await f.run(proof);
  assert.deepEqual(f.messages.filter(m=>m.type==='FLOW_SCENE_REPAIR').map(m=>m.action),['status','prepare_reference','fresh_project']);cases++;
 }
 {
  const f=controller('submitted');const send=f.c.chrome.runtime.sendMessage;
  f.c.chrome.runtime.sendMessage=async message=>{
   const reply=await send(message);
   if(message.action==='status')return {...reply,alternative:true,failure_id:'previous-failure'};
   return reply;
  };
  await f.run(proof);assert(f.messages.some(m=>m.action==='start'));
  assert(!f.messages.some(m=>m.action==='start_alternative'||m.action==='pause'));cases++;
 }
 {
  const repair={phase:'submit_ready',round:1,request_id:'R-service',run_id:'RUN-A',owner_tab:7,
   project_path:'/project/p',fresh_project:{phase:'bound',target_path:'/project/p'},candidate};
  const options={storage:{receipts:{'STORY-TEST:1:RUN-A':{requestedAt:1}},[key]:repair},context:{URL,
   flowRepairKey:()=>key,assertFlowRepairOwner:async()=>{},sender:{tab:{id:7,windowId:3,url:'https://flow.google.com/project/p'}},
   message:{type:'CLICK_FLOW_GENERATE',job_id:'STORY-TEST',shot_index:1,run_id:'RUN-A',repair_request_id:'R-service',prompt_guard:candidate.prompt}}};
  const first=await dispatch(options);assert.equal(first.result.ok,true);
  assert(first.storage.receipts['STORY-TEST:1:RUN-A']);assert(first.storage.receipts['STORY-TEST:1:RUN-A:repair:R-service']);
  const again=await dispatch({...options,storage:first.storage});assert.equal(again.result.duplicateBlocked,true);cases++;
 }
 console.log(JSON.stringify({ok:true,cases,liveSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
