// Execute the actual shared ChatGPT/Gemini image context and repair helpers.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const pkg=JSON.parse(fs.readFileSync(0,'utf8'));
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const helpers=section('  function productScriptRepairInstruction(', '  async function validateOrRepairStoredAnalysis(');
const images=section('      const sceneContents = mode === "story"', '      result.job_id = pkg.job.id;');
const references=section('      if(pkg.job.product_story){', '      if(pkg.request?.product_script_options?.style');
let checks=0;
for(const provider of ['chatgpt','gemini'])for(const wardrobe of ['auto','saved','product']){
  const data=JSON.parse(JSON.stringify(pkg));data.job.product_story.outfit_mode=wardrobe;
  const c=vm.createContext({pkg:data,AI_NAME:provider,mode:'story',result:{},imageCount:3,compactTextStory:false,
    validateStoryContent:()=>{},storySceneContent:(_r,i)=>`Saved scene ${i+1}`});
  vm.runInContext(helpers+images+references+'\nglobalThis.contents=sceneContents;',c);
  for(const text of c.contents){
    assert(text.includes(data.request.product_visual_instruction));
    assert(text.includes('POV wardrobe:'));assert(!text.includes('face and identity'));
    assert(!text.includes('adult character wears the garment'));checks+=4;
  }
  assert(c.productScriptRepairInstruction(data).includes('POINTING REVIEW v1:'));checks++;
  const old=JSON.parse(JSON.stringify(data));old.request.product_script_options.style='auto';
  assert.equal(c.productPointingVisualInstruction(old),'');checks++;
  for(const bad of [null,{},'', 'x'.repeat(3501)]){
    const broken=JSON.parse(JSON.stringify(data));broken.request.product_visual_instruction=bad;
    assert.throws(()=>c.productPointingVisualInstruction(broken),/PRODUCT_POINTING_REVIEW/);checks++;
  }
}
console.log(JSON.stringify({ok:true,checks,providerRequests:0}));
