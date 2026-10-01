const fs=require('fs'),path=require('path'),assert=require('assert/strict'),vm=require('vm');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const read=f=>fs.readFileSync(path.join(root,f),'utf8');
const ai=read('browser_extension/chatgpt.js'),flow=read('browser_extension/flow.js'),bg=read('browser_extension/background.js');
const part=(s,a,b)=>{const i=s.indexOf(a),j=s.indexOf(b,i+a.length);assert(i>=0&&j>i,a);return s.slice(i,j);};
let checks=0;const eq=(a,b)=>{assert.deepEqual(a,b);checks++;};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:900,height:700}});
  await page.route('**/*',r=>r.request().url()==='https://chatgpt.com/c/fixture'?r.fulfill({contentType:'text/html',body:'<main></main>'}):r.abort());
  await page.goto('https://chatgpt.com/c/fixture');
  await page.addScriptTag({content:`
    let IS_GEMINI=false,activeJobId='STORY-TEST',activeRunId='RUN',cancelRequested=false;
    const events=[];let afterSleep=null;const sleep=async()=>{if(afterSleep)await afterSleep();};
    const report=async(...args)=>events.push(args);
    const assertNotCancelled=()=>{if(cancelRequested)throw Error('cancelled');};
    ${part(ai,'  function visible(', '  const dismissedDiscoveryCards')}
    ${part(ai,'  function chatGPTConversationFrames(', '  function explicitImageFailure(')}
    ${part(ai,'  function chatGPTKnownRenderedRequestMatches(', '  function chatGPTMotionRequestText(')}
    ${part(ai,'  function storyImageAssetKey(', '  function storyImageWaitObservation(')}
    ${part(ai,'  function generatedImageElements(', '  async function collectConversationImageUrls(')}
    ${part(flow,'  function flowPromptMatches(', '  function findPromptEditor(')}
    ${part(bg,'function freshFlowProgressMatches(', 'async function flowFreshProjectAction(')}
    const draft='One calm continuous shot.\\nAUDIO: พูดภาษาไทยเท่านั้น';
    let pkg={video_prompt:draft},freshId='repair',phase='preparing',attached=true,stages=[];
    const findPromptEditor=()=>document.querySelector('[contenteditable]');
    const promptHasAttachedMedia=()=>attached;
    const freshCall=async action=>{stages.push(action);return {phase};};
    async function resume(){${part(flow,"      if(freshId){\n        const bound=await freshCall('bind_fresh_project');","      await saveFlowProjectCheckpoint")}return false;}
    async function prepress(){const promptTextBeforeGenerate=findPromptEditor().innerText.trim();${part(flow,"          if(freshId){\n            if(!flowPromptMatches",'          const promptLines')}return true;}
  `});
  await page.setContent('<div contenteditable="true"><p>One calm continuous shot.</p><p>AUDIO: พูดภาษาไทยเท่านั้น</p></div>');
  eq(await page.evaluate(()=>findPromptEditor().innerText.trim()!==draft),true);
  eq(await page.evaluate(()=>flowPromptMatches(findPromptEditor().innerText,draft)),true);
  eq(await page.evaluate(()=>resume()),false);
  eq(await page.evaluate(()=>prepress()),true);
  eq(await page.evaluate(()=>stages.includes('submit_ready')),true);
  for(const changed of ['One calm continuous shot.\nAUDIO: อีกคำพูด','One calm continuous shot.','One calm continuous shot.\nAUDIO: พูดภาษาไทยเท่านั้น!','']){
    eq(await page.evaluate(t=>flowPromptMatches(t,draft),changed),false);
  }
  eq(await page.evaluate(()=>flowPromptMatches(draft.replace('\n','\r\n\n\t'),draft)),true);
  await page.evaluate(()=>{phase='submitted';});
  eq(await page.evaluate(()=>resume()),true);
  await page.evaluate(()=>{phase='preparing';attached=false;});
  eq(await page.evaluate(()=>resume()),true);
  const guard={run_id:'RUN',phase:'preparing',owner_tab:5,request_id:'R',fresh_project:{phase:'bound',target_path:'/project/current'}};
  const progress={run_id:'RUN',step:'error',failure_code:'FLOW_SEND_REVIEW',pre_submit:true,repair_request_id:'R',page_url:'https://flow.google.com/project/current'};
  const accepted=(p,r,t=5)=>page.evaluate(({p,r,t})=>freshFlowProgressMatches(p,r,t),{p,r,t});
  eq(await accepted(progress,guard),true);
  eq(await accepted(progress,{...guard,phase:'submitted'}),false);
  eq(await accepted({...progress,repair_request_id:'old'},guard),false);
  eq(await accepted({...progress,page_url:'https://flow.google.com/project/old'},guard),false);
  eq(await accepted(progress,guard,6),false);
  eq(await accepted(progress,{...guard,run_id:'OLD'}),false);
  eq(await accepted(progress,{...guard,phase:'completed'}),false);
  eq(await accepted(progress,null),false);
  // Current source's duplicate guard normalizes BOTH containers, not only marker.
  const countStart=bg.indexOf('            const count = (text, needle) => {',bg.indexOf('const promptGuard = String(message.prompt_guard'));
  const countCode=bg.slice(countStart,bg.indexOf('            const visible =',countStart));
  const normStart=bg.indexOf('            const normalize = value =>',countStart);
  const normCode=bg.slice(normStart,bg.indexOf('            const pageHasAcceptedWork',normStart));
  const dup=new Function('bodyText','editorText','marker',countCode+normCode+'return {bodyMatches,editorMatches,outsideComposerMatches};');
  eq(dup('draft one\n\ndraft two','draft one\n\ndraft two','draft one\ndraft two').outsideComposerMatches,0);
  eq(dup('draft one\n\ndraft two\ndraft one\n\ndraft two','draft one\n\ndraft two','draft one\ndraft two').outsideComposerMatches,1);
  const setup=async()=>{
   await page.setContent(`<style>#thread{overflow:auto;height:300px}#sidebar{overflow:auto;height:150px}img{width:350px;height:400px}.collapsed{display:none}</style>
    <aside id="sidebar"><div style="height:4000px">sidebar</div></aside><main><div id="thread">
    <section data-testid="conversation-turn-1"><div data-message-author-role="user">old request</div><img src="https://chatgpt.com/backend-api/estuary/content?id=source"></section>
    <section data-testid="conversation-turn-2"><img src="https://chatgpt.com/backend-api/estuary/content?id=old"></section>
    <div style="height:1500px"></div><section data-testid="conversation-turn-3"><div data-message-author-role="user">current request</div></section>
    <section id="result" data-testid="conversation-turn-4"></section></div></main>`);
   await page.evaluate(()=>{cancelRequested=false;activeRunId='RUN';IS_GEMINI=false;revealChatGPTAnswer.userUntil=0;afterSleep=null;});
  };
  const image=async(id='new',collapsed=false)=>page.evaluate(({id,collapsed})=>{
   const frame=document.querySelector('#result');frame.innerHTML='<img src="https://chatgpt.com/backend-api/estuary/content?id='+id+'">';
   frame.classList.toggle('collapsed',collapsed);
   for(const i of document.images)Object.defineProperties(i,{complete:{value:true,configurable:true},naturalWidth:{value:1024,configurable:true},naturalHeight:{value:1024,configurable:true}});
  },{id,collapsed});
  await setup();await image('new',true);
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'image_ready');
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('wrong request').reason),'request_missing');
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),false);
  eq(await page.evaluate(()=>document.querySelector('#thread').scrollTop),0);
  await setup();
  await page.evaluate(()=>{
    const main=document.querySelector('main'),thread=document.querySelector('#thread');
    main.parentElement.insertBefore(thread,main);main.replaceChildren(...thread.childNodes);thread.append(main);
  });
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),true);
  eq(await page.evaluate(()=>document.querySelector('#thread').scrollTop>0),true);
  eq(await page.evaluate(()=>document.querySelector('#sidebar').scrollTop),0);
  await image('old',true);
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'no_image');
  await image('source',true);
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'no_image');
  await setup();
  await page.evaluate(()=>{afterSleep=()=>{document.querySelector('#result').innerHTML='<div data-message-author-role="assistant">completed answer</div>';};});
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,false)),true);
  eq(await page.evaluate(()=>latestAssistantStrictlyAfterLatestUser()?.textContent),'completed answer');
  eq(await page.evaluate(()=>document.querySelector('#sidebar').scrollTop),0);
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,false)),false);
  await setup();
  eq(await page.evaluate(async()=>{const s={};for(let i=0;i<5;i++){document.querySelector('#thread').scrollTop=0;s.lastAt=0;await revealChatGPTAnswer('current request',s,0,true);}return s.attempts;}),3);
  await setup();
  await page.evaluate(()=>{revealChatGPTAnswer.userUntil=Date.now()+6000;});
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),false);
  await setup();
  await page.evaluate(()=>{afterSleep=()=>{activeRunId='FOREIGN';};});
  eq(await page.evaluate(async()=>{try{await revealChatGPTAnswer('current request',{},0,true);return '';}catch(e){return e.code;}}),'AI_WEB_RESUME_REVIEW');
  await setup();await page.evaluate(()=>{afterSleep=()=>{cancelRequested=true;};});
  eq(await page.evaluate(async()=>{try{await revealChatGPTAnswer('current request',{},0,true);return '';}catch(e){return e.message;}}),'cancelled');
  await setup();await page.evaluate(()=>{IS_GEMINI=true;});
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),false);
  await setup();
  await page.evaluate(()=>{
    // A virtualized answer is recreated only after the conversation is revealed.
    document.querySelector('#result').remove();
    afterSleep=()=>{document.querySelector('#thread').insertAdjacentHTML('beforeend','<section id="result" data-testid="conversation-turn-4"><img src="https://chatgpt.com/backend-api/estuary/content?id=mounted"></section>');
      const i=document.querySelector('#result img');Object.defineProperties(i,{complete:{value:true},naturalWidth:{value:1024},naturalHeight:{value:1024}});};
  });
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'waiting_response');
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),true);
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'image_ready');
  await setup();await image('new',true);
  eq(await page.evaluate(()=>{const i=document.querySelector('#result img');Object.defineProperty(i,'complete',{value:false,configurable:true});return chatGPTStoryImageSnapshot('current request').reason;}),'no_image');
  await page.evaluate(()=>{afterSleep=()=>{const i=document.querySelector('#result img');Object.defineProperty(i,'complete',{value:true,configurable:true});};});
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,true)),true);
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'image_ready');
  await setup();await image('new');
  await page.evaluate(()=>{const i=document.querySelector('#result img');i.style.width='48px';i.style.height='48px';});
  eq(await page.evaluate(()=>chatGPTStoryImageSnapshot('current request').reason),'no_image');
  await setup();
  await page.evaluate(()=>document.querySelector('#result').innerHTML='<div data-message-author-role="assistant" style="display:none">complete retained answer</div>');
  eq(await page.evaluate(()=>revealChatGPTAnswer('current request',{},0,false)),false);
  eq(await page.evaluate(()=>document.querySelector('#thread').scrollTop),0);
  // Coalesce pending package reads while allowing one fresh reread during load.
  const queueCode=part(flow,'  function queuePackageReload()', '  function runAutoPrepareOnce(');
  let calls=0,resolvers=[];const c=vm.createContext({load:()=>{calls++;return new Promise(r=>resolvers.push(r));}});
  vm.runInContext('let packageLoadQueue=Promise.resolve(),packageReloadPending=null;'+queueCode,c);
  const first=c.queuePackageReload();eq(c.queuePackageReload()===first,true);
  await new Promise(r=>setImmediate(r));const second=c.queuePackageReload();eq(c.queuePackageReload()===second,true);
  resolvers.shift()(true);await first;await new Promise(r=>setImmediate(r));eq(calls,2);resolvers.shift()(true);await second;
  console.log(JSON.stringify({ok:true,checks,scope:'actual-source guards + isolated DOM, no live generation'}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
