/* Actual modal controls + action handlers; no server, real queue or provider. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const presenter=fs.readFileSync(path.join(root,'web_ui/presenter.js'),'utf8');
const app=fs.readFileSync(path.join(root,'web_ui/app.js'),'utf8');
const queue=fs.readFileSync(path.join(root,'web_ui/creation_queue.js'),'utf8');
const html=fs.readFileSync(path.join(root,'web_ui/index.html'),'utf8');
const nodes=new Map(),actions=[];
function node(tag,text='',cls=''){
  return {tag,textContent:text,className:cls,dataset:{},children:[],listeners:{},isConnected:true,open:false,checked:false,value:'',hidden:false,
    append(...children){this.children.push(...children);},setAttribute(key,value){this[key]=value;},
    addEventListener(key,handler){this.listeners[key]=handler;},before(child){this.beforeNode=child;},after(child){this.afterNode=child;},
    closest(){return this;},focus(){this.focused=true;},querySelector(){return null;},showModal(){this.open=true;},close(){this.open=false;}};
}
const $=selector=>{if(!nodes.has(selector))nodes.set(selector,node('div'));return nodes.get(selector);};
$('.create-submit-stack').parentElement=node('div');
const ctx={node,$,document:{createTextNode:text=>node('text',text)},ui:{activePage:'story'},
  loaded:true,saved:{available:true,name:'Guide',settings:{enabled:true,id:'PRESENTER-123456ABCDEF',x:5,y:95,size:32,timing:'all'}},
  returnPage:'products',returnDialog:null,refresh(){},showPage(page){ctx.ui.activePage=page;},
  toast(){},poll:async()=>{},storyBatchTopics:()=>['เรื่องหนึ่ง','เรื่องสอง','เรื่องสาม'],
  storyStylePayload:()=>({visual_style:'anime'}),selectedAiModel:()=> 'current',updateStoryBatchDialog(){}};
ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(presenter.slice(presenter.indexOf('  function returnToCreation()'),presenter.indexOf('  const url=')),ctx);
vm.runInContext(presenter.slice(presenter.indexOf('  const toggles={}'),presenter.indexOf('  let libraryStamp=')),ctx);
const toggles=vm.runInContext('toggles',ctx);
let cases=0;function test(name,fn){try{fn();cases++;}catch(error){error.message=name+': '+error.message;throw error;}}
test('both batch controls mounted at real anchors',()=>{
  assert.equal($('#story-batch-provider').beforeNode,toggles['story-batch'].box);
  assert.equal($('#creation-editor-settings').beforeNode,toggles['product-batch'].box);
  assert.match(html,/id="story-batch-provider"/);assert.match(queue,/id="creation-editor-settings"/);
  assert.ok(fs.readFileSync(path.join(root,'web_ui/presenter.css'),'utf8').includes('.presenter-quick-choice[data-batch] .presenter-check{display:flex;'));
  for(const mode of ['story-batch','product-batch']){assert.equal(toggles[mode].check.checked,false);assert.ok(toggles[mode].check['aria-describedby']);}
});
test('actual open handlers initialize dedicated choices',()=>{
  const storyOpen=app.slice(app.indexOf("$('#open-story-batch').addEventListener"),app.indexOf("$('#story-batch-topics').addEventListener"));
  assert.match(storyOpen,/preparePresenterQueue\?\.\('story-batch'\)/);
  assert.match(queue,/preparePresenterQueue\?\.\('product-batch', \{editing:Boolean\(item\)\}\)/);
});
test('inherits single story once',()=>{
  toggles.story.check.checked=true;ctx.preparePresenterQueue('story-batch');
  assert.equal(toggles['story-batch'].check.checked,true);
  assert.equal(toggles['story-batch'].check.disabled,false);
  assert.match(toggles['story-batch'].info.textContent,/Guide.*32%/);
});
test('batch overrides without changing single form',()=>{
  toggles['story-batch'].check.checked=false;
  assert.equal(ctx.presenterPayload('enqueue_story_batch',{}).presenter.enabled,false);
  assert.equal(ctx.presenterPayload('create_story',{}).presenter.enabled,true);
});
test('batch on independent of single off, frozen settings',()=>{
  toggles.story.check.checked=false;toggles['story-batch'].check.checked=true;
  const result=ctx.presenterPayload('enqueue_story_batch',{topics:['one','two']});
  ctx.saved.settings.size=50;
  assert.equal(result.presenter.size,32);assert.equal(result.presenter.enabled,true);
  assert.equal(ctx.presenterPayload('create_story',{}).presenter.enabled,false);
  ctx.saved.settings.size=32;
});
test('product batch choice used instead of hidden parent choice',()=>{
  toggles.product.check.checked=false;ctx.preparePresenterQueue('product-batch');
  $('#creation-editor').open=true;toggles['product-batch'].check.checked=true;
  assert.equal(ctx.presenterPayload('creation_enqueue',{mode:'product'}).presenter.enabled,true);
  assert.equal(ctx.presenterPayload('create_product',{}).presenter.enabled,false);
  $('#creation-editor').close();
});
test('single queued story still follows own choice',()=>{
  assert.equal(ctx.presenterPayload('creation_enqueue',{mode:'story'}).presenter.enabled,false);
});
test('missing ready presenter blocks checked batch, not unchecked',()=>{
  ctx.saved.available=false;ctx.preparePresenterQueue('story-batch');
  assert.equal(toggles['story-batch'].check.disabled,true);
  toggles['story-batch'].check.checked=true;assert.throws(()=>ctx.presenterPayload('enqueue_story_batch',{}));
  toggles['story-batch'].check.checked=false;assert.equal(ctx.presenterPayload('enqueue_story_batch',{}).presenter.enabled,false);
  ctx.saved.available=true;
});
test('old job, edits and drama are not overwritten',()=>{
  const old={job_id:'STORY-OLD',presenter:{enabled:true,id:'OLD'}};
  assert.equal(ctx.presenterPayload('enqueue_story_batch',old),old);
  assert.equal(ctx.presenterPayload('creation_edit',old),old);
  const drama={mode:'drama'};assert.equal(ctx.presenterPayload('creation_enqueue',drama),drama);
  ctx.preparePresenterQueue('product-batch',{editing:true});assert.equal(toggles['product-batch'].box.hidden,true);
});
test('settings roundtrip keeps modal fields and choice, no enqueue',()=>{
  const modal=$('#story-batch-modal');modal.showModal();ctx.ui.activePage='creation';
  $('#story-batch-topics').value='Draft A\nDraft B';toggles['story-batch'].check.checked=true;
  toggles['story-batch'].box.children[2].onclick();
  assert.equal(modal.open,false);assert.equal(ctx.ui.activePage,'presenter-settings');
  ctx.returnToCreation();assert.equal(modal.open,true);assert.equal(ctx.ui.activePage,'creation');
  assert.equal($('#story-batch-topics').value,'Draft A\nDraft B');assert.equal(toggles['story-batch'].check.checked,true);
  assert.equal(actions.length,0);ctx.returnToCreation();assert.equal(ctx.returnDialog,null);
});
ctx.postAction=async(action,payload)=>{actions.push({action,payload:ctx.presenterPayload(action,payload)});return {queued:3,duplicates:0,paused:true};};
vm.runInContext(app.slice(app.indexOf("$('#story-batch-submit').addEventListener"),app.indexOf("$('#create-story').addEventListener")),ctx);
(async()=>{
  $('#story-batch-direction').value='แนวทางเดิม';$('#story-batch-provider').value='chatgpt';
  $('#story-batch-video-mode').value='image_motion';$('#story-batch-scenes').value='10';
  await $('#story-batch-submit').listeners.click();
  test('real batch submit handler includes narrator in one request',()=>{
    assert.equal(actions.length,1);const {action,payload}=actions[0];
    assert.equal(action,'enqueue_story_batch');assert.equal(payload.presenter.enabled,true);
    assert.equal(payload.presenter.size,32);assert.equal(payload.topics.length,3);
    assert.equal(payload.video_generation_mode,'image_motion');assert.equal(payload.visual_style,'anime');
    assert.equal($('#story-batch-modal').open,false);
  });
  toggles['story-batch'].check.checked=false;await $('#story-batch-submit').listeners.click();
  test('real batch submit unchecked sends explicit disabled',()=>assert.equal(actions[1].payload.presenter.enabled,false));
  process.stdout.write(JSON.stringify({ok:true,cases}));
})().catch(error=>{console.error(error);process.exitCode=1;});
