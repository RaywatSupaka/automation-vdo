const fs=require('fs'),assert=require('node:assert/strict');
function fixture(baseline=false){
 const proxy={...fs,readFileSync:(file,...args)=>fs.readFileSync(baseline&&String(file).replaceAll('\\','/').endsWith('browser_extension/background.js')
  ? 'deliverables/SmartFlow_AI_Extension_0.15.407/background.js':file,...args)};
 const req=name=>name==='fs'||name==='node:fs'?proxy:require(name);
 return new Function('require','__dirname',fs.readFileSync('tests/flow_home_recovery_407.cjs','utf8').split('\n(async()=>')[0]+';return paused;')(req,__dirname)();
}
async function prepare(baseline=false){
 const f=await fixture(baseline),key='smartflowFlowRepair:STORY-TEST:1',r=f.storage[key];
 f.pkg.ready_home_replacement={version:1,request_id:r.request_id,event_digest:f.permit.event_digest,
  fingerprint:r.fingerprint,source_project_path:r.manual_resume_proof.source_project_path,
  prompt:f.pkg.video_prompt,image_url:f.pkg.image_urls[0]};
 return {f,key};
}
(async()=>{
 let checks=0;
 {const {f,key}=await prepare(true);delete f.storage[key];await assert.rejects(f.start(),/ภาพใหม่หรือหลักฐาน/);checks++;}
 for(const mode of ['missing','cancelled','old-run','loopback-url','lost-proof']){
  const {f,key}=await prepare(),r=f.storage[key],count=f.calls.length;
  if(mode==='missing')delete f.storage[key];
  if(mode==='cancelled')r.phase='cancelled';
  if(mode==='old-run')r.run_id='RECOVERED-RUN';
  if(mode==='loopback-url')r.replacement.image_url='http://localhost:8765/previous-origin';
  if(mode==='lost-proof')delete r.manual_resume_proof;
  assert.equal(await f.start(),true);assert.equal(f.storage[key].phase,'ready');
  assert(!f.calls.slice(count).some(c=>c[0]==='begin'),'must not ask AI');
  assert.equal(f.calls.slice(count).filter(c=>c[0]==='create').length,1);
  assert.equal(f.tabs.get(5).url,'https://flow.google.com/project/old');
  assert(f.c.manualFlowReviewProofMatches(f.storage[key],f.storage.smartpostFlowMonitor.storyPolicyTerminal));checks++;
 }
 for(const mode of ['submitted','fresh','receipt','digest','image','prompt','candidate','source']){
  const {f,key}=await prepare(),r=f.storage[key],count=f.calls.length;
  if(mode==='submitted')r.phase='submitted';
  if(mode==='fresh')r.fresh_project={phase:'opening'};
  if(mode==='receipt')f.storage.smartpostFlowSubmissionReceipts[`STORY-TEST:1:OLD:replacement:${r.request_id}`]={requestedAt:1};
  if(['digest','image','prompt','source'].includes(mode)){
   delete f.storage[key];
   f.pkg.ready_home_replacement[{digest:'event_digest',image:'image_url',prompt:'prompt',source:'source_project_path'}[mode]]='WRONG';
  }
  if(mode==='candidate')r.candidate.prompt='different';
  await assert.rejects(f.start());assert(!f.calls.slice(count).some(c=>c[0]==='begin'));checks++;
 }
 console.log(JSON.stringify({ok:true,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
