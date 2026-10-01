const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8'),fixture=JSON.parse(fs.readFileSync(0,'utf8'));
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const helpers=section('  function productScriptRepairInstruction(', '  async function validateOrRepairStoredAnalysis(');
const stored=section('  async function validateOrRepairStoredAnalysis(', '  function storyCanonicalIdBindingPhrase(');
const parseStart=source.indexOf('  async function parseOrRepairAnalysis('),parse=source.slice(parseStart,source.indexOf('\n  function ',parseStart+1));
(async()=>{
 let checks=0;
 for(const provider of ['chatgpt','gemini']){
  const sent=[],good=structuredClone(fixture),options={version:2,style:'short_film_ad',genre:'warm',ending_cta:true};
  const c=vm.createContext({AI_NAME:provider,report:async()=>{},extractJson:turn=>JSON.parse(turn.innerText),
   normaliseDialogueSpeakers:r=>r,validateStoryContent:()=>{},storyImageRefusal:()=>false,
   geminiAnalysisCapabilityOnly:()=>false,explicitAnalysisRefusal:()=>false,
   submitPrompt:async prompt=>{sent.push(prompt);return {innerText:JSON.stringify(good)};}});
  vm.runInContext(section('  function validateAnalysis(', '  function productScriptRepairInstruction(')+helpers+stored+parse,c);
  const pkg={job:{id:good.job_id,product_short:true},request:{required_fields:['scene_prompts','scene_narrations','product_film_plan'],
   product_script_options:options,product_script_instruction:'PRODUCT SHORT FILM AD v2: preserve the event, hidden opening product and final CTA.'}};
  c.validateAnalysis(good,'scene_prompts',3,pkg.request.required_fields,[],pkg.request);checks++;
  for(const change of [r=>delete r.product_film_plan,r=>r.product_film_plan.scenes[0].product_visible=true,
    r=>r.product_film_plan.scenes[0].spoken_text='wrong',r=>r.product_film_plan.scenes[1].roles=['setup'],
    r=>r.narration_script='wrong',r=>r.product_film_plan.ending_cta_text='different']){
    const bad=structuredClone(good);change(bad);assert.throws(()=>c.validateAnalysis(bad,'scene_prompts',3,[],[],pkg.request),/PRODUCT_FILM_PLAN/);checks++;
  }
  const bad=structuredClone(good);delete bad.product_film_plan;
  const repaired=await c.validateOrRepairStoredAnalysis(bad,pkg,'scene_prompts',3);
  assert.equal(sent.length,1);assert.match(sent[0],/PRODUCT SHORT FILM AD/);assert.deepEqual(JSON.parse(JSON.stringify(repaired)),good);checks++;
  sent.length=0;
  await c.parseOrRepairAnalysis({innerText:'bad JSON'},pkg,'scene_prompts',3);
  assert.equal(sent.length,1);assert.match(sent[0],/PRODUCT SHORT FILM AD/);checks++;
  pkg.job.product_short=false;assert.equal(c.productScriptRepairInstruction(pkg),'');checks++;
 }
 console.log(JSON.stringify({ok:true,checks,providers:2,networkRequests:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
