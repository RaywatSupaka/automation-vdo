const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const background = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
const flow = fs.readFileSync(path.join(__dirname, '../browser_extension/flow.js'), 'utf8');
const part = (source, start, end) => {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing actual-source section: ${start}`);
  return source.slice(first, last);
};
const ident = 'PRESENTER-AABBCCDDEEFF', run = 'RUN-original', key = `${ident}:1`;
const project = 'https://flow.google.com/project/exact-project';
const tabKey = `smartpostFlowTab:${key}`, runKey = `smartpostFlowRun:${key}`;
const receiptsKey = 'smartpostFlowSubmissionReceipts';
const flush = () => new Promise(resolve => setImmediate(resolve));
let cases = 0;
async function test(name, callback) {
  try { await callback(); cases++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; }
}
function context(storage = {}) {
  const calls = [];
  const tabs = new Map([[7, {id: 7, url: project}], [8, {id: 8, url: 'https://flow.google.com/project/other'}]]);
  const state = {
    URL, Date, console, setTimeout, clearTimeout,
    VERSION: 'test', FLOW_HELPER_BUILD: 'test-build', FLOW_URL: 'https://flow.google.com/',
    FLOW_SUBMISSION_RECEIPTS_KEY: receiptsKey,
    flowHelperInstallPromises: new Map(),
    flowRunStorageKey: (job, shot) => `smartpostFlowRun:${job}:${shot}`,
    flowProjectId: url => String(url || '').match(/\/project\/([^/?#]+)/)?.[1] || '',
    normalizeAIProvider: provider => provider || 'chatgpt',
    BRIDGE: 'http://fixture.invalid',
    AI_WEB: {chatgpt: {name:'ChatGPT Web', url:'https://chatgpt.com/', matches:['https://chatgpt.com/*']},
      gemini: {name:'Gemini Web', url:'https://gemini.google.com/app', matches:['https://gemini.google.com/*']}},
    chrome: {
      storage: {local: {
        async get(keys) { return Object.fromEntries((Array.isArray(keys) ? keys : [keys])
          .map(k => [k, storage[k] === undefined ? undefined : structuredClone(storage[k])])); },
        async set(value) { Object.assign(storage, structuredClone(value)); },
        async remove(keys) { for (const k of Array.isArray(keys) ? keys : [keys]) delete storage[k]; }
      }},
      tabs: {
        async get(id) { if (!tabs.has(id)) throw Error('closed tab'); return {...tabs.get(id)}; },
        async update(id, value) { calls.push(['update', id, value]); Object.assign(tabs.get(id), value); return tabs.get(id); },
        async query() { return [...tabs.values()]; },
        async sendMessage(id, message) { calls.push(['message', id, message]); return {ok:true, paused:true}; },
        async reload(id) { calls.push(['reload', id]); throw Error('Unexpected reload'); },
        async remove(id) { calls.push(['remove', id]); throw Error('Unexpected tab deletion'); },
      },
      scripting: {async executeScript(request) { calls.push(['script', request]); return [{result:{}}]; }},
    },
    waitForTabComplete: async () => {},
    rememberAutomationTabs: async () => {},
    focusOpenedBrowserTab: async () => {},
    isWebLoginUrl: () => false,
    isGoogleVerificationUrl: () => false,
    queryFlowTabs: async () => [...tabs.values()],
    pickHealthyFlowProjectTab: async choices => choices.find(t => /\/project\//.test(t.url)),
    ensureFlowHelper: async id => { calls.push(['helper', id]); },
  };
  state.globalThis = state;
  vm.createContext(state);
  vm.runInContext(part(background,'function sceneVideoPlanMatches(', 'async function flowProgressOwnership('),state);
  return {state, storage, calls, tabs};
}
function ownedStorage() {
  return {
    [tabKey]: 7, [runKey]: run,
    smartpostFlowCheckpoints: {[key]: {jobId:ident,shotIndex:1,runId:run,url:project,status:'preparing'},
      'JOB-other:2':{url:'https://flow.google.com/project/other',status:'complete'}},
    [receiptsKey]: {[`${key}:${run}`]:{jobId:ident,shotIndex:1,runId:run,requestedAt:1}},
    smartpostFlowMonitor: {jobId:ident,shotIndex:1,runId:run,startedAt:1},
    smartpostAutoFlow: {jobId:ident,shotIndex:1,runId:run},
    smartpostFlowAttachmentAttempts: {[`${key}:exact-project`]:{startedAt:1,status:'uploaded'}},
  };
}

async function pauseTests() {
  await test('content helper acknowledges pause only after all old asynchronous work drains',async()=>{
    const c=context();let listener,resolvePrepare,resolveInspect,response;
    Object.assign(c.state,{pkg:{job_id:ident,shot_index:1,run_id:run},automationPaused:false,inspectionCommandId:'CMD-old',
      autoPreparePromise:new Promise(resolve=>{resolvePrepare=resolve;}),packageLoadQueue:Promise.resolve(),
      generationInspectionPromise:new Promise(resolve=>{resolveInspect=resolve;}),
      stopManualAttachmentWatch:()=>{},stopGenerationMonitor:()=>{}});
    c.state.chrome.runtime={onMessage:{addListener:value=>{listener=value;}}};
    vm.runInContext(part(flow,'  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {',
      '  queuePackageReload().then((usedAuto) => {'),c.state);
    assert.equal(listener({type:'PAUSE_FLOW_JOB',job_id:ident,shot_index:1,run_id:run},{},value=>{response=value;}),true);
    await flush();assert.equal(response,undefined);assert.equal(c.state.automationPaused,true);
    resolvePrepare();await flush();assert.equal(response,undefined);
    resolveInspect();await flush();assert.equal(response.paused,true);
    assert.equal(c.state.inspectionCommandId,'');
  });
  await test('content helper rejects an unrelated pause without stopping its work',async()=>{
    const c=context();let listener,response;
    Object.assign(c.state,{pkg:{job_id:ident,shot_index:1,run_id:run},automationPaused:false,
      stopManualAttachmentWatch:()=>{throw Error('wrong owner stopped');},stopGenerationMonitor:()=>{throw Error('wrong owner stopped');}});
    c.state.chrome.runtime={onMessage:{addListener:value=>{listener=value;}}};
    vm.runInContext(part(flow,'  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {',
      '  queuePackageReload().then((usedAuto) => {'),c.state);
    listener({type:'PAUSE_FLOW_JOB',job_id:ident,shot_index:1,run_id:'RUN-other'},{},value=>{response=value;});
    assert.equal(response.ok,false);assert.equal(c.state.automationPaused,false);
  });
  await test('pause preserves evidence and other jobs', async () => {
    const c = context(ownedStorage());
    const before = structuredClone(c.storage);
    vm.runInContext(part(background, 'async function pauseFlowForResume(', 'async function stopFlowGeneration('), c.state);
    const result = await c.state.pauseFlowForResume(ident,1,run);
    assert.equal(result.paused,true);
    for (const name of ['smartpostFlowCheckpoints', receiptsKey, 'smartpostFlowMonitor', 'smartpostFlowAttachmentAttempts', tabKey, runKey])
      assert.deepEqual(c.storage[name],before[name],name);
    assert.equal(c.storage.smartpostAutoFlow,undefined);
    assert.equal(c.storage[`smartpostFlowPaused:${key}`].runId,run);
    assert.equal(c.calls.filter(x=>x[0]!=='message').length,0);
    assert.equal(c.calls[0][2].type,'PAUSE_FLOW_JOB');
  });
  await test('pause must await helper drainage acknowledgement', async () => {
    const c = context(ownedStorage()); let resolve, done = false;
    c.state.chrome.tabs.sendMessage = () => new Promise(r => { resolve=r; });
    vm.runInContext(part(background,'async function pauseFlowForResume(','async function stopFlowGeneration('),c.state);
    const pending=c.state.pauseFlowForResume(ident,1,run).then(r=>{done=true;return r;});
    await flush(); assert.equal(done,false); resolve({ok:true,paused:true});
    assert.equal((await pending).paused,true);
  });
  await test('negative helper acknowledgement is not success', async () => {
    const c=context(ownedStorage());c.state.chrome.tabs.sendMessage=async()=>({ok:false,error:'still draining'});
    vm.runInContext(part(background,'async function pauseFlowForResume(','async function stopFlowGeneration('),c.state);
    await assert.rejects(c.state.pauseFlowForResume(ident,1,run),/still draining/);
    assert(c.storage.smartpostFlowCheckpoints[key]);assert(c.storage[receiptsKey][`${key}:${run}`]);
  });
  await test('old run cannot pause replacement run',async()=>{
    const c=context(ownedStorage());c.storage[runKey]='RUN-new';const before=JSON.stringify(c.storage);
    vm.runInContext(part(background,'async function pauseFlowForResume(','async function stopFlowGeneration('),c.state);
    await assert.rejects(c.state.pauseFlowForResume(ident,1,run),/รอบเก่า/);
    assert.equal(JSON.stringify(c.storage),before);assert.equal(c.calls.length,0);
  });
  await test('missing owned tab never adopts other project',async()=>{
    const c=context(ownedStorage());delete c.storage[tabKey];
    vm.runInContext(part(background,'async function pauseFlowForResume(','async function stopFlowGeneration('),c.state);
    assert.equal((await c.state.pauseFlowForResume(ident,1,run)).reason,'no_registered_flow_tab');
    assert.equal(c.calls.length,0);
  });
  await test('stale inspection ID is rejected for same original run',async()=>{
    const c=context(ownedStorage());c.storage[`smartpostFlowInspection:${key}`]={commandId:'CMD-new',runId:run};
    vm.runInContext(part(background,'async function flowProgressOwnership(','async function aiProgressOwnership('),c.state);
    const progress={job_id:ident,shot_index:1,run_id:run,inspection_command_id:'CMD-old'};
    assert.equal((await c.state.flowProgressOwnership(progress,7)).reason,'stale_flow_inspection');
    assert.equal((await c.state.flowProgressOwnership({...progress,inspection_command_id:'CMD-new'},7)).active,true);
    assert.equal((await c.state.flowProgressOwnership({...progress,inspection_command_id:'CMD-new'},8)).reason,'stale_flow_tab');
  });
}

function loadContext(change={}) {
  const inspect = {jobId:ident,shotIndex:1,runId:run,commandId:'CMD-fresh',readOnly:true,
    checkpointRunId:run,checkpointStatus:'preparing',expectedUrl:project,requestedAt:Date.now(), ...change.inspect};
  const storage={smartpostFlowInspectOnly:inspect,...change.storage};
  const c=context(storage); const reports=[];let auto=0, inspections=0, monitors=0;
  const snapshot={activeProgress:false,videoCount:0,resultCardCount:0,failureCount:0,videoSources:[],...change.snapshot};
  Object.assign(c.state,{
    pkg:null,automationPaused:false,inspectionCommandId:'',readOnlyInspection:false,lastObservationMs:0,
    FLOW_VIDEO_PROMPT_GUARD:'fixture guard', FLOW_SUBMISSION_RECEIPTS_KEY:receiptsKey,
    location:{href:change.url||project,pathname:'/project/exact-project'},
    document:{body:{innerText:change.text||''}},
    $:()=>({textContent:''}),setStatus:()=>{},
    reportLatchedAttachmentFailure:async()=>false, loginRequired:()=>false,
    generationSnapshot:()=>snapshot,findPromptEditor:()=>null,
    promptHasAttachedMedia:()=>false,findGenerateButton:()=>null,
    confirmationKind:()=>change.confirmation||'',
    runAutoPrepareOnce:async()=>{auto++;return true;},
    inspectGenerationState:async()=>{inspections++;await c.state.report('generation_status_unknown','fixture passive result');},
    monitorGeneration:()=>{monitors++;},
  });
  c.state.chrome.runtime={sendMessage:async message=>{
    if(message.type==='GET_FLOW_PACKAGE')return {ok:true,package:{job_id:ident,shot_index:1,shot_count:3,run_id:run,video_prompt:'portrait motion',...(change.package||{})}};
    if(message.type==='IS_ACTIVE_FLOW_TAB')return {active:true};
    if(message.type==='FLOW_PROGRESS'){reports.push(message.progress);return {ok:true};}
    throw Error(`Unexpected message ${message.type}`);
  }};
  vm.runInContext(part(flow,'  const report = async (','  const copyText = async ('),c.state);
  vm.runInContext('globalThis.report = report;',c.state);
  vm.runInContext(part(flow,'  function ownedStoryPolicyTerminal(', '  function evaluateFlowPolicyFailure('),c.state);
  vm.runInContext(part(flow,'  async function resumeSubmittedCheckpoint()', '  async function autoPrepare()'),c.state);
  vm.runInContext(part(flow,'  async function load() {','  function queuePackageReload() {'),c.state);
  return {...c,reports,counts:()=>({auto,inspections,monitors})};
}
async function inspectionTests(){
  await test('known exact pre-submit checkpoint reports fresh proof without clicking',async()=>{
    const c=loadContext();await c.state.load();
    assert.equal(c.reports.at(-1).step,'checkpoint_preparing');
    assert(c.reports.every(r=>r.inspection_command_id==='CMD-fresh'));
    assert.equal(c.counts().auto,0);assert.equal(c.counts().inspections,0);
  });
  const refused=[
    ['unknown phase',{inspect:{checkpointStatus:'unknown'}}],
    ['submitted phase',{inspect:{checkpointStatus:'active'}}],
    ['wrong checkpoint run',{inspect:{checkpointRunId:'RUN-other'}}],
    ['expired current submit receipt',{storage:{[receiptsKey]:{[`${key}:${run}`]:{requestedAt:1}}}}],
    ['another run submit receipt',{storage:{[receiptsKey]:{[`${key}:RUN-earlier`]:{requestedAt:1}}}}],
    ['old owned monitor',{storage:{smartpostFlowMonitor:{jobId:ident,shotIndex:1,runId:run,startedAt:1}}}],
    ['visible render progress',{snapshot:{activeProgress:true}}],
    ['visible completed result',{snapshot:{videoCount:1,videoSources:['https://flow-content.google/video/a']}}],
    ['visible result card',{snapshot:{resultCardCount:1}}],
    ['visible policy failure',{snapshot:{failureCount:1}}],
    ['queued narrative',{text:'The video is queued'}],
    ['credit approval',{confirmation:'credit'}],
  ];
  for(const [name,change] of refused)await test(`inspection remains passive: ${name}`,async()=>{
    const c=loadContext(change);await c.state.load();
    assert(!c.reports.some(r=>r.step==='checkpoint_preparing'));assert.equal(c.counts().auto,0);
    assert.equal(c.reports.at(-1).inspection_command_id,'CMD-fresh');
  });
  await test('wrong project cannot consume request',async()=>{
    const c=loadContext({url:'https://flow.google.com/project/other'});await c.state.load();
    assert.equal(c.reports.at(-1).step,'checkpoint_mismatch');
    assert(c.storage.smartpostFlowInspectOnly);assert.equal(c.counts().auto,0);
  });
}
async function agedContinuousMonitorTests(){
  const oldMonitor={jobId:ident,shotIndex:1,runId:run,startedAt:1,
    projectPath:'/project/exact-project',repairRequestId:'',baseline:{videoCount:0},
    observedActiveGeneration:true,highestProgress:80,progressChangedAt:2};
  await test('old owned continuous monitor resumes observation without Generate',async()=>{
    const c=loadContext({storage:{smartpostFlowInspectOnly:null,smartpostFlowMonitor:oldMonitor},
      package:{mode:'story',flow_repair:{enabled:true,continuous:true}}});
    await c.state.load();
    assert.equal(c.counts().auto,0);
    assert.equal(c.counts().inspections,0);
    assert.equal(c.state.generationHighestProgress,80);
    assert(c.reports.some(r=>r.step==='generation_in_progress'));
    assert.equal(c.counts().monitors,1);
  });
  await test('read-only inspect of aged continuous monitor still arms passive watcher',async()=>{
    const c=loadContext({storage:{smartpostFlowMonitor:oldMonitor},
      inspect:{checkpointStatus:'active'},
      package:{mode:'story',flow_repair:{enabled:true,continuous:true}}});
    await c.state.load();
    assert.equal(c.counts().auto,0);
    assert.equal(c.counts().monitors,1);
    assert(c.counts().inspections>=1);
  });
  await test('aged monitor from different repair round cannot be adopted',async()=>{
    const c=loadContext({storage:{smartpostFlowInspectOnly:null,smartpostFlowMonitor:{...oldMonitor,repairRequestId:'OTHER'}},
      package:{mode:'story',flow_repair:{enabled:true,continuous:true},flow_repair_request_id:'CURRENT'}});
    await c.state.load();
    assert(!c.reports.some(r=>r.step==='generation_in_progress'));
  });
  for(const [name,monitorPatch] of [
    ['another run',{runId:'RUN-other'}],
    ['another project',{projectPath:'/project/other'}],
    ['another job',{jobId:'STORY-other'}],
  ])await test(`aged continuous monitor from ${name} is never adopted`,async()=>{
    const c=loadContext({storage:{smartpostFlowInspectOnly:null,smartpostFlowMonitor:{...oldMonitor,...monitorPatch}},
      package:{mode:'story',flow_repair:{enabled:true,continuous:true}}});
    await c.state.load();
    assert(!c.reports.some(r=>r.step==='generation_in_progress'));
    assert.equal(c.counts().monitors,0);
  });
}

function resumeContext(change={}){
  const storage=ownedStorage();delete storage[receiptsKey];delete storage.smartpostFlowMonitor;
  Object.assign(storage,change.storage||{});const c=context(storage);
  if(change.noOwned){delete c.storage[tabKey];delete c.storage.smartpostFlowCheckpoints;}
  c.state.chrome.scripting.executeScript=async()=>[{result:change.evidence||{editorFound:true,readyComposer:true,hasGenerationEvidence:false,bodyChildren:1,interactiveCount:1,textLength:40}}];
  const marker='      } else if (command.action === "resume_flow_workspace") {';
  const body=part(background,marker,'      } else if (command.action === "inspect_flow") {').slice(marker.length);
  // The production handler is inside the command loop (including404's early
  // fresh-review continue). Preserve that scope when executing its real body.
  vm.runInContext(`async function resume(command){for(const once of [1]){${body}}}`,c.state);
  return c;
}
async function resumeTests(){
  await test('same pre-submit workspace resume avoids reload and preserves other tabs',async()=>{
    const c=resumeContext();await c.state.resume({action:'resume_flow_workspace',job_id:ident,shot_index:1,run_id:run});
    assert.equal(c.storage.smartpostAutoFlow.runId,run);assert.equal(c.storage[tabKey],7);
    assert(!c.calls.some(x=>['reload','remove'].includes(x[0])));
    assert.equal(c.storage.smartpostFlowCheckpoints[key].url,project);
  });
  await test('missing bound workspace does not adopt an unrelated project',async()=>{
    const c=resumeContext({noOwned:true});await assert.rejects(c.state.resume({job_id:ident,shot_index:1,run_id:run}));
    assert(!c.calls.some(x=>['update','helper'].includes(x[0])));
  });
  await test('existing receipt prevents preparation even when old',async()=>{
    const c=resumeContext({storage:{[receiptsKey]:{[`${key}:RUN-earlier`]:{requestedAt:1}}}});
    await assert.rejects(c.state.resume({job_id:ident,shot_index:1,run_id:run}),/ไม่เคยส่งสร้าง/);
    assert(!c.calls.some(x=>x[0]==='helper'));
  });
  await test('live generation appearing after inspection prevents preparation',async()=>{
    const c=resumeContext({evidence:{editorFound:true,readyComposer:true,hasGenerationEvidence:true,bodyChildren:1,interactiveCount:1,textLength:40}});
    await assert.rejects(c.state.resume({job_id:ident,shot_index:1,run_id:run}));
    assert(!c.calls.some(x=>x[0]==='helper'));
  });
  await test('loading-only workspace cannot be treated as preparation-ready',async()=>{
    const c=resumeContext({evidence:{editorFound:false,readyComposer:false,hasGenerationEvidence:false}});
    await assert.rejects(c.state.resume({job_id:ident,shot_index:1,run_id:run}));
    assert(!c.calls.some(x=>x[0]==='helper'));
  });
}

async function aiResumeTests(){
  for(const provider of ['chatgpt','gemini']){
    await test(`${provider} owned AI resume retains exact chat without reload`,async()=>{
      const job='STORY-fixture',tabUrl=provider==='gemini'?'https://gemini.google.com/app/owned':'https://chatgpt.com/c/owned';
      const c=context({[`smartpostAIWebTab:${provider}:${job}`]:7});c.tabs.set(7,{id:7,url:tabUrl});
      c.state.bridgeFetch=async()=>({ok:true,json:async()=>({ok:true,package:{job:{image_ai_provider:provider}}})});
      c.state.openAIWebTab=async()=>{throw Error('Must reuse owned tab');};
      vm.runInContext(part(background,'async function startAIWebJob(','async function cancelChatGPTJob('),c.state);
      const result=await c.state.startAIWebJob(job,true,provider,false,run);
      assert.equal(result.tabId,7);assert(!c.calls.some(x=>['reload','remove'].includes(x[0])));
    });
  }
  await test('closed owned AI tab opens fresh provider rather than unrelated conversation',async()=>{
    const job='STORY-fixture',c=context({[`smartpostAIWebTab:chatgpt:${job}`]:99});
    c.tabs.set(7,{id:7,url:'https://chatgpt.com/c/user-private'});let opened=0;
    c.state.bridgeFetch=async()=>({ok:true,json:async()=>({ok:true,package:{job:{image_ai_provider:'chatgpt'}}})});
    c.state.openAIWebTab=async()=>{opened++;c.tabs.set(11,{id:11,url:'https://chatgpt.com/'});return 11;};
    vm.runInContext(part(background,'async function startAIWebJob(','async function cancelChatGPTJob('),c.state);
    assert.equal((await c.state.startAIWebJob(job,true,'chatgpt',false,run)).tabId,11);
    assert.equal(opened,1);assert(!c.calls.some(x=>['reload','remove'].includes(x[0])));
  });
  await test('old helper DOM is replaced without reloading project',async()=>{
    const c=context();let count=0;
    c.state.chrome.scripting.executeScript=async request=>{c.calls.push(['script',request]);return [{result:count++===0?{exists:true,version:'old',build:'old'}:{}}];};
    vm.runInContext(part(background,'async function ensureFlowHelper(','async function startAIWebJob('),c.state);
    assert.equal((await c.state.ensureFlowHelper(7)).reused,false);
    assert(!c.calls.some(x=>['reload','remove','update'].includes(x[0])));
    assert.equal(c.calls.filter(x=>x[0]==='script'&&x[1].files).length,1);
  });
}
(async()=>{await pauseTests();await inspectionTests();await agedContinuousMonitorTests();await resumeTests();await aiResumeTests();
  process.stdout.write(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
