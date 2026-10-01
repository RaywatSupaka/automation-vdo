// Offline Chromium: real writer -> submitted DOM -> real motion wait/Resume.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(process.env.SMARTFLOW_TEST_SOURCE || 'browser_extension/chatgpt.js','utf8');
const rule=fs.readFileSync('browser_extension/single_answer.js','utf8');
const part=(a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i,a);return source.slice(i,j);};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  await page.setContent('<textarea id="editor"></textarea><main></main>');
  await page.addScriptTag({content:rule});
  await page.addScriptTag({content:`
    let IS_GEMINI=false,activeJobId='STORY-414',activeRunId='RUN-414';
    const PROVIDER_KEY='chatgpt',AI_NAME='ChatGPT Web';
    let cancelRequested=false,activeRepairKey='',activeCoverRequest=null;
    let clock=1000,sends=0,uploads=0,marks=0,busy=false,answerText='',fresh=false;
    Date.now=()=>clock;
    const request='Write motion JSON for scene 15. บทพูดเดิม unchanged.';
    const context={job_id:activeJobId,index:15,context_id:'c'.repeat(64),image_url:'http://fixture.invalid/scene15.png'};
    const result={job_id:activeJobId,index:15,context_id:context.context_id,
      prompt:'Vertical 9:16, one video. The traveler walks toward the station. A smooth camera move follows the departure.',
      needs_review:false,reference_compatible:true,material_change:false,review_reason:'Preserve the saved event.'};
    let record={phase:'requested',request},actions=[],cancelAt=Infinity,delayedAnswerAt=0;
    const composer=()=>document.querySelector('#editor');
    const userTurns=()=>[...document.querySelectorAll('[data-message-author-role="user"]')];
    const assistantTurns=()=>[...document.querySelectorAll('[data-message-author-role="assistant"]')];
    const latestAssistantStrictlyAfterLatestUser=()=>{
      const user=userTurns().at(-1),answer=assistantTurns().at(-1);
      return user&&answer&&(user.compareDocumentPosition(answer)&Node.DOCUMENT_POSITION_FOLLOWING)?answer:null;
    };
    const analysisAnswerNode=n=>n,extractJson=n=>JSON.parse(n.innerText||n.textContent);
    const analysisResponseStopButton=()=>busy?{}:null;
    const analysisContentHash=s=>String(s.length),analysisStopLabel=()=>'';
    const assertNotCancelled=()=>{if(cancelRequested||clock>=cancelAt){const e=Error('Cancelled');e.name='AbortError';throw e;}};
    const sleep=async ms=>{clock+=ms;if(delayedAnswerAt&&clock>=delayedAnswerAt){busy=false;showAnswer(JSON.stringify(result));delayedAnswerAt=0;}};
    const report=async()=>{},revealChatGPTAnswer=async()=>{},refreshPendingChatGPTMotion=async()=>{};
    const waitForResponseIdle=async()=>{},setChatGPTImageTool=async()=>{},waitForComposer=async()=>composer();
    const sendButton=()=>({}),lastUserTurnSignature=()=>String(userTurns().length);
    const attachSourceImages=async()=>{uploads++;};
    const explicitAnalysisRefusal=()=>false,explicitImageFailure=()=>false;
    const visible=()=>true,chatGPTComposerAttachmentState=()=>({count:0,busy:false,failed:false});
    function showRequest(text,layout='bubble'){
      document.querySelector('main').innerHTML='<section data-testid="conversation-turn-1"><div data-message-author-role="user" data-message-id="user414"></div></section>';
      const user=userTurns()[0];
      if(layout==='bubble')user.innerHTML='<div class="user-message-bubble-color"><div class="whitespace-pre-wrap"></div><button>ดูเพิ่มเติม</button></div><img alt="attached image">';
      else user.innerHTML='<div class="whitespace-pre-wrap"></div><button>ดูเพิ่มเติม</button><img alt="attached image">';
      user.querySelector('.whitespace-pre-wrap').textContent=text;
    }
    function showAnswer(text){
      document.querySelector('#answer-frame')?.remove();
      const frame=document.createElement('section');frame.id='answer-frame';frame.dataset.testid='conversation-turn-2';
      frame.innerHTML='<div data-message-author-role="assistant"></div><button data-testid="copy-turn-action-button">Copy</button>';
      frame.firstChild.textContent=text;document.querySelector('main').append(frame);
    }
    const sendAndVerify=async()=>{sends++;showRequest(composer().value);composer().value='';showAnswer(answerText);};
    globalThis.chrome={runtime:{sendMessage:async m=>{
      if(m.type!=='FLOW_MOTION_PLAN')throw Error('Unexpected browser action '+m.type);
      if(m.job_id!==context.job_id||m.run_id!==activeRunId||m.index!==15)throw Error('Changed owner');
      actions.push(m.action);
      if(m.action==='status')return {ok:true,context,record};
      if(m.action==='prepare')return {ok:true,context,record,claimed:fresh};
      if(m.action==='mark_sending'){marks++;record.phase='requested';return {ok:true,record};}
      if(m.action==='review'){
        if(JSON.stringify(m.result)!==JSON.stringify(result))throw Error('Changed answer');
        return {ok:true,validation:{errors:[],repairable:false}};
      }
      if(m.action==='save'){record={...record,phase:'ready',prompt:m.result.prompt};return {ok:true,record};}
      throw Error('Unexpected motion transition '+m.action);
    }}};
    ${part('function chatGPTConversationFrames(', 'function assistantTurns(')}
    ${part('function composerText(', 'function explicitAnalysisRefusal(')}
    ${part('function confirmedAnalysisTechnicalFailure(', 'function composerText(')}
    ${part('function confirmedStoryImageServiceError(', 'function storyImageNoResultReady(')}
    ${part('async function setComposerText(', 'async function sourceFile(')}
    ${part('function stableOwnedMotionAnswer(', 'async function readPendingAnalysis(')}
    ${part('async function submitPrompt(', 'function analysisAnswerNode(')}
    ${part('async function prepareFlowMotionPlan(', 'function sceneRepairRequest(')}
    window.run=async()=>{
      const checks=[],ok=(v,name)=>{if(!v)throw Error(name);checks.push(name);};
      const norm=v=>v.trim().replace(/\\s+/g,' ');
      for(const layout of ['bubble','legacy'])for(const wire of [false,true]){
        await setComposerText(composer(),request);
        showRequest(wire?composer().value:request,layout);composer().value='';
        ok(motionRequestMatches(request),'writer to motion '+layout+' wire='+wire);
        ok(chatGPTMotionRequestText(userTurns()[0])===norm(request),'canonical submitted body '+layout+' wire='+wire);
      }
      for(const text of [SmartFlowSingleAnswer.wrap(request)+' extra',request+' extra',
          SmartFlowSingleAnswer.instruction+' '+request,SmartFlowSingleAnswer.wrap(request).replace('exactly one','two'),
          SmartFlowSingleAnswer.wrap('A different scene'),SmartFlowSingleAnswer.wrap(request)+' '+SmartFlowSingleAnswer.instruction]){
        showRequest(text);ok(!motionRequestMatches(request),'reject changed/foreign/duplicate suffix '+checks.length);
      }
      showRequest(SmartFlowSingleAnswer.wrap(request));
      const original=userTurns()[0].outerHTML;
      chatGPTMotionRequestText(userTurns()[0]);ok(original===userTurns()[0].outerHTML,'reader never edits live DOM');
      ok(chatGPTMotionRequestText({textContent:SmartFlowSingleAnswer.wrap(request)})===request,'no-clone reader');
      const savedRule=globalThis.SmartFlowSingleAnswer;delete globalThis.SmartFlowSingleAnswer;
      showRequest(request);ok(motionRequestMatches(request),'legacy without transport helper');globalThis.SmartFlowSingleAnswer=savedRule;
      for(const mode of ['fresh','resume','wait','late_partial','cancel','foreign','already_ready']){
        clock=1000;sends=uploads=marks=0;actions=[];cancelAt=Infinity;delayedAnswerAt=0;cancelRequested=false;busy=false;
        fresh=mode==='fresh';record={phase:mode==='already_ready'?'ready':'requested',request,prompt:result.prompt};
        answerText=JSON.stringify(result);document.querySelector('main').innerHTML='';composer().value='';
        if(!fresh){showRequest(SmartFlowSingleAnswer.wrap(mode==='foreign'?'Foreign question':request));showAnswer(answerText);}
        if(mode==='late_partial'||mode==='cancel'){showAnswer('{"job_id":');busy=true;delayedAnswerAt=450000;if(mode==='cancel')cancelAt=40000;}
        let value,error;try{value=mode==='wait'?await waitForMotionAnswer(request,context,15):await prepareFlowMotionPlan({job:{id:activeJobId}},{},15,15);}catch(e){error=e;}
        if(mode==='cancel')ok(error?.name==='AbortError'&&sends===0,'cancel leaves accepted request');
        else if(mode==='foreign')ok(String(error?.message).includes('FLOW_PLAN_REVIEW')&&sends===0,'foreign owner never resubmits');
        else{
          if(error)throw error;
          ok(mode==='wait'?JSON.parse(value.textContent).context_id===context.context_id:value===result.prompt,'real motion completion '+mode);
          ok(sends===(fresh?1:0)&&uploads===(fresh?1:0)&&marks===(fresh?1:0),'exact send/reference/receipt count '+mode);
          if(mode==='late_partial')ok(clock>=450000,'partial/busy not truncated');
          if(mode==='already_ready')ok(actions.join(',')==='status','saved plan not regenerated');
        }
      }
      return checks;
    };`});
  const passed=await page.evaluate(()=>window.run());
  console.log(JSON.stringify({passed:passed.length,cases:passed}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
