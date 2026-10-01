// Actual-source Meta controller fixture. No provider, browser tab, or user job is touched.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');

const source = fs.readFileSync(path.join(__dirname, '../browser_extension/src/platforms/meta-ai/video.js'), 'utf8');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'meta_service_recovery_cases.json'), 'utf8'));
const answer = cases.find(([text]) => text === 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง')[0];
let now = 100000;
class Clock extends Date { static now() { return now; } }
const scope = {URL, Date: Clock};
vm.runInNewContext(source.replaceAll('export ', '') + '\nthis.Adapter=MetaVideoAdapter;this.classify=metaReplyFailure;', scope);
const conversation = 'https://www.meta.ai/prompt/owned';
const baseDOM = {matchedUser:true, userCount:1, conversation, stop:false, busy:false, answerBusy:false,
  answerText:answer, answerComplete:true, answerTruncated:false, videoCount:0, videoReady:false};

function fixture({dom = {}, stage = 'generating'} = {}) {
  now = 100000;
  let receipt = {job_id:'STORY-FIXTURE', index:14, request_id:'owned', context_id:'context',
    stage, conversation_url:conversation};
  const calls = [], local = {}, session = {smartflowMetaTabOwnersV1:{11:'owned'}};
  let redesignCalls = 0;
  const chrome = {storage:{
    local:{get:async key=>({[key]:local[key]}),set:async data=>Object.assign(local,data)},
    session:{get:async key=>({[key]:session[key]}),set:async data=>Object.assign(session,data)}},
    tabs:{get:async()=>({id:11,url:conversation,status:'complete'})}};
  const api = async (_route, body) => {
    if (!body) return {package:{...receipt, prompt:'saved prompt', image_path:'saved image'}};
    calls.push(body);
    if (body.stage === 'redesign_prepare') {
      const proof = body.retry_evidence;
      assert.equal(body.request_id, 'owned');
      assert.equal(body.context_id, 'context');
      assert.equal(body.conversation_url, conversation);
      assert.equal(proof.matched_request, true);
      assert.equal(proof.answer_complete, true);
      assert.equal(proof.answer_truncated, false);
      assert.equal(proof.stop, false);
      assert.equal(proof.busy, false);
      assert.equal(proof.video_count, 0);
      assert.equal(proof.answer_text, answer);
      assert(proof.samples >= 2 && proof.stable_ms >= 5000);
      receipt = {...receipt, stage:'redesigning', redesign:{id:'replacement',phase:'prepared'}};
    } else if (body.stage === 'retry_prepared') {
      throw Error('The exact Thai reply must not resend the same image and prompt');
    } else receipt = {...receipt, stage:body.stage, message:body.message};
    return {receipt:{...receipt}};
  };
  const adapter = new scope.Adapter({api,chromeAPI:chrome,redesign:async()=>{redesignCalls++;}});
  adapter.inspect = async () => ({...baseDOM,...dom});
  adapter.click = async () => { throw Error('No provider Send is authorized'); };
  const row = {...receipt, tabId:11, sendAt:now};
  return {adapter,row,calls,receipt:()=>receipt,redesignCalls:()=>redesignCalls};
}

async function observe(value) {
  await value.adapter.step(value.row);
  now += 6000;
  await value.adapter.step(value.row);
}

(async () => {
  assert.equal(scope.classify(answer), 'technical_redesign');
  assert.equal(scope.classify(`  ${answer}。  `), 'technical_redesign');
  assert.equal(scope.classify(`${answer} นโยบายไม่อนุญาต`), 'policy');
  assert.equal(scope.classify(`${answer} โควตาหมด`), 'quota');
  assert.equal(scope.classify(cases[0][0]), 'transient_service_error');

  const owned = fixture();
  await owned.adapter.step(owned.row);
  assert.equal(owned.calls.length, 0, 'one sample must not start redesign');
  now += 6000;
  await owned.adapter.step(owned.row);
  assert.equal(owned.calls.filter(call=>call.stage==='redesign_prepare').length, 1);
  assert.equal(owned.receipt().stage, 'redesigning');
  assert.equal(owned.calls.filter(call=>call.stage==='retry_prepared').length, 0);
  await owned.adapter.step(owned.row);
  assert.equal(owned.redesignCalls(), 1, 'existing helper owns the next step');

  for (const dom of [{matchedUser:false},{answerComplete:false},{answerTruncated:true},
    {stop:true},{busy:true},{answerBusy:true},{videoCount:1},
    {composerText:'manual draft'},{imageCount:1},{uploadDialog:true},
    {answerText:`${answer} นโยบายไม่อนุญาต`},{answerText:`${answer} โควตาหมด`}]) {
    const blocked = fixture({dom});
    await observe(blocked);
    assert.equal(blocked.calls.filter(call=>call.stage==='redesign_prepare').length, 0);
    assert.equal(blocked.calls.filter(call=>call.stage==='retry_prepared').length, 0);
  }
  const unknown = fixture({stage:'send_intent',dom:{matchedUser:false}});
  await observe(unknown);
  assert.equal(unknown.calls.filter(call=>['redesign_prepare','retry_prepared'].includes(call.stage)).length, 0);
  console.log('Meta exact Thai technical redesign: owned proof, guarded helper, and no blind retry passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
