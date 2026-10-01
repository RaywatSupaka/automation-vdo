// Offline real Chromium DOM + production acceptance loop; no provider traffic.
const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const baseline=process.argv.includes('--baseline');
const legacy=baseline?fs.readFileSync('../../../browser_extension/chatgpt.js','utf8'):source;
const section=(a,b)=>{const start=source.indexOf(a),end=source.indexOf(b,start+1);assert(start>=0&&end>start);return source.slice(start,end);};
const production=fs.readFileSync('browser_extension/single_answer.js','utf8')+
 section('  function chatGPTConversationFrames(','  async function revealChatGPTAnswer(')+
 section('  function motionRequestIsLatestUser(','  function geminiStoryImageSnapshot(')+
 section('  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')+
 section('  function storyTurnNumber(','  function chatGPTStoryImageSnapshot(')+
 legacy.slice(legacy.indexOf('  async function sendAndVerify('),legacy.indexOf('  async function ensureAiWebModel('));
(async()=>{
 const browser=await chromium.launch({headless:true});let cases=0;
 try{
  const page=await browser.newPage();await page.route('**/*',route=>route.fulfill({body:'<!doctype html><main></main><textarea></textarea><button>Send</button>',contentType:'text/html'}));
  for(const provider of ['chatgpt','gemini'])for(const mode of baseline?['stop_only','cleared_only']:['accepted','late','stop_only','cleared_only','foreign','old','duplicate','echo_draft','remount','cancel','changed_run','changed_chat',...(provider==='chatgpt'?['late_after_timeout','echo_after_timeout']:[])]){
   const url=provider==='chatgpt'?'https://chatgpt.com/c/owned':'https://gemini.google.com/app/0123456789abcdef';
   await page.goto(url);
   await page.addScriptTag({content:production});
   const result=await page.evaluate(async({provider,mode})=>{
    Object.assign(globalThis,{IS_GEMINI:provider==='gemini',PROVIDER_KEY:provider,AI_NAME:provider,activeJobId:'STORY-FIXTURE',activeRunId:'RUN-FIXTURE'});
    const prompt='Review only the saved product. Return one JSON answer.';
    let ticks=0,sends=0,cancelled=false;const reports=[];
    globalThis.visible=()=>true;
    globalThis.composer=()=>document.querySelector('textarea');
    globalThis.composerText=editor=>SmartFlowSingleAnswer.canonical((editor||composer())?.value||'').trim();
    composer().value=SmartFlowSingleAnswer.wrap(prompt);
    globalThis.stopButtonVisible=()=>mode==='stop_only';
    globalThis.assertNotCancelled=()=>{if(cancelled)throw Object.assign(Error('cancelled'),{name:'AbortError'});};
    globalThis.waitForStableSendDraft=async()=>({editor:composer(),button:document.querySelector('button')});
    globalThis.report=async(step,_message,_n,extra)=>reports.push({step,...extra});
    function user(text,id){
     const frame=document.createElement('article');
     if(IS_GEMINI){frame.className='conversation-container';frame.id=('0000000000000000'+id).slice(-16);frame.innerHTML='<user-query></user-query>';frame.firstChild.textContent='You said '+text;}
     else {frame.dataset.testid='conversation-turn-'+id;frame.innerHTML='<div data-message-author-role="user"><div class="whitespace-pre-wrap"></div></div>';frame.firstChild.dataset.messageId='message-'+id;frame.firstChild.firstChild.textContent=SmartFlowSingleAnswer.wrap(text);}
     document.querySelector('main').append(frame);return frame;
    }
    if(mode==='old')user(prompt,1);else user('Previous unrelated request',1);
    const users=userTurns().length,signature=lastUserTurnSignature(),answers=assistantTurns().length;
    const accept=()=>{user(mode==='foreign'?'A different request':prompt,2);if(mode==='duplicate')user(prompt,3);if(!mode.startsWith('echo_'))composer().value='';};
    globalThis.sleep=async()=>{ticks++;if(mode==='late'&&ticks===44)accept();if(mode==='cancel'&&ticks===2)cancelled=true;};
    globalThis.chrome={runtime:{sendMessage:async()=>{
     sends++;
     if(mode==='cleared_only')composer().value='';
     if(mode==='old')composer().value='';
     if(['accepted','foreign','duplicate','echo_draft','echo_after_timeout','remount','changed_run','changed_chat'].includes(mode))accept();
     if(mode==='remount'){const old=composer(),fresh=old.cloneNode();fresh.value='';old.replaceWith(fresh);}
     if(mode==='changed_run')activeRunId='OTHER-RUN';
     if(mode==='changed_chat')history.replaceState({},'',IS_GEMINI?'/app/fedcba9876543210':'/c/foreign');
     return {ok:true,dispatched:true,dispatchCompleted:true,method:'single_trusted_ai_send',diagnostics:{gesture_phase:'released'}};
    }}};
    let error='',caught=null,recovered=false;try{await sendAndVerify(document.querySelector('button'),composer(),users,signature,answers);}catch(e){error=e.code||e.name;caught=e;}
    if(mode==='late_after_timeout')accept();
    if(mode.endsWith('_after_timeout'))recovered=await reconcileChatGPTSendAcceptance(caught);
    return {sends,ticks,error,recovered,accepted:reports.some(r=>r.step==='ai_send_accepted'),proof:reports.find(r=>r.step==='ai_send_accepted')?.submission_proof};
   },{provider,mode});
   const success=['accepted','late','remount'].includes(mode);
   if(baseline){assert.equal(result.accepted,true,'Reproduce old false acceptance');cases++;continue;}
   if(mode.endsWith('_after_timeout')){assert.equal(result.accepted,false);assert.equal(result.recovered,mode==='late_after_timeout');assert.equal(result.sends,1);cases++;continue;}
   assert.equal(result.accepted,success,provider+'/'+mode+': '+JSON.stringify(result));
   assert.equal(result.sends,1);assert(result.ticks<=240);
   if(success)assert.equal(result.proof,provider==='chatgpt'?'owned_chatgpt_user_turn':'owned_gemini_user_turn');
   else assert.equal(result.error,mode==='cancel'?'AbortError':'AI_SEND_DISPATCHED_UNCONFIRMED');
   cases++;
  }
 }finally{await browser.close();}
 console.log(JSON.stringify({ok:true,native_receipt_cases:cases,baseline_false_acceptance:baseline,provider_generations:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
