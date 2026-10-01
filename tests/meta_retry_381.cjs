const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'meta_retry_cases_381.json'), 'utf8'));
let now = 100000;
class Clock extends Date { static now() { return now; } }
const sandbox = {URL, Date:Clock};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../browser_extension/single_answer.js'), 'utf8'), sandbox);
vm.runInNewContext(source.replaceAll('export ', '') + '\nthis.Adapter=MetaVideoAdapter;this.inspect=inspectMetaDOM;this.classify=metaReplyFailure;', sandbox);
const clone = value => JSON.parse(JSON.stringify(value));
const prompt = 'Create a vertical video from this image.';
const conversation = 'https://www.meta.ai/prompt/owned';
const completed = {matchedUser:true, userCount:1, conversation, stop:false, busy:false, answerBusy:false,
  answerText:cases[0][0], answerComplete:true, answerTruncated:false, videoCount:0, videoReady:false};
let count = 0;
function controller(overrides = {}, receiptChanges = {}) {
  let receipt = {job_id:'STORY-FIXTURE', index:8, request_id:'old', context_id:'ctx', stage:'generating',
    conversation_url:conversation, ...receiptChanges};
  const pkg = {prompt, image_name:'scene_08.png', image_path:'C:/fixture/scene_08.png'};
  const storage = {}, session = {}, calls = [], physical = [], removed = [];
  let dom = {...completed, ...overrides}, failAck = false, cancel = false;
  const api = async(route, body) => {
    if (cancel) throw Object.assign(new Error('cancelled'), {metaBridge:true,metaPaused:true});
    if (!body) return {package:{...pkg,...clone(receipt)}};
    calls.push(clone(body));
    if(body.stage === 'retry_prepared' || body.stage === 'fresh_start') {
      receipt = {job_id:receipt.job_id,index:receipt.index,request_id:'new',context_id:'ctx',stage:'prepared',
        retry_count:1,retry_previous_request_id:'old'};
      if(body.stage === 'fresh_start') {
        assert.equal(body.fresh_start_evidence.reason,'tab_not_owned');
        receipt.fresh_start_reason='tab_not_owned';
      }
      if(failAck) { failAck=false; throw Object.assign(new Error('lost ack'),{metaBridge:true}); }
    } else receipt = {...receipt,...body};
    return {receipt:clone(receipt)};
  };
  const tabs = {11:{id:11,url:conversation,status:'complete'}};
  const chrome = {runtime:{id:'extension'}, storage:{
    local:{get:async()=>clone(storage),set:async data=>Object.assign(storage,clone(data))},
    session:{get:async()=>clone(session),set:async data=>Object.assign(session,clone(data))}},
    tabs:{get:async id=>tabs[id] || null, create:async data=>{
      physical.push('new-tab'); const tab={id:12,url:data.url,status:'complete'}; tabs[12]=tab; return tab;
    },remove:async id=>removed.push(id)},
    downloads:{download:async()=>{physical.push('download');return 9;},
      search:async()=>[{id:9,state:'complete',filename:'C:/fixture/result.mp4',exists:true}]}};
  function adapter() {
    const a = new sandbox.Adapter({api,chromeAPI:chrome});
    a.inspect = async()=>({...dom,composerWireText:dom.composerText?sandbox.SmartFlowSingleAnswer.wrap(dom.composerText):''});
    a.click = async(id,point)=>physical.push(point?.tag || 'click');
    a.debug = async(id,fn)=>fn(async(method,params)=>{
      if(method==='Input.dispatchMouseEvent') {
        physical.push(params.type);
        if(params.type==='mouseReleased') {
          assert.deepEqual([params.x,params.y],[3,3],'release the verified successor Send target');
          physical.push('send');
        }
        return {};
      }
      physical.push(method);
      if(method==='Input.insertText') assert.equal(params.text,sandbox.SmartFlowSingleAnswer.wrap(prompt));
      if(method==='DOM.setFileInputFiles') assert.deepEqual(Array.from(params.files),[pkg.image_path]);
      return {root:{nodeId:1},nodeId:2};
    });
    return a;
  }
  const a=adapter(),row={...pkg,...receipt,tabId:11,textIntent:true,uploadIntent:true,sendAt:1};
  return {a,row,adapter,physical,calls,removed,tabs,receipt:()=>receipt,
    setDOM:value=>{dom=value;}, lostAck:()=>{failAck=true;},cancel:()=>{cancel=true;},
    init:async()=>{await a.save(row);await a.own(row);}};
}
async function observe(c) { await c.init(); await c.a.step(c.row); now+=6000; await c.a.step(c.row); }
(async()=>{
  for(const [answer,expected] of cases){assert.equal(sandbox.classify(answer),expected);count++;}
  const browser=await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try {
    const page=await browser.newPage();
    await page.route('**/*',route=>route.abort());
    await page.setContent('<div role="article" aria-label="ข้อความของคุณ"><p id="prompt"></p><img alt="scene_08.png"></div><div role="article" aria-label="การตอบกลับของ Meta AI"><p id="answer"></p><button aria-label="ถูกใจการตอบกลับนี้">Like</button><button aria-label="คัดลอกการตอบกลับ">Copy</button></div>');
    await page.evaluate(({prompt,answer})=>{
      document.querySelector('#prompt').textContent=prompt;
      document.querySelector('#answer').textContent=answer;
      Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}});
    },{prompt,answer:cases[0][0]});
    const scan=()=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene_08.png'),{fn:sandbox.inspect.toString(),prompt});
    let state=await scan();
    assert.equal(state.matchedUser,true); assert.equal(state.answerComplete,true);
    assert.equal(state.answerBusy,false); assert.equal(state.videoCount,0); count++;
    await page.evaluate(()=>{const a=document.querySelector('[aria-label="การตอบกลับของ Meta AI"]');a.insertAdjacentHTML('beforeend','<div role="progressbar">Working</div>');});
    assert.equal((await scan()).answerBusy,true);count++;
    await page.evaluate(()=>{document.querySelector('[role="progressbar"]').remove();document.querySelector('#answer').insertAdjacentHTML('afterend','<video></video>');});
    state=await scan();assert.equal(state.videoCount,1);assert.equal(state.videoReady,false);count++;
    await page.evaluate(()=>{document.querySelector('video').remove();document.querySelector('#answer').textContent="I couldn't create it. "+'x'.repeat(12000);});
    state=await scan();assert.equal(state.answerTruncated,true);assert.equal(state.answerText.length,12000);count++;
    await page.evaluate(()=>{document.querySelector('[aria-label="คัดลอกการตอบกลับ"]').remove();});
    assert.equal((await scan()).answerComplete,false);count++;
  } finally {await browser.close();}

  for(const blocker of [{stop:true},{busy:true},{answerBusy:true},{videoCount:1},{answerComplete:false},
    {answerTruncated:true},{matchedUser:false},{answerText:''},{answerText:'Still generating'}]){
    const c=controller(blocker);await observe(c);
    assert.equal(c.receipt().stage,'generating');assert.deepEqual(c.physical,[]);count++;
  }
  for(const answer of [cases[7][0],cases[9][0]]){
    const c=controller({answerText:answer});await observe(c);
    assert.equal(c.receipt().stage,'needs_attention');assert.deepEqual(c.physical,[]);count++;
  }
  // Stability resets on progress, busy, changed reply, or a pending video.
  for(const change of [{stop:true},{videoCount:1},{answerText:'Still generating'},{matchedUser:false}]){
    const c=controller();await c.init();await c.a.step(c.row);now+=6000;
    c.setDOM({...completed,...change});await c.a.step(c.row);
    c.setDOM(completed);await c.a.step(c.row);assert.equal(c.receipt().stage,'generating');
    assert.deepEqual(c.physical,[]);count++;
  }
  // Full successor path: original prompt and image, one Send, verified download,
  // then close only the successful new tab, never destroy the old evidence.
  const c=controller();await observe(c);
  assert.equal(c.receipt().stage,'prepared');assert.deepEqual(c.physical,['new-tab']);
  const records=await c.a.records();let next=records.new;
  assert.equal(records.old.closed,true);assert.equal(next.prompt,prompt);
  for(const key of ['textIntent','uploadIntent','sendAt','download_id','conversation_url']) assert.equal(next[key] || undefined,undefined);
  let draft={composerFound:true,composer:{tag:'editor',x:2,y:2},composerText:'',userCount:0,
    imageCount:0,busy:false,stop:false,conversation:'',documentReady:true,
    documentId:'successor-document',observedURL:'https://www.meta.ai/',sendTarget:'successor-send-node'};
  c.setDOM(draft);await c.a.step(next); // original prompt
  draft={...draft,composerText:prompt};c.setDOM(draft);await c.a.step(next);
  assert.equal(c.receipt().stage,'uploading');
  draft={...draft,uploadDialog:true,fileInput:true};c.setDOM(draft);await c.a.step(next);
  draft={...draft,uploadDialog:false,imageCount:1,imageReady:false,imageName:'scene_08.png',imageSource:'blob:successor-scene-08'};
  c.setDOM(draft);await c.a.step(next);assert.equal(c.receipt().stage,'uploading');
  draft={...draft,imageReady:true,send:{tag:'send',x:3,y:3}};c.setDOM(draft);await c.a.step(next);
  assert.equal(c.receipt().stage,'ready_to_send');await c.a.step(next);await c.a.step(next);
  assert.equal(c.physical.filter(x=>x==='send').length,1);
  assert.equal(c.physical.filter(x=>x==='mousePressed').length,1);
  assert.equal(c.physical.filter(x=>x==='mouseReleased').length,1);
  const accepted={...completed,composerFound:true,composerText:'',imageCount:0,uploadDialog:false,
    conversation:'https://www.meta.ai/prompt/new',answerText:'',videoCount:0};
  c.setDOM({...accepted,composerText:prompt,imageCount:1});await c.a.step(next);
  assert.equal(c.receipt().stage,'send_intent','matching echo with draft/reference still present must wait');
  c.tabs[12].url=accepted.conversation;c.setDOM(accepted);await c.a.step(next);await c.a.step(next);
  c.setDOM({...accepted,answerText:cases[0][0],videoReady:true,videoCount:1,videoSrc:'https://media.invalid/video.mp4'});
  await c.a.step(next);assert.equal(c.receipt().stage,'downloading');
  const restarted=c.adapter();next=(await restarted.records()).new;
  await restarted.step(next);assert.equal(c.receipt().stage,'stored');
  await restarted.step(next);assert.deepEqual(c.removed,[12]);
  assert.equal(c.physical.filter(x=>x==='download').length,1);count++;

  // Desktop committed retry, worker lost ACK: restore exactly one fresh tab.
  const lost=controller();await lost.init();await lost.a.step(lost.row);now+=6000;lost.lostAck();
  await assert.rejects(()=>lost.a.step(lost.row),/lost ack/);
  const recovery=lost.adapter();const old=(await recovery.records()).old;
  await recovery.step(old);await recovery.step(old);
  assert.deepEqual(lost.physical,['new-tab']);
  assert.equal(lost.calls.filter(x=>x.stage==='retry_prepared').length,1);count++;

  // A browser restart loses ownership: never act on a recycled tab id.
  const unowned=controller();await unowned.init();unowned.a.owns=async()=>false;
  await unowned.a.step(unowned.row);assert.equal(unowned.receipt().stage,'prepared');
  assert.deepEqual(unowned.physical,['new-tab']);
  assert.equal(unowned.receipt().retry_previous_request_id,'old');
  assert.equal(unowned.tabs[12].url,'https://www.meta.ai/');
  assert.equal(unowned.tabs[11].url,conversation);assert.deepEqual(unowned.removed,[]);count++;
  // Unknown send cannot create a successor even if a failure happens to be visible.
  const unknown=controller({matchedUser:false},{stage:'send_intent',conversation_url:''});await observe(unknown);
  assert(!unknown.calls.some(x=>x.stage==='retry_prepared'));assert.deepEqual(unknown.physical,[]);count++;
  const cancelled=controller();await cancelled.init();cancelled.cancel();
  await cancelled.a.tick();assert.deepEqual(cancelled.physical,[]);count++;
  console.log(`Meta retry381: ${count} cases passed; offline actual DOM/controller, no provider requests`);
})().catch(error=>{console.error(error);process.exitCode=1;});
