// Actual background controller with isolated Chrome storage/document fixtures.
// No network, real browser, provider Send, Stop, or filesystem mutation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const extract=name=>{const start=source.search(new RegExp('(?:async )?function '+name+'\\('));
  assert(start>=0,name);return source.slice(start,source.indexOf('\n}',start)+2);};
const clone=value=>JSON.parse(JSON.stringify(value));
const oldFixture=new Function('require','__dirname',fs.readFileSync('tests/story_image_refresh_background_harness.js','utf8')
  .split('(async () =>')[0]+';return fixture;')(require,__dirname);
const oldWorker=new Function('require','__dirname',fs.readFileSync('tests/recovery_413.cjs','utf8')
  .split('\n(async()=>')[0]+';return worker;')(require,__dirname);
const documentFixture=new Function('require','__dirname',fs.readFileSync('tests/story_refresh_document_438.cjs','utf8')
  .split('\n(async()=>')[0]+';return fixture;')(require,__dirname);
function setup(options={}){
  let now=1000000;
  const f=oldFixture({...options,guard:(reply,count,storage,sender)=>{
    Object.assign(reply,{recovery_protocol:3,refresh_cycle:f.message.refresh_cycle,
      result_owner_nonce:f.message.result_owner_nonce});
    options.guard?.(reply,count,storage,sender);
  }});
  f.context.Date={now:()=>now};
  vm.runInContext(extract('assertStoryImageRefreshResultOwner'),f.context);
  Object.assign(f.message,{recovery_protocol:3,refresh_cycle:1,result_owner_nonce:'send-nonce',
    stagnant_since:940000,stalled_reason:'active_generation_wait'});
  f.sender.documentId='document-0';
  const send=f.context.chrome.tabs.sendMessage;
  f.context.chrome.tabs.sendMessage=async(id,msg,target)=>{
    assert.equal(target.documentId,f.sender.documentId,'live guard is pinned to sender document');
    return send(id,msg);
  };
  f.child=()=>{
    const parent=f.storage[f.key],proof=clone(parent.result_proof),key=f.key+':reminder:'+parent.send_nonce;
    const child={version:1,provider:'chatgpt',job_id:parent.job_id,run_id:parent.run_id,scene_index:parent.scene_index,
      parent_key:f.key,parent_nonce:parent.send_nonce,parent_identity:parent.identity,
      send_phase:'accepted',send_nonce:'child-nonce',prompt:'one short reminder',
      conversation_url:proof.conversation_url,original_result_proof:proof,
      result_proof:{...proof,prompt:'one short reminder',request_message_id:'child-message',request_turn_id:'conversation-turn-26'}};
    f.storage[key]=child;
    parent.same_chat_reminder={version:1,key,nonce:child.send_nonce,parent_nonce:parent.send_nonce};
    parent.result_proof=clone(child.result_proof);
    f.message.prompt=child.prompt;f.message.result_owner_nonce=child.send_nonce;
    return child;
  };
  f.advance=()=>{now+=60001;f.sender.documentId='document-'+f.message.refresh_cycle;
    f.message.refresh_cycle++;f.message.stagnant_since=now-60000;};
  return f;
}
function redoSetup(){
  const f=oldWorker(),row=f.store[f.key],now=Date.now();
  vm.runInContext(extract('assertStoryImageRefreshResultOwner'),f.c);
  f.pkg.browser_recovery.image_post_refresh_redo={version:1};
  Object.assign(row,{recovery_protocol:3,retry_kind:'missing_after_refresh',response_excerpt:'',
    refresh_recovery:{version:1,loop_version:1,refresh_cycle:2,result_owner_nonce:row.send_nonce,
      phase:'checking',tab_id:7,send_nonce:row.send_nonce,document_fence_version:1,
      previous_document_id:'old-doc',document_id:'new-doc',conversation_url:row.result_proof.conversation_url,
      claimed_at:now-90000,ready_at:now-45000},
    post_refresh_evidence:{version:1,loop_version:1,refresh_cycle:2,result_owner_nonce:row.send_nonce,
      receipt_identity:row.identity,send_nonce:row.send_nonce,conversation_url:row.result_proof.conversation_url,
      refresh_claimed_at:now-90000,observed_at:now,stable_since:now-35000,stable_samples:4,signature:'owned-idle-absence',
      result_reason:'waiting_response',page_ready:true,history_ready:true,response_active:false,draft_present:false,
      at_end:true,reload_completed:true}});
  f.c.chrome.tabs.query=async()=>Object.values(f.tabs);
  f.c.chrome.scripting.executeScript=async request=>{
    f.events.push(['inject']);return [{frameId:0,documentId:'successor-document',result:f.tabs[request.target.tabId].url}];
  };
  const send=f.c.chrome.tabs.sendMessage;
  f.c.chrome.tabs.sendMessage=async(id,msg,target)=>{
    if(msg.type==='VERIFY_STORY_IMAGE_REDO'){
      assert.equal(target.documentId,'new-doc');f.events.push(['redo_guard',id]);
      return {...msg,ok:true,allowed:true};
    }
    return send(id,msg);
  };
  return f;
}
function restartSetup(){
  const f=redoSetup();
  Object.assign(f.c,{storyFreshImageLoopRequests:new Map(),waitForAIRecoveryOperation:async promise=>promise,
    aiProgressOwnership:async()=>({active:true,ownerTabId:f.store['smartpostAIWebTab:chatgpt:STORY-413'],activeRunId:'RUN-413'})});
  vm.runInContext(extract('assertStoryCheckpointOwner')+'\n'+extract('restartFailedStoryImageLoop'),f.c);
  f.message={recovery_protocol:3,provider:'chatgpt',job_id:'STORY-413',run_id:'RUN-413',index:15,
    receipt_identity:'exact-scene',send_nonce:'original-nonce',refresh_cycle:2,result_owner_nonce:'original-nonce'};
  f.sender={tab:{id:7,url:f.tabs[7].url},documentId:'new-doc'};
  f.dispatch=()=>f.c.restartFailedStoryImageLoop(f.message,f.sender);
  f.consume=()=>{
    const row=f.store[f.key];
    f.store[f.key]={...row,status:'awaiting_result',send_phase:'prepared',send_nonce:'',result_proof:null,
      refresh_recovery:null,post_refresh_evidence:null,same_chat_reminder:null,
      run_id:'RUN-413',fresh_restart:{...row.fresh_restart,phase:'consumed'}};
  };
  return f;
}
(async()=>{
  let cases=0;
  for(const child of [false,true]){
    const f=setup();if(child)f.child();
    const original=clone(f.storage[f.key]);
    await f.dispatch();
    assert.equal(f.replies.at(-1).ok,true);assert.equal(f.resumes.length,1);
    assert.equal(f.storage[f.key].send_nonce,original.send_nonce);
    assert.deepEqual(f.storage[f.key].result_proof,original.result_proof);
    assert.equal(f.storage[f.key].refresh_recovery.result_owner_nonce,f.message.result_owner_nonce);
    assert.equal(f.storage[f.key].refresh_recovery.document_id,'document-1');
    f.advance();await f.dispatch();
    assert.equal(f.replies.at(-1).ok,true);assert.equal(f.events.filter(x=>x==='reload').length,2);
    assert.equal(f.storage[f.key].refresh_recovery.refresh_cycle,2);
    assert.equal(f.storage[f.key].refresh_recovery.previous_document_id,'document-1');
    assert.equal(f.storage[f.key].refresh_recovery.document_id,'document-2');cases+=2;
    await f.dispatch();assert.equal(f.events.filter(x=>x==='reload').length,2);
    assert.equal(f.replies.at(-1).ok,false,'same-cycle ACK loss never repeats reload');cases++;
  }
  for(const mutate of [
    f=>f.message.refresh_cycle=0,f=>f.message.refresh_cycle=2,f=>f.message.refresh_cycle=1.5,
    f=>f.message.result_owner_nonce='foreign',f=>f.message.stagnant_since=940001,
    f=>delete f.sender.documentId,f=>f.storage[f.key].send_phase='dispatching',
    f=>f.storage[f.key].image_url='saved.png',
    f=>f.storage['smartflowChatGPTStoryRefreshCancelled:'+f.message.job_id]=f.message.run_id,
  ]){const f=setup();mutate(f);await f.dispatch();assert(!f.events.includes('reload'));cases++;}
  for(const mutate of [
    (f,c)=>c.send_phase='dispatching',(f,c)=>c.send_phase='prepared',(f,c)=>c.parent_nonce='foreign',
    (f,c)=>c.parent_identity='foreign',(f,c)=>c.run_id='foreign',(f,c)=>c.scene_index=11,
    (f,c)=>c.result_proof.request_message_id='foreign',(f,c)=>c.original_result_proof.prompt='',
    f=>f.storage[f.key].same_chat_reminder.nonce='foreign',
    f=>f.message.result_owner_nonce=f.message.send_nonce,
  ]){const f=setup(),child=f.child();mutate(f,child);await f.dispatch();assert(!f.events.includes('reload'));cases++;}
  for(const field of ['recovery_protocol','refresh_cycle','result_owner_nonce']){
    const f=setup({guard:reply=>{reply[field]='wrong';}});await f.dispatch();
    assert(!f.events.includes('reload'));cases++;
  }
  const late=setup({onDelay:store=>{store[late.key].image_url='late-result.png';}});
  await late.dispatch();assert(!late.events.includes('reload'));cases++;
  const veto=setup({guard:(reply,count)=>{if(count===2)reply.allowed=false;}});
  const vetoReceipt=clone(veto.storage[veto.key]);
  await veto.dispatch();assert(!veto.events.includes('reload'));
  assert.deepEqual(veto.storage[veto.key],vetoReceipt,'late result keeps the exact content-owned receipt');
  assert(Object.values(veto.storage).some(row=>row?.phase==='guard_deferred'
    && JSON.stringify(row.preclaim_receipt)===JSON.stringify(vetoReceipt)));cases++;
  const early=setup();await early.dispatch();early.message.refresh_cycle=2;early.sender.documentId='document-1';
  await early.dispatch();assert.equal(early.events.filter(x=>x==='reload').length,1);cases++;
  const handoff=setup();await handoff.dispatch();handoff.advance();
  handoff.storage[handoff.key].refresh_recovery.phase='reloaded';
  await handoff.dispatch();assert.equal(handoff.events.filter(x=>x==='reload').length,1);cases++;
  const legacy=setup();Object.assign(legacy.storage[legacy.key],{refresh_recovery:{version:1,phase:'checking',
    claimed_at:900000,ready_at:930000,send_nonce:'send-nonce'}});
  legacy.child();await legacy.dispatch();assert.equal(legacy.replies.at(-1).ok,true);cases++;
  const redo=redoSetup();assert.equal(redo.c.restartableStoryServiceReceipt(redo.store[redo.key],'STORY-413',15),true);
  await redo.run();await redo.run();assert.equal(redo.events.filter(row=>row[0]==='create').length,1);cases++;
  for(const field of ['refresh_cycle','result_owner_nonce','loop_version']){
    const f=redoSetup();f.store[f.key].post_refresh_evidence[field]='wrong';
    assert.equal(f.c.restartableStoryServiceReceipt(f.store[f.key],'STORY-413',15),false);cases++;
  }
  const busy=redoSetup();busy.store[busy.key].post_refresh_evidence.response_active=true;
  await assert.rejects(busy.run());assert.equal(busy.events.filter(row=>row[0]==='create').length,0);cases++;
  // Real readiness/Start implementation: old ready document, navigation races,
  // and a lost START ACK retain the exact accepted owner and one reload.
  for(const mode of ['delayed','after_readiness','during_injection','injection_rejected','probe_rejected','after_start','ack_lost']){
    const f=documentFixture(mode);vm.runInContext(extract('assertStoryImageRefreshResultOwner'),f.w.c);
    Object.assign(f.message,{recovery_protocol:3,refresh_cycle:1,result_owner_nonce:f.message.send_nonce});
    await f.run();assert.equal(f.events.filter(e=>e[0]==='reload-enqueued').length,1,mode);
    assert.equal(f.budget().phase,'resumed',mode);
    assert(!f.events.some(e=>e[0]==='START'&&e[1]==='old-document'),mode);
    assert(!f.events.some(e=>e[0]==='progress'&&e[1]==='error'),mode);
    if(mode==='ack_lost')assert.equal(f.collectors.size,1);cases++;
  }
  // Lost reload/receipt ACK: the periodic recovery reads a distinct document
  // and reattaches without a second reload, Send, or fresh scene allocation.
  for(const phase of ['claimed','reloaded']){
    const f=documentFixture();f.setDoc('new-document');
    vm.runInContext(extract('assertStoryImageRefreshResultOwner')+'\n'+extract('resumePendingStoryImageRefresh'),f.w.c);
    f.w.c.STORY_REFRESH_COLLECTOR_REATTACH='fixture-handoff:';
    f.w.c.storyRefreshDesktopRunActive=async()=>true;
    f.w.c.waitForAIRecoveryOperation=async promise=>promise;
    f.w.store[f.w.key].refresh_recovery={version:1,loop_version:1,run_id:'RUN-413',phase,tab_id:7,
      refresh_cycle:1,result_owner_nonce:'original-nonce',conversation_url:f.w.tabs[7].url,
      send_nonce:'original-nonce',claimed_at:900000,document_fence_version:1,previous_document_id:'old-document'};
    f.w.store['smartpostAIWebRun:STORY-413']='RUN-413';
    await f.w.c.resumePendingStoryImageRefresh(f.w.key,clone(f.w.store[f.w.key]),clone(f.w.store),1000000);
    assert.equal(f.events.filter(e=>e[0]==='reload-enqueued').length,0);
    assert.equal(f.events.filter(e=>e[0]==='START').length,1);
    assert.equal(f.w.store[f.w.key].refresh_recovery.phase,'checking');cases++;
  }
  // A lost navigation ACK must remain pending if Chrome still exposes only
  // the original document; reloading again is not reconciliation.
  const unchanged=documentFixture();vm.runInContext(extract('assertStoryImageRefreshResultOwner')+'\n'
    +extract('resumePendingStoryImageRefresh'),unchanged.w.c);
  Object.assign(unchanged.w.c,{STORY_REFRESH_COLLECTOR_REATTACH:'fixture:',storyRefreshDesktopRunActive:async()=>true,
    waitForAIRecoveryOperation:async promise=>promise});
  unchanged.w.store['smartpostAIWebRun:STORY-413']='RUN-413';
  unchanged.w.store[unchanged.w.key].refresh_recovery={version:1,loop_version:1,run_id:'RUN-413',phase:'claimed',tab_id:7,
    refresh_cycle:1,result_owner_nonce:'original-nonce',conversation_url:unchanged.w.tabs[7].url,
    send_nonce:'original-nonce',claimed_at:900000,document_fence_version:1,previous_document_id:'old-document'};
  await unchanged.w.c.resumePendingStoryImageRefresh(unchanged.w.key,clone(unchanged.w.store[unchanged.w.key]),clone(unchanged.w.store),1000000);
  assert(!unchanged.events.some(e=>['reload-enqueued','START'].includes(e[0])));cases++;
  // Restart ACK loss reconciles the archive and existing successor even after
  // content consumes/replaces the parent's nonce; it never creates or Starts twice.
  const consumed=restartSetup(),sendConsumed=consumed.c.chrome.tabs.sendMessage;
  consumed.c.chrome.tabs.sendMessage=async(id,msg,target)=>{
    const result=await sendConsumed(id,msg,target);
    if(msg.type==='START_CHATGPT_JOB'){consumed.consume();throw Error('START ACK lost');}
    return result;
  };
  assert.equal((await consumed.dispatch()).pending,true);
  assert.equal((await consumed.dispatch()).already_started,true);
  assert.equal(consumed.events.filter(e=>e[0]==='create').length,1);
  assert.equal(consumed.events.filter(e=>e[0]==='START_CHATGPT_JOB').length,1);cases++;
  // Unknown allocation is reconciled only by the unique persisted marker.
  for(const visible of [false,true]){
    const f=restartSetup(),create=f.c.chrome.tabs.create;
    f.c.chrome.tabs.create=async opts=>{if(visible)await create(opts);throw Error('create ACK lost');};
    assert.equal((await f.dispatch()).pending,true);
    const answer=await f.dispatch();
    assert.equal(visible?answer.ok:answer.pending,true);
    assert.equal(f.events.filter(e=>e[0]==='create').length,visible?1:0);
    assert.equal(f.events.filter(e=>e[0]==='START_CHATGPT_JOB').length,visible?1:0);cases++;
  }
  // A persisted pending claim never outlives cancellation, a new run, or a
  // different source document, and cannot be claimed with another owner's proof.
  for(const mutate of [
    f=>f.store['smartflowChatGPTStoryRefreshCancelled:STORY-413']='RUN-413',
    f=>f.store['run:STORY-413']='new-run',f=>f.sender.documentId='different-document',
    f=>f.message.refresh_cycle=3,f=>f.message.result_owner_nonce='other-child',
    f=>f.message.receipt_identity='other-scene',f=>f.message.send_nonce='other-parent'
  ]){
    const f=restartSetup();f.c.chrome.tabs.create=async()=>{throw Error('create ACK lost');};
    assert.equal((await f.dispatch()).pending,true);mutate(f);
    await assert.rejects(f.dispatch());assert(!f.events.some(e=>e[0]==='START_CHATGPT_JOB'));cases++;
  }
  const cancelDuring=restartSetup();
  cancelDuring.c.chrome.tabs.create=async()=>{
    cancelDuring.store['smartflowChatGPTStoryRefreshCancelled:STORY-413']='RUN-413';throw Error('create ACK lost');
  };
  await assert.rejects(cancelDuring.dispatch(),/run changed/);cases++;
  const wrongDoc=restartSetup();wrongDoc.sender.documentId='different-document';
  await assert.rejects(wrongDoc.dispatch());assert(!wrongDoc.events.some(e=>e[0]==='create'));cases++;
  // Parallel retries join one in-flight transaction. They cannot collide in
  // the lower allocation lock or allocate a second tab.
  const concurrent=restartSetup();
  const answers=await Promise.all([concurrent.dispatch(),concurrent.dispatch()]);
  assert(answers.every(reply=>reply.ok));assert.equal(concurrent.events.filter(e=>e[0]==='create').length,1);cases++;
  const navigation=restartSetup(),navigate=navigation.c.chrome.tabs.update;
  let navigationFailure=true;
  navigation.c.chrome.tabs.update=async(...args)=>{
    if(navigationFailure){navigationFailure=false;throw Error('navigation ACK unavailable');}return navigate(...args);
  };
  assert.equal((await navigation.dispatch()).pending,true);
  assert(!navigation.events.some(e=>e[0]==='CANCEL_CHATGPT_JOB'),'source reconciler stays alive until START');
  assert.equal((await navigation.dispatch()).ok,true);
  assert.equal(navigation.events.filter(e=>e[0]==='create').length,1);cases++;
  const startUnknown=restartSetup(),sendUnknown=startUnknown.c.chrome.tabs.sendMessage;
  let missingStart=true;
  startUnknown.c.chrome.tabs.sendMessage=async(id,msg,target)=>{
    if(msg.type==='START_CHATGPT_JOB'){
      assert.equal(target.documentId,'successor-document');
      if(missingStart){missingStart=false;throw Error('START transport unknown before content ACK');}
    }
    return sendUnknown(id,msg,target);
  };
  assert.equal((await startUnknown.dispatch()).pending,true);
  assert.equal(startUnknown.store[startUnknown.key].fresh_restart.phase,'starting');
  assert(!startUnknown.events.some(e=>e[0]==='CANCEL_CHATGPT_JOB'));
  assert.equal((await startUnknown.dispatch()).ok,true);
  assert.equal(startUnknown.events.filter(e=>e[0]==='create').length,1);cases++;
  const changedDoc=restartSetup(),sendChanged=changedDoc.c.chrome.tabs.sendMessage;
  changedDoc.c.chrome.tabs.sendMessage=async(id,msg,target)=>{
    if(msg.type==='START_CHATGPT_JOB')throw Error('START ACK unknown');return sendChanged(id,msg,target);
  };
  assert.equal((await changedDoc.dispatch()).pending,true);
  changedDoc.c.chrome.scripting.executeScript=async request=>[
    {frameId:0,documentId:'unrelated-document',result:changedDoc.tabs[request.target.tabId].url}];
  assert.equal((await changedDoc.dispatch()).pending,true);
  assert.equal(changedDoc.events.filter(e=>e[0]==='create').length,1);
  assert(!changedDoc.events.some(e=>e[0]==='START_CHATGPT_JOB'));cases++;
  const lateBusy=restartSetup(),sendLate=lateBusy.c.chrome.tabs.sendMessage;
  lateBusy.c.chrome.tabs.sendMessage=async(id,msg,target)=>{
    if(msg.type==='VERIFY_STORY_IMAGE_REDO'&&lateBusy.events.some(e=>e[0]==='inject'))
      return {...msg,ok:true,allowed:false};
    return sendLate(id,msg,target);
  };
  await assert.rejects(lateBusy.dispatch(),error=>error.refresh_retry_safe===true);
  assert.equal(lateBusy.store['smartpostAIWebTab:chatgpt:STORY-413'],7);
  assert(!lateBusy.events.some(e=>['START_CHATGPT_JOB','CANCEL_CHATGPT_JOB'].includes(e[0])));cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
