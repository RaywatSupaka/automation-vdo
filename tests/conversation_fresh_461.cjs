const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const code=background.slice(background.indexOf('const CONVERSATION_RECOVERY_PREFIX='),background.indexOf('const STORY_REFRESH_COLLECTOR_REATTACH'));
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const copy=x=>JSON.parse(JSON.stringify(x));
let cases=0;
function fixture(stage='image') {
 const job='STORY-FIXTURE',run='RUN',url='https://chatgpt.com/c/original',receiptKey=`smartpostStoryGeneratedImage:chatgpt:${job}:8`;
 const resume={required:true,provider:'chatgpt',stage,conversation_url:url,...(stage==='image'?{index:8}:{request:'FULL EXACT REQUEST STORY-FIXTURE'})};
 const packet={ok:true,package:{job:{id:job,image_ai_provider:'chatgpt',video_generation_mode:'meta_ai',meta_scene_sequence_version:1},
  prompt:'saved',request:{image_count:10},image_urls:[],ai_resume:resume,
  ...(stage==='image'?{analysis_checkpoint:{job_id:job,scene_prompts:Array(10).fill('saved')},
   checkpoint_images:Array.from({length:7},(_,i)=>({index:i+1,url:`saved-${i+1}`}))}:{})}};
 const original={version:1,job_id:job,provider:'chatgpt',scene_index:8,run_id:run,status:'awaiting_result',
   send_nonce:'old-nonce',result_proof:{prompt:'FULL IMAGE INSTRUCTION',conversation_url:url},identity:'original identity'};
 const storage={[`smartpostAIWebRun:${job}`]:run,[`smartpostAIWebTab:chatgpt:${job}`]:1,[receiptKey]:copy(original),saved_scenes:['1','2','3','4','5','6','7']};
 const tabs=new Map([[1,{id:1,url,documentId:'old',state:'unavailable'}]]),events=[];
 let now=1000,active=true,lostStart=false;
 const ctx=vm.createContext({Date:{now:()=>now},crypto:{randomUUID:()=>`nonce-${now}`},BRIDGE:'http://fixture',URL,console});
 ctx.chrome={runtime:{id:'extension'},storage:{local:{get:async keys=>copy(keys===null?storage:Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>k in storage).map(k=>[k,storage[k]]))),set:async values=>Object.assign(storage,copy(values))}},
  scripting:{executeScript:async({target,files})=>{if(files){events.push('inject');return [];}
   const t=tabs.get(target.tabId);return [{frameId:0,documentId:t.documentId,result:{state:t.state,url:t.url}}];}},
  tabs:{get:async id=>copy(tabs.get(id)),query:async()=>[...tabs.values()].map(copy),
   reload:async id=>{events.push('reload');tabs.get(id).documentId='refreshed';},
   create:async({url})=>{events.push('create');tabs.set(2,{id:2,url,state:'outside',documentId:'blank'});return {id:2};},
   update:async(id,{url})=>{events.push('navigate:'+url);Object.assign(tabs.get(id),{url,documentId:url.endsWith('/c/original')?'replacement':'home',state:url.endsWith('/c/original')?'unavailable':'fresh_ready'});},
   sendMessage:async(id,message,options)=>{assert.equal(id,2);assert.equal(options.documentId,'home');assert.equal(message.accept_existing_run,true);
    events.push('start');ctx.lastStart=copy(message);if(lostStart)throw Error('lost Start ACK');return {ok:true};}}};
 ctx.aiRunStorageKey=id=>`smartpostAIWebRun:${id}`;
 ctx.storyRefreshDesktopRunActive=async()=>active;
 ctx.bridgeFetch=async url=>{assert(url.endsWith('/chatgpt-package'));return {ok:true,json:async()=>copy(packet)};};
 ctx.rememberAutomationTabs=async()=>{};ctx.reportWebActionProgress=async value=>assert.equal(value.imageCount,undefined);
 ctx.startAIWebJob=async(...args)=>{await args[5]();events.push('read-original');};
 vm.runInContext(fs.readFileSync('browser_extension/conversation_recovery.js','utf8'),ctx);vm.runInContext(code,ctx);
 const row=()=>Object.values(storage).find(r=>r?.version===1&&r.phase&&r.key);
 const tick=async()=>{now+=15000;await ctx.runConversationPageRecoveryAudit();};
 const setup=async()=>{await ctx.registerConversationPageRecovery({job_id:job,run_id:run,provider:'chatgpt',conversation_url:url,pending_request:resume.request},
  {id:'extension',tab:{id:1},frameId:0,documentId:'old',url});await ctx.runConversationPageRecoveryAudit();for(let i=0;i<4;i++)await tick();assert.equal(row().phase,'replacement');};
 const claim=async(patch={},senderPatch={})=>ctx.claimConversationFreshStep({key:row().key,token:row().token,stage,index:stage==='image'?8:0,job_id:job,run_id:run,...patch},
  {id:'extension',tab:{id:2},frameId:0,documentId:'home',url:'https://chatgpt.com/',...senderPatch});
 return {ctx,packet,storage,tabs,events,row,tick,setup,claim,original,receiptKey,pause:()=>active=false,loseStart:()=>lostStart=true};
}
(async()=>{
 let f=fixture();await f.setup();await f.tick();assert.equal(f.row().phase,'fresh_navigating');
 assert.deepEqual(f.storage[f.receiptKey],f.original);assert.equal(f.tabs.get(1).url,'https://chatgpt.com/c/original');cases++;
 await f.tick();assert.equal(f.row().phase,'fresh_started');assert.equal(f.ctx.lastStart.package.conversation_fresh_step.index,8);
 assert.equal(f.ctx.lastStart.package.checkpoint_images.length,7);cases++;
 for(const [patch,sender] of [[{index:7},{}],[{run_id:'other'},{}],[{}, {tab:{id:1}}],[{}, {documentId:'other'}],[{stage:'analysis'},{}]]){
  await assert.rejects(()=>f.claim(patch,sender));cases++;
 }
 vm.runInContext(`conversationRecoveryLocks.add(${JSON.stringify(f.row().key)})`,f.ctx);
 assert.equal((await f.claim()).pending,true);assert.equal(f.row().claimed,undefined);
 vm.runInContext(`conversationRecoveryLocks.delete(${JSON.stringify(f.row().key)})`,f.ctx);cases++;
 let claimed=await f.claim();assert.equal(claimed.first,true);assert.deepEqual(claimed.archive.receipt,f.original);cases++;
 assert.equal((await f.claim()).first,false);await f.tick();assert.equal(f.events.filter(x=>x==='start').length,1);cases++;
 assert.equal(f.storage.saved_scenes.length,7);assert.deepEqual(f.storage[f.receiptKey],f.original);cases++;
 for(const scenario of ['saved','generated','nonce','changed_prompt','paused','busy','late_result']) {
  f=fixture();await f.setup();
  if(scenario==='saved')f.packet.package.checkpoint_images.push({index:8,url:'saved-eight'});
  if(scenario==='generated')f.storage[f.receiptKey].status='generated';
  if(scenario==='nonce')f.storage[f.receiptKey].run_id='other';
  if(scenario==='changed_prompt')f.packet.package.prompt='changed';
  if(scenario==='paused')f.pause();
  if(scenario==='busy')f.tabs.get(1).state='protected';
  if(scenario==='late_result')f.tabs.get(1).state='ready';
  await f.tick();await f.tick();assert(!f.events.includes('start'),scenario);
  if(scenario==='late_result')assert(f.events.includes('read-original'));
  cases++;
 }
 f=fixture();await f.setup();await f.tick();f.tabs.get(2).state='protected';await f.tick();assert(!f.events.includes('start'));cases++;
 f=fixture();await f.setup();await f.tick();f.loseStart();await f.tick();assert.equal(f.row().phase,'fresh_starting');
 claimed=await f.claim();assert(claimed.first);await f.tick();assert.equal(f.events.filter(x=>x==='start').length,1);cases++;
 f=fixture('analysis');await f.setup();await f.tick();await f.tick();claimed=await f.claim();
 assert.equal(claimed.archive.resume.request,'FULL EXACT REQUEST STORY-FIXTURE');assert.equal((await f.claim()).first,false);cases++;
 f=fixture('analysis');f.packet.package.long_video_plan={outline:{saved:true},chapters:[{saved:1},{saved:2}]};
 f.packet.package.ai_resume={...f.packet.package.ai_resume,evidence:'long_video_plan',long_video_stage:'chapter',chapter_index:3};
 await f.setup();await f.tick();await f.tick();assert.equal(f.ctx.lastStart.package.long_video_plan.chapters.length,2);
 assert.equal(f.ctx.lastStart.package.ai_resume.chapter_index,3);cases++;

 // Exercise the actual content receipt transition, not a rewritten model.
 const start=content.indexOf('  function createStoryImageReceipt('),end=content.indexOf('\n  async function ',start);
 const factory=content.slice(start,end);assert(factory.includes('async begin()'));
 const job='STORY-CONTENT',run='RUN',key=`smartpostStoryGeneratedImage:chatgpt:${job}:8`,identity=JSON.stringify([['scene'],[],0]);
 const original={version:1,job_id:job,provider:'chatgpt',scene_index:8,run_id:run,identity,review_revision:0,created_at:1,
   status:'awaiting_result',send_phase:'accepted',send_nonce:'old',result_proof:{prompt:'FULL SCENE',conversation_url:'https://chatgpt.com/c/old'}};
 const storage={[key]:copy(original)};let writes=0;
 const c=vm.createContext({PROVIDER_KEY:'chatgpt',activeRunId:run,Date,location:{href:'https://chatgpt.com/'},assertNotCancelled:()=>{},
   storyImageRecoveryError:(code,index,message)=>Error(message),sameStoryImageReceipt:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
   claimUnavailablePendingStep:async()=>({archive:{receipt_key:key,receipt:original}}),
   chrome:{storage:{local:{get:async k=>({[k]:copy(storage[k])}),set:async values=>{writes++;Object.assign(storage,copy(values));}}}}});
 vm.runInContext(factory,c);
 const pkg={job:{id:job},request:{},image_urls:[],conversation_fresh_step:{stage:'image',index:8,token:'token',key:'recovery'}};
 let receipt=c.createStoryImageReceipt(pkg,8,['scene'],7);assert.equal(await receipt.restore(),null);
 assert.equal(storage[key].resume_image_prompt,'FULL SCENE');assert.equal(storage[key].send_nonce,'');cases++;
 const count=writes;receipt=c.createStoryImageReceipt(pkg,8,['scene'],7);assert.equal(await receipt.restore(),null);assert.equal(writes,count);cases++;
 await receipt.begin();assert.equal(storage[key].conversation_restart.token,'token');cases++;
 // Dispatch marker is not cleared by another fresh replay.
 storage[key].send_phase='dispatching';storage[key].result_proof={prompt:'NEW ACCEPTED'};
 c.recoverOwnedStoryImage=async()=>{throw Error('read-only pending');};c.report=async()=>{};
 receipt=c.createStoryImageReceipt(pkg,8,['scene'],7);await assert.rejects(()=>receipt.restore());
 assert.equal(storage[key].send_phase,'dispatching');assert.equal(storage[key].result_proof.prompt,'NEW ACCEPTED');cases++;

 // Actual analysis reader: only first durable claim submits; restart reads.
 const analysis=content.slice(content.indexOf('  async function readPendingAnalysis('),content.indexOf('  async function submitPrompt('));
 let first=true,sends=0,clock=1000;
 const a=vm.createContext({IS_GEMINI:false,PROVIDER_KEY:'chatgpt',Date:{now:()=>clock},location:{href:'https://chatgpt.com/'},
  claimUnavailablePendingStep:async()=>({first,archive:{resume:{request:'FULL REQUEST'}},analysis_references:['saved-ref']}),
  submitPrompt:async(request,refs)=>{assert.equal(request,'FULL REQUEST');assert.deepEqual(Array.from(refs),['saved-ref']);sends++;first=false;a.location.href='https://chatgpt.com/c/new';},
  revealChatGPTAnswer:async()=>{},assertNotCancelled:()=>{},motionRequestMatches:()=>true,
  latestAssistantStrictlyAfterLatestUser:()=>({textContent:'complete'}),analysisAnswerNode:x=>x,analysisResponseStopButton:()=>null,
  extractJson:()=>({job_id:job}),validateAnalysis:x=>x,report:async()=>{},sleep:async()=>{clock+=9000;}});
 vm.runInContext(analysis,a);
 const ap={job:{id:job},ai_resume:{provider:'chatgpt',request:'FULL REQUEST',conversation_url:'https://chatgpt.com/c/old'},conversation_fresh_step:{stage:'analysis'}};
 await a.readPendingAnalysis(ap,'scene_prompts',8);await a.readPendingAnalysis(ap,'scene_prompts',8);assert.equal(sends,1);cases++;
 const claimHelper=content.slice(content.indexOf('  async function claimUnavailablePendingStep('),content.indexOf('  function createStoryImageReceipt('));
 let attempts=0;
 const h=vm.createContext({IS_GEMINI:false,activeJobId:job,activeRunId:run,assertNotCancelled:()=>{},setTimeout:cb=>cb(),
   chrome:{runtime:{sendMessage:async message=>{assert.equal(message.type,'CLAIM_CHATGPT_CONVERSATION_FRESH_STEP');
     return ++attempts===1?{ok:false,pending:true}:{ok:true,first:true,archive:{token:'once'}};}}}});
 vm.runInContext(claimHelper,h);
 assert.equal((await h.claimUnavailablePendingStep({job:{id:job},run_id:run,conversation_fresh_step:{stage:'analysis',index:0,key:'claim',token:'once'}},'analysis',0)).first,true);
 assert.equal(attempts,2);cases++;
 console.log(JSON.stringify({ok:true,cases,live_provider_sends:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
