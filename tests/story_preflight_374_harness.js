const assert=require('node:assert/strict');
const {fixture}=require('./ai_send_acceptance_harness');
const {routing}=require('./ai_web_resume_345_harness');
(async()=>{
 let cases=0;
 for(const variant of ['unchanged','unicode_space','settling','changed','blocked','prior_press','late_claim','wrong_claim','press_lost']){
  const f=fixture({storyClaim:true,acceptImmediately:true,blocked:variant==='blocked',
   claimAlreadyPressed:variant==='prior_press',claimMismatch:variant==='wrong_claim',
   pressResponseLost:variant==='press_lost',noCapturedEvents:variant==='press_lost'});
  const expected=f.storage[f.claim.key].result_proof.prompt;
  if(variant==='unicode_space')f.state.editor.innerText=expected.replace('existing response','existing\u00a0\u00a0response');
  if(['changed','settling'].includes(variant))f.state.editor.innerText='A genuinely different prompt';
  let resamples=0;
  if(variant==='settling')f.backend.setTimeout=(cb,ms)=>{
   if(ms===150){resamples++;f.state.editor.innerText=expected;}cb();
  };
  if(variant==='late_claim')f.backend.chrome.debugger.attach=async()=>{f.storage[f.claim.key+':dispatch']=f.claim.nonce;};
  const result=await f.backend.handle({type:'CLICK_AI_SEND_BUTTON',provider:'chatgpt',job_id:'JOB-TEST',
    run_id:'run-test',expectedPrompt:expected,story_send_claim:f.claim},
    {tab:{id:12,windowId:2,url:'https://chatgpt.com/c/existing'}});
  const presses=f.commands.filter(e=>e.type==='mousePressed').length;
  if(['unchanged','unicode_space','settling'].includes(variant)) {assert.equal(result.ok,true,variant);assert.equal(presses,1);}
  else if(['changed','blocked'].includes(variant)){assert.equal(presses,0);assert.equal(result.notDispatched,true);assert.equal(result.diagnostics.gesture_phase,'not_started');}
  else if(variant==='press_lost'){assert.equal(presses,1);assert.notEqual(result.notDispatched,true);}
  else {assert.equal(presses,0);assert.notEqual(result.notDispatched,true);}
  if(variant==='settling')assert.equal(resamples,1,'Must recover in the read-only mismatch resample, not before first preflight');
  cases++;
 }
 for(const kind of ['closed','root','existing','redirect']){await routing('chatgpt',kind,'image');cases++;}
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
