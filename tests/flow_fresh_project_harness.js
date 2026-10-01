const fs=require('fs'),vm=require('vm'),assert=require('assert');
const fixture=new Function('require',fs.readFileSync('tests/story_repair_background_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
const key='smartflowFlowRepair:STORY-TEST:1';
async function setup(){
 const f=fixture();
 Object.assign(f.c,{URL,FLOW_URL:'https://flow.google.com/',isFlowUrl:u=>u.startsWith('https://flow.google.com/'),
  flowMobileDebugger:{pin:async()=>f.events.push('mobile')},
  flowProgressOwnership:async()=>({active:true,ownerTabId:5,activeRunId:'RUN-1'})});
 f.sender.tab.url='https://flow.google.com/project/old';f.tabs.set(5,{...f.sender.tab,status:'complete'});
 f.c.chrome.tabs.update=async(id,patch)=>{Object.assign(f.tabs.get(id),patch);f.sender.tab.url=f.tabs.get(id).url;f.events.push('navigate');};
 f.c.chrome.storage.local.remove=async keys=>{for(const k of Array.isArray(keys)?keys:[keys])delete f.storage[k];};
 Object.assign(f.message,{type:'FLOW_SCENE_REPAIR',shot_index:1,fingerprint:'fp',failure_card_key:'tile',failure_id:'one'});
 f.storage.smartpostFlowMonitor={jobId:'STORY-TEST',runId:'RUN-1',shotIndex:1,
  storyPolicyTerminal:{repair_eligible:true,failure_code:'FLOW_POLICY_BLOCKED',failure_card_fingerprint:'fp',failure_card_key:'tile',failure_reason:'failed',projectPath:'/project/old'}};
 const fetch=f.c.bridgeFetch;
 f.c.bridgeFetch=async(url,opts)=>{
  if(JSON.parse(opts?.body||'{}').replacement_action==='begin'){
   assert(f.audit.some(x=>x.event?.fingerprint==='fp'),'terminal audited BEFORE replacement begin');
   return {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16'},replacement:{phase:'requested'}})};
  }
  return fetch(url,opts);
 };
 const result=await f.call({action:'start_alternative'});
 assert(result.alternative);assert.equal(result.phase,'rewrite_sent');assert.equal(result.provider,'chatgpt');
 f.storage[key].phase='ready';f.storage[key].candidate={prompt:'Vertical 9:16, a hand puts a bottle into a recycling bin.',needs_review:false,reference_compatible:true,material_change:false};
 f.storage[key].replacement={image_url:'http://fixture/new.png'};
 f.storage.smartpostFlowReferenceFile={jobId:'STORY-TEST',shotIndex:1,replacement_id:result.request_id,filename:'new.png'};
 f.storage.smartpostFlowCheckpoints={'STORY-TEST:1':{phase:'failed'},'OTHER:2':{phase:'completed'}};
 f.storage.smartpostFlowSubmissionReceipts={old:{clicked:true}};
 f.storage.smartpostFlowActiveProject={jobId:'STORY-TEST',shotIndex:1,tabId:5};
 f.message.request_id=result.request_id;
 return f;
}
(async()=>{
 const f=await setup();
 await f.call({action:'fresh_project'});
 assert.equal(f.tabs.get(5).url,'https://flow.google.com/');assert(f.events.includes('mobile'));
 assert.equal(f.storage[key].fresh_project.source_path,'/project/old');
 assert(f.storage[`${key}:project-archive:${f.message.request_id}`].smartpostFlowMonitor);
 assert.deepEqual(f.storage.smartpostFlowSubmissionReceipts,{old:{clicked:true}});
 assert(f.storage.smartpostFlowCheckpoints['OTHER:2']);assert(!f.storage.smartpostFlowCheckpoints['STORY-TEST:1']);
 await f.call({action:'fresh_project'});assert.equal(f.events.filter(x=>x==='navigate').length,1);
 assert((await f.call({action:'claim_fresh_project_click'})).claimed);
 assert.equal((await f.call({action:'claim_fresh_project_click'})).claimed,false);
 await assert.rejects(f.call({action:'bind_fresh_project'}),/destination/);
 f.tabs.get(5).url=f.sender.tab.url='https://flow.google.com/project/new';
 await f.call({action:'bind_fresh_project'});await f.call({action:'bind_fresh_project'});
 assert.equal(f.storage[key].project_path,'/project/new');assert.equal(f.storage[key].fresh_project.target_path,'/project/new');
 await f.call({action:'preparing'});await f.call({action:'submit_ready'});
 f.tabs.get(5).url=f.sender.tab.url='https://flow.google.com/project/unrelated';
 await assert.rejects(f.call({action:'bind_fresh_project'}),/destination/);
 for(const mode of ['missing-proof','wrong-file','review','request','submitted']){
  const g=await setup();
  if(mode==='missing-proof')delete g.storage.smartpostFlowMonitor;
  if(mode==='wrong-file')g.storage.smartpostFlowReferenceFile.replacement_id='other';
  if(mode==='review')g.storage[key].candidate.needs_review=true;
  if(mode==='request')g.message.request_id='other';
  if(mode==='submitted')g.storage[key].phase='submitted';
  await assert.rejects(g.call({action:'fresh_project'}));assert(!g.events.includes('navigate'));
 }
 console.log('Fresh project: first-failure audit, one navigation/click, exact target, retained receipts and 5 rejection guards passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
