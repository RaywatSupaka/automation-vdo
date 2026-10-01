const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const fn=source.slice(source.indexOf('  async function checkpointEditorialAnalysis('),source.indexOf('  async function runJob('));
const pkg={job:{id:'STORY-TEST'},request:{required_fields:[]}};
async function scenario({resume=false,exhaust=false,unknown=false,legacy=false}={}){
 let sends=0,reads=0,marks=0,saves=0,phase=resume?'sending':'prepared';
 const state=()=>({status:'needs_repair',phase,request_id:'one',request:'owned request',attempts:1,
   affected_scenes:[2],provider:'chatgpt',conversation_url:'https://chatgpt.com/c/test'});
 const c={activeRunId:'RUN-X',PROVIDER_KEY:'chatgpt',location:{href:'https://chatgpt.com/c/test'},
   assertNotCancelled(){},async report(){},analysisFormatGuard(){},analysisFormatAnswerSignature(){return 'owned';},
   validateAnalysis:v=>v,extractJson:v=>v,
   async readPendingAnalysis(p){assert.equal(p.ai_resume.request,'owned request');reads++;return {fixed:true};},
   async submitPrompt(text,urls,ref,count,before){sends++;assert.equal(text,'owned request');assert.equal(urls.length,0);await before();
     if(unknown)throw Error('unknown Send');return {fixed:true};},
   chrome:{runtime:{async sendMessage(m){
     if(m.type==='PRODUCT_EDITORIAL_SENDING'){marks++;phase='sending';return {ok:true,editorial:state()};}
     saves++;return {ok:true,...(legacy?{}:{editorial:exhaust?{status:'needs_review'}:
       m.result.fixed?{status:'approved',approved_hash:'hash'}:state()})};
   }}}};vm.createContext(c);vm.runInContext(fn+';globalThis.run=checkpointEditorialAnalysis;',c);
 const p={...pkg,...(resume?{product_editorial_state:{...state(),draft:{bad:true}}}:{})};
 if(exhaust || unknown){await assert.rejects(()=>c.run(p,{bad:true},'scene_prompts',3),exhaust?/PRODUCT_EDITORIAL_REVIEW/:/unknown Send/);}
 else{const value=await c.run(p,{bad:true},'scene_prompts',3);assert.equal(Boolean(value.fixed),!legacy);}
 assert.equal(sends,resume||exhaust||legacy?0:1);assert.equal(reads,resume?1:0);
 assert.equal(marks,sends);if(unknown)assert.equal(saves,1);
}
(async()=>{for(const options of [{},{resume:true},{exhaust:true},{unknown:true},{legacy:true}])await scenario(options);
 const gate=source.indexOf('result=await checkpointEditorialAnalysis(pkg,result');
 assert(gate>0 && gate<source.indexOf('const sceneContents =',gate));
 assert(source.indexOf('pkg.product_editorial_state?.draft')>0);
 const bg=fs.readFileSync('browser_extension/background.js','utf8');
 const handler=bg.slice(bg.indexOf("message?.type === 'PRODUCT_EDITORIAL_SENDING'"),bg.indexOf('message?.type === "CHECKPOINT_STORY_ANALYSIS"'));
 assert(handler.includes('assertStoryCheckpointOwner'));assert(handler.includes('/api/stories/editorial-sending'));
 console.log('editorial shared ChatGPT/Gemini handshake: 5 cases and gate/owner ordering passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
