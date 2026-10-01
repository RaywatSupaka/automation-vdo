const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const a=source.indexOf('const progressOutboxLocks='),b=source.indexOf('function scheduleFastCommandHandoff',a);
assert(a>0&&b>a);
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
(async()=>{
 let online=false,active=true,sends=0,store={};
 const context=vm.createContext({Map,Object,Promise,JSON,AbortController,setTimeout,clearTimeout,BRIDGE:'http://test',
  chrome:{storage:{local:{get:async key=>key===null?{...store}:{[key]:store[key]},set:async o=>Object.assign(store,o),remove:async key=>{delete store[key];}}}},
  bridgeFetch:async()=>{sends++;if(!online)throw Error('offline');return {ok:true,json:async()=>({ok:true})};},
  aiProgressOwnership:async()=>({active}),flowProgressOwnership:async()=>({active})});
 vm.runInContext(source.slice(a,b),context);
 const body={scope:'chatgpt',job_id:'STORY-X',run_id:'R',tab_id:1,observed_at_ms:100};
 assert((await context.forwardObservedProgress(body)).buffered);assert.equal(Object.keys(store).length,1);
 await context.forwardObservedProgress({...body,observed_at_ms:102});
 assert((await context.forwardObservedProgress({...body,observed_at_ms:101})).ignored);
 const queued=()=>Object.keys(store).filter(key=>key.startsWith('smartflowProgressOutbox:')).length;
 online=true;await context.flushProgressOutbox();assert.equal(queued(),0);
 online=false;await context.forwardObservedProgress({...body,observed_at_ms:103});
 active=false;const before=sends;await context.flushProgressOutbox();assert.equal(sends,before);assert.equal(queued(),0);
 // Exercise actual wait implementation beyond the former seven-minute bound.
 const start=content.indexOf('  async function waitForResponseIdle('),end=content.indexOf('  function assertNotCancelled()',start);
 for(const gemini of [true,false]){
  let now=0,checks=0,reports=0,stopClicks=0;
  // Production wait is outside runJob's local scope. Never fabricate its local
  // lastCompletedImageCount here: that masked the real ReferenceError in 368.
  const c=vm.createContext({IS_GEMINI:gemini,Date:{now:()=>now},
    assertNotCancelled:()=>{checks++;},stopButtonVisible:()=>now<480000,
    stopButton:()=>({click:()=>stopClicks++}),sleep:async n=>{now+=n;},
    report:async(_step,_message,count)=>{assert.equal(count,2);reports++;}});
  vm.runInContext(content.slice(start,end),c);await c.waitForResponseIdle(1,null,'',2);
  assert(now>=480000);assert(checks>700);assert(reports>50);assert.equal(stopClicks,0);
 }
 let cancelled=0;
 const c=vm.createContext({assertNotCancelled:()=>{cancelled++;throw Error('cancel');}});
 vm.runInContext(content.slice(start,end),c);await assert.rejects(c.waitForResponseIdle(),/cancel/);assert.equal(cancelled,1);
 console.log('observation outbox / stale report / busy wait / cancellation passed');
})().catch(e=>{console.error(e);process.exit(1);});
