// Actual adapter/inspector/UI, offline. No provider generation or user Job writes.
const fs=require('fs'), vm=require('vm'), assert=require('assert/strict');
const {chromium}=require('playwright');
const src=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
let now=100000;
class Clock extends Date {static now(){return now;}}
const scope={URL,Date:Clock};
vm.runInNewContext(src.replaceAll('export ','')+';this.Adapter=MetaVideoAdapter;this.scan=inspectMetaDOM;',scope);
const clone=x=>JSON.parse(JSON.stringify(x)),url='https://www.meta.ai/prompt/saved-scene';
const home={conversation:'',observedURL:'https://www.meta.ai/',documentId:'old-document',documentReady:true,
  login:false,composerFound:true,composerCount:1,composerText:'',userCount:0,imageCount:0,pageVideoCount:0,
  pageMessageCount:0,pageBusy:false,pageDialog:false,busy:false,stop:false,answerText:'',matchedUser:false};
function fixture(){
  let receipt={job_id:'STORY-TEST',index:13,request_id:'old',context_id:'context',stage:'generating',conversation_url:url};
  let dom={...home},cancelled=false,loseFresh=false;
  const local={},session={},calls=[],effects=[],tabs={1:{id:1,url:home.observedURL,status:'complete'}};
  const api=async(route,body)=>{
    if(cancelled) throw Object.assign(Error('cancelled'),{metaBridge:true,metaPaused:true});
    if(!body)return {package:{prompt:'saved prompt',image_name:'scene_13.png',image_path:'saved.png',...clone(receipt)}};
    calls.push(clone(body));
    if(body.stage==='fresh_start'){
      assert.equal(body.request_id,'old');assert.equal(body.fresh_start_evidence.reason,'route_home');
      assert.equal(body.fresh_start_evidence.tab_missing,false);assert.equal(body.fresh_start_evidence.session_owned,true);
      assert.equal(body.route_evidence.document_id,'old-document');
      assert(body.route_evidence.samples>=2 && body.route_evidence.stable_ms>=5000);
      receipt={job_id:'STORY-TEST',index:13,request_id:'new',context_id:'context',stage:'prepared',retry_previous_request_id:'old',
        fresh_start_reason:'route_home',fresh_start_not_before:now/1000};
      if(loseFresh){loseFresh=false;throw Error('lost fresh ACK');}
    }else if(body.stage==='route_restored'){delete receipt.route_recovery;}
    else receipt={...receipt,...body};
    return {receipt:clone(receipt)};
  };
  const chrome={storage:{local:{get:async()=>clone(local),set:async x=>Object.assign(local,clone(x))},
    session:{get:async()=>clone(session),set:async x=>Object.assign(session,clone(x))}},
    tabs:{get:async id=>tabs[id],update:async()=>{throw Error('never reopen the lost saved route');},
      create:async arg=>{assert.equal(arg.url,home.observedURL);effects.push('new-tab');return tabs[2]={id:2,url:arg.url,status:'complete'};},
      remove:async()=>effects.push('close')},downloads:{download:async()=>{effects.push('download');return 17;}}};
  const make=()=>{const a=new scope.Adapter({api,chromeAPI:chrome});a.inspect=async()=>dom;
    a.click=async()=>{throw Error('fixture must never Send');};return a;};
  const a=make(),row={...receipt,tabId:1};
  return {a,row,make,calls,effects,receipt:()=>receipt,
    set:x=>{dom={...dom,...x};},cancel:()=>{cancelled=true;},lostFresh:()=>{loseFresh=true;},
    init:async()=>{await a.save(row);await a.own(row);}};
}
async function checked(c){await c.init();await c.a.step(c.row);now+=6000;}
(async()=>{
  const normal=fixture();await checked(normal);await normal.a.step(normal.row);
  assert.deepEqual(normal.effects,['new-tab']);
  assert.equal((await normal.a.records()).old.closed,true);
  const fresh=(await normal.a.records()).new;
  assert.equal(fresh.prompt,'saved prompt');assert(!fresh.conversation_url);
  assert.equal(fresh.image_path,'saved.png');assert.equal(fresh.stage,'prepared');
  const lost=fixture();await checked(lost);lost.lostFresh();
  await assert.rejects(()=>lost.a.step(lost.row),/lost fresh/);
  const resumed=lost.make();await resumed.step(lost.row);await resumed.step(lost.row);
  assert.equal(lost.effects.filter(x=>x==='new-tab').length,1);
  assert.equal(lost.calls.filter(x=>x.stage==='fresh_start').length,1);
  for(const blocker of [{documentReady:false},{composerCount:2},{composerText:'user draft'},
    {userCount:1},{imageCount:1},{pageVideoCount:1},{pageMessageCount:1},{busy:true},{stop:true},
    {pageBusy:true},{pageDialog:true},{documentId:''},{answerText:'unfinished response'}]){
    const c=fixture();await checked(c);c.set(blocker);await c.a.step(c.row);
    assert(!c.effects.includes('new-tab'));assert.equal(c.receipt().stage,'generating');
    c.set(home);await c.a.step(c.row);
    assert(!c.effects.includes('new-tab'),'must observe stable state again after interruption');
  }
  const login=fixture();await login.init();login.set({login:true});await login.a.step(login.row);
  assert.equal(login.effects.length,0);assert.match(login.receipt().message,/เข้าสู่ระบบ/);
  const other=fixture();await other.init();other.set({conversation:'https://www.meta.ai/prompt/other'});await other.a.step(other.row);
  assert.equal(other.effects.length,0);assert.equal(other.receipt().stage,'needs_attention');
  const late=fixture();await checked(late);late.set({conversation:url,matchedUser:true,videoReady:true,videoCount:1,videoSrc:'https://fixture.invalid/clip.mp4'});
  await late.a.step(late.row);assert.deepEqual(late.effects,['download']);assert(!late.receipt().route_recovery);
  const active=fixture();await checked(active);active.set({conversation:url,matchedUser:true,stop:true});
  await active.a.step(active.row);assert.deepEqual(active.effects,[]);
  const cancel=fixture();await checked(cancel);cancel.cancel();await assert.rejects(()=>cancel.a.step(cancel.row),/cancelled/);
  assert(!cancel.effects.includes('new-tab'));
  const restart=fixture();await checked(restart);const a=restart.make();await a.step(restart.row);
  assert(!restart.effects.includes('new-tab'));now+=6000;await a.step(restart.row);assert(restart.effects.includes('new-tab'));
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage();await page.route('**/*',route=>route.fulfill({body:'<html><body><div role="textbox" contenteditable="true" data-lexical-editor="true" style="width:300px;height:50px"></div></body></html>',contentType:'text/html'}));
    await page.goto(url+'/');
    const scan=()=>page.evaluate(({fn})=>new Function('return ('+fn+')')()('saved prompt','scene.png'),{fn:scope.scan.toString()});
    let state=await scan();assert.equal(state.conversation,url);assert.equal(state.documentReady,true);
    await page.goto('https://www.meta.ai/');state=await scan();
    assert.equal(state.observedURL,home.observedURL);assert.equal(state.composerCount,1);assert.equal(state.pageMessageCount,0);
    const html=fs.readFileSync('web_ui/index.html','utf8'),app=fs.readFileSync('web_ui/app.js','utf8');
    await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,''));
    await page.addScriptTag({content:`const $=s=>document.querySelector(s); const escapeHtml=s=>String(s??'').replaceAll('<','&lt;').replaceAll('"','&quot;');
      const ui={state:{}}, videoSourcePresentation=()=>({label:'Meta AI'});
      ${app.slice(app.indexOf('let storyRecoveryClearing ='),app.indexOf('let dramaQueuePending'))}`});
    const job={id:'STORY-CAC5D8',title:'คลิปยาวค้าง',long_video:true,status:'error',video_status:'missing',pipeline_stage:'meta_ai',image_count:23,scene_count:23,meta_clip_count:12,video_generation_mode:'meta_ai'};
    await page.evaluate(job=>renderStories([job,{...job,id:'SHORT',long_video:false},{...job,id:'DONE',status:'completed',video_status:'ready'}]),job);
    assert.equal(await page.locator('#long-recovery-list article').count(),1);
    assert.match(await page.locator('#long-recovery-list').textContent(),/ภาพ 23\/23 • คลิป Meta 12\/23/);
    assert.equal(await page.locator('#long-recovery-list [data-retry-story]').getAttribute('data-retry-story'),job.id);
    assert.equal(await page.locator('#story-list [data-retry-story="STORY-CAC5D8"]').count(),0);
    await page.evaluate(job=>renderStories([job],{active:true,job_id:'OTHER'}),job);
    assert.equal(await page.locator('#long-recovery-list [data-retry-story]').isDisabled(),true);
    await page.evaluate(()=>renderStories([]));assert.equal(await page.locator('#long-recovery-panel').getAttribute('hidden'),'');
  }finally{await browser.close();}
  console.log('Meta route recovery and Long Video UI: controller/DOM/late result/activity/cancel/restart/lost ACK fixtures passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
