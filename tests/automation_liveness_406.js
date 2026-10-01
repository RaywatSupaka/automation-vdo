// Actual-source fault injection. No browser, credentials, customer jobs or provider calls.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const flow = fs.readFileSync('browser_extension/flow.js', 'utf8');
const background = fs.readFileSync('browser_extension/background.js', 'utf8');
const section = (source, start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => {resolve=a;reject=b;}); return {promise,resolve,reject}; };
let cases = 0;
async function test(name, run) {
  if (process.argv[2] && !name.includes(process.argv[2])) return;
  await run(); cases++; console.log(`PASS ${name}`);
}
function monitorFixture() {
  const timers = new Map(); let sequence=0, reads=0, inspections=0, reports=0;
  const monitor = {jobId:'STORY-FIXTURE',shotIndex:9,runId:'RUN',startedAt:1,projectPath:'/project/new'};
  const c = vm.createContext({
    pkg:{job_id:monitor.jobId,shot_index:9,run_id:'RUN',mode:'story',flow_repair:{enabled:true,continuous:true}},
    location:{pathname:monitor.projectPath},Date:{now:()=>100000},
    generationMonitorActive:false,generationMonitorTimer:null,generationMonitorEpoch:0,
    generationProgressDisappearedAt:0,generationHighestProgress:0,observedActiveGeneration:false,
    setTimeout:fn=>{timers.set(++sequence,fn);return sequence;},clearTimeout:id=>timers.delete(id),
    chrome:{storage:{local:{get:async()=>{reads++;return {smartpostFlowMonitor:{...monitor}};}}}},
    inspectGenerationState:async()=>{inspections++;},reportFlowError:async()=>{reports++;}
  });
  vm.runInContext(section(flow,'  function stopGenerationMonitor()','  async function inspectGenerationState()'),c);
  return {c,timers,monitor,counts:()=>({reads,inspections,reports}),async run(){
    const [id,fn]=timers.entries().next().value;timers.delete(id);await fn();
  }};
}
function outboxFixture() {
  const store={},sent=[];
  const c=vm.createContext({Map,Object,Promise,JSON,AbortController,setTimeout,clearTimeout,BRIDGE:'http://fixture',
    chrome:{storage:{local:{get:async key=>key===null?{...store}:{[key]:store[key]},
      set:async values=>Object.assign(store,values),remove:async key=>{delete store[key];}}}},
    bridgeFetch:async(_url,options)=>{sent.push(JSON.parse(options.body));return {ok:true,json:async()=>({ok:true})};},
    aiProgressOwnership:async()=>({active:true}),flowProgressOwnership:async()=>({active:true})});
  vm.runInContext(section(background,'const progressOutboxLocks=','function scheduleFastCommandHandoff'),c);
  const body=index=>({scope:'flow',job_id:`STORY-${index}`,run_id:'RUN',tab_id:index,shot_index:9,observed_at_ms:100});
  const key=b=>`smartflowProgressOutbox:${b.scope}:${b.job_id}:${b.run_id}:${b.tab_id}`;
  const queue=index=>{const b=body(index);store[key(b)]=b;return b;};
  return {c,store,sent,body,key,queue,keys:()=>Object.keys(store).filter(k=>k.startsWith('smartflowProgressOutbox:'))};
}
function imageWaitFixture() {
  const harness=fs.readFileSync('tests/story_image_wait_342_harness.js','utf8');
  return vm.runInNewContext(harness.slice(0,harness.indexOf('(async()=>{'))+';fixture',{require})();
}
(async()=>{
  await test('monitor storage outage rearms without reporting provider failure',async()=>{
    const f=monitorFixture();const get=f.c.chrome.storage.local.get;let fail=true;
    f.c.chrome.storage.local.get=async key=>{if(fail){fail=false;throw Error('temporary storage unavailable');}return get(key);};
    f.c.monitorGeneration();await f.run();assert.equal(f.timers.size,1);
    assert.equal(f.counts().reports,0);await f.run();assert.equal(f.counts().inspections,1);
  });
  await test('monitor delayed storage result cannot stop or inspect replacement owner',async()=>{
    const f=monitorFixture(),pending=deferred();const get=f.c.chrome.storage.local.get;
    f.c.chrome.storage.local.get=()=>pending.promise;
    f.c.monitorGeneration();const old=f.run();await tick();
    f.c.stopGenerationMonitor();f.c.pkg={...f.c.pkg,run_id:'RUN-NEW'};
    f.c.chrome.storage.local.get=get;f.c.monitorGeneration();
    pending.resolve({smartpostFlowMonitor:{...f.monitor}});await old;
    assert.equal(f.c.generationMonitorActive,true);assert.equal(f.timers.size,1);assert.equal(f.counts().inspections,0);
  });
  await test('monitor old inspection completion cannot arm a second timer',async()=>{
    const f=monitorFixture(),pending=deferred();f.c.inspectGenerationState=()=>pending.promise;
    f.c.monitorGeneration();const old=f.run();await tick();
    f.c.stopGenerationMonitor();f.c.monitorGeneration();pending.resolve();await old;
    assert.equal(f.timers.size,1);
  });
  await test('monitor failed error reporting still rearms and respects stop',async()=>{
    const f=monitorFixture();f.c.inspectGenerationState=async()=>{throw Error('DOM read failed');};
    f.c.reportFlowError=async()=>{throw Error('bridge temporarily unavailable');};
    f.c.monitorGeneration();await f.run();assert.equal(f.timers.size,1);
    f.c.stopGenerationMonitor();assert.equal(f.timers.size,0);assert.equal(f.c.generationMonitorActive,false);
  });
  await test('monitor stopped during storage await stays stopped',async()=>{
    const f=monitorFixture(),pending=deferred();f.c.chrome.storage.local.get=()=>pending.promise;
    f.c.monitorGeneration();const old=f.run();await tick();f.c.stopGenerationMonitor();
    pending.resolve({smartpostFlowMonitor:f.monitor});await old;
    assert.equal(f.timers.size,0);assert.equal(f.counts().inspections,0);
  });
  await test('monitor stale rejected inspection cannot report against next scene',async()=>{
    const f=monitorFixture(),pending=deferred();f.c.inspectGenerationState=()=>pending.promise;
    f.c.monitorGeneration();const old=f.run();await tick();f.c.stopGenerationMonitor();f.c.monitorGeneration();
    pending.reject(Error('old DOM'));await old;assert.equal(f.counts().reports,0);assert.equal(f.timers.size,1);
  });
  await test('monitor absent owner stops without an inspection',async()=>{
    const f=monitorFixture();f.c.chrome.storage.local.get=async()=>({});
    f.c.monitorGeneration();await f.run();assert.equal(f.timers.size,0);assert.equal(f.counts().inspections,0);
  });
  await test('outbox rejected head does not starve following current report',async()=>{
    const f=outboxFixture();f.queue(1);f.queue(2);const send=f.c.bridgeFetch;
    f.c.bridgeFetch=async(url,options)=>JSON.parse(options.body).tab_id===1
      ?{ok:false,status:400,json:async()=>({ok:false,error:'temporary callback failure'})}:send(url,options);
    await f.c.flushProgressOutbox();assert.equal(f.sent.length,1);assert.equal(f.sent[0].tab_id,2);
    assert.equal(f.keys().length,1,'keep unacknowledged report for retry');
  });
  await test('outbox ownership lookup failure is isolated',async()=>{
    const f=outboxFixture();f.queue(1);f.queue(2);
    f.c.flowProgressOwnership=async body=>{if(body.tab_id===1)throw Error('owner lookup unavailable');return {active:true};};
    await f.c.flushProgressOutbox();assert.equal(f.sent.length,1);assert.equal(f.keys().length,1);
  });
  await test('outbox bounded fair batches reach jobs after four broken reports',async()=>{
    const f=outboxFixture();for(let i=1;i<=9;i++)f.queue(i);
    const send=f.c.bridgeFetch;
    f.c.bridgeFetch=async(url,options)=>{if(JSON.parse(options.body).tab_id<=4)throw Error('offline job');return send(url,options);};
    await f.c.flushProgressOutbox();await f.c.flushProgressOutbox();await f.c.flushProgressOutbox();
    assert.equal(f.sent.length,5);assert.equal(f.keys().length,4);
  });
  await test('outbox old ownership result never erases a newer report',async()=>{
    const f=outboxFixture(),body=f.queue(1),pending=deferred();
    f.c.flowProgressOwnership=()=>pending.promise;
    const flushing=f.c.flushProgressOutbox();await tick();
    f.c.bridgeFetch=async()=>{throw Error('offline');};
    const newer=f.c.forwardObservedProgress({...body,observed_at_ms:101});await tick();
    pending.resolve({active:false});await Promise.all([flushing,newer]);
    assert.equal(f.store[f.key(body)]?.observed_at_ms,101);
  });
  await test('outbox concurrent flush is single flight',async()=>{
    const f=outboxFixture(),pending=deferred();f.queue(1);let calls=0;
    f.c.bridgeFetch=async()=>{calls++;await pending.promise;return {ok:true,json:async()=>({ok:true})};};
    const first=f.c.flushProgressOutbox();await tick();await f.c.flushProgressOutbox();
    assert.equal(calls,1);pending.resolve();await first;assert.equal(f.keys().length,0);
  });
  await test('outbox worker restart retains retry cursor and rejected reports',async()=>{
    const first=outboxFixture();for(let i=1;i<=6;i++)first.queue(i);
    first.c.bridgeFetch=async()=>{throw Error('offline');};await first.c.flushProgressOutbox();
    const next=outboxFixture();Object.assign(next.store,first.store);await next.c.flushProgressOutbox();
    assert.equal(next.sent[0].tab_id,5);assert.equal(next.sent.length,4);
  });
  await test('outbox completion cannot be coalesced away by passive page status',async()=>{
    const f=outboxFixture(),body=f.body(1);f.c.bridgeFetch=async()=>{throw Error('offline');};
    await f.c.forwardObservedProgress({...body,step:'generation_complete',download_path:'scene.mp4'});
    await f.c.forwardObservedProgress({...body,observed_at_ms:101,step:'package_loaded'});
    assert.equal(f.keys().length,2);assert(f.keys().some(key=>f.store[key].download_path==='scene.mp4'));
  });
  await test('outbox stale scoped download receipt is discarded without network send',async()=>{
    const f=outboxFixture(),send=f.c.bridgeFetch;
    f.c.bridgeFetch=async()=>{throw Error('offline');};
    await f.c.forwardObservedProgress({...f.body(1),step:'generation_complete',download_path:'scene.mp4'});
    f.c.flowProgressOwnership=async()=>({active:false});f.c.bridgeFetch=send;await f.c.flushProgressOutbox();
    assert.equal(f.sent.length,0);assert.equal(f.keys().length,0);
  });
  await test('outbox pre406 download key remains deliverable after upgrade',async()=>{
    const f=outboxFixture(),body={...f.body(1),step:'generation_complete',download_path:'scene.mp4'};
    f.store[f.key(body)]=body;await f.c.flushProgressOutbox();
    assert.equal(f.sent.length,1);assert.equal(f.keys().length,0);
  });
  for(const failure of ['network','invalid-json','http-400','http-403','http-429','http-500']){
    await test(`outbox retains ${failure} until ACK without pretending delivered`,async()=>{
      const f=outboxFixture(),send=f.c.bridgeFetch;
      f.c.bridgeFetch=async()=>{
        if(failure==='network')throw Error('offline');
        if(failure==='invalid-json')return {ok:true,json:async()=>{throw Error('invalid response');}};
        return {ok:false,status:Number(failure.slice(5)),json:async()=>({ok:false})};
      };
      assert.equal((await f.c.forwardObservedProgress(f.body(1))).buffered,true);assert.equal(f.keys().length,1);
      f.c.bridgeFetch=send;await f.c.flushProgressOutbox();assert.equal(f.sent.length,1);assert.equal(f.keys().length,0);
    });
  }
  await test('download completion survives lost bridge reply without second download',async()=>{
    const f=outboxFixture();let online=false,downloads=0,acks=0;
    const command={id:'CMD',action:'download_flow_result',job_id:'STORY-1',shot_index:9,run_id:'RUN'};
    Object.assign(f.c,{CLIENT_ID:'fixture',COMMAND_OUTCOMES_KEY:'outcomes',pollAICovers:async()=>{},
      commandOutcomeMatches:()=>false,rememberCommandRun:async()=>{},
      downloadFlowResult:async()=>{downloads++;return {filename:'SmartPost/STORY-1/flow-shot-09.mp4'};},
      acknowledge:async(_command,ok)=>{assert.equal(ok,true);acks++;},scheduleFastCommandHandoff:()=>{},
      reportAICommandFailure:async()=>{},reportFlowCommandFailure:async()=>{}});
    f.c.bridgeFetch=async(url,options)=>{
      if(url.includes('/commands?'))return {ok:true,json:async()=>({commands:[command]})};
      if(!online)throw Error('lost progress reply');
      f.sent.push(JSON.parse(options.body));return {ok:true,json:async()=>({ok:true})};
    };
    vm.runInContext(section(background,'async function pollCommands()','async function extensionTick()'),f.c);
    await f.c.pollCommands();assert.equal(downloads,1);assert.equal(acks,1);
    assert.equal(f.keys().length,1,'file completion must remain durable before command success');
    online=true;await f.c.flushProgressOutbox();assert.equal(f.sent.length,1);
    assert.equal(f.sent[0].download_path,'SmartPost/STORY-1/flow-shot-09.mp4');assert.equal(downloads,1);
  });
  await test('chatgpt temporary receipt read failure does not consume refresh opportunity',async()=>{
    const f=imageWaitFixture(),get=f.c.chrome.storage.local.get;
    f.c.chrome.storage.local.get=async()=>{throw Error('temporary worker disconnect');};
    for(let i=1;i<=3;i++){f.set(i*700,{signature:'broken',stalledReason:'image_load_failed'});await f.tick();}
    assert.equal(f.messages.length,0);
    f.c.chrome.storage.local.get=get;f.set(10000);await f.tick();
    assert.equal(f.messages.length,1,'retry passive receipt read, not provider Send');
  });
  await test('chatgpt passive storage retry is throttled',async()=>{
    const f=imageWaitFixture();let reads=0;f.c.chrome.storage.local.get=async()=>{reads++;throw Error('storage unavailable');};
    for(let i=1;i<=8;i++){f.set(i*700,{signature:'broken',stalledReason:'image_load_failed'});await f.tick();}
    assert.equal(reads,1);f.set(10000);await f.tick();assert.equal(reads,2);assert.equal(f.messages.length,0);
  });
  await test('chatgpt user draft veto does not burn later refresh',async()=>{
    const f=imageWaitFixture();f.c.composerText=()=> 'user draft';
    for(let i=1;i<=3;i++){f.set(i*700,{signature:'broken',stalledReason:'image_load_failed'});await f.tick();}
    assert.equal(f.messages.length,0);f.c.composerText=()=>'';f.set(10000);await f.tick();
    assert.equal(f.messages.length,1);
  });
  await test('chatgpt lost refresh reply never permits another dispatch',async()=>{
    const f=imageWaitFixture();let sends=0;f.c.chrome.runtime.sendMessage=async()=>{sends++;throw Error('port closed');};
    for(let i=1;i<=3;i++){f.set(i*700,{signature:'broken',stalledReason:'image_load_failed'});await f.tick();}
    f.set(10000);await f.tick();assert.equal(sends,1);
  });
  console.log(JSON.stringify({ok:true,cases,providerActions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
