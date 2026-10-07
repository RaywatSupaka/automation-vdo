// Actual Extension pre-send audit; no browser session or generation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const start = source.indexOf('  async function recordStoryImageRequest(');
const end = source.indexOf('  async function submitImagePrompt(', start);
assert(start >= 0 && end > start);
function fixture({ gemini = false, attachments = 0, expanded = false, ack = {ok:true}, failure = false, cancel = false } = {}) {
  const events = [], messages = [];
  const editor = { closest: () => ({querySelectorAll: () => []}) };
  const context = vm.createContext({
    IS_GEMINI: gemini, PROVIDER_KEY: gemini ? 'gemini' : 'chatgpt',
    activeJobId: 'STORY-TEST', activeRunId: 'RUN-TEST', location: {href:'https://example.invalid/test'},
    composer: () => editor, composerText: () => 'สร้างภาพใหม่ 🐈', visible: () => true,
    aiWebFailureDiagnostic: () => JSON.stringify({source_attachment_count:attachments,
      source_attachment_busy:false, source_attachment_failed:false, image_expansion_open:expanded, send_button_enabled:true}),
    assertNotCancelled: () => { if(cancel) throw Object.assign(new Error('cancelled'), {code:'CANCELLED'}); },
    setTimeout, clearTimeout,
    chrome: {runtime: {sendMessage: async message => {
      events.push('audit'); messages.push(message);
      if(failure) throw new Error('transport down');
      return ack;
    }}}
  });
  vm.runInContext(source.slice(start, end), context);
  return {events, messages, run: urls => context.recordStoryImageRequest('สร้างภาพใหม่ 🐈', urls || [], {scene_index:1,attempt:1}, 0)};
}
(async () => {
  let cases = 0;
  for(const gemini of [false,true]) for(const urls of [[],['actual-reference']]) {
    const f = fixture({gemini,attachments:urls.length}); await f.run(urls);
    const p = f.messages[0].progress;
    assert.equal(p.step,'image_prompt_ready'); assert.equal(p.image_count,0);
    assert.equal(p.image_request.prompt,p.image_request.composer_text);
    assert.equal(p.image_request.source_count,urls.length);
    assert.equal(p.image_request.input_kind,urls.length?'reference_image':'text_to_image');
    assert.equal(p.image_request.entry_mode,'not_exposed');
    assert.equal(p.image_request.attachment_scope,gemini?'page_upload_previews':'composer');
    cases++;
  }
  for(const options of [{ack:null},{ack:{ok:false}},{ack:{ok:true,ignored:true}},{failure:true}]) {
    const f = fixture(options);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_AUDIT_UNCONFIRMED'});
    assert.equal(f.messages.length,1); cases++;
  }
  for(const options of [{attachments:1},{expanded:true},{gemini:true,expanded:true}]) {
    const f = fixture(options);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_CONTEXT_CONFLICT'});
    assert.equal(f.messages.length,1,'Record conflict evidence before stopping'); cases++;
  }
  await fixture({gemini:true,attachments:3}).run(); cases++;
  await assert.rejects(fixture({cancel:true}).run(),{code:'CANCELLED'}); cases++;
  // Verify integration placement in the real sender, not a copied call sequence.
  const sender = source.slice(end, source.indexOf('    await report("waiting_for_image"',end));
  assert(sender.indexOf('await setComposerText(') < sender.indexOf('await recordStoryImageRequest('));
  assert(sender.indexOf('await recordStoryImageRequest(') < sender.indexOf('await sendAndVerify('));
  assert(sender.includes('if (button && storyContext)'));
  assert(!sender.includes('catch ('));
  cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error => { console.error(error); process.exitCode=1; });
