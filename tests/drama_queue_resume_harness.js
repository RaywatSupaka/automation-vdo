const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web_ui/app.js', 'utf8');
const nodes = new Map();
const $ = id => {
  if (!nodes.has(id)) nodes.set(id, {disabled:false, textContent:'', innerHTML:'', close(){}, addEventListener(type, fn) {this[type] = fn;}});
  return nodes.get(id);
};
const calls = [], errors = [];
let release, rejectNext = false;
const state = {story_queue:{paused:true,items:[
  {mode:'story', status:'completed'}, {mode:'drama',status:'completed'},
  {mode:'drama',status:'queued'}, {mode:'drama',status:'queued'}
]}, drama_series:{items:[]}};
const context = { $, ui:{state}, toast:(message,type)=>errors.push(type),
  postAction:async action => {calls.push(action); if(rejectNext) throw Error('blocked'); await new Promise(r=>release=r);},
  poll:async()=>{}, escapeHtml:String, pill:String};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('let dramaQueuePending'), source.indexOf('function openDramaProject')), context);
vm.runInContext(source.split('\n').find(line=>line.startsWith("$('#drama-queue-toggle')?.addEventListener")), context);
(async()=>{
  $('#story-queue-toggle').disabled = true;
  context.renderDramaSeries(state.drama_series);
  assert.equal($('#drama-queue-toggle').disabled,false);
  assert.match($('#drama-queue-toggle').textContent,/2 EP/);
  const first=$('#drama-queue-toggle').click();
  await $('#drama-queue-toggle').click();
  context.renderDramaSeries(state.drama_series);
  assert.equal($('#drama-queue-toggle').disabled,true);
  assert.deepEqual(calls,['story_queue_resume']);
  release(); await first;
  assert.equal($('#drama-queue-toggle').disabled,false);
  state.story_queue.paused=false;
  const pause=$('#drama-queue-toggle').click(); release(); await pause;
  assert.equal(calls.at(-1),'story_queue_pause');
  rejectNext=true;
  await $('#drama-queue-toggle').click();
  assert.equal(errors.at(-1),'error');
  assert.equal($('#drama-queue-toggle').disabled,false);
  state.story_queue.items.forEach(row=>row.status='completed');
  context.renderDramaSeries(state.drama_series);
  assert.equal($('#drama-queue-toggle').disabled,true);
  const series={id:'SERIES-target',title:'Target',status:'queued',episode_count:2,
    episodes:[{episode_no:1,status:'completed',story_job_id:'STORY-done'}, {episode_no:2,status:'queued'}]};
  state.drama_series.items=[series]; state.story_queue.paused=true;
  context.renderDramaSeries(state.drama_series);
  assert.match($('#drama-series-list').innerHTML,/data-start-drama-series="SERIES-target"/);
  assert.match($('#drama-series-list').innerHTML,/เริ่ม EP 2/);
  assert.match($('#drama-series-list').innerHTML,/คิวกำลังพัก/);
  series.episodes[1].story_job_id='STORY-saved';
  assert.match(context.dramaQueuedAction(series),/ทำ EP 2 ต่อจากจุดเดิม/);
  assert.match(context.dramaQueuedAction(series,'STORY-live'),/disabled/);
  for(const status of ['cancelled','failed','running','completed']) {
    series.episodes[1].status=status;
    assert.equal(context.dramaQueuedAction(series),'');
  }
  series.episodes[1].status='queued';
  const start=source.indexOf("  const startDrama = event.target.closest('[data-start-drama-series]');");
  const end=source.indexOf('  const retryDrama =',start);
  vm.runInContext(`async function clickSeries(event){${source.slice(start,end)}}`,context);
  let submitted=[]; context.postAction=async(action,payload)=>{submitted.push({action,payload});await new Promise(r=>release=r);};
  const button={dataset:{startDramaSeries:series.id},disabled:false};
  const event={target:{closest:()=>button}};
  const pending=context.clickSeries(event); await context.clickSeries(event);
  assert.equal(submitted.length,1); assert.equal(submitted[0].action,'creation_start_series');
  assert.equal(submitted[0].payload.series_id,series.id);
  assert.match(context.dramaQueuedAction(series),/กำลังเริ่ม/);
  release();await pending; assert.equal(button.disabled,false);
  console.log('Drama direct resume, pause, duplicate guard, error recovery and empty queue passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
