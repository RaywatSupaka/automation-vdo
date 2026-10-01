// Execute the shipped capture block with simulated Chrome/bridge, never live sites.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function fixture(mode,old=false){
  const source=fs.readFileSync(old?'deliverables/SmartFlow_AI_Extension_0.15.418/background.js':'browser_extension/background.js','utf8');
  const section=source.slice(source.indexOf('        const activeTabs =',source.indexOf('if (command.action === "capture_shopee_product")')),
    source.indexOf('      } else if (command.action === "open_chatgpt"'));
  const job={id:'JOB-X',product_url:'https://shopee.co.th/item',product_name:'Fixture bag'};
  let imports=0,closed=[];
  const c=vm.createContext({BRIDGE:'http://fixture.invalid',setTimeout:fn=>fn(),
    command:{id:'CMD-X',job_id:'JOB-X'},rememberAutomationTabs:async()=>{},
    chrome:{tabs:{query:async()=>[],create:async()=>({id:77}),remove:async id=>closed.push(id),
      sendMessage:async()=>({data:{product:mode==='empty'?null:{product_name:'Fixture bag',images:['https://fixture.invalid/bag.jpg']}}})}},
    bridgeFetch:async url=>{
      if(url.endsWith('/api/products'))return {json:async()=>({jobs:[job]})};
      imports++;return {ok:true,json:async()=>({ok:true,job:{...job,source_images:mode==='missing-image'?[]:['original/bag.jpg']},
        capture_ready:mode!=='missing-image',verified_source_image_count:mode==='missing-image'?0:1,capture_command_id:'CMD-X'})};
    }});
  vm.runInContext('async function capture(){'+section+'}',c);
  return {run:()=>c.capture(),get closed(){return closed;},get imports(){return imports;}};
}
(async()=>{
  const old=fixture('missing-image',true);await old.run();assert.deepEqual(old.closed,[77]);
  const missing=fixture('missing-image');await assert.rejects(()=>missing.run(),/บันทึกชื่อหรือรูป/);
  assert.deepEqual(missing.closed,[]);assert.equal(missing.imports,1);
  const empty=fixture('empty');await assert.rejects(()=>empty.run(),/หน้า Shopee/);assert.deepEqual(empty.closed,[]);assert.equal(empty.imports,0);
  const ready=fixture('ready');await ready.run();assert.deepEqual(ready.closed,[77]);assert.equal(ready.imports,1);
  console.log('Shopee capture: RED418 empty-image success reproduced; failure tab retained, ready handoff unchanged');
})().catch(error=>{console.error(error);process.exitCode=1;});
