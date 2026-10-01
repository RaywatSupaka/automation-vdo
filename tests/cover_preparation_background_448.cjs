// Actual source functions; fake Chrome, bridge, DOM and time. No browser/provider.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(text,start,end)=>{const a=text.indexOf(start),b=text.indexOf(end,a+start.length);assert(a>=0&&b>a,start);return text.slice(a,b);};
const helpers=part(source,'const coverOwnerOperations =','async function closeSavedCoverTabs(')
  +part(source,'async function coverBridgeEvent(','async function pollAICovers(');
const eventBody=part(source,"    if (message?.type === 'AI_COVER_EVENT') {",'    const pausedMutationTypes =');
const clone=value=>JSON.parse(JSON.stringify(value));
const rid='a'.repeat(32),key=`smartflowCover:${rid}`;
let cases=0;const failures=[];
async function check(name,fn){try{await fn();cases++;}catch(error){failures.push({name,error:String(error.stack||error)});}}
function fixture(config={}){
  const initial={request_id:rid,provider:'chatgpt',job_id:'STORY-fixture',tab_id:77,phase:'recovering',
    preparation_id:'prep-old',document_id:'doc-old',preparation_attempt:2,
    preparation_state:{stage:'image_tool',reason:'opener_missing',attempt:2,not_dispatched:true,request_id:rid},
    ...config.row};
  const stored={[key]:clone(initial)},actions=[],events=[];
  let desktop=clone(initial),ticks=0,uuid=0,proofCalls=0;
  let enterReload,releaseReload;
  const reloadEntered=new Promise(resolve=>enterReload=resolve);
  const reloadGate=new Promise(resolve=>releaseReload=resolve);
  const sender={documentId:'doc-old',tab:{id:77,url:'https://chatgpt.com/'},...config.sender};
  const message={type:'RESTART_AI_COVER_PREPARATION',request_id:rid,preparation_id:'prep-old',attempt:2,...config.message};
  const c=vm.createContext({URL,JSON,Date,Promise,Map,BRIDGE:'http://fixture',CLIENT_ID:'fixture',
    crypto:{randomUUID:()=>`prep-new-${++uuid}`},
    setTimeout:callback=>{ticks++;config.onTick?.({desktop,stored,ticks});callback();},
    closeSavedCoverTabs:async()=>{},
    bridgeFetch:async(url,init)=>{
      if(url.endsWith('/api/ai-covers/event')){
        const event=JSON.parse(init.body);events.push(event);actions.push(['event',event.phase]);
        if(config.cancelBeforeReload&&event.phase==='recovering')desktop.phase='cancelled';
        if(desktop.phase!=='cancelled')desktop={...desktop,...event};
        return {ok:true,json:async()=>({ok:true,request:clone(desktop)})};
      }
      if(url.endsWith('/api/extension/progress'))return {ok:true,json:async()=>({ok:true})};
      assert.equal(url,`http://fixture/api/ai-covers/${rid}`);
      return {ok:true,json:async()=>({ok:true,request:{...clone(desktop),...config.packet}})};
    },
    chrome:{runtime:{getManifest:()=>({version:'fixture448'})},
      storage:{local:{get:async storageKey=>clone(storageKey===null?stored:{[storageKey]:stored[storageKey]}),
        set:async value=>{Object.assign(stored,clone(value));actions.push(['store',stored[key]?.preparation_id,stored[key]?.document_id]);}}},
      tabs:{reload:async tabId=>{actions.push(['reload',tabId]);enterReload();if(config.holdReload)await reloadGate;},
        get:async tabId=>({id:tabId,status:config.loading?'loading':'complete',url:config.url||'https://chatgpt.com/'}),
        sendMessage:async(tabId,payload,options)=>{actions.push(['start',tabId,clone(payload),clone(options)]);return config.badAck?{ok:false,error:'START rejected'}:{ok:true};}},
      scripting:{executeScript:async args=>{
        if(args.files){actions.push(['inject',clone(args.target),args.files]);return [];}
        actions.push(['inspect',clone(args.target)]);
        if(args.target.documentIds){proofCalls++;return [{documentId:config.proofDocument||'doc-old',
          result:{empty:config.emptyOld!==false && !(config.changedBeforeReload && proofCalls>1)}}];}
        const old=config.sameDocument || ticks<(config.newDocumentAfterTick||0);
        return [{documentId:old?'doc-old':'doc-new',result:{empty:config.emptyNew!==false}}];
      }}}});
  vm.runInContext(helpers+`\nasync function dispatchCoverEvent(message,sender){let output;const sendResponse=value=>{output=value;};await (async()=>{${eventBody}})();return output;}`,c);
  return {c,stored,actions,events,message,sender,reloadEntered,releaseReload,get ticks(){return ticks;},
    restart:()=>c.restartCoverPreparation(message,sender),
    event:(event={},overrides={})=>c.dispatchCoverEvent({type:'AI_COVER_EVENT',request_id:rid,preparation_id:'prep-old',event,...overrides},sender),
    count:type=>actions.filter(row=>row[0]===type).length};
}
function inspect(config={}){
  const node=(attributes={})=>({isConnected:true,getClientRects:()=>[{}],getAttribute:key=>attributes[key]||null});
  const form={querySelector:()=>config.attachment?{}:null};
  const editor={...node(),innerText:config.draft||'',textContent:config.draft||'',value:config.draft||'',closest:()=>form};
  const buttons=(config.buttons||[]).map(node);
  const document={querySelectorAll:selector=>selector==='button'?buttons:selector.includes('input[type="file"]')
    ? [{files:config.files?[{}]:[]}]:config.noComposer?[]:[editor],
    querySelector:selector=>config.legacyTurn&&selector.includes('data-message-author-role')?{}
      :config.semanticTurn&&/data-chatgpt-search-unit-key|data-chatgpt-search-message-ids/.test(selector)?{}:null};
  const c=vm.createContext({document,location:{hostname:'chatgpt.com',pathname:config.path||'/'}});
  vm.runInContext(part(source,'function inspectEmptyCoverPreparation()','async function restartCoverPreparation('),c);
  return c.inspectEmptyCoverPreparation();
}
async function contentHandoffFailure(){
  const request={request_id:rid,preparation_id:'prep-old'},events=[];
  const c=vm.createContext({IS_GEMINI:false,activeCoverRequest:request,Math,Number,Error,
    // This unit isolates a failed background handoff. Real preflight readers
    // and delayed/remounted forms are covered by cover_preflight_dom_449.cjs.
    coverPreparationSnapshot:()=>({ready:true,reason:'ready',transient:false,checks:{
      owner_current:true,composer_ready:true,user_turns:0,assistant_turns:0,draft_present:false,
      attachment_count:0,attachment_busy:false,attachment_failed:false,response_active:false}}),
    assertNotCancelled:()=>{},chatGPTComposerAttachmentState:()=>({count:0,busy:false,failed:false}),
    userTurns:()=>[],assistantTurns:()=>[],composer:()=>({}),composerText:()=>'',stopButtonVisible:()=>false,
    setChatGPTImageTool:async()=>{throw Object.assign(Error('tool late'),{code:'AI_SEND_NOT_READY',notDispatched:true,toolReason:'opener_missing',transient:true});},
    coverEvent:async event=>{events.push(event);return {phase:event.phase};},sleep:async()=>{},
    chrome:{runtime:{sendMessage:async()=>({ok:false,error:'refresh denied'})}}});
  vm.runInContext(part(content,'  async function prepareCoverImageTool(', '  async function collectCoverImage('),c);
  await assert.rejects(c.prepareCoverImageTool(request,'cover',0),error=>error.code==='AI_SEND_NOT_READY'
    && error.notDispatched===true && error.coverPreparationState?.not_dispatched===true);
}
(async()=>{
  await check('exact owner refreshes once, fences old doc, addresses new START',async()=>{
    const f=fixture();assert.equal((await f.restart()).ok,true);
    assert.equal(f.count('reload'),1);assert.equal(f.count('start'),1);assert.equal(f.count('inject'),1);
    const start=f.actions.find(row=>row[0]==='start');assert.deepEqual(start[3],{documentId:'doc-new'});
    assert.equal(start[2].request.request_id,rid);assert.equal(start[2].request.preparation_id,'prep-new-1');
    assert.equal(f.stored[key].document_id,'doc-new');assert.equal(f.stored[key].preparation_id,'prep-new-1');
    assert(f.actions.findIndex(row=>row[0]==='store')<f.actions.findIndex(row=>row[0]==='reload'));
  });
  for(const [name,config] of Object.entries({wrongTab:{sender:{tab:{id:78,url:'https://chatgpt.com/'}}},
    wrongDocument:{sender:{documentId:'doc-other',tab:{id:77,url:'https://chatgpt.com/'}}},
    missingDocument:{sender:{documentId:null,tab:{id:77,url:'https://chatgpt.com/'}}},
    wrongPreparation:{message:{preparation_id:'other'}},wrongAttempt:{message:{attempt:1}},
    wrongRequest:{row:{request_id:'b'.repeat(32),preparation_state:{stage:'image_tool',reason:'opener_missing',attempt:2,not_dispatched:true,request_id:'b'.repeat(32)}}},
    alreadySent:{row:{send_state:'accepted'}},dispatchEvidence:{row:{send_diagnostics:{gesture_phase:'released'}}},
    references:{row:{reference_proof:{count:1}}},result:{row:{result_proof:{images:1}}},activity:{row:{collector_state:{stage:'generating'}}},
    collectOnly:{row:{collect_only:true}},notPreparing:{row:{phase:'running'}},
    proofDocumentMismatch:{proofDocument:'doc-other'},draftOrActivityProof:{emptyOld:false}})){
    await check(`reject ${name} before reload`,async()=>{const f=fixture(config);await assert.rejects(f.restart());assert.equal(f.count('reload'),0);assert.equal(f.count('start'),0);});
  }
  await check('same old document is never STARTed and failure retains typed no-send',async()=>{
    const f=fixture({sameDocument:true});await assert.rejects(f.restart());assert.equal(f.count('start'),0);assert.equal(f.count('reload'),1);
    assert.equal(f.ticks,120);const event=f.events.at(-1);assert.equal(event.error_code,'AI_SEND_NOT_READY');
    assert.equal(event.notDispatched,true);assert.equal(event.preparation_state.not_dispatched,true);
  });
  await check('busy/nonempty new document is not STARTed',async()=>{const f=fixture({emptyNew:false});await assert.rejects(f.restart());assert.equal(f.count('start'),0);});
  await check('cancel before reload',async()=>{const f=fixture({cancelBeforeReload:true});await assert.rejects(f.restart());assert.equal(f.count('reload'),0);assert.equal(f.count('start'),0);});
  await check('draft/activity arriving during bridge check vetoes reload',async()=>{
    const f=fixture({changedBeforeReload:true});await assert.rejects(f.restart());assert.equal(f.count('reload'),0);assert.equal(f.count('start'),0);
  });
  await check('cancel while reload is pending',async()=>{
    const f=fixture({newDocumentAfterTick:1,onTick:({desktop})=>{desktop.phase='cancelled';}});
    await assert.rejects(f.restart());assert.equal(f.count('reload'),1);assert.equal(f.count('start'),0);
  });
  for(const [name,packet] of Object.entries({wrongRequest:{request_id:'b'.repeat(32)},wrongProvider:{provider:'gemini'},
    accepted:{send_state:'accepted'},diagnostics:{send_diagnostics:{gesture_phase:'released'}},
    reference:{reference_proof:{count:1}},activity:{collector_state:{stage:'generating'}},result:{result_proof:{images:1}}})){
    await check(`new desktop ${name} evidence forbids START`,async()=>{const f=fixture({packet});await assert.rejects(f.restart());assert.equal(f.count('start'),0);});
  }
  await check('concurrent repeated restart does not create second reload or START',async()=>{
    const f=fixture();const results=await Promise.allSettled([f.restart(),f.restart()]);
    assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal(f.count('reload'),1);assert.equal(f.count('start'),1);
  });
  await check('old callback waits behind handoff then rejects without bridge event',async()=>{
    const f=fixture({holdReload:true}),restart=f.restart();await f.reloadEntered;
    const oldEvent=f.event({phase:'needs_review',message:'obsolete callback'});f.releaseReload();await restart;
    await assert.rejects(oldEvent);assert.equal(f.events.some(e=>e.message==='obsolete callback'),false);
  });
  await check('new owner event bound to new document only',async()=>{
    const f=fixture();await f.restart();await assert.rejects(f.event({phase:'preparing'},{preparation_id:'prep-new-1'}));
    const reply=await f.c.dispatchCoverEvent({type:'AI_COVER_EVENT',request_id:rid,preparation_id:'prep-new-1',event:{phase:'preparing'}},
      {documentId:'doc-new',tab:{id:77,url:'https://chatgpt.com/'}});
    assert.equal(reply.ok,true);assert.equal(f.stored[key].document_id,'doc-new');
  });
  await check('first owned event pins exact document',async()=>{
    const f=fixture({row:{document_id:null}});assert.equal((await f.event({phase:'preparing'})).ok,true);assert.equal(f.stored[key].document_id,'doc-old');
  });
  for(const provider of ['chatgpt','gemini']){
    await check(`legacy ${provider} cover events retain original owner contract`,async()=>{
      const f=fixture({row:{provider,preparation_id:null,document_id:null},
        sender:{tab:{id:77,url:provider==='gemini'?'https://gemini.google.com/app':'https://chatgpt.com/'}}});
      assert.equal((await f.event({phase:'running'})).ok,true);assert.equal(f.count('reload'),0);assert.equal(f.count('start'),0);
    });
  }
  await check('rejected new content START preserves typed never-sent failure',async()=>{
    const f=fixture({badAck:true});await assert.rejects(f.restart());assert.equal(f.count('reload'),1);assert.equal(f.count('start'),1);
    assert.equal(f.events.at(-1).error_code,'AI_SEND_NOT_READY');assert.equal(f.events.at(-1).notDispatched,true);
  });
  await check('empty native page proof',()=>assert.equal(inspect().empty,true));
  for(const [name,config] of Object.entries({draft:{draft:'user draft'},reference:{attachment:true},fileUpload:{files:true},
    conversation:{legacyTurn:true},semanticConversation:{semanticTurn:true},route:{path:'/c/existing'},composerMissing:{noComposer:true}})){
    await check(`native proof rejects ${name}`,()=>assert.equal(inspect(config).empty,false));
  }
  for(const attributes of [{'aria-label':'หยุด'},{'aria-label':'Stop'},{'aria-label':'Stop response'},
    {'aria-label':'Stop generating'},{title:'Stop generating'},{'data-testid':'stop-button'}]){
    await check(`native proof rejects Stop ${JSON.stringify(attributes)}`,()=>assert.equal(inspect({buttons:[attributes]}).empty,false));
  }
  await check('content handoff rejection retains typed never-sent evidence',contentHandoffFailure);
  console.log(JSON.stringify({ok:failures.length===0,cases,failures,providerSubmissions:0}));
  if(failures.length)process.exitCode=1;
})().catch(error=>{console.error(error);process.exit(1);});
