// Actual background recovery and resume functions; no network/browser/provider work.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const orderClone = (value, reverse) => Array.isArray(value) ? value.map(item => orderClone(item, reverse))
  : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value)
    .sort((left, right) => (reverse ? -1 : 1) * left.localeCompare(right))
    .map(key => [key, orderClone(value[key], reverse)])) : value;
function functionSource(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert(start >= 0, name);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}
function fixture(options = {}) {
  const job = 'STORY-REFRESH', key = `smartpostStoryGeneratedImage:chatgpt:${job}:12`;
  const message = {type: 'RELOAD_CHATGPT_STORY_RESULT', provider: 'chatgpt', job_id: job, run_id: 'RUN-CURRENT', index: 12,
    receipt_identity: '["exact-scene-and-source-identity"]', send_nonce: 'send-nonce',
    prompt: 'exact image request', conversation_url: 'https://chatgpt.com/c/current',
    stagnant_since: 1000000, signature: 'owned-failed-image',
    stalled_reason: 'image_load_failed', stable_samples: 3};
  const sender = {tab: {id: 7, url: message.conversation_url, status:'complete'}};
  const storage = {
    [`smartpostAIWebTab:chatgpt:${job}`]: 7, [`smartpostAIWebRun:${job}`]: message.run_id,
    [key]: {version: 1, job_id: job, provider: 'chatgpt', scene_index: 12,
      identity: message.receipt_identity, run_id: 'ORIGINAL-ACCEPTED-RUN', status: 'awaiting_result',
      send_phase: 'accepted', send_nonce: message.send_nonce,
      result_proof: {prompt: message.prompt, conversation_url: message.conversation_url,
        request_turn_id: 'conversation-turn-24', request_message_id: 'current-user'}},
  };
  const events = [], replies = [], failures = [], resumes = [];
  let guardCount = 0, missingTab = false, storageReadCount = 0, documentGeneration=0;
  const context = vm.createContext({
    crypto: webcrypto, TextEncoder, Uint8Array,
    Date: {now: () => 1000000},
    setTimeout: callback => {options.onDelay?.(storage, sender); callback();},
    chatGPTStoryResultRefreshLocks: new Set(),
    chrome: {
      storage: {local: {
        get: async () => options.reorderStorage ? orderClone(storage, ++storageReadCount % 2 === 0) : clone(storage),
        set: async values => {
          events.push('persist'); Object.assign(storage, clone(values));
          options.onSet?.(storage, values);
        },
      }},
      tabs: {
        get: async id => {if (missingTab) throw Error('tab closed'); return {...sender.tab, id};},
        sendMessage: async (id, guard) => {
          assert.equal(id, 7); assert.equal(guard.type, 'VERIFY_CHATGPT_STORY_RESULT_REFRESH');
          events.push('guard'); guardCount += 1;
          const reply = {ok: true, allowed: true, challenge: guard.challenge,
            send_nonce: guard.send_nonce, signature: guard.signature, stagnant_since: guard.stagnant_since,
            stalled_reason: guard.stalled_reason, stable_samples: guard.stable_samples};
          options.guard?.(reply, guardCount, storage, sender);
          return reply;
        },
        reload: async id => {events.push('reload'); assert.equal(id, 7); options.onReload?.(storage, sender); documentGeneration++;},
      },
      scripting:{executeScript:async()=>[{frameId:0,documentId:`document-${documentGeneration}`,result:sender.tab.url}]},
    },
    waitForAIRefreshReady: async (id,_verify,_notice,_timeout,fence) => {events.push('loaded'); if (options.closeOnReload) missingTab = true;
      return fence?{documentId:`document-${documentGeneration}`}:undefined;},
    startAIWebJob: async (...args) => {
      events.push('resume');
      if(options.busy){const error=Error('same Job still running');error.code='AI_WEB_JOB_BUSY';error.jobId=job;throw error;}
      await args[5](7); resumes.push(args.slice(0, 5));
    },
    reportWebActionProgress: async value => failures.push(value),
  });
  for (const name of ['normalizeAIProvider', 'aiRunStorageKey', 'aiProgressOwnership',
    'assertStoryCheckpointOwner', 'refreshStoryChatGPTResult']) vm.runInContext(functionSource(name), context);
  const handler = source.slice(source.indexOf('    if (message?.type === "RELOAD_CHATGPT_STORY_RESULT")'),
    source.indexOf("    if(message?.type==='RELOAD_GEMINI_STORY')"));
  vm.runInContext(`async function dispatch(message, sender, sendResponse) {${handler}}`, context);
  const dispatch = async (patch = {}) => {
    await context.dispatch({...message, ...patch}, sender, reply => {
      if (reply.ok) events.push('ack'); replies.push(clone(reply));
    });
  };
  return {message, sender, storage, key, events, replies, failures, resumes, context, dispatch};
}
(async () => {
  let cases = 0;
  const valid = fixture(), original = clone(valid.storage[valid.key]);
  await valid.dispatch();
  assert.deepEqual(valid.replies, [{ok: true, refresh_scheduled: true}]);
  assert.deepEqual(valid.resumes, [['STORY-REFRESH', true, 'chatgpt', false, 'RUN-CURRENT']]);
  assert.deepEqual(valid.storage[valid.key], original, 'accepted receipt must remain byte-equivalent');
  assert.equal(valid.events.filter(x => x === 'reload').length, 1);
  assert(valid.events.lastIndexOf('guard') < valid.events.indexOf('ack'));
  assert.equal(valid.events[valid.events.indexOf('reload') - 1], 'ack');
  cases += 1;
  const busy=fixture({busy:true});await busy.dispatch();
  assert.equal(busy.replies[0].refresh_scheduled,true);
  assert.equal(busy.failures.at(-1).step,'recovering_response');
  assert.equal(busy.failures.some(row=>row.step==='error'),false);
  assert.equal(busy.resumes.length,0);cases++;
  // DOM completion evidence is sufficient without waiting any number of minutes.
  const empty = fixture(); await empty.dispatch({stalled_reason: 'empty_completed_response'});
  assert.deepEqual(empty.replies, [{ok: true, refresh_scheduled: true}]); cases += 1;
  const stream = fixture(); await stream.dispatch({stalled_reason:'completed_service_error'});
  assert.equal(stream.replies[0].refresh_scheduled,true);cases++;
  const minute = fixture();await minute.dispatch({stalled_reason:'idle_answer_wait',stagnant_since:940000});
  assert.equal(minute.replies[0].refresh_scheduled,true);cases++;
  const early = fixture();await early.dispatch({stalled_reason:'idle_answer_wait',stagnant_since:940001});
  assert.equal(early.replies[0].ok,false);assert(!early.events.includes('reload'));cases++;
  const nextAttempt=fixture();
  await nextAttempt.dispatch();
  nextAttempt.storage[nextAttempt.key].service_retry_count=1;
  nextAttempt.storage[nextAttempt.key].send_nonce='new-send-nonce';
  await nextAttempt.dispatch({send_nonce:'new-send-nonce'});
  assert.equal(nextAttempt.events.filter(x=>x==='reload').length,2);cases++;
  const missing = fixture();
  await missing.dispatch({stalled_reason:'request_dom_missing',stagnant_since:970000});
  assert.deepEqual(missing.replies,[{ok:true,refresh_scheduled:true}]);
  assert.equal(missing.events.filter(x=>x==='reload').length,1);
  await missing.dispatch({stalled_reason:'request_dom_missing',stagnant_since:970000});
  assert.match(missing.replies.at(-1).error,/budget used/);cases+=2;
  for(const turn of ['', 'conversation-turn-unknown']){
    const f=fixture();f.storage[f.key].result_proof.request_turn_id=turn;
    await f.dispatch({stalled_reason:'request_dom_missing',stagnant_since:970000});
    assert.equal(f.replies.at(-1).ok,false);assert(!f.events.includes('reload'));cases++;
  }
  for(const since of [970001,1000000,1000001]){
    const f=fixture();await f.dispatch({stalled_reason:'request_dom_missing',stagnant_since:since});
    assert.equal(f.replies.at(-1).ok,false);assert(!f.events.includes('reload'));cases++;
  }
  const reordered = fixture({reorderStorage: true}); await reordered.dispatch();
  assert.deepEqual(reordered.replies, [{ok: true, refresh_scheduled: true}],
    'Chrome storage key order cannot invalidate equivalent receipt or budget ACK');
  assert.equal(reordered.events.filter(event => event === 'reload').length, 1); cases += 1;
  // Durable budget survives both a worker restart and a newly owned desktop run.
  valid.context.chatGPTStoryResultRefreshLocks.clear();
  valid.storage['smartpostAIWebRun:STORY-REFRESH'] = 'NEW-RUN';
  await valid.dispatch({run_id: 'NEW-RUN'});
  assert.match(valid.replies.at(-1).error, /budget used/);
  assert.equal(valid.events.filter(x => x === 'reload').length, 1);
  cases += 1;
  for (const patch of [
    {provider: 'gemini'}, {job_id: 'JOB-WRONG'}, {index: 0}, {index: 51}, {index: 2.5},
    {run_id: 'WRONG'}, {run_id: ''}, {receipt_identity: 'changed'}, {send_nonce: 'changed'},
    {prompt: 'another prompt'}, {conversation_url: 'https://chatgpt.com/'},
    {conversation_url: 'https://chatgpt.com/c/other'}, {stalled_reason: ''},
    {stalled_reason: 'image_loading'}, {stalled_reason: 'unknown'},
    {stable_samples: 2}, {stable_samples: 3.5}, {stable_samples: 101},
    {stagnant_since: NaN}, {signature: ''},
  ]) {
    const f = fixture(); await f.dispatch(patch);
    assert.equal(f.replies.at(-1).ok, false, JSON.stringify(patch));
    assert(!f.events.includes('reload')); assert(!f.events.includes('resume')); cases += 1;
  }
  for (const mutate of [
    f => f.sender.tab.id = 8,
    f => f.sender.tab.url = 'https://example.com/c/current',
    f => delete f.storage['smartpostAIWebTab:chatgpt:STORY-REFRESH'],
    f => delete f.storage['smartpostAIWebRun:STORY-REFRESH'],
    f => f.storage[f.key].status = 'generated',
    f => f.storage[f.key].image_url = 'https://chatgpt.com/backend-api/estuary/already-ready',
    f => f.storage[f.key].send_phase = 'dispatching',
    f => delete f.storage[f.key].send_nonce,
    f => delete f.storage[f.key].result_proof,
    f => f.storage[f.key].scene_index = 11,
    f => f.storage['smartflowChatGPTStoryRefreshCancelled:STORY-REFRESH'] = 'RUN-CURRENT',
  ]) {
    const f = fixture(); mutate(f); await f.dispatch();
    assert.equal(f.replies.at(-1).ok, false); assert(!f.events.includes('reload')); cases += 1;
  }
  // Live guard denies busy/loading progress, ready images, new drafts and changed ownership.
  for (const field of ['allowed', 'challenge', 'send_nonce', 'signature', 'stagnant_since', 'stalled_reason', 'stable_samples']) {
    for (const finalOnly of [false, true]) {
      const f = fixture({guard: (reply, count) => {
        if (!finalOnly || count === 2) reply[field] = field === 'allowed' ? false : 'changed';
      }});
      await f.dispatch(); assert.equal(f.replies.at(-1).ok, false);
      assert(!f.events.includes('reload')); assert(!f.events.includes('ack')); cases += 1;
    }
  }
  for (const onDelay of [
    storage => storage['smartpostAIWebRun:STORY-REFRESH'] = 'NEW-RUN',
    storage => storage['smartflowChatGPTStoryRefreshCancelled:STORY-REFRESH'] = 'RUN-CURRENT',
    (_storage, sender) => sender.tab.url = 'https://chatgpt.com/c/other',
    storage => storage['smartpostStoryGeneratedImage:chatgpt:STORY-REFRESH:12'].result_proof.request_message_id = 'changed',
  ]) {
    const f = fixture({onDelay}); await f.dispatch();
    assert(!f.events.includes('reload')); assert.equal(f.replies.at(-1).ok, false);
    assert(Object.keys(f.storage).some(k => k.startsWith('smartflowChatGPTStoryResultRefresh:')));
    cases += 1;
  }
  const missingACK = fixture({onSet: (storage, values) => {
    const key = Object.keys(values).find(k => k.startsWith('smartflowChatGPTStoryResultRefresh:'));
    if (key) delete storage[key];
  }});
  await missingACK.dispatch(); assert.match(missingACK.replies.at(-1).error, /ACK missing/);
  assert(!missingACK.events.includes('reload')); cases += 1;
  const removed = fixture({closeOnReload: true}); await removed.dispatch();
  assert.equal(removed.events.filter(x => x === 'reload').length, 1);
  assert.equal(removed.resumes.length, 0); assert.equal(removed.failures.length, 1);
  assert.match(removed.failures[0].message, /STORY_IMAGE_RECEIPT_REVIEW/); cases += 1;
  const concurrent = fixture(); await Promise.all([concurrent.dispatch(), concurrent.dispatch()]);
  assert.equal(concurrent.events.filter(x => x === 'reload').length, 1); cases += 1;
  // Actual startAIWebJob: losing the registered tab during package-fetch must
  // never fall through to its ordinary missing-tab/new-tab recovery.
  for (const missingTab of [true, false]) {
    let opens = 0, starts = 0, guards = 0;
    const c = vm.createContext({
      BRIDGE: 'http://offline.invalid', AI_WEB: {chatgpt: {name: 'ChatGPT', matches: ['https://chatgpt.com/*']}},
      bridgeFetch: async () => ({ok: true, json: async () => ({ok: true, package: {job: {id: 'STORY-REFRESH'}}})}),
      chrome: {storage: {local: {get: async () => ({'smartpostAIWebTab:chatgpt:STORY-REFRESH': 7}), set: async () => {}}},
        tabs: {get: async () => {if (missingTab) throw Error('closed'); return {id: 7, url: 'https://chatgpt.com/c/current'};},
          update: async () => {}, sendMessage: async (_id, value) => {starts += 1; assert.equal(value.package.reuse_analysis, true); return {ok: true};}},
        scripting: {executeScript: async () => {}}},
      openAIWebTab: async () => {opens += 1; return 8;}, waitForTabComplete: async () => {},
      waitForAIRefreshReady: async (_id, guard) => guard(),
      isWebLoginUrl: () => false,
    });
    for (const name of ['normalizeAIProvider', 'startAIWebJob']) vm.runInContext(functionSource(name), c);
    const call = () => c.startAIWebJob('STORY-REFRESH', true, 'chatgpt', false, 'RUN-CURRENT', async id => {
      guards += 1; if (id !== undefined) assert.equal(id, 7);
    });
    if (missingTab) await assert.rejects(call(), /tab disappeared/); else await call();
    assert.equal(opens, 0); assert.equal(starts, missingTab ? 0 : 1); assert(guards >= (missingTab ? 1 : 4)); cases += 1;
  }
  process.stdout.write(JSON.stringify({ok: true, cases}));
})().catch(error => {console.error(error); process.exitCode = 1;});
