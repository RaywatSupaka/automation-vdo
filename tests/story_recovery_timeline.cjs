const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('web_ui/app.js', 'utf8');
const start = source.indexOf('function storyRecoveryTimeline(');
const end = source.indexOf('\nlet dramaQueuePending', start);
assert(start >= 0 && end > start);
const elements = Object.fromEntries(['#story-list', '#story-recovery-panel',
  '#story-recovery-count', '#story-recovery-clear'].map(id => [id, {innerHTML: '', hidden: false}]));
const context = {
  escapeHtml: value => String(value).replaceAll('<', '&lt;'),
  $: selector => elements[selector],
  renderLongVideoRecovery: () => {},
  videoSourcePresentation: () => ({label: 'Motion ในเครื่อง'}),
  metaSequenceAction: () => '',
  storyRecoveryClearing: false,
  window: {},
};
vm.runInNewContext(source.slice(start, end) + '\nthis.render = storyRecoveryTimeline; this.renderStories = renderStories;', context);

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
assert.match(elements['#story-list'].innerHTML, /ดูรายละเอียดข้อผิดพลาด/);
assert.match(elements['#story-list'].innerHTML, /ภาพฉาก 3 • ยังไม่ส่งคำขอ/);
console.log('Story recovery timeline: saved scenes, exact failure, pending scenes and old bootstrap failure passed');
