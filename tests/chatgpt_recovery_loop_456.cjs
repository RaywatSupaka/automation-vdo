// Actual ChatGPT Story receipt/reminder/monitor orchestration, virtual time only.
// Existing fixtures supply a virtual owned document and isolated Chrome storage.
// No Chrome profile, local bridge, provider network or user job is opened.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const part = (start, end) => {
  const from = source.indexOf(start), to = source.indexOf(end, from + start.length);
  assert(from >= 0 && to > from, `actual production boundary: ${start}`);
  return source.slice(from, to);
};
const originalFixture = fs.readFileSync('tests/story_same_chat_reminder.cjs', 'utf8');
const fixtureEnd = originalFixture.indexOf('(async()=>{');
assert(fixtureEnd > 0, 'isolated fixture boundary');
const fixtureContext = vm.createContext({require, structuredClone});
vm.runInContext(originalFixture.slice(0, fixtureEnd) + '\nglobalThis.makeFixture=fixture;', fixtureContext);
let checks = 0, scenarios = 0;
const equal = (actual, expected, reason) => {assert.deepEqual(actual, expected, reason); checks++;};

async function acceptedReminderFixture(retryCount=0) {
  const f = fixtureContext.makeFixture();
  f.setParent({service_retry_count:retryCount});
  const reminder = f.make();
  await reminder.prepare(f.error);
  await reminder.resume();
  equal(f.sends, 1, 'one accepted reminder before continued observation');
  const childKey = f.db[f.key].same_chat_reminder.key;
  const child = f.db[childKey];
  let now = 100000, state = 'waiting_response', busy = false, signature = 'stable-child';
  let sleepHook = null, messageHook = null, maxTime = now + 240000, stopClicks=0;
  const messages = [];
  const image = {src:'https://chatgpt.com/backend-api/estuary/content?id=child', complete:true,
    naturalWidth:941, naturalHeight:1672};
  const observe = () => ({signature, busy, completedControl:false, stalledReason:state==='waiting_response'?'idle_answer_wait':'',
    request:{frame:f.frame}, state:{reason:state, images:state==='image_ready'?[image]:[], turn:null}});
  Object.assign(f.c, {
    Date:{now:()=>now}, revealChatGPTAnswer:async()=>false,
    storyImageWaitObservation:observe,
    chatGPTStoryImageSnapshot:()=>observe().state,
    chatGPTFrameAssistant:()=>null, stopButtonVisible:()=>busy,
    analysisResponseStopButton:()=>busy?{click:()=>{stopClicks++;throw Error('provider Stop is forbidden in recovery');}}:null,
    chatGPTStoryRequest:()=>({frame:f.frame}),
    confirmedStoryImageServiceError:()=>false, retryableCompletedImageText:()=>false,
    storyImageAssetKey:image=>image.src,
    imageDataFromUrl:async()=> 'data:image/png;base64,owned-child',
    waitStoryImageServiceRetry:async()=>{},
    sleep:async ms=>{
      now += ms;
      if(sleepHook)await sleepHook(now);
      if(now > maxTime)throw Object.assign(Error('fixture elapsed without a recovery handoff'), {code:'FIXTURE_PASSIVE_WAIT'});
    },
  });
  f.c.chrome.runtime.sendMessage = async message => {
    messages.push(structuredClone(message));
    if(messageHook)return await messageHook(message);
    if(message.type==='RELOAD_CHATGPT_STORY_RESULT')
      return {ok:true,refresh_scheduled:true};
    if(message.type==='RESTART_FAILED_STORY_IMAGE')return {ok:true,refresh_scheduled:true};
    throw Error(`unexpected browser action: ${message.type}`);
  };
  vm.runInContext(part('  function storyImageNoResultReady(', '  async function waitStoryImageServiceRetry(')
    +part('  function createStoryImageWaitMonitor(', '  function createStoryImageReceipt(')
    +part('  function createStoryImageReceipt(', '  function largeAssistantImages('), f.c);
  return {f, child, childKey, messages, image,
    receipt:()=>f.c.createStoryImageReceipt(f.pkg, 9, f.promptIdentity, 8),
    setState:(next, nextBusy=false)=>{state=next;busy=nextBusy;signature=`${next}:${nextBusy}`;},
    setSignature:value=>signature=value,
    onSleep:hook=>sleepHook=hook, onMessage:hook=>messageHook=hook, setLimit:value=>maxTime=value,
    completeRefresh:(message, fields={})=>{
      const row=f.db[f.key];
      row.refresh_recovery={version:1,phase:'checking',document_fence_version:1,
        previous_document_id:'child-before-'+message.refresh_cycle,document_id:'child-after-'+message.refresh_cycle,
        tab_id:1,send_nonce:row.send_nonce,conversation_url:f.c.location.href,
        claimed_at:now-1000,ready_at:now,loop_version:1,
        refresh_cycle:message.refresh_cycle,result_owner_nonce:message.result_owner_nonce,...fields};
    },
    get now(){return now;},get stopClicks(){return stopClicks;}};
}

async function checkpoint(f, label) {
  let result;
  try {await f.receipt().restore();} catch(error) {result=error;}
  equal(result?.code, 'STORY_IMAGE_REFRESH_SCHEDULED', label);
  equal(f.stopClicks,0,'recovery never clicks provider Stop');
  return f.messages.at(-1);
}

async function refreshedChild(f) {
  const previous=f.f.db[f.f.key].refresh_recovery;
  const expectedCycle=Number(previous?.loop_version===1?previous.refresh_cycle:0)+1;
  const message=await checkpoint(f,'silent accepted child reaches a recovery checkpoint');
  equal(message.type,'RELOAD_CHATGPT_STORY_RESULT','child is refreshed before any fresh generation');
  equal(message.recovery_protocol,3,'child never falls into the legacy refresh budget');
  equal(message.result_owner_nonce,f.child.send_nonce,'refresh is bound to the accepted child');
  equal(message.send_nonce,f.f.db[f.f.key].send_nonce,'parent Send nonce remains intact');
  equal(message.refresh_cycle,expectedCycle,'next durable refresh cycle for this receipt');
  f.completeRefresh(message);
  return message;
}

function mountLateOriginal(f, {foreignOriginal=false, laterUser=false, sourceAsset=false, deferred=false}={}) {
  const originalImage={...f.image,src:'https://chatgpt.com/backend-api/estuary/content?id=original'};
  const originalFrame={id:'turn-original',message:'message-original',text:foreignOriginal?'different original':'original',user:true};
  const answerFrame={id:'answer-original',text:'',images:deferred?[]:[originalImage]};
  const childFrame={id:'turn-child',message:'message-child',text:f.child.prompt,user:true};
  const frames=[originalFrame,answerFrame,childFrame];
  if(sourceAsset)originalFrame.images=[originalImage];
  if(laterUser)frames.push({id:'turn-foreign',message:'message-foreign',text:'unrelated new request',user:true});
  const child=f.f.db[f.childKey];
  child.original_result_proof={...child.original_result_proof,before_message_ids:['older-user'],
    before_frame_ids:['older-frame'],before_turn:1};
  Object.assign(f.f.c,{URL,chatGPTConversationFrames:()=>frames,
    chatGPTFrameUser:frame=>frame?.user?frame:null,
    chatGPTFrameAssistant:frame=>frame&&!frame.user?frame:null,
    chatGPTFrameId:frame=>frame?.id||'',chatGPTUserMessageId:frame=>frame?.message||'',
    chatGPTKnownRenderedRequestMatches:(actual,expected)=>actual===expected,
    generatedImageElements:frame=>frame.images||[],
    imageDataFromUrl:async url=>url===originalImage.src?'data:image/png;base64,late-original':'data:image/png;base64,owned-child',
  });
  vm.runInContext(part('  function storyImageAssetKey(', '  function storyImageMissingRequestEvidence('),f.f.c);
  f.f.c.storyUserBody=frame=>frame?.user?frame.text:'';
  f.f.c.storyImageWaitObservation=(prompt,proof)=>{
    const state=f.f.c.chatGPTStoryImageSnapshot(prompt,new Set(),proof);
    return {state,request:f.f.c.chatGPTStoryRequest(prompt,proof),signature:state.reason,busy:false,
      completedControl:state.reason==='image_ready',stalledReason:state.reason==='waiting_response'?'idle_answer_wait':''};
  };
  return {originalImage,child,frames,answerFrame};
}

(async()=>{
  {
    // Execute the actual readiness helper against a minimal synthetic DOM.
    // Only the exact latest request's answer progress may survive active refresh.
    let historyBusy=false,alerts=[],progress=[],resolved=null,visibleEditor=true;
    const editor={},body={},original={user:true,parentElement:body},request={user:true,parentElement:body};
    const ownProgress={},otherProgress={};
    const answer={parentElement:body,contains:node=>node===ownProgress};
    let frames=[original,request,answer];
    const main={matches:()=>historyBusy,querySelectorAll:()=>progress};
    const c=vm.createContext({Date:{now:()=>100000},Number,Math,
      document:{readyState:'complete',body,querySelector:()=>main,querySelectorAll:()=>alerts},
      composer:()=>editor,visible:node=>node!==editor||visibleEditor,
      chatGPTConversationFrames:()=>frames,chatGPTFrameUser:node=>node.user?node:null,
      chatGPTStoryRequest:()=>({frame:resolved}),getComputedStyle:()=>({overflowY:'visible'}),
      revealChatGPTAnswer:{userUntil:0}});
    vm.runInContext(part('  function storyImagePostRefreshPageReady(', '  function storyImagePostRefreshEvidenceValid('),c);
    const generation={prompt:'exact',proof:{request_message_id:'owned'}};
    progress=[ownProgress];resolved=request;
    equal(c.storyImagePostRefreshPageReady(),false,'ordinary absence check rejects answer progress');
    equal(c.storyImagePostRefreshPageReady(generation),true,'active refresh allows exact latest answer progress');
    progress=[answer];equal(c.storyImagePostRefreshPageReady(generation),true,'streaming answer frame itself is owned');
    progress=[ownProgress,otherProgress];equal(c.storyImagePostRefreshPageReady(generation),false,'unowned progress still blocks active refresh');
    progress=[ownProgress];resolved=original;
    equal(c.storyImagePostRefreshPageReady(generation),false,'older request cannot borrow latest answer progress');
    resolved=null;equal(c.storyImagePostRefreshPageReady(generation),false,'missing exact owner cannot borrow progress');
    resolved=request;historyBusy=true;
    equal(c.storyImagePostRefreshPageReady(generation),false,'page-level loading is never provider-only progress');
    historyBusy=false;alerts=[{textContent:'Usage limit reached'}];
    equal(c.storyImagePostRefreshPageReady(generation),false,'quota remains a readiness blocker');
    alerts=[];visibleEditor=false;
    equal(c.storyImagePostRefreshPageReady(generation),false,'unmounted composer remains a readiness blocker');
    visibleEditor=true;c.revealChatGPTAnswer.userUntil=100001;
    equal(c.storyImagePostRefreshPageReady(generation),false,'active refresh preserves user-scroll grace');
    scenarios++;
  }
  {
    const f = await acceptedReminderFixture();
    await refreshedChild(f);
    const message=await checkpoint(f,'refreshed child silence reaches a fresh successor instead of endless wait');
    equal(message.type,'RESTART_FAILED_STORY_IMAGE','fresh successor after child result recheck');
    equal(message.post_refresh_evidence.result_owner_nonce,f.child.send_nonce,'fresh evidence belongs to this child');
    equal(f.f.db[f.f.key].recovery_protocol,3,'new evidence carries v3 receipt contract');
    equal(f.f.sends,1,'no duplicate reminder Send');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,1,'one fresh allocation request');
    const token='successor-owned-once';
    f.f.db[f.f.key].fresh_restart={token,run_id:'run',phase:'created',tab_id:99};
    f.f.db[f.f.key].previous_scene_reference_index=8;
    f.f.pkg.fresh_image_restart={index:9,token};
    equal(await f.receipt().restore(),null,'consume the exact background successor');
    const row=f.f.db[f.f.key];
    equal(row.resume_image_prompt,'original','fresh generation retains full original instruction, not short reminder');
    equal(row.previous_scene_reference_index,8,'fresh generation retains preceding scene reference');
    equal(row.identity.includes('saved/reference.png'),true,'saved source identity survives handoff');
    equal(row.same_chat_reminder,null,'next original attempt does not inherit the spent child');
    equal(row.fresh_restart.phase,'consumed','successor is consumed once');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    f.f.c.activeRunId='continued-run';
    await refreshedChild(f);
    await assert.rejects(f.receipt().restore(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW'
      && error.message.includes('CHATGPT_IMAGE_PRIOR_RUN_PENDING'));checks++;
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,
      'an accepted request from a cancelled run never allocates another tab');
    equal(f.f.db[f.f.key].status,'awaiting_result','prior-run receipt remains available for later result inspection');
    equal(f.f.sends,1,'Continue does not create another provider image request');
    scenarios++;
  }
  for(const invalid of ['foreignOriginal','laterUser','sourceAsset']) {
    const f=await acceptedReminderFixture();
    mountLateOriginal(f,{[invalid]:true});
    await assert.rejects(f.receipt().restore(),error=>
      error.code==='STORY_IMAGE_REFRESH_SCHEDULED'||error.code==='STORY_IMAGE_RECEIPT_REVIEW');checks++;
    equal(f.f.db[f.f.key].image_url,undefined,invalid+' cannot be adopted as an original result');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'invalid original cannot authorize fresh allocation');
    equal(f.f.sends,1,'invalid original evidence never repeats Send');
    scenarios++;
  }
  for(const retryCount of [1,2,7]) {
    const f=await acceptedReminderFixture(retryCount);
    await refreshedChild(f);
    const message=await checkpoint(f,'later failed attempts retain the same continuous recovery route');
    equal(message.type,'RESTART_FAILED_STORY_IMAGE','no lifetime stop after earlier recovered attempts');
    equal(f.f.db[f.f.key].service_retry_count,retryCount,'observation does not invent another generation');
    equal(f.f.sends,1,'one reminder for each exact original attempt');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    const row=f.f.db[f.f.key];
    Object.assign(row.refresh_recovery,{loop_version:1,refresh_cycle:3,result_owner_nonce:row.send_nonce});
    const before=f.now;
    const message=await refreshedChild(f);
    equal(message.refresh_cycle,4,'child gets a new monotonic cycle after original-request refreshes');
    equal(f.now-before>=60000,true,'original owner refresh never counts as a child ready check');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'original v3 evidence cannot immediately restart a silent child');
    scenarios++;
  }
  for(const state of ['image_ready','image_loading']) {
    const f=await acceptedReminderFixture();
    await refreshedChild(f);
    f.setState(state);
    f.onSleep(async()=>f.setState('image_ready'));
    equal(await f.receipt().restore(),'data:image/png;base64,owned-child','late child result is collected');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'late/loading child never starts another generation');
    equal(f.f.sends,1,'late child uses existing Send');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    const {originalImage,child}=mountLateOriginal(f);
    equal(f.f.c.chatGPTStoryImageSnapshot('original',new Set(),child.original_result_proof).reason,
      'request_not_latest','raw original proof retains the ordinary latest-user guard');
    equal(await f.receipt().restore(),'data:image/png;base64,late-original',
      'accepted child does not hide a late exact original image');
    equal(f.f.db[f.f.key].image_url,originalImage.src,'late parent asset is persisted to the existing scene');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'late original precludes fresh allocation');
    equal(f.f.sends,1,'late original after child acceptance does not repeat Send');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    const {originalImage}=mountLateOriginal(f);
    const link=structuredClone(f.f.db[f.f.key].same_chat_reminder);
    originalImage.complete=false;originalImage.naturalWidth=0;originalImage.naturalHeight=0;
    const began=f.now;
    f.onSleep(async now=>{
      equal(structuredClone(f.f.db[f.f.key].same_chat_reminder),link,
        'original loading and stability sleep retain the exact active reminder link');
      equal(f.f.db[f.f.key].completed_reminder,undefined,'reminder is not archived before stable adoption');
      if(now>=began+20000){originalImage.complete=true;originalImage.naturalWidth=941;originalImage.naturalHeight=1672;}
    });
    equal(await f.receipt().restore(),'data:image/png;base64,late-original','loading original waits and then adopts exact original result');
    equal(f.now-began>=22000,true,'original result decodes and remains stable before persistence');
    equal(f.f.db[f.f.key].same_chat_reminder,null,'stable adoption clears only the active reminder link');
    equal(structuredClone(f.f.db[f.f.key].completed_reminder),link,'stable adoption archives that exact reminder link');
    equal(f.f.db[f.f.key].result_proof.prompt,'original','adoption persists original rather than reminder proof');
    equal(f.f.db[f.childKey].send_nonce,link.nonce,'adoption retains the child receipt and nonce');
    equal(f.messages.length,0,'loading original is not stable absence or new-generation authority');
    equal(f.f.sends,1,'loading original never repeats a reminder');
    equal(f.stopClicks,0,'loading original never clicks Stop');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    const {originalImage,answerFrame}=mountLateOriginal(f,{deferred:true});
    await refreshedChild(f);
    let vetoes=0;
    f.onMessage(async message=>{
      equal(message.type,'RESTART_FAILED_STORY_IMAGE','late-image race occurs at the fresh-allocation boundary');
      answerFrame.images=[originalImage];
      equal(f.f.c.storyImageRedoGuard(message),false,'live redo guard rejects original image arriving after absence proof');
      vetoes++;
      return {ok:false,refresh_scheduled:false,retry_safe:true,refresh_reason:'live_guard_changed'};
    });
    equal(await f.receipt().restore(),'data:image/png;base64,late-original','late original veto returns to exact result collection');
    equal(vetoes,1,'late original veto happens before any allocation');
    equal(f.f.db[f.f.key].image_url,originalImage.src,'late original is saved in existing scene');
    equal(f.f.sends,1,'post-proof original result never repeats Send');
    equal(f.stopClicks,0,'post-proof original result never clicks Stop');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    await refreshedChild(f);
    let calls=0,allocations=0,first=null;
    f.onMessage(async message=>{
      equal(message.type,'RESTART_FAILED_STORY_IMAGE','pending transport reconciles only the existing allocation');
      if(!first){first=structuredClone(message);allocations++;}
      else equal(structuredClone(message),first,'lost ACK repeats exact ownership/evidence RPC');
      calls++;
      if(calls===1)return {pending:true};
      if(calls===2)throw Error('allocation ACK lost');
      return {ok:true,refresh_scheduled:true};
    });
    await checkpoint(f,'pending/lost allocation ACK eventually reconciles');
    equal(calls,3,'same RPC reconciles pending then lost ACK');
    equal(allocations,1,'only one durable successor is allocated');
    equal(f.f.sends,1,'allocation reconciliation never sends to provider');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    await refreshedChild(f);
    f.setState('waiting_response',true);
    f.setLimit(f.now+480000);
    for(let cycle=2;cycle<=4;cycle++) {
      const message=await checkpoint(f,'active generation remains observable through repeated refresh rounds');
      equal(message.type,'RELOAD_CHATGPT_STORY_RESULT','busy recovery only refreshes the owned page');
      equal(message.stalled_reason,'active_generation_wait','busy generation has distinct refresh evidence');
      equal(message.refresh_cycle,cycle,'durable refresh cycle advances without a lifetime cap');
      equal(message.result_owner_nonce,f.child.send_nonce,'all active refresh rounds keep the same accepted child');
      f.completeRefresh(message);
    }
    f.f.c.cancelRequested=true;
    await assert.rejects(f.receipt().restore(),error=>error.message==='cancelled');checks++;
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'busy child cannot create a fresh successor');
    equal(f.f.sends,1,'busy wait never repeats Send');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    await refreshedChild(f);
    const began=f.now;
    f.setLimit(began+60000);
    f.onSleep(async now=>{
      f.setSignature('render-progress-'+now);
      if(now>=began+50000)f.setState('image_ready');
    });
    equal(await f.receipt().restore(),'data:image/png;base64,owned-child','changing progress is observed until an actual result');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'progress cannot be counted as stable absence');
    equal(f.f.sends,1,'progress never duplicates the reminder');
    scenarios++;
  }
  {
    const f=await acceptedReminderFixture();
    f.onMessage(async message=>{
      if(message.type==='RELOAD_CHATGPT_STORY_RESULT') {
        const row=f.f.db[f.f.key];
        row.refresh_recovery={version:1,phase:'claimed',loop_version:1,send_nonce:row.send_nonce,
          result_owner_nonce:message.result_owner_nonce,refresh_cycle:message.refresh_cycle,
          conversation_url:f.f.c.location.href,claimed_at:f.now};
        throw Error('acknowledgement lost after durable claim');
      }
      throw Error('unexpected generation after lost refresh ACK');
    });
    f.onSleep(async now=>{if(now>=260000)f.f.c.cancelRequested=true;});
    await assert.rejects(f.receipt().restore(),error=>error.message==='cancelled');checks++;
    equal(f.messages.filter(row=>row.type==='RELOAD_CHATGPT_STORY_RESULT').length,1,'lost ACK never dispatches a second refresh claim');
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,'unknown refresh outcome does not authorize generation');
    equal(f.f.sends,1,'unknown ACK does not replay reminder');
    scenarios++;
  }
  for(const change of ['child_nonce','document','owner']) {
    const f=await acceptedReminderFixture();
    const originalMessage=await refreshedChild(f);
    if(change==='child_nonce')f.completeRefresh(originalMessage,{result_owner_nonce:'foreign-child'});
    if(change==='document')f.completeRefresh(originalMessage,{document_id:'same',previous_document_id:'same'});
    if(change==='owner')f.f.db[f.f.key].same_chat_reminder.nonce='foreign-child';
    f.onMessage(async message=>{
      if(message.type==='RESTART_FAILED_STORY_IMAGE')throw Error('stale evidence must never allocate');
      return {ok:false,refresh_scheduled:false,refresh_reason:'ack_unknown',retry_safe:false};
    });
    f.onSleep(async now=>{if(now>=230000)f.f.c.cancelRequested=true;});
    await assert.rejects(f.receipt().restore(),error=>error.message==='cancelled'||error.code==='STORY_IMAGE_RECEIPT_REVIEW');checks++;
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,change+' does not authorize another generation');
    equal(f.f.sends,1,'stale state never repeats reminder');
    scenarios++;
  }
  for(const invalidation of ['claimed','document','ready_at']) {
    const f=await acceptedReminderFixture();
    await refreshedChild(f);
    const began=f.now;
    let mutated=false;
    f.onSleep(async now=>{
      if(!mutated) {
        mutated=true;
        const recovery=f.f.db[f.f.key].refresh_recovery;
        if(invalidation==='claimed')recovery.phase='claimed';
        if(invalidation==='document')recovery.document_id=recovery.previous_document_id;
        if(invalidation==='ready_at')recovery.ready_at=now+120000;
      }
      if(now>=began+45000)f.f.c.cancelRequested=true;
    });
    await assert.rejects(f.receipt().restore(),error=>error.message==='cancelled');checks++;
    equal(f.messages.filter(row=>row.type==='RESTART_FAILED_STORY_IMAGE').length,0,
      'mid-wait '+invalidation+' invalidates the old post-refresh ready window');
    equal(f.f.sends,1,'invalidated refresh cannot replay the reminder');
    scenarios++;
  }
  {
    const f=fixtureContext.makeFixture(), reminder=f.make();
    await reminder.prepare(f.error);
    f.setObservation({state:{reason:'image_ready',images:[{}]}});
    await reminder.resume();
    equal(f.sends,0,'late original result wins before any reminder Send');
    equal(f.db[f.key].same_chat_reminder,null,'late original retains original result ownership');
    scenarios++;
  }
  console.log(JSON.stringify({ok:true,checks,scenarios,providerSubmissions:0,liveStateWrites:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
