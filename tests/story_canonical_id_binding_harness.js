const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
// Scene1 is the inspected49B3FD prompt; subsequent scenes reproduce its exact
// declared-ID shape without copying the user's entire story or job state.
const scene1 = 'Vertical 9:16 aspect ratio, cinematic dark fantasy style. foreground shows a muscular woodcutter_man wearing a distinctive white mask with red markings, brown fur shoulder guard, and dark red armor, holding a large axe in a dense ancient forest. midground shows thick ferns and ancient mossy trees. background features a deep misty forest under a dim canopy. Dramatic warm rim lighting, rich color contrast, highly detailed character design, no text, no watermark.';
function analysis() {
  return { job_id: 'STORY-ID-FIXTURE', video_title: 'เรื่องคนตัดฟืน', narration_script: 'คนตัดฟืนเดินในป่า',
    story_entities: [{ id: 'woodcutter_man', name: 'ไอ่หนุ่มตัดฟืน', aliases: [], visual_identity: 'White mask with red markings, brown fur shoulder guard, dark red armor and a large axe.' }],
    scene_entities: Array.from({ length: 10 }, () => ['woodcutter_man']),
    scene_prompts: [scene1, ...Array.from({ length: 9 }, (_, index) => `Vertical 9:16. foreground ${['features', 'shows', 'displays', 'captures'][index % 4]} woodcutter_man in a dense ancient forest, holding the same large axe. Scene ${index + 2}. no text, no watermark.`)],
    scene_narrations: Array(10).fill('คนตัดฟืนเดินในป่า'), scene_durations: Array(10).fill(4),
    visual_bible: { setting: 'an ancient forest' }, pronunciation_notes: {} };
}
function fixture(input = analysis()) {
  const sends = [], reports = [], storage = {};
  const page = {user:'MASTER',answer:JSON.stringify(input),draft:''};
  const pkg = { mode: 'story', job: { id: input.job_id }, checkpoint_images: [], request: {
    story_content_contract: { version: 1 }, required_named_entities: [],
    required_fields: ['video_title', 'narration_script', 'scene_prompts', 'scene_narrations', 'scene_durations'] } };
  const c = vm.createContext({ AI_NAME: 'Offline', IS_GEMINI: true, PROVIDER_KEY:'gemini',
    activeJobId:'',activeRunId:'',location:{href:'https://gemini.google.com/app/test'},
    crypto:require('node:crypto').webcrypto,TextEncoder,
    userTurns:()=>[{innerText:page.user}],latestAssistantStrictlyAfterLatestUser:()=>({innerText:page.answer}),
    analysisAnswerNode:turn=>turn,analysisResponseStopButton:()=>false,composer:()=>({}),composerText:()=>page.draft,
    geminiComposerAttachmentState:()=>({count:0}),chatGPTComposerAttachmentState:()=>({count:0}),
    explicitAnalysisRefusal:()=>false,sleep:async()=>{},
    chrome:{storage:{local:{get:async()=>clone(storage),set:async value=>Object.assign(storage,clone(value))}}},
    normaliseDialogueSpeakers: value => value, assertNotCancelled: () => {},
    report: async (...args) => reports.push(args), extractJson: turn => JSON.parse(turn.innerText),
    submitPrompt: async(prompt,urls,strict,count,beforeSend)=>{
      page.draft=prompt;if(beforeSend)await beforeSend();sends.push(prompt);
      page.user=prompt;page.answer='{"bindings":[]}';page.draft='';return {innerText:page.answer};} });
  const start = source.indexOf('  function storyContentMismatch('), end = source.indexOf('  function largeAssistantImages(', start);
  assert(start >= 0 && end > start); vm.runInContext(source.slice(start, end), c);
  return { c, pkg, sends, reports,
    parse: () => c.parseOrRepairAnalysis({ innerText: JSON.stringify(input) }, pkg, 'scene_prompts', 10) };
}
(async () => {
  let cases = 0;
  const original = analysis(), saved = JSON.stringify(original), f = fixture(original);
  assert.throws(() => f.c.validateStoryContent(original, f.pkg.request, 10), error => error.missingNames.length === 10);
  const repaired = await f.parse(); assert.equal(f.sends.length, 0);
  assert.equal(repaired.story_content_name_repair.changes.length, 10);
  assert.equal(JSON.stringify(original), saved);
  for (const [key, value] of Object.entries(original)) if (key !== 'scene_prompts') assert.deepEqual(clone(repaired[key]), value);
  repaired.scene_prompts.forEach((prompt, index) => assert.equal(prompt, original.scene_prompts[index].replace('woodcutter_man', 'woodcutter_man (ไอ่หนุ่มตัดฟืน)')));
  assert(repaired.story_content_name_repair.changes.every(row => row.method === 'canonical_entity_id' && row.phrase === row.entity_id));
  assert(!f.reports.some(row => row[0] === 'repairing_story_names')); cases++;
  const repeat = fixture(repaired); assert.deepEqual(clone(await repeat.parse()), clone(repaired)); assert.equal(repeat.sends.length, 0); cases++;
  for (const text of [
    'A taller_woodcutter_man stands nearby.', 'woodcutter_man_extra stands nearby.',
    'woodcutter_man-child stands nearby.', 'ก่อนwoodcutter_man walks.', 'woodcutter_manก่อน walks.',
    'woodcutter_man and woodcutter_man stand nearby.',
    'No woodcutter_man in this scene.', 'Do not depict woodcutter_man in the forest.',
    'The frame excludes woodcutter_man.', 'Negative prompt: woodcutter_man.',
    'woodcutter_man is not present.', 'woodcutter_man should not appear.',
    'woodcutter_man, absent from the scene.', 'ห้ามแสดง woodcutter_man ในฉากนี้',
    'woodcutter_man ไม่ปรากฏในภาพ', 'Foreground shows woodcutter_man with unknown_person.'
  ]) {
    const input = analysis(); input.scene_prompts[0] = text; const bad = fixture(input);
    await assert.rejects(bad.parse(), { code: 'STORY_CONTENT_MISMATCH' }); assert.equal(bad.sends.length, 0); cases++;
  }
  for (const other of [
    { id: 'woodcutter-man', name: 'อีกคน', aliases: [] },
    { id: 'other_person', name: 'woodcutter man', aliases: [] },
    { id: 'other_person', name: 'อีกคน', aliases: ['woodcutter man'] },
    { id: 'other_person', name: 'ไอ่หนุ่มตัดฟืน', aliases: [] }
  ]) {
    const input = analysis(); input.story_entities.push({ ...other, visual_identity: 'A different character.' });
    const bad = fixture(input); await assert.rejects(bad.parse(), { code: 'STORY_CONTENT_MISMATCH' });
    assert.equal(bad.sends.length, 0); cases++;
  }
  for (const declared of [true, false]) {
    const input = analysis(); input.story_entities.push({ id: 'other_person', name: 'Somchai', aliases: [], visual_identity: 'Another person.' });
    input.scene_prompts[0] += declared ? ' foreground shows woodcutter_man with Somchai.' : ' other_person watches.';
    if (declared) { input.scene_prompts[0] = 'Foreground shows woodcutter_man beside Somchai.'; input.scene_entities[0].push('other_person'); }
    const bad = fixture(input); await assert.rejects(bad.parse(), { code: 'STORY_CONTENT_MISMATCH' }); assert.equal(bad.sends.length, 0); cases++;
  }
  assert.equal(f.c.storyCanonicalIdBindingPhrase(scene1, 'woodcutter_man', original.story_entities, []), null); cases++;
  for (const guard of ['reuse_analysis', 'scene_prompt_overrides', 'checkpoint_images', 'anchor']) {
    const guarded = fixture();
    if (guard === 'anchor') guarded.pkg.request.required_named_entities = ['ไอ่หนุ่มตัดฟืน'];
    else guarded.pkg[guard] = guard === 'checkpoint_images' ? [{ index: 1 }] : true;
    await assert.rejects(guarded.parse(), { code: 'STORY_CONTENT_MISMATCH' }); assert.equal(guarded.sends.length, 0); cases++;
  }
  const ordinary = analysis(); ordinary.scene_prompts[0] = ordinary.scene_prompts[0].replace('woodcutter_man', 'a masked woodcutter');
  const fallback = fixture(ordinary); await assert.rejects(fallback.parse(), { code: 'STORY_CONTENT_MISMATCH' }); assert.equal(fallback.sends.length, 3); cases++;
  const malformed = analysis(); malformed.scene_durations = []; const invalid = fixture(malformed);
  await assert.rejects(invalid.parse(), { code: 'STORY_CONTENT_MISMATCH' }); assert.equal(invalid.sends.length, 0); cases++;
  if (process.argv.includes('--emit')) console.log(JSON.stringify({ original, repaired }));
  else console.log(JSON.stringify({ ok: true, cases }));
})().catch(error => { console.error(error); process.exitCode = 1; });
