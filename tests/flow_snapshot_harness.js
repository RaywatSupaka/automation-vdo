const fs = require("fs");
const vm = require("vm");

function extractFunction(source, name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`${name} not found`);
  // Skip object/default values inside the parameter list. The first `{` after
  // the function marker is not necessarily the function body (`state = {}`).
  const signatureClose = source.indexOf(") {", start);
  if (signatureClose < 0) throw new Error(`${name} signature closing parenthesis not found`);
  const brace = source.indexOf("{", signatureClose);
  let depth = 0;
  let mode = "code";
  let escaped = false;
  let regexClass = false;
  const templateExpressionDepths = [];
  const regexCanStartHere = (index) => {
    const prefix = source.slice(brace, index).trimEnd();
    const previous = prefix.at(-1) || "";
    if (!previous || /[([{:;,=!?&|+\-*%^~<>]/.test(previous)) return true;
    return /(?:return|case|throw|else|do|typeof|instanceof|in|of|yield|await)$/.test(prefix);
  };
  for (let index = brace; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1] || "";
    if (mode === "line-comment") {
      if (char === "\n" || char === "\r") mode = "code";
      continue;
    }
    if (mode === "block-comment") {
      if (char === "*" && next === "/") {
        mode = "code";
        index += 1;
      }
      continue;
    }
    if (mode === "single" || mode === "double") {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if ((mode === "single" && char === "'") || (mode === "double" && char === '"')) mode = "code";
      continue;
    }
    if (mode === "regex") {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === "[") regexClass = true;
      else if (char === "]") regexClass = false;
      else if (char === "/" && !regexClass) mode = "code";
      continue;
    }
    if (mode === "template") {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char.charCodeAt(0) === 96) mode = "code";
      else if (char === "$" && next === "{") {
        templateExpressionDepths.push(depth);
        depth += 1;
        mode = "code";
        index += 1;
      }
      continue;
    }
    if (char === "/" && next === "/") {
      mode = "line-comment";
      index += 1;
      continue;
    }
    if (char === "/" && next === "*") {
      mode = "block-comment";
      index += 1;
      continue;
    }
    if (char === "'") {
      mode = "single";
      continue;
    }
    if (char === '"') {
      mode = "double";
      continue;
    }
    if (char.charCodeAt(0) === 96) {
      mode = "template";
      continue;
    }
    if (char === "/" && regexCanStartHere(index)) {
      mode = "regex";
      regexClass = false;
      continue;
    }
    if (char === "{") depth += 1;
    else if (char === "}") {
      depth -= 1;
      if (templateExpressionDepths.at(-1) === depth) {
        templateExpressionDepths.pop();
        mode = "template";
        continue;
      }
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`${name} closing brace not found`);
}

class FakeElement {
  constructor(tagName, options = {}) {
    this.tagName = tagName.toUpperCase();
    this.textContent = options.text || "";
    this.innerText = options.text || "";
    this.currentSrc = options.currentSrc || "";
    this.src = options.src || "";
    this.poster = options.poster || "";
    this.href = options.href || "";
    this.attributes = { ...(options.attributes || {}) };
    this.backgroundImage = options.backgroundImage || "none";
    this.children = [];
    this.parentElement = null;
    this.card = options.card || null;
    this.rect = options.rect || { x: 0, y: 0, left: 0, top: 0, right: 240, bottom: 180, width: 240, height: 180 };
  }
  append(child) {
    child.parentElement = this;
    if (!child.card && this.card) child.card = this.card;
    this.children.push(child);
    return child;
  }
  getAttribute(name) { return this.attributes[name] || ""; }
  getBoundingClientRect() { return this.rect; }
  closest(selector) {
    if (selector.includes("#smartpost-flow-helper-host")) return null;
    if (selector === ".error-tile-content") {
      let current = this;
      while (current) {
        const classes = String(current.getAttribute("class") || "").split(/\s+/);
        if (classes.includes("error-tile-content")) return current;
        current = current.parentElement;
      }
      return null;
    }
    if (this.card && /data-media-id|data-testid|article|listitem|button/.test(selector)) return this.card;
    return null;
  }
  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }
  querySelectorAll(selector) {
    const all = this.descendants();
    if (selector === ".error-message-text") {
      return all.filter((item) => item.getAttribute("class").split(/\s+/).includes("error-message-text"));
    }
    if (selector.includes("button") || selector.includes('[role="button"]')) {
      return all.filter((item) => item.tagName === "BUTTON" || item.getAttribute("role") === "button");
    }
    if (selector.includes("video") || selector.includes("source") || selector.includes("img") || selector.includes("a[href]")) {
      return all.filter((item) => {
        if (selector.includes("video") && item.tagName === "VIDEO") return true;
        if (selector.includes("source") && item.tagName === "SOURCE") return true;
        if (selector.includes("img") && item.tagName === "IMG") return true;
        if (selector.includes("a[href]") && item.tagName === "A" && item.href) return true;
        return false;
      });
    }
    if (selector.includes("div") || selector.includes("span")) {
      return all.filter((item) => item.tagName === "DIV" || item.tagName === "SPAN");
    }
    return [];
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function card(id, imageUrl, markerCount = 2) {
  const root = new FakeElement("article", { attributes: { "data-media-id": id }, text: `video result ${id}` });
  root.card = root;
  root.append(new FakeElement("img", { src: imageUrl, currentSrc: imageUrl, card: root }));
  const markers = [];
  for (let index = 0; index < markerCount; index += 1) {
    const marker = new FakeElement(index ? "span" : "i", { text: "play_circle", card: root });
    root.append(marker);
    markers.push(marker);
  }
  return { root, markers };
}

function failureCard(text, retryLabel = "ลองอีกครั้ง", reason = "") {
  const root = new FakeElement("div", {
    text,
    attributes: { class: "error-tile-content" }
  });
  if (reason) root.append(new FakeElement("span", { text: reason, attributes: { class: "error-message-text" } }));
  root.append(new FakeElement("button", {
    text: "refresh",
    attributes: { "aria-label": retryLabel, title: retryLabel }
  }));
  return root;
}

const source = fs.readFileSync("browser_extension/flow.js", "utf8");
const functionSource = extractFunction(source, "generationSnapshot");
const policyDecisionSource = extractFunction(source, "evaluateFlowPolicyFailure") + '\n' + extractFunction(source, "flowRepairRouting") + '\n' + extractFunction(source, "mobileResultReady") + '\n' + extractFunction(source, "canRepairRecoveredTerminal");
const first = card("media-a", "https://labs.google/media-a.jpg", 3);
const second = card("media-b", "https://labs.google/media-b.jpg", 2);
const video = new FakeElement("video", { currentSrc: "blob:https://labs.google/video-a" });
let markers = [...first.markers];
let videos = [video];
let bodyText = "old status 11%\ncurrent status 42%";
let failureCards = [];
let mobileTiles = [];

const document = {
  body: { get innerText() { return bodyText; } },
  getElementById() { return null; },
  querySelectorAll(selector) {
    if (selector === 'flow-video-tile') return mobileTiles;
    if (selector === "video") return videos;
    if (selector === ".error-tile-content,.error-message") return failureCards;
    if (selector.includes("i,span,button")) return markers;
    return [];
  }
};
const context = {
  document,
  getComputedStyle(element) { return { backgroundImage: element.backgroundImage || "none" }; },
  visible(element) {
    const rect = element?.getBoundingClientRect();
    return Boolean(rect && rect.width > 20 && rect.height > 12);
  },
  console
};
vm.createContext(context);
vm.runInContext(`${functionSource}; ${policyDecisionSource}; ${extractFunction(source, "currentStoryFailureCard")}; ${extractFunction(source, "observeStoryPolicyCard")}; ${extractFunction(source, "ownedStoryPolicyTerminal")}; this.snapshot = generationSnapshot; this.policyDecision = evaluateFlowPolicyFailure; this.currentCard = currentStoryFailureCard; this.observePolicy = observeStoryPolicyCard; this.ownedTerminal = ownedStoryPolicyTerminal;`, context);

const one = context.snapshot();
{
  const savedVideos=videos,savedMarkers=markers;
  const thumb={src:'https://flow.google.com/asb/completed-video'};
  mobileTiles=[{getBoundingClientRect:()=>({width:140,height:250}),getAttribute:()=>'',
    querySelector:s=>s==='img.thumbnail'?thumb:s==='.mobile-play-badge,flow-video-hotbar'?{}:null,
    querySelectorAll:s=>s==='video,source,img,a[href]'?[thumb]:[]}];
  videos=[];markers=[];
  const mobile=context.snapshot();
  if(mobile.videoCount!==0||mobile.resultCardCount!==1||mobile.completedTileSources.length!==1)throw Error('mobile thumbnail video not detected');
  const ready=vm.runInContext('mobileResultReady',context),state={owned:true,age:45000};
  if(!ready(mobile,{videoCount:0,resultCardCount:0,videoSources:[]},state))throw Error('legacy empty baseline recovery failed');
  for(const stateChange of [{owned:false},{age:1000},{active:true},{busy:true},{confirmation:true}])
    if(ready(mobile,{completedTileSources:[]},{...state,...stateChange}))throw Error('unsafe mobile acceptance');
  if(ready(mobile,{completedTileSources:mobile.completedTileSources},state))throw Error('old result accepted');
  if(ready(mobile,{resultCardCount:1},state))throw Error('ambiguous legacy baseline accepted');
  if(ready({...mobile,completedTileSources:['one','two']},{completedTileSources:[]},state))throw Error('multiple results accepted');
  mobileTiles=[];videos=savedVideos;markers=savedMarkers;
}
if (one.resultCardCount !== 1) throw new Error(`nested play markers counted as ${one.resultCardCount}, expected 1`);
if (one.videoCount !== 1 || one.videoSources.length !== 1) throw new Error("video source detection failed");
if (one.latestProgressValue !== 42 || !one.activeProgress) throw new Error("latest active progress detection failed");

markers = [...first.markers, ...second.markers];
const two = context.snapshot();
if (two.resultCardCount !== 2) throw new Error(`two cards counted as ${two.resultCardCount}`);
if (new Set(two.resultFingerprints).size !== 2) throw new Error("result fingerprints are not unique");
if (two.resultFingerprints[0] === one.resultFingerprints[0] && two.resultFingerprints.length < 2) throw new Error("new result was not observable");

bodyText = "old status 11%\nfinished 100%";
const finished = context.snapshot();
if (finished.latestProgressValue !== 100 || finished.activeProgress) throw new Error("completed progress was treated as active");

const policyText = "ล้มเหลว การสร้างนี้อาจละเมิดนโยบายเกี่ยวกับบุคคลที่มีชื่อเสียง ระบบไม่ได้เรียกเก็บเงินจากคุณ";
failureCards = [failureCard(policyText)];
bodyText = `${policyText}\nI've started generating it. It's currently in the queue.`;
const policyBaseline = context.snapshot();
const baselineFingerprints = new Set(policyBaseline.failureCardFingerprints);
const unchangedPolicy = context.snapshot();
const unchangedLatest = unchangedPolicy.visibleFailureCards.at(-1);
const unchangedIsCurrent = Boolean(unchangedLatest)
  && (!baselineFingerprints.has(unchangedLatest.fingerprint)
    || unchangedPolicy.visibleFailureCardCount > policyBaseline.visibleFailureCardCount);
if (unchangedIsCurrent) throw new Error("old policy card plus a new queue acknowledgement was treated as a current failure");
if (!unchangedLatest?.hasRetry || !unchangedLatest?.hasNoCharge) {
  throw new Error("same-card Retry/no-charge evidence was not captured");
}

// Flow can append a second visually identical policy card. Its fingerprint is
// intentionally the same, so the visible-card count must still prove that it
// appeared after the pre-submit baseline.
failureCards = [failureCards[0], failureCard(policyText)];
bodyText = `${policyText}\n${policyText}\nI've started generating it. It's currently in the queue.`;
const currentPolicy = context.snapshot();
const currentLatest = currentPolicy.visibleFailureCards.at(-1);
const currentIsNew = Boolean(currentLatest)
  && (!baselineFingerprints.has(currentLatest.fingerprint)
    || currentPolicy.visibleFailureCardCount > policyBaseline.visibleFailureCardCount);
if (!currentIsNew) throw new Error("new same-text policy card was not distinguishable from its baseline");

failureCards = [failureCard("interface")];
bodyText = "interface";
const interfaceOnly = context.snapshot();
if (interfaceOnly.visibleFailureCardCount !== 0) throw new Error("interface was misread as a bounded face/facial policy marker");

const queuedPolicyDecision = context.policyDecision({
  currentVisiblePolicyFailure: true,
  isQueued: true,
  isBusy: false,
  hasStrongActiveGeneration: false,
  hasDownload: false,
  confirmation: "",
  policyFailureGraceElapsed: true,
  generationFailureChecks: 3
});
if (queuedPolicyDecision.terminal || queuedPolicyDecision.step !== "generation_in_progress") {
  throw new Error("new policy card followed by newer queue evidence became terminal");
}
const busyAfterOldFailureDecision = context.policyDecision({
  currentVisiblePolicyFailure: false,
  isQueued: false,
  isBusy: true,
  hasStrongActiveGeneration: false,
  hasDownload: false,
  confirmation: "",
  policyFailureGraceElapsed: true,
  generationFailureChecks: 3
});
if (busyAfterOldFailureDecision.terminal || busyAfterOldFailureDecision.step !== "generation_in_progress") {
  throw new Error("new busy evidence after an old no-charge card became terminal");
}
const terminalPolicyDecision = context.policyDecision({
  currentVisiblePolicyFailure: true,
  isQueued: false,
  isBusy: false,
  hasStrongActiveGeneration: false,
  hasDownload: false,
  confirmation: "",
  policyFailureGraceElapsed: true,
  generationFailureChecks: 3
});
if (!terminalPolicyDecision.terminal || terminalPolicyDecision.step !== "generation_failed") {
  throw new Error("current policy failure newer than queue/busy did not become terminal after grace");
}

// Observed Story case: a new failed gallery card appears above unchanged queue
// prose. Use actual-source classification/observation, never DOM text order.
const famousText = "พรอมต์นี้อาจละเมิดนโยบายเกี่ยวกับการสร้างบุคคลที่มีชื่อเสียง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้";
failureCards = [failureCard(famousText)];
const famousSnapshot = context.snapshot();
const emptyBaseline = { failureCardFingerprints: [], failureCardKeys: [] };
const currentCard = context.currentCard(famousSnapshot, emptyBaseline);
if (!currentCard?.hasNoCharge || !currentCard?.hasRetry) throw new Error("actual Thai famous-person card missing proof");
if (context.currentCard(famousSnapshot, famousSnapshot)) throw new Error("old card considered current");
if (context.currentCard(famousSnapshot, null)) throw new Error("missing baseline authorized fallback");
const sameTextDifferentScene = { ...famousSnapshot, visibleFailureCards: [{ ...currentCard, cardKey: "scene2" }], failureCardKeys: ["scene2"] };
if (!context.currentCard(sameTextDifferentScene, { ...famousSnapshot, failureCardKeys: ["scene1"] })) throw new Error("new scene with same failure text lost");
if (context.currentCard(sameTextDifferentScene, { ...famousSnapshot, failureCardKeys: ["scene2"] })) throw new Error("recycled old scene authorized fallback");
const oldLast = { ...famousSnapshot, visibleFailureCards: [{ ...currentCard, cardKey: "new" }, { ...currentCard, cardKey: "old" }], failureCardKeys: ["new", "old"] };
if (context.currentCard(oldLast, { failureCardFingerprints: [currentCard.fingerprint], failureCardKeys: ["old"] })?.cardKey !== "new") throw new Error("last old card hid new card");

const observation = { enabled: true, currentPolicy: true, owner: "story|run|2|project", cardKey: "scene2|policy", narrative: "queue-unchanged", now: 1000 };
let observed = context.observePolicy(observation);
observed = context.observePolicy({ ...observation, now: 16000 }, observed);
if (observed.overrideNarrative) throw new Error("policy grace skipped");
observed = context.observePolicy({ ...observation, now: 31000 }, observed);
if (!observed.overrideNarrative) throw new Error("unchanged queue prose kept current terminal card stuck");
const resolved = context.policyDecision({ currentVisiblePolicyFailure: true, isQueued: !observed.overrideNarrative, policyFailureGraceElapsed: true, generationFailureChecks: observed.checks });
if (!resolved.terminal) throw new Error("confirmed current card did not release desktop");
for (const guard of [{ enabled: false }, { currentPolicy: false }, { strongActivity: true }, { hasResult: true }, { confirmation: "credit" }, { confirmation: "rights" }, { owner: "" }]) {
  if (context.observePolicy({ ...observation, now: 61000, ...guard }, observed)) throw new Error(`unsafe policy override ${JSON.stringify(guard)}`);
}
for (const change of [{ narrative: "new queue response" }, { owner: "another-run" }, { cardKey: "scene3" }]) {
  const changed = context.observePolicy({ ...observation, now: 61000, ...change }, observed);
  if (changed.overrideNarrative || changed.firstSeenAt !== 61000) throw new Error("new activity/owner/card inherited old grace");
}
const rehydrated = context.observePolicy({ ...observation, now: 32000 }, JSON.parse(JSON.stringify(observed)));
if (!rehydrated.overrideNarrative) throw new Error("matching persisted observation lost grace on reload");
const request = { mode: "story", job_id: "STORY1", run_id: "RUN1", shot_index: 2 };
const terminalMonitor = { jobId: "STORY1", runId: "RUN1", shotIndex: 2,
  storyPolicyTerminal: { projectPath: "/project/abc", failure_code: "FLOW_POLICY_BLOCKED", policy_failure_category: "face_or_public_figure", failure_card_fingerprint: "card2", message: "terminal" } };
if (!context.ownedTerminal(JSON.parse(JSON.stringify(terminalMonitor)), request, "/project/abc")) throw new Error("durable same-terminal replay lost");
for (const invalid of [{mode:"product"}, {job_id:"STORY2"}, {run_id:"RUN2"}, {run_id:""}, {shot_index:3}]) {
  if (context.ownedTerminal(terminalMonitor, {...request, ...invalid}, "/project/abc")) throw new Error("terminal crossed owner boundary");
}
if (context.ownedTerminal(terminalMonitor, request, "/project/other")) throw new Error("terminal crossed project boundary");
if (context.ownedTerminal({...terminalMonitor, storyPolicyTerminal:{...terminalMonitor.storyPolicyTerminal, failure_card_fingerprint:""}}, request, "/project/abc")) throw new Error("terminal without proof replayed");

(async () => {
  // Exercise the complete actual readGenerationState, including persistence
  // and report transport, not just a manually composed policy decision.
  let now = 1000;
  const reports = [];
  let store = {};
  Object.assign(context, {
    Date: { now: () => now }, location: { pathname: "/project/abc" },
    pkg: { ...request, shot_count: 6 }, inspectionCommandId: "inspect1",
    automationPaused: false, readOnlyInspection: true,
    generationProgressSignature: "", generationHighestProgress: 0,
    generationProgressChangedAt: 1000, generationProgressDisappearedAt: 0,
    generationStartedAt: 1000, generationFailureChecks: 0,
    generationUnknownChecks: 0, observedActiveGeneration: false,
    loginRequired: () => false, confirmationKind: () => "", creditExhausted: () => false,
    stopGenerationMonitor: () => {}, saveFlowProjectCheckpoint: async () => {},
    promptHasAttachedMedia: () => false, findPromptEditor: () => null,
    report: async (step, message, detail) => { reports.push({ step, message, detail }); },
    chrome: { storage: { local: {
      get: async () => JSON.parse(JSON.stringify(store)),
      set: async (value) => { Object.assign(store, JSON.parse(JSON.stringify(value))); },
      remove: async (key) => { delete store[key]; }
    } }, runtime: { sendMessage: async () => { throw new Error("unexpected browser action"); } } }
  });
  vm.runInContext(`async ${extractFunction(source, "readGenerationState")}; this.readState = readGenerationState;`, context);
  videos = []; markers = []; failureCards = []; bodyText = "";
  context.generationBaseline = context.snapshot();
  store.smartpostFlowMonitor = { jobId: request.job_id, runId: request.run_id, shotIndex: 2, startedAt: 1000, baseline: context.generationBaseline };
  failureCards = [failureCard(famousText)];
  bodyText = `${famousText}\nI've started generating it. It's currently in the queue due to high demand.`;
  for (const time of [1000, 16000, 31000]) { now = time; await context.readState(); }
  const finalReport = reports.at(-1);
  if (finalReport.step !== "generation_failed" || finalReport.detail.failure_code !== "FLOW_POLICY_BLOCKED") throw new Error("actual monitor remained stuck behind queue prose");
  if (!store.smartpostFlowMonitor?.storyPolicyTerminal) throw new Error("terminal not durable before reporting");
  bodyText = ""; failureCards = [];
  await context.readState();
  if (reports.at(-1).detail.failure_card_fingerprint !== finalReport.detail.failure_card_fingerprint) throw new Error("terminal replay lost identity after DOM vanished");
  // Existing policy card + genuine later queue must still wait, not fallback.
  failureCards = [failureCard(famousText)];
  bodyText = `${famousText}\nIt's currently in the queue due to high demand.`;
  context.generationBaseline = context.snapshot();
  store.smartpostFlowMonitor = { jobId: request.job_id, runId: request.run_id, shotIndex: 2, startedAt: now, baseline: context.generationBaseline };
  for (const time of [32000, 48000, 64000]) { now = time; await context.readState(); }
  if (reports.at(-1).step !== "generation_in_progress" || reports.at(-1).detail.failure_code) throw new Error("old failure interrupted actual queued work");
  for (const guard of ["product", "active-progress"]) {
    failureCards = []; bodyText = "";
    context.generationBaseline = context.snapshot();
    context.pkg = { ...request, mode: guard === "product" ? "product" : "story", shot_count: 6 };
    context.generationFailureChecks = 0;
    store.smartpostFlowMonitor = { jobId: request.job_id, runId: request.run_id, shotIndex: 2, startedAt: now, baseline: context.generationBaseline };
    failureCards = [failureCard(famousText)];
    bodyText = `${famousText}\nIt's currently in the queue due to high demand.${guard === "active-progress" ? "\n42%" : ""}`;
    for (const time of [65000, 81000, 97000]) { now = time; await context.readState(); }
    if (reports.at(-1).step !== "generation_in_progress" || reports.at(-1).detail.failure_code) throw new Error(`actual monitor broke preserved ${guard} path`);
  }
  const reputationReason = "ไม่สามารถสร้างวิดีโอที่อาจทำให้เกิดความเสี่ยงต่อชื่อเสียงหรือแสดงเหตุการณ์ปัจจุบันอย่างไม่ถูกต้อง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น";
  const reputationText = `ล้มเหลว ${reputationReason} ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้`;
  {
    const thirdPartyReason='ฉันสร้างวิดีโอที่คุณขอไม่ได้ในขณะนี้เนื่องด้วยเหตุผลด้านผลประโยชน์ของผู้ให้บริการเนื้อหาบุคคลที่สาม โปรดแก้ไขพรอมต์แล้วลองอีกครั้ง';
    failureCards=[];bodyText='';context.generationBaseline=context.snapshot();
    context.pkg={...request,mode:'story',shot_count:6};context.generationFailureChecks=0;
    store.smartpostFlowMonitor={jobId:request.job_id,runId:request.run_id,shotIndex:2,startedAt:now,baseline:context.generationBaseline};
    bodyText=`ล้มเหลว ${thirdPartyReason} ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้`;
    failureCards=[failureCard(bodyText,'ลองอีกครั้ง',thirdPartyReason)];
    for(let n=0;n<4;n++){now+=16000;await context.readState();}
    if(reports.at(-1).detail.failure_code!=='FLOW_POLICY_BLOCKED' || reports.at(-1).detail.failure_reason!==thirdPartyReason)
      throw Error('third-party refusal not recognized from owned card');
  }
  for (const mode of ["story", "product", "presenter"]) {
    failureCards = []; bodyText = "";
    context.generationBaseline = context.snapshot();
    context.pkg = { ...request, mode, shot_count: 6 };
    context.generationFailureChecks = 0;
    store.smartpostFlowMonitor = { jobId: request.job_id, runId: request.run_id, shotIndex: 2, startedAt: now, baseline: context.generationBaseline };
    failureCards = [failureCard(reputationText, "ลองอีกครั้ง", `\n${reputationReason}\u0000\n`)];
    bodyText = reputationText;
    if (context.snapshot().visibleFailureCards[0].reason !== reputationReason) throw new Error("reason not extracted from exact card node");
    for (let sample = 0; sample < 4; sample++) {
      now += 16000; await context.readState();
      if (reports.at(-1).detail.failure_code === "FLOW_POLICY_BLOCKED") break;
    }
    const failure = reports.at(-1);
    if (failure.step !== "generation_failed" || failure.detail.failure_code !== "FLOW_POLICY_BLOCKED"
        || failure.detail.policy_failure_category !== "general_policy" || failure.detail.failure_reason !== reputationReason) {
      throw new Error(`reputational policy not delivered with exact reason for ${mode}`);
    }
    if (mode === "presenter" && /Local Motion|รูปถัดไป/.test(failure.message)) throw new Error("presenter falsely promised local fallback");
    if (mode === "story") {
      failureCards = []; bodyText = "";
      await context.readState();
      if (reports.at(-1).detail.failure_reason !== reputationReason) throw new Error("terminal reload lost provider reason");
    }
  }
  // Bare prose and a card without same-card no-charge/Retry remain nonterminal.
  for (const kind of ["prose-only", "no-retry", "no-nocharge", "old-card"]) {
    context.pkg = { ...request, mode: "story", shot_count: 6 };
    failureCards = kind === "old-card" ? [failureCard(reputationText, "ลองอีกครั้ง", reputationReason)] : [];
    bodyText = "";
    context.generationBaseline = context.snapshot();
    context.generationFailureChecks = 0;
    store.smartpostFlowMonitor = { jobId: request.job_id, runId: request.run_id, shotIndex: 2, startedAt: now, baseline: context.generationBaseline };
    if (kind === "no-retry") failureCards = [failureCard(reputationText, "", reputationReason)];
    if (kind === "no-nocharge") failureCards = [failureCard(`ล้มเหลว ${reputationReason}`, "ลองอีกครั้ง", reputationReason)];
    bodyText = `${reputationText}\nIt's currently in the queue due to high demand.`;
    for (let sample = 0; sample < 4; sample++) { now += 16000; await context.readState(); }
    if (reports.at(-1).detail.failure_code === "FLOW_POLICY_BLOCKED") throw new Error(`unsafe reputational terminal ${kind}`);
  }
  videos=[];markers=[];failureCards=[];bodyText='';
  context.generationBaseline=context.snapshot();
  context.generationUnknownChecks=6;context.observedActiveGeneration=false;
  context.generationHighestProgress=0;context.generationProgressDisappearedAt=0;
  now=500000;
  store.smartpostFlowMonitor={jobId:request.job_id,runId:request.run_id,shotIndex:2,startedAt:1000,baseline:context.generationBaseline};
  await context.readState();
  if(reports.at(-1).detail.failure_code!=='FLOW_SEND_REVIEW' || !store.smartpostFlowMonitor?.sendReview
    || store.smartpostFlowMonitor.startedAt!==1000 || store.smartpostFlowMonitor.sendReviewEvidence.elapsed_ms!==499000)
    throw Error('silent Send review lost owned checkpoint');
  // 387: a live continuous repair waits for owned results, never borrows the
  // old attempt's age or treats Flow home as a failed Send (7A343B round7).
  context.pkg={...request,mode:'story',flow_repair:{enabled:true,continuous:true},flow_repair_request_id:'round7'};
  context.readOnlyInspection=false;context.inspectionCommandId='';
  context.dismissFlowChangelogAnnouncement=async()=>false;
  store.smartpostFlowMonitor={jobId:request.job_id,runId:request.run_id,shotIndex:2,
    startedAt:1000,projectPath:'/project/abc',repairRequestId:'round7',baseline:context.generationBaseline};
  now=947000;await context.readState();
  if(reports.at(-1).step!=='error' || reports.at(-1).detail.failure_code!=='FLOW_SEND_REVIEW'
      || !store.smartpostFlowMonitor?.sendReview)
    throw Error('unaccepted continuous dispatch was mislabeled as active generation');
  const count=reports.length;
  for(const pathname of ['/','/project/unrelated']){
    context.location.pathname=pathname;await context.readState();
    if(reports.length!==count)throw Error('foreign/home page reported a current result');
  }
  context.location.pathname='/project/abc';
  store[`smartflowFlowRepair:${request.job_id}:2`]={run_id:request.run_id,phase:'cancelled'};
  await context.readState();if(reports.length!==count)throw Error('cancelled repair revived old monitor');
  console.log(JSON.stringify({
  ok: true,
  nestedMarkers: first.markers.length,
  firstResultCount: one.resultCardCount,
  secondResultCount: two.resultCardCount,
  videoSources: one.videoSources,
  latestActiveProgress: one.latestProgressValue,
  finishedProgress: finished.latestProgressValue,
  stalePolicyCurrent: unchangedIsCurrent,
  newSameTextPolicyCurrent: currentIsNew,
  policyCardHasRetry: unchangedLatest.hasRetry,
  policyCardHasNoCharge: unchangedLatest.hasNoCharge,
  interfaceFailureCards: interfaceOnly.visibleFailureCardCount,
  queuedPolicyStep: queuedPolicyDecision.step,
  busyAfterOldFailureStep: busyAfterOldFailureDecision.step,
  terminalPolicyStep: terminalPolicyDecision.step
}, null, 2));
})().catch((error) => { console.error(error); process.exitCode = 1; });
