// Existing457 status-only outbox, no network, DOM, provider or filesystem writes.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/background.js'),'utf8');
const code=source.slice(source.indexOf('const progressOutboxLocks=new Map();'),source.indexOf('function scheduleFastCommandHandoff('));
const rows={},calls=[];let rejection=false;
const ctx={AbortController,setTimeout,clearTimeout,Promise,BRIDGE:'http://fixture.invalid',
  chrome:{storage:{local:{get:async key=>key===null?structuredClone(rows):{[key]:rows[key]},
    set:async value=>Object.assign(rows,structuredClone(value)),remove:async key=>{delete rows[key];}}}},
  flowProgressOwnership:async()=>({active:true}),aiProgressOwnership:async()=>({active:true}),
  bridgeFetch:async(url,options)=>{calls.push(JSON.parse(options.body));return{ok:!rejection,
    json:async()=>rejection?{ok:false,error:'unrelated validation error'}:{ok:true,ignored:true,reason:'job_permanently_deleted'}};}};
vm.createContext(ctx);vm.runInContext(code,ctx);
(async()=>{
  const report={job_id:'STORY-DELETED',run_id:'original',tab_id:7,scope:'flow',step:'generation_complete',
    download_path:'fixture/original-attempt.mp4',observed_at_ms:1};
  const result=await ctx.forwardObservedProgress(report);
  assert.equal(result.ignored,true);assert.equal(Object.keys(rows).length,0);
  await ctx.flushProgressOutbox();assert.equal(calls.length,1,'terminal ACK cannot keep retrying');
  rejection=true;
  const blocked=await ctx.forwardObservedProgress({...report,job_id:'STORY-LIVE',observed_at_ms:2});
  assert.equal(blocked.buffered,true);assert.equal(Object.keys(rows).length,1);
  assert.equal(Object.values(rows)[0].download_path,report.download_path,'retain exact unknown save evidence');
  await ctx.flushProgressOutbox();assert.equal(calls.length,3,'unrelated HTTP400 must remain retryable');
  assert(Object.keys(rows).some(key=>key.startsWith('smartflowProgressOutbox:')));
  console.log('PASS existing457 terminal deletion ACK clears only passive outbox; ordinary400 retains evidence');
})().catch(error=>{console.error(error);process.exitCode=1;});
