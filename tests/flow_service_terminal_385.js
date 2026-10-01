// Offline replay of the user's timeout tile through the actual Flow controller.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const harness=fs.readFileSync('tests/flow_snapshot_harness.js','utf8');
const extract=vm.runInNewContext(harness.slice(0,harness.indexOf('class FakeElement'))+';extractFunction',{require});
const source=fs.readFileSync(process.argv[2]||'browser_extension/flow.js','utf8');
const rebuild=process.argv.includes('--rebuild');
const names=['currentStoryFailureCard','observeStoryPolicyCard','ownedStoryPolicyTerminal','evaluateFlowPolicyFailure','flowRepairRouting','mobileResultReady','generationSnapshot','canRepairRecoveredTerminal','recoverFlowPolicy','readGenerationState'];
const code=names.map(name=>(source.includes('async function '+name+'(')?'async ':'')+extract(source,name)).join('\n');
const tile=`<div class="error-tile-content"><div class="error-message"><mat-icon>warning</mat-icon><div class="error-title">ล้มเหลว</div><div class="error-subtitle"><span class="error-message-text">หมดเวลาสร้าง โปรดลองอีกครั้ง</span><span class="disclaimer-message">ระบบไม่ได้เรียกเก็บเงินจากคุณสำหรับการสร้างครั้งนี้</span></div></div><div class="buttons-container"><button aria-label="ลองอีกครั้ง"><mat-icon>refresh</mat-icon></button><button aria-label="ใช้พรอมต์ซ้ำ"><mat-icon>undo</mat-icon></button><button aria-label="ลบ"><mat-icon>delete_forever</mat-icon></button></div></div>`;
(async()=>{
 const browser=await chromium.launch({headless:true});let cases=0;
 try{
  const page=await browser.newPage();await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<body></body>'}));
  await page.goto('https://flow.google.com/project/fixture');
  for(const kind of ['story-chatgpt','story-gemini','product-chatgpt','product-gemini','service-other','english-failed','no-tile-id','duplicate-reason-new-tile','resume-story','resume-product',
    'old-card','no-title','no-retry','no-nocharge','no-reason','progress','stop','local-progress','result','approval','wrong-project','wrong-run','read-only','changed-narrative','changed-card','disappeared','cancelled','disabled','ambiguous-cards','queued-only','text-only',...(rebuild?['policy-story','policy-product','resume-policy-product']:[])]){
   const outcome=await page.evaluate(async({code,tile,kind,rebuild})=>{
    document.body.innerHTML='';
    return await new Function('tile','kind','rebuild',`return (async()=>{
     let now=100000;const Date={now:()=>now};
     const product=kind.includes('product');
     let pkg={mode:product?'product':'story',job_id:product?'JOB-FIXTURE':'STORY-FIXTURE',run_id:'RUN',shot_index:1,shot_count:3,
      image_ai_provider:kind.includes('gemini')?'gemini':'chatgpt',video_prompt:'Original 9:16 prompt',flow_repair:{enabled:kind!=='disabled',revise_story:!product,same_image_only:product,continuous:true,fresh_project_on_repair:true}};
     if(rebuild)Object.assign(pkg.flow_repair,{rebuild_scene_on_failure:true,same_image_only:false});
     let inspectionCommandId='',automationPaused=false,readOnlyInspection=kind==='read-only'||kind.startsWith('resume-'),flowRepairBusy=false;
     let generationProgressSignature='',generationHighestProgress=0,generationProgressChangedAt=now,generationProgressDisappearedAt=0,generationStartedAt=now,generationFailureChecks=0,generationUnknownChecks=0,observedActiveGeneration=false;
     const visible=e=>!!e?.getClientRects().length,loginRequired=()=>false,dismissFlowChangelogAnnouncement=async()=>false,confirmationKind=()=>kind==='approval'?'credit':'',creditExhausted=()=>false,stopGenerationMonitor=()=>{},saveFlowProjectCheckpoint=async()=>{},promptHasAttachedMedia=()=>false,findPromptEditor=()=>null;
     const reports=[],actions=[],store={};let phase='missing';
     const report=async(step,message,detail)=>reports.push({step,message,detail});
     const chrome={storage:{local:{get:async()=>structuredClone(store),set:async p=>Object.assign(store,structuredClone(p)),remove:async k=>delete store[k]}},runtime:{sendMessage:async m=>{
      if(m.type==='IS_ACTIVE_FLOW_TAB')return {active:true};if(m.type!=='FLOW_SCENE_REPAIR')throw Error('Unexpected action '+m.type);
      actions.push(m);if(m.action==='status')return {ok:true,phase};
      if(m.action==='start'){phase='requested';return {ok:true,phase};}
      if(m.action==='start_alternative'){phase='requested';return {ok:true,phase,alternative:true};}
      throw Error('Unexpected repair '+m.action);
     }}};
     ${code}
     if(kind==='old-card')document.body.innerHTML='<div data-media-id="new">'+tile+'</div>';
     if(kind==='duplicate-reason-new-tile')document.body.innerHTML='<div data-media-id="old">'+tile+'</div>';
     const generationBaseline=generationSnapshot();
     store.smartpostFlowMonitor={jobId:pkg.job_id,runId:kind==='wrong-run'?'OLD':'RUN',shotIndex:1,projectPath:kind==='wrong-project'?'/project/other':location.pathname,startedAt:now,baseline:generationBaseline};
     if(kind.startsWith('resume-'))Object.assign(store.smartpostFlowMonitor,{readOnlyRecovery:true,resumedCheckpointRunId:pkg.run_id});
     document.body.innerHTML='<div data-media-id="new">'+tile+'</div><p id="narrative">It is currently in the queue.</p>';
     if(kind==='no-tile-id')document.querySelector('[data-media-id]').removeAttribute('data-media-id');
     if(kind==='service-other')document.querySelector('.error-message-text').textContent='Something went wrong. Please try again.';
     if(kind.includes('policy-'))document.querySelector('.error-message-text').textContent='ภาพนี้อาจละเมิดนโยบาย โปรดใช้ภาพที่ปลอดภัย';
     if(kind==='english-failed'){document.querySelector('.error-title').textContent='Failed';document.querySelector('.error-message-text').textContent='Generation timed out. Please try again.';}
     if(kind==='no-title')document.querySelector('.error-title').remove();
     if(kind==='no-retry')document.querySelector('button[aria-label="ลองอีกครั้ง"]').remove();
     if(kind==='no-nocharge')document.querySelector('.disclaimer-message').remove();
     if(kind==='no-reason')document.querySelector('.error-message-text').remove();
     if(kind==='progress')document.body.insertAdjacentHTML('beforeend','<p>42%</p>');
     if(kind==='stop')document.body.insertAdjacentHTML('beforeend','<button>Stop</button>');
     if(kind==='local-progress')document.body.insertAdjacentHTML('beforeend','<flow-video-tile><div role="progressbar">Loading</div></flow-video-tile>');
     if(kind==='result')document.body.insertAdjacentHTML('beforeend','<video style="width:200px;height:200px"></video>');
     if(kind==='ambiguous-cards')document.body.insertAdjacentHTML('beforeend','<div data-media-id="second">'+tile+'</div>');
     if(kind==='queued-only')document.querySelector('.error-tile-content').remove();
     if(kind==='text-only')document.body.innerHTML='<p>Here are some ideas for a video, but no video is attached.</p>';
     await readGenerationState();const first=actions.filter(m=>m.action==='start'||m.action==='start_alternative').length;
     now+=2500;
     if(kind==='changed-narrative')document.getElementById('narrative').textContent+=' New activity';
     if(kind==='changed-card')document.querySelector('.error-message-text').textContent+=' changed';
     if(kind==='disappeared')document.querySelector('.error-tile-content').remove();
     if(kind==='cancelled')automationPaused=true;
     await readGenerationState();now+=2500;await readGenerationState();
     return {first,actions,reports,terminal:store.smartpostFlowMonitor?.storyPolicyTerminal};
    })()`)(tile,kind,rebuild);
   },{code,tile,kind,rebuild});
   const success=['story-chatgpt','story-gemini','product-chatgpt','product-gemini','service-other','english-failed','no-tile-id','duplicate-reason-new-tile','resume-story','resume-product'].includes(kind);
   assert.equal(outcome.first,0,kind+' needs two reads');
   const starts=outcome.actions.filter(m=>m.action===(rebuild?'start_alternative':'start'));
   // Changed evidence is sampled once again only, so it must remain unconfirmed.
   const expected=success||kind==='changed-narrative'||kind==='changed-card'||kind.includes('policy-');
   assert.equal(starts.length,expected?1:0,kind);
   assert(!outcome.actions.some(m=>m.action===(rebuild?'start':'start_alternative')),kind+' uses only the selected recovery strategy');
   if(expected){assert.equal(outcome.terminal.failure_code,kind.includes('policy-')?'FLOW_POLICY_BLOCKED':'FLOW_GENERATION_FAILED');if(!kind.includes('policy-'))assert.equal(outcome.terminal.confirmed_uncharged_failure,true);assert.equal(starts[0].provider,kind.includes('gemini')?'gemini':'chatgpt');assert.equal(starts[0].original_prompt,'Original 9:16 prompt');if(rebuild)assert.equal(starts[0].rebuild_scene,true);else assert(starts[0].request.includes('JSON'));assert(!outcome.reports.some(r=>r.step==='error'));}
   cases++;
  }
  console.log(JSON.stringify({ok:true,cases,liveSubmissions:0}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
