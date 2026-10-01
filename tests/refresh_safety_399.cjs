// Production functions, offline DOM and in-memory receipts only; no provider access.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {chromium}=require('playwright');
const chat=fs.readFileSync(process.env.SMARTFLOW_TEST_CHAT_SOURCE||'browser_extension/chatgpt.js','utf8');
const flow=fs.readFileSync(process.env.SMARTFLOW_TEST_FLOW_SOURCE||'browser_extension/flow.js','utf8');
const part=(s,a,b)=>{const start=s.indexOf(a),end=s.indexOf(b,start+a.length);assert(start>=0&&end>start);return s.slice(start,end);};
let checks=0;const check=(actual,expected,message)=>{assert.deepEqual(actual,expected,message);checks++;};
function flowFixture(){
  const events=[],timers=[];
  const store={smartpostFlowMonitor:{jobId:'STORY-FIXTURE',runId:'RUN-FIXTURE',shotIndex:8,
    projectPath:'/project/offline-fixture',baseline:{resultCardCount:0},startedAt:1}};
  let gets=0,onGet=null,onSet=null,onReport=null;
  const c=vm.createContext({Date:{now:()=>100000},Boolean,String,Number,
    pkg:{job_id:'STORY-FIXTURE',run_id:'RUN-FIXTURE',shot_index:8},automationPaused:false,
    inspectionCommandId:'',readOnlyInspection:false,
    location:{pathname:'/project/offline-fixture',reload:()=>events.push('reload')},
    snapshot:{resultCardCount:1,videoCount:0,activeProgress:false,activeRenderControl:false},
    labels:[],generationSnapshot:()=>c.snapshot,visible:()=>true,
    document:{body:{innerText:'Queued in old prose'},querySelectorAll:()=>c.labels.map(label=>({getAttribute:()=>label,innerText:''}))},
    confirmationKind:()=>'',generationHighestProgress:100,generationProgressSignature:'100',
    generationProgressChangedAt:100,generationProgressDisappearedAt:0,
    chrome:{storage:{local:{get:async()=>{gets++;onGet?.(gets);return structuredClone(store);},
      set:async values=>{Object.assign(store,structuredClone(values));events.push('persist');onSet?.();}}}},
    saveFlowProjectCheckpoint:async()=>events.push('checkpoint'),
    report:async()=>{events.push('report');onReport?.();},setTimeout:fn=>timers.push(fn),
  });
  vm.runInContext(part(flow,'  async function refreshCompletedFlowResult(','  async function readGenerationState('),c);
  const monitor=structuredClone(store.smartpostFlowMonitor);
  return {c,store,events,timers,run:()=>c.refreshCompletedFlowResult(monitor),
    drain:async()=>{for(const fn of timers.splice(0))await fn();},
    onGet:fn=>onGet=fn,onSet:fn=>onSet=fn,onReport:fn=>onReport=fn};
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage();
    const url='https://chatgpt.com/c/offline-fixture';
    await page.route('**/*',r=>r.request().url()===url?r.fulfill({contentType:'text/html',body:'<main></main>'}):r.abort());
    await page.goto(url);
    await page.addScriptTag({content:`const visible=n=>n.isConnected;const stopButtonVisible=()=>false;
      const generatedImageElements=f=>[...f.querySelectorAll('img')];`+
      'const storyImageRefusal=()=>false,storyImageReferenceRequest=()=>false;'+
      part(chat,'  function confirmedStoryImageServiceError(','  async function waitStoryImageServiceRetry(')+
      part(chat,'  function chatGPTConversationFrames(','  function assistantTurns(')+
      part(chat,'  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')+
      part(chat,'  function storyImageAssetKey(','  function createStoryImageWaitMonitor(')});
    const proof={prompt:'full scene prompt',conversation_url:url,request_turn_id:'conversation-turn-16',request_message_id:'scene16'};
    const user='<article data-testid="conversation-turn-16"><div data-message-author-role="user" data-message-id="scene16">full scene prompt</div></article>';
    const read=()=>page.evaluate(p=>{const o=storyImageWaitObservation(p.prompt,p);return {busy:o.busy,reason:o.stalledReason};},proof);
    for(const marker of ['aria-busy="true"','data-is-streaming="true"','role="progressbar"']){
      for(const present of [false,true]){
        for(const onFrame of [false,true]){
          const html=(present?user:'')+`<article data-testid="conversation-turn-17" ${onFrame?marker:''}><div data-message-author-role="assistant" ${onFrame?'':marker}></div><button data-testid="copy-turn-action">copy</button></article>`;
          await page.evaluate(html=>document.querySelector('main').innerHTML=html,html);
          check(await read(),{busy:true,reason:''},'self/descendant activity vetoes owned and missing-request refresh');
        }
      }
    }
    await page.evaluate(html=>document.querySelector('main').innerHTML=html,
      '<article data-testid="conversation-turn-15" aria-busy="true"></article>'+user+
      '<article data-testid="conversation-turn-17"><div data-message-author-role="assistant"></div><button data-testid="copy-turn-action">copy</button></article>');
    check(await read(),{busy:false,reason:'empty_completed_response'},'stale activity before an owned request does not block real recovery');
    await page.evaluate(()=>document.querySelector('main').innerHTML='');
    check(await read(),{busy:false,reason:'request_dom_missing'},'idle missing history retains398 recovery');
  }finally{await browser.close();}
  let f=flowFixture();check(await f.run(),true,'owned100% remains recoverable despite stale queue prose');
  check(f.events.includes('reload'),false,'no reload before450ms guard');await f.drain();
  check(f.events,['persist','checkpoint','report','reload'],'claim and exact checkpoint precede reload');
  check(f.store.smartpostFlowMonitor.resultRefreshedAt,100000,'durable once-only result claim');
  check(await f.run(),false,'same request cannot refresh twice');
  for(const change of [
    f=>f.c.automationPaused=true,f=>{f.c.inspectionCommandId='READ';f.c.readOnlyInspection=true;},
    f=>f.c.snapshot.activeProgress=true,f=>f.c.snapshot.activeRenderControl=true,
    f=>f.c.snapshot.videoCount=1,f=>f.c.snapshot.resultCardCount=0,
    f=>f.c.labels=['Stop'],f=>f.c.labels=['หยุด'],f=>f.c.labels=['Download video'],
    f=>f.c.confirmationKind=()=> 'credit',f=>f.c.pkg.run_id='OTHER',
    f=>f.c.location.pathname='/project/other',f=>f.store.smartpostFlowMonitor.runId='OTHER',
    f=>f.store.smartpostFlowMonitor.shotIndex=9,
    f=>f.store['smartpostFlowPaused:STORY-FIXTURE:8']=true,
    f=>f.store['smartflowFlowRepair:STORY-FIXTURE:8']={run_id:'RUN-FIXTURE',phase:'cancelled'},
  ]){
    f=flowFixture();change(f);check(await f.run(),false,'unsafe initial owner/activity/inspection veto');
    await f.drain();check(f.events.length,0,'veto cannot overwrite receipt/checkpoint or reload');
  }
  f=flowFixture();f.c.readOnlyInspection=true;check(await f.run(),true,'automatic result-only resume still reads existing result');await f.drain();
  check(f.events.includes('reload'),true,'automatic recovery is not explicit read-only inspection');
  for(const change of [f=>f.c.automationPaused=true,f=>f.c.snapshot.activeProgress=true,
    f=>f.c.labels=['Stop'],f=>f.c.snapshot.videoCount=1,f=>f.c.pkg.run_id='OTHER',
    f=>f.c.location.pathname='/project/other',f=>f.store.smartpostFlowMonitor.runId='OTHER']){
    f=flowFixture();await f.run();change(f);await f.drain();
    check(f.events.includes('reload'),false,'late pause/activity/result/owner change vetoes450ms callback');
    check(f.store.smartpostFlowMonitor.resultRefreshedAt,100000,'late veto never clears claimed refresh budget');
  }
  f=flowFixture();f.onGet(n=>{if(n===1)f.store.smartpostFlowMonitor.runId='OTHER';});
  check(await f.run(),false,'storage owner change during await vetoes before write');
  check(f.store.smartpostFlowMonitor.runId,'OTHER','new monitor is never overwritten by stale snapshot');
  f=flowFixture();f.onGet(n=>{if(n===1)f.store.smartpostFlowMonitor.freshObservation='retained';});
  await f.run();await f.drain();
  check(f.store.smartpostFlowMonitor.freshObservation,'retained','fresh same-owner fields survive the durable claim');
  f=flowFixture();f.onSet(()=>f.c.automationPaused=true);await f.run();await f.drain();
  check(f.events,['persist'],'pause during claim prevents checkpoint/report/navigation');
  f=flowFixture();f.onReport(()=>f.c.automationPaused=true);await f.run();await f.drain();
  check(f.events.includes('reload'),false,'pause while report awaited prevents delayed navigation');
  console.log(JSON.stringify({ok:true,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
