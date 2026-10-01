const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../browser_extension/background.js'),'utf8');
const start=source.indexOf('async function focusSmartFlowBrowser()');
const code=source.slice(start,source.indexOf('async function closeAutomationBrowser(',start));
(async()=>{
 const uri=require('node:url').pathToFileURL(require('node:path').join(__dirname,'../browser_extension/src/'));
 const {ACTIONS,PLATFORM}=await import(new URL('core/constants.js',uri));
 const {JobRouter}=await import(new URL('background/job-router.js',uri));
 const {PlatformAdapter}=await import(new URL('platforms/platform-adapter.js',uri));
 const router=new JobRouter();
 router.registerAdapter(new PlatformAdapter({id:PLATFORM.CORE,actions:ACTIONS[PLATFORM.CORE]}));
 router.assertRegistered({id:'CMD-FOCUS',action:'focus_browser',client_id:'fixture',run_id:'RUN-FOCUS',lease_token:'lease',job_id:''});
 for(const scenario of ['owned','focused','empty','failed']){
  const calls=[];
  const windows=scenario==='empty'?[]:[{id:1,focused:true,state:'normal',tabs:[{id:11}]},{id:2,focused:false,state:'minimized',tabs:[{id:22}]}];
  const context={rememberedAutomationTabIds:async()=>scenario==='focused'?[]:[22],chrome:{windows:{
   getAll:async()=>windows,
   update:async(id,options)=>{calls.push({id,options});},
   get:async()=>({focused:scenario!=='failed',state:'normal'}),
   create:async options=>{calls.push({create:options});}
  }}};
  vm.createContext(context);vm.runInContext(code,context);
  if(scenario==='failed')await assert.rejects(context.focusSmartFlowBrowser(),/CHROME_FOCUS_REVIEW/);
  else await context.focusSmartFlowBrowser();
  assert.equal(calls.length,1);
  if(scenario==='empty')assert.equal(calls[0].create.url,'about:blank');
  else assert.equal(calls[0].id,scenario==='focused'?1:2);
  if(scenario==='owned')assert.equal(calls[0].options.state,'normal');
 }
 console.log('4 profile-focus cases passed; no tab navigation or job dispatch');
})().catch(e=>{console.error(e);process.exitCode=1;});
