// Real worker functions, isolated Chrome/desktop fixture. No user browser or Send.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {setup,key}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]
 +';return {setup,key};')(require,__dirname);
const background=fs.readFileSync('browser_extension/background.js','utf8');
const flow=fs.readFileSync('browser_extension/flow.js','utf8');
async function fixture(state='missing'){
 const f=await setup(), calls=[];
 const checkpoint={...f.storage[key],phase:'needs_review',alternative:true,alternative_stage:'proposal',
  error:'ภาพทางเลือกต้องเปลี่ยนสาระหรือยังต้องตรวจ • completed proposal',digest:'review404',helper_tab:0};
 const permit={job_id:'STORY-TEST',token:'fixture-only',index:1,request_id:checkpoint.request_id,
  event_digest:checkpoint.digest,review_checkpoint:checkpoint};
 const pkg={job_id:'STORY-TEST',shot_index:1,image_ai_provider:'chatgpt',image_urls:['http://fixture/scene.png'],
  mode:'story',run_id:'RUN-1',manual_flow_repair:permit,flow_repair:{enabled:true,rebuild_scene_on_failure:true}};
 if(state==='missing')delete f.storage[key];else f.storage[key]={...checkpoint,phase:state};
 const command={job_id:'STORY-TEST',shot_index:1,run_id:'RUN-1'};
 const create=f.c.chrome.tabs.create;
 f.c.chrome.tabs.create=async opts=>{calls.push(['create',opts.url]);return create(opts);};
 f.c.chrome.tabs.update=async(id,opts)=>{calls.push(['navigate',id,opts.url]);return Object.assign(f.tabs.get(id),opts);};
 f.c.chrome.tabs.sendMessage=async(id,msg)=>{calls.push(['message',id,msg.type]);return {ok:true};};
 f.c.flowProgressOwnership=async()=>({active:true,ownerTabId:f.storage['smartpostFlowTab:STORY-TEST:1'],activeRunId:'RUN-1'});
 const fetch=f.c.bridgeFetch;
 f.c.bridgeFetch=async(url,options)=>{
  if(url.includes('/flow-package'))return {ok:true,json:async()=>({ok:true,package:pkg})};
  const body=JSON.parse(options?.body||'{}');
  if(body.replacement_action==='begin'){
   calls.push(['begin',body]);return {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16'},
    replacement:{rebuild_scene:true,revise_story:true,creative_revision_version:1,creative_round:0,phase:'requested'}})};
  }
  return fetch(url,options);
 };
 Object.assign(f.c,{getFlowPackage:async()=>({ok:true,package:pkg}),
  ensureFlowHelper:async id=>calls.push(['ensure',id]),rememberAutomationTabs:async()=>{},waitForTabComplete:async()=>{},
  acknowledge:async()=>{},queryFlowTabs:async()=>{throw Error('must not search/reopen old projects');}});
 return Object.assign(f,{pkg,checkpoint,permit,command,calls,
  start:()=>f.c.openFlowReviewRebuild(command,pkg)});
}
(async()=>{
 let cases=0;
 for(const state of ['missing','needs_review','cancelled','manual_restart']){
  const f=await fixture(state), old=JSON.stringify(f.tabs.get(5)), receipts=JSON.stringify(f.storage.smartpostFlowSubmissionReceipts);
  assert.equal(await f.start(),true);
  const record=f.storage[key], tab=f.tabs.get(record.owner_tab);
  assert.equal(tab.url,'https://flow.google.com/');assert.notEqual(tab.id,5);
  assert.equal(record.phase,'rewrite_sent');assert.equal(record.alternative,true);assert.equal(record.creative_revision_version,1);
  assert.equal(record.manual_resume_proof.source_project_path,'/project/old');
  assert.equal(JSON.stringify(f.tabs.get(5)),old);assert.equal(JSON.stringify(f.storage.smartpostFlowSubmissionReceipts),receipts);
  assert(f.storage[`${key}:history:${f.permit.request_id}`]);
  assert.equal(f.calls.filter(x=>x[0]==='begin').length,1);
  assert.equal(f.calls.filter(x=>x[0]==='create').length,2,'one new controller and one AI helper');
  assert(f.calls.filter(x=>x[0]==='navigate').every(x=>x[2]==='https://flow.google.com/'));
  const terminal=f.storage.smartpostFlowMonitor.storyPolicyTerminal;
  assert.equal(terminal.failure_code,'FLOW_REPAIR_REVIEW');assert.equal(terminal.confirmed_uncharged_failure,undefined);
  assert(f.c.manualFlowReviewProofMatches(record,terminal));
  assert(!f.c.manualFlowReviewProofMatches(record,{...terminal,manual_fresh_start:false}));
  assert(!f.c.manualFlowReviewProofMatches(record,{...terminal,source_project_path:'/project/other'}));
  // Desktop no longer exposes review_checkpoint after helper audit. Repeated
  // command must still adopt this one successor, not reopen the old project.
  delete f.permit.review_checkpoint;
  assert.equal(await f.start(),true);
  assert.equal(f.calls.filter(x=>x[0]==='create').length,2);cases++;
 }
 for(const state of ['requested','rewrite_sent','ready','preparing','submitted','completed']){
  const f=await fixture(state);await assert.rejects(f.start());assert.equal(f.calls.length,0);cases++;
 }
 for(const invalid of ['digest','request','job','path','unknown_image']){
  const f=await fixture('needs_review');
  if(invalid==='digest')f.permit.event_digest='wrong';
  if(invalid==='request')f.permit.request_id='wrong';
  if(invalid==='job')f.permit.job_id='STORY-OTHER';
  if(invalid==='path')f.checkpoint.project_path='//unsafe.invalid';
  if(invalid==='unknown_image')f.storage[key].alternative_stage='image_sent';
  if(invalid==='unknown_image')await assert.rejects(f.start());else assert.equal(await f.start(),false);
  assert.equal(f.calls.length,0);cases++;
 }
 for(const action of ['open_flow','resume_flow_workspace']){
  const f=await fixture();
  const marker=`      } else if (command.action === "${action}") {`;
  const start=background.indexOf(marker),end=background.indexOf('      } else if (command.action ===',start+marker.length);
  vm.runInContext(`async function execute(command){for(const one of [1]){${background.slice(start+marker.length,end)}}}`,f.c);
  await f.c.execute({...f.command,action});
  assert.equal(f.storage[key].phase,'rewrite_sent');
  assert(f.calls.filter(x=>x[0]==='navigate').every(x=>x[2]==='https://flow.google.com/'));cases++;
 }
 // Finish the REAL new-image helper transaction, then claim exactly one NEW
 // Flow project; Generate receipts and completed neighbors remain intact.
 {
  const f=await fixture();await f.start();const record=f.storage[key];
  Object.assign(record,{phase:'ready',candidate:{prompt:'A genuinely new safe 9:16 scene with revised Thai dialogue.',
   needs_review:false,reference_compatible:true,material_change:false},replacement:{image_url:'http://fixture/new.png'}});
  f.storage.smartpostFlowReferenceFile={jobId:'STORY-TEST',shotIndex:1,replacement_id:record.request_id};
  const sender={tab:f.tabs.get(record.owner_tab)}, msg={...f.command,type:'FLOW_SCENE_REPAIR',index:1,request_id:record.request_id};
  await f.c.storyRepairMessage({...msg,action:'fresh_project'},sender);
  assert.equal(f.storage[key].fresh_project.source_path,'/');
  assert.equal(f.calls.filter(x=>x[0]==='navigate'&&x[2]==='https://flow.google.com/').length,2);
  assert((await f.c.storyRepairMessage({...msg,action:'claim_fresh_project_click'},sender)).claimed);
  assert.equal((await f.c.storyRepairMessage({...msg,action:'claim_fresh_project_click'},sender)).claimed,false);
  sender.tab.url='https://flow.google.com/project/brand-new';
  await f.c.storyRepairMessage({...msg,action:'bind_fresh_project'},sender);
  assert.equal(f.storage[key].fresh_project.target_path,'/project/brand-new');
  assert(f.storage.smartpostFlowSubmissionReceipts.old);assert.equal(f.tabs.get(5).url,'https://flow.google.com/project/old');cases++;
 }
 for(const interruption of ['changed_permit','cancelled','login','lost_tab_ack','lost_helper_ack']){
  const f=await fixture();
  if(interruption==='changed_permit')f.c.waitForTabComplete=async()=>{f.permit.event_digest='newer';};
  if(interruption==='cancelled')f.c.waitForTabComplete=async()=>{f.c.flowProgressOwnership=async()=>({active:false});};
  if(interruption==='login')f.c.waitForTabComplete=async id=>{f.tabs.get(id).url='https://accounts.google.com/';};
  if(interruption==='lost_tab_ack'){
   const create=f.c.chrome.tabs.create;
   f.c.chrome.tabs.create=async options=>{await create(options);throw Error('lost tab ACK');};
  }
  if(interruption==='lost_helper_ack')f.c.chrome.tabs.sendMessage=async()=>{throw Error('lost dispatch ACK');};
  await assert.rejects(f.start());
  if(interruption==='lost_helper_ack'){
   assert.equal(f.storage[key].phase,'rewrite_sent');
   assert.equal(await f.start(),true);assert.equal(f.calls.filter(x=>x[0]==='create').length,2);
  }else{
   assert(!f.calls.some(x=>x[0]==='begin'));
   if(interruption==='lost_tab_ack'){
    await assert.rejects(f.start());assert.equal(f.calls.filter(x=>x[0]==='create').length,1);
   }
  }cases++;
 }
 // Old403 would loop fresh_project on home because source_path is now '/'.
 {
  const c=vm.createContext({automationPaused:false,pkg:{flow_repair_request_id:'new',flow_repair_source_path:'/'},
   location:{pathname:'/'},reportLatchedAttachmentFailure:async()=>true,
   chrome:{runtime:{sendMessage:async()=>{throw Error('must not redirect Home repeatedly');}}}});
  vm.runInContext(flow.slice(flow.indexOf('  async function autoPrepare('),flow.indexOf('  function stopGenerationMonitor(')),c);
  assert.equal(await c.autoPrepare(),true);cases++;
 }
 // A dedicated manual controller can observe its AI helper on Home; arbitrary
 // Home navigation or an old/foreign terminal cannot own the new repair.
 {
  const f=await fixture();await f.start();
  const c=vm.createContext({});
  vm.runInContext(flow.slice(flow.indexOf('  function ownedStoryPolicyTerminal('),flow.indexOf('  function evaluateFlowPolicyFailure(')),c);
  const monitor=f.storage.smartpostFlowMonitor;
  assert(c.ownedStoryPolicyTerminal(monitor,f.pkg,'/'));
  for(const patch of [{runId:'other'},{shotIndex:2},{storyPolicyTerminal:{...monitor.storyPolicyTerminal,manual_fresh_start:false}},
   {storyPolicyTerminal:{...monitor.storyPolicyTerminal,manual_review_digest:'wrong'}}]){
   assert.equal(c.ownedStoryPolicyTerminal({...monitor,...patch},f.pkg,'/'),null);
  }cases++;
 }
 for(const mode of ['owned','foreign','cancelled','handoff','unmarked']){
  const f=await fixture();await f.start();let repairs=0,stops=0;
  if(mode==='foreign')f.pkg.run_id='other';
  if(mode==='cancelled')f.storage[key].phase='cancelled';
  if(mode==='handoff')f.storage[key].fresh_project={phase:'opening'};
  if(mode==='unmarked')delete f.storage.smartpostFlowMonitor.storyPolicyTerminal.manual_fresh_start;
  const c=vm.createContext({pkg:f.pkg,location:{pathname:'/'},automationPaused:false,
   inspectionCommandId:'',readOnlyInspection:false,chrome:f.c.chrome,
   stopGenerationMonitor:()=>stops++,recoverFlowPolicy:async()=>{repairs++;return true;}});
  vm.runInContext(flow.slice(flow.indexOf('  function ownedStoryPolicyTerminal('),flow.indexOf('  function evaluateFlowPolicyFailure(')),c);
  vm.runInContext(flow.slice(flow.indexOf('  async function readGenerationState('),flow.indexOf('  $(".copy-prompt").addEventListener')),c);
  await c.readGenerationState();assert.equal(repairs,mode==='owned'?1:0,mode);
  assert.equal(stops,mode==='owned'?0:1,mode);cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
