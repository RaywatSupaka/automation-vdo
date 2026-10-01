// Native isolated Chrome storage/message transport. Never user Chrome/provider URLs.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),vm=require('node:vm');
const {chromium}=require('playwright');
(async()=>{
  const fixtureDir=path.resolve('tests/fixtures/review_storage_419');
  const context=await chromium.launchPersistentContext('',{headless:true,channel:'chromium',
    args:[`--disable-extensions-except=${fixtureDir}`,`--load-extension=${fixtureDir}`]});
  try{
    const worker=context.serviceWorkers()[0] || await context.waitForEvent('serviceworker',{timeout:15000});
    const id=new URL(worker.url()).host;
    const page=await context.newPage();
    await page.goto(`chrome-extension://${id}/probe.html`);
    const candidate={prompt:'Vertical 9:16. A fictional gardener walks beside a garden gate.',
      needs_review:true,reference_compatible:false,material_change:true,change_summary:'Choose a different benign scene.'};
    const result=await page.evaluate(candidate=>chrome.runtime.sendMessage({type:'roundtrip',candidate}),candidate);
    assert.deepEqual(result.stored,candidate);
    assert.deepEqual(result.transported,candidate);
    assert.notEqual(JSON.stringify(result.stored),JSON.stringify(result.transported),'Exercise the native storage reorder, not an identity mock');
    function handler(source){
      const section=source.slice(source.indexOf("    if (message?.type === 'FLOW_ALTERNATIVE_EVENT')"),source.indexOf("    if (message?.type === 'AI_COVER_EVENT')"));
      const row={alternative:true,phase:'rewrite_sent',request_id:'owned',helper_tab:8,owner_tab:5,provider:'chatgpt',
        job_id:'STORY-T',run_id:'RUN-1',index:15,creative_revision_version:1,creative_round:0,alternative_stage:'motion_sent',completed_motion_candidate:result.stored};
      let bridges=0;
      const c=vm.createContext({URL,JSON,Number,String,BRIDGE:'http://fixture.invalid',
        chrome:{storage:{local:{get:async()=>({key:row})}},tabs:{get:async()=>({id:5})}},
        assertFlowRepairOwner:async()=>{},bridgeFetch:async()=>{bridges++;return {ok:true,json:async()=>({ok:true})};}});
      vm.runInContext('async function handle(message,sender,sendResponse){'+section+'}',c);
      return {row,call:(changes={},sender={tab:{id:8,url:'https://chatgpt.com/c/fixture'}})=>c.handle({
        type:'FLOW_ALTERNATIVE_EVENT',key:'key',request_id:'owned',action:'redesign',creative_round:0,candidate:result.transported,...changes},sender,()=>{}),
        get bridges(){return bridges;}};
    }
    const old=handler(fs.readFileSync('deliverables/SmartFlow_AI_Extension_0.15.418/background.js','utf8'));
    await assert.rejects(()=>old.call(),/ยังไม่มีคำตอบตรวจภาพใหม่/);assert.equal(old.bridges,0);
    const fixed=handler(fs.readFileSync('browser_extension/background.js','utf8'));
    await fixed.call();assert.equal(fixed.bridges,1);
    for(const [field,value] of Object.entries(candidate)){
      await assert.rejects(()=>fixed.call({candidate:{...candidate,[field]:typeof value==='boolean'?!value:value+' changed'}}));
    }
    for(const change of [{request_id:'other'},{creative_round:1},{candidate:null},{candidate:{}},
      {candidate:{...candidate,extra:'unexpected'}},{candidate:{...candidate,needs_review:'true'}}])
      await assert.rejects(()=>fixed.call(change));
    await assert.rejects(()=>fixed.call({}, {tab:{id:9,url:'https://chatgpt.com/c/fixture'}}));
    fixed.row.alternative_stage='image_sent';await assert.rejects(()=>fixed.call());
    fixed.row.alternative_stage='motion_sent';delete fixed.row.completed_motion_candidate;await assert.rejects(()=>fixed.call());
    assert.equal(fixed.bridges,1,'No mismatched result may rotate a scene');
    // Nested key order is irrelevant, but array ordering and all values remain exact.
    const nested=handler(fs.readFileSync('browser_extension/background.js','utf8'));
    const withTurns={...candidate,turns:[{speaker:'A',text:'hello'},{speaker:'B',text:'reply'}]};
    const native=await page.evaluate(candidate=>chrome.runtime.sendMessage({type:'roundtrip',candidate}),withTurns);
    nested.row.completed_motion_candidate=native.stored;
    await nested.call({candidate:native.transported});
    await assert.rejects(()=>nested.call({candidate:{...withTurns,turns:[...withTurns.turns].reverse()}}));
    assert.equal(nested.bridges,1);
    console.log('Native Chrome storage/message RED418 -> current GREEN; exact value/array/owner guards passed');
  }finally{await context.close();}
  const testSource=fs.readFileSync('tests/flow_creative_recovery_402.js','utf8').split('async function run(){')[0];
  const fixture=new Function('require',testSource+';return fixture;')(require);
  for(const provider of ['chatgpt','gemini']){
    const red=fixture(provider,{storageOrder:true,motionReviews:1,oldHelper:true,oldBackground:true});
    await assert.rejects(()=>red.run(false),/ยังไม่มีคำตอบตรวจภาพใหม่/);assert.equal(red.images,1);
    const continuous=fixture(provider,{storageOrder:true,motionReviews:8});
    await continuous.run(false);
    assert.equal(continuous.row.phase,'ready');assert.equal(continuous.images,9);
    assert.equal(continuous.row.creative_round,8);assert.equal(continuous.events.filter(e=>e.action==='redesign').length,8);
    const crash=fixture(provider,{storageOrder:true,motionReviews:1,crash:true});
    await assert.rejects(()=>crash.run(false),/crash after redesign/);
    await crash.run(true);assert.equal(crash.row.phase,'ready');assert.equal(crash.images,2);
    assert.equal(crash.events.filter(e=>e.action==='redesign').length,1,'Lost ACK cannot rotate twice');
    const oldResume=fixture(provider,{storageOrder:true,motionReviews:1,crash:true,oldHelper:true});
    await assert.rejects(()=>oldResume.run(false),/crash after redesign/);
    await assert.rejects(()=>oldResume.run(true),/ผลตรวจภาพก่อนออกแบบใหม่เปลี่ยนไป/);
    assert.equal(oldResume.images,1);
    const tampered=fixture(provider,{storageOrder:true,motionReviews:1,crash:true});
    await assert.rejects(()=>tampered.run(false),/crash after redesign/);
    tampered.row.completed_motion_candidate.prompt+=' different';
    await assert.rejects(()=>tampered.run(true),/ผลตรวจภาพก่อนออกแบบใหม่เปลี่ยนไป/);assert.equal(tampered.images,1);
  }
  console.log('Both provider helpers + actual background: 8 redesign rounds, Resume, tamper and RED418 passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
