// Actual source, isolated memory/DOM fixtures only; never contact the bridge/provider.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'browser_extension/background.js'),'utf8');
const part=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)+a.length));
const clone=value=>structuredClone(value);
const binding={version:1,scene_index:3,plan_revision:2,selection_id:'selection-a',attempt_id:'attempt-a',provider:'google_flow',settings_sha256:'a'.repeat(64)};
const message={job_id:'STORY-PLAN',shot_index:3,run_id:'run-a',scene_video_plan:binding};
let checks=0;
const check=(actual,expected)=>{assert.equal(actual,expected);checks++;};
async function rejects(call,pattern){await assert.rejects(call,pattern);checks++;}
function context(){
  const storage={},state={current:clone(binding),settings:{model:'Omni 1.1 Flash'},reads:0,watch:true,consumed:0};
  const ctx={URL,BRIDGE:'http://fixture.invalid',flowRunStorageKey:(job,index)=>`run:${job}:${index}`,
    chrome:{storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(key=>[key,storage[key]]))}},
      scripting:{executeScript:async({args})=>{if(args[1])state.consumed++;return[{result:state.watch}];}}},
    bridgeFetch:async()=>{state.reads++;return{ok:true,json:async()=>({ok:true,package:{scene_video_plan:clone(state.current),flow_settings:state.settings,scene_video_plan_legacy_active:state.legacyActive}})}},
    SmartFlowSettings:{checkWatch(){}}};
  vm.createContext(ctx);vm.runInContext(part('function sceneVideoPlanMatches(','async function aiProgressOwnership('),ctx);
  return{ctx,storage,state};
}
(async()=>{
  const {ctx,storage,state}=context();
  check(ctx.sceneVideoPlanMatches(null,null),true);
  check(ctx.sceneVideoPlanMatches(binding,clone(binding)),true);
  check(ctx.sceneVideoPlanMatches({...binding,plan_revision:0},{...binding,plan_revision:0}),true);
  for(const field of ['version','scene_index','plan_revision','selection_id','attempt_id','provider','settings_sha256']){
    const stale={...binding,[field]:typeof binding[field]==='number'?binding[field]+1:'other'};
    check(ctx.sceneVideoPlanMatches(binding,stale),false);
    state.current=stale;await rejects(()=>ctx.assertFlowScenePlan(message),/STALE/);
  }
  state.current=clone(binding);
  check(Boolean(await ctx.assertFlowScenePlan(message)),true);
  await rejects(()=>ctx.assertFlowScenePlan({...message,flow_settings:{model:'Lite'}}),/SETTINGS_MISMATCH/);
  check(Boolean(await ctx.assertFlowScenePlan({...message,flow_settings:{...state.settings,display:'compact'}})),true);
  const legacy={job_id:'STORY-LEGACY',shot_index:1,run_id:'run-old'};
  const reads=state.reads;check(await ctx.assertFlowScenePlan(legacy),null);check(state.reads,reads);
  storage[ctx.flowScenePlanKey(legacy.job_id,1,'required')]=true;
  await rejects(()=>ctx.assertFlowScenePlan(legacy),/STALE/);
  state.current=null;state.legacyActive=true;
  check(await ctx.assertFlowScenePlan(legacy,{allowLegacyActive:true}),null);
  await rejects(()=>ctx.assertFlowScenePlan(legacy),/STALE/);
  state.current=clone(binding);state.legacyActive=false;
  storage['smartpostFlowTab:STORY-PLAN:3']=7;storage['run:STORY-PLAN:3']='run-a';
  check((await ctx.flowProgressOwnership(message,7)).active,true);
  const online=ctx.bridgeFetch;ctx.bridgeFetch=async()=>{throw Error('offline');};
  check((await ctx.flowProgressOwnership(message,7)).planUnverified,true);
  await rejects(()=>ctx.assertFlowScenePlan(message),/offline/);
  ctx.bridgeFetch=online;
  check((await ctx.flowProgressOwnership(message,8)).active,false);
  check((await ctx.flowProgressOwnership({...message,run_id:'old'},7)).active,false);
  state.current={...binding,attempt_id:'successor'};
  check((await ctx.flowProgressOwnership(message,7)).active,false);
  state.current=clone(binding);
  const sender={tab:{id:7}},submission={...message,settings_verification_id:'verified'};
  await rejects(()=>ctx.assertFlowSceneSubmission(submission,sender),/PROOF_MISSING/);
  vm.runInContext(part('function flowDownloadRecordMatches(','async function downloadFlowResult('),ctx);
  const request={filename:'attempt-a.mp4',jobId:'STORY-PLAN',shotIndex:3,runId:'run-a',scene_video_plan:binding};
  check(ctx.flowDownloadRecordMatches(request,clone(request)),true);
  check(ctx.flowDownloadRecordMatches({...request,scene_video_plan:{...binding,attempt_id:'old'}},request),false);
  vm.runInContext(part('async function downloadFlowResult(','async function downloadFlowResultOwned('),ctx);
  ctx.downloadFlowResultOwned=async()=>{state.current={...binding,attempt_id:'new'};return{filename:'old-attempt.mp4'};};
  await rejects(()=>ctx.downloadFlowResult(message.job_id,3,'run-a',binding),/STALE/);
  state.current=clone(binding);
  vm.runInContext(`flowSceneSettingsProofs.set('verified',{tabId:7,jobId:'STORY-PLAN',runId:'run-a',binding:${JSON.stringify(binding)}})`,ctx);
  await ctx.assertFlowSceneSubmission(submission,sender);check(state.consumed,0);
  state.watch=false;await rejects(()=>ctx.assertFlowSceneSubmission(submission,sender),/CHANGED_BEFORE_GENERATE/);
  state.watch=true;await ctx.assertFlowSceneSubmission(submission,sender,true);check(state.consumed,1);
  await rejects(()=>ctx.assertFlowSceneSubmission(submission,sender),/PROOF_MISSING/);
  // Meta keeps legacy compatibility but requires every original claim field.
  const meta={};vm.createContext(meta);
  vm.runInContext(fs.readFileSync(path.join(root,'browser_extension/src/platforms/meta-ai/video.js'),'utf8').replaceAll('export ',''),meta);
  const row={index:3,scene_video_plan:{...binding,provider:'meta_ai'}};
  check(meta.metaScenePlanMatches({index:3},{index:3}),true);
  check(meta.metaScenePlanMatches(row,clone(row)),true);
  check(meta.metaScenePlanMatches({...row,scene_video_plan:{...row.scene_video_plan,plan_revision:0}},
    {...row,scene_video_plan:{...row.scene_video_plan,plan_revision:0}}),true);
  check(meta.metaScenePlanMatches({index:3},{index:3,scene_video_plan_required:true}),false);
  const held={index:3,stage:'generating',scene_video_plan_required:true,scene_video_plan_legacy_active:true};
  check(meta.metaScenePlanMatches({index:3,stage:'generating'},held,true),true);
  check(meta.metaScenePlanMatches({index:3,stage:'generating'},held),false);
  check(meta.metaScenePlanMatches({index:3,stage:'ready_to_send'},held,true),false);
  for(const field of ['version','scene_index','plan_revision','selection_id','attempt_id','provider','settings_sha256']){
    check(meta.metaScenePlanMatches(row,{...row,scene_video_plan:{...row.scene_video_plan,[field]:'stale'}}),false);
  }
  // A changed/retired claim cannot authorize even a download reconciliation tick.
  vm.runInContext('this.Adapter=MetaVideoAdapter',meta);
  const saved=[];const adapter=new meta.Adapter({api:async()=>({package:{...row,scene_video_plan:{...row.scene_video_plan,attempt_id:'new'}}})});
  adapter.save=async value=>saved.push(clone(value));adapter.collectDownload=async()=>{throw Error('stale download consumed');};
  const active={...row,job_id:'STORY-PLAN',request_id:'r',context_id:'c',stage:'downloading'};
  await adapter.step(active);check(active.paused,true);check(saved.length,1);
  console.log(JSON.stringify({ok:true,checks}));
})().catch(error=>{console.error(error);process.exitCode=1;});
