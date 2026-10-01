const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'browser_extension/chatgpt.js'), 'utf8');
const part = (a, b) => source.slice(source.indexOf(a), source.indexOf(b, source.indexOf(a) + a.length));
let checks = 0;
const eq = (actual, expected) => { assert.deepEqual(actual, expected); checks++; };
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    await page.route('**/*', route => route.fulfill({contentType:'text/html',body:'<main></main>'}));
    await page.goto('https://chatgpt.com/c/WEB:135591fa-0899-49ad-890c-b3714c65f725');
    await page.addScriptTag({content:`
      let IS_GEMINI=false,activeJobId='STORY-TEST',activeRunId='RUN',cancelRequested=false;
      let activeRepairKey='',activeCoverRequest=null,conversationPendingText='',conversationPendingReferences=[];
      let afterSleep=null,clock=null; const sleep=async(ms)=>{if(clock!==null)clock+=ms;if(afterSleep)await afterSleep();};
      const report=async()=>{},generatedImageElements=()=>[];
      const assertNotCancelled=()=>{if(cancelRequested)throw Error('cancelled');};
      ${part('  function chatGPTConversationFrames(', '  function assistantTurns(')}
      ${part('  async function revealChatGPTAnswer(', '  function explicitImageFailure(')}
      ${part('  function storyTurnNumber(', '  function chatGPTStoryImageSnapshot(')}
      ${part('  function chatGPTKnownRenderedRequestMatches(', '  function chatGPTMotionServiceErrorSnapshot(')}
      ${part('  function motionRequestMatches(', '  function extractMotionJson(')}
      ${part('  function confirmedAnalysisTechnicalFailure(', '  function composerText(')}
      ${part('  function confirmedStoryImageServiceError(', '  function storyImageNoResultReady(')}
      let state={};
      const temporary='/c/WEB:135591fa-0899-49ad-890c-b3714c65f725';
      const canonical='/c/6ab01332-8088-83ec-aec4-10f89a49cb9c';
      const reset=(route=temporary)=>{
        history.replaceState({},'',route);state={};activeJobId='STORY-TEST';activeRunId='RUN';
        cancelRequested=false;IS_GEMINI=false;afterSleep=null;revealChatGPTAnswer.userUntil=0;
        document.body.innerHTML='<main><section data-testid="conversation-turn-1"><div data-message-author-role="user" data-message-id="request-1"><div class="whitespace-pre-wrap">exact current request</div></div></section><section data-testid="conversation-turn-2"><div data-message-author-role="assistant">complete answer</div></section></main>';
      };
      const read=()=>revealChatGPTAnswer('exact current request',state);
      const outcome=async()=>{try{await read();return 'ok';}catch(error){return error.code||error.message;}};
    `});
    // Actual incident: accepted request gets a WEB: placeholder then a saved URL.
    await page.evaluate(async()=>{reset();await read();history.replaceState({},'',canonical);});
    eq(await page.evaluate(()=>outcome()),'ok');
    eq(await page.evaluate(()=>state.identity.endsWith(canonical)),true);
    eq(await page.evaluate(()=>outcome()),'ok');
    // Old snapshots can temporarily lack the mounted request at the placeholder.
    await page.evaluate(async()=>{reset();const main=document.querySelector('main'),html=main.innerHTML;main.innerHTML='';await read();main.innerHTML=html;history.replaceState({},'',canonical);});
    eq(await page.evaluate(()=>outcome()),'ok');
    // A real 428 failure: the provisional route had a mounted request, but
    // ChatGPT briefly unmounts every turn while saving the canonical URL.
    // The accepted Send must wait for the SAME request to remount, not stop or
    // submit another copy while the page skeleton is empty.
    const hydrated = await page.evaluate(async()=>{
      reset();await read();
      const main=document.querySelector('main'),html=main.innerHTML;
      main.innerHTML='';history.replaceState({},'',canonical);
      let polls=0;afterSleep=()=>{if(++polls===3)main.innerHTML=html;};
      const result=await outcome();
      return {result,polls,bound:state.identity.endsWith(canonical)};
    });
    eq(hydrated.result,'ok');eq(hydrated.polls,3);eq(hydrated.bound,true);
    const neverHydrated = await page.evaluate(async()=>{
      reset();await read();document.querySelector('main').innerHTML='';
      history.replaceState({},'',canonical);
      const realNow=Date.now;let elapsed=0;
      Date.now=()=>elapsed;afterSleep=()=>{elapsed+=500;};
      try{return {result:await outcome(),elapsed,reason:state.binding?.url};}
      finally{Date.now=realNow;}
    });
    eq(neverHydrated.result,'AI_WEB_RESUME_REVIEW');
    eq(neverHydrated.elapsed>=30000,true);
    eq(neverHydrated.reason,'https://chatgpt.com/c/WEB:135591fa-0899-49ad-890c-b3714c65f725');
    // ChatGPT renders the 428 analysis instruction's inline Markdown code as
    // <code>json</code>. The submitted text had literal ```json, so a strict
    // textContent comparison must recognize only that known rendering change.
    const renderedPrompt = 'exact current request [SmartFlow analysis JSON v1] Return exactly one JSON object inside one ```json code block, with no prose outside it.';
    await page.evaluate(()=>{
      reset(canonical);
      document.querySelector('.whitespace-pre-wrap').innerHTML='exact current request [SmartFlow analysis JSON v1] Return exactly one JSON object inside one <code>json</code> code block, with no prose outside it.';
    });
    eq(await page.evaluate(prompt=>chatGPTStoryRequest(prompt).reason,renderedPrompt),'request_found');
    eq(await page.evaluate(prompt=>chatGPTKnownRenderedRequestMatches('exact current request [SmartFlow analysis JSON v1] Return exactly one JSON object inside one json code block, with no prose outside it.',prompt),renderedPrompt),true);
    eq(await page.evaluate(()=>chatGPTKnownRenderedRequestMatches(
      'format this JSON transport: Return exactly one complete JSON object inside one json code block.',
      'format this JSON transport: Return exactly one complete JSON object inside one ```json code block.')),true);
    eq(await page.evaluate(()=>chatGPTKnownRenderedRequestMatches('format this json block','format this ```json block')),false);
    eq(await page.evaluate(()=>chatGPTStoryRequest('exact current request ```js').reason),'request_missing');
    // Non-normal navigation never gets a broad URL-change exemption.
    for(const target of ['/c/other','/c/WEB:other','/','/g/other']){
      await page.evaluate(async target=>{reset(canonical);await read();history.replaceState({},'',target);},target);
      eq(await page.evaluate(()=>outcome()),'AI_WEB_RESUME_REVIEW');
    }
    for(const kind of ['wrong_prompt','duplicate','later_user','changed_message','changed_run','changed_job']){
      await page.evaluate(async kind=>{
        reset();await read();history.replaceState({},'',canonical);
        const user=document.querySelector('[data-message-author-role="user"]');
        if(kind==='wrong_prompt')user.textContent='another request';
        if(kind==='duplicate')document.querySelector('main').append(user.closest('section').cloneNode(true));
        if(kind==='later_user')document.querySelector('main').insertAdjacentHTML('beforeend','<section data-testid="conversation-turn-3"><div data-message-author-role="user">later</div></section>');
        if(kind==='changed_message')user.setAttribute('data-message-id','different');
        if(kind==='changed_run')activeRunId='OTHER';
        if(kind==='changed_job')activeJobId='OTHER';
      },kind);
      eq(await page.evaluate(()=>outcome()),'AI_WEB_RESUME_REVIEW');
    }
    // Transition can happen during the reveal's await, not just between polls.
    await page.evaluate(()=>{
      reset();document.querySelector('[data-message-author-role="assistant"]').textContent='';
      document.querySelector('main').outerHTML='<div id="thread" style="overflow:auto;height:100px">'+document.querySelector('main').outerHTML+'<div style="height:2000px"></div></div>';
      afterSleep=()=>history.replaceState({},'',canonical);
    });
    eq(await page.evaluate(()=>outcome()),'ok');
    eq(await page.evaluate(()=>state.identity.endsWith(canonical)),true);
    // Query/hash changes and whitespace do not change a request's identity.
    await page.evaluate(async()=>{reset();await read();document.querySelector('.whitespace-pre-wrap').textContent='exact\n current  request';history.replaceState({},'',canonical+'?model=auto#main');});
    eq(await page.evaluate(()=>outcome()),'ok');
    await page.evaluate(async()=>{reset();await read();IS_GEMINI=true;activeRunId='other';});
    eq(await page.evaluate(()=>outcome()),'ok');
    await page.addScriptTag({content:`
      ${part('  function visible(', '  const dismissedDiscoveryCards')}
      ${part('  function assistantTurns(', '  async function revealChatGPTAnswer(')}
      ${part('  async function submitPrompt(', '  function escapeJsonControlCharacters(')}
      const AI_NAME='ChatGPT Web';let sends=0,attachments=0;
      const waitForResponseIdle=async()=>{},setChatGPTImageTool=async()=>{},waitForComposer=async()=>({});
      const attachSourceImages=async()=>{attachments++;};
      const setComposerText=async e=>e,sendButton=()=>({});
      const explicitAnalysisRefusal=()=>false,explicitImageFailure=()=>false;
      const sendAndVerify=async()=>{
        sends++;reset();clock=1000;
        document.querySelector('[data-message-author-role="assistant"]').textContent='';
        afterSleep=()=>{
          if(clock>=2500){history.replaceState({},'',canonical);
            document.querySelector('[data-message-author-role="assistant"]').textContent=JSON.stringify({job_id:activeJobId,scene_prompts:['one','two','three']});}
        };
      };
      const clockOriginal=Date.now;Date.now=()=>clock===null?clockOriginal():clock;
    `});
    await page.evaluate(()=>{
      reset(canonical);
      document.querySelector('.whitespace-pre-wrap').innerHTML='exact current request [SmartFlow analysis JSON v1] Return exactly one JSON object inside one <code>json</code> code block, with no prose outside it.';
    });
    eq(await page.evaluate(prompt=>motionRequestMatches(prompt),renderedPrompt),true);
    const run = await page.evaluate(async()=>{
      reset('/');clock=1000;
      const result=await submitPrompt('exact current request',['reference']);
      return {sends,attachments,answer:JSON.parse(result.textContent),url:location.pathname,clock};
    });
    eq(run.sends,1);eq(run.attachments,1);eq(run.answer.job_id,'STORY-TEST');
    eq(run.answer.scene_prompts.length,3);eq(run.url,'/c/6ab01332-8088-83ec-aec4-10f89a49cb9c');
    eq(run.clock>=5000,true);
    console.log(JSON.stringify({ok:true,checks,scope:'actual-source route guard in isolated Chromium; no provider sends'}));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
