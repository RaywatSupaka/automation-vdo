// Native DOM regression from the observed 2026-09-25 ChatGPT markup. All
// network requests are intercepted; synthetic media is collector-only proof.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>{const start=source.indexOf(a),end=source.indexOf(b,start+a.length);assert(start>=0&&end>start);return source.slice(start,end);};
let checks=0;const eq=(a,b,label)=>{assert.deepEqual(a,b,label);checks++;};
(async()=>{const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.request().url()==='https://chatgpt.com/c/fixture'
    ?route.fulfill({contentType:'text/html',body:'<main></main>'}):route.abort());
  await page.goto('https://chatgpt.com/c/fixture');
  await page.addScriptTag({path:path.join(root,'browser_extension/single_answer.js')});
  await page.addScriptTag({content:`
    let IS_GEMINI=false,activeJobId='STORY-FIXTURE',activeRunId='RUN-FIXTURE',cancelRequested=false;
    const AI_NAME='ChatGPT Web',PROVIDER_KEY='chatgpt';let busy=false,events=[],dispatches=0,clock=0;
    const visible=node=>!!node && node.getAttribute('data-hidden')!=='true';
    const assertNotCancelled=()=>{if(cancelRequested)throw Error('cancelled');};
    const sleep=async ms=>{clock+=ms;},report=async(...args)=>events.push(args);
    const stopButtonVisible=()=>busy;
    const composer=()=>document.querySelector('textarea');
    const composerText=node=>SmartFlowSingleAnswer.canonical((node||composer())?.value||'');
    const waitForStableSendDraft=async()=>({button:document.querySelector('button[type=submit]'),editor:composer()});
    const savedReceipts={};
    globalThis.chrome={runtime:{sendMessage:async()=>{dispatches++;mount();return {ok:true,method:'single_trusted_ai_send'};}},
      storage:{local:{get:async key=>({[key]:savedReceipts[key]??null}),
        set:async values=>Object.assign(savedReceipts,structuredClone(values))}}};
    const sameStoryImageReceipt=(left,right)=>JSON.stringify(left)===JSON.stringify(right);
    let recoverOwnedStoryImage=async proof=>chatGPTStoryImageSnapshot(proof.prompt,new Set(),proof).images[0]||null;
    let storyImageRefreshGuard=null,storyImageRedoGuard=null;
    const imageDataFromUrl=async (url,node)=>{if(node && url===node.src)return 'data:image/png;base64,fixture';throw Error('wrong image');};
    const prompt='Create exactly one new portrait of the fictional scientist in the library. Use the saved reference only for appearance.';
    const answer='ไม่สามารถสร้างภาพจริงในรอบนี้ได้ เนื่องจากเครื่องมือสร้างภาพระบุว่าต้องมีภาพอ้างอิงที่ใช้งานได้ก่อน กรุณาอัปโหลดหรือระบุภาพที่จะใช้เป็นเป้าหมาย แล้วจึงสามารถสร้างภาพต่อได้';
    const userHtml=(key='fallback-turn-0:0:user',id='owned-user',text=SmartFlowSingleAnswer.wrap(prompt))=>
      '<div class="block-BQZwFn"><div class="group/user-message" data-chatgpt-search-unit-key="'+key+'" data-chatgpt-search-message-ids="'+id+'"><div data-content-search-unit-key="'+key+'"><div><div data-user-message-bubble="true"><div><div class="text-size-chat whitespace-pre-wrap" dir="auto">'+text+'</div></div></div></div></div><button>ดูเพิ่มเติม</button><button>แก้ไขข้อความ</button></div></div>';
    const assistantHtml=(text=answer,key='fallback-turn-0:2:assistant')=>
      '<div class="block-BQZwFn"><span hidden data-chatgpt-agent-turn-start></span><div data-content-search-unit-key="'+key+'" data-chatgpt-search-unit-key="'+key+'" data-chatgpt-search-message-ids="answer-start answer-final"><h4 data-conversation-role="assistant">ChatGPT พูดว่า:</h4><div data-chatgpt-selection-conversation-id="local-chatgpt:fixture" data-chatgpt-selection-message-id="answer-final"><div data-markdown-text-style="assistant-message"><p>'+text+'</p></div></div></div></div>';
    const galleryHtml=()=>'<div class="block-BQZwFn"><span hidden data-chatgpt-agent-turn-start></span><h4 data-conversation-role="assistant">ChatGPT พูดว่า:</h4><div data-chatgpt-search-message-ids="gallery-message"><div><div data-testid="generated-image-gallery"><button type="button" data-testid="generated-image-preview" aria-label="รูปภาพที่สร้าง 1" aria-hidden="false"><img width="941" height="1672" alt="รูปภาพที่สร้าง 1" src="blob:https://chatgpt.com/bf3d2a97-8042-4dbf-b0f2-80642122367a"></button></div></div></div></div>';
    const reasoningHtml=()=>'<div class="block-BQZwFn"><span hidden data-chatgpt-agent-turn-start></span><div>Worked 57s</div></div>';
    const reasonedGalleryHtml=()=>galleryHtml().replace('<span hidden data-chatgpt-agent-turn-start></span>','');
    const mount=(gallery=false)=>{history.replaceState({},'','/c/fixture');document.body.innerHTML='<main><div class="group flex flex-col pb-2 pt-2"><div class="flex flex-col gap-3">'+userHtml()+(gallery?galleryHtml():assistantHtml())+'</div><div class="turn-action-controls"><button aria-label="คัดลอก">copy</button><button aria-label="ให้คะแนนคำตอบ">rate</button></div></div></main><textarea></textarea>';busy=false;};
    const mountReasoned=()=>{mount();document.querySelector('.flex.flex-col.gap-3').innerHTML=userHtml()+reasoningHtml()+reasonedGalleryHtml();loadImages();};
    const loadImages=()=>{for(const image of document.images)Object.defineProperties(image,{
      complete:{value:true,configurable:true},naturalWidth:{value:1024,configurable:true},naturalHeight:{value:1536,configurable:true}});};
    ${part('  function chatGPTConversationFrames(', '  function explicitImageFailure(')}
    ${part('  function thirdPartyContentFailure(', '  function storyImageReferenceRequest(')}
    ${part('  function storyImageReferenceRequest(', '  function stopButton(')}
    ${part('  function chatGPTKnownRenderedRequestMatches(', '  function chatGPTMotionServiceErrorSnapshot(')}
    ${part('  function motionRequestMatches(', '  function extractMotionJson(')}
    ${part('  function analysisAnswerNode(', '  function analysisResponseStopButton(')}
    ${part('  function confirmedStoryImageServiceError(', '  async function waitStoryImageServiceRetry(')}
    ${part('  function storyImageAssetKey(', '  function createStoryImageWaitMonitor(')}
    ${part('  function generatedImageElements(', '  async function collectConversationImageUrls(')}
    ${part('  function storyImageRecoveryError(', '  async function readStoryImageCheckpoint(')}
    ${part('  function createStoryImageReceipt(', '\n  function largeAssistantImages(')}
    ${part('  async function sendAndVerify(', '  async function ensureAiWebModel(')}
  `});
  await page.evaluate(()=>mount());
  eq(await page.evaluate(()=>document.querySelectorAll('[data-message-author-role],[data-testid^="conversation-turn-"]').length),0,'fixture has none of the retired role/turn selectors');
  eq(await page.evaluate(()=>[userTurns().length,assistantTurns().length,chatGPTConversationFrames().length]),[1,1,2]);
  eq(await page.evaluate(()=>chatGPTMotionRequestText(userTurns()[0])===prompt),true,'full canonical prompt excludes heading/actions and exact suffix only');
  eq(await page.evaluate(()=>storyUserBody(chatGPTConversationFrames()[0])===prompt),true);
  eq(await page.evaluate(()=>motionRequestMatches(prompt)),true);
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt).owner),{conversation_url:'https://chatgpt.com/c/fixture',request_turn_id:'fallback-turn-0:0:user',request_message_id:'owned-user'});
  eq(await page.evaluate(()=>analysisAnswerNode(latestAssistantStrictlyAfterLatestUser()).textContent),await page.evaluate(()=>answer),'no role heading or controls in answer text');
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt).reason),'no_image');
  eq(await page.evaluate(()=>{const o=storyImageWaitObservation(prompt);return {busy:o.busy,complete:o.completedControl,reference:storyImageReferenceRequest(chatGPTFrameAssistant(o.state.turn).textContent)};}),{busy:false,complete:true,reference:true});
  eq(await page.evaluate(()=>storyImageRefusal(answer)),false,'missing reference is not policy refusal');
  eq(await page.evaluate(()=>chatGPTConversationFrames()[1].querySelectorAll('button').length),0,'observed completion controls are outside semantic unit');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt+' changed').reason),'request_missing');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{request_message_id:'another-user'}).reason),'request_missing');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{request_turn_id:'fallback-turn-2:0:user'}).reason),'request_missing');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{before_turn:0}).reason),'request_missing','preexisting request is not acceptance of another Send');
  eq(await page.evaluate(()=>storyImageMissingRequestEvidence('another prompt',{prompt:'another prompt',request_turn_id:'conversation-turn-12',conversation_url:location.href})),null,'legacy missing-request proof cannot ignore occupied semantic history');
  await page.evaluate(()=>document.querySelector('main > div').insertAdjacentHTML('beforeend',userHtml('fallback-turn-1:0:user','later','new unrelated request')));
  eq(await page.evaluate(()=>latestAssistantStrictlyAfterLatestUser()),null,'newer user blocks older assistant');
  eq(await page.evaluate(()=>motionRequestMatches(prompt)),false);
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{conversation_url:'https://chatgpt.com/c/previous'}).reason),'request_not_latest');
  eq(await page.evaluate(()=>chatGPTCompletionButtons(chatGPTConversationFrames()[1]).length),0,'later user prevents borrowing exchange completion controls');
  await page.evaluate(()=>{mount();document.querySelector('main > div').insertAdjacentHTML('beforeend',userHtml('fallback-turn-1:0:user','duplicate'));});
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt).reason),'request_ambiguous');
  await page.evaluate(()=>{mount();busy=true;});
  eq(await page.evaluate(()=>storyImageWaitObservation(prompt).busy),true);
  await page.evaluate(()=>{busy=false;chatGPTConversationFrames()[1].insertAdjacentHTML('beforeend','<div aria-busy="true">generating</div>');});
  eq(await page.evaluate(()=>storyImageWaitObservation(prompt).busy),true,'current-frame activity prevents completed recovery');
  await page.evaluate(()=>{mount();chatGPTConversationFrames()[1].setAttribute('data-is-streaming','true');});
  eq(await page.evaluate(()=>storyImageWaitObservation(prompt).busy),true,'activity on unit itself also vetoes');
  // Retain the existing generated-file URL/size contract; no invented new
  // image selectors. A reference repeated in the response is not new output.
  await page.evaluate(()=>{mount();chatGPTConversationFrames()[0].insertAdjacentHTML('beforeend','<img width="256" height="384" src="https://chatgpt.com/backend-api/estuary/content?id=reference">');
    chatGPTConversationFrames()[1].insertAdjacentHTML('beforeend','<img width="256" height="384" src="https://chatgpt.com/backend-api/estuary/content?id=reference">');loadImages();});
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt).images.length),0,'uploaded/old reference cannot satisfy new-image result');
  await page.evaluate(()=>{chatGPTConversationFrames()[1].insertAdjacentHTML('beforeend','<img width="256" height="384" src="https://chatgpt.com/backend-api/estuary/content?id=new-result">');loadImages();});
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt).reason),'image_ready');
  eq(await page.evaluate(()=>storyImageAssetKey(chatGPTStoryImageSnapshot(prompt).images[0])),'https://chatgpt.com/backend-api/estuary/content?id=new-result');
  await page.evaluate(()=>{mount(true);loadImages();});
  eq(await page.evaluate(()=>[chatGPTConversationFrames().length,assistantTurns().length]),[2,1],'observed image-only message is an assistant frame without a unit key');
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt).reason),'image_ready','observed scoped gallery blob is generated media');
  eq(await page.evaluate(()=>chatGPTCompletionButtons(chatGPTConversationFrames()[1]).filter(button=>button.closest('.turn-action-controls')).length),2,'gallery completion controls use the same owned exchange only');
  eq(await page.evaluate(()=>storyImageAssetKey(chatGPTStoryImageSnapshot(prompt).images[0])),'blob:https://chatgpt.com/bf3d2a97-8042-4dbf-b0f2-80642122367a');
  await page.evaluate(()=>mountReasoned());
  eq(await page.evaluate(()=>[chatGPTConversationFrames().length,assistantTurns().length,chatGPTStoryImageSnapshot(prompt).reason]),[2,1,'image_ready'],'completed image after a separate reasoning block belongs to the exact owned request');
  eq(await page.evaluate(()=>chatGPTGeneratedGalleryFrame(document.querySelector('[data-chatgpt-search-message-ids="gallery-message"]'))),true,'a direct assistant heading proves the gallery even when its agent marker is in the prior reasoning block');
  const receiptProof=await page.evaluate(async()=>{
    const pkg={job:{id:activeJobId},request:{},image_urls:[],scene_repair:{enabled:true}};
    const receipt=createStoryImageReceipt(pkg,2,[prompt,'','',''],1);
    await receipt.restore();await receipt.begin();
    await receipt.submitted(prompt,{request_message_id:'owned-user',request_turn_id:'fallback-turn-0:0:user'});
    const generated=chatGPTStoryImageSnapshot(prompt).images[0];
    await receipt.generated(generated);
    const key='smartpostStoryGeneratedImage:chatgpt:'+activeJobId+':2';
    const saved=savedReceipts[key];
    const restored=await receipt.restore();
    return {status:saved.status,url:saved.image_url,restored,dispatches};
  });
  eq(receiptProof,{status:'generated',url:'blob:https://chatgpt.com/bf3d2a97-8042-4dbf-b0f2-80642122367a',restored:'data:image/png;base64,fixture',dispatches:0},'actual receipt accepts and restores only the owned completed image after reasoning without another Send');
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt,new Set(),{request_message_id:'wrong-user'}).reason),'request_missing','wrong message owner cannot adopt the reasoned gallery');
  await page.evaluate(()=>{mountReasoned();document.querySelector('.text-size-chat').textContent='old unrelated request';document.querySelector('main').insertAdjacentHTML('beforeend','<div class="group flex flex-col pb-2 pt-2"><div class="flex flex-col gap-3">'+userHtml('fallback-turn-1:0:user','current-user')+assistantHtml('Still working','fallback-turn-1:2:assistant')+'</div></div>');});
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot(prompt).images.length),0,'a completed old gallery before the current request is not the new result');
  await page.evaluate(()=>{mountReasoned();document.querySelector('[data-user-message-bubble="true"]').insertAdjacentHTML('beforeend',reasonedGalleryHtml().replace('gallery-message','source-gallery'));loadImages();});
  eq(await page.evaluate(()=>chatGPTGeneratedGalleryFrame(document.querySelector('[data-chatgpt-search-message-ids="source-gallery"]'))),false,'a source gallery nested inside a user bubble cannot become assistant output');
  eq(await page.evaluate(async()=>{
    const pkg={job:{id:activeJobId},request:{},image_urls:[],scene_repair:{enabled:true}};
    const checks=[];
    for(const [index,owner,image] of [
      [3,{request_message_id:'wrong-user'},document.querySelector('[data-chatgpt-search-message-ids="gallery-message"] img')],
      [4,{request_message_id:'owned-user'},document.querySelector('[data-chatgpt-search-message-ids="source-gallery"] img')]]){
      const receipt=createStoryImageReceipt(pkg,index,[prompt,'','',''],1);
      await receipt.restore();await receipt.begin();await receipt.submitted(prompt,owner);
      const key='smartpostStoryGeneratedImage:chatgpt:'+activeJobId+':'+index;
      const before=JSON.stringify(savedReceipts[key]);
      let rejected=false;try{await receipt.generated(image);}catch{rejected=true;}
      checks.push(rejected && JSON.stringify(savedReceipts[key])===before);
    }
    return checks;
  }),[true,true],'actual receipt preserves wrong-owner and uploaded-source exclusions after reasoning');
  await page.evaluate(()=>{mount(true);loadImages();});
  await page.evaluate(()=>document.querySelector('[data-testid="generated-image-preview"]').removeAttribute('data-testid'));
  eq(await page.evaluate(()=>generatedImageElements(document).length),0,'arbitrary blob image in wrapper is not generated media');
  await page.evaluate(()=>{mount(true);loadImages();document.querySelector('h4[data-conversation-role="assistant"]').remove();});
  eq(await page.evaluate(()=>generatedImageElements(document).length),0,'gallery alone cannot authorize arbitrary user-upload blob');
  await page.evaluate(()=>{mount(true);loadImages();document.querySelector('[data-chatgpt-agent-turn-start]').remove();});
  eq(await page.evaluate(()=>generatedImageElements(document).length),1,'assistant heading plus message-owned gallery remains valid without a direct agent marker');
  await page.evaluate(()=>{mount(true);loadImages();document.querySelector('img').src='blob:https://unrelated.example/bf3d2a97-8042-4dbf-b0f2-80642122367a';});
  eq(await page.evaluate(()=>generatedImageElements(document).length),0,'other-origin blobs stay excluded');
  await page.evaluate(()=>{mount(true);loadImages();const gallery=document.querySelector('[data-chatgpt-search-message-ids="gallery-message"]');gallery.innerHTML+='<div data-user-message-bubble="true">upload</div>';});
  eq(await page.evaluate(()=>generatedImageElements(document).length),0,'user reference marker vetoes gallery classification');
  // A legacy wrapper enclosing semantic markup counts once and keeps its
  // old saved message/turn identity. This is a compatibility fixture only.
  await page.evaluate(()=>{document.body.innerHTML='<main><article data-testid="conversation-turn-7"><div data-message-author-role="user" data-message-id="legacy"><div class="whitespace-pre-wrap">'+prompt+'</div></div></article><article data-testid="conversation-turn-8"><div data-message-author-role="assistant">legacy complete answer</div></article></main>';});
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt).owner.request_message_id),'legacy');
  eq(await page.evaluate(()=>analysisAnswerNode(latestAssistantStrictlyAfterLatestUser()).textContent),'legacy complete answer');
  eq(await page.evaluate(()=>storyTurnNumber(chatGPTConversationFrames()[0])),7);
  await page.evaluate(()=>{document.querySelector('[data-message-author-role=user]').setAttribute('data-chatgpt-search-unit-key','fallback-turn-0:0:user');});
  eq(await page.evaluate(()=>[chatGPTConversationFrames().length,userTurns().length]),[2,1],'nested semantic marker does not double-count legacy user');
  // Full production Send acceptance path: exactly one trusted background
  // dispatch followed by exact semantic user/message proof, no retries.
  const sent=await page.evaluate(async()=>{document.body.innerHTML='<main></main><textarea></textarea><button type="submit" aria-label="ส่ง">send</button>';composer().value=SmartFlowSingleAnswer.wrap(prompt);dispatches=0;events=[];
    const owner=await sendAndVerify(document.querySelector('button'),composer(),0,'',0,false,{scene_index:14,onDispatch:async()=>({nonce:'fixture'})});
    return {owner,dispatches,accepted:events.some(row=>row[0]==='ai_send_accepted')};});
  eq(sent.dispatches,1);eq(sent.accepted,true);eq(sent.owner.request_message_id,'owned-user');
  for(const provisional of ['/c/WEB:135591fa-0899-49ad-890c-b3714c65f725','/c/local-chatgpt%3Aa027289b-0899-49ad-890c-b3714c65f725']){
    eq(await page.evaluate(async route=>{mount();history.replaceState({},'',route);const state={};await revealChatGPTAnswer(prompt,state);history.replaceState({},'','/c/6ab5594d-be8c-83ec-bfbe-b27148f1ebd1');await revealChatGPTAnswer(prompt,state);return state.binding.messageId;},provisional),'owned-user','observed temporary route canonicalizes only with exact owner');
  }
  // 437: analysis history disappears after scene 4 Send. Stable IDs must
  // identify the current request even though the visible ordinal shrinks.
  const shrinking=await page.evaluate(()=>{
    mount();dispatches=0;
    const main=document.querySelector('main');
    main.innerHTML='<section id="old-analysis">'+userHtml('analysis:user','analysis-user','old analysis')+assistantHtml('old analysis result','analysis:assistant')+'</section>'
      +[1,2,3].map(n=>'<section>'+userHtml('scene-'+n+':user','scene-'+n,'earlier scene '+n)+assistantHtml('saved earlier','scene-'+n+':assistant')+'</section>').join('');
    const proof={prompt,conversation_url:location.href,before_turn:Math.max(...chatGPTConversationFrames().map(storyTurnNumber)),
      before_message_ids:chatGPTConversationFrames().filter(chatGPTFrameUser).map(frame=>chatGPTUserMessageId(chatGPTFrameUser(frame))),
      before_frame_ids:chatGPTConversationFrames().filter(chatGPTFrameUser).map(chatGPTFrameId)};
    main.insertAdjacentHTML('beforeend','<section>'+userHtml('scene-4:user','scene-4')+reasoningHtml()+reasonedGalleryHtml()+'</section>');loadImages();
    const original=chatGPTStoryRequest(prompt,proof).reason;
    document.querySelector('#old-analysis').remove();
    const legacy={prompt,conversation_url:location.href,before_turn:proof.before_turn};
    return {original,shrunk:chatGPTStoryRequest(prompt,proof).reason,image:chatGPTStoryImageSnapshot(prompt,new Set(),proof).reason,
      owner:chatGPTStoryRequest(prompt,proof).owner.request_message_id,
      legacyBefore:chatGPTStoryRequest(prompt,legacy).reason,
      legacyAfter:chatGPTStoryImageSnapshot(prompt,new Set(),{...legacy,post_refresh_recheck:true}).reason,
      dispatches};
  });
  eq(shrinking,{original:'request_found',shrunk:'request_found',image:'image_ready',owner:'scene-4',
    legacyBefore:'request_missing',legacyAfter:'image_ready',dispatches:0},'scene4 is collected without another Send after DOM shrinks or legacy receipt refreshes');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{conversation_url:location.href,before_turn:999,
    before_message_ids:['old-user-id'],before_frame_ids:['scene-4:user']}).owner?.request_message_id),'scene-4','new stable message ID wins even if a virtualized semantic ordinal key is reused');
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{conversation_url:location.href,before_turn:999,
    before_message_ids:['scene-4'],before_frame_ids:['scene-4:user']}).reason),'request_missing','pre-existing exact request still cannot accept a new Send');
  await page.evaluate(()=>document.querySelector('main').insertAdjacentHTML('beforeend',userHtml('duplicate:user','duplicate')));
  eq(await page.evaluate(()=>chatGPTStoryRequest(prompt,{conversation_url:location.href,before_turn:999,post_refresh_recheck:true}).reason),'request_ambiguous','legacy refresh never chooses between duplicate exact requests');
  // Full trusted Send -> durable receipt -> timeout -> production recovery
  // monitor. Empty live composer is not treated as proof of acceptance.
  await page.addScriptTag({content:part('  function createStoryImageWaitMonitor(', '  async function recoverOwnedStoryImage(')
    +'recoverOwnedStoryImage=('+part('  async function recoverOwnedStoryImage(', '  async function claimUnavailablePendingStep(').trim()+');'});
  const timeoutRecovery=await page.evaluate(async()=>{
    mount();document.querySelector('.whitespace-pre-wrap').textContent='previous scene already saved';
    document.querySelector('[data-markdown-text-style]').textContent='previous response';
    document.body.insertAdjacentHTML('beforeend','<button type="submit" aria-label="ส่ง">send</button>');
    clock=Date.now();const initial=clock,originalNow=Date.now;Date.now=()=>clock;
    const messages=[];
    chrome.runtime.sendMessage=async message=>{
      messages.push(message);
      if(message.type==='CLICK_AI_SEND_BUTTON'){composer().value='';return {ok:true,method:'single_trusted_ai_send'};}
      if(message.type==='RELOAD_CHATGPT_STORY_RESULT')return {ok:true,refresh_scheduled:true};
      throw Error('unexpected mutation '+message.type);
    };
    globalThis.chatGPTComposerAttachmentState=()=>({count:0,busy:false,failed:false});
    const pkg={job:{id:activeJobId},request:{image_files:['saved/reference.png']},image_urls:['http://local/reference'],
      checkpoint_images:['saved/scene1.png','saved/scene2.png','saved/scene3.png'],
      browser_recovery:{version:1,image_post_refresh_redo:{version:1}}};
    const beforeCheckpoints=JSON.stringify(pkg.checkpoint_images),receipt=createStoryImageReceipt(pkg,8,[prompt,'','',''],3);
    await receipt.restore();await receipt.begin();composer().value=SmartFlowSingleAnswer.wrap(prompt);
    let error;
    try{await sendAndVerify(document.querySelector('button[type=submit]'),composer(),1,'previous scene already saved',1,false,
      {scene_index:8,completedCount:3,postRefreshRedo:true,onDispatch:(text,baseline)=>receipt.dispatching(text,baseline),
        onAcceptanceTimeout:(text,baseline,monitor)=>receipt.acceptanceTimeout(text,baseline,monitor)});}catch(caught){error=caught;}
    const saved=savedReceipts['smartpostStoryGeneratedImage:chatgpt:'+activeJobId+':8'];Date.now=originalNow;
    return {code:error?.code,clicks:messages.filter(m=>m.type==='CLICK_AI_SEND_BUTTON').length,
      reloads:messages.filter(m=>m.type==='RELOAD_CHATGPT_STORY_RESULT').length,phase:saved.send_phase,
      promptKept:saved.result_proof.prompt===prompt,referenceKept:saved.identity.includes('saved/reference.png'),
      checkpointsKept:beforeCheckpoints===JSON.stringify(pkg.checkpoint_images),waited:clock-initial>=60000&&clock-initial<=65000};
  });
  eq(timeoutRecovery,{code:'STORY_IMAGE_REFRESH_SCHEDULED',clicks:1,reloads:1,phase:'dispatching',
    promptKept:true,referenceKept:true,checkpointsKept:true,waited:true},'unconfirmed Send enters owned refresh instead of terminal review; no duplicate Send or checkpoint loss');
  // D87DD1 installed437: five semantic text units followed by an ID-only
  // generated gallery. The completed image is recognized by existing source;
  // the stale waiting_response trace was from the reload handoff, not this DOM.
  const idOnlyGallery=await page.evaluate(()=>{
    mount();dispatches=0;
    document.querySelector('main').innerHTML='<div class="group flex flex-col pb-2 pt-2"><div class="flex flex-col gap-3">'
      +userHtml('fallback-turn-0:0:user','old-analysis','analysis request')+assistantHtml('analysis result','fallback-turn-0:2:assistant')
      +userHtml('fallback-turn-1:0:user','old-binding','binding request')+assistantHtml('binding result','fallback-turn-1:2:assistant')
      +userHtml('fallback-turn-2:0:user','66872beb-700c-4d8c-988f-ec654547be2b')
      +galleryHtml().replace('gallery-message','c188672a-4237-4d0b-a424-eb2effde91d1')+'</div></div>';loadImages();
    const proof={conversation_url:location.href,request_turn_id:'fallback-turn-2:0:user',
      request_message_id:'66872beb-700c-4d8c-988f-ec654547be2b'};
    const state=chatGPTStoryImageSnapshot(prompt,new Set(),proof);
    return {semanticUnits:document.querySelectorAll('[data-chatgpt-search-unit-key]').length,
      frames:chatGPTConversationFrames().length,request:chatGPTStoryRequest(prompt,proof).reason,
      result:state.reason,images:state.images.length,galleryId:state.turn?.getAttribute('data-chatgpt-search-message-ids'),
      galleryUnit:state.turn?.getAttribute('data-chatgpt-search-unit-key'),dispatches};
  });
  eq(idOnlyGallery,{semanticUnits:5,frames:6,request:'request_found',result:'image_ready',images:1,
    galleryId:'c188672a-4237-4d0b-a424-eb2effde91d1',galleryUnit:null,dispatches:0},
    'observed ID-only gallery after the exact accepted request is ready without another Send');
  const legacyGallery=await page.evaluate(async()=>{
    const pkg={job:{id:activeJobId},request:{},image_urls:[],
      browser_recovery:{version:1,image_post_refresh_redo:{version:1}}};
    const receipt=createStoryImageReceipt(pkg,10,[prompt,'','',''],0);
    await receipt.restore();await receipt.begin();
    await receipt.dispatching(prompt,{conversation_url:location.href,before_turn:3});
    await receipt.submitted(prompt,{conversation_url:location.href,request_turn_id:'fallback-turn-2:0:user',
      request_message_id:'66872beb-700c-4d8c-988f-ec654547be2b'});
    const key='smartpostStoryGeneratedImage:chatgpt:'+activeJobId+':10';
    const original=savedReceipts[key];
    savedReceipts[key]={...original,refresh_recovery:{version:1,phase:'checking',send_nonce:original.send_nonce,
      conversation_url:location.href,claimed_at:Date.now()-90000,ready_at:Date.now()-60000}};
    let sent=0;chrome.runtime.sendMessage=async()=>{sent++;throw Error('existing image must not dispatch anything');};
    const image=await receipt.restore();
    return {image,status:savedReceipts[key].status,sent,promptUnchanged:savedReceipts[key].result_proof.prompt===prompt};
  });
  eq(legacyGallery,{image:'data:image/png;base64,fixture',status:'generated',sent:0,promptUnchanged:true},
    'legacy437 unfenced checking receipt saves its actual ready image without requiring another refresh or Send');
  // The actual START handler distinguishes a newly started runner from an
  // old document that is still running. ok:true alone cannot prove a reload
  // handoff; the old runner will disappear when navigation finally commits.
  await page.addScriptTag({content:'function testContentStartHandoff(message,sendResponse){'
    +part('    if (message?.type !== "START_CHATGPT_JOB") return;', '\n  });')+'}'});
  const starts=await page.evaluate(()=>{
    let count=0;globalThis.runJob=async()=>{count++;};
    const previousJob=activeJobId,previousRun=activeRunId;
    const message={type:'START_CHATGPT_JOB',accept_existing_run:true,package:{job:{id:activeJobId},run_id:activeRunId}};
    let oldAck,newAck;
    testContentStartHandoff(message,ack=>oldAck=ack);
    const oldStarts=count;
    activeJobId='';activeRunId='';testContentStartHandoff(message,ack=>newAck=ack);
    activeJobId=previousJob;activeRunId=previousRun;
    return {oldAck,oldStarts,newAck,newStarts:count};
  });
  eq([starts.oldAck,starts.oldStarts],[{ok:true,started:false,already_running:true},0],
    'old document idempotent ACK is not proof that a refreshed runner started');
  eq([starts.newAck,starts.newStarts],[{ok:true,started:true},1],'new document starts exactly one runner');
  console.log(JSON.stringify({ok:true,cases:checks,providerSubmissions:0}));
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exit(1);});
