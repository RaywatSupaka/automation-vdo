// Sanitized Flow Home DOM -> real snapshot -> real content recovery -> worker.
// All network is intercepted; never uses the customer's Chrome or bridge.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const flow=fs.readFileSync('browser_extension/flow.js','utf8');
const harness=fs.readFileSync('tests/flow_snapshot_harness.js','utf8');
const extract=vm.runInNewContext(harness.slice(0,harness.indexOf('class FakeElement'))+';extractFunction',{require});
const {fixture}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_fresh_start_404.js','utf8').split('\n(async()=>')[0]+';return {fixture};')(require,__dirname);
const key='smartflowFlowRepair:STORY-TEST:1';
const candidate={prompt:'Vertical 9:16, a newly imagined quiet workshop and two invented adult characters discussing an old letter. All spoken dialogue must be in Thai only.',
 needs_review:false,reference_compatible:true,material_change:false};
const promo='<section aria-label="แบนเนอร์โปรโมต"><h2>Take Google Flow on the road.</h2><video autoplay muted style="width:384px;height:584px" src="https://fixture.invalid/promo.mp4"></video><button>Learn More</button></section><button>New Project</button>';
let checks=0;
async function ready(){
 const f=await fixture();await f.start();
 Object.assign(f.storage[key],{phase:'ready',alternative_stage:'motion_sent',candidate:structuredClone(candidate),
  replacement:{image_url:'http://fixture/new.png'},helper_tab:0});
 Object.assign(f.pkg,{aspect_ratio:'9:16',video_prompt:candidate.prompt,replacement_id:f.storage[key].request_id,
  image_urls:['http://fixture/new.png'],flow_repair:{enabled:true,fresh_project_on_repair:true,rebuild_scene_on_failure:true}});
 return f;
}
async function paused(){
 const f=await ready(),r=f.storage[key];
 await f.c.storyRepairMessage({...f.command,type:'FLOW_SCENE_REPAIR',index:1,action:'pause',
  pause_reason:'ต้องตรวจผลเดิมก่อนย้ายโปรเจกต์'},{tab:f.tabs.get(r.owner_tab)});
 const checkpoint={...f.checkpoint,phase:'needs_review',project_path:'/',request_id:r.request_id,
  run_id:r.run_id,alternative:true,alternative_stage:'motion_sent',digest:'home-review407',
  prompt:candidate.prompt,error:'',pause_reason:'ต้องตรวจผลเดิมก่อนย้ายโปรเจกต์'};
 Object.assign(f.permit,{token:'new-fixture-only',event_digest:checkpoint.digest,request_id:r.request_id,review_checkpoint:checkpoint});
 f.command.run_id=f.pkg.run_id='RUN-NEW';
 f.c.flowProgressOwnership=async()=>({active:true,ownerTabId:f.storage['smartpostFlowTab:STORY-TEST:1'],activeRunId:f.command.run_id});
 f.checkpoint=checkpoint;return f;
}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const kind of ['home-promo','home-gallery','resumed-home','home-unowned','home-wrong-run','home-busy','home-credit','home-draft',
                     'project-video','project-late-video','project-late-draft','cancel-during-download','home-late-credit']){
   const f=kind==='resumed-home'?await paused():await ready();
   if(kind==='resumed-home')assert.equal(await f.start(),true);
   const r=f.storage[key],messages=[];
   const project=kind.startsWith('project-');
   const path=project?'/project/current':'/';
   r.project_path=path;f.tabs.get(r.owner_tab).url='https://flow.google.com'+path;
   const monitor=f.storage.smartpostFlowMonitor;monitor.storyPolicyTerminal.projectPath=path;
   if(project){monitor.storyPolicyTerminal.failure_code='FLOW_POLICY_BLOCKED';monitor.storyPolicyTerminal.policy_failure_category='general_policy';}
   if(kind==='home-unowned')delete monitor.storyPolicyTerminal.manual_fresh_start;
   if(kind==='home-wrong-run')monitor.runId='OTHER';
   const page=await browser.newPage(),pageErrors=[];
   page.on('pageerror',error=>pageErrors.push(String(error)));
   await page.route('**/*',route=>route.request().isNavigationRequest()
    ? route.fulfill({contentType:'text/html',body:'<main></main>'}):route.abort());
   await page.goto('https://flow.google.com'+path);
   await page.setContent(project&&kind!=='project-video'?'<main></main>':promo);
   if(kind==='home-gallery')await page.locator('body').evaluate(e=>e.insertAdjacentHTML('beforeend','<article data-media-id="old"><img src="https://fixture.invalid/thumb.png"><button aria-label="play video">play_circle</button></article>'));
   if(kind==='home-busy')await page.locator('body').evaluate(e=>e.insertAdjacentHTML('beforeend','<flow-video-tile><div role="progressbar" style="width:100px;height:20px">45%</div></flow-video-tile>'));
   if(kind==='home-draft')await page.locator('body').evaluate(e=>e.insertAdjacentHTML('beforeend','<textarea>User draft</textarea>'));
   await page.exposeFunction('worker',async message=>{
    if(message.type==='IS_ACTIVE_FLOW_TAB')return f.c.flowProgressOwnership(message,r.owner_tab);
    messages.push(message.action);
    if(message.action==='prepare_alternative'){
     if(kind==='project-late-video')await page.locator('body').evaluate((e,html)=>e.innerHTML=html,promo);
     if(kind==='project-late-draft')await page.locator('body').evaluate(e=>e.innerHTML='<textarea>User draft</textarea>');
     if(kind==='cancel-during-download')await page.evaluate(()=>{automationPaused=true;});
     if(kind==='home-late-credit')await page.evaluate(()=>{approval='credit';});
    }
    return f.c.storyRepairMessage(message,{tab:f.tabs.get(r.owner_tab)});
   });
   await page.addScriptTag({content:`
    let pkg=${JSON.stringify(f.pkg)}, flowRepairBusy=false, automationPaused=false, inspectionCommandId='', readOnlyInspection=false;
    let approval=${JSON.stringify(kind==='home-credit'?'credit':'')};
    globalThis.chrome={runtime:{sendMessage:worker}};
    const report=async()=>{}, stopGenerationMonitor=()=>{};
    const findPromptEditor=()=>document.querySelector('textarea'), confirmationKind=()=>approval;
    const visible=e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0;
    ${extract(flow,'ownedStoryPolicyTerminal')}
    ${extract(flow,'flowPromptMatches')}
    ${extract(flow,'generationSnapshot')}
    async ${extract(flow,'recoverFlowPolicy')}
   `});
   assert.equal(await page.evaluate(()=>typeof generationSnapshot),'function',pageErrors.join(' | ') || 'Flow snapshot script did not load');
   const snapshot=await page.evaluate(()=>generationSnapshot());
   if(!project||kind==='project-video')assert.equal(snapshot.videoCount,1,'actual source sees the promotional VIDEO');
   await page.evaluate(m=>recoverFlowPolicy(m.storyPolicyTerminal,m),JSON.parse(JSON.stringify(monitor)));
   const succeeds=['home-promo','home-gallery','resumed-home'].includes(kind);
   assert.equal(messages.includes('fresh_project'),succeeds,kind+': '+messages.join(','));
   assert.equal(messages.includes('start_alternative'),false,'no second image helper');
   if(succeeds){
    assert.equal(f.storage[key].fresh_project.source_path,'/');
    const sender={tab:f.tabs.get(r.owner_tab)},msg={...f.command,type:'FLOW_SCENE_REPAIR',index:1,request_id:r.request_id};
    assert.equal((await f.c.storyRepairMessage({...msg,action:'claim_fresh_project_click'},sender)).claimed,true);
    assert.equal((await f.c.storyRepairMessage({...msg,action:'claim_fresh_project_click'},sender)).claimed,false);
    sender.tab.url='https://flow.google.com/project/brand-new';
    await f.c.storyRepairMessage({...msg,action:'bind_fresh_project'},sender);
    assert.equal(f.storage[key].fresh_project.target_path,'/project/brand-new');
   }
   assert.equal(f.tabs.get(5).url,'https://flow.google.com/project/old');
   assert.deepEqual(f.storage.smartpostFlowSubmissionReceipts,{old:{clicked:true}});
   await page.close();checks++;
  }
  // Resume the exact already-created replacement after 406's false Home pause.
  {
   const f=await paused(),prior=structuredClone(f.storage[key]),count=f.calls.length;
   f.c.waitForTabComplete=async id=>{
    assert.equal(f.storage[key].phase,'manual_restart','manifest must not start before permit recheck');
    const response=await f.c.storyRepairMessage({...f.command,index:1,type:'FLOW_SCENE_REPAIR',
     action:'manual_restart',token:f.permit.token},{tab:f.tabs.get(id)});
    assert.equal(response.phase,'fresh_start_pending');
   };
   assert.equal(await f.start(),true);
   const r=f.storage[key];assert.equal(r.phase,'ready');assert.equal(r.run_id,'RUN-NEW');
   assert.equal(r.request_id,prior.request_id);assert.deepEqual(r.candidate,prior.candidate);
   assert.deepEqual(r.replacement,prior.replacement);assert.equal(r.manual_resume_proof.source_project_path,'/project/old');
   assert.equal(f.calls.slice(count).filter(x=>x[0]==='create').length,1,'controller only, no AI helper');
   assert(!f.calls.slice(count).some(x=>x[0]==='begin'));
   assert.equal(await f.start(),true);assert.equal(f.calls.slice(count).filter(x=>x[0]==='create').length,1);
   assert(f.c.manualFlowReviewProofMatches(r,f.storage.smartpostFlowMonitor.storyPolicyTerminal));
   assert.equal(f.tabs.get(5).url,'https://flow.google.com/project/old');checks++;
  }
  for(const invalid of ['missing-record','missing-proof','wrong-source','wrong-request','wrong-prompt','wrong-image',
                        'unsafe-candidate','submitted','fresh-project','receipt','unknown-stage','changed-permit','cancelled']){
   const f=await paused(),r=f.storage[key],count=f.calls.length;
   if(invalid==='missing-record')delete f.storage[key];
   if(invalid==='missing-proof')delete r.manual_resume_proof;
   if(invalid==='wrong-source')r.manual_resume_proof.source_project_path='/';
   if(invalid==='wrong-request')r.request_id='OTHER';
   if(invalid==='wrong-prompt')f.pkg.video_prompt='OTHER';
   if(invalid==='wrong-image')f.pkg.replacement_id='OTHER';
   if(invalid==='unsafe-candidate')r.candidate.needs_review=true;
   if(invalid==='submitted')r.phase='submitted';
   if(invalid==='fresh-project')r.fresh_project={phase:'opening'};
   if(invalid==='receipt')f.storage.smartpostFlowSubmissionReceipts[`STORY-TEST:1:OLD:replacement:${r.request_id}`]={requestedAt:1};
   if(invalid==='unknown-stage')r.alternative_stage='image_sent';
   if(invalid==='changed-permit')f.c.waitForTabComplete=async()=>{f.pkg.manual_flow_repair={...f.permit,token:'changed'};};
   if(invalid==='cancelled')f.c.waitForTabComplete=async()=>{f.c.flowProgressOwnership=async()=>({active:false});};
   const result=await f.start().catch(()=>false);assert.equal(result,false,invalid);
   assert(!f.calls.slice(count).some(x=>['begin','ensure'].includes(x[0])),invalid);
   assert(f.storage.smartpostFlowSubmissionReceipts.old);checks++;
  }
 }finally{await browser.close();}
 console.log(JSON.stringify({ok:true,checks}));
})().catch(e=>{console.error(e);process.exitCode=1;});
