// Offline DOM fixture: never connects to a provider or the user's bridge.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const harness=fs.readFileSync('tests/flow_snapshot_harness.js','utf8');
const extract=vm.runInNewContext(harness.slice(0,harness.indexOf('class FakeElement'))+';extractFunction',{require});
const source=fs.readFileSync(process.argv[2] || 'browser_extension/flow.js','utf8');
const names=['currentStoryFailureCard','observeStoryPolicyCard','ownedStoryPolicyTerminal',
 'evaluateFlowPolicyFailure','flowRepairRouting','mobileResultReady','generationSnapshot',
 'canRepairRecoveredTerminal','recoverFlowPolicy','readGenerationState'];
const code=names.map(name=>(source.includes('async function '+name+'(')?'async ':'')+extract(source,name)).join('\n');
const reason='พรอมต์นี้อาจละเมิดนโยบายเกี่ยวกับการสร้างบุคคลที่มีชื่อเสียง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น';
// Semantic structure supplied by the user, including icon text != aria label.
const tile=`<div class="error-tile-content"><div class="error-message">
 <mat-icon>warning</mat-icon><div class="error-title">ล้มเหลว</div><div class="error-subtitle">
 <span class="error-message-text">${reason}</span><span class="disclaimer-message">ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้</span>
 </div></div><div class="buttons-container"><button aria-label="ลองอีกครั้ง"><mat-icon>refresh</mat-icon><span class="mat-focus-indicator"></span></button>
 <button aria-label="ใช้พรอมต์ซ้ำ"><mat-icon>undo</mat-icon></button><button aria-label="ลบ"><mat-icon>delete_forever</mat-icon></button></div></div>`;
(async()=>{
 const browser=await chromium.launch({headless:true});
 let cases=0;
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<html><body></body></html>'}));
  await page.goto('https://flow.google.com/project/fixture');
  for(const kind of ['chatgpt','gemini','old-card','no-title','no-retry','no-nocharge','no-reason',
    'progress','stop','local-progress','result','approval','wrong-project','wrong-run','read-only',
    'changed-narrative','changed-card','disappeared','cancelled','disabled']){
   const outcome=await page.evaluate(async({code,tile,kind})=>{
    document.body.innerHTML='';
    return await new Function('tile','kind',`return (async()=>{
     let now=100000; const Date={now:()=>now};
     let pkg={mode:'story',job_id:'STORY-FIXTURE',run_id:'RUN',shot_index:1,shot_count:4,
       image_ai_provider:kind==='gemini'?'gemini':'chatgpt',video_prompt:'original prompt',
       flow_repair:{enabled:kind!=='disabled',revise_story:true}};
     let inspectionCommandId='',automationPaused=false,readOnlyInspection=kind==='read-only',flowRepairBusy=false;
     let generationProgressSignature='',generationHighestProgress=0,generationProgressChangedAt=now,
       generationProgressDisappearedAt=0,generationStartedAt=now,generationFailureChecks=0,
       generationUnknownChecks=0,observedActiveGeneration=false;
     const visible=element=>!!element?.getClientRects().length;
     const loginRequired=()=>false,dismissFlowChangelogAnnouncement=async()=>false,
       confirmationKind=()=>kind==='approval'?'credit':'',creditExhausted=()=>false,
       stopGenerationMonitor=()=>{},saveFlowProjectCheckpoint=async()=>{},
       promptHasAttachedMedia=()=>false,findPromptEditor=()=>null;
     const reports=[],actions=[];let phase='missing';
     const report=async(step,message,detail)=>reports.push({step,message,detail});
     const store={};
     const chrome={storage:{local:{get:async()=>structuredClone(store),
       set:async patch=>Object.assign(store,structuredClone(patch)),remove:async key=>delete store[key]}},
       runtime:{sendMessage:async message=>{
        if(message.type==='IS_ACTIVE_FLOW_TAB')return {active:true};
        if(message.type!=='FLOW_SCENE_REPAIR')throw Error('Unexpected action '+message.type);
        actions.push(message);
        if(message.action==='status')return {ok:true,phase,alternative:phase!=='missing'};
        if(message.action==='start_alternative'){phase='requested';return {ok:true};}
        throw Error('Unexpected repair action '+message.action);
       }}};
     ${code}
     if(kind==='old-card')document.body.innerHTML=tile;
     const generationBaseline=generationSnapshot();
     store.smartpostFlowMonitor={jobId:pkg.job_id,runId:kind==='wrong-run'?'OLD':'RUN',shotIndex:1,
       projectPath:kind==='wrong-project'?'/project/other':location.pathname,startedAt:now,baseline:generationBaseline};
     document.body.innerHTML=tile+'<div id="narrative">It is currently in the queue.</div>';
     if(kind==='no-title')document.querySelector('.error-title').remove();
     if(kind==='no-retry')document.querySelector('button[aria-label="ลองอีกครั้ง"]').remove();
     if(kind==='no-nocharge')document.querySelector('.disclaimer-message').remove();
     if(kind==='no-reason')document.querySelector('.error-message-text').remove();
     if(kind==='progress')document.body.insertAdjacentHTML('beforeend','<p>42%</p>');
     if(kind==='stop')document.body.insertAdjacentHTML('beforeend','<button>Stop</button>');
     if(kind==='local-progress')document.body.insertAdjacentHTML('beforeend','<flow-video-tile><div role="progressbar">Loading</div></flow-video-tile>');
     if(kind==='result')document.body.insertAdjacentHTML('beforeend','<video style="width:200px;height:200px"></video>');
     const first=generationSnapshot().visibleFailureCards[0];
     await readGenerationState();
     const afterFirst=actions.filter(a=>a.action==='start_alternative').length;
     now+=2500;
     if(kind==='changed-narrative')document.getElementById('narrative').textContent='It is currently in the queue. New response';
     if(kind==='changed-card')document.querySelector('.error-message-text').textContent+=' new detail';
     if(kind==='disappeared')document.querySelector('.error-tile-content').remove();
     if(kind==='cancelled')automationPaused=true;
     await readGenerationState();
     if(kind==='chatgpt'||kind==='gemini'){now+=2500;await readGenerationState();}
     return {afterFirst,actions,reports,terminal:store.smartpostFlowMonitor?.storyPolicyTerminal,first};
    })()`)(tile,kind);
   },{code,tile,kind});
   assert.equal(outcome.afterFirst,0,kind+' requires a second read');
   const started=outcome.actions.filter(a=>a.action==='start_alternative');
   const success=['chatgpt','gemini'].includes(kind);
   assert.equal(started.length,success?1:0,kind);
   if(success){
    assert.equal(started[0].provider,kind);
    assert.equal(started[0].original_prompt,'original prompt');
    assert.equal(started[0].reason,reason);
    assert.equal(outcome.terminal.failure_code,'FLOW_POLICY_BLOCKED');
    assert(outcome.first.hasRetry && outcome.first.hasNoCharge && outcome.first.hasFailedTitle);
    assert(!outcome.reports.some(row=>['error','generation_failed'].includes(row.step)));
   }
   cases++;
  }
  console.log(JSON.stringify({ok:true,cases,network:'intercepted offline only'}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
