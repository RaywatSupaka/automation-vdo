const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const src=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b,src.indexOf(a)+a.length));
let cases=0;
function setup(options={}){
  let clock=1000,sends=0,attached=0,retries=0,downloads=0,draft='legacy prompt',interrupted=false;const downloadedKeys=[];
  const retryButton={textContent:'ลองอีกครั้ง',disabled:false,isConnected:true,click:()=>{retries++;}};
  const retryScope={textContent:'สร้างรูปภาพไม่สำเร็จ',matches:selector=>selector==='[data-conversation-screenshot-content]',querySelectorAll:()=>[retryButton]};
  const makeUser=()=>{const id=`user-${sends}`;return {id,innerText:draft,textContent:draft+' '+(options.wrongRefs?'other request':sends<2?`smartflow-cover-${'a'.repeat(32)}-1.jpg`:''),
    getAttribute:key=>key==='data-message-id'?id:null,querySelectorAll:()=>[],compareDocumentPosition:()=>4};};
  const events=[],users=options.collectOnly?[makeUser()]:[],old={src:'old',currentSrc:'old',complete:true,naturalWidth:576,naturalHeight:1024};
  const image={...old,src:'new',currentSrc:'new'};
  const c={IS_GEMINI:!!options.gemini,PROVIDER_KEY:options.gemini?'gemini':'chatgpt',activeJobId:'',activeRunId:'',activeCoverRequest:null,cancelRequested:false,
    URL,location:{href:options.gemini?'https://gemini.google.com/app/0123456789abcdef':'https://chatgpt.com/c/fixture'},Node:{DOCUMENT_POSITION_FOLLOWING:4},Date:{now:()=>clock},waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>{},waitForComposer:async()=>({}),
    ensureAiWebModel:async()=>{},
    attachSourceImages:async images=>{attached++;assert.equal(images.length,options.title?2:1);},setComposerText:async(editor,text)=>{draft=text;if(options.title){assert.equal(text,`สร้างปกคลิป ${options.ratio==='16:9'?'แนวนอน':'Shorts'}\nชื่อคลิป: ${options.title}`);}return {};},waitForStableSendDraft:async()=>({button:{},editor:{}}),
    userTurns:()=>users,lastUserTurnSignature:()=>String(users.length),assistantTurns:()=>[],
    composer:()=>({}),composerText:()=>'',motionRequestIsLatestUser:()=>(sends>0||options.collectOnly)&&!options.wrongOwner,
    latestAssistantStrictlyAfterLatestUser:()=>({innerText:options.nativeRetry&&!retries?'ไม่สำเร็จ':options.failure||options.retrySuccess&&sends===1?'service failure':options.policy?'policy refusal':options.text||'',closest:selector=>options.nativeRetry&&selector==='[data-conversation-screenshot-content]'?retryScope:null}),
    visible:()=>true,
    analysisResponseStopButton:()=>clock<(options.readyAt||2000)?{click:()=>{}}:null,stopButtonVisible:()=>clock<(options.readyAt||2000),
    document:{querySelectorAll:()=>[]},generatedImageElements:scope=>scope===c.document?[old,...(sends?[{...image,src:'uploaded-reference',currentSrc:'uploaded-reference'}]:[])]:
      ((sends||options.collectOnly) && (!options.nativeRetry||retries) && clock>(options.imageAt||options.readyAt||2000) && !options.failure && !(options.retrySuccess&&sends===1) && !options.policy && !options.referenceOnly?
        [{...image,complete:!options.loadedAt||clock>options.loadedAt},...(options.secondImage?[{...image,src:'other',currentSrc:'other'}]:[])]:[]),
    sleep:async ms=>{clock+=ms;if(clock>1000000)throw Error('fixture limit');},
    assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancelled');},
    confirmedStoryImageServiceError:text=>text==='service failure',storyImageRefusal:text=>text==='policy refusal',
    imageData:async image=>{downloads++;downloadedKeys.push(image.src);
      if(options.downloadOwnerChange)c.motionRequestIsLatestUser=()=>false;
      if(options.downloadBusy)c.analysisResponseStopButton=()=>({click:()=>{throw Error('Never stop generation');}});
      if(options.downloadDraft)c.composerText=()=>'user draft';
      if(options.downloadFail||options.downloadOnce&&downloads===1)throw Error('download failed');return'data:image/png;base64,TEST';},
    chrome:{runtime:{sendMessage:async message=>{events.push(message.event);
      if(options.interruptRetry&&!interrupted&&message.event.reference_chain?.retry_user){interrupted=true;throw Error('collector interrupted after accepted retry');}
      if(options.saveAckLost&&message.event.phase==='ready')throw Error('save acknowledgement lost');
      return{ok:true,request:{phase:message.event.phase,retry_count:message.event.retry_count}};}}}};
  const send=async()=>{sends++;users.push(makeUser());};
  c.sendAndVerify=send;c.sendGeminiImageAndVerify=send;
  vm.createContext(c);vm.runInContext(part('  function chatGPTConversationFrames(', '  function assistantTurns(')
    +part('  async function coverEvent(', '  async function runSceneRepairHelper('),c);
  c.sendCoverAndVerify=async(request,stable,users,signature,answers)=>send(stable.button,stable.editor,users,signature,answers);
  const request={request_id:'a'.repeat(32),preparation_id:options.preparationId,collect_only:options.collectOnly,source:'scene.jpg',source_images:options.title?['data:image/jpeg;base64,QQ==','data:image/jpeg;base64,Qg==']:undefined,source_data:'data:image/jpeg;base64,QQ==',prompt:options.title?undefined:'legacy prompt',title:options.title,aspect_ratio:options.ratio};
  return{request,run:()=>c.runAICover(request),
    events,c,sends:()=>sends,attached:()=>attached,clock:()=>clock,retries:()=>retries,downloads:()=>downloads,downloadedKeys};
}
(async()=>{
  const downloadRecovery=setup({downloadOnce:true});await downloadRecovery.run();assert.equal(downloadRecovery.sends(),1);assert.equal(downloadRecovery.events.at(-1).phase,'ready');
  const retry=setup({nativeRetry:true});await retry.run();assert.equal(retry.retries(),1);assert.equal(retry.sends(),1);assert.equal(retry.attached(),1);assert.equal(retry.events.at(-1).phase,'ready');
  const ignored=setup({nativeRetry:true,referenceOnly:true});await ignored.run();assert.equal(ignored.retries(),1);assert.equal(ignored.sends(),1);assert.equal(ignored.events.at(-1).phase,'needs_review');
  for(const options of [{gemini:true},{wrongOwner:true}]){
    const noRetry=setup({nativeRetry:true,...options});await noRetry.run();assert.equal(noRetry.retries(),0);assert.equal(noRetry.sends(),1);
  }
  const retryFailure=setup({nativeRetry:true,failure:true});await retryFailure.run();assert.equal(retryFailure.retries(),1);assert.equal(retryFailure.sends(),1);assert.equal(retryFailure.events.at(-1).phase,'needs_review');
  for(const gemini of [false,true]){
    const f=setup({gemini,title:'กระต่ายกับไก่',ratio:gemini?'16:9':'9:16'});await f.run();assert.equal(f.sends(),1);assert.equal(f.attached(),1);
    assert.equal(f.events.at(-1).phase,'ready');assert.equal(f.c.activeCoverRequest,null);cases++;
  }
  const slow=setup({readyAt:450000});await slow.run();assert.equal(slow.events.at(-1).phase,'ready');assert.equal(slow.sends(),1);cases++;
  const uncertainSend=setup();const acceptedSend=uncertainSend.c.sendCoverAndVerify;
  uncertainSend.c.sendCoverAndVerify=async(...args)=>{
    await acceptedSend(...args);
    throw Object.assign(Error('acceptance acknowledgement lost'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED',
      submissionDispatched:true,sendDiagnostics:{gesture_phase:'released',release_on_send_target:true}});
  };
  await uncertainSend.run();assert.equal(uncertainSend.sends(),1,'uncertain cover Send is never replayed');
  assert.equal(uncertainSend.events.at(-1).phase,'ready','late owned cover image is saved after an uncertain Send');
  assert(uncertainSend.events.some(event=>event.send_state==='unconfirmed'));
  assert(uncertainSend.events.some(event=>event.send_state==='accepted'));cases++;
  const loading=setup({loadedAt:25000,text:'You could try:'});await loading.run();assert.equal(loading.events.at(-1).phase,'ready');assert(loading.clock()>=28500);
  for(const collectOnly of [false,true]){
    const multiple=setup({secondImage:true,collectOnly,text:'You could try:'});await multiple.run();
    assert.equal(multiple.events.at(-1).phase,'ready');assert.equal(multiple.events.at(-1).result_proof.images,1);
    assert.equal(multiple.sends(),collectOnly?0:1);assert.equal(multiple.attached(),collectOnly?0:1);
    assert.equal(multiple.downloads(),1);assert.deepEqual(multiple.downloadedKeys,['new']);assert(multiple.clock()<10000);
  }
  for(const collectOnly of [false,true]){
    const failedDownload=setup({downloadFail:true,secondImage:true,collectOnly});await failedDownload.run();
    assert.equal(failedDownload.downloads(),3);assert.equal(failedDownload.sends(),collectOnly?0:1);
    assert.deepEqual(JSON.parse(JSON.stringify(failedDownload.events.at(-1).download_failure)),{attempts:3,owned:true,idle:true});
    assert.equal(failedDownload.events.filter(e=>e.download_failure).length,1,'Desktop alone creates the replacement owner');
  }
  for(const flag of ['downloadOwnerChange','downloadBusy','downloadDraft','saveAckLost']){
    const guarded=setup({downloadFail:flag!=='saveAckLost',[flag]:true});await guarded.run();
    assert(!guarded.events.some(e=>e.download_failure),'Never replace for '+flag);assert.equal(guarded.sends(),1);
  }
  const promptFixture=setup({title:'ปกทดสอบ'});
  assert.equal(promptFixture.c.coverPromptForRequest(promptFixture.request),'สร้างปกคลิป Shorts\nชื่อคลิป: ปกทดสอบ');
  promptFixture.request.single_image_only=true;
  assert.match(promptFixture.c.coverPromptForRequest(promptFixture.request),/เพียง 1 รูปเท่านั้น ไม่ต้องมีตัวเลือก/);
  for(const gemini of [false,true]){
    const f=setup({gemini,imageAt:2000,readyAt:20000});await f.run();assert.equal(f.events.at(-1).phase,'ready');assert(f.clock()>=23500);assert.equal(f.sends(),1);
    const ref=setup({gemini,referenceOnly:true});await ref.run();assert.equal(ref.events.at(-1).phase,'needs_review');assert.equal(ref.sends(),1);
  }
  const failure=setup({failure:true});await failure.run();assert.equal(failure.sends(),2);assert.equal(failure.attached(),1);
  assert.equal(failure.events.at(-1).phase,'needs_review');assert(failure.events.some(x=>x.retry_count===1));cases++;
  const interrupted=setup({retrySuccess:true,interruptRetry:true});await interrupted.run();
  assert.equal(interrupted.sends(),2);assert.equal(interrupted.attached(),1);assert.equal(interrupted.downloads(),0);
  assert.equal(interrupted.events.at(-1).phase,'needs_review');
  interrupted.request.collect_only=true;await interrupted.run();
  assert.equal(interrupted.events.at(-1).phase,'ready');assert.equal(interrupted.sends(),2);assert.equal(interrupted.attached(),1);assert.equal(interrupted.downloads(),1);cases++;
  for(const options of [{policy:true},{wrongOwner:true},{downloadFail:true}]){
    const f=setup(options);await f.run();assert.equal(f.sends(),1);assert.equal(f.events.at(-1).phase,'needs_review');cases++;
  }
  const occupied=setup();occupied.c.userTurns=()=>[{}];await occupied.run();assert.equal(occupied.sends(),0);cases++;
  const cancelled=setup();cancelled.c.chrome.runtime.sendMessage=async()=>({ok:true,request:{phase:'cancelled'}});
  await cancelled.run();assert.equal(cancelled.sends(),0);cases++;
  for(const options of [{collectOnly:true},{collectOnly:true,wrongRefs:true},{collectOnly:true,wrongOwner:true},{collectOnly:true,failure:true}]){
    const f=setup(options);await f.run();assert.equal(f.sends(),0);assert.equal(f.attached(),0);assert.equal(f.retries(),0);
    assert.equal(f.events.at(-1).phase,options.wrongRefs||options.wrongOwner||options.failure?'needs_review':'ready');
  }
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
