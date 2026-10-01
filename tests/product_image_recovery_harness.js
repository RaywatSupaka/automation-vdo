const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
function fixture(options={}) {
  let state={revision:'rev',slots:{'1':{status:'missing',attempts:0},'2':{status:'missing',attempts:0},'3':{status:'missing',attempts:0}}};
  if(options.pending)state.slots['1'].status='reserved';
  const calls=[], reports=[], finishes=[];let currentIndex=0,downloads=0;
  const context=vm.createContext({activeJobId:'JOB-TEST',activeRunId:'RUN-1',PROVIDER_KEY:options.gemini?'gemini':'chatgpt',IS_GEMINI:!!options.gemini,
    crypto:{randomUUID:()=>String(calls.length)},assertNotCancelled:()=>{},sleep:async()=>{},
    thirdPartyContentFailure:text=>/บุคคลที่สาม|third.party/i.test(text),
    report:async(...args)=>reports.push(args),imageDataFromUrl:async(url)=>url,
    submitImagePrompt:async(prompt,refs,count,strict,context,geminiIndex)=>{
      calls.push({index:currentIndex,prompt,refs,strict,geminiIndex});
      const error=options.fail?.(currentIndex,calls.filter(c=>c.index===currentIndex).length);
      if(error)throw Object.assign(new Error(error.text||'failed'),{code:error.code||'CHATGPT_NO_IMAGE',responseText:error.text||'สร้างภาพไม่สำเร็จ'});
      return 'image-'+currentIndex;
    },
    imageData:async(image)=>{downloads++;if(options.downloadFails)throw new Error('download failed');return image;},
    chrome:{runtime:{sendMessage:async(message)=>{
      if(message.operation==='start')return{ok:true,state:JSON.parse(JSON.stringify(state))};
      const slot=state.slots[String(message.index)];
      if(message.operation==='reserve'){
        assert(['missing','failed'].includes(slot.status));assert(slot.attempts<2);
        currentIndex=message.index;slot.attempts++;slot.status='reserved';slot.donor_index=message.donor_index;
        return{ok:true,token:'token',attempt:slot.attempts};
      }
      finishes.push(message.outcome);
      slot.status=options.duplicate&&message.index===3&&message.outcome==='succeeded'?'failed':message.outcome;
      return{ok:true,state:JSON.parse(JSON.stringify(state))};
    }}}
  });
  vm.runInContext(section('  function productImageFailureKind(', '  async function runJob('), context);
  const pkg={image_urls:['http://127.0.0.1:8765/api/jobs/JOB-TEST/files/original/one.png']};
  return{calls,reports,finishes,downloads:()=>downloads,run:()=>context.runProductImages(pkg,{image_prompts:['scene-one','scene-two','scene-three']})};
}

function attachmentFixture({gemini=false,old=false,prove=true,count=1,limit=3,strict=true}={}){
  let time=0,attached=false,uploads=0;const names=[];
  const node={getAttribute:()=>''};const shell={contains:()=>attached||old,querySelector:()=>null,querySelectorAll:selector=>selector.startsWith('img[')&&(attached||old)?[node]:[],get textContent(){return attached&&prove?'smartpost-recovery-3-from-2':'';}};
  const input={dispatchEvent:()=>{attached=true;uploads++;},files:[]};
  function Input(){};Object.defineProperty(Input.prototype,'files',{set(value){this.files=value;}});
  const context=vm.createContext({activeCoverRequest:null,activeSourceReferenceLimit:limit,IS_GEMINI:gemini,AI_NAME:'AI',report:async()=>{},composer:()=>({closest:()=>shell}),
    sourceAttachmentPreviews:()=>attached||old?[node]:[],chatGPTComposerAttachmentState:()=>({count:old?1:0}),
    document:{querySelectorAll:()=>[]},preferredSourceFileInput:()=>input,userTurns:()=>[{}],
    sourceFile:async(url,index,name)=>{names.push(url);return{name,url};},DataTransfer:class{constructor(){this.files=[];this.items={add:file=>this.files.push(file)}}},
    HTMLInputElement:Input,Event:class{},sleep:async(ms)=>time+=ms,Date:{now:()=>time},
    waitForChatGPTSourceAttachmentProof:async()=>({count}),visible:()=>true,assertNotCancelled:()=>{}});
  vm.runInContext(section('  async function attachSourceImages(', '  function aiWebFailureDiagnostic('), context);
  return{uploads:()=>uploads,names:()=>names,run:()=>context.attachSourceImages(
    Array.from({length:count},(_,i)=>`reference-${i+1}`),2,strict?'smartpost-recovery-3-from-2':'')};
}
(async()=>{
  const normal=fixture();await normal.run();assert.deepEqual(normal.calls.map(c=>c.index),[1,2,3]);assert(normal.calls.every(c=>!c.strict));
  const third=fixture({fail:(i,n)=>i===3&&n===1?{}:null});await third.run();assert.deepEqual(third.calls.map(c=>c.index),[1,2,3,3]);
  assert(third.calls[3].refs[0].endsWith('selling_image_02.png'));assert(third.calls[3].prompt.includes('scene-three'));assert.equal(third.calls[3].strict,'smartpost-recovery-3-from-2');
  const first=fixture({fail:(i,n)=>i===1&&n===1?{}:null});await first.run();assert.deepEqual(first.calls.map(c=>c.index),[1,2,3,1]);
  const geminiFirst=fixture({gemini:true,fail:(i,n)=>i===1&&n===1?{}:null});await geminiFirst.run();assert.deepEqual(geminiFirst.calls.map(c=>c.geminiIndex),[1,2,3,1]);
  const all=fixture({fail:()=>({})});await assert.rejects(all.run(),/RECOVERY_STOP/);assert.equal(all.calls.length,3);
  const policy=fixture({fail:()=>({text:'อาจละเมิดกฎบุคคลที่สาม'})});await assert.rejects(policy.run(),/RECOVERY_STOP/);assert.equal(policy.calls.length,1);assert.equal(policy.finishes[0],'policy_blocked');
  const uncertain=fixture({fail:()=>({code:'CHATGPT_NO_RESPONSE',text:'no response'})});await assert.rejects(uncertain.run(),/RECOVERY_STOP/);assert.equal(uncertain.calls.length,1);
  for(const text of ['ฉันไม่สามารถช่วยในเรื่องนี้ได้','credit limit exceeded','please sign in']){
    const blocked=fixture({fail:()=>({text})});await assert.rejects(blocked.run(),/RECOVERY_STOP/);assert.equal(blocked.calls.length,1);assert.equal(blocked.finishes[0],'blocked');
  }
  const pending=fixture({pending:true});await assert.rejects(pending.run(),/RECOVERY_STOP/);assert.equal(pending.calls.length,0);
  const download=fixture({downloadFails:true});await assert.rejects(download.run(),/RECOVERY_STOP/);assert.equal(download.calls.length,1);assert.equal(download.downloads(),10);assert.equal(download.finishes[0],'download_pending');
  const duplicate=fixture({duplicate:true});await assert.rejects(duplicate.run(),/RECOVERY_STOP/);assert.equal(duplicate.calls.length,4);
  for(const gemini of [false,true]){const a=attachmentFixture({gemini});await a.run();assert.equal(a.uploads(),2);}
  const old=attachmentFixture({old:true});await assert.rejects(old.run(),/REFERENCE_UNCONFIRMED/);assert.equal(old.uploads(),0);
  const missing=attachmentFixture({prove:false});await assert.rejects(missing.run(),/REFERENCE_UNCONFIRMED/);assert.equal(missing.uploads(),2);
  const wardrobe=attachmentFixture({count:4,limit:4,strict:false});await wardrobe.run();
  assert.deepEqual(wardrobe.names(),['reference-1','reference-2','reference-3','reference-4']);
  const legacy=attachmentFixture({count:4,limit:3,strict:false});await legacy.run();assert.equal(legacy.names().length,3);
  const contaminated=attachmentFixture({count:4,limit:4,strict:false,old:true});
  await assert.rejects(contaminated.run(),/REFERENCE_UNCONFIRMED/);assert.equal(contaminated.names().length,0);
  process.stdout.write(JSON.stringify({ok:true,cases:20}));
})().catch(error=>{console.error(error);process.exitCode=1;});
