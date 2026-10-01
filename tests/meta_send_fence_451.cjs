const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/src/platforms/meta-ai/video.js','utf8');
const sandbox={URL,Date};vm.runInNewContext(source.replaceAll('export ', '')+'\nthis.Adapter=MetaVideoAdapter;',sandbox);
vm.runInNewContext(fs.readFileSync('browser_extension/single_answer.js','utf8'),sandbox);
const clone=x=>JSON.parse(JSON.stringify(x));let checks=0;
async function run(change,where='ack',choice=false,planned=false){
 let receipt={job_id:'STORY-FIXTURE',index:1,request_id:'r',context_id:'c',stage:choice?'generating':'ready_to_send',prompt:'owned prompt',image_name:'scene.png'};
 if(planned)receipt.scene_video_plan={version:1,scene_index:1,plan_revision:1,selection_id:'s',attempt_id:'a',provider:'meta_ai',settings_sha256:'a'.repeat(64)};
 if(choice)receipt.choice={stage:'prepared',prompt:'owned choice',proposal_text:'proposal'};
 let state={composerFound:true,composerCount:1,composerText:choice?'owned choice':'owned prompt',userCount:choice?1:0,
  busy:false,stop:false,uploadDialog:false,documentReady:true,documentId:'document-1',observedURL:'https://www.meta.ai/',
  imageCount:choice?0:1,imageReady:!choice,imageName:'scene.png',imageSource:'blob:original',send:{x:50,y:50},sendTarget:'target-1',
  matchedOriginal:choice,proposalText:'proposal',proposalBusy:false,proposalVideoCount:0};
 let owner=true,tab={url:'https://www.meta.ai/',status:'complete'},current=true,scans=0;
 const storage={},events=[],physical=[];
 const mutate=()=>{if(change==='draft')state.composerText='manual draft';if(change==='stop'){state.stop=true;state.send=null;}
  if(change==='move')state.send={x:150,y:150};if(change==='target')state.sendTarget='another-button';
  if(change==='image')state.imageSource='blob:other';if(change==='document')state.documentId='document-2';
  if(change==='owner')owner=false;if(change==='cancel')current=false;if(change==='navigation')tab.url='https://www.meta.ai/prompt/other';
  if(change==='plan')receipt.scene_video_plan={...receipt.scene_video_plan,attempt_id:'successor'};};
 const api=async(route,body)=>{if(!body){if(!current)throw Error('cancelled');return{package:clone(receipt)};}
  // This fixture owns the gesture boundary only. Lost-session recovery has a
  // separate durable-successor harness; do not model it as an ordinary stage.
  if(body.stage==='fresh_start')throw Error('fresh recovery fixture boundary');
  events.push(clone(body));receipt={...receipt,...body};if(body.stage==='choice_send_intent')receipt.choice={...receipt.choice,stage:'send_intent',send_at:Date.now()/1000};
  if(where==='ack'&&['send_intent','choice_send_intent'].includes(body.stage))mutate();
  return{receipt:{...clone(receipt),choice_send_authorized:true}};};
 const chrome={storage:{local:{get:async()=>clone(storage),set:async value=>Object.assign(storage,clone(value))}},tabs:{get:async()=>clone(tab)},
  debugger:{attach:async()=>{if(where==='attach')mutate();},detach:async()=>{},sendCommand:async(target,method,params)=>{
   if(method==='Input.dispatchMouseEvent'){physical.push(clone(params));if(params.type==='mousePressed'&&where==='press')mutate();}return{};}}};
 const adapter=new sandbox.Adapter({api,chromeAPI:chrome});adapter.owns=async()=>owner;adapter.inspect=async()=>{scans++;return {...clone(state),composerWireText:sandbox.SmartFlowSingleAnswer.wrap(state.composerText)};};
 const row={...receipt,tabId:1};await adapter.step(row);try{await adapter.step(row);}catch(error){
  assert(!current || change==='owner'&&error.message==='fresh recovery fixture boundary');}
 return{physical,events,row,scans};
}
(async()=>{
 for(const choice of [false,true]){
  const normal=await run('', 'ack',choice);assert.equal(normal.physical.filter(x=>x.type==='mousePressed').length,1);checks++;
  for(const where of ['ack','attach','press'])for(const change of ['draft','stop','move','target','image','document','owner','cancel','navigation']){
   if(choice&&change==='image')continue;
   const result=await run(change,where,choice),pressed=result.physical.filter(x=>x.type==='mousePressed'),released=result.physical.filter(x=>x.type==='mouseReleased');
   assert.equal(pressed.length,where==='press'?1:0,`${choice}/${where}/${change}: unsafe press`);
   if(where==='press'){assert.equal(released.length,1);assert(released[0].x<0&&released[0].y<0,`${where}/${change}: release must be outside page`);}
   else assert.equal(released.length,0);
   assert(!['prepared','uploading','ready_to_send'].includes(result.row.stage),'intent must never reset');checks++;
  }
 }
 for(const choice of [false,true]){
  const normal=await run('','ack',choice,true);assert.equal(normal.physical.filter(x=>x.type==='mousePressed').length,1);checks++;
  for(const where of ['attach','press']){
   const result=await run('plan',where,choice,true),pressed=result.physical.filter(x=>x.type==='mousePressed'),released=result.physical.filter(x=>x.type==='mouseReleased');
   assert.equal(pressed.length,where==='press'?1:0);
   if(where==='press'){assert.equal(released.length,1);assert(released[0].x<0&&released[0].y<0);}
   else assert.equal(released.length,0);checks++;
  }
 }
 console.log(JSON.stringify({ok:true,checks,providerActions:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
