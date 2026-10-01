const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
function fixture(){
  const storage={},tabs=new Map(),events=[],audit=[];let next=40;
  const c=vm.createContext({console,crypto:require('node:crypto').webcrypto,Set,Number,JSON,String,Promise,
    setTimeout:fn=>fn(),BRIDGE:'http://fixture',AI_WEB:{chatgpt:{url:'https://chatgpt.com/'},gemini:{url:'https://gemini.google.com/app'}},
    normalizeAIProvider:v=>v||'chatgpt',
    BRIDGE_TOKEN:'fixture-capability',membershipProfile:async()=>'fixture-profile',
    isAllowedFlowImageUrl:url=>url.startsWith('http://fixture/'),
    assertStoryCheckpointOwner:async(m,s)=>{if(s.tab.id!==5||m.run_id!=='RUN-1')throw Error('owner');},
    aiProgressOwnership:async(m,id)=>({active:m.run_id==='RUN-1',ownerTabId:5,activeRunId:'RUN-1'}),
    bridgeFetch:async(url,opts)=>{if(url.includes('/chatgpt-package'))return {ok:true,json:async()=>({ok:true,package:c.testPackage})};if(url.includes('/flow-package'))return {ok:true,json:async()=>({ok:true,package:{image_ai_provider:c.testProvider || 'chatgpt',image_urls:['http://fixture/scene.png']}})};audit.push(JSON.parse(opts.body));return {ok:true,json:async()=>({ok:true})};},
    chrome:{storage:{local:{get:async key=>typeof key==='string'?{[key]:storage[key]}:storage,
      set:async values=>Object.assign(storage,structuredClone(values)),remove:async key=>{delete storage[key];}}},
      scripting:{executeScript:async()=>{}},tabs:{create:async opts=>{const t={id:++next,status:'complete',...opts};tabs.set(t.id,t);events.push('open');return t;},
        get:async id=>{if(!tabs.has(id))throw Error('missing');return tabs.get(id);},
        sendMessage:async(id,msg)=>{events.push(msg.type);return {ok:true};},remove:async id=>{tabs.delete(id);events.push('close');}}}
  });
  vm.runInContext(source.slice(source.indexOf('async function pairedDownloadHeaders('),source.indexOf('const FLOW_RUN_ACTIONS =')),c);
  vm.runInContext(source.slice(source.indexOf('const storyRepairLocks ='),source.indexOf('async function startAIWebJob(')),c);
  const message={type:'STORY_SCENE_REPAIR',action:'start',job_id:'STORY-TEST',run_id:'RUN-1',provider:'chatgpt',index:1,
    original_prompt:'original scene',request:'rewrite scene safely',reason:'service failure'};
  const sender={tab:{id:5}};
  return {c,storage,tabs,events,audit,message,sender,call:(extra={})=>c.storyRepairMessage({...message,...extra},sender)};
}
(async()=>{
  const f=fixture();let r=await f.call();assert.equal(r.phase,'rewrite_sent');assert.equal(f.events.filter(x=>x==='open').length,1);
  await f.call();assert.equal(f.events.filter(x=>x==='open').length,1);
  assert.equal(await f.c.isStoryRepairSendOwner({...f.message,expectedPrompt:f.message.request},r.helper_tab),true);
  assert.equal(await f.c.isStoryRepairSendOwner({...f.message,expectedPrompt:'wrong'},r.helper_tab),false);
  assert.equal(await f.c.isStoryRepairSendOwner({...f.message,expectedPrompt:f.message.request,run_id:'RUN-OTHER'},r.helper_tab),false);
  const key='smartflowSceneRepair:STORY-TEST:1';
  f.storage[key]={...f.storage[key],phase:'ready',candidate:{prompt:'new scene',needs_review:false,change_summary:'clear'}};
  r=await f.call({action:'status'});assert.equal(r.phase,'ready');assert.equal(f.tabs.size,0);
  assert(f.audit.some(x=>x.event.prompt==='new scene'));
  await f.call({action:'image_pending'});await f.call();assert.equal(f.storage[key].round,2);
  f.storage[key].phase='image_pending';r=await f.call();assert.equal(r.exhausted,true);assert.equal(f.events.filter(x=>x==='open').length,2);
  await assert.rejects(f.c.storyRepairMessage(f.message,{tab:{id:99}}),/owner/);
  await assert.rejects(f.call({original_prompt:'different'}),/เปลี่ยน/);
  await f.call({action:'cancel'});assert.equal(f.tabs.size,0);assert.equal(f.storage[key].phase,'cancelled');
  const g=fixture();const old=await g.call();
  g.c.chrome.tabs.sendMessage=async()=>({ok:false}); // A reused tab ID is not our helper document.
  await g.call({action:'cancel'});assert(g.tabs.has(old.helper_tab));
  const live=fixture();
  const checkpoint={index:13,url:'http://fixture/api/stories/STORY-TEST/files/generated/scene_13.png'};
  live.c.testPackage={job:{id:'STORY-TEST',image_ai_provider:'chatgpt'},checkpoint_images:[checkpoint]};
  assert.deepEqual((await live.call({action:'previous_reference',index:14})).checkpoint,checkpoint,
    'read the saved preceding image from the current desktop package');
  live.c.testPackage.checkpoint_images=[{...checkpoint,url:checkpoint.url.replace('STORY-TEST','STORY-OTHER')}];
  assert.equal((await live.call({action:'previous_reference',index:14})).checkpoint,null);

  for(const previousPhase of ['image_pending','ready']){
    const fresh=fixture(),key='smartflowSceneRepair:STORY-TEST:1';
    const receiptKey='smartpostStoryGeneratedImage:chatgpt:STORY-TEST:1';
    fresh.storage[key]={job_id:'STORY-TEST',run_id:'RUN-1',provider:'chatgpt',owner_tab:5,index:1,
      original_prompt:fresh.message.original_prompt,round:2,phase:previousPhase,request_id:'OLD-HELPER',helper_tab:0,
      candidate:{prompt:'old non-standalone candidate',needs_review:false}};
    fresh.storage[receiptKey]={version:1,job_id:'STORY-TEST',provider:'chatgpt',scene_index:1,status:'reference_required'};
    const revised=await fresh.call({standalone_after_reference:true,request:'Create one independent text-only scene brief'});
    assert.equal(revised.round,1,'standalone branch is not blocked by two completed previous rewrites');
    assert.equal(revised.standalone_after_reference,true);
    assert.equal(revised.phase,'rewrite_sent');
    assert.equal(fresh.storage[key+':history:OLD-HELPER'].phase,previousPhase,'retain the old completed helper');
    assert.equal(fresh.events.filter(x=>x==='open').length,1);
    await fresh.call({standalone_after_reference:true,request:'Create one independent text-only scene brief'});
    assert.equal(fresh.events.filter(x=>x==='open').length,1,'restart adopts the same pending standalone request');
    fresh.storage[key].phase='ready';fresh.storage[key].candidate={prompt:'actual independent scene'};
    assert.equal((await fresh.call({standalone_after_reference:true})).candidate.prompt,'actual independent scene');
    assert.equal(fresh.events.filter(x=>x==='open').length,1,'completed standalone helper survives restart');
    fresh.storage[receiptKey].status='awaiting_result';
    await assert.rejects(fresh.call({standalone_after_reference:true}),/ยังไม่มีคำตอบยืนยัน/);
    assert.equal(fresh.events.filter(x=>x==='open').length,1,'unknown image Send never authorizes a new helper');
  }
  const uncertain=fixture();await uncertain.call();
  uncertain.storage['smartpostStoryGeneratedImage:chatgpt:STORY-TEST:1']={version:1,job_id:'STORY-TEST',provider:'chatgpt',scene_index:1,status:'reference_required'};
  await assert.rejects(uncertain.call({standalone_after_reference:true}),/ยังไม่ยืนยันผล/);
  assert.equal(uncertain.events.filter(x=>x==='open').length,1,'unanswered old helper cannot be replaced');
  process.stdout.write(JSON.stringify({ok:true,cases:22}));
})().catch(e=>{console.error(e);process.exitCode=1;});
