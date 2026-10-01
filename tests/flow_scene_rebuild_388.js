// Actual controller/background functions. Browser, bridge and provider effects are isolated fixtures.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {setup,content,key,candidate,source}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]
 +';return {setup,content,key,candidate,source};')(require,__dirname);
const service={failure_code:'FLOW_GENERATION_FAILED',confirmed_uncharged_failure:true,failure_reason:'สร้างเสียงไม่สำเร็จ โปรดลองใช้พรอมต์อื่น'};
const policy={failure_code:'FLOW_POLICY_BLOCKED',failure_reason:'ภาพต้องเปลี่ยนเป็นเหตุการณ์ที่ปลอดภัย'};
function controller(phase='missing',recordPatch={},job='STORY-TEST'){
 const f=content(phase);
 Object.assign(f.c.pkg,{job_id:job,mode:'story',flow_repair:{enabled:true,continuous:true,
  rebuild_scene_on_failure:true,same_image_only:false,revise_story:job.startsWith('STORY-'),creative_revision_version:job.startsWith('STORY-')?1:0,fresh_project_on_repair:true}});
 f.c.document={body:{innerText:''}};f.c.confirmationKind=()=>'';
 const send=f.c.chrome.runtime.sendMessage;
 f.c.chrome.runtime.sendMessage=async message=>{
  const result=await send(message);return message.action==='status'?{...result,...recordPatch}:result;
 };
 return f;
}
(async()=>{
 let cases=0;
 for(const job of ['STORY-TEST','JOB-TEST'])for(const provider of ['chatgpt','gemini'])for(const proof of [service,policy]){
  const f=controller('missing',{candidate:null},job);f.c.pkg.image_ai_provider=provider;await f.run(proof);
  const request=f.messages.find(m=>m.action==='start_alternative');assert(request);
  assert.equal(request.rebuild_scene,true);assert.equal(request.revise_story,job.startsWith('STORY-'));
  assert.equal(request.creative_revision_version,job.startsWith('STORY-')?1:0);
  assert.equal(request.provider,provider);assert.equal(request.reason,proof.failure_reason);
  assert.equal(request.last_prompt,'original prompt');assert(!f.messages.some(m=>m.action==='start'));cases++;
 }
 for(const phase of ['starting','requested','rewrite_sent','cancelled','completed']){
  const f=controller(phase,{alternative:true});await f.run(service);
  assert(!f.messages.some(m=>['start','start_alternative','fresh_project'].includes(m.action)));cases++;
 }
 for(const job of ['STORY-TEST','JOB-TEST']){
  const f=controller('submitted',{alternative:true,failure_id:'older'},job);await f.run(service);
  assert(f.messages.some(m=>m.action==='start_alternative'));cases++;
  const duplicate=controller('submitted',{alternative:true,failure_id:'1:fp'},job);await duplicate.run(service);
  assert(!duplicate.messages.some(m=>m.action==='start_alternative'));cases++;
 }
 for(const phase of ['ready','needs_review']){
  const f=controller(phase,{alternative:true,candidate:{...candidate,needs_review:true}});await f.run(service);
  assert(f.messages.some(m=>m.action==='pause'));assert(!f.messages.some(m=>m.action==='start_alternative'));cases++;
 }
 for(const block of ['paused','foreign','readonly','not-terminal']){
  const f=controller();
  if(block==='paused')f.c.automationPaused=true;
  if(block==='readonly')f.c.readOnlyInspection=true;
  if(block==='foreign')f.c.chrome.runtime.sendMessage=async()=>({active:false});
  await f.run({...service,...(block==='not-terminal'?{repair_eligible:false}:{})});
  assert(!f.messages.some(m=>m.action==='start_alternative'));cases++;
 }
 // Upgrading does not discard an already approved/in-flight text repair.
 {const f=controller('ready');await f.run(service);assert(f.messages.some(m=>m.action==='prepare_reference'));
  assert(f.messages.some(m=>m.action==='fresh_project'));assert(!f.messages.some(m=>m.action==='start_alternative'));cases++;}
 {const f=controller('needs_review',{exhausted:true,pause_reason:'ครบสองรอบซ่อมพรอมต์แล้ว'});await f.run(service);
  assert(f.messages.some(m=>m.action==='start_alternative'));assert(!f.messages.some(m=>m.action==='start'));cases++;}
 for(const provider of ['chatgpt','gemini'])for(const job of ['STORY-TEST','JOB-TEST']){
  const f=await setup(provider,service),newKey=key.replace('STORY-TEST',job);
  f.storage[newKey]=f.storage[key];if(newKey!==key)delete f.storage[key];
  f.storage[newKey].job_id=job;f.storage[newKey].phase='submitted';
  f.storage.smartpostFlowMonitor.jobId=job;f.storage.smartpostFlowMonitor.startedAt=1;
  Object.assign(f.message,{job_id:job,action:'start_alternative',rebuild_scene:true,
   revise_story:job.startsWith('STORY-'),last_prompt:'The motion prompt of the failed image.'});
  const fetch=f.c.bridgeFetch;let begins=0;
  f.c.bridgeFetch=async(url,options)=>{
   const body=JSON.parse(options?.body || '{}');
   if(body.replacement_action==='begin'){
    begins++;assert.equal(body.rebuild_scene,true);assert(body.previous_request_id);
    return {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16',previous_visuals:[]},
     replacement:{rebuild_scene:true,revise_story:job.startsWith('STORY-'),phase:'requested'}})};
   }return fetch(url,options);
  };
  for(let round=1;round<=4;round++){
   f.storage.smartpostFlowMonitor.startedAt=round;f.message.failure_id=`${round}:fp`;
   const r=await f.call();assert(r.alternative);assert(r.rebuild_scene);assert.equal(r.phase,'rewrite_sent');
   assert(r.request.includes('exactly ONE'));assert(r.request.includes(f.message.last_prompt));
   assert(r.request.includes('preserve product identity') || r.request.includes('preserve product identity'.replace('p','P')));
   assert.deepEqual(Array.from(r.image_urls),['http://fixture/scene.png']);
   const opened=f.events.filter(x=>x==='open').length;
   await f.call();assert.equal(f.events.filter(x=>x==='open').length,opened);
   Object.assign(f.storage[newKey],{phase:'submitted'});
   await f.call();assert.equal(f.events.filter(x=>x==='open').length,opened);
  }
  assert.equal(begins,4);assert.deepEqual(f.storage.smartpostFlowSubmissionReceipts,{old:{clicked:true}});
  await assert.rejects(f.call({failure_id:'forged-failure'}));assert.equal(begins,4);
  f.storage[newKey].phase='cancelled';await f.call();assert.equal(begins,4);
  f.storage.smartpostFlowMonitor.storyPolicyTerminal.confirmed_uncharged_failure=false;
  await assert.rejects(f.call());assert.equal(begins,4);cases++;
 }
 // Actual package chooses new contract for both job families, excludes Presenter IDs.
 for(const job of ['STORY-TEST','JOB-TEST','PRESENTER-TEST']){
  const f=await setup();f.c.flowRunStorageKey=()=> 'run-key';f.storage['run-key']='RUN-1';
  vm.runInContext(source.slice(source.indexOf('async function getFlowPackage('),source.indexOf('async function pageType(')),f.c);
  const p=(await f.c.getFlowPackage(job,1)).package;
  if(job.startsWith('PRESENTER'))assert.equal(p.flow_repair,null);
  else{assert.equal(p.flow_repair.rebuild_scene_on_failure,true);assert.equal(p.flow_repair.same_image_only,false);assert.equal(p.flow_repair.creative_revision_version,job.startsWith('STORY-')?1:0);}
  cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
