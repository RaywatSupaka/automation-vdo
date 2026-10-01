// Actual production monitor; fake elapsed time, no browser/provider requests.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const adapterSource=source.slice(source.indexOf('  function chatGPTConversationFrames('),source.indexOf('  function assistantTurns('));
const monitorSource=source.slice(source.indexOf('  function createStoryImageWaitMonitor('),source.indexOf('  async function recoverOwnedStoryImage('));
const recoverSource=source.slice(source.indexOf('  async function recoverOwnedStoryImage('),source.indexOf('  function createStoryImageReceipt('));
const noResultSource=source.slice(source.indexOf('  function storyImageNoResultReady('),source.indexOf('  async function waitStoryImageServiceRetry('));
function fixture(){
  const userFrame=index=>({getAttribute:name=>name==='data-testid'?`conversation-turn-${index}`:null,
    querySelector:selector=>selector==='[data-message-author-role="user"]'?{}:null});
  const frame=userFrame(1),frames=[frame];
  let time=0,observed={signature:'a',busy:false,stalledReason:'',request:{frame},state:{reason:'image_loading',images:[{}]}};
  const messages=[],events=[];
  const receipt={status:'awaiting_result',send_phase:'accepted',send_nonce:'nonce',identity:'identity',result_proof:{prompt:'prompt'}};
  const c=vm.createContext({Date:{now:()=>time},Math,Number,Boolean,String,Error,
    revealChatGPTAnswer:async()=>false, // DOM reveal is covered by result_readiness_392.
    activeJobId:'STORY-TEST',activeRunId:'RUN-TEST',cancelRequested:false,storyImageRefreshGuard:null,
    location:{href:'https://chatgpt.com/c/test'},composer:()=>({}),composerText:()=>'',
    document:{querySelectorAll:selector=>selector==='[data-testid^="conversation-turn-"]'?frames:[]},
    chatGPTComposerAttachmentState:()=>({count:0,busy:false,failed:false}),
    assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancelled');},
    storyImageWaitObservation:()=>observed,
    storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),
    report:async(...args)=>events.push(args),
    chrome:{storage:{local:{get:async()=>({'smartpostStoryGeneratedImage:chatgpt:STORY-TEST:12':receipt})}},
      runtime:{sendMessage:async message=>{messages.push(message);return {ok:false,refresh_scheduled:false};}}}
  });
  vm.runInContext(adapterSource+monitorSource+'; monitor=createStoryImageWaitMonitor("prompt",{},12,11);',c);
  return {c,receipt,messages,events,newUser:()=>frames.push(userFrame(frames.length+1)),
    set:(ms,next)=>{time=ms;if(next)observed={...observed,...next};},tick:()=>c.monitor.observe()};
}
function recoveryFixture({text='',busy=false,controls=true,loading=false,onSleep=null}={}){
  let time=1,sleeps=0,reads=0;
  const state={reason:loading?'image_loading':'no_image',images:loading?[{complete:false}]:[],
    turn:{querySelector:()=>({innerText:text,textContent:text})}};
  const observation=()=>{reads++;return {state,busy,completedControl:controls};};
  const c=vm.createContext({IS_GEMINI:false,Date:{now:()=>time},String,Boolean,Set,JSON,
    revealChatGPTAnswer:async()=>false,
    location:{href:'https://chatgpt.com/c/test'},assertNotCancelled:()=>{},
    createStoryImageWaitMonitor:()=>({observe:async()=>{}}),
    chatGPTStoryRequest:()=>({frame:{}}),chatGPTStoryImageSnapshot:()=>state,
    storyImageWaitObservation:observation,
    sleep:async ms=>{time+=ms;sleeps++;onSleep?.(c,sleeps);if(sleeps>=8)throw Error('fixture ended while waiting');},
  });
  const serviceSource=source.slice(source.indexOf('  function confirmedStoryImageServiceError('),
    source.indexOf('  function storyImageNoResultReady('));
  vm.runInContext(adapterSource+serviceSource+noResultSource+recoverSource,c);
  return {run:()=>c.recoverOwnedStoryImage({prompt:'prompt',conversation_url:'https://chatgpt.com/c/test'},null,
    {scene_index:12,completedCount:11}),get time(){return time;},get reads(){return reads;}};
}
(async()=>{
  const broken=async f=>{for(let n=0;n<3;n++){f.set(100+n*700,{signature:'broken',stalledReason:'image_load_failed'});await f.tick();}};
  let f=fixture();await f.tick();
  for(let n=1;n<=80;n++){f.set(n*15000,{busy:true});await f.tick();}
  assert.equal(f.messages.length,0,'twenty minutes active generation never refreshes/fails');
  assert(f.events.length>=80,'keep desktop informed during long waits');
  assert.equal(f.events.at(-1)[3].response_active,true,'use bridge input field for active response');
  assert.equal(f.events.at(-1)[3].response_signature,'a','use bridge input field for response identity');
  assert(!('ai_response_active' in f.events.at(-1)[3]),'do not send desktop output aliases as input');
  f=fixture();await f.tick();
  for(let n=1;n<=60;n++){f.set(n*15000,{signature:String(n)});await f.tick();}
  assert.equal(f.messages.length,0,'changing loading/progress never refreshes');
  f=fixture();await f.tick();f.set(86400000);await f.tick();assert.equal(f.messages.length,0,'a full day loading is not failure evidence');
  await broken(f);assert.equal(f.messages.length,1,'three observed broken-load states trigger recovery without minute threshold');
  assert.equal(f.messages[0].type,'RELOAD_CHATGPT_STORY_RESULT');
  f.set(900000);await f.tick();assert.equal(f.messages.length,1,'denied/exhausted refresh keeps waiting without repeated dispatch');
  f=fixture();f.c.chrome.runtime.sendMessage=async message=>{
    f.messages.push(message);
    return {ok:false,refresh_scheduled:false,retry_safe:true,refresh_reason:'live_guard_changed'};
  };
  await broken(f);assert.equal(f.messages.length,1,'explicit pre-claim denial is one dispatch');
  f.set(6499);await f.tick();assert.equal(f.messages.length,1,'pre-claim rejection obeys backoff');
  f.set(6500);await f.tick();assert.equal(f.messages.length,2,'definite pre-claim denial can recheck once after backoff');
  f.set(16500);
  await assert.rejects(f.tick(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW'
    && /CHATGPT_IMAGE_REFRESH_REJECTED/.test(error.message));
  assert.equal(f.messages.length,3,'three stable guard denials stop bounded retry without another Send');
  assert(f.events.some(args=>args[3]?.refresh_outcome==='rejected_preclaim'
    && args[3]?.refresh_reason==='live_guard_changed'),'denial reason stays visible in wait status');
  f=fixture();let unknownCalls=0;f.c.chrome.runtime.sendMessage=async()=>{unknownCalls++;throw Error('port disconnected');};
  await broken(f);f.set(90000);await f.tick();assert.equal(unknownCalls,1,'lost ACK is never replayed');
  assert(f.events.some(args=>args[3]?.refresh_outcome==='ack_unknown'),
    'uncertain refresh is reported instead of silently counted as success');
  f=fixture();f.receipt.send_nonce='';await broken(f);assert.equal(f.messages.length,0,'legacy receipt without nonce is wait-only');
  f=fixture();await f.tick();f.set(400000,{state:{reason:'image_ready',images:[{}]}});await f.tick();assert.equal(f.messages.length,0,'ready image wins over refresh');
  f=fixture();f.c.composerText=()=> 'user draft';await broken(f);assert.equal(f.messages.length,0,'never refresh an unsent draft');
  f=fixture();f.c.chatGPTComposerAttachmentState=()=>({count:1});await broken(f);assert.equal(f.messages.length,0,'never drop attachments');
  f=fixture();f.newUser();await broken(f);assert.equal(f.messages.length,0,'newer same-chat request forbids refreshing old scene');
  f=fixture();f.c.chrome.runtime.sendMessage=async message=>{
    assert(f.c.storyImageRefreshGuard(message));
    f.newUser();
    assert(!f.c.storyImageRefreshGuard(message),'newer request during Background await vetoes final VERIFY');
    return {ok:false};
  };await broken(f);
  f=fixture();await f.tick();f.c.chrome.runtime.sendMessage=async message=>{
    assert(f.c.storyImageRefreshGuard(message));
    assert(!f.c.storyImageRefreshGuard({...message,run_id:'OTHER'}));
    f.set(400001,{busy:true});assert(!f.c.storyImageRefreshGuard(message),'late busy vetoes reload');
    f.set(400002,{busy:false,signature:'changed'});assert(!f.c.storyImageRefreshGuard(message),'late image change vetoes reload');
    return {ok:false};
  };await broken(f);
  f=fixture();f.c.chrome.runtime.sendMessage=async()=>({ok:true,refresh_scheduled:true});
  await assert.rejects(broken(f),error=>error.code==='STORY_IMAGE_REFRESH_SCHEDULED');assert.equal(typeof f.c.storyImageRefreshGuard,'function','guard retained during handoff');
  f=fixture();f.set(0,{request:{},state:{reason:'request_missing',images:[]}});await f.tick();f.set(30000);
  await assert.rejects(f.tick(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW');assert.equal(f.messages.length,0,'missing owner never reloads');
  f=fixture();f.c.cancelRequested=true;await assert.rejects(f.tick(),/cancelled/);
  for(const text of ['Something went wrong while generating your image.', 'I cannot create that image.']){
    const resumed=recoveryFixture({text});
    assert.equal(await resumed.run(),null,'completed owned error/refusal returns to existing receipt review');
    assert(resumed.time>=10000,'the whole owned terminal text must remain stable');
    assert(resumed.reads>=3,'re-read current ownership/DOM after every awaited monitor');
  }
  for(const options of [{text:''},{text:'still generating',busy:true},{text:'loading image',loading:true},
    {text:'not proven complete',controls:false}]){
    const resumed=recoveryFixture(options);
    await assert.rejects(resumed.run(),/fixture ended while waiting/,'empty, busy, loading or unconfirmed text remains waiting');
  }
  console.log('PASS: Story342 extended wait, loading activity, idle single-refresh request, fresh guard, ownership and cancellation');
})().catch(error=>{console.error(error);process.exitCode=1;});
