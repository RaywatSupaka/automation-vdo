const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  async function generateStoryImageWithRepair(');
const end = source.indexOf('\n  chrome.runtime.onMessage.addListener', start);
assert(start >= 0 && end > start, 'actual Story repair source');

(async () => {
  const jobId = 'STORY-REFERENCE-TEST';
  const previousUrl = `http://127.0.0.1:8765/api/stories/${jobId}/files/generated/scene_13.png`;
  const calls = [];
  let referenceIndex = 0;
  const receipt = {
    async restore() {
      if (!referenceIndex) throw Object.assign(new Error('reference required'), {
        code: 'STORY_REFERENCE_REQUIRED', responseText: 'โปรดแนบภาพต้นฉบับก่อนสร้างต่อ'
      });
      return null;
    },
    repairPrompt: () => referenceIndex ? 'new scene' : '',
    previousSceneIndex: () => referenceIndex,
    standaloneAttempted: () => false,
    async repaired(prompt, index) { calls.push(['claim', prompt, index]); referenceIndex = index; }
  };
  const context = vm.createContext({
    URL, console, Number, String, Array, Error, encodeURIComponent,
    PROVIDER_KEY: 'chatgpt', activeRunId: 'RUN-TEST', cancelRequested: false,
    assertNotCancelled() {}, async report() {},
    sceneRepairRequest() { throw Error('must discover the saved previous scene before starting a rewrite helper'); },
    storyImageRecoveryError: (code, index, message) => Object.assign(new Error(message), {code, index}),
    async generateOneImage(...args) { calls.push(['generate', args]); return {src: 'new-image'}; },
    chrome: {runtime: {sendMessage: async () => { throw Error('unneeded helper'); }}}
  });
  vm.runInContext(source.slice(start, end), context);
  const pkg = {job: {id: jobId}, image_urls: [], checkpoint_images: [
    {index: 12, url: previousUrl.replace('scene_13', 'scene_12')},
    {index: 13, url: previousUrl}
  ]};
  const args = ['new scene', [], 14, 'story', 13, '', '', null, receipt, '9:16'];
  const image = await context.generateStoryImageWithRepair(pkg, {}, 14, receipt, args);
  assert.equal(image.src, 'new-image');
  assert.deepEqual(calls[0], ['claim', 'new scene', 13]);
  assert.equal(calls[1][0], 'generate');
  assert.deepEqual([...calls[1][1][1]], [previousUrl]);
  assert.equal(calls[1][1][10], 'previous_scene');
  assert.equal(calls.length, 2, 'one claimed request and one new image request');

  // A fresh job package has no checkpoints yet, even after scene 13 is saved
  // during the same run. Recovery must ask the desktop before skipping it.
  const currentPkg={job:{id:jobId},image_urls:[],checkpoint_images:[]};
  referenceIndex=0;calls.length=0;
  const lookups=[];
  context.chrome.runtime.sendMessage=async request=>{
    lookups.push(request.action);
    assert.equal(request.action,'previous_reference');
    return {ok:true,phase:'reference_ready',checkpoint:{index:13,url:previousUrl}};
  };
  const currentImage=await context.generateStoryImageWithRepair(currentPkg,{},14,receipt,
    ['new scene',[],14,'story',13,'','',null,receipt,'9:16']);
  assert.equal(currentImage.src,'new-image');
  assert.deepEqual(lookups,['previous_reference']);
  assert.deepEqual([...calls[1][1][1]],[previousUrl]);
  assert.equal(currentPkg.checkpoint_images[0].url,previousUrl,'retain live checkpoint for duplicate-image recovery');

  const refusedCalls = [];
  const refusedReceipt = {
    async restore() { throw Object.assign(new Error('policy refusal'), {
      code: 'STORY_SCENE_REPAIR_REQUIRED', disposition: 'refused'
    }); },
    repairPrompt: () => 'new scene', previousSceneIndex: () => 13,
    standaloneAttempted: () => false
  };
  const refusedContext = vm.createContext({
    URL, console, Number, String, Array, Error, encodeURIComponent,
    PROVIDER_KEY: 'chatgpt', activeRunId: 'RUN-TEST', cancelRequested: false,
    assertNotCancelled() {}, async report() {},
    storyImageRecoveryError: (code, index, message) => Object.assign(new Error(message), {code, index}),
    async generateOneImage(...args) { refusedCalls.push(args); return {src: 'must-not-send'}; },
    chrome: {runtime: {sendMessage: async () => { throw Error('must-not-start-helper'); }}}
  });
  vm.runInContext(source.slice(start, end), refusedContext);
  await assert.rejects(refusedContext.generateStoryImageWithRepair(pkg, {}, 14, refusedReceipt,
    ['new scene', [], 14]), /policy refusal/);
  assert.equal(refusedCalls.length, 0, 'a confirmed refusal after reference does not loop or send');

  const standaloneCalls = [];
  let standalone = false;
  const standaloneReceipt = {
    async restore() {
      if (!standalone) throw Object.assign(new Error('reference absent'), {
        code: 'STORY_REFERENCE_REQUIRED', responseText: 'ต้องแนบภาพก่อน'
      });
      return null;
    },
    repairPrompt: () => standalone ? 'independent new scene' : '',
    previousSceneIndex: () => 0,
    standaloneAttempted: () => standalone,
    async repaired(prompt, index, isStandalone) {
      standaloneCalls.push(['claim', prompt, index, isStandalone]);
      standalone = isStandalone;
    }
  };
  const standaloneContext = vm.createContext({
    URL, console, Number, String, Array, Error, encodeURIComponent,
    PROVIDER_KEY: 'chatgpt', activeRunId: 'RUN-TEST', cancelRequested: false,
    assertNotCancelled() {}, async report() {},
    sceneRepairRequest: () => 'rewrite independently',
    validateSceneRepair: candidate => candidate.prompt,
    storyImageRecoveryError: (code, index, message) => Object.assign(new Error(message), {code, index}),
    async generateOneImage(...args) { standaloneCalls.push(['generate', args]); return {src: 'new-independent-image'}; },
    chrome: {runtime: {sendMessage: async request => {
      if(request.action==='start'){
        assert.equal(request.standalone_after_reference,true,'select the dedicated confirmed-reference branch');
        return {ok: true, phase: 'ready', candidate: {prompt: 'independent new scene'}};
      }
      return {ok: true, phase: 'image_pending'};
    }}}
  });
  vm.runInContext(source.slice(start, end), standaloneContext);
  const independent = await standaloneContext.generateStoryImageWithRepair(
    {job: {id: jobId}, image_urls: [], checkpoint_images: []}, {}, 14, standaloneReceipt,
    ['old scene', [], 14, 'story', 13, '', '', null, standaloneReceipt, '9:16']);
  assert.equal(independent.src, 'new-independent-image');
  assert.deepEqual(standaloneCalls[0], ['claim', 'independent new scene', 0, true]);
  assert.deepEqual([...standaloneCalls[1][1][1]], [], 'fresh scene uses no missing reference');
  assert.equal(standaloneCalls[1][1][10], 'standalone_scene');
  assert.equal(standaloneCalls.length, 2);

  const receiptStart = source.indexOf('  function createStoryImageReceipt(');
  const receiptEnd = source.indexOf('\n  function largeAssistantImages(', receiptStart);
  assert(receiptStart >= 0 && receiptEnd > receiptStart, 'actual receipt source');
  const receiptStore = {};
  const receiptKey = `smartpostStoryGeneratedImage:chatgpt:${jobId}:14`;
  const promptIdentity = ['new scene', '', '', null];
  receiptStore[receiptKey] = {version: 1, job_id: jobId, provider: 'chatgpt', scene_index: 14,
    identity: JSON.stringify([promptIdentity, [], 0]), run_id: 'RUN-TEST', created_at: Date.now(),
    review_revision: 0, status: 'reference_required', response_excerpt: 'ต้องมีรูปอ้างอิง'};
  const receiptContext = vm.createContext({
    URL, console, Number, String, Array, Date, JSON, Error,
    PROVIDER_KEY: 'chatgpt', activeRunId: 'RUN-TEST', location: {href: 'https://chatgpt.com/'},
    assertNotCancelled() {}, sameStoryImageReceipt: (a, b) => JSON.stringify(a) === JSON.stringify(b),
    storyImageRecoveryError: (code, index, message) => Object.assign(new Error(message), {code, index}),
    chrome: {storage: {local: {
      get: async key => ({[key]: receiptStore[key]}),
      set: async values => Object.assign(receiptStore, structuredClone(values))
    }}}
  });
  vm.runInContext(source.slice(receiptStart, receiptEnd), receiptContext);
  const durable = receiptContext.createStoryImageReceipt({job: {id: jobId}, request: {}, image_urls: [],
    scene_repair: {enabled: true}}, 14, promptIdentity, 13);
  await assert.rejects(durable.restore(), /STORY_SCENE_REPAIR_REQUIRED|ตรวจและปรับพรอมต์/);
  await durable.repaired('new scene', 13);
  await durable.begin();
  assert.equal(receiptStore[receiptKey].previous_scene_reference_index, 13,
    'the accepted previous-scene reference survives a new Send claim');
  receiptStore[receiptKey] = {...receiptStore[receiptKey], status: 'reference_required',
    response_excerpt: 'อ้างอิงยังใช้ไม่ได้'};
  await assert.rejects(durable.restore(), /STORY_SCENE_REPAIR_REQUIRED|ตรวจและปรับพรอมต์/);
  await durable.repaired('independent new scene', 0, true);
  await durable.begin();
  assert.equal(receiptStore[receiptKey].standalone_scene_attempted, true,
    'a standalone branch is durable across restart and cannot repeat indefinitely');
  process.stdout.write(JSON.stringify({ok: true, cases: 15}));
})().catch(error => { console.error(error); process.exitCode = 1; });
