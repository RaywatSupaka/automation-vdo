const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const code=source.slice(source.indexOf('  function extractAlternativeJson('),source.indexOf('  async function runSceneRepairHelper('));
async function background(){
 const fixture=new Function('require',fs.readFileSync('tests/story_repair_background_harness.js','utf8').split('(async()=>')[0]+';return fixture;')(require);
 const f=fixture(),key='smartflowFlowRepair:STORY-TEST:1';
 Object.assign(f.c,{URL,isFlowUrl:u=>u.startsWith('https://flow.google.com/'),flowProgressOwnership:async()=>({active:true,ownerTabId:5,activeRunId:'RUN-1'})});
 f.sender.tab.url='https://flow.google.com/project/p';
 Object.assign(f.message,{type:'FLOW_SCENE_REPAIR',shot_index:1,fingerprint:'fp',failure_id:'one'});
 f.storage.smartpostFlowMonitor={jobId:'STORY-TEST',runId:'RUN-1',shotIndex:1,storyPolicyTerminal:{repair_eligible:true,failure_code:'FLOW_POLICY_BLOCKED',failure_card_fingerprint:'fp',failure_reason:'failed',projectPath:'/project/p'}};
 await f.call();f.storage[key].phase='needs_review';
 const fetch=f.c.bridgeFetch;
 f.c.bridgeFetch=async(url,options)=>JSON.parse(options?.body || '{}').replacement_action==='begin'
   ? {ok:true,json:async()=>({ok:true,context:{aspect_ratio:'9:16'},replacement:{phase:'requested'}})}:fetch(url,options);
 const next=await f.call({action:'start_alternative'});
 assert(next.alternative);assert.equal(next.phase,'rewrite_sent');assert.equal(next.image_urls[0],'http://fixture/scene.png');
 const opened=f.events.filter(x=>x==='open').length;
 await f.call({action:'start_alternative'});assert.equal(f.events.filter(x=>x==='open').length,opened);
 assert.equal(await f.c.isStoryRepairSendOwner({...f.message,expectedPrompt:next.request},next.helper_tab),true);
 f.storage[key].phase='ready';f.storage[key].replacement={image_url:'http://fixture/new.png'};
 f.storage[key].candidate={prompt:'Vertical 9:16. Safe alternative motion with the saved reference.',needs_review:false,reference_compatible:true,material_change:false};
 let downloads=0;f.c.chrome.downloads={download:async()=>{downloads++;return 4;},search:async()=>[{state:'complete',filename:'C:/new.png'}]};
 await f.call({action:'prepare_alternative'});await f.call({action:'prepare_alternative'});
 assert.equal(downloads,1);assert.equal(f.storage.smartpostFlowReferenceFile.replacement_id,next.request_id);
 assert.equal(f.storage[key].phase,'ready');
}
async function run(provider,deny=false,recover=false,formatStage='',revision=false,changedReference=false,motionConflict=false,duplicates=0,cancelCorrection=false,resumeCorrection=false,actors=false,schema=''){
 const record={request_id:'id',provider,alternative_stage:recover?'image_sent':'proposal',request:'proposal',image_urls:['original'],context:{aspect_ratio:'9:16'}};
 const calls=[],image={complete:true,naturalWidth:288,naturalHeight:512,src:'new-image'};
 record.revise_story=revision;
 if(resumeCorrection){record.alternative_stage='proposal_correction';record.proposal_feedback_round=2;}
 record.context.story_beat='OLD FAILED EVENT';
 if(changedReference)record.context.audio_instruction='AUDIO PERFORMANCE: Old reviewer must speak on camera. Spoken line: OLD FAILED EVENT';
 if(actors)record.context.audio_instruction='ACTOR DIALOGUE: มะลิ speaks to ต้น: เห็นกุญแจไหม';
 const candidate={prompt:'Vertical 9:16. A hand places a bottle into a clean recycling container.',needs_review:false,material_change:false,reference_compatible:true};
 let formatted=false,proposalChecks=0,reads=0;
 const c=vm.createContext({String,Error,record,document:{querySelectorAll:()=>[]},Node:{DOCUMENT_POSITION_FOLLOWING:4},location:{href:'https://gemini.google.com/app/test'},
   chrome:{runtime:{sendMessage:async m=>{calls.push(m.action);
    if(m.action==='proposal_check' && ++proposalChecks<=duplicates)return {ok:true,replacement:{proposal_feedback:{code:'duplicate_story',reason:'duplicate',digest:'digest'}}};
    return {ok:true,replacement:{image_url:'saved-new-image'}};}}},
   userTurns:()=>[],composerText:()=>'',motionRequestIsLatestUser:()=>true,stopButtonVisible:()=>false,
   latestAssistantStrictlyAfterLatestUser:()=>({innerText:'reply'}),sleep:async()=>{},
   assertNotCancelled:()=>{if(cancelCorrection && record.alternative_stage==='proposal_correction')throw Error('cancelled');},report:async()=>{},
   revealChatGPTAnswer:async()=>false, // Actual bounded reveal is tested in result_readiness_392.cjs.
   alternativeImageReply:()=>({innerText:'reply'}),storyImageAssetKey:i=>i.src,
   generatedImageElements:()=>[image],imageData:async()=> 'data:image/png;base64,abc',waitForResponseIdle:async()=>{},
   submitPrompt:async(prompt,refs)=>{calls.push(['text',refs]);if(revision && refs[0]==='saved-new-image'){assert(prompt.includes('NEW THAI EVENT'));assert(!prompt.includes('OLD FAILED EVENT'));if(actors){assert(prompt.includes('ACTOR DIALOGUE:'));assert(prompt.includes('เห็นกุญแจไหม'));assert(!prompt.includes('Use only the NEW Thai narration'));}if(changedReference){assert(prompt.includes('off-screen Thai review speech'));assert(!prompt.includes('Old reviewer must'));}}return {};},
   submitImagePrompt:async()=>{calls.push('generate-image');return image;},
   extractJson:()=>{
    reads++;
    if(formatStage && !formatted && record.alternative_stage===(formatStage==='proposal'?'proposal':'motion_sent')){
     formatted=true;throw Error('plain text, not JSON');
    }
    const value={...candidate,reference_compatible:!(changedReference && record.alternative_stage==='proposal') && !(motionConflict && record.alternative_stage==='motion_sent'),material_change:deny || (revision && ['proposal','proposal_correction'].includes(record.alternative_stage)),scene_narration:'NEW THAI EVENT',context_summary:'A different situation'};
    if(reads===1 && schema==='missing')delete value.material_change;
    if(reads===1 && schema==='string')value.needs_review='false';
    if(reads===1 && schema==='context')delete value.context_summary;
    if(schema==='review')value.needs_review=true;
    return value;
   },
 });
 vm.runInContext(code,c);
 const save=async patch=>Object.assign(record,patch);
 if(schema==='review'){
  await assert.rejects(()=>c.runFlowAlternativeHelper('key',record,false,save),/ยังต้องตรวจ/);
  assert(!calls.includes('generate-image'));assert(!record.alternative_format_attempts);
  assert.equal(record.proposal_review.needs_review,true);return;
 }
 if(cancelCorrection){await assert.rejects(()=>c.runFlowAlternativeHelper('key',record,false,save),/cancelled/);assert(!calls.includes('generate-image'));assert.equal(calls.filter(x=>Array.isArray(x)).length,1);return;}
 if(deny){await assert.rejects(()=>c.runFlowAlternativeHelper('key',record,false,save));assert(!calls.includes('generate-image'));return;}
 if(motionConflict){await assert.rejects(()=>c.runFlowAlternativeHelper('key',record,false,save));assert(calls.includes('generate-image'));assert(!calls.includes('ready'));return;}
 await c.runFlowAlternativeHelper('key',record,recover,save);
 assert.equal(record.phase,'ready');assert.equal(calls.filter(x=>x==='generate-image').length,recover&&!resumeCorrection?0:1);
 assert(calls.includes('image') && calls.includes('ready'));
 if(revision)assert(calls.indexOf('proposal_check') >= 0 && calls.indexOf('proposal_check') < calls.indexOf('generate-image'));
 if(duplicates){assert.equal(proposalChecks,duplicates+1);assert.equal(record.proposal_feedback_round,duplicates);assert.equal(calls.filter(x=>Array.isArray(x)&&x[1].length===0).length,duplicates);}
 if(resumeCorrection)assert(!calls.some(x=>Array.isArray(x)&&x[1][0]==='original'));
 assert(calls.some(x=>Array.isArray(x)&&x[1][0]==='saved-new-image'));
 if(formatStage){assert.equal(record.alternative_format_attempts[formatStage],1);assert.equal(calls.filter(x=>Array.isArray(x)&&x[1].length===0).length,1);}
 if(schema){assert.equal(record.alternative_format_attempts.proposal,1);assert.equal(calls.filter(x=>Array.isArray(x)&&x[1].length===0).length,1);}
}
(async()=>{for(const p of ['chatgpt','gemini']){await run(p);await run(p,true);await run(p,false,true);await run(p,false,false,'proposal');await run(p,false,false,'motion');await run(p,false,false,'',true);await run(p,false,false,'',true,true);await run(p,false,false,'',true,true,true);await run(p,false,false,'',true,false,false,3);await run(p,false,false,'',true,false,false,1,true);await run(p,false,true,'',true,false,false,0,false,true);await run(p,false,false,'',true,false,false,0,false,false,true);for(const schema of ['missing','string','context','review'])await run(p,false,false,'',true,false,false,0,false,false,true,schema);}await background();console.log('32 helper scenarios including actor dialogue, typed repair and background ownership/download passed');})().catch(e=>{console.error(e);process.exit(1);});
