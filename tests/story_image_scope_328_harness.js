const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const root=path.join(__dirname,'..'),source=fs.readFileSync(process.env.SMARTFLOW_TEST_IMAGE_SOURCE||path.join(root,'browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>{const x=source.indexOf(a),y=source.indexOf(b,x+a.length);assert(x>=0&&y>x);return source.slice(x,y);};
(async()=>{const browser=await chromium.launch({headless:true});try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const html=fs.readFileSync(path.join(__dirname,'fixtures/chatgpt-story-empty-328.html'),'utf8');
  await page.route('**/*',r=>r.request().url()==='https://chatgpt.com/c/fixture'
    ?r.fulfill({contentType:'text/html',body:html}):r.abort());
  await page.goto('https://chatgpt.com/c/fixture');
  await page.addScriptTag({content:`let IS_GEMINI=false;const visible=()=>true;
    let ticks=0,stops=0,cancelled=false,onSleep=null,sent=false,busy=false,events=[];
    const Date={now:()=>ticks};
    const assertNotCancelled=()=>{if(cancelled)throw Error('cancelled');};
    const sleep=async ms=>{ticks+=ms;if(onSleep)onSleep(ms);};
    const stopButtonVisible=()=>busy,stopButton=()=>({click:()=>stops++});
    const stopStalledChatGPTGeneration=async()=>{stops++;return false;};
    const report=async(...args)=>events.push(args);
    const AI_NAME='ChatGPT',CHATGPT_COMPLETE_IMAGE_GRACE_MS=45000,CHATGPT_IMAGE_STALL_WARNING_MS=120000,CHATGPT_IMAGE_STALL_ABORT_MS=180000;
    const waitForResponseIdle=async()=>{},setChatGPTImageTool=async()=>{},waitForComposer=async()=>({}),setComposerText=async e=>e,sendButton=()=>({});
    const recordStoryImageRequest=async()=>{},attachSourceImages=async()=>{};
    const imageGenerationSignature=(turn,images)=>JSON.stringify(images.map(i=>i.src));
    const storyImageNoResultReady=()=>false;
    let sendAndVerify=async()=>{sent=true;};
    const loadImages=()=>{for(const image of document.images)Object.defineProperties(image,{
      complete:{value:true,configurable:true},naturalWidth:{value:941,configurable:true},naturalHeight:{value:1672,configurable:true}});};
    const addCurrent=(id='file_current',layers=3)=>{document.querySelector('.result').innerHTML=Array.from({length:layers},(_,i)=>'<img src="https://chatgpt.com/backend-api/estuary/content?id='+id+'&v='+i+'">').join('');loadImages();};
    `+part('  function chatGPTConversationFrames(','  function explicitImageFailure(')+
    part('  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')+
    part('  function motionRequestIsLatestUser(','  async function sendAndVerify(')+
    part('  function generatedImageElements(','  async function collectConversationImageUrls(')+
    part('  function storyImageRecoveryError(','  function sameStoryImageReceipt(')+
    part('  function confirmedStoryImageServiceError(','  function storyImageNoResultReady(')+
    'const storyImageRefusal=()=>false,storyImageReferenceRequest=()=>false;'+
    part('  function retryableCompletedImageText(','  async function waitStoryImageServiceRetry(')+
    part('  function storyImageAssetKey(','  function createStoryImageReceipt(')+
    part('  async function submitImagePrompt(','  async function imageData(')});
  assert.deepEqual(errors,[]);await page.evaluate(()=>loadImages());
  assert.deepEqual(await page.evaluate(()=>{const s=chatGPTStoryImageSnapshot('current scene prompt');return {reason:s.reason,count:s.images.length};}),{reason:'no_image',count:0});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('missing').reason),'request_missing');
  await page.evaluate(()=>addCurrent());
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').images.length),1,'Three layers = one result');
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt',new Set(['https://chatgpt.com/backend-api/estuary/content?id=file_current&v=older'])).reason),'no_image','Renewed URL is not new image');
  await page.evaluate(()=>{addCurrent('file_old');});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'no_image','Old asset placed under new answer excluded');
  await page.evaluate(()=>{addCurrent();const i=document.createElement('img');i.src='https://chatgpt.com/backend-api/estuary/content?id=file_other';document.querySelector('.result').append(i);loadImages();});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'image_ready','Owned alternatives need no preference controls');
  assert.equal(await page.evaluate(()=>{
    const proof={selected_image_asset_key:'https://chatgpt.com/backend-api/estuary/content?id=file_other'};
    return storyImageAssetKey(chatGPTStoryImageSnapshot('current scene prompt',new Set(),proof).images[0]);
  }),'https://chatgpt.com/backend-api/estuary/content?id=file_other','Persisted selection survives different DOM order');
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt',new Set(),{
    selected_image_asset_key:'https://chatgpt.com/backend-api/estuary/content?id=missing_selected'}).reason),
    'image_loading','Missing pinned selection cannot silently become the other alternative');
  await page.evaluate(()=>document.querySelector('.result').insertAdjacentHTML('beforeend','<style>.mobile-choice{display:none}@media(max-width:640px){.mobile-choice{display:inline}.desktop-choice{display:none}}</style><div>คุณชอบภาพใดมากกว่า</div><button><div><svg></svg><span class="mobile-choice">ภาพ 1</span><span class="desktop-choice">ภาพที่ 1 ดีกว่า</span></div></button><button><div><svg></svg><span class="mobile-choice">ภาพ 2</span><span class="desktop-choice">ภาพที่ 2 ดีกว่า</span></div></button>'));
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'image_ready','Preference pair is not an ambiguous scene');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'image_ready','Mobile hidden desktop label still identifies pair');
  await page.setViewportSize({width:1280,height:900});
  assert.equal(await page.evaluate(()=>storyImageAssetKey(chatGPTStoryImageSnapshot('current scene prompt').images[0])),'https://chatgpt.com/backend-api/estuary/content?id=file_current');
  assert.equal(await page.evaluate(async()=>storyImageAssetKey(await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href}))),'https://chatgpt.com/backend-api/estuary/content?id=file_current','Resume recovers comparison without Send');
  assert.equal(await page.evaluate(async()=>{
    let saved=null;await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href},async owner=>{saved=owner;});
    return saved?.selected_image_asset_key;
  }),'https://chatgpt.com/backend-api/estuary/content?id=file_current','Resume ACKs selected asset in exact result proof');
  assert.equal(await page.evaluate(async()=>{
    try{await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href},async owner=>{
      if(owner.selected_image_asset_key)throw Error('selection ACK missing');});return false;
    }catch(error){return error.message==='selection ACK missing';}
  }),true,'Unknown selection persistence never proceeds to collection');
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('missing').reason),'request_missing');
  await page.evaluate(()=>{for(const i of document.querySelectorAll('.result img'))if(i.src.includes('file_current'))Object.defineProperty(i,'complete',{value:false,configurable:true});});
  assert.equal(await page.evaluate(()=>storyImageAssetKey(chatGPTStoryImageSnapshot('current scene prompt').images[0])),'https://chatgpt.com/backend-api/estuary/content?id=file_other','Ready second image can be selected');
  await page.evaluate(()=>{for(const i of document.querySelectorAll('.result img'))Object.defineProperty(i,'complete',{value:false,configurable:true});});
  assert.notEqual(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'image_ready','Never download two loading alternatives');
  await page.evaluate(()=>{addCurrent();for(const i of document.querySelectorAll('.result img'))Object.defineProperty(i,'complete',{value:false,configurable:true});});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'image_loading');
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'','An undecoded loading image is not a failed load');
  await page.evaluate(()=>{for(const i of document.querySelectorAll('.result img'))Object.defineProperties(i,{complete:{value:true,configurable:true},naturalWidth:{value:0,configurable:true},naturalHeight:{value:0,configurable:true}});});
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'image_load_failed','A completed broken image has concrete DOM failure evidence');
  await page.evaluate(()=>{busy=true;});
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'','Ongoing generation vetoes broken-image recovery');
  await page.evaluate(()=>{busy=false;document.querySelector('.result').innerHTML='<div data-message-author-role="assistant"></div><button data-testid="copy-turn-action-button">Copy</button>';});
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'empty_completed_response');
  await page.evaluate(()=>{document.querySelector('.result').innerHTML='<div data-message-author-role="assistant"><p>เกิดข้อผิดพลาดในสตรีมของข้อความ</p><button>ลองใหม่</button></div>';});
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'completed_service_error');
  await page.evaluate(()=>{busy=true;});
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'','Streaming overrides error text');
  await page.evaluate(()=>{busy=false;});
  await page.evaluate(()=>document.querySelector('.result').insertAdjacentHTML('beforeend','<div role="progressbar" aria-valuenow="40"></div>'));
  assert.equal(await page.evaluate(()=>storyImageWaitObservation('current scene prompt').stalledReason),'','Visible current response progress vetoes refresh');
  await page.evaluate(()=>{document.querySelector('.result').innerHTML='';});
  // Recovery re-queries newly mounted nodes and deduplicates changed URL layers.
  assert.equal(await page.evaluate(async()=>{document.querySelector('.result').innerHTML='';onSleep=()=>{addCurrent();onSleep=null;};return storyImageAssetKey(await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href}));}),'https://chatgpt.com/backend-api/estuary/content?id=file_current');
  assert.equal(await page.evaluate(async()=>{addCurrent();onSleep=()=>{addCurrent('file_changed');onSleep=null;};const image=await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href});return storyImageAssetKey(image);}),'https://chatgpt.com/backend-api/estuary/content?id=file_changed','Changed result needs a fresh stable check');
  assert.equal(await page.evaluate(async()=>storyImageAssetKey(await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:'https://chatgpt.com/c/other',request_message_id:'previous-chat-message'}))),'https://chatgpt.com/backend-api/estuary/content?id=file_changed','Authorized cross-chat exact-prompt recovery');
  assert.equal(await page.evaluate(async()=>recoverOwnedStoryImage({prompt:'different full prompt',conversation_url:'https://chatgpt.com/c/other'})),null,'Different chat does not authorize a different scene');
  assert.equal(await page.evaluate(async()=>{document.querySelector('.result').innerHTML='';const start=ticks;const result=await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href});return result===null&&ticks-start===30000;}),true,'Bounded passive empty-result recovery');
  assert.equal(await page.evaluate(async()=>{
    const start=ticks;busy=true;document.querySelector('.result').innerHTML='';
    onSleep=()=>{if(ticks-start>480000){addCurrent();busy=false;onSleep=null;}};
    const result=await recoverOwnedStoryImage({prompt:'current scene prompt',conversation_url:location.href},null,{scene_index:12,completedCount:11});
    return Boolean(result)&&ticks-start>480000;
  }),true,'Accepted receipt Resume waits for an eight-minute generation, without another Send');
  await page.evaluate(()=>{const duplicate=document.querySelector('[data-testid="conversation-turn-23"]').cloneNode(true);duplicate.id='duplicate';document.body.append(duplicate);});
  assert.equal(await page.evaluate(()=>chatGPTStoryImageSnapshot('current scene prompt').reason),'request_ambiguous');
  await page.evaluate(()=>document.querySelector('#duplicate').remove());
  // Full production wait loop, not just an extracted if. Simulate accepted Send,
  // old scene React remount and empty current answer from the observed page.
  for(const mode of ['old_remount_busy','old_remount_idle','current_busy','current_idle','slow_busy','slow_loading','two_results','wrong_prompt','cancel']){
    const result=await page.evaluate(async mode=>{
      const user=document.querySelector('[data-testid="conversation-turn-23"]'),reply=document.querySelector('[data-testid="conversation-turn-24"]');
      user.remove();reply.remove();reply.querySelector('.result').innerHTML='';user.querySelector('.whitespace-pre-wrap').textContent='current scene prompt';
      ticks=0;stops=0;events=[];cancelled=false;sent=false;busy=!['old_remount_idle','current_idle','slow_loading'].includes(mode);onSleep=null;loadImages();
      sendAndVerify=async()=>{
        document.body.append(user,reply);sent=true;
        // Identity unchanged, node and URL spelling changed in the older turn.
        const old=document.querySelector('#old-image');old.innerHTML=old.innerHTML.replaceAll('v=','display=');loadImages();
        if(mode.startsWith('current'))addCurrent();
        if(mode==='slow_loading'){addCurrent();for(const image of reply.querySelectorAll('img'))Object.defineProperty(image,'complete',{value:false,configurable:true});}
        if(mode==='wrong_prompt'){user.querySelector('.whitespace-pre-wrap').textContent='different scene prompt';addCurrent();}
      if(mode==='two_results'){addCurrent();reply.querySelector('.result').insertAdjacentHTML('beforeend','<img src="https://chatgpt.com/backend-api/estuary/content?id=file_second">');loadImages();}
      };
      if(mode==='cancel')onSleep=()=>{if(sent&&ticks>10000)cancelled=true;};
      if(mode==='current_busy')onSleep=()=>{if(sent&&ticks>150000)busy=false;};
      if(mode==='two_results')onSleep=()=>{if(sent&&ticks>150000)busy=false;};
      if(mode.startsWith('old_remount'))onSleep=()=>{if(sent&&ticks>420000)cancelled=true;};
      if(mode.startsWith('slow'))onSleep=()=>{if(sent&&ticks>480000){addCurrent();busy=false;onSleep=null;}};
      let selected='';
      try{const image=await submitImagePrompt('current scene prompt',[],10,'',{scene_index:11,onSubmitted:async(_text,owner)=>{selected=owner?.selected_image_asset_key||selected;}});return{asset:storyImageAssetKey(image),stops,selected,ticks};}
      catch(e){return{code:e.code||e.message,stops};}finally{onSleep=null;cancelled=false;busy=false;}
    },mode);
    assert.equal(result.stops,0,mode+' must never Stop before checkpoint');
    if(mode.startsWith('current')||mode.startsWith('slow')||mode==='two_results')assert.equal(result.asset,'https://chatgpt.com/backend-api/estuary/content?id=file_current');
    else assert.equal(result.code,mode==='cancel'||mode.startsWith('old_remount')?'cancelled':'STORY_IMAGE_RECEIPT_REVIEW',mode);
    if(mode==='two_results'){assert.equal(result.selected,result.asset);assert(result.ticks>150000,'multiple results wait for real generation');}
  }
  const studio=fs.readFileSync(path.join(root,'web_ui/studio.js'),'utf8');
  await page.addScriptTag({content:'const escapeHtml=value=>String(value).replaceAll("<","&lt;");'+studio.slice(studio.indexOf('  function storyFailureMarkup('),studio.indexOf('  function pendingReviewDrafts('))});
  assert.equal(await page.evaluate(()=>storyFailureMarkup({last_error:'STORY_IMAGE_RECEIPT_REVIEW',image_result_review:{message:'empty reply <script>'}}).includes('empty reply &lt;script>')),true);
  console.log('Story328: observed SECTION, current-owner-only, old remount/asset exclusion, layers, ambiguity, loading, fresh recovery, timeout/cancellation no-Stop, actual wait loop and Studio explanation passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
