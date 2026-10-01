const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const fixture=new Function('require','__dirname',
  fs.readFileSync('tests/story_image_receipt_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require,__dirname);
const background=fs.readFileSync('browser_extension/background.js','utf8');
const content=fs.readFileSync(process.env.SMARTFLOW_413_BASELINE||'browser_extension/chatgpt.js','utf8');
const extract=(source,name,indent='')=>{
  const start=source.search(new RegExp('(?:async )?function '+name+'\\('));
  assert(start>=0,name);return source.slice(start,source.indexOf('\n'+indent+'}',start)+indent.length+2);
};
const failure='เกิดข้อผิดพลาดในสตรีมของข้อความ\nลองใหม่';
function worker(options={}) {
  const job='STORY-413',key='smartpostStoryGeneratedImage:chatgpt:'+job+':15';
  const receipt={version:1,job_id:job,provider:'chatgpt',scene_index:15,identity:'exact-scene',
    run_id:'old-run',status:'completed_no_image',send_phase:'accepted',send_nonce:'original-nonce',
    service_retry_count:1,response_excerpt:failure,result_proof:{prompt:'exact original request',
      conversation_url:'https://chatgpt.com/c/failed',request_message_id:'original'}};
  const store={[key]:receipt,['run:'+job]:'RUN-413',['smartpostAIWebTab:chatgpt:'+job]:7};
  const tabs={7:{id:7,url:'https://chatgpt.com/c/failed'}},events=[];
  const pkg={mode:'story',job:{id:job,image_ai_provider:'chatgpt'},browser_recovery:{version:1},
    ai_resume:{required:true,stage:'image',provider:'chatgpt',index:15,conversation_url:tabs[7].url},
    analysis_checkpoint:{job_id:job},checkpoint_images:['scene_01.png']};
  let next=8;
  const clone=v=>JSON.parse(JSON.stringify(v));
  const c=vm.createContext({crypto:webcrypto,storyFreshImageLocks:new Set(),aiRunStorageKey:id=>'run:'+id,
    BRIDGE:'http://fixture',normalizeAIProvider:x=>x,AI_WEB:{chatgpt:{url:'https://chatgpt.com/',matches:['https://chatgpt.com/*']}},
    bridgeFetch:async()=>({ok:true,json:async()=>({ok:true,package:pkg})}),
    rememberAutomationTabs:async()=>{},waitForTabComplete:async()=>{if(options.cancel)store['smartflowChatGPTStoryRefreshCancelled:'+job]='RUN-413';},
    isWebLoginUrl:url=>url.includes('/auth'),webActionError:()=>Error('login'),
    chrome:{storage:{local:{get:async()=>clone(store),set:async values=>{
      Object.assign(store,clone(values));options.onSet?.(store,key,values);
    }}},tabs:{
      create:async opts=>{events.push(['create',opts.url]);const tab={id:next++,url:opts.url};tabs[tab.id]=tab;return tab;},
      get:async id=>{if(!tabs[id])throw Error('closed');return clone(tabs[id]);},
      update:async(id,opts)=>{events.push(['navigate',opts.url]);Object.assign(tabs[id],opts);return clone(tabs[id]);},
      sendMessage:async(id,message)=>{
        events.push([message.type,id]);
        if(message.type==='START_CHATGPT_JOB'){
          assert.equal(message.package.reuse_analysis,true);
          assert.equal(message.package.ai_resume,null);
          assert.deepEqual(message.package.checkpoint_images,pkg.checkpoint_images);
          assert.equal(tabs[id].url,'https://chatgpt.com/');
          options.onStart?.(store,key,message);
        }
        return {ok:true};
      }
    },scripting:{executeScript:async()=>{events.push(['inject']);}}}});
  for(const name of ['restartableStoryServiceReceipt','startFreshStoryImage','startAIWebJob'])
    vm.runInContext(extract(background,name),c);
  return {c,pkg,key,store,tabs,events,run:()=>c.startAIWebJob(job,true,'chatgpt',true,'RUN-413')};
}
(async()=>{
  let cases=0;
  const classifier=vm.createContext({});
  vm.runInContext(extract(content,'confirmedStoryImageServiceError','  '),classifier);
  for(const text of [failure,'Error in message stream','A network error occurred. Try again.',
    'Something went wrong. Please try again.']) {
    assert.equal(classifier.confirmedStoryImageServiceError(text),true,text);cases++;
  }
  for(const text of ['Still generating','You have reached your limit','Please log in',
    'I cannot help with that request','Error in message stream. This violates our policy',
    'The words Error in message stream are an example.']) {
    assert.equal(classifier.confirmedStoryImageServiceError(text),false,text);cases++;
  }
  // Native error panels can be siblings rather than assistant-role bodies.
  // A completed native error must leave passive Resume and enter retry.
  const native=fixture({provider:'chatgpt'});let waited=0;
  native.context.Date={now:()=>100000+waited};
  const nativeState={reason:'no_image',images:[],turn:{textContent:failure,querySelector:()=>null}};
  native.context.createStoryImageWaitMonitor=()=>({observe:async()=>{},updateProof:()=>{}});
  native.context.storyImageWaitObservation=()=>({state:nativeState,busy:false,completedControl:true});
  native.context.chatGPTStoryImageSnapshot=()=>nativeState;
  native.context.chatGPTStoryRequest=()=>({});
  native.context.sleep=async ms=>{waited+=ms;};
  native.context.assertNotCancelled=()=>{if(waited>20000)throw Error('native error stranded in passive wait');};
  assert.equal(await native.context.recoverOwnedStoryImage({prompt:'original',conversation_url:native.context.location.href},
    null,{scene_index:1,completedCount:0}),null);cases++;
  // Actual receipt: stable native failure retries once with original full prompt,
  // then hands off a NEW tab. It never re-asks the master analysis.
  let f=fixture({provider:'chatgpt'}),sent=[],handoffs=0;
  f.pkg.browser_recovery={version:1};f.pkg.scene_repair={enabled:true};
  f.context.activeJobId=f.pkg.job.id;f.context.activeRunId=f.pkg.run_id;
  const receipt=f.context.createStoryImageReceipt(f.pkg,1,['scene','style'],0);
  await receipt.begin();await receipt.dispatching('FULL ORIGINAL',{conversation_url:f.context.location.href});
  await receipt.submitted('FULL ORIGINAL',{request_message_id:'m1'});
  await receipt.noImage('completed_no_image',failure);
  assert.equal(await receipt.claimServiceRetry(),1);
  assert.equal(receipt.retryInstruction(),'FULL ORIGINAL');cases++;
  await receipt.begin();await receipt.dispatching('FULL ORIGINAL',{conversation_url:f.context.location.href});
  await receipt.submitted('FULL ORIGINAL',{request_message_id:'m2'});
  await receipt.noImage('completed_no_image',failure);
  f.context.chrome.runtime.sendMessage=async msg=>{sent.push(msg);handoffs++;return {ok:true,refresh_scheduled:true};};
  await assert.rejects(receipt.claimServiceRetry(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');
  assert.equal(sent[0].type,'RESTART_FAILED_STORY_IMAGE');assert.equal(handoffs,1);cases++;
  // Successor restores only matching token/identity and retains full prompt.
  f.storage[f.key].fresh_restart={token:'fresh-token',run_id:f.pkg.run_id,tab_id:8};
  f.pkg.fresh_image_restart={index:1,token:'fresh-token'};
  f.context.location.href='https://chatgpt.com/';
  const restored=f.context.createStoryImageReceipt(f.pkg,1,['scene','style'],0);
  assert.equal(await restored.restore(),null);
  assert.equal(f.storage[f.key].send_phase,'prepared');
  assert.equal(restored.retryInstruction(),'FULL ORIGINAL');
  assert.equal(f.storage[f.key].fresh_restart.phase,'consumed');cases++;
  await restored.begin();await restored.dispatching('FULL ORIGINAL',{conversation_url:'https://chatgpt.com/c/new'});
  await restored.submitted('FULL ORIGINAL',{request_message_id:'m3'});
  await restored.noImage('completed_no_image',failure);
  assert.equal(f.storage[f.key].fresh_restart,null,'New failure must not inherit used successor');
  assert.equal(f.storage[f.key].service_retry_count,2);
  await assert.rejects(restored.claimServiceRetry(),e=>e.code==='STORY_IMAGE_REFRESH_SCHEDULED');
  assert.equal(handoffs,2);cases++;
  // Completed prose/choices instead of an image uses the same recovery path.
  assert.equal(restored.canRetryCompleted('Here are two ideas instead of an image.'),true);
  assert.equal(restored.canRetryCompleted('Please log in to continue'),false);
  assert.equal(restored.canRetryCompleted('You have reached your quota'),false);cases+=3;
  await restored.repaired('A newly reviewed replacement scene');
  assert.equal(restored.retryInstruction(),'','Reviewed rewrite must retire the cached OLD full prompt');
  assert.equal(restored.repairPrompt(),'A newly reviewed replacement scene');cases++;
  // Actual worker manual Continue: bypass obsolete URL ONLY for saved failure.
  let w=worker();await w.run();
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);
  assert(w.events.some(e=>e[0]==='navigate' && e[1]==='https://chatgpt.com/'));
  assert(!w.events.some(e=>e[0]==='navigate' && String(e[1]).includes('/c/failed')));
  assert.equal(w.store[Object.keys(w.store).find(k=>k.includes(':failed:'))].send_nonce,'original-nonce');
  assert.equal(w.tabs[7].url,'https://chatgpt.com/c/failed');cases++;
  // Lost initial ACK reuses recorded fresh tab, not another page.
  await w.run();assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  for(const patch of [{status:'awaiting_result'},{image_url:'real.png'},
    {response_excerpt:'Please log in'}, {response_excerpt:'policy violation'},
    {response_excerpt:'rate limit'}, {send_nonce:''}]) {
    w=worker();Object.assign(w.store[w.key],patch);
    await assert.rejects(w.run());assert(!w.events.some(e=>e[0]==='create'));cases++;
  }
  w=worker({cancel:true});await assert.rejects(w.run(),/ยกเลิก/);
  assert(!w.events.some(e=>e[0]==='START_CHATGPT_JOB'));cases++;
  w=worker();w.store[w.key].fresh_restart={token:'crash',run_id:'RUN-413',phase:'creating'};
  await assert.rejects(w.run(),/ไม่เปิดซ้ำ/);
  assert(!w.events.some(e=>e[0]==='create'));cases++;
  w=worker({onStart:(store,key)=>{store[key]={...store[key],status:'awaiting_result',send_phase:'accepted',
    run_id:'RUN-413',fresh_restart:{...store[key].fresh_restart,phase:'consumed'}};}});
  await w.run();await w.run();
  assert.equal(w.events.filter(e=>e[0]==='create').length,1);cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
