// Actual helper source; no provider requests, Chrome navigation or paid generation.
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const code=source.slice(source.indexOf('  function extractAlternativeJson('),source.indexOf('  async function runSceneRepairHelper('));
const good={prompt:'Vertical 9:16. Two fictional friends walk beside a quiet garden gate with a slow camera movement.',
  needs_review:false,reference_compatible:true,material_change:false,scene_narration:'เพื่อนสองคนเดินกลับบ้านผ่านสวนดอกไม้',context_summary:'A safe new garden walk.',
  scene_dialogue_turns:[{speaker:'มะลิ',listener:'ต้น',text:'กลับบ้านกันไหม'},{speaker:'ต้น',listener:'มะลิ',text:'เดินไปด้วยกันนะ'}]};
function fixture(provider,options={}){
 const row={request_id:'owned',job_id:'STORY-T',run_id:'RUN-1',index:1,phase:'rewrite_sent',provider,creative_revision_version:1,creative_round:0,
   alternative:true,helper_tab:8,owner_tab:5,
   revise_story:true,alternative_stage:'proposal',request:'initial proposal',image_urls:['original'],
   context:{aspect_ratio:'9:16',actor_dialogue:true,story_beat:'OLD FAILED EVENT',audio_instruction:'ACTOR DIALOGUE: OLD WORDS'}};
 let currentRequest='',draft='',answer=null,proposalCount=0,motionCount=0,images=0,cancelled=false,interrupted=false;
 const calls=[],sleeps=[],events=[];
 const attachment=()=>({count:options.guard==='attachment'?1:0,busy:options.guard==='upload',failed:false});
 const motionContext={story_beat:good.scene_narration,audio_instruction:'ACTOR DIALOGUE: มะลิ speaks to ต้น: กลับบ้านกันไหม'};
 let replacement={phase:'requested',creative_round:0,motion_context:motionContext};
 const image=()=>({complete:true,naturalWidth:288,naturalHeight:512,src:'new-image-'+images});
 const makeReply=stage=>{
   let candidate={...good};
   if(['proposal','proposal_correction'].includes(stage)){
     proposalCount++;
     candidate.reference_compatible=false; // Exact observed false/false false-positive.
     candidate.needs_review=proposalCount<=(options.reviews || 0);
   }else if(stage==='motion_sent'){
     motionCount++;
     candidate.needs_review=motionCount<=(options.motionReviews || 0);
   }
   return {innerText:JSON.stringify(candidate),candidate};
 };
 const c=vm.createContext({String,Number,Error,JSON,IS_GEMINI:provider==='gemini',location:{href:'https://'+(provider==='gemini'?'gemini.google.com/app/test':'chatgpt.com/c/test')},
   document:{querySelectorAll:()=>[]},Node:{DOCUMENT_POSITION_FOLLOWING:4},
   chrome:{runtime:{sendMessage:async message=>{
     assert.equal(message.creative_round,row.creative_round);events.push(message);
     if(message.action==='proposal_check'){
       if(options.invalid && events.filter(x=>x.action==='proposal_check').length<=options.invalid)
         return {ok:true,replacement:{proposal_feedback:{code:'revision_invalid',reason:'Invalid actor assignment'}}};
       replacement={...replacement,motion_context:motionContext};
     }
     if(message.action==='image')replacement={...replacement,phase:'image_saved',image_url:'saved-image-'+images};
     if(message.action==='redesign')replacement={phase:'requested',creative_round:row.creative_round+1};
     if(message.action==='ready')replacement={...replacement,phase:'ready',effective_prompt:message.candidate.prompt+'\n'+motionContext.audio_instruction};
     return {ok:true,replacement:structuredClone(replacement)};
   }}},
   userTurns:()=>[],composerText:()=>options.guard==='draft'?'user draft':draft,
   motionRequestIsLatestUser:request=>options.guard!=='owner' && currentRequest===request,
   stopButtonVisible:()=>options.guard==='busy',geminiComposerAttachmentState:attachment,chatGPTComposerAttachmentState:attachment,
   latestAssistantStrictlyAfterLatestUser:()=>answer,alternativeImageReply:()=>answer,
   revealChatGPTAnswer:async()=>false,generatedImageElements:()=>[image()],storyImageAssetKey:i=>i.src,
   imageData:async()=> 'data:image/png;base64,fixture',waitForResponseIdle:async()=>{},
   report:async()=>{},assertNotCancelled:()=>{if(cancelled)throw Error('cancelled');},
   sleep:async ms=>{sleeps.push(ms);if(options.cancel && row.alternative_stage==='proposal_correction')cancelled=true;},
   extractJson:turn=>turn.candidate || JSON.parse(turn.innerText),
   submitPrompt:async(request,refs,filename,n,beforeSend)=>{
     if(beforeSend){draft=request;await beforeSend();draft='';}
     calls.push({stage:row.alternative_stage,request,refs});
     if(options.unknown && row.alternative_stage==='proposal_correction')throw Error('unknown send');
     if(row.alternative_stage==='motion_sent'){
       assert(request.includes('กลับบ้านกันไหม'));
       assert(!request.includes('OLD WORDS'));
       assert.equal(refs[0],'saved-image-'+images);
     }
     currentRequest=request;answer=makeReply(row.alternative_stage);return answer;
   },
   submitImagePrompt:async(request,refs)=>{
     images++;calls.push({stage:'generate-image',request,refs});
     assert(request.includes('genuinely different fictional design'));
     currentRequest=request;answer={innerText:'new generated image'};return image();
   }
 });
 const selected=options.oldHelper ? fs.readFileSync('deliverables/SmartFlow_AI_Extension_0.15.418/chatgpt.js','utf8') : source;
 vm.runInContext(selected.slice(selected.indexOf('  function extractAlternativeJson('),selected.indexOf('  async function runSceneRepairHelper(')),c);
 const storageClone=value=>JSON.parse(JSON.stringify(value,(_key,item)=>item && typeof item==='object' && !Array.isArray(item)
   ? Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])) : item));
 if(options.storageOrder){
   const bg=fs.readFileSync(options.oldBackground?'deliverables/SmartFlow_AI_Extension_0.15.418/background.js':'browser_extension/background.js','utf8');
   const section=bg.slice(bg.indexOf("    if (message?.type === 'FLOW_ALTERNATIVE_EVENT')"),bg.indexOf("    if (message?.type === 'AI_COVER_EVENT')"));
   const bridgeEvent=c.chrome.runtime.sendMessage;
   const b=vm.createContext({URL,JSON,Number,String,BRIDGE:'http://fixture.invalid',
     chrome:{storage:{local:{get:async()=>({key:storageClone(row)})}},tabs:{get:async()=>({id:5})}},
     assertFlowRepairOwner:async()=>{},bridgeFetch:async(url,options)=>{
       const body=JSON.parse(options.body);
       const result=await bridgeEvent({...body,action:body.replacement_action});
       return {ok:true,json:async()=>result};
     }});
   vm.runInContext('async function handle(message,sender,sendResponse){'+section+'}',b);
   c.chrome.runtime.sendMessage=async message=>{
     let response;
     await b.handle(structuredClone(message),{tab:{id:8,url:c.location.href}},value=>{response=value;});
     return response;
   };
 }
 const save=async patch=>{
   Object.assign(row,options.storageOrder?storageClone(patch):structuredClone(patch));
   if(options.crash && patch.alternative_stage==='redesign_prepared' && !interrupted){interrupted=true;throw Error('crash after redesign');}
 };
 return {row,calls,events,sleeps,run:recover=>c.runFlowAlternativeHelper('key',structuredClone(row),recover,save),
   get images(){return images;},get proposalCount(){return proposalCount;}};
}
async function run(){
 let cases=0;
 for(const provider of ['chatgpt','gemini']){
   for(const options of [{},{reviews:4},{invalid:3},{motionReviews:2}]){
     const f=fixture(provider,options);await f.run(false);
     assert.equal(f.row.phase,'ready');
     assert(f.row.candidate.prompt.includes('ACTOR DIALOGUE:'));
     assert(f.row.candidate.prompt.includes('กลับบ้านกันไหม'));
     assert.equal(f.images,1+(options.motionReviews || 0));
     assert.equal(f.events.filter(x=>x.action==='redesign').length,options.motionReviews || 0);
     assert.equal(f.row.creative_round,options.motionReviews || 0);
     assert(f.events.some(x=>x.action==='proposal_check' && x.candidate.reference_compatible===false && x.candidate.material_change===false));
     assert(!f.events.some(x=>x.action==='proposal_check' && x.candidate.needs_review));
     if(options.reviews)assert.equal(f.row.proposal_feedback_round,options.reviews);
     if(options.invalid)assert.equal(f.row.proposal_feedback_round,options.invalid);
     assert(f.sleeps.every(ms=>ms<=30000));cases++;
   }
   for(const guard of ['draft','attachment','upload','busy','owner']){
     const f=fixture(provider,{reviews:1,guard});
     await assert.rejects(()=>f.run(false));
     assert.equal(f.images,0);assert(f.calls.length<=1);cases++;
   }
   const cancelled=fixture(provider,{reviews:1,cancel:true});
   await assert.rejects(()=>cancelled.run(false),/cancelled/);assert.equal(cancelled.calls.length,1);assert.equal(cancelled.images,0);cases++;
   const unknown=fixture(provider,{reviews:1,unknown:true});
   await assert.rejects(()=>unknown.run(false),/unknown send/);
   const sends=unknown.calls.length;await unknown.run(true);
   assert.equal(unknown.calls.length,sends);assert.equal(unknown.images,0);assert.equal(unknown.row.phase,'rewrite_sent');cases++;
   const crash=fixture(provider,{motionReviews:1,crash:true});
   await assert.rejects(()=>crash.run(false),/crash after redesign/);
   assert.equal(crash.row.alternative_stage,'redesign_prepared');await crash.run(true);
   assert.equal(crash.row.phase,'ready');assert.equal(crash.images,2);
   assert.equal(crash.events.filter(e=>e.action==='redesign').length,1);cases++;
 }
 // Actual background listener rejects stale rounds, foreign tabs and invented reviews.
 const bg=fs.readFileSync('browser_extension/background.js','utf8');
 const section=bg.slice(bg.indexOf("    if (message?.type === 'FLOW_ALTERNATIVE_EVENT')"),bg.indexOf("    if (message?.type === 'AI_COVER_EVENT')"));
 const row={alternative:true,phase:'rewrite_sent',request_id:'owned',helper_tab:8,owner_tab:5,provider:'chatgpt',
   job_id:'STORY-T',run_id:'RUN-1',index:1,creative_revision_version:1,creative_round:2,alternative_stage:'motion_sent',
   completed_motion_candidate:{...good,needs_review:true}};
 let bridges=0;
 const c=vm.createContext({URL,JSON,Number,String,BRIDGE:'http://fixture',
   chrome:{storage:{local:{get:async()=>({key:row})}},tabs:{get:async()=>({id:5})}},
   assertFlowRepairOwner:async()=>{},bridgeFetch:async(url,opts)=>{bridges++;assert.equal(JSON.parse(opts.body).creative_round,2);return {ok:true,json:async()=>({ok:true})};}});
 vm.runInContext('async function handle(message,sender,sendResponse){'+section+'}',c);
 const message={type:'FLOW_ALTERNATIVE_EVENT',key:'key',request_id:'owned',action:'redesign',creative_round:2,candidate:row.completed_motion_candidate};
 const sender={tab:{id:8,url:'https://chatgpt.com/c/helper'}};
 await c.handle(message,sender,()=>{});assert.equal(bridges,1);cases++;
 for(const changed of [{creative_round:1},{candidate:{...good}},{request_id:'other'}]){
   await assert.rejects(()=>c.handle({...message,...changed},sender,()=>{}));cases++;
 }
 await assert.rejects(()=>c.handle(message,{tab:{...sender.tab,id:9}},()=>{}));cases++;
 row.alternative_stage='image_sent';await assert.rejects(()=>c.handle(message,sender,()=>{}));cases++;
 assert.equal(bridges,1);
 // Real start_alternative path carries the opt-in and constructs the new brief.
 const factory=new Function('require',fs.readFileSync('tests/story_repair_background_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
 const f=factory(),key='smartflowFlowRepair:STORY-TEST:1';
 Object.assign(f.c,{URL,isFlowUrl:u=>u.startsWith('https://flow.google.com/'),flowProgressOwnership:async()=>({active:true,ownerTabId:5,activeRunId:'RUN-1'})});
 f.sender.tab.url='https://flow.google.com/project/p';
 Object.assign(f.message,{type:'FLOW_SCENE_REPAIR',shot_index:1,fingerprint:'fp',failure_id:'one'});
 f.storage.smartpostFlowMonitor={jobId:'STORY-TEST',runId:'RUN-1',shotIndex:1,storyPolicyTerminal:{repair_eligible:true,failure_code:'FLOW_POLICY_BLOCKED',failure_card_fingerprint:'fp',failure_reason:'failed',projectPath:'/project/p'}};
 await f.call();f.storage[key].phase='needs_review';
 const fetch=f.c.bridgeFetch;
 f.c.bridgeFetch=async(url,options)=>{
   const body=JSON.parse(options?.body || '{}');
   if(body.replacement_action!=='begin')return fetch(url,options);
   assert.equal(body.creative_revision_version,1);
   return {ok:true,json:async()=>({ok:true,context:{actor_dialogue:true,aspect_ratio:'9:16'},replacement:{phase:'requested',creative_revision_version:1,creative_round:0}})};
 };
 f.storage.smartpostFlowMonitor.startedAt=1;
 const started=await f.call({action:'start_alternative',failure_id:'1:fp',rebuild_scene:true,revise_story:true,creative_revision_version:1});
 assert.equal(started.creative_revision_version,1);
 assert(started.request.includes('spoken script of THIS segment'));
 assert(started.request.includes('scene_dialogue_turns'));
 assert(!started.request.includes('Preserve character continuity and assigned dialogue.'));cases++;
 console.log(cases+' actual-source creative recovery cases passed (both providers + background guards)');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
