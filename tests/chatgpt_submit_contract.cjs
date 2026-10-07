// Offline submit-contract discriminators, not evidence of the live provider cause.
// Real production content readiness/acceptance + MAIN resolver, native mouse input.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.SMARTFLOW_TEST_PLAYWRIGHT_PACKAGE || 'playwright');
const ROOT = path.resolve(__dirname, '..');
const baseline = process.argv.includes('--baseline');
const runtimeFolder = baseline ? path.join(ROOT, '..', 'before-runtime') : path.join(ROOT, 'browser_extension');
const content = fs.readFileSync(path.join(runtimeFolder, 'chatgpt.js'), 'utf8');
const background = fs.readFileSync(path.join(runtimeFolder, 'background.js'), 'utf8');
const section = (source, startMarker, endMarker) => {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start + startMarker.length);
  assert(start >= 0 && end > start, 'Production extraction markers exist: ' + startMarker);
  return source.slice(start,end);
};
const targetMarker = '  function resolveChatGPTComposerSendTarget(editor) {';
const targetResolver = content.includes(targetMarker)
  ? section(content,targetMarker,'\n  function sendButton()') : '';
const production = fs.readFileSync(path.join(ROOT,'browser_extension','single_answer.js'),'utf8')
  + section(content,'  function visible(element) {','  const dismissedDiscoveryCards')
  + section(content,'  function composer() {','  function loginRequired()')
  + section(content,'  function composerText(','  function explicitAnalysisRefusal(')
  + section(content,'  function isStopGenerationButton(','  function imageGenerationSignature(')
  + targetResolver
  + section(content,'  function sendButton() {','  function motionRequestIsLatestUser(')
  + section(content,'  function chatGPTConversationFrames(','  async function revealChatGPTAnswer(')
  + section(content,'  function motionRequestIsLatestUser(','  function geminiStoryImageSnapshot(')
  + section(content,'  function chatGPTKnownRenderedRequestMatches(','  function chatGPTMotionRequestText(')
  + section(content,'  function storyTurnNumber(','  function chatGPTStoryImageSnapshot(')
  + section(content,'  function storyImageRecoveryError(','  async function readStoryImageCheckpoint(')
  + section(content,'  async function sendAndVerify(','  async function ensureAiWebModel(')
  + '\n' + section(background,'const resolveAiSendPrepressPoint = (','const readInitialSendPoint =')
  + '\nwindow.__fixtureBackgroundPoint = resolveAiSendPrepressPoint;';

const URL = 'https://chatgpt.com/c/offline-submit-contract';
const CANONICAL = 'Synthetic offline contract request. Return one small JSON object.';
const HTML = `<!doctype html><meta charset="utf-8"><title>Offline submit contract</title>
<style>*{box-sizing:border-box}body{margin:0;min-height:900px}form{margin:0}
 textarea{position:fixed;left:20px;top:650px;width:260px;height:100px}
 #owned-send{position:fixed;left:312px;top:690px;width:64px;height:48px;padding:0;border:0}
 button svg{width:24px;height:24px}#foreign{position:fixed;left:20px;top:20px}
 #other-submit,#disabled-first,#stop{position:fixed;left:20px;top:100px;width:64px;height:48px}
</style><main></main><form id="owned-form"><textarea id="prompt-textarea"></textarea>
<button id="owned-send" type="submit" aria-label="ส่ง"><svg aria-hidden="true" viewBox="0 0 24 24"><rect width="24" height="24" fill="black"/></svg></button></form>`;
let checks = 0, dispatches = 0, formSubmits = 0, acceptedRequests = 0;
function equal(actual,expected,label) {checks++;assert.equal(actual,expected,label);}
function truth(value,label) {checks++;assert(value,label);}
const point = (page,{initial=false,focus=false,key=''}={}) => page.evaluate(
  ({initial,focus,key}) => __fixtureBackgroundPoint(__fixtureWire,initial,focus,key,true),{initial,focus,key});

async function setup(page,variant='thai') {
  await page.goto(URL);
  await page.addScriptTag({content:production});
  await page.evaluate(({canonical,variant}) => {
    Object.assign(globalThis,{IS_GEMINI:false,PROVIDER_KEY:'chatgpt',AI_NAME:'ChatGPT',
      activeJobId:'OFFLINE-CONTRACT',activeRunId:'OFFLINE-RUN'});
    window.__fixtureWire=SmartFlowSingleAnswer.wrap(canonical);
    const editor=document.querySelector('#prompt-textarea'), button=document.querySelector('#owned-send');
    editor.value=__fixtureWire;
    if (['bare','class','title','aria_substring','unowned_bare','feedback_type_button','visible_text_conflicting'].includes(variant))button.removeAttribute('aria-label');
    if (variant==='class')button.className='send-button';
    if (variant==='title')button.title='Send';
    if (variant==='aria_substring')button.setAttribute('aria-label','Send this request');
    if (variant==='feedback_type_button') {button.type='button';button.title='Submit feedback';}
    if (variant==='conflicting_submit')button.setAttribute('aria-label','Delete chat');
    if (variant==='visible_text_conflicting')button.innerText='Delete chat';
    if (variant==='aria_disabled_duplicate') {
      const first=button.cloneNode(true);first.id='disabled-first';first.setAttribute('aria-disabled','true');
      document.querySelector('#owned-form').insertBefore(first,editor);
    }
    if (variant==='foreign_decoy') {
      const foreign=document.createElement('form');foreign.id='foreign-form';
      foreign.innerHTML='<button id="foreign" type="submit" aria-label="ส่ง">Foreign form</button>';
      document.body.prepend(foreign);
    }
    if (variant==='foreign_reassociated') {
      const foreign=document.createElement('form');foreign.id='foreign-form';
      document.body.prepend(foreign);button.setAttribute('form','foreign-form');
    }
    if (variant==='ambiguous_owned') {
      const other=button.cloneNode(true);other.id='other-submit';
      document.querySelector('#owned-form').append(other);
    }
    if (variant==='stop' || variant==='disabled_stop') {
      const stop=document.createElement('button');stop.id='stop';stop.type='button';
      stop.setAttribute('data-testid','stop-button');stop.setAttribute('aria-label','Stop generating');
      if (variant==='disabled_stop')stop.disabled=true;
      document.querySelector('#owned-form').prepend(stop);
    }
    if (variant==='unowned_bare') {
      const form=document.querySelector('#owned-form');form.replaceWith(...form.childNodes);
    }
    window.__fixtureEvents=[];window.__fixtureSubmits=[];window.__fixtureReports=[];
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      document.addEventListener(type,event => __fixtureEvents.push({type,trusted:event.isTrusted,
        target:event.target.closest?.('button')?.id||''}),true);
    }
    document.addEventListener('submit',event => {
      event.preventDefault();
      const submitted=editor.value;
      __fixtureSubmits.push({trusted:event.isTrusted,form:event.target.id,
        submitter:event.submitter?.id||'',exactWire:submitted===__fixtureWire});
      if (event.target.id!=='owned-form' || event.submitter?.id!=='owned-send')return;
      const frame=document.createElement('article');frame.dataset.testid='conversation-turn-1';
      frame.innerHTML='<div data-message-author-role="user" data-message-id="offline-message-1"><div class="whitespace-pre-wrap"></div></div>';
      frame.firstChild.firstChild.textContent=submitted;document.querySelector('main').append(frame);
      editor.value='';
    },true);
    globalThis.assertNotCancelled=()=>{};
    globalThis.sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    globalThis.report=async(step,_message,_count,extra)=>__fixtureReports.push({step,...extra});
    globalThis.chrome={runtime:{sendMessage:message=>__fixtureTrustedSend(message)}};
  },{canonical:CANONICAL,variant});
}

async function selection(page) {
  return page.evaluate(() => {
    const editor=composer(), selected=sendButton();
    const target=typeof resolveChatGPTComposerSendTarget==='function'
      ? resolveChatGPTComposerSendTarget(editor) : null;
    return {editor:editor?.id||'',button:selected?.id||'',
      reason:target?.reason||'',method:target?.method||'',form:target?.form?.id||''};
  });
}

async function selectedOwned(page,variant) {
  await setup(page,variant);
  const selected=await selection(page);
  equal(selected.editor,'prompt-textarea',variant+' reads actual composer');
  equal(selected.button,'owned-send',variant+' content selects unique owned button');
  // Exercise the actual content stable-draft wait, rather than replacing it.
  const stable=await page.evaluate(async expected=> {
    const result=await waitForStableSendDraft(expected,1500,false);
    return {editor:result.editor.id,button:result.button.id};
  },CANONICAL);
  equal(stable.button,'owned-send',variant+' content readiness keeps owned button');
  const initial=await point(page,{initial:true,focus:true});
  equal(initial.ok,true,variant+' background resolves: '+JSON.stringify(initial));
  truth(await page.evaluate(({x,y})=> {
    const hit=document.elementFromPoint(x,y),button=document.querySelector('#owned-send');
    return hit===button||button.contains(hit);
  },initial),variant+' background point hits same owned button/child');
  return initial;
}

async function rejection(page,variant,reason) {
  await setup(page,variant);
  equal((await selection(page)).button,'',variant+' content rejects unsafe selection');
  const initial=await point(page,{initial:true,focus:true});
  equal(initial.ok,false,variant+' background rejects unsafe selection');
  if (!baseline)equal(initial.reason,reason,variant+' reports bounded reason');
  equal(await page.evaluate(()=>__fixtureEvents.length),0,variant+' performs no input');
}

async function nativeAcceptance(page,variant) {
  await selectedOwned(page,variant);
  const beforeDispatches=dispatches;
  const result=await page.evaluate(async()=> {
    let error='';
    try {await sendAndVerify(sendButton(),composer(),userTurns().length,lastUserTurnSignature(),assistantTurns().length);}
    catch(caught) {error=caught.code||caught.message;}
    return {error,submits:__fixtureSubmits,reports:__fixtureReports,
      events:__fixtureEvents,promptCleared:composerText(composer())==='',
      exactAccepted:document.querySelector('[data-message-id="offline-message-1"]')?.textContent===__fixtureWire,
      acceptedTurnCount:document.querySelectorAll('[data-message-author-role="user"]').length};
  });
  equal(result.error,'',variant+' real production sendAndVerify accepts');
  equal(dispatches-beforeDispatches,1,variant+' dispatches one gesture');
  equal(result.submits.length,1,variant+' native input causes one local FORM submit');
  truth(result.submits[0].trusted,variant+' FORM submit is trusted');
  equal(result.submits[0].form,'owned-form',variant+' submits owned form');
  equal(result.submits[0].submitter,'owned-send',variant+' submits correct button');
  truth(result.submits[0].exactWire && result.exactAccepted,variant+' exact full wire request accepted');
  equal(result.acceptedTurnCount,1,variant+' commits one synthetic user turn');
  truth(result.promptCleared,variant+' live composer clears after submit');
  equal(result.events.filter(event=>event.type==='mousedown').length,1,variant+' has one native press');
  equal(result.events.filter(event=>event.type==='mouseup').length,1,variant+' has one native release');
  equal(result.events.filter(event=>event.type==='click').length,1,variant+' has one native click');
  truth(result.events.every(event=>event.trusted && event.target==='owned-send'),variant+' no synthetic/wrong-target input');
  equal(result.reports.filter(report=>report.step==='ai_send_accepted').length,1,variant+' production reports one acceptance');
  equal(result.reports.find(report=>report.step==='ai_send_accepted')?.submission_proof,'owned_chatgpt_user_turn',
    variant+' production proves exact owned user turn');
  formSubmits+=result.submits.length;acceptedRequests++;
}

async function relationshipChanged(page,which) {
  await setup(page);
  const initial=await point(page,{initial:true,focus:true});
  equal(initial.ok,true,which+' initial point exists');
  const previous=await page.evaluate(()=> {
    const r=document.querySelector('#owned-send').getBoundingClientRect();return [r.left,r.top,r.width,r.height];
  });
  await page.evaluate(which=> {
    const editor=document.querySelector('#prompt-textarea'),button=document.querySelector('#owned-send');
    if (which==='editor_changed') {const fresh=editor.cloneNode(true);fresh.value=editor.value;editor.replaceWith(fresh);}
    else {const old=document.querySelector('#owned-form'),fresh=document.createElement('form');fresh.id='owned-form';
      fresh.append(...old.childNodes);old.replaceWith(fresh);button.focus({preventScroll:true});}
  },which);
  equal(JSON.stringify(await page.evaluate(()=> {
    const r=document.querySelector('#owned-send').getBoundingClientRect();return [r.left,r.top,r.width,r.height];
  })),JSON.stringify(previous),which+' mutation preserves button geometry');
  const armed=await point(page,{key:initial.key});
  equal(armed.ok,false,which+' same geometry cannot arm changed relationship');
  if (!baseline)equal(armed.reason,'composer_form_changed',which+' reports relationship fence');
  equal(await page.evaluate(()=>__fixtureEvents.length),0,which+' never dispatches input');
}

const cases=[
  ['thai_submit_native_acceptance',page=>nativeAcceptance(page,'thai')],
  ['bare_owned_submit_native_acceptance',page=>nativeAcceptance(page,'bare')],
  ['inline_image_tool_keeps_exact_wire_draft',async page=>{
    await setup(page);
    await page.evaluate(()=>{
      const old=document.querySelector('#prompt-textarea');
      const editor=document.createElement('div');
      editor.id='prompt-textarea';editor.contentEditable='true';
      editor.style.cssText='position:fixed;left:20px;top:650px;width:260px;min-height:100px;max-height:100px;overflow:hidden';
      editor.textContent=__fixtureWire;
      const chip=document.createElement('span');chip.contentEditable='false';chip.textContent='สร้างรูปภาพ';
      editor.append(chip);old.replaceWith(editor);
    });
    const initial=await point(page,{initial:true,focus:true});
    equal(initial.ok,true,'inline image token after transport suffix leaves exact wire draft ready');
    await page.evaluate(()=>{
      const editor=document.querySelector('#prompt-textarea');
      editor.firstChild.nodeValue='Synthetic offline contract request. Return one small JSON object.';
    });
    const missing=await point(page,{initial:true,focus:true});
    equal(missing.ok,false,'missing transport suffix still blocks Background Send');
    equal(missing.reason,'draft_mismatch','missing suffix reports draft mismatch');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'no input on either preflight');
  }],
  ['class_submit',page=>selectedOwned(page,'class')],
  ['title_submit',page=>selectedOwned(page,'title')],
  ['aria_substring_submit',page=>selectedOwned(page,'aria_substring')],
  ['aria_disabled_earlier_duplicate',page=>selectedOwned(page,'aria_disabled_duplicate')],
  ['foreign_form_decoy',page=>selectedOwned(page,'foreign_decoy')],
  ['foreign_reassociated',async page=> {
    await setup(page,'foreign_reassociated');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').closest('form').id),'owned-form',
      'Reassociated labeled Send is a DOM descendant of owned form');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').form.id),'foreign-form',
      'Native form relationship points to different external form');
    equal((await selection(page)).button,'','Reassociated native foreign submit is not selected by content');
    const initial=await point(page,{initial:true,focus:true});
    equal(initial.ok,false,'Reassociated native foreign submit is rejected by background');
    if (!baseline)equal(initial.reason,'send_not_ready','Native ownership mismatch has bounded rejection');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Reassociated button causes zero native gestures');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Reassociated button causes zero form submissions');
  }],
  ['ambiguous_owned_submit_reject',page=>rejection(page,'ambiguous_owned','send_target_ambiguous')],
  ['stop_reject',page=>rejection(page,'stop','response_active')],
  ['rendered_disabled_stop_reject',page=>rejection(page,'disabled_stop','response_active')],
  ['feedback_type_button_reject',async page=> {
    await setup(page,'feedback_type_button');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').type),'button','Feedback is not native submit');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').title),'Submit feedback','Feedback title is not exact Send');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').form.id),'owned-form','Feedback is in owned composer form');
    equal((await selection(page)).button,'','Feedback control never receives Send authority');
    const initial=await point(page,{initial:true,focus:true});
    equal(initial.ok,false,'Background rejects feedback type=button');
    if (!baseline)equal(initial.reason,'send_not_ready','Feedback rejection has bounded reason');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Feedback has zero native gestures');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Feedback has zero form submissions');
  }],
  ['explicit_conflicting_submit_reject',async page=> {
    await setup(page,'conflicting_submit');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').type),'submit','Conflicting control is native submit');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').getAttribute('aria-label')),'Delete chat',
      'Conflicting submit has explicit non-Send semantics');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').form.id),'owned-form','Conflicting submit belongs to owned form');
    equal((await selection(page)).button,'','Explicit non-Send action never receives fallback authority');
    const initial=await point(page,{initial:true,focus:true});
    equal(initial.ok,false,'Background rejects explicit conflicting action');
    if (!baseline)equal(initial.reason,'send_not_ready','Conflicting action has bounded rejection');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Conflicting action has zero native gestures');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Conflicting action has zero form submissions');
  }],
  ['content_timeout_keeps_typed_target_reason',async page=> {
    await setup(page,'ambiguous_owned');
    const result=await page.evaluate(async expected=> {
      const nativeNow=Date.now,nativeSleep=globalThis.sleep;let elapsed=0;
      Date.now=()=>elapsed;globalThis.sleep=async ms=>{elapsed+=ms;};
      try {await waitForStableSendDraft(expected,1000,false);return {unexpectedReady:true};}
      catch(error) {return {code:error.code,notDispatched:error.notDispatched,
        diagnostics:error.sendDiagnostics,elapsed};}
      finally {Date.now=nativeNow;globalThis.sleep=nativeSleep;}
    },CANONICAL);
    equal(result.code,'AI_SEND_NOT_READY','Content timeout keeps established error code');
    equal(result.notDispatched,true,'Content timeout attests no Send');
    equal(result.diagnostics?.gesture_phase,'not_started','Content timeout has typed not-started phase');
    equal(result.diagnostics?.dispatch_completed,false,'Content timeout cannot claim completed dispatch');
    equal(result.diagnostics?.preflight_reason,'send_target_ambiguous','Content timeout preserves exact target veto');
    truth(Number.isFinite(result.elapsed) && result.elapsed<=1250,'Actual passive wait remains bounded with synthetic clock');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Content timeout dispatches no input');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Content timeout submits no form');
  }],
  ['visible_text_conflicting_submit',async page=> {
    await setup(page,'visible_text_conflicting');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').type),'submit','Visible conflicting control is native submit');
    truth(await page.evaluate(()=> {
      const button=document.querySelector('#owned-send');
      return !button.hasAttribute('aria-label')&&!button.hasAttribute('title');
    }),'Visible conflict has no aria/title labels');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').innerText.trim()),'Delete chat',
      'Native rendered button text explicitly says Delete chat');
    equal(await page.evaluate(()=>document.querySelector('#owned-send').form.id),'owned-form','Visible conflicting submit belongs to owned form');
    equal((await selection(page)).button,'','Visible non-Send action is not an unlabeled fallback');
    const initial=await point(page,{initial:true,focus:true});
    equal(initial.ok,false,'Background rejects visible conflicting native submit');
    if (!baseline)equal(initial.reason,'send_not_ready','Visible conflict has bounded rejection');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Visible conflict has zero native gestures');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Visible conflict has zero form submissions');
  }],
  ['story_timeout_preserves_typed_target_reason',async page=> {
    await setup(page,'ambiguous_owned');
    const result=await page.evaluate(async()=> {
      const nativeNow=Date.now,nativeSleep=globalThis.sleep;let elapsed=0;
      Date.now=()=>elapsed;globalThis.sleep=async ms=>{elapsed+=ms;};
      try {
        await sendAndVerify(sendButton(),composer(),userTurns().length,lastUserTurnSignature(),assistantTurns().length,
          false,{scene_index:1});
        return {unexpectedReady:true};
      } catch(error) {return {code:error.code,notDispatched:error.notDispatched,
        diagnostics:error.sendDiagnostics,elapsed};}
      finally {Date.now=nativeNow;globalThis.sleep=nativeSleep;}
    });
    equal(result.code,'STORY_IMAGE_RECEIPT_REVIEW','Actual Story wrapper keeps established review code');
    equal(result.notDispatched,true,'Actual Story timeout preserves no-Send attestation');
    equal(result.diagnostics?.gesture_phase,'not_started','Story wrapper preserves typed not-started phase');
    equal(result.diagnostics?.dispatch_completed,false,'Story timeout cannot claim completed dispatch');
    equal(result.diagnostics?.preflight_reason,'send_target_ambiguous','Story wrapper preserves exact target veto');
    truth(Number.isFinite(result.elapsed)&&result.elapsed<=12250,'Actual Story passive waiter remains bounded with synthetic clock');
    equal(await page.evaluate(()=>__fixtureEvents.length),0,'Story timeout dispatches no input');
    equal(await page.evaluate(()=>__fixtureSubmits.length),0,'Story timeout submits no form');
    equal(await page.evaluate(()=>userTurns().length),0,'Story timeout creates no accepted user turn');
  }],
  ['unowned_bare_submit_reject',page=>rejection(page,'unowned_bare','send_not_ready')],
  ['form_changed_before_arm',page=>relationshipChanged(page,'form_changed')],
  ['editor_changed_before_arm',page=>relationshipChanged(page,'editor_changed')],
];

(async()=> {
  const requested=process.argv.find(arg=>arg.startsWith('--case='))?.slice(7);
  const names=requested?requested.split(','):null;
  const selected=names?cases.filter(([name])=>names.includes(name)):cases;
  assert(selected.length && (!names || selected.length===names.length),'Requested fixture exists');
  const browser=await chromium.launch({headless:true,
    ...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  const violations=[];let fulfilledDocuments=0,blockedRequests=0,passed=0;
  try {
    const context=await browser.newContext({viewport:{width:400,height:850},serviceWorkers:'block'});
    await context.route('**/*',route=> {
      if (route.request().isNavigationRequest()&&route.request().url()===URL) {
        fulfilledDocuments++;return route.fulfill({contentType:'text/html; charset=utf-8',body:HTML});
      }
      blockedRequests++;return route.abort();
    });
    const page=await context.newPage();
    await page.exposeFunction('__fixtureTrustedSend',async message=> {
      equal(message.type,'CLICK_AI_SEND_BUTTON','Actual content requests trusted Send');
      equal(message.expectedPrompt,CANONICAL,'Actual content carries canonical synthetic request');
      let current=await point(page,{initial:true,focus:true});
      if(!current.ok)return {ok:false,error:current.error,notDispatched:true,
        diagnostics:{gesture_phase:'not_started',preflight_reason:current.reason}};
      await page.mouse.move(current.x,current.y);
      current=await point(page,{focus:true});
      const armed=await point(page,{key:current.key});
      if(!armed.ok)return {ok:false,error:armed.error,notDispatched:true,
        diagnostics:{gesture_phase:'not_started',preflight_reason:armed.reason}};
      dispatches++;
      await page.mouse.down();await page.mouse.up();
      const capture=await page.evaluate(()=> {
        const gesture=window.__smartflowAiSendGestureV3;gesture.armed=false;
        return {ok:gesture.trustedClickSeen===true,clickEvents:gesture.events,
          diagnostics:{gesture_phase:'released',release_on_send_target:gesture.releaseOnSendTarget,
            send_target_strategy:gesture.pointStrategy}};
      });
      return {...capture,dispatched:true,dispatchCompleted:true,
        method:capture.ok?'single_trusted_ai_send':'single_trusted_ai_send_unconfirmed'};
    });
    for(const [name,run]of selected) {
      try {await run(page);passed++;}
      catch(error) {violations.push({scenario:name,assertion:error.message});}
    }
    equal(blockedRequests,0,'No external resource requests');
  } finally {await browser.close();}
  const proof={ok:violations.length===0,nativeDom:true,baselineRegression:baseline,
    scenarios:selected.length,passed,checks,violations,fulfilledDocuments,blockedRequests,
    nativeGestures:dispatches,nativeFormSubmits:formSubmits,exactAcceptedRequests:acceptedRequests,
    providerNetworkRequests:0,providerActions:0,ownedBrowserClosed:true};
  console.log(JSON.stringify(proof));
  if(violations.length)process.exitCode=1;
})().catch(error=> {console.error(error);process.exitCode=1;});
