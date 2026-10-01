const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const helper=fs.readFileSync('browser_extension/flow.js','utf8');
const refreshSource=background.slice(background.indexOf('async function refreshFlowStartPicker'),background.indexOf('// Runs in the page after tab activation'));
const verifySource=helper.slice(helper.indexOf('  function verifyFlowPickerRefresh'),helper.indexOf('  chrome.runtime.onMessage.addListener',helper.indexOf('  function verifyFlowPickerRefresh')));
const url='https://flow.google.com/project/p1',attemptKey='JOB:2:p1',args={jobId:'JOB',shot:2,run:'RUN',tabId:4,url,filename:'image.png'};
function fixture(){
 const state={stalled:true,idle_ms:45000,target:null,animation_active:false,dialog_count:1,list_count:1,matching_count:1,image_state:'failed',activity:'still'};
 const data={smartpostFlowAttachmentAttempts:{[attemptKey]:{key:attemptKey,runId:'RUN',status:'uploaded_ready',method:'golden_hidden_file_input',fileSet:true,mediaReady:true,uploadedAt:1}},
   smartpostAutoFlow:{jobId:'JOB',shotIndex:2,runId:'RUN'},smartpostFlowReferenceFile:{filename:'image.png'}};
 const calls={reload:0,helper:0,verify:0};let current=true;
 const c={args:{...args,state,isCurrent:async()=>current,inspect:async()=>({...state})},data,calls,flowGenerateInFlight:new Set(),
   Date,crypto:{randomUUID:()=>String(++calls.verify)},flowProjectId:u=>u.split('/').at(-1),
   waitForTabComplete:async()=>{},ensureFlowHelper:async()=>{calls.helper++;},
   chrome:{storage:{local:{get:async()=>structuredClone(data),set:async changes=>Object.assign(data,structuredClone(changes))}},
     tabs:{get:async()=>({url}),reload:async()=>{calls.reload++;},sendMessage:async(_id,m)=>({ok:true,challenge:m.challenge,attempt_key:attemptKey})}}};
 vm.createContext(c);vm.runInContext(refreshSource,c);
 return {c,data,state,calls,run:()=>vm.runInContext('refreshFlowStartPicker(args)',c),cancel:()=>current=false};
}
(async()=>{
 let f=fixture();assert.equal((await f.run()).reloaded,true);assert.equal(f.calls.reload,1);assert.equal(f.calls.helper,1);
 assert(f.data.smartpostFlowAttachmentAttempts[attemptKey].pickerRefresh);
 assert.equal(f.data.smartpostFlowAttachmentAttempts[attemptKey].status,'uploaded_ready','never reupload');
 assert.equal((await f.run()).reason,'refresh_already_used');assert.equal(f.calls.reload,1);
 // Independent invocations/restarts see the persisted claim too.
 const g=fixture();Object.assign(g.data,structuredClone(f.data));assert.equal((await g.run()).reason,'refresh_already_used');assert.equal(g.calls.reload,0);
 for(const mutate of [
   f=>f.cancel(),f=>f.c.flowGenerateInFlight.add('JOB:2:RUN'),f=>f.state.animation_active=true,
   f=>f.state.target={x:1},f=>f.state.idle_ms=500,f=>f.state.matching_count=2,
   f=>f.c.chrome.tabs.get=async()=>({url:url+'other'}),
   f=>f.data.smartpostFlowAttachmentAttempts[attemptKey].fileSet=false,
   f=>f.data.smartpostFlowAttachmentAttempts[attemptKey].mediaReady=false,
   f=>f.data.smartpostFlowAttachmentAttempts[attemptKey].runId='OTHER',
   f=>f.data.smartpostAutoFlow.waitingForManualAttachment=true,
   f=>f.data.smartpostFlowReferenceFile.filename='other.png',
   f=>f.c.chrome.tabs.sendMessage=async()=>({ok:false}),
   f=>f.c.args.inspect=async()=>({...f.state,animation_active:true}),
   f=>f.c.chrome.storage.local.set=async()=>{},
   f=>f.c.chrome.storage.local.set=async changes=>{Object.assign(f.data,changes);f.cancel();}
 ]) {f=fixture();mutate(f);await f.run();assert.equal(f.calls.reload,0,'unsafe refresh blocked');}
 // Race between persisted claim and the final page guard cannot reload.
 f=fixture();f.c.chrome.tabs.sendMessage=async(_id,m)=>({ok:f.calls.verify===1,challenge:m.challenge,attempt_key:attemptKey});
 await f.run();assert.equal(f.calls.reload,0);
 const page={automationPaused:false,pkg:{job_id:'JOB',shot_index:2,run_id:'RUN'},location:{href:url},
   findPromptEditor:()=>({value:''}),activeRightsDialog:()=>false,flowAttachmentAttemptKey:()=>attemptKey,
   proof:{imageReady:false,submissionAbsent:true,generationAbsent:true,resultAbsent:true,confirmationAbsent:true},
   attachmentWaitSnapshot:()=>page.proof,
   msg:{job_id:'JOB',shot_index:2,run_id:'RUN',project_url:url,challenge:'q'}};
 vm.createContext(page);vm.runInContext(verifySource,page);
 const check=()=>vm.runInContext('verifyFlowPickerRefresh(msg)',page);
 assert.equal(check().ok,true);
 for(const field of ['submissionAbsent','generationAbsent','resultAbsent','confirmationAbsent']){
   page.proof[field]=false;assert.equal(check().ok,false,field);page.proof[field]=true;
 }
 page.proof.imageReady=true;assert.equal(check().ok,false);page.proof.imageReady=false;
 page.findPromptEditor=()=>({value:'user draft'});assert.equal(check().ok,false);page.findPromptEditor=()=>null;
 page.automationPaused=true;assert.equal(check().ok,false);page.automationPaused=false;
 page.msg.run_id='OLD';assert.equal(check().ok,false);page.msg.run_id='RUN';
 page.activeRightsDialog=()=>true;assert.equal(check().ok,false);
 // Actual post-reload upload route: an aged uploaded record with the persisted
 // refresh marker MUST select the saved asset, never assign the file again.
 const dropSource=helper.slice(helper.indexOf('  async function dropReferenceImage()'),helper.indexOf('  async function dropReferenceImage()')+helper.slice(helper.indexOf('  async function dropReferenceImage()')).indexOf('\n  async function ',10));
 const restored={pkg:{image_urls:['saved.png']},promptHasAttachedMedia:()=>false,
   readFlowAttachmentAttempt:async()=>({status:'uploaded_ready',startedAt:1,pickerRefresh:{claimed_at:1}}),
   attachExistingMediaToPrompt:async()=>{restored.selections++;return true;},selections:0,saves:[],
   saveFlowAttachmentAttempt:async patch=>restored.saves.push(patch),promptMediaDebug:{},setTimeout:fn=>fn(),Date};
 vm.createContext(restored);vm.runInContext(dropSource,restored);
 assert.equal(await vm.runInContext('dropReferenceImage()',restored),true);
 assert.equal(restored.selections,1);assert.equal(restored.saves[0].status,'composer_proof_verified');
 console.log('picker refresh, page guard and original-upload resume passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
