const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const text=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const source=text.slice(text.indexOf('  async function runMetaRedesignHelper('),text.indexOf('  async function runSceneRepairHelper('));
async function helperCase({step='image',sent=false,missing=false,malformed=false,malformedForever=false,resumeMalformed=false,needsReview=false,
  answerOverride='',imageAnswer='',runPrompt=true,freshPromptTab=false}={}){
  const imageRequest='Generate exactly one NEW illustration now from the prior image, with no JSON.';
  let lastRequest=missing?'different request':imageRequest,turn=resumeMalformed?{innerText:'{}'}:null,sends=0,images=0,promptRefs=[];
  let record={step,sent,request:imageRequest,image_urls:['source.png'],redesign_id:'revision'};
  const proposal={needs_review:needsReview,video_prompt:'Walk slowly across the room with ordinary camera motion.'};
  const image={currentSrc:'new.png',complete:true,naturalWidth:720,naturalHeight:1280};
  const scope={JSON,Number,String,location:{href:'https://chatgpt.com/c/new'},IS_GEMINI:false,
    revealChatGPTAnswer:async()=>{},motionRequestIsLatestUser:r=>r===lastRequest,
    stopButtonVisible:()=>false,sleep:async()=>{},assertNotCancelled:()=>{},
    latestAssistantStrictlyAfterLatestUser:()=>turn,alternativeImageReply:()=>turn,
    storyImageAssetKey:i=>i.currentSrc,generatedImageElements:t=>t?.image?[image]:[],
    userTurns:()=>[],composerText:()=>'',chatGPTComposerAttachmentState:()=>({count:0}),
    ensureAiWebModel:async()=>{},
    explicitAnalysisRefusal:()=>false,storyImageRefusal:()=>false,
    submitPrompt:async(r,refs=[])=>{assert.equal(record.sent,true);sends++;promptRefs.push(refs);
      if(sends>2)throw Error('unexpected third Meta helper Send');
      lastRequest=r;turn={innerText:answerOverride||(malformedForever||malformed&&sends===1?'{}':JSON.stringify(proposal))};return turn;},
    submitImagePrompt:async(r,refs,_count,_strict,_context,_index,wait)=>{
      assert.equal(record.sent,true);assert.equal(r,imageRequest);assert.equal(refs[0],'source.png');
      images++;lastRequest=r;turn=imageAnswer?{innerText:imageAnswer}:{innerText:'',image:true};return wait();},
    imageData:async()=> 'data:image/png;base64,new'};
  vm.runInNewContext(source+'\nthis.run=runMetaRedesignHelper',scope);
  let error;
  try{await scope.run(record,async patch=>{record={...record,...patch};});}catch(e){error=e;}
  const afterImage={...record};
  if(!error && record.phase==='image_ready' && runPrompt){
    // This state transition represents the separate desktop save_image ACK.
    // A video-prompt Send must never happen before this durable checkpoint.
    assert.equal(sends,0);assert.equal(record.image,'data:image/png;base64,new');
    record={...record,phase:'rewrite_sent',step:'prompt',sent:resumeMalformed,
      request:'Write a video prompt for the NEW saved image.',
      saved_image_url:'http://127.0.0.1:8765/api/stories/test/files/generated/new.jpg',
      prompt_fresh_tab:freshPromptTab,format_round:resumeMalformed?1:0};
    if(resumeMalformed){lastRequest=record.request;turn={innerText:'{}'};}
    try{await scope.run(record,async patch=>{record={...record,...patch};});}catch(e){error=e;}
  }
  return {record,afterImage,sends,images,promptRefs,error};
}
(async()=>{
  let value=await helperCase({malformed:true});assert.ifError(value.error);
  assert.equal(value.sends,2);assert.equal(value.images,1);assert.equal(value.record.phase,'ready');
  assert.equal(value.afterImage.phase,'image_ready');
  assert.equal(value.record.proposal.video_prompt,proposalPrompt());
  assert.equal(value.promptRefs[0][0],'http://127.0.0.1:8765/api/stories/test/files/generated/new.jpg');
  value=await helperCase({malformedForever:true});assert(value.error);
  assert.match(value.error.message,/หลังจัดรูปแบบหนึ่งครั้ง/);
  assert.equal(value.sends,2);assert.equal(value.images,1);assert.equal(value.record.format_round,1);
  assert.equal(value.afterImage.phase,'image_ready');
  value=await helperCase({resumeMalformed:true});assert(value.error);
  assert.match(value.error.message,/หลังจัดรูปแบบหนึ่งครั้ง/);
  assert.equal(value.sends,0);assert.equal(value.images,1);
  value=await helperCase({answerOverride:'quota reached'});assert(value.error);
  assert.equal(value.sends,1);assert.equal(value.images,1);assert.equal(value.afterImage.phase,'image_ready');
  value=await helperCase({sent:true,missing:true});assert.equal(value.sends,0);assert.equal(value.images,0);
  value=await helperCase({step:'proposal'});assert(value.error);
  assert.equal(value.sends,0);assert.equal(value.images,0);
  value=await helperCase({needsReview:true});assert(value.error);assert.equal(value.images,1);
  assert.equal(value.afterImage.phase,'image_ready');
  value=await helperCase({imageAnswer:'AI cannot create a new image.'});assert(value.error);
  assert.equal(value.sends,0);assert.equal(value.images,1);
  value=await helperCase({runPrompt:false});assert.ifError(value.error);
  assert.equal(value.record.phase,'image_ready');assert.equal(value.sends,0);
  value=await helperCase({freshPromptTab:true});assert.ifError(value.error);
  assert.equal(value.record.phase,'ready');
  const adapterSource=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
  const sandbox={URL,Date,console};vm.runInNewContext(adapterSource.replaceAll('export ','')+'\nthis.Adapter=MetaVideoAdapter;',sandbox);
  let repairs=0,saved=0,opened=0;
  const current={job_id:'STORY-test',index:1,request_id:'old',context_id:'old-context',stage:'redesigning'};
  const adapter=new sandbox.Adapter({api:async()=>({package:current}),redesign:async()=>repairs++,chromeAPI:{}});
  adapter.save=async()=>saved++;
  await adapter.step({...current});assert.equal(repairs,1);
  current.request_id='new';current.context_id='new-context';current.redesign_previous_request_id='old';
  adapter.open=async()=>opened++;
  const old={job_id:'STORY-test',index:1,request_id:'old',context_id:'old-context'};
  await adapter.step(old);assert.equal(opened,1);assert.equal(old.closed,true);assert.equal(old.superseded_by,'new');
  const openedUrls=[];let redesignCalls=0;
  let freshPackage={job_id:'STORY-test',index:14,request_id:'fresh-repair',context_id:'same-source',
    stage:'redesigning',redesign:{id:'fresh-helper',phase:'prepared'},
    redesign_previous_request_id:'old-repair'};
  const freshAdapter=new sandbox.Adapter({api:async()=>({package:freshPackage}),
    redesign:async()=>{redesignCalls++;},chromeAPI:{tabs:{create:async options=>{
      openedUrls.push(options.url);return {id:77,url:options.url};}}}});
  freshAdapter.records=async()=>({});freshAdapter.save=async()=>{};freshAdapter.own=async()=>{};
  await freshAdapter.open({job_id:'STORY-test',shot_index:14});
  assert.equal(redesignCalls,1);assert.deepEqual(openedUrls,[],
    'a fresh redesign must open its AI helper before any old Meta conversation');
  freshPackage={...freshPackage,request_id:'new-video',context_id:'new-image-context',
    stage:'prepared',redesign:undefined,redesign_previous_request_id:'fresh-repair'};
  await freshAdapter.open({job_id:'STORY-test',shot_index:14});
  assert.deepEqual(openedUrls,['https://www.meta.ai/'],
    'after the new image and prompt, Meta must open Home, not the old /prompt URL');
  const background=fs.readFileSync('browser_extension/background.js','utf8');
  const redesignSource=background.slice(background.indexOf('async function ensureMetaRedesign(pkg)') ,background.indexOf('const AI_RUN_ACTIONS ='));
  for(const aspect of ['16:9','9:16']){
    const saved={},stop=Error('stop after helper row is saved');
    const rowScope={BRIDGE:'http://127.0.0.1:8765',chrome:{storage:{local:{
      get:async key=>({[key]:saved[key]}),set:async data=>Object.assign(saved,data)}}},
      metaRedesignCall:async()=>{throw stop;}};
    vm.runInNewContext(redesignSource+'\nthis.ensure=ensureMetaRedesign;',rowScope);
    await assert.rejects(()=>rowScope.ensure({job_id:'STORY-test',index:1,request_id:'old',context_id:'ctx',
      aspect_ratio:aspect,image_relative:'generated/scene_01.png',redesign:{id:`repair-${aspect}`,
        provider:'chatgpt',ai_web_model:'auto',failure_reason:'technical_redesign',request:'original'}}),error=>error===stop);
    assert.equal(saved[`smartflowMetaRedesign:repair-${aspect}`].aspect_ratio,aspect);
    assert.equal(saved[`smartflowMetaRedesign:repair-${aspect}`].failure_reason,'technical_redesign');
  }
  const ownerSource=background.slice(background.indexOf('async function isStoryRepairSendOwner('),background.indexOf('function freshFlowProgressMatches('));
  const helper={scope:'meta',helper_tab:7,phase:'rewrite_sent',job_id:'STORY-test',run_id:'meta-run',
    provider:'gemini',request:'owned prompt',redesign_id:'repair',request_id:'old',context_id:'ctx'};
  let pkg={stage:'redesigning',request_id:'old',context_id:'ctx',redesign:{id:'repair',phase:'requested'}};
  const ownerSandbox={chrome:{storage:{local:{get:async key=>({[key]:key.startsWith('smartflowRepairHelper:')?'key':helper})},
    session:{get:async key=>({[key]:'repair'})}}},normalizeAIProvider:x=>x,
    getMetaVideoAdapter:()=>({api:async()=>({package:pkg})})};
  vm.runInNewContext(ownerSource+'\nthis.owns=isStoryRepairSendOwner;',ownerSandbox);
  const request={job_id:'STORY-test',run_id:'meta-run',provider:'gemini',expectedPrompt:'owned prompt'};
  assert.equal(await ownerSandbox.owns(request,7),true);
  assert.equal(await ownerSandbox.owns({...request,expectedPrompt:'changed'},7),false);
  pkg={...pkg,request_id:'successor'};assert.equal(await ownerSandbox.owns(request,7),false);
  const fetchSource=background.slice(background.indexOf('async function fetchImageData('),background.indexOf('async function focusOpenedBrowserTab('));
  const routes=[];const response={ok:true,blob:async()=>({type:'image/png',arrayBuffer:async()=>new Uint8Array([1,2]).buffer})};
  const fetchSandbox={AbortController,setTimeout,clearTimeout,Uint8Array,
    isAllowedFlowImageUrl:u=>u.startsWith('http://127.0.0.1:8765/api/'),
    bridgeFetch:async()=>{routes.push('paired');return response;},fetch:async()=>{routes.push('external');return response;},
    bytesToBase64:bytes=>Buffer.from(bytes).toString('base64')};
  vm.runInNewContext(fetchSource+'\nthis.read=fetchImageData;',fetchSandbox);
  await fetchSandbox.read('http://127.0.0.1:8765/api/stories/job/files/image.jpg');
  await fetchSandbox.read('https://image.example/fixture.png');assert.deepEqual(routes,['paired','external']);
  const headersSource=background.slice(background.indexOf('async function pairedDownloadHeaders('),background.indexOf('const FLOW_RUN_ACTIONS ='));
  const downloadScope={BRIDGE_TOKEN:'fixture',isAllowedFlowImageUrl:fetchSandbox.isAllowedFlowImageUrl,
    refreshBridgeToken:async()=>{},membershipProfile:async()=>'profile'};
  vm.runInNewContext(headersSource+'\nthis.headers=pairedDownloadHeaders;',downloadScope);
  const headers=await downloadScope.headers('http://127.0.0.1:8765/api/jobs/job/files/image.jpg');
  assert.equal(headers.find(h=>h.name==='X-SmartFlow-Token').value,'fixture');
  assert.equal(headers.find(h=>h.name==='X-SmartFlow-Profile').value,'profile');
  await assert.rejects(()=>downloadScope.headers('https://image.example/fixture.png'));
  assert.equal((background.match(/headers:\s*await pairedDownloadHeaders\(/g)||[]).length,3);
  console.log('Meta redesign: save new image before prompt, bounded prompt JSON correction, refusal/unknown-send guards, helper handoff, changed-context successor passed');
})().catch(e=>{console.error(e);process.exit(1);});

function proposalPrompt(){return 'Walk slowly across the room with ordinary camera motion.';}
