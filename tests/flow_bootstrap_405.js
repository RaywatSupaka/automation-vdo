// Reproduce the manifest content-script reentry omitted by the 404 fixture.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {fixture,key}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_fresh_start_404.js','utf8').split('\n(async()=>')[0]
 +';return {fixture,key};')(require,__dirname);
const source=fs.readFileSync('browser_extension/background.js','utf8');
const flow=fs.readFileSync('browser_extension/flow.js','utf8');
async function setup(){
 const f=await fixture();
 vm.runInContext(source.slice(source.indexOf('function flowRunStorageKey('),source.indexOf('async function aiProgressOwnership(')),f.c);
 f.storage['smartpostFlowRun:STORY-TEST:1']='RUN-1';
 f.handshake=async id=>f.c.storyRepairMessage({type:'FLOW_SCENE_REPAIR',action:'manual_restart',
  ...f.command,index:1,token:f.permit.token},{tab:f.tabs.get(id)});
 return f;
}
(async()=>{
 let cases=0;
 // Automatic flow.js load is allowed DURING the worker's page-load await.
 // 404 navigates this very tab back to /project/old and then claims login failed.
 {
  const f=await setup();let early;
  f.c.waitForTabComplete=async id=>{early=await f.handshake(id);};
  await f.start();
  assert.equal(early.phase,'fresh_start_pending');
  assert(!f.calls.some(x=>x[0]==='navigate'&&x[2].includes('/project/old')));
  assert.equal(f.storage[key].phase,'rewrite_sent');
  assert.equal(f.storage[key].manual_resume_proof.fresh_start,true);
  assert.equal(f.calls.filter(x=>x[0]==='begin').length,1);cases++;
 }
 // No Flow document (hence no content-script) before ownership is saved.
 {
  const f=await setup(),create=f.c.chrome.tabs.create,update=f.c.chrome.tabs.update;
  let checked=false;
  f.c.chrome.tabs.create=async opts=>{
   if(!checked){assert.equal(opts.url,'about:blank');checked=true;}
   return create(opts);
  };
  f.c.chrome.tabs.update=async(id,opts)=>{
   if(opts.url==='https://flow.google.com/'){
    assert.equal(f.storage['smartpostFlowTab:STORY-TEST:1'],id);
    assert.equal(f.storage[key].owner_tab,id);
    assert.equal(f.storage[key].manual_resume_proof.fresh_start,true);
   }
   return update(id,opts);
  };
  await f.start();assert(checked);cases++;
 }
 // Explicit Resume after 404's pre-helper navigation failure can start a
 // new controller, but never after an unknown image/text/Generate send.
 for(const phase of ['manual_restart','cancelled','rewrite_sent','requested','ready','submitted']){
  const f=await setup();
  f.c.waitForTabComplete=async()=>{throw Error('pre-helper page failure');};
  await assert.rejects(f.start(),/pre-helper/);
  const firstTab=f.storage[key].owner_tab;
  f.storage[key].phase=phase;
  f.command.run_id='RUN-2';f.pkg.run_id='RUN-2';
  f.storage['smartpostFlowRun:STORY-TEST:1']='RUN-2';
  f.c.waitForTabComplete=async()=>{};
  if(['manual_restart','cancelled'].includes(phase)){
   await f.start();assert.notEqual(f.storage[key].owner_tab,firstTab);
   assert.equal(f.storage[key].phase,'rewrite_sent');
   assert.equal(f.storage[key].run_id,'RUN-2');
   assert.equal(f.calls.filter(x=>x[0]==='begin').length,1);
   assert.equal(f.tabs.get(5).url,'https://flow.google.com/project/old');
  }else{await assert.rejects(f.start());assert(!f.calls.some(x=>x[0]==='begin'));}
  cases++;
 }
 // The new controller must not inherit an old inspection-only command gate.
 {
  const f=await setup();f.storage['smartpostFlowInspection:STORY-TEST:1']={runId:'RUN-1',commandId:'OLD-INSPECT'};
  f.storage.smartpostFlowInspectOnly={jobId:'STORY-TEST',shotIndex:1,runId:'RUN-1',commandId:'OLD-INSPECT'};
  await f.start();assert.equal(f.storage[key].phase,'rewrite_sent');cases++;
 }
 // Content side must leave the controller bootstrap to the worker. It may
 // neither read the old project's DOM nor launch a second recovery helper.
 {
  const f=await setup(),messages=[];
  const c=vm.createContext({automationPaused:false,pkg:f.pkg,location:{pathname:'/'},
   chrome:{runtime:{sendMessage:async msg=>{messages.push(msg);return {ok:true,phase:'fresh_start_pending'};}}},
   setStatus:()=>{},report:async(step)=>assert.notEqual(step,'error'),
   inspectGenerationState:async()=>{throw Error('bootstrap must not inspect');},
   monitorGeneration:()=>{throw Error('bootstrap must not start monitor');}});
  vm.runInContext(flow.slice(flow.indexOf('  async function autoPrepare('),flow.indexOf('  function stopGenerationMonitor(')),c);
  assert.equal(await c.autoPrepare(),true);assert.equal(messages.length,1);cases++;
 }
 // Run both sides together at actual document injection time, not just a
 // hand-written response: content -> real owner/manual handler -> worker.
 {
  const f=await setup();let loads=0;
  const update=f.c.chrome.tabs.update;
  f.c.chrome.tabs.update=async(id,opts)=>{
   const tab=await update(id,opts);
   if(opts.url==='https://flow.google.com/'){
    const c=vm.createContext({automationPaused:false,pkg:f.pkg,location:{pathname:'/'},setTimeout,
     chrome:{runtime:{sendMessage:msg=>f.c.storyRepairMessage(msg,{tab})}},
     setStatus:()=>{},report:async step=>assert.notEqual(step,'error'),
     inspectGenerationState:async()=>{throw Error('not ready yet');},monitorGeneration:()=>{throw Error('not ready yet');}});
    vm.runInContext(flow.slice(flow.indexOf('  async function autoPrepare('),flow.indexOf('  function stopGenerationMonitor(')),c);
    await Promise.all([c.autoPrepare(),c.autoPrepare()]);loads+=2;
   }
   return tab;
  };
  await f.start();await f.start();
  assert.equal(loads,2);assert.equal(f.calls.filter(x=>x[0]==='begin').length,1);
  assert.equal(f.calls.filter(x=>x[0]==='create').length,2);cases++;
 }
 for(const change of ['helper','candidate','fresh_project','successor','request','digest','fingerprint','source','project','round','unknown_tab']){
  const f=await setup();f.c.waitForTabComplete=async()=>{throw Error('pre-helper');};
  await assert.rejects(f.start(),/pre-helper/);
  const record=f.storage[key],intentKey=`${key}:fresh-start:${f.permit.event_digest}`;
  if(change==='helper')record.helper_tab=99;
  if(change==='candidate')record.candidate={prompt:'saved result'};
  if(change==='fresh_project')record.fresh_project={phase:'opening'};
  if(change==='successor')f.storage[intentKey].successor_request_id='new';
  if(change==='request')record.request_id='new';
  if(change==='digest')record.manual_resume_proof.event_digest='other';
  if(change==='fingerprint')record.manual_resume_proof.fingerprint='other';
  if(change==='source')record.manual_resume_proof.source_project_path='/project/foreign';
  if(change==='project')record.project_path='/project/new';
  if(change==='round')record.round=1;
  if(change==='unknown_tab')f.storage[intentKey].tab_id=0;
  f.command.run_id='RUN-2';f.pkg.run_id='RUN-2';f.storage['smartpostFlowRun:STORY-TEST:1']='RUN-2';
  f.c.waitForTabComplete=async()=>{};
  await assert.rejects(f.start());assert(!f.calls.some(x=>x[0]==='begin'));cases++;
 }
 // Same-run stale controller, changed run, and explicit pause still fail the
 // real ownership guard. Fresh bootstrap does not excuse these violations.
 for(const change of ['tab','run','paused']){
  const f=await setup();f.c.waitForTabComplete=async id=>{
   if(change==='tab')f.storage['smartpostFlowTab:STORY-TEST:1']=999;
   if(change==='run')f.storage['smartpostFlowRun:STORY-TEST:1']='OTHER';
   if(change==='paused')f.storage.smartpostFlowPausedTabs={[id]:true};
  };
  await assert.rejects(f.start(),/owner changed/);
  assert(!f.calls.some(x=>x[0]==='begin'));cases++;
 }
 // Unrelated inspection jobs are never cleared by the new scene's setup.
 {
  const f=await setup(),foreign={jobId:'STORY-OTHER',shotIndex:7,runId:'RUN-Z',commandId:'OTHER'};
  f.storage.smartpostFlowInspectOnly=foreign;
  f.storage['smartpostFlowInspection:STORY-OTHER:7']=foreign;
  await f.start();assert.deepEqual(f.storage.smartpostFlowInspectOnly,foreign);
  assert.deepEqual(f.storage['smartpostFlowInspection:STORY-OTHER:7'],foreign);cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
