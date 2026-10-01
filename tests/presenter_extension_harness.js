const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../browser_extension/chatgpt.js'), 'utf8');
const start = source.indexOf('  async function runPresenterImage('), end = source.indexOf('  async function runJob(', start);
assert(start >= 0 && end > start);
function setup(options={}) {
  const events=[], sends=[], reports=[];
  const pkg={mode:'presenter',job:{id:'PRESENTER-123456ABCDEF',image:options.saved?'generated/character.png':''},prompt:'New portrait with green background',image_urls:options.refs||[],request:{image_count:1}};
  const context=vm.createContext({activeJobId:pkg.job.id,activeRunId:'RUN-test1',PROVIDER_KEY:options.provider||'chatgpt',
    report:async(...a)=>reports.push(a), assertNotCancelled:()=>{},
    submitImagePrompt:async(...args)=>{events.push('submit');sends.push(args);if(options.failSend)throw new Error('uncertain send');return 'image';},
    imageData:async()=>{events.push('download');return 'data:image/png;base64,AA==';},
    chrome:{runtime:{sendMessage:async m=>{events.push(m.action);assert.equal(m.run_id,'RUN-test1');assert.equal(m.provider,options.provider||'chatgpt');return {ok:!(options.failClaim&&m.action==='claim')&&!(options.failSave&&m.action==='save')};}}}
  });vm.runInContext(source.slice(start,end),context);
  return {run:()=>context.runPresenterImage(pkg),pkg,events,sends,reports};
}
(async()=>{
  let cases=0;
  for(const provider of ['chatgpt','gemini']) for(const refs of [[],['http://127.0.0.1:8765/api/presenters/PRESENTER-123456ABCDEF/files/source/reference.png']]){
    const t=setup({provider,refs});await t.run();assert.deepEqual(t.events,['claim','submit','download','save']);
    assert.equal(t.sends.length,1);assert.equal(t.sends[0][0],t.pkg.prompt);assert.equal(t.sends[0][1],refs);assert.equal(t.reports.at(-1)[0],'complete');cases++;
  }
  let t=setup({failClaim:true});await assert.rejects(t.run);assert.equal(t.sends.length,0);cases++;
  t=setup({failSend:true});await assert.rejects(t.run);assert.deepEqual(t.events,['claim','submit']);cases++;
  t=setup({failSave:true});await assert.rejects(t.run);assert.equal(t.sends.length,1);assert.notEqual(t.reports.at(-1)[0],'complete');cases++;
  t=setup({saved:true});await t.run();assert.deepEqual(t.events,[]);cases++;
  t=setup();t.pkg.request.image_count=3;await assert.rejects(t.run);assert.deepEqual(t.events,[]);cases++;
  console.log(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
