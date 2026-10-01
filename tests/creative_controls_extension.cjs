const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const helper=section('  function speechDeliveryRepairInstruction(', '  async function validateOrRepairStoredAnalysis(');
const stored=section('  async function validateOrRepairStoredAnalysis(', '  function storyCanonicalIdBindingPhrase(');
const start=source.indexOf('  async function parseOrRepairAnalysis('),parse=source.slice(start,source.indexOf('\n  function ',start+1));
(async()=>{
  let checks=0;
  for(const provider of ['chatgpt','gemini'])for(const kind of ['product','story']){
    const sent=[],brief={version:1,kind,selection:'auto',title:'เหตุการณ์หนึ่งวัน',description:'เริ่มเหตุการณ์และจบเป็นเรื่องเดียว'};
    const good={scene_prompts:['one','two','three'],scene_narrations:['เดิม','เดิม','เดิม'],scene_durations:[5,5,5],creative_brief:brief};
    let reject=true;
    const c=vm.createContext({AI_NAME:provider,report:async()=>{},extractJson:turn=>JSON.parse(turn.innerText),
      validateAnalysis:result=>{if(reject){reject=false;throw Error('missing scene');}return result;},
      storyImageRefusal:()=>false,geminiAnalysisCapabilityOnly:()=>false,explicitAnalysisRefusal:()=>false,
      submitPrompt:async prompt=>{sent.push(prompt);return {innerText:JSON.stringify(good)};}});
    vm.runInContext(helper+stored+parse,c);
    const pkg={job:{id:'STORY-FIXTURE',product_short:kind==='product'},request:{required_fields:['scene_prompts','creative_brief'],
      speech_delivery_version:1,speech_delivery_instruction:'SPEECH DELIVERY v1:\nPreserve approved words, roles and facts.\nEND SPEECH DELIVERY v1',
      creative_contract:{version:1,kind,selection:'auto'},creative_brief:brief,creative_instruction:'CREATIVE BRIEF v1: preserve one direction.',
      ...(kind==='product'?{product_script_options:{version:3,style:'auto'},product_script_instruction:'PRODUCT CREATIVE SCRIPT v3: preserve facts.'}:{})}};
    c.validateCreativeBrief(good,pkg.request);checks++;
    const initialRequest={...pkg.request};delete initialRequest.creative_brief;
    const sceneRepair=c.creativeBriefRepairInstruction({...pkg,request:initialRequest},brief);
    assert(sceneRepair.includes(brief.title));assert(sceneRepair.includes('Keep the saved narrative direction'));checks++;
    if(kind==='product'){
      c.validateProductCreativePlan({...good,narration_script:'เดิม เดิม เดิม'},3);
      assert.throws(()=>c.validateProductCreativePlan({...good,narration_script:'คนละบท'},3),/PRODUCT_CREATIVE_REVIEW/);
      assert.throws(()=>c.validateProductCreativePlan({...good,scene_narrations:['กดติดตาม','ต่อเรื่อง','จบ'],narration_script:'กดติดตาม ต่อเรื่อง จบ'},3),/PRODUCT_CREATIVE_REVIEW/);checks+=3;
    }
    for(const bad of [{...brief,selection:'countdown'},{...brief,title:'another'},{...brief,description:'<tag>'},{...brief,title:'x'.repeat(101)}]){
      assert.throws(()=>c.validateCreativeBrief({...good,creative_brief:bad},pkg.request),/CREATIVE_BRIEF_REVIEW/);checks++;
    }
    await c.validateOrRepairStoredAnalysis(good,pkg,'scene_prompts',3);
    assert.equal(sent.length,1);assert(sent[0].includes('CREATIVE BRIEF v1'));checks++;
    assert(sent[0].includes(pkg.request.speech_delivery_instruction));checks++;
    sent.length=0;reject=false;
    await c.parseOrRepairAnalysis({innerText:'invalid JSON'},pkg,'scene_prompts',3);
    assert.equal(sent.length,1);assert(sent[0].includes('CREATIVE BRIEF v1'));checks++;
    if(kind==='product')assert(sent[0].includes('PRODUCT CREATIVE SCRIPT v3'));
    assert(sent[0].includes(pkg.request.speech_delivery_instruction));checks++;
  }
  console.log(JSON.stringify({ok:true,checks,networkRequests:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
