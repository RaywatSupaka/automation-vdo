const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const old=fs.readFileSync('deliverables/SmartFlow_AI_Extension_0.15.408/background.js','utf8');
function section(s,a,b){const start=s.indexOf(a),end=s.indexOf(b,start+a.length);assert(start>=0&&end>start);return s.slice(start,end);}
const report=s=>section(s,'async function reportWebActionProgress(', 'async function reportExtensionTrace(');
const wait=s=>section(s,'async function waitForTabComplete(',s===old?'async function ensureFlowHelper(':'async function waitForAIRefreshReady(');
const ready=section(source,'async function waitForAIRefreshReady(','async function ensureFlowHelper(');
(async()=>{
 let checks=0;
 for(const [s,scope] of [[old,'story'],[source,'chatgpt']]){
  let sent;const c=vm.createContext({BRIDGE:'offline',CLIENT_ID:'fixture',bridgeFetch:async(_u,o)=>sent=JSON.parse(o.body)});
  vm.runInContext(report(s),c);await c.reportWebActionProgress({scope:'story',step:'error',jobId:'STORY-fixture',provider:'chatgpt',runId:'RUN'});
  assert.equal(sent.scope,scope);assert.equal(sent.run_id,'RUN');checks++;
 }
 for(const s of [old,source]){
  const listeners=new Set();let reads=0;
  const c=vm.createContext({setTimeout,clearTimeout,setInterval,clearInterval,chrome:{tabs:{
   get:async()=>{reads++;for(const fn of [...listeners])fn(7,{status:'complete'});return {status:'loading'};},
   onUpdated:{addListener:fn=>listeners.add(fn),removeListener:fn=>listeners.delete(fn)}}}});
  vm.runInContext(wait(s),c);
  if(s===old)await assert.rejects(c.waitForTabComplete(7,25));else await c.waitForTabComplete(7,25);
  assert.equal(listeners.size,0);assert.equal(reads,1);checks++;
 }
 for(const mode of ['ready','slow','navigation','draft','owner','timeout']){
  let now=0,probes=0,guards=0,notices=0,probeFn;
  const c=vm.createContext({Date:{now:()=>now},setTimeout:(fn,ms)=>{now+=ms;queueMicrotask(fn);},
   chrome:{scripting:{executeScript:async req=>{probeFn=req.func;probes++;
    if(mode==='navigation'&&probes===1)throw Error('document navigating');
    return [{result:{ready:mode!=='timeout'&&(mode!=='slow'||now>=60000),draft:mode==='draft'}}];}}}});
  vm.runInContext(ready,c);
  const run=()=>c.waitForAIRefreshReady(7,async()=>{guards++;if(mode==='owner'&&guards===2)throw Error('cancelled');},async()=>notices++,70000);
  if(['draft','owner','timeout'].includes(mode))await assert.rejects(run());else await run();
  if(mode==='slow'){assert(now>=60000);assert(notices>=6);}
  if(mode==='navigation')assert.equal(probes,2);
  if(mode==='owner')assert.equal(probes,1);
  if(mode==='ready'){
   for(const [doc,expected] of [
    [{readyState:'interactive',editor:true,thread:true,text:''},true],
    [{readyState:'loading',editor:true,thread:true,text:''},false],
    [{readyState:'complete',editor:false,thread:true,text:''},false],
    [{readyState:'complete',editor:true,thread:false,text:''},false]]){
    c.document={readyState:doc.readyState,querySelector:q=>q.split(',').includes('[data-message-author-role]')?doc.thread:null,
     querySelectorAll:q=>q.startsWith('#prompt-textarea')&&doc.editor
       ?[{getBoundingClientRect:()=>({width:200,height:50}),textContent:doc.text}]:[]};
    const state=vm.runInContext('('+probeFn.toString()+')()',c);assert.equal(state.ready,expected);checks++;
   }
  }
  checks++;
 }
 console.log(JSON.stringify({ok:true,checks}));
})().catch(e=>{console.error(e);process.exitCode=1;});
