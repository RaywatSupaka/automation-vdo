// Exact production successor transaction; simulated storage/tabs, no provider.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {fn,source}=require('./shared_refresh_fixture_439.cjs');
let cases=0;
function fixture(options={}){
 const job='STORY-GEMINI-439',run='RUN-GEMINI',index=4,key=`smartpostStoryGeneratedImage:gemini:${job}:${index}`;
 const tabKey=`smartpostAIWebTab:gemini:${job}`,runKey='run:'+job,cancelKey=`smartflowGeminiReloadCancelled:${job}`;
 const url='https://gemini.google.com/app/1234567890abcdef';
 const proof={prompt:'Original scene prompt with all saved references',conversation_url:url,prompt_hash:'12345678',request_index:3,request_container_id:'fedcba0987654321'};
 const row={version:1,job_id:job,provider:'gemini',scene_index:index,run_id:run,identity:'exact-scene-reference-identity',
   status:'completed_no_image',send_phase:'accepted',send_nonce:'accepted-send',result_proof:proof,response_excerpt:'Image generation failed. Please try again.',service_retry_count:1};
 row.gemini_restart_evidence={version:1,receipt_identity:row.identity,send_nonce:row.send_nonce,conversation_url:url,
   prompt_hash:proof.prompt_hash,request_index:proof.request_index,request_container_id:proof.request_container_id,
   response_text:row.response_excerpt,stable_since:1000,observed_at:4000,stable_samples:3,completed:true,busy:false,draft_present:false,attachment_count:0};
 const store={[key]:row,[tabKey]:7,[runKey]:run},tabs={7:{id:7,url,status:'complete'}};
 const events=[];let serial=0,guardCalls=0,startCalls=0,allocations=0;
 const pkg={job:{id:job,image_ai_provider:'gemini'},browser_recovery:{version:1},image_urls:['saved-source.png'],checkpoint_images:['scene_01.png']};
 const c=vm.createContext({crypto:{randomUUID:()=>`token-${++serial}`},Date,setTimeout,clearTimeout,
   normalizeAIProvider:x=>x,aiRunStorageKey:id=>'run:'+id,rememberAutomationTabs:async()=>{},
   AI_WEB:{gemini:{url:'https://gemini.google.com/app'}},isWebLoginUrl:()=>false,webActionError:()=>Error('login'),
   waitForTabComplete:async()=>{},chrome:{storage:{local:{get:async keys=>keys===null?structuredClone(store):Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,structuredClone(store[k])])),
     set:async values=>{Object.assign(store,structuredClone(values));options.onSet?.(store,key,values);}}},tabs:{
     get:async id=>{if(!tabs[id])throw Error('Tab closed');return {...tabs[id]};},query:async()=>Object.values(tabs),
     create:async opts=>{allocations++;events.push('allocate');const tab={id:8,url:opts.url,status:'complete'};tabs[8]=tab;
       if(options.cancelAtAllocation)store[cancelKey]=run;
       if(options.allocationAckLost)throw Error('allocation ACK missing');return {...tab};},
     update:async(id,opts)=>{Object.assign(tabs[id],opts);events.push('navigate');return {...tabs[id]};},
     sendMessage:async(id,message,target)=>{
       if(message.type==='VERIFY_GEMINI_STORY_REDO'){
         guardCalls++;events.push('guard');assert.equal(id,7);assert.equal(message.evidence.response_text,row.response_excerpt);
         const allowed=!options.rejectGuardAt || guardCalls<options.rejectGuardAt;
         return {ok:true,allowed,challenge:message.challenge,receipt_identity:message.receipt_identity,send_nonce:message.send_nonce};
       }
       if(message.type==='CANCEL_CHATGPT_JOB'){assert.equal(message.retire_only,true);events.push('retire');return {ok:true};}
       assert.equal(message.type,'START_CHATGPT_JOB');assert.equal(target.documentId,'document-8');assert.equal(id,8);
       assert.equal(message.package.image_ai_provider,'gemini');assert.equal(message.package.fresh_image_restart.provider,'gemini');
       assert.deepEqual(Array.from(message.package.image_urls),pkg.image_urls);assert.deepEqual(Array.from(message.package.checkpoint_images),pkg.checkpoint_images);
       startCalls++;events.push('start');
       const existing=store[key];
       if(existing.fresh_restart.phase!=='consumed')store[key]={...existing,status:'awaiting_result',send_phase:'prepared',send_nonce:'',
         resume_image_prompt:existing.result_proof.prompt,result_proof:null,response_excerpt:'',gemini_generation_nonce:existing.fresh_restart.token,
         fresh_restart:{...existing.fresh_restart,phase:'consumed'}};
       if(options.startAckLost && startCalls===1)throw Error('START ACK lost');
       if(options.allStartAcksLost)throw Error('all START ACKs lost');
       return {ok:true,...(startCalls>1?{already_running:true}:{started:true})};
     }},scripting:{executeScript:async request=>{
       if(request.files){assert.deepEqual(Array.from(request.target.documentIds),['document-8']);events.push('inject');return [];}
       return [{frameId:0,documentId:'document-'+request.target.tabId,result:tabs[request.target.tabId]?.url}];
     }}}});
 vm.runInContext(['waitForAIRecoveryOperation','restartableGeminiStoryReceipt','restartFailedGeminiStoryImage'].map(fn).join('\n')+'\nconst geminiFreshImageLocks=new Set();\n'+fn('startFreshGeminiStoryImage'),c);
 Object.assign(c,{BRIDGE:'offline',assertStoryCheckpointOwner:async(message,sender)=>{
   if(sender.tab?.id!==store[tabKey])throw Error('wrong source owner');},
   bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:pkg})})});
 return {c,store,tabs,pkg,row,key,tabKey,runKey,cancelKey,job,run,index,events,
   allocations:()=>allocations,starts:()=>startCalls,runJob:()=>c.startFreshGeminiStoryImage(pkg,run,index)};
}
async function test(name,action){try{await action();cases++;}catch(error){error.message=name+': '+error.message;throw error;}}
(async()=>{
 await test('archive before one allocation; exact saved prompt/references',async()=>{
   const f=fixture();await f.runJob();assert.equal(f.allocations(),1);assert.equal(f.starts(),1);
   const row=f.store[f.key],archive=f.store[row.fresh_restart.archive];assert.equal(archive.send_nonce,'accepted-send');
   assert.equal(row.resume_image_prompt,archive.result_proof.prompt);assert.equal(f.store[f.tabKey],8);
   assert.equal(row.fresh_restart.phase,'consumed');assert(f.events.indexOf('guard')<f.events.indexOf('allocate'));
 });
 for(const change of [r=>delete r.gemini_restart_evidence,r=>r.gemini_restart_evidence.stable_samples=2,
   r=>r.gemini_restart_evidence.observed_at=2000,r=>r.gemini_restart_evidence.busy=true,
   r=>r.gemini_restart_evidence.draft_present=true,r=>r.gemini_restart_evidence.attachment_count=1,
   r=>r.gemini_restart_evidence.receipt_identity='foreign',r=>r.gemini_restart_evidence.send_nonce='other',
   r=>r.gemini_restart_evidence.request_container_id='0000000000000000',r=>r.send_phase='dispatching',
   r=>r.image_url='already-created',r=>r.status='generated',r=>{r.response_excerpt='This violates policy';r.gemini_restart_evidence.response_text=r.response_excerpt;},
   r=>{r.response_excerpt='Image generation failed. Please log in.';r.gemini_restart_evidence.response_text=r.response_excerpt;}])
   await test('invalid proof denied '+cases,async()=>{const f=fixture();change(f.store[f.key]);await assert.rejects(()=>f.runJob());assert.equal(f.allocations(),0);assert.equal(f.starts(),0);});
 await test('missing or foreign live guard denied',async()=>{const f=fixture({rejectGuardAt:1});await assert.rejects(()=>f.runJob(),e=>e.refresh_retry_safe===true);assert.equal(f.allocations(),0);});
 await test('late result between archive and allocation denied',async()=>{const f=fixture({rejectGuardAt:4});await assert.rejects(()=>f.runJob(),e=>e.refresh_reason==='live_guard_changed');assert.equal(f.allocations(),0);});
 await test('late result after allocation prevents transfer',async()=>{const f=fixture({rejectGuardAt:5});await assert.rejects(()=>f.runJob());assert.equal(f.allocations(),1);assert.equal(f.starts(),0);assert.equal(f.store[f.tabKey],7);});
 await test('late result before START restores read ownership',async()=>{const f=fixture({rejectGuardAt:6});await assert.rejects(()=>f.runJob(),e=>e.refresh_retry_safe===true);assert.equal(f.allocations(),1);assert.equal(f.starts(),0);assert.equal(f.store[f.tabKey],7);});
 await test('lost allocation ACK reconciles exact tagged tab without duplicate',async()=>{
   const f=fixture({allocationAckLost:true});await assert.rejects(()=>f.runJob(),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   assert.equal(f.store[f.key].fresh_restart.phase,'creating');await f.runJob();assert.equal(f.allocations(),1);assert.equal(f.starts(),1);
 });
 await test('unknown allocation stays pending without a second tab',async()=>{
   const f=fixture({allocationAckLost:true});await assert.rejects(()=>f.runJob());delete f.tabs[8];
   await assert.rejects(()=>f.runJob(),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');assert.equal(f.allocations(),1);
 });
 await test('lost START ACK idempotently reattaches same document',async()=>{const f=fixture({startAckLost:true});await f.runJob();assert.equal(f.allocations(),1);assert.equal(f.starts(),2);});
 await test('all START ACKs lost preserve consumed receipt for later resume',async()=>{
   const f=fixture({allStartAcksLost:true});await assert.rejects(()=>f.runJob(),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   const nonce=f.store[f.key].fresh_restart.token;await assert.rejects(()=>f.runJob(),e=>e.code==='AI_RECOVERY_OPERATION_PENDING');
   assert.equal(f.allocations(),1);assert.equal(f.store[f.key].fresh_restart.token,nonce);
 });
 await test('cancel before allocation',async()=>{const f=fixture();f.store[f.cancelKey]=f.run;await assert.rejects(()=>f.runJob());assert.equal(f.allocations(),0);});
 await test('cancel after allocation prevents START',async()=>{const f=fixture({cancelAtAllocation:true});await assert.rejects(()=>f.runJob());assert.equal(f.allocations(),1);assert.equal(f.starts(),0);});
 await test('changed run cannot reuse archived proof',async()=>{const f=fixture();f.store[f.runKey]='foreign';await assert.rejects(()=>f.runJob());assert.equal(f.allocations(),0);});
 await test('changed registered tab after claim denies transfer',async()=>{
   const f=fixture({onSet:(store,key,values)=>{if(values[key]?.fresh_restart?.phase==='created')store[`smartpostAIWebTab:gemini:${store[key].job_id}`]=99;}});
   await assert.rejects(()=>f.runJob(),/ownership changed/);assert.equal(f.starts(),0);
 });
 await test('lost original restart RPC ACK reconciles archived predecessor',async()=>{
   const f=fixture(),m={provider:'gemini',job_id:f.job,run_id:f.run,index:4,receipt_identity:f.row.identity,send_nonce:f.row.send_nonce};
   const first=await f.c.restartFailedGeminiStoryImage(m,{tab:{id:7}});
   assert.equal(first.ok,true);assert.equal(first.refresh_scheduled,true);
   const again=await f.c.restartFailedGeminiStoryImage(m,{tab:{id:7}});
   assert.equal(again.ok,true);assert.equal(f.allocations(),1);assert.equal(f.starts(),2);
 });
 await test('foreign retry RPC cannot borrow the predecessor archive',async()=>{
   const f=fixture();await f.runJob();
   await assert.rejects(()=>f.c.restartFailedGeminiStoryImage({provider:'gemini',job_id:f.job,run_id:f.run,index:4,
     receipt_identity:f.row.identity,send_nonce:f.row.send_nonce},{tab:{id:99}}),/sender mismatch/);
   assert.equal(f.allocations(),1);assert.equal(f.starts(),1);
 });
 await test('saved scene checkpoint prevents another collector attach',async()=>{
   const f=fixture();await f.runJob();f.pkg.checkpoint_images.push('scene_04.png');
   const reply=await f.c.restartFailedGeminiStoryImage({provider:'gemini',job_id:f.job,run_id:f.run,index:4,
     receipt_identity:f.row.identity,send_nonce:f.row.send_nonce},{tab:{id:7}});
   assert.equal(reply.completed,true);assert.equal(f.starts(),1);assert.equal(f.allocations(),1);
 });
 await test('actual content evidence through background into actual clean-tab consumption',async()=>{
   const prefix=fs.readFileSync('tests/gemini_story_result_recovery_439.cjs','utf8').split('(async()=>{')[0];
   const content=new Function('require',prefix+`;return {c,data,pkg,identity,key,URL,prompt,seed,
     fail:()=>{images=[];reply={text:'Something went wrong',busy:false,completed:true};},
     clean:()=>{users=[];c.location.href='https://gemini.google.com/app';}};`)(require);
   const f=fixture();content.fail();content.seed('completed_no_image',{send_phase:'accepted',send_nonce:'accepted-2',
     response_excerpt:'Something went wrong',service_retry_count:1});
   Object.assign(f.store,content.data);f.store[f.runKey]='RUN-A';f.tabs[7].url=content.URL;
   content.c.chrome.storage.local=f.c.chrome.storage.local;
   const pkg={...content.pkg,job:{...content.pkg.job,image_ai_provider:'gemini'}};
   f.c.bridgeFetch=async()=>({ok:true,json:async()=>({ok:true,package:pkg})});
   f.c.chrome.tabs.sendMessage=async(id,message,target)=>{
     if(message.type==='VERIFY_GEMINI_STORY_REDO')return {ok:true,allowed:content.c.geminiStoryRedoGuard(message),
       challenge:message.challenge,receipt_identity:message.receipt_identity,send_nonce:message.send_nonce};
     if(message.type==='CANCEL_CHATGPT_JOB')return {ok:true};
     assert.equal(target.documentId,'document-8');assert.equal(f.store[f.key].fresh_restart.phase,'starting');
     content.clean();const receipt=content.c.createStoryImageReceipt(message.package,4,content.identity,3);
     assert.equal(await receipt.restore(),null);assert.equal(f.store[f.key].fresh_restart.phase,'consumed');
     assert.equal(f.store[f.key].resume_image_prompt,content.prompt);
     return {ok:true,started:true};
   };
   content.c.chrome.runtime.sendMessage=message=>f.c.restartFailedGeminiStoryImage(message,{tab:{id:7}});
   await assert.rejects(()=>content.c.createStoryImageReceipt(pkg,4,content.identity,3).restore(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');
   assert.equal(f.allocations(),1);assert.equal(f.store[f.tabKey],8);
   assert.equal(f.store[f.key].gemini_generation_nonce,f.store[f.key].fresh_restart.token);
 });
 console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
