// Request 332 regression: run the production text coordinator, acceptance loop,
// analysis wait and Background trusted gesture. Only DOM, time and storage are
// simulated. No browser profile, provider request or user job is touched.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const { fixture } = require('./ai_send_acceptance_harness');

const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing production section: ${start}`);
  return source.slice(first, last);
}
const copy = value => JSON.parse(JSON.stringify(value));
const REQUEST = 'Return request twelve as JSON with scene_index 12 and the existing scene identity.';
const OWNER_ID = 'cccccccccccc0012';

function setup(options = {}) {
  const f = fixture({ gemini: true }), c = f.frontend;
  const storage = {}, writes = [], containers = [];
  let now = 1000, firstPressAt = null, acceptedAt = null, attachments = 0;
  const rect = { left: 20, top: 20, width: 40, height: 40, bottom: 60, right: 60 };
  const shell = { querySelectorAll: () => [] };
  const setDraft = text => {
    f.state.editor = { innerText: text, textContent: text, isConnected: true, closest: () => shell,
      getBoundingClientRect: () => rect };
  };
  setDraft('');

  // Sanitized structure observed in Gemini: a stable hexadecimal ID belongs to
  // .conversation-container; user-query itself has no ID. model-response is
  // in the same container, following its user-query. The text is fixture data.
  function makeContainer(id, prompt, answer, sequence) {
    const container = { id, className: 'conversation-container', sequence };
    function node(tag, text, offset) {
      const attributes = tag === 'user-query' ? {} : { 'data-test-id': 'model-response' };
      const value = { tagName: tag.toUpperCase(), id: '', innerText: text, textContent: text,
        parentElement: container, isConnected: true, position: sequence * 2 + offset,
        getBoundingClientRect: () => ({ width: 100, height: 40 }),
        getAttribute: name => attributes[name] || null,
        matches: selector => selector === tag,
        closest: selector => selector.includes('.conversation-container') ? container : null,
        contains: other => other === value,
        compareDocumentPosition: other => other.position > value.position ? 4 : 2,
        querySelector: () => null, querySelectorAll: () => [] };
      return value;
    }
    container.user = node('user-query', 'คุณบอกว่า\n' + prompt, 0);
    container.answer = answer == null ? null : node('model-response', answer, 1);
    Object.assign(container, {
      getAttribute: name => name === 'id' ? id : name === 'class' ? 'conversation-container' : null,
      matches: selector => selector === '.conversation-container' || selector === '#' + id,
      closest: selector => selector.includes('.conversation-container') ? container : null,
      contains: other => other === container || other === container.user || other === container.answer,
      querySelector: selector => selector === 'user-query' ? container.user
        : selector === 'model-response' ? container.answer : null,
      querySelectorAll: selector => selector === 'user-query' ? [container.user]
        : selector === 'model-response' ? (container.answer ? [container.answer] : []) : [],
      getBoundingClientRect: () => ({ width: 100, height: 100 })
    });
    return container;
  }
  function mount(id, prompt, answer, sequence = containers.length + 1) {
    const container = makeContainer(id, prompt, answer, sequence);
    containers.push(container); containers.sort((a, b) => a.sequence - b.sequence);
    return container;
  }
  function remove(id) {
    const index = containers.findIndex(row => row.id === id);
    if (index < 0) return null;
    const [row] = containers.splice(index, 1);
    row.user.isConnected = false;
    if (row.answer) row.answer.isConnected = false;
    return row;
  }
  for (let index = 1; index <= (options.historyCount ?? 11); index++) {
    mount(index.toString(16).padStart(16, '0'), `Saved request ${index}.`,
      JSON.stringify({ scene_index: index, answer: 'previous' }), index);
  }
  const allUsers = () => containers.map(row => row.user);
  const allAnswers = () => containers.map(row => row.answer).filter(Boolean);
  const document = {
    getElementById: id => containers.find(row => row.id === id) || null,
    querySelector: selector => selector.startsWith('#')
      ? containers.find(row => row.id === selector.slice(1)) || null : null,
    querySelectorAll: selector => selector === 'user-query' ? allUsers()
      : selector === 'model-response' ? allAnswers()
      : selector.includes('.conversation-container') ? containers : []
  };
  Object.assign(c, {
    IS_GEMINI: true, geminiImageRetryGuard: null, geminiTextRetryGuard: null,
    geminiTextSendGuardDetail: null, cancelRequested: false,
    TextEncoder, Uint8Array, crypto: webcrypto, Date: { now: () => now },
    location: { href: 'https://gemini.google.com/app/aaaaaaaaaaaa0332' }, document,
    Node: { DOCUMENT_POSITION_FOLLOWING: 4 }, CSS: { escape: value => value },
    visible: value => Boolean(value),
    generatedImageElements: () => [], sourceAttachmentPreviews: () => [],
    sendButton: () => f.state.button, stopButtonVisible: () => false,
    waitForResponseIdle: async () => {}, setChatGPTImageTool: async () => {}, waitForComposer: async () => f.state.editor,
    attachSourceImages: async () => { attachments++; },
    setComposerText: async (editor, text) => { setDraft(c.SmartFlowSingleAnswer.wrap(text)); return f.state.editor; },
    waitForStableSendDraft: async expected => {
      assert.equal(c.SmartFlowSingleAnswer.canonical(f.state.editor.innerText), expected);
      return { editor: f.state.editor, button: f.state.button };
    },
    analysisResponseStopButton: () => options.unrelatedStop && acceptedAt != null
      ? { getAttribute: () => 'Stop generating' } : null,
    explicitAnalysisRefusal: () => false, explicitImageFailure: () => false,
    assertNotCancelled: () => {
      assert(now - 1000 < (options.maxElapsed ?? 145000),
        'Owner loss must not drift into a six-minute timeout or wait forever on unrelated Stop');
    },
    sleep: async ms => {
      now += ms; f.state.sleeps++;
      await options.onSleep?.(api, ms);
    }
  });
  c.chrome.storage = { local: {
    get: async key => ({ [key]: storage[key] ? copy(storage[key]) : null }),
    set: async value => {
      for (const [key, row] of Object.entries(value)) {
        storage[key] = copy(row); writes.push(copy(row));
      }
    }
  } };
  vm.runInContext(section('function chatGPTConversationFrames(', 'function explicitImageFailure(')
    + section('function confirmedAnalysisTechnicalFailure(', 'function composerText(')
    + section('function motionRequestIsLatestUser(', 'async function sendAndVerify(')
    + section('function sameStoryImageReceipt(', 'function createStoryImageReceipt(')
    + section('function geminiImageSendState(', 'async function sendGeminiImageAndVerify(')
    + section('function stableOwnedMotionAnswer(', 'async function submitPrompt(')
    + section('async function submitPrompt(', 'function analysisResponseStopButton(')
    + section('function analysisStopLabel(', 'function escapeJsonControlCharacters('), c);
  const ready = section('    if (message?.type === "VERIFY_AI_SEND_READY")',
    '    if (message?.type === "CANCEL_CHATGPT_JOB")');
  vm.runInContext(`function verifyReady(message) { return new Promise(resolve => {
    const sendResponse = resolve; (() => { ${ready} })(); }); }`, c);
  f.backend.chrome.tabs.sendMessage = async (_tab, message) => c.verifyReady(message);
  const originalSend = c.chrome.runtime.sendMessage;
  c.chrome.runtime.sendMessage = async message => {
    const draft = f.state.editor.innerText;
    const result = await originalSend(message);
    if(message.type === 'MEMBERSHIP_AUTHORIZE') return result;
    if (firstPressAt == null && f.commands.some(row => row.type === 'mousePressed')) firstPressAt = now;
    await options.onSend?.(api, draft, f.sends());
    return result;
  };
  const originalReport = c.report;
  c.report = async (...args) => {
    await originalReport(...args);
    if (args[0] === 'ai_send_accepted') acceptedAt = now;
    await options.onReport?.(api, args[0]);
  };
  const api = { ...f, storage, writes, containers, setDraft, mount, remove,
    now: () => now, elapsed: () => now - 1000,
    sincePress: () => firstPressAt == null ? -1 : now - firstPressAt,
    sinceAccepted: () => acceptedAt == null ? -1 : now - acceptedAt,
    presses: () => f.commands.filter(row => row.type === 'mousePressed').length,
    attachments: () => attachments,
    accept: (prompt = REQUEST, answer = '{"scene_index":12,"answer":"owned"}', id = OWNER_ID, sequence = 12) => {
      const container = mount(id, prompt, answer, sequence); setDraft(''); return container;
    },
    run: (prompt = REQUEST, beforeSend = null) => c.submitPrompt(prompt, [], '', 0, beforeSend)
  };
  return api;
}

async function review(run) {
  let result;
  await assert.rejects(run, error => {
    result = error;
    assert.equal(error.code, 'GEMINI_TEXT_REQUEST_REVIEW');
    assert.equal(error.submissionConfirmed, false);
    return true;
  });
  return result;
}

function motionResumeFixture(key, receipt, options = {}) {
  const f = setup({ maxElapsed: 35000, ...options }), c = f.frontend;
  f.storage[key] = copy(receipt);
  const context = { job_id: c.activeJobId, index: 12, context_id: 'fixture-motion-332',
    image_url: 'http://fixture.invalid/saved-scene12.png', aspect_ratio: '9:16' };
  const candidate = { job_id: context.job_id, index: context.index, context_id: context.context_id,
    prompt: '9:16 one video. The original character walks slowly through the same scene.',
    needs_review: false, reference_compatible: true, material_change: false };
  const mountOwner = () => f.mount(OWNER_ID, REQUEST, JSON.stringify(candidate), 12);
  if (!options.ownerMissing) mountOwner();
  f.mount('dddddddddddd0013', 'Unrelated request thirteen.',
    '{"job_id":"OTHER","index":13,"prompt":"wrong owner"}', 13);
  f.setDraft('');
  c.analysisResponseStopButton = () => ({ getAttribute: () => 'Stop generating' });
  // Resume now shares the production motion completion/parser gate. Keep the
  // pinned Gemini owner DOM below, but do not replace that parser with a stub.
  vm.runInContext(section('function escapeJsonControlCharacters(', 'function normaliseDialogueSpeakers('), c);
  const messages = [];
  let record = { phase: 'requested', request: REQUEST };
  const originalMessage = c.chrome.runtime.sendMessage;
  c.chrome.runtime.sendMessage = async message => {
    if (message.type !== 'FLOW_MOTION_PLAN') return originalMessage(message);
    messages.push(copy(message));
    if (message.action === 'status') return { ok: true, context, record };
    if (message.action === 'prepare') return { ok: true, claimed: false, context, record };
    if (message.action === 'review') {
      record = { ...record, phase: 'answered', result: message.result };
      return { ok: true, record, validation: { errors: [], repairable: false } };
    }
    if (message.action === 'save') {
      record = { ...record, phase: 'ready', prompt: message.result.prompt };
      return { ok: true, context, record };
    }
    assert.fail(`Passive motion resume must not request ${message.action}`);
  };
  vm.runInContext(section('async function prepareFlowMotionPlan(', 'function sceneRepairRequest('), c);
  return { ...f, messages, mountOwner,
    runResume: () => c.prepareFlowMotionPlan({ job: { id: context.job_id } }, {}, 12, 11) };
}

async function tests() {
  let cases = 0;
  // A website-created user bubble visible for one sample is optimistic UI,
  // not durable acceptance. It disappears and the original draft returns.
  let rolledBack = false;
  let f = setup({ maxElapsed: 35000,
    onSend: (current, draft) => current.accept(draft, null),
    onSleep: current => {
      if (current.sincePress() >= 250 && !rolledBack) {
        rolledBack = true; current.remove(OWNER_ID); current.setDraft(REQUEST);
      }
    }
  });
  await review(f.run());
  assert.equal(f.presses(), 1);
  assert.equal(f.containers.length, 11);
  assert.equal(f.frontend.composerText(f.state.editor), REQUEST);
  assert(!f.writes.some(row => row.phase === 'accepted'));
  assert(!f.reports.some(row => row.step === 'ai_send_accepted'));
  assert.equal(f.attachments(), 0); cases++;

  // The receipt was genuinely stable before reporting; then its container
  // vanishes. Even an unrelated live Stop must not renew its wait deadline.
  for (const lossStep of ['ai_send_accepted', 'waiting_for_analysis']) for (const unrelatedStop of [false, true]) {
    f = setup({ maxElapsed: 35000, unrelatedStop,
      onSend: (current, draft) => current.accept(draft),
      onReport: (current, step) => {
        if (step === lossStep) {
          current.remove(OWNER_ID); current.setDraft(REQUEST);
        }
      }
    });
    await review(f.run());
    assert.equal(f.presses(), 1);
    assert(f.sinceAccepted() >= 29000 && f.sinceAccepted() <= 31000,
      `Owner review waited ${f.sinceAccepted()}ms; steps=${f.reports.map(row => row.step).join(',')}`);
    assert(!f.reports.some(row => row.response_active === true),
      'Unowned Stop must not be reported as current request activity');
    if (lossStep === 'waiting_for_analysis') {
      const receipt = Object.values(f.storage).find(row => row.phase === 'accepted');
      assert(receipt, 'This case must lose an owner after its durable acceptance receipt');
      assert.equal(receipt.request_owner.request_container_id, OWNER_ID);
      assert.equal(receipt.request_owner.request_index, 11);
      assert.match(receipt.request_owner.prompt_hash, /^[a-f0-9]{8}$/);
    }
    assert.equal(f.attachments(), 0); cases++;
  }

  // Remount the saved container with entirely new nodes. A later unrelated
  // turn is present, so latest-user/latest-answer selection would be wrong.
  let originalNode, restoredNode;
  f = setup({ maxElapsed: 20000, unrelatedStop: true,
    onSend: (current, draft) => { originalNode = current.accept(draft); },
    onReport: (current, step) => {
      if (step === 'waiting_for_analysis' && !restoredNode && current.containers.some(row => row.id === OWNER_ID)) {
        current.remove(OWNER_ID);
        current.mount('dddddddddddd0013', 'Unrelated request thirteen.',
          '{"scene_index":13,"answer":"unrelated"}', 13);
      }
    },
    onSleep: current => {
      if (current.sinceAccepted() >= 10000 && !restoredNode) {
        restoredNode = current.mount(OWNER_ID, REQUEST,
          '{"scene_index":12,"answer":"remounted"}', 12);
      }
    }
  });
  const remounted = await f.run();
  assert.notEqual(restoredNode.user, originalNode.user);
  assert.equal(remounted.innerText, '{"scene_index":12,"answer":"remounted"}');
  assert.equal(f.presses(), 1); cases++;

  // An owned completed answer remains usable when another later user request
  // starts generating. Its Stop control belongs to that later request.
  f = setup({ maxElapsed: 7000, unrelatedStop: true,
    onSend: (current, draft) => current.accept(draft),
    onReport: (current, step) => {
      if (step === 'waiting_for_analysis') current.mount('dddddddddddd0013',
        'Different active request thirteen.', '{"scene_index":13,"answer":"in progress"}', 13);
    }
  });
  assert.equal((await f.run()).innerText, '{"scene_index":12,"answer":"owned"}');
  assert.equal(f.presses(), 1); cases++;

  // The original request is supplied separately from the mutable composer.
  // A change in beforeSend must not be silently adopted as a different job.
  f = setup();
  await assert.rejects(f.run(REQUEST, async () => f.setDraft('User replacement draft B.')),
    error => /^GEMINI_TEXT_(?:SEND|REQUEST)_REVIEW$/.test(error.code));
  assert.equal(f.presses(), 0);
  assert.equal(f.frontend.composerText(f.state.editor), 'User replacement draft B.');
  assert(!f.writes.some(row => row.phase === 'accepted')); cases++;

  // First and subsequent ordinary text requests continue through the same
  // production path; no image attachment or duplicated request is required.
  f = setup({ historyCount: 0, onSend: (current, draft, number) =>
    current.accept(draft, JSON.stringify({ answer: number }),
      number.toString(16).padStart(16, '0'), number) });
  assert.equal((await f.run('Initial analysis request.')).innerText, '{"answer":1}');
  assert.equal((await f.run('Follow-up scene identity request.')).innerText, '{"answer":2}');
  assert.equal(f.presses(), 2); assert.equal(f.attachments(), 0);
  assert.equal(Object.keys(f.storage).length, 2);
  assert(f.writes.filter(row => row.phase === 'accepted').every(row => row.retry_count === 0));
  cases++;

  // A late first acceptance is still recovered within the existing minute,
  // with no second gesture and no attachment change.
  let lateAccepted = false;
  f = setup({ onSleep: current => {
    if (current.sincePress() >= 11000 && !lateAccepted) {
      lateAccepted = true; current.accept();
    }
  } });
  assert.equal((await f.run()).innerText, '{"scene_index":12,"answer":"owned"}');
  assert.equal(f.presses(), 1); assert.equal(f.attachments(), 0);
  assert(f.writes.some(row => row.phase === 'accepted' && row.retry_count === 0));
  cases++;

  // A genuinely empty new chat may gain its server-assigned conversation URL
  // on the first request. Preserve that successful transition explicitly.
  f = setup({ historyCount: 0, onSend: (current, draft) => {
    current.frontend.location.href = 'https://gemini.google.com/app/bbbbbbbbbbbb0012';
    current.accept(draft, '{"answer":"new chat"}', OWNER_ID, 1);
  } });
  f.frontend.location.href = 'https://gemini.google.com/app';
  assert.equal((await f.run()).innerText, '{"answer":"new chat"}');
  assert.equal(f.presses(), 1);
  assert.equal(Object.values(f.storage)[0].request_owner.conversation_url,
    'https://gemini.google.com/app/bbbbbbbbbbbb0012'); cases++;

  // Matching text in another existing conversation must not own this request,
  // even when that page also has an empty composer and a completed answer.
  f = setup({ maxElapsed: 65000, onSend: (current, draft) => {
    current.frontend.location.href = 'https://gemini.google.com/app/bbbbbbbbbbbb0012';
    current.accept(draft);
  } });
  await assert.rejects(f.run(), error => /^GEMINI_TEXT_(?:SEND|REQUEST)_REVIEW$/.test(error.code));
  assert.equal(f.presses(), 1);
  assert(!f.writes.some(row => row.phase === 'accepted'));
  assert(!f.reports.some(row => row.step === 'ai_send_accepted')); cases++;

  // An unmounted or detached editor is not an observed empty composer.
  // Keep it absent beyond the acceptance stability window, then restore the
  // full draft after the optimistic request bubble disappears.
  for (const detached of [false, true]) {
    let restored = false;
    f = setup({ maxElapsed: 35000, onSend: (current, draft) => {
      current.accept(draft, null);
      current.state.editor = detached ? { innerText: '', isConnected: false } : null;
    }, onSleep: current => {
      if (current.sincePress() >= 1000 && !restored) {
        restored = true; current.remove(OWNER_ID); current.setDraft(REQUEST);
      }
    } });
    await review(f.run());
    assert.equal(f.presses(), 1);
    assert(!f.writes.some(row => row.phase === 'accepted'));
    assert(!f.reports.some(row => row.step === 'ai_send_accepted')); cases++;
  }

  // A genuinely re-mounted empty editor can still prove acceptance after its
  // own stable samples; time spent without an editor must not count.
  let editorRestored = false;
  f = setup({ onSend: (current, draft) => {
    current.accept(draft); current.state.editor = null;
  }, onSleep: current => {
    if (current.sincePress() >= 1000 && !editorRestored) {
      editorRestored = true; current.setDraft('');
    }
  } });
  assert.equal((await f.run()).innerText, '{"scene_index":12,"answer":"owned"}');
  assert.equal(f.presses(), 1);
  assert(f.sincePress() - f.sinceAccepted() >= 1500,
    'Acceptance stability starts only after the empty composer remounts'); cases++;

  // Reuse the actual accepted receipt produced above in a fresh context. This
  // executes prepareFlowMotionPlan's real claimed=false resume path, including
  // receipt key lookup and validation, with no call to the Send coordinator.
  const [receiptKey, acceptedReceipt] = Object.entries(f.storage)[0];
  let resumed = motionResumeFixture(receiptKey, acceptedReceipt);
  await resumed.runResume();
  assert.equal(resumed.presses(), 0); assert.equal(resumed.sends(), 0);
  assert.equal(resumed.attachments(), 0);
  assert.equal(resumed.messages.find(row => row.action === 'save').result.index, 12);
  assert.equal(resumed.writes.length, 0, 'Passive lookup preserves the accepted receipt'); cases++;

  let recoveredOwner = false;
  resumed = motionResumeFixture(receiptKey, acceptedReceipt, { ownerMissing: true,
    onSleep: current => {
      if (current.elapsed() >= 10000 && !recoveredOwner) {
        recoveredOwner = true; resumed.mountOwner();
      }
    }
  });
  await resumed.runResume();
  assert.equal(resumed.sends(), 0);
  assert(resumed.elapsed() >= 18000 && resumed.elapsed() < 20000);
  assert.equal(resumed.messages.find(row => row.action === 'save').result.index, 12); cases++;

  // A present but invalid owner receipt cannot silently fall back to another
  // latest answer. A valid different conversation also stays passive/review.
  for (const [label, corrupt] of [
    ['unaccepted phase', row => { row.phase = 'dispatch_claimed'; }],
    ['wrong job', row => { row.job_id = 'OTHER-JOB'; }],
    ['wrong prompt hash', row => { row.request_owner.prompt_hash = '00000000'; }],
    ['malformed container', row => { row.request_owner.request_container_id = 'not-a-container'; }],
    ['invalid index', row => { row.request_owner.request_index = -1; }],
    ['malformed URL', row => { row.request_owner.conversation_url = 'https://example.invalid/app'; }],
    ['different conversation', row => { row.request_owner.conversation_url = 'https://gemini.google.com/app/bbbbbbbbbbbb0012'; }],
    ['null owner', row => { row.request_owner = null; }]
  ]) {
    const damaged = copy(acceptedReceipt); corrupt(damaged);
    resumed = motionResumeFixture(receiptKey, damaged);
    await review(resumed.runResume());
    assert.equal(resumed.sends(), 0, label);
    assert(!resumed.messages.some(row => ['review', 'save', 'mark_sending'].includes(row.action)), label);
    assert.equal(resumed.writes.length, 0, label); cases++;
  }

  console.log(JSON.stringify({ ok: true, cases }));
}

if(require.main===module)tests().catch(error => { console.error(error); process.exitCode = 1; });
module.exports={setup,REQUEST,OWNER_ID};
