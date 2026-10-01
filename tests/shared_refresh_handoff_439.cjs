// Actual background functions, simulated Chrome documents/storage only.
const assert=require('node:assert/strict'),vm=require('node:vm');
const {fn,source}=require('./shared_refresh_fixture_439.cjs');
const crypto=require('node:crypto').webcrypto;
let cases=0;
function fixture(options={}){
 let now=100000,doc='old',pending=0,cancelled=false,starts=0,readyProbes=0;
 let state={phase:'claimed',nonce:'nonce',...options.state};
 const events=[],store={};
 const c=vm.createContext({crypto,Date:{now:()=>now},setTimeout:(callback,ms)=>
   ms<=1000?setImmediate(()=>{now+=ms;callback();}):setTimeout(callback,ms/1000),
   clearTimeout:handle=>{clearTimeout(handle);clearImmediate(handle);},
   chrome:{tabs:{get:async id=>({id,status:'complete',url:'https://chatgpt.com/c/owned'}),
    reload:async()=>{events.push('reload');pending=2;if(options.reloadAckLost)return new Promise(()=>{});},
    sendMessage:async(id,message,target)=>{assert.equal(target.documentId,doc);events.push('start:'+doc);starts++;
      if(options.ackLost && starts===1)throw Error('Port closed after collector started');
      if(options.changeAfterAck && starts===1)doc='newer';
      return {ok:true,started:true,key:message.key,request_id:message.request_id,run_id:message.run_id};}},
    scripting:{executeScript:async request=>{
      if(request.files){assert.deepEqual(Array.from(request.target.documentIds),[doc]);events.push('inject:'+doc);
        if(options.changeDuringInjection && doc==='new'){doc='newer';throw Error('No document with id new');}return [];}
      const isReady=!!request.args;
      if(isReady){readyProbes++;events.push('ready:'+doc);}
      const current=doc;
      if(isReady && pending && --pending===0)doc='new';
      if(options.probeThrows && isReady && readyProbes===1)throw Error('Frame was removed');
      return [{frameId:0,documentId:current,result:{ready:true,draft:false,busy:false,has_media:false}}];}},
    storage:{local:{get:async key=>key===null?structuredClone(store):Object.fromEntries((Array.isArray(key)?key:[key]).map(k=>[k,structuredClone(store[k])])),
      set:async rows=>Object.assign(store,structuredClone(rows))}}},
 });
 vm.runInContext(['waitForAIRefreshReady','waitForAIRecoveryOperation','handoffAIRefreshDocument'].map(fn).join('\n'),c);
 const verify=async()=>{if(cancelled)throw Error('owner cancelled');};
 const start=async(id,check)=>{
   await check();
   try{await c.chrome.scripting.executeScript({target:{tabId:7,documentIds:[id]},files:['chatgpt.js']});}
   catch(error){await check();throw error;}
   await check();
   const send=()=>c.chrome.tabs.sendMessage(7,{type:'READ_ONLY_START'},{documentId:id});
   try{await send();}catch(error){await check();await send();}
   await check();
 };
 const run=(patch={})=>c.handoffAIRefreshDocument({tabId:7,verifyOwner:verify,read:async()=>state,
   write:async row=>{state={...state,...row};events.push('phase:'+state.phase);if(options.cancelAtPhase===state.phase)cancelled=true;},
   allowReload:true,beforeReload:async()=>{await verify();},start,onWait:async()=>{},...patch});
 return {c,store,events,run,state:()=>state,setDoc:value=>doc=value,cancel:()=>cancelled=true,starts:()=>starts,
   now:value=>now=value};
}
async function test(name,action){try{await action();cases++;}catch(error){error.message=name+': '+error.message;throw error;}}
async function controllers(){
 // Real completed-response controller including bridge ownership and its
 // durable budget, not merely the shared helper invoked in isolation.
 const f=fixture(),job='STORY-439',run='RUN-439',url='https://chatgpt.com/c/owned';
 const message={provider:'chatgpt',job_id:job,index:3,run_id:run,conversation_url:url,
   signature:'aabbccdd',context_id:'context',pending_request:'saved next prompt'};
 Object.assign(f.c,{BRIDGE:'offline',assertStoryCheckpointOwner:async()=>{},
   bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,context:{context_id:'context'},record:{phase:'preparing',request:'saved next prompt'}})}),
   reportWebActionProgress:async()=>{},
   startAIWebJob:async(j,reuse,provider,fresh,r,guard,id)=>{
     assert.equal(j,job);assert.equal(r,run);assert.equal(provider,'chatgpt');assert.equal(reuse,true);assert.equal(fresh,false);
     await guard(7);assert.equal(id,'new');f.events.push('resume:'+id);
   }});
 const originalSend=f.c.chrome.tabs.sendMessage;
 f.c.chrome.tabs.sendMessage=async(id,m,target)=>m.type==='VERIFY_CHATGPT_COMPLETED_RESPONSE_REFRESH'
   ?{ok:true,allowed:true,challenge:m.challenge,signature:m.signature}:originalSend(id,m,target);
 vm.runInContext('const completedResponseRefreshLocks=new Set();'+fn('refreshCompletedChatGPTResponse'),f.c);
 let ack=0;await f.c.refreshCompletedChatGPTResponse(message,{tab:{id:7}},()=>ack++);
 assert.equal(ack,1);assert.equal(f.events.filter(e=>e==='reload').length,1);
 assert(f.events.includes('ready:old'));assert(f.events.includes('resume:new'));
 const key=Object.keys(f.store)[0];assert.equal(f.store[key].phase,'resumed');
 await assert.rejects(()=>f.c.refreshCompletedChatGPTResponse(message,{tab:{id:7}},()=>{}),/used/);
 cases++;
 // Exact helper ACK. A generic busy/foreign acknowledgement must NEVER mark
 // the new document as having an active collector.
 for(const bad of [false,true]){
   const g=fixture(),key='helper-key';
   g.store[key]={alternative:true,provider:'chatgpt',phase:'rewrite_sent',alternative_stage:'image_sent',
     request_id:'request-439',run_id:run,helper_tab:7,owner_tab:8,job_id:job,index:3,request:'saved image prompt',
     empty_image_observation:{signature:'proof',conversation_url:url,samples:3}};
   Object.assign(g.c,{assertFlowRepairOwner:async()=>{},reportWebActionProgress:async()=>{}});
   g.c.chrome.tabs.sendMessage=async(id,m,target)=>{
     if(m.type==='VERIFY_FLOW_ALTERNATIVE_EMPTY')return {ok:true,challenge:m.challenge};
     assert.equal(m.request_id,'request-439');assert.equal(m.run_id,run);assert.equal(target.documentId,'new');
     g.events.push('helper:new');return bad?{ok:true,busy:true}:{ok:true,already_running:true,key,request_id:m.request_id,run_id:m.run_id};
   };
   vm.runInContext('const alternativeRefreshLocks=new Set();'+fn('refreshAlternativeEmpty'),g.c);
   const call=()=>g.c.refreshAlternativeEmpty({key,request_id:'request-439',signature:'proof',conversation_url:url},{tab:{id:7}},()=>{});
   if(bad){await assert.rejects(call,e=>e.code==='AI_RECOVERY_OPERATION_PENDING');assert.equal(g.store[key].empty_image_refresh.phase,'checking');}
   else {await call();assert.equal(g.store[key].empty_image_refresh.phase,'resumed');}
   assert.equal(g.events.filter(e=>e==='reload').length,1);cases++;
 }
}
async function resumeActualJob(){
 for(const provider of ['chatgpt','gemini']){
  const f=fixture(),job='STORY-439',run='RUN-439';f.setDoc('new');
  const url=provider==='chatgpt'?'https://chatgpt.com/c/owned':'https://gemini.google.com/app/1234567890abcdef';
  const prefix=provider==='chatgpt'?'smartflowPendingMotionRefresh':'smartflowGeminiReload';
  const key=`${prefix}:${job}:3:proof`,tabKey=`smartpostAIWebTab:${provider}:${job}`;
  f.store[key]={phase:'checking',handoff_kind:'job',job_id:job,provider,index:3,run_id:run,tab_id:7,
    nonce:'n',conversation_url:url,document_fence_version:1,previous_document_id:'old'};
  f.store[tabKey]=7;f.store['run:'+job]=run;
  const pkg={mode:'story',job:{id:job,image_ai_provider:provider},
    ai_resume:{required:true,stage:'motion',provider,index:3,conversation_url:url}};
  Object.assign(f.c,{BRIDGE:'offline',normalizeAIProvider:x=>x,aiRunStorageKey:id=>'run:'+id,
    AI_WEB:{[provider]:{name:provider,url:provider==='chatgpt'?'https://chatgpt.com/':'https://gemini.google.com/app',matches:[provider==='chatgpt'?'https://chatgpt.com/*':'https://gemini.google.com/*']}},
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:pkg})}),
    waitForTabComplete:async()=>{},isWebLoginUrl:()=>false});
  f.c.chrome.tabs.get=async id=>({id,status:'complete',url});
  f.c.chrome.tabs.update=async()=>{};
  let dispatched=0;
  f.c.chrome.tabs.sendMessage=async(id,message,target)=>{
    assert.equal(message.type,'START_CHATGPT_JOB');assert.equal(message.package.ai_resume.conversation_url,url);
    assert.equal(message.accept_existing_run,true);assert.equal(target.documentId,'new');dispatched++;
    if(dispatched===1)throw Error('ACK lost');
    return {ok:true,already_running:true};
  };
  vm.runInContext(fn('startAIWebJob'),f.c);
  await f.c.startAIWebJob(job,true,provider,false,run);
  assert.equal(dispatched,2);assert.equal(f.store[key].phase,'resumed');
  assert.equal(f.events.filter(e=>e==='reload').length,0);cases++;
 }
}
(async()=>{
 await test('old complete document cannot acknowledge reload',async()=>{
   const f=fixture();await f.run();assert(f.events.includes('ready:old'));
   assert(!f.events.includes('start:old'));assert.equal(f.state().previous_document_id,'old');
   assert.equal(f.state().document_id,'new');assert.equal(f.state().phase,'resumed');
 });
 for(const option of ['changeDuringInjection','changeAfterAck','probeThrows','ackLost','reloadAckLost'])
   await test(option,async()=>{const f=fixture({[option]:true});await f.run();
     assert.equal(f.events.filter(e=>e==='reload').length,1);assert.equal(f.state().phase,'resumed');
     assert(!f.events.includes('start:old'));
     if(option.startsWith('change'))assert.equal(f.state().document_id,'newer');
   });
 for(const phase of ['claimed','reload_requested','reloaded','checking'])
   await test('worker resume '+phase,async()=>{
     const f=fixture({state:{phase,document_fence_version:1,previous_document_id:'old'}});f.setDoc('new');
     await f.run({allowReload:false});assert.equal(f.events.filter(e=>e==='reload').length,0);
     assert.equal(f.state().document_id,'new');assert.equal(f.state().phase,'resumed');
   });
 await test('legacy claim stays read-only without invented navigation',async()=>{
   const f=fixture();await f.run({allowReload:false});assert.equal(f.events.filter(e=>e==='reload').length,0);
   assert.equal(f.state().legacy_unfenced,true);assert.equal(f.state().document_id,'old');
 });
 await test('cancel before mutation',async()=>{
   const f=fixture();f.cancel();await assert.rejects(()=>f.run(),/cancelled/);assert.equal(f.events.length,0);
 });
 await test('cancel during persisted claim',async()=>{
   const f=fixture({cancelAtPhase:'reload_requested'});await assert.rejects(()=>f.run(),/cancelled/);
   assert.equal(f.events.filter(e=>e==='reload').length,0);assert.equal(f.starts(),0);
 });
 await test('hung owner ACK is unknown not a failed provider Send',async()=>{
   const f=fixture();await assert.rejects(()=>f.run({verifyOwner:()=>new Promise(()=>{})}),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   assert.equal(f.events.length,0);
 });
 await test('hung telemetry cannot prevent new-document collection',async()=>{
   const f=fixture();await f.run({onWait:()=>new Promise(()=>{})});assert.equal(f.state().phase,'resumed');
 });
 await test('late collector guard retires after bounded unknown ACK',async()=>{
   const f=fixture();let lateGuard;
   await assert.rejects(()=>f.run({start:async(id,check)=>{lateGuard=check;await new Promise(()=>{});}}),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   assert.equal(f.state().phase,'checking');await assert.rejects(()=>lateGuard(),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   assert.equal(f.events.filter(e=>e==='reload').length,1);
 });
 await controllers();
 await resumeActualJob();
 await test('progress omitted image count and strictly ordered observation timestamp',async()=>{
   const sent=[],c=vm.createContext({BRIDGE:'offline',CLIENT_ID:'offline-client',Date:{now:()=>42},bridgeFetch:async(url,opts)=>{sent.push(JSON.parse(opts.body));return {ok:true};}});
   vm.runInContext(fn('reportWebActionProgress'),c);
   await c.reportWebActionProgress({scope:'chatgpt',jobId:'STORY-439',runId:'RUN-439',message:'recover'});
   await c.reportWebActionProgress({scope:'chatgpt',jobId:'STORY-439',runId:'RUN-439',imageCount:0,message:'reset explicit'});
   assert(!Object.hasOwn(sent[0],'image_count'));assert.equal(sent[1].image_count,0);
   assert(sent[1].observed_at_ms>sent[0].observed_at_ms);
 });
 console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
