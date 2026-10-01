const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../browser_extension/chatgpt.js"), "utf8");
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing source section: ${start}`);
  return source.slice(first, last);
}

const analysis = {
  job_id: "JOB-ANALYSIS-FIXTURE",
  caption_short: "ตัวอย่างสินค้า\nพิกัดสินค้า https://example.com/item",
  image_prompts: ["shot one", "shot two", "shot three"]
};
const completeJson = JSON.stringify(analysis, null, 2);

// Time, DOM elements and browser actions are mocked. Production turn discovery,
// ordering, visibility, Stop detection, submitPrompt and JSON extraction run.
function fixture(options = {}) {
  let clock = 1000, sentAt = 0, sends = 0, attachments = 0;
  const reports = [];
  const elapsed = () => clock - sentAt;
  const editor = {}, button = {};
  const element = (attributes = {}, position = 0) => ({
    getAttribute: (name) => attributes[name] || null,
    matches: (selector) => selector === '[data-message-author-role="assistant"]'
      && attributes["data-message-author-role"] === "assistant",
    getBoundingClientRect: () => options.zeroRect && attributes["data-message-author-role"] === "assistant"
      ? { width: 0, height: 0 } : { width: 100, height: 40 },
    compareDocumentPosition: (other) => other.position > position ? 4 : 2,
    querySelector: () => null, querySelectorAll: () => [], position
  });
  const turn = {
    ...element({ "data-message-author-role": "assistant" }, 4),
    get innerText() { return options.content ? options.content(elapsed()) : completeJson; },
    get textContent() { return this.innerText; }
  };
  const oldTurn = { ...element({ "data-message-author-role": "assistant" }, 2), innerText: "old answer" };
  const oldUser = { ...element({ "data-message-author-role": "user" }, 1), innerText: "old question" };
  const newUser = { ...element({ "data-message-author-role": "user" }, 3),
    innerText: options.userContent || "Analyze the same product as JSON only." };
  const liveTurns = () => {
    if (!sends || options.noResponse) return [oldTurn];
    const latest = options.replaceNode ? Object.create(turn) : turn;
    return options.constantCount ? [latest] : [oldTurn, latest];
  };
  const article = (body) => ({
    ...element({}, body.position),
    get innerText() { return body.innerText + (body.position === 4 && options.wrapperContent
      ? options.wrapperContent(elapsed()) : ""); },
    get textContent() { return this.innerText; },
    querySelector: (selector) => selector === '[data-message-author-role="assistant"]' ? body : null
  });
  const stopControls = () => {
    const controls = options.stopLabels ? options.stopLabels(elapsed()) : [];
    if (options.stop?.(elapsed())) controls.push({ label: "Stop generating", testId: "stop-button" });
    return controls.map((control) => ({
      ...element({ "aria-label": control.label, "data-testid": control.testId }),
      getBoundingClientRect: () => control.hidden ? { width: 0, height: 0 } : { width: 40, height: 40 }
    }));
  };
  const document = {
    querySelector: (selector) => selector === 'button[data-testid="stop-button"]'
      ? stopControls().find((control) => control.getAttribute("data-testid") === "stop-button") || null : null,
    querySelectorAll: (selector) => {
      if (selector === "button") return stopControls();
      if (selector === '[data-message-author-role="assistant"]') return liveTurns();
      if (selector === 'article[data-testid^="conversation-turn-"]') return liveTurns().map(article);
      if (selector === '[data-message-author-role="user"]') return sends ? [oldUser, newUser] : [oldUser];
      if (selector === "model-response") return liveTurns();
      if (selector === "user-query") return sends ? [oldUser, newUser] : [oldUser];
      return [];
    }
  };
  const context = vm.createContext({
    activeRepairKey:'',activeCoverRequest:null,conversationPendingText:'',conversationPendingReferences:[],
    chrome: { runtime: { sendMessage: async message => {
      assert.equal(message.type, 'MEMBERSHIP_AUTHORIZE');
      return { ok: true }; // Licensed fixture; authorization denial has its own regression.
    } } },
    AI_NAME: "ChatGPT Web", IS_GEMINI: Boolean(options.gemini),
    document, Node: { DOCUMENT_POSITION_FOLLOWING: 4 },
    location: { href: options.gemini ? 'https://gemini.google.com/app/analysis-fixture' : 'https://chatgpt.com/c/analysis-fixture' },
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    Date: { now: () => clock },
    waitForResponseIdle: async () => {}, waitForComposer: async () => editor,
    setChatGPTImageTool: async () => {}, // Dedicated actual-mode contract: chatgpt_image_tool_447.cjs.
    refreshPendingChatGPTMotion: async () => {}, // DOM/background contract: pending_motion_refresh_396.cjs
    attachSourceImages: async () => { attachments++; },
    setComposerText: async (target) => target, sendButton: () => button,
    sendAndVerify: async () => { sends++; sentAt = clock; },
    assertGeminiTextSendAvailable: async () => {},
    sendGeminiTextAndVerify: async () => { sends++; sentAt = clock; },
    motionRequestIsLatestUser: () => sends > 0,
    sleep: async (ms) => { clock += ms; },
    assertNotCancelled: () => {
      if (sends && elapsed() >= (options.cancelAt ?? Infinity)) {
        const error = new Error("Cancelled"); error.name = "AbortError"; throw error;
      }
    },
    report: async (step, message, count, detail) => reports.push({ step, message, count, detail })
  });
  vm.runInContext(section("  function visible(", "  function statusBanner("), context);
  vm.runInContext(section("  function chatGPTConversationFrames(", "  function explicitImageFailure("), context);
  vm.runInContext(section("  function motionRequestIsLatestUser(", "  async function sendAndVerify("), context);
  vm.runInContext(section("  function isStopGenerationButton(", "  function imageGenerationSignature("), context);
  vm.runInContext(section("  function explicitImageFailure(", "  function composerText("), context);
  vm.runInContext(section("  function confirmedStoryImageServiceError(", "  function storyImageNoResultReady("), context);
  vm.runInContext(section("  function explicitAnalysisRefusal(", "  function storyImageRefusal("), context);
  vm.runInContext(section("  function stableOwnedMotionAnswer(", "  function normaliseDialogueSpeakers("), context);
  return {
    context, turn, reports, elapsed,
    run: () => context.submitPrompt("Analyze the same product as JSON only.", options.images || [], '', 0, null, options.motionContext || null),
    checkSingleSend() {
      assert.equal(sends, 1, "Analysis must have one submission only");
      assert.equal(attachments, options.images?.length ? 1 : 0, "Never attach again while waiting");
    }
  };
}

async function tests() {
  const failures = [], passed = [], timings = {};
  async function test(name, action) {
    try { await action(); passed.push(name); }
    catch (error) { failures.push({ name, error: error.message }); }
  }

  const motionContext={job_id:'STORY-TEST',index:1,context_id:'owned-context'};
  const motion={...motionContext,prompt:'A gentle camera movement follows the same character through the scene.',
    needs_review:false,reference_compatible:true,material_change:false};
  await test('owned full motion JSON survives stale Stop without another Send',async()=>{
    const f=fixture({motionContext,content:()=>JSON.stringify(motion)+'_',stop:()=>true,cancelAt:70000});
    assert.deepEqual(JSON.parse((await f.run()).innerText),motion);
    assert.equal(f.elapsed(),60000);f.checkSingleSend();
  });
  for(const kind of ['wrong_owner','partial','extra_prose','wrong_type','extra_field','gemini'])
    await test('motion stale Stop rejects '+kind,async()=>{
      let value={...motion},suffix='';
      if(kind==='wrong_owner')value.index=2;
      if(kind==='wrong_type')value.needs_review='false';
      if(kind==='extra_field')value.other='unexpected';
      if(kind==='extra_prose')suffix=' service error';
      const content=JSON.stringify(value)+suffix;
      const f=fixture({motionContext,gemini:kind==='gemini',content:()=>kind==='partial'?content.slice(0,-5):content,
        stop:()=>true,cancelAt:70000});
      await assert.rejects(f.run(),{name:'AbortError'});f.checkSingleSend();
    });
  await test('motion review flags are preserved for downstream validation',async()=>{
    const value={...motion,needs_review:true,reference_compatible:false,material_change:true};
    const f=fixture({motionContext,content:()=>JSON.stringify(value),stop:()=>true,cancelAt:70000});
    assert.deepEqual(JSON.parse((await f.run()).innerText),value);f.checkSingleSend();
  });
  await test('motion equal-length edits restart stable window',async()=>{
    const f=fixture({motionContext,content:ms=>JSON.stringify({...motion,prompt:motion.prompt+(ms<40000?'A':'B')}),
      stop:()=>true,cancelAt:110000});
    await f.run();assert.equal(f.elapsed(),100000);f.checkSingleSend();
  });

  await test("growing text with absent Stop must finish and stabilize", async () => {
    const f = fixture({
      images: ["safe-source-image"],
      content: (ms) => ms < 7000 ? completeJson.slice(0, 30 + Math.floor(ms / 500) * 5) : completeJson
    });
    const result = await f.run();
    timings.growing_text_ms = f.elapsed();
    assert.equal(result.innerText, completeJson, "Do not hand partial JSON to repair while text is growing");
    assert(f.elapsed() >= 9200, "Completed text must remain unchanged for the stability interval");
    assert.equal(f.context.extractJson(result).job_id, analysis.job_id);
    f.checkSingleSend();
  });

  await test("equal length text changes reset stability", async () => {
    const f = fixture({ content: (ms) => ms < 7000
      ? JSON.stringify({ job_id: "JOB-ANALYSIS-FIXTURE", caption: String(Math.floor(ms / 500) % 10) })
      : JSON.stringify({ job_id: "JOB-ANALYSIS-FIXTURE", caption: "Z" }) });
    const result = await f.run();
    timings.equal_length_changes_ms = f.elapsed();
    assert.equal(f.context.extractJson(result).caption, "Z");
    assert(f.elapsed() >= 9200);
    f.checkSingleSend();
  });

  await test("completed JSON still returns after the original stability interval", async () => {
    const f = fixture();
    await f.run();
    timings.already_complete_ms = f.elapsed();
    assert(f.elapsed() >= 2200 && f.elapsed() <= 3000);
    f.checkSingleSend();
  });

  await test("changing article controls do not delay a completed inner answer", async () => {
    const f = fixture({ wrapperContent: (ms) => "\nElapsed " + ms + " seconds" });
    const result = await f.run();
    assert.equal(result, f.turn, "Return the selected article's own assistant body");
    assert.equal(result.innerText, completeJson);
    assert.equal(f.elapsed(), 2500);
    assert.equal(f.context.extractJson(result).job_id, analysis.job_id);
    f.checkSingleSend();
  });

  await test("growing inner answer still waits while article controls change", async () => {
    const f = fixture({
      content: (ms) => ms < 7000 ? completeJson.slice(0, 30 + Math.floor(ms / 500) * 5) : completeJson,
      wrapperContent: (ms) => "\nElapsed " + ms
    });
    assert.equal((await f.run()).innerText, completeJson);
    assert.equal(f.elapsed(), 9500);
    f.checkSingleSend();
  });

  await test("virtualized zero-size answer with changing wrappers completes", async () => {
    const f = fixture({ zeroRect: true, replaceNode: true, constantCount: true,
      wrapperContent: (ms) => "\nElapsed " + ms });
    assert.equal((await f.run()).innerText, completeJson);
    assert.equal(f.elapsed(), 2500);
    f.checkSingleSend();
  });

  await test("clear audio Stop labels are not image generation or analysis Stop", async () => {
    for (const label of ["Stop reading aloud", "Stop recording", "หยุดอ่านออกเสียง", "หยุดการบันทึกเสียง"]) {
      const f = fixture({ stopLabels: () => [{ label }] });
      assert.equal(f.context.stopButtonVisible(), false, "Audio controls must not block image generation or act as generation Stop");
      assert.equal((await f.run()).innerText, completeJson);
      assert.equal(f.elapsed(), 2500);
      f.checkSingleSend();
    }
  });

  await test("audio Stop never hides simultaneous genuine generation Stop", async () => {
    for (const reverse of [false, true]) {
      const f = fixture({ cancelAt: 420000, stopLabels: () => {
        const labels = [{ label: "Stop reading aloud" }, { label: "Stop generating" }];
        return reverse ? labels.reverse() : labels;
      } });
      await assert.rejects(f.run(), { name: "AbortError" });
      assert.equal(f.elapsed(), 420000);
      f.checkSingleSend();
    }
  });

  await test("genuine unlabeled generation Stop still blocks completion", async () => {
    const f = fixture({ cancelAt: 420000, stopLabels: () => [{ label: "", testId: "stop-button" }] });
    await assert.rejects(f.run(), { name: "AbortError" });
    f.checkSingleSend();
  });

  await test("timeout diagnostics omit answer and arbitrary page labels", async () => {
    const secret = "https://example.invalid/private?token=DO-NOT-LOG";
    const f = fixture({ noResponse: true });
    await assert.rejects(f.run(), (error) => {
      assert.equal(error.code, "AI_ANALYSIS_TIMEOUT");
      assert(error.message.includes("AI_ANALYSIS_TIMEOUT"));
      assert.equal(error.analysisDiagnostics.answer_length, 0);
      assert.equal(error.analysisDiagnostics.answer_unchanged_ms, 360000);
      assert.equal(error.analysisDiagnostics.response_wait_ms, 360000);
      assert.equal(error.analysisDiagnostics.after_latest_user, false);
      assert.equal(error.analysisDiagnostics.answer_node, "none");
      assert.match(error.analysisDiagnostics.answer_hash, /^[0-9a-f]{8}$/);
      assert.equal(error.analysisDiagnostics.stop_label, "none");
      assert(!error.message.includes(secret) && !error.message.includes(analysis.job_id));
      assert(error.message.length < 700);
      return true;
    });
    f.checkSingleSend();
  });

  await test("Gemini audio Stop cannot hide a completed answer", async () => {
    const f = fixture({ gemini: true, cancelAt: 420000, stopLabels: () => [{ label: "Stop reading aloud" }] });
    await f.run();
    assert(f.elapsed() < 10000);
    f.checkSingleSend();
  });

  await test("Stop reappearing resets stability without another send", async () => {
    const f = fixture({ stop: (ms) => ms >= 1500 && ms < 4000 });
    await f.run();
    assert(f.elapsed() >= 6200);
    f.checkSingleSend();
  });

  await test("temporarily empty response resets stability", async () => {
    const f = fixture({ content: (ms) => ms >= 1500 && ms < 4000 ? "" : completeJson });
    await f.run();
    assert(f.elapsed() >= 6200);
    f.checkSingleSend();
  });

  await test("virtualized constant turn count uses the response after the user", async () => {
    const f = fixture({ constantCount: true });
    const result = await f.run();
    assert.equal(f.context.extractJson(result).job_id, analysis.job_id);
    f.checkSingleSend();
  });

  await test("replacing a virtualized node with unchanged text does not restart the timer", async () => {
    const f = fixture({ replaceNode: true, constantCount: true });
    await f.run();
    assert(f.elapsed() >= 2200 && f.elapsed() <= 3000);
    f.checkSingleSend();
  });

  await test("stable refusal preserves the bounded repair handoff", async () => {
    const refusal = "ฉันเป็นเพียงโมเดลภาษา ไม่สามารถช่วยได้";
    const f = fixture({ gemini: true, content: () => refusal });
    assert.equal((await f.run()).innerText, refusal);
    assert(f.elapsed() >= 1800 && f.elapsed() <= 2500);
    f.checkSingleSend();
  });

  await test("transient refusal resets the ordinary response stability interval", async () => {
    const refusal = "ฉันเป็นเพียงโมเดลภาษา ไม่สามารถช่วยได้";
    const f = fixture({ content: (ms) => ms >= 500 && ms < 2000 ? refusal : completeJson });
    const result = await f.run();
    timings.transient_refusal_then_same_json_ms = f.elapsed();
    assert.equal(result.innerText, completeJson);
    assert(f.elapsed() >= 4200, "Time before a transient refusal must not count toward JSON stability");
    f.checkSingleSend();
  });

  await test("completed owned provider failure waits for stable idle proof", async () => {
    const f = fixture({ content: () => "failed to generate an image" });
    await assert.rejects(f.run(), (error) => error.code === "AI_ANALYSIS_FAILED"
      && error.confirmedServiceFailure === true);
    assert(f.elapsed() >= 7000);
    f.checkSingleSend();
  });

  await test("transient native stream error with Stop becomes valid JSON", async () => {
    const failure = "เกิดข้อผิดพลาดในสตรีมของข้อความ\nลองใหม่";
    const f = fixture({ content: ms => ms < 12000 ? failure : completeJson,
      stop: ms => ms < 10000 });
    assert.equal((await f.run()).innerText, completeJson);
    assert(f.elapsed() >= 14000);
    f.checkSingleSend();
  });

  await test("brief idle provider error becomes valid JSON without terminal", async () => {
    const f = fixture({ content: ms => ms < 4000 ? "failed to generate an image" : completeJson });
    assert.equal((await f.run()).innerText, completeJson);
    assert(f.elapsed() >= 6200);
    f.checkSingleSend();
  });

  await test("policy text and quoted technical words are not native failures", async () => {
    for (const content of [
      "failed to generate an image because of policy",
      JSON.stringify({ job_id: analysis.job_id, message: "failed to generate an image" })
    ]) {
      const f = fixture({ content: () => content });
      assert.equal((await f.run()).innerText, content);
      assert(f.elapsed() < 7000);
      f.checkSingleSend();
    }
  });

  await test("foreign request cannot confirm a technical analysis failure", async () => {
    const f = fixture({ userContent: "Unrelated request", content: () => "failed to generate an image" });
    await assert.rejects(f.run(), error => error.code === "AI_ANALYSIS_TIMEOUT");
    f.checkSingleSend();
  });

  await test("changing response beyond six minutes finishes in the same submission", async () => {
    const f = fixture({ content: (ms) => ms < 480000 ? '{"draft":"' + ms : completeJson });
    assert.equal((await f.run()).innerText, completeJson);
    assert.equal(f.elapsed(), 482500);
    f.checkSingleSend();
  });

  await test("long thinking without answer finishes after twelve minutes", async () => {
    for (const gemini of [false, true]) {
      const f = fixture({ gemini, stop: ms => ms < 720000,
        content: ms => ms < 720000 ? "" : completeJson });
      assert.equal((await f.run()).innerText, completeJson);
      assert.equal(f.elapsed(), 722500);
      assert(f.reports.some(r => r.step === "waiting_for_analysis" && r.detail?.response_wait_ms > 360000));
      f.checkSingleSend();
    }
  });

  await test("lost generation signal gets a fresh inactivity window", async () => {
    const f = fixture({ noResponse: true, stop: ms => ms < 420000 });
    await assert.rejects(f.run(), error => error.code === "AI_ANALYSIS_TIMEOUT");
    assert(f.elapsed() >= 779000);
    f.checkSingleSend();
  });

  await test("absent response keeps the existing timeout and delayed status", async () => {
    const f = fixture({ noResponse: true });
    await assert.rejects(f.run(), (error) => error.code === "AI_ANALYSIS_TIMEOUT" && error.submissionConfirmed);
    assert.equal(f.elapsed(), 360000);
    assert.equal(f.reports.filter((report) => report.step === "analysis_response_delayed").length, 1);
    f.checkSingleSend();
  });

  await test("stable malformed answer still reaches bounded repair", async () => {
    const f = fixture({ content: () => '{"job_id":"JOB-ANALYSIS-FIXTURE","draft":' });
    const result = await f.run();
    assert(f.elapsed() >= 2200 && f.elapsed() <= 3000);
    assert.throws(() => f.context.extractJson(result), /JSON/);
    f.checkSingleSend();
  });

  await test("cancellation interrupts a growing response", async () => {
    const f = fixture({ cancelAt: 4000, content: (ms) => '{"draft":"' + ms });
    await assert.rejects(f.run(), { name: "AbortError" });
    assert.equal(f.elapsed(), 4000);
    f.checkSingleSend();
  });

  await test("existing local parser already accepts decorated link newline", async () => {
    const f = fixture();
    const innerText = completeJson.replace("https://example.com/item", "https://example.com/item\n");
    assert.throws(() => JSON.parse(innerText));
    const parsed = f.context.extractJson({ innerText, textContent: completeJson });
    assert.equal(parsed.job_id, analysis.job_id);
    assert.equal(parsed.image_prompts.length, 3);
  });

  process.stdout.write(JSON.stringify({ ok: failures.length === 0, cases: passed.length + failures.length, timings, passed, failures }) + "\n");
  if (failures.length) process.exitCode = 1;
}

tests().catch((error) => { console.error(error); process.exitCode = 1; });
