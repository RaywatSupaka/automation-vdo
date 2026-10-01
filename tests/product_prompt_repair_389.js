// Real production functions in isolated VMs. No network, Chrome profile or paid media.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const clone=v=>JSON.parse(JSON.stringify(v));
const load=file=>new Function('require','__dirname',fs.readFileSync(path.join(__dirname,file),'utf8').split('(async()=>')[0]+';return fixture;')(require,__dirname);
const background=load('story_repair_background_harness.js'),content=load('story_image_receipt_harness.js');
const candidate={prompt:'A new vertical studio photo of the same real product on a plain surface.',needs_review:false,reference_compatible:true,material_change:false,change_summary:'Changed staging and background.',
  visual_concept:'Overhead product composition on a daylight studio table.',visual_changes:['Change the camera to an overhead composition.','Replace the background with a daylight studio table.'],substantive_redesign:true,product_facts_preserved:true};
function controller(options={}){
  const state={revision:'REV',slots:{1:{status:'succeeded',attempts:1},2:{status:options.initial||'missing',attempts:0},3:{status:'missing',attempts:0}}};
  let now=0,current=0,helpers=0,downloads=0;const sends=[],operations=[],reports=[];
  const c=vm.createContext({activeJobId:'JOB-TEST',activeRunId:'RUN-1',cancelRequested:false,PROVIDER_KEY:options.provider||'chatgpt',IS_GEMINI:options.provider==='gemini',
    Date:{now:()=>now},crypto:{randomUUID:()=>String(now)},thirdPartyContentFailure:t=>/policy/i.test(t),
    assertNotCancelled:()=>{if(c.cancelRequested)throw Object.assign(Error('cancelled'),{name:'AbortError'});},
    sleep:async ms=>{now+=ms;if(options.cancel)c.cancelRequested=true;},report:async(...args)=>reports.push(args),
    imageDataFromUrl:async()=> 'saved-one',imageData:async image=>{downloads++;if(options.download)throw Error('download');return image;},
    submitImagePrompt:async(prompt,refs,count,name,ctx,index)=>{
      sends.push({index:current,prompt,refs,name,geminiIndex:index});
      if(current===2 && sends.filter(s=>s.index===2).length<=(options.failures??2))
        throw Object.assign(Error('completed failure'),{code:options.unknown?'CHATGPT_NO_RESPONSE':'CHATGPT_NO_IMAGE',responseText:options.policy?'policy refusal':'image service failed'});
      return 'image-'+current;
    },chrome:{runtime:{sendMessage:async m=>{
      operations.push(m.operation||m.action);
      if(m.type==='PRODUCT_IMAGE_REPAIR'){
        helpers++;if(options.helperPending)return {ok:true,phase:'rewrite_sent'};
        return {ok:true,phase:'ready',candidate:options.review?{...candidate,needs_review:true}:candidate};
      }
      if(m.operation==='start')return {ok:true,state:clone(state)};
      const slot=state.slots[m.index];
      if(m.operation==='prepare_repair'){assert.equal(m.contract_version,2);return {ok:true,repair:slot.repair||={phase:'prepared',contract_version:2,request_id:'repair-'+slot.attempts,round:slot.attempts}};}
      if(m.operation==='approve_repair')return {ok:true,repair:slot.repair={...slot.repair,phase:m.candidate.needs_review?'needs_review':'approved'}};
      if(['reserve','reserve_repaired'].includes(m.operation)){
        current=m.index;slot.status='reserved';slot.attempts++;
        if(m.operation==='reserve_repaired')slot.effective_prompt=candidate.prompt;
        return {ok:true,token:'token',attempt:slot.attempts,prompt:candidate.prompt};
      }
      assert.equal(m.operation,'finish');slot.status=m.outcome;delete slot.repair;
      return {ok:true,state:clone(state)};
    }}}});
  vm.runInContext(source.slice(source.indexOf('  function productImageFailureKind('),source.indexOf('  async function runPresenterImage(')),c);
  const result={image_prompts:['one','two','three']};
  return {c,sends,operations,reports,result,state,helpers:()=>helpers,downloads:()=>downloads,
    run:()=>c.runProductImages({product_prompt_repair:{enabled:true,contract_version:2},image_urls:['http://local/api/jobs/JOB-TEST/files/original/one.png']},result)};
}
function bg(){
  const f=background();
  const repair={request_id:'repair-1',contract_version:2,failure_token:'failed-token',phase:'prepared',round:1,original_prompt:'original product',previous_prompt:'failed product',reason:'service error'};
  const state={revision:'REV',slots:{1:{token:'failed-token',status:'failed',prompt_repair:repair}}};
  let claims=0;
  f.c.bridgeFetch=async(url,opts)=>{
    if(url.endsWith('/chatgpt-package'))return {ok:true,json:async()=>({ok:true,package:{job:{id:'JOB-TEST',image_ai_provider:'chatgpt'},product_prompt_repair:{enabled:true},image_urls:['http://fixture/api/jobs/JOB-TEST/files/original/one.png']}})};
    const m=JSON.parse(opts.body);
    if(m.operation==='claim_repair_helper'){claims++;assert.equal(repair.phase,'prepared');repair.phase='helper_claimed';}
    return {ok:true,json:async()=>({ok:true,state:clone(state)})};
  };
  const msg={job_id:'JOB-TEST',index:1,revision:'REV',request_id:'repair-1',run_id:'RUN-1',provider:'chatgpt',action:'start'};
  const key='smartflowProductRepair:JOB-TEST:1:REV';
  return {...f,repair,state,key,msg,claims:()=>claims,call:(extra={})=>f.c.productPromptRepairMessage({...msg,...extra},{tab:{id:5}})};
}
(async()=>{
  let cases=0;const test=async(name,fn)=>{try{await fn();cases++;}catch(e){e.message=name+': '+e.message;throw e;}};
  for(const provider of ['chatgpt','gemini'])await test('saved first image + continuous service '+provider,async()=>{
    const f=controller({provider});const images=await f.run();
    assert.deepEqual(f.sends.map(s=>s.index),[2,2,2,3]);assert.equal(images[0],'saved-one');assert.equal(f.helpers(),2);
    assert.equal(f.result.image_prompts[1],candidate.prompt);assert.equal(f.result.image_prompts[0],'one');
    assert(f.sends.every(s=>s.refs[0].endsWith('original/one.png')));
    if(provider==='gemini')assert(f.sends.every(s=>s.geminiIndex===s.index));
  });
  await test('saved policy failure starts helper before generating again',async()=>{
    const f=controller({initial:'policy_blocked',failures:0});await f.run();
    assert(f.operations.indexOf('prepare_repair')<f.operations.indexOf('reserve_repaired'));assert.equal(f.helpers(),1);
  });
  for(const initial of ['reserved','uncertain','download_pending','blocked'])await test('never resend '+initial,async()=>{
    const f=controller({initial});await assert.rejects(f.run());assert.equal(f.sends.length,0);assert.equal(f.helpers(),0);
  });
  await test('unknown send never rewritten',async()=>{const f=controller({unknown:true});await assert.rejects(f.run());assert.equal(f.sends.length,1);assert.equal(f.helpers(),0);});
  await test('download retries never regenerate',async()=>{const f=controller({download:true,failures:0});await assert.rejects(f.run());assert.equal(f.sends.length,1);assert.equal(f.downloads(),10);assert.equal(f.helpers(),0);});
  await test('review is terminal',async()=>{const f=controller({review:true});await assert.rejects(f.run(),/REVIEW/);assert.equal(f.sends.length,1);});
  await test('helper timeout retains original request',async()=>{const f=controller({helperPending:true});await assert.rejects(f.run(),/REVIEW/);assert.equal(f.sends.length,1);assert.equal(f.operations.filter(o=>o==='start').length,2);});
  await test('backoff cancellable before helper send',async()=>{const f=controller({cancel:true});await assert.rejects(f.run(),/cancelled/);assert.equal(f.sends.length,1);assert(!f.operations.includes('reserve_repaired'));});
  await test('helper durable claim and lost ACK adopt same tab',async()=>{
    const f=bg();const record=await f.call();await f.call();assert.equal(f.claims(),1);assert.equal(f.events.filter(e=>e==='open').length,1);
    assert.equal(await f.c.isStoryRepairSendOwner({...f.msg,expectedPrompt:record.request},record.helper_tab),true);
    assert.equal(await f.c.isStoryRepairSendOwner({...f.msg,expectedPrompt:'different'},record.helper_tab),false);
    assert(record.request.includes('Never override a refusal'));assert(record.request.includes('DATA'));
    assert(record.request.includes('visual_concept'));assert(record.request.includes('substantive_redesign'));
  });
  await test('extension storage loss cannot allocate another helper',async()=>{
    const f=bg();await f.call();delete f.storage[f.key];await assert.rejects(f.call());assert.equal(f.events.filter(e=>e==='open').length,1);
  });
  for(const patch of [{request_id:'wrong'},{revision:'wrong'},{index:4}])await test('wrong helper identity '+JSON.stringify(patch),async()=>{
    const f=bg();await assert.rejects(f.call(patch));assert.equal(f.events.length,0);
  });
  await test('ready old-run answer read without resending and owned tab closed',async()=>{
    const f=bg();await f.call();f.storage[f.key].phase='ready';f.storage[f.key].candidate=candidate;
    const record=await f.call({run_id:'RUN-2',action:'status'});assert.equal(record.phase,'ready');assert.equal(f.tabs.size,0);assert.equal(f.claims(),1);
  });
  for(const provider of ['chatgpt','gemini'])for(const mode of ['fresh','resume','busy','review','bad_json'])await test('real helper '+provider+' '+mode,async()=>{
    const f=content({provider}),key='product-helper',calls=[];
    const reply=mode==='bad_json'?'I cannot provide this content':JSON.stringify({...candidate,needs_review:mode==='review'});
    f.storage[key]={scope:'product_image',phase:'rewrite_sent',provider,image_urls:['product-one','product-two'],
      job_id:'JOB-TEST',run_id:'RUN-ONE',request_id:'R1',request:'exact helper request'};
    f.context.userTurns=()=>mode==='resume'||mode==='busy'?[{textContent:'exact helper request'}]:[];
    f.context.composerText=()=>'';f.context.extractJson=n=>JSON.parse(n.textContent);
    f.context.chatGPTComposerAttachmentState=()=>({count:0,busy:false,failed:false});
    f.context.latestAssistantStrictlyAfterLatestUser=()=>({textContent:reply});f.context.stopButtonVisible=()=>mode==='busy';
    f.context.submitPrompt=async(...args)=>{calls.push(args);return {textContent:reply};};
    await f.context.runSceneRepairHelper(key,mode==='resume'||mode==='busy');
    assert.equal(calls.length,['resume','busy'].includes(mode)?0:1);
    if(calls.length){assert.deepEqual(Array.from(calls[0][1]),['product-one','product-two']);assert.equal(calls[0][2],'smartflow-product-R1');}
    assert.equal(f.storage[key].phase,mode==='busy'?'rewrite_sent':mode==='bad_json'?'needs_review':'ready');
    if(mode==='review')assert.equal(f.storage[key].candidate.needs_review,true);
  });
  process.stdout.write(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
