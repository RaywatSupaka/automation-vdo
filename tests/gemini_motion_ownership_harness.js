const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)+a.length));
const helper=part('  function motionRequestIsLatestUser(', '  async function sendAndVerify(');
const request='เขียน motion JSON '+JSON.stringify({job_id:'JOB-X',index:2,context_id:'scene-two'});
const oldRequest=request.replace('"index":2','"index":1').replace('scene-two','scene-one');
let cases=0;
function acceptance({acceptedAt=Infinity,cleared=false,strict=true}={}) {
  let ticks=0,sends=0;const reports=[];const editor={innerText:request};
  const c={AI_NAME:'Gemini Web',PROVIDER_KEY:'gemini',activeJobId:'JOB-X',activeRunId:'RUN-X',
    location:{href:'https://gemini.google.com/app/0123456789abcdef'},
    userTurns:()=>[{innerText:ticks>=acceptedAt?'คุณบอกว่า\n'+request:oldRequest}],
    lastUserTurnSignature:()=>ticks>=acceptedAt?'new':'old',assistantTurns:()=>Array(9),
    composer:()=>editor,composerText:()=>cleared?'':request,
    stopButtonVisible:()=>true,waitForStableSendDraft:async()=>({button:{},editor}),
    assertNotCancelled:()=>{},report:async(...a)=>reports.push(a),sleep:async()=>{ticks++;},
    chrome:{runtime:{sendMessage:async message=>{if(message.type==='MEMBERSHIP_AUTHORIZE')return {ok:true};sends++;return {ok:true,method:'single_trusted_ai_send'};}}}};
  // Keep initial expected draft nonempty, then simulate a cleared composer if needed.
  let reads=0;c.composerText=(_node,raw)=>raw?editor.innerText:(ticks>=acceptedAt || cleared&&reads++>0?'':request);
  vm.createContext(c);
  vm.runInContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),c);
  c.HTMLTextAreaElement=class{};editor.innerText=c.SmartFlowSingleAnswer.wrap(request);
  vm.runInContext(helper+part('  async function sendAndVerify(', '  async function ensureAiWebModel('),c);
  return {run:()=>c.sendAndVerify({},editor,1,'old',1,strict),reports,sends:()=>sends,ticks:()=>ticks};
}
function response({ownedAt=5000,answerAt=6000,strict=true,gemini=true,noAfter=false,cancel=false}={}) {
  let clock=100,sends=0;const old={innerText:'old scene-one answer'},fresh={innerText:'new scene-two answer'};
  const c={IS_GEMINI:gemini,activeRepairKey:'',activeCoverRequest:null,conversationPendingText:'',conversationPendingReferences:[],AI_NAME:gemini?'Gemini Web':'ChatGPT Web',Date:{now:()=>clock},
    chrome:{runtime:{sendMessage:async message=>{assert.equal(message.type,'MEMBERSHIP_AUTHORIZE');return {ok:true};}}},
    location:{href:'https://gemini.google.com/app/motion-fixture'},
    composer:()=>({innerText:''}),composerText:()=>'',
    waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>{},waitForComposer:async()=>({}),attachSourceImages:async()=>{},setComposerText:async()=>({}),
    assistantTurns:()=>Array(9).fill(clock>=answerAt?fresh:old),
    userTurns:()=>[{innerText:clock>=ownedAt?'คุณบอกว่า\n'+request:oldRequest,
      compareDocumentPosition:answer=>!noAfter&&answer===fresh?4:2}],lastUserTurnSignature:()=>'',
    sendButton:()=>({}),sendAndVerify:async(...a)=>{sends++;assert.equal(a[5],false);},
    assertGeminiTextSendAvailable:async()=>{},sendGeminiTextAndVerify:async()=>{sends++;},
    latestAssistantStrictlyAfterLatestUser:()=>noAfter?null:(clock>=answerAt?fresh:old),
    analysisAnswerNode:x=>x,analysisResponseStopButton:()=>null,analysisStopLabel:()=>'',analysisContentHash:x=>x,
    explicitAnalysisRefusal:()=>false,explicitImageFailure:()=>false,report:async()=>{},sleep:async(ms)=>{clock+=ms;},
    assertNotCancelled:()=>{if(cancel&&clock>2000)throw Error('cancelled');}};
  c.revealChatGPTAnswer=async()=>false; // ChatGPT-only helper does not operate Gemini.
  vm.createContext(c);vm.runInContext(helper
    +part('  function confirmedAnalysisTechnicalFailure(', '  function composerText(')
    +part('  function confirmedStoryImageServiceError(', '  function storyImageNoResultReady(')
    +part('  async function submitPrompt(', '  function analysisAnswerNode('),c);
  return {run:()=>c.submitPrompt(request,[],strict?'smartflow-motion-fixture':''),clock:()=>clock,sends:()=>sends};
}
(async()=>{
  for(const cleared of [false,true]) {
    const f=acceptance({cleared});await assert.rejects(f.run(),/60/);assert.equal(f.sends(),1);
    assert(!f.reports.some(r=>r[0]==='ai_send_accepted'));cases++;
  }
  const delayed=acceptance({acceptedAt:12});await delayed.run();assert.equal(delayed.ticks(),14);
  assert.equal(delayed.reports.at(-1)[3].submission_proof,'owned_gemini_user_turn');assert.equal(delayed.sends(),1);cases++;
  const normal=acceptance({strict:false});await assert.rejects(normal.run(),/60/);assert(!normal.reports.some(r=>r[0]==='ai_send_accepted'));cases++;
  const fresh=response();assert.equal((await fresh.run()).innerText,'new scene-two answer');assert(fresh.clock()>=8000);assert.equal(fresh.sends(),1);cases++;
  for(const options of [{ownedAt:Infinity},{noAfter:true}]) {
    const f=response(options);await assert.rejects(f.run(),options.ownedAt===Infinity
      ? /GEMINI_TEXT_REQUEST_REVIEW/ : /AI_ANALYSIS_TIMEOUT/);assert.equal(f.sends(),1);cases++;
  }
  const cancel=response({cancel:true});await assert.rejects(cancel.run(),/cancelled/);cases++;
  for(const options of [{strict:false},{gemini:false}]) {
    const f=response(options);assert.equal((await f.run()).innerText,options.gemini===false?'old scene-one answer':'new scene-two answer');cases++;
  }
  const h={userTurns:()=>[{innerText:'คุณบอกว่า short preview',textContent:'คุณบอกว่า\n'+request.replaceAll(' ', '\n')}]};
  vm.createContext(h);vm.runInContext(helper,h);assert.equal(h.motionRequestIsLatestUser(request),true);assert.equal(h.motionRequestIsLatestUser(oldRequest),false);cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
