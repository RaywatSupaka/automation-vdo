// Execute the actual trusted Send handler and both of its injected resolvers.
// All browser surfaces are isolated fixtures; no live tab or provider is used.
const assert = require('node:assert/strict');
const { fixture } = require('./ai_send_acceptance_harness.js');

function composerControl(options = {}) {
  const f = fixture({ label: options.label ?? 'ส่ง', acceptImmediately: true });
  let testId = options.testId ?? 'composer-submit-button';
  let title = options.title ?? '';
  const originalAttribute = f.state.button.getAttribute;
  f.state.button.getAttribute = name => name === 'data-testid' ? testId
    : name === 'title' ? title : originalAttribute(name);
  const originalQuery = f.page.document.querySelectorAll;
  f.page.document.querySelectorAll = selector => selector === `button[data-testid="${testId}"]`
    ? [f.state.button] : originalQuery(selector);
  return {
    ...f,
    morph(next) {
      if (next.label !== undefined) f.state.label = next.label;
      if (next.testId !== undefined) testId = next.testId;
      if (next.title !== undefined) title = next.title;
    }
  };
}

async function noPress(f, label) {
  await assert.rejects(f.run(), undefined, label);
  assert.equal(f.responses[0].notDispatched, true, label);
  assert.equal(f.commands.filter(event => event.type === 'mousePressed').length, 0, label);
  assert.equal(f.commands.filter(event => event.type === 'mouseReleased').length, 0, label);
  assert.equal(f.commands.filter(event => event.method === 'Input.dispatchKeyEvent').length, 0, label);
  assert.equal(f.sends(), 1, label + ': no second request');
}

async function tests() {
  let cases = 0;
  for (const label of ['Stop', 'Stop generating', 'Stop response', 'Stop streaming',
                       'หยุด', 'หยุดการสร้าง', 'หยุดคำตอบ', '  STOP   GENERATING  ']) {
    await noPress(composerControl({label}), 'initial Stop label: ' + label); cases++;
  }
  for (const title of ['Stop', 'หยุด', 'Stop generating']) {
    await noPress(composerControl({label: 'ส่ง', title}), 'initial Stop title: ' + title); cases++;
  }
  await noPress(composerControl({label: 'ส่ง', testId: 'stop-button'}), 'explicit Stop test ID'); cases++;

  // A Send-labelled control can morph into Stop without changing node/geometry.
  for (const next of [{label:'หยุด'}, {label:'Stop generating'}, {title:'Stop'}, {testId:'stop-button'}]) {
    const f = composerControl();
    const attach = f.backend.chrome.debugger.attach;
    f.backend.chrome.debugger.attach = async (...args) => { await attach(...args); f.morph(next); };
    await noPress(f, 'same-node Stop before press: ' + JSON.stringify(next)); cases++;
  }

  // Preserve proven Thai/English Send labels and unlabeled test-ID fallback.
  for (const label of ['ส่ง', 'ส่งข้อความ', 'ส่งพรอมต์', 'Send message', 'Send prompt', '']) {
    const f = composerControl({label}); await f.run();
    assert.equal(f.responses[0].ok, true, 'real Send: ' + label); f.checkSingleDispatch(); cases++;
  }
  process.stdout.write(JSON.stringify({ok:true, cases}) + '\n');
}
tests().catch(error => { console.error(error); process.exitCode = 1; });
