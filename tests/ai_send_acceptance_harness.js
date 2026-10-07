const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const background = fs.readFileSync(path.join(root, "browser_extension/background.js"), "utf8");
const content = fs.readFileSync(path.join(root, "browser_extension/chatgpt.js"), "utf8");
function section(source, start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing source section: ${start}`);
  return source.slice(first, last);
}

// Execute the real Background handler, its injected capture functions, and the
// real content acceptance loop. Only browser surfaces and time are mocked.
function fixture(options = {}) {
  const prompt = "Repair this existing response as JSON; do not create a new job.";
  const state = { editor: { innerText: prompt }, label: options.label || "Send message", accepted: false, sleeps: 0, offset: 0, ownerChecks: 0, preflightReads: 0, postAttachReads: 0, postClaimReads: 0, delays: [], windowUpdates: [], tabUpdates: [],
    windowState: options.minimizedWindow ? 'minimized' : 'normal', tabActive: true, probeVerifies: 0 };
  const originalEditor = state.editor;
  const claim={key:'smartpostStoryGeneratedImage:chatgpt:JOB-TEST:6',nonce:'test-nonce',scene_index:6};
  const storage={[claim.key]:{job_id:'JOB-TEST',run_id:'run-test',send_nonce:'test-nonce',send_phase:'dispatching',
    result_proof:{prompt,conversation_url:'https://chatgpt.com/c/existing'}}};
  if(options.claimMismatch)storage[claim.key].send_nonce='other';
  if(options.claimAlreadyPressed)storage[claim.key+':dispatch']=claim.nonce;
  const listeners = new Map(), commands = [], reports = [], responses = [];
  let sends = 0, cancelled = false;
  let clock = 1000;
  const rect = { left: 20, top: 20, width: 40, height: 40, bottom: 60, right: 60 };
  function queryButtons(selector) {
    return selector === 'button' || selector === 'button[type="submit"]'
      || selector === `button[aria-label="${state.label}"]`
      ? [state.button, ...(options.ambiguousUntilPreflightReads && state.preflightReads < options.ambiguousUntilPreflightReads
        ? [state.extraButton] : [])] : [];
  }
  const composerForm = { isConnected: true, querySelectorAll: queryButtons };
  originalEditor.isConnected = true;
  originalEditor.closest = selector => selector === 'form' ? composerForm : null;
  originalEditor.getBoundingClientRect = () => rect;
  function makeButton() {
    const node = {
      isConnected: true, get disabled() { return options.disabled === true
        || (options.readyAfterPreflightReads && state.preflightReads < options.readyAfterPreflightReads)
        || (options.postAttachNotReadyReads && state.postAttachReads > 0
          && state.postAttachReads <= options.postAttachNotReadyReads)
        || (options.postClaimNotReadyReads && state.postClaimReads > 0
          && state.postClaimReads <= options.postClaimNotReadyReads); }, innerText: "", textContent: "",
      form: composerForm, type: 'submit',
      getBoundingClientRect: () => ({ ...rect, left: rect.left + state.offset, right: rect.right + state.offset }),
      getAttribute: (name) => name === "aria-label" ? state.label : name === 'type' ? 'submit'
        : name === 'aria-disabled' && options.ariaDisabled ? 'true' : null,
      contains: (target) => target === node,
      closest: selector => selector === 'form' ? composerForm : state.label === "Send message" ? node : null,
      focus: () => {
        state.focused = node;
        if (options.focusReplacesButton && !state.focusReplaced) {
          state.focusReplaced = true; node.isConnected = false;
          state.button = makeButton(); state.offset += 40;
        }
      }
    };
    return node;
  }
  const button = makeButton(); state.button = button; state.extraButton = makeButton();
  const page = vm.createContext({
    window: {}, innerHeight: 1000, innerWidth: 1000, HTMLTextAreaElement: class {},
    Date: { now: () => clock },
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    document: {
      get activeElement() { return state.focused; },
      querySelector: () => null,
      querySelectorAll: (selector) => selector.includes("contenteditable") ? [state.editor]
        : queryButtons(selector),
      elementFromPoint: () => options.blocked ? { tagName: "DIV", id: "overlay" } : state.button,
      addEventListener: (type, callback) => listeners.set(type, [...(listeners.get(type) || []), callback])
    }
  });
  if (options.legacyCapture) {
    page.window.__smartflowAiSendGesture = { armed: true, events: [] };
    for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
      listeners.set(type, [(event) => {
        const oldGesture = page.window.__smartflowAiSendGesture;
        if (oldGesture?.armed) oldGesture.events.push({ type, trusted: event.isTrusted });
      }]);
    }
  }
  function fire(type, target = state.button, x = 40 + state.offset, y = 40) {
    if (type !== 'mousemove') clock += options.slowEvents ? 70000 : 7;
    if (type === 'mousemove' ? !options.dropHoverEvents : !options.noCapturedEvents)
      for (const listener of listeners.get(type) || []) {
      listener({ target, isTrusted: true, clientX:x, clientY:y, composedPath: () => [target] });
    }
  }
  function accept() {
    state.accepted = true;
    // Keep the editor handed to sendAndVerify detached and nonempty.
    state.editor = { innerText: "", getBoundingClientRect: () => rect, closest: () => null };
  }
  const backend = vm.createContext({
    aiSendInFlight: new Set(),
    aiProgressOwnership: async () => {
      state.ownerChecks++;
      return { active: !(options.loseOwnership && state.ownerChecks > 1), ownerTabId: 12, activeRunId: "run-test" };
    },
    setTimeout: (callback, delay) => { state.delays.push(delay); callback(); return 1; },
    chrome: {
      storage:{local:{get:async()=>structuredClone(storage),set:async value=>{
        if (Object.hasOwn(value,claim.key+':dispatch')) state.dispatchLatched=true;
        Object.assign(storage,structuredClone(value));
      }}},
      windows: { get: async () => ({state:state.windowState}),
        update: async (_id,update) => {state.windowUpdates.push(update); if(update.state) state.windowState=update.state;} }, tabs: {
        get: async () => {
          if(state.tabMissing) throw Error('Tab closed');
          return {id:12,windowId:2,active:state.tabActive};
        },
        update: async (_id,update) => {state.tabUpdates.push(update); if(update.active) state.tabActive=true;},
        sendMessage: async (_tabId, message) => {
          assert.equal(message.type, "VERIFY_AI_SEND_READY");
          return { ok: !options.cancelDuringPreparation };
        }
      },
      scripting: { executeScript: async ({ func, args = [] }) => {
        if (args[1] === true && func.toString().includes('resolveChatGPTComposerSendTarget')) {
          state.preflightReads++;
          if (options.changeDraftAfterPreflightRead === state.preflightReads) state.editor.innerText = 'Changed draft';
        }
        if (args[1] === false && func.toString().includes('resolveChatGPTComposerSendTarget')) {
          state.postAttachReads++;
          if (options.changeDraftAfterPostAttachRead === state.postAttachReads) state.editor.innerText = 'Changed draft';
          if (state.dispatchLatched) {
            state.postClaimReads++;
            if (options.changeDraftAfterPostClaimRead === state.postClaimReads) state.editor.innerText = 'Changed draft';
          }
        }
        page.injectedArgs = args;
        const result = await vm.runInContext(`(${func.toString()})(...injectedArgs)`, page);
        if (args[0] === 'verify' && args[1]?.key) {
          state.probeVerifies++;
          if (state.probeVerifies === 1) {
            if (options.minimizeAfterHover) state.windowState='minimized';
            if (options.switchTabAfterHover) state.tabActive=false;
            if (options.tabMissingAfterHover) state.tabMissing=true;
          }
          if (state.probeVerifies === 2 && options.minimizeAgainAfterRecovery)
            state.windowState='minimized';
        }
        return [{ result }];
      } },
      debugger: {
        attach: async () => { if (options.draftChangesBeforeDispatch) state.editor.innerText = "Changed draft"; },
        detach: async () => {},
        sendCommand: async (_target, method, event) => {
          commands.push({ method, ...event });
          if (event.type === "mouseMoved" && options.hoverMovesButton && !state.hoverMoved) {
            state.hoverMoved = true; state.offset += 30;
          }
          if (event.type === 'mouseMoved' && !options.dropHoverEvents
              && !(options.dropHoverUntilRefocus && state.windowUpdates.length < 2)) {
            const r=state.button.getBoundingClientRect();
            const target=event.x>r.left && event.x<r.right && event.y>r.top && event.y<r.bottom
              ? state.button : {tagName:'DIV'};
            fire('mousemove',target,event.x,event.y);
          }
          if (event.type === "mousePressed") {
            assert.equal(event.x, 40 + state.offset, "Press must use post-hover live coordinates");
            assert.equal(state.focused, state.button, "Focus settles before press");
            fire("pointerdown"); fire("mousedown");
            if (options.pressReplacesButton) { state.button.isConnected = false; state.button = makeButton(); }
            if (options.pressMovesButton) state.offset += 25;
            if (options.pressResponseLost) throw new Error("press response lost");
          }
          if (event.type === "mouseReleased") {
            const releaseTarget = options.releaseOffTarget ? { tagName: "DIV" } : state.button;
            fire("pointerup", releaseTarget); fire("mouseup", releaseTarget);
            // Plausible capture race: the same button no longer matches Send
            // by click time. This reproduces a possibility, not the live cause.
            if (options.captureRace) state.label = "Stop streaming";
            fire("click", releaseTarget);
            if (options.acceptImmediately) accept();
            if (options.releaseResponseLost) throw new Error("release response lost");
          }
        }
      }
    }
  });
  const handler = section(background, 'if (message?.type === "CLICK_AI_SEND_BUTTON")',
    'if (message?.type === "LATCH_FLOW_ATTACHMENT_FAILURE")');
  vm.runInContext(`async function handle(message, sender) {
    let response; const sendResponse = (value) => { response = value; };
    try { await (async () => { ${handler} })(); }
    catch (error) { response = { ok: false, error: error.message }; }
    return response;
  }`, backend);
  const frontend = vm.createContext({
    HTMLTextAreaElement: class {},
    AI_NAME: options.gemini ? "Gemini Web" : "ChatGPT Web", PROVIDER_KEY: options.gemini ? "gemini" : "chatgpt",
    activeJobId: "JOB-TEST", activeRunId: "run-test",
    location:{href:options.gemini?'https://gemini.google.com/app/existing':'https://chatgpt.com/c/existing'},
    chatGPTConversationFrames:()=>[], storyTurnNumber:()=>-1, chatGPTFrameUser:()=>null,
    chatGPTUserMessageId:()=>'',chatGPTFrameId:()=>'',
    chatGPTStoryRequest:()=>state.accepted && options.proof!=='composer'
      ?{reason:'request_found',owner:{conversation_url:'https://chatgpt.com/c/existing',request_turn_id:'turn-new',request_message_id:'message-new'}}
      :{reason:'request_missing',owner:null},
    motionRequestIsLatestUser:()=>state.accepted && options.proof!=='composer',
    geminiTextRequestSnapshot:()=>state.accepted && options.proof!=='composer'
      ?{owner:{conversation_url:'https://gemini.google.com/app/existing',request_container_id:'0123456789abcdef',request_index:1,prompt_hash:'exact'}}:{owner:null},
    composer: () => state.editor, composerText: (editor) => editor?.innerText || "",
    userTurns: () => Array(state.accepted && options.proof !== "composer" ? 2 : 1),
    lastUserTurnSignature: () => "existing-user-turn", assistantTurns: () => Array(1),
    stopButtonVisible: () => false,
    waitForStableSendDraft: async (expected) => {
      assert.equal(expected, prompt); return { button, editor: state.editor };
    },
    assertNotCancelled: () => { if (cancelled) { const error = new Error("Cancelled"); error.name = "AbortError"; throw error; } },
    report: async (step, message, count, extra) => reports.push({ step, message, count, ...extra }),
    sleep: async (ms) => {
      state.sleeps++;
      (state.sleepDelays ||= []).push(ms);
      if (state.sleeps === options.acceptAfterSleeps) accept();
      if (state.sleeps === options.cancelAfterSleeps) cancelled = true;
    },
    chrome: { runtime: { sendMessage: async (message) => {
      if (message.type === 'MEMBERSHIP_AUTHORIZE') return {ok: options.membershipDenied !== true};
      assert.equal(message.type, "CLICK_AI_SEND_BUTTON"); sends++;
      const response = options.responseOverride || await backend.handle({...message,...(options.storyClaim?{story_send_claim:claim}:{})},
        { tab: { id: 12, windowId: 2, url: options.gemini ? "https://gemini.google.com/app/existing" : "https://chatgpt.com/c/existing" } });
      responses.push(response); return response;
    } } }
  });
  {
    const shared=fs.readFileSync(path.join(root,'browser_extension/single_answer.js'),'utf8');
    vm.runInContext(shared,frontend);vm.runInContext(shared,backend);
    if(options.singleAnswer)state.editor.innerText=frontend.SmartFlowSingleAnswer.wrap(prompt);
    frontend.composerText=editor=>frontend.SmartFlowSingleAnswer.canonical(editor?.innerText || '');
  }
  vm.runInContext(section(options.contentSource || content, "async function sendAndVerify(", "async function ensureAiWebModel("), frontend);
  if (options.storySend) {
    frontend.createStoryImageWaitMonitor=()=>({observe:async()=>({})});
    frontend.storyImageRecoveryError=(code,index,message)=>Object.assign(new Error(message),{code,index});
  }
  return {
    run: () => {
      if(frontend.composerText(state.editor)===prompt)
        state.editor.innerText=frontend.SmartFlowSingleAnswer.wrap(prompt);
      return frontend.sendAndVerify(button, originalEditor, 1, "existing-user-turn", 1,
        false, options.storySend ? {scene_index:2,completedCount:1,postRefreshRedo:true,
          onAcceptanceTimeout:async()=>{throw Error('unbounded result monitor entered');}} : null);
    },
    state, originalEditor, commands, reports, responses, frontend, backend, page, accept, storage, claim, sends: () => sends,
    checkSingleDispatch() {
      assert.equal(sends, 1, "Never request another send or upload");
      assert.equal(commands.filter((event) => event.type === "mousePressed").length, 1);
      assert.equal(commands.filter((event) => event.type === "mouseReleased").length, 1);
      assert.equal(commands.filter((event) => event.method === "Input.dispatchKeyEvent").length, 0);
    }
  };
}

async function tests() {
  {
    const f=fixture({storyClaim:true,dropHoverUntilRefocus:true,acceptImmediately:true});
    await f.run();
    assert.equal(f.responses[0].ok,true,'One refocus recovers page input before Send');
    assert.equal(f.state.windowUpdates.length,2);
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,dropHoverEvents:true});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true,'Missing page input stays pre-Send');
    assert.equal(f.responses[0].diagnostics.preflight_reason,'input_not_delivered');
    assert.equal(f.commands.filter(event=>event.type==='mousePressed').length,0);
    assert.equal(f.storage[f.claim.key+':dispatch'],undefined,'No durable claim for a lost hover');
    assert.equal(f.state.windowUpdates.length,2,'One bounded refocus after missing input');
  }
  {
    const f=fixture({storyClaim:true,acceptImmediately:true,minimizedWindow:true});
    await f.run();
    assert.equal(JSON.stringify(f.state.windowUpdates),JSON.stringify([{state:'normal',focused:true}]),
      'Restore only the exact owned minimized browser before Send measurement');
    assert(f.state.delays.includes(350) && f.state.delays.includes(300),
      'Wait for layout after restore and again before the dispatch claim');
    f.checkSingleDispatch();
  }
  for (const option of ['minimizeAfterHover','switchTabAfterHover']) {
    const f=fixture({storyClaim:true,acceptImmediately:true,[option]:true});
    await f.run();
    assert.equal(f.state.probeVerifies,2,`${option} requires a fresh trusted hover`);
    assert.equal(f.state.windowUpdates.length,2,`${option} restores only the owned window once`);
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,minimizeAfterHover:true,minimizeAgainAfterRecovery:true});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true,'Repeated minimize stops before Send');
    assert.equal(f.responses[0].diagnostics.preflight_reason,'send_surface_changed');
    assert.equal(f.commands.filter(event=>event.type==='mousePressed').length,0);
    assert.equal(f.storage[f.claim.key+':dispatch'],undefined);
  }
  {
    const f=fixture({storyClaim:true,tabMissingAfterHover:true});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true,'Lost owned tab stops before Send');
    assert.equal(f.responses[0].diagnostics.preflight_reason,'send_surface_changed');
    assert.equal(f.commands.filter(event=>event.type==='mousePressed').length,0);
    assert.equal(f.storage[f.claim.key+':dispatch'],undefined);
  }
  // Captured 2026-09-24 ChatGPT composer uses aria-label="ส่ง", no test ID.
  // Content sees it, but both injected trusted-click selectors must agree.
  for (const label of ['ส่ง', 'ส่งข้อความ', 'ส่งพรอมต์', 'Send message', 'Send prompt']) {
    const f=fixture({label,storyClaim:true,acceptImmediately:true});
    await f.run();
    assert.equal(f.responses[0].ok,true,label);
    f.checkSingleDispatch();
  }
  for (const flags of [{disabled:true},{ariaDisabled:true}]) {
    const f=fixture({label:'ส่ง',storyClaim:true,...flags});
    await assert.rejects(f.run());
    assert.equal(f.commands.filter(event=>event.type==='mousePressed').length,0);
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,3);
    assert.deepEqual(f.state.delays.filter(delay => delay === 5000),[5000,5000,5000]);
  }
  for (const readyAfterPreflightReads of [2,3,4]) {
    const f=fixture({storyClaim:true,acceptImmediately:true,readyAfterPreflightReads});
    await f.run();
    assert.equal(f.state.preflightReads,readyAfterPreflightReads);
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,readyAfterPreflightReads-1);
    f.checkSingleDispatch();
  }
  for (const postAttachNotReadyReads of [1,3]) {
    const f=fixture({storyClaim:true,acceptImmediately:true,postAttachNotReadyReads});
    await f.run();
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,postAttachNotReadyReads);
    assert.equal(f.reports[0].detail.preflight_rechecks,postAttachNotReadyReads);
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,postAttachNotReadyReads:4});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'send_not_ready');
    assert.equal(f.responses[0].diagnostics.preflight_stage,'after_attach');
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,3);
    assert.equal(f.commands.filter(event => event.type==='mousePressed').length,0);
  }
  {
    const f=fixture({storyClaim:true,postAttachNotReadyReads:2,changeDraftAfterPostAttachRead:2});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'draft_mismatch');
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,1);
    assert.equal(f.commands.filter(event => event.type==='mousePressed').length,0);
  }
  {
    const f=fixture({storyClaim:true,acceptImmediately:true,postClaimNotReadyReads:2});
    await f.run();
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,2);
    assert.equal(f.reports[0].detail.preflight_rechecks,2);
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,postClaimNotReadyReads:4});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'send_not_ready');
    assert.equal(f.responses[0].diagnostics.preflight_stage,'after_claim');
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,3);
    assert.equal(f.commands.filter(event => event.type==='mousePressed').length,0);
  }
  {
    const f=fixture({storyClaim:true,postClaimNotReadyReads:2,changeDraftAfterPostClaimRead:2});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'draft_mismatch');
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,1);
    assert.equal(f.commands.filter(event => event.type==='mousePressed').length,0);
  }
  for (const ambiguousUntilPreflightReads of [2,4]) {
    const f=fixture({storyClaim:true,acceptImmediately:true,ambiguousUntilPreflightReads});
    await f.run();
    assert.equal(f.state.preflightReads,ambiguousUntilPreflightReads);
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,ambiguousUntilPreflightReads-1);
    assert.equal(f.reports[0].detail.preflight_rechecks,ambiguousUntilPreflightReads-1);
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,ambiguousUntilPreflightReads:99});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'send_target_ambiguous');
    assert.equal(f.responses[0].diagnostics.preflight_rechecks,3);
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,3);
    assert.equal(f.commands.filter(event => event.type === 'mousePressed').length,0);
  }
  {
    const f=fixture({storyClaim:true,readyAfterPreflightReads:4,changeDraftAfterPreflightRead:2});
    await assert.rejects(f.run());
    assert.equal(f.responses[0].notDispatched,true);
    assert.equal(f.responses[0].diagnostics.preflight_reason,'draft_mismatch');
    assert.equal(f.state.delays.filter(delay => delay === 5000).length,1);
    assert.equal(f.commands.filter(event => event.type === 'mousePressed').length,0);
  }
  for(const gemini of [false,true]){
    const f=fixture({singleAnswer:true,gemini,storyClaim:!gemini,acceptImmediately:true});
    await f.run();assert.equal(f.responses[0].ok,true);f.checkSingleDispatch();
    assert(f.originalEditor.innerText.includes('Return exactly one final answer'));
    assert.equal(f.storage[f.claim.key].result_proof.prompt.includes('[SmartFlow'),false);
  }
  for (const proof of ["user_turn"]) {
    const f = fixture({ captureRace: true, acceptImmediately: true, proof });
    await f.run();
    assert.equal(f.responses[0].ok, true);
    assert.equal(f.responses[0].dispatched, true);
    assert(f.responses[0].clickEvents.some((event) => event.type === "click"));
    assert.equal(f.reports.at(-1).step, "ai_send_accepted");
    assert.equal(f.reports.at(-1).submission_proof, "owned_chatgpt_user_turn");
    assert(f.originalEditor.innerText.length > 0, "Acceptance must read the live, not detached, composer");
    const detail = f.reports[0].detail;
    assert.equal(detail.trusted_click_seen, true);
    assert(detail.click_events.every((event) => Object.keys(event).sort().join() === "elapsed_ms,on_target,phase,trusted,type"));
    assert.deepEqual(Array.from(detail.click_events, (event) => event.elapsed_ms), [7, 14, 21, 28, 35]);
    assert(detail.click_events.every((event) => event.on_target === true));
    assert.deepEqual(Array.from(detail.click_events, (event) => event.phase), ["pressed", "pressed", "released", "released", "released"]);
    for (const key of ["target_node_changes_prepress", "target_geometry_changes_prepress",
                       "target_node_changes_during_gesture", "target_geometry_changes_during_gesture"]) {
      assert.equal(detail[key], 0);
    }
    f.checkSingleDispatch();
  }
  let f = fixture({ noCapturedEvents: true, acceptAfterSleeps: 44 });
  await f.run();
  assert(f.reports.some((report) => report.step === "ai_send_waiting_acceptance"));
  assert.equal(f.reports.at(-1).step, "ai_send_accepted");
  f.checkSingleDispatch();

  for (const noCapturedEvents of [true, false]) {
    f = fixture({ noCapturedEvents });
    await assert.rejects(f.run(), (error) => {
      assert.equal(error.code, "AI_SEND_DISPATCHED_UNCONFIRMED");
      assert.equal(error.submissionDispatched, true);
      assert.equal(error.sendDiagnostics.draft_still_present, true);
      assert.equal(error.sendDiagnostics.trusted_click_seen, !noCapturedEvents);
      return true;
    });
    assert.equal(f.state.sleeps, 240);
    assert(!f.reports.some((report) => report.step === "ai_send_accepted"));
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,storySend:true,noCapturedEvents:true});
    await assert.rejects(f.run(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW'
      && error.message.includes('SEND_UNCONFIRMED_DRAFT_PRESENT'));
    assert.equal(f.state.sleepDelays.filter(ms=>ms===5000).length,3,
      'uncertain Story Send checks the owned draft three more times');
    assert(f.reports.some(row=>row.step==='image_send_stalled'));
    assert(!f.reports.some(row=>row.step==='ai_send_accepted'));
    f.checkSingleDispatch();
  }
  {
    const f=fixture({storyClaim:true,storySend:true,noCapturedEvents:true,acceptAfterSleeps:241});
    await assert.rejects(f.run(),/unbounded result monitor entered/);
    assert(!f.reports.some(row=>row.step==='image_send_stalled'),
      'a late owned user turn keeps result-only recovery available');
    f.checkSingleDispatch();
  }
  f = fixture({ acceptImmediately: true });
  await f.run();
  assert.equal(f.responses[0].ok, true);
  assert.equal(f.reports[0].detail.trusted_click_seen, true);
  f.checkSingleDispatch();

  for (const options of [{ blocked: true }, { draftChangesBeforeDispatch: true }]) {
    f = fixture(options);
    await assert.rejects(f.run());
    assert.equal(f.commands.length, 0, "Preflight failures must never dispatch");
    assert.equal(f.state.sleeps, 0);
    assert.equal(f.reports.length, 0);
  }
  for (const responseOverride of [
    { ok: false, method: "single_trusted_ai_send_unconfirmed" },
    { ok: false, dispatched: true, method: "different_failure" }
  ]) {
    f = fixture({ responseOverride });
    await assert.rejects(f.run());
    assert.equal(f.state.sleeps, 0, "An unverified dispatch marker must not enter passive acceptance");
  }
  f = fixture({ noCapturedEvents: true, cancelAfterSleeps: 2 });
  await assert.rejects(f.run(), { name: "AbortError" });
  assert.equal(f.state.sleeps, 2);
  f.checkSingleDispatch();
  // Candidate fixes: preparation can focus/hover but never submit twice.
  for (const options of [{ hoverMovesButton: true }, { focusReplacesButton: true },
                         { hoverMovesButton: true, focusReplacesButton: true }]) {
    f = fixture({ ...options, acceptImmediately: true });
    await f.run();
    assert.equal(f.reports.at(-1).step, "ai_send_accepted");
    assert.equal(f.reports[0].detail.target_stable_before_press, true);
    assert.equal(f.reports[0].detail.release_on_send_target, true);
    assert.equal(f.reports[0].detail.gesture_phase, "released");
    assert.equal(f.reports[0].detail.target_node_changes_prepress, options.focusReplacesButton ? 1 : 0);
    assert.equal(f.reports[0].detail.target_geometry_changes_prepress,
      Number(Boolean(options.focusReplacesButton)) + Number(Boolean(options.hoverMovesButton)));
    assert.equal(f.reports[0].detail.target_node_changes_during_gesture, 0);
    assert.equal(f.reports[0].detail.target_geometry_changes_during_gesture, 0);
    if (options.focusReplacesButton) assert.equal(f.reports[0].detail.target_changed, true);
    f.checkSingleDispatch();
  }
  for (const options of [{ releaseOffTarget: true }, { pressReplacesButton: true }]) {
    f = fixture(options);
    await assert.rejects(f.run(), (error) => {
      assert.equal(error.code, "AI_SEND_DISPATCHED_UNCONFIRMED");
      assert.equal(error.sendDiagnostics.trusted_click_seen, false);
      assert.equal(error.sendDiagnostics.release_on_send_target, false);
      assert.equal(error.sendDiagnostics.target_node_changes_prepress, 0);
      assert.equal(error.sendDiagnostics.target_node_changes_during_gesture, options.pressReplacesButton ? 1 : 0);
      assert.equal(error.sendDiagnostics.target_geometry_changes_during_gesture, 0);
      assert(error.sendDiagnostics.click_events.filter((e) => e.phase === "released").every((e) => !e.on_target));
      assert(error.sendDiagnostics.click_events.some((e) => e.type === "mouseup"));
      assert.equal(error.sendDiagnostics.draft_still_present, true);
      return true;
    });
    f.checkSingleDispatch();
  }
  f = fixture({ pressMovesButton: true, acceptImmediately: true });
  await f.run();
  assert.equal(f.reports[0].detail.target_geometry_changes_prepress, 0);
  assert.equal(f.reports[0].detail.target_geometry_changes_during_gesture, 1);
  assert.equal(f.reports[0].detail.target_node_changes_during_gesture, 0);
  const press = f.commands.find((e) => e.type === "mousePressed");
  const release = f.commands.find((e) => e.type === "mouseReleased");
  assert.equal(release.x, press.x, "Diagnostic geometry changes never retarget the release");
  f.checkSingleDispatch();
  f = fixture({ slowEvents: true, acceptImmediately: true });
  await f.run();
  assert(f.reports[0].detail.click_events.every((e) => e.elapsed_ms === 60000));
  f.checkSingleDispatch();
  f = fixture({ legacyCapture: true, acceptImmediately: true });
  await f.run();
  assert.equal(f.page.window.__smartflowAiSendGesture.armed, false);
  assert.equal(f.page.window.__smartflowAiSendGesture.events.length, 0, "Old capture stays inert");
  assert.equal(f.responses[0].clickEvents.length, 5, "Updated capture records one entry per event");
  f.checkSingleDispatch();
  f = fixture({ loseOwnership: true });
  await assert.rejects(f.run());
  assert.equal(f.commands.filter((e) => e.type === "mousePressed").length, 0);
  assert.equal(f.state.sleeps, 0);

  f = fixture({ cancelDuringPreparation: true });
  await assert.rejects(f.run());
  assert.equal(f.commands.filter((e) => e.type === "mousePressed").length, 0);

  const readiness = vm.createContext({ activeJobId: "JOB-TEST", activeRunId: "run-test", cancelRequested: false, IS_GEMINI: false,
    composer: () => ({}), composerText: () => "current draft" });
  const readinessCode = section(content, 'if (message?.type === "VERIFY_AI_SEND_READY")', 'if (message?.type === "CANCEL_CHATGPT_JOB")');
  vm.runInContext(`function ready(message) { let result; const sendResponse = value => { result = value; }; (function () { ${readinessCode} })(); return result; }`, readiness);
  const readinessMessage = { type: "VERIFY_AI_SEND_READY", job_id: "JOB-TEST", run_id: "run-test", expectedPrompt: "current draft" };
  assert.equal(readiness.ready(readinessMessage).ok, true);
  readiness.cancelRequested = true;
  assert.equal(readiness.ready(readinessMessage).ok, false);
  readiness.cancelRequested = false;
  assert.equal(readiness.ready({ ...readinessMessage, run_id: "old-run" }).ok, false);
  assert.equal(readiness.ready({ ...readinessMessage, expectedPrompt: "changed" }).ok, false);

  f = fixture({ acceptImmediately: true });
  const concurrent = await Promise.allSettled([f.run(), f.run()]);
  assert.equal(concurrent.filter((r) => r.status === "fulfilled").length, 1);
  assert.equal(f.commands.filter((e) => e.type === "mousePressed").length, 1);
  assert.equal(f.commands.filter((e) => e.type === "mouseReleased").length, 1);

  for (const options of [{ pressResponseLost: true }, { releaseResponseLost: true }]) {
    f = fixture({ ...options, noCapturedEvents: true });
    await assert.rejects(f.run(), (error) => {
      assert.equal(error.code, "AI_SEND_DISPATCHED_UNCONFIRMED");
      assert.equal(error.submissionDispatched, true);
      assert.equal(error.sendDiagnostics.dispatch_completed, !options.releaseResponseLost);
      assert.equal(error.sendDiagnostics.gesture_phase, options.releaseResponseLost ? "release_uncertain" : "released");
      return true;
    });
    f.checkSingleDispatch();
  }
  f=fixture({storyClaim:true,acceptImmediately:true});await f.run();f.checkSingleDispatch();
  assert.equal(f.storage[f.claim.key+':dispatch'],f.claim.nonce,'Claim persisted before gesture');
  for(const option of ['claimMismatch','claimAlreadyPressed']){
    f=fixture({storyClaim:true,[option]:true});await assert.rejects(f.run());
    assert.equal(f.commands.filter(e=>e.type==='mousePressed').length,0,option);
  }
  process.stdout.write(JSON.stringify({ ok: true, cases: 53 }) + "\n");
}

module.exports = { fixture };
if (require.main === module) tests().catch((error) => { console.error(error); process.exitCode = 1; });
