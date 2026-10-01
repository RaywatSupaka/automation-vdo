const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'browser_extension/chatgpt.js'), 'utf8');
const sourceHash = crypto.createHash('sha256').update(source).digest('hex');
const start = source.indexOf('  async function storyNameBindingDigest(');
const end = source.indexOf('  function validateStoryNameBinding(', start);
assert(start >= 0 && end > start);
const actual = source.slice(start, end);
const helper = fs.readFileSync(path.join(root, 'browser_extension/single_answer.js'), 'utf8');
const proposal = actual;
const legacy = actual.replace('|| !draftMatches', '|| normalize(composerText(composer())) !== normalize(allowedDraft)');
let checks = 0;
const contentError = Object.assign(Error('synthetic original content mismatch'), {code: 'STORY_CONTENT_MISMATCH'});
function fixture(patched = true, gemini = false) {
  const page = {user: 'owned request', answer: 'owned completed answer', draft: '', busy: false,
    cancelled: false, attachments: {count: 0, busy: false, failed: false}};
  const cancelError = Object.assign(Error('cancelled'), {code: 'USER_CANCELLED'});
  const context = vm.createContext({crypto: crypto.webcrypto, TextEncoder, IS_GEMINI: gemini,
    location: {href: 'https://example.invalid/owned-conversation'},
    assertNotCancelled() { if (page.cancelled) throw cancelError; },
    userTurns: () => [{innerText: page.user, textContent: page.user}],
    latestAssistantStrictlyAfterLatestUser: () => ({innerText: page.answer}),
    analysisAnswerNode: value => value, analysisResponseStopButton: () => page.busy,
    chatGPTComposerAttachmentState: () => page.attachments,
    geminiComposerAttachmentState: () => page.attachments,
    composer: () => ({}), composerText: () => page.draft});
  vm.runInContext(helper, context);
  vm.runInContext(patched ? proposal : legacy, context);
  return {page, context, cancelError, call: (allowed = '', expected = null, request = '') =>
    context.storyNameBindingOwner(contentError, expected, request, allowed)};
}
async function passes(promise) { await promise; checks++; }
async function rejects(promise, expected = contentError) {
  await assert.rejects(promise, error => error === expected); checks++;
}
(async () => {
  const raw = 'Verify one missing entity.\nKeep the exact original scene.';
  for (const gemini of [false, true]) {
    const baseline = fixture(false, gemini);
    baseline.page.draft = raw;
    await passes(baseline.call(raw));
    baseline.page.draft = baseline.context.SmartFlowSingleAnswer.wrap(raw);
    await rejects(baseline.call(raw));
    const fixed = fixture(true, gemini), wrap = fixed.context.SmartFlowSingleAnswer.wrap;
    fixed.page.draft = raw; await passes(fixed.call(raw));
    fixed.page.draft = wrap(raw); await passes(fixed.call(raw));
    fixed.page.draft = wrap(raw).replace(/\s+/g, ' '); await passes(fixed.call(raw));
    for (const draft of [wrap(raw) + ' manual extra', wrap(raw + ' altered'),
      wrap(raw).replace('Return exactly one', 'Return two'),
      raw + ' [SmartFlow response format v1] fake', raw + ' manual extra',
      wrap(raw) + '\n' + fixed.context.SmartFlowSingleAnswer.instruction]) {
      fixed.page.draft = draft; await rejects(fixed.call(raw));
    }
    fixed.page.draft = ''; await passes(fixed.call(''));
    fixed.page.draft = fixed.context.SmartFlowSingleAnswer.instruction;
    await rejects(fixed.call(''));
    await rejects(fixed.call('   \n'));
    fixed.page.draft = wrap(raw);
    for (const key of ['count', 'busy', 'failed']) {
      fixed.page.attachments[key] = key === 'count' ? 1 : true;
      await rejects(fixed.call(raw));
      fixed.page.attachments[key] = key === 'count' ? 0 : false;
    }
    fixed.page.busy = true; await rejects(fixed.call(raw)); fixed.page.busy = false;
    await rejects(fixed.call(raw, {innerText: 'foreign answer'}));
    await rejects(fixed.call(raw, null, 'foreign requested text'));
    const owner = await fixed.call(raw);
    fixed.page.user = 'foreign latest user';
    assert.notEqual(await fixed.call(raw), owner); checks++;
    fixed.page.user = ''; await rejects(fixed.call(raw)); fixed.page.user = 'owned request';
    fixed.page.cancelled = true; await rejects(fixed.call(raw), fixed.cancelError);
  }
  console.log(JSON.stringify({checks, source_sha256: sourceHash, baseline: 'exact wrapped draft rejected',
    proposal: 'exact raw or owned wrapped draft accepted; empty/manual/busy/owner/cancel fences retained',
    provider_sends: 0, live_state_writes: 0, actual_source: true}));
})().catch(error => { console.error(error); process.exitCode = 1; });
