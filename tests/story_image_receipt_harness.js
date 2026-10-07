// Real recovery/runJob functions; no live browser, network, or generation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const storageClone = value => Array.isArray(value) ? value.map(storageClone)
  : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, storageClone(value[key])])) : value;
function fixture(options = {}) {
  const storage = options.storage || {}, messages = [], sends = [], reads = [], events = [];
  const provider = options.provider || 'gemini';
  const pkg = {mode:'story',job:{id:'STORY-RECEIPT-TEST',scene_count:1},run_id:options.run || 'RUN-ONE',
    prompt:'saved master',reuse_analysis:true,image_urls:[],checkpoint_images:[],
    request:{image_count:1,prompt_field:'scene_prompts'},
    analysis_checkpoint:{job_id:'STORY-RECEIPT-TEST',scene_prompts:['One quiet scene'],scene_narrations:['Quiet'],scene_durations:[4]}};
  const getImage = async url => { reads.push(url); events.push('download');
    if(options.read) return options.read(url,reads.length); return 'data:image/png;base64,SAVED'; };
  const context = vm.createContext({AI_NAME:'Offline',IS_GEMINI:provider==='gemini',PROVIDER_KEY:provider,
    waitForResponseIdle:async()=>{if(options.idleError)throw new Error('still busy');},
    stopButtonVisible:()=>Boolean(options.staleStop),
    chatGPTComposerAttachmentState:()=>({count:0,busy:false,failed:false}),
    composer:()=>null,composerText:()=>'',
    stopStalledChatGPTGeneration:async()=>{events.push('stop_after_checkpoint');return false;},
    activeJobId:'',activeRunId:'',cancelRequested:false,location:{href:`https://${provider==='gemini'?'gemini.google.com/app':'chatgpt.com/c'}/receipt-test`},
    assertNotCancelled:()=>{},sleep:async()=>{},report:async()=>{},ensureAiWebModel:async()=>{},aiWebFailureDiagnostic:()=>'',
    revealChatGPTAnswer:async()=>false, // DOM reveal is exercised by result_readiness_392.cjs.
    validateOrRepairStoredAnalysis:async result=>result,validateAnalysis:result=>result,validateStoryContent:()=>{},boundedStoryText:value=>value,
    storySceneContent:()=> 'scene identity',collectConversationImageUrls:async()=>[],
    submitPrompt:async()=>{throw new Error('Master must not be resent');},
    crypto:require('node:crypto').webcrypto,
    submitImagePrompt:async(text,urls,count,ref,story)=>{if(provider==='chatgpt'&&story?.onDispatch)await story.onDispatch(text,{conversation_url:`https://chatgpt.com/c/receipt-test`,before_turn:0});
      sends.push(1);events.push('generate');if(options.sendError)throw options.sendError;
      if(provider==='chatgpt'&&story?.onSubmitted)await story.onSubmitted(text,{request_turn_id:'conversation-turn-1'});
      return {src:provider==='gemini'?'https://lh3.googleusercontent.com/exact-generated-scene':'https://chatgpt.com/backend-api/estuary/exact-generated-scene'};},
    imageData:async image=>getImage(image.src),imageDataFromUrl:getImage,
    // This isolated receipt fixture exercises the old completed guideline
    // branch; Gemini DOM ownership/technical retry has its own focused harness.
    geminiStoryTechnicalFailure:()=>false,
    geminiStoryImageSnapshot:()=>({reason:'request_missing',completed:false,busy:false}),
    storyImageRefusal:text=>text.includes('policy'),storyImageReferenceRequest:()=>false,
    chrome:{storage:{local:{get:async()=>storageClone(storage),set:async value=>{
      const record = Object.values(value)[0]; events.push(record?.status || 'storage');
      if(options.writeFailure?.(value))throw new Error('storage unavailable');Object.assign(storage,storageClone(value));
    }}},runtime:{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',sendMessage:async message=>{messages.push(clone(message));
      if(message.type==='CHECKPOINT_STORY_IMAGE'){events.push('checkpoint');if(options.ack)return options.ack(message,storage);}
      return {ok:true};}}}
  });
  for(const [start,end] of [['  function normalizeOptionalCover(', '  function visible('], ['  function chatGPTConversationFrames(', '  function assistantTurns('], ['  function chatGPTKnownRenderedRequestMatches(', '  function chatGPTMotionRequestText('], ['  function storyImageRecoveryError(','  function largeAssistantImages('],
    ['  function productPointingVisualInstruction(', '  function validateProductCreativePlan('],
    ['  function geminiImageGuidelineResponse(', '  function storyImageReferenceRequest('],
    ['  function imageDownloadFailure(', '  async function imageDataFromUrl('],
    ['  function skipLegacyConversationScan(', '  async function recordStoryImageRequest('],
    ['  async function generateOneImage(','  function productImageFailureKind('],
    ['  async function runJob(','  chrome.runtime.onMessage.addListener(']]){
    const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);vm.runInContext(source.slice(a,b),context);
  }
  return {context,pkg,storage,messages,sends,reads,events,key:`smartpostStoryGeneratedImage:${provider}:${pkg.job.id}:1`,run:()=>context.runJob(pkg)};
}
const code = expected => error => error.code === expected;
(async()=>{
  let cases=0;const test=async(name,fn)=>{if(process.env.SMARTFLOW_TEST_PROGRESS)console.error(name);try{await fn();cases++;}catch(error){error.message=name+': '+error.message;throw error;}};
  for(const resumed of [false,true])await test('Gemini guideline reply opens helper and finishes same scene '+resumed,async()=>{
    const f=fixture({provider:'gemini'});
    const reply='ฉันอยู่ในช่วงเรียนรู้วิธีสร้างรูปภาพบางประเภท ดังนั้นจึงอาจยังไม่สามารถสร้างสิ่งที่คุณขอได้ตรงตามที่ต้องการทั้งหมด หรือสิ่งที่คุณขออาจขัดกับหลักเกณฑ์ของฉัน ถ้าอยากขออย่างอื่น ก็บอกฉันได้เลย';
    assert(f.context.geminiImageGuidelineResponse(reply));
    assert(!f.context.geminiImageGuidelineResponse('ภาพกำลังสร้าง โปรดรอ'));
    assert(!f.context.geminiImageGuidelineResponse('อธิบายหลักเกณฑ์ของฉัน'));
    if(!resumed){
      f.context.thirdPartyContentFailure=()=>false;
      const a=source.indexOf('  function storyImageRefusal('),b=source.indexOf('  function storyImageReferenceRequest(',a);
      vm.runInContext(source.slice(a,b),f.context);assert(f.context.storyImageRefusal(reply));
    }
    const submit=f.context.submitImagePrompt,send=f.context.chrome.runtime.sendMessage;let calls=0,helpers=0;
    f.context.submitImagePrompt=async(...args)=>{calls++;if(calls===1)throw Object.assign(Error('no image'),{code:'CHATGPT_NO_IMAGE',responseText:reply});return submit(...args);};
    if(resumed)await assert.rejects(f.run()); // Old completed_no_image receipt, not reset.
    f.pkg.scene_repair={enabled:true,max_rounds:2};
    f.context.chrome.runtime.sendMessage=async m=>{
      if(m.type!=='STORY_SCENE_REPAIR')return send(m);
      if(m.action==='start'){helpers++;assert(m.reason.includes('หลักเกณฑ์'));return {ok:true,phase:'ready',candidate:{prompt:'One quiet scene in warm natural light with a peaceful ocean background.',needs_review:false,change_summary:'Clear compliant composition'}};}
      return {ok:true,phase:'image_pending'};
    };
    await f.run();assert.equal(calls,2);assert.equal(helpers,1);assert.equal(f.storage[f.key],null);
  });
  await test('enabled helper repairs one failed scene and checkpoints it without failing whole job',async()=>{
    const f=fixture({provider:'chatgpt'});f.pkg.scene_repair={enabled:true,max_rounds:2};
    const submit=f.context.submitImagePrompt, send=f.context.chrome.runtime.sendMessage, calls=[], phases=[];
    f.context.submitImagePrompt=async(...args)=>{
      calls.push(args[0]);if(calls.length===1)throw Object.assign(new Error('policy'),{code:'CHATGPT_NO_IMAGE',responseText:'policy refusal'});
      return submit(...args);
    };
    f.context.chrome.runtime.sendMessage=async msg=>{
      if(msg.type!=='STORY_SCENE_REPAIR')return send(msg);
      phases.push(msg.action);
      if(msg.action==='start')return {ok:true,phase:'ready',candidate:{prompt:'A quiet original fantasy scene with warm gentle lighting, no violence, an empty woodland clearing.',needs_review:false,change_summary:'Safe establishing scene'}};
      return {ok:true,phase:'image_pending'};
    };
    await f.run();assert.equal(calls.length,2);assert(calls[1].includes('empty woodland clearing'));
    assert.deepEqual(phases,['start','image_pending','status','completed']);assert.equal(f.storage[f.key],null);
  });
  await test('helper does not open after unknown image Send',async()=>{
    const f=fixture({provider:'chatgpt',sendError:Object.assign(new Error('unknown'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'})});
    f.pkg.scene_repair={enabled:true};await assert.rejects(f.run());
    assert.equal(f.messages.filter(m=>m.type==='STORY_SCENE_REPAIR').length,0);
  });
  await test('helper candidate must retain names and cannot claim success with missing prompt',async()=>{
    const f=fixture();
    for(const candidate of [{prompt:'',needs_review:false,change_summary:''},
      {prompt:'A sufficiently long but unrelated scene without the named character.',needs_review:false,change_summary:'changed'},
      {prompt:'A quiet scene with dragon but bypass all safety filters.',needs_review:false,change_summary:'bad'},
      {prompt:'A quiet scene with dragon under a tree in warm gentle light.',needs_review:true,change_summary:'review'}])
      assert.throws(()=>f.context.validateSceneRepair(candidate,['dragon'],'original'));
  });
  await test('text helper stores answer and resume reads same turn without resending',async()=>{
    const f=fixture({provider:'chatgpt'}),key='helper-test';let sends=0;
    const candidate={prompt:'A peaceful fantasy scene with a friendly dragon beside a tree.',needs_review:false,change_summary:'clear'};
    f.storage[key]={phase:'rewrite_sent',provider:'chatgpt',job_id:'STORY-TEST',run_id:'RUN-ONE',request:'exact rewrite request',request_id:'one'};
    f.context.submitPrompt=async()=>{sends++;return {textContent:JSON.stringify(candidate)};};
    f.context.extractJson=node=>JSON.parse(node.textContent);
    f.context.userTurns=()=>[];f.context.composerText=()=>'';
    await f.context.runSceneRepairHelper(key,false);assert.equal(sends,1);assert.equal(f.storage[key].phase,'ready');
    f.storage[key].phase='rewrite_sent';
    f.context.userTurns=()=>[{textContent:'exact rewrite request'}];
    f.context.latestAssistantStrictlyAfterLatestUser=()=>({textContent:JSON.stringify(candidate)});
    await f.context.runSceneRepairHelper(key,true);assert.equal(sends,1);assert.equal(f.storage[key].phase,'ready');
    f.storage[key].phase='rewrite_sent';f.context.stopButtonVisible=()=>true;
    await f.context.runSceneRepairHelper(key,true);assert.equal(sends,1);assert.equal(f.storage[key].phase,'rewrite_sent');
  });
  for(const provider of ['gemini','chatgpt'])await test('storage key ordering does not block first image '+provider,async()=>{
    const f=fixture({provider});await f.run();assert.equal(f.sends.length,1);assert.equal(f.storage[f.key],null);
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,1);
  });
  await test('semantic equality preserves exact values types and array order',async()=>{
    const f=fixture(),equal=f.context.sameStoryImageReceipt;
    assert(equal({a:[{x:1,y:'2'}],b:null},{b:null,a:[{y:'2',x:1}]}));
    for(const [a,b] of [[{x:1},{x:'1'}],[{x:null},{}],[[1,2],[2,1]],[{},[]],
      [{job_id:'same',run_id:'old'},{run_id:'new',job_id:'same'}]])assert.equal(equal(a,b),false);
  });
  for(const provider of ['gemini','chatgpt'])await test('exact legacy desktop pre-send proof permits first image only '+provider,async()=>{
    const legacy=fixture({provider,sendError:Object.assign(new Error('pre-send fixture'),{code:'UNKNOWN'})});
    await assert.rejects(legacy.run()); const old=legacy.storage[legacy.key];
    delete old.result_proof;delete old.send_phase;delete old.send_nonce; // Actual v259 receipt predates send phases.
    const f=fixture({provider,storage:legacy.storage,run:'RUN-RESUMED'});
    f.pkg.image_receipt_pre_send_proof={'1':{reason:'v259_first_image_receipt_ack',job_id:f.pkg.job.id,provider,
      scene_index:1,run_id:old.run_id,client_id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      created_after_ms:old.created_at-10,created_before_ms:old.created_at+10,trace_sequence:21}};
    await f.run();assert.equal(f.sends.length,1);assert.equal(f.storage[f.key],null);
  });
  await test('proven 521 prepared image can move to a fresh chat before Send',async()=>{
    const first=fixture({provider:'chatgpt'});
    first.context.submitImagePrompt=async()=>{throw new Error('pre-Send tool check');};
    await assert.rejects(first.run());
    const old=first.storage[first.key];
    assert.equal(old.send_phase,'prepared');assert(!old.send_nonce);
    const oldStorage=clone(first.storage);
    const resumed=fixture({provider:'chatgpt',storage:first.storage,run:'RUN-NEW'});
    resumed.context.location.href='https://chatgpt.com/c/new-chat';
    resumed.pkg.first_image_pre_send={version:1,job_id:resumed.pkg.job.id,provider:'chatgpt',scene_index:1,
      source_run_id:old.run_id,client_id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      conversation_url:old.prepared_conversation,trace_sequence:29,
      created_after_ms:old.created_at-100,created_before_ms:old.created_at+100};
    resumed.context.submitImagePrompt=async()=>{resumed.sends.push(1);throw new Error('after recovery');};
    await assert.rejects(resumed.run(),/after recovery/);
    assert.equal(resumed.sends.length,1);
    assert.equal(resumed.storage[resumed.key].run_id,'RUN-NEW');
    assert.equal(resumed.storage[resumed.key].prepared_conversation,'https://chatgpt.com/c/new-chat');
    for(const tamper of ['dispatch','nonce','proof']){
      const rows=clone(oldStorage),record=rows[first.key];
      if(tamper==='dispatch')rows[first.key+':dispatch']='accepted-nonce';
      if(tamper==='nonce')record.send_nonce='accepted-nonce';
      if(tamper==='proof')record.result_proof={prompt:'sent earlier'};
      const blocked=fixture({provider:'chatgpt',storage:rows,run:'RUN-NEW'});
      blocked.context.location.href='https://chatgpt.com/c/new-chat';
      blocked.pkg.first_image_pre_send=resumed.pkg.first_image_pre_send;
      await assert.rejects(blocked.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));
      assert.equal(blocked.sends.length,0);
    }
  });
  const legacySeed=fixture({sendError:Object.assign(new Error('unknown'),{code:'UNKNOWN'})});
  await assert.rejects(legacySeed.run());
  const legacyClaim=legacySeed.storage[legacySeed.key];
  const validProof={reason:'v259_first_image_receipt_ack',job_id:legacySeed.pkg.job.id,provider:'gemini',
    scene_index:1,run_id:legacyClaim.run_id,client_id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    created_after_ms:legacyClaim.created_at-10,created_before_ms:legacyClaim.created_at+10,trace_sequence:21};
  for(const [field,value] of [['reason','unknown'],['run_id','RUN-OTHER'],['job_id','STORY-OTHER'],
    ['provider','chatgpt'],['client_id','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],['scene_index',2],
    ['created_after_ms',legacyClaim.created_at+1],['created_before_ms',legacyClaim.created_at-1],
    ['created_before_ms',legacyClaim.created_at+6000],['trace_sequence',0]])await test('invalid legacy proof never releases unknown claim '+field,async()=>{
      const f=fixture({storage:clone(legacySeed.storage)});f.pkg.image_receipt_pre_send_proof={'1':{...validProof,[field]:value}};
      await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.sends.length,0);
  });
  await test('unreadable existing scene never becomes missing or regenerates',async()=>{
    const f=fixture({read:async()=>{throw new Error('temporarily unreachable');}});
    f.pkg.checkpoint_images=[{index:1,url:'disk-scene-1'}];const before=JSON.stringify(f.pkg.checkpoint_images);
    await assert.rejects(f.run(),code('STORY_IMAGE_CHECKPOINT_UNREADABLE'));
    assert.equal(f.reads.length,3);assert.equal(f.sends.length,0);assert.equal(JSON.stringify(f.pkg.checkpoint_images),before);
  });
  await test('bounded transient disk retrieval succeeds without generation',async()=>{
    const f=fixture({read:async(url,n)=>{if(n===1)throw new Error('temporary');return 'disk-image';}});
    f.pkg.checkpoint_images=[{index:1,url:'disk-scene-1'}];await f.run();assert.equal(f.reads.length,2);assert.equal(f.sends.length,0);
    assert.equal(f.messages.at(-1).result.generated_images[0],'disk-image');
  });
  for(const provider of ['gemini','chatgpt'])await test('generated download failure resumes exact image without any generation '+provider,async()=>{
    const f=fixture({provider,read:async()=>{throw new Error('download unavailable');}});
    await assert.rejects(f.run(),code('STORY_IMAGE_DOWNLOAD_PENDING'));assert.equal(f.sends.length,1);assert.equal(f.reads.length,3);
    const receipt=clone(f.storage[f.key]);assert.equal(receipt.status,'generated');
    assert(f.events.indexOf('awaiting_result')<f.events.indexOf('generate'));
    assert(f.events.indexOf('generated')<f.events.indexOf('download'));
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,0);
    const g=fixture({provider,storage:f.storage,run:'RUN-RESUMED'});await g.run();assert.equal(g.sends.length,0);
    assert.deepEqual(g.reads,[receipt.image_url]);assert.equal(g.storage[g.key],null);
    assert.equal(g.messages.find(m=>m.type==='CHECKPOINT_STORY_IMAGE').run_id,'RUN-RESUMED');
    assert.equal(g.messages.find(m=>m.type==='CHECKPOINT_STORY_IMAGE').provider,provider);
    assert.equal(g.messages.find(m=>m.type==='CHECKPOINT_STORY_ANALYSIS').provider,provider);
    const final = g.messages.find(m=>m.type==='SUBMIT_STORY_RESULT');
    assert.equal(final.job_id,g.pkg.job.id);assert.equal(final.run_id,'RUN-RESUMED');assert.equal(final.provider,provider);
  });
  await test('desktop checkpoint failure keeps generated receipt for read-only resume',async()=>{
    const f=fixture({ack:()=>({ok:false,error:'disk ACK failed'})});await assert.rejects(f.run(),/disk ACK failed/);
    assert.equal(f.storage[f.key].status,'generated');const g=fixture({storage:f.storage});await g.run();assert.equal(g.sends.length,0);
  });
  await test('unconfirmed dispatch claim survives and cannot resend',async()=>{
    const error=Object.assign(new Error('unknown dispatch'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'});
    const f=fixture({sendError:error});await assert.rejects(f.run(),e=>e===error);assert.equal(f.storage[f.key].status,'awaiting_result');
    const g=fixture({storage:f.storage});await assert.rejects(g.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(g.sends.length,0);
  });
  await test('policy refusal remains terminal and is never retried',async()=>{
    const f=fixture({sendError:Object.assign(new Error('policy'),{code:'CHATGPT_NO_IMAGE',responseText:'policy'})});
    await assert.rejects(f.run(),code('STORY_IMAGE_REFUSED'));assert.equal(f.sends.length,1);
  });
  for(const errorCode of ['CHATGPT_NO_RESPONSE','CHATGPT_IMAGE_STALLED','CHATGPT_NO_IMAGE'])await test('ambiguous image outcome claims once and never internally retries '+errorCode,async()=>{
    const f=fixture({sendError:Object.assign(new Error('uncertain image outcome'),{code:errorCode,responseText:''})});
    await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.sends.length,1);
    assert.equal(f.storage[f.key].status,'awaiting_result');
  });
  await test('explicit new saved prompt after confirmed refusal can run without restoring rejected brief',async()=>{
    const f=fixture({sendError:Object.assign(new Error('policy'),{code:'CHATGPT_NO_IMAGE',responseText:'policy'})});
    await assert.rejects(f.run(),code('STORY_IMAGE_REFUSED'));assert.equal(f.storage[f.key].status,'refused');
    const g=fixture({storage:f.storage});g.pkg.analysis_checkpoint.scene_prompts[0]='A newly reviewed quiet landscape';
    g.pkg.scene_prompt_overrides={'1':g.pkg.analysis_checkpoint.scene_prompts[0]};g.pkg.scene_prompt_override_revision=1;
    await g.run();assert.equal(g.sends.length,1);assert.equal(g.storage[g.key],null);
  });
  await test('same rejected brief with review revision is still not resubmitted',async()=>{
    const f=fixture({sendError:Object.assign(new Error('policy'),{code:'CHATGPT_NO_IMAGE',responseText:'policy'})});
    await assert.rejects(f.run(),code('STORY_IMAGE_REFUSED'));
    const g=fixture({storage:f.storage});g.pkg.scene_prompt_overrides={'1':g.pkg.analysis_checkpoint.scene_prompts[0]};g.pkg.scene_prompt_override_revision=1;
    await assert.rejects(g.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(g.sends.length,0);
  });
  await test('reviewed prompt revision cannot also change source identity',async()=>{
    const f=fixture({sendError:Object.assign(new Error('policy'),{code:'CHATGPT_NO_IMAGE',responseText:'policy'})});
    await assert.rejects(f.run(),code('STORY_IMAGE_REFUSED'));
    const g=fixture({storage:f.storage});g.pkg.analysis_checkpoint.scene_prompts[0]='Reviewed different prompt';
    g.pkg.scene_prompt_overrides={'1':g.pkg.analysis_checkpoint.scene_prompts[0]};g.pkg.scene_prompt_override_revision=1;
    g.pkg.request.image_files=['different-source.png'];g.pkg.image_urls=['different-source-url'];
    await assert.rejects(g.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(g.sends.length,0);
  });
  await test('reviewed changed prompt cannot bypass an uncertain existing generation',async()=>{
    const f=fixture({sendError:Object.assign(new Error('uncertain'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'})});await assert.rejects(f.run());
    const g=fixture({storage:f.storage});g.pkg.analysis_checkpoint.scene_prompts[0]='New scene after unknown request';
    g.pkg.scene_prompt_overrides={'1':g.pkg.analysis_checkpoint.scene_prompts[0]};g.pkg.scene_prompt_override_revision=1;
    await assert.rejects(g.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(g.sends.length,0);
  });
  const seed=fixture({ack:()=>({ok:false,error:'keep receipt'})});await assert.rejects(seed.run(),/keep receipt/);
  for(const [field,value] of [['job_id','STORY-OTHER'],['provider','chatgpt'],['scene_index',2],['identity','changed'],
    ['run_id',''],['image_url','https://example.com/old-image'],['image_url','blob:https://evil.example/old'],['version',2],['created_at',0]]){
    await test('mismatched or unsupported receipt stops '+field+' '+value,async()=>{
      const storage=clone(seed.storage);storage[seed.key][field]=value;const f=fixture({storage});
      await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.sends.length,0);assert.equal(f.reads.length,0);
    });
  }
  await test('changed scene prompt cannot consume old result',async()=>{
    const f=fixture({storage:clone(seed.storage)});f.pkg.analysis_checkpoint.scene_prompts[0]='A different scene';
    await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.sends.length,0);
  });
  await test('failed pre-generation receipt persistence sends nothing',async()=>{
    const f=fixture({writeFailure:value=>Object.values(value)[0]?.status==='awaiting_result'});
    await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.sends.length,0);
  });
  await test('failed generated receipt write keeps unresolved claim and never regenerates',async()=>{
    const f=fixture({writeFailure:value=>Object.values(value)[0]?.status==='generated'});
    await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(f.storage[f.key].status,'awaiting_result');
    const g=fixture({storage:f.storage});await assert.rejects(g.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));assert.equal(g.sends.length,0);
  });
  await test('checkpoint ACK cannot remove a newer owner receipt',async()=>{
    const f=fixture({ack:(m,storage)=>{const key=Object.keys(storage).find(k=>k.startsWith('smartpostStoryGeneratedImage:'));storage[key]={...storage[key],run_id:'NEWER-RUN'};return {ok:true};}});
    await f.run();assert.equal(f.storage[f.key].run_id,'NEWER-RUN');
  });
  await test('repeated download failure stays bounded and preserves same receipt',async()=>{
    const storage=clone(seed.storage),before=JSON.stringify(storage[seed.key]);
    const f=fixture({storage,read:async()=>{throw new Error('expired URL');}});
    await assert.rejects(f.run(),code('STORY_IMAGE_DOWNLOAD_PENDING'));assert.equal(f.sends.length,0);assert.equal(f.reads.length,3);
    assert.equal(JSON.stringify(storage[seed.key]),before);
  });
  for(const item of [{index:0,url:'disk'},{index:1.5,url:'disk'},{index:1,url:''}])await test('invalid explicit checkpoint is not ignored '+JSON.stringify(item),async()=>{
    const f=fixture();f.pkg.checkpoint_images=[item];await assert.rejects(f.run(),code('STORY_IMAGE_CHECKPOINT_UNREADABLE'));assert.equal(f.sends.length,0);
  });
  await test('Product direct helper retains old download behavior and creates no Story receipt',async()=>{
    const f=fixture({read:async()=>{throw new Error('download failed');}});
    await assert.rejects(f.context.generateOneImage('product',[],1,'product'),/ดาวน์โหลดภาพที่ 1/);
    assert.equal(f.reads.length,60);assert.equal(Object.keys(f.storage).length,0);
  });
  await test('confirmed service errors continue beyond old retry limit with identical prompt',async()=>{
    const error=Object.assign(new Error('service'),{code:'CHATGPT_NO_IMAGE',responseText:'Something went wrong while generating your image. Sorry about that.'});
    const f=fixture({provider:'chatgpt'}), submit=f.context.submitImagePrompt, prompts=[];
    f.context.submitImagePrompt=async(...args)=>{prompts.push(args[0]);if(prompts.length<=4)throw error;return submit(...args);};
    await f.run();assert.equal(prompts.length,5);assert.equal(new Set(prompts).size,1);assert.equal(f.storage[f.key],null);
  });
  await test('mixed policy or generic text never authorizes service retry',async()=>{
    for(const text of ['policy Something went wrong while generating your image. Sorry about that.','No image available']){
      const f=fixture({provider:'chatgpt',sendError:Object.assign(new Error('failed'),{code:'CHATGPT_NO_IMAGE',responseText:text})});
      await assert.rejects(f.run());assert.equal(f.sends.length,1);
    }
  });
  const thaiServiceError='ขออภัยครับ ครั้งนี้ผมไม่สามารถสร้างภาพได้สำเร็จ เนื่องจากระบบสร้างภาพเกิดข้อผิดพลาดระหว่างประมวลผลคำขอนี้';
  await test('latest real Thai service error is not misclassified as policy refusal',async()=>{
    const text='ขออภัย ฉันไม่สามารถสร้างภาพได้ในครั้งนี้เนื่องจากเกิดข้อผิดพลาดระหว่างการสร้างภาพ กรุณาส่งคำขอใหม่อีกครั้ง แล้วฉันจะลองสร้างให้ใหม่ทันที';
    const f=fixture({provider:'chatgpt'}), submit=f.context.submitImagePrompt;
    f.context.storyImageRefusal=value=>value.includes('ฉันไม่สามารถสร้างภาพ');
    let attempts=0;
    f.context.submitImagePrompt=async(...args)=>{if(++attempts===1)throw Object.assign(new Error('service'),{code:'CHATGPT_NO_IMAGE',responseText:text});return submit(...args);};
    await f.run();assert.equal(attempts,2);assert.equal(f.storage[f.key],null);
    assert.equal(f.context.confirmedStoryImageServiceError(text+' ละเมิดนโยบาย'),false);
    const live='ไม่สามารถสร้างภาพได้ในครั้งนี้เนื่องจากเครื่องมือสร้างภาพเกิดข้อผิดพลาด จึงยังไม่มีภาพใหม่ถูกสร้างขึ้นครับ';
    assert.equal(f.context.confirmedStoryImageServiceError(live),true);
    assert.equal(f.context.confirmedStoryImageServiceError(live+' ละเมิดนโยบาย'),false);
  });
  await test('Thai completed service error retries once and checkpoints success',async()=>{
    const f=fixture({provider:'chatgpt'}), submit=f.context.submitImagePrompt;
    let calls=0;
    f.context.submitImagePrompt=async(...args)=>{
      if(++calls===1)throw Object.assign(new Error('service'),{code:'CHATGPT_NO_IMAGE',responseText:thaiServiceError});
      return submit(...args);
    };
    await f.run();assert.equal(calls,2);assert.equal(f.storage[f.key],null);
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,1);
  });
  await test('Thai retry cancellation stops sends and does not re-use old failure proof',async()=>{
    const f=fixture({provider:'chatgpt',sendError:Object.assign(new Error('service'),{code:'CHATGPT_NO_IMAGE',responseText:thaiServiceError})});
    f.context.sleep=async()=>{throw Object.assign(new Error('cancelled'),{name:'AbortError'});};
    await assert.rejects(f.run());assert.equal(f.sends.length,1);assert.equal(f.storage[f.key].service_retry_count,1);
    assert.equal(f.storage[f.key].result_proof,null);assert.equal(f.storage[f.key].response_excerpt,'');
    const resumed=fixture({provider:'chatgpt',storage:f.storage});
    await assert.rejects(resumed.run());assert.equal(resumed.sends.length,0);
  });
  await test('saved completed service error resumes despite previous retries',async()=>{
    const f=fixture({provider:'chatgpt'});f.context.activeRunId='RUN-ONE';
    const receipt=f.context.createStoryImageReceipt(f.pkg,1,['scene'],0);
    await receipt.restore();await receipt.begin();await receipt.submitted('exact prompt');
    await receipt.noImage('completed_no_image',thaiServiceError);
    f.storage[f.key].service_retry_count=4;
    const next=f.context.createStoryImageReceipt(f.pkg,1,['scene'],0);
    assert.equal(await next.restore(),null);assert.equal(f.storage[f.key].service_retry_count,5);
  });
  await test('legacy false refusal with full exact service text can resume',async()=>{
    const f=fixture({provider:'chatgpt'});f.context.activeRunId='RUN-ONE';
    const receipt=f.context.createStoryImageReceipt(f.pkg,1,['scene'],0);
    await receipt.restore();await receipt.begin();
    await receipt.noImage('refused',thaiServiceError);
    const next=f.context.createStoryImageReceipt(f.pkg,1,['scene'],0);
    assert.equal(await next.restore(),null);assert.equal(f.storage[f.key].service_retry_count,1);
  });
  for(const variant of ['valid','wrong_chat','busy','different_prompt','partial','image','changed'])await test('old truncated reply recovery '+variant,async()=>{
    const f=fixture({provider:'chatgpt'}), user={textContent:'exact prompt',querySelector:()=>null};
    let text=variant==='partial'?thaiServiceError.slice(0,75):thaiServiceError;
    const userFrame={getAttribute:name=>name==='data-testid'?'conversation-turn-1':null,
      querySelector:selector=>selector.includes('user')?user:null};
    const response={getAttribute:name=>name==='data-testid'?'conversation-turn-2':null,
      querySelector:selector=>selector.includes('assistant')?{textContent:text}:null};
    f.context.document={querySelectorAll:selector=>selector==='[data-testid^="conversation-turn-"]'?[userFrame,response]:[]};
    f.context.generatedImageElements=()=>variant==='image'?[{}]:[];
    if(variant==='wrong_chat')f.context.location.href='https://chatgpt.com/c/other';
    if(variant==='busy')f.context.stopButtonVisible=()=>true;
    if(variant==='different_prompt')user.textContent='another scene';
    if(variant==='changed')f.context.sleep=async()=>{text+=' still processing';};
    const result=await f.context.recoverOwnedStoryServiceReply({prompt:'exact prompt',conversation_url:'https://chatgpt.com/c/receipt-test'});
    assert.equal(Boolean(result),variant==='valid');assert.equal(f.sends.length,0);
  });
  await test('partial Thai mixed refusal and unrelated prose do not authorize retry',async()=>{
    const f=fixture({provider:'chatgpt'});
    for(const text of [thaiServiceError.slice(0,75),thaiServiceError+' policy', 'policy '+thaiServiceError, 'ระบบสร้างภาพเกิดข้อผิดพลาด'])
      assert.equal(f.context.confirmedStoryImageServiceError(text),false);
  });
  await test('Story no-image waits for stable full reply and resets on busy or image',async()=>{
    const f=fixture({provider:'chatgpt'}), ready=f.context.storyImageNoResultReady, state={};
    assert.equal(ready(state,'ไม่สามารถสร้างภาพ',true,false,0),false);
    assert.equal(ready(state,'ไม่สามารถสร้างภาพ',false,false,1000),false);
    assert.equal(ready(state,thaiServiceError,false,false,8000),false);
    assert.equal(ready(state,thaiServiceError,false,false,14000),false);
    assert.equal(ready(state,thaiServiceError,true,false,15000),false);
    assert.equal(ready(state,thaiServiceError,false,false,16000),false);
    assert.equal(ready(state,thaiServiceError,false,false,24001),true);
    assert.equal(ready(state,thaiServiceError,false,true,25000),false);
    assert(source.includes('if (!guardedStoryResponse && latest && explicitImageFailure(latestText))'));
    assert(source.replace(/\s+/g,' ').includes('storyImageNoResultReady(storyNoResult, latestText, stopButtonVisible() || storyObservation?.busy || IS_GEMINI && !geminiReplyState?.completed || !IS_GEMINI && storyContext.postRefreshRedo===true && retryableCompletedImageText(latestText), Boolean(generated || ownedStory?.images.length || ownedStory?.selectedAssetKey || geminiOwned?.selectedAssetKey), Date.now())'));
  });
  await test('checkpoint waits naturally and never presses stale Stop',async()=>{
    const f=fixture({provider:'chatgpt',staleStop:true});
    await f.run();
    assert.equal(f.storage[f.key],null);
    assert.equal(f.events.includes('stop_after_checkpoint'),false);
    assert.equal(f.sends.length,1);
  });
  await test('busy previous response never claims the next scene',async()=>{
    const f=fixture({provider:'chatgpt',idleError:true});
    await assert.rejects(f.run());assert.equal(f.storage[f.key],undefined);assert.equal(f.sends.length,0);
  });
  await test('accepted request stores exact prompt and conversation before result',async()=>{
    const f=fixture({provider:'chatgpt'});f.context.activeRunId='RUN-ONE';
    const receipt=f.context.createStoryImageReceipt(f.pkg,1,['scene'],0);
    await receipt.restore();await receipt.begin();await receipt.submitted('exact prompt');
    assert.equal(f.storage[f.key].result_proof.prompt,'exact prompt');
    assert.equal(f.storage[f.key].status,'awaiting_result');
  });
  for (const variant of ['valid','wrong_chat','duplicate_prompt','two_images','old_image','responsive_pair']) await test('owned result recovery '+variant,async()=>{
    const seed=fixture({provider:'chatgpt',sendError:new Error('unknown')});
    await assert.rejects(seed.run());
    const f=fixture({provider:'chatgpt',storage:seed.storage});
    f.storage[f.key].result_proof={prompt:'exact image prompt',conversation_url:'https://chatgpt.com/c/receipt-test'};
    const pic={src:'https://chatgpt.com/backend-api/estuary/recovered',complete:true,naturalWidth:1024,naturalHeight:1536};
    const user={textContent:'exact image prompt',querySelector:()=>null,getAttribute:()=>null,
      cloneNode(){return {textContent:this.textContent,querySelectorAll:()=>[]};}};
    let turn=0;
    const frame=(u,images=[])=>{const id='conversation-turn-'+turn++;return {querySelector:()=>u,querySelectorAll:()=>[],images,getAttribute:()=>id};};
    const frames=[frame(null,variant==='old_image'?[pic]:[]),frame(user),frame(null,[pic])];
    if(variant==='duplicate_prompt')frames.push(frame(user));
    if(variant==='two_images'||variant==='responsive_pair')frames[2].images.push({...pic,src:pic.src+'2'});
    if(variant==='responsive_pair'){
      frames[2].textContent='คุณชอบภาพใดมากกว่า';
      frames[2].contains=image=>frames[2].images.includes(image);
      frames[2].querySelectorAll=selector=>selector==='button'?[1,2].map(n=>({
        textContent:`ภาพ ${n}ภาพที่ ${n} ดีกว่า`,getAttribute:()=>null,
        querySelectorAll:()=>[{textContent:`ภาพ ${n}`},{textContent:`ภาพที่ ${n} ดีกว่า`}]
      })):[];
      f.context.visible=()=>true;
    }
    if(variant==='wrong_chat')f.context.location.href='https://chatgpt.com/c/other';
    f.context.document={querySelectorAll:selector=>selector==='[data-testid^="conversation-turn-"]'?frames:[]};
    f.context.generatedImageElements=frame=>frame.images;
    f.context.generatedImageUrls=frame=>frame.images.map(x=>x.src);
    if(variant==='valid'||variant==='responsive_pair'||variant==='two_images'||variant==='wrong_chat') {
      await f.run();assert.equal(f.storage[f.key],null);assert.equal(f.reads.length,1);
      assert.equal(f.reads[0],pic.src);
      assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,1);
    }
    else if(variant==='old_image') {
      // A historical asset is not a current result. The owned empty reply now
      // keeps waiting until new DOM evidence or user cancellation, including
      // beyond the former six-minute limit.
      const started=Date.now(), reports=[];let elapsed=0;
      f.context.Date={now:()=>started+elapsed};
      f.context.report=async(...args)=>reports.push(args);
      f.context.sleep=async ms=>{elapsed+=ms;};
      f.context.assertNotCancelled=()=>{
        if(elapsed>=420000)throw Object.assign(new Error('cancelled'),{name:'AbortError'});
      };
      await assert.rejects(f.run(),error=>error.name==='AbortError');
      assert(elapsed>=420000);
      assert.equal(f.storage[f.key].status,'awaiting_result');
      assert.equal(f.reads.length,0);
      assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,0);
      assert(reports.some(args=>args[0]==='waiting_for_image'));
      assert(!reports.some(args=>args[0]==='story_image_result_review'));
    }
    else await assert.rejects(f.run(),code('STORY_IMAGE_RECEIPT_REVIEW'));
    assert.equal(f.sends.length,0);
  });
  await test('owned preview cannot return before provider idle',async()=>{
    assert.equal(source.includes("report('image_ready_before_idle'"),false);
    assert(source.includes('chatGPTImageReady && !stopButtonVisible() && !storyObservation?.busy'));
  });
  await test('legacy image wait helper is passive, never Stop',async()=>{
    const a=source.indexOf('  async function stopStalledChatGPTGeneration(');
    const b=source.indexOf('  async function waitForResponseIdle(',a);
    assert(a>0&&b>a);
    let stops=0,waits=0;
    const context=vm.createContext({report:async()=>{},waitForResponseIdle:async()=>waits++,stopButton:()=>({click:()=>stops++})});
    vm.runInContext(source.slice(a,b),context);
    assert.equal(await context.stopStalledChatGPTGeneration('wait',0),true);
    assert.equal(stops,0);assert.equal(waits,1);
  });
  await test('accepted Story does not fail on empty placeholder at 35 seconds',async()=>{
    const a=source.indexOf('      if (!storyContext && !generated && !stopButtonVisible()');
    const b=source.indexOf('      await sleep(700);',a);
    assert(a>0&&b>a);
    for(const story of [true,false]){
      const context=vm.createContext({storyContext:story?{scene_index:10}:null,generated:null,
        stopButtonVisible:()=>false,latestText:'',Date:{now:()=>40000},started:0,AI_NAME:'ChatGPT'});
      const run=()=>vm.runInContext('(async()=>{'+source.slice(a,b)+'})()',context);
      if(story)await run();else await assert.rejects(run(),code('CHATGPT_NO_RESPONSE'));
    }
    assert(source.includes('while (storyWait || stopButtonVisible() || Date.now() - started < 360000)'));
  });
  process.stdout.write(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
