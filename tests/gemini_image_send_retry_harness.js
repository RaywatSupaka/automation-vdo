// Real shared send loop + Background CDP/capture handler + Gemini-only retry.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { fixture } = require('./ai_send_acceptance_harness');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const copy = value => JSON.parse(JSON.stringify(value));
let cases = 0;
function setup(options = {}) {
  const f = fixture({ gemini: true, ...options });
  const c = f.frontend;
  const prompt = f.originalEditor.innerText;
  f.originalEditor.innerText=c.SmartFlowSingleAnswer.wrap(prompt);
  const storage = {}, images = [], refs = [], historyImages = [], historyRefs = [], assistants = [{ innerText: 'previous image answer' }];
  let claimReads = 0, claimWrites = 0, verifyCount = 0;
  f.state.elapsedMs = 0;
  const rows = { images, refs, historyImages, historyRefs, assistants };
  const shell = { querySelectorAll: selector => selector.startsWith('img') ? refs
    : selector.includes('[role="status"]') ? (f.state.uploadStatus ? [{ innerText: f.state.uploadStatus }] : [])
    : (f.state.uploadBusy ? [{}] : []) };
  f.originalEditor.closest = () => shell;
  const expansion=()=>{
    const overlay=f.state.expansion;
    if(overlay && !overlay.getBoundingClientRect)overlay.getBoundingClientRect=()=>({left:0,top:0,width:800,height:600,right:800,bottom:600});
    return overlay || null;
  };
  const originalQuery=f.page.document.querySelector;
  f.page.document.querySelector=selector=>selector==='.image-expansion-dialog-backdrop.cdk-overlay-backdrop-showing'
    ? expansion() : originalQuery(selector);
  const originalCommand=f.backend.chrome.debugger.sendCommand;
  f.backend.chrome.debugger.sendCommand=async(target,method,event)=>{
    await originalCommand(target,method,event);
    if(method==='Input.dispatchKeyEvent' && event.type==='keyUp' && event.key==='Escape' && !options.dismissFails){
      f.state.expansion=null;
    }
  };
  Object.assign(c, {
    IS_GEMINI: true, geminiImageRetryGuard: null, geminiImageSendGuardDetail: null,
    geminiTextRetryGuard: null, cancelRequested: false,
    location: { href: 'https://gemini.google.com/app/existing' },
    sendButton: () => f.state.button, assistantTurns: () => assistants,
    generatedImageElements: scope => scope === c.document ? [...historyImages, ...images] : images,
    sourceAttachmentPreviews: () => historyRefs,
    visible: element => !!element,
    document: { querySelector: expansion },
    Date: { now: () => 1000 + f.state.elapsedMs },
    crypto: { randomUUID: () => 'unique-claim-test' },
    assertNotCancelled: () => { if (c.cancelRequested) { const error = Error('cancelled'); error.name = 'AbortError'; throw error; } }
  });
  {
    if(options.story)c.activeJobId='STORY-TEST';
    c.userTurns=()=>f.state.accepted
      ? [{innerText:'previous request'},{innerText:'คุณบอกว่า\n'+prompt}]
      : [{innerText:'previous request'}];
  }
  c.chrome.storage = { local: {
    get: async key => { claimReads++; if (options.readFail) throw Error('storage read failed'); return { [key]: storage[key] ? copy(storage[key]) : null }; },
    set: async value => {
      claimWrites++; if (options.writeFail) throw Error('storage write failed');
      for (const [key, row] of Object.entries(value)) storage[key] = options.badAck ? { ...row, nonce: 'other' }
        : Object.fromEntries(Object.keys(row).sort().map(k => [k, row[k]]));
      if (options.acceptOnClaim) f.accept();
    }
  } };
  vm.runInContext(section('function motionRequestIsLatestUser(', 'async function sendAndVerify(')
    + section('function sameStoryImageReceipt(', 'function createStoryImageReceipt(')
    + section('function geminiImageSendState(', 'async function submitImagePrompt('), c);
  const ready = section('    if (message?.type === "VERIFY_AI_SEND_READY")', '    if (message?.type === "CANCEL_CHATGPT_JOB")');
  vm.runInContext(`function verifyReady(message) { return new Promise(resolve => { const sendResponse = resolve; (() => { ${ready} })(); }); }`, c);
  f.backend.chrome.tabs.sendMessage = async (_tab, message) => {
    verifyCount++;
    options.beforePress?.(f, c, rows, verifyCount);
    if (options.acceptAtRetryPress && verifyCount === 2) f.accept();
    if (options.cancelAtRetryPress && verifyCount === 2) c.cancelRequested = true;
    if (options.changeAtRetryPress && verifyCount === 2) f.state.editor.innerText = 'User edited the draft';
    return c.verifyReady(message);
  };
  const originalSend = c.chrome.runtime.sendMessage;
  c.chrome.runtime.sendMessage = async message => {
    const result = await originalSend(message);
    if (options.acceptSecond && f.sends() === 2) f.accept();
    return result;
  };
  const originalSleep = c.sleep;
  c.sleep = async ms => {
    await originalSleep(ms);
    f.state.elapsedMs += ms;
    options.onSleep?.(f, c, rows);
    if (f.state.sleeps === 240) options.afterFirstWait?.(f, c, images, refs, assistants);
  };
  // Composer replacement can remove Send immediately after acceptance.
  const originalAccept = f.accept;
  f.accept = () => { originalAccept(); f.state.editor.closest = () => null; };
  const run = () => c.sendGeminiImageAndVerify(f.state.button, f.originalEditor, 1, 'existing-user-turn', assistants.length, 2, 1,
    options.storyContext || null);
  return { ...f, run, storage, images, refs, historyImages, historyRefs, assistants,
    claimWrites: () => claimWrites, claimReads: () => claimReads,
    presses: () => f.commands.filter(x => x.type === 'mousePressed').length };
}

(async () => {
  let f = setup({ acceptImmediately: true });
  await f.run(); assert.equal(f.presses(), 1); assert.equal(f.claimWrites(), 0); cases++;

  f = setup({ acceptSecond: true, pressReplacesButton: true });
  await f.run(); assert.equal(f.presses(), 2); assert.equal(f.claimWrites(), 1);
  assert.ok(f.reports.some(row => row.step === 'gemini_image_send_retry_accepted'));
  assert.equal(f.frontend.geminiImageRetryGuard, null); cases++;

  f = setup();
  await assert.rejects(f.run(), error => error.code === 'AI_SEND_DISPATCHED_UNCONFIRMED');
  assert.equal(f.presses(), 2); assert.equal(f.claimWrites(), 1);
  assert.equal(f.frontend.geminiImageRetryGuard, null);
  await assert.rejects(f.run(), error => error.code === 'GEMINI_IMAGE_SEND_REVIEW');
  assert.equal(f.presses(), 2, 're-entry cannot spend a third click'); cases++;

  for (const options of [{ acceptAfterSleeps: 44 }, { acceptAfterSleeps: 240 },
    { acceptOnClaim: true }, { acceptAtRetryPress: true }]) {
    f = setup(options); await f.run(); assert.equal(f.presses(), 1); cases++;
  }
  for (const signal of [
    (f,c) => { c.stopButtonVisible = () => true; },
    (f,c) => { c.lastUserTurnSignature = () => 'new user turn'; },
    (f,c,images,refs,assistants) => { assistants.push({ innerText: 'new reply' }); }
  ]) {
    f = setup({ afterFirstWait: signal }); await assert.rejects(f.run(),e=>e.code==='AI_SEND_DISPATCHED_UNCONFIRMED');
    assert.equal(f.presses(), 1); cases++;
  }
  for (const change of [
    (f) => { f.state.editor.innerText = 'different draft'; },
    (f,c) => { c.activeRunId = 'another-run'; },
    (f,c) => { c.activeJobId = 'another-job'; },
    (f,c) => { c.location.href = 'https://gemini.google.com/app/another'; },
    (f,c,images) => { images.push({ src: 'new-image' }); },
    (f,c,images,refs) => { refs.push({ src: 'new-source' }); },
    (f,c,images,refs,assistants) => { assistants[0].innerText = 'changed response'; },
    (f) => { f.state.button.disabled = true; },
    (f) => { f.state.expansion = {}; },
    (f) => { f.state.editor.closest = () => ({ querySelectorAll: () => [{}] }); }
  ]) {
    f = setup({ afterFirstWait: change });
    await assert.rejects(f.run()); assert.equal(f.presses(), 1); assert.equal(f.claimWrites(), 0); cases++;
  }
  for (const options of [{ cancelAtRetryPress: true }, { changeAtRetryPress: true },
    { afterFirstWait: (f,c) => { c.cancelRequested = true; } },
    { releaseResponseLost: true }, { writeFail: true }, { badAck: true }]) {
    f = setup(options); await assert.rejects(f.run()); assert.equal(f.presses(), 1); cases++;
  }
  f = setup({ readFail: true }); await assert.rejects(f.run()); assert.equal(f.presses(), 0); cases++;
  // Current composer reference changes block the bounded second gesture even
  // though the old history previews stay unchanged. Actual DOM uses .text-input-field.
  f=setup({afterFirstWait:(_f,_c,_images,refs)=>{refs[0].src='replacement-reference';}});
  f.refs.push({src:'current-reference'});
  f.frontend.sourceAttachmentPreviews=()=>Array.from({length:5},(_,i)=>({src:`old-${i}`}));
  assert.equal(JSON.parse(f.frontend.geminiImageSendState().sourceSignature).length,1);
  await assert.rejects(f.run());assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);cases++;
  f=setup({afterFirstWait:(_f,_c,_images,refs)=>{refs[0].complete=false;}});
  f.refs.push({src:'current-reference',complete:true,naturalWidth:572});
  await assert.rejects(f.run());assert.equal(f.presses(),1);cases++;

  // Readiness belongs to the first gesture too. Failed/uploading references,
  // active generation and undismissed overlays cannot receive a mouse press.
  for (const [label, prepare, options = {}] of [
    ['loading reference', f => { f.refs.push({src:'current-reference',complete:false,naturalWidth:0}); }],
    ['empty reference pixels', f => { f.refs.push({src:'current-reference',complete:true,naturalWidth:0}); }],
    ['upload progress', f => { f.state.uploadBusy=true; }],
    ['upload failure', f => { f.state.uploadStatus='Upload failed'; }],
    ['active response', f => { f.frontend.stopButtonVisible=()=>true; }],
    ['expanded image dismissal failed', f => { f.state.expansion={}; },{dismissFails:true}],
    ['disabled send', f => { f.state.button.disabled=true; }]
  ]) {
    f=setup(options);prepare(f);
    await assert.rejects(f.run(), undefined, label);
    assert.equal(f.presses(),0,label);assert.equal(f.claimWrites(),0,label);
    if(options.dismissFails){
      assert.deepEqual(f.commands.filter(event=>event.method==='Input.dispatchKeyEvent').map(event=>[event.type,event.key]),
        [['keyDown','Escape'],['keyUp','Escape']]);
      assert(f.state.expansion,'unsuccessful Escape cannot authorize Send');
    }
    assert(f.state.elapsedMs<=12250,`${label}: readiness wait stays bounded`);cases++;
  }
  // An expansion already open at entry retains Background's one trusted
  // Escape dismissal. Only after it has closed may the initial Send proceed.
  f=setup({acceptImmediately:true});f.state.expansion={};
  await f.run();assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);
  assert.deepEqual(f.commands.filter(event=>event.method==='Input.dispatchKeyEvent').map(event=>[event.type,event.key]),
    [['keyDown','Escape'],['keyUp','Escape']]);
  assert.equal(f.state.expansion,null);
  assert(f.commands.findIndex(event=>event.type==='mousePressed')>f.commands.findIndex(event=>event.type==='keyUp'));
  cases++;
  // A newly opened overlay during first preflight is not the initial
  // dismissal exemption, and must block without pressing or another Escape.
  f=setup({beforePress:current=>{current.state.expansion={};}});
  await assert.rejects(f.run(),error=>{
    assert.equal(error.sendDiagnostics.gesture_phase,'not_started');
    assert(error.sendDiagnostics.changed_fields.includes('image_expanded'));
    return true;
  });
  assert.equal(f.presses(),0);assert.equal(f.claimWrites(),0);
  assert.equal(f.commands.filter(event=>event.method==='Input.dispatchKeyEvent').length,0);cases++;
  // After the initial dismissal, a reopened overlay is a permanent change
  // for this wait even if it closes again before the full minute expires.
  f=setup({onSleep:current=>{
    if(current.state.sleeps===20)current.state.expansion={};
    if(current.state.sleeps===21)current.state.expansion=null;
  }});
  f.state.expansion={};
  await assert.rejects(f.run());assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);
  assert.equal(f.state.sleeps,240);
  assert.deepEqual(f.commands.filter(event=>event.method==='Input.dispatchKeyEvent').map(event=>[event.type,event.key]),
    [['keyDown','Escape'],['keyUp','Escape']]);cases++;
  for (const loadingReference of [false,true]) {
    f=setup({acceptImmediately:true,onSleep:(current,_c,rows)=>{
      if(current.state.sleeps<=2)assert.equal(current.sends(),0,'readiness waits before any dispatch request');
      if(current.state.sleeps===2){
        current.state.uploadBusy=false;
        for(const ref of rows.refs){ref.complete=true;ref.naturalWidth=572;}
      }
    }});
    if(loadingReference)f.refs.push({src:'current-reference',complete:false,naturalWidth:0});
    else f.state.uploadBusy=true;
    await f.run();assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);
    assert(f.state.elapsedMs>0 && f.state.elapsedMs<=12000);cases++;
  }
  // State can change after content preparation but before Background presses.
  for (const [label, change, changedField] of [
    ['reference edit',(_f,_c,rows)=>{rows.refs.push({src:'replacement-reference'});},'sourceSignature'],
    ['draft edit',current=>{current.state.editor.innerText='user edited draft';}],
    ['upload busy',current=>{current.state.uploadBusy=true;},'upload_busy'],
    ['upload failed',current=>{current.state.uploadStatus='Upload failed';}],
    ['response active',(_f,c)=>{c.stopButtonVisible=()=>true;}],
    ['cancelled',(_f,c)=>{c.cancelRequested=true;}]
  ]) {
    f=setup({beforePress:change});
    await assert.rejects(f.run(),error=>{
      if(changedField){
        assert.equal(error.sendDiagnostics.gesture_phase,'not_started',label);
        assert.equal(error.sendDiagnostics.preflight_reason,'image_retry_guard',label);
        assert(error.sendDiagnostics.changed_fields.includes(changedField),label);
      }
      return true;
    },label);
    assert.equal(f.presses(),0,label);assert.equal(f.claimWrites(),0,label);
    assert.equal(f.frontend.geminiImageRetryGuard,null,label);cases++;
  }
  // Every acceptance sample contributes to the unchanged observation. A
  // restored draft/reference/upload state must not make a second press safe.
  const transientChanges=[
    ['draft',current=>{const saved=current.state.editor.innerText;current.state.editor.innerText='temporary user edit';return()=>{current.state.editor.innerText=saved;};}],
    ['reference',(_f,_c,rows)=>{rows.refs[0].src='temporary-reference';return()=>{rows.refs[0].src='current-reference';};}],
    ['upload busy',current=>{current.state.uploadBusy=true;return()=>{current.state.uploadBusy=false;};}],
    ['owner',(_f,c)=>{const saved=c.activeRunId;c.activeRunId='temporary-run';return()=>{c.activeRunId=saved;};}]
  ];
  for (const [label,change] of transientChanges) {
    let restore;
    f=setup({onSleep:(current,c,rows)=>{
      if(current.state.sleeps===20)restore=change(current,c,rows);
      if(current.state.sleeps===21)restore();
    }});
    f.refs.push({src:'current-reference',complete:true,naturalWidth:572});
    await assert.rejects(f.run(),undefined,label);
    assert.equal(f.presses(),1,label);assert.equal(f.claimWrites(),0,label);
    assert.equal(f.state.sleeps,240,'still give late acceptance the full minute');cases++;
  }
  // A later exact acceptance wins even after a prior transient observation.
  let restore;
  f=setup({onSleep:(current,c,rows)=>{
    if(current.state.sleeps===20)restore=transientChanges[0][1](current,c,rows);
    if(current.state.sleeps===21)restore();
    if(current.state.sleeps===80)current.accept();
  }});
  await f.run();assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);cases++;

  // Lazy history images, old uploads and previous answer toolbars are outside
  // the current request guard, before the first click and during its wait.
  for (const beforePress of [true,false]) {
    const historyChange=(_f,_c,rows)=>{
      rows.historyImages.push({src:'history-loaded-late'});
      rows.historyRefs[0].src='history-thumbnail-refreshed';
      rows.assistants[0].innerText='older answer refreshed';
      rows.assistants.at(-1).innerText='latest answer toolbar refreshed';
    };
    f=setup(beforePress?{acceptImmediately:true,beforePress:historyChange}
      :{acceptSecond:true,onSleep:(current,c,rows)=>{if(current.state.sleeps===20)historyChange(current,c,rows);}});
    f.historyRefs.push({src:'old-upload'});
    f.refs.push({src:'current-reference',complete:true,naturalWidth:572});
    f.assistants.unshift({innerText:'older answer'});
    f.assistants.at(-1).querySelector=()=>({textContent:'previous image answer'});
    await f.run();assert.equal(f.presses(),beforePress?1:2);
    assert.equal(f.claimWrites(),beforePress?0:1);cases++;
  }

  // Story image acceptance uses the real exact-current-user helper. A prior
  // transient change forbids retry, but cannot suppress later owned acceptance.
  let storyDraft;
  f=setup({story:true,onSleep:current=>{
    if(current.state.sleeps===20){storyDraft=current.state.editor.innerText;current.state.editor.innerText='temporary Story edit';}
    if(current.state.sleeps===21)current.state.editor.innerText=storyDraft;
    if(current.state.sleeps===80)current.accept();
  }});
  await f.run();assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);
  assert(f.reports.some(row=>row.step==='ai_send_accepted' && row.submission_proof==='owned_gemini_user_turn'));cases++;

  f=setup({story:true,onSleep:(current,c)=>{
    if(current.state.sleeps===20)c.stopButtonVisible=()=>true;
    if(current.state.sleeps===21)c.stopButtonVisible=()=>false;
  }});
  await assert.rejects(f.run());assert.equal(f.presses(),1);assert.equal(f.claimWrites(),0);
  assert.equal(f.state.sleeps,240);
  assert(!f.reports.some(row=>row.step==='ai_send_accepted'));cases++;

  // Another actor may submit the same exact request while Background is
  // preparing the first gesture. The fresh owned user turn needs zero presses.
  f=setup({story:true,beforePress:(current,_c,_rows,check)=>{
    assert.equal(check,1);current.accept();
  }});
  await f.run();assert.equal(f.presses(),0);assert.equal(f.claimWrites(),0);
  assert.equal(f.frontend.geminiImageRetryGuard,null);cases++;

  f=setup({story:true,beforePress:(_f,c)=>{c.stopButtonVisible=()=>true;}});
  await assert.rejects(f.run(),error=>{
    assert.equal(error.sendDiagnostics.gesture_phase,'not_started');
    assert(error.sendDiagnostics.changed_fields.includes('response_active'));
    return true;
  });
  assert.equal(f.presses(),0);assert.equal(f.claimWrites(),0);
  assert(!f.reports.some(row=>row.step==='ai_send_accepted'));cases++;
  // A completed technical predecessor can claim a distinct durable Gemini
  // generation epoch; the prior gesture-retry key must not poison this new
  // confirmed attempt. Dispatch proof is written before its trusted click.
  const dispatches=[];
  f=setup({story:true,acceptImmediately:true,storyContext:{geminiGenerationNonce:'completed-tech-2',
    onDispatch:async(prompt,baseline)=>dispatches.push({prompt,baseline})}});
  const owner=f.frontend.geminiTextSendState();
  f.storage[`smartpostGeminiImageSendRetry:${owner.job}:${owner.run}:2`]={retry_count:1};
  await f.run();assert.equal(f.presses(),1);assert.equal(dispatches.length,1);
  assert.equal(dispatches[0].prompt,owner.prompt);
  assert.equal(dispatches[0].baseline.before_user_count,1);cases++;
  // Generic ChatGPT path remains the original single-press transaction.
  const chatgpt = fixture();
  await assert.rejects(chatgpt.run(), error => error.code === 'AI_SEND_DISPATCHED_UNCONFIRMED');
  chatgpt.checkSingleDispatch(); cases++;
  console.log(JSON.stringify({ ok: true, cases }));
})().catch(error => { console.error(error); process.exitCode = 1; });
