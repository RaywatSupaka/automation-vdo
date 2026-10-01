const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/background.js'),'utf8');
const start=source.indexOf("    if (message?.type === 'AI_COVER_EVENT') {");
const end=source.indexOf('    const pausedMutationTypes',start);
assert(start>=0&&end>start);
const code='async function handleCover(message,sender,sendResponse){'+source.slice(start,end)+'}';
async function scenario(phase,successor=false,wrongTab=false){
  const rid='a'.repeat(32),child='b'.repeat(32),key='smartflowCover:'+rid;
  const saved={[key]:{request_id:rid,job_id:'STORY-FIXTURE',provider:'chatgpt',phase:'running',tab_id:17}};
  const events=[],progress=[],timeouts=[];let response;
  const context={URL,CLIENT_ID:'fixture',BRIDGE:'http://fixture.invalid',Date,
    withCoverOwner:async(id,operation)=>operation(),
    coverBridgeEvent:async(id,event)=>{assert.equal(id,rid);events.push(event);return {
      request_id:rid,job_id:'STORY-FIXTURE',phase,message:'fixture',...(successor?{successor_request_id:child}:{})};},
    bridgeFetch:async(url,init)=>{progress.push(JSON.parse(init.body));},
    chrome:{storage:{local:{get:async k=>({[k]:saved[k]}),set:async values=>Object.assign(saved,values)}}},
    setTimeout:(f,ms)=>timeouts.push(ms),closeSavedCoverTabs:async()=>{},
  };
  vm.createContext(context);vm.runInContext(code,context);
  const message={type:'AI_COVER_EVENT',request_id:rid,event:{phase:'needs_review',
    download_failure:{attempts:3,owned:true,idle:true}}};
  const sender={tab:{id:wrongTab?99:17,url:'https://chatgpt.com/c/owned-cover'}};
  if(wrongTab){
    await assert.rejects(context.handleCover(message,sender,r=>response=r),/แท็บเจ้าของปกไม่ตรง/);
    assert.equal(events.length,0);assert.equal(progress.length,0);return;
  }
  await context.handleCover(message,sender,r=>response=r);
  assert.equal(events.length,1);assert.equal(progress.length,1);assert(response.ok);
  assert.equal(response.request.request_id,rid,'Reply must remain bound to the old tab/request');
  assert.equal(saved[key].phase,phase);
  assert.equal(Object.keys(saved).length,1,'Event handler never dispatches a replacement itself');
  assert.equal(progress[0].step,successor?'preparing_cover':phase==='ready'?'image_checkpoint_saved':'error');
  if(successor)assert.equal(saved[key].successor_request_id,child);
  assert.deepEqual(timeouts,phase==='ready'?[500]:[]);
}
(async()=>{
  await scenario('needs_review',true);
  await scenario('needs_review');
  await scenario('ready');
  await scenario('needs_review',true,true);
  console.log('4 owned cover replacement background cases passed; no tabs, provider actions or network');
})().catch(error=>{console.error(error);process.exitCode=1;});
