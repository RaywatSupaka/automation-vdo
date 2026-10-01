// Uses real dialog elements and production renderer on an offline page only.
const fs=require('fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const app=fs.readFileSync('web_ui/app.js','utf8');
const presenter=fs.readFileSync('web_ui/presenter_progress.js','utf8');
const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>route.request().isNavigationRequest()
    ?route.fulfill({contentType:'text/html',body:html}):route.abort());
  await page.goto('https://smartflow-fixture.invalid/');
  await page.addScriptTag({content:`const ui={progressMinimized:false,state:{}};
    const $=s=>document.querySelector(s);function toast(){}function progressSteps(){return '';}
    ${app.slice(app.indexOf('function minimizeProgress()'),app.indexOf('function renderNotice(state)'))}
    ${presenter}
    window.checkProgress=(type,p)=>{
      const inactive={active:false,job_id:'',percent:0};
      ui.state={product_progress:inactive,story_progress:inactive,presenter_progress:{},system:{},[type+'_progress']:p};
      renderProgress(ui.state);
      return {open:$('#progress-modal').open,pill:!$('#progress-minimized').classList.contains('hidden'),ready:!!ui.progressResultReady};
    };`});
  let cases=0;
  for(const [type,extra] of [['product',{}],['story',{}],['story',{mode:'drama_episode'}],['story',{content_kind:'product'}]]){
   const active={active:true,percent:80,job_id:'JOB-'+cases,...extra};
   assert((await page.evaluate(([t,p])=>checkProgress(t,p),[type,active])).open);
   const imageDone={...active,percent:100,stage:'finishing',detail:'Extension complete; Final still running'};
   assert((await page.evaluate(([t,p])=>checkProgress(t,p),[type,imageDone])).open);
   const done={...imageDone,active:false};
   assert.deepEqual(await page.evaluate(([t,p])=>checkProgress(t,p),[type,done]),{open:false,pill:false,ready:false});
   assert(!(await page.evaluate(([t,p])=>checkProgress(t,p),[type,done])).open);
   cases++;
  }
  const active={job_id:'PRESENTER-1',run_id:'RUN-1',active:true,status:'running',stage:'video',clips:2};
  assert((await page.evaluate(p=>checkProgress('presenter',p),active)).open);
  await page.evaluate(()=>minimizeProgress());
  assert.deepEqual(await page.evaluate(p=>checkProgress('presenter',p),{...active,active:false,status:'ready',clips:3}),{open:false,pill:false,ready:false});
  cases++;
  assert((await page.evaluate(p=>checkProgress('presenter',p),{...active,run_id:'RUN-2',active:false,status:'clip_review'})).open);
  assert((await page.evaluate(p=>checkProgress('presenter',p),{...active,run_id:'RUN-2',active:false,status:'error'})).open);
  cases+=2;
  await page.evaluate(()=>$('#automation-error-modal').showModal());
  await page.evaluate(()=>{checkProgress('story',{active:true,job_id:'NEXT',percent:70});checkProgress('story',{active:false,job_id:'NEXT',percent:100});});
  assert(await page.locator('#automation-error-modal').evaluate(node=>node.open),'success dismissal must not close error reports');
  cases++;
  console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
