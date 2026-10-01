'use strict';
// Actual source classifiers, recovery loops and message handler; all provider,
// storage and browser operations are isolated in memory. No live requests.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const slice=(start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a,start);return source.slice(a,b);};
const definition=name=>{const start=new RegExp('^  (?:async )?function '+name+'\\(','m').exec(source);assert(start,name);
  const rest=source.slice(start.index+start[0].length),end=/\n  (?:async )?function \w+\(/.exec(rest);assert(end,name);return source.slice(start.index,start.index+start[0].length+end.index);};
const clone=value=>JSON.parse(JSON.stringify(value));
const historical='ขออภัย ตอนนี้ฉันไม่สามารถสร้างภาพนี้ได้เนื่องจากเกิดข้อผิดพลาดระหว่างการสร้างภาพ หากต้องการ ให้ส่งคำขอเดิมมาอีกครั้งแล้วฉันจะลองสร้างให้ใหม่ทันที';
const {setup,original,good}=new Function('require','__dirname',
  fs.readFileSync(path.join(__dirname,'story_name_binding_harness.js'),'utf8').split('\n(async()=>')[0]
  +';return {setup,original,good};')(require,__dirname);
const record=f=>Object.values(f.storage).find(row=>row?.version===1&&row.context);
function helpers(replies=[],options={}) {
  const key='helper:test',row={phase:'rewrite_sent',scope:options.scope||'flow',provider:options.gemini?'gemini':'chatgpt',
    job_id:'STORY-FIXTURE',run_id:'RUN-FIXTURE',request_id:'request-fixture',request:'original helper request'};
  const storage={[key]:clone(row)},sends=[],reports=[],waits=[],writes=[];
  const page={user:row.request,answer:options.first||'{broken',draft:'',busy:false,attachments:{count:0,busy:false,failed:false}};
  const turn=()=>({innerText:page.answer,textContent:page.answer,querySelectorAll:()=>[]});
  const ctx=vm.createContext({PROVIDER_KEY:row.provider,IS_GEMINI:Boolean(options.gemini),AI_NAME:'Offline',
    activeJobId:'',activeRunId:'',activeRepairKey:'',activeCoverRequest:null,lastRepairIdentity:null,cancelRequested:false,
    location:{href:'https://chatgpt.com/c/owned'},crypto:require('node:crypto').webcrypto,
    chrome:{storage:{local:{get:async()=>clone(storage),set:async value=>{writes.push(clone(value));Object.assign(storage,clone(value));}}}},
    userTurns:()=>[{innerText:page.user,textContent:page.user,getAttribute:()=> 'user-owned'}],
    latestAssistantStrictlyAfterLatestUser:turn,analysisAnswerNode:value=>value,
    analysisResponseStopButton:()=>page.busy,stopButtonVisible:()=>page.busy,
    chatGPTKnownRenderedRequestMatches:(a,b)=>a===b,chatGPTMotionRequestText:node=>node.innerText,
    geminiTextRequestSnapshot:req=>({owner:page.user===req}),motionRequestMatches:req=>page.user===req,
    chatGPTComposerAttachmentState:()=>page.attachments,geminiComposerAttachmentState:()=>page.attachments,
    composerText:()=>page.draft,visible:()=>true,assertNotCancelled:()=>{if(ctx.cancelRequested)throw Error('cancelled');},
    report:async(...args)=>reports.push(args),sleep:async ms=>{waits.push(ms);if(options.onSleep)await options.onSleep(page,ctx,ms);},
    extractJson:node=>{if(options.ambiguous)throw Object.assign(Error('ambiguous'),{code:'AI_ANALYSIS_JSON_AMBIGUOUS'});return JSON.parse(node.innerText);},
    submitPrompt:async(prompt,urls,strict,count,beforeSend)=>{
      page.draft=prompt;if(options.beforeSend)options.beforeSend(page,ctx);
      if(beforeSend)await beforeSend();
      assert.equal(storage[key].request,prompt,'exact format request saved before Send');
      sends.push(prompt);const reply=replies.shift();if(reply instanceof Error)throw reply;
      page.user=prompt;page.draft='';page.answer=typeof reply==='string'?reply:JSON.stringify(reply);return turn();
    }});
  vm.runInContext(slice('  function explicitAnalysisRefusal(','  function stopButton('),ctx);
  for(const name of ['confirmedStoryImageServiceError','analysisFormatAnswerSignature','analysisFormatGuard','waitForAnalysisFormat','runSceneRepairHelper'])vm.runInContext(definition(name),ctx);
  const handler=slice("    if (message?.type === 'SMARTFLOW_REPAIR_HELPER') {",'    if (message?.type === "VERIFY_AI_SEND_READY") {');
  vm.runInContext(`this.handle=(message,sender,sendResponse)=>{${handler}}`,ctx);
  return {ctx,page,storage,row,key,sends,reports,waits,writes,run:()=>ctx.runSceneRepairHelper(key,true),
    message:extra=>new Promise(resolve=>ctx.handle({type:'SMARTFLOW_REPAIR_HELPER',key,recover:true,request_id:row.request_id,run_id:row.run_id,...extra},{},resolve))};
}
const complete={prompt:'same safe scene',needs_review:false,reference_compatible:true,material_change:false,change_summary:''};
(async()=>{
  let cases=0;const test=async(name,run)=>{try{await run();cases++;}catch(error){error.message=name+': '+error.message;throw error;}};
  await test('historical Thai service reply overrides broad inability classifier',()=>{
    const f=helpers();assert.equal(f.ctx.storyImageRefusal(historical),true);
    assert.equal(f.ctx.confirmedStoryImageServiceError(historical),true);
  });
  for(const suffix of [' เพราะขัดต่อนโยบาย',' Your quota is exhausted.',' Please sign in.',' This violates safety guidelines.'])
    await test('technical prefix cannot hide restriction '+suffix,()=>assert.equal(helpers().ctx.confirmedStoryImageServiceError(historical+suffix),false));
  await test('truncated service text has no complete-failure authority',()=>assert.equal(helpers().ctx.confirmedStoryImageServiceError(historical.slice(0,70)),false));
  await test('Gemini terminal prose waits for completed idle owned response and unchanged text',()=>{
    let now=0,complete=false,stop=false,text='Something went wrong',busy=false;
    const prompt='Generate the owned scene four image.',url='https://gemini.google.com/app/aaaaaaaaaaaaaaaa';
    const node={get innerText(){return text;},matches:()=>complete,
      querySelector:selector=>selector.includes('aria-busy="true"')?busy?{}:null:selector.includes('aria-busy="false"')&&complete?{}:null};
    const user={innerText:prompt,textContent:prompt,closest:()=>container,compareDocumentPosition:()=>4,contains:()=>false};
    const container={id:'bbbbbbbbbbbbbbbb',contains:value=>value===user||value===node,
      querySelectorAll:selector=>selector==='model-response'?[node]:[]};
    const ctx=vm.createContext({IS_GEMINI:true,AI_NAME:'Offline Gemini',Date:{now:()=>now},storyNoResult:{},
      storyContext:{postRefreshRedo:true},storyObservation:null,ownedStory:null,generated:null,latest:node,
      location:{href:url},userTurns:()=>[user],generatedImageElements:()=>[],Node:{DOCUMENT_POSITION_FOLLOWING:4},
      stopButtonVisible:()=>stop,explicitImageFailure:()=>true,chatGPTConversationFrame:value=>value,
      extractMotionJson:()=>{throw Error('not JSON');},retryableCompletedImageText:()=>true});
    vm.runInContext(['motionResponseState','storyImageNoResultReady','geminiTextRequestHash',
      'geminiTextRequestSnapshot','geminiStoryImageSnapshot'].map(definition).join('\n'),ctx);
    ctx.geminiResultProof={prompt,conversation_url:url,request_container_id:container.id,request_index:0,
      prompt_hash:ctx.geminiTextRequestHash(prompt)};
    assert.equal(ctx.geminiStoryImageSnapshot(ctx.geminiResultProof).owner.request_container_id,container.id);
    const block=slice('      const guardedStoryResponse = Boolean(storyContext);','      const noPageProgressMs =');
    vm.runInContext(`this.check=latestText=>{const geminiOwned=geminiStoryImageSnapshot(geminiResultProof);${block}}`,ctx);
    for(now of [0,8000,16000])ctx.check(text); // No completed marker, no error.
    complete=true;stop=true;now=24000;ctx.check(text);
    stop=false;busy=true;now=32000;ctx.check(text);
    busy=false;now=40000;ctx.check(text);now=45000;text+=' while generating';ctx.check(text);
    now=50000;ctx.check(text);now=53000;
    assert.throws(()=>ctx.check(text),error=>error.code==='CHATGPT_NO_IMAGE'&&error.responseText===text);
    ctx.geminiResultProof.selected_image_asset_key='https://lh3.googleusercontent.com/owned-scene-four';
    now=65000;ctx.check(text);now=75000;ctx.check(text);
    assert.equal(ctx.geminiStoryImageSnapshot(ctx.geminiResultProof).reason,'image_loading',
      'missing pinned owned image stays image loading, not terminal no-image retry authority');
  });
  for(const provider of ['chatgpt','gemini']){
    await test('completed malformed bindings continue past two with durable attempts '+provider,async()=>{
      const f=setup((p,n)=>n<=4?'{broken':good(),original,provider);f.pkg.browser_recovery={version:1};
      const waits=[];f.context.sleep=async ms=>waits.push(ms);await f.parse();
      assert.equal(f.prompts.length,5);assert.equal(record(f).attempts['1:third_signal'],4);
      assert(waits.every(ms=>ms<=1500));assert(f.reports.some(r=>r[0]==='repairing_story_names'&&r[1].includes('รอบที่ 4')));
      assert.equal(f.images.length,0);
    });
    await test('truthful empty bindings do not become an infinite fabrication loop '+provider,async()=>{
      const f=setup({bindings:[]},original,provider);f.pkg.browser_recovery={version:1};
      await assert.rejects(f.parse(),/ไม่เติมชื่อโดยเดา/);assert.equal(f.prompts.length,2);
      await assert.rejects(f.parse(),/ไม่เติมชื่อโดยเดา/);assert.equal(f.prompts.length,2);
      assert.equal(record(f).no_match_counts['1:third_signal'],2);
    });
    await test('continuous bindings preserve unknown Send rather than replay '+provider,async()=>{
      const unknown=Object.assign(Error('unknown'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'});
      const f=setup(unknown,original,provider);f.pkg.browser_recovery={version:1};
      await assert.rejects(f.parse(),e=>e===unknown);await assert.rejects(f.parse());assert.equal(f.prompts.length,1);
    });
    for(const notice of ['Please sign in to continue.','Your quota is exhausted.','คำขอนี้ขัดต่อนโยบายการใช้งาน'])
      await test('bindings notice never starts correction loop '+provider+notice,async()=>{
        const f=setup(notice,original,provider);f.pkg.browser_recovery={version:1};await assert.rejects(f.parse());assert.equal(f.prompts.length,1);
      });
    for(const scope of ['flow','product_image','story'])await test('owned helper fixes three completed malformed answers '+provider+scope,async()=>{
      const f=helpers(['{broken again','still not JSON',complete],{gemini:provider==='gemini',scope});
      await f.run();assert.equal(f.storage[f.key].phase,'ready');assert.equal(f.sends.length,3);
      assert.equal(f.storage[f.key].format_attempt,3);assert.equal(f.storage[f.key].original_request,f.row.request);
      assert.deepEqual(f.storage[f.key].candidate,complete);
    });
  }
  for(const first of [historical,'Something went wrong while generating your image. Sorry about that.'])
    await test('completed technical helper failure requests format once, not policy rewrite',async()=>{
      const f=helpers([complete],{first});await f.run();assert.equal(f.storage[f.key].phase,'ready');assert.equal(f.sends.length,1);
    });
  for(const first of ['I cannot help due to policy.','Your usage limit has been reached.','Please sign in to continue.','Complete the CAPTCHA.',JSON.stringify({error:'Your quota is exhausted.'})])
    await test('helper provider notice stops without a correction Send '+first,async()=>{
      const f=helpers([complete],{first});await f.run();assert.equal(f.sends.length,0);assert.equal(f.storage[f.key].phase,'needs_review');
    });
  await test('valid review outcome is preserved rather than repaired until approval',async()=>{
    const f=helpers([],{first:JSON.stringify({...complete,needs_review:true})});await f.run();
    assert.equal(f.sends.length,0);assert.equal(f.storage[f.key].candidate.needs_review,true);
  });
  await test('ambiguous helper JSON does not authorize another Send',async()=>{
    const f=helpers([complete],{ambiguous:true});await f.run();assert.equal(f.sends.length,0);
  });
  await test('unknown format Send preserves request and never auto replays',async()=>{
    const f=helpers([Object.assign(Error('unknown Send'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'})]);await f.run();
    assert.equal(f.sends.length,1);assert.equal(f.storage[f.key].format_attempt,1);assert.equal(f.storage[f.key].request,f.sends[0]);
    assert.equal(f.storage[f.key].phase,'needs_review');
  });
  for(const kind of ['busy','draft','owner','run','attachment','cancel'])await test('helper backoff blocks changed '+kind,async()=>{
    const f=helpers([complete],{onSleep:(p,c,ms)=>{if(ms===8000)return;
      if(kind==='busy')p.busy=true;if(kind==='draft')p.draft='user edit';if(kind==='owner')p.user='other';
      if(kind==='run')c.activeRunId='other';if(kind==='attachment')p.attachments.count=1;if(kind==='cancel')c.cancelRequested=true;}});
    await f.run();assert.equal(f.sends.length,0);
  });
  await test('last-moment change blocks helper format dispatch',async()=>{
    const f=helpers([complete],{beforeSend:p=>{p.user='other';}});await f.run();assert.equal(f.sends.length,0);
  });
  await test('helper ACK starts one collector and idempotent duplicate acknowledges same owner',async()=>{
    const f=helpers();let release,calls=0;f.storage[f.key].scope='meta';
    f.ctx.runMetaRedesignHelper=async()=>{calls++;await new Promise(resolve=>{release=resolve;});};
    const replies=await Promise.all([f.message(),f.message()]);assert.equal(calls,1);
    assert.equal(replies.filter(r=>r.started===true).length,1);assert.equal(replies.filter(r=>r.already_running===true).length,1);
    assert(replies.every(r=>r.ok&&r.key===f.key&&r.request_id===f.row.request_id&&r.run_id===f.row.run_id));release();
  });
  for(const change of [{request_id:'foreign'},{run_id:'foreign'},{key:'missing'}])await test('helper ACK rejects wrong identity '+JSON.stringify(change),async()=>{
    const f=helpers();const response=await f.message(change);assert.equal(response.ok,false);assert.equal(f.sends.length,0);
  });
  await test('generic busy helper is not a successful started ACK',async()=>{
    const f=helpers();f.ctx.activeJobId='OTHER';f.ctx.activeRunId='OTHER-RUN';
    const response=await f.message();assert.equal(response.ok,false);assert.equal(response.busy,true);assert.equal(f.sends.length,0);
  });
  console.log(JSON.stringify({ok:true,cases,networkRequests:0,liveStateWrites:0}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
