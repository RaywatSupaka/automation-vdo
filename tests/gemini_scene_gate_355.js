const fs=require('fs'),vm=require('vm'),assert=require('assert');
const bg=fs.readFileSync('browser_extension/background.js','utf8');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function fn(name){const start=bg.search(new RegExp('(?:async )?function '+name+'\\('));return bg.slice(start,bg.indexOf('\n}',start)+2);}
const start=content.indexOf('const finishScene=async index=>{');
const finish=content.slice(start,content.indexOf('      if(pkg.job.product_story)',start));
const hs=bg.indexOf("    if (message?.type === 'STORY_SCENE_GATE') {");
const handler=bg.slice(hs,bg.indexOf('\n    if (',hs+5));
(async()=>{
 let cases=0;
 for(const provider of ['gemini','chatgpt'])for(const defect of ['', 'missing','wrong_provider','wrong_tab','wrong_run']){
  const id='STORY-FIXTURE',run='RUN-ONE',calls=[],events=[];
  const storage={[`smartpostAIWebTab:${provider}:${id}`]:9,[`smartpostAIWebRun:${id}`]:run};
  const sender={tab:{id:9,url:provider==='gemini'?'https://gemini.google.com/app/1234567890abcdef':'https://chatgpt.com/c/fixture'}};
  let reply;
  const backend=vm.createContext({chrome:{storage:{local:{get:async()=>storage}}},BRIDGE:'offline',
   bridgeFetch:async(url,opt)=>{const body=JSON.parse(opt.body);calls.push(body);return {ok:true,json:async()=>({ok:true,phase:body.action==='status'?'complete':'waiting'})};},
   sendResponse:r=>{reply=r;}});
  for(const name of ['normalizeAIProvider','resultAIProvider','aiRunStorageKey','aiProgressOwnership','assertStoryCheckpointOwner'])vm.runInContext(fn(name),backend);
  vm.runInContext('async function dispatch(message,sender){'+handler+'}',backend);
  const ctx=vm.createContext({metaSequence:false,scenePipeline:true,pkg:{job:{id}},activeRunId:run,PROVIDER_KEY:provider,
   assertNotCancelled:()=>{},result:{},completedImageCount:()=>1,imageCount:3,
   prepareFlowMotionPlan:async()=>events.push('motion'),report:async()=>{},sleep:async()=>{},
   chrome:{runtime:{sendMessage:async msg=>{
    if(defect==='missing')delete msg.provider;
    if(defect==='wrong_provider')msg.provider=provider==='gemini'?'chatgpt':'gemini';
    if(defect==='wrong_run')msg.run_id='RUN-OLD';
    if(defect==='wrong_tab')sender.tab.id=10;
    await backend.dispatch(msg,sender);return reply;
   }}}});
  vm.runInContext(finish+'globalThis.finish=finishScene;',ctx);
  if(defect){await assert.rejects(ctx.finish(1));assert.equal(calls.length,0);assert.equal(events.length,0);}
  else {await ctx.finish(1);assert.deepEqual(calls.map(c=>c.action),['prepare','ready','status']);assert.deepEqual(events,['motion']);assert(calls.every(c=>c.index===1&&c.run_id===run));}
  cases++;
 }
 console.log(JSON.stringify({cases,ok:true}));
})().catch(e=>{console.error(e);process.exitCode=1;});
