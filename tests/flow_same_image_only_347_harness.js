const fs=require('fs'),assert=require('assert/strict');
const {content}=new Function('require','__dirname',fs.readFileSync('tests/flow_prompt_repair_harness.js','utf8').split('\n(async()=>')[0]+';return {content};')(require,__dirname);
const fixture=new Function('require',fs.readFileSync('tests/story_repair_background_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
(async()=>{
 for(const patch of [{needs_review:true},{reference_compatible:false},{}]){
  const f=content('needs_review',patch);f.c.pkg.flow_repair.same_image_only=true;
  await f.run();assert(f.messages.some(m=>m.action==='pause'));
  assert(!f.messages.some(m=>m.action==='start_alternative'||m.type==='CLICK_FLOW_GENERATE'));
 }
 const manual=content('manual_restart');manual.c.pkg.flow_repair.same_image_only=true;
 await manual.run();assert(manual.messages.some(m=>m.action==='start'));
 assert(!manual.messages.some(m=>m.action==='start_alternative'));
 const f=fixture(),key='smartflowFlowRepair:STORY-TEST:1';
 f.c.URL=URL;f.c.isFlowUrl=()=>true;f.sender.tab.url='https://flow.google.com/project/test';
 f.c.flowProgressOwnership=async()=>({active:true,ownerTabId:5,activeRunId:'RUN-1'});
 f.storage[key]={job_id:'STORY-TEST',run_id:'RUN-1',index:1,phase:'requested',helper_tab:0,
   request:'Create a safe alternate illustration and review it before video generation.'};
 const r=await f.call({type:'FLOW_SCENE_REPAIR',action:'status'});
 assert.equal(r.phase,'needs_review');assert.equal(f.events.length,0);
 f.storage[key]={...f.storage[key],phase:'requested',request:'normal uncertain helper request'};
 assert.equal((await f.call({type:'FLOW_SCENE_REPAIR',action:'status'})).phase,'requested');
 const setup=new Function('require','__dirname',fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]+';return setup;')(require,__dirname);
 const rejected=await setup();const priorId=rejected.storage[key].request_id;
 const originalFetch=rejected.c.bridgeFetch;
 rejected.c.bridgeFetch=async(url,opts)=>{
  if(opts?.body && JSON.parse(opts.body).replacement_action==='begin')
   return {ok:false,json:async()=>({ok:false,error:'replacement already used'})};
  return originalFetch(url,opts);
 };
 const failed=await rejected.call({action:'start_alternative'});
 assert.equal(failed.phase,'needs_review');assert.equal(failed.request_id,priorId);
 assert.equal(failed.helper_tab,0);assert.equal(rejected.events.filter(x=>x==='open').length,1);
 console.log('347: no implicit image replacement, manual text restart, exact legacy orphan recovery, unknown request preserved');
})().catch(e=>{console.error(e);process.exitCode=1;});
