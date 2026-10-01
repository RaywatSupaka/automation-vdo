// Actual background guard/handlers. HTTP is only an in-memory call recorder.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/background.js'), 'utf8');
function functionSource(name) {
  const pattern = new RegExp(`(?:async )?function ${name}\\(`);
  const start = source.search(pattern);
  assert(start >= 0, `missing actual function ${name}`);
  const end = source.indexOf('\n}', start);
  assert(end > start);
  return source.slice(start, end + 2);
}
function handlerSource(type) {
  const start = source.indexOf(`    if (message?.type === "${type}") {`);
  assert(start >= 0, `missing actual handler ${type}`);
  const end = source.indexOf('\n    if (', start + 1);
  assert(end > start);
  return source.slice(start, end);
}
function fixture(provider = 'gemini') {
  const job = 'STORY-CHECKPOINT-OWNER', calls = [], responses = [];
  const storage = {
    [`smartpostAIWebTab:${provider}:${job}`]: 9,
    [`smartpostAIWebRun:${job}`]: 'RUN-CURRENT',
  };
  const context = vm.createContext({
    BRIDGE: 'http://offline.invalid',
    chrome: {storage: {local: {get: async () => ({...storage})}}},
    bridgeFetch: async (url, options) => {
      calls.push({url, body: JSON.parse(options.body)});
      return {ok: true, json: async () => ({ok: true})};
    },
    sendResponse: value => responses.push(value),
  });
  for (const name of ['normalizeAIProvider', 'resultAIProvider', 'aiRunStorageKey', 'aiProgressOwnership', 'assertStoryCheckpointOwner']) {
    vm.runInContext(functionSource(name), context);
  }
  vm.runInContext(`async function dispatch(message, sender) {\n${handlerSource('CHECKPOINT_STORY_IMAGE')}\n${handlerSource('CHECKPOINT_STORY_ANALYSIS')}\n${handlerSource('SUBMIT_STORY_RESULT')}\n}`, context);
  return {job, calls, responses, storage, dispatch: context.dispatch};
}
(async () => {
  let cases = 0;
  for (const provider of ['gemini', 'chatgpt']) {
    const url = provider === 'gemini' ? 'https://gemini.google.com/app/existing' : 'https://chatgpt.com/c/existing';
    for (const type of ['CHECKPOINT_STORY_IMAGE', 'CHECKPOINT_STORY_ANALYSIS', 'SUBMIT_STORY_RESULT']) {
      const clean = fixture(provider);
      const message = {type, provider, job_id: clean.job, run_id: 'RUN-CURRENT', index: 2,
        image: 'saved-image', result: {job_id: clean.job, provider}};
      await clean.dispatch(message, {tab: {id: 9, url}});
      assert.equal(clean.calls.length, 1);
      assert.equal(clean.calls[0].body.run_id, 'RUN-CURRENT');
      assert.equal(clean.calls[0].body.job_id, clean.job);
      assert.equal(clean.responses.length, 1);
      if (type === 'CHECKPOINT_STORY_IMAGE') assert.equal(clean.calls[0].body.index, 2);
      if (type === 'SUBMIT_STORY_RESULT') assert.equal(clean.calls[0].body.provider, `${provider}_web_extension`);
      cases += 1;
      for (const change of [
        {tab: {id: 10, url}}, {tab: {id: 0, url}}, {tab: {id: 9, url: 'https://example.com/'}},
        {run: ''}, {run: 'RUN-OLD'}, {provider: provider === 'gemini' ? 'chatgpt' : 'gemini'},
        {missingOwner: true}, {missingRun: true},
      ]) {
        const f = fixture(provider);
        if (change.missingOwner) delete f.storage[`smartpostAIWebTab:${provider}:${f.job}`];
        if (change.missingRun) delete f.storage[`smartpostAIWebRun:${f.job}`];
        const altered = {...message};
        if ('run' in change) altered.run_id = change.run;
        if (change.provider) altered.provider = change.provider;
        await assert.rejects(f.dispatch(altered, {tab: change.tab || {id: 9, url}}),
          `unexpected allowed ${provider}/${type}/${JSON.stringify(change)}`);
        assert.equal(f.calls.length, 0, 'invalid owner must never reach HTTP');
        assert.equal(f.responses.length, 0);
        cases += 1;
      }
    }
  }
  process.stdout.write(JSON.stringify({ok: true, cases}));
})().catch(error => { console.error(error); process.exitCode = 1; });
