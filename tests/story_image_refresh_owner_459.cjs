// Isolated actual-source reproduction. No Chrome, network, or user storage.
// The proposed patch is applied to a VM string only; source files are read-only.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=fs.existsSync(path.join(__dirname,'../browser_extension/background.js'))
  ?path.resolve(__dirname,'..'):path.resolve(__dirname,'../..');process.chdir(root);
const mode=process.argv[2]||'current';
assert(['baseline','proposed','current'].includes(mode));
const clone=value=>structuredClone(value);
const originalBackground=fs.readFileSync('browser_extension/background.js','utf8').replace(/\r\n/g,'\n');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8').replace(/\r\n/g,'\n');
const part=(source,a,b)=>{const start=source.indexOf(a),end=source.indexOf(b,start+a.length);
  assert(start>=0&&end>start,a);return source.slice(start,end);};
const func=(source,name)=>{const start=source.search(new RegExp('(?:async )?function '+name+'\\('));
  assert(start>=0,name);return source.slice(start,source.indexOf('\n}',start)+2);};
function patchedBackground(){
  let source=originalBackground;
  const patch=fs.readFileSync(path.join(__dirname,'background-rollback.patch'),'utf8').replace(/\r\n/g,'\n');
  for(const section of patch.split(/^@@\n/m).slice(1)){
    const rows=section.split('\n').filter(line=>line&&' +-'.includes(line[0])&&!line.startsWith('***'));
    const before=rows.filter(line=>line[0]!=='+').map(line=>line.slice(1)).join('\n');
    const after=rows.filter(line=>line[0]!=='-').map(line=>line.slice(1)).join('\n');
    assert(source.includes(before),'patch context exists');
    assert.equal(source.indexOf(before),source.lastIndexOf(before),'patch context is unique');
    source=source.replace(before,after);
  }
  return source;
}
const fixtureSource=fs.readFileSync('tests/story_refresh_loop_background_456.cjs','utf8').split('(async()=>{')[0];
const setup=new Function('require','__dirname',fixtureSource+';return setup;')(require,path.join(root,'tests'));
let checks=0;
const eq=(a,b,label)=>{assert.deepEqual(a,b,label);checks++;};
async function fixture({patched=false,child=false,restore=false,lostAck=false,rollbackAckLoss=false,mutate=null}={}){
  let state='waiting_response',busy=true,now=940000,ctx,receipt,monitor;
  const reports=[],messages=[];
  const f=setup({guard:(reply,count)=>{
    reply.allowed=ctx.storyImageRefreshGuard({...f.message,challenge:reply.challenge});
  },onDelay:()=>{state='image_ready';busy=false;if(mutate)mutate(f,ctx);}});
  if(patched&&mode!=='current')vm.runInContext(func(patchedBackground(),'refreshStoryChatGPTResult'),f.context);
  if(rollbackAckLoss){
    let pending=false;
    const get=f.context.chrome.storage.local.get,set=f.context.chrome.storage.local.set;
    f.context.chrome.storage.local.set=async rows=>{
      await set(rows);
      if(Object.values(rows).some(row=>row?.phase==='guard_deferred'&&row.preclaim_receipt))pending=true;
    };
    f.context.chrome.storage.local.get=async keys=>{
      if(pending){pending=false;throw Error('synthetic rollback readback ACK lost');}
      return get(keys);
    };
  }
  const pkg={job:{id:f.message.job_id},request:{image_files:['synthetic/reference.png']},image_urls:['synthetic-reference'],
    browser_recovery:{version:1,image_post_refresh_redo:{version:1}}};
  const promptIdentity=[f.message.prompt,'','',''];
  const frame={},image={src:'https://chatgpt.com/backend-api/estuary/content?id=synthetic-owned',complete:true,naturalWidth:941,naturalHeight:1672};
  const observation=()=>({request:{frame},signature:state,busy,completedControl:false,
    stalledReason:state==='waiting_response'?'idle_answer_wait':'',state:{reason:state,images:state==='image_ready'?[image]:[],turn:null}});
  const local={get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(key=>[key,clone(f.storage[key])])),
    set:async rows=>Object.assign(f.storage,clone(rows))};
  ctx=vm.createContext({Date:{now:()=>now},Math,Number,Boolean,String,Error,JSON,Set,crypto:crypto.webcrypto,
    PROVIDER_KEY:'chatgpt',IS_GEMINI:false,activeJobId:f.message.job_id,activeRunId:f.message.run_id,cancelRequested:false,
    location:{href:f.message.conversation_url},storyImageRefreshGuard:null,
    assertNotCancelled:()=>{if(ctx.cancelRequested)throw Error('cancelled');},
    storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),
    report:async(...args)=>reports.push(args),revealChatGPTAnswer:async()=>false,
    storyImageWaitObservation:observation,chatGPTStoryImageSnapshot:()=>observation().state,
    chatGPTStoryRequest:()=>({frame}),chatGPTConversationFrames:()=>[frame],chatGPTFrameUser:x=>x,
    chatGPTFrameAssistant:()=>null,composer:()=>({}),composerText:()=>'',
    chatGPTComposerAttachmentState:()=>({count:0,busy:false,failed:false}),
    storyImagePostRefreshPageReady:()=>true,retryableCompletedImageText:()=>false,confirmedStoryImageServiceError:()=>false,
    stopButtonVisible:()=>busy,storyImageAssetKey:image=>image.src,
    imageDataFromUrl:async()=> 'data:image/png;base64,synthetic-result',
    sleep:async ms=>{now+=ms;if(now>1050000)throw Error('bounded virtual wait exhausted');},
    chrome:{storage:{local},runtime:{sendMessage:async message=>{
      messages.push(clone(message));assert.equal(message.type,'RELOAD_CHATGPT_STORY_RESULT');
      Object.assign(f.message,clone(message));await f.dispatch();
      if(lostAck)throw Error('synthetic transport ACK lost');
      return clone(f.replies.at(-1));
    }}}
  });
  vm.runInContext(part(content,'  function sameStoryImageReceipt(','  function storyLocalRefusalFallbackAllowed(')
    +part(content,'  function storyImageLoopOwnerNonce(','  function storyImageWaitObservation(')
    +part(content,'  function createStoryImageWaitMonitor(','  function createStoryImageReceipt(')
    +part(content,'  function createStoryImageReceipt(','  function largeAssistantImages('),ctx);
  delete f.storage[f.key];
  receipt=ctx.createStoryImageReceipt(pkg,12,promptIdentity,11);
  await receipt.begin();await receipt.dispatching(f.message.prompt,{conversation_url:f.message.conversation_url});
  await receipt.submitted(f.message.prompt,{request_message_id:'synthetic-owned-request',request_turn_id:'conversation-turn-24'});
  Object.assign(f.message,{receipt_identity:f.storage[f.key].identity,send_nonce:f.storage[f.key].send_nonce,
    result_owner_nonce:f.storage[f.key].send_nonce});
  if(child){
    f.child();
    // An actual Resume reads the persisted child ownership before monitoring.
    restore=true;
  }
  const baseline=clone(f.storage[f.key]);
  if(restore){
    ctx.createStorySameChatReminder=()=>({resume:async()=>{}});
    ctx.storyImagePostRefreshEvidenceValid=()=>false;
    // Real restore and monitor; child preparation/Send never runs in this fixture.
    ctx.recoverOwnedStoryImage=async(proof,_owner,context)=>{
      monitor=ctx.createStoryImageWaitMonitor(proof.prompt,proof,12,11,true);
      for(const tick of [940000,970000,1000000]){now=tick;await monitor.observe();}
      await monitor.observe();return image;
    };
  }else monitor=ctx.createStoryImageWaitMonitor(baseline.result_proof.prompt,baseline.result_proof,12,11,true);
  let error=null;
  try{
    if(restore)await receipt.restore();
    else{
      for(const tick of [940000,970000,1000000]){now=tick;await monitor.observe();}
      const observed=await monitor.observe();eq(observed.state.reason,'image_ready','late owned image visible');
      await receipt.generated(image);
    }
  }catch(value){error=value;}
  return {f,ctx,receipt,baseline,image,error,reports,messages,
    budget:()=>Object.values(f.storage).find(row=>row?.phase==='guard_deferred'&&row?.identity===baseline.identity)};
}
async function main(){
  const results=[];
  for(const restore of [false,true])for(const child of restore?[false,true]:[false]){
    if(mode!=='current'){
    const broken=await fixture({restore,child});
    eq(broken.error?.code,'STORY_IMAGE_RECEIPT_REVIEW','current source fails receipt save');
    assert.match(broken.error.message,/generated\/owner_changed/);checks++;
    eq(broken.f.replies.at(-1).refresh_reason,'live_guard_changed','background veto reason');
    eq(broken.f.storage[broken.f.key].refresh_recovery.phase,'guard_deferred','only refresh metadata changed');
    const withoutRefresh=clone(broken.f.storage[broken.f.key]);delete withoutRefresh.refresh_recovery;
    eq(withoutRefresh,broken.baseline,'all owner fields unchanged');
    eq(broken.f.events.includes('reload'),false,'no reload');
    results.push({mode:child?'restored-child':restore?'restored-original':'fresh-original',current:'reproduced generated/owner_changed'});
    }
    if(mode==='baseline')continue;
    for(const lostAck of [false,true]){
      const fixed=await fixture({patched:true,restore,child,lostAck});
      eq(fixed.error,null,'proposed rollback allows existing image save');
      eq(fixed.f.storage[fixed.f.key].status,'generated','image saved');
      eq(fixed.budget().preclaim_receipt,fixed.baseline,'durable original receipt retained');
      eq(fixed.f.storage[fixed.f.key].send_nonce,fixed.baseline.send_nonce,'original nonce preserved');
      eq(fixed.f.storage[fixed.f.key].result_proof,fixed.baseline.result_proof,'result owner proof preserved');
      eq(fixed.f.events.includes('reload'),false,'proposed rollback performs no reload');
      eq(fixed.messages.length,1,'one refresh request; no Send or fresh scene');
    }
    const unknown=await fixture({patched:true,restore,child,rollbackAckLoss:true});
    eq(unknown.error,null,'rollback readback uncertainty still permits original image collection');
    eq(unknown.f.replies.at(-1).retry_safe,false,'unknown rollback ACK never authorizes repeat refresh');
    eq(unknown.f.storage[unknown.f.key].status,'generated','existing image survives rollback ACK loss');
  }
  if(mode!=='baseline'){
  for(const [label,mutate] of Object.entries({
    run:f=>f.storage[f.key].run_id='foreign-run',nonce:f=>f.storage[f.key].send_nonce='foreign-nonce',
    proof:f=>f.storage[f.key].result_proof.request_message_id='foreign-message',
    generated:f=>Object.assign(f.storage[f.key],{status:'generated',image_url:'foreign-image'}),
    successor:f=>f.storage[f.key].fresh_restart={token:'foreign-successor',phase:'starting'},
    cancel:(f,c)=>{f.storage['smartflowChatGPTStoryRefreshCancelled:'+f.message.job_id]=f.message.run_id;c.cancelRequested=true;},
    document:f=>{f.context.chrome.scripting.executeScript=async()=>[{frameId:0,documentId:'different-document',result:f.sender.tab.url}];},
    documentAwaitWriter:f=>{f.context.chrome.scripting.executeScript=async()=>{
      f.storage[f.key].result_proof.request_message_id='concurrent-writer';
      return [{frameId:0,documentId:'document-0',result:f.sender.tab.url}];
    };},
    reloaded:f=>{f.storage[f.storage[f.key].refresh_recovery.budget_key].phase='reloaded';},
    checking:f=>{f.storage[f.storage[f.key].refresh_recovery.budget_key].phase='checking';},
  })){
    const f=await fixture({patched:true,mutate});
    assert(f.error,label+' cannot save over changed state');checks++;
    eq(f.f.events.includes('reload'),false,label+' no reload');
    eq(f.budget(),undefined,label+' does not rollback to old owner');
  }
  // Retry from a durable, explicitly not-reloaded deferred claim. Current
  // owner/tab/document checks must survive continuation and worker restart.
  for(const scenario of ['same-run','new-run','new-document','stale-sender','malformed-baseline','changed-baseline','cancelled']){
    const f=setup({guard:(reply,count)=>{if(count===2)reply.allowed=false;}});
    if(mode!=='current')vm.runInContext(func(patchedBackground(),'refreshStoryChatGPTResult'),f.context);
    const baseline=clone(f.storage[f.key]);
    await f.dispatch();
    eq(f.replies.at(-1).retry_safe,true,scenario+' confirmed deferred rollback');
    eq(f.storage[f.key],baseline,scenario+' exact original receipt restored');
    const budgetKey=Object.keys(f.storage).find(key=>key.startsWith('smartflowChatGPTStoryResultRefresh:'));
    if(scenario==='new-run'){
      f.message.run_id='EXPLICIT-CONTINUE-RUN';
      f.storage['smartpostAIWebRun:'+f.message.job_id]=f.message.run_id;
    }
    if(scenario==='new-document'||scenario==='stale-sender'){
      f.context.chrome.scripting.executeScript=async()=>[{frameId:0,documentId:'manual-new-document',result:f.sender.tab.url}];
      if(scenario==='new-document')f.sender.documentId='manual-new-document';
    }
    if(scenario==='malformed-baseline')f.storage[budgetKey].preclaim_receipt=null;
    if(scenario==='changed-baseline')f.storage[f.key].result_proof.request_message_id='foreign';
    if(scenario==='cancelled')f.storage['smartflowChatGPTStoryRefreshCancelled:'+f.message.job_id]=f.message.run_id;
    await f.dispatch();
    const allowed=['same-run','new-run','new-document'].includes(scenario);
    eq(f.events.filter(item=>item==='reload').length,allowed?1:0,scenario+' repeat reload decision');
    if(!allowed)eq(f.replies.at(-1).ok,false,scenario+' remains fenced');
  }
  }
  eq(fs.readFileSync('browser_extension/background.js','utf8').replace(/\r\n/g,'\n'),originalBackground,'background source untouched');
  eq(fs.readFileSync('browser_extension/chatgpt.js','utf8').replace(/\r\n/g,'\n'),content,'content source untouched');
  console.log(JSON.stringify({ok:true,mode,checks,results,providerSubmissions:0,liveStateWrites:0}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
