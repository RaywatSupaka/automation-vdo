// Synthetic completed-response fixtures, executing the production parser,
// validators, ownership checks and repair loop. No browser, provider or jobs.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'browser_extension/chatgpt.js'), 'utf8');
const singleAnswerSource = fs.readFileSync(path.join(root, 'browser_extension/single_answer.js'), 'utf8');
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing actual-source section: ${start}`);
  return source.slice(first, last);
}
function definition(name) {
  const pattern = new RegExp(`^  (?:async )?function ${name}\\(`, 'm');
  const match = pattern.exec(source);
  assert(match, `Missing actual-source function: ${name}`);
  const rest = source.slice(match.index + match[0].length);
  const end = /\n  (?:async )?function \w+\(/.exec(rest);
  assert(end, `Missing actual-source end: ${name}`);
  return source.slice(match.index, match.index + match[0].length + end.index);
}
const copy = value => JSON.parse(JSON.stringify(value));
const normalize = value => String(value || '').trim().replace(/\s+/g, ' ');
const initialRequest = 'Analyze the supplied synthetic product as a ten-scene short film. Keep its quoted name.';

function plan() {
  const lines = Array.from({ length: 10 }, (_, index) => `วันนี้เพื่อนทำอาหารด้วยกันเป็นครั้งที่ ${index + 1}`);
  lines[9] += ' ลองเลือกชิมได้เลย';
  return {
    job_id: 'STORY-TEST',
    video_title: 'เรื่องของ"น้ำพริก" ครบทุกรสชาติ',
    product_name: 'น้ำพริก "สูตรบ้านเรา"',
    narration_script: lines.join(' '),
    scene_prompts: lines.map((line, index) => `Scene ${index + 1}: two friends cooking, label "บ้านเรา". ${line}`),
    scene_narrations: lines,
    scene_durations: Array(10).fill(6),
    product_film_plan: {
      version: 1, premise: 'Two friends cook dinner together.',
      product_connection: 'Their meal uses the supplied condiment.',
      resolution: 'They share the completed dinner.', ending_cta_text: 'ลองเลือกชิมได้เลย',
      scenes: lines.map((line, index) => ({
        roles: index === 0 ? ['hook'] : index === 2 ? ['bridge']
          : index === 4 ? ['product'] : index === 9 ? ['payoff', 'cta'] : ['setup'],
        product_visible: index >= 4,
        action: 'Prepare and share the meal.', speaker: 'เพื่อน', listener: 'เจ้าบ้าน',
        spoken_text: line, facts_used: index >= 4 ? ['condiment'] : []
      }))
    }
  };
}
const valid = plan();
const validJson = JSON.stringify(valid, null, 2);
// This models the observed rendered paragraph shape, not the unknown raw reply.
const malformedJson = validJson.replace(/\\"/g, '"');
const pkg = {
  job: { id: valid.job_id, product_short: true },
  request: {
    required_fields: ['video_title', 'product_name', 'narration_script', 'scene_prompts',
      'scene_narrations', 'scene_durations', 'product_film_plan'],
    product_script_options: { version: 2, style: 'short_film_ad', genre: 'warm', ending_cta: true },
    product_script_instruction: 'PRODUCT SHORT FILM AD v2: preserve the event, hidden opening product and final CTA.'
  }
};

function answer(text, rawCode = null) {
  const codes = rawCode === null ? [] : [{ innerText: text, textContent: rawCode,
    matches: selector => selector === 'code', querySelectorAll: () => [] }];
  const node = {
    innerText: text, textContent: text,
    matches: selector => selector.includes('data-message-author-role="assistant"'),
    querySelector: selector => /(?:pre|code)/.test(selector) ? codes[0] || null : null,
    querySelectorAll: selector => /(?:pre|code)/.test(selector) ? codes : [],
    getAttribute: () => null
  };
  return node;
}
const fencedAnswer = () => answer('```json\n' + validJson + '\n```', validJson);

function fixture(options = {}) {
  const calls = [], reports = [], delays = [];
  let currentAnswer = options.first || answer(malformedJson), currentRequest = initialRequest;
  let draft = '', elapsed = 0, dispatched = 0, stopped = false, changed = false;
  let messageId = 'analysis-user-1';
  let attachment = { count: 0, busy: false, failed: false };
  const uuid = '12345678-1234-1234-1234-123456789abc';
  const location = { href: options.temporaryWebUrl
    ? 'https://chatgpt.com/c/WEB:' + uuid : 'https://chatgpt.com/c/analysis-json-fixture' };
  const user = { get innerText() { return currentRequest; }, get textContent() { return currentRequest; },
    getAttribute: name => name === 'data-message-id' ? messageId : null };
  class SyntheticTextArea {
    get value() { return draft; }
    set value(text) { draft = text; }
    focus() {}
    dispatchEvent() { return true; }
  }
  class SyntheticInputEvent { constructor(type, options) { this.type = type; Object.assign(this, options); } }
  const editor = new SyntheticTextArea();
  const context = vm.createContext({
    AI_NAME: options.gemini ? 'Gemini Web' : 'ChatGPT Web', IS_GEMINI: Boolean(options.gemini),
    activeJobId: valid.job_id, activeRunId: 'RUN-ANALYSIS-FIXTURE',
    activeRepairKey: '', activeCoverRequest: null, cancelRequested: false, stopProviderOnCancel: true,
    location, document: { querySelectorAll: () => [], querySelector: () => null },
    Date: { now: () => 1000 + elapsed }, visible: () => true,
    analysisResponseStopButton: () => stopped ? {} : null,
    stopButtonVisible: () => stopped,
    stopButton: () => null, loginRequired: () => false,
    composer: () => editor, composerText: () => normalize(draft),
    HTMLTextAreaElement: SyntheticTextArea, InputEvent: SyntheticInputEvent, Event: SyntheticInputEvent,
    chatGPTComposerAttachmentState: () => attachment, geminiComposerAttachmentState: () => attachment,
    userTurns: () => [user], motionRequestIsLatestUser: request => normalize(request) === normalize(currentRequest),
    geminiTextRequestSnapshot: request => ({ owner: normalize(request) === normalize(currentRequest) ? user : null }),
    latestAssistantStrictlyAfterLatestUser: () => currentAnswer,
    report: async (...args) => reports.push(args),
    sleep: async ms => {
      delays.push(ms); elapsed += ms;
      if (options.cancelDuringWait) context.cancelRequested = true;
      if (!changed && options.changeDuringWait) {
        changed = true; change(options.changeDuringWait);
      }
    },
    submitPrompt: async (request, images, filename, completedCount, beforeSend) => {
      const call = { request, images: images || [], elapsed }; calls.push(call);
      if (options.actualComposerWriter) await context.setComposerText(editor, request);
      else draft = request;
      call.wireDraft = draft;
      call.canonicalDraft = context.composerText();
      if (options.changeBeforeSend) change(options.changeBeforeSend);
      if (beforeSend) await beforeSend();
      dispatched += 1;
      if (options.unknownSend) {
        const error = new Error('AI_SEND_DISPATCHED_UNCONFIRMED fixture');
        error.code = 'AI_SEND_DISPATCHED_UNCONFIRMED'; error.submissionDispatched = true;
        throw error;
      }
      currentRequest = options.actualComposerWriter ? draft : request;
      messageId = 'analysis-user-' + (dispatched + 1); draft = '';
      currentAnswer = options.replies?.[dispatched - 1] || fencedAnswer();
      return currentAnswer;
    }
  });
  function change(kind) {
    if (kind === 'owner') currentRequest = 'An unrelated user request';
    else if (kind === 'answer') currentAnswer = answer('A different completed answer');
    else if (kind === 'draft') draft = 'Unsent user-owned draft';
    else if (kind === 'busy') stopped = true;
    else if (kind === 'job') context.activeJobId = 'STORY-OTHER';
    else if (kind === 'run') context.activeRunId = 'RUN-OTHER';
    else if (kind === 'url') location.href = 'https://chatgpt.com/c/another-conversation';
    else if (kind === 'canonical-url') location.href = 'https://chatgpt.com/c/' + uuid;
    else if (kind === 'canonical-different-message') {
      location.href = 'https://chatgpt.com/c/' + uuid; messageId = 'different-message';
    }
    else if (kind === 'wire-tail') draft += '\nUnrequested added instruction';
    else if (kind === 'attachment') attachment = { count: 1, busy: false, failed: false };
    else if (kind === 'upload') attachment = { count: 0, busy: true, failed: false };
    else if (kind === 'failed-upload') attachment = { count: 0, busy: false, failed: true };
    else if (kind === 'streaming') {
      const originalQuery = currentAnswer.querySelectorAll;
      currentAnswer.querySelectorAll = selector => selector.includes('data-is-streaming') ? [{}] : originalQuery(selector);
    }
    else throw new Error('Unknown fixture transition: ' + kind);
  }
  vm.runInContext([
    section('  function chatGPTConversationFrames(', '  function assistantTurns('),
    definition('analysisAnswerNode'), definition('analysisContentHash'), definition('assertNotCancelled'),
    definition('chatGPTKnownRenderedRequestMatches'), definition('chatGPTMotionRequestText'),
    definition('motionRequestMatches'),
    section('  function explicitAnalysisRefusal(', '  function storyImageReferenceRequest('),
    section('  function escapeJsonControlCharacters(', '  async function validateOrRepairStoredAnalysis('),
    section('  function analysisFormatAnswerSignature(', '  function storyImageRecoveryError(')
  ].join('\n'), context);
  if (options.actualComposerWriter) {
    vm.runInContext(singleAnswerSource + '\n' + definition('composerText') + '\n' + definition('setComposerText'), context);
    currentRequest = context.SmartFlowSingleAnswer.wrap(initialRequest);
  }
  if (options.initialGuard) change(options.initialGuard);
  if (options.cancelled) context.cancelRequested = true;
  return {
    context, calls, reports, delays, change,
    get dispatched() { return dispatched; },
    run: (request = initialRequest) => {
      const requestPackage = copy(pkg);
      if (options.beforeAnalysisSend) requestPackage.before_analysis_send = options.beforeAnalysisSend;
      return context.parseOrRepairAnalysis(currentAnswer, requestPackage, 'scene_prompts', 10, request);
    }
  };
}

async function nativeMarkdownRoundtrip() {
  const { chromium } = require(process.env.SMARTFLOW_TEST_PLAYWRIGHT_PACKAGE || 'playwright');
  const { marked } = await import(pathToFileURL(require.resolve('marked')).href);
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.SMARTFLOW_TEST_CHROMIUM || undefined });
  let networkRequests = 0;
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => { networkRequests += 1; return route.abort(); });
    await page.setContent('<main><section id="prose"></section><section id="fenced"></section></main>');
    await page.evaluate(({ prose, fenced }) => {
      document.querySelector('#prose').innerHTML = prose;
      document.querySelector('#fenced').innerHTML = fenced;
    }, { prose: marked.parse(validJson), fenced: marked.parse('```json\n' + validJson + '\n```') });
    await page.addScriptTag({ content: 'const IS_GEMINI=false,AI_NAME="ChatGPT Web";\n'
      + section('  function chatGPTConversationFrames(', '  function assistantTurns(')
      + definition('analysisAnswerNode')
      + section('  function escapeJsonControlCharacters(', '  function normaliseDialogueSpeakers(') });
    const evidence = await page.evaluate(() => {
      const paragraph = document.querySelector('#prose'), fenced = document.querySelector('#fenced');
      let paragraphError = '';
      try { extractJson(paragraph); } catch (error) { paragraphError = error.code || error.message; }
      return { paragraphText: paragraph.innerText, paragraphHasPre: Boolean(paragraph.querySelector('pre')),
        paragraphError, codeText: fenced.querySelector('pre code').textContent,
        parsed: extractJson(fenced) };
    });
    assert.equal(evidence.paragraphHasPre, false);
    assert.notEqual(evidence.paragraphText.trim(), validJson);
    assert.throws(() => JSON.parse(evidence.paragraphText));
    assert(evidence.paragraphError, 'The actual parser must reject the broken paragraph');
    assert.equal(evidence.codeText.trim(), validJson);
    assert.deepEqual(evidence.parsed, valid);
    assert.equal(networkRequests, 0);
  } finally { await browser.close(); }
  console.log(JSON.stringify({ ok: true, checks: 7, native: true,
    networkRequests, liveStateWrites: 0, browserClosed: true }));
}

(async () => {
  if (process.argv.includes('--native')) { await nativeMarkdownRoundtrip(); return; }
  const passed = [], failed = [];
  async function test(name, run) {
    try { await run(); passed.push(name); }
    catch (error) { failed.push({ name, error: String(error.stack || error) }); }
  }

  await test('valid ordinary analysis retains every supplied value', () => {
    const f = fixture();
    assert.deepEqual(copy(f.context.extractJson(answer(validJson))), valid);
  });
  await test('valid fenced content retains NBSP and zero-width text without sanitizing values', () => {
    const f = fixture(), value = { ...valid, caption_short: 'A\u00a0B\u200dC\u200bD' };
    const text = JSON.stringify(value);
    assert.deepEqual(copy(f.context.extractJson(answer('```json\n' + text + '\n```'))), value);
  });
  await test('owned code textContent preserves escaped quotes lost in rendered innerText', () => {
    const f = fixture();
    const node = answer(malformedJson, validJson);
    assert.throws(() => JSON.parse(node.innerText));
    assert.deepEqual(copy(f.context.extractJson(node)), valid);
    assert.equal(node.querySelector('pre code').textContent, validJson, 'Do not mutate the provider DOM');
  });
  await test('selected assistant body scopes code lookup within its own article', () => {
    const f = fixture(), owned = answer(malformedJson, validJson);
    const unrelated = JSON.stringify({ job_id: 'STORY-OTHER', video_title: 'Wrong conversation' });
    const article = {
      innerText: malformedJson + '\nCopy code', textContent: unrelated,
      matches: () => false,
      querySelector: selector => selector.includes('data-message-author-role') ? owned : null,
      querySelectorAll: () => [{ textContent: unrelated }]
    };
    assert.deepEqual(copy(f.context.extractJson(article)), valid);
  });
  await test('malformed paragraph quotes are rejected without inventing local content', () => {
    const f = fixture(), node = answer(malformedJson);
    assert.throws(() => f.context.extractJson(node), /JSON/);
    assert.equal(node.innerText, malformedJson);
  });
  await test('fenced text fallback accepts complete existing JSON', () => {
    const f = fixture();
    assert.deepEqual(copy(f.context.extractJson(answer('```json\n' + validJson + '\n```'))), valid);
  });
  await test('successful ten-scene film bypasses all correction sends and waits', async () => {
    const f = fixture({ first: fencedAnswer() });
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.calls.length, 0); assert.equal(f.delays.length, 0);
  });
  await test('one malformed paragraph is corrected as fenced JSON with original film rules', async () => {
    const f = fixture();
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.dispatched, 1); assert.equal(f.calls[0].images.length, 0);
    assert.match(f.calls[0].request, /```json/);
    assert.match(f.calls[0].request, /PRODUCT SHORT FILM AD/);
    assert.match(f.calls[0].request, /10/); assert.match(f.calls[0].request, /STORY-TEST/);
    assert(!f.calls[0].request.includes('ห้ามใช้ Markdown code fence'));
  });
  await test('long-video repair checkpoints the exact correction before an uncertain Send', async () => {
    const pending = [], f = fixture({ unknownSend:true,
      beforeAnalysisSend: async request => pending.push(request) });
    await assert.rejects(f.run(), error => error.code === 'AI_SEND_DISPATCHED_UNCONFIRMED');
    assert.equal(f.calls.length, 1);
    assert.deepEqual(pending, [f.calls[0].request]);
    assert.equal(f.dispatched, 1);
  });
  await test('actual writer suffix and composer reader preserve canonical beforeSend ownership', async () => {
    const f = fixture({ actualComposerWriter: true });
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.dispatched, 1); assert.equal(f.calls.length, 1);
    const call = f.calls[0], transport = f.context.SmartFlowSingleAnswer;
    assert.notEqual(call.wireDraft, call.request);
    assert.equal(call.wireDraft, transport.wrap(call.request));
    assert(call.wireDraft.endsWith(transport.instruction));
    assert.equal(call.canonicalDraft, normalize(call.request));
    assert.equal(call.wireDraft.split(transport.instruction).length, 2);
  });
  await test('actual composer reader never strips suffix with extra trailing task text', async () => {
    const f = fixture({ actualComposerWriter: true, changeBeforeSend: 'wire-tail' });
    await assert.rejects(f.run(), error => error.code === 'AI_ANALYSIS_FORMAT_REVIEW');
    assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 1);
  });
  await test('owned temporary WEB URL canonicalization keeps the same formatting request', async () => {
    const f = fixture({ temporaryWebUrl: true, changeDuringWait: 'canonical-url', actualComposerWriter: true });
    assert.deepEqual(copy(await f.run()), valid); assert.equal(f.dispatched, 1);
  });
  await test('temporary URL canonicalization with changed message identity cannot Send', async () => {
    const f = fixture({ temporaryWebUrl: true, changeDuringWait: 'canonical-different-message' });
    await assert.rejects(f.run(), error => error.code === 'AI_ANALYSIS_FORMAT_REVIEW');
    assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
  });
  await test('three completed malformed replies reach the fourth good reply beyond old two-repair cap', async () => {
    const f = fixture({ replies: [answer(malformedJson), answer(malformedJson), fencedAnswer()] });
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.dispatched, 3); assert.equal(f.calls.length, 3);
    assert(f.calls.every(call => call.images.length === 0));
    assert(f.reports.length >= 3);
  });
  await test('repeated completed formatting errors have bounded cancellable backoff', async () => {
    const f = fixture({ replies: [...Array.from({ length: 16 }, () => answer(malformedJson)), fencedAnswer()] });
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.dispatched, 17);
    assert(f.delays.length > 0); assert(f.delays.every(ms => ms > 0 && ms <= 500));
    const waits = f.calls.map((call, index) => call.elapsed - (index ? f.calls[index - 1].elapsed : 0));
    assert(waits.every(ms => ms > 0 && ms <= 30000));
    assert.equal(waits.at(-1), 30000); assert.equal(waits.at(-2), 30000);
  });
  await test('unbound legacy callers do not gain continuous Send authority', async () => {
    const f = fixture({ replies: [answer(malformedJson), answer(malformedJson), fencedAnswer()] });
    await assert.rejects(f.run(''), /2/); assert.equal(f.dispatched, 2);
  });
  await test('wrong scene count is corrected with all required ten-scene fields intact', async () => {
    const bad = copy(valid); bad.scene_prompts.pop();
    const f = fixture({ first: answer(JSON.stringify(bad)) });
    assert.deepEqual(copy(await f.run()), valid); assert.equal(f.dispatched, 1);
    for (const field of pkg.request.required_fields) assert(f.calls[0].request.includes(field));
    assert(f.calls[0].request.includes('10'));
  });
  for (const field of ['scene_prompts', 'scene_narrations', 'scene_durations']) {
    for (const count of [9, 11]) {
      await test(`actual validator enforces exactly ten ${field}, rejects ${count}`, () => {
        const f = fixture(), bad = copy(valid);
        bad[field] = Array.from({ length: count }, (_, index) => valid[field][index % 10]);
        assert.throws(() => f.context.validateAnalysis(bad, 'scene_prompts', 10,
          pkg.request.required_fields, [], pkg.request), /10/);
      });
    }
  }
  await test('film plan validation still rejects product in opening and changed narration', () => {
    const f = fixture();
    for (const mutate of [value => { value.product_film_plan.scenes[0].product_visible = true; },
      value => { value.product_film_plan.scenes[4].spoken_text = 'changed spoken text'; },
      value => { value.product_film_plan.scenes.pop(); }]) {
      const bad = copy(valid); mutate(bad);
      assert.throws(() => f.context.validateAnalysis(bad, 'scene_prompts', 10,
        pkg.request.required_fields, [], pkg.request), /PRODUCT_FILM_PLAN/);
    }
  });
  await test('unknown correction Send propagates immediately without replay', async () => {
    const f = fixture({ unknownSend: true });
    await assert.rejects(f.run(), error => error.code === 'AI_SEND_DISPATCHED_UNCONFIRMED');
    assert.equal(f.dispatched, 1); assert.equal(f.calls.length, 1);
  });
  for (const options of [{ cancelled: true }, { cancelDuringWait: true }]) {
    await test('cancellation blocks correction ' + Object.keys(options)[0], async () => {
      const f = fixture(options);
      await assert.rejects(f.run(), { name: 'AbortError' });
      assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
    });
  }
  for (const guard of ['owner', 'answer', 'draft', 'busy', 'job', 'run', 'url', 'attachment', 'upload', 'failed-upload', 'streaming']) {
    await test('changed ' + guard + ' during backoff blocks new Send', async () => {
      const f = fixture({ changeDuringWait: guard });
      await assert.rejects(f.run()); assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
    });
  }
  await test('last-moment ownership change fails before correction dispatch', async () => {
    const f = fixture({ changeBeforeSend: 'owner' });
    await assert.rejects(f.run()); assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 1);
  });
  await test('genuine Story refusal remains terminal with no format retry', async () => {
    const f = fixture({ first: answer('I cannot help with this request because it violates policy.') });
    await assert.rejects(f.run(), /STORY_IMAGE_REFUSED/);
    assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
  });
  for (const text of ['Your usage limit has been reached.', 'Please sign in to continue.', 'Complete the CAPTCHA.']) {
    await test('auth or quota response is not formatting-retry permission: ' + text, async () => {
      const f = fixture({ first: answer(text) });
      await assert.rejects(f.run()); assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
    });
  }
  await test('JSON account error envelope is a terminal notice with zero correction Sends', async () => {
    const f = fixture({ first: answer(JSON.stringify({ error: 'Quota exceeded. Please sign in.' })) });
    await assert.rejects(f.run(), error => error.code === 'AI_ANALYSIS_FORMAT_REVIEW');
    assert.equal(f.dispatched, 0); assert.equal(f.calls.length, 0);
  });
  for (const text of ['ตัวละครพูดว่า เข้าสู่ระบบ', 'The character reads credits remaining on a sign.']) {
    await test('account words within malformed story JSON are content, not an account notice: ' + text, async () => {
      const value = { ...valid, caption_short: text };
      const first = answer(JSON.stringify(value).replace(/\\"/g, '"'));
      const corrected = answer('```json\n' + JSON.stringify(value) + '\n```', JSON.stringify(value));
      const f = fixture({ first, replies: [corrected] });
      assert.deepEqual(copy(await f.run()), value); assert.equal(f.dispatched, 1);
    });
  }
  await test('Gemini completed format errors retain provider and pass beyond two corrections', async () => {
    const f = fixture({ gemini: true, replies: [answer(malformedJson), answer(malformedJson), fencedAnswer()] });
    assert.deepEqual(copy(await f.run()), valid); assert.equal(f.dispatched, 3);
  });
  await test('Gemini whole capability disclaimer stays bounded to two corrections', async () => {
    const capability = answer('ฉันเป็นเพียงโมเดลภาษา');
    const f = fixture({ gemini: true, first: capability, replies: [capability, capability, fencedAnswer()] });
    await assert.rejects(f.run(), /2/); assert.equal(f.dispatched, 2);
  });
  await test('Gemini capability disclaimer with appended policy does not bypass refusal', async () => {
    const f = fixture({ gemini: true, first: answer('ฉันเป็นเพียงโมเดลภาษา This request violates policy.') });
    await assert.rejects(f.run(), /STORY_IMAGE_REFUSED/); assert.equal(f.dispatched, 0);
  });
  await test('two complete code alternatives select one original plan without another Send', async () => {
    const node = answer(malformedJson);
    node.querySelectorAll = selector => selector === 'pre'
      ? [{ textContent: validJson }, { textContent: JSON.stringify({ ...valid, video_title: 'Other plan' }) }] : [];
    const f = fixture({ first: node });
    assert.deepEqual(copy(await f.run()), valid);
    assert.equal(f.dispatched, 0);
  });
  for (const format of ['code', 'prose', 'array']) {
    await test(`analysis ${format} alternatives skip foreign and incomplete plans without merging`, async () => {
      const partial = { ...valid, scene_prompts: valid.scene_prompts.slice(0, 3) };
      const foreign = { ...valid, job_id: 'STORY-FOREIGN' };
      const values = [foreign, partial, valid, { ...valid, video_title: 'Later complete plan' }];
      const texts = values.map(value => JSON.stringify(value));
      const node = answer(format === 'array' ? JSON.stringify(values) : texts.join('\n\n'));
      if (format === 'code') node.querySelectorAll = selector => selector === 'pre'
        ? texts.map(textContent => ({ textContent })) : [];
      const f = fixture({ first: node });
      assert.deepEqual(copy(await f.run()), valid); assert.equal(f.dispatched, 0);
    });
  }
  await test('complementary incomplete alternatives are never concatenated into one plan', async () => {
    const left = { ...valid, scene_prompts: valid.scene_prompts.slice(0, 5) };
    const right = { ...valid, scene_prompts: valid.scene_prompts.slice(5) };
    const node = answer(JSON.stringify(left) + '\n' + JSON.stringify(right));
    const f = fixture({ first: node });
    assert.deepEqual(copy(await f.run()), valid); assert.equal(f.dispatched, 1);
  });
  await test('foreign-only complete analysis is review and never becomes the current job', async () => {
    const f = fixture({ first: answer(JSON.stringify({ ...valid, job_id: 'STORY-FOREIGN' })) });
    await assert.rejects(f.run(), error => error.code === 'AI_ANALYSIS_JSON_OWNER_REVIEW');
    assert.equal(f.dispatched, 0);
  });
  await test('Long chapter alternatives select the requested chapter with its complete scene count', () => {
    const first={...valid,chapter_index:1}, second={...valid,chapter_index:2};
    const f=fixture(), node=answer(JSON.stringify(first)+'\n'+JSON.stringify(second));
    const request={...pkg.request,chapter_index:2};
    const result=f.context.extractJson(node,false,false,{jobId:valid.job_id,validate:value=>
      f.context.validateAnalysis(value,'scene_prompts',10,request.required_fields,[],request)});
    assert.deepEqual(copy(result),second);
  });
  await test('valid motion and Flow repair flags are unchanged by analysis code preference', () => {
    const f = fixture(), original = { job_id: 'STORY-TEST', index: 1, context_id: 'owned',
      prompt: 'A quiet garden with a sign "Welcome".', needs_review: true,
      reference_compatible: false, material_change: true };
    const node = answer(JSON.stringify(original), JSON.stringify({ ...original, needs_review: false }));
    assert.deepEqual(copy(f.context.extractJson(node, false, true)), original);
    assert.deepEqual(copy(f.context.extractJson(node, true)), original);
  });

  console.log(JSON.stringify({ ok: failed.length === 0, checks: passed.length + failed.length,
    passed, failed, networkRequests: 0, liveStateWrites: 0 }));
  if (failed.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
