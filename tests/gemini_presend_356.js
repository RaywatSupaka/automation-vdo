const fs=require('fs'),vm=require('vm'),assert=require('assert');
const s=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const start=s.indexOf('  async function waitGeminiTextPreSend('),end=s.indexOf('  async function sendGeminiTextAndVerify(',start);
(async()=>{
 for(const mode of ['ready','delayed','busy','edited','timeout','cancel']){
 let tick=0;const initial={job:'J',run:'R',url:'U',prompt:'hello',ready:true,busy:false,stopped:false,expanded:false};
 const c=vm.createContext({Date:{now:()=>tick},assertNotCancelled:()=>{if(mode==='cancel')throw Error('cancel');},sleep:async ms=>{tick+=ms;},
 geminiTextSendState:()=>({...initial,ready:mode==='timeout'?false:mode==='delayed'?tick>=750:true,busy:mode==='busy'&&tick<1000,prompt:mode==='edited'?'changed':'hello'}),
 geminiTextSendReview:m=>Error(m),geminiTextSendChanges:()=>['send_not_ready']});vm.runInContext(s.slice(start,end),c);
 if(['edited','timeout','cancel'].includes(mode))await assert.rejects(c.waitGeminiTextPreSend(initial,'hello'));
 else {const result=await c.waitGeminiTextPreSend(initial,'hello');assert(result.ready&&!result.busy);}
 }
 console.log('6 Gemini presend cases passed');
})().catch(e=>{console.error(e);process.exitCode=1});
