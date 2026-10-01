const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert(a>=0&&b>a);return source.slice(a,b);}
const functions=section('  function validateAnalysis(', '  async function validateOrRepairStoredAnalysis(');
let checks=0;
for(const provider of ['chatgpt','gemini']){
 const c=vm.createContext({AI_NAME:provider,normaliseDialogueSpeakers:r=>({...r,normalized:true}),validateStoryContent:()=>{}});
 vm.runInContext(functions,c);
 const base={video_title:'กุญแจ',narration_script:'เห็นกุญแจไหม อยู่ตรงนี้ไง',scene_prompts:['มะลิและต้นหน้าบ้าน','มะลิและต้นเดินออก'],
  scene_narrations:['ทั้งคู่ค้นกุญแจ','ทั้งคู่เดินออก'],scene_durations:[6,6],character_bible:[{name:'มะลิ'},{name:'ต้น'}],
  scene_dialogue_turns:[[{speaker:'มะลิ',listener:'ต้น',text:'เห็นกุญแจไหม'},{speaker:'ต้น',listener:'มะลิ',text:'อยู่ตรงนี้ไง'}],[]]};
 for(const mode of ['narrator','solo','dialogue','visual']){
  const good=structuredClone(base),request={storytelling_options:{version:1,mode,cta_enabled:false},storytelling_cast:['มะลิ','ต้น']};
  if(mode==='solo')good.scene_dialogue_turns[0]=[{speaker:'มะลิ',listener:'',text:'กุญแจอยู่ไหนเนี่ย'}];
  if(mode==='visual'){good.scene_dialogue_turns=[[],[]];good.narration_script='';good.dialogue_turns=[];}
  const result=c.validateAnalysis(good,'scene_prompts',2,['scene_narrations','scene_durations'],request.storytelling_cast,request);
  assert.equal(Boolean(result.normalized),mode==='narrator');checks++;
  if(mode!=='narrator'){
   for(const edit of [r=>r.character_bible[0].name='คนอื่น',r=>r.scene_dialogue_turns[0]=[{speaker:'ผู้บรรยาย',text:'เรื่องเล่า'}],
       r=>r.scene_durations[0]=Infinity,r=>r.scene_dialogue_turns[0]=[{speaker:'มะลิ',listener:'ต้น',text:'กดหัวใจให้ด้วย'}],
       r=>r.scene_dialogue_turns[0]=[{speaker:'มะลิ',listener:'ต้น',text:r.scene_narrations[0]}]]){
    const bad=structuredClone(good);edit(bad);assert.throws(()=>c.validateAnalysis(bad,'scene_prompts',2,[],[],request),/STORYTELLING_REVIEW/);checks++;
   }
  }
  const repair=c.storytellingRepairInstruction({request:{...request,storytelling_instruction:'DO NOT READ VISUAL BEATS. CTA OFF.'}});
  assert(repair.includes(mode)&&repair.includes('CTA OFF')&&repair.includes('มะลิ'));checks++;
 }
 const legacy=c.validateAnalysis(structuredClone(base),'scene_prompts',2,[],[],{});assert(legacy.normalized);checks++;
 assert.equal(c.storytellingRepairInstruction({request:{}}),'');checks++;
}
console.log(JSON.stringify({ok:true,checks,providers:2,networkRequests:0}));
