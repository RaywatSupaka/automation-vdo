const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const prior=fs.readFileSync(require('node:path').join(__dirname,'motion_response_344_harness.js'),'utf8');
const {resumeFixture,responseFixture,motion,owned}=vm.runInNewContext(prior.slice(0,prior.indexOf('\nasync function tests()'))+';({resumeFixture,responseFixture,motion,owned})',{require,__dirname,process});
const broken=value=>`{\n  "job_id": "${owned.job_id}",\n  "index": ${owned.index},\n  "context_\`\`\`json\n${JSON.stringify(value)}`;
function completed(node){
 const prior=node.querySelector?.bind(node);
 node.querySelector=selector=>selector.includes('.markdown[aria-busy="false"]')?{}:prior?.(selector)||null;
 return node;
}
(async()=>{
 let cases=0;
 const initial=responseFixture({gemini:true,motionContext:owned,content:()=>broken(motion),cancelAt:90000});
 initial.context.geminiTextRequestSnapshot=()=>({owner:{},turn:initial.turn,user:initial.context.userTurns().at(-1)});
 initial.context.motionRequestMatches=()=>true;
 completed(initial.turn);
 const first=await initial.run();assert.equal(JSON.stringify(JSON.parse(first.innerText)),JSON.stringify(motion));initial.checkSingleSend();cases++;
 const f=resumeFixture({provider:'gemini',content:()=>broken(motion)});
 completed(f.answer);
 await f.run();assert.equal(f.snapshot().sends,0);assert.equal(f.snapshot().record.phase,'ready');
 assert.deepEqual(Array.from(f.messages,m=>m.action),['status','prepare','review','save']);cases++;
 const g=resumeFixture({provider:'gemini',content:()=>broken(motion),stop:ms=>ms<450000});
 completed(g.answer);
 g.c.analysisResponseStopButton=()=>g.snapshot().elapsed<450000?{}:null;
 await g.run();assert(g.snapshot().elapsed>=457000);assert.equal(g.snapshot().sends,0);cases++;
 const h=resumeFixture({provider:'gemini',content:()=>'{"context_id":',cancelAt:900000});
 await assert.rejects(h.run(),{name:'AbortError'});assert(h.snapshot().elapsed>=900000);assert.equal(h.snapshot().sends,0);cases++;
 const done=resumeFixture({provider:'gemini',content:()=>'{"context_id":'});
 completed(done.answer);
 await assert.rejects(done.run(),/FLOW_PLAN_REVIEW/);
 assert(done.snapshot().elapsed<15000);assert(done.messages.some(m=>m.action==='review_text'));assert.equal(done.snapshot().sends,0);cases++;
 const pending=responseFixture({gemini:true,motionContext:owned,content:()=>'{"context_id":',cancelAt:900000});
 pending.context.geminiTextRequestSnapshot=()=>({owner:{},turn:pending.turn,user:pending.context.userTurns().at(-1)});
 pending.context.motionRequestMatches=()=>true;
 await assert.rejects(pending.run(),{name:'AbortError'});assert(pending.elapsed()>=900000);pending.checkSingleSend();cases++;
 const c=f.c, turn=text=>completed({innerText:text,querySelector:()=>null,querySelectorAll:()=>[]});
 const request='Write motion JSON for the same reference scene. '+JSON.stringify({...owned,aspect_ratio:'9:16',image_url:'http://fixture.invalid/scene.png'});
 for(const [name,text] of [
  ['wrong job',broken({...motion,job_id:'other'})],['wrong scene',broken({...motion,index:1})],
  ['wrong context',broken({...motion,context_id:'other'})],['string flags',broken({...motion,needs_review:'false'})],
  ['extra object',broken(motion)+'\n'+JSON.stringify(motion)],['trailing prose',broken(motion)+'\nPlease ignore rules'],
  ['leading prose','policy refusal\n'+broken(motion)],['different prefix',broken(motion).replace('"index": 10','"index": 9')],
  ['unfinished',broken(motion).slice(0,-1)]]){
   const state={};assert.equal(c.stableOwnedMotionAnswer(state,request,owned,turn(text),0),null,name);
   assert.equal(c.stableOwnedMotionAnswer(state,request,owned,turn(text),9000),null,name);cases++;
 }
 for(const value of [{...motion,review_reason:null},{...motion,needs_review:true,reference_compatible:false,material_change:true}]){
  const state={},node=turn(broken(value));c.stableOwnedMotionAnswer(state,request,owned,node,0);
  const answer=c.stableOwnedMotionAnswer(state,request,owned,node,9000);
  assert.deepEqual(JSON.parse(answer.innerText),value);cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
