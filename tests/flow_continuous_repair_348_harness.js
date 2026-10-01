const fs=require('fs'),assert=require('assert/strict');
const setup=new Function('require','__dirname',fs.readFileSync('tests/flow_same_image_repair_346_harness.js','utf8').split('\n(async()=>')[0]+';return setup;')(require,__dirname);
(async()=>{
 for(const provider of ['chatgpt','gemini']){
  const f=await setup(provider),key='smartflowFlowRepair:STORY-TEST:1';
  for(let round=2;round<=5;round++){
   Object.assign(f.storage[key],{phase:'submitted',failure_id:`failure-${round-1}`});
   const next=await f.call({failure_id:`failure-${round}`});
   assert.equal(next.round,round);assert.equal(next.phase,'rewrite_sent');
   assert.equal(next.provider,provider);assert.equal(next.alternative,undefined);
   assert.equal(next.image_urls[0],'http://fixture/scene.png');
   await f.call({failure_id:`failure-${round}`});
   assert.equal(f.events.filter(x=>x==='open').length,round);
  }
  Object.assign(f.storage[key],{phase:'needs_review',round:2,exhausted:true,
    pause_reason:'ครบสองรอบซ่อมพรอมต์แล้ว ยังไม่ได้วิดีโอ'});
  const migrated=await f.call({failure_id:'legacy'});
  assert.equal(migrated.round,3);assert.equal(migrated.phase,'rewrite_sent');
  Object.assign(f.storage[key],{phase:'needs_review',exhausted:true,pause_reason:'reference requires review'});
  const opened=f.events.filter(x=>x==='open').length;
  assert.equal((await f.call({failure_id:'review'})).phase,'needs_review');
  assert.equal(f.events.filter(x=>x==='open').length,opened);
 }
 console.log('348 both providers: rounds3-5 continue, same image, helper dedup, budget-only migration; genuine review preserved');
})().catch(e=>{console.error(e);process.exitCode=1;});
