// Real background/controller functions; no provider or running browser access.
const fs=require('fs'),assert=require('node:assert/strict');
const {setup,content,key}=new Function('require','__dirname',
 fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]
 +';return {setup,content,key};')(require,__dirname);
const service={failure_code:'FLOW_GENERATION_FAILED',confirmed_uncharged_failure:true,failure_reason:'หมดเวลาสร้าง โปรดลองอีกครั้ง'};
(async()=>{
 let cases=0;
 for(const provider of ['chatgpt','gemini'])for(const legacy of [false,true]){
  const f=await setup(provider,service);
  const previous={...f.storage[key],phase:'needs_review',alternative:true,alternative_stage:'proposal',
   rebuild_scene:true,revise_story:true,error:'ภาพทางเลือกต้องเปลี่ยนสาระหรือยังต้องตรวจ • new staging',
   digest:'review1',helper_tab:0};
  f.storage[key]=previous;
  const permit={token:'manual1',index:1,request_id:previous.request_id,event_digest:'review1',review_checkpoint:previous};
  if(legacy){
   f.storage[`${key}:history:${previous.request_id}`]=structuredClone(previous);
   f.storage[key]={...previous,phase:'manual_restart',manual_token:'manual1',error:'',pause_reason:'',candidate:null,round:0};
  }
  const fetch=f.c.bridgeFetch;
  let begins=0;
  f.c.bridgeFetch=async(url,opts)=>{
   if(url.includes('/flow-package'))return {ok:true,json:async()=>({ok:true,package:{image_ai_provider:provider,
    image_urls:['http://fixture/scene.png'],manual_flow_repair:permit}})};
   const body=JSON.parse(opts?.body||'{}');
   if(body.replacement_action==='begin'){
    begins++;assert.equal(body.manual_resume_token,'manual1');assert.equal(body.previous_request_id,previous.request_id);
    return {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16',audio_instruction:'ACTOR DIALOGUE: This scene is intentionally silent: no speech; acting only.'},
     replacement:{rebuild_scene:true,revise_story:true,phase:'requested'}})};
   }return fetch(url,opts);
  };
  f.storage.smartpostFlowMonitor.startedAt=1;
  const resumed=await f.call({action:'manual_restart',token:'manual1'});
  assert.equal(resumed.phase,'manual_restart');
  const patch={action:'start_alternative',rebuild_scene:true,revise_story:true,failure_id:'1:fp'};
  const result=await f.call(patch);
  assert.equal(result.phase,'rewrite_sent','manual restart must leave old alternative dead end');
  assert.notEqual(result.request_id,previous.request_id);
  assert(result.request.includes('Use real booleans'));
  assert(result.request.includes('A deliberate change alone is not unresolved review'));
  assert(result.request.includes('intentionally silent'));
  await f.call(patch);assert.equal(begins,1,'one explicit resume cannot create duplicate helper');
  assert(f.storage[`${key}:history:${previous.request_id}`]);cases++;
 }
 for(const stage of ['image_sent','image_saved','motion_sent']){
  const f=await setup('chatgpt',service),previous={...f.storage[key],phase:'needs_review',alternative:true,
   alternative_stage:stage,error:'Needs inspection',digest:'d'};
  f.storage[key]=previous;const fetch=f.c.bridgeFetch;
  f.c.bridgeFetch=async(url,opts)=>url.includes('/flow-package')?{ok:true,json:async()=>({ok:true,package:{image_ai_provider:'chatgpt',
   manual_flow_repair:{token:'t',index:1,request_id:previous.request_id,event_digest:'d',review_checkpoint:previous}}})}:fetch(url,opts);
  const opened=f.events.filter(x=>x==='open').length;
  const row=await f.call({action:'manual_restart',token:'t'});
  assert.equal(row.phase,'needs_review');assert.equal(row.alternative_stage,stage);
  assert.equal(f.events.filter(x=>x==='open').length,opened);cases++;
 }
 // A rejected begin/legacy manual restart must not be advertised as active work.
 for(const returned of ['needs_review','manual_restart','cancelled']){
  const f=content('missing');f.c.pkg.flow_repair={enabled:true,rebuild_scene_on_failure:true};
  const send=f.c.chrome.runtime.sendMessage;
  f.c.chrome.runtime.sendMessage=async m=>m.action==='start_alternative'
   ?(f.messages.push(m),{ok:true,phase:returned,error:'saved terminal'}):send(m);
  await f.run(service);
  assert(f.reports.some(([step])=>step==='error'));
  assert(!f.messages.some(m=>m.type==='CLICK_FLOW_GENERATE'));cases++;
 }
 console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e);process.exitCode=1;});
