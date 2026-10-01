const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(process.env.SMARTFLOW_TEST_SOURCE || path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const prior = fs.readFileSync(path.join(__dirname, 'ai_analysis_completion_harness.js'), 'utf8');
// Reuse the established synthetic DOM/clock, NOT its test expectations. The
// factory extracts the current real submitPrompt/parser/turn-discovery code.
const responseFixture = vm.runInNewContext(prior.slice(0, prior.indexOf('async function tests()')) + '\nfixture;',
  { require:name=>name==='node:fs'?{...fs,readFileSync:(file,...args)=>String(file).replace(/\\/g,'/').endsWith('browser_extension/chatgpt.js')
      ? source:fs.readFileSync(file,...args)}:require(name), __dirname });
function section(start, end) {
  const first = source.indexOf(start), last = source.indexOf(end, first + start.length);
  assert(first >= 0 && last > first, start);
  return source.slice(first, last);
}
const owned = {job_id:'STORY-344-FIXTURE', index:10, context_id:'context-scene-ten'};
const motion = {...owned,
  prompt:'Vertical 9:16, one video. The traveler looks back once, turns on the path, and walks away from the city. The camera stays beside the path. All spoken dialogue must be in Thai only.',
  needs_review:false, reference_compatible:true, material_change:false,
  review_reason:'A natural turn preserves the departure event and uses the image as the starting frame.'};
const prefix = '{\n"job_id":_';
const full = JSON.stringify(motion, null, 2);
const plain = value => JSON.parse(JSON.stringify(value));

function completionActions(turn) {
  const copy = {innerText:'Copy', textContent:'Copy', getAttribute:key=>key==='aria-label'?'Copy response':null,
    getBoundingClientRect:()=>({width:30,height:30}), matches:()=>true};
  const scope = {querySelectorAll:()=>[copy], querySelector:selector=>selector.includes('aria-busy')?null:copy,
    get innerText(){return turn.innerText;}, get textContent(){return turn.textContent;}};
  turn.closest=()=>scope;
  return scope;
}

function resumeFixture(options={}) {
  const provider=options.provider||options.packet?.provider||'chatgpt';
  const context = options.packet?.context || {...owned, aspect_ratio:'9:16', image_url:'http://fixture.invalid/scene.png'};
  const request = options.packet?.request || 'Write motion JSON for the same reference scene. '+JSON.stringify(context);
  const result = options.packet?.result || motion;
  const messages=[], reports=[];
  let clock=1000, reads=0, sends=0;
  let record=options.packet?.record || {phase:'answered_text',request,answer_text:prefix,story_visual_revision:1};
  const answer={get innerText(){reads++;return options.content?.(clock-1000)||JSON.stringify(result);},
    get textContent(){return this.innerText;},querySelector:()=>null,querySelectorAll:()=>[]};
  const body={innerText:request,textContent:request,querySelectorAll:()=>[],querySelector:()=>null};
  const user={innerText:request+(options.collapsed?'\nดูเพิ่มเติม':''),textContent:request+(options.collapsed?'\nดูเพิ่มเติม':''),
    querySelector:()=>body,querySelectorAll:()=>[],cloneNode:()=>({innerText:request,textContent:request,
      querySelectorAll:selector=>selector==='button,[role="button"],img'?[{remove(){}}]:[]})};
  const c=vm.createContext({activeRunId:'RUN-344',activeJobId:context.job_id,PROVIDER_KEY:provider,
    AI_NAME:provider==='gemini'?'Gemini Web':'ChatGPT Web',IS_GEMINI:provider==='gemini',
    Date:{now:()=>clock},location:{href:provider==='gemini'?'https://gemini.google.com/app/0123456789abcdef':'https://chatgpt.com/c/344-fixture'},
    Node:{DOCUMENT_POSITION_FOLLOWING:4},getComputedStyle:()=>({display:'block',visibility:'visible'}),
    document:{querySelector:()=>null,querySelectorAll:()=>[]},
    userTurns:()=>[{...user,innerText:options.wrongOwner?'other request':user.innerText,
      textContent:options.wrongOwner?'other request':user.textContent,
      cloneNode:()=>options.wrongOwner?{innerText:'other request',textContent:'other request',querySelectorAll:()=>[]}:user.cloneNode(),
      querySelector:()=>options.wrongOwner?{innerText:'other request',textContent:'other request'}:body}],
    assistantTurns:()=>[answer],latestAssistantStrictlyAfterLatestUser:()=>answer,
    analysisAnswerNode:x=>x,analysisResponseStopButton:()=>options.stop?.(clock-1000)?{}:null,
    stopButtonVisible:()=>options.stop?.(clock-1000)||false,
    analysisContentHash:text=>String(text.length),analysisStopLabel:()=>'',
    geminiTextSendKey:async()=> 'legacy-344',readGeminiTextSend:async()=>null,
    explicitAnalysisRefusal:()=>false,explicitImageFailure:()=>false,
    revealChatGPTAnswer:async()=>false,refreshPendingChatGPTMotion:async()=>{}, // Dedicated392/396 DOM contracts.
    report:async(...args)=>reports.push(args),sleep:async ms=>{clock+=ms;},
    assertNotCancelled:()=>{if(clock-1000>=(options.cancelAt??1000000)){const e=Error('Cancelled');e.name='AbortError';throw e;}},
    submitPrompt:async()=>{sends++;throw Error('Unexpected new Send during passive Resume');},
    chrome:{runtime:{sendMessage:async message=>{
      messages.push(plain(message));
      if(message.action==='status')return {ok:true,context,record};
      if(message.action==='prepare')return {ok:true,context,record,claimed:false};
      if(message.action==='review_text'){record={...record,phase:'answered_text',answer_text:message.answer_text};
        return {ok:true,context,record,validation:{errors:['JSON อ่านไม่ได้'],repairable:false}};}
      if(message.action==='review'){
        assert.deepEqual(plain(message.result),plain(result),'Only the complete owned result may be reviewed');
        record={...record,phase:'answered',result:message.result};return {ok:true,context,record,validation:{errors:[],repairable:false}};
      }
      if(message.action==='save'){record={...record,phase:'ready',prompt:message.result.prompt};return {ok:true,context,record};}
      throw Error('Unexpected action '+message.action);
    }}}
  });
  vm.runInContext(section('  function chatGPTConversationFrames(', '  function assistantTurns('),c);
  vm.runInContext(section('  function visible(', '  function statusBanner('),c);
  vm.runInContext(section('  function motionRequestIsLatestUser(', '  async function sendAndVerify('),c);
  vm.runInContext(section('  function stableOwnedMotionAnswer(', '  async function submitPrompt('),c);
  vm.runInContext(section('  function analysisAnswerNode(', '  function normaliseDialogueSpeakers('),c);
  // The real selection is still invoked; synthetic answer has no nested body.
  vm.runInContext(section('  async function prepareFlowMotionPlan(', '  function sceneRepairRequest('),c);
  if(options.completed)completionActions(answer);
  return {c,messages,reports,answer,run:()=>c.prepareFlowMotionPlan({job:{id:context.job_id}},{},context.index,10),
    snapshot:()=>({elapsed:clock-1000,reads,sends,record:plain(record)})};
}

async function tests(){
  const passed=[],failures=[];
  const test=async(name,run)=>{try{await run();passed.push(name);}catch(e){failures.push({name,error:e.message});}};
  await test('actual submitPrompt waits through the observed 30s Stop / 40s partial prefix',async()=>{
    const f=responseFixture({motionContext:owned,content:ms=>ms<40000?prefix:full,stop:ms=>ms<30000,cancelAt:90000});
    const answer=await f.run();assert.deepEqual(plain(f.context.extractJson(answer)),motion);
    assert(f.elapsed()>=40000,'A 2.2-second prefix pause must not be completion');f.checkSingleSend();
  });
  await test('actual submitPrompt does not impose a six-minute limit on unclosed motion JSON',async()=>{
    const f=responseFixture({motionContext:owned,content:ms=>ms<450000?prefix:full,cancelAt:480000});
    assert.deepEqual(plain(f.context.extractJson(await f.run())),motion);assert(f.elapsed()>=450000);f.checkSingleSend();
  });
  await test('review_reason eighth field survives full-motion stale Stop recovery',async()=>{
    const f=responseFixture({motionContext:owned,content:()=>full+'_',stop:()=>true,cancelAt:70000});
    assert.deepEqual(plain(f.context.extractJson(await f.run())),motion);assert.equal(f.elapsed(),60000);f.checkSingleSend();
  });
  await test('cancel while partial never produces a parse error or another Send',async()=>{
    const f=responseFixture({motionContext:owned,content:()=>prefix,cancelAt:45000});
    await assert.rejects(f.run(),{name:'AbortError'});f.checkSingleSend();
  });
  await test('still-generating partial response remains waiting beyond six minutes',async()=>{
    const f=responseFixture({motionContext:owned,content:()=>prefix,stop:()=>true,cancelAt:450000});
    await assert.rejects(f.run(),{name:'AbortError'});assert(f.elapsed()>=450000);f.checkSingleSend();
  });
  await test('motion parser accepts unfenced prompt-first object without key-order dependency',async()=>{
    const f=responseFixture({motionContext:owned});const value={prompt:motion.prompt,...motion};
    const parse=f.context.extractMotionJson||f.context.extractJson;
    assert.deepEqual(plain(parse({innerText:'Here is the motion result:\n'+JSON.stringify(value)})),motion);
  });
  for(const literal of ['‘Exit’', ', }']){
    await test('exact JSON text preserves '+literal+' without false ambiguity',async()=>{
      const f=responseFixture({motionContext:owned});const value={...motion,prompt:motion.prompt+' Literal source detail: '+literal};
      assert.deepEqual(plain(f.context.extractMotionJson({innerText:JSON.stringify(value)})),value);
    });
  }
  await test('two genuinely different complete motion objects are never selected arbitrarily',async()=>{
    const f=responseFixture({motionContext:owned});const other={...motion,prompt:motion.prompt+' Different camera movement.'};
    assert.throws(()=>f.context.extractMotionJson({innerText:JSON.stringify(motion)+'\n'+JSON.stringify(other)}));
  });
  for(const gemini of [false,true])for(const fenced of [false,true]){
    await test((gemini?'Gemini':'ChatGPT')+' complete encoded JSON '+(fenced?'inside code fence':'as whole string')+' is ready',async()=>{
      const encoded=JSON.stringify(full);
      const content=fenced?'```json\n'+encoded+'\n```':encoded;
      const f=responseFixture({gemini,motionContext:owned,content:()=>content,cancelAt:15000});
      assert.deepEqual(plain(f.context.extractMotionJson(await f.run())),motion);f.checkSingleSend();
    });
  }
  await test('an encoded unfinished object remains waiting even with completion controls',async()=>{
    const f=responseFixture({motionContext:owned,content:()=>JSON.stringify(prefix),cancelAt:15000});
    completionActions(f.turn);await assert.rejects(f.run(),{name:'AbortError'});f.checkSingleSend();
  });
  await test('completed malformed JSON reaches format review only with real completion controls',async()=>{
    const malformed='{"job_id":"STORY-344-FIXTURE","context_id":"context-scene-ten","prompt": invalid}';
    const f=responseFixture({motionContext:owned,content:()=>malformed,cancelAt:15000});
    completionActions(f.turn);
    assert.equal((await f.run()).innerText,malformed);f.checkSingleSend();
  });
  await test('a stale Copy control cannot turn an unclosed prefix into a completed answer',async()=>{
    const f=responseFixture({motionContext:owned,content:()=>prefix,cancelAt:15000});
    completionActions(f.turn);
    await assert.rejects(f.run(),{name:'AbortError'});f.checkSingleSend();
  });
  for(const provider of ['chatgpt','gemini']){
    await test(provider+' cached partial passively rereads the completed answer with zero Sends',async()=>{
      const f=resumeFixture({provider});assert.equal(await f.run(),motion.prompt);
      const state=f.snapshot();assert(state.reads>0);assert.equal(state.sends,0);
      assert.deepEqual(f.messages.map(x=>x.action),['status','prepare','review','save']);
    });
    await test(provider+' cached partial can remain streaming beyond six minutes',async()=>{
      const f=resumeFixture({provider,content:ms=>ms<450000?prefix:full,stop:ms=>ms<30000});
      // Gemini359 requires actual activity, not an unchanged malformed prefix.
      if(provider==='gemini')f.c.analysisResponseStopButton=()=>f.snapshot().elapsed<450000?{}:null;
      assert.equal(await f.run(),motion.prompt);assert(f.snapshot().elapsed>=450000);assert.equal(f.snapshot().sends,0);
    });
  }
  await test('collapsed user-turn More control is not part of the canonical request',async()=>{
    const f=resumeFixture({collapsed:true});assert.equal(await f.run(),motion.prompt);assert.equal(f.snapshot().sends,0);
  });
  await test('completed conflicting JSON objects reach review without choosing one or another Send',async()=>{
    const conflict=full+'\n'+JSON.stringify({...motion,prompt:motion.prompt+' A materially different camera move.'});
    const f=resumeFixture({completed:true,content:()=>conflict});
    await assert.rejects(f.run(),/JSON/);assert.equal(f.snapshot().sends,0);
    assert.deepEqual(f.messages.map(message=>message.action),['status','prepare','review_text']);
    assert.equal(f.messages.at(-1).answer_text,conflict);
  });
  await test('wrong latest request cannot recover or overwrite the old partial',async()=>{
    const f=resumeFixture({wrongOwner:true,cancelAt:45000});await assert.rejects(f.run());
    assert.equal(f.snapshot().sends,0);assert.equal(f.messages.filter(x=>['review','save'].includes(x.action)).length,0);
  });
  await test('cancelled Resume never parses cached partial or submits a replacement',async()=>{
    const f=resumeFixture({cancelAt:0});await assert.rejects(f.run(),{name:'AbortError'});
    assert.equal(f.snapshot().sends,0);assert.equal(f.messages.filter(x=>['review','review_text','save'].includes(x.action)).length,0);
  });
  console.log(JSON.stringify({ok:failures.length===0,passed,failures}));
  if(failures.length)process.exitCode=1;
}
async function main(){
  if(process.argv.includes('--packet')){
    let input='';for await(const chunk of process.stdin)input+=chunk;
    const f=resumeFixture({packet:JSON.parse(input),collapsed:true});const prompt=await f.run();
    console.log(JSON.stringify({ok:true,prompt,messages:f.messages,...f.snapshot()}));
  }else await tests();
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
