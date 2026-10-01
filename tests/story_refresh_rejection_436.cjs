const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');

const source = fs.readFileSync('browser_extension/background.js', 'utf8');
const slice = source.slice(source.indexOf('const chatGPTStoryResultRefreshLocks = new Set();'),
  source.indexOf('const geminiReloadLocks = new Set();'));
assert(slice.includes('async function refreshStoryChatGPTResult('));

const url = 'https://chatgpt.com/c/fixture';
const message = {provider:'chatgpt',job_id:'STORY-FIXTURE',run_id:'RUN-FIXTURE',index:2,
  conversation_url:url,receipt_identity:'identity',send_nonce:'nonce',prompt:'Exact request',
  signature:'abc123',stalled_reason:'image_load_failed',stable_samples:3,
  stagnant_since:Date.now()-60000};
const receipt = {version:1,job_id:message.job_id,provider:'chatgpt',scene_index:2,
  status:'awaiting_result',send_phase:'accepted',run_id:message.run_id,
  identity:message.receipt_identity,send_nonce:message.send_nonce,
  result_proof:{prompt:message.prompt,conversation_url:url,request_message_id:'message-fixture'}};
const receiptKey = `smartpostStoryGeneratedImage:chatgpt:${message.job_id}:2`;

async function run(mode) {
  let budgetRow = mode==='budget_used' ? {phase:'claimed'} : null;
  let reloads = 0, writes = 0, liveChecks = 0;
  const chrome = {
    tabs:{get:async()=>({url}),reload:async()=>{reloads++;}},
    storage:{local:{
      get:async keys => Array.isArray(keys) ? {[receiptKey]:receipt}
        : keys===receiptKey ? {[receiptKey]:receipt}
        : {[keys]:budgetRow},
      set:async value=>{
        writes++;budgetRow=Object.values(value)[0];
        if(mode==='write_then_throw') throw Error('storage callback failed after write');
      },
    }},
  };
  chrome.tabs.sendMessage = async (_tab, challenge) => {
    liveChecks++;
    return mode==='guard_rejected' ? {ok:false}
      : {ok:true,allowed:true,challenge:challenge.challenge,
         send_nonce:message.send_nonce,signature:message.signature,
         stagnant_since:message.stagnant_since,stalled_reason:message.stalled_reason,
         failure_text:undefined,stable_samples:message.stable_samples};
  };
  if(mode==='claim_uncertain') chrome.storage.local.get = async keys => Array.isArray(keys)
    ? {[receiptKey]:receipt} : keys===receiptKey ? {[receiptKey]:receipt}
    : {[keys]:budgetRow && {...budgetRow, phase:'changed'}};
  const c=vm.createContext({chrome,crypto:webcrypto,TextEncoder,Date,Error,
    assertStoryCheckpointOwner:async()=>{},reportWebActionProgress:async()=>{},
    startAIWebJob:async()=>{throw Error('fresh job must not start');},
    restartableStoryServiceReceipt:()=>false,setTimeout});
  vm.runInContext(slice,c);
  let error;
  try {await c.refreshStoryChatGPTResult(message,{tab:{id:42}},()=>{});}
  catch (caught) {error=caught;}
  assert(error,`${mode} must reject before Chrome reload`);
  assert.equal(reloads,0);
  return {error,writes,liveChecks};
}

(async()=>{
  const changed=await run('guard_rejected');
  assert.equal(changed.error.refresh_retry_safe,true,
    `a fresh live guard denial before storage claim is explicitly retriable: ${changed.error.stack}`);
  assert.equal(changed.error.refresh_reason,'live_guard_changed');
  assert.equal(changed.writes,0);
  const claimed=await run('budget_used');
  assert.equal(claimed.error.refresh_retry_safe,false,
    'existing durable budget cannot be used for another reload');
  assert.equal(claimed.error.refresh_reason,'budget_used');
  assert.equal(claimed.liveChecks,0);
  const uncertain=await run('claim_uncertain');
  assert.equal(uncertain.error.refresh_retry_safe,false,
    'a failed ACK after storage write is not proof that reload is safe');
  assert.equal(uncertain.error.refresh_reason,'claim_uncertain');
  assert.equal(uncertain.writes,1);
  const writeUnknown=await run('write_then_throw');
  assert.equal(writeUnknown.error.refresh_retry_safe,false,
    'an uncertain storage write cannot reopen the same reload budget');
  assert.equal(writeUnknown.writes,1);
  console.log(JSON.stringify({ok:true,cases:4}));
})().catch(error=>{console.error(error);process.exitCode=1;});
