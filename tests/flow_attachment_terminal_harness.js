const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const flow = fs.readFileSync(path.join(root, "browser_extension/flow.js"), "utf8");
const background = fs.readFileSync(path.join(root, "browser_extension/background.js"), "utf8");
const section = (source, start, end) => {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing source section: ${start}`);
  return source.slice(first, last);
};
const terminalKey = "smartpostFlowAttachmentTerminals";
const receiptKey = "smartpostFlowSubmissionReceipts";
const scopeKey = "JOB-A:2:RUN-A";
const attemptKey = "JOB-A:2:project-a";
const sender = { tab: { id: 12, url: "https://flow.google.com/project/project-a" } };
const request = { jobId: "JOB-A", shotIndex: 2, runId: "RUN-A", requestedAt: 100000, waitingForManualAttachment: true };

function fixture() {
  let now = 100000, nextId = 1, generated = 0;
  const timers = new Map(), reports = [];
  const state = { image: false, text: "", labels: [], confirmation: "", login: false, credit: false,
    snapshot: { videoCount: 0, resultCardCount: 0, progressValues: [], activeProgress: false } };
  const storage = {
    "smartpostFlowTab:JOB-A:2": 12, "smartpostFlowRun:JOB-A:2": "RUN-A",
    smartpostFlowAttachmentAttempts: { [attemptKey]: {
      startedAt: 95000, status: "composer_proof_missing_after_upload", composerProof: false,
      runId: "RUN-A", attemptCount: 1
    } }
  };
  const context = {
    console, Date: { now: () => now },
    FLOW_ATTACHMENT_TERMINALS_KEY: terminalKey, FLOW_ATTACHMENT_ATTEMPTS_KEY: "smartpostFlowAttachmentAttempts",
    FLOW_SUBMISSION_RECEIPTS_KEY: receiptKey, FLOW_ATTACHMENT_GRACE_MS: 30000,
    flowGenerateInFlight: new Set(), flowAttachmentClaimsInFlight: new Set(),
    pkg: { job_id: "JOB-A", shot_index: 2, run_id: "RUN-A", video_prompt: "Create exactly one playable vertical video. Original shot two prompt." },
    location: { href: sender.tab.url },
    manualAttachmentObserver: null, manualAttachmentCheckTimer: null, manualAttachmentExpiryTimer: null,
    manualAttachmentDecisionInFlight: false, autoPreparePromise: null,
    lastClickResult: null, generationStartedAt: 0, generationMonitorActive: false, observedActiveGeneration: false,
    MutationObserver: class { observe() {} disconnect() {} },
    setTimeout(callback, delay) { const id = nextId++; timers.set(id, { at: now + delay, callback }); return id; },
    clearTimeout(id) { timers.delete(id); },
    generationSnapshot: () => state.snapshot,
    visible: () => true,
    findPromptEditor: () => ({ innerText: context.pkg.video_prompt }),
    findGenerateButton: () => ({}), promptHasAttachedMedia: () => state.image,
    confirmationKind: () => state.confirmation, loginRequired: () => state.login, creditExhausted: () => state.credit,
    document: { body: {}, querySelectorAll: () => state.labels.map((label) => ({ getAttribute: () => label, innerText: label })) },
    report: async (step, message, extra) => reports.push({ step, message, ...extra }),
    setStatus: () => {}, runAutoPrepareOnce: async () => { generated++; },
    flowProjectId: (url) => String(url || "").match(/\/project\/([^/?#]+)/)?.[1] || "",
    flowRunStorageKey: (job, shot) => `smartpostFlowRun:${job}:${shot}`,
    chrome: { storage: { local: {
      async get(keys) { return structuredClone(Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map((key) => [key, storage[key]]))); },
      async set(values) { Object.assign(storage, structuredClone(values)); },
      async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) delete storage[key]; }
    } }, runtime: {} }
  };
  Object.defineProperty(context.document.body, "innerText", { get: () => `${context.pkg.video_prompt}\n${state.text}` });
  vm.createContext(context);
  vm.runInContext(section(background, "function sceneVideoPlanMatches(", "async function aiProgressOwnership("), context);
  vm.runInContext(section(background, "async function readFlowAttachmentTerminal(", "// A command poll"), context);
  vm.runInContext(section(flow, "function stopManualAttachmentWatch(", "function flowAttachmentAttemptKey("), context);
  context.chrome.runtime.sendMessage = async (message) => message.type === "IS_ACTIVE_FLOW_TAB"
    ? context.flowProgressOwnership(message, sender.tab.id)
    : message.type === 'RESUME_FLOW_ATTACHMENT_SELECTION' ? context.resumeFlowAttachmentSelection(message,sender)
    : context.latchFlowAttachmentFailure(message, sender);
  const selectModel = section(background, 'if (message?.type === "SELECT_AI_MODEL"', 'if (message?.type === "CLICK_AI_SEND_BUTTON")');
  vm.runInContext(`async function testModel(message, sender) { let response; const sendResponse = (value) => { response = value; }; await (async () => { ${selectModel} })(); return response; }`, context);
  context.chrome.scripting = { executeScript: async () => [{ result: { ok: true, alreadySelected: true, modePoint: { x: 1, y: 1 }, modeLabel: "Thinking" } }] };
  // Execute the whole handler so its lock-cleanup finally is also tested.
  const generate = section(background, 'if (message?.type === "CLICK_FLOW_GENERATE")', 'sendResponse({ ok: false, error: "unknown_message" });');
  vm.runInContext(`async function testGenerate(message, sender) { let response; const sendResponse = (value) => { response = value; }; await (async () => { ${generate} })(); return response; }`, context);
  async function advance(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      now = next[1].at;
      timers.delete(next[0]);
      await next[1].callback();
      await new Promise(setImmediate);
    }
    now = end;
    await new Promise(setImmediate);
  }
  return { context, storage, reports, state, advance, generated: () => generated };
}

async function tests() {
  let f = fixture();
  for (const [provider, model, url] of [["chatgpt", "thinking", "https://chatgpt.com/"], ["gemini", "pro", "https://gemini.google.com/app"]]) {
    const result = await f.context.testModel({ type: "SELECT_AI_MODEL", provider, model }, { tab: { id: 12, url } });
    assert.equal(result.ok, true, "Explicit AI model selection must not refer to Flow progress");
  }
  await f.context.watchForManualAttachment(request);
  await f.advance(29999);
  assert.equal(f.storage[terminalKey], undefined, "Never fallback before the bounded grace");
  await f.advance(1);
  assert.equal(f.storage[terminalKey][scopeKey].failure_code, "FLOW_ATTACHMENT_UNCONFIRMED");
  assert.equal(f.storage.smartpostAutoFlow, undefined);
  assert.equal(f.reports.at(-1).step, "attachment_failed");
  assert.equal(f.generated(), 0);
  f.state.image = true;
  assert.equal(await f.context.resumeAfterManualAttachment(request), false, "Late attachment cannot submit after fallback latch");
  const blocked = await f.context.testGenerate({ type: "CLICK_FLOW_GENERATE", job_id: "JOB-A", shot_index: 2, run_id: "RUN-A" }, sender);
  assert.equal(blocked.attachmentTerminalBlocked, true);
  assert.equal(await f.context.readFlowAttachmentTerminal("JOB-A", 3, "RUN-A"), null, "Next shot is independent");
  await f.context.watchForManualAttachment(request);
  assert.equal(f.storage.smartpostAutoFlow, undefined, "Reinjection must not re-arm terminal request");

  const stopped=structuredClone(f.storage);
  function prepareSelectionResume() {
    const next=fixture();Object.assign(next.storage,structuredClone(stopped));
    Object.assign(next.storage.smartpostFlowAttachmentAttempts[attemptKey],{fileSet:true,mediaReady:true,method:'golden_hidden_file_input',uploadedAt:96000});
    next.storage.smartpostAutoFlow={...request,requestedAt:150000,waitingForManualAttachment:false};
    next.storage.smartpostFlowReferenceFile={jobId:'JOB-A',shotIndex:2,filename:'scene_02 (35).png'};
    return next;
  }
  f=prepareSelectionResume();
  assert.equal((await f.context.readFlowAttachmentTerminal('JOB-A',2,'RUN-A')).attachment_failure_evidence.selection_recovery_available,true);
  delete f.storage.smartpostFlowAttachmentAttempts[attemptKey].fileSet;
  assert.equal((await f.context.readFlowAttachmentTerminal('JOB-A',2,'RUN-A')).attachment_failure_evidence.selection_recovery_available,true,'legacy completed upload did not persist fileSet');
  assert.equal(await f.context.reportLatchedAttachmentFailure(),false,'new command may resume existing uploaded asset');
  assert(f.storage[terminalKey][scopeKey].attachment_failure_evidence,'original terminal retained');
  assert(f.storage[terminalKey][scopeKey].selection_recovery.authorized_at);
  assert(f.storage.smartpostFlowAttachmentAttempts[attemptKey].selectionRecovery);
  assert.equal(await f.context.readFlowAttachmentTerminal('JOB-A',2,'RUN-A'),null);
  assert.equal(f.generated(),0,'authorization does not upload or generate');
  const recoveryMessage={job_id:'JOB-A',shot_index:2,run_id:'RUN-A',evidence:f.context.attachmentWaitSnapshot()};
  assert.equal((await f.context.resumeFlowAttachmentSelection(recoveryMessage,sender)).ok,false,'cannot authorize twice');
  for(const guard of [
    x=>{x.storage.smartpostAutoFlow.waitingForManualAttachment=true;},
    x=>{x.storage.smartpostAutoFlow.requestedAt=100000;},
    x=>{x.storage.smartpostFlowAttachmentAttempts[attemptKey].fileSet=false;},
    x=>{x.storage.smartpostFlowAttachmentAttempts[attemptKey].mediaReady=false;},
    x=>{x.storage.smartpostFlowReferenceFile.jobId='OTHER';},
    x=>{x.storage[receiptKey]={old:{jobId:'JOB-A',shotIndex:2}};},
    x=>{x.storage.smartpostFlowPausedTabs={12:true};},
    x=>{x.state.snapshot.videoCount=1;},
    x=>{x.state.labels=['Stop'];},
    x=>{x.storage[terminalKey][scopeKey].attachment_failure_evidence.project_id='other';},
    x=>{x.storage['smartpostFlowTab:JOB-A:2']=99;},
    x=>{x.storage.smartpostFlowMonitor={jobId:'JOB-A',shotIndex:2};},
    x=>{x.storage.smartpostFlowAttachmentAttempts[attemptKey].status='started';}
  ]) {
    f=prepareSelectionResume();guard(f);
    assert.equal(await f.context.reportLatchedAttachmentFailure(),true,'unsafe recovery remains terminal');
    assert.equal(f.storage[terminalKey][scopeKey].selection_recovery,undefined);
  }
  // Execute the real closed-tab recovery branch: it may reopen ONLY the saved
  // pre-submit project. It must never bootstrap a new Flow project/home.
  const reopen=section(background,'        let projectTab = await pickHealthyFlowProjectTab(preferredTabs, preferredTabs);','        const presenterResume');
  f=prepareSelectionResume();const created=[];
  f.context.command={job_id:'JOB-A',shot_index:2,run_id:'RUN-A'};f.context.preferredTabs=[];
  // This fixture covers ordinary Product attachment recovery. Story's distinct
  // completed-review route is exercised by flow_review_project_403.js.
  f.context.reviewPath='';
  f.context.pickHealthyFlowProjectTab=async()=>null;
  f.context.isFlowUrl=url=>/^https:\/\/flow\.google\.com\//.test(url);
  f.context.chrome.tabs={create:async opts=>{created.push(opts);return {id:88,url:opts.url};}};
  f.context.waitForTabComplete=async()=>{};f.context.rememberAutomationTabs=async()=>{};
  vm.runInContext(`async function reopenTest(){${reopen}return projectTab;}`,f.context);
  assert.equal((await f.context.reopenTest()).id,88);assert.equal(created[0].url,sender.tab.url);
  f.context.pickHealthyFlowProjectTab=async()=>({id:12,url:sender.tab.url});
  assert.equal((await f.context.reopenTest()).id,12);assert.equal(created.length,1);
  f.context.pickHealthyFlowProjectTab=async()=>null;
  f.storage[terminalKey][scopeKey].page_url='https://example.com/project/project-a';
  await assert.rejects(()=>f.context.reopenTest());assert.equal(created.length,1);

  f = fixture();
  await f.context.watchForManualAttachment(request);
  await f.advance(3000);
  f.state.image = true;
  await f.advance(1000);
  assert.equal(f.generated(), 1, "The real shot-one three-second late proof resumes normal Flow once");
  await f.advance(30000);
  assert.equal(f.storage[terminalKey], undefined);

  f = fixture();
  await f.context.watchForManualAttachment(request);
  await f.advance(20000);
  await f.context.watchForManualAttachment(f.storage.smartpostAutoFlow);
  await f.advance(10000);
  assert(f.storage[terminalKey]?.[scopeKey], "Helper rearm must not reset the grace clock");

  const protections = [
    (f) => { f.state.text = "Considering Video Generation"; },
    (f) => { f.state.text = "scheduled and waiting in the queue"; },
    (f) => { f.state.text = "temporarily unavailable, try again later"; },
    (f) => { f.state.text = "กำลังอัปโหลด"; f.storage.smartpostFlowAttachmentAttempts[attemptKey].status = "uploaded_waiting_media"; },
    (f) => { f.state.labels = ["Stop"]; },
    (f) => { f.state.snapshot.progressValues = [40]; f.state.snapshot.activeProgress = true; },
    (f) => { f.state.snapshot.videoCount = 1; },
    (f) => { f.state.snapshot.resultCardCount = 1; },
    (f) => { f.state.labels = ["Download video"]; },
    (f) => { f.state.confirmation = "credit"; },
    (f) => { f.state.confirmation = "legal_rights"; },
    (f) => { f.state.login = true; },
    (f) => { f.state.credit = true; },
    (f) => { f.context.lastClickResult = { ok: false }; },
    (f) => { f.storage[receiptKey] = { x: { jobId: "JOB-A", shotIndex: 2, runId: "OLD" } }; },
    (f) => { f.storage.smartpostFlowMonitor = { jobId: "JOB-A", shotIndex: 2 }; },
    (f) => { f.storage.smartpostPendingFlowDownload = { jobId: "JOB-A", shotIndex: 2 }; },
    (f) => { f.storage.smartpostFlowDownloadReceipt = { jobId: "JOB-A", shotIndex: 2 }; },
    (f) => { f.storage.smartpostFlowAttachmentAttempts[attemptKey].resumeAttachCount = 1; },
    (f) => { f.storage.smartpostFlowAttachmentAttempts[attemptKey].status = "started"; },
    (f) => { f.storage.smartpostFlowAttachmentAttempts[attemptKey].status = "uploaded_ready"; },
    (f) => { f.storage["smartpostFlowTab:JOB-A:2"] = 99; },
    (f) => { f.storage["smartpostFlowRun:JOB-A:2"] = "RUN-B"; }
  ];
  for (const protect of protections) {
    f = fixture(); protect(f);
    await f.context.watchForManualAttachment(request);
    await f.advance(31000);
    assert.equal(f.storage[terminalKey], undefined, `Protected evidence became terminal: ${protect}`);
  }
  for (const status of ["upload_failed", "uploaded_waiting_media"]) {
    f = fixture();
    f.storage.smartpostFlowAttachmentAttempts[attemptKey].status = status;
    await f.context.watchForManualAttachment(request);
    await f.advance(30000);
    assert(f.storage[terminalKey]?.[scopeKey], `Finished failed transaction with no uploading or generation evidence must complete: ${status}`);
  }
  f = fixture();
  f.state.snapshot.progressValues = [100];
  f.state.text = "100%";
  await f.context.watchForManualAttachment(request);
  await f.advance(30000);
  assert(f.storage[terminalKey]?.[scopeKey], "An image upload's retained 100% is not a submitted video");

  f = fixture();
  await f.context.watchForManualAttachment(request);
  f.state.text = "waiting in the queue";
  await f.advance(1000);
  f.state.text = "";
  await f.advance(30000);
  assert.equal(f.storage[terminalKey], undefined, "Previously observed work must stay protected after DOM text disappears");

  f = fixture();
  await f.context.watchForManualAttachment(request);
  f.storage.smartpostAutoFlow.attachmentGraceStartedAt = 60000;
  const message = { job_id: "JOB-A", shot_index: 2, run_id: "RUN-A", page_url: sender.tab.url, evidence: f.context.attachmentWaitSnapshot() };
  f.context.flowGenerateInFlight.add(scopeKey);
  assert.equal((await f.context.latchFlowAttachmentFailure(message, sender)).reason, "submission_in_flight");
  f.context.flowGenerateInFlight.delete(scopeKey);
  f.storage.smartpostFlowAttachmentAttempts[attemptKey].startedAt = 50000;
  const claim = f.context.latchFlowAttachmentFailure(message, sender);
  const racing = await f.context.testGenerate({ type: "CLICK_FLOW_GENERATE", job_id: "JOB-A", shot_index: 2, run_id: "RUN-A" }, sender);
  assert.equal(racing.attachmentTerminalBlocked, true, "Claim race must not manufacture a submission receipt or monitor");
  assert.equal((await claim).ok, true);
  console.log(JSON.stringify({ ok: true, protectedCases: protections.length, graceMs: 30000, lateProofMs: 3000, terminalGenerateRace: "passed" }));
}

tests().catch((error) => { console.error(error); process.exitCode = 1; });
