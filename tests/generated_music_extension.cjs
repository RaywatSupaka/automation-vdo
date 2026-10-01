const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');
const shared = fs.readFileSync('browser_extension/single_answer.js', 'utf8');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const helper = source.slice(source.indexOf('  async function runSceneRepairHelper('),
  source.indexOf('  async function generateStoryImageWithRepair('));
const instruction = 'AI GENERATED MUSIC v1: Add subtle original instrumental background music with a warm, gentle mood. Keep dialogue clearly dominant. No singing or lyrics. Use gentle entry and exit. No generated speech; narration is added separately. [END AI GENERATED MUSIC]';
const candidate = {prompt: 'Create one 9:16 video with a gentle camera move. No background music. Spoken line: "No music, please"',
  needs_review: false, reference_compatible: true, material_change: false, change_summary: 'Simplified camera'};
const base = {scope: 'flow', provider: 'chatgpt', phase: 'rewrite_sent', job_id: 'STORY-TEST', index: 1,
  run_id: 'run-1', request_id: 'request-1', request: 'owned helper request', original_prompt: 'Original motion\n' + instruction,
  generated_music_instruction: instruction};
async function run(row, answer = candidate, stale = false) {
  let current = structuredClone(row), writes = [];
  const turn = {innerText: JSON.stringify(answer)};
  const context = vm.createContext({activeJobId: '', activeRunId: '', activeRepairKey: '', cancelRequested: false,
    stopProviderOnCancel: true, lastRepairIdentity: null, PROVIDER_KEY: 'chatgpt', IS_GEMINI: false,
    location: {href: 'https://chatgpt.com/c/owned-fixture'},
    userTurns: () => [{innerText: row.request}], stopButtonVisible: () => false,
    latestAssistantStrictlyAfterLatestUser: () => turn, sleep: async () => {}, assertNotCancelled: () => {},
    extractJson: () => structuredClone(answer), composerText: () => '',
    submitPrompt: async () => { throw Error('fixture must never send'); },
    chrome: {storage: {local: {
      get: async key => ({[key]: stale ? {...current, phase: 'submitted'} : structuredClone(current)}),
      set: async value => {current = structuredClone(value.fixture); writes.push(current);}
    }}}
  });
  vm.runInContext(shared, context); vm.runInContext(helper, context);
  context.row = structuredClone(row);
  await vm.runInContext('runSceneRepairHelper("fixture", true, row)', context);
  return {current, writes, policy: context.SmartFlowGeneratedMusic};
}
(async () => {
  const accepted = await run(base);
  assert.equal(accepted.writes.length, 1);
  assert.equal(accepted.current.phase, 'ready');
  assert.equal(accepted.current.request_id, base.request_id);
  assert.equal(accepted.current.run_id, base.run_id);
  assert.equal(accepted.current.original_prompt, base.original_prompt);
  assert.equal(accepted.current.candidate.prompt.match(/AI GENERATED MUSIC v1:/g).length, 1);
  assert.ok(accepted.current.candidate.prompt.includes('Spoken line: "No music, please"'));
  assert.ok(!accepted.current.candidate.prompt.includes('No background music.'));
  assert.equal(accepted.policy.assertCandidate(accepted.current), true);
  assert.equal(accepted.policy.finalizeCandidate(accepted.current, accepted.current.candidate).prompt,
    accepted.current.candidate.prompt);
  assert.throws(() => accepted.policy.assertCandidate({...base, candidate}), /not saved/);
  for (const phase of ['submitted', 'submit_ready', 'preparing', 'ready', 'cancelled']) {
    const saved = await run({...base, phase});
    assert.equal(saved.writes.length, 0, `must not rewrite ${phase}`);
  }
  assert.equal((await run(base, candidate, true)).writes.length, 0, 'latest receipt owns commit');
  for (const changes of [{needs_review: true}, {reference_compatible: false}, {material_change: true}]) {
    const review = await run(base, {...candidate, ...changes});
    assert.equal(review.current.candidate.prompt, candidate.prompt);
  }
  const legacy = {...base}; delete legacy.generated_music_instruction;
  for (const original of ['legacy exact prompt', 'unselected scene: No background music.']) {
    const saved = await run({...legacy, original_prompt: original});
    assert.deepEqual(saved.current.candidate, candidate);
  }
  assert.equal(accepted.policy.extract(base.original_prompt), instruction);
  assert.equal(accepted.policy.extract('AI GENERATED MUSIC v1: arbitrary text [END AI GENERATED MUSIC]'), '');
  const lower = accepted.policy.finalizeCandidate(base, {...candidate,
    prompt: 'One 9:16 video. no speech or music; narration is added separately.'});
  assert.ok(!lower.prompt.includes('no speech or music'));
  const authored = 'The product is called No Music and ships in blue. "No background music." \'No music.\'\nAction: No music, please';
  assert.ok(accepted.policy.finalizeCandidate(base, {...candidate, prompt: authored}).prompt.startsWith(authored));
  console.log('Generated music: actual owned helper commit, frozen directive, dialogue, review and receipt guards passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
