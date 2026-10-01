// Actual Story run/receipt and background handlers; all provider/network work mocked.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const clone = value => JSON.parse(JSON.stringify(value));
function loadFixture(file, marker) {
  const text = fs.readFileSync(path.join(__dirname, file), 'utf8');
  const context = { require, __dirname };
  vm.runInNewContext(text.slice(0, text.indexOf(marker)) + '\nthis.makeFixture = fixture;', context);
  return context;
}
const base = loadFixture('story_image_receipt_harness.js', '(async()=>{');
const ownerBase = loadFixture('story_checkpoint_ownership_harness.js', '(async () => {');
function fallbackFixture(options = {}) {
  const f = base.makeFixture({ ...options, read: async url => `data:image/png;base64,${Buffer.from(url).toString('base64')}` });
  f.pkg.job.scene_count = 3;
  f.pkg.job.video_generation_mode = 'image_motion';
  f.pkg.request.image_count = 3;
  f.pkg.analysis_checkpoint.scene_prompts = ['Saved scene one', 'Scene two', 'Scene three'];
  f.pkg.analysis_checkpoint.scene_narrations = ['One', 'Two', 'Three'];
  f.pkg.analysis_checkpoint.scene_durations = [4, 4, 4];
  f.pkg.checkpoint_images = [{ index: 1, url: 'disk-scene-1' }];
  f.fallbackCalls = [];
  f.reports = [];
  f.context.report = async (...args) => f.reports.push(args);
  const oldSend = f.context.chrome.runtime.sendMessage;
  f.context.chrome.runtime.sendMessage = async message => {
    if (message.type !== 'CHECKPOINT_STORY_IMAGE_FALLBACK') return oldSend(message);
    f.fallbackCalls.push(clone(message));
    if (options.fallbackResponse) return options.fallbackResponse(message, f);
    return { ok: true, image: `data:image/png;base64,${Buffer.from('disk-scene-' + message.source_index).toString('base64')}`,
      metadata: { scene_index: message.index, source_index: message.source_index, reason: message.reason,
        policy: message.policy, status: 'ready', image_sha256: 'offline-fixture-hash' } };
  };
  f.context.submitImagePrompt = async (prompt, urls, count, empty, audit) => {
    f.sends.push({ prompt, index: audit.scene_index });
    if (options.error) throw options.error;
    if (audit.scene_index === 2 || options.refuseAll) {
      throw Object.assign(new Error('confirmed policy reply'), { code: 'CHATGPT_NO_IMAGE', responseText: 'policy refusal for this request' });
    }
    return { src: 'https://lh3.googleusercontent.com/generated-scene-' + audit.scene_index };
  };
  f.sceneKey = index => `smartpostStoryGeneratedImage:${options.provider || 'gemini'}:${f.pkg.job.id}:${index}`;
  return f;
}
(async () => {
  let cases = 0;
  const test = async (name, action) => { try { await action(); cases += 1; } catch (error) { error.message = name + ': ' + error.message; throw error; } };
  for (const provider of ['gemini', 'chatgpt']) await test('confirmed refusal reuses acknowledged donor and continues ' + provider, async () => {
    const f = fallbackFixture({ provider });
    if (provider === 'chatgpt') {
      const submit = f.context.submitImagePrompt;
      f.context.submitImagePrompt = async (...args) => {
        const value = await submit(...args);
        value.src = value.src.replace('https://lh3.googleusercontent.com/', 'https://chatgpt.com/backend-api/estuary/');
        return value;
      };
    }
    const plan = clone(f.pkg.analysis_checkpoint);
    await f.run();
    assert.deepEqual(clone(f.sends.map(item => item.index)), [2, 3]);
    assert.equal(f.fallbackCalls.length, 1);
    assert.equal(f.fallbackCalls[0].source_index, 1);
    assert.equal(f.storage[f.sceneKey(2)].status, 'refused');
    assert.equal(f.messages.filter(item => item.type === 'CHECKPOINT_STORY_IMAGE').length, 1);
    const result = f.messages.find(item => item.type === 'SUBMIT_STORY_RESULT').result;
    assert.equal(result.generated_images[1], result.generated_images[0]);
    assert.equal(result.story_image_fallbacks['2'].status, 'ready');
    for (const key of ['scene_prompts', 'scene_narrations', 'scene_durations']) assert.deepEqual(clone(result[key]), plan[key]);
    assert(f.reports.some(item => item[0] === 'submitting' && item[1].includes('สร้างสำเร็จ 2 รูป')));
  });
  const seed = fallbackFixture();
  await seed.run();
  for (const legacyExcerpt of [false, true]) await test('exact old refused receipt resumes without resending ' + legacyExcerpt, async () => {
    const storage = clone(seed.storage);
    if (legacyExcerpt) delete storage[seed.sceneKey(2)].response_excerpt;
    const before = clone(storage[seed.sceneKey(2)]);
    const f = fallbackFixture({ storage, run: 'RUN-RESUMED' });
    await f.run();
    assert.deepEqual(clone(f.sends.map(item => item.index)), [3]);
    assert.deepEqual(clone(f.storage[f.sceneKey(2)]), before);
    assert.equal(f.fallbackCalls[0].run_id, 'RUN-RESUMED');
    assert.equal(f.fallbackCalls[0].refusal_receipt.run_id, 'RUN-ONE');
  });
  await test('fallback is never a donor for later refused scene', async () => {
    const f = fallbackFixture({ refuseAll: true });
    await f.run();
    assert.deepEqual(f.fallbackCalls.map(item => item.source_index), [1, 1]);
    assert.equal(f.messages.filter(item => item.type === 'CHECKPOINT_STORY_IMAGE').length, 0);
  });
  for (const setting of [{ video_generation_mode: 'google_flow' }, { job_type: 'drama_episode' }, { video_generation_mode: undefined }]) {
    await test('excluded mode never falls back ' + JSON.stringify(setting), async () => {
      const f = fallbackFixture(); Object.assign(f.pkg.job, setting);
      await assert.rejects(f.run(), { code: 'STORY_IMAGE_REFUSED' });
      assert.equal(f.fallbackCalls.length, 0); assert.equal(f.sends.length, 1);
    });
  }
  await test('no successful prior scene remains terminal', async () => {
    const f = fallbackFixture({ refuseAll: true }); f.pkg.checkpoint_images = [];
    await assert.rejects(f.run(), { code: 'STORY_IMAGE_REFUSED' }); assert.equal(f.fallbackCalls.length, 0);
  });
  for (const code of ['AI_SEND_DISPATCHED_UNCONFIRMED', 'CHATGPT_NO_RESPONSE', 'CHATGPT_IMAGE_STALLED']) {
    await test('unknown outcome cannot become fallback ' + code, async () => {
      const f = fallbackFixture({ error: Object.assign(new Error(code), { code }) });
      await assert.rejects(f.run()); assert.equal(f.fallbackCalls.length, 0); assert.equal(f.sends.length, 1);
    });
  }
  for (const change of [{ status: 'awaiting_result' }, { identity: 'other prompt' }, { provider: 'chatgpt' },
    { review_revision: 1 }, { image_url: 'https://lh3.googleusercontent.com/already-generated' }]) {
    await test('altered refusal receipt cannot fallback ' + JSON.stringify(change), async () => {
      const storage = clone(seed.storage); Object.assign(storage[seed.sceneKey(2)], change);
      const f = fallbackFixture({ storage }); await assert.rejects(f.run(), { code: 'STORY_IMAGE_RECEIPT_REVIEW' });
      assert.equal(f.fallbackCalls.length, 0); assert.equal(f.sends.length, 0);
    });
  }
  await test('fallback ACK failure stops with refusal receipt intact', async () => {
    const f = fallbackFixture({ fallbackResponse: () => ({ ok: false, error: 'disk ACK missing' }) });
    await assert.rejects(f.run(), { code: 'STORY_IMAGE_FALLBACK_REVIEW' });
    assert.equal(f.storage[f.sceneKey(2)].status, 'refused'); assert.equal(f.sends.length, 1);
    assert(!f.messages.some(item => item.type === 'SUBMIT_STORY_RESULT'));
  });
  const metadata = clone(seed.messages.find(item => item.type === 'SUBMIT_STORY_RESULT').result.story_image_fallbacks['2']);
  await test('ready fallback restores checkpoint without retry or extra fallback request', async () => {
    const f = fallbackFixture({ storage: clone(seed.storage) });
    f.pkg.job.story_image_fallbacks = { '2': metadata };
    f.pkg.checkpoint_images.push({ index: 2, url: 'disk-scene-1' });
    await f.run(); assert.equal(f.fallbackCalls.length, 0); assert.deepEqual(clone(f.sends.map(item => item.index)), [3]);
  });
  for (const copied of [false, true]) await test('pending fallback reconciles after copy boundary ' + copied, async () => {
    const f = fallbackFixture({ storage: clone(seed.storage) });
    f.pkg.job.story_image_fallbacks = { '2': { ...metadata, status: 'pending' } };
    if (copied) f.pkg.checkpoint_images.push({ index: 2, url: 'disk-scene-1' });
    await f.run(); assert.equal(f.fallbackCalls.length, 1); assert.deepEqual(clone(f.sends.map(item => item.index)), [3]);
  });
  await test('pending fallback with lost receipt never generates replacement', async () => {
    const f = fallbackFixture(); f.pkg.job.story_image_fallbacks = { '2': { ...metadata, status: 'pending' } };
    await assert.rejects(f.run(), { code: 'STORY_IMAGE_FALLBACK_REVIEW' });
    assert.equal(f.sends.length, 0); assert.equal(f.fallbackCalls.length, 0);
  });
  for (const provider of ['gemini', 'chatgpt']) {
    const runtime = ownerBase.makeFixture(provider);
    const receipt = clone(seed.storage[seed.sceneKey(2)]);
    Object.assign(receipt, { job_id: runtime.job, provider });
    const valid = { type: 'CHECKPOINT_STORY_IMAGE_FALLBACK', job_id: runtime.job, provider, run_id: 'RUN-CURRENT',
      index: 2, source_index: 1, reason: 'STORY_IMAGE_REFUSED', policy: 'reuse_saved_local_v1', response_excerpt: 'x'.repeat(1500),
      refusal_receipt: { identity: receipt.identity, run_id: receipt.run_id, created_at: receipt.created_at, review_revision: receipt.review_revision } };
    const handler = ownerBase.handlerSource('CHECKPOINT_STORY_IMAGE_FALLBACK');
    for (const bad of [null, { run_id: 'RUN-OLD' }, { source_index: 2 }, { reason: 'UNKNOWN' }, { policy: 'unsafe' }, { receipt_status: 'awaiting_result' }, { owner: 10 }, { identity: 'other' }]) {
      await test('background verifies owner and refusal before fallback HTTP ' + provider + JSON.stringify(bad), async () => {
        const f = ownerBase.makeFixture(provider);
        f.storage[`smartpostStoryGeneratedImage:${provider}:${f.job}:2`] = { ...receipt, ...(bad?.receipt_status ? { status: bad.receipt_status } : {}) };
        // Handler uses the same ownership helper and storage fixture as existing checkpoint tests.
        const context = vm.createContext({ BRIDGE: 'http://offline.invalid', chrome: { storage: { local: { get: async () => f.storage } } },
          bridgeFetch: async (url, options) => { f.calls.push({ url, body: JSON.parse(options.body) }); return { ok: true, json: async () => ({ ok: true }) }; }, sendResponse: () => {} });
        for (const name of ['normalizeAIProvider', 'aiRunStorageKey', 'aiProgressOwnership', 'assertStoryCheckpointOwner']) vm.runInContext(ownerBase.functionSource(name), context);
        vm.runInContext(`async function dispatch(message,sender) { ${handler} }`, context);
        const message = { ...valid, ...(bad || {}) };
        if (bad?.identity) message.refusal_receipt = { ...valid.refusal_receipt, identity: bad.identity };
        const sender = { tab: { id: bad?.owner || 9, url: provider === 'gemini' ? 'https://gemini.google.com/app/owned' : 'https://chatgpt.com/c/owned' } };
        if (bad) { await assert.rejects(context.dispatch(message, sender)); assert.equal(f.calls.length, 0); }
        else { await context.dispatch(message, sender); assert.equal(f.calls.length, 1); assert.equal(f.calls[0].body.response_excerpt.length, 1200); assert(!('refusal_receipt' in f.calls[0].body)); }
      });
    }
  }
  process.stdout.write(JSON.stringify({ ok: true, cases }));
})().catch(error => { console.error(error); process.exitCode = 1; });
