const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const helper=section('  function speechDeliveryRepairInstruction(', '  async function validateOrRepairStoredAnalysis(');
const stored=section('  async function validateOrRepairStoredAnalysis(', '  function storyCanonicalIdBindingPhrase(');
const parseStart=source.indexOf('  async function parseOrRepairAnalysis(');
// The next declaration bounds this complete actual-source function.
const next=source.indexOf('\n  function ',parseStart+1);
const parse=source.slice(parseStart,next);
(async()=>{
 let checks=0;
 for(const provider of ['chatgpt','gemini'])for(const style of ['story_first_review','standard',undefined]){
  const sent=[];let rejectFirst=true;
  const good={scene_prompts:['one','two','three'],scene_narrations:['เดิม','เดิม','เดิม'],scene_durations:[5,5,5]};
  const c=vm.createContext({AI_NAME:provider, report:async()=>{},extractJson:turn=>JSON.parse(turn.innerText),
   validateAnalysis:result=>{if(rejectFirst){rejectFirst=false;throw Error('missing scene');}return result;},
   storyImageRefusal:()=>false,geminiAnalysisCapabilityOnly:()=>false,explicitAnalysisRefusal:()=>false,
   submitPrompt:async prompt=>{sent.push(prompt);return {innerText:JSON.stringify(good)};}});
  vm.runInContext(helper+stored+parse,c);
  const pkg={job:{id:'STORY-TEST',product_short:true},request:{required_fields:['scene_prompts'],
   product_script_options:style?{version:1,style}:undefined,product_script_instruction:'PRODUCT STORY-FIRST REVIEW v1: preserve approved dialogue; no mandatory CTA.'}};
  await c.validateOrRepairStoredAnalysis(good,pkg,'scene_prompts',3);
  assert.equal(sent.length,1);assert.equal(sent[0].includes('PRODUCT STORY-FIRST REVIEW'),style==='story_first_review');checks++;
  sent.length=0;rejectFirst=false;
  await c.parseOrRepairAnalysis({innerText:'invalid JSON'},pkg,'scene_prompts',3);
  assert.equal(sent.length,1);assert.equal(sent[0].includes('PRODUCT STORY-FIRST REVIEW'),style==='story_first_review');checks++;
  pkg.job.product_short=false;assert.equal(c.productScriptRepairInstruction(pkg),'');checks++;
 }
 console.log(JSON.stringify({ok:true,checks,providers:['chatgpt','gemini'],networkRequests:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
