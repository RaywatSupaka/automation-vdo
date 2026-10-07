const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const extract = (start, end) => {
  const first = source.indexOf(start), last = source.indexOf(end, first);
  assert(first >= 0 && last > first);
  return source.slice(first, last);
};
const receiptSource = extract('  function createStoryImageReceipt(', '\n  function largeAssistantImages(');
const repairSource = extract('  async function generateStoryImageWithRepair(', '\n  chrome.runtime.onMessage.addListener');
const jobId = 'STORY-PREPARED-REFERENCE';
const index = 14, identity = ['scene 14', '', '', null];
const key = `smartpostStoryGeneratedImage:chatgpt:${jobId}:${index}`;
const previousUrl = `http://127.0.0.1:8765/api/stories/${jobId}/files/generated/scene_13.png`;
const base = {version: 1, job_id: jobId, provider: 'chatgpt', scene_index: index,
  identity: JSON.stringify([identity, [], 0]), run_id: 'RUN-OLD', review_revision: 0,
  created_at: Date.now(), repair_prompt: 'repaired scene 14'};

function fixture(record = null, options = {}) {
  const store = {[key]: record && structuredClone(record)};
  if (options.dispatchClaim) store[key + ':dispatch'] = options.dispatchClaim;
  const calls = [];
  const pkg = {job: {id: jobId}, request: {}, image_urls: options.sources || [], scene_repair: {enabled: true},
    checkpoint_images: options.live || options.missing ? [] : [{index: 13, url: previousUrl}]};
  if (options.reviewed) Object.assign(pkg, {scene_prompt_overrides: {'14': 'scene 14'}, scene_prompt_override_revision: 1});
  const context = vm.createContext({
    URL, console, Number, String, Array, Date, JSON, Error, encodeURIComponent,
    PROVIDER_KEY: 'chatgpt', activeRunId: 'RUN-NEW', cancelRequested: false,
    location: {href: 'https://chatgpt.com/'},
    assertNotCancelled() {}, async report() {},
    sameStoryImageReceipt: (a, b) => JSON.stringify(a) === JSON.stringify(b),
    storyImageRecoveryError: (code, scene, message) => Object.assign(new Error(message), {code, scene}),
    stopButtonVisible: () => options.busy === true,
    chatGPTStoryRequest: () => ({frame: options.userTurn ? {} : null}),
    chrome: {storage: {local: {
      get: async name => ({[name]: store[name]}),
      set: async values => Object.assign(store, structuredClone(values))
    }}, runtime: {sendMessage: async message => {
      calls.push(['message', message.action]);
      if (message.action === 'previous_reference') return {ok: true,
        checkpoint: options.missing ? null : {index: 13, url: previousUrl}};
      if (message.action === 'status') return {ok: true, phase: 'image_pending'};
      throw Error('unexpected helper action ' + message.action);
    }}},
    async generateOneImage(...args) {
      calls.push(['generate', args]);
      await args[8].begin();
      return {src: 'new-scene-14'};
    }
  });
  vm.runInContext(receiptSource + '\n' + repairSource, context);
  const receipt = context.createStoryImageReceipt(pkg, index, identity, 13);
  return {store, calls, pkg, context, receipt, run: () => context.generateStoryImageWithRepair(pkg, {}, index,
    receipt, ['scene 14', pkg.image_urls, index, 'story', 13, '', '', null, receipt, '9:16'])};
}

(async () => {
  let cases = 0;
  for (const [name, record, options] of [
    ['new scene', null, {}],
    ['old repaired receipt', {...base, status: 'repair_ready'}, {}],
    ['not-dispatched prepared receipt', {...base, status: 'awaiting_result', send_phase: 'prepared',
      prepared_conversation: 'https://chatgpt.com/', send_nonce: 'OLD-NONCE',
      result_proof: {prompt: 'old text-only instruction'}, resume_image_prompt: 'old text-only instruction'}, {}],
    ['same-run checkpoint', {...base, status: 'repair_ready'}, {live: true}],
    ['user-reviewed prompt revision', {...base, status: 'reference_required',
      identity: JSON.stringify([['old scene', '', '', null], [], 0])}, {reviewed: true}]
  ]) {
    const f = fixture(record, options);
    await f.run();
    const args = f.calls.find(call => call[0] === 'generate')[1];
    assert.deepEqual([...args[1]], [previousUrl], name + ' attaches the saved image before Send');
    assert.equal(args[10], 'previous_scene', name);
    assert.equal(f.store[key].previous_scene_reference_index, 13, name + ' survives restart');
    assert.equal(f.store[key].resume_image_prompt, '', name + ' does not reuse the text-only wire instruction');
    assert.equal(f.calls.filter(call => call[0] === 'generate').length, 1, name);
    cases++;
  }

  for (const [name, record, options] of [
    ['claimed dispatch', {...base, status: 'awaiting_result', send_phase: 'prepared',
      prepared_conversation: 'https://chatgpt.com/', send_nonce: 'CLAIM'}, {dispatchClaim: 'CLAIM'}],
    ['busy prepared', {...base, status: 'awaiting_result', send_phase: 'prepared',
      prepared_conversation: 'https://chatgpt.com/'}, {busy: true}],
    ['user turn exists', {...base, status: 'awaiting_result', send_phase: 'prepared',
      prepared_conversation: 'https://chatgpt.com/', result_proof: {prompt: 'old instruction'}}, {userTurn: true}]
  ]) {
    const f = fixture(record, options);
    const before = JSON.stringify(f.store);
    await assert.rejects(f.run(), undefined, name);
    assert.equal(f.calls.filter(call => call[0] === 'generate').length, 0, name + ' never replays');
    assert.equal(JSON.stringify(f.store), before, name + ' keeps the prior receipt');
    cases++;
  }

  for (const [name, record, options, expected] of [
    ['explicit user source wins', null, {sources: ['http://127.0.0.1:8765/user-reference.png']},
      ['http://127.0.0.1:8765/user-reference.png']],
    ['intentional independent fallback remains text-only', {...base, status: 'repair_ready',
      standalone_scene_attempted: true}, {}, []],
    ['no saved checkpoint remains text-only', null, {missing: true}, []]
  ]) {
    const f = fixture(record, options);
    await f.run();
    const args = f.calls.find(call => call[0] === 'generate')[1];
    assert.deepEqual([...args[1]], expected, name);
    assert.equal(f.store[key].previous_scene_reference_index || 0, 0, name);
    if (!options.missing) assert.equal(f.calls.some(call => call[1] === 'previous_reference'), false, name);
    cases++;
  }

  for (const scenario of [
    {name: 'completed owned reference request', success: true},
    {name: 'still generating', busy: true},
    {name: 'no completed controls', completed: false},
    {name: 'media now present', images: [{}]},
    {name: 'ownership changed', reason: 'request_missing'},
    {name: 'response node changed', otherTurn: true},
    {name: 'explicit refusal', refusal: true}
  ]) {
    const f = fixture({...base, status: 'awaiting_result', send_phase: 'accepted',
      result_proof: {prompt: 'old text-only instruction', conversation_url: 'https://chatgpt.com/'}});
    const response = 'กรุณาแนบภาพต้นฉบับก่อนสร้างต่อ';
    const answer = {innerText: response};
    const turn = {textContent: response, querySelector: () => answer};
    const state = {reason: 'no_image', turn, images: []};
    Object.assign(f.context, {
      confirmedStoryImageServiceError: () => false,
      storyImageRefusal: () => scenario.refusal === true,
      recoverOwnedStoryImage: async () => null,
      chatGPTFrameAssistant: frame => frame.querySelector(),
      chatGPTStoryImageSnapshot: () => state,
      storyImageWaitObservation: () => ({state: {reason: scenario.reason || 'no_image',
        turn: scenario.otherTurn ? {} : turn, images: scenario.images || []},
        busy: scenario.busy === true, completedControl: scenario.completed !== false})
    });
    vm.runInContext(extract('  function storyImageReferenceRequest(', '\n  function stopButton('), f.context);
    const before = JSON.stringify(f.store);
    if (scenario.success) {
      await f.run();
      const args = f.calls.find(call => call[0] === 'generate')[1];
      assert.deepEqual([...args[1]], [previousUrl], scenario.name);
      assert.equal(args[10], 'previous_scene');
    } else {
      await assert.rejects(f.run(), undefined, scenario.name);
      assert.equal(f.calls.filter(call => call[0] === 'generate').length, 0, scenario.name);
      assert.equal(JSON.stringify(f.store), before, scenario.name + ' retains accepted request');
    }
    cases++;
  }

  // Exercise the actual caller, reference uploader and pre-Send audit together.
  // Only the provider response wait is cut off after the real Send boundary;
  // downloads, DOM and trusted browser input are deterministic test doubles.
  const integrated = fixture({...base, status: 'repair_ready'});
  const events = [];
  let uploaded = false, draft = '', snapshot;
  const preview = {tagName: 'IMG', complete: true, naturalWidth: 1000};
  const shell = {get textContent() { return uploaded ? 'smartflow-story-previous-13.png' : ''; },
    contains: node => node === preview, querySelector: () => null, querySelectorAll: () => []};
  const editor = {closest: () => shell};
  const input = {files: [], dispatchEvent: () => { uploaded = true; }};
  const resultImage = {src: 'https://chatgpt.com/backend-api/estuary/content?id=result-scene14'};
  const oldMessage = integrated.context.chrome.runtime.sendMessage;
  integrated.context.chrome.runtime.sendMessage = async message => {
    if (message.type !== 'CHATGPT_PROGRESS') return oldMessage(message);
    snapshot = message.progress.image_request;
    events.push('audit');
    assert.equal(snapshot.input_kind, 'reference_image');
    assert.equal(snapshot.source_count, 1);
    assert.equal(snapshot.source_attachment_count, 1);
    assert.match(snapshot.prompt, /ภาพฉากก่อนหน้าที่บันทึกแล้ว/);
    return {ok: true, audit_persisted: true};
  };
  Object.assign(integrated.context, {
    IS_GEMINI: false, AI_NAME: 'ChatGPT Web', activeJobId: jobId,
    activeProductOutfitMode: '', activeCoverRequest: null, activeSourceReferenceLimit: 3,
    crypto: require('node:crypto').webcrypto,
    document: {querySelectorAll: () => []}, visible: () => true,
    composer: () => editor, composerText: () => draft,
    retainedStoryReferenceReady: () => false, chatGPTComposerShell: () => shell,
    setTimeout, clearTimeout,
    waitForComposer: async () => editor, waitForResponseIdle: async () => {}, setChatGPTImageTool: async () => {}, sleep: async () => {},
    userTurns: () => [], assistantTurns: () => [], lastUserTurnSignature: () => '',
    chatGPTConversationFrames: () => [], storyTurnNumber: () => -1,
    generatedImageElements: () => [], storyImageAssetKey: () => '',
    sourceAttachmentPreviews: () => uploaded ? [preview] : [],
    chatGPTComposerAttachmentState: () => ({count: uploaded ? 1 : 0, busy: false, failed: false}),
    preferredSourceFileInput: () => input,
    sourceFile: async (url, fileIndex, strict) => {
      assert.equal(url, previousUrl);
      assert.equal(strict, 'smartflow-story-previous-13');
      events.push('reference_download');
      return {name: strict + '.png'};
    },
    waitForChatGPTSourceAttachmentProof: async expected => {
      assert.equal(expected, 1); assert.equal(input.files.length, 1); assert.equal(uploaded, true);
      events.push('reference_verified'); return {count: 1};
    },
    DataTransfer: class { constructor() { this.files = []; this.items = {add: file => this.files.push(file)}; } },
    HTMLInputElement: class {}, Event: class {},
    setComposerText: async (node, text) => { draft = text; return node; }, sendButton: () => ({}),
    aiWebFailureDiagnostic: () => JSON.stringify({source_attachment_count: uploaded ? 1 : 0,
      source_attachment_busy: false, source_attachment_failed: false, send_button_enabled: true}),
    async sendAndVerify(button, node, users, signature, assistants, ignored, story) {
      assert.equal(uploaded, true); assert(snapshot);
      events.push('send');
      await story.onDispatch(draft, {conversation_url: 'https://chatgpt.com/'});
      return {conversation_url: 'https://chatgpt.com/', request_id: 'owned-scene14'};
    },
    resultImage, imageData: async () => ({src: 'saved-new-image'})
  });
  const submitPrefix = extract('  async function submitImagePrompt(', '    const chatGPTResultProof=');
  vm.runInContext(extract('  async function attachSourceImages(', '\n  function aiWebFailureDiagnostic(')
    + '\n' + extract('  async function recordStoryImageRequest(', '\n  function geminiImageSendState(')
    + '\n' + submitPrefix + '\n    return resultImage;\n  }\n'
    + extract('  async function generateOneImage(', '\n  function productImageFailureKind('), integrated.context);
  await integrated.run();
  assert.deepEqual(events, ['reference_download', 'reference_verified', 'audit', 'send']);
  cases++;

  const blobUrl = 'blob:https://chatgpt.com/11111111-2222-3333-4444-555555555555';
  const nextBlobUrl = 'blob:https://chatgpt.com/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
  function blobFixture(record, options = {}) {
    const f = fixture(record);
    const gallery = {}, frame = {contains: node => node === gallery};
    const image = {src: options.url || blobUrl, complete: options.complete !== false,
      naturalWidth: 1024, naturalHeight: 1536,
      closest: () => options.source ? null : {closest: () => gallery}};
    const downloads = [];
    let reads = 0;
    Object.assign(f.context, {
      chatGPTConversationFrame: () => frame,
      chatGPTGeneratedGalleryFrame: value => value === frame && !options.source,
      chatGPTStoryImageSnapshot: (prompt, before, proof) => {
        assert.equal(prompt, 'owned image request');
        assert.equal(proof.prompt, 'owned image request');
        return {reason: options.wrongOwner ? 'request_missing' : 'image_ready',
          images: options.otherImage ? [{}] : [image], turn: frame};
      },
      recoverOwnedStoryImage: async () => { reads++; return options.missing ? null : image; },
      imageDataFromUrl: async (url, node) => { downloads.push({url, node}); return 'data:image/png;base64,fixture'; }
    });
    return {...f, image, downloads, reads: () => reads};
  }
  for (const options of [{}, {source: true}, {wrongOwner: true}, {otherImage: true},
    {url: 'blob:https://example.com/11111111-2222-3333-4444-555555555555'}, {complete: false}]) {
    const f = blobFixture(null, options);
    await f.receipt.restore();
    await f.receipt.begin();
    await f.receipt.submitted('owned image request', {conversation_url: 'https://chatgpt.com/'});
    const before = JSON.stringify(f.store);
    if (!Object.keys(options).length) {
      await f.receipt.generated(f.image);
      assert.equal(f.store[key].image_url, blobUrl);
    } else {
      await assert.rejects(f.receipt.generated(f.image));
      assert.equal(JSON.stringify(f.store), before, 'unowned/source/foreign/incomplete Blob is not persisted');
    }
    cases++;
  }
  const proof = {prompt: 'owned image request', conversation_url: 'https://chatgpt.com/'};
  const rotated = blobFixture({...base, status: 'generated', image_url: blobUrl, result_proof: proof}, {url: nextBlobUrl});
  assert.match(await rotated.receipt.restore(), /^data:image/);
  assert.equal(rotated.reads(), 1);
  assert.equal(rotated.store[key].image_url, nextBlobUrl);
  assert.equal(rotated.downloads[0].node, rotated.image, 'pass current decoded node for canvas fallback');
  cases++;

  const missing = blobFixture({...base, status: 'generated', image_url: blobUrl, result_proof: proof}, {missing: true});
  const beforeMissing = JSON.stringify(missing.store);
  await assert.rejects(missing.receipt.restore(), error => error.code === 'STORY_IMAGE_DOWNLOAD_PENDING');
  assert.equal(JSON.stringify(missing.store), beforeMissing);
  assert.equal(missing.downloads.length, 0);
  assert.equal(missing.calls.length, 0, 'missing saved Blob never resends');
  cases++;

  const httpsUrl = 'https://chatgpt.com/backend-api/estuary/content?id=saved';
  const https = blobFixture({...base, status: 'generated', image_url: httpsUrl});
  assert.match(await https.receipt.restore(), /^data:image/);
  assert.equal(https.reads(), 0, 'legacy saved HTTPS download unchanged');
  assert.equal(https.downloads[0].url, httpsUrl);
  cases++;
  process.stdout.write(JSON.stringify({ok: true, cases}));
})().catch(error => { console.error(error); process.exitCode = 1; });
