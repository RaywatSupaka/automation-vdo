const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const src=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const code=src.slice(src.indexOf('  async function sendCoverAndVerify('),src.indexOf('  async function collectCoverImage('));
async function run(options={}){
 let calls=0,samples=0,acceptanceSamples=0,clock=0;const saved={},events=[];
 const c={Date,coverDraftSnapshot:()=>({ready:!options.notReady,identity:options.changed&&++samples>1?'changed':'same'}),
 chrome:{storage:{local:{get:async()=>options.used?{'smartflowCoverSendRetry:R':true}:saved,set:async x=>Object.assign(saved,x)}}},
 coverEvent:async e=>events.push(e),waitForStableSendDraft:async()=>({button:{},editor:{}}),
 assertNotCancelled:()=>{},sleep:async()=>{},coverRecoveryOwnsReferences:()=>!options.referencesMissing,
 sendAndVerify:async(...args)=>{calls++;args[7]?.observe();if(options.accepted||calls===2&&!options.failTwice)return;
 const e=Error('unconfirmed');e.code='AI_SEND_DISPATCHED_UNCONFIRMED';e.sendDiagnostics={gesture_phase:options.partial?'pressed':'released',release_on_send_target:!options.offTarget};
 if(options.lateAccepted||options.neverAccepted||options.referencesMissing){
   e.submissionDispatched=true;e.readOwnedAcceptance=()=>++acceptanceSamples>=3&&!options.neverAccepted?'owned_chatgpt_user_turn':'';
 }
 throw e;}};
 if(options.lateAccepted||options.neverAccepted||options.referencesMissing)c.Date={now:()=>clock+=5000};
 vm.createContext(c);vm.runInContext(code,c);let failed=false;
 try{await c.sendCoverAndVerify({request_id:'R'},{},0,'',0,'prompt');}catch{failed=true;}
 return{calls,saved,failed,events};
}
(async()=>{
 const request={request_id:'R',sources:['a','b']};
 const shell={textContent:'smartflow-cover-R-1.jpg smartflow-cover-R-2.jpg',querySelectorAll:()=>[]};
 const nodes=[1,2].map(i=>({matches:()=>true,currentSrc:'image'+i,complete:true,naturalWidth:100}));
 const snapshot={IS_GEMINI:false,activeCoverRequest:request,activeJobId:'COVER-R',activeRunId:'R',cancelRequested:false,
   location:{href:'https://chatgpt.com/'},composer:()=>({closest:()=>shell}),sendButton:()=>({disabled:false,getAttribute:()=>null}),
   chatGPTComposerAttachmentState:()=>({busy:false,failed:false}),chatGPTCoverAttachmentPreviews:()=>nodes,composerText:()=>'prompt',userTurns:()=>[],assistantTurns:()=>[],stopButtonVisible:()=>false};
 vm.createContext(snapshot);vm.runInContext(src.slice(src.indexOf('  function coverDraftSnapshot('),src.indexOf('  async function sendCoverAndVerify(')),snapshot);
 assert(snapshot.coverDraftSnapshot(request,'prompt').ready);
 snapshot.stopButtonVisible=()=>true;assert.equal(snapshot.coverDraftSnapshot(request,'prompt').ready,false);
 snapshot.stopButtonVisible=()=>false;snapshot.chatGPTComposerAttachmentState=()=>({busy:true});assert.equal(snapshot.coverDraftSnapshot(request,'prompt').ready,false);
 assert.equal((await run()).calls,2);
 assert.equal((await run({accepted:true})).calls,1);
 for(const option of ['changed','used','partial','offTarget','notReady']){const r=await run({[option]:true});assert.equal(r.calls,1,option);assert(r.failed);}
 const r=await run({failTwice:true});assert.equal(r.calls,2);assert(r.failed);assert(r.saved['smartflowCoverSendRetry:R']);
 const late=await run({lateAccepted:true,offTarget:true});
 assert.equal(late.calls,1);assert.equal(late.failed,false);
 assert(late.events.some(event=>event.send_state==='accepted'));
 for(const option of ['neverAccepted','referencesMissing']){
   const outcome=await run({[option]:true,offTarget:true});
   assert.equal(outcome.calls,1,option);assert(outcome.failed,option);
   assert(!outcome.events.some(event=>event.send_state==='accepted'),option);
 }
 console.log('cover send recovery: 11 cases passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
