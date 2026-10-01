// Read-only fixture: ambiguous legacy receipts lack a stable tile identity.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/flow.js'), 'utf8');
const hash = value => { let n=2166136261; for(const c of value){n^=c.charCodeAt(0);n=Math.imul(n,16777619);} return (n>>>0).toString(16); };
async function probe(count) {
  const text='ล้มเหลว ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้';
  let attached=false, clicks=0;
  const buttons=['ลองอีกครั้ง','ใช้พรอมต์ซ้ำ','ลบ'].map(label=>({disabled:false,innerText:'',textContent:'',
    getAttribute:name=>name==='aria-label'?label:'',click:()=>{attached=true;clicks++;}}));
  const cards=Array.from({length:count},()=>({innerText:text,querySelectorAll:()=>buttons}));
  const fingerprint=hash(`${text}|${buttons.map(b=>b.getAttribute('aria-label')).join(' | ')}`);
  const messages=[], reports=[], editor={value:''};
  let record={phase:'ready',request_id:'fixture',round:2,original_prompt:'original',candidate:{
    prompt:'Vertical 9:16, one video. A worker calmly arranges keys on a workbench. Slow camera push-in.',
    needs_review:false,reference_compatible:true,material_change:false}};
  const context=vm.createContext({automationPaused:false,readOnlyInspection:false,inspectionCommandId:'',Date,
    pkg:{job_id:'STORY-FIXTURE',shot_index:1,run_id:'RUN-FIXTURE',flow_repair:{enabled:true},video_prompt:'original'},
    location:{pathname:'/project/fixture'},document:{querySelectorAll:()=>cards},visible:()=>true,
    findPromptEditor:()=>editor,promptHasAttachedMedia:()=>attached,findGenerateButton:()=>({}),
    fillPrompt:async()=>{editor.value=context.pkg.video_prompt;return true;},generationSnapshot:()=>({videoCount:0}),
    setTimeout:fn=>fn(),stopGenerationMonitor:()=>{},report:async(...args)=>reports.push(args),
    chrome:{storage:{local:{set:async()=>{}}},runtime:{sendMessage:async message=>{
      messages.push(message);
      if(message.type==='IS_ACTIVE_FLOW_TAB')return {active:true};
      if(message.type==='CLICK_FLOW_GENERATE')return {ok:true};
      if(message.action!=='status')record={...record,phase:message.action,pause_reason:message.pause_reason};
      return {ok:true,...record};
    }}}
  });
  vm.runInContext(source.slice(source.indexOf('  let flowRepairBusy ='),source.indexOf('  async function readGenerationState()')),context);
  await context.recoverFlowPolicy({repair_eligible:true,failure_card_fingerprint:fingerprint,failure_reason:'fixture failure'}, {startedAt:1});
  return {cards:count,restore_clicks:clicks,generate_requests:messages.filter(m=>m.type==='CLICK_FLOW_GENERATE').length,
    pause_reason:record.pause_reason || '',reports:reports.map(row=>row[0])};
}
(async()=>{
  const single=await probe(1), duplicates=await probe(2), four=await probe(4);
  assert.equal(single.generate_requests,1);
  assert.equal(duplicates.generate_requests,0);assert.match(duplicates.pause_reason,/หลายการ์ด/);
  assert.equal(four.generate_requests,0);assert.match(four.pause_reason,/หลายการ์ด/);
  console.log(JSON.stringify({kind:'legacy_ambiguous_receipt_guard',note:'New identified-card and fresh-project paths are covered by flow_prompt_repair_harness.js.',results:[single,duplicates,four]},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
