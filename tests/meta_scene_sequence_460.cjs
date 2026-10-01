const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'browser_extension/chatgpt.js'),'utf8');
const start=source.indexOf('      const scenePipeline=mode===');
const middle=source.indexOf('      if(pkg.job.product_story){',start);
const loop=source.indexOf('      for (let index = 0; index < imageCount; index += 1) {',middle);
const end=source.indexOf('      if (generatedImages.some',loop);
assert(start>0&&middle>start&&loop>middle&&end>loop);
const actual=source.slice(start,middle)+source.slice(loop,end);
let checks=0;
async function run({saved=false,failed=false,lostImageAck=false,gemini=false,flow=false}={}){
  const events=[], generatedImages=[saved?'saved-1':null,null]; let polls={};
  const pkg={job:{id:'STORY-TEST',video_generation_mode:flow?'google_flow':'meta_ai',
    meta_scene_sequence_version:1,scene_pipeline_version:flow?1:0},scene_repair:{enabled:false},request:{}};
  const context={mode:'story',pkg,IS_GEMINI:gemini,PROVIDER_KEY:gemini?'gemini':'chatgpt',activeRunId:'RUN-A',
    result:{},imageCount:2,generatedImages,storyImageFallbacks:{},prompts:['image1','image2'],
    sceneContents:['one','two'],visualStyle:'',textRenderStyle:'',compactLongImages:false,
    lastCompletedImageCount:0,AI_NAME:'ChatGPT',completedImageCount:()=>generatedImages.filter(Boolean).length,
    assertNotCancelled:()=>{},sleep:async()=>{},report:async()=>{},waitForResponseIdle:async()=>{},
    prepareFlowMotionPlan:async(_pkg,_result,n)=>events.push(`flow-plan${n}`),
    createStoryImageReceipt:(_pkg,n)=>({restore:async()=>null,committed:async()=>events.push(`image${n}-committed`)}),
    generateOneImage:async(_p,_refs,n)=>{events.push(`image${n}-send`);return `image${n}`;},
    alreadyUsedImage:async()=>false,rememberSavedImage:async(i,image)=>{generatedImages[i]=image;},
    checkpointStoryRefusalFallback:async(_p,_n,_images,_fallback,_r,error)=>{throw error;},
    chrome:{runtime:{sendMessage:async message=>{
      if(message.type==='CHECKPOINT_STORY_IMAGE'){
        events.push(`image${message.index}-saved`);
        return lostImageAck?{ok:false,error:'lost image ACK'}:{ok:true};
      }
      assert.equal(message.type,'STORY_SCENE_GATE');
      if(message.action==='prepare'){assert(flow);return {ok:true};}
      if(message.action==='ready'){events.push(`video${message.index}-start`);return {ok:true,phase:'video_pending'};}
      polls[message.index]=(polls[message.index]||0)+1;
      if(failed)return {ok:true,phase:'error',error:'review exact request'};
      if(polls[message.index]<2)return {ok:true,phase:'video_pending'};
      events.push(`video${message.index}-stored`);
      return {ok:true,phase:flow?'complete':'scene_ready'};
    }}}};
  const execution=vm.runInNewContext(`(async()=>{${actual}})()`,context);
  if(failed||lostImageAck)await assert.rejects(execution);else await execution;
  return events;
}
(async()=>{
  const normal=await run();
  for(let n=1;n<=2;n++){
    assert(normal.indexOf(`image${n}-saved`)<normal.indexOf(`video${n}-start`));checks++;
    assert(normal.includes(`video${n}-stored`));checks++;
  }
  assert(normal.indexOf('video1-stored')<normal.indexOf('image2-send'));checks++;
  const saved=await run({saved:true});assert(!saved.includes('image1-send'));checks++;
  assert(saved.indexOf('video1-stored')<saved.indexOf('image2-send'));checks++;
  for(const options of [{failed:true},{lostImageAck:true}]){
    const result=await run(options);assert(!result.includes('image2-send'));checks++;
  }
  const other=await run({gemini:true});assert(!other.some(x=>x.startsWith('video')));checks++;
  const flow=await run({flow:true});assert(flow.includes('flow-plan1'));checks++;
  assert(flow.indexOf('video1-stored')<flow.indexOf('image2-send'));checks++;
  console.log(JSON.stringify({checks,actual_source_loop:true,provider_sends:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
