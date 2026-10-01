const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {File}=require('buffer');
const source=fs.readFileSync(require('path').join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const start=source.indexOf('  async function sourceFile('),end=source.indexOf('\n  function ',start);
const code=source.slice(start,end);
async function check(request){
 let bridge=0;
 const c=vm.createContext({activeCoverRequest:request,File,Uint8Array,Number,Error,atob,
   chrome:{runtime:{sendMessage:async()=>{bridge++;return {ok:false,error:'unexpected URL fetch'};}}},
   setTimeout:()=>0,report:async()=>{},sleep:async()=>{}});
 vm.runInContext(code,c);
 const refs=request.source_images || [request.source_data],files=[];
 for(let index=0;index<refs.length;index++){
   const file=await c.sourceFile(refs[index],index,'smartflow-cover-test.jpg');files.push(file);
   assert.equal(file.type,'image/jpeg');
   assert.deepEqual(Buffer.from(await file.arrayBuffer()),Buffer.from(refs[index].split(',')[1],'base64'));
 }
 assert.equal(new Set(files.map(f=>f.name)).size,refs.length);
 await assert.rejects(()=>c.sourceFile('data:image/jpeg;base64,WA==',0));
 await assert.rejects(()=>c.sourceFile(refs[0],refs.length));
 assert.equal(bridge,0,'cover bytes must never be sent to the URL-fetch endpoint');
}
(async()=>{
 if(process.argv[2])await check(JSON.parse(fs.readFileSync(process.argv[2],'utf8')));
 for(const provider of ['chatgpt','gemini']){
   await check({provider,source_images:['data:image/jpeg;base64,QQ==','data:image/jpeg;base64,Qg=='],source_data:'data:image/jpeg;base64,QQ=='});
   await check({provider,source_data:'data:image/jpeg;base64,QQ=='});
 }
 console.log('cover source bytes and ownership passed');
})().catch(e=>{console.error(e);process.exit(1);});
