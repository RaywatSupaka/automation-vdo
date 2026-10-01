// Exercise the real Drama submit functions without starting the desktop or a provider.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('web_ui/app.js','utf8');
const code=source.slice(source.indexOf('let dramaSubmitting = false;'),
  source.indexOf("$('#create-drama-series').addEventListener"));
const nodes=new Map(), cards=[];
function node(selector){
  if(!nodes.has(selector))nodes.set(selector,{value:'',disabled:false,dataset:{},textContent:'',
    selectedOptions:[{textContent:'ใช้เสียงหลัก'}],removeAttribute(){},closest(){return {hidden:false}}});
  return nodes.get(selector);
}
for(let i=1;i<=4;i++){
  for(const field of ['name','description','image','file','voice','image-name','preview'])node(`#drama-character-${i}-${field}`);
  const card={hidden:i>1};cards.push(card);
  node(`#drama-character-${i}-preview`).closest=()=>card;
}
const cast={open:true,querySelector(){return {disabled:true}}}, calls=[], notices=[];
const context={
  $:node,ui:{dramaImages:{1:'asset:fixture'},dramaFootage:['fixture.mp4']},
  document:{querySelector:()=>cast},URL:{revokeObjectURL(){}},
  toast:(message,type)=>notices.push({message,type}),
  postAction:async(action,payload)=>{calls.push({action,payload});return {queued:1,queued_only:true}},
  poll:async()=>{},renderDramaPlotBoard:()=>{},
  updateCreationAvailability:()=>{node('#create-drama-series').disabled=!node('#drama-title').value.trim()},
  storyStylePayload:()=>({}),selectedAiModel:()=>'',currentDramaPlotBoard:()=>[],
};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{
  node('#create-drama-series').disabled=true;
  await context.submitDramaSeries(true);
  assert.equal(calls.length,0);
  assert.match(notices.at(-1).message,/ชื่อเรื่อง/);
  node('#drama-title').value='ร้านลับ';node('#drama-premise').value='ความลับของร้าน';
  node('#drama-character-1-name').value='มะลิ';node('#drama-character-1-description').value='เสื้อสีฟ้า';
  node('#drama-character-1-voice').value='voice-a';node('#drama-video-mode').value='google_flow';
  node('#drama-provider').value='chatgpt';node('#drama-episodes').value='2';node('#drama-scenes').value='6';
  await context.submitDramaSeries(true);
  assert.equal(calls.length,1);assert.equal(calls[0].action,'create_drama_series');
  assert.equal(calls[0].payload.characters[0].name,'มะลิ');
  assert.equal(node('#drama-character-1-name').value,'');
  assert.equal(node('#drama-character-1-voice').value,'');
  assert.equal(node('#drama-title').value,'');assert.equal(context.ui.dramaImages[1],undefined);
  assert.equal(cards[1].hidden,true);assert.equal(cast.open,false);
  assert.equal(node('#create-drama-series').disabled,true);
  console.log('PASS: Drama queue validation, one submit, draft/cast cleanup');
})().catch(error=>{console.error(error);process.exitCode=1});
