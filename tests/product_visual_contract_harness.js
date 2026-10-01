const fs=require('fs'),os=require('os'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const {spawnSync}=require('child_process');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const python=process.env.SMARTFLOW_TEST_PYTHON || 'python';
function section(start,end){const first=source.indexOf(start);return source.slice(first,source.indexOf(end,first+start.length));}
let cases=0;
async function scenario(provider,{seed=true,bad=false,interrupt=false}={}){
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'smartflow-visual-test-'));
  try{
    fs.mkdirSync(path.join(folder,'generated'));
    fs.writeFileSync(path.join(folder,'generated/selling_image_02.png'),'unchanged image');
    const job={id:'JOB-FIXTURE',image_ai_provider:provider,product_name:'HMS device',description:'Compatible car display supports split screen.',
      image_prompts:['hero','Studio close-up of the same product'],flow_shot_prompts:['hero',{scene_index:2,prompt:'LEGACY_DASHBOARD_CUT'}],
      spoken_script_segments:['intro',{scene_index:2,text:'รองรับการแบ่งหน้าจอ'}]};
    const messages=[],sends=[];let clock=1000;
    const bridge=extra=>{
      const child=spawnSync(python,['tests/product_visual_bridge.py'],{input:JSON.stringify({folder,job,...extra}),encoding:'utf8'});
      assert.equal(child.status,0,child.stderr);return JSON.parse(child.stdout);
    };
    if(seed)assert(bridge({seed:true}).ok);
    const message=body=>bridge({body:{index:2,provider,job_id:job.id,...body}});
    const c=vm.createContext({activeRunId:'RUN-TEST',activeJobId:job.id,PROVIDER_KEY:provider,AI_NAME:provider,
      IS_GEMINI:provider==='gemini',report:async()=>{},assertNotCancelled:()=>{},
      Date:{now:()=>clock},sleep:async ms=>{clock+=ms;},
      analysisAnswerNode:x=>x,analysisResponseStopButton:()=>null,analysisContentHash:text=>String(text.length),
      geminiTextSendKey:async()=> 'fixture',readGeminiTextSend:async()=>null,
      motionRequestIsLatestUser:()=>false,userTurns:()=>[],latestAssistantStrictlyAfterLatestUser:()=>null,
      chrome:{runtime:{sendMessage:async m=>{messages.push(m);return message(m);}}},
      submitPrompt:async(request,images,name,count,mark,context)=>{
        assert(!request.includes('LEGACY_DASHBOARD_CUT'));
        assert(request.includes('รองรับการแบ่งหน้าจอ'));
        assert(request.includes('All spoken dialogue must be in Thai only.'));
        assert.equal(context.provider,provider);assert.equal(images.length,1);
        assert.equal(images[0],'http://fixture-only/selling_image_02.png');
        assert.equal(message({action:'status'}).record.phase,'preparing');
        await mark();sends.push(request);
        assert.equal(message({action:'status'}).record.phase,'requested');
        if(interrupt)throw Error('simulated disconnect after dispatch');
        const answer={job_id:job.id,index:2,context_id:context.context_id,
          prompt:'Create one vertical 9:16 video. The product stays still as the camera slowly moves closer. All spoken dialogue must be in Thai only.',
          needs_review:bad,reference_compatible:true,material_change:bad,review_reason:bad?'Explicit requirement still cannot be met':'Current brief fits the studio image'};
        return {innerText:JSON.stringify(answer)};
      }});
    vm.runInContext(section('  function motionRequestIsLatestUser(', '  async function sendAndVerify(')
      +section('  function stableOwnedMotionAnswer(', '  async function submitPrompt(')
      +section('  function escapeJsonControlCharacters(', '  function normaliseDialogueSpeakers('),c);
    vm.runInContext(source.slice(source.indexOf('  async function prepareFlowMotionPlan('),source.indexOf('  function sceneRepairRequest(')),c);
    const run=()=>c.prepareFlowMotionPlan({job},{flow_shot_prompts:job.flow_shot_prompts},2,3);
    if(bad||interrupt){await assert.rejects(run());await assert.rejects(run());}
    else {const prompt=await run();assert.equal(await run(),prompt);assert.equal(bridge({saved:true}).prompt,prompt);}
    assert.equal(sends.length,1,'No additional Send on repeated resume');
    const saved=JSON.parse(fs.readFileSync(path.join(folder,'prompts/flow_motion_plans.json'),'utf8'));
    assert.equal(Object.keys(saved.plans).length,seed?2:1);
    if(seed){const original=Object.values(saved.plans).find(r=>!r.context.product_visual_contract);
      assert.equal(original.content_recheck_attempt,1);assert.equal(original.result.material_change,true);}
    assert.equal(fs.readFileSync(path.join(folder,'generated/selling_image_02.png'),'utf8'),'unchanged image');
    if(bad||interrupt)assert(!messages.some(m=>m.action==='save'));
    cases++;
  }finally{fs.rmSync(folder,{recursive:true,force:true});}
}
(async()=>{
  for(const p of ['chatgpt','gemini']){
    await scenario(p);await scenario(p,{seed:false});await scenario(p,{bad:true});await scenario(p,{interrupt:true});
  }
  // Execute the real analysis validator for explicit index mismatches.
  const c=vm.createContext({AI_NAME:'fixture',normaliseDialogueSpeakers:x=>x});
  vm.runInContext(source.slice(source.indexOf('  function validateAnalysis('),source.indexOf('  async function validateOrRepairStoredAnalysis(')),c);
  const analysis={image_prompts:['a','b','c'],flow_shot_prompts:[{scene_index:1},{scene_index:2},{scene_index:3}]};
  c.validateAnalysis(analysis,'image_prompts',3,['flow_shot_prompts']);
  for(const wrong of [1,'2',true]){analysis.flow_shot_prompts[1].scene_index=wrong;assert.throws(()=>c.validateAnalysis(analysis,'image_prompts',3,['flow_shot_prompts']),/scene_index/);cases++;}
  console.log(`Product visual contract real Python/Extension: ${cases} cases passed; zero provider calls.`);
})().catch(error=>{console.error(error);process.exitCode=1;});
