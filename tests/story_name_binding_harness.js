const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const original = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/story_name_binding_2A16D8.json'), 'utf8'));
const bilingual = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/story_bilingual_names_6E3623.json'), 'utf8'));
const phrase = 'แสงสีขาวอมม่วงกะพริบขึ้นเป็นจังหวะที่สาม';
const good = () => ({ bindings: [{ scene_index: 1, entity_id: 'third_signal', phrase }] });
const clone = value => JSON.parse(JSON.stringify(value));
function setup(reply = good(), analysis = original, provider = 'chatgpt') {
  const prompts = [], images = [], messages = [], reports = [], storage = {};
  const page = {user:'MASTER', answer:JSON.stringify(analysis), draft:'', busy:false,attachments:{count:0,busy:false,failed:false}};
  const request = { story_content_contract: {version:1}, required_named_entities: [], prompt_field:'scene_prompts',
    image_count:10, visual_render_instruction:'2D anime', required_fields:['video_title','narration_script','scene_prompts','scene_narrations','scene_durations'] };
  const pkg = {mode:'story',job:{id:analysis.job_id,scene_count:10},run_id:'TEST',request,prompt:'MASTER',image_urls:[],checkpoint_images:[]};
  const context = vm.createContext({ AI_NAME:'Offline', PROVIDER_KEY:provider, IS_GEMINI:provider==='gemini',
    crypto:require('node:crypto').webcrypto, TextEncoder,
    userTurns:()=>[{innerText:page.user,textContent:page.user}],
    latestAssistantStrictlyAfterLatestUser:()=>({innerText:page.answer}),
    analysisAnswerNode:turn=>turn, analysisResponseStopButton:()=>page.busy,
    geminiComposerAttachmentState:()=>page.attachments,chatGPTComposerAttachmentState:()=>page.attachments,
    composer:()=>({}), composerText:()=>page.draft,
    waitForResponseIdle:async()=>{},
    stopButtonVisible:()=>false,
    activeJobId:'',activeRunId:'',cancelRequested:false, location:{href:'https://chatgpt.com/test'},
    report:async(...args)=>reports.push(args), assertNotCancelled:()=>{}, sleep:async()=>{},
    normaliseDialogueSpeakers:v=>v, extractJson:turn=>JSON.parse(turn.innerText),
    submitPrompt:async(prompt,urls,strict,count,beforeSend)=>{
      page.draft=prompt; if(beforeSend)await beforeSend(); prompts.push(prompt);
      const value=prompt.startsWith('MASTER')?analysis:typeof reply==='function'?await reply(prompt,prompts.length):reply;
      if(value instanceof Error)throw value;
      page.user=prompt;page.draft='';page.answer=typeof value==='string'?value:JSON.stringify(value);
      return {innerText:page.answer};},
    submitImagePrompt:async(p,urls,count,strict,metadata)=>{images.push({p,urls,metadata});return {src:provider==='gemini'?`https://lh3.googleusercontent.com/generated-${images.length}`:`https://chatgpt.com/backend-api/estuary/image-${images.length}`, value:'image-'+images.length};},
    imageData:async value=>value.value, ensureAiWebModel:async()=>{}, aiWebFailureDiagnostic:()=>'',
    chrome:{storage:{local:{get:async()=>clone(storage),set:async value=>Object.assign(storage,clone(value))}},runtime:{sendMessage:async message=>{messages.push(message);return {ok:true};}}}
  });
  for(const [start,end] of [['  function normalizeOptionalCover(', '  function visible('], ['  function explicitAnalysisRefusal(','  function stopButton('],
    ['  function storyContentMismatch(','  function largeAssistantImages('],
    ['  async function generateOneImage(','  function productImageFailureKind('],
    ['  async function runJob(','  chrome.runtime.onMessage.addListener(']]) {
    const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);vm.runInContext(source.slice(a,b),context);
  }
  return {context,pkg,prompts,images,messages,reports,storage,page,parse:(result=clone(analysis))=>context.parseOrRepairAnalysis({innerText:JSON.stringify(result)},pkg,'scene_prompts',10)};
}
(async()=>{
  let cases=0;const test=async(name,fn)=>{try{await fn();cases++;}catch(e){e.message=name+': '+e.message;throw e;}};
  await test('real response reproduced then locally bound without rewriting story',async()=>{
    const f=setup(),input=clone(original),saved=JSON.stringify(input);
    assert.throws(()=>f.context.validateStoryContent(input,f.pkg.request,10),e=>e.missingNames.length===1&&e.missingNames[0].entity_id==='third_signal');
    const result=await f.parse(input); assert.equal(f.prompts.length,1);assert.equal(JSON.stringify(input),saved);
    assert.equal(result.scene_prompts[0],original.scene_prompts[0].replace(phrase,phrase+' (สัญญาณที่สาม)'));
    for(const key of Object.keys(original))if(key!=='scene_prompts')assert.deepEqual(JSON.parse(JSON.stringify(result[key])),original[key]);
    assert.deepEqual(Array.from(result.scene_prompts).slice(1),original.scene_prompts.slice(1));
    assert.equal(result.story_content_name_repair.changes.length,1);
    assert(f.prompts[0].includes('ไม่สร้างรูป'));assert.equal(f.images.length,0);
  });
  await test('fresh actual runJob continues all ten indexed scenes after repair and checkpoint',async()=>{
    const f=setup();await f.context.runJob(f.pkg);assert.equal(f.prompts.length,2);assert.equal(f.images.length,10);
    const checkpoint=f.messages.find(m=>m.type==='CHECKPOINT_STORY_ANALYSIS');assert(checkpoint.result.story_content_name_repair);
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,10);
    assert.equal(f.images[0].metadata.scene_index,1);assert.equal(f.images[9].metadata.scene_index,10);
  });
  const bad=[{bindings:[{...good().bindings[0],entity_id:'mira'}]},
    {bindings:[{...good().bindings[0],scene_index:2}]},{bindings:[{...good().bindings[0],phrase:'invented description'}]},
    {bindings:[{...good().bindings[0],phrase:'แสง'}]},
    {bindings:[{...good().bindings[0],phrase:'เสารับคลื่นทรงวงแหวนของอาร์คมี'+phrase}]},
    {...good(),narration_script:'replacement'}, {bindings:[{...good().bindings[0],extra:true}]},
    {bindings:[...good().bindings,...good().bindings]}, 'I cannot help due to policy'];
  for(const reply of bad)await test('invalid/refused repair stops once '+JSON.stringify(reply),async()=>{
    const f=setup(reply);await assert.rejects(f.parse(),{code:'STORY_CONTENT_MISMATCH'});assert.equal(f.prompts.length,1);assert.equal(f.images.length,0);
  });
  for(const reply of [{bindings:[]}, 'still generating', '{broken'])await test('completed incomplete repair has finite supplemental budget '+JSON.stringify(reply),async()=>{
    const f=setup(reply);await assert.rejects(f.parse(),{code:'STORY_CONTENT_MISMATCH'});assert.equal(f.prompts.length,3);assert.equal(f.images.length,0);
  });
  for(const field of ['reuse_analysis','scene_prompt_overrides','checkpoint_images'])await test('never repair saved reviewed or paid plan '+field,async()=>{
    const f=setup();f.pkg[field]=field==='checkpoint_images'?[{index:1,url:'saved'}]:true;
    await assert.rejects(f.parse(),{code:'STORY_CONTENT_MISMATCH'});assert.equal(f.prompts.length,0);
  });
  await test('user named anchor remains strict',async()=>{
    const f=setup();f.pkg.request.required_named_entities=['สัญญาณที่สาม'];await assert.rejects(f.parse(),{code:'STORY_CONTENT_MISMATCH'});assert.equal(f.prompts.length,0);
  });
  await test('other invalid structure does not trigger name repair',async()=>{
    const f=setup(),input=clone(original);input.scene_durations=[];await assert.rejects(f.parse(input),{code:'STORY_CONTENT_MISMATCH'});assert.equal(f.prompts.length,0);
  });
  await test('uncertain repair Send never retries',async()=>{
    const error=Object.assign(new Error('uncertain'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED',submissionDispatched:true,
      sendDiagnostics:{draft_still_present:true,trusted_click_seen:true,prompt_length:9796}});
    const diagnostics=error.sendDiagnostics, f=setup(error);
    await assert.rejects(f.parse(),e=>e===error && e.message.startsWith('รับบทวิเคราะห์แล้ว • ติดขั้นตรวจการอ้างชื่อในแผน')
      && e.code==='AI_SEND_DISPATCHED_UNCONFIRMED' && e.submissionDispatched===true && e.sendDiagnostics===diagnostics);
    assert.equal(f.prompts.length,1);assert.equal(f.images.length,0);
    assert(f.reports.find(r=>r[0]==='repairing_story_names')[1].startsWith('รับบทวิเคราะห์แล้ว'));
  });
  for(const code of ['USER_CANCELLED','LOGIN_REQUIRED'])await test('other errors remain unchanged '+code,async()=>{
    const error=Object.assign(new Error('original reason'),{code}),f=setup(error);
    await assert.rejects(f.parse(),e=>e===error && e.message==='original reason');assert.equal(f.prompts.length,1);
  });
  for(const provider of ['gemini','chatgpt'])await test('exact bilingual response proceeds ten scenes without repair '+provider,async()=>{
    const input=clone(bilingual), before=JSON.stringify(input), f=setup(good(),input,provider);
    const parsed=await f.parse(input);assert.equal(JSON.stringify(parsed),before);assert.equal(f.prompts.length,0);
    await f.context.runJob(f.pkg);
    assert.equal(f.prompts.length,1);assert(f.prompts[0].startsWith('MASTER'));assert.equal(f.images.length,10);
    assert.equal(f.reports.filter(r=>r[0]==='repairing_story_names').length,0);
    const checkpoint=f.messages.find(m=>m.type==='CHECKPOINT_STORY_ANALYSIS');assert(checkpoint);
    for(const key of Object.keys(input))assert.deepEqual(JSON.parse(JSON.stringify(checkpoint.result[key])),input[key]);
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length,10);
    assert.equal(JSON.stringify(input),before);assert(!checkpoint.result.story_content_name_repair);
  });
  await test('bilingual saved analysis needs no repair on resume',async()=>{
    const f=setup(good(),bilingual,'gemini');f.pkg.reuse_analysis=true;
    const result=await f.context.validateOrRepairStoredAnalysis(clone(bilingual),f.pkg,'scene_prompts',10);
    assert.equal(f.prompts.length,0);assert.deepEqual(JSON.parse(JSON.stringify(result)),bilingual);
  });
  await test('first-generation fixture aliases really omit English spellings',async()=>{
    assert.deepEqual(bilingual.story_entities[0].aliases,['เจ้าด่าง','ด่าง']);
    const f=setup();assert.equal(f.context.storyNameInText(bilingual.scene_prompts[0],bilingual.story_entities[0].name),false);
    assert.equal(bilingual.story_entities[0].aliases.some(n=>f.context.storyNameInText(bilingual.scene_prompts[0],n)),false);
  });
  const partCases=[['เจ้าด่าง (Chao Dang)',['เจ้าด่าง','Chao Dang']],['Nong May (น้องเมย์)',['Nong May','น้องเมย์']],
    ['เจ้าด่าง （Ｃｈａｏ Ｄａｎｇ）',['เจ้าด่าง','Chao Dang']],['เจ้าด่าง (a generic hero)',[]],
    ['เจ้าด่าง (Chao Dang) (Dog)',[]],['เจ้าด่าง ((Chao Dang))',[]],['เจ้าด่าง (Chao 2)',[]],
    ['เจ้าด่าง (Chao\nDang)',[]],['เจ้าด่าง (Chao/Dang)',[]],['เจ้าด่าง๒ (Chao Dang)',[]],
    ['Thor (God Of Thunder)',[]],['น้องเมย์ (Nong May) extra',[]]];
  for(const [name,expected] of partCases)await test('strict bilingual display parsing '+name,async()=>{
    assert.deepEqual(Array.from(setup().context.storyBilingualDisplayParts(name)),expected);
  });
  for(const collision of ['canonical','alias','display'])await test('ambiguous inferred Latin does not bind '+collision,async()=>{
    const f=setup(),input=clone(bilingual);
    input.story_entities.push({id:'other',name:collision==='canonical'?'Chao Dang':collision==='display'?'เจ้าส้ม (Chao Dang)':'Another Dog',
      aliases:collision==='alias'?['Chao Dang']:[],visual_identity:'Another separate character.'});
    assert.throws(()=>f.context.validateStoryContent(input,f.pkg.request,10),e=>e.code==='STORY_CONTENT_MISMATCH');
  });
  await test('Thai spacing collisions also block newly inferred names',async()=>{
    const f=setup(),input=clone(bilingual);input.story_entities[0].name='เจ้า ด่าง (Chao Dang)';input.story_entities[0].aliases=[];
    input.scene_prompts=input.scene_prompts.map(p=>p.replaceAll('Chao Dang','เจ้าด่าง'));
    input.story_entities.push({id:'other',name:'เจ้าด่าง',aliases:[],visual_identity:'Different dog.'});
    assert.throws(()=>f.context.validateStoryContent(input,f.pkg.request,10),e=>e.code==='STORY_CONTENT_MISMATCH');
  });
  await test('user anchored bilingual names are not silently expanded',async()=>{
    const f=setup(),input=clone(bilingual);f.pkg.request.required_named_entities=[input.story_entities[0].name];
    assert.throws(()=>f.context.validateStoryContent(input,f.pkg.request,10),e=>e.code==='STORY_CONTENT_MISMATCH');
    f.pkg.request.story_source_aliases={[input.story_entities[0].name]:['Chao Dang']};
    f.context.validateStoryContent(input,f.pkg.request,10);
  });
  await test('different names and Latin substrings still fail',async()=>{
    const f=setup(),input=clone(bilingual);input.scene_prompts[0]=input.scene_prompts[0].replaceAll('Chao Dang','Chao Dan');
    assert.throws(()=>f.context.validateStoryContent(input,f.pkg.request,10),e=>e.code==='STORY_CONTENT_MISMATCH');
    assert.equal(f.context.storyNameInText('An author writes','Thor'),false);
  });
  await test('name repair cannot relabel another bilingual named character',async()=>{
    const otherPhrase='Chao Dang walks across the floor',input=clone(original);
    input.story_entities.push({id:'dog',name:'เจ้าด่าง (Chao Dang)',aliases:[],visual_identity:'Honey-brown dog.'});
    input.scene_entities[0].push('dog');input.scene_prompts[0]+=' '+otherPhrase;
    const f=setup({bindings:[{scene_index:1,entity_id:'third_signal',phrase:otherPhrase}]},input);
    await assert.rejects(f.parse(),{code:'STORY_CONTENT_MISMATCH'});
    assert.equal(f.prompts.length,1);assert.equal(f.images.length,0);
  });
  await test('analysis checkpoint failure prevents every image',async()=>{
    const f=setup();f.context.chrome.runtime.sendMessage=async()=>({ok:false,error:'disk failed'});
    await assert.rejects(f.context.runJob(f.pkg),/disk failed/);assert.equal(f.images.length,0);
  });
  if(process.argv.includes('--emit')) {const f=setup();process.stdout.write(JSON.stringify(await f.parse()));}
  else console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
