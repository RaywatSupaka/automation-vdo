const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('web_ui/app.js', 'utf8');
const start = source.indexOf('let storyRecoveryClearing =');
const end = source.indexOf('\nlet dramaQueuePending', start);
assert(start >= 0 && end > start);
const elements = Object.fromEntries(['#story-list', '#story-recovery-panel',
  '#story-recovery-count', '#story-recovery-clear', '#story-recovery-tab-count',
  '#story-new-panel', '#story-new-tab', '#story-old-tab'].map(id =>
    [id, {innerHTML: '', hidden: false, setAttribute(name, value) { this[name] = value; }}]));
const context = {
  escapeHtml: value => String(value).replaceAll('<', '&lt;'),
  $: selector => elements[selector],
  renderLongVideoRecovery: () => {},
  videoSourcePresentation: () => ({label: 'Motion ในเครื่อง'}),
  metaSequenceAction: () => '',
  storyRecoveryClearing: false,
  window: {},
};
vm.runInNewContext(source.slice(start, end) + '\nthis.render = storyRecoveryTimeline; this.renderStories = renderStories; this.setStoryView = setStoryView;', context);

const job = {scene_count: 10, image_count: 2, pipeline_stage: 'chatgpt',
  recovery: {analysis_ready: true, saved_image_scenes: [1, 2],
    failed_image_scene: 3, send_not_started: true}};
const html = context.render(job, true);
assert.match(html, /บทและรายละเอียด<\/b><span>บันทึกแล้ว/);
assert.match(html, /ฉาก 1 · บันทึกแล้ว/);
assert.match(html, /ฉาก 2 · บันทึกแล้ว/);
assert.match(html, /story-recovery-scene failed[^>]*>ฉาก 3 · หยุดที่นี่/);
assert.match(html, /ภาพฉาก 3 • ยังไม่ส่งคำขอ/);
assert.match(html, /ฉาก 4 · ยังไม่เริ่ม/);
assert.doesNotMatch(html, /ฉาก 4 · บันทึกแล้ว/);
const old = context.render({scene_count: 10, image_count: 0, pipeline_stage: 'chatgpt',
  recovery: {analysis_ready: false, saved_image_scenes: [], failed_image_scene: 0}}, true);
assert.match(old, /ขั้นเชื่อมต่อหรือสร้างบท/);
assert.doesNotMatch(old, /story-recovery-scene failed/);
context.renderStories([{...job, id: 'STORY-ONE', title: 'ตัวอย่าง', status: 'error',
  last_error: 'STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 3 • CHATGPT_IMAGE_RESULT_SEND_NOT_STARTED'}]);
assert.doesNotMatch(elements['#story-list'].innerHTML, /story-recovery-item failed/);
assert.match(elements['#story-list'].innerHTML, /รายละเอียดสำหรับทีมช่วยเหลือ/);
assert.match(elements['#story-list'].innerHTML, /ภาพฉาก 3 • ยังไม่ส่งคำขอ/);
assert.match(elements['#story-list'].innerHTML, /ภาพฉากที่บันทึกแล้ว<\/b><span>2\/10 ฉาก/);
assert.match(elements['#story-list'].innerHTML, /aria-valuenow="20"/);
assert.equal(elements['#story-recovery-tab-count'].textContent, '1');
context.setStoryView('old');
assert.equal(elements['#story-new-panel'].hidden, true);
assert.equal(elements['#story-recovery-panel'].hidden, false);
assert.equal(elements['#story-old-tab']['aria-selected'], 'true');
elements['#story-list'].scrollTop = 120;
context.renderStories(Array.from({length: 12}, (_, index) => ({...job, id: `STORY-${index}`, title: `เรื่อง ${index}`})));
assert.equal((elements['#story-list'].innerHTML.match(/role="listitem"/g) || []).length, 12);
assert.equal(elements['#story-list'].scrollTop, 120);
context.renderStories([{...job, id: 'STORY-ONE', title: 'ตัวอย่าง'}],
  {active: true, job_id: 'STORY-ONE', percent: 47});
assert.match(elements['#story-list'].innerHTML, /ความคืบหน้างานปัจจุบัน<\/b><span>47%/);
assert.match(elements['#story-list'].innerHTML, /aria-valuenow="47"/);
console.log('Story recovery timeline: saved scenes, exact failure, pending scenes and old bootstrap failure passed');
