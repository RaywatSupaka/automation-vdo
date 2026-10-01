// Actual adapter, isolated Chrome/desktop receipts. No network, provider Send or user Job writes.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const scope = {URL, Date, console};
vm.runInNewContext(source.replaceAll('export ', '') + ';this.Adapter=MetaVideoAdapter;', scope);
const KEY = 'smartflowMetaVideoRequestsV1', OWNERS = 'smartflowMetaTabOwnersV1';
const HOME = 'https://www.meta.ai/', OLD_URL = HOME + 'prompt/old-scene';
const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const command = {job_id: 'STORY-FIXTURE-454', shot_index: 4};

function fixture(options = {}) {
  const base = {job_id: command.job_id, index: 4, request_id: 'old-request', context_id: 'scene-context',
    stage: 'generating', conversation_url: OLD_URL, prompt: 'Saved scene prompt', image_name: 'scene_04.png',
    image_path: 'C:/isolated-fixture/scene_04.png', aspect_ratio: '16:9', ...options.receipt};
  let receipt = clone(base), nextTab = 50, lostFreshAck = options.lostFreshAck === true;
  const initial = {...base, tabId: 41, textIntent: true, uploadIntent: true, openIntent: true,
    sendAt: 100, ...options.row};
  const local = {[KEY]: options.noLocal ? {} : {[initial.request_id]: clone(initial)}};
  const session = {[OWNERS]: options.noOwner ? {} : {[initial.tabId]: initial.request_id}};
  const tabs = new Map(options.missing ? [] : [[41, {id: 41, url: options.url || OLD_URL, status: 'complete'}]]);
  const calls = [], effects = [], history = [], inspected = [], tabsRead = [];
  let state = {documentId: 'owned-document', documentReady: true, observedURL: OLD_URL, conversation: OLD_URL,
    matchedUser: true, userCount: 1, composerFound: true, composerCount: 1, composerText: '', imageCount: 0,
    answerText: '', answerComplete: false, answerBusy: false, busy: true, stop: true,
    pageBusy: true, pageVideoCount: 0, pageMessageCount: 1, pageDialog: false, ...options.dom};
  const api = async (route, body) => {
    if (!body) return {package: clone(receipt)};
    calls.push(clone(body));
    if (body.stage === 'fresh_start') {
      if (Object.prototype.hasOwnProperty.call(options, 'freshAck')) return {receipt: clone(options.freshAck)};
      if (body.request_id !== receipt.request_id) {
        assert.equal(receipt.retry_previous_request_id, body.request_id, 'only the linked predecessor is idempotent');
        return {receipt: clone(receipt)};
      }
      assert.equal(body.context_id, receipt.context_id);
      const proof = body.fresh_start_evidence;
      assert(proof && ['tab_missing', 'tab_not_owned', 'tab_left_meta'].includes(proof.reason));
      assert(Number.isInteger(proof.tab_id) && proof.tab_id >= -1);
      assert.equal(typeof proof.tab_missing, 'boolean');
      assert.equal(typeof proof.session_owned, 'boolean');
      history.push(clone(receipt));
      receipt = {...base, request_id: 'fresh-request-' + history.length, stage: 'prepared',
        retry_previous_request_id: receipt.request_id, fresh_start_reason: proof.reason,
        fresh_start_not_before: Date.now() / 1000 + (options.successorDelay || 0)};
      delete receipt.conversation_url;
      delete receipt.download_id;
      if (lostFreshAck) { lostFreshAck = false; throw Object.assign(Error('lost fresh ACK'), {metaBridge: true}); }
      return {receipt: clone(receipt)};
    }
    assert.equal(body.request_id, receipt.request_id, 'a retired callback may not mutate the successor');
    assert.equal(body.context_id, receipt.context_id);
    receipt = {...receipt, ...body};
    return {receipt: clone(receipt)};
  };
  const chrome = {runtime: {id: 'isolated-extension'}, storage: {
    local: {get: async () => clone(local), set: async value => Object.assign(local, clone(value))},
    session: {get: async () => clone(session), set: async value => Object.assign(session, clone(value))}},
    tabs: {get: async id => { tabsRead.push(id); if (!tabs.has(id)) throw Error('No tab with id: ' + id); return clone(tabs.get(id)); },
      create: async args => { effects.push({type: 'create', ...clone(args)}); const tab = {id: nextTab++, url: args.url, status: 'complete'}; tabs.set(tab.id, tab); return clone(tab); },
      update: async (id, args) => { effects.push({type: 'update', id, ...clone(args)}); Object.assign(tabs.get(id), args); return clone(tabs.get(id)); },
      remove: async id => { effects.push({type: 'remove', id}); tabs.delete(id); }},
    downloads: {download: async () => { throw Error('must not start another download'); },
      search: async query => { effects.push({type: 'download-read', ...clone(query)}); return clone(options.downloads || []); }}};
  const make = () => { const adapter = new scope.Adapter({api, chromeAPI: chrome});
    adapter.inspect = async row => { inspected.push(row.request_id); return clone(state); };
    adapter.click = async () => { throw Error('must not click/Send in a recovery fixture'); };
    adapter.debug = async () => { throw Error('must not type/upload/Send in a recovery fixture'); };
    return adapter; };
  const adapter = make();
  return {adapter, make, row: initial, calls, effects, history, inspected, tabsRead, tabs, local, session,
    receipt: () => clone(receipt), setReceipt: patch => { receipt = {...receipt, ...clone(patch)}; },
    setDOM: patch => { state = {...state, ...clone(patch)}; },
    freshCalls: () => calls.filter(call => call.stage === 'fresh_start'),
    creates: () => effects.filter(effect => effect.type === 'create')};
}

function verifyFresh(c, reason) {
  assert.equal(c.history.length, 1, 'one durable successor');
  assert.equal(c.receipt().fresh_start_reason, reason);
  assert.equal(c.receipt().stage, 'prepared');
  assert.equal(c.receipt().context_id, 'scene-context');
  assert.equal(c.receipt().prompt, 'Saved scene prompt');
  assert.equal(c.receipt().image_path, 'C:/isolated-fixture/scene_04.png');
  assert.equal(c.receipt().aspect_ratio, '16:9');
  assert.equal(c.creates().length, 1, 'one replacement tab');
  assert.equal(c.creates()[0].url, HOME, 'only clean Meta Home is a recovery destination');
  assert(!c.effects.some(effect => effect.type === 'update' || effect.type === 'remove'), 'preserve former/user tabs');
  const saved = c.local[KEY][c.receipt().request_id];
  assert(saved && !saved.conversation_url);
  for (const stale of ['textIntent', 'uploadIntent', 'sendAt', 'send_diagnostic', 'download_id'])
    assert(!saved[stale], 'new request must not inherit ' + stale);
  assert.equal(c.local[KEY]['old-request'].closed, true, 'predecessor is retired');
}

const cases = [];
function test(name, run) { cases.push({name, run}); }

test('fresh prepared package opens Home without a retry', async () => {
  const c = fixture({noLocal: true, noOwner: true, missing: true,
    receipt: {stage: 'prepared', conversation_url: undefined}});
  await c.adapter.open(command);
  assert.equal(c.creates().length, 1); assert.equal(c.creates()[0].url, HOME);
  assert.equal(c.freshCalls().length, 0);
});
for (const stage of ['send_intent', 'submitted', 'generating']) {
  test('missing owned tab at ' + stage + ' creates exact clean successor', async () => {
    const c = fixture({missing: true, receipt: {stage}});
    await c.adapter.step(c.row); verifyFresh(c, 'tab_missing');
    assert.equal(c.freshCalls()[0].fresh_start_evidence.tab_missing, true);
    assert.equal(c.freshCalls()[0].fresh_start_evidence.session_owned, true);
  });
}
test('Chrome session loss does not adopt or touch a recycled existing tab', async () => {
  const c = fixture({noOwner: true});
  await c.adapter.step(c.row); verifyFresh(c, 'tab_not_owned');
  assert.equal(c.freshCalls()[0].fresh_start_evidence.session_owned, false);
  assert(c.tabs.has(41)); assert(!c.inspected.includes('old-request'));
});
test('owned tab moved away from Meta creates new Home without navigation', async () => {
  const c = fixture({url: 'https://example.invalid/user-page'});
  await c.adapter.step(c.row); verifyFresh(c, 'tab_left_meta');
  assert.equal(c.tabs.get(41).url, 'https://example.invalid/user-page');
});
test('open never restores a saved conversation when its tab is missing', async () => {
  const c = fixture({missing: true});
  await c.adapter.open(command); verifyFresh(c, 'tab_missing');
});
test('stale open intent without a bound tab is recoverable', async () => {
  const c = fixture({noOwner: true, missing: true, receipt: {stage: 'prepared', conversation_url: undefined},
    row: {tabId: undefined, openIntent: true}});
  await c.adapter.open(command);
  assert.equal(c.history.length, 1); assert.equal(c.creates().length, 1);
  assert.equal(c.creates()[0].url, HOME); assert.equal(c.receipt().stage, 'prepared');
});
test('concurrent opens share the same replacement request and tab', async () => {
  const c = fixture({missing: true});
  await Promise.all([c.adapter.open(command), c.adapter.open(command), c.adapter.open(command)]);
  verifyFresh(c, 'tab_missing');
});
test('lost durable successor ACK resumes that successor after worker restart', async () => {
  const c = fixture({missing: true, lostFreshAck: true});
  try { await c.adapter.step(c.row); } catch (error) { assert.match(error.message, /lost fresh ACK/); }
  assert.equal(c.history.length, 1);
  const restarted = c.make();
  await restarted.step(c.row);
  await restarted.step(c.row);
  verifyFresh(c, 'tab_missing');
});
test('late old worker callback adopts current successor without a new tab', async () => {
  const c = fixture({missing: true});
  const stale = clone(c.row);
  await c.adapter.step(c.row); verifyFresh(c, 'tab_missing');
  await c.adapter.step(stale);
  assert.equal(c.history.length, 1); assert.equal(c.creates().length, 1);
  assert.equal(c.local[KEY][c.receipt().request_id].stage, 'prepared');
});
test('durable cooldown survives restart and tick opens the saved successor once', async () => {
  const c = fixture({missing: true, successorDelay: 30});
  await c.adapter.step(c.row);
  assert.equal(c.history.length, 1); assert.equal(c.creates().length, 0);
  assert.equal(c.local[KEY]['old-request'].closed, true);
  assert.equal(c.local[KEY][c.receipt().request_id].stage, 'prepared');
  const restarted = c.make();
  await restarted.tick(); assert.equal(c.creates().length, 0);
  c.setReceipt({fresh_start_not_before: 0});
  await restarted.tick();
  verifyFresh(c, 'tab_missing');
});
for (const [label, receipt] of [
  ['missing-receipt', undefined],
  ['wrong-context', {request_id: 'new-request', context_id: 'foreign', retry_previous_request_id: 'old-request', stage: 'prepared'}],
  ['wrong-predecessor', {request_id: 'new-request', context_id: 'scene-context', retry_previous_request_id: 'foreign', stage: 'prepared'}],
  ['same-current-active', {request_id: 'old-request', context_id: 'scene-context', stage: 'generating'}],
  ['same-current-prepared-expired', {request_id: 'old-request', context_id: 'scene-context', stage: 'prepared', fresh_start_not_before: 0}],
  ['same-current-active-future', {request_id: 'old-request', context_id: 'scene-context', stage: 'generating', fresh_start_not_before: Date.now() / 1000 + 30}],
]) {
  test('invalid fresh-start ACK ' + label + ' cannot retire the current worker', async () => {
    const c = fixture({missing: true, freshAck: receipt});
    await assert.rejects(() => c.adapter.freshStart(c.row, {
      reason: 'tab_missing', tab_id: 41, tab_missing: true, session_owned: true}), /acknowledgement/);
    assert(!c.local[KEY]['old-request'].closed); assert.equal(c.creates().length, 0);
    assert.equal(c.history.length, 0);
  });
}
test('same-current prepared future-cooldown ACK remains a saved current worker', async () => {
  const ack = {request_id: 'old-request', context_id: 'scene-context', stage: 'prepared',
    fresh_start_not_before: Date.now() / 1000 + 30};
  const c = fixture({missing: true, receipt: {stage: 'prepared'}, freshAck: ack});
  const returned = await c.adapter.freshStart(c.row, {
    reason: 'tab_missing', tab_id: 41, tab_missing: true, session_owned: true});
  assert.equal(returned.request_id, 'old-request'); assert.equal(returned.stage, 'prepared');
  assert(!c.local[KEY]['old-request'].closed); assert.equal(c.history.length, 0); assert.equal(c.creates().length, 0);
});
test('desktop needs-attention receipt remains passive despite stale active local stage', async () => {
  const c = fixture({missing: true}); c.setReceipt({stage: 'needs_attention'});
  await c.adapter.step(c.row);
  assert.equal(c.calls.length, 0); assert.equal(c.effects.length, 0);
});
test('an owned live busy generation is observed without new request', async () => {
  const c = fixture(); await c.adapter.step(c.row);
  assert.equal(c.freshCalls().length, 0); assert.equal(c.effects.length, 0);
  assert.equal(c.receipt().stage, 'generating');
});
test('stored clip remains stored after its tab disappears', async () => {
  const c = fixture({missing: true, receipt: {stage: 'stored'}});
  await c.adapter.step(c.row);
  assert.equal(c.receipt().stage, 'stored'); assert.equal(c.freshCalls().length, 0);
  assert.equal(c.creates().length, 0); assert.equal(c.local[KEY]['old-request'].closed, true);
});
for (const stage of ['download_intent', 'downloading']) {
  test('completed ' + stage + ' reconciles before requiring a browser tab', async () => {
    const name = 'SmartFlow/Meta/' + command.job_id + '/scene-4-old-request.mp4';
    const c = fixture({missing: true, noOwner: true, receipt: {stage, ...(stage === 'downloading' ? {download_id: 81} : {})},
      row: {downloadName: name}, downloads: [{id: 81, state: 'complete', filename: 'C:/Downloads/' + name,
        exists: true, byExtensionId: 'isolated-extension'}]});
    await c.adapter.step(c.row);
    if (stage === 'download_intent') await c.adapter.step(c.row);
    assert.equal(c.receipt().stage, 'stored'); assert.equal(c.freshCalls().length, 0);
    assert.equal(c.creates().length, 0); assert.equal(c.inspected.length, 0);
  });
}
test('lost download ACK can derive its exact filename without old local flags', async () => {
  const name = 'SmartFlow/Meta/' + command.job_id + '/scene-4-old-request.mp4';
  const c = fixture({missing: true, noOwner: true, receipt: {stage: 'download_intent'},
    downloads: [{id: 81, state: 'complete', filename: 'C:/Downloads/' + name,
      exists: true, byExtensionId: 'isolated-extension'}]});
  await c.adapter.step(c.row); await c.adapter.step(c.row);
  assert.equal(c.receipt().stage, 'stored'); assert.equal(c.freshCalls().length, 0);
  assert.equal(c.creates().length, 0);
});
for (const blocker of ['foreign-extension', 'duplicate-matches', 'no-match']) {
  test('unresolved download ' + blocker + ' preserves its receipt without fresh generation', async () => {
    const name = 'SmartFlow/Meta/' + command.job_id + '/scene-4-old-request.mp4';
    const item = {id: 81, state: 'complete', filename: 'C:/Downloads/' + name,
      exists: true, byExtensionId: 'isolated-extension'};
    const downloads = blocker === 'foreign-extension' ? [{...item, byExtensionId: 'other-extension'}]
      : blocker === 'duplicate-matches' ? [item, {...item, id: 82}] : [];
    const c = fixture({missing: true, noOwner: true, receipt: {stage: 'download_intent'}, downloads});
    await c.adapter.step(c.row);
    assert.equal(c.receipt().stage, 'needs_attention'); assert.equal(c.freshCalls().length, 0);
    assert.equal(c.receipt().request_id, 'old-request'); assert.equal(c.creates().length, 0);
  });
}

(async () => {
  let failures = 0;
  for (const entry of cases) {
    try { await entry.run(); process.stdout.write('PASS ' + entry.name + '\n'); }
    catch (error) { failures++; process.stderr.write('FAIL ' + entry.name + ': ' + error.stack + '\n'); }
  }
  process.stdout.write(`Meta tab recovery454: ${cases.length - failures}/${cases.length} isolated production-adapter scenarios passed; no live actions\n`);
  if (failures) process.exitCode = 1;
})();
