const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  function normalizeOptionalCover(');
const end = source.indexOf('\n  function visible(', start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const normalize = value => JSON.parse(JSON.stringify(context.normalizeOptionalCover(value, 3)));
for (const input of [undefined, null, [], 'bad', {}, {headline:'x'.repeat(61)}, {headline:[]}]) assert.equal(normalize(input), null);
assert.deepEqual(normalize({headline:' เปิดประตู ', alternatives:['เปิดประตู','ใครอยู่ข้างใน'], scene_index:2, emphasis:'ประตู', theme:'mystery', position:'top'}),
  {headline:'เปิดประตู', alternatives:['ใครอยู่ข้างใน'], scene_index:2, emphasis:'ประตู', theme:'mystery', position:'top'});
const bad = normalize({headline:'คำสั้น', scene_index:99, emphasis:'นอกเรื่อง', theme:{}, position:'outside'});
assert.equal(bad.scene_index, 1); assert.equal(bad.emphasis, ''); assert.equal(bad.theme, 'bold'); assert.equal(bad.position, 'bottom');
const call = source.indexOf('const optionalCover = normalizeOptionalCover(result.cover, imageCount);');
assert.ok(call < source.indexOf('type: "CHECKPOINT_STORY_ANALYSIS"', call));
assert.ok(call < source.indexOf('type: "SUBMIT_STORY_RESULT"', call));
assert.ok(!/sendMessage|submitPrompt|fetch\(/.test(source.slice(start, end)));
console.log('Cover optional metadata: 15 assertions passed; no provider calls.');
