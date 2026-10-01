const fs=require('fs');
const vm=require('vm');
const assert=require('assert/strict');

const background=fs.readFileSync('browser_extension/background.js','utf8');
const start=background.indexOf('async function metaRedesignCall(');
const end=background.indexOf('const AI_RUN_ACTIONS =',start);
assert(start>=0&&end>start);
const source=background.slice(start,end);
const savedImage={image_relative:'generated/meta_repair_14_abcdef0123456789.jpg',
  image_sha256:'a'.repeat(64),image_name:'meta_repair_14_abcdef0123456789.jpg'};
const correctionRequest='Return exactly one complete JSON object for the video-prompt task about the NEW saved image: '
  +'video_prompt (string), needs_review (boolean), reason. Previous reply (data): {}';

function fixture(initialRepair={}) {
  const local={},session={},tabs=new Map(),calls=[],messages=[];
  let nextTab=40;
  const repair={id:'repair-14',phase:'prepared',provider:'chatgpt',ai_web_model:'auto',
    image_request:'Generate one new vertical scene image from this saved reference.',
    request:'Generate one new vertical scene image from this saved reference.',
    ...initialRepair};
  const pkg={job_id:'STORY-fixture',index:14,request_id:'req-14',context_id:'ctx-14',
    aspect_ratio:'9:16',image_relative:'generated/scene_14.png',stage:'redesigning',redesign:repair};
  const chrome={
    storage:{local:{get:async key=>({[key]:local[key]}),set:async values=>Object.assign(local,values)},
      session:{get:async key=>({[key]:session[key]}),set:async values=>Object.assign(session,values)}},
    tabs:{create:async options=>{const tab={id:++nextTab,url:options.url,status:'complete'};tabs.set(tab.id,tab);return tab;},
      update:async(id,options)=>Object.assign(tabs.get(id),options),
      get:async id=>{if(!tabs.has(id))throw Error('tab missing');return tabs.get(id);},
      sendMessage:async(id,message)=>{messages.push({id,message});return {ok:true};}},
    scripting:{executeScript:async()=>[{result:true}]},
  };
  const adapter={api:async(_path,body)=>{
    if(!body)return {package:pkg};
    calls.push(body);
    if(body.action==='claim'){
      if(repair.phase==='prepared'){repair.phase='requested';return {receipt:{redesign:repair,send_authorized:true}};}
      return {receipt:{redesign:repair,send_authorized:false}};
    }
    if(body.action==='save_image'){
      assert.equal(body.image,'data:image/png;base64,NEW');
      repair.phase='image_saved';repair.saved_image=savedImage;
      repair.prompt_request='Inspect the NEW saved image and return one matching video prompt with Thai dialogue.';
      repair.prompt_attempt=0;
      return {receipt:{redesign:repair}};
    }
    if(body.action==='save_prompt')return {receipt:{stage:'prepared',request_id:'new-meta'}};
    return {receipt:{redesign:repair}};
  }};
  const ownerStart=background.indexOf('async function isStoryRepairSendOwner(');
  const ownerEnd=background.indexOf('function freshFlowProgressMatches(',ownerStart);
  assert(ownerStart>=0&&ownerEnd>ownerStart);
  const restartWorker=()=>{
    const scope={BRIDGE:'http://127.0.0.1:8765',AI_WEB:{chatgpt:{url:'https://chatgpt.com/'}},
      chrome,getMetaVideoAdapter:()=>adapter,normalizeAIProvider:value=>value,URL,Number,String,Error};
    vm.runInNewContext(source+'\nthis.ensureMetaRedesign=ensureMetaRedesign;',scope);
    vm.runInNewContext(background.slice(ownerStart,ownerEnd)
      +'\nthis.isStoryRepairSendOwner=isStoryRepairSendOwner;',scope);
    return scope;
  };
  const scope=restartWorker();
  const key='smartflowMetaRedesign:repair-14';
  return {scope,restartWorker,local,session,tabs,calls,messages,repair,pkg,key};
}

(async()=>{
  const f=fixture();
  await f.restartWorker().ensureMetaRedesign(f.pkg);
  assert.equal(f.local[f.key].step,'image');
  assert.equal(f.local[f.key].request,f.repair.image_request);
  assert.equal(f.local[f.key].phase,'rewrite_sent');
  assert.equal(f.calls.filter(call=>call.action==='claim').length,1);
  assert.equal(f.messages.length,1);

  // The content script has a decoded, owned image. The desktop ACK must come
  // before the separate prompt helper can receive a dispatch.
  f.local[f.key]={...f.local[f.key],step:'prompt',phase:'image_ready',image:'data:image/png;base64,NEW',
    image_request:f.repair.image_request,helper_url:'https://chatgpt.com/c/owned'};
  await f.scope.ensureMetaRedesign(f.pkg);
  const imageCall=f.calls.findIndex(call=>call.action==='save_image');
  assert(imageCall>=0);
  assert.equal(f.messages.length,2);
  assert.equal(f.local[f.key].phase,'rewrite_sent');
  assert.equal(f.local[f.key].step,'prompt');
  assert.equal(f.local[f.key].image,undefined);
  assert.equal(f.local[f.key].request,f.repair.prompt_request);
  assert.equal(f.local[f.key].saved_image_url,
    'http://127.0.0.1:8765/api/stories/STORY-fixture/files/generated/meta_repair_14_abcdef0123456789.jpg');
  assert.equal(f.calls.filter(call=>call.action==='save_prompt').length,0);
  const tabId=f.local[f.key].helper_tab;
  const ownerMessage={job_id:f.pkg.job_id,run_id:f.local[f.key].run_id,
    provider:'chatgpt',expectedPrompt:f.local[f.key].request};
  assert.equal(await f.scope.isStoryRepairSendOwner(ownerMessage,tabId),true);
  f.local[f.key]={...f.local[f.key],request:correctionRequest,
    format_round:1,sent:true};
  assert.equal(await f.scope.isStoryRepairSendOwner({...ownerMessage,
    expectedPrompt:f.local[f.key].request},tabId),true,
  'one owned format correction must retain its desktop prompt owner');
  const imageCallsBeforeCorrection=f.calls.filter(call=>call.action==='save_image').length;
  const claimsBeforeCorrection=f.calls.filter(call=>call.action==='claim').length;
  const messagesBeforeCorrection=f.messages.length;
  await f.restartWorker().ensureMetaRedesign(f.pkg);
  assert.equal(f.local[f.key].phase,'rewrite_sent');
  assert.equal(f.local[f.key].request,correctionRequest);
  assert.equal(f.local[f.key].sent,true);
  assert.equal(f.messages.length,messagesBeforeCorrection+1);
  assert.equal(f.messages.at(-1).message.recover,true);
  assert.equal(f.calls.filter(call=>call.action==='save_image').length,imageCallsBeforeCorrection);
  assert.equal(f.calls.filter(call=>call.action==='claim').length,claimsBeforeCorrection);
  assert.equal(f.calls.filter(call=>call.action==='save_prompt').length,0);
  f.local[f.key].format_round=2;
  assert.equal(await f.scope.isStoryRepairSendOwner({...ownerMessage,
    expectedPrompt:f.local[f.key].request},tabId),false,
  'a second format correction has no Send authority');
  f.local[f.key].format_round=1;
  f.repair.prompt_attempt=1;
  assert.equal(await f.scope.isStoryRepairSendOwner({...ownerMessage,
    expectedPrompt:f.local[f.key].request},tabId),false,
  'an old helper cannot Send after a new explicit Continue attempt');
  f.repair.prompt_attempt=0;
  assert.equal(await f.scope.isStoryRepairSendOwner(ownerMessage,tabId+1),false);
  f.local[f.key]={...f.local[f.key],phase:'ready',sent:true,
    proposal:{needs_review:false,video_prompt:'Animate the new saved scene with slow camera motion.'}};
  await f.scope.ensureMetaRedesign(f.pkg);
  assert.equal(f.calls.filter(call=>call.action==='save_prompt').length,1);
  assert.equal(f.local[f.key].phase,'committed');
  assert.equal(f.calls.find(call=>call.action==='save_prompt').image,undefined);

  // Browser restart after the desktop image ACK reconstructs only stage two.
  const restarted=fixture({phase:'image_saved',saved_image:savedImage,
    prompt_request:'Inspect the NEW saved image and return one matching video prompt with Thai dialogue.',
    prompt_attempt:0});
  await restarted.scope.ensureMetaRedesign(restarted.pkg);
  assert.equal(restarted.local[restarted.key].step,'prompt');
  assert.equal(restarted.local[restarted.key].prompt_fresh_tab,true);
  assert.equal(restarted.calls.filter(call=>call.action==='save_image').length,0);
  assert.equal(restarted.calls.filter(call=>call.action==='claim').length,0);

  // A stale image owner cannot issue another Send after stage one is saved.
  const stale=fixture({phase:'requested'});
  await stale.scope.ensureMetaRedesign(stale.pkg);
  assert.equal(stale.local[stale.key].phase,'needs_review');
  assert.equal(stale.messages.length,0);

  // Only an explicit desktop prompt_attempt increment rearms a terminal
  // prompt review; no second image is requested.
  const retry=fixture({phase:'image_saved',saved_image:savedImage,
    prompt_request:'Inspect the NEW saved image and return one matching video prompt with Thai dialogue.',
    prompt_attempt:0});
  await retry.scope.ensureMetaRedesign(retry.pkg);
  const oldTab=retry.local[retry.key].helper_tab;
  retry.local[retry.key]={...retry.local[retry.key],phase:'needs_review',step:'prompt',sent:true,
    request:correctionRequest,format_round:1,
    error:'Prompt answer completed but invalid'};
  await retry.scope.ensureMetaRedesign(retry.pkg);
  assert.equal(retry.messages.length,1);
  retry.repair.prompt_attempt=1;
  await retry.scope.ensureMetaRedesign(retry.pkg);
  assert.equal(retry.local[retry.key].prompt_attempt,1);
  assert.equal(retry.local[retry.key].prompt_fresh_tab,true);
  assert.equal(retry.local[retry.key].format_round,0);
  assert.equal(retry.local[retry.key].request,retry.repair.prompt_request);
  assert.equal(retry.local[retry.key].sent,false);
  assert.notEqual(retry.local[retry.key].helper_tab,oldTab);
  assert.equal(retry.calls.filter(call=>call.action==='save_image').length,0);
  assert.equal(retry.calls.filter(call=>call.action==='claim').length,0);

  console.log('Meta two-stage background: image ACK precedes prompt, restart/retry and stale owner guards passed');
})().catch(error=>{console.error(error);process.exit(1);});
