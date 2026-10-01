// Execute the source capture handler offline; never open live Shopee pages.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function fixture(mode){
  const source=fs.readFileSync('browser_extension/background.js','utf8');
  const start=source.indexOf('        const activeTabs =',source.indexOf('if (command.action === "capture_shopee_product")'));
  const end=source.indexOf('      } else if (command.action === "open_chatgpt"',start);
  const section=source.slice(start,end);
  const job={id:'JOB-X',product_url:'https://shopee.co.th/item',product_name:'Fixture bag'};
  let imports=0,closed=[],posted={},scans=0;
  const c=vm.createContext({BRIDGE:'http://fixture.invalid',setTimeout:fn=>fn(),
    command:{id:'CMD-current',job_id:'JOB-X'},rememberAutomationTabs:async()=>{},
    chrome:{tabs:{query:async()=>[],create:async()=>({id:77}),remove:async id=>closed.push(id),
      sendMessage:async()=>{scans++;return {data:{product:{product_name:'Fixture bag',images:['https://fixture.invalid/bag.jpg'],
        description:mode==='late-detail'&&scans>=3?'Verified bag size from product details':' '}}};}}},
    bridgeFetch:async(_url,options={})=>{
      if(!options.method)return {json:async()=>({jobs:[job]})};
      imports++;posted=JSON.parse(options.body||'{}');
      const captureReady=mode==='ready'||mode==='late-detail';
      return {ok:true,json:async()=>({ok:true,capture_ready:captureReady,
        verified_source_image_count:captureReady?1:0,
        capture_command_id:mode==='wrong-command'?'CMD-old':'CMD-current',
        job:{...job,source_images:mode==='empty'?[ ]:['original/bag.jpg']}})};
    }});
  vm.runInContext('async function capture(){'+section+'}',c);
  return {run:()=>c.capture(),get closed(){return closed;},get imports(){return imports;},get posted(){return posted;},get scans(){return scans;}};
}
(async()=>{
  const ready=fixture('ready');await ready.run();
  assert.deepEqual(ready.closed,[77]);assert.equal(ready.imports,1);
  assert.equal(ready.posted.target_job_id,'JOB-X');assert.equal(ready.posted.target_capture_command_id,'CMD-current');
  const detail=fixture('late-detail');await detail.run();
  assert.equal(detail.scans,3);assert.equal(detail.posted.description,'Verified bag size from product details');
  for(const mode of ['empty','not-verified','wrong-command']){
    const failed=fixture(mode);await assert.rejects(()=>failed.run());
    assert.deepEqual(failed.closed,[],'Keep the owned Shopee tab open for diagnosis');
    assert.equal(failed.imports,1);
  }
  console.log('Shopee Product capture 420: matching command + server-verified disk image required; safe tab cleanup passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
