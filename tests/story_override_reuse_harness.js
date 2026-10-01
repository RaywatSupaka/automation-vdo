// Actual runJob and validation; browser I/O and generation are offline doubles.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing actual source ${start}`);
  return source.slice(first, last);
}
function analysis(prefix = 'Saved') {
  return {
    job_id: 'STORY-REVIEWED', video_title: 'A river story', narration_script: 'River narration',
    scene_prompts: [`${prefix} river at dawn`, `${prefix} river at sunset`],
    scene_narrations: ['Morning', 'Evening'], scene_durations: [4, 4],
    visual_bible: { light: 'natural' }, story_entities: [], scene_entities: [[], []]
  };
}
function fixture(provider = 'gemini') {
  const images = [], requests = [], messages = [], reports = [];
  let cacheReads = 0, pageImageReads = 0;
  const cached = analysis('Old cached'), fresh = analysis('Fresh analysis');
  const context = vm.createContext({
    stopButtonVisible:()=>false,
    AI_NAME: 'Offline', IS_GEMINI: provider === 'gemini', PROVIDER_KEY: provider,
    activeJobId: '', activeRunId: '', cancelRequested: false,
    location: { href: 'https://gemini.google.com/app/offline' },
    ensureAiWebModel: async () => {}, assertNotCancelled: () => {}, waitForResponseIdle: async () => {},
    report: async (...args) => reports.push(args), aiWebFailureDiagnostic: () => '',
    normaliseDialogueSpeakers: (result) => result,
    submitPrompt: async (prompt) => { requests.push(prompt); return { innerText: JSON.stringify(fresh) }; },
    extractJson: (turn) => JSON.parse(turn.innerText),
    generateOneImage: async (prompt) => { images.push(prompt); return `image-${images.length}`; },
    collectConversationImageUrls: async () => { pageImageReads++; return ['old-page-image-1', 'old-page-image-2']; },
    imageDataFromUrl: async (url) => `encoded:${url}`,
    chrome: {
      storage: { local: {
        get: async keys => { if(typeof keys === 'string' && keys.startsWith('smartpostStoryGeneratedImage:')) return {}; cacheReads++; return { [`smartpostAIAnalysis:${provider}:STORY-REVIEWED`]: cached }; },
        set: async () => {},
      } },
      runtime: { sendMessage: async (message) => { messages.push(message); return { ok: true }; } },
    },
  });
  vm.runInContext(section('  function storyContentMismatch(', '  function largeAssistantImages('), context);
  vm.runInContext(section('  function normalizeOptionalCover(', '  function visible('), context);
  vm.runInContext(section('  async function runJob(', '  chrome.runtime.onMessage.addListener('), context);
  context.storySceneContent = () => 'Current scene visual direction';
  const pkg = {
    mode: 'story', job: { id: 'STORY-REVIEWED', scene_count: 2 }, run_id: 'RUN-REVIEWED',
    prompt: 'Original story', reuse_analysis: false, image_urls: [], checkpoint_images: [],
    request: { image_count: 2, prompt_field: 'scene_prompts', story_content_contract: { version: 1 },
      required_fields: ['video_title', 'narration_script', 'scene_prompts', 'scene_narrations', 'scene_durations', 'story_entities', 'scene_entities'] },
    analysis_checkpoint: analysis(), scene_prompt_overrides: { '1': 'Reviewed river wide view' },
    scene_prompt_override_revision: 7,
  };
  pkg.analysis_checkpoint.scene_prompts[0] = pkg.scene_prompt_overrides['1'];
  return { context, pkg, images, requests, messages, reports, cached, fresh,
    cacheReads: () => cacheReads, pageImageReads: () => pageImageReads, run: () => context.runJob(pkg) };
}
const stale = (error) => error.code === 'STORY_SCENE_PROMPT_STALE'
  && error.message.startsWith('STORY_SCENE_PROMPT_STALE');

(async () => {
  let cases = 0;
  async function test(name, fn) {
    try { await fn(); cases++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; }
  }
  for (const reuse of [false, true]) {
    await test(`reviewed checkpoint wins with transport reuse=${reuse}`, async () => {
      const f = fixture(); f.pkg.reuse_analysis = reuse; await f.run();
      assert.deepEqual(f.images, ['Reviewed river wide view', 'Saved river at sunset']);
      assert.equal(f.requests.length, 0); assert.equal(f.cacheReads(), 0);
      const saved = f.messages.find((message) => message.type === 'CHECKPOINT_STORY_ANALYSIS');
      assert.equal(saved.result.scene_prompts[0], 'Reviewed river wide view');
      assert.equal(f.cached.scene_prompts[0], 'Old cached river at dawn');
    });
  }
  await test('reviewed ChatGPT prompt never harvests unindexed old page images', async () => {
    const f = fixture('chatgpt'); await f.run();
    assert.equal(f.pageImageReads(), 0); assert.equal(f.requests.length, 0);
    assert.deepEqual(f.images, ['Reviewed river wide view', 'Saved river at sunset']);
    assert.deepEqual(f.messages.filter((message) => message.type === 'CHECKPOINT_STORY_IMAGE').map((message) => message.index), [1, 2]);
  });
  await test('reviewed ChatGPT prompt retains identified persisted scene slots', async () => {
    const f = fixture('chatgpt'); f.pkg.checkpoint_images = [{ index: 2, url: 'persisted-scene-2' }];
    await f.run();
    assert.equal(f.pageImageReads(), 0); assert.equal(f.requests.length, 0);
    assert.deepEqual(f.images, ['Reviewed river wide view']);
    const submitted = f.messages.find((message) => message.type === 'SUBMIT_STORY_RESULT');
    assert.equal(submitted.result.generated_images[1], 'encoded:persisted-scene-2');
  });
  for (const [name, change] of [
    ['missing checkpoint', (p) => { delete p.analysis_checkpoint; }],
    ['wrong checkpoint job', (p) => { p.analysis_checkpoint.job_id = 'STORY-OTHER'; }],
    ['stale prompt', (p) => { p.analysis_checkpoint.scene_prompts[0] = 'Old direction'; }],
    ['missing override map', (p) => { delete p.scene_prompt_overrides; }],
    ['empty override map', (p) => { p.scene_prompt_overrides = {}; }],
    ['invalid scene index', (p) => { p.scene_prompt_overrides = { '3': 'Reviewed' }; }],
    ['invalid revision', (p) => { p.scene_prompt_override_revision = 0; }],
    ['incomplete schema', (p) => { delete p.analysis_checkpoint.video_title; }],
    ['incomplete entity metadata', (p) => { delete p.analysis_checkpoint.scene_entities; }],
  ]) {
    await test(`${name} stops before cache, repair, checkpoint or image`, async () => {
      const f = fixture(); change(f.pkg); await assert.rejects(f.run(), stale);
      assert.equal(f.cacheReads(), 0); assert.equal(f.requests.length, 0);
      assert.equal(f.images.length, 0); assert.equal(f.messages.length, 0);
      assert(f.reports.some((report) => report[0] === 'error' && report[3].error_code === 'STORY_SCENE_PROMPT_STALE'));
    });
  }
  await test('ordinary initial request still requests analysis', async () => {
    const f = fixture(); delete f.pkg.scene_prompt_overrides; delete f.pkg.scene_prompt_override_revision;
    await f.run(); assert.equal(f.requests.length, 1); assert.deepEqual(f.images, f.fresh.scene_prompts);
  });
  await test('ordinary legacy reuse without disk checkpoint still uses cache', async () => {
    const f = fixture(); delete f.pkg.scene_prompt_overrides; delete f.pkg.scene_prompt_override_revision;
    delete f.pkg.analysis_checkpoint; f.pkg.reuse_analysis = true;
    await f.run(); assert.equal(f.requests.length, 0); assert.equal(f.cacheReads(), 1);
    assert.deepEqual(f.images, f.cached.scene_prompts);
  });
  await test('ordinary reuse still prefers supplied checkpoint before cached analysis', async () => {
    const f = fixture(); delete f.pkg.scene_prompt_overrides; delete f.pkg.scene_prompt_override_revision;
    f.pkg.reuse_analysis = true; await f.run();
    assert.equal(f.requests.length, 0); assert.deepEqual(f.images, f.pkg.analysis_checkpoint.scene_prompts);
  });
  await test('ordinary ChatGPT reuse retains legacy page-image recovery', async () => {
    const f = fixture('chatgpt'); delete f.pkg.scene_prompt_overrides; delete f.pkg.scene_prompt_override_revision;
    f.pkg.reuse_analysis = true; await f.run();
    assert.equal(f.pageImageReads(), 1); assert.equal(f.images.length, 0);
    const submitted = f.messages.find((message) => message.type === 'SUBMIT_STORY_RESULT');
    assert.equal(submitted.result.generated_images[0], 'encoded:old-page-image-1');
  });
  console.log(JSON.stringify({ ok: true, cases }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
