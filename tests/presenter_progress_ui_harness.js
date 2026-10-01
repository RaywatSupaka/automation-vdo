const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),app=fs.readFileSync(path.join(root,'web_ui/app.js'),'utf8');
const nodes=new Map();
function element(){const classes=new Set();return {open:false,style:{},textContent:'',showCalls:0,listeners:{},
 classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,on){on?classes.add(c):classes.delete(c);}},
 setAttribute(k,v){this[k]=v;},append(){},replaceChildren(...x){this.children=x;},addEventListener(k,fn){this.listeners[k]=fn;},
 showModal(){this.open=true;this.showCalls++;},close(){this.open=false;}};}
const $=key=>{if(!nodes.has(key))nodes.set(key,element());return nodes.get(key);};
const ui={state:{},progressMinimized:false},ctx={ui,$,document:{createElement:element,querySelector:$},
 clearTimeout(){},setTimeout(){},toast(){},showPage(){},progressSteps:()=>'',navigator:{clipboard:{writeText:async()=>{}}}};
ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(app.slice(app.indexOf('function minimizeProgress()'),app.indexOf('function renderNotice(state)')),ctx);
vm.runInContext(fs.readFileSync(path.join(root,'web_ui/presenter_progress.js'),'utf8'),ctx);
const idle={active:false,percent:0,job_id:''};
function render(p){ui.state={product_progress:idle,story_progress:idle,system:{},presenter_progress:{job_id:'PRESENTER-A',run_id:'RUN-A',stage:'image',status:'running',active:true,clips:0,...p}};ctx.renderProgress(ui.state);}
render({});assert.equal($('#progress-modal').showCalls,1);assert.equal(ui.progressType,'presenter');
ctx.minimizeProgress();for(let i=0;i<20;i++)render({clips:1,image_ready:true});
assert.equal($('#progress-modal').open,false);assert.equal($('#progress-modal').showCalls,1);
ctx.restoreProgress();assert.equal($('#progress-modal').open,true);
render({active:false,status:'error',stage:'error',message:'Failed',clips:1});assert.equal($('#progress-modal').open,true);
assert.equal($('#progress-result').textContent,'ดูงานและจุดที่หยุด');assert.equal($('#progress-percent').textContent,'1/3 คลิป');
ctx.dismissPresenterProgress();ctx.dismissProgressResult();render({active:false,status:'error',stage:'error',clips:1});assert.equal($('#progress-modal').open,false);
render({run_id:'RUN-B'});assert.equal($('#progress-modal').open,true,'new accepted run opens once');
ctx.minimizeProgress();render({run_id:'RUN-B',active:false,status:'image_review'});assert.equal($('#progress-modal').open,false,'review does not steal focus');
ctx.restoreProgress();assert.equal($('#progress-modal').open,true);
render({run_id:'RUN-B',active:false,status:'ready',stage:'ready',clips:3,image_ready:true});
assert.equal($('#progress-modal').open,false);assert.equal($('#progress-minimized').classList.contains('hidden'),true);
assert.equal(ui.progressResultReady,false);assert.equal($('#progress-modal').classList.contains('presenter-running'),false);
const shows=$('#progress-modal').showCalls;
for(let n=0;n<10;n++)render({run_id:'RUN-B',active:false,status:'ready',stage:'ready',clips:3,image_ready:true});
assert.equal($('#progress-modal').showCalls,shows,'ready heartbeat never reopens');
render({run_id:'RUN-C',stage:'cancelling'});assert.equal($('#progress-cancel').disabled,true);
const presenter=fs.readFileSync(path.join(root,'web_ui/presenter.js'),'utf8');
ctx.loaded=true;ctx.saved={available:true,settings:{enabled:true,id:'PRESENTER-123456ABCDEF',size:32}};
ctx.toggles={product:{check:{checked:true}},story:{check:{checked:false}}};
vm.runInContext(presenter.slice(presenter.indexOf('  window.presenterPayload='),presenter.indexOf('  let libraryStamp=')),ctx);
const result=ctx.presenterPayload('create_product',{});ctx.saved.settings.size=50;
assert.equal(result.presenter.size,32,'payload freezes saved configuration');
assert.equal(ctx.presenterPayload('create_story',{}).presenter.enabled,false,'checkbox off remains off');
const old={job_id:'JOB-OLD'};assert.equal(ctx.presenterPayload('create_product',old),old,'old resume untouched');
ctx.saved.available=false;assert.throws(()=>ctx.presenterPayload('creation_enqueue',{mode:'product'}));
assert.equal(presenter.includes("for(const mode of ['settings'])"),true);
assert.equal(presenter.includes("for(const b of $$('[data-x]',panel))"),true);
assert.equal(presenter.includes('ui.activePage===\'presenter-settings\''),true);
process.stdout.write(JSON.stringify({ok:true,cases:16}));
