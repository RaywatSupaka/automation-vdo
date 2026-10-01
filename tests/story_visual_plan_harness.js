// Real Extension orchestration with synthetic DOM/provider/bridge; no live Send.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function fixture(provider,phase='preparing_image',delay=0){
  let now=1,draft='',imageSends=0,motionSends=0,cancel=false;
  const actions=[],attachments=[],motionRequests=[];
  const image={complete:true,naturalWidth:288,naturalHeight:512};
  const repair={phase,request_id:'uuid',image_request:'exact image request uuid',
    motion_request:'exact motion request uuid',image_url:'http://fixture/new.png',candidate_context:{context_id:'new'}};
  const status={context:{context_id:'old',image_url:'http://fixture/original.png'},record:{story_visual_revision:1,story_visual_repair:repair}};
  const turn={innerText:'{"prompt":"one video"}'};
  const c=vm.createContext({Date:{now:()=>now},AI_NAME:provider,IS_GEMINI:provider==='gemini',
    report:async()=>{},assertNotCancelled:()=>{if(cancel)throw Error('cancelled');},
    waitForResponseIdle:async()=>{},waitForComposer:async()=>({}),composer:()=>({}),composerText:()=>draft,
    setChatGPTImageTool:async()=>{}, // Dedicated actual-mode contract: chatgpt_image_tool_447.cjs.
    attachSourceImages:async urls=>attachments.push(...urls),setComposerText:async(_editor,text)=>{draft=text;},
    waitForStableSendDraft:async()=>({button:{},editor:{}}),userTurns:()=>[],assistantTurns:()=>[],lastUserTurnSignature:()=>'',
    location:{href:provider==='gemini'?'https://gemini.google.com/app/test':'https://chatgpt.com/c/test'},
    sendAndVerify:async()=>{imageSends++;draft='';},motionRequestIsLatestUser:()=>true,
    coverResultScope:()=>({querySelectorAll:()=>[],innerText:''}),coverResultImages:()=>now>delay?[image]:[],
    stopButtonVisible:()=>now<=delay,visible:()=>true,coverImageKey:()=> 'asset-1',
    imageData:async()=> 'data:image/png;base64,fixture',storyImageNoResultReady:()=>false,
    sleep:async ms=>{now+=ms;if(now>1000000)throw Error('fixture runaway');},
    submitPrompt:async(request,urls,name,count,before)=>{attachments.push(...urls);await before();motionSends++;
      motionRequests.push({request,urls,name});return c.motionResponses?.length?c.motionResponses.shift():turn;},
    extractMotionJson:node=>JSON.parse(node.innerText),latestAssistantStrictlyAfterLatestUser:()=>turn,
    waitForMotionAnswer:async()=>turn,
    prepareFlowMotionPlan:async()=> 'rechecked-motion'});
  const send=async(name,extra)=>{
    actions.push(name);assert.equal(extra.context_id,'old');
    if(name==='story_visual_recheck')return status;
    if(name==='story_visual_begin')status.record.story_visual_repair=repair;
    else{
      assert.equal(extra.request_id,'uuid');
      const phases={story_visual_mark_image:'image_requested',story_visual_image:'image_saved',
        story_visual_prepare_motion:'preparing_motion',story_visual_mark_motion:'motion_requested',story_visual_save:'ready',
        story_visual_review_text:'motion_answered_text',story_visual_reformat:'preparing_motion_format',
        story_visual_mark_format:'motion_format_requested'};
      assert(phases[name],name);repair.phase=phases[name];
      if(name==='story_visual_review_text'){repair.answer_text=extra.answer_text;repair.validation=c.textValidation||{repairable:true,errors:['JSON invalid']};}
      if(name==='story_visual_reformat'){
        assert(!repair.format_attempt,'Fixture must never authorize a second format request');
        repair.format_attempt=1;repair.motion_request='format candidate motion, exact owned IDs';
      }
      if(name==='story_visual_save')status.record.prompt='validated motion';
    }
    if(c.afterAction)c.afterAction(name);
    return name==='story_visual_reformat'?{...status,claimed:true}:status;
  };
  vm.runInContext(source.slice(source.indexOf('  async function resumeStoryVisualPlan('),source.indexOf('  async function prepareFlowMotionPlan(')),c);
  return {c,status,repair,actions,attachments,motionRequests,cancel:()=>{cancel=true;},counts:()=>({imageSends,motionSends,now}),
    run:()=>c.resumeStoryVisualPlan({job:{id:'STORY-X'}},{},1,2,status,send)};
}
(async()=>{
  let cases=0;
  for(const provider of ['chatgpt','gemini']){
    const initial=fixture(provider);assert.equal(await initial.run(),'validated motion');
    assert.equal(initial.counts().imageSends,1);assert.equal(initial.counts().motionSends,1);
    assert.deepEqual(initial.attachments,['http://fixture/original.png','http://fixture/new.png']);
    assert.deepEqual(initial.actions,['story_visual_mark_image','story_visual_image','story_visual_prepare_motion','story_visual_mark_motion','story_visual_save']);cases++;
    const slow=fixture(provider,'image_requested',420000);await slow.run();
    assert.equal(slow.counts().imageSends,0);assert(slow.counts().now>420000);cases++;
    const saved=fixture(provider,'image_saved');await saved.run();assert.equal(saved.counts().imageSends,0);
    assert.deepEqual(saved.attachments,['http://fixture/new.png']);cases++;
    const requested=fixture(provider,'motion_requested');await requested.run();
    assert.equal(requested.counts().motionSends,0);assert.equal(requested.counts().imageSends,0);cases++;
    const unknown=fixture(provider,'image_requested');unknown.c.motionRequestIsLatestUser=()=>false;
    await assert.rejects(unknown.run(),/ไม่ส่งซ้ำ/);assert.equal(unknown.counts().imageSends,0);cases++;
    const failed=fixture(provider,'needs_review');await assert.rejects(failed.run(),/ยังไม่ตรงเรื่อง/);
    assert.equal(failed.counts().imageSends,0);assert.equal(failed.actions.length,0);cases++;
    const cancel=fixture(provider);cancel.c.afterAction=name=>{if(name==='story_visual_mark_image')cancel.cancel();};
    await assert.rejects(cancel.run(),/cancelled/);assert.equal(cancel.counts().imageSends,0);cases++;
    const changed=fixture(provider);changed.c.afterAction=()=>{changed.c.composerText=()=> 'changed by user';};
    await assert.rejects(changed.run(),/ข้อความภาพแก้เปลี่ยน/);assert.equal(changed.counts().imageSends,0);cases++;
    const download=fixture(provider,'image_requested');download.c.imageData=async()=>{throw Error('download failed');};
    await assert.rejects(download.run(),/download failed/);assert.equal(download.repair.phase,'image_requested');
    download.c.imageData=async()=> 'data:image/png;base64,fixture';await download.run();
    assert.equal(download.counts().imageSends,0);cases++;
    const recheck=fixture(provider);delete recheck.status.record.story_visual_repair;delete recheck.status.record.story_visual_revision;
    assert.equal(await recheck.run(),'rechecked-motion');assert.deepEqual(recheck.actions,['story_visual_recheck']);cases++;
    const format=fixture(provider);
    format.c.motionResponses=[{innerText:'completed malformed candidate JSON'},{innerText:'{"prompt":"formatted same candidate motion"}'}];
    await format.run();await format.run();
    assert.equal(format.counts().imageSends,1);assert.equal(format.counts().motionSends,2);
    assert.equal(format.actions.filter(x=>x==='story_visual_reformat').length,1);
    assert.equal(format.actions.filter(x=>x==='story_visual_save').length,1);
    assert.deepEqual(format.attachments,['http://fixture/original.png','http://fixture/new.png']);
    assert.equal(format.motionRequests[1].urls.length,0,'Format correction never uploads or creates another image');
    assert(format.actions.indexOf('story_visual_reformat')<format.actions.indexOf('story_visual_mark_format'));cases++;
    const formatPending=fixture(provider,'motion_format_requested');formatPending.repair.format_attempt=1;
    await formatPending.run();assert.equal(formatPending.counts().imageSends,0);assert.equal(formatPending.counts().motionSends,0);
    assert.equal(formatPending.attachments.length,0);assert.deepEqual(formatPending.actions,['story_visual_save']);cases++;
    const oldPartial=fixture(provider,'motion_answered_text');oldPartial.repair.answer_text='{\n"job_id":_';
    await oldPartial.run();assert.equal(oldPartial.counts().imageSends,0);assert.equal(oldPartial.counts().motionSends,0);
    assert.deepEqual(oldPartial.actions,['story_visual_save'],'Read completed candidate answer before asking a format question');cases++;
    const exhausted=fixture(provider,'image_saved');
    exhausted.c.motionResponses=[{innerText:'malformed first answer'},{innerText:'malformed format answer'}];
    exhausted.c.waitForMotionAnswer=async()=>({innerText:'malformed format answer'});
    await assert.rejects(exhausted.run(),/ยังไม่ตรงเรื่อง/);await assert.rejects(exhausted.run(),/ยังไม่ตรงเรื่อง/);
    assert.equal(exhausted.counts().imageSends,0);assert.equal(exhausted.counts().motionSends,2);
    assert.equal(exhausted.actions.filter(x=>x==='story_visual_reformat').length,1);
    assert.equal(exhausted.actions.filter(x=>x==='story_visual_save').length,0);cases++;
    const formatCancel=fixture(provider,'image_saved');
    formatCancel.c.motionResponses=[{innerText:'malformed first answer'}];
    formatCancel.c.afterAction=name=>{if(name==='story_visual_reformat')formatCancel.cancel();};
    await assert.rejects(formatCancel.run(),/cancelled/);
    assert.equal(formatCancel.counts().imageSends,0);assert.equal(formatCancel.counts().motionSends,1);
    assert.equal(formatCancel.repair.phase,'preparing_motion_format');
    assert(!formatCancel.actions.includes('story_visual_mark_format'));cases++;
    const ambiguous=fixture(provider,'motion_requested');
    const conflicting='{"prompt":"first candidate"}\n{"prompt":"different candidate"}';
    ambiguous.c.waitForMotionAnswer=async()=>({innerText:conflicting});
    ambiguous.c.textValidation={repairable:false,repair_kind:'ambiguous_json',errors:['conflicting complete objects']};
    await assert.rejects(ambiguous.run(),/ยังไม่ตรงเรื่อง/);
    assert.deepEqual(ambiguous.actions,['story_visual_review_text']);
    assert.equal(ambiguous.repair.answer_text,conflicting);
    assert.equal(ambiguous.counts().imageSends,0);assert.equal(ambiguous.counts().motionSends,0);cases++;
  }
  console.log(`${cases} Story visual recovery source cases passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
