// Actual extension source in a deterministic Chrome/DOM simulation.
// No browser launch, provider traffic, credits or customer workspace writes.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const bg = fs.readFileSync(path.join(root, 'browser_extension/background.js'), 'utf8');
const flow = fs.readFileSync(path.join(root, 'browser_extension/flow.js'), 'utf8');
const helper = bg.slice(bg.indexOf('function resolveFlowGenerateClickTarget('), bg.indexOf('const AI_WEB ='));
const handler = bg.slice(bg.indexOf('    if (message?.type === "CLICK_FLOW_GENERATE")'), bg.indexOf('    sendResponse({ ok: false, error: "unknown_message" });'));
const readState = flow.slice(flow.indexOf('  async function readGenerationState()'), flow.indexOf('  $(".copy-prompt").addEventListener'));
const policy = flow.slice(flow.indexOf('  function currentStoryFailureCard('), flow.indexOf('  function generationSnapshot('));
let cases = 0;
const copy = (value) => JSON.parse(JSON.stringify(value));

function page(options = {}) {
  let box = { left: 700, top: 600, width: 40, height: 40, ...options.box };
  const state = { scrolls: 0, options };
  const rectangle = () => ({ ...box, right: box.left + box.width, bottom: box.top + box.height });
  const button = {
    tagName: 'BUTTON', textContent: options.unrelated ? 'Settings' : 'arrow_forward',
    disabled: !!options.disabled,
    getBoundingClientRect: rectangle,
    getAttribute: (key) => key === 'aria-label' ? (options.unrelated ? 'Settings' : 'เริ่มสร้าง') : null,
    hasAttribute: () => false,
    matches: () => !options.unrelated,
    contains: (element) => element === child,
    scrollIntoView: () => { state.scrolls++; if (!options.noScroll) box = { ...box, left: 700, top: 600 }; }
  };
  const child = { tagName: 'SPAN' };
  const editor = { getBoundingClientRect: () => ({ left: 400, right: 760, top: 300, bottom: 640, width: 360, height: 340 }),
    closest: () => null };
  const document = {
    getElementById: () => null,
    querySelectorAll: (query) => query === 'button' ? options.ambiguous ? [button, button] : [button] : [editor],
    elementFromPoint: (x, y) => options.nullHit || x >= 1000 || y >= 800 ? null : options.blocked ? { tagName: 'DIV' } : child
  };
  Object.assign(state, { document, getComputedStyle: () => ({ display: 'block', visibility: 'visible', pointerEvents: 'auto' }),
    innerWidth: 1000, innerHeight: 800, move: (left, top) => { box = { ...box, left, top }; } });
  return state;
}

async function dispatch(options = {}) {
  const dom = page(options);
  const events = [], storage = copy(options.storage || {}), responses = [];
  const locks = new Set();
  let probes = 0, hovered = 0;
  const chrome = {
    tabs: { update: async () => { events.push('activate'); if (options.activationMoves) dom.move(1200, 930); } },
    windows: { update: async () => events.push('focus') },
    storage: { local: {
      get: async (key) => { if (options.readFails) throw Error('read_failed'); return Object.fromEntries((Array.isArray(key)?key:[key]).map(k=>[k,storage[k]===undefined?undefined:copy(storage[k])])); },
      set: async (value) => { events.push('receipt'); if (options.writeFails) throw Error('write_failed'); Object.assign(storage, copy(value));
        if (options.storageMoves) dom.move(710, 600); }
    } },
    scripting: { executeScript: async ({ func, args = [] }) => {
      if (func.name === 'checkWatch') return [{result:!(options.settingsChangeAfterReceipt && events.includes('receipt'))}];
      if (func.name !== 'resolveFlowGenerateClickTarget') return [{ result: { outsideComposerMatches: options.alreadySent ? 1 : 0 } }];
      events.push('probe'); probes++;
      const ctx = vm.createContext(dom);
      vm.runInContext(helper, ctx);
      return [{ result: ctx.resolveFlowGenerateClickTarget(...args) }];
    } },
    debugger: {
      onEvent: { addListener: () => events.push('listen'), removeListener: () => events.push('unlisten') },
      attach: async () => { events.push('attach'); if (options.attachFails) throw Error('attach_failed'); if (options.debuggerMoves) dom.move(1200, 920); },
      detach: async () => events.push('detach'),
      sendCommand: async (_target, method, params) => {
        if (method === 'Network.enable') return;
        assert.equal(method, 'Input.dispatchMouseEvent'); events.push(params.type);
        if (params.type === 'mouseMoved') {
          hovered++;
          if (options.hoverMoves && hovered === 1) dom.move(720, 600);
          if (options.unstable) dom.move(700 + hovered * 5, 600);
        }
        if (params.type === options.failEvent) throw Error('dispatch_failed');
      }
    }
  };
  const context = vm.createContext({ chrome, ...dom, flowGenerateInFlight: locks, flowAttachmentClaimsInFlight: new Set(),
    FLOW_SUBMISSION_RECEIPTS_KEY: 'receipts',
    readFlowAttachmentTerminal: async () => null, dismissStaleFlowAssetPicker: async () => {},
    message: { type: 'CLICK_FLOW_GENERATE', job_id: 'PRESENTER-TEST', shot_index: 1, run_id: 'RUN-A', prompt_guard: 'Unique prompt marker at least twenty four characters' },
    sender: { tab: { id: 7, windowId: 3 } }, sendResponse: (value) => responses.push(copy(value)),
    setTimeout: (callback) => callback(), Date, console, ...(options.context || {}) });
  context.BRIDGE='http://fixture.invalid';context.flowRunStorageKey=(job,index)=>`run:${job}:${index}`;
  context.SmartFlowSettings={checkWatch:function checkWatch(){}};
  context.bridgeFetch=async()=>({ok:true,json:async()=>({ok:true,package:{scene_video_plan:
    options.planChanged || options.planChangeAfterReceipt && events.includes('receipt') ? {...options.plan,attempt_id:'stale'} : options.plan}})});
  if(options.plan)Object.assign(context.message,{scene_video_plan:options.plan,settings_verification_id:'proof'});
  vm.runInContext(helper, context);
  vm.runInContext(bg.slice(bg.indexOf('function sceneVideoPlanMatches('),bg.indexOf('async function aiProgressOwnership(')),context);
  if(options.plan)vm.runInContext(`flowSceneSettingsProofs.set('proof',{tabId:7,jobId:'PRESENTER-TEST',runId:'RUN-A',binding:${JSON.stringify(options.plan)}})`,context);
  try { await vm.runInContext(`(async () => { ${handler} })()`, context); }
  catch (error) { responses.push({ ok: false, error: error.message }); }
  assert.equal(locks.size, 0, 'all return/error paths release only the in-flight lock');
  assert.equal(responses.length, 1);
  return { result: responses[0], events, storage, probes, dom };
}

async function monitor(text, snapshotChanges = {}, confirmation = '') {
  const calls = [], reports = [], writes = [];
  let snapshot = { progressValues: [], activeProgress: false, videoCount: 0, resultCardCount: 0,
    failureCount: 0, visibleFailureCardCount: 0, visibleFailureCards: [], failureCardFingerprints: [], ...snapshotChanges };
  const storage = { smartpostFlowMonitor: { startedAt: Date.now() - 20 * 60 * 1000 } };
  const context = vm.createContext({
    Date, Set, inspectionCommandId: 'inspect-owned', automationPaused: false, readOnlyInspection: true,
    loginRequired: () => false, visible: () => true, report: async (step, message, detail) => reports.push({ step, message, detail }),
    document: { body: { innerText: text }, getElementById: () => null, querySelectorAll: () => [] },
    confirmationKind: () => confirmation, generationSnapshot: () => snapshot,
    generationProgressSignature: '', generationProgressChangedAt: Date.now(), generationProgressDisappearedAt: 0,
    generationHighestProgress: 0, generationStartedAt: Date.now() - 20 * 60 * 1000,
    observedActiveGeneration: false, generationUnknownChecks: 9, generationFailureChecks: 0,
    generationBaseline: { videoCount: 0, resultCardCount: 0, failureCount: 0, failureCardFingerprints: [], visibleFailureCardCount: 0 },
    creditExhausted: () => false,
    chrome: { storage: { local: {
      get: async () => copy(storage), set: async (value) => { Object.assign(storage, copy(value)); writes.push(value); },
      remove: async (key) => { delete storage[key]; calls.push(`remove:${key}`); }
    } }, runtime: { sendMessage: async (message) => { calls.push(message.type); assert.equal(message.type, 'AUTO_DOWNLOAD_FLOW_RESULT'); return { ok: true, filename: 'test.mp4' }; } } },
    saveFlowProjectCheckpoint: async (status) => calls.push(`checkpoint:${status}`),
    stopGenerationMonitor: () => calls.push('stop'), promptHasAttachedMedia: () => true,
    findPromptEditor: () => ({ innerText: 'draft' }), pkg: { job_id: 'PRESENTER-TEST', shot_index: 1, run_id: 'RUN-A', video_prompt: 'draft' },
    location: { pathname: '/project/fixture', reload: () => { throw Error('must not refresh queued work'); } },
    setTimeout: () => { throw Error('must not schedule a refresh'); }
  });
  const promptMatch = flow.slice(flow.indexOf('  function flowPromptMatches('), flow.indexOf('  function findPromptEditor('));
  vm.runInContext(promptMatch + policy + readState, context);
  await context.readGenerationState();
  return { reports, calls, context, storage };
}

(async () => {
  for (const options of [{ nullHit: true }, { blocked: true }, { disabled: true }, { unrelated: true },
    { ambiguous: true }, { box: { left: 1855, top: 910 }, noScroll: true }, { unstable: true }, { attachFails: true }]) {
    const value = await dispatch(options);
    assert.equal(value.result.ok, false); assert.equal(value.result.notDispatched, true);
    assert.ok(!value.events.includes('mousePressed')); assert.ok(!value.events.includes('receipt'));
    if (!options.attachFails) assert.ok(value.events.includes('detach'));
    cases++;
  }
  for (const options of [{}, { activationMoves: true }, { debuggerMoves: true }, { hoverMoves: true }, { box: { left: 1855, top: 910 } }]) {
    const value = await dispatch(options);
    assert.equal(value.result.ok, true); assert.equal(value.result.point.target, 'SPAN');
    assert.equal(value.events.filter(x => x === 'mousePressed').length, 1);
    assert.equal(value.events.filter(x => x === 'mouseReleased').length, 1);
    assert.ok(value.events.indexOf('activate') < value.events.indexOf('probe'));
    assert.ok(value.events.indexOf('attach') < value.events.indexOf('probe'));
    assert.ok(value.events.indexOf('receipt') < value.events.indexOf('mousePressed'));
    assert.equal(value.events.at(-1), 'detach'); cases++;
  }
  for (const failEvent of ['mousePressed', 'mouseReleased']) {
    const value = await dispatch({ failEvent });
    assert.equal(value.result.dispatchUncertain, true); assert.equal(value.result.notDispatched, false);
    assert.equal(value.events.filter(x => x === 'mousePressed').length, 1);
    assert.ok(value.storage.receipts['PRESENTER-TEST:1:RUN-A']);
    const resumed = await dispatch({ storage: value.storage });
    assert.equal(resumed.result.duplicateBlocked, true); assert.equal(resumed.probes, 0); cases++;
  }
  for (const requestedAt of [Date.now(), Date.now() - 72 * 3600 * 1000]) {
    const value = await dispatch({ storage: { receipts: { 'PRESENTER-TEST:1:RUN-A': { requestedAt } } } });
    assert.equal(value.result.duplicateBlocked, true); assert.equal(value.probes, 0); cases++;
  }
  const existing = await dispatch({ alreadySent: true });
  assert.equal(existing.result.duplicateBlocked, true); assert.equal(existing.probes, 0); cases++;
  const plan={version:1,scene_index:1,plan_revision:1,selection_id:'s',attempt_id:'a',provider:'google_flow',settings_sha256:'a'.repeat(64)};
  for(const extra of [{planChanged:true},{planChangeAfterReceipt:true},{settingsChangeAfterReceipt:true}]){
    const value=await dispatch({plan,...extra});
    assert.equal(value.result.notDispatched,true);assert(!value.events.includes('mousePressed'));
    if(!extra.planChanged)assert(value.storage.receipts['PRESENTER-TEST:1:RUN-A']);cases++;
  }
  {const value=await dispatch({plan,failEvent:'mousePressed'});assert.equal(value.result.dispatchUncertain,true);
    assert.deepEqual(value.storage.receipts['PRESENTER-TEST:1:RUN-A'].scene_video_plan,plan);
    const resumed=await dispatch({plan,storage:value.storage});assert.equal(resumed.result.duplicateBlocked,true);
    assert(!resumed.events.includes('mousePressed'));cases++;}
  for (const options of [{ readFails: true }, { writeFails: true }, { storageMoves: true }]) {
    const value = await dispatch(options);
    assert.equal(value.result.ok, false); assert.ok(!value.events.includes('mousePressed')); cases++;
  }
  // User contract: high demand and real queue remain waiting, even after
  // twenty minutes and many checks. Never error/retry/refresh/upload/send.
  for (const text of [
    'Flow is currently experiencing high demand, affecting video generation. Requests may need to be retried at a later time.',
    'high demand', 'ความต้องการสูง', 'วิดีโอได้รับการจัดคิวเรียบร้อยแล้ว', 'กำลังรอคิว',
    "I've started generating your vertical cinematic video. It's currently in the queue and will be ready shortly.",
    'Your video has been queued due to high demand',
    'ล้มเหลว\nYour video is still waiting in the queue'
  ]) {
    const value = await monitor(text);
    assert.equal(value.reports.at(-1).step, 'generation_in_progress', text);
    assert.equal(value.reports.at(-1).detail.failure_code, '');
    assert.ok(value.storage.smartpostFlowMonitor); assert.ok(!value.calls.includes('stop'));
    assert.ok(value.calls.every(x => x === 'checkpoint:active')); cases++;
  }
  const progress = await monitor('high demand', { activeProgress: true, progressValues: [58] });
  assert.equal(progress.reports.at(-1).step, 'generation_in_progress'); cases++;
  const finished = await monitor('high demand', { videoCount: 1, resultCardCount: 1 });
  assert.equal(finished.reports.at(-1).step, 'generation_complete');
  assert.equal(finished.calls.filter(x => x === 'AUTO_DOWNLOAD_FLOW_RESULT').length, 1); cases++;
  const unknown = await monitor('Unchanged draft without queue or render evidence');
  assert.equal(unknown.reports.at(-1).step, 'error');
  assert.equal(unknown.reports.at(-1).detail.failure_code, 'FLOW_SEND_REVIEW');
  assert.ok(!unknown.calls.includes('AUTO_DOWNLOAD_FLOW_RESULT')); cases++;
  const approval = await monitor('approve credit', {}, 'credit');
  assert.equal(approval.reports.at(-1).step, 'awaiting_credit_approval'); cases++;
  console.log(JSON.stringify({ ok: true, cases }));
})().catch(error => { console.error(error); process.exitCode = 1; });
