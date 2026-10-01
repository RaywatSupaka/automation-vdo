const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const start=background.indexOf("const CONVERSATION_RECOVERY_PREFIX=");
const end=background.indexOf("const STORY_REFRESH_COLLECTOR_REATTACH",start);
const source=background.slice(start,end);assert(start>0&&end>start);
const job='STORY-FIXTURE',run='RUN-ONE',url='https://chatgpt.com/c/original';
const packet={ok:true,package:{job:{id:job},analysis_checkpoint:{scene_prompts:['saved']},
 ai_resume:{required:true,provider:'chatgpt',stage:'image',index:8,conversation_url:url}}};
const receipt={scene_index:8,send_nonce:'original',result_proof:{conversation_url:url},saved_images:7};
let clock=1000,active=true,failCreate=false,checks=0;
const storage={[`smartpostAIWebRun:${job}`]:run,[`smartpostAIWebTab:chatgpt:${job}`]:1,receipt};
const tabs=new Map([[1,{id:1,url,documentId:'old',state:'unavailable'}]]),events=[];
const copy=x=>JSON.parse(JSON.stringify(x));
const context=vm.createContext({Date:{now:()=>clock},crypto:{randomUUID:()=>`nonce-${clock}`},
 BRIDGE:'http://fixture',URL,console,globalThis:undefined});context.globalThis=context;
context.chrome={runtime:{id:'fixture'},storage:{local:{
 get:async keys=>copy(keys===null?storage:Object.fromEntries((Array.isArray(keys)?keys:[keys]).filter(k=>k in storage).map(k=>[k,storage[k]]))),
 set:async values=>Object.assign(storage,copy(values))}},scripting:{executeScript:async({target})=>{
  const tab=tabs.get(target.tabId);return [{frameId:0,documentId:tab.documentId,result:{url:tab.url,state:tab.state}}];}},
 tabs:{get:async id=>copy(tabs.get(id)),query:async()=>[...tabs.values()].map(copy),reload:async id=>{events.push('reload');tabs.get(id).documentId='refreshed';},
 create:async ({url})=>{events.push('create');tabs.set(2,{id:2,url,documentId:'blank',state:'outside'});if(failCreate)throw Error('lost ACK');return {id:2};},
 update:async(id,{url})=>{events.push('navigate');Object.assign(tabs.get(id),{url,documentId:'new',state:'unavailable'});}}};
context.aiRunStorageKey=id=>`smartpostAIWebRun:${id}`;
context.storyRefreshDesktopRunActive=async(id,owner)=>active&&id===job&&owner===run;
context.bridgeFetch=async address=>{assert(address.endsWith(`/api/stories/${job}/chatgpt-package`));return {ok:true,json:async()=>copy(packet)};};
context.rememberAutomationTabs=async()=>{};
context.reportWebActionProgress=async value=>{assert.equal(value.runId,run);assert.equal(value.imageCount,undefined);};
context.startAIWebJob=async(...args)=>{
 assert.equal(args[0],job);assert.equal(args[1],true);assert.equal(args[2],'chatgpt');assert.equal(args[3],false);
 assert.equal(args[4],run);await args[5]();assert.equal(args[6],'new');assert.equal(JSON.stringify(args[7]),JSON.stringify(packet.package.ai_resume));
 events.push('read-original');};
vm.runInContext(fs.readFileSync('browser_extension/conversation_recovery.js','utf8'),context);
vm.runInContext(source,context);
const message={job_id:job,run_id:run,provider:'chatgpt',conversation_url:url};
const sender={id:'fixture',tab:{id:1},documentId:'old',frameId:0,url};
const audit=async()=>{clock+=15000;await context.runConversationPageRecoveryAudit();};
(async()=>{
 for(const patch of [{id:'other'},{frameId:1},{url:'https://evil.example/'}]){
  await assert.rejects(()=>context.registerConversationPageRecovery(message,{...sender,...patch}));checks++;
 }
 assert.equal((await context.registerConversationPageRecovery(message,{...sender,documentId:'foreign'})).pending,false);checks++;
 active=false;await assert.rejects(()=>context.registerConversationPageRecovery(message,sender));checks++;active=true;
 const before=JSON.stringify(storage.receipt);
 await context.registerConversationPageRecovery(message,sender);await context.runConversationPageRecoveryAudit();
 assert.equal(events.length,0);checks++;
 await audit();await audit();assert.deepEqual(events,['reload']);checks++;
 failCreate=true;await audit();assert.deepEqual(events,['reload','create']);checks++;
 await audit();assert.deepEqual(events,['reload','create','navigate']);checks++;
 assert.equal(storage[`smartpostAIWebTab:chatgpt:${job}`],2);checks++;
 await assert.rejects(()=>context.registerConversationPageRecovery(message,sender));checks++;
 tabs.get(2).state='ready';active=false;await audit();assert(!events.includes('read-original'));checks++;active=true;
 await audit();assert.equal(events.filter(e=>e==='read-original').length,1);checks++;
 await audit();assert.equal(events.filter(e=>e==='read-original').length,1);checks++;
 assert.equal(JSON.stringify(storage.receipt),before);checks++;
 assert.equal(tabs.get(1).url,url);assert.equal(tabs.get(2).url,url);checks++;
 assert.equal(Object.values(storage).filter(row=>row?.phase==='resumed').length,1);checks++;
 console.log(JSON.stringify({ok:true,checks,provider_sends:0,live_state_writes:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
