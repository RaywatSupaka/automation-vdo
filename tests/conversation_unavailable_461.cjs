const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {chromium}=require('playwright');
const source=fs.readFileSync('browser_extension/conversation_recovery.js','utf8');
const ctx=vm.createContext({});vm.runInContext(source,ctx);
const advance=ctx.SmartFlowConversationRecovery.advance;
let cases=0;
function fixture(){
 let now=1000,valid=true,record={version:1,token:'token',phase:'observing',tab_id:1,
  source_tab_id:1,document_id:'old',url:'https://chatgpt.com/c/original',first_at:0};
 const tabs=new Map([[1,{state:'unavailable',url:record.url,document_id:'old'}]]),events=[];
 const io={now:()=>now,validate:async()=>{if(!valid)throw Error('owner');return record;},
  inspect:async id=>tabs.get(id),save:async(old,patch)=>{assert.deepEqual(old,record);return record={...record,...patch};},
  reload:async id=>{events.push(['reload',id]);tabs.set(id,{...tabs.get(id),document_id:'refreshed'});},
  create:async url=>{events.push(['create',url]);tabs.set(2,{url,state:'outside',document_id:'blank'});return {id:2};},
  find:async url=>[...tabs].filter(([,tab])=>tab.url===url).map(([id])=>({id})),
  transfer:async()=>events.push(['transfer']),navigate:async(id,url)=>{events.push(['navigate',id,url]);tabs.set(id,{url,state:'unavailable',document_id:'new'});},
  resume:async()=>events.push(['read-original'])};
 return {io,tabs,events,get row(){return record;},tick:async(ms=15000)=>{now+=ms;await advance(io,record);},
  state:patch=>{record={...record,...patch};},invalidate:()=>{valid=false;}};
}
(async()=>{
 let f=fixture();await f.tick(1000);assert.equal(f.events.length,0);cases++;
 await f.tick();await f.tick();assert.equal(f.row.phase,'checking');cases++;
 f.tabs.set(1,{...f.tabs.get(1),state:'ready'});await f.tick();
 assert.equal(f.row.phase,'resumed');assert.deepEqual(f.events,[['reload',1],['read-original']]);cases++;
 f=fixture();await f.tick();await f.tick();await f.tick();
 assert.equal(f.row.phase,'replacement');assert.equal(f.row.tab_id,2);
 assert.deepEqual(f.events.at(-1),['navigate',2,'https://chatgpt.com/c/original']);cases++;
 for(let i=0;i<6;i++)await f.tick(60000);
 assert.equal(f.events.filter(x=>x[0]==='create').length,1);assert(!f.events.some(x=>x[0]==='read-original'));cases++;
 f.tabs.set(2,{...f.tabs.get(2),state:'ready'});await f.tick(60000);assert.equal(f.row.phase,'resumed');cases++;
 f=fixture();f.io.reload=async()=>{f.events.push(['reload']);throw Error('lost ACK');};
 await assert.rejects(()=>f.tick());for(let i=0;i<3;i++)await f.tick();assert.equal(f.events.length,1);cases++;
 f.tabs.set(1,{...f.tabs.get(1),document_id:'refreshed',state:'ready'});await f.tick();await f.tick();
 assert.equal(f.row.phase,'resumed');cases++;
 f=fixture();const create=f.io.create;f.io.create=async url=>{await create(url);throw Error('lost create ACK');};
 await f.tick();await f.tick();await assert.rejects(()=>f.tick());await f.tick();
 assert.equal(f.events.filter(x=>x[0]==='create').length,1);assert.equal(f.row.phase,'replacement');cases++;
 f=fixture();f.io.create=async()=>{f.events.push(['create']);throw Error('unknown allocation');};
 await f.tick();await f.tick();await assert.rejects(()=>f.tick());await f.tick();await f.tick();
 assert.equal(f.events.filter(x=>x[0]==='create').length,1);cases++;
 for(const state of ['protected','loading','ready']){f=fixture();f.tabs.get(1).state=state;await f.tick();assert.equal(f.events.length,0);cases++;}
 f=fixture();f.invalidate();await assert.rejects(()=>f.tick());assert.equal(f.events.length,0);cases++;
 f=fixture();f.io.navigate=async()=>{throw Error('navigation ACK lost');};await f.tick();await f.tick();await assert.rejects(()=>f.tick());
 let navigated=0;f.io.navigate=async(id,url)=>{navigated++;assert.equal(id,2);assert.equal(url,f.row.url);};
 await f.tick();assert.equal(navigated,1);assert.equal(f.events.filter(x=>x[0]==='create').length,1);cases++;
 f=fixture();let views=0;const inspect=f.io.inspect;f.io.inspect=async id=>{const view=await inspect(id);return ++views>1?{...view,state:'ready'}:view;};
 await f.tick();assert.equal(f.row.phase,'aborted');assert.equal(f.events.length,0);cases++;
 f=fixture();f.state({phase:'resuming',document_id:'old'});f.tabs.get(1).state='ready';await f.tick();assert.equal(f.events.length,1);cases++;

 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',route=>route.fulfill({status:200,contentType:'text/html',body:'<html><body></body></html>'}));
  const panel='<div><div class="text-lg">ไม่สามารถโหลดการสนทนา ChatGPT นี้ได้</div><div><button>ลองใหม่</button></div></div>';
  await page.goto('https://chatgpt.com/c/original');await page.addScriptTag({content:source});
  const check=async(html,expected)=>{await page.setContent(html);assert.equal(await page.evaluate(()=>SmartFlowConversationRecovery.inspect().state),expected);cases++;};
  await check(panel,'unavailable');
  await check(panel.replace('ไม่สามารถโหลดการสนทนา ChatGPT นี้ได้','Unable to load conversation abc-def').replace('ลองใหม่','Retry'),'unavailable');
  await check('<article data-message-author-role="assistant">'+panel+'</article><div id="prompt-textarea" contenteditable="true"></div>','ready');
  await check('<nav>'+panel+'</nav>','loading');
  await check('<div style="display:none">'+panel+'</div>','loading');
  await check(panel+'<textarea>my draft</textarea>','protected');
  await check(panel+'<button data-testid="stop-button">Stop</button>','protected');
  await check(panel+'<div role="progressbar">42%</div>','protected');
  await check(panel+'<article data-message-author-role="assistant">saved result</article><textarea></textarea>','ready');
  await check(panel.replace('ลองใหม่','Send'),'loading');
  await check('<div>Something went wrong</div><button>Retry</button>','loading');
  await page.goto('https://codex.example/c/original');await page.addScriptTag({content:source});await check(panel,'outside');
  await page.goto('https://chatgpt.com/auth/login');await page.addScriptTag({content:source});await check(panel,'outside');
  await page.goto('https://chatgpt.com/');await page.addScriptTag({content:source});
  await check('<textarea></textarea>','fresh_ready');
  await check('<textarea></textarea><button>Log in</button>','protected');
  await check('<textarea>draft</textarea>','protected');
  await check('<textarea></textarea><div data-message-author-role="user">existing request</div>','protected');
 }finally{await browser.close();}
 console.log(JSON.stringify({ok:true,cases,provider_sends:0,live_state_writes:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
