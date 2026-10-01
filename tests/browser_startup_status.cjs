// Execute the actual complete renderer with inert view dependencies; no network.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../web_ui/app.js'), 'utf8');
const start = source.indexOf('function renderSystem(state) {');
const end = source.indexOf('\nfunction pill(', start);
assert(start >= 0 && end > start);
const nodes = new Map();
const context = {
  $: selector => {
    if (!nodes.has(selector)) nodes.set(selector, {classList: {toggle() {}}, checked: false});
    return nodes.get(selector);
  },
  window: {}, renderCredits() {}, creditPresentation: () => ({}),
  statusCard: () => '', bindLibraryOpenControls() {},
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const state = {system: {bridge_online: true}, app: {extension_required: 'fixture'}, stats: {}, library: []};
for (const phase of ['connecting', 'needs_attention']) {
  state.system.browser_connection = {phase, message: `fixture ${phase}`};
  context.renderSystem(state);
  assert.equal(nodes.get('#side-extension').textContent, `fixture ${phase}`);
}
for (const phase of ['ready', 'skipped', '']) {
  state.system.browser_connection = {phase, message: 'stale connected message'};
  context.renderSystem(state);
  assert.match(nodes.get('#side-extension').textContent, /Extension offline/);
}
state.system.extension_online = true;
state.system.extension_compatible = true;
state.system.extension_version = 'fixture';
context.renderSystem(state);
assert.equal(nodes.get('#side-status-text').textContent, 'พร้อมทำงาน');
assert.match(nodes.get('#side-extension').textContent, /Extension vfixture/);
state.system.extension_compatible = false;
context.renderSystem(state);
assert.match(nodes.get('#side-status-text').textContent, /ไม่ตรง/);
console.log('7 startup connection UI states passed; no network or actions');
