// Actual-source recovery, offline DOM only. Never connects to a provider.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {chromium}=require('playwright');
const source=fs.readFileSync(process.env.SMARTFLOW_TEST_IMAGE_SOURCE||'browser_extension/chatgpt.js','utf8');
const part=(a,b)=>{const start=source.indexOf(a),end=source.indexOf(b,start+a.length);assert(start>=0&&end>start);return source.slice(start,end);};
let checks=0;const check=(actual,expected,message)=>{assert.deepEqual(actual,expected,message);checks++;};
const url='https://chatgpt.com/c/offline-fixture';
const proof={prompt:'scene eight full prompt',conversation_url:url,request_turn_id:'conversation-turn-16',request_message_id:'request-eight'};
function fixture(fresh=false){
  let time=100000,observation={signature:'missing-a',busy:false,missingRequestOwned:true,stalledReason:'request_dom_missing',request:{frame:null},state:{reason:'request_missing',images:[]}};
  const receipt={status:'awaiting_result',send_phase:'accepted',send_nonce:'nonce',identity:'scene-identity',result_proof:{...proof}};
  const messages=[],events=[];
  const c=vm.createContext({Date:{now:()=>time},Math,Number,Boolean,String,Error,
    revealChatGPTAnswer:async()=>false,activeJobId:'STORY-TEST',activeRunId:'RUN-TEST',cancelRequested:false,storyImageRefreshGuard:null,
    location:{href:url},composer:()=>({}),composerText:()=>'',document:{querySelectorAll:()=>[]},
    chatGPTComposerAttachmentState:()=>({count:0,busy:false,failed:false}),
    assertNotCancelled:()=>{if(c.cancelRequested)throw Error('cancelled');},
    storyImageWaitObservation:(prompt,currentProof)=>currentProof?.prompt===prompt?observation
      :{...observation,missingRequestOwned:false,stalledReason:''},
    storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),report:async(...args)=>events.push(args),
    chrome:{storage:{local:{get:async()=>({'smartpostStoryGeneratedImage:chatgpt:STORY-TEST:8':receipt})}},
      runtime:{sendMessage:async message=>{messages.push(message);return {ok:false};}}}});
  c.proof=proof;
  vm.runInContext(part('  function chatGPTConversationFrames(','  function assistantTurns(')
    +part('  function createStoryImageWaitMonitor(','  async function recoverOwnedStoryImage(')+';monitor=createStoryImageWaitMonitor(proof.prompt,proof,8,7);',c);
  if(fresh){
    c.IS_GEMINI=false;c.text=proof.prompt;c.completedCount=7;
    const {prompt,...owner}=proof;c.storyContext={requestOwner:owner,scene_index:8};
    vm.runInContext(part('    const storyWait=!IS_GEMINI','    const reveal={};')+';monitor=storyWait;',c);
  }
  return {c,receipt,messages,events,set:(offset,patch={})=>{time=100000+offset;observation={...observation,...patch};},tick:()=>c.monitor.observe()};
}
async function stable(f){for(const t of [0,15000,30000]){f.set(t);await f.tick();}}
(async()=>{
  let f=fixture();await stable(f);
  check(f.messages.length,1,'missing accepted request reloads before its old 30s review');
  check(f.messages[0].stalled_reason,'request_dom_missing','reload reason is explicit');
  const initial=fixture(true);await stable(initial);check(initial.messages.length,1,'actual initial-send monitor also refreshes (owner has no prompt field)');
  await assert.rejects(f.tick(),e=>e.code==='STORY_IMAGE_RECEIPT_REVIEW');checks++;
  check(f.messages.length,1,'denied/used budget cannot loop reloads');
  f=fixture();f.c.chrome.runtime.sendMessage=async m=>{f.messages.push(m);return {ok:true,refresh_scheduled:true};};
  await assert.rejects(stable(f),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');checks++;
  check(typeof f.c.storyImageRefreshGuard,'function','guard survives handoff');
  f=fixture();for(const t of [0,60000,1200000]){f.set(t,{busy:true,stalledReason:''});await f.tick();}
  check(f.messages.length,0,'missing DOM during active generation waits, not timeout or reload');
  for(const mutate of [f=>f.c.composerText=()=> 'user draft',f=>f.c.chatGPTComposerAttachmentState=()=>({count:1}),
    f=>f.receipt.send_phase='dispatching',f=>f.receipt.send_nonce='',f=>f.receipt.result_proof.prompt='other',
    f=>f.c.revealChatGPTAnswer.userUntil=999999]){
    f=fixture();mutate(f);await stable(f);check(f.messages.length,0,'draft, attachment, unknown Send, other prompt or user interaction veto');
  }
  f=fixture();f.set(0,{missingRequestOwned:false,stalledReason:''});await f.tick();f.set(30000);
  await assert.rejects(f.tick(),e=>e.code==='STORY_IMAGE_RECEIPT_REVIEW');checks++;
  check(f.messages.length,0,'unproven missing owner still cannot refresh');
  f=fixture();f.set(0);await f.tick();f.set(30000,{signature:'new-dom'});await f.tick();
  check(f.messages.length,0,'changing history gets a fresh stable grace');
  f=fixture();f.c.chrome.runtime.sendMessage=async m=>{
    check(f.c.storyImageRefreshGuard(m),true,'initial guard permits bounded read recovery');
    for(const change of [{busy:true},{missingRequestOwned:false},{signature:'changed'},
      {state:{reason:'image_ready',images:[{}]}},{state:{reason:'request_ambiguous',images:[]}}]){
      f.set(30001,change);check(f.c.storyImageRefreshGuard(m),false,'late result/activity/owner change vetoes');
      f.set(30000,{busy:false,missingRequestOwned:true,signature:'missing-a',state:{reason:'request_missing',images:[]}});
    }
    f.c.cancelRequested=true;check(f.c.storyImageRefreshGuard(m),false,'late cancellation vetoes');return {ok:false};
  };await stable(f);
  f=fixture();f.set(0);await f.tick();f.set(30000,{state:{reason:'image_ready',images:[{}]},request:{frame:{}},stalledReason:''});await f.tick();
  check(f.messages.length,0,'ready scene wins before reload');
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage();
    await page.route('**/*',r=>r.request().url()===url?r.fulfill({contentType:'text/html',body:'<main></main>'}):r.abort());
    await page.goto(url);
    await page.addScriptTag({content:`let busy=false;const visible=node=>node.isConnected;
      const stopButtonVisible=()=>busy,generatedImageElements=frame=>[...frame.querySelectorAll('img')];`+
      part('  function chatGPTConversationFrames(','  function assistantTurns(')+
      part('  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')+
      part('  function storyImageAssetKey(','  function createStoryImageWaitMonitor(')});
    const read=()=>page.evaluate(p=>{const o=storyImageWaitObservation(p.prompt,p);return {owned:o.missingRequestOwned,reason:o.stalledReason,busy:o.busy,signature:o.signature};},proof);
    let state=await read();check(state.owned,true,'saved same-chat request allows recovery of fully unmounted history');
    check(state.reason,'request_dom_missing','idle DOM gap is explicit evidence');
    await page.evaluate(()=>busy=true);check((await read()).busy,true,'global Stop remains busy when request frame is missing');
    check((await read()).reason,'','active generation never claims stalled');await page.evaluate(()=>busy=false);
    await page.evaluate(()=>document.querySelector('main').innerHTML='<article data-testid="conversation-turn-15"><div data-message-author-role="assistant"><div role="progressbar"></div></div></article>');
    check((await read()).busy,true,'visible conversation progress vetoes missing-frame reload');
    const user=(turn,text,id='other')=>`<article data-testid="conversation-turn-${turn}"><div data-message-author-role="user" data-message-id="${id}"><div class="whitespace-pre-wrap">${text}</div></div></article>`;
    await page.evaluate(html=>document.querySelector('main').innerHTML=html,user(14,'prior scene'));
    check((await read()).owned,true,'prior scene alone is not mistaken for current result');
    const previous=(await read()).signature;
    await page.evaluate(html=>document.querySelector('main').innerHTML+=html,user(12,'another old request'));
    check((await read()).signature===previous,false,'history remount changes observation signature');
    for(const html of [user(18,'new user request'),user(16,'wrong prompt'),user(14,proof.prompt),user('unknown','unidentified')]){
      await page.evaluate(html=>document.querySelector('main').innerHTML=html,html);
      check((await read()).owned,false,'new, conflicting or unorderable user requests cannot be refreshed');
    }
    await page.evaluate(()=>document.querySelector('main').innerHTML='');
    // Verify proof variants directly, without using a global page prompt.
    for(const altered of [{...proof,conversation_url:'https://chatgpt.com/c/other'},{...proof,request_turn_id:''},{...proof,prompt:''}]){
      check(await page.evaluate(({prompt,p})=>storyImageWaitObservation(prompt,p).missingRequestOwned,{prompt:proof.prompt,p:altered}),false,'exact saved URL, prompt and turn required');
    }
    await page.evaluate(html=>document.querySelector('main').innerHTML=html,user(16,proof.prompt,'request-eight')+'<article data-testid="conversation-turn-17"><div data-message-author-role="assistant"><img src="https://chatgpt.com/backend-api/estuary/content?id=scene-eight"></div></article>');
    await page.evaluate(()=>{const i=document.querySelector('img');Object.defineProperties(i,{complete:{value:true},naturalWidth:{value:1024},naturalHeight:{value:1024}});});
    check(await page.evaluate(p=>chatGPTStoryImageSnapshot(p.prompt,new Set(),p).reason,proof),'image_ready','after refresh strict original request recovers exact image');
    check(await page.evaluate(p=>chatGPTStoryImageSnapshot(p.prompt,new Set(),{...p,request_message_id:'wrong-id'}).reason,proof),'request_missing','refresh does not relax final image ownership');
  }finally{await browser.close();}
  // Preserve actual Flow's proven 100% -> same-project reload -> read path.
  // This is the exact production block, with browser/network actions stubbed.
  const flow=fs.readFileSync('browser_extension/flow.js','utf8');
  const block=flow.slice(flow.indexOf('    const reachedHundredWithoutPlayableResult'),flow.indexOf('    const completedAfterObservedProgress'));
  const refresh=flow.slice(flow.indexOf('  async function refreshCompletedFlowResult('),flow.indexOf('  async function readGenerationState('));
  for(const patch of [{},{generationHighestProgress:99},{videoCount:1},{hasExplicitVideoDownload:true},
    {completedMobileResult:true},{monitor:{resultRefreshedAt:1}}]){
    const events=[],saved=[],timers=[];let stored={smartpostFlowMonitor:{jobId:'STORY-TEST',shotIndex:7,runId:'RUN-TEST'}};
    const c=vm.createContext({completedMobileResult:false,generationHighestProgress:100,
      snapshot:{resultCardCount:1,videoCount:0},videoCount:0,hasExplicitVideoDownload:false,monitor:stored.smartpostFlowMonitor,
      hasStrongActiveGeneration:false,inspectionId:'',inspectionCommandId:'',readOnlyInspection:false,confirmation:'',automationPaused:false,
      pkg:{job_id:'STORY-TEST',shot_index:7,run_id:'RUN-TEST'},Date:{now:()=>123456},
      generationStartedAt:1,generationBaseline:{resultCardCount:0},generationProgressSignature:'done',
      generationProgressChangedAt:1,generationProgressDisappearedAt:0,
      generationSnapshot:()=>c.snapshot,visible:()=>true,document:{querySelectorAll:()=>[],body:{innerText:''}},confirmationKind:()=>'',
      chrome:{storage:{local:{get:async()=>stored,set:async row=>{stored={...stored,...row};saved.push(row);events.push('persist');}}}},
      saveFlowProjectCheckpoint:async()=>events.push('checkpoint'),report:async()=>events.push('report'),
      setTimeout:fn=>timers.push(fn),location:{pathname:'/project/offline',reload:()=>events.push('reload')},...patch});
    vm.runInContext(refresh+'async function inspect(){'+block+'}',c);await c.inspect();
    for(const fn of timers.splice(0))await fn();
    check(events.includes('reload'),Object.keys(patch).length===0,'Flow only refreshes completed unplayable result once');
    if(saved.length){check(saved[0].smartpostFlowMonitor.resultRefreshedAt,123456,'persist before reload');
      c.monitor=saved[0].smartpostFlowMonitor;await c.inspect();for(const fn of timers.splice(0))await fn();
      check(events.filter(x=>x==='reload').length,1,'resume does not repeat Flow reload');}
  }
  console.log(JSON.stringify({ok:true,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
