const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const harness=fs.readFileSync('tests/flow_snapshot_harness.js','utf8');
const extract=vm.runInNewContext(harness.slice(0,harness.indexOf('class FakeElement'))+';extractFunction',{require});
const source=fs.readFileSync('browser_extension/flow.js','utf8');
(async()=>{
 let cases=0;
 for(const kind of ['continuous','legacy','cancelled','wrong-owner']){
  const timers=[];let inspections=0;
  const c=vm.createContext({
   pkg:{job_id:'STORY-X',shot_index:5,run_id:'RUN',mode:'story',flow_repair:{enabled:true,continuous:kind!=='legacy'}},
   location:{pathname:'/project/current'},Date:{now:()=>7200000},
   generationMonitorActive:false,generationMonitorTimer:null,generationMonitorEpoch:0,
   generationProgressDisappearedAt:0,generationHighestProgress:0,observedActiveGeneration:false,
   setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:()=>{},
   chrome:{storage:{local:{get:async()=>({smartpostFlowMonitor:{jobId:kind==='wrong-owner'?'OTHER':'STORY-X',
    shotIndex:5,runId:'RUN',startedAt:1,projectPath:'/project/current'}})}}},
   inspectGenerationState:async()=>{inspections++;if(kind==='cancelled')c.stopGenerationMonitor();},
   reportFlowError:async error=>{throw error;}
  });
  for(const name of ['stopGenerationMonitor','nextGenerationMonitorDelay','monitorGeneration'])
   vm.runInContext(extract(source,name),c);
  c.monitorGeneration();c.monitorGeneration();assert.equal(timers.length,1,'single flight');
  await timers.shift()();
  assert.equal(inspections,kind==='wrong-owner'?0:1);
  assert.equal(timers.length,kind==='continuous'?1:0,kind);
  assert.equal(c.generationMonitorActive,kind==='continuous',kind);cases++;
 }
 console.log(JSON.stringify({ok:true,cases,providerActions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
