// Actual-source offline controller: no browser/provider requests or paid Sends.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'meta_service_recovery_cases.json'), 'utf8'));
let now = 100000;
class Clock extends Date { static now() { return now; } }
const scope = {URL, Date:Clock};
vm.runInNewContext(source.replaceAll('export ', '') + '\nthis.Adapter=MetaVideoAdapter;this.classify=metaReplyFailure;this.inspectDOM=inspectMetaDOM;', scope);
const clone = value => JSON.parse(JSON.stringify(value));
const prompt = 'Create one playable video from the saved image.';
const conversation = 'https://www.meta.ai/prompt/current';
const completed = {matchedUser:true, userCount:1, conversation, stop:false, busy:false, answerBusy:false,
  answerText:cases[0][0], answerComplete:true, answerTruncated:false, videoCount:0, videoReady:false};
let passed = 0;

function controller(overrides = {}, receiptChanges = {}) {
  let receipt = {job_id:'STORY-FIXTURE', index:8, request_id:'old', context_id:'context', stage:'generating',
    conversation_url:conversation, ...receiptChanges};
  const pkg = {prompt, image_name:'scene_08.png', image_path:'C:/fixture/scene_08.png'};
  const local = {}, session = {}, calls = [], physical = [], tabs = {11:{id:11,url:conversation,status:'complete'}};
  let dom = {...completed, ...overrides}, cancelled = false, loseSchedule = false, loseSuccessor = false;
  const api = async (route, body) => {
    if (cancelled) throw Object.assign(new Error('cancelled'), {metaBridge:true,metaPaused:true});
    if (!body) return {package:{...pkg,...clone(receipt)}};
    calls.push(clone(body));
    if (body.stage === 'retry_prepared') {
      assert.equal(body.request_id, receipt.request_id);
      assert.equal(body.context_id, receipt.context_id);
      assert.equal(body.conversation_url, receipt.conversation_url);
      assert.equal(receipt.stage, 'generating');
      const proof = body.retry_evidence;
      assert.equal(proof.matched_request, true);assert.equal(proof.answer_complete, true);
      assert.equal(proof.answer_truncated, false);assert.equal(proof.stop, false);assert.equal(proof.busy, false);
      assert.equal(proof.video_count, 0);assert(proof.samples >= 2 && proof.stable_ms >= 5000);
      assert.equal(scope.classify(proof.answer_text), 'transient_service_error');
      if (!receipt.recovery) {
        receipt = {...receipt,recovery:{protocol:1,category:'transient_service_error',state:'cooldown',
          attempt:Number(receipt.service_retry_count || 0)+1,next_retry_at:now/1000+15}};
        if (loseSchedule) {loseSchedule=false;throw Object.assign(new Error('lost schedule ack'), {metaBridge:true});}
      } else if (now >= receipt.recovery.next_retry_at*1000) {
        const previous = receipt;
        receipt = {job_id:previous.job_id,index:previous.index,request_id:'new',context_id:previous.context_id,
          stage:'prepared',retry_previous_request_id:previous.request_id,retry_count:previous.retry_count || 0,
          service_retry_count:previous.recovery.attempt};
        if (loseSuccessor) {loseSuccessor=false;throw Object.assign(new Error('lost successor ack'), {metaBridge:true});}
      }
    } else {
      assert.notEqual(body.stage, 'redesign_prepare', 'Service outage must not redesign the image');
      receipt = {...receipt,...body};
      if (body.stage !== 'generating') delete receipt.recovery;
    }
    return {receipt:clone(receipt)};
  };
  const chrome = {storage:{
    local:{get:async()=>clone(local),set:async data=>Object.assign(local,clone(data))},
    session:{get:async()=>clone(session),set:async data=>Object.assign(session,clone(data))}},
    tabs:{get:async id=>tabs[id] || null,create:async data=>{
      physical.push('new-tab');const tab={id:12,url:data.url,status:'complete'};tabs[12]=tab;return tab;
    },remove:async id=>physical.push(`close:${id}`)},
    downloads:{download:async()=>{physical.push('download');return 9;}}};
  const adapter = () => {
    const a = new scope.Adapter({api,chromeAPI:chrome});
    a.inspect = async()=>dom;
    a.click = async()=>{physical.push('click');throw Error('No Send is authorized in this fixture');};
    return a;
  };
  const a=adapter(),row={...pkg,...clone(receipt),tabId:11,textIntent:true,uploadIntent:true,sendAt:1};
  return {a,row,adapter,physical,calls,tabs,receipt:()=>clone(receipt),setDOM:x=>{dom=x;},
    cancel:()=>{cancelled=true;},lostSchedule:()=>{loseSchedule=true;},lostSuccessor:()=>{loseSuccessor=true;},
    init:async()=>{await a.save(row);await a.own(row);}};
}
async function observe(c) {await c.init();await c.a.step(c.row);now+=6000;await c.a.step(c.row);}

(async()=>{
  for(const [answer, expected] of cases) {assert.equal(scope.classify(answer),expected);passed++;}
  // Even after generic retry_count=2, a technical outage waits then retries the
  // same media, rather than consuming an image-redesign or manual-review path.
  const c=controller({}, {retry_count:2});await observe(c);
  assert.equal(c.receipt().stage,'generating');assert.equal(c.receipt().recovery.state,'cooldown');
  assert.deepEqual(c.physical,[]);assert.equal(c.calls.length,1);
  now+=14000;await c.a.step(c.row);assert.equal(c.calls.length,1);
  now+=1000;await c.a.step(c.row);await c.a.step(c.row);
  assert.deepEqual(c.physical,['new-tab']);assert.equal(c.receipt().stage,'prepared');
  assert.equal(c.receipt().retry_count,2);assert.equal(c.receipt().service_retry_count,1);
  const next=(await c.a.records()).new;
  assert.equal(next.prompt,prompt);assert.equal(next.image_path,'C:/fixture/scene_08.png');
  for(const field of ['conversation_url','sendAt','uploadIntent','textIntent','recovery']) assert(!next[field]);
  assert.equal((await c.a.records()).old.closed,true);passed++;

  for(const blockers of [{matchedUser:false},{stop:true},{busy:true},{answerBusy:true},{videoCount:1},
    {answerComplete:false},{answerTruncated:true}]) {
    const blocked=controller(blockers);await observe(blocked);
    assert.equal(blocked.calls.length,0);assert.deepEqual(blocked.physical,[]);passed++;
  }
  for(const reply of [cases[4][0],cases[5][0]]) {
    const guarded=controller({answerText:reply});await observe(guarded);
    assert.equal(guarded.receipt().stage,'needs_attention');assert.deepEqual(guarded.physical,[]);passed++;
  }
  // A late video is downloaded even before the cooldown expires.
  const late=controller();await observe(late);
  late.setDOM({...completed,videoReady:true,videoCount:1,videoSrc:'https://media.invalid/video.mp4'});
  await late.a.step(late.row);assert.equal(late.receipt().stage,'downloading');
  assert.deepEqual(late.physical,['download']);assert(!late.receipt().recovery);passed++;

  // Real activity invalidates the prior failure observation, including after due.
  for(const active of [{busy:true},{answerBusy:true},{stop:true},{videoCount:1},{matchedUser:false}]) {
    const blocked=controller();await observe(blocked);now+=20000;
    blocked.setDOM({...completed,...active});await blocked.a.step(blocked.row);
    blocked.setDOM(completed);await blocked.a.step(blocked.row);
    assert.equal(blocked.receipt().stage,'generating');assert.deepEqual(blocked.physical,[]);
    now+=6000;await blocked.a.step(blocked.row);assert.deepEqual(blocked.physical,['new-tab']);passed++;
  }
  // A restarted worker reconstructs cooldown from desktop, but cannot reuse old
  // stable samples as authority. It observes a new pair without resetting delay.
  const restart=controller();await observe(restart);const deadline=restart.receipt().recovery.next_retry_at;
  now+=20000;const resumed=restart.adapter(),old=(await resumed.records()).old;
  await resumed.step(old);assert.deepEqual(restart.physical,[]);
  assert.equal(restart.receipt().recovery.next_retry_at,deadline);
  now+=6000;await resumed.step(old);assert.deepEqual(restart.physical,['new-tab']);passed++;

  // Lost schedule ACK is restored from the durable receipt, not re-scheduled.
  const lostSchedule=controller();await lostSchedule.init();await lostSchedule.a.step(lostSchedule.row);now+=6000;
  lostSchedule.lostSchedule();await assert.rejects(()=>lostSchedule.a.step(lostSchedule.row),/lost schedule ack/);
  const savedDeadline=lostSchedule.receipt().recovery.next_retry_at;
  await lostSchedule.a.step(lostSchedule.row);assert.equal(lostSchedule.calls.length,1);
  assert.equal(lostSchedule.receipt().recovery.next_retry_at,savedDeadline);passed++;

  // Desktop allocated a successor; restart adopts one tab and never retries the
  // old completed error again. Old prompt/image/conversation evidence is kept.
  const lost=controller();await observe(lost);now+=15000;lost.lostSuccessor();
  await assert.rejects(()=>lost.a.step(lost.row),/lost successor ack/);
  const recovery=lost.adapter(),stale=(await recovery.records()).old;
  await recovery.step(stale);await recovery.step(stale);
  assert.deepEqual(lost.physical,['new-tab']);assert.equal(lost.calls.filter(x=>x.stage==='retry_prepared').length,2);passed++;

  const unknown=controller({answerText:'I have finished reviewing your request.'});await observe(unknown);
  assert.equal(unknown.receipt().stage,'generating');assert.match(unknown.receipt().message,/Meta/);
  for(let i=0;i<3;i++){now+=6000;await unknown.a.step(unknown.row);}
  assert.equal(unknown.calls.length,1);assert.deepEqual(unknown.physical,[]);passed++;
  const cancelled=controller();await observe(cancelled);now+=20000;cancelled.cancel();
  await cancelled.a.tick();assert.deepEqual(cancelled.physical,[]);passed++;
  const unsent=controller({matchedUser:false},{stage:'send_intent',conversation_url:''});await observe(unsent);
  assert(!unsent.calls.some(x=>x.stage==='retry_prepared'));assert.deepEqual(unsent.physical,[]);passed++;

  // Inspect actual production DOM reader against a local page: the technical
  // sentence in the user request must not classify the provider as failed.
  const {chromium}=require('playwright');
  const browser=await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  try {
    const page=await browser.newPage();await page.route('**/*',route=>route.abort());
    await page.setContent('<div role="article" aria-label="ข้อความของคุณ"><p id="prompt"></p><img alt="scene_08.png"></div><div role="article" aria-label="การตอบกลับของ Meta AI"><p id="answer"></p><button aria-label="ถูกใจการตอบกลับนี้">Like</button><button aria-label="คัดลอกการตอบกลับ">Copy</button></div>');
    const quotedPrompt=`${prompt}\nPrevious service response: ${cases[0][0]}`;
    await page.evaluate(({prompt})=>{
      document.querySelector('#prompt').textContent=prompt;
      document.querySelector('#answer').textContent='Generating your video now';
      Object.defineProperties(document.querySelector('img'),{complete:{value:true},naturalWidth:{value:720}});
    },{prompt:quotedPrompt});
    const scan=()=>page.evaluate(({fn,prompt})=>new Function('return ('+fn+')')()(prompt,'scene_08.png'),
      {fn:scope.inspectDOM.toString(),prompt:quotedPrompt});
    let state=await scan();assert.equal(state.matchedUser,true);
    assert.equal(scope.classify(state.answerText),'');assert(!state.answerText.includes('server error'));passed++;
    await page.evaluate(answer=>{document.querySelector('#answer').textContent=answer;},cases[0][0]);
    state=await scan();assert.equal(state.answerComplete,true);assert.equal(state.answerTruncated,false);
    assert.equal(scope.classify(state.answerText),'transient_service_error');assert.equal(state.videoCount,0);passed++;
    await page.evaluate(answer=>{document.querySelector('#answer').textContent=answer;},
      'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง');
    state=await scan();assert.equal(state.matchedUser,true);assert.equal(state.answerComplete,true);
    assert.equal(state.videoCount,0);assert.equal(scope.classify(state.answerText),'technical_redesign');passed++;
    await page.evaluate(()=>document.querySelector('#answer').insertAdjacentHTML('afterend','<video></video>'));
    state=await scan();assert.equal(state.videoCount,1);assert.equal(state.videoReady,false);passed++;
  } finally {await browser.close();}
  console.log(`Meta service recovery: ${passed} cases passed; offline actual source/DOM, no provider Sends`);
})().catch(error=>{console.error(error);process.exitCode=1;});
