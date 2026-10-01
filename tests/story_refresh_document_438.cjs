// Exact refresh/readiness/resume functions. Only simulated Chrome documents;
// no browser profile, provider Send, user receipt or external network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const fn=name=>{const at=source.search(new RegExp('(?:async )?function '+name+'\\('));assert(at>=0,name);return source.slice(at,source.indexOf('\n}',at)+2);};
const worker=new Function('require','__dirname',fs.readFileSync('tests/recovery_413.cjs','utf8').split('\n(async()=>')[0]+';return worker;')(require,__dirname);
function fixture(mode='delayed') {
  const w=worker(),row=w.store[w.key],events=[];
  row.status='awaiting_result';delete row.response_excerpt;
  w.tabs[7].status='complete';
  let now=1000000,doc='old-document',reload=false,probes=0,changed=false,lostAck=false;
  const collectors=new Set();
  Object.assign(w.c,{TextEncoder,Date:{now:()=>now},setTimeout:cb=>{now+=1000;queueMicrotask(cb);},
    chatGPTStoryResultRefreshLocks:new Set(),
    assertStoryCheckpointOwner:async()=>{
      assert.equal(w.store['run:STORY-413'],'RUN-413');
      if(w.store['smartflowChatGPTStoryRefreshCancelled:STORY-413']==='RUN-413')throw Error('cancelled');
    },reportWebActionProgress:async event=>events.push(['progress',event.step])});
  w.c.chrome.tabs.reload=async()=>{reload=true;events.push(['reload-enqueued',doc]);};
  w.c.chrome.scripting.executeScript=async options=>{
    if(options.files) {
      assert.deepEqual(Array.from(options.target.documentIds||[]),[doc],'injection pins the current document');
      events.push(['inject',doc]);
      if(['during_injection','injection_rejected'].includes(mode)&&!changed){doc='newer-document';changed=true;
        if(mode==='injection_rejected')throw Error('No document with given id');}
      return [{frameId:0,documentId:options.target.documentIds[0]}];
    }
    const readiness=String(options.func).includes('querySelectorAll');
    if(mode==='probe_rejected'&&!readiness&&doc==='new-document'&&!changed) {
      changed=true;doc='newer-document';throw Error('Frame with ID 0 was removed.');
    }
    if(readiness && reload) {
      probes++;
      if(probes===3 && mode!=='never_commits')doc='new-document';
      if(mode==='cancel'&&probes===3 || mode==='never_commits'&&probes===8)
        w.store['smartflowChatGPTStoryRefreshCancelled:STORY-413']='RUN-413';
    }
    const resultDoc=doc;
    events.push([readiness?'ready-probe':'document-probe',resultDoc]);
    if(mode==='after_readiness'&&readiness&&doc==='new-document'&&!changed){changed=true;doc='newer-document';}
    return [{frameId:0,documentId:resultDoc,result:readiness?{ready:true,busy:false,has_media:doc!=='old-document',draft:false}:w.tabs[7].url}];
  };
  w.c.chrome.tabs.sendMessage=async(id,message,options)=>{
    if(message.type==='VERIFY_CHATGPT_STORY_RESULT_REFRESH')return {...message,ok:true,allowed:true};
    if(message.type==='START_CHATGPT_JOB') {
      assert.equal(options?.documentId,doc,'START pins its acknowledged ready document');
      assert.notEqual(doc,'old-document','old active collector must never satisfy refreshed handoff');
      events.push(['START',doc]);
      const existing=collectors.has(doc);collectors.add(doc);
      if(mode==='ack_lost'&&!lostAck){lostAck=true;throw Error('ACK lost');}
      if(mode==='after_start'&&!changed){changed=true;doc='newer-document';}
      return {ok:true,started:!existing,already_running:existing};
    }
    return {ok:true};
  };
  vm.runInContext(fn('waitForAIRefreshReady')+'\n'+fn('refreshStoryChatGPTResult'),w.c);
  const message={provider:'chatgpt',job_id:'STORY-413',run_id:'RUN-413',index:15,
    receipt_identity:row.identity,send_nonce:row.send_nonce,prompt:row.result_proof.prompt,
    conversation_url:w.tabs[7].url,signature:'owned-idle',stable_samples:3,stagnant_since:900000,
    stalled_reason:'idle_answer_wait',recovery_protocol:2};
  return {w,events,collectors,message,setDoc:value=>doc=value,
    run:()=>w.c.refreshStoryChatGPTResult(message,{tab:w.tabs[7],documentId:'old-document'},()=>events.push(['ack'])),
    budget:()=>Object.entries(w.store).find(([key])=>key.startsWith('smartflowChatGPTStoryResultRefresh:'))?.[1]};
}
(async()=>{
  let cases=0;
  for(const mode of ['delayed','after_readiness','during_injection','injection_rejected','probe_rejected','after_start','ack_lost']) {
    const f=fixture(mode);await f.run();
    assert.equal(f.events.filter(e=>e[0]==='reload-enqueued').length,1,mode);
    assert.equal(f.events.some(e=>e[0]==='START'&&e[1]==='old-document'),false,mode);
    assert.equal(f.budget().phase,'resumed',mode);
    assert.equal(f.w.store[f.w.key].refresh_recovery.document_fence_version,1);
    assert.equal(f.w.store[f.w.key].refresh_recovery.previous_document_id,'old-document');
    assert.equal(f.w.store[f.w.key].send_nonce,'original-nonce');
    assert.equal(f.events.some(e=>e[0]==='progress'&&e[1]==='error'),false,mode);
    if(mode==='delayed')assert(f.events.filter(e=>e[0]==='ready-probe'&&e[1]==='old-document').length>=2);
    if(mode==='ack_lost'){assert.equal(f.events.filter(e=>e[0]==='START').length,2);assert.equal(f.collectors.size,1);}
    cases++;
  }
  for(const mode of ['cancel','never_commits']) {
    const f=fixture(mode);await f.run();
    assert.equal(f.events.filter(e=>e[0]==='START').length,0);
    assert.notEqual(f.budget()?.phase,'resumed');cases++;
  }
  // Restart after reload ACK: retain the old-document fence and collect in the
  // already loaded new document, without issuing another reload.
  for(const legacy of [false,true]) {
    const f=fixture();f.setDoc('new-document');
    f.w.pkg.browser_recovery.image_post_refresh_redo={version:1};
    f.w.store[f.w.key].refresh_recovery={version:1,phase:legacy?'checking':'reloaded',tab_id:7,
      conversation_url:f.w.tabs[7].url,send_nonce:'original-nonce',claimed_at:900000,ready_at:910000,
      ...(!legacy?{document_fence_version:1,previous_document_id:'old-document'}:{})};
    await f.w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
    assert.equal(f.events.filter(e=>e[0]==='reload-enqueued').length,0);
    assert.deepEqual(f.events.filter(e=>e[0]==='START'),[['START','new-document']]);
    assert.equal(f.w.store[f.w.key].refresh_recovery.phase,legacy?'legacy_recheck':'checking');
    assert.equal(f.w.store[f.w.key].send_nonce,'original-nonce');
    assert.equal(f.w.store[f.w.key].result_proof.prompt,'exact original request');cases++;
  }
  for(const mode of ['after_readiness','during_injection','injection_rejected','probe_rejected','after_start','ack_lost']) {
    const f=fixture(mode);f.setDoc('new-document');
    f.w.store[f.w.key].refresh_recovery={version:1,phase:'checking',tab_id:7,
      conversation_url:f.w.tabs[7].url,send_nonce:'original-nonce',claimed_at:900000,ready_at:910000};
    await f.w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
    assert.equal(f.events.filter(e=>e[0]==='reload-enqueued').length,0,mode);
    assert.equal(f.w.store[f.w.key].refresh_recovery.phase,'legacy_recheck',mode);
    assert.equal(f.events.some(e=>e[0]==='START'&&e[1]==='old-document'),false,mode);cases++;
  }
  // Claimed write survived but reload ACK did not. A changed document proves
  // navigation happened, so Continue performs no second reload.
  const claimed=fixture();claimed.setDoc('new-document');
  claimed.w.store[claimed.w.key].refresh_recovery={version:1,phase:'claimed',tab_id:7,
    conversation_url:claimed.w.tabs[7].url,send_nonce:'original-nonce',claimed_at:900000,
    document_fence_version:1,previous_document_id:'old-document'};
  await claimed.w.c.startAIWebJob('STORY-413',true,'chatgpt',false,'RUN-413');
  assert.equal(claimed.events.filter(e=>e[0]==='reload-enqueued').length,0);
  assert.equal(claimed.w.store[claimed.w.key].refresh_recovery.phase,'checking');cases++;
  console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
