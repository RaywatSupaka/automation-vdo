// Real pre-Send audit functions, isolated from Chrome and the provider page.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const background=fs.readFileSync('browser_extension/background.js','utf8');
const slice=(source,start,end)=>{
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0 && b>a,start);
  return source.slice(a,b);
};
const record=slice(content,'  async function recordStoryImageRequest(','  function geminiImageSendState()');
const forward=slice(background,'async function forwardStoryImageAudit(','let progressOutboxFlushing=false;');

async function contentCase(name,replies,accepted) {
  const sent=[];
  const context=vm.createContext({
    JSON,Error,Promise,clearTimeout,setTimeout,
    aiWebFailureDiagnostic:()=>JSON.stringify({source_attachment_count:0,source_attachment_busy:false,
      source_attachment_failed:false,image_expansion_open:false,send_button_enabled:true}),
    composer:()=>({closest:()=>null}),composerText:()=>'',visible:()=>true,
    activeJobId:'STORY-AUDIT',activeRunId:'RUN-AUDIT',PROVIDER_KEY:'chatgpt',IS_GEMINI:false,
    location:{href:'https://chatgpt.com/c/owned'},assertNotCancelled:()=>{},
    chrome:{runtime:{sendMessage:async message=>{sent.push(message);return replies.shift();}}}
  });
  vm.runInContext(record,context);
  let result;
  try {await context.recordStoryImageRequest('owned prompt',[],{scene_index:1,attempt:1},0);result=true;}
  catch(error){result=error.code;}
  assert.equal(result,accepted?true:'STORY_IMAGE_AUDIT_UNCONFIRMED');
  assert.equal(sent.length,accepted?2:2);
  assert(sent.every(row=>row.progress.step==='image_prompt_ready'
    && row.progress.job_id==='STORY-AUDIT' && row.progress.run_id==='RUN-AUDIT'));
  process.stdout.write(`PASS ${name}\n`);
}

async function backgroundCase(name,payload,accepted) {
  let called=0;
  const context=vm.createContext({AbortController,setTimeout,clearTimeout,BRIDGE:'http://fixture',
    bridgeFetch:async()=>{called++;return {ok:true,json:async()=>payload};}});
  vm.runInContext(forward,context);
  const result=await context.forwardStoryImageAudit({job_id:'STORY-AUDIT',step:'image_prompt_ready'});
  assert.equal(result.audit_persisted,accepted);
  assert.equal(called,1);
  process.stdout.write(`PASS ${name}\n`);
}

(async()=>{
  await contentCase('buffered status is retried and cannot authorize Send',
    [{ok:true,buffered:true},{ok:true,buffered:true}],false);
  await contentCase('late durable ACK permits continued pre-Send checks',
    [{timeout:true},{ok:true,audit_persisted:true}],true);
  await contentCase('ignored audit stays pre-Send',
    [{ok:true,ignored:true},{ok:true,ignored:true}],false);
  await backgroundCase('Bridge fsync ACK is marked durable',{ok:true},true);
  await backgroundCase('Bridge ignored response is never durable',{ok:true,ignored:true},false);
})().catch(error=>{console.error(error);process.exitCode=1;});
