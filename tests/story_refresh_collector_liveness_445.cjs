// Actual-source, offline regression: a refresh START ACK alone is not a
// collector heartbeat. Never send another provider request from this watchdog.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const background=fs.readFileSync('browser_extension/background.js','utf8');

async function reportNeverResolvesCase(){
  const start=content.indexOf('  let lastObservationMs = 0;');
  const end=content.indexOf('  function composer()',start);
  assert(start>=0&&end>start);
  let messages=0;
  const scope={activeCoverRequest:null,activeRepairKey:'',activeJobId:'STORY-test',
    activeRunId:'RUN',PROVIDER_KEY:'chatgpt',location:{href:'https://chatgpt.com/c/test'},
    statusBanner:()=>({textContent:''}),Date:{now:()=>200000},Math,
    chrome:{runtime:{sendMessage:()=>{messages++;return new Promise(()=>{});}}},
    setTimeout:callback=>{queueMicrotask(callback);return 1;},clearTimeout:()=>{}};
  vm.runInNewContext(content.slice(start,end)+'\nthis.report=report;',scope);
  await scope.report('image_refresh_check','checking',8,{scene_index:9});
  assert.equal(messages,1,'observational message can hang but monitor must continue');
}

async function unrelatedTickCannotStarveCollectorCase(){
  const tickStart=background.indexOf('async function extensionTick()');
  const tickEnd=background.indexOf('function runExtensionTickOnce()',tickStart);
  const auditStart=background.indexOf('function runStoryRefreshCollectorAudit()');
  const auditEnd=background.indexOf('async function noteStoryRefreshCollectorPulse(',auditStart);
  assert(tickStart>=0&&tickEnd>tickStart&&auditStart>=0&&auditEnd>auditStart);
  const code='let extensionTickPromise=null;let storyRefreshCollectorAuditPromise=null;\n'
    +background.slice(tickStart,tickEnd)+background.slice(auditStart,auditEnd)
    +'\nthis.extensionTick=extensionTick;';
  let audits=0;
  const scope={Promise,heartbeat:async()=>({updateRequired:false}),
    resolvePendingWebAction:async()=>{},getMetaVideoAdapter:()=>({tick:()=>new Promise(()=>{})}),
    pollCommands:async()=>{},auditStoryRefreshCollectors:async()=>{audits++;}};
  vm.runInNewContext(code,scope);
  scope.extensionTick();await new Promise(setImmediate);
  assert.equal(audits,1);
  scope.extensionTick();await new Promise(setImmediate);
  assert.equal(audits,2,'later heartbeat audits despite a permanently hung Meta tick');

  let lockedAudits=0;
  const locked={...scope,auditStoryRefreshCollectors:()=>{
    lockedAudits++;return new Promise(()=>{});
  }};
  vm.runInNewContext(code,locked);
  locked.extensionTick();await new Promise(setImmediate);
  locked.extensionTick();await new Promise(setImmediate);
  assert.equal(lockedAudits,1,'one in-flight audit must not spawn concurrent collectors');
}

function fixture({active=false,desktopActive=true,wrongDocument=false}={}){
  let now=200000,starts=0,pings=0,ownerChecks=0,providerSubmissions=0;
  const jobId='STORY-test',index=9,runId='RUN',url='https://chatgpt.com/c/test';
  const receiptKey=`smartpostStoryGeneratedImage:chatgpt:${jobId}:${index}`;
  const receipt={status:'awaiting_result',job_id:jobId,scene_index:index,run_id:runId,
    identity:'receipt-9',send_nonce:'nonce-9',image_url:null,
    refresh_recovery:{version:1,phase:'checking',document_fence_version:1,
      document_id:'new-doc',previous_document_id:'old-doc',ready_at:1000,
      tab_id:7,conversation_url:url}};
  const store={[receiptKey]:receipt,[`smartpostAIWebRun:${jobId}`]:runId,
    [`smartpostAIWebTab:chatgpt:${jobId}`]:7};
  const chrome={storage:{local:{get:async key=>key===null?{...store}:Array.isArray(key)
    ?Object.fromEntries(key.map(item=>[item,store[item]])):{[key]:store[key]},
    set:async values=>Object.assign(store,values)}},
    tabs:{get:async()=>({id:7,url,status:'complete'}),sendMessage:async()=>{
      pings++;return {ok:true,active,observed_at_ms:active?now:0};}},
    scripting:{executeScript:async()=>[{frameId:0,documentId:wrongDocument?'other-doc':'new-doc',result:url}]}};
  const scope={chrome,Date:{now:()=>now},Number,String,Object,Error,Promise,RegExp,encodeURIComponent,
    BRIDGE:'http://127.0.0.1:8765',setTimeout,clearTimeout,bridgeFetch:async address=>{
      if(address.includes('/api/extension/run-owner?')){
        ownerChecks++;return {ok:true,json:async()=>({ok:true,active:desktopActive})};
      }
      return {ok:true,json:async()=>({ok:true,package:{
        ai_resume:{required:true,stage:'image',index,conversation_url:url}}})};
    },
    startAIWebJob:async(job,reuse,provider,fresh,run,verify,document)=>{
      assert.equal(job,jobId);assert.equal(reuse,true);assert.equal(provider,'chatgpt');
      assert.equal(fresh,false);assert.equal(run,runId);assert.equal(document,'new-doc');
      await verify(7);starts++;},
    providerSend:()=>providerSubmissions++};
  const start=background.indexOf("const STORY_REFRESH_COLLECTOR_PULSE =");
  const end=background.indexOf('async function refreshStoryChatGPTResult(',start);
  assert(start>=0&&end>start);
  vm.runInNewContext(background.slice(start,end)
    +'\nthis.audit=auditStoryRefreshCollectors;this.pulse=noteStoryRefreshCollectorPulse;',scope);
  return {scope,store,receipt,jobId,index,runId,url,now:value=>{now=value;},
    counts:()=>({starts,pings,ownerChecks,providerSubmissions})};
}

(async()=>{
  await reportNeverResolvesCase();
  await unrelatedTickCannotStarveCollectorCase();
  const silent=fixture();
  await silent.scope.audit();
  assert.equal(silent.counts().starts,1,'START ACK without any later content pulse must reattach same document');
  assert.equal(silent.counts().providerSubmissions,0);
  silent.now(230001);await silent.scope.audit();
  assert.equal(silent.counts().starts,1,'cooldown prevents repeated reattachment');

  const active=fixture({active:true});await active.scope.audit();
  assert.equal(active.counts().starts,0,'live collector is never replaced on silence alone');
  const changed=fixture({wrongDocument:true});await changed.scope.audit();
  assert.equal(changed.counts().starts,0,'another document cannot inherit refresh owner');
  const paused=fixture({desktopActive:false});await paused.scope.audit();
  assert.equal(paused.counts().starts,0,'desktop restart or paused run cannot reattach from stale Extension storage');
  assert.equal(paused.counts().pings,0,'paused desktop owner stops before messaging the page');

  const healthy=fixture();
  await healthy.scope.pulse({job_id:healthy.jobId,run_id:healthy.runId,scene_index:healthy.index,
    recovery_phase:'checking',send_nonce:'nonce-9'},
    {tab:{id:7},documentId:'new-doc'});
  await healthy.scope.audit();
  assert.equal(healthy.counts().starts,0,'fresh exact collector pulse blocks reattachment');
  assert.equal(healthy.counts().providerSubmissions,0);
  console.log('Story refresh collector liveness: bounded progress, silent START, active/wrong-document/pulse guards passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
