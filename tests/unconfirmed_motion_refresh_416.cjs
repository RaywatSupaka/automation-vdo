const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const first=source.indexOf('  function unconfirmedChatGPTMotionSnapshot(');
const last=source.indexOf('  function pendingChatGPTMotionSnapshot(',first);
assert(first>0&&last>first);
const code=source.slice(source.indexOf('  function chatGPTConversationFrames('),source.indexOf('  function assistantTurns('))
  +source.slice(first,last),request='Write the original motion JSON for this saved image.';
const context={job_id:'STORY-TEST',index:12,context_id:'c'.repeat(64)};
const url='https://chatgpt.com/c/12345678-1234-1234-1234-123456789012';
function fixture(){
 const state={draft:request,stop:false,owned:false,progress:false,attachment:{count:2,busy:false,failed:false},history:'old saved reply',frames:true,sleeps:0,sends:[],change:'',deny:false};
 const frame={getAttribute:name=>name==='data-testid'?'conversation-turn-23':null,get textContent(){return state.history;},querySelectorAll:()=>[]};
 const c=vm.createContext({IS_GEMINI:false,cancelRequested:false,activeRepairKey:'',activeCoverRequest:null,activeJobId:context.job_id,activeRunId:'run416',
   unconfirmedMotionRefreshGuard:null,location:{href:url},analysisResponseStopButton:()=>state.stop,motionRequestMatches:()=>state.owned,
   composer:()=>({}),composerText:()=>state.draft,chatGPTComposerAttachmentState:()=>state.attachment,
   document:{querySelectorAll:s=>s==='[data-testid^="conversation-turn-"]'?(state.frames?[frame]:[]):s==='[data-chatgpt-search-unit-key]'?[]:state.progress?[{}]:[]},visible:()=>true,
   analysisContentHash:s=>crypto.createHash('sha256').update(s).digest('hex').slice(0,8),
   assertNotCancelled:()=>{if(c.cancelRequested)throw Error('Cancelled');},
   sleep:async()=>{state.sleeps++;if(state.sleeps===2&&state.change)state[state.change]=state.change==='history'?'new answer':true;},report:async()=>{},
   chrome:{runtime:{sendMessage:async m=>{state.sends.push(m);assert.equal(c.unconfirmedMotionRefreshGuard(m),true);return state.deny?{ok:false}:{ok:true,refresh_scheduled:true};}}}});
 vm.runInContext(code,c);
 const error=Object.assign(Error('unconfirmed'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED',submissionDispatched:true,
   sendDiagnostics:{dispatch_completed:true,trusted_click_seen:true,gesture_phase:'released',release_on_send_target:true,
     target_stable_before_press:true,target_node_changes_during_gesture:0,target_geometry_changes_during_gesture:0}});
 return {c,state,error};
}
(async()=>{
 let cases=0;
 for(const kind of ['ok','react_node','gemini','cancel','repair','cover','wrong_context','draft','stop','owned','progress','upload','upload_failure','no_frames','wrong_url',
   'untrusted','partial_release','unknown_dispatch','moved_during_click','history_changed','late_owned','late_stop','denied']){
   const f=fixture();let ctx=context;
   if(kind==='react_node'){const node={src:'blob:original',textContent:'owned reference'};node.reactFiber={stateNode:node};f.state.attachment.nodes=[node];}
   if(kind==='gemini')f.c.IS_GEMINI=true;
   if(kind==='cancel')f.c.cancelRequested=true;
   if(kind==='repair')f.c.activeRepairKey='repair';
   if(kind==='cover')f.c.activeCoverRequest={};
   if(kind==='wrong_context')ctx={...context,job_id:'STORY-OTHER'};
   if(kind==='draft')f.state.draft='user typed a different draft';
   if(['stop','owned','progress'].includes(kind))f.state[kind]=true;
   if(kind==='upload')f.state.attachment.busy=true;
   if(kind==='upload_failure')f.state.attachment.failed=true;
   if(kind==='no_frames')f.state.frames=false;
   if(kind==='wrong_url')f.c.location.href='https://chatgpt.com/';
   if(kind==='untrusted')f.error.sendDiagnostics.trusted_click_seen=false;
   if(kind==='partial_release')f.error.sendDiagnostics.gesture_phase='pressed';
   if(kind==='unknown_dispatch')f.error.submissionDispatched=false;
   if(kind==='moved_during_click')f.error.sendDiagnostics.target_geometry_changes_during_gesture=1;
   if(kind==='history_changed')f.state.change='history';
   if(kind==='late_owned')f.state.change='owned';
   if(kind==='late_stop')f.state.change='stop';
   if(kind==='denied')f.state.deny=true;
   if(['ok','react_node'].includes(kind))await assert.rejects(f.c.refreshUnconfirmedChatGPTMotion(f.error,request,ctx,12),e=>e.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED');
   else assert.equal(await f.c.refreshUnconfirmedChatGPTMotion(f.error,request,ctx,12),false,kind);
   assert.equal(f.state.sends.length,['ok','react_node','denied'].includes(kind)?1:0,kind);
   if(f.state.sends.length){assert.equal(f.state.sends[0].type,'RELOAD_CHATGPT_COMPLETED_RESPONSE');assert.equal(f.state.sends[0].pending_request,request);}
   cases++;
 }
 const start=source.indexOf('  async function submitPrompt('),end=source.indexOf('    const started = Date.now();',start);
 assert(start>0&&end>start);
 const reconcileStart=source.indexOf('  async function reconcileChatGPTSendAcceptance(');
 const reconcileEnd=source.indexOf('  async function ensureAiWebModel(',reconcileStart);
 assert(reconcileStart>0&&reconcileEnd>reconcileStart);
 const submit=source.slice(reconcileStart,reconcileEnd)+source.slice(start,end)+' return true; }';
 for(const kind of ['late_accepted','not_accepted','draft_echo','presend_error','scheduled']){
   const original=Object.assign(Error('original'),{code:kind==='presend_error'?'AI_SEND_NOT_READY':'AI_SEND_DISPATCHED_UNCONFIRMED',submissionDispatched:true});
   original.readOwnedAcceptance=()=>kind==='late_accepted'?'owned_chatgpt_user_turn':'';
   let clicks=0,reloads=0;
   const c=vm.createContext({IS_GEMINI:false,AI_NAME:'ChatGPT',report:async()=>{},
     waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>{},waitForComposer:async()=>({}),assistantTurns:()=>[],userTurns:()=>[],
     lastUserTurnSignature:()=>'',setComposerText:async e=>e,assertNotCancelled:()=>{},sleep:async()=>{},sendButton:()=>({}),
     sendAndVerify:async()=>{clicks++;throw original;},motionRequestMatches:()=>['late_accepted','draft_echo','presend_error'].includes(kind),
     refreshUnconfirmedChatGPTMotion:async()=>{if(kind==='scheduled'){reloads++;throw Object.assign(Error('scheduled'),{code:'CHATGPT_RESPONSE_REFRESH_SCHEDULED'});}}});
   vm.runInContext(submit,c);
   const work=c.submitPrompt(request,[],'',12,null,context);
   if(kind==='late_accepted')assert.equal(await work,true);
   else await assert.rejects(work,e=>kind==='scheduled'?e.code==='CHATGPT_RESPONSE_REFRESH_SCHEDULED':e===original);
   assert.equal(clicks,1);assert.equal(reloads,kind==='scheduled'?1:0);cases++;
 }
 assert(source.includes('if (motionContext) await refreshUnconfirmedChatGPTMotion(error, text, motionContext, completedCount)'));
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
