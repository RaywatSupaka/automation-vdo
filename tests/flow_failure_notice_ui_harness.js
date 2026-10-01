const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../web_ui/app.js'), 'utf8');
const reader = source.slice(source.indexOf('function renderAutomationError(state)'), source.indexOf('\nfunction render(state)'));
function fixture(saved = new Map()) {
  const nodes = new Map(), toasts = [];
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {open:false, showCalls:0, textContent:'', hidden:false, listeners:{},
      classList:{toggle(_name,hidden){nodes.get(id).hidden=hidden;}},
      addEventListener(name,callback){this.listeners[name]=callback;},
      showModal(){this.open=true;this.showCalls++;}, close(){this.open=false;}});
    return nodes.get(id);
  };
  const context = {ui:{progressMinimized:false}, $, toast:(...args)=>toasts.push(args),
    sessionStorage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value)}};
  vm.createContext(context); vm.runInContext(reader, context);
  return {context, $, saved, toasts};
}
const reason = 'ไม่สามารถสร้างวิดีโอที่อาจทำให้เกิดความเสี่ยงต่อชื่อเสียงหรือแสดงเหตุการณ์ปัจจุบันอย่างไม่ถูกต้อง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น';
const report = {job_id:'STORY-TEST', service:'Google Flow', kind:'warning', event_id:'owned-run-scene-card',
  title:'สร้างวิดีโอฉาก 2 ไม่สำเร็จ', message:'สาเหตุ: '+reason, text:'Exact reason: '+reason, at:'first'};
const state = value => ({automation_error_log:value});
const f = fixture();
f.context.renderAutomationError(state(report));
assert.equal(f.$('#automation-error-modal').showCalls, 1);
assert.equal(f.$('#automation-error-title').textContent, report.title);
assert.equal(f.$('#automation-error-message').textContent, report.job_id + ' • ' + report.message);
f.$('#automation-error-modal').close();
for(let i=0;i<30;i++) f.context.renderAutomationError(state({...report,at:'heartbeat'+i}));
assert.equal(f.$('#automation-error-modal').showCalls, 1);
const reload = fixture(f.saved);
reload.context.renderAutomationError(state({...report,at:'replayed'}));
assert.equal(reload.$('#automation-error-modal').showCalls, 0);
assert.equal(reload.$('#automation-error-log').textContent, report.text);
assert.equal(reload.$('#automation-error-open').hidden, false);
reload.context.ui.progressMinimized = true;
reload.context.renderAutomationError(state({...report,event_id:'next-scene',at:'next'}));
assert.equal(reload.$('#automation-error-modal').showCalls, 0);
assert.equal(reload.toasts.length, 1);
reload.context.ui.progressMinimized = false;
reload.context.renderAutomationError(state({...report,event_id:'next-scene',at:'next-new-time'}));
assert.equal(reload.$('#automation-error-modal').showCalls, 0);
reload.context.ui.state = state(report);
vm.runInContext(source.split('\n').find(line=>line.startsWith("$('#automation-error-open').")), reload.context);
reload.$('#automation-error-open').listeners.click();
assert.equal(reload.$('#automation-error-modal').showCalls, 1, 'minimized report can be opened manually from Log');
reload.$('#automation-error-modal').close();
reload.context.renderAutomationError(state({...report,event_id:'third-scene',at:'third'}));
assert.equal(reload.$('#automation-error-modal').showCalls, 2);
reload.context.renderAutomationError(state({job_id:'JOB-FAIL',message:'real terminal',text:'log',at:'failure'}));
assert.equal(reload.$('#automation-error-title').textContent, 'งานหยุดเพราะพบข้อผิดพลาด');
reload.context.renderAutomationError(state({}));
assert.equal(reload.$('#automation-error-modal').open, false);
assert.equal(reload.$('#automation-error-open').hidden, true);
const stale = fixture();
stale.context.renderAutomationError({...state(report),story_progress:{active:true,job_id:'STORY-OTHER'}});
assert.equal(stale.$('#automation-error-modal').showCalls, 0, 'other active job must not receive old popup');
stale.context.renderAutomationError(state({...report,at:'later'}));
assert.equal(stale.$('#automation-error-modal').showCalls, 0, 'old popup must not appear when newer job finishes');
stale.context.renderAutomationError(state({...report,job_id:'PRESENTER-ABCDEF123456',event_id:'presenter-card',at:'presenter'}));
assert.equal(stale.context.ui.automationErrorPage, 'presenter');
assert.equal(Array.from(f.saved.values()).some(value=>value.includes(reason)), false);
console.log('PASS: exact reason, copy log text, dismissal/30 heartbeats, reload, minimized next card, restored future card, old error and clear');
