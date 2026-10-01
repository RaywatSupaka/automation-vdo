const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const bg=fs.readFileSync('browser_extension/background.js','utf8');
const block=bg.slice(bg.indexOf("    if(message?.type==='RELOAD_GEMINI_STORY')"),bg.indexOf("    if (message?.type === 'FLOW_MOTION_PLAN')"));
async function runCase(change={}){
 const message={type:'RELOAD_GEMINI_STORY',job_id:'STORY-X',run_id:'RUN-X',provider:'gemini',index:2};
 const key='smartpostStoryGeneratedImage:gemini:STORY-X:2',budget='smartflowGeminiReload:STORY-X:2';
 const tab={id:1,url:'https://gemini.google.com/app/exact'};const data={[key]:{status:'pre_send_reload',run_id:'RUN-X',result_proof:{conversation_url:tab.url}},...change};
 let reload=0,resume=0;const errors=[];
 const c=vm.createContext({geminiReloadLocks:new Set(),message,sender:{tab},sendResponse:()=>{},setTimeout:f=>f(),assertStoryCheckpointOwner:async()=>{},
 chrome:{storage:{local:{get:async()=>data,set:async v=>Object.assign(data,v)}},tabs:{get:async()=>tab,reload:async()=>{reload++;}}},
 waitForTabComplete:async()=>{},startAIWebJob:async(...args)=>{assert.deepEqual(args.slice(0,5),['STORY-X',true,'gemini',false,'RUN-X']);assert.equal(args[6],'new-document');await args[5](1);resume++;},reportWebActionProgress:async v=>errors.push(v)});
 require('./shared_refresh_fixture_439.cjs').install(c);
 await vm.runInContext(`(async()=>{${block}})()`,c);
 return {reload,resume,data,budget,errors,c};
}
(async()=>{
 const good=await runCase();assert.equal(good.reload,1);assert.equal(good.resume,1);
 await assert.rejects(vm.runInContext(`(async()=>{${block}})()`,good.c),/budget/);assert.equal(good.data[good.budget].phase,'resumed');
 await assert.rejects(runCase({'smartpostStoryGeneratedImage:gemini:STORY-X:2':{status:'awaiting_result'}}),/proof/);
 const cancel=await runCase({'smartflowGeminiReloadCancelled:STORY-X':'RUN-X'});assert.equal(cancel.reload,0);assert.equal(cancel.resume,0);
 const src=fs.readFileSync('browser_extension/chatgpt.js','utf8');
 const accept=src.slice(src.indexOf('  function geminiImageSendAccepted('),src.indexOf('  function geminiTextSendReview('));
 const c=vm.createContext({motionRequestIsLatestUser:()=>false});vm.runInContext(accept,c);
 const before={job:'STORY-X',run:'R',url:'same',prompt:'scene2',composerPresent:true,userCount:1,userSignature:'old'};
 assert.equal(c.geminiImageSendAccepted(before,{...before,stopped:true,assistantCount:99}),false);
 c.motionRequestIsLatestUser=()=>true;
 assert.equal(c.geminiImageSendAccepted(before,{...before,userCount:2}),false,'owned echo with unsent draft is not acceptance');
 assert.equal(c.geminiImageSendAccepted(before,{...before,prompt:'',userCount:2}),true);
 const data={};const rc=vm.createContext({PROVIDER_KEY:'gemini',IS_GEMINI:true,activeRunId:'RUN-X',location:{href:'https://gemini.google.com/app/exact'},
   assertNotCancelled:()=>{},stopButtonVisible:()=>false,motionRequestIsLatestUser:()=>false,
   sameStoryImageReceipt:(a,b)=>JSON.stringify(a)===JSON.stringify(b),storyImageRecoveryError:(_code,_index,text)=>Error(text),
   chrome:{storage:{local:{get:async()=>data,set:async v=>Object.assign(data,v)}}}});
 vm.runInContext(src.slice(src.indexOf('  function createStoryImageReceipt('),src.indexOf('  function largeAssistantImages(')),rc);
 const pkg={job:{id:'STORY-X'},request:{},image_urls:[]};const receipt=rc.createStoryImageReceipt(pkg,2,['scene'],1);
 await receipt.restore();await receipt.begin();await receipt.missingSend('exact draft');
 const recovered=rc.createStoryImageReceipt(pkg,2,['scene'],1);assert.equal(await recovered.restore(),null);await recovered.begin();assert.equal(recovered.retryInstruction(),'exact draft');
 console.log(JSON.stringify({ok:true,cases:7}));
})().catch(e=>{console.error(e);process.exitCode=1;});
