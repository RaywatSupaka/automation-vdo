const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  const dismissedDiscoveryCards =');
const end = source.indexOf('  function statusBanner()', start);
assert(start > 0 && end > start);
function fixture(options = {}) {
  let clicks = 0;
  const button = {textContent: ' ไว้ทีหลัง ', disabled: false,
    getAttribute: name => name === 'aria-label' ? 'รับทราบและปิดการ์ดแสดงข้อมูล' : null,
    click: () => clicks++, ...options.button};
  const card = {textContent: 'เพิ่มประสิทธิภาพให้ Gemini ด้วย Personal Intelligence',
    querySelectorAll: () => options.buttons || [button], ...options.card};
  const context = {IS_GEMINI: true, activeJobId: 'JOB-TEST', cancelRequested: false,
    visible: node => !node.hidden, document: {querySelectorAll: selector => {
      assert.equal(selector, 'discovery-card-dialog'); return options.cards || [card];
    }}, ...options.state};
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  return {run: () => vm.runInContext('dismissGeminiDiscoveryCard()', context), clicks: () => clicks};
}
const normal = fixture(); assert.equal(normal.run(), true); assert.equal(normal.run(), false); assert.equal(normal.clicks(), 1);
for (const options of [
  {state: {IS_GEMINI: false}}, {state: {activeJobId: ''}}, {state: {cancelRequested: true}},
  {cards: []}, {card: {hidden: true}}, {card: {textContent: 'Login required'}},
  {button: {textContent: 'เริ่มกันเลย'}}, {button: {disabled: true}},
  {button: {hidden: true}}, {button: {getAttribute: () => 'true'}},
  {buttons: []}, {cards: [{}, {}]},
]) { const f = fixture(options); assert.equal(f.run(), false); assert.equal(f.clicks(), 0); }
assert(/dismissGeminiDiscoveryCard\(\);\r?\n\s+const editor = composer\(\);/.test(source));
assert(/const sleep = async \(ms\) => \{\r?\n    dismissGeminiDiscoveryCard\(\);/.test(source));
console.log('Gemini discovery: scoped Later click, once-only latch and 12 negative cases passed');
