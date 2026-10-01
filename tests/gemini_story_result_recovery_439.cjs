// Actual-source Gemini Story result and receipt recovery. No browser/provider calls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0&&b>a,`${start} source bounds`);return source.slice(a,b);};
const URL='https://gemini.google.com/app/aaaaaaaaaaaaaaaa';
const prompt='Create exactly one image for scene 4.';
let now=1000;
const user={innerText:`คุณบอกว่า ${prompt}`,textContent:`คุณบอกว่า ${prompt}`,
  compareDocumentPosition:()=>4,contains:()=>false,closest:()=>container};
const answer={innerText:'',textContent:''};
const image={src:'https://lh3.googleusercontent.com/scene4',complete:true,naturalWidth:1024,naturalHeight:1792,
  closest:()=>null};
const container={id:'bbbbbbbbbbbbbbbb',contains:node=>[user,answer,image].includes(node)};
let users=[user],images=[image],reply={text:'',busy:false,completed:true},sleepHook=null;
const data={},messages=[];let pendingOnce=false,vetoOnce=false;
const c=vm.createContext({IS_GEMINI:true,PROVIDER_KEY:'gemini',activeJobId:'STORY-GEMINI-439',
  activeRunId:'RUN-A',cancelRequested:false,geminiStoryRedoGuard:null,location:{href:URL},
  Node:{DOCUMENT_POSITION_FOLLOWING:4},Date:{now:()=>now},crypto:{randomUUID:()=>`nonce-${now}`},
  document:{},stopButtonVisible:()=>false,userTurns:()=>users,
  generatedImageElements:scope=>scope===container?images:[],motionResponseState:()=>reply,
  geminiTextRequestHash:()=> 'exact-hash',
  geminiTextRequestSnapshot:(_prompt,owner)=>owner?.request_container_id && owner.request_container_id!==container.id
    ? {reason:'request_owner_changed'} : {reason:'owned_request',user,turn:answer,
      owner:{conversation_url:URL,request_container_id:container.id,request_index:users.length-1,prompt_hash:'exact-hash'}},
  storyImageRefusal:value=>/policy/i.test(value),storyImageReferenceRequest:()=>false,
  confirmedStoryImageServiceError:value=>/^Something went wrong$/.test(value),
  sameStoryImageReceipt:(a,b)=>JSON.stringify(a)===JSON.stringify(b),
  storyImageRecoveryError:(code,_index,message)=>Object.assign(Error(message),{code}),
  assertNotCancelled:()=>{},sleep:async ms=>{now+=ms;if(sleepHook)sleepHook();},report:async()=>{},
  composer:()=>null,composerText:()=>'',geminiComposerAttachmentState:()=>({count:0,busy:false}),
  recoverOwnedStoryImage:async()=>null,waitStoryImageServiceRetry:async()=>{},imageDataFromUrl:async()=> 'data:image/png;base64,SU1BR0U=',
  chrome:{runtime:{id:'extension-id',sendMessage:async message=>{messages.push(message);
    if(pendingOnce){pendingOnce=false;return {ok:false,pending:true};}
    if(vetoOnce){vetoOnce=false;data[key]={...data[key],fresh_restart:{version:1,provider:'gemini',
      token:'one-allocation',run_id:'RUN-A',phase:'created',archive:key+':failed:one-allocation'}};
      images=[image];reply={text:'',busy:false,completed:true};
      return {ok:false,refresh_scheduled:false,retry_safe:true,refresh_reason:'live_guard_changed'};}
    return {ok:true,refresh_scheduled:true};}},
    storage:{local:{get:async key=>({[key]:data[key]}),set:async value=>Object.assign(data,value)}}}
});
vm.runInContext(part('  function geminiStoryImageSnapshot(', '  function geminiTextRequestReview(')
  +part('  function createStoryImageReceipt(', '  function largeAssistantImages('),c);
const proof={prompt,conversation_url:URL,request_container_id:container.id,request_index:0,prompt_hash:'exact-hash'};
const pkg={job:{id:'STORY-GEMINI-439'},request:{},image_urls:[],browser_recovery:{version:1}};
const identity=[prompt,'style','scene',null],key='smartpostStoryGeneratedImage:gemini:STORY-GEMINI-439:4';
const seed=(status,extra={})=>{data[key]={version:1,job_id:pkg.job.id,provider:'gemini',scene_index:4,
  identity:JSON.stringify([identity,[],0]),run_id:'RUN-A',review_revision:0,created_at:now,
  status,result_proof:proof,...extra};};
(async()=>{
  let cases=0;
  assert.equal(c.geminiStoryImageSnapshot(proof).reason,'image_ready');cases++;
  assert.equal(c.geminiStoryImageSnapshot({...proof,conversation_url:'https://gemini.google.com/app/other'}).reason,'wrong_conversation');cases++;
  assert.equal(c.geminiStoryImageSnapshot({...proof,before_user_count:1}).reason,'request_missing');cases++;
  const other={...image,src:'https://lh3.googleusercontent.com/scene4b'};
  images=[image,{...image,complete:false,naturalWidth:0,naturalHeight:0}];
  assert.equal(c.geminiStoryImageSnapshot(proof).image,image,'decoded duplicate URL layer wins loading placeholder');cases++;
  images=[other,image];
  assert.equal(c.geminiStoryImageSnapshot(proof).image.src,image.src,'deterministic owned selection');cases++;
  assert.equal(c.geminiStoryImageSnapshot({...proof,selected_image_asset_key:other.src}).image.src,other.src,'saved selection wins DOM order');cases++;
  assert.equal(c.geminiStoryImageSnapshot({...proof,selected_image_asset_key:'missing'}).reason,'image_loading','missing chosen asset cannot switch');cases++;
  assert.equal(c.geminiStoryImageSnapshot({...proof,before_image_assets:[image.src]}).image.src,other.src,'uploaded/earlier source URL excluded');cases++;
  image.complete=false;
  assert.equal(c.geminiStoryImageSnapshot(proof).image.src,other.src,'choose decoded alternative');cases++;
  image.complete=true;
  seed('awaiting_result');
  reply={text:'',busy:true,completed:false};const busyStarted=now;
  sleepHook=()=>{images=[image,other];if(now-busyStarted>75000)reply={text:'',busy:false,completed:true};};
  assert.equal(await c.createStoryImageReceipt(pkg,4,identity,3).restore(),'data:image/png;base64,SU1BR0U=');
  assert.equal(data[key].result_proof.selected_image_asset_key,image.src,'selection ACK is durable before collection');
  assert(now-busyStarted>=79500,'real generation and stable idle finish before save');cases++;
  sleepHook=null;
  images=[other];reply={text:'',busy:false,completed:true};
  seed('awaiting_result',{result_proof:{...proof,selected_image_asset_key:image.src}});
  const idleMissingStarted=now;
  await assert.rejects(c.createStoryImageReceipt(pkg,4,identity,3).restore(),/GEMINI_IMAGE_RESULT_IMAGE_LOADING/);
  assert(now-idleMissingStarted>=59000 && now-idleMissingStarted<=60000,'missing pinned idle asset returns bounded review');
  assert.equal(data[key].result_proof.selected_image_asset_key,image.src);cases++;
  seed('awaiting_result',{result_proof:{...proof,selected_image_asset_key:image.src}});
  reply={text:'',busy:true,completed:false};const missingBusyStarted=now;
  sleepHook=()=>{if(now-missingBusyStarted>75000){images=[image,other];reply={text:'',busy:false,completed:true};}};
  assert.equal(await c.createStoryImageReceipt(pkg,4,identity,3).restore(),'data:image/png;base64,SU1BR0U=');
  assert(now-missingBusyStarted>=79500,'missing pinned asset keeps waiting during real generation and then stabilizes');cases++;
  sleepHook=null;
  images=[];reply={text:'Something went wrong',busy:false,completed:true};
  assert.equal(c.geminiStoryImageSnapshot(proof).reason,'no_image');cases++;
  assert.equal(c.geminiStoryTechnicalFailure('Something went wrong'),true);cases++;
  assert.equal(c.geminiStoryTechnicalFailure('policy: Something went wrong'),false);cases++;
  assert.equal(c.geminiStoryTechnicalFailure('Something went wrong. Credits exhausted'),false);cases++;
  images=[image];reply={text:'',busy:false,completed:true};seed('awaiting_result');
  const saved=c.createStoryImageReceipt(pkg,4,identity,3);
  assert.equal(await saved.restore(),'data:image/png;base64,SU1BR0U=');
  assert.equal(data[key].status,'generated');cases++;
  seed('awaiting_result',{result_proof:{...proof,conversation_url:'https://gemini.google.com/app/other'}});
  await assert.rejects(c.createStoryImageReceipt(pkg,4,identity,3).restore(),/GEMINI_IMAGE_RESULT_WRONG_CONVERSATION/);cases++;
  images=[];reply={text:'Something went wrong',busy:false,completed:true};seed('completed_no_image',{response_excerpt:'Something went wrong'});
  const retry=c.createStoryImageReceipt(pkg,4,identity,3);
  assert.equal(await retry.restore(),null);
  assert.equal(data[key].send_phase,'prepared');assert.equal(data[key].service_retry_count,1);
  assert.equal(data[key].resume_image_prompt,prompt);assert(data[key].retry_parent.archive in data);cases++;
  const nonce=data[key].gemini_generation_nonce;
  const resumed=c.createStoryImageReceipt(pkg,4,identity,3);
  assert.equal(await resumed.restore(),null);await resumed.begin();
  assert.equal(data[key].gemini_generation_nonce,nonce,'prepared successor survives re-entry');cases++;
  await resumed.dispatching(prompt,{conversation_url:URL,before_user_count:1});
  await assert.rejects(c.createStoryImageReceipt(pkg,4,identity,3).restore(),/GEMINI_IMAGE_RESULT_REQUEST_MISSING/);
  assert.equal(data[key].send_phase,'dispatching','unknown Send must not become a second successor');cases++;
  seed('completed_no_image',{send_phase:'accepted',send_nonce:'accepted-2',response_excerpt:'Something went wrong',
    service_retry_count:1});
  const clean=c.createStoryImageReceipt(pkg,4,identity,3);
  await assert.rejects(clean.restore(),error=>error.code==='STORY_IMAGE_REFRESH_SCHEDULED');
  assert.equal(messages.at(-1).type,'RESTART_FAILED_GEMINI_STORY_IMAGE');
  assert.equal(data[key].gemini_restart_evidence.stable_samples>=3,true);
  assert.equal(data[key].gemini_restart_evidence.observed_at-data[key].gemini_restart_evidence.stable_since>=2000,true);cases++;
  const evidence=data[key].gemini_restart_evidence;
  assert.equal(c.geminiStoryRedoGuard({job_id:pkg.job.id,run_id:'RUN-A',index:4,
    receipt_identity:data[key].identity,send_nonce:'accepted-2',evidence}),true);cases++;
  images=[image];assert.equal(c.geminiStoryRedoGuard({job_id:pkg.job.id,run_id:'RUN-A',index:4,
    receipt_identity:data[key].identity,send_nonce:'accepted-2',evidence}),false,'late media vetoes a new Send');cases++;
  images=[];const token='fresh-token',archive=key+':failed:'+token;
  data[archive]={...data[key]};data[key]={...data[key],fresh_restart:{version:1,provider:'gemini',
    token,run_id:'RUN-A',phase:'starting',archive}};
  c.location.href='https://gemini.google.com/app';users=[];
  const freshPkg={...pkg,fresh_image_restart:{provider:'gemini',index:4,token}};
  const fresh=c.createStoryImageReceipt(freshPkg,4,identity,3);
  assert.equal(await fresh.restore(),null);
  assert.equal(data[key].status,'awaiting_result');assert.equal(data[key].send_phase,'prepared');
  assert.equal(data[key].fresh_restart.phase,'consumed');assert.equal(data[key].gemini_generation_nonce,token);
  assert.equal(data[key].retry_parent.proof.prompt,prompt);assert.equal(data[key].resume_image_prompt,prompt);cases++;
  assert.equal(await c.createStoryImageReceipt(freshPkg,4,identity,3).restore(),null,
    'prepared new root can restore without reading the failed old conversation');cases++;
  c.location.href=URL;users=[user];images=[];pendingOnce=true;
  seed('completed_no_image',{send_phase:'accepted',send_nonce:'accepted-3',response_excerpt:'Something went wrong',
    service_retry_count:1});
  const before=messages.length;
  await assert.rejects(c.createStoryImageReceipt(pkg,4,identity,3).restore(),error=>error.code==='STORY_IMAGE_REFRESH_SCHEDULED');
  assert.equal(messages.length-before,2,'pending handoff repeats the same receipt RPC, not a second user Send');cases++;
  seed('completed_no_image',{send_phase:'accepted',send_nonce:'accepted-4',response_excerpt:'Something went wrong',
    service_retry_count:1});vetoOnce=true;
  assert.equal(await c.createStoryImageReceipt(pkg,4,identity,3).restore(),'data:image/png;base64,SU1BR0U=',
    'late media after a durable allocation is read from the original request');
  assert.equal(data[key].status,'generated');assert.equal(data[key].fresh_restart.token,'one-allocation');cases++;
  // Execute the actual initial collector too: exact accepted owner, durable
  // selection, reordering while busy, then idle collection with no Stop call.
  Object.assign(c,{waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>{},
    waitForComposer:async()=>({}),lastUserTurnSignature:()=>'',chatGPTConversationFrames:()=>[],
    assistantTurns:()=>[answer],setComposerText:async editor=>editor,sendButton:()=>({}),
    recordStoryImageRequest:async()=>{},revealChatGPTAnswer:async()=>{},conversationTurnNumber:()=>0,
    motionRequestIsLatestUser:()=>true,latestAssistantStrictlyAfterLatestUser:()=>answer,
    imageGenerationSignature:()=>'',storyImageNoResultReady:()=>false,AI_NAME:'Gemini',
    storyTurnNumber:()=>0,storyImageAssetKey:image=>String(image?.src||image),
    sendGeminiImageAndVerify:async()=>{users=[user];images=[other,image];reply={text:'',busy:true,completed:false};},
    stopButtonVisible:()=>reply.busy});
  vm.runInContext(part('  async function submitImagePrompt(', '  async function imageData('),c);
  users=[];images=[];reply={text:'',busy:false,completed:true};const initialStarted=now;let pinned='';
  sleepHook=()=>{if(users.length){images=[image,other];if(now-initialStarted>20000)reply={text:'',busy:false,completed:true};}};
  const collected=await c.submitImagePrompt(prompt,[],3,'',{scene_index:4,onSubmitted:async(_text,owner)=>{
    if(owner.selected_image_asset_key)pinned=owner.selected_image_asset_key;
  }});
  assert.equal(collected.src,image.src);assert.equal(pinned,image.src);assert(now-initialStarted>20000);cases++;
  sleepHook=null;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
