const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {setup,original,good,clone,phrase}=new Function('require','__dirname',
  fs.readFileSync(path.join(__dirname,'story_name_binding_harness.js'),'utf8').split('\n(async()=>')[0]
  +';return {setup,original,good,clone,phrase};')(require,__dirname);
function twoMissing(){
  const input=clone(original);
  input.scene_prompts[1]=input.scene_prompts[0]+' Scene two.';
  input.scene_entities[1]=clone(input.scene_entities[0]);
  return input;
}
const record=f=>Object.values(f.storage).find(row=>row?.version===1 && row.context);
const review={code:'STORY_CONTENT_MISMATCH'};
(async()=>{
  let cases=0;
  const test=async(name,run)=>{try{await run();cases++;}catch(e){e.message=name+': '+e.message;throw e;}};
  for(const provider of ['chatgpt','gemini']){
    await test('empty completed bindings are corrected before images '+provider,async()=>{
      const f=setup((prompt,n)=>n===1?{bindings:[]}:good(),original,provider);
      const result=await f.parse();assert.equal(f.prompts.length,2);
      assert.equal(result.story_content_name_repair.changes.length,1);assert.equal(f.images.length,0);
      assert(f.prompts[1].includes('ฉาก 1'));assert(f.prompts[1].includes('รอบที่ 1/2'));
      assert.notEqual(f.prompts[0],f.prompts[1]);assert.equal(record(f).attempts['1:third_signal'],1);
      assert(f.reports.some(row=>row[0]==='repairing_story_names'&&row[1].includes('รอบที่ 1/2')));
      for(const key of Object.keys(original))if(key!=='scene_prompts')assert.deepEqual(clone(result[key]),original[key]);
    });
    for(const reply of ['{broken', {}, {bindings:null}, {bindings:[null]}, {bindings:[{scene_index:1,entity_id:'third_signal'}]}]){
      await test('incomplete structure only asks for missing proof '+provider+JSON.stringify(reply),async()=>{
        const f=setup((prompt,n)=>n===1?reply:good(),original,provider);
        await f.parse();assert.equal(f.prompts.length,2);assert.equal(f.images.length,0);
      });
    }
    await test('partial response retained and asks only unresolved pair '+provider,async()=>{
      const f=setup((prompt,n)=>n===1?good():{bindings:[{...good().bindings[0],scene_index:2}]},twoMissing(),provider);
      const result=await f.parse();assert.equal(f.prompts.length,2);
      assert.equal(result.story_content_name_repair.changes.length,2);
      const targets=JSON.parse(f.prompts[1].split('\n').at(-1));assert.equal(targets.length,1);assert.equal(targets[0].scene_index,2);
      assert.deepEqual(record(f).attempts,{'1:third_signal':0,'2:third_signal':1});
    });
    await test('each missing pair has its own two attempts '+provider,async()=>{
      const f=setup((prompt,n)=>[1,2,4].includes(n)?{bindings:[]}:
        {bindings:[{...good().bindings[0],scene_index:n===3?1:2}]},twoMissing(),provider);
      await f.parse();assert.equal(f.prompts.length,5);
      assert.deepEqual(record(f).attempts,{'1:third_signal':2,'2:third_signal':2});
      assert.equal(new Set(f.prompts).size,5);
    });
    await test('empty answer never replenishes budget on same job retry '+provider,async()=>{
      const f=setup({bindings:[]},original,provider);
      await assert.rejects(f.parse(),e=>e.code===review.code&&e.message.includes('2 ครั้ง'));
      assert.equal(f.prompts.length,3);f.pkg.run_id='OTHER_RUN';
      await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,3);
      assert(!JSON.stringify(record(f)).includes(original.narration_script));
    });
    await test('unknown Send is never repeated on reentry '+provider,async()=>{
      const err=Object.assign(Error('uncertain'),{code:'AI_SEND_DISPATCHED_UNCONFIRMED'}),f=setup(err,original,provider);
      await assert.rejects(f.parse(),e=>e===err);assert.equal(record(f).phase,'pending');
      await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
    });
    await test('completed proof is revalidated without another request '+provider,async()=>{
      const f=setup((p,n)=>n===1?{bindings:[]}:good(),original,provider),a=await f.parse();
      const b=await f.parse();assert.deepEqual(clone(a),clone(b));assert.equal(f.prompts.length,2);
    });
    await test('same job new context cannot reuse or reset old receipt '+provider,async()=>{
      const f=setup(good(),original,provider);await f.parse();
      const changed=clone(original);changed.video_title+=' changed';
      await assert.rejects(f.parse(changed),review);assert.equal(f.prompts.length,1);
    });
    await test('real runJob waits for correction and desktop checkpoint before mock images '+provider,async()=>{
      const f=setup((prompt,n)=>n===2?{bindings:[]}:good(),original,provider);
      await f.context.runJob(f.pkg);assert.equal(f.prompts.length,3);assert.equal(f.images.length,10);
      const checkpoint=f.messages.findIndex(m=>m.type==='CHECKPOINT_STORY_ANALYSIS');
      assert(checkpoint>=0);assert(f.messages.findIndex(m=>m.type==='CHECKPOINT_STORY_IMAGE')>checkpoint);
    });
  }
  for(const [label,mutate] of [
    ['busy',f=>{f.page.busy=true;}],['user draft',f=>{f.page.draft='manual edit';}],
    ['wrong answer',f=>{f.page.answer='unrelated answer';}],['missing user',f=>{f.page.user='';}]
  ])await test('no first send with '+label,async()=>{
    const f=setup();mutate(f);await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,0);
  });
  for(const [label,mutate] of [
    ['busy',f=>{f.page.busy=true;}],['draft',f=>{f.page.draft='manual';}],
    ['owner',f=>{f.page.user='another question';}],['answer',f=>{f.page.answer='different answer';}],
    ['attachment',f=>{f.page.attachments.count=1;}],['upload',f=>{f.page.attachments.busy=true;}],
    ['failed upload',f=>{f.page.attachments.failed=true;}],
    ['chat',f=>{f.context.location.href='https://chatgpt.com/c/other';}],
    ['run',f=>{f.context.activeRunId='other';}],['job',f=>{f.context.activeJobId='other';}]
  ])await test('no supplementary send if '+label+' changes during backoff',async()=>{
    const f=setup({bindings:[]});f.context.sleep=async()=>mutate(f);
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  await test('cancel remains original error during backoff',async()=>{
    const f=setup({bindings:[]}),err=Object.assign(Error('cancel'),{code:'USER_CANCELLED'});
    f.context.sleep=async()=>{f.context.assertNotCancelled=()=>{throw err;};};
    await assert.rejects(f.parse(),e=>e===err);assert.equal(f.prompts.length,1);
  });
  await test('receipt claimed before press and tampering prevents Send',async()=>{
    const f=setup(),send=f.context.submitPrompt;
    f.context.submitPrompt=async(...args)=>{record(f).phase='review';return send(...args);};
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,0);
  });
  await test('storage failure before claim prevents provider call',async()=>{
    const f=setup(),err=Error('storage offline');f.context.chrome.storage.local.set=async()=>{throw err;};
    await assert.rejects(f.parse(),e=>e===err);assert.equal(f.prompts.length,0);
  });
  await test('response save failure keeps pending request and cannot resend',async()=>{
    const f=setup({bindings:[]}),set=f.context.chrome.storage.local.set;let writes=0;
    f.context.chrome.storage.local.set=async value=>{if(++writes===2)throw Error('save failed');return set(value);};
    await assert.rejects(f.parse(),/save failed/);assert.equal(record(f).phase,'pending');
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  await test('wrong owned request after response does not authorize next Send',async()=>{
    const f=setup({bindings:[]}),send=f.context.submitPrompt;
    f.context.submitPrompt=async(...args)=>{const turn=await send(...args);f.page.user='manual unrelated question';return turn;};
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  await test('simultaneous parser calls never send twice',async()=>{
    const f=setup();const outcomes=await Promise.allSettled([f.parse(),f.parse()]);
    assert.equal(outcomes.filter(x=>x.status==='fulfilled').length,1);assert.equal(f.prompts.length,1);
  });
  await test('partial proof survives interruption without reasking resolved item',async()=>{
    const f=setup((p,n)=>n===1?good():{bindings:[{...good().bindings[0],scene_index:2}]},twoMissing());
    const err=Object.assign(Error('cancel'),{code:'USER_CANCELLED'});f.context.sleep=async()=>{throw err;};
    await assert.rejects(f.parse(),e=>e===err);assert.equal(record(f).bindings.length,1);
    f.context.sleep=async()=>{};const result=await f.parse();assert.equal(f.prompts.length,2);
    assert.equal(result.story_content_name_repair.changes.length,2);
  });
  await test('incomplete row does not discard valid sibling',async()=>{
    const f=setup((p,n)=>n===1?{bindings:[...good().bindings,{scene_index:2,entity_id:'third_signal'}]}:
      {bindings:[{...good().bindings[0],scene_index:2}]},twoMissing());
    const result=await f.parse();assert.equal(f.prompts.length,2);assert.equal(result.story_content_name_repair.changes.length,2);
  });
  await test('foreign pair even with missing phrase remains conflict not repair',async()=>{
    const f=setup({bindings:[{scene_index:99,entity_id:'foreign'}]});
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  await test('tampered stored phrase is revalidated',async()=>{
    const f=setup();await f.parse();record(f).bindings[0].phrase='made up description';
    await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  for(const reply of ['This request violates our policies.','คำขอนี้ขัดต่อนโยบายการใช้งาน'])await test('explicit refusal never starts supplemental requests '+reply,async()=>{
    const f=setup(reply);await assert.rejects(f.parse(),review);assert.equal(f.prompts.length,1);
  });
  if(process.argv.includes('--emit')){
    const f=setup((p,n)=>n===1?good():{bindings:[{...good().bindings[0],scene_index:2}]},twoMissing());
    console.log(JSON.stringify({ok:true,cases,original:twoMissing(),repaired:await f.parse()}));
  }else console.log(JSON.stringify({ok:true,cases}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
