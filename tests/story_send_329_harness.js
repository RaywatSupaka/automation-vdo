// Actual content Send -> owned reply -> image receipt, in isolated Chromium.
// Provider transport/clock/image bytes are simulated; no live generation.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i);return source.slice(i,j);};
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage();
 const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
 await page.route('**/*',r=>r.request().url()==='https://chatgpt.com/c/fixture'
   ?r.fulfill({contentType:'text/html',body:'<style>img{width:400px;height:710px}</style><main id="thread"></main><form id="composer-form"><div id="prompt-textarea" contenteditable="true"></div><button id="send" type="submit" aria-label="Send message">Send</button></form>'}):r.abort());
 await page.goto('https://chatgpt.com/c/fixture');
 await page.addScriptTag({content:fs.readFileSync('browser_extension/single_answer.js','utf8')});
 await page.addScriptTag({content:`
 const IS_GEMINI=false,PROVIDER_KEY='chatgpt',AI_NAME='ChatGPT',visible=e=>Boolean(e);
 let ticks=1000,busy=false,cancelled=false,onSleep=null,events=[],sends=0,stops=0,storage={},mode='';
 let activeJobId='STORY-TEST',activeRunId='RUN-TEST',requireDownloadOwner=false,cancelRequested=false;
 const Date={now:()=>ticks},sleep=async ms=>{ticks+=ms;if(onSleep)onSleep();};
 const assertNotCancelled=()=>{if(cancelled)throw Error('cancelled');};
 const report=async(...args)=>events.push(args),stopButtonVisible=()=>busy,stopButton=()=>({click:()=>stops++});
 const stopStalledChatGPTGeneration=async()=>{stops++;return false;};
 const composer=()=>document.querySelector('#prompt-textarea');
 const composerText=(e=composer(),raw=false)=>raw?String(e?.textContent||''):SmartFlowSingleAnswer.canonical(String(e?.textContent||'')).trim().replace(/\\s+/g,' ');
 const waitForComposer=async()=>composer(),waitForResponseIdle=async()=>{},setChatGPTImageTool=async()=>{};
 const setComposerText=async(e,text)=>{e.textContent=SmartFlowSingleAnswer.wrap(text);return e;};
 const sendButton=()=>document.querySelector('#send');
 const recordStoryImageRequest=async()=>{},attachSourceImages=async()=>{};
 const imageGenerationSignature=(turn,images)=>JSON.stringify(images.map(i=>i.src));
 const CHATGPT_COMPLETE_IMAGE_GRACE_MS=45000,CHATGPT_IMAGE_STALL_WARNING_MS=120000,CHATGPT_IMAGE_STALL_ABORT_MS=180000;
 const imageDataFromUrl=async url=>{
  if(requireDownloadOwner){const saved=storage[key];
   if(saved.result_proof?.conversation_url!==location.href||saved.result_proof?.request_message_id!=='message-1'
      ||saved.result_proof?.request_turn_id!=='conversation-turn-1')throw Error('Resolved owner must be persisted before download');}
  return url;
 };
 const pkg={job:{id:'STORY-TEST'},request:{image_files:[]},image_urls:[]};
 const key='smartpostStoryGeneratedImage:chatgpt:STORY-TEST:6';
 function user(n,text){const f=document.createElement('section');f.dataset.testid='conversation-turn-'+n;f.dataset.turn='user';
  f.innerHTML='<div data-message-author-role="user" data-message-id="message-'+n+'"><div class="whitespace-pre-wrap"></div><button>ดูเพิ่มเติม</button></div>';
  f.querySelector('.whitespace-pre-wrap').textContent=text;document.querySelector('#thread').append(f);return f;}
 function answer(n){const f=document.createElement('section');f.dataset.testid='conversation-turn-'+n;f.dataset.turn='assistant';
  f.innerHTML='<div data-conversation-screenshot-content><img src="https://chatgpt.com/backend-api/estuary/content?id=file_'+n+'"></div>';
  document.querySelector('#thread').append(f);const i=f.querySelector('img');Object.defineProperties(i,{complete:{value:true},naturalWidth:{value:941},naturalHeight:{value:1672}});return f;}
 globalThis.chrome={runtime:{id:'fixture',sendMessage:async message=>{
  if(message.type==='MEMBERSHIP_AUTHORIZE')return {ok:true};
  if(message.type!=='CLICK_AI_SEND_BUTTON')throw Error('Unexpected transport');sends++;
  if(mode==='not_started')return {ok:false,notDispatched:true,diagnostics:{gesture_phase:'not_started'},error:'preflight blocked'};
  assertClaim(message);composer().textContent='';busy=true;
  if(mode.startsWith('root_')||mode==='existing_switched'){
   const currentPrompt=message.expectedPrompt;
   const populate=()=>{document.querySelector('#thread').replaceChildren();
    if(mode==='root_not_first'){user(1,'unrelated first request');answer(2);user(3,currentPrompt);answer(4);}
    else if(mode==='root_not_latest'){user(1,currentPrompt);answer(2);user(3,'new unrelated scene');answer(4);}
    else{user(1,mode==='root_wrong'?'another complete scene':currentPrompt);answer(2);
     if(mode==='root_ambiguous'){user(3,currentPrompt);answer(4);}}
    busy=false;};
   if(mode==='root_late_message'){
    history.replaceState({},'', '/c/new-scene');const when=ticks+3000;
    onSleep=()=>{if(ticks>=when){populate();onSleep=null;}};
   }else{
    populate();
    if(mode==='root_late_url'){const when=ticks+3000;onSleep=()=>{if(ticks>=when){history.replaceState({},'','/c/new-scene');onSleep=null;}};}
    else if(mode!=='root_url_pending'){
     history.replaceState({},'','/c/new-scene');
     if(mode==='root_owner_switch')onSleep=()=>{history.replaceState({},'','/c/different-chat');onSleep=null;};
    }
   }
  }
  else if(mode==='late'){const when=ticks+3000;onSleep=()=>{if(ticks>=when){user(13,'scene six');answer(14);busy=false;onSleep=null;}};}
  else if(mode==='cancel')onSleep=()=>{cancelled=true;};
  else if(mode==='cleared_only'){busy=false;}
  else if(!['stop_only','old_only'].includes(mode)){
    user(13,mode==='wrong_prompt'?'other scene':'scene six');answer(14);busy=false;
    if(mode==='duplicate')user(15,'scene six');
  }
  return {ok:true,method:'single_trusted_ai_send',diagnostics:{gesture_phase:'released'}};
 }},storage:{local:{get:async()=>structuredClone(storage),set:async data=>{Object.assign(storage,structuredClone(data));}}}};
 function assertClaim(message){if(storage[key].send_phase!=='dispatching'||message.story_send_claim.nonce!==storage[key].send_nonce)throw Error('No durable claim before Send');}
 `+part('  function chatGPTConversationFrames(','  function explicitImageFailure(')+
 part('  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')+
 part('  function resolveChatGPTComposerSendTarget(','  function sendButton(')+
 part('  async function waitForStableSendDraft(','  async function ensureAiWebModel(')+
 part('  function generatedImageElements(','  async function collectConversationImageUrls(')+
 part('  function storyImageRecoveryError(','  function largeAssistantImages(')+
 part('  async function submitImagePrompt(','  async function imageData(')});
 assert.deepEqual(pageErrors,[]);
 for(const mode of ['normal','late','stop_only','cleared_only','busy_before','preflight_resumes','old_only','wrong_prompt','duplicate','cancel','not_started']){
  const result=await page.evaluate(async chosen=>{
   mode=chosen;ticks=1000;busy=false;cancelled=false;onSleep=null;events=[];sends=0;stops=0;storage={};
   document.querySelector('#thread').replaceChildren();composer().textContent='';
   user(11,chosen==='old_only'?'scene six':'scene five');answer(12);
   if(chosen==='busy_before')busy=true;
   if(chosen==='preflight_resumes'){busy=true;onSleep=()=>{if(ticks>2000){busy=false;onSleep=null;}};}
   const receipt=createStoryImageReceipt(pkg,6,['scene six'],5);await receipt.restore();await receipt.begin();
   let error='',asset='';
   try{const image=await submitImagePrompt('scene six',[],5,'',{scene_index:6,
     onDispatch:(text,baseline)=>receipt.dispatching(text,baseline),onSendRejected:()=>receipt.sendNotStarted(),
     onSubmitted:(text,owner)=>receipt.submitted(text,owner)});asset=storyImageAssetKey(image);await receipt.generated(image);}
   catch(e){error=e.message;}
   return {error,asset,sends,stops,ticks,receipt:storage[key],accepted:events.filter(e=>e[0]==='ai_send_accepted'),waiting:events.some(e=>e[0]==='waiting_for_image')};
  },mode);
  assert.equal(result.sends,mode==='busy_before'?0:1,mode);assert.equal(result.stops,0,mode);
  if(['normal','late','preflight_resumes'].includes(mode)){
   assert(result.asset.endsWith('file_14'),mode+JSON.stringify(result));assert.equal(result.receipt.status,'generated');
   assert.equal(result.receipt.result_proof.request_turn_id,'conversation-turn-13');
   assert.equal(result.accepted[0][3].submission_proof,'owned_story_user_turn');
  }else{
   assert.equal(result.waiting,false,mode+' must not enter image wait');assert.equal(result.accepted.length,0,mode);
   assert(result.error.includes(mode==='cancel'?'cancelled':['busy_before','not_started'].includes(mode)?'SEND_NOT_STARTED':'SEND_UNCONFIRMED'),mode+result.error);
   assert(result.ticks<65000,'Must not wait six minutes for a missing request');
  }
 }
 // Resume prepared safely; dispatched/legacy missing prompts must never grant a resend.
 const phases=await page.evaluate(async()=>{
  cancelled=false;busy=false;onSleep=null;document.querySelector('#thread').replaceChildren();storage={};
  let r=createStoryImageReceipt(pkg,6,['scene six'],5);await r.restore();await r.begin();
  let next=createStoryImageReceipt(pkg,6,['scene six'],5);const prepared=await next.restore()===null;
  await next.begin();await next.dispatching('scene six',{conversation_url:location.href,before_turn:12});
  let duplicateBlocked=false;try{await next.dispatching('scene six',{conversation_url:location.href,before_turn:12});}catch{duplicateBlocked=true;}
  const inspect=async()=>{try{await createStoryImageReceipt(pkg,6,['scene six'],5).restore();return false;}catch{return true;}};
  const dispatched=await inspect();delete storage[key].send_phase;delete storage[key].send_nonce;const legacy=await inspect();
  user(13,'scene six');answer(14);const recovered=await createStoryImageReceipt(pkg,6,['scene six'],5).restore();
  return {prepared,duplicateBlocked,dispatched,legacy,recovered};
 });
 assert(phases.prepared&&phases.duplicateBlocked&&phases.dispatched&&phases.legacy);
 assert(phases.recovered.endsWith('file_14'));
 // Same exact prompt can recur; persisted message id owns its answer after remount.
 const owner=await page.evaluate(()=>{
  user(15,'scene six');answer(16);
  const proof={conversation_url:location.href,request_message_id:'message-13',request_turn_id:'conversation-turn-13'};
  const old=document.querySelector('[data-testid="conversation-turn-13"]');old.replaceWith(old.cloneNode(true));
  return {unbound:chatGPTStoryImageSnapshot('scene six').reason,bound:storyImageAssetKey(chatGPTStoryImageSnapshot('scene six',new Set(),proof).images[0])};
 });
 assert.equal(owner.unbound,'request_ambiguous');assert(owner.bound.endsWith('file_14'));
 // Regression330: observed Send started on chatgpt.com/ and committed a new /c/ URL.
 // Use a full multi-paragraph prompt, not a prefix or a "latest image" fallback.
 const prompt='สร้างภาพแนวตั้ง 9:16 หนึ่งภาพจากคำบรรยายต่อไปนี้:\n\nA small caramel and white dog follows a gray-coated man carrying a red bag through a morning market alley.\n\nสถานที่ แสง และภาษาภาพ: {"visual_style":"warm three-dimensional family animation"}\n\nภาพเดียวเต็มเฟรม ไม่มีตัวอักษรหรือลายน้ำ';
 const rootModes=['root_normal','root_late_url','root_late_message','root_wrong','root_ambiguous','root_nonempty','root_not_first','root_not_latest','root_url_pending','root_owner_switch','existing_switched'];
 for(const chosen of rootModes){
  const result=await page.evaluate(async({chosen,prompt})=>{
   mode=chosen;ticks=1000;busy=false;cancelled=false;onSleep=null;events=[];sends=0;stops=0;storage={};
   document.querySelector('#thread').replaceChildren();composer().textContent='';
   history.replaceState({},'',chosen==='existing_switched'?'/c/previous-chat':'/');
   if(['root_nonempty','existing_switched'].includes(chosen)){user(11,'previous scene');answer(12);}
   const receipt=createStoryImageReceipt(pkg,6,[prompt],5);await receipt.restore();await receipt.begin();
   let error='',asset='';
   try{const image=await submitImagePrompt(prompt,[],5,'',{scene_index:6,
     onDispatch:(text,baseline)=>receipt.dispatching(text,baseline),onSendRejected:()=>receipt.sendNotStarted(),
     onSubmitted:(text,owner)=>receipt.submitted(text,owner)});asset=storyImageAssetKey(image);await receipt.generated(image);}
   catch(e){error=e.message;}
   return {error,asset,sends,stops,ticks,receipt:storage[key],accepted:events.filter(e=>e[0]==='ai_send_accepted'),waiting:events.some(e=>e[0]==='waiting_for_image')};
  },{chosen,prompt});
  assert.equal(result.sends,1,chosen);assert.equal(result.stops,0,chosen);
  if(['root_normal','root_late_url','root_late_message','root_nonempty','root_not_first','root_owner_switch','existing_switched'].includes(chosen)){
   const turn=chosen==='root_not_first'?3:1;
   assert.equal(result.error,'',chosen+JSON.stringify(result));assert(result.asset.endsWith('file_'+(turn+1)),chosen);
   assert.equal(result.receipt.status,'generated',chosen);assert.equal(result.receipt.send_phase,'accepted',chosen);
   assert.equal(result.receipt.result_proof.conversation_url,'https://chatgpt.com/c/'+(chosen==='root_owner_switch'?'different-chat':'new-scene'),chosen);
   assert.equal(result.receipt.result_proof.request_message_id,'message-'+turn,chosen);
   assert.equal(result.receipt.result_proof.request_turn_id,'conversation-turn-'+turn,chosen);
   assert.equal(result.accepted.length,1,chosen);
   if(['root_late_url','root_late_message'].includes(chosen))assert(result.ticks>=4000,chosen+' must await route/message evidence');
  }else{
   assert(result.error.includes('SEND_UNCONFIRMED'),chosen+result.error);
   assert.equal(result.asset,'',chosen);assert.equal(result.waiting,false,chosen);assert.equal(result.accepted.length,0,chosen);
   assert.equal(result.receipt.send_phase,'dispatching',chosen);assert(result.ticks<65000,chosen);
  }
 }
 // A real329 persisted dispatching receipt keeps the root URL. Resume must bind
 // the first exact request and download its existing image with zero new Sends.
 const restored=await page.evaluate(async prompt=>{
  mode='';ticks=1000;cancelled=false;busy=false;onSleep=null;events=[];sends=0;stops=0;storage={};
  document.querySelector('#thread').replaceChildren();history.replaceState({},'','/');composer().textContent='';
  const normalized=prompt.trim().replace(/\s+/g,' ');
  const previous=createStoryImageReceipt(pkg,6,[prompt],5);await previous.restore();await previous.begin();
  await previous.dispatching(normalized,{conversation_url:location.href,before_turn:-1});
  storage=JSON.parse(JSON.stringify(storage));history.replaceState({},'','/c/recovered-scene');user(1,prompt);answer(2);
  requireDownloadOwner=true;let error='',asset='';
  try{asset=await createStoryImageReceipt(pkg,6,[prompt],5).restore();}catch(e){error=e.message;}finally{requireDownloadOwner=false;}
  return {error,asset,sends,stops,receipt:storage[key]};
 },prompt);
 assert.equal(restored.error,'',JSON.stringify(restored));assert(restored.asset.endsWith('file_2'));
 assert.equal(restored.sends,0);assert.equal(restored.stops,0);assert.equal(restored.receipt.status,'generated');
 assert.equal(restored.receipt.result_proof.conversation_url,'https://chatgpt.com/c/recovered-scene');
 assert.equal(restored.receipt.result_proof.request_message_id,'message-1');
 // Regression374: restore only the positively attested old no-click failure.
 for(const variant of ['valid','unknown','pressed','edited','accepted','busy','wrong_client','wrong_run','wrong_time','wrong_url']){
  const result=await page.evaluate(async variant=>{
   mode='';ticks=1000;cancelled=false;busy=false;onSleep=null;events=[];sends=0;stops=0;storage={};
   document.querySelector('#thread').replaceChildren();history.replaceState({},'','/c/fixture');composer().textContent='scene six';
   delete pkg.ai_resume;
   const receipt=createStoryImageReceipt(pkg,6,['scene six'],5);await receipt.restore();await receipt.begin();
   await receipt.dispatching('scene six',{conversation_url:location.href,before_turn:12});
   const proof={reason:'v373_draft_preflight_no_click',job_id:pkg.job.id,provider:'chatgpt',scene_index:6,
    run_id:activeRunId,client_id:'fixture',prompt:'scene six',conversation_url:location.href,
    trace_sequence:5,created_after_ms:900,created_before_ms:1100};
   pkg.ai_resume={stage:'image',pre_send_proof:proof};
   if(variant==='unknown')delete pkg.ai_resume.pre_send_proof;
   if(variant==='pressed')storage[key+':dispatch']=storage[key].send_nonce;
   if(variant==='edited')composer().textContent='user changed draft';
   if(variant==='accepted'){user(13,'scene six');answer(14);composer().textContent='';}
   if(variant==='busy')busy=true;
   if(variant==='wrong_client')proof.client_id='other';
   if(variant==='wrong_run')proof.run_id='RUN-OTHER';
   if(variant==='wrong_time')proof.created_after_ms=2000;
   if(variant==='wrong_url')history.replaceState({},'','/');
   let value,error='';try{value=await createStoryImageReceipt(pkg,6,['scene six'],5).restore();}catch(e){error=e.message;}
   return {resumable:value===null,phase:storage[key].send_phase,status:storage[key].status,error,sends,stops};
  },variant);
  assert.equal(result.resumable,variant==='valid',variant+JSON.stringify(result));
  assert.equal(result.phase==='prepared',variant==='valid',variant);
  if(variant==='accepted')assert.equal(result.status,'generated');
  assert.equal(result.sends,0);assert.equal(result.stops,0);
 }
 console.log('Story329/330/374: Send-to-image, durable phases/resume, new-chat URL binding and 10 attested preflight recovery scenarios passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
