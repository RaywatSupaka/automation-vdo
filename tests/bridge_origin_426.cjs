// Observe native browser headers on a private ephemeral server; no user port or providers.
const http=require('http'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const seen=[];
  const server=http.createServer((req,res)=>{
    seen.push({method:req.method,origin:req.headers.origin,site:req.headers['sec-fetch-site'],token:req.headers['x-smartflow-token'],profile:req.headers['x-smartflow-profile']});
    if(req.headers.origin)res.setHeader('Access-Control-Allow-Origin',req.headers.origin);
    res.setHeader('Access-Control-Allow-Headers','Content-Type, X-SmartFlow-Token, X-SmartFlow-Profile');
    if(req.url==='/download'){res.statusCode=403;res.end();return;} // Never save a download.
    res.setHeader('Content-Type','application/json');res.end('{"ok":true}');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let context;
  try{
    const fixture=path.resolve('tests/fixtures/bridge_origin_426');
    context=await chromium.launchPersistentContext('',{headless:true,channel:'chromium',args:[`--disable-extensions-except=${fixture}`,`--load-extension=${fixture}`]});
    const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
    if(process.env.SMARTFLOW_TEST_BRIDGE_URL){
      const result=await worker.evaluate(async({base,version})=>{
        const response=await fetch(base+'/api/extension/heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({client_id:chrome.runtime.id,profile_id:'fixture-profile',version})});
        const paired=await response.json();
        if(!response.ok||!paired.extension_token)throw Error('Fixture bootstrap failed');
        const state=await fetch(base+'/api/desktop/state',{headers:{'X-SmartFlow-Token':paired.extension_token,'X-SmartFlow-Profile':'fixture-profile'}});
        return {status:state.status,body:await state.json()};
      },{base:process.env.SMARTFLOW_TEST_BRIDGE_URL,version:process.env.SMARTFLOW_TEST_BRIDGE_VERSION});
      assert.equal(result.status,200);assert.equal(result.body.private,'fixture');
      console.log('Native Extension POST bootstrap -> Origin-less private GET authenticated successfully');return;
    }
    const base=`http://127.0.0.1:${server.address().port}`;
    await worker.evaluate(async base=>{
      await fetch(base+'/heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      await fetch(base+'/private',{headers:{'X-SmartFlow-Token':'fixture','X-SmartFlow-Profile':'fixture'}});
      await chrome.downloads.download({url:base+'/download',headers:[{name:'X-SmartFlow-Token',value:'fixture'},{name:'X-SmartFlow-Profile',value:'fixture-profile'}]}).catch(()=>{});
    },base);
    for(let n=0;n<50&&seen.filter(row=>row.method!=='OPTIONS').length<3;n++)await new Promise(r=>setTimeout(r,100));
    const requests=seen.filter(row=>row.method!=='OPTIONS');
    assert.equal(requests.length,3);
    assert.equal(requests[2].token,'fixture');
    assert.equal(requests[2].profile,'fixture-profile');
    assert.equal(requests[0].origin,'chrome-extension://'+new URL(worker.url()).host);
    console.log(JSON.stringify(requests));
  }finally{await context?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1);});
