const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function fixture(provider='gemini',phase=null,index=1,jobId='STORY-X'){
  const messages=[],sends=[];let record=phase?{phase,request:'existing request',prompt:'cached'}:null;
  const context={context_id:'abcd0123456789',job_id:jobId,index,image_url:'http://fixture/scene.png',aspect_ratio:'9:16'};
  const candidate={...context,prompt:'9:16 a single video of the attached character walking naturally.',needs_review:false,reference_compatible:true,material_change:false};
  const c=vm.createContext({activeRunId:'RUN-X',PROVIDER_KEY:provider,AI_NAME:provider,IS_GEMINI:provider==='gemini',
    document:{querySelectorAll:()=>[]},
    analysisAnswerNode:x=>x,motionRequestIsLatestUser:()=>true,
    geminiTextSendKey:async()=> 'legacy-motion-fixture',readGeminiTextSend:async()=>null,
    analysisContentHash:text=>String(text.length),report:async()=>{},submitPrompt:async(...args)=>{if(args[4])await args[4]();sends.push(args);return candidate;},extractJson:x=>x,
    userTurns:()=>[],stopButtonVisible:()=>false,latestAssistantStrictlyAfterLatestUser:()=>null,sleep:async()=>{},assertNotCancelled:()=>{},
    chrome:{runtime:{sendMessage:async m=>{messages.push(m);
      if(m.action==='status')return {ok:true,context,record};
      if(m.action==='prepare'){if(record)return {ok:true,claimed:record.phase==='preparing',context,record};record={phase:'preparing',request:m.request};return {ok:true,claimed:true,context,record};}
      if(m.action==='mark_sending'){assert.equal(record.phase,'preparing');record.phase='requested';return {ok:true,context,record};}
      if(m.action==='review'){const content=m.result.needs_review===true;const errors=content?['needs_review ระบุว่าต้องตรวจเนื้อหา']:m.result.material_change===''?['material_change ต้องเป็น boolean']:[];record={...record,phase:'answered',result:m.result};return {ok:true,record,validation:{errors,repairable:!!errors.length&&!content,content_recheckable:content}};}
      if(m.action==='recheck_content'){if(record.content_recheck_attempt)return {ok:true,claimed:false,record};record={...record,phase:'preparing',content_recheck_attempt:1,request:m.request};return {ok:true,claimed:true,record};}
      if(m.action==='review_text'){
        const capability=provider==='gemini' && m.answer_text==='Gemini บอกว่า\n\nฉันเป็นแค่โมเดลภาษา และไม่สามารถให้ความช่วยเหลือในเรื่องนี้ได้';
        const json=m.answer_text.includes('"prompt"')&&m.answer_text.includes('"context_id"');
        record={...record,phase:'answered_text',answer_text:m.answer_text};
        return {ok:true,record,validation:{errors:['JSON อ่านไม่ได้'],repairable:capability||json,repair_kind:capability?'capability':'json_format'}};
      }
      if(m.action==='reformat'){if(record.format_attempt)return {ok:true,claimed:false,record};record={...record,phase:'requested',format_attempt:1,request:m.request};return {ok:true,claimed:true,record};}
      record={...record,phase:'ready',prompt:m.result.prompt};return {ok:true,context,record};
    }}}
  });
  c.revealChatGPTAnswer=async()=>false; // Separate DOM fixture covers reveal.
  c.refreshPendingChatGPTMotion=async()=>{}; // Separate pending-motion refresh fixture.
  vm.runInContext(source.slice(source.indexOf('  function chatGPTConversationFrames('),source.indexOf('  function assistantTurns(')),c);
  vm.runInContext(source.slice(source.indexOf('  function stableOwnedMotionAnswer('),source.indexOf('  async function submitPrompt(')),c);
  vm.runInContext(source.slice(source.indexOf('  async function prepareFlowMotionPlan('),source.indexOf('  function sceneRepairRequest(')),c);
  vm.runInContext(source.slice(source.indexOf('  function motionRequestIsLatestUser('),source.indexOf('  async function sendAndVerify(')),c);
  return {c,messages,sends,context,setRecord:value=>{record=value;},
    run:()=>c.prepareFlowMotionPlan({job:{id:jobId}},{scene_narrations:['scene beat']},index,6)};
}
(async()=>{
  for(const provider of ['chatgpt','gemini']){
    const initial=fixture(provider,null,2,'JOB-X');await initial.run();
    assert(initial.sends[0][0].includes('one continuous shot'));
    assert(initial.sends[0][0].includes('factual claims and saved narration unchanged'));
    assert(initial.sends[0][0].includes('review_reason'));
    const f=fixture(provider,null,2,'JOB-X');
    const conflict={...f.context,needs_review:true,reference_compatible:false,material_change:true,
      prompt:'Create one vertical 9:16 video. Show device close-up then cut to a car dashboard with split screen.'};
    f.setRecord({phase:'answered',request:'legacy device then dashboard request',result:conflict,
      validation:{content_recheckable:false}});
    await f.run();await f.run();
    assert.equal(f.sends.length,1,'Cached conflict gets one new motion request, not original generation');
    assert.equal(f.sends[0][1].length,1);assert.equal(f.sends[0][1][0],f.context.image_url);
    assert(f.sends[0][0].includes('same attached product image'));
    assert(f.sends[0][0].includes('Do not follow a draft cut'));
    assert(f.sends[0][0].includes('All spoken dialogue must be in Thai only.'));
    assert(f.messages.findIndex(m=>m.action==='recheck_content')<f.messages.findIndex(m=>m.action==='mark_sending'));
    assert.equal(f.messages.filter(m=>m.action==='save').length,1);
    assert(f.messages.filter(m=>m.action==='save').every(m=>m.result.material_change===false));
    const blocked=fixture(provider,null,2,'JOB-X');
    blocked.setRecord({phase:'answered',request:'legacy product motion',result:conflict});
    blocked.c.submitPrompt=async(...args)=>{await args[4]();blocked.sends.push(args);return {...conflict,review_reason:'Reference still does not support the proposed shot'};};
    await assert.rejects(blocked.run(),/Reference still does not support/);
    await assert.rejects(blocked.run(),/หนึ่งรอบ/);
    assert.equal(blocked.sends.length,1,'Unresolved flags cannot loop or reset the persisted retry budget');
    assert.equal(blocked.messages.filter(m=>m.action==='save').length,0);
  }
  const prefixBlock=source.slice(source.indexOf("      if(record.scope === 'flow') {"),source.indexOf("      await save({phase:'ready',candidate,helper_url:location.href});"));
  for(const confirmed of [true,false]){
    const context=vm.createContext({record:{scope:'flow',fictional_ai_characters_confirmed:confirmed},candidate:{needs_review:false,prompt:'9:16 a single original scene'}});
    vm.runInContext(prefixBlock,context);
    const phrase='บุคคลในภาพเป็นตัวละครสมมติที่สร้างด้วย AI ไม่ใช่บุคคลจริง';
    assert.equal(context.candidate.prompt.includes(phrase),false);
    vm.runInContext(prefixBlock,context);assert.equal(context.candidate.prompt.split(phrase).length-1,0);
    if(!confirmed){context.candidate.prompt=phrase;assert.throws(()=>vm.runInContext(prefixBlock,context),/ยืนยัน/);}
  }
  for(const provider of ['chatgpt','gemini']){
    const english=fixture(provider);await english.run();
    const actors=fixture(provider);actors.context.audio_instruction='ACTOR DIALOGUE: มะลิ speaks to ต้น: เห็นกุญแจไหม';
    await actors.run();
    assert(actors.sends[0][0].includes('Follow ACTOR DIALOGUE exactly'));
    assert(actors.sends[0][0].includes('never as spoken lines'));
    assert(actors.sends[0][0].includes('No subtitles or captions'));
    assert(actors.sends[0][0].includes('เห็นกุญแจไหม'));
    assert(!actors.sends[0][0].includes('the visible reviewer speaks'));
    assert(english.sends[0][0].includes('concise English'));
    assert(english.sends[0][0].includes('All spoken dialogue must be in Thai only.'));
    assert(english.sends[0][0].includes('never personal names'));
    assert(english.sends[0][0].includes('Do not repeat facial features'));
    const f=fixture(provider);let count=0;
    f.c.submitPrompt=async(...args)=>{if(args[4])await args[4]();f.sends.push(args);return {job_id:'STORY-X',index:1,context_id:'abcd0123456789',prompt:'9:16 a single video of the attached character walking naturally.',needs_review:count++===0,reference_compatible:count>1,material_change:false};};
    await f.run();await f.run();
    assert.equal(f.sends.length,2);assert.equal(f.sends[1][1][0],'http://fixture/scene.png');
    assert(f.sends[1][0].includes('review_reason'));
    assert.equal(f.messages.filter(m=>m.action==='mark_sending').length,2);
  }
  for(const provider of ['chatgpt','gemini']){
    const f=fixture(provider);await f.run();await f.run();
    assert.equal(f.sends.length,1,'saved prompt is never requested twice');
    assert(f.messages.every(m=>m.provider===provider));
    assert.equal(f.sends[0][1][0],'http://fixture/scene.png');
    assert(f.sends[0][2].startsWith('smartflow-motion-'),'strict current image attachment');
    assert(f.messages.findIndex(m=>m.action==='prepare')<f.messages.findIndex(m=>m.action==='mark_sending'));
  }
  const recovered=fixture('chatgpt','requested');let recoveredClock=0;
  recovered.c.Date={now:()=>recoveredClock};recovered.c.sleep=async()=>{recoveredClock+=1000;};
  recovered.c.userTurns=()=>[{innerText:'existing request'}];recovered.c.analysisResponseStopButton=()=>true;
  const owned={job_id:'STORY-X',index:1,context_id:'abcd0123456789',
    prompt:'The camera gently follows the same character through the original scene.',
    needs_review:false,reference_compatible:true,material_change:false};
  recovered.c.latestAssistantStrictlyAfterLatestUser=()=>({innerText:JSON.stringify(owned)+'_'});
  recovered.c.extractJson=x=>JSON.parse(x.innerText);
  await recovered.run();assert.equal(recoveredClock,60000);assert.equal(recovered.sends.length,0);
  assert(recovered.messages.some(m=>m.action==='review'));assert(recovered.messages.some(m=>m.action==='save'));
  const attachment=fixture();attachment.c.submitPrompt=async()=>{throw Error('AI_IMAGE_REFERENCE_UNCONFIRMED');};
  const schema=fixture();let schemaCalls=0;
  schema.c.submitPrompt=async(...args)=>{schema.sends.push(args);return {job_id:'STORY-X',context_id:'abcd0123456789',index:1,prompt:'เครื่องนวดวางบนแท่น กล้องเคลื่อนรอบสินค้าอย่างช้า ๆ',material_change:schemaCalls++?'': ''};};
  await assert.rejects(schema.run(),/material_change/);
  assert.equal(schema.sends.length,2,'bad schema gets at most one repair');
  assert.equal(schema.sends[1][1].length,0,'repair never uploads another image');
  await assert.rejects(attachment.run(),/AI_IMAGE_REFERENCE_UNCONFIRMED/);
  assert(!attachment.messages.some(m=>m.action==='mark_sending'),'attachment failure never claims Send');
  const preflight=fixture();
  const detail={gesture_phase:'not_started',preflight_reason:'text_guard_changed',changed_fields:['sourceSignature']};
  preflight.c.submitPrompt=async(...args)=>{await args[4]();const error=Error('GEMINI_TEXT_SEND_REVIEW');error.sendDiagnostics=detail;throw error;};
  await assert.rejects(preflight.run(),error=>{
    assert.equal(error.sendDiagnostics,detail);assert.equal(error.submissionDispatched,false);
    return error.message.includes('FLOW_PLAN_REVIEW');
  });
  assert(!preflight.messages.some(m=>['review','save'].includes(m.action)));
  const unknown=fixture('gemini','requested');await assert.rejects(unknown.run(),/FLOW_PLAN_REVIEW/);assert.equal(unknown.sends.length,0);
  const busy=fixture('gemini','requested');let clock=0;
  busy.c.Date={now:()=>clock};busy.c.sleep=async()=>{clock+=1000;};
  busy.c.userTurns=()=>[{innerText:'existing request'}];
  busy.c.analysisResponseStopButton=()=>clock<720000;
  busy.c.latestAssistantStrictlyAfterLatestUser=()=>({innerText:'completed answer'});
  busy.c.extractJson=()=>({prompt:'ready'});
  await busy.run();assert(clock>=727000);assert.equal(busy.sends.length,0,'busy resume waits beyond six minutes without Send');
  const format=fixture();let parses=0;
  format.c.submitPrompt=async(...args)=>{format.sends.push(args);return {innerText:'{"prompt": "motion", "context_id": broken}'};};
  format.c.extractJson=()=>{if(!parses++)throw Error('format');return {prompt:'correct format'};};
  await format.run();assert.equal(format.sends.length,2);assert.equal(format.sends[1][1].length,0);
  assert.equal(format.messages.filter(m=>m.action==='reformat').length,1);
  const bad=fixture();bad.c.extractJson=()=>{throw Error('bad JSON');};await assert.rejects(bad.run(),/FLOW_PLAN_REVIEW/);
  assert.equal(bad.messages.filter(m=>m.action==='save').length,0);
  const declined=fixture();declined.c.submitPrompt=async()=>{throw Error('unknown send');};await assert.rejects(declined.run(),/FLOW_PLAN_REVIEW/);
  const capabilityText='Gemini บอกว่า\n\nฉันเป็นแค่โมเดลภาษา และไม่สามารถให้ความช่วยเหลือในเรื่องนี้ได้';
  for(const repaired of [true,false]) {
    const f=fixture();let calls=0;
    f.c.submitPrompt=async(...args)=>{if(args[4])await args[4]();f.sends.push(args);return ++calls===1||!repaired?{innerText:capabilityText}:{prompt:'กล้องเคลื่อนรอบกล่องเครื่องมืออย่างช้า ๆ คงสินค้าและฉากตามภาพเดิม'};};
    f.c.extractJson=x=>{if(x.innerText)throw Error('no JSON');return x;};
    if(repaired) {await f.run(); await f.run();} else await assert.rejects(f.run(),/FLOW_PLAN_REVIEW/);
    assert.equal(f.sends.length,2,'one capability clarification, no repeat after saved');
    assert.equal(f.sends[1][1].length,0,'no extra attachment/image generation');
    assert(f.sends[1][0].includes('คำขอเดิมของฉากนี้'));
    assert(f.sends[1][0].includes('abcd0123456789'));
    assert.equal(f.messages.filter(m=>m.action==='reformat').length,1);
    assert(f.messages.findIndex(m=>m.action==='review_text')<f.messages.findIndex(m=>m.action==='reformat'));
  }
  for(const [provider,text] of [['chatgpt',capabilityText],['gemini',capabilityText+' เนื่องจากละเมิดนโยบาย'],['gemini','กรุณาแนบรูปใหม่']]){
    const f=fixture(provider);f.c.submitPrompt=async(...args)=>{f.sends.push(args);return {innerText:text};};
    f.c.extractJson=()=>{throw Error('no JSON');};await assert.rejects(f.run(),/FLOW_PLAN_REVIEW/);
    assert.equal(f.sends.length,1,'unknown/reference/policy/ChatGPT not retried');
  }
  // Execute the actual post-image Product handoff block: cached scene1,
  // observed capability failure in scene2, normal scene3, final submit last.
  const scenes=[fixture('gemini','ready',1),fixture('gemini',null,2),fixture('gemini',null,3)];
  let scene2Calls=0;
  scenes[1].c.submitPrompt=async(...args)=>{if(args[4])await args[4]();scenes[1].sends.push(args);return ++scene2Calls===1?{innerText:capabilityText}:{prompt:'กล้องเคลื่อนใกล้ชุดเครื่องมือเดิมอย่างนุ่มนวล ไม่มีการเปลี่ยนสินค้า'};};
  scenes[1].c.extractJson=x=>{if(x.innerText)throw Error('no JSON');return x;};
  const events=[];
  const handoff=vm.createContext({metaSequence:false,generatedImages:['saved1','saved2','saved3'],imageCount:3,completedImageCount:()=>3,
    result:{},pkg:{job:{id:'JOB-X',video_ai_provider:'flow'}},mode:'product',PROVIDER_KEY:'gemini',storyImageFallbacks:{},
    prepareFlowMotionPlan:async(p,r,i)=>{await scenes[i-1].run();events.push('ready'+i);},
    report:async()=>{},chrome:{runtime:{sendMessage:async m=>{events.push(m.type);assert.equal(m.result.generated_images.length,3);return {ok:true};}}}});
  const handoffStart=source.indexOf('      if (generatedImages.some((image) => !image))');
  const handoffEnd=source.indexOf('    } catch (error)',handoffStart);
  assert(handoffStart>0&&handoffEnd>handoffStart);
  await vm.runInContext('(async()=>{'+source.slice(handoffStart,handoffEnd)+'})()',handoff);
  assert.deepEqual(events,['ready1','ready2','ready3','SUBMIT_CHATGPT_RESULT']);
  assert.equal(scenes[0].sends.length,0);assert.equal(scenes[1].sends.length,2);assert.equal(scenes[2].sends.length,1);
  // Resuming the saved non-JSON answer does not require an original re-send.
  const cached=fixture('gemini','answered_text');let cachedCalls=0;
  // A cached parse failure must inspect the current owned answer first. The
  // exact completed capability reply then uses its existing one format turn.
  let cachedClock=1000;
  cached.c.Date={now:()=>cachedClock};cached.c.sleep=async ms=>{cachedClock+=ms;};
  cached.c.userTurns=()=>[{innerText:'คุณบอกว่า\nexisting request'}];
  cached.c.analysisResponseStopButton=()=>false;
  cached.c.latestAssistantStrictlyAfterLatestUser=()=>({innerText:capabilityText,
    // Gemini's actual finished content marker, not ChatGPT's Copy button.
    querySelector:selector=>selector.includes('.markdown[aria-busy="false"]')?{}:null});
  const baseMessage=cached.c.chrome.runtime.sendMessage;
  cached.c.chrome.runtime.sendMessage=async m=>{const r=await baseMessage(m);if(['status','prepare'].includes(m.action))r.record.answer_text=capabilityText;return r;};
  cached.c.extractJson=x=>{if(x.innerText)throw Error('no JSON');return x;};
  cached.c.submitPrompt=async(...args)=>{cachedCalls++;return {prompt:'กล้องเคลื่อนรอบสินค้าตามภาพเดิม ไม่มีการเพิ่มหรือลบชิ้นส่วน'};};
  await cached.run();assert.equal(cachedCalls,1,'cached reply only sends clarification');
  for(const owned of [true,false]) {
    const stale=fixture('gemini','answered',2);const original=stale.c.chrome.runtime.sendMessage;
    stale.c.chrome.runtime.sendMessage=async m=>{
      const value=await original(m);
      if(['status','prepare'].includes(m.action))value.record.result={job_id:'STORY-X',index:1,context_id:'wrong-scene'};
      return value;
    };
    let now=1;stale.c.Date={now:()=>now};stale.c.sleep=async()=>{now+=1000;};
    stale.c.userTurns=()=>[{innerText:owned?'คุณบอกว่า\nexisting request':'previous request'}];
    stale.c.analysisResponseStopButton=()=>false;
    stale.c.latestAssistantStrictlyAfterLatestUser=()=>({innerText:'correct fresh response'});
    stale.c.extractJson=()=>({job_id:'STORY-X',index:2,context_id:'abcd0123456789',prompt:'current-scene motion'});
    if(owned) {await stale.run();assert(now>=8000);assert(stale.messages.some(m=>m.action==='save'&&m.result.index===2));}
    else {await assert.rejects(stale.run(),/FLOW_PLAN_REVIEW/);assert(!stale.messages.some(m=>m.action==='review'||m.action==='save'));}
    assert.equal(stale.sends.length,0,'invalid cached owner recovery is read-only, never a new Send');
  }
  console.log(JSON.stringify({ok:true,coverage:'planner, capability recovery, saved answer resume, three-scene Product handoff'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
