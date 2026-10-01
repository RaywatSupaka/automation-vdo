// Actual saved desktop packages exercise unchanged Extension validation/repair.
// All provider-facing functions are inert, local capture boundaries.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
function section(start, end) {
  const a = source.indexOf(start), b = source.indexOf(end, a + start.length);
  assert(a >= 0 && b > a, 'Production function boundary missing');
  return source.slice(a, b);
}
const functions = section('  function validateStorytellingPlan(', '  function productScriptRepairInstruction(')
  + section('  function analysisJsonFormatInstruction(', '  function analysisJsonStructuralError(')
  + section('  async function validateOrRepairStoredAnalysis(', '  function storyCanonicalIdBindingPhrase(');
let checks = 0;
function check(fn) { fn(); checks++; }

(async () => {
  for (const {provider, mode, brief, package: pkg} of cases) {
    const before = JSON.stringify(pkg);
    const submitted = [];
    const context = vm.createContext({
      AI_NAME: provider,
      validateAnalysis: () => { throw Error('Synthetic missing field: formatting repair only'); },
      report: async () => {},
      productScriptRepairInstruction: () => '',
      creativeBriefRepairInstruction: () => '',
      submitPrompt: async prompt => { submitted.push(prompt); return {localFixture: true}; },
      parseOrRepairAnalysis: async (_turn, _pkg, _field, _count, prompt) => ({capturedPrompt: prompt}),
    });
    vm.runInContext(functions, context);
    const count = pkg.request.image_count;
    const groups = Array.from({length: count}, () => []);
    if (mode === 'solo') groups[0] = [{speaker: 'มะลิ', listener: '', text: 'กุญแจอยู่ตรงนี้เอง'}];
    if (mode === 'dialogue') groups[0] = [
      {speaker: 'มะลิ', listener: 'ต้น', text: 'เห็นกุญแจไหม'},
      {speaker: 'ต้น', listener: 'มะลิ', text: 'อยู่ตรงนี้ไง'},
    ];
    const result = {
      video_title: 'คืนกุญแจ', video_description: brief,
      character_bible: [{name: 'มะลิ'}, {name: 'ต้น'}],
      story_entities: [{id: 'a', name: 'มะลิ'}, {id: 'b', name: 'ต้น'}],
      scene_entities: Array.from({length: count}, () => ['a', 'b']),
      scene_narrations: Array.from({length: count}, () => 'ทั้งคู่พบกุญแจหน้าประตู'),
      scene_prompts: Array.from({length: count}, () => 'มะลิและต้นพบกุญแจหน้าประตู'),
      scene_durations: Array(count).fill(6), scene_dialogue_turns: groups,
      narration_script: mode === 'narrator' ? 'ทั้งคู่พบกุญแจหน้าประตู' : groups.flat().map(t => t.text).join(' '),
      dialogue_turns: groups.flat(),
    };
    const repair = context.storytellingRepairInstruction(pkg);
    check(() => assert(pkg.prompt.includes(JSON.stringify(brief))));
    check(() => assert(repair.includes(JSON.stringify(pkg.request.storytelling_options))));
    check(() => assert(repair.includes('CTA OFF:')));
    check(() => assert(repair.includes(mode === 'narrator' ? 'NARRATED MODE:' : 'ACTING CONTRACT:')));
    check(() => assert(repair.includes('Resolve the central conflict')));
    check(() => assert.doesNotThrow(() => context.validateStorytellingPlan(structuredClone(result), pkg.request, count)));
    const bad = structuredClone(result);
    if (mode === 'narrator') bad.narration_script = 'กดติดตามด้วย';
    else bad.scene_dialogue_turns[0] = [{speaker: 'มะลิ', listener: 'ต้น', text: 'กดติดตามด้วย'}];
    check(() => assert.throws(() => context.validateStorytellingPlan(bad, pkg.request, count), /STORYTELLING_REVIEW/));
    const response = await context.validateOrRepairStoredAnalysis(result, pkg, 'scene_prompts', count);
    check(() => assert.equal(submitted.length, 1));
    check(() => assert.equal(response.capturedPrompt, submitted[0]));
    check(() => assert(submitted[0].includes(JSON.stringify(result))));
    check(() => assert(submitted[0].includes(repair)));
    check(() => assert.equal(JSON.stringify(pkg), before));
  }
  console.log(JSON.stringify({ok: true, cases: cases.length, checks, providerRequests: 0}));
})().catch(error => { console.error(error); process.exitCode = 1; });
