const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../browser_extension/background.js"), "utf8");
const section = (start, end) => {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Source section missing: ${start}`);
  return source.slice(first, last);
};
const flush = () => new Promise((resolve) => setImmediate(resolve));
const pendingKey = "smartpostPendingFlowDownload";
const receiptKey = "smartpostFlowDownloadReceipt";
const runKey = "smartpostFlowRun:JOB-A:1";
const filename = "SmartPost/JOB-A/flow-shot-01.mp4";
const sourceUrl = "https://flow-content.google/video/asset-a.mp4?signature=DO-NOT-PERSIST";
const request = { filename, jobId: "JOB-A", shotIndex: 1, runId: "RUN-A" };
const downloadHelpers = section("function flowDownloadSourceIdentity(", "async function inspectFlowResultDom(");

function contextFor(storage = {}) {
  const context = {
    console, URL, Date, setTimeout, clearTimeout, AbortController,
    membershipProfile: async () => 'a'.repeat(48), // Stable non-secret fixture profile.
    CLIENT_ID: "test-client", COMMAND_OUTCOMES_KEY: "smartpostCommandOutcomes",
    FLOW_SUBMISSION_RECEIPTS_KEY: "smartpostFlowSubmissionReceipts", flowGenerateInFlight: new Set(),
    FLOW_NATIVE_DOWNLOAD_START_TIMEOUT_MS: 15000, FLOW_URL: "https://flow.google.com/",
    flowProjectId: (url) => String(url || "").match(/\/project\/([^/?#]+)/)?.[1] || "",
    flowRunStorageKey: (job, shot) => `smartpostFlowRun:${job}:${shot}`,
    chrome: {
      storage: { local: {
        async get(keys) {
          if (typeof keys === "string") return { [keys]: storage[keys] };
          return Object.fromEntries(keys.map((key) => [key, storage[key]]));
        },
        async set(value) { Object.assign(storage, value); },
        async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) delete storage[key]; }
      } },
      downloads: {}, tabs: {}, scripting: {}
    }
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(section('function sceneVideoPlanMatches(', 'async function flowProgressOwnership('),context);
  vm.runInContext("let flowDownloadEventPromise = Promise.resolve();", context);
  vm.runInContext(downloadHelpers, context);
  return context;
}

async function downloadEventTests() {
  const storage = { [pendingKey]: { ...request, requestedAt: Date.now(), mode: "native", projectId: "project-a" } };
  const context = contextFor(storage);
  let listener;
  context.chrome.downloads.onDeterminingFilename = { addListener(value) { listener = value; } };
  vm.runInContext(section("chrome.downloads.onDeterminingFilename.addListener", "chrome.runtime.onInstalled.addListener"), context);
  const suggest = (item) => new Promise((resolve) => listener(item, resolve));
  const pdf = { id: 99, url: "https://example.org/invoice.pdf", mime: "application/pdf", filename: "invoice.pdf" };
  assert.equal(await suggest(pdf), undefined);
  assert.equal(storage[pendingKey].downloadId, undefined);
  assert.equal(await suggest({ ...pdf, url: "https://flow-content.google.evil.example/video/x.mp4" }), undefined);
  assert.equal(await suggest({ id: 49, url: "https://storage.googleapis.com/unrelated/video.mp4", mime: "video/mp4" }), undefined);
  const otherProject = { id: 42, url: sourceUrl, mime: "video/mp4", referrer: "https://flow.google.com/project/project-b" };
  assert.equal(await suggest(otherProject), undefined);
  const video = { id: 41, url: sourceUrl, mime: "video/mp4", referrer: "https://flow.google.com/project/project-a" };
  const suggestion = await suggest(video);
  assert.equal(suggestion.filename, filename);
  assert.equal(suggestion.conflictAction, "overwrite");
  assert.equal(storage[pendingKey].downloadId, 41);
  assert.equal(await suggest({ ...video, id: 42 }), undefined);
  assert.equal(await suggest(pdf), undefined);
  assert.equal(storage[pendingKey].downloadId, 41);
  assert.equal((await suggest(video)).filename, filename);
  storage[pendingKey] = { ...request, mode: "direct", requestedAt: Date.now(), sourceIdentity: context.flowDownloadSourceIdentity(sourceUrl) };
  assert.equal(await suggest({ ...video, url: "https://flow-content.google/video/other.mp4" }), undefined);
  assert.equal((await suggest(video)).filename, filename);
  storage[pendingKey] = { ...request, mode: "direct", requestedAt: Date.now(), sourceIdentity: "" };
  assert.equal(await suggest({ id: 45, url: "data:video/mp4;base64,YQ==", byExtensionId: "other-extension" }), undefined);
  assert.equal((await suggest({ id: 46, url: "data:video/mp4;base64,YQ==", byExtensionId: context.CLIENT_ID })).filename, filename);
  storage[pendingKey].requestedAt = Date.now() - 121000;
  assert.equal(await suggest({ id: 46 }), undefined);
  assert.equal(context.flowDownloadSourceIdentity(sourceUrl), "https://flow-content.google/video/asset-a.mp4");
  storage[pendingKey] = { ...request, requestedAt: Date.now(), mode: "native", projectId: "project-a" };
  assert.equal((await suggest({ id: 50, url: "https://storage.googleapis.com/flow/video.mp4", mime: "video/mp4", referrer: "https://flow.google.com/project/project-a" })).filename, filename);
  storage[pendingKey] = { ...request, requestedAt: Date.now(), mode: "native", projectId: "project-a" };
  assert.equal((await suggest({ id: 51, url: "blob:https://flow.google.com/video-asset", mime: "video/mp4", referrer: "https://flow.google.com/project/project-a" })).filename, filename);
}

async function receiptTests() {
  const storage = {
    [runKey]: "RUN-A",
    [receiptKey]: { ...request, downloadId: 41, completedAt: Date.now(), sourceIdentity: "https://flow-content.google/video/asset-a.mp4" }
  };
  const context = contextFor(storage);
  let tabLookups = 0, downloads = 0;
  context.flowTabForJob = async () => { tabLookups++; return null; };
  context.findUnambiguousFinishedFlowVideoTab = async () => null;
  const completed = { id: 41, state: "complete", exists: true, filename: `C:/Downloads/${filename}`, url: sourceUrl };
  context.chrome.downloads.search = async () => [completed];
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-A")).alreadyCompleted, true);
  assert.equal(tabLookups, 0, "Receipt recovery must not require an open browser tab");
  completed.exists = false;
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-A"), /Google Flow/);
  completed.exists = true;
  completed.url = "https://flow-content.google/video/wrong.mp4";
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-A"), /Google Flow/);
  completed.url = sourceUrl;
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-B"), /Google Flow/);
  context.flowTabForJob = async () => ({ id: 5, url: "https://flow.google.com/project/project-a" });
  context.locateFlowDownloadPoint = async () => ({ videoUrl: sourceUrl });
  context.chrome.downloads.download = async () => { downloads++; return 41; };
  const fresh = await context.downloadFlowResult("JOB-A", 1, "RUN-B");
  assert.equal(fresh.direct, true);
  assert.equal(downloads, 1, "Different run must download its current result");
  assert.equal(storage[receiptKey].runId, "RUN-B");
  assert.equal(storage[receiptKey].projectId, "project-a");
  assert(!JSON.stringify(storage).includes("DO-NOT-PERSIST"));
  delete storage[receiptKey];
  storage[pendingKey] = { ...request, requestedAt: Date.now(), downloadId: 41, projectId: "project-a" };
  context.flowTabForJob = async () => { throw new Error("Pending receipt should be checked first"); };
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-A")).alreadyStarted, true);
  assert.equal(storage[receiptKey].runId, "RUN-A");
  delete storage[receiptKey];
  storage[pendingKey] = { ...request, requestedAt: Date.now(), downloadId: 41, sourceIdentity: "https://flow-content.google/video/asset-a.mp4" };
  completed.url = "https://flow-content.google/video/wrong.mp4";
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-A"), /Google Flow/);
  completed.url = sourceUrl;
  completed.filename = "C:/Downloads/unrelated.mp4";
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-A"), /Google Flow/);
}

async function nativeDownloadSuccessTest() {
  const storage = { [runKey]: "RUN-A" };
  const context = contextFor(storage);
  let nativeListener, filenameListener, presses = 0;
  const item = { id: 73, url: sourceUrl, mime: "video/mp4", referrer: "https://flow.google.com/project/project-a", state: "complete", exists: true };
  context.flowTabForJob = async () => ({ id: 5, url: item.referrer });
  context.locateFlowDownloadPoint = async () => ({ x: 10, y: 20, directSceneDownload: true });
  context.chrome.downloads = {
    onCreated: { addListener(value) { nativeListener = value; }, removeListener() {} },
    onDeterminingFilename: { addListener(value) { filenameListener = value; } },
    search: async () => [item]
  };
  vm.runInContext(section("chrome.downloads.onDeterminingFilename.addListener", "chrome.runtime.onInstalled.addListener"), context);
  context.chrome.debugger = {
    attach: async () => {}, detach: async () => {},
    sendCommand: async (_target, _method, event) => {
      if (event.type !== "mouseReleased") return;
      presses++;
      const suggestion = await new Promise((resolve) => filenameListener(item, resolve));
      item.filename = `C:/Downloads/${suggestion.filename}`;
      nativeListener(item);
    }
  };
  const result = await context.downloadFlowResult("JOB-A", 1, "RUN-A");
  assert.equal(result.source, "download_scene");
  assert.equal(result.downloadId, 73);
  assert.equal(presses, 1);
  assert.equal(storage[receiptKey].sourceIdentity, "https://flow-content.google/video/asset-a.mp4");
  assert.equal(storage[receiptKey].runId, "RUN-A");
}

async function redirectAndNativeRecoveryTests() {
  const redirectUrl = "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=asset-a";
  const storage = { [runKey]: "RUN-A" };
  const context = contextFor(storage);
  let downloads = 0;
  const item = { id: 81, state: "complete", exists: true, filename: `C:/Downloads/${filename}`, url: redirectUrl, finalUrl: sourceUrl };
  context.flowTabForJob = async () => ({ id: 5, url: "https://flow.google.com/project/project-a" });
  context.locateFlowDownloadPoint = async () => ({ videoUrl: redirectUrl });
  context.chrome.downloads.download = async () => { downloads++; return item.id; };
  context.chrome.downloads.search = async () => [item];
  const redirected = await context.downloadFlowResult("JOB-A", 1, "RUN-A");
  assert.equal(redirected.direct, true);
  assert.equal(downloads, 1);
  assert.equal(context.flowDownloadMatchesItem({ ...request, mode: "direct", requestedAt: Date.now(), sourceIdentity: context.flowDownloadSourceIdentity(redirectUrl) }, item), true);
  assert.equal(context.flowDownloadMatchesItem({ ...request, mode: "direct", requestedAt: Date.now(), sourceIdentity: context.flowDownloadSourceIdentity(redirectUrl) }, { ...item, url: redirectUrl.replace("asset-a", "asset-b"), finalUrl: "https://flow-content.google/video/asset-b.mp4" }), false);
  context.flowTabForJob = async () => null;
  context.findUnambiguousFinishedFlowVideoTab = async () => null;
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-A")).alreadyCompleted, true);

  const blobUrl = "blob:https://flow.google.com/native-asset-uuid";
  Object.assign(item, { url: blobUrl, finalUrl: blobUrl, filename: "C:/Downloads/flow-native-uuid.mp4" });
  delete storage[receiptKey];
  storage[pendingKey] = { ...request, mode: "native", downloadId: item.id, requestedAt: Date.now(), sourceIdentity: context.flowDownloadSourceIdentity(blobUrl) };
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-A")).alreadyStarted, true);
  assert.equal(storage[receiptKey].absoluteFilename, item.filename);
  assert.equal(storage[receiptKey].mode, "native");
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-A")).alreadyCompleted, true);
  assert.equal(downloads, 1, "Native UUID recovery must not click or download again");
  item.filename = "C:/Downloads/replaced-unrelated.mp4";
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, "RUN-A"), /Google Flow/);

  delete storage[runKey];
  storage[receiptKey] = { ...request, runId: "", completedAt: Date.now(), downloadId: item.id, absoluteFilename: item.filename, mode: "native", sourceIdentity: context.flowDownloadSourceIdentity(blobUrl) };
  await assert.rejects(context.downloadFlowResult("JOB-A", 1, ""), /Google Flow/);
  assert.equal(context.flowDownloadRecordMatches(storage[receiptKey], { ...request, runId: "" }), false);
  context.flowTabForJob = async () => ({ id: 5, url: "https://flow.google.com/project/project-a" });
  context.locateFlowDownloadPoint = async () => ({ videoUrl: sourceUrl });
  Object.assign(item, { url: sourceUrl, finalUrl: sourceUrl, filename: `C:/Downloads/${filename}` });
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "")).direct, true);
  assert.equal(downloads, 2, "An unscoped live download remains available but cannot reuse cached results");

  delete storage[receiptKey];
  context.locateFlowDownloadPoint = async () => ({ videoUrl: blobUrl });
  context.chrome.scripting.executeScript = async () => [{ result: { dataUrl: "data:video/mp4;base64,YQ==", size: 1 } }];
  context.chrome.downloads.download = async () => { Object.assign(item, { url: "data:video/mp4;base64,YQ==", finalUrl: "", byExtensionId: context.CLIENT_ID }); return item.id; };
  assert.equal((await context.downloadFlowResult("JOB-A", 1, "RUN-B")).source, "player_blob");
}

async function stopTests() {
  const storage = {
    smartpostFlowMonitor: { jobId: "JOB-B", shotIndex: 2 },
    smartpostFlowInspectOnly: { jobId: "JOB-B", shotIndex: 2 },
    smartpostFlowSubmissionReceipts: { "JOB-B:2:RUN-B": { submittedAt: Date.now() } }
  };
  const context = contextFor(storage);
  context.queryFlowTabs = async () => [];
  vm.runInContext(source.split('\n').find(line => line.startsWith('const flowRepairKey =')), context);
  vm.runInContext(section("async function stopFlowGeneration(", "async function openFlowResultCard("), context);
  assert.equal((await context.stopFlowGeneration("JOB-A", 1)).reason, "no_registered_flow_tab");
  assert.equal(storage.smartpostFlowMonitor.jobId, "JOB-B");
  assert.equal(storage.smartpostFlowInspectOnly.jobId, "JOB-B");
  await context.stopFlowGeneration("JOB-B", 1);
  assert.equal(storage.smartpostFlowMonitor.shotIndex, 2);
  await context.stopFlowGeneration("JOB-B", 2);
  assert.equal(storage.smartpostFlowMonitor, undefined);
  assert.equal(storage.smartpostFlowInspectOnly, undefined);
  assert.equal(Object.keys(storage.smartpostFlowSubmissionReceipts).length, 0);
}

async function ackTests() {
  const storage = {};
  const command = { id: "CMD-A", action: "focus_ai_web", job_id: "JOB-A", shot_index: 0, run_id: "RUN-A", lease_token: "LEASE-1" };
  let actions = 0, acknowledgments = 0, rejectAck = true, failureReports = 0, closes = 0;
  const makeContext = () => {
    const context = contextFor(storage);
    context.BRIDGE = "mock://bridge";
    context.pollAICovers = async () => {}; // Separately exercised by ai_cover_background_harness.js.
    context.rememberCommandRun = async () => {};
    context.focusAIWebTab = async () => { actions++; };
    context.closeAutomationBrowser = async () => { closes++; };
    context.reportAICommandFailure = context.reportFlowCommandFailure = async () => { failureReports++; };
    context.reportExtensionTrace = async () => {};
    context.bridgeFetch = async (url) => {
      if (url.includes("/commands?")) return { json: async () => ({ commands: [command] }) };
      acknowledgments++;
      return { ok: !rejectAck, status: rejectAck ? 400 : 200, json: async () => ({ ok: !rejectAck, error: rejectAck ? "Lease expired" : "" }) };
    };
    vm.runInContext(section("function commandOutcomeMatches(", "async function reportAICommandFailure("), context);
    vm.runInContext(section("async function pollCommands()", "async function extensionTick()"), context);
    return context;
  };
  let context = makeContext();
  await context.pollCommands();
  assert.equal(actions, 1);
  assert.equal(failureReports, 0, "ACK failure is not an action failure");
  assert.equal(storage.smartpostCommandOutcomes[command.id].ok, true);
  await assert.rejects(context.acknowledge(command, true), (error) => error.code === "COMMAND_ACK_PENDING");
  command.lease_token = "LEASE-2";
  rejectAck = false;
  context = makeContext(); // Simulate MV3 restart; only Chrome storage survives.
  await context.pollCommands();
  assert.equal(actions, 1, "Redelivery after worker restart must only resend ACK");
  assert(acknowledgments >= 3);
  assert(!JSON.stringify(storage).includes("LEASE-"), "Do not persist lease secrets");
  command.id = "CMD-B";
  context.focusAIWebTab = async () => { actions++; throw new Error("Tab unavailable"); };
  await context.pollCommands();
  assert.equal(storage.smartpostCommandOutcomes[command.id].ok, false);
  const failedActionCount = actions;
  await makeContext().pollCommands();
  assert.equal(actions, failedActionCount, "Failed action receipts also survive redelivery");
  command.id = "CMD-CLOSE";
  command.action = "close_automation_browser";
  rejectAck = true;
  await makeContext().pollCommands();
  assert.equal(closes, 1, "Close must finish once even when ACK was rejected");
  rejectAck = false;
  await makeContext().pollCommands();
  assert.equal(closes, 1, "ACK replay must not close replacement tabs");
}

async function heartbeatTests() {
  let heartbeats = 0, polls = 0, finish;
  const blocked = new Promise((resolve) => { finish = resolve; });
  const context = contextFor();
  context.heartbeat = async () => { heartbeats++; return { updateRequired: false }; };
  context.resolvePendingWebAction = async () => {};
  // This fixture extracts only extensionTick; the collector audit itself has
  // a separate actual-source liveness harness.
  context.runStoryRefreshCollectorAudit = () => {};
  context.runConversationPageRecoveryAudit = () => {};
  context.pollCommands = async () => { polls++; await blocked; };
  vm.runInContext("let extensionTickPromise = null;\n" + section("async function extensionTick()", "function runExtensionTickOnce()"), context);
  const first = context.extensionTick();
  await flush();
  const second = context.extensionTick();
  await flush();
  assert.equal(heartbeats, 2);
  assert.equal(polls, 1, "Physical commands remain single flight");
  finish();
  await Promise.all([first, second]);
  context.heartbeat = async () => ({ updateRequired: true });
  await context.extensionTick();
  assert.equal(polls, 1);
  const heartbeatContext = contextFor();
  heartbeatContext.BRIDGE = "mock://bridge";
  heartbeatContext.VERSION = "test";
  heartbeatContext.pageType = async () => "google_flow";
  let fetchCount = 0, finishFetch;
  heartbeatContext.fetch = async () => {
    fetchCount++;
    await new Promise((resolve) => { finishFetch = resolve; });
    return { ok: true, json: async () => ({ ok: true, extension_token: "session-only" }) };
  };
  vm.runInContext("let heartbeatPromise = null; let BRIDGE_TOKEN = '';\n" + section("async function heartbeat()", "function commandOutcomeMatches("), heartbeatContext);
  const heartbeatA = heartbeatContext.heartbeat();
  const heartbeatB = heartbeatContext.heartbeat();
  await flush();
  assert.equal(fetchCount, 1);
  finishFetch();
  await Promise.all([heartbeatA, heartbeatB]);
  let timeoutMs = 0;
  heartbeatContext.setTimeout = (callback, milliseconds) => { timeoutMs = milliseconds; return setImmediate(callback); };
  heartbeatContext.clearTimeout = clearImmediate;
  heartbeatContext.fetch = async (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true }));
  await assert.rejects(heartbeatContext.heartbeat(), /aborted/);
  assert.equal(timeoutMs, 10000);
  heartbeatContext.pageType = async () => new Promise(() => {});
  await assert.rejects(heartbeatContext.heartbeat(), /page lookup timed out/);
}

(async () => {
  await downloadEventTests();
  await receiptTests();
  await nativeDownloadSuccessTest();
  await redirectAndNativeRecoveryTests();
  await stopTests();
  await ackTests();
  await heartbeatTests();
  console.log("extension_transport_lifecycle: PASS (download isolation, run receipts, stop ownership, ACK-only replay, heartbeat)");
})().catch((error) => { console.error(error); process.exitCode = 1; });
