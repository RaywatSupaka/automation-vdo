const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const start=source.indexOf('const finishScene=async index=>{');
const code=source.slice(start,source.indexOf('      if(pkg.job.product_story)',start));
(async()=>{
 for(const provider of ['chatgpt','gemini']){
  const states=structuredClone(rows),events=[];
  const c=vm.createContext({metaSequence:false,scenePipeline:true,pkg:{job:{id:'STORY-FIXTURE'}},
   activeRunId:'RUN-NEW',PROVIDER_KEY:provider,imageCount:3,result:{},
   assertNotCancelled:()=>{},completedImageCount:()=>1,
   prepareFlowMotionPlan:async()=>events.push('saved-motion'),
   sleep:async()=>events.push('wait'),report:async()=>{},
   chrome:{runtime:{sendMessage:async m=>{
    assert.equal(m.provider,provider);assert.equal(m.run_id,'RUN-NEW');assert.equal(m.index,1);
    events.push(m.action);return m.action==='prepare'?{ok:true}:states.shift();
   }}}});
  vm.runInContext(code+'globalThis.finish=finishScene;',c);
  await c.finish(1);events.push('next-scene');
  assert.equal(states.length,0);
  assert.deepEqual(events,['prepare','saved-motion','ready','wait','status','wait','status','wait','status','next-scene']);
 }
 console.log('Actual ChatGPT/Gemini scene gate: resumed backend states wait through complete, no old-error exit.');
})().catch(e=>{console.error(e);process.exitCode=1;});
