// Actual parser + helper; isolated protocol/DOM fixtures, never provider requests.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const old=fs.readFileSync('deliverables/SmartFlow_AI_Extension_0.15.409/chatgpt.js','utf8');
const part=(s,a,b)=>{const i=s.indexOf(a),j=s.indexOf(b,i+a.length);assert(i>=0&&j>i);return s.slice(i,j);};
const good={prompt:'Vertical 9:16. Two fictional friends walk beside a quiet garden gate, with a slow camera movement.',
  needs_review:false,reference_compatible:true,material_change:false,
  scene_narration:'เพื่อนเดินเล่นผ่านสวนหน้าบ้าน',context_summary:'A safe garden walk.',scene_dialogue_turns:[]};
function fixture(options={}){
 const row={request_id:'owned',job_id:'STORY-X',run_id:'RUN-X',index:14,provider:options.provider||'chatgpt',
   phase:'rewrite_sent',alternative:true,alternative_stage:'proposal',alternative_json_recovery_version:1,
   request:'Original image proposal',image_urls:['original-image'],context:{aspect_ratio:'9:16'}};
 if(options.legacy)delete row.alternative_json_recovery_version;
 if(options.creative)Object.assign(row,{revise_story:true,creative_revision_version:1,
   context:{...row.context,actor_dialogue:true}});
 let currentRequest='',draft='',answer=null,images=0,sends=0,cancelled=false,interrupted=false;
 const counts={proposal:0,motion:0},calls=[],events=[],delays=[],notices=[];
 const page={href:'https://chatgpt.com/c/owned'};
 const answerText=()=>String(answer?.innerText || '');
 const makeReply=()=>{
   const stage=row.alternative_stage==='motion_sent'?'motion':'proposal';counts[stage]++;
   const malformed=counts[stage]<=(options[stage] || 0);
   let content=JSON.stringify(good);
   if(malformed)content=options.refusal?'I cannot help with this request.'
     :options.empty?'':options.incomplete?JSON.stringify({...good,scene_narration:'',scene_dialogue_turns:null})
     :options.schema?JSON.stringify({...good,needs_review:'false'})
     :counts[stage]%2?'Here is the proposed scene, but no JSON object.':'{"prompt": "truncated';
   answer={innerText:content};return answer;
 };
 const attachment=()=>({count:options.guard==='attachment'?1:0,busy:options.guard==='upload',failed:options.guard==='failed-upload'});
 const c=vm.createContext({String,Number,Error,JSON,AI_NAME:'ChatGPT Web',IS_GEMINI:row.provider==='gemini',location:page,
   document:{querySelectorAll:()=>[]},Node:{DOCUMENT_POSITION_FOLLOWING:4},
   chrome:{storage:{local:{get:async()=>({key:structuredClone(row)})}},runtime:{sendMessage:async m=>{
     events.push(m.action);
     return {ok:true,replacement:{image_url:'saved-new-image',effective_prompt:good.prompt,
       ...(options.creative?{motion_context:{story_beat:good.scene_narration,scene_dialogue_turns:[]}}:{})}};
   }}},
   userTurns:()=>[],composerText:()=>options.guard==='draft'&&sends>0?'user draft':draft,
   motionRequestIsLatestUser:request=>options.guard!=='owner'&&request===currentRequest,
   stopButtonVisible:()=>options.guard==='busy',geminiComposerAttachmentState:attachment,chatGPTComposerAttachmentState:attachment,
   latestAssistantStrictlyAfterLatestUser:()=>options.guard==='changed-answer'?{innerText:'other answer'}:answer,
   alternativeImageReply:()=>answer,revealChatGPTAnswer:async()=>false,
   generatedImageElements:()=>[{complete:true,naturalWidth:288,naturalHeight:512,src:'new-image'}],
   storyImageAssetKey:i=>i.src,imageData:async()=> 'data:image/png;base64,fixture',waitForResponseIdle:async()=>{},
   report:async(...args)=>notices.push(args),assertNotCancelled:()=>{if(cancelled)throw Error('cancelled');},
   sleep:async ms=>{
     delays.push(ms);
     if(row.alternative_format_state?.phase==='requested'){
       if(options.cancel)cancelled=true;
       if(options.changeOwner)row.run_id='RUN-OTHER';
       if(options.navigate)page.href='https://chatgpt.com/c/other';
       if(options.changeAnswer)answer={innerText:'different completed reply'};
     }
   },
   submitPrompt:async(request,refs,filename,n,beforeSend)=>{
     if(beforeSend){draft=request;await beforeSend();draft='';}
     sends++;calls.push({request,refs});
     if(options.unknown && row.alternative_format_state?.phase==='requested'&&!interrupted){
       interrupted=true;throw Error('unknown Send');
     }
     currentRequest=request;return makeReply();
   },
   submitImagePrompt:async request=>{
     images++;currentRequest=request;answer={innerText:'created new image'};
     return {src:'new-image'};
   }
 });
 const chosen=options.old?old:source;
 vm.runInContext(part(chosen,'  function explicitAnalysisRefusal(','  function storyImageReferenceRequest(')
   +part(chosen,'  function escapeJsonControlCharacters(','  function normaliseDialogueSpeakers(')
   +part(chosen,'  function extractAlternativeJson(','  async function runSceneRepairHelper('),c);
 const save=async patch=>{
   if(options.saveFailure&&patch.alternative_format_state?.phase==='answered')throw Error('storage unavailable');
   Object.assign(row,structuredClone(patch));
   if(options.crash&&patch.alternative_format_state?.phase==='requested'&&!interrupted){interrupted=true;throw Error('crash after intent');}
 };
 return {row,calls,events,delays,notices,counts,
   run:recover=>c.runFlowAlternativeHelper('key',structuredClone(row),recover,save),
   acceptPending:()=>{currentRequest=row.request;answer={innerText:JSON.stringify(good)};},
   get images(){return images;},get sends(){return sends;}};
}
(async()=>{
 let checks=0;
 const red=fixture({old:true,proposal:3});
 await assert.rejects(()=>red.run(false),/JSON/);assert.equal(red.images,0);checks++;
 const legacy=fixture({legacy:true,proposal:3});
 await assert.rejects(()=>legacy.run(false),/JSON/);assert.equal(legacy.sends,2);assert.equal(legacy.images,0);checks++;
 for(const provider of ['chatgpt','gemini']){
   const valid=fixture({provider,creative:true});await valid.run(false);
   assert.equal(valid.row.phase,'ready');assert.equal(valid.sends,2);assert.equal(valid.images,1);
   assert.equal(valid.row.alternative_format_state,undefined);checks++;
   for(const options of [{proposal:4,motion:3},{proposal:3,schema:true},{creative:true,proposal:4,motion:3},
       {creative:true,proposal:3,incomplete:true}]){
     const f=fixture({provider,...options});await f.run(false);
     assert.equal(f.row.phase,'ready');assert.equal(f.images,1);
     assert.equal(f.row.alternative_format_attempts.proposal,options.proposal);
     if(options.motion)assert.equal(f.row.alternative_format_attempts.motion,options.motion);
     assert.equal(f.row.alternative_format_state.phase,'answered');
     assert.equal(f.calls.filter(x=>x.refs.length===0).length,options.proposal+(options.motion||0));
     assert(f.notices.length>=options.proposal);assert(f.delays.every(ms=>ms<=30000));checks++;
   }
   for(const guard of ['draft','attachment','upload','failed-upload','busy','owner','changed-answer']){
     const f=fixture({provider,proposal:2,guard});await assert.rejects(()=>f.run(false));
     assert.equal(f.sends,1);assert.equal(f.images,0);checks++;
   }
   for(const option of ['cancel','changeOwner','navigate','changeAnswer']){
     const f=fixture({provider,proposal:2,[option]:true});await assert.rejects(()=>f.run(false));
     assert.equal(f.sends,1);assert.equal(f.images,0);checks++;
   }
   for(const option of ['empty','refusal']){
     const f=fixture({provider,proposal:1,[option]:true});await assert.rejects(()=>f.run(false));
     assert.equal(f.sends,1);assert.equal(f.images,0);checks++;
   }
   for(const option of ['unknown','crash']){
     const f=fixture({provider,proposal:1,[option]:true});await assert.rejects(()=>f.run(false));
     const sends=f.sends;await f.run(true);assert.equal(f.sends,sends);assert.equal(f.images,0);
     f.acceptPending();await f.run(true);assert.equal(f.row.phase,'ready');assert.equal(f.images,1);checks++;
   }
   const failedSave=fixture({provider,proposal:1,saveFailure:true});
   await assert.rejects(()=>failedSave.run(false),/storage unavailable/);
   assert.equal(failedSave.sends,2);assert.equal(failedSave.images,0);checks++;
 }
 console.log(JSON.stringify({ok:true,checks,old409_reproduced:true}));
})().catch(e=>{console.error(e);process.exitCode=1;});
