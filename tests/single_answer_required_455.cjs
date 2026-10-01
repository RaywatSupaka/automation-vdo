const assert = require('assert/strict'), fs = require('fs'), vm = require('vm');
const source = fs.readFileSync('browser_extension/chatgpt.js', 'utf8');
const ruleSource = fs.readFileSync('browser_extension/single_answer.js', 'utf8');
const part = (a,b) => source.slice(source.indexOf(a), source.indexOf(b, source.indexOf(a)));
async function writer(restore, mutate='') {
  let value = '', writes = 0, recoveries = 0;
  class Textarea { set value(v) { value=v; writes++; } get value() { return value; } focus(){} dispatchEvent(){} }
  const editor = new Textarea();
  const sandbox = {HTMLTextAreaElement:Textarea, InputEvent:class{}, Event:class{}, IS_GEMINI:false,
    composer:()=>editor,sleep:async()=>{},chrome:{runtime:{sendMessage:async m=>{
      assert.equal(m.type,'ENSURE_AI_RESPONSE_FORMAT');recoveries++;
      if(restore)vm.runInContext(ruleSource,context);
      if(mutate==='draft')editor.value='manual user draft';
      if(mutate==='owner')context.activeJobId='new-job';
      if(mutate==='busy')context.stopButtonVisible=()=>true;
      if(mutate==='remount')context.composer=()=>new Textarea();
      return {ok:restore};
    }}}};
  const context=vm.createContext(sandbox);
  vm.runInContext(part('  async function setComposerText(', '  async function sourceFile('),context);
  let error;try{await context.setComposerText(editor,'Return all 10 scenes as one JSON value.');}catch(e){error=e;}
  return {value,writes,recoveries,error,context};
}
(async()=>{
  const missing=await writer(false);
  assert(missing.error,'Missing response-format helper must never write a raw prompt');
  assert.equal(missing.writes,0);assert.equal(missing.recoveries,1);
  const recovered=await writer(true);
  assert.equal(recovered.error,undefined);assert.equal(recovered.recoveries,1);
  assert(recovered.context.SmartFlowSingleAnswer.has(recovered.value));
  assert.equal(recovered.context.SmartFlowSingleAnswer.canonical(recovered.value),'Return all 10 scenes as one JSON value.');
  assert.equal(recovered.context.SmartFlowSingleAnswer.wrap(recovered.value),recovered.value);
  for(const mutate of ['draft','owner','busy','remount']){
    const raced=await writer(true,mutate);
    assert.match(raced.error?.message||'',/AI_RESPONSE_FORMAT_CONTEXT_CHANGED/);
    assert.equal(raced.writes,mutate==='draft'?1:0,'Only simulated user input may change the draft');
    if(mutate==='draft')assert.equal(raced.value,'manual user draft');
  }
  const bg=fs.readFileSync('browser_extension/background.js','utf8');
  const start=bg.indexOf("if (message?.type === 'ENSURE_AI_RESPONSE_FORMAT')");
  assert(start>=0);
  const handler=bg.slice(start,bg.indexOf('    const pausedMutationTypes',start));
  let target,answer;
  const context=vm.createContext({message:{type:'ENSURE_AI_RESPONSE_FORMAT'},sender:{documentId:'doc-owned',tab:{id:7,url:'https://chatgpt.com/'}},
    chrome:{scripting:{executeScript:async args=>{target=args;return[];}}},sendResponse:value=>answer=value});
  await vm.runInContext(`(async()=>{${handler}})()`,context);
  assert.equal(answer.ok,true);assert.deepEqual(JSON.parse(JSON.stringify(target.target)),{tabId:7,documentIds:['doc-owned']});
  assert.deepEqual(JSON.parse(JSON.stringify(target.files)),['single_answer.js']);
  context.sender.documentId='';target=null;
  await assert.rejects(vm.runInContext(`(async()=>{${handler}})()`,context));assert.equal(target,null);
  context.sender.documentId='doc-owned';context.sender.tab.url='https://example.org/';
  await assert.rejects(vm.runInContext(`(async()=>{${handler}})()`,context));assert.equal(target,null);
  const {fixture}=require('./ai_send_acceptance_harness');
  const raw=fixture({acceptImmediately:true});
  await assert.rejects(raw.frontend.sendAndVerify(raw.state.button,raw.originalEditor,1,'existing-user-turn',1),
    error=>error.notDispatched===true && error.code==='AI_SEND_NOT_READY');
  assert.equal(raw.sends(),0);assert.equal(raw.commands.length,0,'Raw draft never reaches a trusted gesture');
  console.log('455 required response-format helper: missing/recover/idempotence/document/host guards passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
