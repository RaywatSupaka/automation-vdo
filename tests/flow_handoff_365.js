const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const flow=fs.readFileSync('browser_extension/flow.js','utf8');
const bg=fs.readFileSync('browser_extension/background.js','utf8');
const pkg={job_id:'STORY-TEST',shot_index:2,run_id:'RUN',flow_repair_request_id:'new'};
const record={job_id:pkg.job_id,index:2,run_id:'RUN',request_id:'new',owner_tab:5,
 phase:'ready',fresh_project:{phase:'opening',source_path:'/project/old'},
 alternative:true,replacement:{image_url:'new-image'},candidate:{prompt:'new prompt'}};
const progress={job_id:pkg.job_id,shot_index:2,run_id:'RUN',step:'error',
 failure_code:'FLOW_SEND_REVIEW',repair_request_id:'old',page_url:'https://flow.google.com/'};
const c=vm.createContext({URL});
vm.runInContext(bg.slice(bg.indexOf('function freshFlowProgressMatches('),bg.indexOf('async function flowFreshProjectAction(')),c);
for(const step of ['generation_status_unknown','generation_complete','generation_failed','submission_guarded','error'])
 assert.equal(c.freshFlowProgressMatches({...progress,step},record,5),false,step);
assert.equal(c.freshFlowProgressMatches({...progress,step:'opening_project'},record,5),true);
assert.equal(c.freshFlowProgressMatches({...progress,step:'opening_project'},record,6),false);
const submitted={...record,phase:'submitted',fresh_project:{phase:'bound',target_path:'/project/new'}};
const current={...progress,step:'generation_in_progress',repair_request_id:'new',page_url:'https://flow.google.com/project/new'};
assert.equal(c.freshFlowProgressMatches(current,submitted,5),true);
assert.equal(c.freshFlowProgressMatches({...current,repair_request_id:''},submitted,5),false);
assert.equal(c.freshFlowProgressMatches({...current,page_url:'https://flow.google.com/project/old'},submitted,5),false);
assert.equal(c.freshFlowProgressMatches({...current,page_url:'https://flow.google.com/'},{...submitted,phase:'cancelled'},5),false);
assert.equal(c.freshFlowProgressMatches(progress,null,5),true);
assert(bg.includes("reason:'stale_or_presubmit_repair_progress'"));

// Execute actual state-reader entry: landing/old/stale-package never scans
// generation or inherits the source project's 243-second timer.
const prefix=flow.slice(flow.indexOf('  async function readGenerationState()'),flow.indexOf('    const terminalStore =',flow.indexOf('  async function readGenerationState()')));
(async()=>{
 for(const [r,path,id,expected] of [[record,'/','new',0],[record,'/project/old','new',0],
  [submitted,'/project/new','old',0],[submitted,'/project/old','new',0],
  [submitted,'/project/new','new',1],[null,'/project/ordinary','',1]]){
  const ctx=vm.createContext({pkg:{...pkg,flow_repair_request_id:id},inspectionCommandId:'',automationPaused:false,
   location:{pathname:path},scans:0,stops:0,stopGenerationMonitor(){ctx.stops++;},
   chrome:{storage:{local:{get:async key=>({[key]:r})}}}});
  vm.runInContext(prefix+'scans++;\n}',ctx);await ctx.readGenerationState();
  assert.equal(ctx.scans,expected);assert.equal(ctx.stops,expected?0:1);
 }
 // Reproduce stale GET_FLOW_PACKAGE completion: adopt persisted fresh identity.
 const adoption=flow.slice(flow.indexOf('    if(flowRecovery?.fresh_project'),flow.indexOf('    if (!matchingInspection && pkg.flow_repair_request_id'));
 const ctx=vm.createContext({pkg:{job_id:pkg.job_id,shot_index:2,run_id:'RUN',video_prompt:'OLD'},flowRecovery:record});
 vm.runInContext(adoption,ctx);
 assert.equal(ctx.pkg.flow_repair_request_id,'new');assert.equal(ctx.pkg.video_prompt,'new prompt');
 assert.equal(ctx.pkg.image_urls[0],'new-image');assert.equal(ctx.pkg.flow_repair_receipt_key,'STORY-TEST:2:RUN:replacement:new');
 // Actual checkpoint recovery refuses to rebind the old scene-wide checkpoint.
 vm.runInContext(flow.slice(flow.indexOf('  async function resumeSubmittedCheckpoint()'),flow.indexOf('  async function autoPrepare()')),ctx);
 assert.equal(await ctx.resumeSubmittedCheckpoint(),false);
 const monitors={smartpostFlowMonitor:{jobId:pkg.job_id,shotIndex:2,runId:'RUN',startedAt:1,
   repairRequestId:'old',projectPath:'/project/old'}};
 const receiptContext=vm.createContext({pkg,freshId:'new',location:{pathname:'/project/new'},
   submissionReceiptActive:true,submissionReceipt:{baseline:{videoCount:0},requestedAt:123456},
   generationBaseline:null,generationStartedAt:0,generationSnapshot:()=>{throw Error('must use saved new baseline');},
   chrome:{storage:{local:{get:async()=>monitors,set:async patch=>Object.assign(monitors,patch)}}}});
 const receiptStart=flow.indexOf('    if (submissionReceiptActive) {');
 const receiptCode=flow.slice(receiptStart,flow.indexOf('      setStatus(`AUTO FLOW',receiptStart));
 vm.runInContext('async function receiptResume(){'+receiptCode+'}}',receiptContext);
 await receiptContext.receiptResume();
 assert.equal(monitors.smartpostFlowMonitor.startedAt,123456);
 assert.equal(monitors.smartpostFlowMonitor.repairRequestId,'new');
 assert.equal(monitors.smartpostFlowMonitor.projectPath,'/project/new');
 assert(flow.includes('monitor.repairRequestId!==freshId || monitor.projectPath!==location.pathname'));
 console.log('365: stale package/receipt, pre-submit monitor, delayed old progress and exact submitted target passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
