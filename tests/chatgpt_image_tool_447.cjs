// Actual production functions, synthetic DOM/time only. No provider or live job.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
// Small deterministic DOM fixture implementing only the production selectors.
// The real current menu/chip was separately verified in an idle Chrome tab.
class Element {
  constructor(tag,attributes={}){this.tag=tag;this.attributes={...attributes};this.children=[];this.parentElement=null;this.disabled=false;this.hidden=false;this.text='';}
  get nodeType(){return 1;}
  get tagName(){return this.tag.toUpperCase();}
  get childNodes(){return [...(this.text?[{nodeType:3,nodeValue:this.text}]:[]),...this.children];}
  get isConnected(){return this.tag==='document'||Boolean(this.parentElement?.isConnected);}
  get form(){
    if(!['button','input','textarea','select','fieldset','object','output'].includes(this.tag))return undefined;
    const explicit=this.getAttribute('form');
    if(explicit!==null){let root=this;while(root.parentElement)root=root.parentElement;return root.querySelector(`form[id="${explicit}"]`)||null;}
    return this.closest('form');
  }
  getBoundingClientRect(){return {left:0,top:0,width:this.hidden?0:48,height:this.hidden?0:48,right:this.hidden?0:48,bottom:this.hidden?0:48};}
  getAttribute(key){return this.attributes[key]??null;}
  setAttribute(key,value){this.attributes[key]=String(value);}
  removeAttribute(key){delete this.attributes[key];}
  append(child){child.parentElement=this;this.children.push(child);}
  cloneNode(deep=false){const copy=new Element(this.tag,this.attributes);copy.text=this.text;copy.disabled=this.disabled;copy.hidden=this.hidden;if(deep)for(const child of this.children)copy.append(child.cloneNode(true));return copy;}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);this.parentElement=null;}
  click(){this.onclick?.();}
  closest(tag){for(let e=this;e;e=e.parentElement)if(e.tag===tag)return e;return null;}
  get textContent(){return this.text+this.children.map(e=>e.textContent).join('');}
  get innerText(){return this.hidden?'':this.textContent;}
  set textContent(value){this.text=String(value);this.children=[];}
  set innerHTML(value){this.children=[];for(const match of value.matchAll(/<span>(.*?)<\/span>/g)){const span=new Element('span');span.textContent=match[1];this.append(span);}}
  querySelectorAll(selector){
    const matches=e=>selector.split(',').some(s=>{
      s=s.trim();const tag=s.match(/^[a-z]+/)?.[0];if(tag&&e.tag!==tag)return false;
      const simple=s.replace(/\[[^\]]*\]/g,'');
      for(const m of simple.matchAll(/\.([\w-]+)/g))if(!String(e.getAttribute('class')||'').split(/\s+/).includes(m[1]))return false;
      const id=simple.match(/#([\w-]+)/)?.[1];if(id&&e.getAttribute('id')!==id)return false;
      for(const m of s.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g))if(e.getAttribute(m[1])===null||(m[2]!==undefined&&e.getAttribute(m[1])!==m[2]))return false;
      return true;
    });
    const descendants=e=>e.children.flatMap(child=>[child,...descendants(child)]);
    return descendants(this).filter(matches);
  }
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function documentFixture(){
  const d=new Element('document'),body=new Element('body'),main=new Element('main'),form=new Element('form',{'data-chatgpt-composer':''});
  d.append(body);body.append(main);main.append(form);d.body=body;d.createElement=tag=>new Element(tag);
  form.append(new Element('button',{'data-composer-navigation-target':'add-context','aria-label':'เพิ่มไฟล์และอื่นๆ','aria-expanded':'false'}));
  form.append(new Element('div',{contenteditable:'true'}));return d;
}
const source=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const part=(a,b)=>{const i=source.indexOf(a),j=source.indexOf(b,i+a.length);assert(i>=0&&j>i,a);return source.slice(i,j);};
let cases=0;
const eq=(a,b,label)=>{assert.deepEqual(a,b,label);cases++;};
const modeCode=part('  function chatGPTImageToolChip(', '  async function submitImagePrompt(');
function modeFixture(config={}){
  const document=documentFixture();
  let scope=document.querySelector('form'),editor=document.querySelector('[contenteditable]'),opener=scope.querySelector('button');
  let opens=0,choices=0,removes=0,time=0,busy=Boolean(config.busy),cancelled=false;
  const events=[];
  editor.textContent=config.draft||'';
  const chip=()=>{
    if(!config.inlineOnly){
      const b=document.createElement('button');b.setAttribute('aria-label',config.english?'Remove Create image':'ลบ สร้างรูปภาพ');
      b.textContent='สร้างรูปภาพ';b.onclick=()=>{removes++;if(!config.noRemove)b.remove();};scope.append(b);
    }
    if(config.inlineTool||config.inlineOnly){const inline=document.createElement('span');inline.setAttribute('contenteditable','false');inline.textContent='สร้างรูปภาพ';editor.append(inline);}
  };
  if(config.selected)chip();
  opener.disabled=Boolean(config.disabled);
  const menuOption=()=>{
      const b=document.createElement('button');b.setAttribute('data-list-navigation-item','true');b.setAttribute('aria-current','true');
      b.innerHTML='<span>'+(config.english?'Create image':'สร้างรูปภาพ')+'</span><span>เปลี่ยนทุกสิ่งให้เป็นภาพ</span>';
      b.onclick=()=>{choices++;if(!config.noProof)chip();document.querySelectorAll('[data-list-navigation-item]').forEach(x=>x.remove());opener.setAttribute('aria-expanded','false');};
      document.body.append(b);
      return b;
  };
  const bindOpener=button=>{button.onclick=()=>{
    opens++;button.setAttribute('aria-expanded','true');
    if(config.busyAfterOpen)busy=true;
    for(let n=0;n<(config.options??1);n++)menuOption();
  };};
  bindOpener(opener);
  const remount=(draft='')=>{
    const parent=scope.parentElement || document.body;scope.remove();
    scope=document.createElement('form');scope.setAttribute('data-chatgpt-composer','');parent.append(scope);
    opener=document.createElement('button');opener.setAttribute('data-composer-navigation-target','add-context');
    opener.setAttribute('aria-expanded','false');scope.append(opener);bindOpener(opener);
    editor=document.createElement('div');editor.setAttribute('contenteditable','true');editor.textContent=draft;scope.append(editor);
  };
  const c=vm.createContext({document,IS_GEMINI:Boolean(config.gemini),String,Boolean,Error,
    HTMLTextAreaElement:class {},composer:()=>editor,waitForComposer:async()=>editor,
    visible:e=>Boolean(e?.isConnected)&&!e.hidden,stopButtonVisible:()=>busy,
    assertNotCancelled:()=>{if(cancelled)throw Object.assign(Error('cancelled'),{name:'AbortError'});},
    sleep:async ms=>{time+=ms;config.onSleep?.(api);},report:async(...args)=>events.push(args)});
  vm.runInContext(part('  function composerText(', '  function explicitAnalysisRefusal(')+modeCode,c);
  const api={c,document,events,get editor(){return editor;},get scope(){return scope;},get opener(){return opener;},
    get opens(){return opens;},get choices(){return choices;},get removes(){return removes;},get time(){return time;},
    setBusy:v=>busy=v,cancel:()=>cancelled=true,addChip:chip,addMenuOption:menuOption,remount};
  return api;
}
async function modeTests(){
  let f=modeFixture();await f.c.setChatGPTImageTool(true);
  eq(f.opens,1);eq(f.choices,1);eq(Boolean(f.c.chatGPTImageToolChip()),true,'real composer chip required');
  await f.c.setChatGPTImageTool(true);eq(f.opens,1,'selected mode does not click twice');eq(f.choices,1);
  await f.c.setChatGPTImageTool(false);eq(f.removes,1);eq(f.c.chatGPTImageToolChip(),null);
  await f.c.setChatGPTImageTool(false);eq(f.removes,1,'text mode no redundant mutation');
  for(const config of [{disabled:true},{options:0},{options:2},{noProof:true},{busy:true},{draft:'user draft'},{busyAfterOpen:true}]){
    f=modeFixture(config);await assert.rejects(f.c.setChatGPTImageTool(true),e=>e.code==='AI_SEND_NOT_READY'&&e.notDispatched===true);cases++;
    eq(f.choices,config.noProof?1:0,'unsafe/no-proof state never sends or repeats option');
  }
  f=modeFixture({noProof:true});await assert.rejects(f.c.setChatGPTImageTool(true));cases++;
  eq(Boolean(f.c.chatGPTImageToolChip()),false,'menu aria-current is not selection');
  f=modeFixture({draft:'owned prompt'});await f.c.setChatGPTImageTool(true,0,'owned prompt');
  eq(f.editor.textContent,'owned prompt','owned unsent draft preserved');
  await f.c.setChatGPTImageTool(false,0,'owned prompt');eq(f.editor.textContent,'owned prompt');
  f=modeFixture({selected:true,busy:true});await assert.rejects(f.c.setChatGPTImageTool(false));cases++;eq(f.removes,0,'never change mode during generation');
  f=modeFixture();await assert.rejects(f.c.setChatGPTImageTool(true,0,'',()=>false));cases++;eq(f.opens,0,'owner veto');
  f=modeFixture();f.cancel();await assert.rejects(f.c.setChatGPTImageTool(true),e=>e.name==='AbortError');cases++;eq(f.opens,0);
  f=modeFixture({english:true});await f.c.setChatGPTImageTool(true);eq(f.choices,1);eq(Boolean(f.c.chatGPTImageToolChip()),true);
  f=modeFixture({selected:true,inlineTool:true});eq(f.c.composerText(f.editor),'','selected inline tool is not a draft');
  await f.c.setChatGPTImageTool(true);eq(f.opens,0,'selected inline tool does not reopen menu');
  f=modeFixture({selected:true,inlineOnly:true});eq(f.c.composerText(f.editor),'','inline-only tool is not a draft');
  await f.c.setChatGPTImageTool(true);eq(f.opens,0,'inline-only tool does not select twice');
  await assert.rejects(f.c.setChatGPTImageTool(false),e=>e.toolReason==='inline_tool_unremovable');cases++;
  eq(f.editor.textContent,'สร้างรูปภาพ','unknown inline removal is not attempted');
  f=modeFixture({inlineTool:true});await f.c.setChatGPTImageTool(true);
  eq(f.c.composerText(f.editor),'','new inline tool label is not a draft');eq(f.choices,1);
  f=modeFixture({selected:true,inlineTool:true,draft:'foreign draft'});
  await assert.rejects(f.c.setChatGPTImageTool(true),e=>e.toolReason==='draft_changed');cases++;
  eq(f.editor.textContent,'foreign draftสร้างรูปภาพ','real foreign draft preserved');
  f=modeFixture({draft:'สร้างรูปภาพ'});
  await assert.rejects(f.c.setChatGPTImageTool(true),e=>e.toolReason==='draft_changed');cases++;
  eq(f.choices,0,'editable words identical to tool label remain a draft');
  const prompt='Create one scene image';
  const transport='\n\n[transport instruction]';
  f=modeFixture({selected:true,draft:prompt+transport});
  f.c.SmartFlowSingleAnswer={canonical:value=>String(value).replace(transport,'')};
  eq(f.c.composerText(f.editor),prompt,'draft reader removes transport instruction');
  await f.c.setChatGPTImageTool(true,0,prompt);
  eq(f.choices,0,'canonical owned prompt is accepted without selecting the tool twice');
  eq(source.includes('await setChatGPTImageTool(true, completedCount, text);'),true,
    'Story recheck passes canonical prompt to the draft guard');
  eq(source.includes('await setChatGPTImageTool(true,completedCount,repair.image_request);'),true,
    'visual repair recheck passes canonical prompt');
  eq(source.includes('await setChatGPTImageTool(true,0,coverPrompt);'),true,
    'cover recheck passes canonical prompt');
  f=modeFixture({gemini:true});await f.c.setChatGPTImageTool(true);eq(f.opens,0,'Gemini untouched');
  eq(source.includes('await setChatGPTImageTool(false, completedCount, text);'),true,'text/JSON clears image-only tool');
  eq(source.includes('await setChatGPTImageTool(true, completedCount, repair.image_request);'),true,'visual repair covered');
  eq(/setChatGPTImageTool\(true,\s*0,\s*(?:coverPrompt|prompt)[,)]/.test(source),true,'cover preparation calls the shared tool helper');
}
async function hydrationTests(){
  const rejected=async(f,reason,enabled=true,ownedDraft='',guard=null)=>{
    await assert.rejects(f.c.setChatGPTImageTool(enabled,0,ownedDraft,guard),error=>error.code==='AI_SEND_NOT_READY'
      && error.notDispatched===true && error.toolReason===reason
      && error.transient===!['response_active','draft_changed','owner_changed','menu_ambiguous'].includes(reason));cases++;
  };
  let f=modeFixture({disabled:true,onSleep:f=>{f.opener.disabled=false;}});
  await f.c.setChatGPTImageTool(true);eq(f.time,250,'disabled opener waits one tick');eq(f.opens,1);eq(f.choices,1);
  f=modeFixture({onSleep:f=>{if(f.time===500)f.scope.append(f.opener);}});f.opener.remove();
  await f.c.setChatGPTImageTool(true);eq(f.time,500,'missing opener can hydrate');eq(f.choices,1);
  f=modeFixture();f.c.composer=()=>f.time<500?null:f.editor;
  await f.c.setChatGPTImageTool(true);eq(f.time,500,'composer readiness shares bounded wait');eq(f.choices,1);
  f=modeFixture({disabled:true,onSleep:f=>{if(f.time===250)f.remount();}});const oldEditor=f.editor;
  await f.c.setChatGPTImageTool(true);eq(oldEditor.isConnected,false,'old editor is detached');eq(f.choices,1);eq(f.opens,1,'only current opener clicked');
  const remountConfig={options:0,onSleep:f=>{if(f.time===250){remountConfig.options=1;f.remount();}}};
  f=modeFixture(remountConfig);await f.c.setChatGPTImageTool(true);
  eq(f.opens,2,'new form gets its own opener, no repeated click on old node');eq(f.choices,1);
  f=modeFixture({options:0,onSleep:f=>{if(f.time===750)f.addMenuOption();}});
  await f.c.setChatGPTImageTool(true);eq(f.time,750);eq(f.opens,1,'slow menu does not toggle opener repeatedly');eq(f.choices,1);
  f=modeFixture({options:0,onSleep:f=>{if(f.time===250)f.addMenuOption();}});
  const detachedOption=f.addMenuOption(),readAttribute=detachedOption.getAttribute.bind(detachedOption);
  detachedOption.getAttribute=name=>{if(name==='aria-label')detachedOption.remove();return readAttribute(name);};
  await f.c.setChatGPTImageTool(true);eq(f.time,250,'detached menu option is resolved again');
  eq(detachedOption.isConnected,false);eq(f.choices,1,'only the replacement menu option is clicked');eq(f.opens,1);
  f=modeFixture({noProof:true,onSleep:f=>{if(f.time===1000)f.addChip();}});
  await f.c.setChatGPTImageTool(true);eq(f.time,1000);eq(f.choices,1,'slow selected chip cannot repeat option');eq(f.events.length,1);
  f=modeFixture({disabled:true,onSleep:f=>{f.addChip();}});
  await f.c.setChatGPTImageTool(true);eq(f.choices,0,'mode already selected while waiting');eq(f.opens,0);
  f=modeFixture({disabled:true});await rejected(f,'opener_disabled');eq(f.time,30000);eq(f.opens,0);
  f=modeFixture();f.opener.remove();await rejected(f,'opener_missing');eq(f.time,30000);
  f=modeFixture();f.c.composer=()=>null;await rejected(f,'composer_not_ready');eq(f.time,30000);
  f=modeFixture({options:0});await rejected(f,'menu_missing');eq(f.time,30000);eq(f.opens,1);
  f=modeFixture({noProof:true});await rejected(f,'chip_unconfirmed');eq(f.time,30000);eq(f.choices,1);
  f=modeFixture({disabled:true,noProof:true,onSleep:f=>{if(f.time===29000)f.opener.disabled=false;}});
  await rejected(f,'chip_unconfirmed');eq(f.time,30000,'one total budget across all readiness phases');eq(f.choices,1);
  f=modeFixture({options:2});await rejected(f,'menu_ambiguous');eq(f.time,0);eq(f.choices,0);
  f=modeFixture({disabled:true,onSleep:f=>f.setBusy(true)});await rejected(f,'response_active');eq(f.time,250);eq(f.opens,0);
  f=modeFixture({draft:'other draft'});await rejected(f,'draft_changed');eq(f.time,0);eq(f.editor.textContent,'other draft');
  f=modeFixture({disabled:true,onSleep:f=>{f.editor.textContent='new user draft';}});
  await rejected(f,'draft_changed');eq(f.time,250);eq(f.editor.textContent,'new user draft');eq(f.opens,0);
  f=modeFixture({disabled:true});await rejected(f,'owner_changed',true,'',()=>f.time===0);eq(f.time,250);eq(f.opens,0);
  f=modeFixture({disabled:true,onSleep:f=>f.cancel()});
  await assert.rejects(f.c.setChatGPTImageTool(true),error=>error.name==='AbortError');cases++;eq(f.time,250);eq(f.opens,0);
  f=modeFixture({selected:true,onSleep:f=>{f.c.chatGPTImageToolChip().disabled=false;}});f.c.chatGPTImageToolChip().disabled=true;
  await f.c.setChatGPTImageTool(false);eq(f.time,250);eq(f.removes,1);
  f=modeFixture({selected:true,noRemove:true});await rejected(f,'chip_unconfirmed',false);eq(f.removes,1,'removal is not repeatedly clicked');
}
function sendTests(){
  const document=documentFixture(),form=document.querySelector('form'),editor=form.querySelector('[contenteditable]');
  const b=new Element('button',{type:'submit','data-testid':'composer-submit-button',title:'Stop generating'});form.append(b);
  const c=vm.createContext({document,String,Boolean,IS_GEMINI:false,composer:()=>editor,
    getComputedStyle:e=>({display:e.hidden?'none':'block',visibility:'visible'}),
    visible:e=>Boolean(e?.isConnected)&&!e.hidden});
  vm.runInContext(part('  function isStopGenerationButton(', '  function imageGenerationSignature(')
    +part('  function resolveChatGPTComposerSendTarget(', '  function sendButton(')
    +part('  function sendButton(', '  async function waitForStableSendDraft('),c);
  for(const [attribute,label] of [['title','Stop generating'],['aria-label','หยุด'],['data-testid','stop-button']]){
    b.removeAttribute('title');b.removeAttribute('aria-label');b.setAttribute('data-testid','composer-submit-button');b.setAttribute(attribute,label);
    eq(c.sendButton(),null,'Stop never Send');eq(c.stopButton(),b,'same control counts as active');
  }
  b.removeAttribute('title');b.setAttribute('data-testid','composer-submit-button');b.setAttribute('aria-label','ส่ง');
  eq(c.sendButton(),b,'real Thai Send supported');eq(c.stopButton(),null);
  b.setAttribute('aria-label','หยุด');eq(c.sendButton(),null,'Send morphing to Stop vetoed');
}
async function generationTests(){
  let time=0,busy=false,sends=0,stops=0,toolSelections=0;
  const events=[],image={src:'https://chatgpt.com/backend-api/estuary/content?id=result',currentSrc:'https://chatgpt.com/backend-api/estuary/content?id=result',complete:true,naturalWidth:941,naturalHeight:1672};
  const editor={},proof={prompt:'scene',conversation_url:'https://chatgpt.com/c/fixture'};
  const c=vm.createContext({Date:{now:()=>time},Set,String,Boolean,Math,Number,Error,
    SmartFlowSingleAnswer:{wrap:value=>value},
    IS_GEMINI:false,AI_NAME:'ChatGPT Web',CHATGPT_IMAGE_STALL_WARNING_MS:90000,CHATGPT_IMAGE_STALL_ABORT_MS:180000,
    assertNotCancelled:()=>{},waitForResponseIdle:async()=>{},setChatGPTImageTool:async()=>toolSelections++,
    waitForComposer:async()=>editor,userTurns:()=>[],assistantTurns:()=>[],lastUserTurnSignature:()=>'',
    generatedImageElements:()=>sends?[image]:[],storyImageAssetKey:i=>i.src,chatGPTConversationFrames:()=>[],
    storyTurnNumber:()=>0,conversationTurnNumber:()=>2,setComposerText:async()=>editor,sendButton:()=>({}),
    recordStoryImageRequest:async()=>{},sendAndVerify:async()=>{sends++;busy=true;return proof;},
    report:async(...args)=>events.push(args),sleep:async ms=>{time+=ms;if(time>=150000)busy=false;if(time>200000)throw Error('fixture stuck');},
    stopButtonVisible:()=>busy,stopButton:()=>({click:()=>stops++}),
    createStoryImageWaitMonitor:()=>({observe:async()=>({busy})}),
    chatGPTStoryImageSnapshot:()=>({turn:null,images:[image],reason:'image_ready'}),
    chatGPTFrameAssistant:()=>null,imageGenerationSignature:()=>String(time),
    storyImageNoResultReady:()=>false,confirmedStoryImageServiceError:()=>false,document:{},motionResponseState:()=>({completed:false})});
  vm.runInContext(part('  async function submitImagePrompt(', '  async function imageData('),c);
  const result=await c.submitImagePrompt('scene',[],0,'',{scene_index:1});
  eq(result,image);eq(sends,1,'one accepted request while slow image generates');eq(stops,0,'no Stop even after old45s preview grace');
  eq(time>=150000,true,'wait for provider idle, not progressively decoded preview');eq(toolSelections,2,'tool verified before and after editor replacement');
  eq(events.some(e=>e[0]==='image_ready_before_idle'),false);
  // Actual compatibility helper must now passively wait rather than click Stop.
  time=0;busy=true;stops=0;
  c.sleep=async ms=>{time+=ms;if(time>=8000)busy=false;};
  c.refreshCompletedChatGPTMotion=async()=>{throw Error('unexpected refresh');};
  vm.runInContext(part('  async function stopStalledChatGPTGeneration(', '  function assertNotCancelled('),c);
  eq(await c.stopStalledChatGPTGeneration('wait',0),true);eq(stops,0);eq(time>=8000,true);
  const checkpoint=part("        await report('image_checkpoint_saved'",'        lastCompletedImageCount =');
  eq(checkpoint.includes('stopStalledChatGPTGeneration'),false,'checkpoint never cancels provider');
  eq(checkpoint.includes('await waitForResponseIdle'),true,'checkpoint waits before next scene');
}
(async()=>{await modeTests();await hydrationTests();sendTests();await generationTests();console.log(JSON.stringify({ok:true,cases,providerSubmissions:0}));})().catch(e=>{console.error(e);process.exit(1);});
