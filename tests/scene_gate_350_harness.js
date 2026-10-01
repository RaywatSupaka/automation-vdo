const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const start=source.indexOf('      const scenePipeline=');
const code=source.slice(start,source.indexOf('      for (let index = 0; index < imageCount;',start));
(async()=>{
 for(const enabled of [true,false]){
  const events=[],states=['video','voice','complete'];
  const c=vm.createContext({mode:'story',pkg:{job:{id:'STORY-X',scene_pipeline_version:enabled?1:0,video_generation_mode:'google_flow'}},
   activeRunId:'RUN-X',IS_GEMINI:false,PROVIDER_KEY:'chatgpt',imageCount:2,completedImageCount:()=>1,result:{},assertNotCancelled:()=>{},
   sleep:async()=>events.push('wait'),report:async()=>{},prepareFlowMotionPlan:async()=>events.push('motion'),
   chrome:{runtime:{sendMessage:async m=>{assert.equal(m.index,1);assert.equal(m.run_id,'RUN-X');events.push(m.action);
    return {ok:true,phase:m.action==='prepare'?'prepared':states.shift()};}}}});
  vm.runInContext(code+'\nglobalThis.finish=finishScene;',c);
  await c.finish(1);events.push('next-image');
  assert.deepEqual(events,enabled?['prepare','motion','ready','wait','status','wait','status','next-image']:['next-image']);
 }
 console.log('350 enabled gate waits video+voice, legacy does not gate');
})().catch(e=>{console.error(e);process.exitCode=1;});
