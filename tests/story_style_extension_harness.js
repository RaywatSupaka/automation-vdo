const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, `Missing source section ${start}`);
  return source.slice(first, last);
}
function analysis() {
  return {
    video_title: 'Secret Wars', video_description: 'Marvel story', narration_script: 'บทเรื่องเดิม',
    visual_bible: { world: 'Marvel Earth-616', lighting: 'cool blue', characters: { doom: 'Doctor Doom', thor: 'Thor' } },
    story_entities: [
      { id: 'doom', name: 'Doctor Doom', aliases: ['ด็อกเตอร์ ดูม'], visual_identity: { mask: 'metal mask', cloak: 'green cloak' } },
      { id: 'thor', name: 'Thor', aliases: ['ธอร์'], visual_identity: 'thunder guardian with Mjolnir' }
    ],
    scene_entities: [['doom'], ['thor']],
    scene_prompts: ['Doctor Doom raises a metal gauntlet, wearing his metal mask and green cloak.', 'Thor raises Mjolnir above a cracked bridge.'],
    scene_narrations: ['ด็อกเตอร์ ดูมยกมือขึ้นเหนือเมือง', 'ธอร์ยกค้อนขึ้นเหนือสะพาน'],
    pronunciation_notes: { 'Doctor Doom': 'ด็อกเตอร์ ดูม', Thor: 'ธอร์' }, scene_durations: [4, 4]
  };
}
function request() {
  return { story_content_contract: { version: 1 }, required_named_entities: ['Doctor Doom', 'Thor'],
    prompt_field: 'scene_prompts', image_count: 2, visual_style_instruction: 'STYLE: 2D anime',
    required_fields: ['video_title', 'scene_prompts', 'scene_narrations', 'visual_bible', 'story_entities', 'scene_entities'] };
}
function fixture(outcomes = []) {
  const sent = [], reports = [], messages = [], analysisRequests = [], storage = {};
  const context = vm.createContext({
    waitForResponseIdle:async()=>{},
    stopButtonVisible:()=>false,
    AI_NAME: 'Offline provider', PROVIDER_KEY: 'gemini', IS_GEMINI: true,
    location: { href: 'https://gemini.google.com/app/offline-test' },
    activeJobId: '', activeRunId: '', activeProductOutfitMode: '', cancelRequested: false,
    submitImagePrompt: async (prompt, urls, completedCount, strictReference, storyContext) => {
      sent.push({ prompt, urls, completedCount, strictReference, storyContext });
      const outcome = outcomes.length ? outcomes.shift() : `image-${sent.length}`;
      if (outcome instanceof Error) throw outcome;
      return {src:context.PROVIDER_KEY === 'gemini' ? `https://lh3.googleusercontent.com/generated-${sent.length}` : `https://chatgpt.com/backend-api/estuary/generated-${sent.length}`, value:outcome};
    },
    report: async (step, message, count, detail) => reports.push({ step, message, count, detail }),
    sleep: async () => {}, assertNotCancelled: () => {}, imageData: async (image) => image.value,
    ensureAiWebModel: async () => {}, aiWebFailureDiagnostic: () => '{}',
    collectConversationImageUrls: async () => [],
    normaliseDialogueSpeakers: (value) => value, extractJson: (turn) => JSON.parse(turn.innerText),
    submitPrompt: async (prompt) => { analysisRequests.push(prompt); return { innerText: JSON.stringify(analysis()) }; },
    chrome: { storage: { local: { get: async () => ({...storage}), set: async value => Object.assign(storage,value) } },
      runtime: { sendMessage: async (message) => { messages.push(message); return { ok: true }; } } }
  });
  vm.runInContext(section('  function explicitAnalysisRefusal(', '  function stopButton('), context);
  vm.runInContext(section('  function geminiStoryTechnicalFailure(', '  function geminiTextRequestReview('), context);
  vm.runInContext(section('  function storyContentMismatch(', '  function largeAssistantImages('), context);
  vm.runInContext(section('  async function generateOneImage(', '  function productImageFailureKind('), context);
  vm.runInContext(section('  function normalizeOptionalCover(', '  function visible('), context);
  vm.runInContext(section('  async function runJob(', '  chrome.runtime.onMessage.addListener('), context);
  return { context, sent, reports, messages, analysisRequests,
    run: (result = analysis(), req = request(), packageOverrides = {}) => context.runJob({
      mode: 'story', job: { id: 'STORY-CONTENT-TEST', scene_count: 2 }, run_id: 'RUN-CONTENT', prompt: 'Story text',
      request: req, reuse_analysis: true, analysis_checkpoint: result, image_urls: [], checkpoint_images: [], ...packageOverrides
    }) };
}
// Only silence models the existing retry path. Completed text is not proof
// that another image-generation request is safe.
const transient = (text = '') => Object.assign(new Error(text || 'No response'), { code: text ? 'CHATGPT_NO_IMAGE' : 'CHATGPT_NO_RESPONSE', responseText: text });
const mismatch = (error) => error.code === 'STORY_CONTENT_MISMATCH' && error.message.startsWith('STORY_CONTENT_MISMATCH');

(async () => {
  let cases = 0;
  async function test(name, action) { try { await action(); cases++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; } }
  await test('long video keeps all 40 scenes and uses landscape for both providers', async () => {
    for (const provider of ['chatgpt', 'gemini']) {
      const f = fixture(), req = request(), result = analysis();
      f.context.PROVIDER_KEY = provider; f.context.IS_GEMINI = provider === 'gemini';
      req.image_count = 40; req.aspect_ratio = '16:9';
      for (const key of ['scene_prompts','scene_narrations','scene_entities','scene_durations']) {
        result[key] = Array.from({length:40}, (_,i)=>result[key][i%2]);
      }
      await f.run(result, req, {job:{id:'STORY-LONG-TEST',scene_count:40,long_video:{aspect_ratio:'16:9'}}});
      assert.equal(f.sent.length, 40);
      assert(f.sent.every(row=>row.prompt.includes('16:9') && !row.prompt.includes('9:16') && !row.prompt.includes('แนวตั้ง')));
      assert(f.sent[0].prompt.includes('Doctor Doom'));
    }
  });
  for (const style of ['2D anime', 'comic ink', 'watercolor', 'photorealistic', 'stylized 3D', 'cinematic photography']) {
    await test(`style ${style} preserves per-scene content`, async () => {
      const f = fixture(), req = request(); req.visual_style_instruction = `STYLE: ${style}`;
      await f.run(analysis(), req);
      assert.equal(f.sent.length, 2);
      assert(f.sent[0].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที'));
      assert(f.sent[0].prompt.includes(`\n\nSTYLE: ${style}\n\n`));
      assert(f.sent[1].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที'));
      assert(f.sent[1].prompt.includes(`\n\nSTYLE: ${style}\n\n`));
      assert(f.sent[0].prompt.includes('Doctor Doom') && f.sent[0].prompt.includes('metal mask') && f.sent[0].prompt.includes('green cloak'));
      assert(!f.sent[0].prompt.includes(analysis().scene_narrations[0]), 'Voice narration must not be copied as a literal image instruction');
      assert(f.sent[0].prompt.includes('Doctor Doom raises a metal gauntlet'));
      assert(f.sent[0].prompt.includes('Marvel Earth-616') && f.sent[0].prompt.includes('cool blue'));
      assert(!f.sent[0].prompt.includes('Thor'), 'Do not copy the entire cast to every scene');
      assert(f.sent[1].prompt.includes('Thor raises Mjolnir') && !f.sent[1].prompt.includes('Doctor Doom'));
      assert.equal(f.messages.filter((m) => m.type === 'CHECKPOINT_STORY_IMAGE').length, 2);
    });
  }
  for(const renderStyle of ['', '2D anime', 'comic ink', 'watercolor', 'photorealistic', 'stylized 3D', 'cinematic photography', 'วาดด้วยดินสอสี\nแสงอาทิตย์ยามเช้า รายละเอียดโลหะนุ่มนวล']) {
    await test(`render-only Story uses factual compact briefs for every scene: ${renderStyle || 'auto'}`,async()=>{
      const f=fixture(), req=request(), result=analysis();
      f.context.PROVIDER_KEY='chatgpt'; f.context.IS_GEMINI=false;
      req.visual_render_instruction=renderStyle;
      req.visual_style_instruction='LEGACY_STYLE_META Actor likeness is not implied. Preserve prior images and use the visual bible.';
      req.visual_depiction_instruction='NON_GRAPHIC_META Use narration only in the program.';
      result.visual_bible.plot='BIBLE_PLOT_DO_NOT_RENDER';
      result.visual_bible.narration='BIBLE_NARRATION_DO_NOT_RENDER';
      result.visual_bible.camera='35mm lens'; result.visual_bible.color_palette='silver and blue';
      await f.run(result,req);
      assert.equal(f.sent.length,2); assert.equal(f.analysisRequests.length,0);
      for(let index=0;index<2;index++){
        const prompt=f.sent[index].prompt;
        assert(prompt.startsWith('สร้างภาพแนวตั้ง 9:16 หนึ่งภาพจากคำบรรยายต่อไปนี้:'));
        assert(prompt.includes(result.scene_prompts[index]),'Do not rewrite or shorten the actual visible scene');
        assert.equal(prompt.includes('เทคนิคภาพ:'),Boolean(renderStyle));
        if(renderStyle)assert(prompt.includes(`เทคนิคภาพ: ${renderStyle}`),'Custom direction must remain exact');
        for(const fact of ['Marvel Earth-616','cool blue','35mm lens','silver and blue'])assert(prompt.includes(fact),fact);
        for(const unwanted of ['LEGACY_STYLE_META','Actor likeness','NON_GRAPHIC_META','NON-GRAPHIC VISUAL DEPICTION','BIBLE_PLOT_DO_NOT_RENDER','BIBLE_NARRATION_DO_NOT_RENDER','visual_bible','บทพากย์แยกเก็บไว้',result.narration_script,...result.scene_narrations])assert(!prompt.includes(unwanted),unwanted);
        assert.deepEqual(f.sent[index].urls,[]);
        assert.equal(f.sent[index].storyContext.scene_index,index+1);assert.equal(f.sent[index].storyContext.attempt,1);
        assert.equal(f.sent[index].completedCount,index);
      }
      assert(f.sent[0].prompt.includes('Doctor Doom')&&f.sent[0].prompt.includes('metal mask')&&f.sent[0].prompt.includes('green cloak'));
      assert(!f.sent[0].prompt.includes('Thor'));assert(!f.sent[1].prompt.includes('Doctor Doom'));
      assert(f.sent[1].prompt.includes('Thor')&&f.sent[1].prompt.includes('thunder guardian with Mjolnir'));
      assert.equal(f.messages.filter(row=>row.type==='CHECKPOINT_STORY_ANALYSIS').length,1);
      assert.deepEqual(f.messages.filter(row=>row.type==='CHECKPOINT_STORY_IMAGE').map(row=>row.index),[1,2]);
      assert.equal(f.messages.filter(row=>row.type==='SUBMIT_STORY_RESULT').length,1);
    });
  }
  for(const invalid of [undefined,null,42,false,{},[], 'x'.repeat(6001)])await test(`invalid render-only metadata stops before images/checkpoints: ${typeof invalid}`,async()=>{
    const f=fixture(), req=request();req.visual_render_instruction=invalid;
    await assert.rejects(f.run(analysis(),req),mismatch);
    assert.equal(f.sent.length,0);assert.equal(f.analysisRequests.length,0);
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_ANALYSIS'||row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
  });
  await test('fresh Story analysis enters the compact path once and retains normal checkpoints',async()=>{
    const f=fixture(),req=request();req.visual_render_instruction='photorealistic';
    await f.run(analysis(),req,{reuse_analysis:false});
    assert.equal(f.analysisRequests.length,1);assert.equal(f.sent.length,2);
    assert(f.sent.every(row=>row.prompt.startsWith('สร้างภาพแนวตั้ง 9:16 หนึ่งภาพจากคำบรรยายต่อไปนี้:')));
    assert.deepEqual(f.messages.map(row=>row.type),['CHECKPOINT_STORY_ANALYSIS','CHECKPOINT_STORY_IMAGE','CHECKPOINT_STORY_IMAGE','SUBMIT_STORY_RESULT']);
  });
  await test('compact duplicate-image recovery keeps render-only style and the same indexed scene',async()=>{
    const f=fixture(['image-one','image-one','image-two']),req=request();req.visual_render_instruction='watercolor';
    await f.run(analysis(),req);
    assert.equal(f.sent.length,3);
    for(const row of f.sent)assert(row.prompt.includes('เทคนิคภาพ: watercolor'));
    assert.equal(f.sent[2].storyContext.scene_index,2);
    assert(f.sent[2].prompt.includes(analysis().scene_prompts[1]));assert(!f.sent[2].prompt.includes('Doctor Doom'));
    assert.deepEqual(f.messages.filter(row=>row.type==='CHECKPOINT_STORY_IMAGE').map(row=>row.index),[1,2]);
  });
  await test('inherited render metadata does not opt a legacy package into compact prompts',async()=>{
    const legacy=fixture(), inherited=fixture(), req=Object.assign(Object.create({visual_render_instruction:'DO_NOT_USE'}),request());
    await legacy.run();await inherited.run(analysis(),req);
    assert.deepEqual(inherited.sent.map(row=>row.prompt),legacy.sent.map(row=>row.prompt));
  });
  for(const newField of ['2D anime',null])await test(`source-backed Story ignores new render-only field and stays byte-identical: ${newField}`,async()=>{
    const legacy=fixture(), current=fixture(), req=request();req.visual_render_instruction=newField;
    await legacy.run(analysis(),request(),{image_urls:['source-image']});
    await current.run(analysis(),req,{image_urls:['source-image']});
    assert.equal(JSON.stringify(current.sent),JSON.stringify(legacy.sent));
  });
  for(const mode of ['story','product'])await test(`direct ${mode} source-backed generator ignores eighth render-only argument`,async()=>{
    const legacy=fixture(), current=fixture();
    await legacy.context.generateOneImage('Raw visible scene',['source-image'],1,mode,0,'LEGACY STYLE','LEGACY CONTEXT');
    await current.context.generateOneImage('Raw visible scene',['source-image'],1,mode,0,'LEGACY STYLE','LEGACY CONTEXT','MUST_NOT_APPEAR');
    assert.equal(JSON.stringify(current.sent),JSON.stringify(legacy.sent));
  });
  await test('compact generation respects saved indexed images and audit scene numbering',async()=>{
    const f=fixture(),req=request();req.visual_render_instruction='watercolor';
    f.context.imageDataFromUrl=async()=> 'saved-scene-one';
    await f.run(analysis(),req,{checkpoint_images:[{index:1,url:'checkpoint://scene-one'}]});
    assert.equal(f.sent.length,1);assert(f.sent[0].prompt.includes(analysis().scene_prompts[1]));
    assert.equal(f.sent[0].storyContext.scene_index,2);assert.equal(f.sent[0].completedCount,1);
    assert.deepEqual(f.messages.filter(row=>row.type==='CHECKPOINT_STORY_IMAGE').map(row=>row.index),[2]);
    const submitted=f.messages.find(row=>row.type==='SUBMIT_STORY_RESULT');
    assert.equal(submitted.result.generated_images[0],'saved-scene-one');
  });
  await test('compact generation never advances after an unacknowledged scene checkpoint',async()=>{
    const f=fixture(),req=request();req.visual_render_instruction='';
    f.context.chrome.runtime.sendMessage=async message=>{f.messages.push(message);return message.type==='CHECKPOINT_STORY_IMAGE'?{ok:false,error:'checkpoint refused'}:{ok:true};};
    await assert.rejects(f.run(analysis(),req),/checkpoint refused/);
    assert.equal(f.sent.length,1);assert(!f.messages.some(row=>row.type==='SUBMIT_STORY_RESULT'));
  });
  for(const code of ['STORY_IMAGE_AUDIT_UNCONFIRMED','STORY_IMAGE_CONTEXT_CONFLICT','AI_SEND_DISPATCHED_UNCONFIRMED'])await test(`compact generation preserves terminal guard ${code}`,async()=>{
    const f=fixture([Object.assign(new Error(code),{code})]),req=request();req.visual_render_instruction='3D';
    await assert.rejects(f.run(analysis(),req),{code});
    assert.equal(f.sent.length,1);assert(!f.reports.some(row=>row.step==='retrying_image'));
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
  });
  for(const [response,code] of [
    ['Please send the prompt again, then I will generate an image.','STORY_IMAGE_RESPONSE_REVIEW'],
    ['Please upload the target image.','STORY_REFERENCE_REQUIRED'],
    ['This image request violates policy.','STORY_IMAGE_REFUSED']
  ])await test(`compact generation does not retry completed text: ${code}`,async()=>{
    const f=fixture([transient(response)]),req=request();req.visual_render_instruction='cinematic';
    await assert.rejects(f.run(analysis(),req),{code});
    assert.equal(f.sent.length,1);assert(!f.reports.some(row=>row.step==='retrying_image'));
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
  });
  await test('transient retry retains exact story, style, references and ages', async () => {
    const f = fixture([transient(), 'image']);
    await f.context.generateOneImage('Doctor Doom shields a child without changing their ages.', ['reference'], 1, 'story', 0, 'STYLE: 2D anime', f.context.storySceneContent(analysis(), 0));
    assert.equal(f.sent.length, 2); assert.equal(f.sent[0].prompt, f.sent[1].prompt);
    assert.deepEqual(f.sent[1].urls, ['reference']); assert(!f.sent[1].prompt.includes('ยี่สิบห้าปี'));
  });
  for (const reason of ['third-party content policy', 'คำขอขัดต่อนโยบาย', 'I cannot help with that request', "I can't generate this image", "I'm unable to create that image", 'ผู้ให้บริการเนื้อหาบุคคลที่สาม']) {
    await test(`refusal stops: ${reason}`, async () => {
      const f = fixture([transient(reason)]);
      await assert.rejects(f.context.generateOneImage('Doctor Doom in Marvel Secret Wars', [], 1, 'story', 0, 'STYLE: anime'),
        (error) => error.code === 'STORY_IMAGE_REFUSED' && error.message.startsWith('STORY_IMAGE_REFUSED'));
      assert.equal(f.sent.length, 1); assert(!f.reports.some((r) => r.step === 'retrying_image'));
    });
  }
  await test('last allowed attempt refusal remains terminal', async () => {
    const f = fixture([transient(), transient(), transient('policy refusal')]);
    await assert.rejects(f.context.generateOneImage('Doctor Doom', [], 1, 'story'), { code: 'STORY_IMAGE_REFUSED' });
    assert.equal(f.sent.length, 3);
  });
  await test('unknown send never retries', async () => {
    const f = fixture([Object.assign(new Error('uncertain'), { code: 'AI_SEND_DISPATCHED_UNCONFIRMED' })]);
    await assert.rejects(f.context.generateOneImage('Doctor Doom', [], 1, 'story'), { code: 'AI_SEND_DISPATCHED_UNCONFIRMED' }); assert.equal(f.sent.length, 1);
  });
  await test('duplicate retry changes framing of same event', async () => {
    const f = fixture(['same-image', 'same-image', 'different-image']); await f.run();
    assert.equal(f.sent.length, 3); assert(f.sent[2].prompt.includes(analysis().scene_prompts[1]));
    assert(!f.sent[2].prompt.includes(analysis().scene_narrations[1]));
    assert(f.sent[2].prompt.includes('เปลี่ยนเฉพาะมุมกล้อง') && f.sent[2].prompt.includes('ห้ามเปลี่ยนเป็นเหตุการณ์ใหม่'));
    assert(f.sent[2].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที'));
    assert(f.sent[2].prompt.includes('\n\nSTYLE: 2D anime\n\n'));
  });
  for (const [name, mutate] of [
    ['missing registry', (r) => { delete r.story_entities; }],
    ['null registry', (r) => { r.story_entities = null; }],
    ['duplicate ids', (r) => { r.story_entities[1].id = 'doom'; }],
    ['unknown scene id', (r) => { r.scene_entities[0] = ['unknown']; }],
    ['duplicate scene id', (r) => { r.scene_entities[0] = ['doom', 'doom']; }],
    ['empty scene id', (r) => { r.scene_entities[0] = ['']; }],
    ['invalid aliases', (r) => { r.story_entities[0].aliases = 'Doom'; }],
    ['oversized identity', (r) => { r.story_entities[0].visual_identity = 'x'.repeat(4001); }],
    ['generic replacement', (r) => { r.story_entities[0].name = 'Anonymous king'; r.story_entities[0].aliases.push('Doctor Doom'); r.scene_prompts[0] = 'Anonymous king raises his hand'; }],
    ['untrusted generic alias', (r) => { r.story_entities[0].aliases.push('Anonymous king'); r.scene_prompts[0] = 'Anonymous king raises his hand'; }],
    ['missing scene name', (r) => { r.scene_prompts[0] = 'A generic king raises his hand'; }],
    ['oversized global bible', (r) => { r.visual_bible.world = 'x'.repeat(20001); }]
  ]) {
    await test(`${name} fails before checkpoint and no repair request`, async () => {
      const f = fixture(), result = analysis(); mutate(result); await assert.rejects(f.run(result), mismatch);
      assert.equal(f.sent.length, 0); assert.equal(f.analysisRequests.length, 0); assert.equal(f.messages.length, 0);
    });
  }
  await test('Latin boundaries reject Thor inside author', async () => {
    const f = fixture(), result = analysis(); result.scene_prompts[1] = 'An author raises a hammer';
    await assert.rejects(f.run(result), mismatch); assert.equal(f.context.storyNameInText('An author', 'Thor'), false);
  });
  await test('source alias and tied Thai pronunciation preserve identities despite spacing', async () => {
    const f = fixture(), result = analysis(), req = request(); result.scene_prompts[0] = 'ด็อกเตอร์ดูมยกมือขึ้นเหนือเมือง';
    result.scene_prompts[1] = 'God of Thunder raises Mjolnir'; req.story_source_aliases = { Thor: ['God of Thunder'] };
    await f.run(result, req); assert(f.sent[0].prompt.includes('Doctor Doom') && f.sent[1].prompt.includes('Thor'));
  });
  await test('offscreen narration does not force all characters on screen', async () => {
    const f = fixture(), result = analysis(); result.scene_narrations[0] += ' ขณะที่ธอร์ยังอยู่อีกเมือง'; await f.run(result);
    assert(!f.sent[0].prompt.includes('"name":"Thor"'));
  });
  await test('depiction boundary excludes plot/narration but keeps visible plan and identity', async () => {
    const f = fixture(), result = analysis(), req = request();
    result.scene_narrations[0] = 'VOICE_ONLY_DANGEROUS_ACTION';
    result.visual_bible.plot = { action: 'PLOT_ONLY_DANGEROUS_ACTION' };
    req.visual_depiction_instruction = 'NON-GRAPHIC VISUAL DEPICTION: anticipation only; preserve cast.';
    const original = JSON.stringify(result);
    await f.run(result, req);
    assert(f.sent[0].prompt.includes(req.visual_depiction_instruction));
    assert(!f.sent[0].prompt.includes('VOICE_ONLY') && !f.sent[0].prompt.includes('PLOT_ONLY'));
    assert(f.sent[0].prompt.includes('Doctor Doom raises') && f.sent[0].prompt.includes('metal mask'));
    for(const [key,value] of Object.entries(JSON.parse(original)))assert.equal(JSON.stringify(result[key]), JSON.stringify(value), `Saved ${key} must not be mutated`);
  });
  await test('actual Thai violence refusal stops without another submission', async () => {
    const f = fixture([transient('เราขออภัยอย่างยิ่ง แต่ภาพที่เราสร้างอาจละเมิดกฎเกณฑ์ของเราเกี่ยวกับความรุนแรง')]);
    await assert.rejects(f.run(), {code:'STORY_IMAGE_REFUSED'});
    assert.equal(f.sent.length, 1);
    assert.equal(f.messages.filter(m=>m.type==='CHECKPOINT_STORY_IMAGE').length, 0);
  });
  await test('first scene without references establishes appearance from text', async () => {
    const f=fixture(); await f.run();
    assert(f.sent[0].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที จำนวนหนึ่งภาพแนวตั้ง 9:16 • ฉาก 1\n\nSTYLE: 2D anime'));
    assert(!/ภาพฉากก่อนหน้า|รูปอ้างอิง|อัปโหลด|แก้ไขภาพ/.test(f.sent[0].prompt));
    assert.equal(f.sent[0].urls.length,0);
    assert(f.sent[1].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที จำนวนหนึ่งภาพแนวตั้ง 9:16 • ฉาก 2'));
    assert(!/ภาพฉากก่อนหน้า|รูปอ้างอิง|อัปโหลด|แก้ไขภาพ/.test(f.sent[1].prompt));
    assert.equal(f.sent[0].storyContext.scene_index, 1);
    assert.equal(f.sent[1].storyContext.scene_index, 2);
    assert.equal(f.sent[1].storyContext.attempt, 1);
    assert(!f.sent[1].prompt.includes('นี่คือภาพฉากแรก'));
  });
  await test('provided original reference is not falsely called a previous scene', async () => {
    const f=fixture(); await f.context.generateOneImage('Doctor Doom raises a hand',['source-image'],2,'story');
    assert.deepEqual(f.sent[0].urls,['source-image']);
    assert(f.sent[0].prompt.includes('รูปอ้างอิงเป็นรูปหลักที่ผู้ใช้ให้ไว้'));
    assert(!f.sent[0].prompt.includes('ไม่มีไฟล์รูปอ้างอิงแนบ'));
    assert(f.sent[0].prompt.includes('ไม่ถือว่าเป็นภาพฉากก่อนหน้า'));
  });
  for(const response of [
    'กรุณาอัปโหลดหรือระบุภาพฉากก่อนหน้าที่ต้องใช้เป็นฐานความต่อเนื่อง แล้วผมจะสร้างภาพ 9:16 ฉากนี้ต่อจากภาพนั้นทันที',
    'โปรดแนบรูปอ้างอิงก่อน', 'รบกวนส่งภาพต้นฉบับให้ด้วย',
    'Please upload or specify the previous scene image, then I will generate it.',
    'Could you provide the reference image first?', 'I need the previous scene image before I can proceed.'
  ])await test(`reference request is terminal: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    await assert.rejects(f.run(),error=>error.code==='STORY_REFERENCE_REQUIRED'&&error.message.includes(response.slice(0,60)));
    assert.equal(f.sent.length,1);assert.equal(f.analysisRequests.length,0);
    assert(!f.reports.some(row=>row.step==='retrying_image'));
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'));
  });
  await test('policy takes priority over asking for another image',async()=>{
    const f=fixture([transient('This violates policy. Please upload another image.')]);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_REFUSED'});assert.equal(f.sent.length,1);
  });
  await test('reference acknowledgements and normal generation statements are not requests',async()=>{
    const f=fixture();
    for(const value of ['I received your uploaded reference image.','กำลังสร้างภาพจากรูปที่แนบมา','Please wait while I generate the image.','ภาพฉากก่อนหน้าใช้สีฟ้า','Image generation completed.'])assert.equal(f.context.storyImageReferenceRequest(value),false,value);
  });
  const declarativeReferenceResponses = [
    'ระบบสร้างภาพยังคงระบุคำขอนี้เป็นงานแก้ไขภาพเดิม และไม่อนุญาตให้สร้างต่อโดยไม่มีภาพเป้าหมาย แม้ข้อความของคุณจะระบุว่าเป็นภาพใหม่จากข้อความก็ตาม ในสถานะนี้ต้องมีภาพอ้างอิงหรือภาพเป้าหมายอยู่ในแชตก่อน จึงจะเรียกสร้างภาพต่อได้',
    'ในสถานะนี้ต้องมีภาพอ้างอิงหรือภาพเป้าหมายอยู่ในแชตก่อน จึงจะเรียกสร้างภาพต่อได้',
    'จำเป็นต้องมีรูปต้นฉบับก่อน จึงจะสร้างภาพต่อได้',
    'ระบบไม่อนุญาตให้สร้างต่อโดยไม่มีภาพเป้าหมาย',
    'A target image must be present in the chat before generation can continue.',
    'The system treats this as an image edit. A reference or target image must be uploaded before generation can continue.',
    'The reference image is still required before proceeding.',
    'The image tool cannot proceed without a reference image.'
  ];
  for(const response of declarativeReferenceResponses)await test(`declarative reference prerequisite stops after one image request: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    assert.equal(f.context.storyImageReferenceRequest(response),true);
    await assert.rejects(f.context.generateOneImage('Doctor Doom raises a hand',[],1,'story',0,'STYLE: anime'),
      error=>error.code==='STORY_REFERENCE_REQUIRED'&&error.message.startsWith('STORY_REFERENCE_REQUIRED'));
    assert.equal(f.sent.length,1);assert.equal(f.analysisRequests.length,0);
    assert(!f.reports.some(row=>row.step==='retrying_image'));
    assert.equal(f.messages.length,0);
  });
  await test('exact live declarative reference response halts full job without checkpointing or repair',async()=>{
    const f=fixture([transient(declarativeReferenceResponses[0])]);
    await assert.rejects(f.run(),{code:'STORY_REFERENCE_REQUIRED'});
    assert.equal(f.sent.length,1);assert.equal(f.analysisRequests.length,0);
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
    assert(f.reports.some(row=>row.step==='error'&&row.detail.error_code==='STORY_REFERENCE_REQUIRED'));
  });
  const resendTextResponses = [
    'ขออภัย ระบบสร้างภาพรอบนี้ตีความคำขอเป็นการแก้ไขภาพเดิมและต้องการภาพต้นฉบับ จึงยังสร้างภาพใหม่จากข้อความให้ไม่ได้ในรอบนี้ กรุณาส่งคำสั่งเดิมอีกครั้ง แล้วผมจะสร้างเป็นภาพใหม่แนวตั้ง 9:16 โดยไม่ใช้ภาพอ้างอิง',
    'กรุณาส่งคำสั่งเดิมอีกครั้ง แล้วผมจะสร้างเป็นภาพใหม่แนวตั้ง 9:16 โดยไม่ใช้ภาพอ้างอิง',
    'กรุณาส่งพรอมต์ใหม่ แล้วผมจะสร้างภาพให้',
    'Please send the prompt again, then I will generate a new image without a reference.',
    'Could you provide the original command again? I will create the image.',
    'Please send me the text again and I will create an image.'
  ];
  for(const response of resendTextResponses)await test(`resending text is not uploading an image: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    assert.equal(f.context.storyImageReferenceRequest(response),false);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_RESPONSE_REVIEW'});
    assert.equal(f.sent.length,1);assert.equal(f.analysisRequests.length,0);
    assert(!f.reports.some(row=>row.step==='retrying_image'));
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
  });
  for(const response of [
    'กรุณาส่งคำสั่งพร้อมภาพอ้างอิง',
    'กรุณาแนบภาพต้นฉบับแล้วส่งคำสั่งเพื่อสร้างภาพใหม่',
    'Please send the prompt along with the source image.',
    'Please upload the source image and send the prompt to create a new image.',
    'Please provide the text and attach a target image.',
    'กรุณาส่งคำสั่งเดิมอีกครั้ง แล้วผมจะสร้างภาพ แต่กรุณาแนบภาพต้นฉบับก่อน',
    'Please send the prompt again, then I will generate an image. A target image must be present before generation can continue.'
  ])await test(`a real image prerequisite survives a request for text: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    assert.equal(f.context.storyImageReferenceRequest(response),true);
    await assert.rejects(f.run(),{code:'STORY_REFERENCE_REQUIRED'});
    assert.equal(f.sent.length,1);assert(!f.reports.some(row=>row.step==='retrying_image'));
  });
  await test('policy priority survives the text-resend detector fix',async()=>{
    const f=fixture([transient(`This violates policy. ${resendTextResponses[0]}`)]);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_REFUSED'});
    assert.equal(f.sent.length,1);assert(!f.reports.some(row=>row.step==='retrying_image'));
  });
  for(const response of [
    'มีภาพอ้างอิงอยู่ในแชตแล้ว กำลังสร้างภาพใหม่ให้',
    'ระบบกำลังสร้างภาพต่อจากภาพเป้าหมายที่ได้รับแล้ว',
    'ไม่ต้องมีภาพอ้างอิงก่อน จึงจะสร้างภาพได้ กำลังสร้างจากข้อความ',
    'ไม่จำเป็นต้องมีภาพเป้าหมายในแชตก่อน จึงจะสร้างภาพนี้ได้',
    'The reference image is already in the chat. Generating the new scene now.',
    'The target image is available and generation is in progress.',
    'No reference image is required before generating.',
    'I do not need the previous scene image before I can proceed.',
    "I don't require the reference image before generating.",
    'There is no need for a source image before generating.'
  ])await test(`affirmative or in-progress reference text is not a missing-reference terminal: ${response}`,async()=>{
    const f=fixture();assert.equal(f.context.storyImageReferenceRequest(response),false);
  });
  for(const response of [
    'ไม่ใช่ว่าต้องมีภาพอ้างอิงก่อนจึงจะสร้างได้ กำลังสร้างจากข้อความให้',
    'It is not true that a target image must be present before generation can continue. I will generate it from text.',
    'It is not the case that the image tool cannot proceed without a reference image.',
    'Please do not upload a reference image.',
    "Please don't upload or provide another reference image.",
    'กรุณาอย่าอัปโหลดภาพอ้างอิงเพิ่ม'
  ])await test(`clause-scoped negation does not become a reference request: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    assert.equal(f.context.storyImageReferenceRequest(response),false);
    await assert.rejects(f.context.generateOneImage('Doctor Doom',[],1,'story'),{code:'STORY_IMAGE_RESPONSE_REVIEW'});
    assert.equal(f.sent.length,1);
  });
  for(const response of [
    'ไม่ใช่ว่าต้องมีภาพอ้างอิงก่อนจึงจะสร้างได้ แต่ต้องมีภาพเป้าหมายก่อนจึงจะสร้างต่อได้',
    'ไม่ใช่ว่าต้องมีภาพอ้างอิงก่อนจึงจะสร้างได้; ต้องมีรูปต้นฉบับก่อนจึงจะสร้างต่อได้',
    'It is not true that a target image must be present before generation can continue. A reference image is required before generating.',
    'It is not true that a target image must be present before generation can continue, but the source image must be uploaded before proceeding.',
    'Please do not upload a reference image. Please upload the target image instead.',
    'กรุณาอย่าอัปโหลดภาพอ้างอิงเก่า แต่กรุณาแนบภาพเป้าหมาย'
  ])await test(`a genuine later requirement survives a separate negation clause: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    assert.equal(f.context.storyImageReferenceRequest(response),true);
    await assert.rejects(f.context.generateOneImage('Doctor Doom',[],1,'story'),{code:'STORY_REFERENCE_REQUIRED'});
    assert.equal(f.sent.length,1);
  });
  await test('policy refusal still takes priority over a declarative reference prerequisite',async()=>{
    const f=fixture([transient(`This violates policy. ${declarativeReferenceResponses[0]}`)]);
    await assert.rejects(f.context.generateOneImage('Doctor Doom',[],1,'story'),{code:'STORY_IMAGE_REFUSED'});
    assert.equal(f.sent.length,1);assert(!f.reports.some(row=>row.step==='retrying_image'));
  });
  for(const response of [
    'The image request is in the queue. Please wait.',
    'ระบบกำลังประมวลผลคำขอภาพอยู่ กรุณารอสักครู่',
    'Temporary server error. Try again later.',
    'คำตอบที่ไม่ทราบประเภทและไม่มีไฟล์ภาพ'
  ])await test(`completed response without a confirmed image stops for review: ${response}`,async()=>{
    const f=fixture([transient(response)]);
    await assert.rejects(f.context.generateOneImage('Doctor Doom raises a hand',[],1,'story',0,'STYLE: anime'),{code:'STORY_IMAGE_RESPONSE_REVIEW'});
    assert.equal(f.sent.length,1);assert.equal(f.messages.length,0);
    assert(!f.reports.some(row=>row.step==='retrying_image'));
    const diagnostic=f.reports.find(row=>row.step==='image_attempt_result');
    assert.equal(diagnostic.detail.failure_category,'completed_no_image_response');
    assert.equal(diagnostic.detail.error_code,'CHATGPT_NO_IMAGE');
    assert.equal(diagnostic.detail.image_index,1);assert.equal(diagnostic.detail.attempt,1);
    assert.equal(diagnostic.detail.response_excerpt,response);
    assert(!diagnostic.message.includes('สร้างภาพไม่สำเร็จ'));
  });
  await test('whole job preserves checkpoint plan and stops on unclassified completed image response',async()=>{
    const f=fixture([transient('No image output was provided for this response.')]);
    await assert.rejects(f.run(),{code:'STORY_IMAGE_RESPONSE_REVIEW'});
    assert.equal(f.sent.length,1);assert.equal(f.analysisRequests.length,0);
    assert.equal(f.messages.filter(row=>row.type==='CHECKPOINT_STORY_ANALYSIS').length,1);
    assert(!f.messages.some(row=>row.type==='CHECKPOINT_STORY_IMAGE'||row.type==='SUBMIT_STORY_RESULT'));
    assert(f.reports.some(row=>row.step==='error'&&row.detail.error_code==='STORY_IMAGE_RESPONSE_REVIEW'));
  });
  await test('attempt diagnostics precede policy stop and bound provider text',async()=>{
    const f=fixture([transient(`policy ${'x'.repeat(2000)}`)]);
    await assert.rejects(f.context.generateOneImage('Doctor Doom',[],2,'story'),{code:'STORY_IMAGE_REFUSED'});
    assert.equal(f.sent.length,1);assert.equal(f.reports[0].step,'image_attempt_result');
    assert.equal(f.reports[0].detail.failure_category,'policy_refusal');
    assert.equal(f.reports[0].detail.response_excerpt.length,1200);
    assert(f.reports[0].message.length<600);
  });
  await test('existing silent and stalled branches retain exact first-scene intent on retry',async()=>{
    for(const code of ['CHATGPT_NO_RESPONSE','CHATGPT_IMAGE_STALLED']){
      const f=fixture([Object.assign(new Error(code),{code}),'image']);
      await f.context.generateOneImage('Doctor Doom raises a hand',[],1,'story',0,'STYLE: anime');
      assert.equal(f.sent.length,2);assert.equal(f.sent[0].prompt,f.sent[1].prompt);
      assert(f.sent[0].prompt.startsWith('สร้างภาพใหม่จากข้อความทันที'));
      assert(f.reports.findIndex(row=>row.step==='image_attempt_result')<f.reports.findIndex(row=>row.step==='retrying_image'));
    }
  });
  await test('empty scenery registry passes real validation and full run', async () => {
    const f = fixture(), result = analysis(), req = request(); result.story_entities = []; result.scene_entities = [[], []]; req.required_named_entities = [];
    result.scene_prompts = ['A river at dawn', 'A forest at sunset']; result.scene_narrations = ['แม่น้ำยามเช้า', 'ป่ายามเย็น']; result.visual_bible = { lighting: 'natural light' };
    await f.run(result, req); assert.equal(f.sent.length, 2); assert.equal(f.analysisRequests.length, 0);
  });
  await test('legacy absent metadata remains supported', async () => {
    const f = fixture(), result = analysis(), req = request(); delete result.story_entities; delete result.scene_entities; delete req.story_content_contract; delete req.required_named_entities;
    req.required_fields = ['scene_prompts', 'scene_narrations', 'visual_bible']; await f.run(result, req);
    assert(f.sent[0].prompt.includes('metal gauntlet') && f.sent[0].prompt.includes('cool blue'));
  });
  await test('legacy explicit malformed metadata is rejected', async () => {
    const f = fixture(), result = analysis(); result.story_entities = null; result.scene_entities = null;
    assert.throws(() => f.context.validateStoryContent(result, {}, 2), mismatch);
  });
  await test('new response mismatch bypasses JSON repair loop', async () => {
    const f = fixture(), result = analysis(); result.scene_prompts[0] = 'An unrelated king';
    await assert.rejects(f.context.parseOrRepairAnalysis({ innerText: JSON.stringify(result) }, { job: { id: 'STORY-TEST' }, request: request() }, 'scene_prompts', 2), mismatch);
    assert.equal(f.analysisRequests.length, 0);
  });
  await test('Story capability repair uses Story context', async () => {
    const f = fixture(); await f.context.parseOrRepairAnalysis({ innerText: 'ฉันเป็นเพียงโมเดลภาษา' }, { job: { id: 'STORY-TEST' }, request: request() }, 'scene_prompts', 2);
    assert.equal(f.analysisRequests.length, 1); assert(f.analysisRequests[0].includes('หัวข้อเรื่อง เนื้อเรื่อง บทเล่า'));
    assert(!f.analysisRequests[0].includes('ข้อมูลสินค้า')); assert(f.analysisRequests[0].includes('คง story_entities'));
    assert(!f.analysisRequests[0].includes('รูปอ้างอิงจากข้อความผู้ใช้ก่อนหน้า'));
  });
  await test('Story analysis policy refusal never rewrites', async () => {
    const f = fixture(); await assert.rejects(f.context.parseOrRepairAnalysis({ innerText: 'I cannot help due to policy' }, { job: { id: 'STORY-TEST' }, request: request() }, 'scene_prompts', 2), { code: 'STORY_IMAGE_REFUSED' });
    assert.equal(f.analysisRequests.length, 0);
  });
  const capabilityReply = 'ฉันไม่สามารถช่วยในเรื่องนี้ได้ เพราะเป็นแค่โมเดลภาษาและไม่เข้าใจคำถามนี้';
  await test('D379C1 completed capability variant reaches bounded JSON repair, not image refusal', async () => {
    const reply='Gemini บอกว่า\n\nฉันไม่สามารถช่วยในเรื่องนี้ได้ เพราะเป็นแค่โมเดลภาษา และไม่มีข้อมูลหรือความสามารถที่ใช้ตอบคำถามนั้น';
    const f=fixture();
    await f.context.parseOrRepairAnalysis({innerText:reply},{job:{id:'STORY-TEST'},request:request()},'scene_prompts',2);
    assert.equal(f.analysisRequests.length,1);
    for(const suffix of [' เพราะละเมิดนโยบายความรุนแรง',' third-party content']) {
      const negative=fixture();
      await assert.rejects(negative.context.parseOrRepairAnalysis({innerText:reply+suffix},{job:{id:'STORY-TEST'},request:request()},'scene_prompts',2),{code:'STORY_IMAGE_REFUSED'});
      assert.equal(negative.analysisRequests.length,0);
    }
    const other=fixture();other.context.IS_GEMINI=false;
    assert.equal(other.context.geminiAnalysisCapabilityOnly(reply),false);
  });
  for (const reply of [capabilityReply, `Gemini บอกว่า\n\n${capabilityReply}`, 'ฉันเป็นแค่โมเดลภาษา และคำถามนี้อยู่นอกเหนือความสามารถที่ออกแบบมาให้ฉันทำ']) {
    await test(`Gemini completed capability reply repairs original JSON: ${reply}`, async () => {
      const f = fixture();
      const result = await f.context.parseOrRepairAnalysis({innerText:reply}, {job:{id:'STORY-TEST'},request:request()}, 'scene_prompts', 2);
      assert.equal(f.analysisRequests.length, 1);
      assert(f.analysisRequests[0].includes('งานนี้เป็นงานเขียนข้อความ JSON เท่านั้น'));
      assert(f.analysisRequests[0].includes('คุณสามารถช่วยจัดทำคำตอบเป็นข้อความ JSON ได้'));
      assert(f.analysisRequests[0].includes('ผู้เชี่ยวชาญด้านการวิเคราะห์และจัดโครงสร้างข้อมูล'));
      assert(f.analysisRequests[0].includes('ไม่ต้องเริ่มเรื่องใหม่หรือแต่งข้อมูลเพิ่ม'));
      assert(f.analysisRequests[0].includes('STORY-TEST'));
      assert.equal(f.reports[0].step, 'retrying_analysis_after_refusal');
      assert.equal(result.video_title, analysis().video_title);
      assert.equal(f.sent.length, 0);
      // Image refusal detection itself must not be weakened.
      if (reply.includes('ฉันไม่สามารถช่วย')) assert(f.context.storyImageRefusal(reply));
    });
  }
  await test('Gemini mixed capability and policy still stops without retry', async () => {
    for (const reply of [capabilityReply+' เพราะละเมิดนโยบายความรุนแรง', 'ละเมิดนโยบาย '+capabilityReply, capabilityReply+' third-party content', 'ฉันไม่สามารถช่วยในเรื่องนี้ได้']) {
      const f=fixture();
      await assert.rejects(f.context.parseOrRepairAnalysis({innerText:reply}, {job:{id:'STORY-TEST'},request:request()}, 'scene_prompts', 2), {code:'STORY_IMAGE_REFUSED'});
      assert.equal(f.analysisRequests.length, 0);
    }
  });
  await test('ChatGPT refusal behavior stays unchanged', async () => {
    const f=fixture(); f.context.IS_GEMINI=false;
    await assert.rejects(f.context.parseOrRepairAnalysis({innerText:capabilityReply}, {job:{id:'STORY-TEST'},request:request()}, 'scene_prompts', 2), {code:'STORY_IMAGE_REFUSED'});
    assert.equal(f.analysisRequests.length, 0);
  });
  await test('Repeated capability replies retain two repair maximum', async () => {
    const f=fixture(); let sends=0;
    f.context.submitPrompt=async ()=>{sends++;return {innerText:capabilityReply};};
    await assert.rejects(f.context.parseOrRepairAnalysis({innerText:capabilityReply}, {job:{id:'STORY-TEST'},request:request()}, 'scene_prompts', 2), /2 รอบ/);
    assert.equal(sends, 2);
  });
  await test('Repair unconfirmed send propagates without another submission', async () => {
    const f=fixture(); let sends=0;
    f.context.submitPrompt=async ()=>{sends++;throw new Error('AI_SEND_UNCONFIRMED');};
    await assert.rejects(f.context.parseOrRepairAnalysis({innerText:capabilityReply}, {job:{id:'STORY-TEST'},request:request()}, 'scene_prompts', 2), /AI_SEND_UNCONFIRMED/);
    assert.equal(sends, 1);
  });
  await test('Product initial prompt is unchanged', async () => {
    const f = fixture(); await f.context.generateOneImage('Product scene', ['product-reference'], 1);
    assert.equal(f.sent.length, 1); assert(!f.sent[0].prompt.includes('STYLE:') && !f.sent[0].prompt.includes('เนื้อหาเรื่อง'));
    assert(f.sent[0].prompt.startsWith('สร้างภาพจริงจำนวนหนึ่งภาพทันที')); assert.deepEqual(f.sent[0].urls, ['product-reference']);
  });
  console.log(JSON.stringify({ ok: true, cases }));
})().catch(error => { console.error(error); process.exitCode = 1; });
