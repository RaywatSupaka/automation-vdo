// Actual cancellation handler/checks and runner lifecycles, isolated from Chrome.
// A retired reader must exit without stopping generation in its old conversation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(start,end)=>{
  const first=source.indexOf(start),last=source.indexOf(end,first+start.length);
  assert(first>=0&&last>first,'missing actual-source region: '+start);
  return source.slice(first,last);
};
let cases=0;
const check=(actual,expected,label)=>{assert.deepEqual(actual,expected,label);cases++;};
function fixture(){
  let stops=0,hasStop=true,coverCancels=null,helperStarted=null;
  const responses=[],events=[];
  const stop={click:()=>stops++};
  const startupError=Object.assign(Error('source-only startup probe'),{code:'PROBE_STARTUP'});
  let startupState=null;
  const context=vm.createContext({
    IS_GEMINI:false,AI_NAME:'ChatGPT Web',PROVIDER_KEY:'chatgpt',
    stopButton:()=>hasStop?stop:null,analysisResponseStopButton:()=>hasStop?stop:null,
    loginRequired:()=>false,sendResponse:value=>responses.push(value),
    location:{href:'https://chatgpt.com/c/fixture'},aiWebFailureDiagnostic:()=>'',
    report:async(...args)=>events.push(args),coverEvent:async event=>events.push(event),
    userTurns:()=>[],composer:()=>({}),composerText:()=>'',
    ensureAiWebModel:async()=>{startupState=context.state();throw startupError;},
    collectCoverImage:async()=>{context.cancel(coverCancels);context.assertNotCancelled();},
    runMetaRedesignHelper:async()=>{helperStarted=context.state();},
    chrome:{storage:{local:{get:async()=>({}),set:async()=>{}}}}
  });
  vm.runInContext(part('  let activeJobId = "";','  let activeSourceReferenceLimit =')
    +part('  function assertNotCancelled() {','  async function setComposerText(')
    +'function cancel(message){'+part('    if (message?.type === "CANCEL_CHATGPT_JOB") {',
      '    if (message?.type === \'SMARTFLOW_STORY_COLLECTOR_PING\') {')+'}'
    +part('  async function runJob(pkg) {','  async function resumeStoryVisualPlan(')
    +part('  async function runAICover(request) {','  function alternativeImageReply(')
    +part('  async function runSceneRepairHelper(key, recover, preparedRecord = null) {',
      '  async function generateStoryImageWithRepair(')
    +'function state(){return {cancelRequested,stopProviderOnCancel,activeJobId,activeRunId};}'
    +'function own(job="STORY-FIXTURE",run="RUN-FIXTURE"){activeJobId=job;activeRunId=run;}'
    +'function releaseOwner(){activeJobId="";activeRunId="";}',context);
  return {c:context,responses,events,get stops(){return stops;},setHasStop:value=>hasStop=value,
    setCoverCancel:value=>{coverCancels=value;context.ensureAiWebModel=async()=>{};},get startupState(){return startupState;},
    get helperStarted(){return helperStarted;},startupError};
}
const abortCheck=f=>{
  assert.throws(()=>f.c.assertNotCancelled(),error=>error.name==='AbortError');cases++;
};
(async()=>{
  let f=fixture();f.c.own();
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE',retire_only:true});
  check(f.stops,0,'retirement handler never presses provider Stop');
  check(f.c.state().cancelRequested,true,'retirement still cancels the local collector');
  abortCheck(f);abortCheck(f);
  check(f.stops,0,'subsequent collector cancellation checks never Stop retired work');
  check(f.responses[0].cancelled,true,'retirement still acknowledges cancellation');

  f=fixture();f.c.own();f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE'});
  check(f.stops,1,'ordinary user cancellation retains immediate provider Stop');
  abortCheck(f);
  check(f.stops,2,'ordinary cancellation check retains provider Stop behavior');

  f=fixture();f.c.own();
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'ANOTHER-JOB',retire_only:true});
  f.c.assertNotCancelled();
  check(f.c.state().cancelRequested,false,'foreign retirement cannot cancel this owner');
  check(f.stops,0,'foreign retirement does not Stop');
  check(f.responses[0].cancelled,false,'foreign retirement is acknowledged as ignored');

  f=fixture();f.c.own();
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE',retire_only:true});
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE'});
  abortCheck(f);
  check(f.stops,2,'explicit cancellation after retirement restores Stop authority');

  f=fixture();f.c.own();f.setHasStop(false);
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE'});abortCheck(f);
  check(f.stops,0,'missing Stop does not prevent local cancellation');

  f=fixture();f.c.own();
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE',retire_only:true});
  f.c.releaseOwner();
  await assert.rejects(f.c.runJob({job:{id:'STORY-NEXT'},run_id:'RUN-NEXT',prompt:'fixture'}),
    error=>error===f.startupError);cases++;
  check(f.startupState.cancelRequested,false,'new main runner resets prior cancellation');
  check(f.startupState.stopProviderOnCancel,true,'new main runner restores user Stop authority');
  check(f.c.state().stopProviderOnCancel,true,'main runner cleanup clears retirement state');
  check(f.stops,0,'main lifecycle reset itself never Stop');

  for(const retireOnly of [true,false]){
    f=fixture();
    f.setCoverCancel({type:'CANCEL_CHATGPT_JOB',job_id:'COVER-fixture',retire_only:retireOnly});
    await f.c.runAICover({request_id:'fixture'});
    check(f.stops,retireOnly?0:3,'cover cancellation and catch preserve '+(retireOnly?'retired provider':'explicit user Stop'));
    check(f.c.state().cancelRequested,false,'cover cleanup resets local cancellation');
    check(f.c.state().stopProviderOnCancel,true,'cover cleanup resets retirement');
  }

  f=fixture();f.c.own();
  f.c.cancel({type:'CANCEL_CHATGPT_JOB',job_id:'STORY-FIXTURE',retire_only:true});
  f.c.releaseOwner();
  await f.c.runSceneRepairHelper('fixture-key',false,{phase:'rewrite_sent',provider:'chatgpt',
    job_id:'STORY-NEXT',run_id:'RUN-NEXT',request_id:'helper-fixture',scope:'meta'});
  check(f.helperStarted.cancelRequested,false,'new helper resets local cancellation');
  check(f.helperStarted.stopProviderOnCancel,true,'new helper restores explicit Stop authority');
  check(f.c.state().stopProviderOnCancel,true,'helper cleanup clears retirement');
  check(f.stops,0,'helper lifecycle reset never Stop');

  console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
