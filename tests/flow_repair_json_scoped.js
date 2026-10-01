const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const c={AI_NAME:'Gemini',IS_GEMINI:true,localJsonVariants:t=>[t],parseJsonObject:t=>JSON.parse(t)};
vm.createContext(c);vm.runInContext(
  source.slice(source.indexOf('  function chatGPTConversationFrames('),source.indexOf('  function assistantTurns('))
  +source.slice(source.indexOf('  function analysisAnswerNode('),source.indexOf('  function analysisResponseStopButton('))
  +source.slice(source.indexOf('  function extractJson('),source.indexOf('  function normaliseDialogueSpeakers(')),c);
const good={prompt:'9:16 one video with slow camera movement.',needs_review:false,reference_compatible:true,material_change:false};
for(const text of [JSON.stringify(good),'Here is the result:\n'+JSON.stringify(good)+'\nEnd.', '```json\n'+JSON.stringify(good)+'\n```'])assert.equal(c.extractJson({innerText:text},true).prompt,good.prompt);
const denied={...good,needs_review:true,reference_compatible:false};
assert.equal(c.extractJson({innerText:JSON.stringify(denied)},true).needs_review,true);
for(const text of [JSON.stringify({prompt:'no flags'}),JSON.stringify({...good,needs_review:'false'}),JSON.stringify(good)+'\n'+JSON.stringify(denied)])assert.throws(()=>c.extractJson({innerText:text},true));
assert.equal(c.extractJson({innerText:'{"job_id":"STORY-TEST"}'}).job_id,'STORY-TEST');
console.log('scoped repair JSON passed');
vm.runInContext(source.slice(source.indexOf('  function extractAlternativeJson('),source.indexOf('  async function runFlowAlternativeHelper(')),c);
// Live 418E25 scene3: both initial and formatting replies left Thai dialogue
// quotes unescaped. Only that exact persisted narration may repair syntax.
const line='กลับถึงบ้านก็วางเบาะชิ้นเดิมไว้ในมุมพักได้เลย น้องเดินมานอนต่อเองแบบคุ้นเคย ใช้ชิ้นเดียวต่อเนื่องตั้งแต่ออกจากบ้านจนกลับมาพักค่ะ';
const expected={...good,prompt:'Vertical 9:16. The reviewer speaks: "'+line+'" Add subtle breathing. All spoken dialogue must be in Thai only.',change_summary:'The dog rests in the new image.'};
const valid=JSON.stringify(expected);
const broken=valid.replaceAll('\\"','"');
assert.throws(()=>c.extractJson({innerText:broken},true));
for(const text of [broken,'```json\n'+broken+'\n```',valid]){
  assert.deepEqual(JSON.parse(JSON.stringify(c.extractAlternativeJson({innerText:text},line))),expected);
}
assert.throws(()=>c.extractAlternativeJson({innerText:broken},'คนละบทพูดกับภาพนี้'));
assert.throws(()=>c.extractAlternativeJson({innerText:broken},''));
assert.throws(()=>c.extractAlternativeJson({innerText:broken+'\n'+broken},line));
assert.throws(()=>c.extractAlternativeJson({innerText:broken.slice(0,-1)},line));
assert.throws(()=>c.extractAlternativeJson({innerText:broken.replace('false','"false"')},line));
const refused=broken.replace('"needs_review":false','"needs_review":true');
assert.equal(c.extractAlternativeJson({innerText:refused},line).needs_review,true);
const smart={...good,prompt:'Vertical 9:16. She says “สวัสดีค่ะ” and smiles.'};
assert.equal(c.extractJson({innerText:JSON.stringify(smart)},true).prompt,smart.prompt);
assert.throws(()=>c.extractAlternativeJson({innerText:valid+'\n'+JSON.stringify({...expected,needs_review:true})},line));
assert.ok(c.alternativeJsonInstructions().includes('JSON SERIALIZATION'));
console.log('exact alternate dialogue JSON recovery passed');
vm.runInContext(source.slice(source.indexOf('  async function runFlowAlternativeHelper('),source.indexOf('  async function runSceneRepairHelper(')),c);
(async()=>{
  for(const provider of ['chatgpt','gemini']){
    c.IS_GEMINI=provider==='gemini';
    const record={request_id:'saved-repair',provider,revise_story:true,alternative_stage:'motion_sent',
      proposal:{scene_narration:line},alternative_format_attempts:{motion:1},request:'saved format request'};
    let sends=0,images=0,ready=0;
    Object.assign(c,{
      location:{href:'https://example.test/owned-chat'},motionRequestIsLatestUser:()=>true,
      revealChatGPTAnswer:async()=>false, // DOM reveal is verified by result_readiness_392.cjs.
      stopButtonVisible:()=>false,latestAssistantStrictlyAfterLatestUser:()=>({innerText:broken}),
      sleep:async()=>{},assertNotCancelled:()=>{},submitPrompt:async()=>{sends++;throw Error('unexpected send');},
      submitImagePrompt:async()=>{images++;throw Error('unexpected image');},
      chrome:{runtime:{sendMessage:async message=>{
        assert.equal(message.action,'ready');assert.equal(message.candidate.prompt,expected.prompt);
        ready++;return {ok:true,replacement:{phase:'ready',image_url:'saved-new-image'}};
      }}}
    });
    await c.runFlowAlternativeHelper('key',record,true,async patch=>Object.assign(record,patch));
    assert.equal(record.phase,'ready');assert.equal(ready,1);assert.equal(sends,0);assert.equal(images,0);
    assert.equal(record.alternative_format_attempts.motion,1);
  }
  console.log('saved alternative resume: ready with 0 sends and 0 image regenerations');
})().catch(error=>{console.error(error);process.exitCode=1;});
