const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  function skipLegacyConversationScan(');
const end = source.indexOf('\n  async function recordStoryImageRequest(', start);
assert(start > 0 && end > start, 'scan guard is present');
const context = vm.createContext({ PROVIDER_KEY: 'chatgpt' });
vm.runInContext(`${source.slice(start, end)}\nthis.check = skipLegacyConversationScan`, context);
const pkg = { mode: 'story', job: { id: 'STORY-TEST' }, first_image_pre_send: {
  version: 1, job_id: 'STORY-TEST', provider: 'chatgpt', scene_index: 1,
  source_run_id: 'RUN-OLD', trace_sequence: 29,
} };
assert.equal(context.check(pkg, 0), true);
for (const changed of [
  { mode: 'product' }, { ai_resume: { required: true } },
  { first_image_pre_send: { ...pkg.first_image_pre_send, job_id: 'STORY-OTHER' } },
  { first_image_pre_send: { ...pkg.first_image_pre_send, source_run_id: 'unknown' } },
  { first_image_pre_send: null },
]) assert.equal(context.check({ ...pkg, ...changed }, 0), false);
assert.equal(context.check(pkg, 1), false, 'a checkpoint keeps ordinary recovery');
assert(source.includes('skipLegacyConversationScan(pkg, completedImageCount())'),
  'the guard is wired to the page-wide scan');
console.log('7 pre-Send scan cases passed');
