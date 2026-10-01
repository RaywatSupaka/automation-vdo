// Offline regression for a refreshed Story image page whose original collector
// is still running. A second START is an idempotent attach, never a new Send.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/background.js'),'utf8');
const start=source.indexOf('async function startAIWebJob(');
const end=source.indexOf('\nasync function cancelChatGPTJob(',start);
assert(start>=0&&end>start);
const fn=source.slice(start,end);
async function run(activeRunId){
  const jobId='STORY-OFFLINE',runId='RUN-EXACT',url='https://chatgpt.com/c/exact';
  const tabKey=`smartpostAIWebTab:chatgpt:${jobId}`;
  const storage={[tabKey]:7};let sends=0,creates=0,presses=0;
  const context=vm.createContext({
    BRIDGE:'http://local.invalid',
    AI_WEB:{chatgpt:{name:'ChatGPT',url:'https://chatgpt.com/',matches:['https://chatgpt.com/*']}},
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:{job:{id:jobId,image_ai_provider:'chatgpt'},
      ai_resume:{required:true,provider:'chatgpt',conversation_url:url,stage:'image'},run_id:runId}})}),
    normalizeAIProvider:value=>value||'chatgpt',
    isWebLoginUrl:()=>false,
    waitForAIRefreshReady:async(_id,guard)=>guard(),
    chrome:{storage:{local:{get:async()=>storage,set:async values=>Object.assign(storage,values)}},
      tabs:{get:async()=>({id:7,url}),update:async()=>{},create:async()=>{creates++;throw Error('fresh tab not allowed');},
        sendMessage:async(_id,message)=>{
          sends++;
          assert.equal(message.type,'START_CHATGPT_JOB');
          assert.equal(message.accept_existing_run,true);
          assert.equal(message.package.run_id,runId);
          if(activeRunId!==runId)return {ok:false,code:'AI_WEB_JOB_BUSY',job_id:jobId,
            run_id:activeRunId,cancel_requested:false,error:'กำลังทำงานอื่นอยู่'};
          return {ok:true,started:false,already_running:true};
        }},
      scripting:{executeScript:async()=>{presses++;}}},
  });
  vm.runInContext(fn,context);
  const guard=async id=>{if(id!==undefined)assert.equal(id,7);};
  if(activeRunId===runId){
    const result=await context.startAIWebJob(jobId,true,'chatgpt',false,runId,guard);
    assert.equal(result.tabId,7);
  }else await assert.rejects(()=>context.startAIWebJob(jobId,true,'chatgpt',false,runId,guard),
    error=>error.code==='AI_WEB_JOB_BUSY'&&error.jobId===jobId);
  assert.equal(sends,1);assert.equal(creates,0);assert.equal(presses,1);
}
(async()=>{await run('RUN-EXACT');await run('RUN-OTHER');console.log(JSON.stringify({ok:true,cases:2}));})()
  .catch(error=>{console.error(error);process.exitCode=1;});
