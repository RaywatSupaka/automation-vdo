// Execute the actual trusted Send handler. Only browser/document/desktop
// surfaces are simulated; no provider calls, live receipts or generation.
const assert=require('node:assert/strict');
const {fixture}=require('./ai_send_acceptance_harness');
const JOB='STORY-REMINDER',RUN='run-test',URL='https://chatgpt.com/c/existing',DOC='reminder-document';

function reminderFixture(options={}){
  const f=fixture(options);
  const parentKey=`smartpostStoryGeneratedImage:chatgpt:${JOB}:6`;
  const childKey=`${parentKey}:reminder:parent-nonce`;
  const prompt=f.storage[f.claim.key].result_proof.prompt;
  const original={prompt:'Original image request with the supplied reference.',conversation_url:URL,
    request_message_id:'original-message',request_turn_id:'original-turn',before_message_ids:['older-message'],
    before_frame_ids:['older-frame']};
  const claim={key:childKey,parent_key:parentKey,parent_nonce:'parent-nonce',nonce:'reminder-nonce',scene_index:6};
  const parent={version:1,provider:'chatgpt',job_id:JOB,run_id:RUN,scene_index:6,identity:'exact-parent-identity',
    status:'awaiting_result',send_phase:'accepted',send_nonce:'parent-nonce',result_proof:structuredClone(original),
    refresh_recovery:{version:1,phase:'checking',document_fence_version:1,document_id:DOC,previous_document_id:'old-document',
      send_nonce:'parent-nonce',conversation_url:URL,tab_id:12,ready_at:1000},
    same_chat_reminder:{version:1,key:childKey,nonce:claim.nonce,parent_nonce:claim.parent_nonce}};
  const child={version:1,provider:'chatgpt',job_id:JOB,run_id:RUN,scene_index:6,parent_key:parentKey,
    parent_nonce:claim.parent_nonce,parent_identity:parent.identity,send_phase:'dispatching',send_nonce:claim.nonce,
    created_at:1000,conversation_url:URL,document_id:DOC,prompt,original_result_proof:structuredClone(original),
    result_proof:{prompt,conversation_url:URL,before_frame_ids:['older-frame','original-turn'],before_message_ids:['original-message']}};
  Object.assign(f.storage,{[parentKey]:parent,[childKey]:child});
  const message={type:'CLICK_AI_SEND_BUTTON',provider:'chatgpt',job_id:JOB,run_id:RUN,
    expectedPrompt:prompt,story_reminder_claim:claim,...(options.singleAnswer?{response_format_version:1}:{})};
  const sender={tab:{id:12,windowId:2,url:URL},documentId:DOC};
  let documentId=DOC,desktopActive=true,tabStatus='complete',tabUrl=URL,checks=0,readyCalls=0;
  const script=f.backend.chrome.scripting.executeScript;
  f.backend.chrome.tabs.get=async()=>({id:12,status:tabStatus,url:tabUrl});
  f.backend.storyRefreshDesktopRunActive=async(job,run)=>{
    assert.equal(job,JOB);assert.equal(run,RUN);checks++;return desktopActive;
  };
  f.backend.chrome.scripting.executeScript=async packet=>{
    assert.equal(packet.target.tabId,12);
    assert.deepEqual(Array.from(packet.target.documentIds||[]),[DOC],'Every reminder injection must be document-fenced');
    if(!packet.world)return [{frameId:0,documentId,result:tabUrl}];
    return script(packet);
  };
  f.backend.chrome.tabs.sendMessage=async(tab,message,sendOptions)=>{
    assert.equal(tab,12);assert.equal(message.type,'VERIFY_AI_SEND_READY');
    assert.equal(sendOptions.documentId,DOC);assert.equal(message.require_story_idle,true);
    assert.equal(message.story_reminder_claim.key,claim.key);readyCalls++;
    if(optionsGuard)await optionsGuard(readyCalls);
    return {ok:!(options.cancelDuringPreparation || options.lateReadyVeto && readyCalls>1),reason:'test_veto'};
  };
  let optionsGuard=null;
  return {f,parent,child,claim,message,sender,parentKey,childKey,run:()=>f.backend.handle(message,sender),
    setDocument:id=>{documentId=id;},setDesktop:active=>{desktopActive=active;},
    setTab:(status,url=URL)=>{tabStatus=status;tabUrl=url;},onReady:callback=>{optionsGuard=callback;},
    checks:()=>checks,readyCalls:()=>readyCalls,
    presses:()=>f.commands.filter(row=>row.type==='mousePressed').length,
    releases:()=>f.commands.filter(row=>row.type==='mouseReleased').length};
}

(async()=>{
  let cases=0;
  for(const singleAnswer of [false,true]){
    const t=reminderFixture({acceptImmediately:true,singleAnswer}),before=structuredClone(t.parent);
    const result=await t.run();assert.equal(result.ok,true,JSON.stringify(result));
    assert.equal(t.presses(),1);assert.equal(t.releases(),1);assert.equal(t.readyCalls(),2);
    assert(t.checks()>=3);assert.equal(t.f.storage[t.childKey+':dispatch'],t.claim.nonce);
    assert.deepEqual(t.f.storage[t.parentKey],before,'Reminder dispatch must retain original receipt');
    assert.equal(t.f.commands.filter(row=>row.method==='Input.dispatchKeyEvent').length,0);cases++;
  }
  const mutations={
    wrong_provider:t=>{t.message.provider='gemini';},
    extra_original_claim:t=>{t.message.story_send_claim=t.f.claim;},
    wrong_scene:t=>{t.claim.scene_index=5;},
    wrong_child_key:t=>{t.claim.key=t.parentKey+':reminder:another';},
    wrong_parent_key:t=>{t.claim.parent_key='foreign';},
    empty_nonce:t=>{t.claim.nonce='';},
    unknown_parent_send:t=>{t.parent.send_phase='dispatching';},
    prepared_parent_send:t=>{t.parent.send_phase='prepared';},
    completed_parent:t=>{t.parent.status='generated';},
    refusal_parent:t=>{t.parent.status='refused';},
    already_saved_image:t=>{t.parent.image_url='saved-image';},
    parent_nonce_changed:t=>{t.parent.send_nonce='new-parent';},
    parent_owner_changed:t=>{t.parent.run_id='other-run';},
    wrong_link_nonce:t=>{t.parent.same_chat_reminder.nonce='other-child';},
    missing_link:t=>{delete t.parent.same_chat_reminder;},
    child_identity_changed:t=>{t.child.parent_identity='other-identity';},
    accepted_child:t=>{t.child.send_phase='accepted';},
    prepared_child:t=>{t.child.send_phase='prepared';},
    unknown_child_phase:t=>{delete t.child.send_phase;},
    changed_reminder_draft:t=>{t.child.prompt='other prompt';},
    missing_original_ids:t=>{delete t.parent.result_proof.request_message_id;delete t.parent.result_proof.request_turn_id;
      t.child.original_result_proof=structuredClone(t.parent.result_proof);},
    original_message_changed:t=>{t.parent.result_proof.request_message_id='late-other-message';},
    original_baseline_changed:t=>{t.child.original_result_proof.before_message_ids.push('foreign');},
    sender_document_changed:t=>{t.sender.documentId='old-document';},
    missing_sender_document:t=>{delete t.sender.documentId;},
    new_chrome_document:t=>{t.setDocument('new-document');},
    recovery_document_changed:t=>{t.parent.refresh_recovery.document_id='old-document';},
    missing_refresh_proof:t=>{t.parent.refresh_recovery={document_id:DOC};},
    not_refreshed:t=>{t.parent.refresh_recovery.previous_document_id=DOC;},
    stale_refresh_nonce:t=>{t.parent.refresh_recovery.send_nonce='other-parent';},
    wrong_refresh_tab:t=>{t.parent.refresh_recovery.tab_id=24;},
    future_refresh_ready:t=>{t.parent.refresh_recovery.ready_at=Date.now()+90000;},
    prepared_before_refresh:t=>{t.child.created_at=999;},
    loading_page:t=>{t.setTab('loading');},
    wrong_conversation:t=>{t.setTab('complete','https://chatgpt.com/c/another');},
    desktop_paused:t=>{t.setDesktop(false);},
    already_dispatched:t=>{t.f.storage[t.childKey+':dispatch']=t.claim.nonce;},
    foreign_dispatch_latch:t=>{t.f.storage[t.childKey+':dispatch']='older-child-nonce';},
    successor_pending:t=>{t.parent.fresh_restart={phase:'requested'};},
    redo_pending:t=>{t.parent.post_refresh_evidence={};}
  };
  for(const [name,mutate] of Object.entries(mutations)){
    const t=reminderFixture({acceptImmediately:true});mutate(t);
    const result=await t.run();assert.equal(result.ok,false,name);assert.equal(t.presses(),0,name);cases++;
  }
  // Native storage may reorder object keys; exact nested values remain owner proof.
  {const t=reminderFixture({acceptImmediately:true});
    t.child.original_result_proof=Object.fromEntries(Object.entries(t.child.original_result_proof).reverse());
    const result=await t.run();assert.equal(result.ok,true,JSON.stringify(result));cases++;}
  for(const change of ['image','busy','document','desktop','dispatch']){
    const t=reminderFixture({acceptImmediately:true});
    t.onReady(()=>{
      if(change==='image')t.parent.image_url='late-original-image';
      if(change==='busy')t.parent.status='completed_no_image';
      if(change==='document')t.setDocument('navigated');
      if(change==='desktop')t.setDesktop(false);
      if(change==='dispatch')t.f.storage[t.childKey+':dispatch']=t.claim.nonce;
    });
    const result=await t.run();assert.equal(result.ok,false,change);assert.equal(t.presses(),0,change);cases++;
  }
  {const t=reminderFixture({lateReadyVeto:true});const result=await t.run();
    assert.equal(result.ok,false);assert.equal(t.presses(),0);assert.equal(result.notDispatched,true);cases++;}
  // A press whose response is lost is ambiguous. The durable child latch
  // survives worker restarts and blocks another press of the reminder.
  {const t=reminderFixture({pressResponseLost:true,noCapturedEvents:true});
    const first=await t.run();assert.equal(first.dispatched,true);assert.notEqual(first.notDispatched,true);
    assert.equal(t.presses(),1);assert.equal(t.releases(),1);
    const replay=await t.run();assert.equal(replay.ok,false);assert.notEqual(replay.notDispatched,true);
    assert.equal(t.presses(),1);assert.equal(t.f.storage[t.childKey+':dispatch'],t.claim.nonce);cases++;}
  {const t=reminderFixture({loseOwnership:true});const result=await t.run();
    assert.equal(result.ok,false);assert.equal(t.presses(),0);cases++;}
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
