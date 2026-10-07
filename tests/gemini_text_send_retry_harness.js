// Production text coordinator, acceptance loop and Background trusted gesture.
// Only browser surfaces/storage/time are simulated; no paid provider requests.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const { fixture } = require('./ai_send_acceptance_harness');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const part = (a,b) => source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)+a.length));
const copy = value => JSON.parse(JSON.stringify(value));
let cases = 0;
function setup(options = {}) {
  const f = fixture({ gemini:true, ...options }), c = f.frontend;
  const storage = {}, images = [], refs = [], historyImages = [], historyRefs = [], assistants = [{innerText:'previous completed JSON'}];
  const prompt = f.originalEditor.innerText;
  f.originalEditor.innerText=c.SmartFlowSingleAnswer.wrap(prompt);
  f.state.elapsedMs=0;
  const rows={images,refs,historyImages,historyRefs,assistants};
  const shell={innerText:'',querySelectorAll:selector=>selector.startsWith('img')?refs
    :selector.includes('[role="status"]')?(f.state.uploadStatus?[{innerText:f.state.uploadStatus}]:[])
    :(f.state.uploadBusy?[{}]:[])};
  f.originalEditor.closest=()=>shell;
  let writes=0, checks=0;
  Object.assign(c, { IS_GEMINI:true, geminiImageRetryGuard:null, geminiTextRetryGuard:null,
    cancelRequested:false, TextEncoder, Uint8Array, crypto:webcrypto,
    Date:{now:()=>1000+f.state.elapsedMs},
    location:{href:'https://gemini.google.com/app/existing'},
    sendButton:()=>f.state.button, assistantTurns:()=>assistants,
    generatedImageElements:scope=>scope===c.document?[...historyImages,...images]:images,
    sourceAttachmentPreviews:()=>historyRefs,
    visible:x=>!!x, document:{querySelector:()=>f.state.expansion||null},
    userTurns:()=>f.state.accepted ? [{innerText:'old'}, {innerText:'คุณบอกว่า\n'+prompt}] : [{innerText:'old'}],
    assertNotCancelled:()=>{if(c.cancelRequested){const e=Error('cancelled');e.name='AbortError';throw e;}}
  });
  c.chrome.storage={local:{
    get:async key=>{if(options.readFail)throw Error('read failed');return {[key]:storage[key]?copy(storage[key]):null};},
    set:async value=>{
      writes++; if(options.writeFail)throw Error('write failed');
      for(const [key,row] of Object.entries(value))storage[key]=options.badAck?{...row,nonce:'other'}:copy(row);
      if(options.acceptOnRetryClaim&&Object.values(value)[0].retry_count===1)f.accept();
    }
  }};
  vm.runInContext(part('function motionRequestIsLatestUser(', 'async function sendAndVerify(')
    +part('function sameStoryImageReceipt(', 'function createStoryImageReceipt(')
    +part('function geminiImageSendState(', 'async function sendGeminiImageAndVerify('), c);
  const ready=part('    if (message?.type === "VERIFY_AI_SEND_READY")','    if (message?.type === "CANCEL_CHATGPT_JOB")');
  vm.runInContext(`function verifyReady(message){return new Promise(resolve=>{const sendResponse=resolve;(()=>{${ready}})();});}`, c);
  f.backend.chrome.tabs.sendMessage=async(_tab,message)=>{
    checks++;
    options.beforePress?.(f,c,rows,checks);
    if(options.replaceClaimBeforePress)for(const row of Object.values(storage))row.nonce='other-owner';
    if(checks===2){
      if(options.acceptAtRetryPress)f.accept();
      if(options.editAtRetryPress)f.state.editor.innerText='user edited draft';
      if(options.cancelAtRetryPress)c.cancelRequested=true;
    }
    return c.verifyReady(message);
  };
  const originalSend=c.chrome.runtime.sendMessage;
  c.chrome.runtime.sendMessage=async message=>{
    const reply=await originalSend(message);
    if(options.acceptSecond&&f.sends()===2)f.accept();
    return reply;
  };
  const originalSleep=c.sleep;
  c.sleep=async ms=>{
    await originalSleep(ms);f.state.elapsedMs+=ms;options.onSleep?.(f,c,rows);
    if(f.state.sleeps===240)options.afterFirstWait?.(f,c,images,refs,assistants);
  };
  const run=()=>c.sendGeminiTextAndVerify(f.state.button,f.originalEditor,1,'existing-user-turn',assistants.length,prompt);
  return {...f,run,storage,images,refs,historyImages,historyRefs,assistants,prompt,writes:()=>writes,
    presses:()=>f.commands.filter(x=>x.type==='mousePressed').length};
}

async function twoPromptWorkflow() {
  const f=setup(),c=f.frontend;
  let clock=1000,attachments=0;
  const users=[],answers=[];
  function node(text,pos){return {innerText:text,textContent:text,position:pos,
    querySelector:()=>null,querySelectorAll:()=>[],getBoundingClientRect:()=>({width:100,height:40}),
    compareDocumentPosition:other=>other.position>pos?4:2};}
  Object.assign(c,{Date:{now:()=>clock},Node:{DOCUMENT_POSITION_FOLLOWING:4},
    document:{querySelector:()=>null,querySelectorAll:s=>s==='user-query'?users:s==='model-response'?answers:[]},
    waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>{},waitForComposer:async()=>f.state.editor,
    attachSourceImages:async()=>{attachments++;},
    setComposerText:async(editor,text)=>{editor.innerText=c.SmartFlowSingleAnswer.wrap(text);return editor;},
    waitForStableSendDraft:async expected=>{assert.equal(c.SmartFlowSingleAnswer.canonical(f.state.editor.innerText),expected);return{button:f.state.button,editor:f.state.editor};},
    analysisResponseStopButton:()=>null,explicitAnalysisRefusal:()=>false,explicitImageFailure:()=>false,
    sleep:async ms=>{clock+=ms;}
  });
  vm.runInContext(part('function assistantTurns(', 'function explicitImageFailure(')
    +part('function confirmedAnalysisTechnicalFailure(', 'function composerText(')
    +part('async function submitPrompt(', 'function analysisResponseStopButton(')
    +part('function analysisStopLabel(', 'function escapeJsonControlCharacters('),c);
  // First text click works; the next complete click is ignored by the website;
  // exactly its bounded repeat is accepted. The old JSON remains in the DOM.
  const originalSend=c.chrome.runtime.sendMessage;
  c.chrome.runtime.sendMessage=async message=>{
    const draft=f.state.editor.innerText;
    const reply=await originalSend(message);
    if(message.type==='MEMBERSHIP_AUTHORIZE') return reply;
    if(f.sends()===1||f.sends()===3){
      users.push(node('คุณบอกว่า\n'+draft,users.length*2+1));
      answers.push(node(JSON.stringify({answer:users.length}),answers.length*2+2));
      f.state.editor={innerText:'',closest:()=>null,getBoundingClientRect:()=>({left:20,top:20,width:40,height:40,bottom:60,right:60})};
    }
    return reply;
  };
  const first=await c.submitPrompt('Write the initial scene plan as JSON.');
  assert.equal(first.innerText,'{"answer":1}');
  const second=await c.submitPrompt('Bind the existing scene IDs without rewriting the story.');
  assert.equal(second.innerText,'{"answer":2}');
  assert.equal(f.presses(),3);assert.equal(users.length,2);assert.equal(attachments,0);
  assert.equal(Object.keys(f.storage).length,2);
  assert.equal(c.geminiTextRetryGuard,null);
  // Re-entry is checked before wait/composer mutation, including after new run.
  f.state.editor.innerText='user new draft';c.activeRunId='different-run';
  await assert.rejects(c.submitPrompt('Bind the existing scene IDs without rewriting the story.'),{code:'GEMINI_TEXT_SEND_REVIEW'});
  assert.equal(f.state.editor.innerText,'user new draft');assert.equal(f.presses(),3);
  cases++;
}

(async()=>{
  let f=setup({acceptImmediately:true});await f.run();assert.equal(f.presses(),1);
  assert.equal(Object.values(f.storage)[0].phase,'accepted');cases++;
  f=setup({acceptSecond:true});await f.run();assert.equal(f.presses(),2);
  assert.equal(Object.values(f.storage)[0].retry_count,1);
  assert(f.reports.some(x=>x.step==='gemini_text_send_retry_accepted'));cases++;
  f=setup();await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});assert.equal(f.presses(),2);
  await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});assert.equal(f.presses(),2);
  f.frontend.activeRunId='new-run';await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});
  assert.equal(f.presses(),2);assert.equal(f.frontend.geminiTextRetryGuard,null);cases++;
  for(const options of [{acceptAfterSleeps:44},{acceptAfterSleeps:240},{acceptOnRetryClaim:true},{acceptAtRetryPress:true}]){
    f=setup(options);await f.run();assert.equal(f.presses(),1);cases++;
  }
  let guardCase = 0;
  for(const change of [
    (f,c)=>{c.stopButtonVisible=()=>true;},
    (f,c)=>{c.userTurns=()=>[{innerText:'old'},{innerText:'unrelated question'}];},
    f=>{f.state.editor.innerText='';},
    f=>{f.state.editor.innerText='user edited';},
    (f,c)=>{c.activeRunId='other-run';},
    (f,c)=>{c.activeJobId='other-job';},
    (f,c)=>{c.location.href='https://gemini.google.com/app/other';},
    (f,c,images)=>{images.push({src:'new-image'});},
    (f,c,images,refs)=>{refs.push({src:'new-ref'});},
    (f,c,images,refs,answers)=>{answers[0].innerText='updated old answer';},
    f=>{Object.defineProperty(f.state.button,'disabled',{get:()=>true});},
    f=>{f.state.expansion={};},
    f=>{f.state.editor.closest=()=>({querySelectorAll:()=>[{}]});}
  ]){
    f=setup({afterFirstWait:change});await assert.rejects(f.run());assert.equal(f.presses(),1,`changed state ${guardCase}`);guardCase++;
    assert.equal(f.frontend.geminiTextRetryGuard,null);cases++;
  }
  for(const options of [{pressResponseLost:true},{releaseResponseLost:true}]){
    f=setup(options);await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});
    // Background safely releases even if the press ACK was lost. Only a
    // successfully attested release is eligible for the bounded second press.
    assert.equal(f.presses(),options.pressResponseLost?2:1);cases++;
  }
  for(const options of [{readFail:true},{writeFail:true},{badAck:true}]){
    f=setup(options);await assert.rejects(f.run());assert.equal(f.presses(),0);cases++;
  }
  for(const options of [{editAtRetryPress:true},{cancelAtRetryPress:true}]){
    f=setup(options);await assert.rejects(f.run());assert.equal(f.presses(),1);cases++;
  }
  // Exact same earlier request is not proof of a newly accepted request.
  f=setup();f.frontend.userTurns=()=>[{innerText:f.prompt}];
  await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});assert.equal(f.presses(),2);cases++;
  f=setup({responseOverride:{ok:false,dispatched:true,dispatchCompleted:false,
    method:'single_trusted_ai_send_unconfirmed',diagnostics:{gesture_phase:'pressed'}}});
  await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});assert.equal(f.sends(),1);cases++;
  f=setup({replaceClaimBeforePress:true});await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});
  assert.equal(f.presses(),0);cases++;
  f=setup();f.frontend.userTurns=()=>[{innerText:'old'},{innerText:f.prompt}];f.accept();
  await f.run();assert.equal(f.presses(),0);assert.equal(Object.values(f.storage)[0].phase,'accepted');cases++;
  f=setup({blocked:true});await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});
  assert.equal(f.presses(),0);cases++;
  // Five uploaded thumbnails belong to old user turns, not this composer.
  // Lazy history images and a toolbar repaint during debugger preparation
  // must not block the actual single Send.
  f=setup({acceptImmediately:true,beforePress:(_f,_c,rows)=>{
    rows.historyImages.push({src:'history-loaded-late'});
    rows.historyRefs[0].src='history-thumbnail-refreshed';
    rows.assistants[0].innerText='previous completed JSON toolbar changed';
  }});
  f.historyRefs.push(...Array.from({length:5},(_,i)=>({src:`old-upload-${i}`})));
  f.refs.push({src:'current-reference'});
  f.assistants[0].querySelector=()=>({textContent:'previous completed JSON'});
  assert.equal(f.frontend.geminiComposerAttachmentState().count,1);
  await f.run();assert.equal(f.presses(),1);cases++;
  // A real current attachment edit is still blocked before mousePressed,
  // with attested zero-click detail, not a made-up cancellation diagnosis.
  f=setup({beforePress:(_f,_c,rows)=>{rows.refs.push({src:'changed-current-reference'});}});
  await assert.rejects(f.run(),error=>{
    assert.equal(error.sendDiagnostics.gesture_phase,'not_started');
    assert.equal(error.sendDiagnostics.preflight_reason,'text_guard_changed');
    assert(error.sendDiagnostics.changed_fields.includes('sourceSignature'));
    return error.code==='GEMINI_TEXT_SEND_REVIEW';
  });
  assert.equal(f.presses(),0);assert.equal(Object.values(f.storage)[0].phase,'not_dispatched');cases++;
  f=setup();f.state.uploadBusy=true;
  await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'});assert.equal(f.presses(),0);cases++;
  for(const [label,change] of [
    ['draft edit',current=>{current.state.editor.innerText='changed before first press';}],
    ['upload busy',current=>{current.state.uploadBusy=true;}],
    ['upload failed',current=>{current.state.uploadStatus='Upload failed';}],
    ['response active',(_f,c)=>{c.stopButtonVisible=()=>true;}],
    ['cancelled',(_f,c)=>{c.cancelRequested=true;}]
  ]){
    f=setup({beforePress:change});await assert.rejects(f.run(),undefined,label);
    assert.equal(f.presses(),0,label);
    assert(Object.values(f.storage).every(row=>row.retry_count===0),label);
    assert.equal(f.frontend.geminiTextRetryGuard,null,label);cases++;
  }
  // Transient changes must stay latched even when the end-of-minute snapshot
  // again matches the original prompt, current reference and idle upload.
  const transientChanges=[
    ['draft',current=>{const saved=current.state.editor.innerText;current.state.editor.innerText='temporary user edit';return()=>{current.state.editor.innerText=saved;};}],
    ['reference',(_f,_c,rows)=>{rows.refs[0].src='temporary-reference';return()=>{rows.refs[0].src='current-reference';};}],
    ['upload busy',current=>{current.state.uploadBusy=true;return()=>{current.state.uploadBusy=false;};}],
    ['owner',(_f,c)=>{const saved=c.activeRunId;c.activeRunId='temporary-run';return()=>{c.activeRunId=saved;};}]
  ];
  for(const [label,change] of transientChanges){
    let restore;
    f=setup({onSleep:(current,c,rows)=>{
      if(current.state.sleeps===20)restore=change(current,c,rows);
      if(current.state.sleeps===21)restore();
    }});
    f.refs.push({src:'current-reference',complete:true,naturalWidth:572});
    await assert.rejects(f.run(),{code:'GEMINI_TEXT_SEND_REVIEW'},label);
    assert.equal(f.presses(),1,label);
    assert(Object.values(f.storage).every(row=>row.retry_count===0),label);
    assert.equal(f.state.sleeps,240,'still give late acceptance the full minute');cases++;
  }
  let restore;
  f=setup({onSleep:(current,c,rows)=>{
    if(current.state.sleeps===20)restore=transientChanges[0][1](current,c,rows);
    if(current.state.sleeps===21)restore();
    if(current.state.sleeps===80)current.accept();
  }});
  await f.run();assert.equal(f.presses(),1);
  assert.equal(Object.values(f.storage)[0].retry_count,0);
  assert.equal(Object.values(f.storage)[0].phase,'accepted');cases++;
  // Old history can finish loading during the minute without poisoning a
  // valid retry for the untouched current request.
  f=setup({acceptSecond:true,onSleep:(current,_c,rows)=>{
    if(current.state.sleeps===20){
      rows.historyImages.push({src:'history-loaded-late'});
      rows.historyRefs[0].src='history-thumbnail-refreshed';
      rows.assistants[0].innerText='older answer refreshed';
      rows.assistants.at(-1).innerText='latest answer toolbar refreshed';
    }
  }});
  f.historyRefs.push({src:'old-upload'});
  f.refs.push({src:'current-reference',complete:true,naturalWidth:572});
  f.assistants.unshift({innerText:'older answer'});
  f.assistants.at(-1).querySelector=()=>({textContent:'previous completed JSON'});
  await f.run();assert.equal(f.presses(),2);
  assert.equal(Object.values(f.storage)[0].retry_count,1);cases++;
  await twoPromptWorkflow();
  console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
