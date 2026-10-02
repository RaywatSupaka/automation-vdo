// Exercise the actual content-script preflight without sending to a provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const start = source.indexOf('  function retainedStoryReferenceReady(');
const end = source.indexOf('  function aiWebFailureDiagnostic()', start);
assert(start >= 0 && end > start);
const shellStart=source.indexOf('  function chatGPTComposerShell(');
const shellEnd=source.indexOf('  function chatGPTComposerAttachmentState(',shellStart);
assert(shellStart>=0 && shellEnd>shellStart);

async function scenario(name, changes, expected) {
  const state = {draft:'wrapped prompt',owner:true,request:'request_missing',count:1,busy:false,
    marker:true,...changes};
  const preview = {getAttribute: () => ''};
  const shell = {textContent:state.marker?'smartflow-story-previous-4.png':'other-file.png',
    querySelectorAll:()=>[],contains:()=>true};
  const editor = {closest:()=>state.noClosestForm?null:shell,contains:()=>false};
  const reports=[];
  const context=vm.createContext({IS_GEMINI:false,activeCoverRequest:null,activeSourceReferenceLimit:3,
    document:{querySelector:()=>shell},
    composer:()=>editor,composerText:()=>state.draft,stopButtonVisible:()=>false,
    chatGPTComposerAttachmentState:()=>({count:state.count,busy:state.busy,failed:false,nodes:[preview]}),
    sourceAttachmentPreviews:()=>state.count?[preview]:[],
    chatGPTStoryRequest:()=>({reason:state.request}),
    SmartFlowSingleAnswer:{wrap:()=> 'wrapped prompt'},
    report:async(...args)=>reports.push(args)});
  vm.runInContext(source.slice(shellStart,shellEnd)+source.slice(start,end),context);
  const owns=()=>state.owner;
  const ready=()=>context.retainedStoryReferenceReady('prompt','smartflow-story-previous-4',owns);
  assert.equal(ready(),expected,name);
  if(expected){
    await context.attachSourceImages(['saved-scene-4'],4,'smartflow-story-previous-4',ready);
    assert.equal(reports[0][0],'recovery_reference_reused',name);
  }else if(state.count){
    await assert.rejects(context.attachSourceImages(['saved-scene-4'],4,'smartflow-story-previous-4',ready),
      error=>error.code==='AI_IMAGE_REFERENCE_UNCONFIRMED',name);
  }
  process.stdout.write(`PASS ${name}\n`);
}

async function sendAuditScenario(count, shouldStop) {
  const a=source.indexOf('  async function recordStoryImageRequest(');
  const b=source.indexOf('  function geminiImageSendState()',a);
  assert(a>=0 && b>a);
  const shell={querySelectorAll:()=>[]};
  const editor={closest:()=>shell};
  const context=vm.createContext({IS_GEMINI:false,PROVIDER_KEY:'chatgpt',activeJobId:'STORY-TEST',
    activeRunId:'RUN-TEST',location:{href:'https://chatgpt.com/c/test'},
    aiWebFailureDiagnostic:()=>JSON.stringify({source_attachment_count:count,
      source_attachment_busy:false,source_attachment_failed:false,image_expansion_open:false,
      send_button_enabled:true}),composer:()=>editor,composerText:()=> 'prompt',visible:()=>true,
    chrome:{runtime:{sendMessage:async()=>({ok:true})}},assertNotCancelled:()=>{}});
  vm.runInContext(source.slice(a,b),context);
  const operation=context.recordStoryImageRequest('prompt',['saved-scene-4'],{scene_index:5,attempt:1},4);
  if(shouldStop)await assert.rejects(operation,error=>error.code==='STORY_IMAGE_CONTEXT_CONFLICT');
  else await operation;
  process.stdout.write(`PASS ${count} reference attachment(s) ${shouldStop?'stop':'ready'} before Send\n`);
}

(async()=>{
  await scenario('same prepared scene and exact draft reuse one retained reference',{},true);
  await scenario('same full prompt with ChatGPT newline normalization reuses reference',{draft:'wrapped\n prompt'},true);
  await scenario('unified composer form owns retained reference without a closest form',{noClosestForm:true},true);
  await scenario('changed draft cannot inherit old image',{draft:'different'},false);
  await scenario('changed receipt owner cannot inherit old image',{owner:false},false);
  await scenario('missing source filename cannot inherit old image',{marker:false},false);
  await scenario('already sent request cannot replay',{request:'request_found'},false);
  await scenario('multiple previews cannot inherit old image',{count:2},false);
  await scenario('upload in progress cannot inherit old image',{busy:true},false);
  await sendAuditScenario(1,false);
  await sendAuditScenario(2,true);
})().catch(error=>{console.error(error);process.exitCode=1;});
