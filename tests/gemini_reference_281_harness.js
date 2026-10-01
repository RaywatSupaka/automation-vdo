const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const start=source.indexOf('      const deadline = Date.now() + 20000;',source.indexOf('async function attachSourceImages'));
const end=source.indexOf('      await report("recovery_reference_ready"',start);
const body=source.slice(start,end);
async function run({gemini=true,same=true,busy=false,loaded=true,count=1,label='',replace=false}={}){
 let time=0;const file={},preview={tagName:'IMG',complete:loaded,naturalWidth:loaded?512:0};
 const c=vm.createContext({Date:{now:()=>time},IS_GEMINI:gemini,strictReference:'expected-reference',
  expectedCount:1,files:[file],input:{files:[same?file:{}]},
  localPreviews:()=>Array.from({length:count},()=>replace?{...preview}:preview),
  referenceShell:()=>({textContent:label,querySelectorAll:()=>[],querySelector:()=>busy?{}:null}),
  assertNotCancelled:()=>{},sleep:async ms=>{time+=ms;}});
 await vm.runInContext('(async()=>{'+body+'})()',c);
 return time;
}
(async()=>{
 assert(await run()>=1000,'unnamed new loaded Gemini preview needs stability');
 for(const options of [{same:false},{busy:true},{loaded:false},{count:0},{count:2},{replace:true},{gemini:false}])
  await assert.rejects(run(options),/AI_IMAGE_REFERENCE_UNCONFIRMED/);
 await run({gemini:false,label:'expected-reference'});
 console.log('9 attachment proof cases passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
