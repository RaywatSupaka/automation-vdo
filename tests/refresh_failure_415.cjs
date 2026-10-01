const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const harness=fs.readFileSync('tests/story_image_refresh_background_harness.js','utf8');
const fixture=new Function('require','__dirname',harness.split('(async () =>')[0]+';return fixture;')(require,__dirname);
const fn=name=>{const at=source.indexOf('function '+name+'(');assert(at>=0);return source.slice(at,source.indexOf('\n}',at)+2);};
const failure='Something went wrong while generating your image. Sorry about that.';
const proof={stalled_reason:'completed_service_error',failure_text:failure,stagnant_since:990000};
(async()=>{
 let cases=0;
 for(const mode of ['timeout','ready','busy_then_ready','media_then_ready','busy_then_unknown','draft','cancel','changed_receipt','new_image','policy','early','wrong_echo','archive_failure','archive_ack','terminal_ack','archive_cancel']){
  const f=fixture({guard:(reply,_count,_storage,_sender,guard)=>{
    reply.failure_text=mode==='wrong_echo'?'changed':failure;
  }}),original=JSON.stringify(f.storage[f.key]),fresh=[];
  vm.runInContext(fn('restartableStoryServiceReceipt'),f.context);
  let waits=0;
  f.context.waitForAIRefreshReady=async()=>{
    waits++;
    if(mode==='cancel')f.storage['smartflowChatGPTStoryRefreshCancelled:STORY-REFRESH']='RUN-CURRENT';
    if(mode==='changed_receipt')f.storage[f.key].send_nonce='different';
    if(mode==='new_image')f.storage[f.key].image_url='https://chatgpt.com/backend-api/files/real-image';
    if(mode==='ready'||(['busy_then_ready','media_then_ready'].includes(mode)&&waits===2)||mode==='busy_then_unknown'&&waits===3)return;
    throw Object.assign(Error(mode==='draft'?'user draft':'page not ready'),{
      code:mode==='draft'?'AI_REFRESH_DRAFT_REVIEW':'AI_REFRESH_READY_TIMEOUT',
      refresh_state:{busy:mode==='busy_then_ready'||mode==='busy_then_unknown'&&waits===1,has_media:mode==='media_then_ready'}});
  };
  const resume=f.context.startAIWebJob;
  f.context.startAIWebJob=async(...args)=>{
    if(!args[3])return resume(...args);
    fresh.push(args);
    assert.equal(f.storage[f.key].status,'completed_no_image');
    assert.equal(f.storage[f.key].response_excerpt,failure);
    assert.equal(f.storage[f.key].result_proof.prompt,f.message.prompt);
    assert.equal(f.storage[f.key].fresh_restart,null);
  };
  if(['archive_failure','archive_ack','terminal_ack','archive_cancel'].includes(mode)){
    const save=f.context.chrome.storage.local.set;
    f.context.chrome.storage.local.set=async values=>{
      const archive=Object.keys(values).some(key=>key.includes(':pre-refresh:'));
      if(archive&&mode==='archive_failure')throw Error('disk failed');
      if(archive&&mode==='archive_ack'||values[f.key]?.status==='completed_no_image'&&mode==='terminal_ack')return;
      await save(values);
      if(archive&&mode==='archive_cancel')f.storage['smartflowChatGPTStoryRefreshCancelled:STORY-REFRESH']='RUN-CURRENT';
    };
  }
  await f.dispatch({...proof,...mode==='policy'?{failure_text:'I cannot help because this violates policy'}:{},
    ...mode==='early'?{stagnant_since:995000}:{}});
  if(mode==='timeout'){
    assert.equal(fresh.length,1,'confirmed failed image + exhausted reload must hand off to fresh scene');
    assert.equal(f.failures.filter(e=>e.step==='error').length,0);
    const archived=Object.entries(f.storage).find(([key])=>key.includes(':pre-refresh:'));
    assert(archived);assert.equal(JSON.stringify(archived[1]),original);
    const budget=Object.entries(f.storage).find(([key])=>key.startsWith('smartflowChatGPTStoryResultRefresh:'))[1];
    assert.equal(budget.phase,'fresh_resumed');assert.equal(budget.failure_proof.text,failure);
  }else if(['ready','busy_then_ready','media_then_ready','busy_then_unknown'].includes(mode)){
    assert.equal(fresh.length,0);assert.equal(f.resumes.length,1);assert.equal(JSON.stringify(f.storage[f.key]),original);
  }else{
    assert.equal(fresh.length,0,'never create a fresh attempt for '+mode);
    if(!['changed_receipt','new_image'].includes(mode))assert.equal(JSON.stringify(f.storage[f.key]),original);
  }
  assert.equal(f.events.filter(e=>e==='reload').length,['policy','early','wrong_echo'].includes(mode)?0:1);
  cases++;
 }
 // Without durable confirmed failure, a readiness timeout is never Send authority.
 const unknown=fixture();unknown.context.waitForAIRefreshReady=async()=>{throw Object.assign(Error('not ready'),{code:'AI_REFRESH_READY_TIMEOUT'});};
 await unknown.dispatch();assert.equal(unknown.resumes.length,0);assert.equal(unknown.storage[unknown.key].status,'awaiting_result');cases++;
 // Follow the real refresh -> desktop package -> fresh transaction, not only
 // a mocked start call. No external network or provider generation is used.
 const worker=new Function('require','__dirname',fs.readFileSync('tests/recovery_413.cjs','utf8').split('\n(async()=>')[0]+';return worker;')(require,__dirname);
 for(const mode of ['complete','cancel_before_start']){
  const w=worker(),row=w.store[w.key],events=[];
  row.status='awaiting_result';delete row.response_excerpt;
  const original=JSON.stringify(row),url=w.tabs[7].url;
  const message={provider:'chatgpt',job_id:'STORY-413',run_id:'RUN-413',index:15,receipt_identity:row.identity,
   send_nonce:row.send_nonce,prompt:row.result_proof.prompt,conversation_url:url,signature:'test-native-error',
   stable_samples:3,stagnant_since:Date.now()-10000,...proof};
  message.stagnant_since=Date.now()-10000;
  w.c.TextEncoder=TextEncoder;w.c.Date=Date;w.c.chatGPTStoryResultRefreshLocks=new Set();
  w.c.setTimeout=fn=>queueMicrotask(fn);
  w.c.assertStoryCheckpointOwner=async()=>{
   assert.equal(w.store['run:STORY-413'],'RUN-413');assert.equal(w.store['smartpostAIWebTab:chatgpt:STORY-413'],7);
  };
  w.c.reportWebActionProgress=async event=>{
   events.push(event);
   if(mode==='cancel_before_start'&&event.message.includes('หน้าสะอาด'))w.store['smartflowChatGPTStoryRefreshCancelled:STORY-413']='RUN-413';
  };
  w.c.waitForAIRefreshReady=async()=>{throw Object.assign(Error('page not ready'),{code:'AI_REFRESH_READY_TIMEOUT'});};
  w.c.chrome.tabs.reload=async()=>events.push({step:'reload'});
  const send=w.c.chrome.tabs.sendMessage;
  w.c.chrome.tabs.sendMessage=async(id,m)=>m.type==='VERIFY_CHATGPT_STORY_RESULT_REFRESH'?{...m,ok:true,allowed:true}:send(id,m);
  const at=source.indexOf('async function refreshStoryChatGPTResult(');
  vm.runInContext(source.slice(at,source.indexOf('\n}',at)+2),w.c);
  await w.c.refreshStoryChatGPTResult(message,{tab:w.tabs[7]},()=>events.push({step:'ack'}));
  assert.equal(JSON.stringify(w.store[w.key+':pre-refresh:'+row.send_nonce]),original);
  assert.equal(w.events.filter(e=>e[0]==='START_CHATGPT_JOB').length,mode==='complete'?1:0);
  assert.equal(w.events.filter(e=>e[0]==='create').length,mode==='complete'?1:0);
  assert.equal(w.events.filter(e=>e[0]==='navigate'&&e[1]!== 'https://chatgpt.com/').length,0);
  if(mode==='complete')assert.equal(events.filter(e=>e.step==='error').length,0);
  cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
