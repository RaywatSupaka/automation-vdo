// Actual worker transaction, isolated Chrome/desktop fixtures; no live sends.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {fixture}=new Function('require','__dirname',fs.readFileSync('tests/flow_fresh_start_404.js','utf8')
  .split('\n(async()=>')[0]+';return {fixture};')(require,__dirname);
const key='smartflowFlowRepair:STORY-TEST:1';
const errors=['ChatGPT Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้',
  'Gemini Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้'];
function setError(f,error){f.checkpoint.error=error;if(f.storage[key])f.storage[key].error=error;}
(async()=>{
 let cases=0;
 const old=fs.readFileSync('deliverables/SmartFlow_AI_Extension_0.15.410/background.js','utf8');
 const red=await fixture('needs_review');setError(red,errors[0]);
 vm.runInContext(old.slice(old.indexOf('function completedFlowProposalReview('),old.indexOf('function completedFlowHomeReview(')),red.c);
 assert.equal(await red.start(),false);assert.equal(red.calls.length,0);cases++;
 for(const error of errors){
  for(const state of ['missing','needs_review','cancelled','manual_restart']){
   const f=await fixture(state);setError(f,error);
   const previous=JSON.stringify(f.tabs.get(5)),receipts=JSON.stringify(f.storage.smartpostFlowSubmissionReceipts);
   assert.equal(await f.start(),true);
   assert.equal(f.storage[key].phase,'rewrite_sent');
   assert.equal(f.storage[key].alternative_json_recovery_version,1);
   assert.equal(f.calls.filter(x=>x[0]==='begin').length,1);
   assert.equal(f.calls.filter(x=>x[0]==='create').length,2);
   assert.equal(JSON.stringify(f.tabs.get(5)),previous);
   assert.equal(JSON.stringify(f.storage.smartpostFlowSubmissionReceipts),receipts);
   delete f.permit.review_checkpoint;await f.start();
   assert.equal(f.calls.filter(x=>x[0]==='create').length,2);cases++;
  }
 }
 for(const error of ['unknown Send','FLOW_ALTERNATIVE_FORMAT_OWNER_REVIEW • owner changed',
   'ChatGPT Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้ extra',
   'Login required','FLOW_REPAIR_REVIEW • timeout']){
  const f=await fixture('needs_review');setError(f,error);
  assert.equal(await f.start(),false);assert.equal(f.calls.length,0);cases++;
 }
 for(const state of ['requested','rewrite_sent','ready','submitted']){
  const f=await fixture(state);setError(f,errors[0]);await assert.rejects(f.start());assert.equal(f.calls.length,0);cases++;
 }
 for(const action of ['open_flow','resume_flow_workspace']){
  const source=fs.readFileSync('browser_extension/background.js','utf8');
  const marker=`      } else if (command.action === "${action}") {`;
  const start=source.indexOf(marker),end=source.indexOf('      } else if (command.action ===',start+marker.length);
  const f=await fixture('cancelled');setError(f,errors[0]);
  vm.runInContext(`async function execute(command){for(const one of [1]){${source.slice(start+marker.length,end)}}}`,f.c);
  await f.c.execute({...f.command,action});assert.equal(f.storage[key].phase,'rewrite_sent');
  assert(f.calls.filter(x=>x[0]==='navigate').every(x=>x[2]==='https://flow.google.com/'));cases++;
 }
 console.log(JSON.stringify({ok:true,cases,old410_reproduced:true}));
})().catch(e=>{console.error(e);process.exitCode=1;});
