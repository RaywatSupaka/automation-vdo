const fs = require("fs");
const vm = require("vm");

const DEFAULT_BRIDGE = "http://127.0.0.1:8765";
const BRIDGE = process.env.SMARTPOST_TEST_BRIDGE || DEFAULT_BRIDGE;
const CLIENT_ID = "smartpost-node-e2e";
const createdTabs = [];
const removedTabs = [];
const sentMessages = [];
const storage = {};
let nextTabId = 20;
let messageListener = null;
const nativeFetch = fetch;
const manifest = JSON.parse(fs.readFileSync("browser_extension/manifest.json", "utf8"));

const event = () => ({ addListener() {}, removeListener() {} });
const context = {
  console,
  async fetch(url, options) {
    if (String(url).includes('/api/membership/extension/authorize')) {
      return new Response(JSON.stringify({ok:true,desktop:{allowed:true},extension:{allowed:true,source:'desktop',contract_version:1}}));
    }
    if (String(url).includes("/api/stories/STORY-GEMINI-TEST/chatgpt-package")) {
      return new Response(JSON.stringify({
        ok: true,
        package: {
          mode: "story",
          job: { id: "STORY-GEMINI-TEST", image_ai_provider: "gemini", scene_count: 6 },
          prompt: "Gemini extension routing test",
          request: { image_count: 6 }
        }
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return nativeFetch(url, options);
  },
  URL,
  AbortController,
  AbortSignal,
  crypto: require('node:crypto').webcrypto,
  Response,
  Blob,
  encodeURIComponent,
  setTimeout,
  clearTimeout,
  setInterval() { return 1; },
  clearInterval() {},
  chrome: {
    runtime: {
      id: CLIENT_ID,
      getManifest: () => ({ version: manifest.version }),
      onMessage: { addListener(listener) { messageListener = listener; } },
      onInstalled: event(),
      onStartup: event(),
      reload() {}
    },
    windows: { async update() { return {}; } },
    tabs: {
      async query(options = {}) {
        const all = [
          { id: 1, status: "complete", url: "https://affiliate.shopee.co.th/offer/product_offer" },
          { id: 9, status: "complete", url: "https://chatgpt.com/" },
          ...createdTabs
        ].filter((tab) => !removedTabs.includes(tab.id));
        if (!options.url) return all.map((tab) => ({ ...tab }));
        const patterns = Array.isArray(options.url) ? options.url : [options.url];
        const matches = (url, pattern) => {
          const escaped = String(pattern)
            .replace(/[.+?^${}()|[\]\\]/g, "\\$&")
            .replace(/\*/g, ".*");
          return new RegExp(`^${escaped}$`, "i").test(String(url || ""));
        };
        return all.filter((tab) => patterns.some((pattern) => matches(tab.url, pattern))).map((tab) => ({ ...tab }));
      },
      async get(id) {
        const created = createdTabs.find((tab) => tab.id === id);
        if (created) return { ...created };
        if (id === 9) return { id, status: "complete", url: "https://chatgpt.com/" };
        if (id === 1) return { id, status: "complete", url: "https://affiliate.shopee.co.th/offer/product_offer" };
        throw new Error(`No tab with id ${id}`);
      },
      async update(id, options) {
        const created = createdTabs.find((tab) => tab.id === id);
        if (created) Object.assign(created, options, { status: "complete" });
        return { id, status: "complete", ...(created || {}), ...options };
      },
      async create(options) {
        const tab = { id: nextTabId++, status: "complete", ...options };
        createdTabs.push(tab);
        return { ...tab };
      },
      async reload(id) {
        const created = createdTabs.find((tab) => tab.id === id);
        if (created) created.status = "complete";
      },
      async remove(ids) {
        removedTabs.push(...(Array.isArray(ids) ? ids : [ids]));
      },
      async sendMessage(id, message) {
        sentMessages.push({ id, message });
        if (message?.type === "CANCEL_CHATGPT_JOB") return { ok: true, cancelled: true };
        return { ok: true };
      },
      onUpdated: event()
    },
    storage: {
      local: {
        async get(key) {
          if (typeof key === "string") return { [key]: storage[key] };
          if (Array.isArray(key)) return Object.fromEntries(key.map((item) => [item, storage[item]]));
          return { ...storage };
        },
        async set(values) { Object.assign(storage, values); },
        async remove(key) {
          for (const item of (Array.isArray(key) ? key : [key])) delete storage[item];
        }
      }
    },
    downloads: {
      async download() { return 1; },
      async search() { return [{ id: 1, state: "complete", filename: "C:\\Temp\\flow-reference.png" }]; },
      onDeterminingFilename: event()
    },
    scripting: {
      async executeScript(details) {
        if (details?.files?.includes("flow.js")) {
          const tab = createdTabs.find((item) => item.id === details?.target?.tabId);
          if (tab && !/\/project\//i.test(tab.url || "")) {
            tab.url = `https://flow.google.com/project/mock-project-${tab.id}`;
          }
          return [{ result: true }];
        }
        if (typeof details?.func === "function") {
          const source = String(details.func);
          if (source.includes("bodyChildren") && source.includes("interactiveCount")) {
            return [{ result: { bodyChildren: 4, interactiveCount: 5, editorCount: 1, mediaCount: 0, videoCount: 0, resultControlCount: 0, textLength: 100 } }];
          }
          return [{ result: true }];
        }
        return [{ result: true }];
      }
    },
    debugger: {
      async attach() {},
      async detach() {},
      async sendCommand() { return {}; },
      onEvent: event()
    },
    alarms: { create() {}, onAlarm: event() }
  }
};
context.globalThis = context;

async function post(path, body) {
  const response = await fetch(`${BRIDGE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || path);
  return payload;
}

async function main() {
  const desktopState = await (await fetch(`${BRIDGE}/api/desktop/state`)).json();
  const flowTestJobId = desktopState?.products?.[0]?.id || desktopState?.products?.[0]?.job_id;
  if (!flowTestJobId) throw new Error("ไม่พบ Product Job สำหรับทดสอบ Extension bridge");

  const backgroundPath = process.env.SMARTFLOW_EXTENSION_BACKGROUND || "browser_extension/background.js";
  let source = fs.readFileSync(backgroundPath, "utf8");
  if (BRIDGE !== DEFAULT_BRIDGE) {
    source = source.replace(
      /const BRIDGE\s*=\s*["']http:\/\/127\.0\.0\.1:8765["'];/,
      `const BRIDGE = "${BRIDGE}";`
    );
  }
  vm.runInNewContext(source, context, { filename: "background.js" });
  if (!messageListener) throw new Error("background message listener was not registered");
  const recoveryMessage = {type:'PRODUCT_IMAGE_RECOVERY', operation:'state', job_id:flowTestJobId, provider:'chatgpt', run_id:'RUN-IMAGE-TEST'};
  const recoverySender = {tab:{id:9,url:'https://chatgpt.com/c/test'}};
  const recoveryDispatch = (message, sender) => new Promise(resolve => messageListener(message, sender, resolve));
  const noOwner = await recoveryDispatch(recoveryMessage, recoverySender);
  if (noOwner.ok) throw new Error('image recovery accepted unknown ownership');
  storage[`smartpostAIWebTab:chatgpt:${flowTestJobId}`] = 9;
  storage[`smartpostAIWebRun:${flowTestJobId}`] = 'RUN-IMAGE-TEST';
  const imageState = await recoveryDispatch(recoveryMessage, recoverySender);
  if (!imageState.ok || !imageState.state) throw new Error(`image recovery bridge failed: ${imageState.error}`);
  for (const [message, sender] of [
    [{...recoveryMessage, run_id:'RUN-OLD'}, recoverySender],
    [recoveryMessage, {tab:{id:90,url:recoverySender.tab.url}}],
    [recoveryMessage, {tab:{id:9,url:'https://gemini.google.com/app'}}],
    [recoveryMessage, {tab:{id:9,url:'https://example.com/'}}],
  ]) {
    if ((await recoveryDispatch(message, sender)).ok) throw new Error('stale/foreign image recovery accepted');
  }
  if (!context.isGoogleVerificationUrl("https://www.google.com/sorry/index?continue=https://gemini.google.com/app")) throw new Error("Google verification URL was not detected");
  if (!context.isWebLoginUrl("https://accounts.google.com/v3/signin/identifier", "gemini")) throw new Error("Gemini login redirect was not detected");
  if (!context.isWebLoginUrl("https://accounts.google.com/v3/signin/identifier", "flow")) throw new Error("Flow login redirect was not detected");
  if (!context.isWebLoginUrl("https://chatgpt.com/auth/login", "chatgpt")) throw new Error("ChatGPT login URL was not detected");
  if (!context.isFlowUrl("https://flow.google.com/project/example")) throw new Error("flow.google.com was not detected");
  if (!context.isFlowUrl("https://labs.google/flow/project/example")) throw new Error("labs.google/flow was not detected");

  const cancel = await context.cancelChatGPTJob("STORY-CANCEL-TEST");
  if (!cancel.stopped || !sentMessages.some((item) => item.message?.type === "CANCEL_CHATGPT_JOB")) throw new Error("ChatGPT cancellation was not delivered");

  let mismatchRejected = false;
  try { await context.startAIWebJob("STORY-GEMINI-TEST", false, "chatgpt"); }
  catch (error) { mismatchRejected = String(error?.message || error).includes("ไม่ตรงกับ Provider"); }
  if (!mismatchRejected) throw new Error("provider mismatch was not rejected before opening a tab");
  await context.startAIWebJob("STORY-GEMINI-TEST", false, "gemini");
  if (!createdTabs.some((tab) => String(tab.url).startsWith("https://gemini.google.com/"))) throw new Error("Gemini tab routing failed");
  const geminiStart = sentMessages.find((item) => item.message?.type === "START_CHATGPT_JOB" && item.message?.package?.job?.id === "STORY-GEMINI-TEST");
  if (geminiStart?.message?.package?.image_ai_provider !== "gemini") throw new Error("Gemini provider was not delivered to the content script");
  await new Promise((resolve) => setTimeout(resolve, 100));

  const heartbeat = await (await fetch(`${BRIDGE}/api/extension/status`)).json();
  const harnessClient = (heartbeat.clients || []).find((item) => item.client_id === CLIENT_ID);
  if (!heartbeat.connected || !harnessClient) throw new Error("heartbeat not received");

  const verificationError = new Error("กรุณาติ๊ก ฉันไม่ใช่โปรแกรมอัตโนมัติ");
  verificationError.code = "USER_ACTION_REQUIRED";
  verificationError.actionKind = "login_required";
  verificationError.service = "gemini";
  verificationError.tabId = createdTabs.at(-1)?.id;
  await context.reportAICommandFailure(
    { action: "open_story_chatgpt", job_id: "STORY-GEMINI-TEST", provider: "gemini" },
    verificationError
  );
  const verificationStatus = await (await fetch(`${BRIDGE}/api/extension/status`)).json();
  const verificationClient = (verificationStatus.clients || []).find((item) => item.client_id === CLIENT_ID);
  if (verificationClient?.ai_step !== "user_action_required" || verificationClient?.ai_provider !== "gemini"
      || verificationClient?.ai_action_kind !== "login_required" || verificationClient?.ai_service !== "gemini") {
    throw new Error("human verification status was not reported to the program");
  }
  if (!await context.resolvePendingWebAction()) throw new Error("login readiness did not resolve the pending action");
  const resolvedStatus = await (await fetch(`${BRIDGE}/api/extension/status`)).json();
  const resolvedClient = (resolvedStatus.clients || []).find((item) => item.client_id === CLIENT_ID);
  if (resolvedClient?.ai_step !== "user_action_resolved") throw new Error("resolved login status was not reported to the program");

  const queued = await post("/api/extension/queue", { action: "open_flow", job_id: flowTestJobId });
  await context.extensionTick();
  const command = await (await fetch(`${BRIDGE}/api/extension/command/${queued.command.id}`)).json();
  if (command.command.status !== "completed") throw new Error(`command status=${command.command.status}`);
  const openedFlowTab = createdTabs.find((tab) => context.isFlowUrl(tab.url));
  if (!openedFlowTab) throw new Error("Flow tab was not opened");
  if (storage.smartpostActiveJobId !== flowTestJobId) throw new Error("active Job was not stored");

  const missingCheckpoint = await post("/api/extension/queue", { action: "inspect_flow", job_id: flowTestJobId, shot_index: 2 });
  await context.extensionTick();
  const missingStatus = await (await fetch(`${BRIDGE}/api/extension/command/${missingCheckpoint.command.id}`)).json();
  if (missingStatus.command.status !== "completed") throw new Error(`missing checkpoint status=${missingStatus.command.status}`);
  const bridgeStatus = await (await fetch(`${BRIDGE}/api/extension/status`)).json();
  const inspectedClient = (bridgeStatus.clients || []).find((item) => item.client_id === CLIENT_ID);
  if (inspectedClient?.flow_step !== "checkpoint_missing" || Number(inspectedClient?.flow_shot_index) !== 2) {
    throw new Error("a previous Flow result was incorrectly reused as shot 2");
  }

  const cleanup = await post("/api/extension/queue", { action: "close_automation_browser", job_id: flowTestJobId });
  await context.extensionTick();
  const cleanupStatus = await (await fetch(`${BRIDGE}/api/extension/command/${cleanup.command.id}`)).json();
  if (cleanupStatus.command.status !== "completed") throw new Error(`cleanup status=${cleanupStatus.command.status}`);
  if (!removedTabs.includes(openedFlowTab.id)) throw new Error("automation Chrome tab was not closed");

  await post("/api/extension/disconnect", { client_id: CLIENT_ID });
  console.log(JSON.stringify({
    ok: true,
    version: manifest.version,
    heartbeat: harnessClient,
    command: {
      id: command.command.id,
      action: command.command.action,
      job_id: command.command.job_id,
      shot_index: command.command.shot_index,
      status: command.command.status,
      min_version: command.command.min_version,
      run_id: command.command.run_id
    },
    openedFlow: openedFlowTab.url,
    activeJobId: storage.smartpostActiveJobId
  }, null, 2));
}

main().catch(async (error) => {
  try { await post("/api/extension/disconnect", { client_id: CLIENT_ID }); } catch {}
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
