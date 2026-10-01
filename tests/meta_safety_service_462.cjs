// Actual adapter and DOM reader. No provider network, Send, user Chrome or jobs.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/src/platforms/meta-ai/video.js'),'utf8');
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'meta_safety_service_462.json'),'utf8'));
let now=100000,passed=0;
class Clock extends Date {static now(){return now;}}
const scope={URL,Date:Clock};
vm.runInNewContext(source.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;this.classify=metaReplyFailure;this.inspectDOM=inspectMetaDOM;',scope);
const clone=x=>JSON.parse(JSON.stringify(x));
const conversation='https://www.meta.ai/prompt/owned';
const plan={version:1,scene_index:6,plan_revision:1,selection_id:'sel',attempt_id:'attempt',provider:'meta_ai',settings_sha256:'hash'};
const base={matchedUser:true,userCount:1,conversation,stop:false,busy:false,answerBusy:false,pageBusy:false,
  answerText:cases[0][0],answerComplete:true,answerTruncated:false,videoCount:0,videoReady:false};
function fixture(overrides={},repeat=false){
  now=100000;
  let receipt={job_id:'STORY-FIXTURE',index:6,request_id:'original',context_id:'ctx',stage:'generating',
    conversation_url:conversation,service_retry_count:repeat?1:0,scene_video_plan:plan};
  const local={},session={smartflowMetaTabOwnersV1:{11:'original'}},calls=[],physical=[];
  const tabs={11:{id:11,url:conversation,status:'complete'}};
  let dom={...base,...overrides},loseAck=false,helpers=0;
  const chrome={storage:{local:{get:async()=>clone(local),set:async x=>Object.assign(local,clone(x))},
    session:{get:async()=>clone(session),set:async x=>Object.assign(session,clone(x))}},tabs:{get:async id=>tabs[id],
      create:async args=>{physical.push(args.url);return tabs[12]={id:12,url:args.url,status:'complete'};}}};
  const api=async(route,body)=>{
    if(!body)return {package:{...clone(receipt),prompt:'saved prompt',image_name:'scene.png'}};
    calls.push(clone(body));
    if(body.stage==='retry_prepared'){
      assert.deepEqual(clone(body.scene_video_plan),plan);
      assert.equal(body.retry_evidence.composer_empty,true);
      assert.equal(scope.classify(body.retry_evidence.answer_text),'transient_service_error');
      if(!receipt.recovery)receipt={...receipt,recovery:{protocol:1,category:'transient_service_error',state:'cooldown',next_retry_at:now/1000+15}};
      else if(now>=receipt.recovery.next_retry_at*1000){
        receipt=repeat?{...receipt,stage:'redesigning',redesign:{id:'helper'}}:
          {job_id:receipt.job_id,index:6,request_id:'fresh',context_id:'ctx',stage:'prepared',retry_previous_request_id:'original',scene_video_plan:plan};
        if(loseAck){loseAck=false;throw Error('lost due ACK');}
      }
    }else receipt={...receipt,stage:body.stage,message:body.message};
    return {receipt:clone(receipt)};
  };
  const make=()=>{const a=new scope.Adapter({api,chromeAPI:chrome,redesign:async()=>{helpers++;}});
    a.inspect=async()=>dom;a.click=async()=>{throw Error('No physical Send in fixture');};return a;};
  const a=make(),row={...clone(receipt),tabId:11};
  return {a,row,calls,physical,make,receipt:()=>receipt,helpers:()=>helpers,
    dom:x=>{dom={...base,...x};},lost:()=>{loseAck=true;},init:()=>a.save(row)};
}
async function observe(c){await c.init();await c.a.step(c.row);now+=6000;await c.a.step(c.row);}
(async()=>{
  for(const [text,expected]of cases){assert.equal(scope.classify(text),expected);passed++;}
  const first=fixture();await observe(first);
  assert.equal(first.receipt().stage,'generating');assert.equal(first.physical.length,0);
  now+=15000;await first.a.step(first.row);
  assert.deepEqual(first.physical,['https://www.meta.ai/']);assert.equal(first.row.closed,true);passed++;
  const repeated=fixture({},true);await observe(repeated);now+=15000;repeated.lost();
  await assert.rejects(()=>repeated.a.step(repeated.row),/lost due ACK/);
  const reattached=repeated.make();await reattached.step(repeated.row);
  assert.equal(repeated.helpers(),1);assert.deepEqual(repeated.physical,[]);
  assert.equal(repeated.calls.filter(x=>x.stage==='retry_prepared').length,2);passed++;
  for(const override of [{busy:true},{answerBusy:true},{pageBusy:true},{stop:true},{videoCount:1},
    {matchedUser:false},{answerComplete:false},{answerTruncated:true},
    {composerText:'manual draft'},{imageCount:1},{uploadDialog:true}]){
    const c=fixture(override,true);await observe(c);now+=300000;await c.a.step(c.row);
    assert(!c.calls.some(x=>['retry_prepared','redesign_prepare'].includes(x.stage)));
    assert.equal(c.helpers(),0);assert.deepEqual(c.physical,[]);passed++;
  }
  for(const [text,kind]of cases.filter(x=>['policy','quota','authentication_required'].includes(x[1]))){
    const c=fixture({answerText:text},true);await observe(c);
    assert(!c.calls.some(x=>['retry_prepared','redesign_prepare'].includes(x.stage)));
    assert.equal(c.receipt().stage,'needs_attention');passed++;
  }
  const late=fixture({},true);await observe(late);now+=300000;
  late.dom({videoCount:1});await late.a.step(late.row);
  assert.equal(late.calls.filter(x=>x.stage==='retry_prepared').length,1);assert.equal(late.helpers(),0);passed++;
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try{
    const page=await browser.newPage();await page.route('**/*',r=>r.abort());
    await page.setContent('<div role="article" aria-label="ข้อความของคุณ"><p>Create one video.</p><img alt="scene.png"></div><div role="article" aria-label="การตอบกลับของ Meta AI"><div class="markdown-content min-w-0"><div class="stack mx-auto flex max-w-3xl min-w-0 flex-col items-center overflow-visible"><div class="min-w-0 w-full"><div><div dir="auto" class="ur-markdown prose prose-trimmed citation-aware"><div class="space-y-4 whitespace-normal mb-4 flex flex-col gap-6" id="answer"></div></div></div></div></div></div><button aria-label="คัดลอกการตอบกลับ">Copy</button></div>');
    await page.evaluate(text=>{document.querySelector('#answer').closest('[role="article"]').insertAdjacentHTML('beforeend','<button aria-label="ถูกใจการตอบกลับนี้">Like</button>');for(const line of text.split('\n\n')){const p=document.createElement('p');p.textContent=line;document.querySelector('#answer').append(p);}
      Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}});},cases[0][0]);
    const scan=()=>page.evaluate(fn=>new Function('return ('+fn+')')()('Create one video.','scene.png'),scope.inspectDOM.toString());
    let state=await scan();assert.equal(state.matchedUser,true);assert.equal(state.answerComplete,true);
    assert.equal(state.answerTruncated,false);assert.equal(state.videoCount,0);
    assert.equal(scope.classify(state.answerText),'transient_service_error');assert(!state.answerText.includes('Copy'));passed++;
    await page.evaluate(()=>document.querySelector('#answer').insertAdjacentHTML('beforeend','<video></video>'));
    state=await scan();assert.equal(state.videoCount,1);assert.equal(state.videoReady,false);passed++;
  }finally{await browser.close();}
  console.log(`Meta safety-service outage462: ${passed} checks passed; offline, no provider Sends`);
})().catch(error=>{console.error(error);process.exitCode=1;});
