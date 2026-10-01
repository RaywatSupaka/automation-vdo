// Execute actual runAICover + actual image tool against the same synthetic DOM.
// No provider requests; browser refresh is separately exercised by its owner tests.
const fs=require('fs'),assert=require('assert/strict'),path=require('path');
const factory=(file,end,name)=>new Function('require','__dirname',fs.readFileSync(path.join(__dirname,file),'utf8').split(end)[0]+`;return ${name};`)(require,__dirname);
const modeFixture=factory('chatgpt_image_tool_447.cjs','async function modeTests(){','modeFixture');
const setup=factory('ai_cover_harness.js','(async()=>{','setup');
let cases=0;
function fixture(config={}){
  const m=modeFixture(config),f=setup({preparationId:'owner-448'}),c=f.c;
  c.composer=m.c.composer;c.composerText=m.c.composerText;
  c.setChatGPTImageTool=m.c.setChatGPTImageTool;
  c.chatGPTImageToolChip=m.c.chatGPTImageToolChip;
  c.chatGPTComposerAttachmentState=()=>({count:0,busy:false,failed:false});
  const previousStop=c.stopButtonVisible;c.stopButtonVisible=()=>f.sends()?previousStop():m.c.stopButtonVisible();
  const originalAttach=c.attachSourceImages;
  c.attachSourceImages=async images=>{assert(m.c.chatGPTImageToolChip(),'must prove selected tool BEFORE attaching');await originalAttach(images);};
  m.c.report=async()=>c.coverEvent({phase:'running',message:'tool selected'});
  return{...f,m};
}
(async()=>{
  for(const config of [{disabled:true,onSleep:m=>{if(m.time===500)m.opener.disabled=false;}},
    {disabled:true,onSleep:m=>{if(m.time===250)m.remount();}},
    {noProof:true,onSleep:m=>{if(m.time===750)m.addChip();}}]){
    const f=fixture(config);await f.run();
    assert.equal(f.events.at(-1).phase,'ready');assert.equal(f.sends(),1);assert.equal(f.attached(),1);assert.equal(f.m.choices,1);
    const preparation=f.events.findIndex(e=>e.preparation_state?.reason==='ready');
    const sending=f.events.findIndex(e=>e.send_state==='unconfirmed');
    assert(preparation>=0&&sending>preparation,'durable pre-send boundary follows tool proof');cases++;
  }
  const late=fixture({disabled:true,onSleep:m=>{if(m.time===30500)m.opener.disabled=false;}});
  await late.run();assert(late.events.some(e=>e.phase==='recovering'));assert.equal(late.sends(),1);assert.equal(late.events.at(-1).phase,'ready');
  assert.deepEqual(late.events.filter(e=>e.phase==='preparing').map(e=>e.preparation_state.attempt),[1,2,2]);cases++;
  const refresh=fixture({disabled:true});let handoffs=0;
  const sendMessage=refresh.c.chrome.runtime.sendMessage;
  refresh.c.chrome.runtime.sendMessage=async message=>{
    if(message.type==='RESTART_AI_COVER_PREPARATION'){
      handoffs++;assert.equal(message.preparation_id,'owner-448');assert.equal(message.attempt,2);return{ok:true};
    }return sendMessage(message);
  };
  await refresh.run();assert.equal(handoffs,1);assert.equal(refresh.sends(),0);assert.equal(refresh.attached(),0);
  assert.equal(refresh.events.at(-1).phase,'recovering');assert.equal(refresh.c.activeCoverRequest,null);cases++;
  for(const config of [{options:2},{busy:true},{disabled:true,onSleep:m=>{m.editor.textContent='human draft';}}]){
    const f=fixture(config);await f.run();assert.equal(f.sends(),0);assert.equal(f.attached(),0);
    assert.equal(f.events.at(-1).phase,'needs_review');assert.equal(f.events.at(-1).error_code,'AI_SEND_NOT_READY');cases++;
  }
  const cancelled=fixture({disabled:true,onSleep:m=>m.cancel()});await cancelled.run();assert.equal(cancelled.sends(),0);assert.equal(cancelled.attached(),0);cases++;
  // Once the Send boundary is crossed a failed send is not a preparation retry.
  const uncertain=fixture();let sends=0;
  uncertain.c.sendCoverAndVerify=async()=>{sends++;throw Object.assign(Error('unknown send'),{code:'AI_SEND_NOT_READY',notDispatched:true,toolReason:'opener_missing',transient:true});};
  await uncertain.run();assert.equal(sends,1);assert.equal(uncertain.events.at(-1).phase,'needs_review');
  assert.equal(uncertain.events.at(-1).preparation_state,undefined);assert.equal(uncertain.events.filter(e=>e.phase==='recovering').length,0);cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
