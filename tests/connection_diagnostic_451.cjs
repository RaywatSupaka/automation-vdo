const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const section=source.slice(source.indexOf('async function connectionDiagnostic('),source.indexOf('function commandOutcomeMatches('));
async function run(status,payload,offline=false){
 const store={smartflowConnectionDiagnostic:{reachable:true,paired:true,checkedAt:Date.now()}};
 const context={BRIDGE:'http://fixture',VERSION:'0.15.test',CLIENT_ID:'fixture',BRIDGE_TOKEN:'stale',AbortController,Date,
  setTimeout,clearTimeout,pageType:async()=>'other',membershipProfile:async()=>'fixture',
  fetch:async()=>{if(offline)throw Error('offline');return {ok:status===200,status,json:async()=>payload};},
  chrome:{storage:{local:{get:async key=>({[key]:store[key]}),set:async value=>Object.assign(store,value),remove:async keys=>keys.forEach(key=>delete store[key])}}}};
 vm.createContext(context);vm.runInContext(section,context);
 try{await context.sendHeartbeat();}catch{}
 return {row:store.smartflowConnectionDiagnostic,store,token:context.BRIDGE_TOKEN};
}
(async()=>{
 let r=await run(403,{ok:false,error:'unpaired',extension_version_required:'0.15.new'});
 assert.equal(r.row.paired,false);assert.equal(r.row.updateRequired,true);assert.equal(r.token,'');
 assert.equal(r.store.smartpostExtensionUpdateRequired.requiredVersion,'0.15.new');
 r=await run(403,{ok:false,extension_version_required:'0.15.test'});assert.equal(r.row.paired,false);assert.equal(r.row.updateRequired,false);
 r=await run(200,{ok:true,extension_token:'synthetic',extension_version_required:'0.15.new',reload_required:true});
 assert.equal(r.row.paired,true);assert.equal(r.row.updateRequired,true);
 r=await run(200,{ok:true,extension_token:'synthetic',extension_version_required:'0.15.test'});
 assert.equal(r.row.paired,true);assert.equal(r.row.updateRequired,false);assert.equal(r.store.smartpostExtensionUpdateRequired,undefined);
 r=await run(0,{},true);assert.equal(r.row.reachable,false);assert.equal(r.row.paired,false);assert.equal(r.token,'');
 r=await run(200,{ok:true,extension_version_required:'0.15.test'});assert.equal(r.row.paired,false);assert.equal(r.token,'');
 const popup=fs.readFileSync('browser_extension/popup.js','utf8');
 assert(popup.includes('GET_CONNECTION_STATUS'));assert(!popup.includes('fetch(`${BRIDGE}/health`'));
 console.log('Connection diagnostics: 6 heartbeat states + popup contract passed');
})().catch(error=>{console.error(error);process.exit(1);});
