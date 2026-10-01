const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {fixture}=require('./ai_send_acceptance_harness');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const section=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
(async()=>{
  let calls=[],storage={},allowed=true;
  const c=vm.createContext({crypto:require('node:crypto').webcrypto,Uint8Array,AbortSignal,VERSION:'fixture',BRIDGE:'http://fixture',
    chrome:{storage:{local:{get:async()=>storage,set:async value=>Object.assign(storage,value)}}},
    bridgeFetch:async(url,options,retry)=>{assert.deepEqual(JSON.parse(options.body),{version:'fixture'});calls.push({url,retry});return{ok:allowed,json:async()=>allowed
      ? {ok:true,desktop:{allowed:true},extension:{allowed:true,source:'desktop',contract_version:1}} : {ok:false,error:'Login required'}};}});
  vm.runInContext(section('let membershipProfilePromise =','let flowDownloadEventPromise ='),c);
  const [a,b]=await Promise.all([c.membershipProfile(),c.membershipProfile()]);assert.equal(a,b);assert.match(a,/^[a-f0-9]{48}$/);
  assert.deepEqual(Object.keys(storage),['smartflowMembershipProfile']);
  // An update/service-worker restart changes VERSION, not the persisted profile.
  for(const VERSION of ['0.15.385','0.15.386','future-version']){
    const restarted=vm.createContext({VERSION,chrome:c.chrome,Uint8Array,
      crypto:{getRandomValues:()=>{throw Error('must reuse saved identity');}}});
    vm.runInContext(section('let membershipProfilePromise =','async function membershipRequest('),restarted);
    assert.equal(await restarted.membershipProfile(),a);
  }
  await c.requireMembership();assert.equal(calls.length,1);assert.equal(calls[0].retry,false);
  allowed=false;await assert.rejects(c.requireMembership(),/Login required/);assert.equal(calls.length,2);
  await assert.rejects(c.membershipRequest('login',{token:'do-not-forward'}));assert.equal(calls.length,2);
  c.bridgeFetch=async()=>({ok:true,json:async()=>({ok:true,desktop:{allowed:true},extension:{allowed:true}})});
  await assert.rejects(c.requireMembership(),/อัปเดต/);
  // Refusal happens before any DOM gesture, Send claim, upload or receipt reset.
  const f=fixture({membershipDenied:true}),before=structuredClone(f.storage);await assert.rejects(f.run(),/เข้าสู่ระบบ/);
  assert.equal(f.sends(),0);assert.equal(f.commands.length,0);assert.deepEqual(f.storage,before);
  // Receipt/result messages remain outside the new-work authorization set.
  const guarded=section("if (['CLICK_AI_SEND_BUTTON'", "if(message?.type==='RETRY_CHATGPT_MOTION_SERVICE')");
  for(const name of ['SUBMIT_STORY_RESULT','CHECKPOINT_STORY_IMAGE','FLOW_PROGRESS','AUTO_DOWNLOAD_FLOW_RESULT'])assert(!guarded.includes(name));
  for(const name of ['CLICK_AI_SEND_BUTTON','CLICK_FLOW_GENERATE','CLICK_FLOW_AGENT'])assert(guarded.includes(name));
  console.log(JSON.stringify({ok:true,cases:10}));
})().catch(error=>{console.error(error);process.exitCode=1;});
