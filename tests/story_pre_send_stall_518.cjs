const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('browser_extension/background.js','utf8');
const start=source.indexOf('async function recoverStalledStoryPreSend(');
const end=source.indexOf('\nasync function cancelChatGPTJob(',start);
assert(start>0 && end>start);
const body=source.slice(start,end);
const JOB='STORY-TEST',RUN='RUN-TEST',key=`smartpostStoryGeneratedImage:chatgpt:${JOB}:6`;
const tabKey=`smartpostAIWebTab:chatgpt:${JOB}`;
const receipt={version:1,job_id:JOB,provider:'chatgpt',scene_index:6,run_id:RUN,
  status:'awaiting_result',send_phase:'prepared',send_nonce:'',result_proof:null,image_url:'',
  prepared_conversation:'https://chatgpt.com/c/owned',created_at:1,
  pre_send_audit:{prompt:'scene 6',source_count:1,conversation_url:'https://chatgpt.com/c/owned',
    user_turn_count:5,last_user_signature:'scene 5',prepared_at:2}};

async function scenario(change={}){
  const rows={[key]:{...receipt,...change.receipt},[tabKey]:21,
    [`smartpostChatGPTTab:${JOB}`]:21,[`run:${JOB}`]:RUN};
  if(change.dispatch)rows[key+':dispatch']='nonce';
  if(change.initialClaim)rows[key+':stall-recovery']={job_id:JOB,run_id:RUN};
  let reloads=0,starts=0,probes=0;
  const chrome={storage:{local:{get:async keys=>Object.fromEntries(keys.map(k=>[k,rows[k]])),
    set:async value=>Object.assign(rows,value)}},tabs:{get:async()=>({url:'https://chatgpt.com/c/owned',status:'complete'}),
    sendMessage:async(_id,msg)=>{probes++;
      if(msg.claim && change.raceDispatch)rows[key+':dispatch']='late-nonce';
      return change.probe||{ok:true,claimed:msg.claim===true};},
    reload:async()=>{reloads++;}}};
  const context={chrome,BRIDGE:'http://bridge',aiRunStorageKey:id=>`run:${id}`,
    normalizeAIProvider:()=> 'chatgpt',setTimeout:(fn,ms)=>ms===1500?(fn(),0):setTimeout(fn,ms),clearTimeout,
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:{job:{image_ai_provider:'chatgpt',scene_count:6},
      checkpoint_images:[1,2,3,4,5].map(index=>({index}))}})}),
    startAIWebJob:async()=>{starts++;return {ok:true};}};
  vm.createContext(context);vm.runInContext(body,context);
  let error='';try{await context.recoverStalledStoryPreSend(JOB,RUN);}catch(e){error=e.message;}
  return {error,reloads,starts,probes,rows};
}

(async()=>{
  const good=await scenario();assert.equal(good.error,'');assert.equal(good.reloads,1);
  assert.equal(good.starts,1);assert.equal(good.probes,2);
  const duplicate=await scenario({initialClaim:true});assert.equal(duplicate.error,'');
  assert.equal(duplicate.reloads,0);assert.equal(duplicate.probes,0);
  const accepted=await scenario({receipt:{send_phase:'accepted',send_nonce:'nonce'}});
  assert.match(accepted.error,/REVIEW/);assert.equal(accepted.reloads,0);
  const dispatched=await scenario({dispatch:true});assert.match(dispatched.error,/REVIEW/);
  assert.equal(dispatched.reloads,0);
  const edited=await scenario({probe:{ok:false,reason:'draft_changed'}});
  assert.match(edited.error,/draft_changed/);assert.equal(edited.reloads,0);
  const late=await scenario({raceDispatch:true});assert.match(late.error,/REVIEW/);
  assert.equal(late.reloads,0);assert.equal(late.starts,0);
  console.log('story pre-send stall: 6 guarded scenarios passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
