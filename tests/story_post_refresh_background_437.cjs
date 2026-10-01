// Actual background functions with isolated Chrome storage/tab fixtures. No provider requests.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const worker=new Function('require','__dirname',fs.readFileSync('tests/recovery_413.cjs','utf8').split('\n(async()=>')[0]+';return worker;')(require,__dirname);
const refreshFixture=new Function('require','__dirname',fs.readFileSync('tests/story_image_refresh_background_harness.js','utf8').split('(async () =>')[0]+';return fixture;')(require,__dirname);
const contentFixture=new Function('require',fs.readFileSync('tests/story_refresh_redo_437.cjs','utf8').split('(async()=>')[0]+';return {fixture,complete};')(require);
function setup(options={}) {
  const w=worker(options),row=w.store[w.key],now=Date.now();
  w.pkg.browser_recovery.image_post_refresh_redo={version:1,stable_check_ms:30000,min_stable_samples:3};
  Object.assign(row,{recovery_protocol:2,retry_kind:'missing_after_refresh',response_excerpt:'',
    refresh_recovery:{version:1,phase:'checking',send_nonce:row.send_nonce,
      document_fence_version:1,previous_document_id:'old-document',document_id:'new-document',
      conversation_url:row.result_proof.conversation_url,claimed_at:now-90000,ready_at:now-45000},
    post_refresh_evidence:{version:1,receipt_identity:row.identity,send_nonce:row.send_nonce,
      conversation_url:row.result_proof.conversation_url,refresh_claimed_at:now-90000,
      observed_at:now,stable_since:now-35000,stable_samples:4,signature:'exact-ready-idle-absence',
      result_reason:'request_missing',page_ready:true,history_ready:true,response_active:false,
      draft_present:false,at_end:true,reload_completed:true}});
  const send=w.c.chrome.tabs.sendMessage;
  w.c.chrome.tabs.sendMessage=async(id,msg)=>{
    if(msg.type==='VERIFY_STORY_IMAGE_REDO') {
      w.events.push(['redo_guard',id]);
      return options.guard ? options.guard(msg,w) : {...msg,ok:true,allowed:true};
    }
    return send(id,msg);
  };
  w.c.chrome.tabs.query=async()=>Object.values(w.tabs);
  return w;
}
(async()=>{
  let cases=0,w=setup();
  assert.equal(w.c.restartableStoryServiceReceipt(w.store[w.key],'STORY-413',15),true);cases++;
  w.store[w.key].post_refresh_evidence.result_reason='waiting_response';
  assert.equal(w.c.restartableStoryServiceReceipt(w.store[w.key],'STORY-413',15),true);cases++;
  for(const mutation of [
    row=>row.post_refresh_evidence.stable_samples=2,
    row=>row.post_refresh_evidence.observed_at=row.post_refresh_evidence.stable_since+29999,
    row=>row.post_refresh_evidence.response_active=true,
    row=>row.post_refresh_evidence.draft_present=true,
    row=>row.post_refresh_evidence.history_ready=false,
    row=>row.post_refresh_evidence.reload_completed=false,
    row=>row.post_refresh_evidence.at_end=false,
    row=>row.post_refresh_evidence.send_nonce='other',
    row=>row.post_refresh_evidence.conversation_url='https://chatgpt.com/c/other',
    row=>row.post_refresh_evidence.result_reason='policy_blocked',
    row=>row.post_refresh_evidence.signature='',
    row=>row.refresh_recovery.phase='claimed',
    row=>row.response_excerpt='Please log in',
    row=>row.response_excerpt='policy violation',
    row=>row.image_url='saved.png',
  ]) {
    w=setup();mutation(w.store[w.key]);
    assert.equal(w.c.restartableStoryServiceReceipt(w.store[w.key],'STORY-413',15),false);cases++;
  }
  w=setup();await w.run();await w.run();
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);
  assert(w.events.find(e=>e[0]==='create')[1].startsWith('about:blank#smartflow-story-recovery='));
  assert(w.events.filter(e=>e[0]==='redo_guard').length>=3);
  const archived=Object.entries(w.store).find(([k])=>k.includes(':failed:'))[1];
  assert.equal(archived.result_proof.prompt,'exact original request');
  assert.equal(archived.send_nonce,'original-nonce');cases++;
  w=setup({guard:()=>({ok:true,allowed:false})});
  await assert.rejects(w.run(),error=>/สถานะฉากเปลี่ยน/.test(error.message)&&error.refresh_retry_safe===true);
  assert.equal(w.events.filter(e=>e[0]==='create').length,0);cases++;
  w=setup();delete w.pkg.browser_recovery.image_post_refresh_redo;
  await assert.rejects(w.run(),/ไม่รองรับ/);assert.equal(w.events.filter(e=>e[0]==='create').length,0);cases++;
  // Late result/busy detected by final live guard cancels allocation.
  let guards=0;w=setup({guard:msg=>({...msg,ok:true,allowed:++guards<4})});
  await assert.rejects(w.run(),error=>/สถานะฉากเปลี่ยน/.test(error.message)&&error.refresh_retry_safe===true);
  assert.equal(w.store[w.key].fresh_restart.phase,'claimed');
  assert.equal(w.events.filter(e=>e[0]==='create').length,0);cases++;
  // tabs.create succeeded but worker lost its reply: use the uniquely marked
  // unsubmitted tab after restart instead of allocating a duplicate.
  w=setup();const create=w.c.chrome.tabs.create;let lost=true;
  w.c.chrome.tabs.create=async options=>{const tab=await create(options);if(lost){lost=false;throw Error('lost create ACK');}return tab;};
  await assert.rejects(w.run(),/lost create ACK/);
  assert.equal(w.store[w.key].fresh_restart.phase,'creating');
  await w.run();assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  // New Continue run reuses a consumed successor despite the desktop old URL.
  w=setup({onStart:(store,key)=>{store[key]={...store[key],status:'awaiting_result',send_phase:'dispatching',
    run_id:store['run:STORY-413'],fresh_restart:{...store[key].fresh_restart,phase:'consumed'}};}});
  await w.run();w.store['run:STORY-413']='RUN-NEW';
  await w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-NEW');
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  // No desktop ai_resume does not erase the durable pending successor route.
  w.pkg.ai_resume=null;await w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-NEW');
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  // Result arrived on the successor but its checkpoint ACK was lost. Its
  // generated receipt still belongs to that tab, never to desktop's old URL.
  for(const saved of [false,true]) {
    w=setup({onStart:(store,key)=>{store[key]={...store[key],status:'generated',image_url:'https://chatgpt.com/backend-api/files/final-image',
      fresh_restart:{...store[key].fresh_restart,phase:'consumed'}};}});
    await w.run();
    if(saved)w.pkg.checkpoint_images.push({index:15,url:'http://fixture/saved/scene_15.png'});
    const receiptBefore=JSON.stringify(w.store[w.key]);
    await w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
    assert.equal(w.events.filter(e=>e[0]==='create').length,1);
    assert.equal(w.store['smartpostAIWebTab:chatgpt:STORY-413'],8);
    assert.equal(JSON.stringify(w.store[w.key]),receiptBefore);
    assert(!w.events.some(e=>e[0]==='create'&&String(e[1]).includes('/c/failed')));cases++;
  }
  // A checkpointed old generated receipt cannot compete with a newer pending
  // successor. The later scene remains the only dispatch owner.
  w=setup({onStart:(store,key)=>{store[key]={...store[key],status:'awaiting_result',
    fresh_restart:{...store[key].fresh_restart,phase:'consumed'}};}});
  await w.run();w.pkg.checkpoint_images.push({index:14,url:'http://fixture/saved/scene_14.png'});
  w.store['smartpostStoryGeneratedImage:chatgpt:STORY-413:14']={...w.store[w.key],scene_index:14,
    status:'generated',image_url:'https://chatgpt.com/backend-api/files/old-image',fresh_restart:{phase:'consumed',tab_id:6}};
  await w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  // Completed reload survives worker restart; resume only the same original
  // conversation to check its result, without another reload or allocation.
  w=setup();Object.assign(w.store[w.key],{status:'awaiting_result',send_phase:'dispatching'});
  Object.assign(w.store[w.key].refresh_recovery,{phase:'reloaded',tab_id:7});
  let readiness=0,starts=[];
  w.tabs[7].status='complete';
  w.c.chrome.scripting.executeScript=async()=>[{frameId:0,documentId:'new-document',result:w.tabs[7].url}];
  w.c.waitForAIRefreshReady=async(id,verify)=>{assert.equal(id,7);await verify();readiness++;return {documentId:'new-document'};};
  w.c.chrome.tabs.sendMessage=async(id,message)=>{starts.push({id,message});return {ok:true};};
  await w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
  assert.equal(readiness,2);assert.equal(w.store[w.key].refresh_recovery.phase,'checking');
  assert.equal(starts.at(-1).id,7);assert.equal(w.events.filter(e=>e[0]==='create').length,0);cases++;
  // Content monitor's actual evidence must satisfy the background gate for
  // absent request, accepted request without answer and completed unusable text.
  for(const kind of ['missing','waiting','unusable']) {
    const cf=contentFixture.fixture({kind}),result=await contentFixture.complete(cf);
    w=setup();Object.assign(w.store[w.key],{identity:cf.receipt.identity,send_nonce:cf.receipt.send_nonce,
      result_proof:cf.receipt.result_proof,refresh_recovery:cf.receipt.refresh_recovery,
      retry_kind:result.retryKind,post_refresh_evidence:result.postRefreshEvidence});
    assert.equal(w.c.restartableStoryServiceReceipt(w.store[w.key],'STORY-413',15),true,kind);cases++;
  }
  // Dispatching without captured message ID may refresh, never become accepted
  // until the content reader actually finds its exact request.
  let f=refreshFixture();delete f.storage[f.key].result_proof.request_message_id;
  delete f.storage[f.key].result_proof.request_turn_id;f.storage[f.key].send_phase='dispatching';
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,1);
  assert.equal(f.storage[f.key].send_phase,'dispatching');
  assert.equal(f.storage[f.key].refresh_recovery.phase,'checking');
  assert.equal(f.storage[f.key].refresh_recovery.ready_at,1000000);cases++;
  // v436 consumed a legacy reload without the new ready-check receipt. Its
  // budget must not strand the new protocol; perform one guarded v2 recheck.
  f=refreshFixture();await f.dispatch();
  assert.equal(f.storage[f.key].refresh_recovery,undefined);
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,2);
  assert.equal(f.storage[f.key].refresh_recovery.phase,'checking');
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,2);cases++;
  // Changed live page, cancellation or receipt identity never authorizes reload.
  for(const mode of ['busy','cancel','wrong_nonce']) {
    f=refreshFixture({guard:reply=>{if(mode==='busy')reply.allowed=false;}});
    if(mode==='cancel')f.storage['smartflowChatGPTStoryRefreshCancelled:STORY-REFRESH']='RUN-CURRENT';
    if(mode==='wrong_nonce')f.storage[f.key].send_nonce='changed';
    await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
    assert.equal(f.events.filter(x=>x==='reload').length,0);cases++;
  }
  // Durable claimed phase after worker death can recheck once on an explicit
  // new run, but a repeated callback in that same run cannot reload again.
  f=refreshFixture({onReload:()=>{throw Error('worker stopped before reload ACK');}});
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.storage[f.key].refresh_recovery.phase,'claimed');
  f.storage['smartpostAIWebRun:STORY-REFRESH']='RUN-NEW';
  f.context.chrome.tabs.reload=async()=>f.events.push('reload');
  await f.dispatch({run_id:'RUN-NEW',recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,2);
  assert.equal(f.storage[f.key].refresh_recovery.resumed_recheck,true);
  await f.dispatch({run_id:'RUN-NEW',recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,2);cases++;
  // Busy/result appeared in the final pre-reload guard: it is known that no
  // reload happened, so persist a deferred claim and keep passively checking.
  f=refreshFixture({guard:(reply,count)=>{if(count===2)reply.allowed=false;}});
  const deferredReceipt=JSON.parse(JSON.stringify(f.storage[f.key]));
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,0);
  assert.equal(f.replies.at(-1).retry_safe,true);
  assert.deepEqual(f.storage[f.key],deferredReceipt,'deferred refresh restores content-owned receipt');
  assert(Object.values(f.storage).some(row=>row?.phase==='guard_deferred'
    && JSON.stringify(row.preclaim_receipt)===JSON.stringify(deferredReceipt)));
  await f.dispatch({recovery_protocol:2,stalled_reason:'request_dom_missing',stagnant_since:940000});
  assert.equal(f.events.filter(x=>x==='reload').length,1);
  assert.equal(f.storage[f.key].refresh_recovery.phase,'checking');cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
