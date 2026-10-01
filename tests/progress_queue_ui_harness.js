const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web_ui/app.js'), 'utf8');

function fixture() {
  const nodes = new Map(), timers = new Map(), calls = [];
  let nextTimer = 0;
  function element() {
    const classes = new Set(), descendants = new Map();
    return {open:false, disabled:false, textContent:'', innerHTML:'', style:{}, dataset:{}, value:'all', listeners:{}, showCalls:0,
      classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),
        toggle(c, enabled) {if (enabled) classes.add(c); else classes.delete(c);}},
      setAttribute(k,v){this[k]=v;}, focus(){}, before(){},
      querySelector(selector){
        // Resolve the actual class in this element's assigned markup. Missing
        // modal children remain null, matching native DOM rather than masking it.
        if(!/^\.[a-z][a-z0-9-]*$/i.test(selector))return null;
        const matches=[...this.innerHTML.matchAll(/<[a-z][^>]*\bclass=["']([^"']*)["'][^>]*>/gi)]
          .some(match=>match[1].split(/\s+/).includes(selector.slice(1)));
        if(!matches)return null;
        if(!descendants.has(selector))descendants.set(selector,element());
        return descendants.get(selector);
      },
      addEventListener(k,fn){this.listeners[k]=fn;},
      showModal(){this.open=true;this.showCalls++;},
      close(){this.open=false;this.listeners.close?.();},
      click(){return this.listeners.click?.({target:this,currentTarget:this});},
      closest(){return this;}
    };
  }
  const $ = key => {if (!nodes.has(key)) nodes.set(key,element()); return nodes.get(key);};
  const ui = {state:null,progressType:'',progressJobId:'',progressWasActive:false,progressResultReady:false,
    progressCloseTimer:null,progressMinimized:false};
  const context = {ui,$,$$:()=>[],document:{createElement:element,body:{append(){}},querySelector:$,querySelectorAll:()=>[]},
    console,progressSteps:()=>'',toast(){},addEventListener(){},clearTimeout:id=>timers.delete(id),
    setTimeout:fn=>{timers.set(++nextTimer,fn); return nextTimer;},
    escapeHtml:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    selectedAiModel:()=> 'auto',storyStylePayload:()=>({}),showPage(){},openDetail(){},CSS:{escape:v=>v},
    postAction:async(action,payload)=>{calls.push({action,payload});return {ok:true};},poll:async()=>{}};
  context.window=context;
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function minimizeProgress()'),source.indexOf('function renderNotice(state)')),context);
  for (const prefix of ["$('#progress-close').", "$('#progress-minimized').", "$('#progress-modal')."]) {
    vm.runInContext(source.split('\n').find(line=>line.startsWith(prefix)),context);
  }
  return {context,ui,$,calls,timers};
}
const inactive = () => ({active:false,percent:0,job_id:'',message:''});
function state(type='product',id='JOB-A',percent=42,active=true) {
  return {product_progress:inactive(),story_progress:inactive(),system:{status:active?'running':'stopped'},
    [`${type}_progress`]:{active,percent,job_id:id,message:'กำลังทำงาน',detail:''}};
}

async function main() {
  {
    const {context:c,ui,$}=fixture();
    c.renderProgress(state());
    assert.equal($('#progress-modal').showCalls,1);
    await $('#progress-close').click();
    for(let i=0;i<30;i++) c.renderProgress(state('product','JOB-A',42+i));
    assert.equal($('#progress-modal').open,false);
    assert.equal($('#progress-modal').showCalls,1,'heartbeat must not reopen minimized popup');
    assert.equal($('#progress-minimized').classList.contains('hidden'),false);
    await $('#progress-minimized').click();
    assert.equal($('#progress-modal').open,true);
    let prevented=false;
    $('#progress-modal').listeners.cancel({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);
    c.renderProgress(state());
    assert.equal($('#progress-modal').open,false,'Escape is a durable minimize too');
    c.renderProgress(state('product','JOB-A',100,false));
    assert.equal(ui.progressResultReady,false);
    assert.equal($('#progress-modal').open,false,'completion respects minimize');
    assert.equal($('#progress-minimized').classList.contains('hidden'),true,'completed mini-button is removed');
    await $('#progress-minimized').click();
    assert.equal($('#progress-modal').open,false,'stale click cannot restore completed popup');
    await $('#progress-close').click();
    c.renderProgress(state('story','STORY-NEXT',10));
    assert.equal($('#progress-modal').open,false,'next FIFO job must not undo manual minimize');
  }
  {
    for(const type of ['product','story']){
      const {context:c,ui,$,timers}=fixture();
      c.renderProgress(state(type,'CURRENT',99));
      c.renderProgress(state(type,'CURRENT',100,true));
      assert.equal($('#progress-modal').open,true,'100 percent while still active is not Final');
      c.renderProgress(state(type,'CURRENT',100,false));
      assert.equal($('#progress-modal').open,false);
      assert.equal(ui.progressResultReady,false);
      assert.equal(timers.size,0,'no delayed close races with next queue item');
      for(let n=0;n<10;n++)c.renderProgress(state(type,'CURRENT',100,false));
      assert.equal($('#progress-modal').showCalls,1,'completed heartbeat cannot reopen dialog');
      c.renderProgress(state(type,'NEXT',1));
      assert.equal($('#progress-modal').open,true,'new active queue item remains visible');
    }
  }
  {
    const {context:c,ui,$}=fixture();
    c.renderProgress(state('story','STORY-CURRENT'));
    const cancelled=state('story','STORY-CURRENT',40,false);
    cancelled.product_progress={active:false,percent:100,job_id:'JOB-OLD',message:'WRONG RESULT'};
    c.renderProgress(cancelled);
    assert.equal(ui.progressResultReady,false);
    assert.equal($('#progress-modal').open,false);
    assert.notEqual($('#progress-message').textContent,'WRONG RESULT');
    c.renderProgress(state('product','JOB-A'));
    c.renderProgress(state('product','JOB-OTHER',100,false));
    assert.equal(ui.progressResultReady,false,'even same provider requires exact Job');
  }
  {
    const {context:c,ui,$,calls}=fixture();
    vm.runInContext(fs.readFileSync(path.join(root,'web_ui/creation_queue.js'),'utf8'),c);
    ui.state={...state('product','',0,false),creation_queue:{items:[],counts:{queued:1,failed:1},paused:true,
      unfinished_count:2,cancelable_count:2,can_clear_stuck_state:true,
      recoverable_jobs:[{mode:'story',job_id:'STORY-OLD',title:'<unsafe>'}]}};
    c.renderCreationQueue(ui.state);
    assert.equal($('#creation-resume-unfinished').disabled,false);
    assert.match($('#creation-old-list').innerHTML,/&lt;unsafe&gt;/);
    await $('#creation-resume-unfinished').click();
    assert.equal(calls.at(-1).action,'creation_resume_unfinished');
    await $('#creation-cancel-all').click();
    assert.equal(calls.length,1,'bulk cancel needs confirmation');
    await $('#creation-confirm-close').click();
    assert.equal(calls.length,1,'closing confirmation does not cancel jobs');
    await $('#creation-cancel-all').click();
    await $('#creation-confirm-accept').click();
    assert.equal(calls.at(-1).action,'creation_cancel_all');
    await $('#creation-clear-cache').click();
    await $('#creation-confirm-accept').click();
    assert.equal(calls.at(-1).action,'creation_clear_stuck_state');
    assert.equal(ui.progressWasActive,false);
    ui.state.creation_queue.can_clear_stuck_state=false;
    c.renderCreationQueue(ui.state);
    assert.equal($('#creation-clear-cache').disabled,true,'busy workers prevent clear');
    const button={dataset:{resumeJob:'STORY-OLD'},disabled:false,closest(selector){return selector.includes('data-dismiss-job')?null:this;}};
    await $('#creation-old-list').listeners.click({target:button});
    assert.equal(calls.at(-1).action,'creation_resume_jobs');
    assert.deepEqual(Array.from(calls.at(-1).payload.job_ids),['STORY-OLD']);
  }
  {
    const {context:c,ui,$,calls}=fixture(), opened=[];
    c.openClipCover=async id=>opened.push(id);
    vm.runInContext(fs.readFileSync(path.join(root,'web_ui/creation_queue.js'),'utf8'),c);
    const row={queue_id:'CQ-COVER',mode:'story',job_id:'STORY-COVER',status:'queued'};
    const saved={item_id:'story:STORY-COVER',job_id:row.job_id,size_bytes:100,
      ai_cover_state:{phase:'needs_review'}};
    ui.state={library:[saved],creation_queue:{items:[row],counts:{queued:1},paused:true,
      pause_reason:'ai_cover_needs_attention'}};
    const click=async()=>$('#creation-list').listeners.click({target:{disabled:false,
      dataset:{cq:'cover',id:row.queue_id},closest(){return this;}}});
    c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/data-cq="cover"[^>]*>จัดการปก AI</);
    await click();
    assert.deepEqual(opened,['story:STORY-COVER']);
    assert.equal(calls.length,0,'opening a cover never resumes, regenerates or dispatches queue commands');
    // A library-only heartbeat must invalidate the row controls too.
    saved.ai_cover_state.phase='ready';
    c.renderCreationQueue(ui.state);
    assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/);
    await click();
    assert.equal(opened.length,1,'stale cover controls recheck the latest saved state');
    assert.equal(calls.length,0,'stale cover action must not fall through to creation_cover');
    const oldError='วิดีโอเสร็จแล้ว • พักคิวรอปก AI • ตรวจปกในคลังวิดีโอแล้วกด Run Queue ต่อ • AI_IMAGE_REFERENCE_UNCONFIRMED 0/2';
    row.error=oldError;saved.ai_cover_state.request_id='saved-cover';
    saved.cover_revision='saved-cover';saved.cover_url='/api/desktop/media?kind=cover';
    c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/ปก AI บันทึกแล้ว • กด Run Queue เพื่อทำคิวต่อ/);
    assert.doesNotMatch($('#creation-list').innerHTML,/AI_IMAGE_REFERENCE_UNCONFIRMED/);
    assert.equal(row.error,oldError,'recovered presentation preserves the original queue error ledger');
    saved.cover_url='';c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/AI_IMAGE_REFERENCE_UNCONFIRMED/,'ready state alone cannot hide the error');
    saved.cover_url='/api/desktop/media?kind=cover';saved.cover_revision='old-cover';c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/AI_IMAGE_REFERENCE_UNCONFIRMED/,'old/manual cover is not proof of this request');
    saved.cover_revision='saved-cover';row.error='UNRELATED_FLOW_ERROR';c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/UNRELATED_FLOW_ERROR/,'successful cover cannot hide an unrelated error');
    row.error=oldError;
    for(const phase of ['queued','claimed','running','ready','']){
      saved.ai_cover_state.phase=phase;c.renderCreationQueue(ui.state);
      assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/,phase);
    }
    saved.ai_cover_state.phase='cancelled';c.renderCreationQueue(ui.state);
    assert.match($('#creation-list').innerHTML,/data-cq="cover"/,'cancelled cover may be inspected');
    for(const status of ['completed','cancelled']){
      row.status=status;c.renderCreationQueue(ui.state);
      assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/,'terminal queue is not reopened');
    }
    row.status='queued';saved.ai_cover_state.phase='needs_review';
    for(const size of [0,undefined]){
      saved.size_bytes=size;c.renderCreationQueue(ui.state);
      assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/,'nonempty saved Final is required');
    }
    saved.size_bytes=100;ui.state.library=[];c.renderCreationQueue(ui.state);
    assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/,'missing saved Final is excluded');
    ui.state.library=[saved];
    for(const [mode,job,id] of [['product','JOB-COVER','product:JOB-COVER'],
      ['story','STORY-COVER','story:STORY-COVER'],['drama','STORY-DRAMA','story:STORY-DRAMA']]){
      Object.assign(row,{mode,job_id:job});Object.assign(saved,{job_id:job,item_id:id});
      c.renderCreationQueue(ui.state);assert.match($('#creation-list').innerHTML,/data-cq="cover"/);
      await click();assert.equal(opened.at(-1),id,'exact library identity preserves Drama story prefix');
    }
    for(const [mode,job,id] of [['product','STORY-COVER','product:STORY-COVER'],
      ['drama','JOB-COVER','story:JOB-COVER'],['unknown','STORY-COVER','story:STORY-COVER']]){
      Object.assign(row,{mode,job_id:job});Object.assign(saved,{job_id:job,item_id:id});
      c.renderCreationQueue(ui.state);assert.doesNotMatch($('#creation-list').innerHTML,/data-cq="cover"/);
    }
    assert.equal(calls.length,0,'all cover navigation is read-only');
  }
  assert.match(fs.readFileSync(path.join(root,'web_ui/index.html'),'utf8'),/creation_queue\.js\?v=\d+/);
  console.log('PASS: popup/queue controls, exact saved-cover navigation, library-only updates and recovered-error presentation');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
