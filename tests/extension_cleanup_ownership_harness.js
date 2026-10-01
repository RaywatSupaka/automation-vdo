const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

function fixture() {
  const storage = {
    smartpostAutomationTabIds: [11, 21],
    'smartpostAIWebTab:gemini:STORY-A': 11,
    'smartpostAIWebRun:STORY-A': 'RUN-A',
    'smartpostAIWebTab:gemini:STORY-B': 21,
    'smartpostAIWebRun:STORY-B': 'RUN-B',
    smartpostActiveJobId: 'STORY-B',
    smartpostFlowMonitor: {jobId: 'STORY-B', runId: 'RUN-B', tabId: 21},
    smartpostFlowSubmissionReceipts: {'STORY-A:1:RUN-A': {submittedAt: 10}},
  };
  const removed = [];
  let removeError = null, getError = null;
  const c = {
    AUTOMATION_TAB_IDS_KEY: 'smartpostAutomationTabIds',
    aiRunStorageKey: job => `smartpostAIWebRun:${job}`,
    isAutomationTabUrl: url => /^https:\/\/gemini\.google\.com\//.test(url),
    rememberedAutomationTabIds: async () => [...storage.smartpostAutomationTabIds],
    chrome: {storage: {local: {
      get: async () => structuredClone(storage),
      set: async values => Object.assign(storage, structuredClone(values)),
      remove: async keys => (Array.isArray(keys)?keys:[keys]).forEach(key => delete storage[key]),
    }}, tabs: {
      get: async id => { if(getError)throw getError; return {id, url: `https://gemini.google.com/app/${id}`}; },
      remove: async ids => {if(removeError)throw removeError;removed.push(...ids);},
    }},
  };
  vm.createContext(c);
  vm.runInContext(section('async function closeAutomationBrowser(', 'function bytesToBase64('), c);
  return {storage, removed, c, failRemove:error=>{removeError=error;}, failGet:error=>{getError=error;}};
}

(async () => {
  const results = [];
  {
    const f=fixture();
    f.storage['smartpostFlowTab:STORY-A:1']=31;
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-F1';
    f.storage['smartpostFlowTab:STORY-A:2']=32;
    f.storage['smartpostFlowRun:STORY-A:2']='RUN-F2';
    await f.c.closeAutomationBrowser('STORY-A','RUN-F1','CMD-SAVED',[],1);
    assert.deepEqual(f.removed,[31]);
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],11);
    assert.equal(f.storage['smartpostFlowTab:STORY-A:2'],32);
    assert(f.storage.smartpostFlowSubmissionReceipts['STORY-A:1:RUN-A']);
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-F1','CMD-SAVED',[],2),/BROWSER_CLEANUP_REVIEW/);
    results.push({kind:'saved_scene_keeps_ai_and_next_scene',pass:true});
  }
  {
    const f=fixture();
    f.storage['smartpostFlowTab:STORY-A:1']=31;
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-F1';
    f.storage['smartpostFlowTab:STORY-A:2']=31;
    f.storage['smartpostFlowRun:STORY-A:2']='RUN-F2';
    await f.c.closeAutomationBrowser('STORY-A','RUN-F1','CMD-SHARED',[],1);
    assert.deepEqual(f.removed,[]);
    results.push({kind:'shared_project_not_closed',pass:true});
  }
  for (const kind of ['other_job', 'new_run', 'legacy_conflicting_run']) {
    const f = fixture();
    if (kind === 'new_run') f.storage['smartpostAIWebRun:STORY-A'] = 'RUN-A-NEW';
    if(kind==='legacy_conflicting_run') {
      delete f.storage['smartpostAIWebRun:STORY-A'];
      f.storage['smartpostFlowRun:STORY-A:1']='RUN-A-NEW';
      f.storage['smartpostFlowTab:STORY-A:1']=31;
    }
    await f.c.closeAutomationBrowser('STORY-A', 'RUN-A');
    const expected = kind === 'other_job' ? [11] : [];
    try {
      assert.deepEqual(f.removed, expected);
      assert.equal(f.storage['smartpostAIWebRun:STORY-B'], 'RUN-B');
      assert.equal(f.storage.smartpostActiveJobId, 'STORY-B');
      assert.equal(f.storage.smartpostFlowMonitor.jobId, 'STORY-B');
      assert.deepEqual(f.storage.smartpostAutomationTabIds, kind === 'other_job' ? [21] : [11, 21]);
      assert(f.storage.smartpostFlowSubmissionReceipts['STORY-A:1:RUN-A']);
      results.push({kind, pass: true});
    } catch (error) { results.push({kind, pass: false, removed: f.removed, error: error.message}); }
  }
  async function check(kind, test) {
    try {await test();results.push({kind,pass:true});}
    catch(error){results.push({kind,pass:false,error:error.stack});}
  }
  await check('matching_flow_and_legacy_bindings',async()=>{
    const f=fixture();
    f.storage['smartpostChatGPTTab:STORY-A']=12;
    f.storage['smartpostFlowTab:STORY-A:1']=13;
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-A';
    f.storage.smartpostAutomationTabIds.push(12,13);
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.deepEqual([...f.removed].sort(),[11,12,13]);
    assert.equal(f.storage['smartpostFlowRun:STORY-A:1'],undefined);
    assert.equal(f.storage['smartpostFlowTab:STORY-A:1'],undefined);
  });
  await check('desktop_snapshot_closes_known_ai_and_flow_runs',async()=>{
    const f=fixture();
    f.storage['smartpostFlowTab:STORY-A:1']=13;
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-F';
    f.storage.smartpostAutomationTabIds.push(13);
    await f.c.closeAutomationBrowser('STORY-A','RUN-F','CMD-SNAPSHOT',['RUN-A','RUN-F']);
    assert.deepEqual([...f.removed].sort(),[11,13]);
    assert.equal(f.storage['smartpostAIWebRun:STORY-A'],undefined);
    assert.equal(f.storage['smartpostFlowRun:STORY-A:1'],undefined);
    assert.equal(f.storage['smartpostAIWebRun:STORY-B'],'RUN-B');
  });
  await check('desktop_snapshot_preserves_later_flow_run',async()=>{
    const f=fixture();
    f.storage['smartpostFlowTab:STORY-A:1']=13;
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-NEW';
    f.storage.smartpostAutomationTabIds.push(13);
    f.storage.smartpostFlowMonitor={jobId:'STORY-A',runId:'RUN-NEW',tabId:13};
    await f.c.closeAutomationBrowser('STORY-A','RUN-F','CMD-SNAPSHOT',['RUN-A','RUN-F']);
    assert.deepEqual(f.removed,[11]);
    assert.equal(f.storage['smartpostFlowRun:STORY-A:1'],'RUN-NEW');
    assert.equal(f.storage.smartpostFlowMonitor.runId,'RUN-NEW');
  });
  await check('legacy_tab_preserved_before_new_flow_tab_is_bound',async()=>{
    const f=fixture();delete f.storage['smartpostAIWebRun:STORY-A'];
    f.storage['smartpostFlowRun:STORY-A:1']='RUN-NEW';
    await f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-SNAPSHOT',['RUN-A']);
    assert.deepEqual(f.removed,[]);assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],11);
  });
  await check('preclose_run_change_is_rechecked',async()=>{
    const f=fixture();const originalGet=f.c.chrome.tabs.get;
    f.c.chrome.tabs.get=async id=>{const result=await originalGet(id);f.storage['smartpostAIWebRun:STORY-A']='RUN-NEW';return result;};
    await f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-SNAPSHOT',['RUN-A']);
    assert.deepEqual(f.removed,[]);assert.equal(f.storage['smartpostAIWebRun:STORY-A'],'RUN-NEW');
  });
  await check('saved_plan_cannot_broaden_run_snapshot',async()=>{
    const f=fixture();f.failRemove(Error('worker interrupted'));
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X',['RUN-A']));
    f.failRemove(null);
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X',['RUN-A','RUN-NEW']),/BROWSER_CLEANUP_REVIEW/);
    assert.deepEqual(f.removed,[]);
  });
  await check('invalid_run_snapshot_does_not_close',async()=>{
    for(const value of ['RUN-A', ['https://secret.invalid/token'],Array(101).fill('RUN-A')]) {
      const f=fixture();await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X',value),/BROWSER_CLEANUP_REVIEW/);
      assert.deepEqual(f.removed,[]);
    }
  });
  await check('shared_tab_survives_other_owner',async()=>{
    const f=fixture();f.storage['smartpostAIWebTab:gemini:STORY-B']=11;
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.deepEqual(f.removed,[]);assert.equal(f.storage['smartpostAIWebRun:STORY-A'],'RUN-A');
  });
  await check('failed_close_keeps_storage_and_plan',async()=>{
    const f=fixture();f.failRemove(Error('browser unavailable'));
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X'),/browser unavailable/);
    assert.deepEqual(f.removed,[]);assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],11);
    assert.deepEqual(f.storage['smartpostBrowserCleanup:CMD-X'].tab_ids,[11]);
  });
  await check('crash_replay_excludes_new_same_run_tab',async()=>{
    const f=fixture();f.failRemove(Error('worker interrupted'));
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X'));
    f.failRemove(null);f.storage['smartpostAIWebTab:gemini:STORY-A']=31;f.storage.smartpostAutomationTabIds.push(31);
    await f.c.closeAutomationBrowser('STORY-A','RUN-A','CMD-X');
    assert.deepEqual(f.removed,[]);assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],31);
  });
  await check('explicit_global_plan_excludes_new_registered_tab',async()=>{
    const f=fixture();f.failRemove(Error('worker interrupted'));
    await assert.rejects(f.c.closeAutomationBrowser('','','CMD-G'));
    f.failRemove(null);f.storage['smartpostAIWebTab:gemini:STORY-C']=31;f.storage.smartpostAutomationTabIds.push(31);
    await f.c.closeAutomationBrowser('','','CMD-G');
    assert.deepEqual(f.removed,[11,21]);assert.deepEqual(f.storage.smartpostAutomationTabIds,[31]);
  });
  await check('explicit_global_keeps_rebound_tab',async()=>{
    const f=fixture();f.failRemove(Error('worker interrupted'));
    await assert.rejects(f.c.closeAutomationBrowser('','','CMD-G'));
    f.failRemove(null);f.storage['smartpostAIWebRun:STORY-A']='RUN-NEW';
    await f.c.closeAutomationBrowser('','','CMD-G');
    assert.deepEqual(f.removed,[21]);assert.equal(f.storage['smartpostAIWebRun:STORY-A'],'RUN-NEW');
  });
  await check('read_failure_is_not_absent_tab',async()=>{
    const f=fixture();f.failGet(Error('browser unavailable'));
    await assert.rejects(f.c.closeAutomationBrowser('STORY-A','RUN-A'),/browser unavailable/);
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],11);
  });
  await check('confirmed_missing_tab_cleans_old_binding',async()=>{
    const f=fixture();f.failGet(Error('No tab with id: 11.'));
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],undefined);
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-B'],21);
  });
  await check('real_set_active_job_during_registry_write_survives',async()=>{
    const f=fixture();f.storage.smartpostActiveJobId='STORY-A';f.storage.smartpostActiveShotIndex=4;
    f.c.sendResponse=()=>{};f.c.message={type:'SET_ACTIVE_JOB',jobId:'JOB-B'};
    const activeHandler='(async()=>{'+section('    if (message?.type === "SET_ACTIVE_JOB") {','    if (message?.type === "GET_FLOW_PACKAGE") {')+'})()';
    const originalSet=f.c.chrome.storage.local.set;
    f.c.chrome.storage.local.set=async values=>{
      await originalSet(values);
      if(Object.hasOwn(values,'smartpostAutomationTabIds'))await vm.runInContext(activeHandler,f.c);
    };
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.deepEqual(f.removed,[11]);assert.equal(f.storage.smartpostActiveJobId,'JOB-B');
    assert.equal(f.storage.smartpostActiveShotIndex,4,'Preserve the active selection pair when either field changed');
  });
  await check('late_rebound_run_tab_and_monitor_survive_registry_write',async()=>{
    const f=fixture();f.storage.smartpostActiveJobId='STORY-A';f.storage.smartpostActiveShotIndex=4;
    f.storage.smartpostFlowMonitor={jobId:'STORY-A',runId:'RUN-A',tabId:11};
    const originalSet=f.c.chrome.storage.local.set;
    f.c.chrome.storage.local.set=async values=>{
      await originalSet(values);
      if(Object.hasOwn(values,'smartpostAutomationTabIds'))Object.assign(f.storage,{
        'smartpostAIWebTab:gemini:STORY-A':31,'smartpostAIWebRun:STORY-A':'RUN-NEW',
        smartpostActiveShotIndex:5,smartpostFlowMonitor:{jobId:'STORY-A',runId:'RUN-NEW',tabId:31}});
    };
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.deepEqual(f.removed,[11]);assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],31);
    assert.equal(f.storage['smartpostAIWebRun:STORY-A'],'RUN-NEW');
    assert.equal(f.storage.smartpostFlowMonitor.runId,'RUN-NEW');
    assert.equal(f.storage.smartpostActiveJobId,'STORY-A');assert.equal(f.storage.smartpostActiveShotIndex,5);
  });
  await check('late_same_run_replacement_preserves_unchanged_run_key',async()=>{
    const f=fixture();const originalSet=f.c.chrome.storage.local.set;
    f.c.chrome.storage.local.set=async values=>{
      await originalSet(values);
      if(Object.hasOwn(values,'smartpostAutomationTabIds'))f.storage['smartpostAIWebTab:gemini:STORY-A']=31;
    };
    await f.c.closeAutomationBrowser('STORY-A','RUN-A');
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],31);
    assert.equal(f.storage['smartpostAIWebRun:STORY-A'],'RUN-A');
  });
  for(const fail of [false,true])await check(`real_command_handler_${fail?'failure':'success'}`,async()=>{
    const f=fixture(),acks=[],events=[];
    const command={id:'CMD-CLOSE',action:'close_automation_browser',job_id:'STORY-A',run_id:'RUN-A',lease_token:'LEASE-X'};
    const originalRemove=f.c.chrome.tabs.remove;
    f.c.chrome.tabs.remove=async ids=>{events.push('remove');await originalRemove(ids);};
    if(fail)f.failRemove(Error('browser remove failed'));
    Object.assign(f.c,{AbortController,setTimeout,clearTimeout,CLIENT_ID:'fixture',BRIDGE:'mock://bridge',
      COMMAND_OUTCOMES_KEY:'smartpostCommandOutcomes',pollAICovers:async()=>{},rememberCommandRun:async()=>{},
      reportExtensionTrace:async()=>{},reportAICommandFailure:async()=>{},reportFlowCommandFailure:async()=>{},
      bridgeFetch:async(url,options={})=>{
        if(url.includes('/commands?'))return {json:async()=>({commands:[command]})};
        events.push('ack');acks.push(JSON.parse(options.body));return {ok:true,json:async()=>({ok:true})};
      }});
    vm.runInContext(section('function commandOutcomeMatches(', 'async function reportAICommandFailure('),f.c);
    vm.runInContext(section('async function pollCommands()', 'async function extensionTick()'),f.c);
    await f.c.pollCommands();
    assert.deepEqual(events,['remove','ack']);assert.equal(acks[0].ok,!fail);
    assert.equal(acks[0].run_id,'RUN-A');
    assert.equal(f.storage.smartpostCommandOutcomes['CMD-CLOSE'].ok,!fail);
    assert.deepEqual(f.removed,fail?[]:[11]);
    f.storage['smartpostAIWebTab:gemini:STORY-A']=31;f.storage.smartpostAutomationTabIds.push(31);
    await f.c.pollCommands();
    assert.equal(events.filter(event=>event==='remove').length,1,'ACK replay cannot close replacement tabs');
    assert.equal(f.storage['smartpostAIWebTab:gemini:STORY-A'],31);
  });
  console.log(JSON.stringify(results));
  if (results.some(result => !result.pass)) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
