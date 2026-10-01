const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const fixture=new Function('require',fs.readFileSync('tests/story_repair_background_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
const {content,dispatch}=new Function('require','__dirname',fs.readFileSync('tests/flow_prompt_repair_harness.js','utf8').split('\n(async()=>')[0]+';return {content,dispatch};')(require,__dirname);
const source=fs.readFileSync('browser_extension/background.js','utf8');
const key='smartflowFlowRepair:STORY-TEST:1';
const candidate={prompt:'Vertical 9:16, one video. The traveller returns the umbrella to the vendor, with a gentle camera push-in. All spoken dialogue must be in Thai only.',needs_review:false,reference_compatible:true,material_change:false};
async function setup(provider='chatgpt',terminalPatch={}){
 const f=fixture();
 Object.assign(f.c,{URL,testProvider:provider,FLOW_URL:'https://flow.google.com/',
   isFlowUrl:u=>u.startsWith('https://flow.google.com/'),
   flowMobileDebugger:{pin:async()=>f.events.push('mobile')},
   flowProgressOwnership:async()=>({active:true,ownerTabId:5,activeRunId:'RUN-1'})});
 f.sender.tab.url='https://flow.google.com/project/old';f.tabs.set(5,{...f.sender.tab,status:'complete'});
 f.c.chrome.tabs.update=async(id,p)=>{Object.assign(f.tabs.get(id),p);f.sender.tab.url=f.tabs.get(id).url;f.events.push('navigate');};
 f.c.chrome.storage.local.remove=async keys=>{for(const k of Array.isArray(keys)?keys:[keys])delete f.storage[k];};
 Object.assign(f.message,{type:'FLOW_SCENE_REPAIR',shot_index:1,provider,fingerprint:'fp',failure_card_key:'tile',failure_id:'one'});
 f.storage.smartpostFlowMonitor={jobId:'STORY-TEST',runId:'RUN-1',shotIndex:1,
   storyPolicyTerminal:{repair_eligible:true,failure_code:'FLOW_POLICY_BLOCKED',failure_card_fingerprint:'fp',failure_reason:'public figure policy',projectPath:'/project/old',...terminalPatch}};
 f.c.chrome.downloads={download:async options=>{f.events.push(options.url);return 91;},search:async()=>[{state:'complete',filename:'C:/fixture/original.png'}]};
 const r=await f.call();await f.call();
 assert.equal(r.provider,provider);assert.equal(r.alternative,undefined);
 assert.equal(f.events.filter(x=>x==='open').length,1);
 assert.equal(f.tabs.get(r.helper_tab).url,f.c.AI_WEB[provider].url);
 assert.deepEqual(Array.from(r.image_urls),['http://fixture/scene.png']);
 Object.assign(f.storage[key],{phase:'ready',candidate});f.message.request_id=r.request_id;
 f.storage.smartpostFlowCheckpoints={'STORY-TEST:1':{status:'failed'},'OTHER:2':{status:'complete'}};
 f.storage.smartpostFlowSubmissionReceipts={old:{clicked:true}};
 return f;
}
(async()=>{
 for(const provider of ['chatgpt','gemini']){
  const f=await setup(provider);
  await f.call({action:'prepare_reference'});await f.call({action:'prepare_reference'});
  assert.equal(f.events.filter(x=>x==='http://fixture/scene.png').length,1);
  assert.equal(f.storage[key].repair_reference.source,'original');
  assert.equal(f.storage.smartpostFlowReferenceFile.replacement_id,undefined);
  assert.equal(f.storage.smartpostFlowReferenceFile.repair_request_id,f.message.request_id);
  await f.call({action:'fresh_project'});await f.call({action:'fresh_project'});
  assert.equal(f.events.filter(x=>x==='navigate').length,1);
  assert(f.storage.smartpostFlowCheckpoints['OTHER:2']);
  assert.deepEqual(f.storage.smartpostFlowSubmissionReceipts,{old:{clicked:true}});
  assert((await f.call({action:'claim_fresh_project_click'})).claimed);
  assert.equal((await f.call({action:'claim_fresh_project_click'})).claimed,false);
  await assert.rejects(f.call({action:'bind_fresh_project'}));
  f.tabs.get(5).url=f.sender.tab.url='https://flow.google.com/project/new';
  await f.call({action:'bind_fresh_project'});
  Object.assign(f.c,{flowRunStorageKey:()=> 'run-key'});
  f.storage['run-key']='RUN-1';
  vm.runInContext(source.slice(source.indexOf('async function getFlowPackage('),source.indexOf('async function pageType(')),f.c);
  const p=(await f.c.getFlowPackage('STORY-TEST',1)).package;
  assert.equal(p.flow_repair.fresh_project_on_repair,true);
  assert.equal(p.flow_repair.rebuild_image_on_failure,undefined);
  assert.equal(p.image_urls[0],'http://fixture/scene.png');
  assert.equal(p.video_prompt,candidate.prompt);assert.equal(p.replacement_id,undefined);
  assert.equal(p.flow_repair_receipt_key,`STORY-TEST:1:RUN-1:repair:${f.message.request_id}`);
 }
 for(const mode of ['proof','file','changed-image','review','incompatible','material','run']){
  const f=await setup();await f.call({action:'prepare_reference'});
  if(mode==='proof')delete f.storage.smartpostFlowMonitor;
  if(mode==='file')f.storage.smartpostFlowReferenceFile.repair_request_id='other';
  if(mode==='changed-image')f.storage[key].image_urls=['http://fixture/wrong.png'];
  if(mode==='review')f.storage[key].candidate={...candidate,needs_review:true};
  if(mode==='incompatible')f.storage[key].candidate={...candidate,reference_compatible:false};
  if(mode==='material')f.storage[key].candidate={...candidate,material_change:true};
  if(mode==='run')f.message.run_id='WRONG';
  await assert.rejects(f.call({action:'fresh_project'}));assert(!f.events.includes('navigate'));
 }
 for(const provider of ['chatgpt','gemini']){
  const f=content();Object.assign(f.c.pkg,{image_ai_provider:provider,flow_repair:{enabled:true,fresh_project_on_repair:true}});
  f.c.document={body:{innerText:''}};f.c.confirmationKind=()=>'';
  await f.run();
  assert.deepEqual(f.messages.filter(m=>m.type==='FLOW_SCENE_REPAIR').map(m=>m.action),['status','prepare_reference','fresh_project']);
  assert(!f.messages.some(m=>m.type==='CLICK_FLOW_GENERATE'||m.action==='start_alternative'));
  const first=content('missing');first.c.pkg.flow_repair={enabled:true,fresh_project_on_repair:true};
  first.c.pkg.image_ai_provider=provider;await first.run({failure_card_key:'tile'});
  const start=first.messages.find(m=>m.action==='start');assert(start);assert.equal(start.failure_card_key,'tile');
  assert(!first.messages.some(m=>m.action==='start_alternative'));
 }
 const repair={phase:'submit_ready',round:1,request_id:'R-fresh',run_id:'RUN-A',owner_tab:7,
   project_path:'/project/p',fresh_project:{phase:'bound',target_path:'/project/p'},candidate};
 const options={storage:{receipts:{'STORY-TEST:1:RUN-A':{requestedAt:1}},[key]:repair},context:{URL,
   flowRepairKey:()=>key,assertFlowRepairOwner:async()=>{},
   sender:{tab:{id:7,windowId:3,url:'https://flow.google.com/project/p'}},
   message:{type:'CLICK_FLOW_GENERATE',job_id:'STORY-TEST',shot_index:1,run_id:'RUN-A',repair_request_id:'R-fresh',prompt_guard:candidate.prompt}}};
 const sent=await dispatch(options);assert.equal(sent.result.ok,true,JSON.stringify(sent.result));
 assert(sent.storage.receipts['STORY-TEST:1:RUN-A:repair:R-fresh']);
 assert(sent.storage.receipts['STORY-TEST:1:RUN-A']);
 const duplicate=await dispatch({...options,storage:sent.storage});assert.equal(duplicate.result.duplicateBlocked,true);
 console.log('346 same-image: both providers, text-first, one helper/download/project/Generate, original-image provenance, exact receipts and 7 rejection guards passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
