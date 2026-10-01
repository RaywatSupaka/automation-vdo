const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const flow = fs.readFileSync(path.join(__dirname, '../browser_extension/flow.js'), 'utf8');
const bg = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
const part = (s, a, b) => s.slice(s.indexOf(a), s.indexOf(b, s.indexOf(a) + a.length));
const job = 'STORY-fixture', key = job + ':2', url = 'https://flow.google.com/project/owned';
const baseline = {videoCount: 0, videoSources: [], resultCardCount: 0};
let cases = 0;
function fixture(overrides = {}) {
  const checkpoint = {jobId:job, shotIndex:2, runId:'old', status:'active', url, baseline, highestProgress:100, ...overrides};
  const storage = {smartpostFlowCheckpoints:{[key]:checkpoint}};
  const calls = [];
  const c = {URL, Date, automationPaused:false, pkg:{job_id:job, shot_index:2, run_id:'new'}, location:{href:url},
    chrome:{storage:{local:{get:async()=>structuredClone(storage),set:async v=>Object.assign(storage,structuredClone(v))}}},
    report:async(...args)=>calls.push(['report',...args]),
    inspectGenerationState:async()=>calls.push(['inspect']),monitorGeneration:()=>calls.push(['monitor'])};
  vm.createContext(c);
  vm.runInContext(part(flow,'  async function resumeSubmittedCheckpoint()', '  async function autoPrepare()'), c);
  return {c, storage, calls};
}
(async()=>{
  for (const status of ['active','complete']) {
    const f=fixture({status});
    assert.equal(await f.c.resumeSubmittedCheckpoint(),true);
    assert.equal(f.c.readOnlyInspection,true);
    assert.equal(f.storage.smartpostFlowMonitor.runId,'new');
    assert.equal(f.storage.smartpostFlowMonitor.resumedCheckpointRunId,'old');
    assert.deepEqual(f.storage.smartpostFlowMonitor.baseline,baseline);
    assert.equal(f.storage.smartpostFlowCheckpoints[key].runId,'old');
    assert.equal(f.calls.filter(x=>x[0]==='inspect').length,1); cases++;
  }
  for (const change of [{url:'https://flow.google.com/project/other'}, {jobId:'STORY-other'},
      {shotIndex:3},{baseline:null},{url:'https://evil.invalid/project/owned'}]) {
    const f=fixture(change); assert.equal(await f.c.resumeSubmittedCheckpoint(),true);
    assert.equal(f.calls[0][1],'error'); assert(!f.storage.smartpostFlowMonitor); cases++;
  }
  for (const status of ['preparing','opening','failed']) {
    const f=fixture({status}); assert.equal(await f.c.resumeSubmittedCheckpoint(),false);
    assert.equal(f.calls.length,0); cases++;
  }
  const presenter=fixture(); presenter.c.pkg.job_id='PRESENTER-fixture';
  assert.equal(await presenter.c.resumeSubmittedCheckpoint(),false); cases++;
  for (const extra of [{runId:'new'}, {runId:'old',storyPolicyTerminal:{failure_code:'FLOW_POLICY_BLOCKED'}}]) {
    const f=fixture(); f.storage.smartpostFlowMonitor={jobId:job,shotIndex:2,...extra};
    const before=structuredClone(f.storage);
    assert.equal(await f.c.resumeSubmittedCheckpoint(),false);
    assert.deepEqual(f.storage,before); cases++;
  }
  const paused=fixture(); paused.c.automationPaused=true;
  assert.equal(await paused.c.resumeSubmittedCheckpoint(),true);
  assert.equal(paused.calls.length,0); cases++;
  // Execute the real autoPrepare entry point, not just the recovery helper.
  for (const kind of ['active','complete','missing-checkpoint']) {
    const f=fixture({status:kind});
    f.storage.smartpostAutoFlow={jobId:job,shotIndex:2,runId:'new',requestedAt:Date.now()};
    f.storage.smartpostFlowSubmissionReceipts={[key+':old']:{runId:'old'}};
    Object.assign(f.c,{FLOW_SUBMISSION_RECEIPTS_KEY:'smartpostFlowSubmissionReceipts',
      reportLatchedAttachmentFailure:async()=>false});
    f.c.chrome.runtime={sendMessage:async m=>{
      assert.equal(m.type,'IS_ACTIVE_FLOW_TAB','Unexpected provider action');return {active:true};
    }};
    vm.runInContext(part(flow,'  async function autoPrepare()', '  function stopGenerationMonitor()'),f.c);
    assert.equal(await f.c.autoPrepare(),true);
    assert.equal(f.calls.some(x=>x[0]==='inspect'),kind!=='missing-checkpoint');
    if(kind==='missing-checkpoint') assert.equal(f.calls[0][1],'error');
    cases++;
  }
  // Actual cleanup function: closing tabs may remove transient tokens, never
  // proof of a paid request, checkpoints or pending/completed downloads.
  const receipts={owned:{runId:'old'},other:{runId:'unrelated'}};
  const storage={smartpostFlowSubmissionReceipts:receipts,smartpostFlowCheckpoints:{[key]:{url}},
    smartpostPendingFlowDownload:{downloadId:7},smartpostFlowDownloadReceipt:{downloadId:8}};
  const c={AUTOMATION_TAB_IDS_KEY:'tabs',FLOW_SUBMISSION_RECEIPTS_KEY:'smartpostFlowSubmissionReceipts',
    rememberedAutomationTabIds:async()=>[],aiRunStorageKey:j=>'ai:'+j,
    chrome:{storage:{local:{get:async()=>structuredClone(storage),remove:async keys=>keys.forEach(k=>delete storage[k])}},
      tabs:{get:async()=>{throw Error('no tab');},remove:async()=>{}}}};
  vm.createContext(c); vm.runInContext(part(bg,'async function closeAutomationBrowser(', 'function bytesToBase64('),c);
  await c.closeAutomationBrowser(job);
  assert.deepEqual(storage.smartpostFlowSubmissionReceipts,receipts);
  assert(storage.smartpostFlowCheckpoints[key]); assert.equal(storage.smartpostPendingFlowDownload.downloadId,7);
  assert.equal(storage.smartpostFlowDownloadReceipt.downloadId,8); cases++;
  assert(flow.includes('!readyReceiptActive && !anySubmissionReceipt')); cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
