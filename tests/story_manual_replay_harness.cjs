// Exercise the real receipt transition without a provider Send.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const start=source.indexOf('  function createStoryImageReceipt(');
const end=source.indexOf('  async function imageDataFromUrl(',start);
assert(start>=0 && end>start);
const clone=value=>JSON.parse(JSON.stringify(value));
async function fixture({draft='prompt',request='request_missing',attachment=1}={}){
  const token='11111111-2222-4333-8444-555555555555',key='smartpostStoryGeneratedImage:chatgpt:STORY-TEST:2';
  const identity=JSON.stringify([['scene','style','content',null],[],1]);
  const prior={version:1,job_id:'STORY-TEST',provider:'chatgpt',scene_index:2,identity,
    run_id:'RUN-OLD',review_revision:0,created_at:Date.now()-60000,status:'awaiting_result',
    send_phase:'dispatching',send_nonce:'OLD-NONCE',previous_scene_reference_index:1,
    result_proof:{prompt:'prompt',conversation_url:'https://chatgpt.com/c/test'}};
  const storage={[key]:clone(prior)},events=[],sleeps=[];
  const pkg={job:{id:'STORY-TEST',manual_image_replay:{version:1,scene_index:2,token,max_sends:1}},
    image_urls:['saved scene 1']};
  // The identity includes source images, not the checkpoint image URL.
  prior.identity=JSON.stringify([['scene','style','content',null],[],1]);storage[key]=clone(prior);
  const context=vm.createContext({PROVIDER_KEY:'chatgpt',activeRunId:'RUN-NEW',
    location:{href:'https://chatgpt.com/c/test'},Date,JSON,String,Number,Boolean,Math,RegExp,Set,
    assertNotCancelled:()=>{},sameStoryImageReceipt:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
    storyImageRecoveryError:(code,index,message)=>Object.assign(Error(message),{code}),
    chrome:{storage:{local:{get:async name=>typeof name==='string'?{[name]:clone(storage[name]??null)}:clone(storage),
      set:async value=>Object.assign(storage,clone(value))}}},
    document:{querySelectorAll:()=>[]},
    composer:()=>({}),composerText:()=>draft,stopButtonVisible:()=>false,
    chatGPTComposerAttachmentState:()=>({count:attachment,busy:false,failed:false}),
    chatGPTStoryRequest:()=>({reason:request,frame:null}),
    sleep:async ms=>sleeps.push(ms),report:async(...value)=>events.push(value),
    createStorySameChatReminder:()=>({}),crypto:require('node:crypto').webcrypto});
  vm.runInContext(source.slice(start,end),context);
  const receipt=context.createStoryImageReceipt(pkg,2,['scene','style','content',null],1);
  return {receipt,storage,key,token,events,sleeps,prior};
}
(async()=>{
  let f=await fixture();
  await f.receipt.restore();
  assert.equal(f.sleeps.length,2);
  assert.equal(f.storage[f.key].send_phase,'prepared');
  assert.equal(f.storage[f.key].run_id,'RUN-NEW');
  assert.equal(f.storage[f.key].manual_replay_token,f.token);
  assert.deepEqual(f.storage[f.key+':manual-replay:'+f.token],f.prior);
  await f.receipt.begin();
  assert.equal(f.storage[f.key].manual_replay_token,f.token);
  await f.receipt.restore();
  assert.equal(f.sleeps.length,2,'same authorization cannot prepare a second replay');
  f=await fixture({attachment:0});
  await f.receipt.restore();
  assert.equal(f.storage[f.key].send_phase,'prepared','missing reference is prepared for guarded checkpoint reattach');
  f=await fixture({draft:'changed'});
  await assert.rejects(f.receipt.restore(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW');
  assert.equal(f.events.at(-1)[3].replay_review_reason,'draft_changed');
  assert.equal(f.storage[f.key].send_phase,'dispatching');
  assert.equal(f.storage[f.key+':manual-replay:'+f.token],undefined);
  f=await fixture({request:'request_found'});
  await assert.rejects(f.receipt.restore(),error=>error.code==='STORY_IMAGE_RECEIPT_REVIEW');
  assert.equal(f.events.at(-1)[3].replay_review_reason,'request_found');
  assert.equal(f.storage[f.key].send_phase,'dispatching');
  process.stdout.write(JSON.stringify({ok:true,cases:4}));
})().catch(error=>{console.error(error);process.exitCode=1;});
