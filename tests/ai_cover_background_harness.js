const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/background.js'),'utf8');
const code=source.slice(0,source.indexOf('// Keep a single owned debugger session'))
  +source.slice(source.indexOf('let coverPolling'),source.indexOf('// Runs in the page after tab activation'));
async function scenario(fail=false,recover=false,missing=false,oldReader=false){
  let phase='queued',tabs=0,sends=0;const saved={};
  const row={request_id:'a'.repeat(32),provider:'gemini',collect_only:recover,source_data:'data:image/jpeg;base64,QQ=='};
  if(recover&&!missing)saved['smartflowCover:'+row.request_id]={...row,tab_id:77};
  const context={URL,AI_WEB:{gemini:{url:'https://gemini.google.com/app'}},setTimeout,
    requireMembership:async()=>{},
    bridgeFetch:async(url,init)=>{
      let result;
      if(url.endsWith('/pending'))result={requests:phase==='queued'?[row]:[]};
      else if(url.endsWith('/event')){const event=JSON.parse(init.body);if(event.phase==='claimed'&&phase!=='queued')throw Error('duplicate');phase=event.phase;result={ok:true,request:{...row,phase}};}
      else result={ok:true,request:row};
      return{ok:true,json:async()=>result};
    },chrome:{runtime:{getManifest:()=>({version:'test'})},storage:{local:{set:async value=>Object.assign(saved,value),get:async key=>({[key]:saved[key]})}},
      tabs:{create:async()=>({id:++tabs}),get:async id=>({id,status:'complete',url:'https://gemini.google.com/app/owned'}),sendMessage:async(id,message)=>{if(message.type==='AI_COVER_CAPABILITIES')return oldReader?{}:{collect_only:true,busy:false};sends++;return fail?{ok:false,error:'not ready'}:{ok:true};}},
      scripting:{executeScript:async()=>{}}}};
  vm.createContext(context);vm.runInContext(code,context);
  await Promise.all([context.pollAICovers(),context.pollAICovers()]);
  await context.pollAICovers();
  assert.equal(tabs,recover?0:1);assert.equal(sends,missing||oldReader?0:1);
  assert.equal(phase,fail||missing||oldReader?'needs_review':'claimed');
  if(!missing)assert.ok(!('source_data' in saved['smartflowCover:'+row.request_id]));
}
(async()=>{await scenario();await scenario(true);await scenario(false,true);await scenario(false,true,true);await scenario(false,true,false,true);process.stdout.write(JSON.stringify({ok:true,cases:5}));})().catch(e=>{console.error(e);process.exit(1);});
