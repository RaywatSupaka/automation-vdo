/* Executes the library's actual source with an isolated DOM; no desktop/provider. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web_ui/presenter.js'),'utf8');
function element(tag,text='',className=''){
  return {tag,textContent:text,className,children:[],listeners:{},value:'',open:false,
    append(...xs){this.children.push(...xs);},add(x){this.append(x);},before(x){this.beforeNode=x;},
    replaceChildren(...xs){this.children=xs;},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
    addEventListener(k,fn){this.listeners[k]=fn;},pause(){this.paused=true;},load(){this.loaded=true;},
    showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},
    querySelectorAll(tag){return this.children.flatMap(x=>[...(x.tag===tag?[x]:[]),...x.querySelectorAll(tag)]);}};
}
const cards=element('div'),actions=[];
const ctx={node:element,$:()=>cards,Option:function(label,value){return Object.assign(element('option',label),{value});},
  document:{body:element('body')},url:(id,kind)=>id+'/'+kind,status:{ready:'ready',error:'error'},
  jobs:[{id:'a',name:'Alpha',status:'ready',image:'image.png',clips:{1:{},2:{},3:{}}},
    {id:'b',name:'Beta',status:'error',clips:{},error:'Review'},
    {id:'c',name:'Hidden',status:'ready',library_state:'hidden',clips:{}},
    {id:'d',name:'Trash',status:'ready',library_state:'trash',clips:{}}],
  window:{confirm:()=>true},postAction:async(a,p)=>actions.push({a,p}),refresh:async()=>{},toast:()=>{},
  navigator:{clipboard:{writeText:async()=>{}}}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("  let librarySearch="),source.indexOf('  const panels={}')),ctx);
vm.runInContext('renderCards()',ctx);
assert.equal(cards.children.length,2);assert.equal(cards.querySelectorAll('video').length,0);
vm.runInContext("libraryFilter='trash';renderCards()",ctx);assert.equal(cards.children.length,1);assert.equal(cards.children[0].children[1].textContent,'Trash');
vm.runInContext("libraryFilter='hidden';renderCards()",ctx);assert.equal(cards.children.length,1);
vm.runInContext("libraryFilter='all';librarySearch='alpha';renderCards()",ctx);assert.equal(cards.children.length,1);
vm.runInContext('showDetail(jobs[0])',ctx);
const detail=vm.runInContext('detail',ctx),video=detail.querySelectorAll('video')[0];
assert.equal(detail.querySelectorAll('video').length,1);assert.equal(video.src,'a/export');
const select=detail.querySelectorAll('select')[0];select.value='2';select.onchange();assert.equal(video.src,'a/2');assert.ok(video.paused);
vm.runInContext('renderCards()',ctx);assert.equal(detail.querySelectorAll('video')[0],video);
detail.close();assert.ok(video.paused);assert.equal(video.src,undefined);
vm.runInContext('showDetail(jobs[1])',ctx);assert.equal(detail.querySelectorAll('video').length,0);
(async()=>{
  ctx.window.confirm=()=>false;await vm.runInContext("libraryChange(jobs[0],'trash')",ctx);assert.equal(actions.length,0);
  ctx.window.confirm=()=>true;await vm.runInContext("libraryChange(jobs[1],'trash')",ctx);
  assert.equal(actions[0].a,'presenter_library_state');assert.equal(actions[0].p.confirmed,true);
  console.log('Presenter library actual-source checks passed: filters, compact cards, single player, switch, polling, close, confirmation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
