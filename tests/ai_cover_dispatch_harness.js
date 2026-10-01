const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../browser_extension/chatgpt.js'),'utf8');
const start=source.indexOf("    if(message?.type==='START_AI_COVER')");
const end=source.indexOf("    if (message?.type === 'SMARTFLOW_REPAIR_IDENTITY')",start);
const code='function dispatch(message,sendResponse){'+source.slice(start,end)+'}';
const jpeg='data:image/jpeg;base64,QQ==';
function check(request,expected,busy=false){
  let calls=0,response;
  const c={activeJobId:busy?'active':'',PROVIDER_KEY:request.provider,runAICover:async r=>{calls++;assert.equal(r,request);}};
  vm.createContext(c);vm.runInContext(code,c);c.dispatch({type:'START_AI_COVER',request},r=>response=r);
  assert.equal(response.ok,expected);assert.equal(calls,expected?1:0);
}
const base={request_id:'a'.repeat(32),provider:'chatgpt'};
if(process.argv[2]) {check(JSON.parse(fs.readFileSync(process.argv[2],'utf8')),true);}
for(const provider of ['chatgpt','gemini']){
  for(const fields of [{source_images:[jpeg]},{source_images:[jpeg,jpeg]},{source_data:jpeg}])check({...base,provider,...fields},true);
}
for(const fields of [{},{source_images:[]},{source_images:[jpeg,'bad']},{source_images:[jpeg,jpeg,jpeg]},{source_images:'bad',source_data:jpeg},{source_data:'data:image/jpeg;base64,'}])check({...base,...fields},false);
check({...base,source_images:[jpeg]},false,true);
check({...base,collect_only:true,sources:['scene1.jpg','scene2.jpg']},true);
check({...base,collect_only:true},false);
console.log('cover dispatch passed');
