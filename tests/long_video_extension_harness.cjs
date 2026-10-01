'use strict';
// Executes the actual v2 chapter planner with synthetic completed AI answers.
// No Chrome tab, local bridge, paid provider, or customer job is contacted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const start = source.indexOf('  async function createLongVideoAnalysis(');
const end = source.indexOf('\n  async function runJob(', start);
assert(start >= 0 && end > start);
const actualFunction = source.slice(start, end);
const jobId = 'STORY-TEST-LONG';
const outline = {job_id:jobId,video_title:'สวนแห่งความทรงจำ',video_description:'เรื่องเล่าจากสวน',
  hashtags:['#สวนแห่งความทรงจำ','#เรื่องเล่า','#คลิปยาว'],
  visual_bible:'สวนไม้สีเขียว',story_entities:[],chapter_beats:['เปิดเรื่อง','พบปม','คลี่คลาย']};
const chapter = (index,count) => ({job_id:jobId,chapter_index:index,
  scene_prompts:Array.from({length:count},(_,n)=>`Landscape ${index}-${n+1}`),
  scene_narrations:Array.from({length:count},(_,n)=>`บทเล่าฉาก ${index}-${n+1}`),
  scene_durations:Array(count).fill(7),scene_entities:Array.from({length:count},()=>[]),
  story_entities:[],visual_bible:outline.visual_bible,continuity_summary:`จบชุด ${index}`});

async function scenario(saved, answers, imageCount = 23, aiResume = null, pendingAnswer = null) {
  const sends=[], checkpoints=[], reports=[], reads=[];
  const context={
    activeRunId:'RUN-TEST',PROVIDER_KEY:'chatgpt',
    assertNotCancelled:()=>{},
    report:async (...values)=>reports.push(values),
    submitPrompt:async (text,_images,_reference,_count,beforeSend)=>{
      if(beforeSend)await beforeSend();
      sends.push(text);return {json:answers.shift()};
    },
    readPendingAnalysis:async (_pkg,_field,count,validator)=>{
      reads.push(count);
      return validator?validator(pendingAnswer):pendingAnswer;
    },
    extractJson:turn=>turn.json,
    parseOrRepairAnalysis:async (turn,_pkg,_field,count)=>{
      assert.equal(turn.json.scene_prompts.length,count);
      return turn.json;
    },
    validateAnalysis:(result,_field,count)=>{
      assert.equal(result.scene_prompts.length,count);
      assert.equal(result.scene_narrations.length,count);
      return result;
    },
    explicitAnalysisRefusal:()=>false,storyImageRefusal:()=>false,
    chrome:{runtime:{sendMessage:async message=>{checkpoints.push(message);return {ok:true};}}}
  };
  vm.createContext(context);
  vm.runInContext(`${actualFunction}\nthis.runPlan=createLongVideoAnalysis;`,context);
  const pkg={job:{id:jobId,topic:'สวน',long_video:{version:2,duration_seconds:300}},
    prompt:'วางโครงเรื่องสวน',request:{required_fields:[]},long_video_plan:saved,ai_resume:aiResume};
  const result=await context.runPlan(pkg,imageCount);
  return {sends,checkpoints,reports,reads,result};
}

(async()=>{
  const first=await scenario({version:2,job_id:jobId,outline:null,chapters:[]},
    [outline,chapter(1,10),chapter(2,10),chapter(3,3)]);
  assert.equal(first.sends.length,4);
  assert.equal(first.checkpoints.length,8);
  assert.deepEqual(first.checkpoints.map(row=>row.pending_request?.stage||'saved'),
    ['outline','saved','chapter','saved','chapter','saved','chapter','saved']);
  assert(first.checkpoints.filter(row=>row.pending_request).every(row=>row.pending_request.request.includes(`job_id=${jobId}`)));
  assert(first.checkpoints.filter(row=>row.clear_pending).length===4);
  assert.equal(first.result.scene_prompts.length,23);
  assert.equal(first.result.scene_narrations.length,23);
  assert.deepEqual(Array.from(first.result.hashtags),outline.hashtags);
  assert(first.sends.every(text=>/คำตอบเดียว|คำตอบ JSON ชุดเดียว/.test(text)));
  const repaired=await scenario({version:2,job_id:jobId,outline:null,chapters:[]},
    [{job_id:jobId,video_title:'คำตอบยังไม่ครบ'},outline,chapter(1,10),chapter(2,10),chapter(3,3)]);
  assert.equal(repaired.sends.length,5);
  assert.match(repaired.sends[1],/hashtags \(array 3–6 คำ\)/);
  assert.match(repaired.sends[1],/คำอธิบายพร้อมโพสต์/);
  assert.deepEqual(Array.from(repaired.result.hashtags),outline.hashtags);
  const resumed=await scenario({version:2,job_id:jobId,outline,chapters:[chapter(1,10),chapter(2,10)]},
    [chapter(3,3)]);
  assert.equal(resumed.sends.length,1);
  assert.equal(resumed.checkpoints.length,2);
  assert.equal(resumed.checkpoints[0].pending_request.chapter_index,3);
  assert.equal(resumed.checkpoints[1].chapter_index,3);
  assert.equal(resumed.result.scene_prompts.length,23);
  const oldOutline={...outline};delete oldOutline.hashtags;
  const oldPlan=await scenario({version:2,job_id:jobId,outline:oldOutline,chapters:[chapter(1,10),chapter(2,10)]},
    [chapter(3,3)]);
  assert.deepEqual(Array.from(oldPlan.result.hashtags),[]);
  const pendingChapter=await scenario({version:2,job_id:jobId,outline,chapters:[chapter(1,10),chapter(2,10)]},
    [],23,{required:true,stage:'analysis',evidence:'long_video_plan',long_video_stage:'chapter',chapter_index:3},chapter(3,3));
  assert.equal(pendingChapter.sends.length,0);
  assert.deepEqual(pendingChapter.reads,[3]);
  assert.equal(pendingChapter.checkpoints[0].clear_pending,true);
  const pendingOutline=await scenario({version:2,job_id:jobId,outline:null,chapters:[]},
    [chapter(1,10),chapter(2,10),chapter(3,3)],23,
    {required:true,stage:'analysis',evidence:'long_video_plan',long_video_stage:'outline',chapter_index:0},outline);
  assert.equal(pendingOutline.sends.length,3);
  assert.deepEqual(pendingOutline.reads,[23]);
  await assert.rejects(scenario({version:2,job_id:jobId,outline,chapters:[chapter(1,10)]},
    [],23,{required:true,stage:'analysis',evidence:'job_trace',long_video_stage:'chapter',chapter_index:2},chapter(2,10)),
    /LONG_VIDEO_RESUME_REVIEW/);
  const outline50={...outline,chapter_beats:['เปิดเรื่อง','เริ่มเดินทาง','พบปม','ใกล้คำตอบ','บทสรุป']};
  const fifty=await scenario({version:2,job_id:jobId,outline:null,chapters:[]},
    [outline50,chapter(1,10),chapter(2,10),chapter(3,10),chapter(4,10),chapter(5,10)],50);
  assert.equal(fifty.sends.length,6);
  assert.equal(fifty.checkpoints.length,12);
  assert.equal(fifty.result.scene_prompts.length,50);
  assert(fifty.sends.every(text=>/คำตอบเดียว|คำตอบ JSON ชุดเดียว/.test(text)));
  const resumeBranch=source.indexOf("if (mode === 'story' && pkg.job?.long_video?.version === 2 && !pkg.analysis_checkpoint)");
  const legacyBranch=source.indexOf("if (pkg.reuse_analysis && pkg.ai_resume?.stage === 'analysis')",resumeBranch);
  assert(resumeBranch>0 && legacyBranch>resumeBranch);
  const helperStart=source.indexOf("      const compactLongImages =");
  const helperEnd=source.indexOf("      const storyImageFallbacks",helperStart);
  assert(helperStart>=0 && helperEnd>helperStart);
  const compact=await vm.runInNewContext(`(async()=>{
    const mode='story', pkg={job:{long_video:{version:2}}}, generatedImages=Array(50).fill(null);
    ${source.slice(helperStart,helperEnd)}
    await rememberSavedImage(0,'data:image/png;base64,AA==');
    return {marker:generatedImages[0], duplicate:await alreadyUsedImage('data:image/png;base64,AA=='),
      distinct:await alreadyUsedImage('data:image/png;base64,AQ=='), keptBytes:generatedImages.join('').includes('base64')};
  })()`,{crypto:webcrypto,TextEncoder});
  assert.equal(compact.marker,'checkpoint:1');
  assert.equal(compact.duplicate,true);
  assert.equal(compact.distinct,false);
  assert.equal(compact.keptBytes,false);
  console.log('PASS v2 23-image resume and 50 images in five 10-scene chapters with one-answer prompts');
})().catch(error=>{console.error(error);process.exitCode=1;});
