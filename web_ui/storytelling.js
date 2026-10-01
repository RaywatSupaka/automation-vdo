/* Shared new-job brief; never reads form defaults when resuming a saved job. */
(() => {
  const modes=[['narrator','ผู้บรรยายเล่าเรื่อง','เล่าเหตุการณ์ให้คนดูฟัง'],['solo','ตัวละครพูดเอง','ผู้พูดหลักคนเดียว ไม่มีผู้บรรยาย'],
    ['dialogue','ตัวละครสนทนา','พูดโต้ตอบและแสดงปฏิกิริยา'],['visual','เล่าเรื่องด้วยภาพ','ไม่มีบทพูด ใช้การกระทำและบรรยากาศ']];
  const examples={narrator:'เล่าด้วยภาษาง่าย กระชับ เปิดด้วยเหตุการณ์ชวนสงสัย ค่อย ๆ คลายปมและจบอย่างอบอุ่น',
    solo:'ให้ตัวละครหลักพูดเหมือนเล่าให้เพื่อนฟัง ใช้คำสั้น ๆ เป็นธรรมชาติ มีจังหวะลังเลและตัดสินใจ',
    dialogue:'ให้ตัวละครโต้ตอบสั้น ๆ อย่างเป็นธรรมชาติ เปิดด้วยความเข้าใจผิด แล้วค่อยเผยเหตุผลผ่านบทสนทนา',
    visual:'เล่าผ่านสีหน้า ท่าทาง และรายละเอียดรอบตัว ค่อย ๆ เผยปมด้วยภาพและจบด้วยการกระทำที่ชัดเจน'};
  const panels=new Map(), label=mode=>modes.find(m=>m[0]===mode)?.[1]||'';
  const structures=new Map();
  let disclosure=null;
  window.storytellingModeFor=key=>panels.get(key)?.read().mode;
  window.storytellingLabelFor=key=>label(window.storytellingModeFor(key));
  function options(items){return items.map(([value,text])=>`<option value="${value}">${text}</option>`).join('');}
  for(const [key,anchorId] of [['story','story-text'],['story-batch','story-batch-direction'],['drama','drama-premise']]){
    const anchor=document.getElementById(anchorId);if(!anchor)continue;
    const panel=document.createElement('fieldset');panel.className='storytelling-panel';panel.dataset.storytelling=key;
    panel.innerHTML=`<legend>วิธีเล่าและเสียง</legend>
      <label class="field storytelling-speaker"><span>ใครเป็นคนพูด</span><select name="storytelling-${key}" data-telling="mode" aria-describedby="${key}-speaker-hint">${options(modes)}</select></label>
      <p class="storytelling-intro" id="${key}-speaker-hint" aria-live="polite"></p><p class="storytelling-warning" role="status" hidden></p>
      <details class="storytelling-advanced"><summary>ปรับแต่งเพิ่มเติม <small class="storytelling-advanced-state"></small></summary><div class="storytelling-advanced-fields">
      <small class="storytelling-advanced-note">ตัวช่วยเสริมสำหรับบทใหม่ • ข้อความที่คุณพิมพ์เป็นแนวทางหลัก แต่ไม่เปลี่ยนผู้พูดหรือผู้สร้างวิดีโอที่เลือกไว้</small>
      <label class="field"><span>โทนเรื่อง</span><select data-telling="tone">${options([['auto','ให้ AI เลือกตามเรื่อง'],['comedy','ตลก'],['warm','อบอุ่น'],['drama','ดราม่า'],['mystery','ลึกลับ']])}</select></label>
      <label class="field"><span>เปิดเรื่อง</span><select data-telling="hook">${options([['auto','ตามเนื้อเรื่อง'],['event','เปิดด้วยเหตุการณ์'],['question','เปิดด้วยคำถาม'],['anomaly','เปิดด้วยสิ่งผิดปกติ']])}</select></label>
      <label class="field"><span>ตอนจบ</span><select data-telling="ending">${options([['auto','ตามลำดับตอน'],['resolved','จบเรื่องสมบูรณ์'],['twist','หักมุม'],['cliffhanger','ทิ้งปมให้ติดตาม']])}</select></label>
      <label class="check-row"><input type="checkbox" data-telling="cta_enabled"><span>ชวนติดตามท้ายเรื่อง <small>ปิดไว้เพื่อให้จบเหมือนละคร</small></span></label></div></details>
      <small>ใช้กับงานใหม่ • งานที่ทำต่อยึดค่าที่บันทึกไว้ • ซับบนจอตั้งแยกในส่วนเสียง</small>`;
    anchor.closest('label').after(panel);
    const help=document.createElement('details');help.className='storytelling-writing-help';
    help.innerHTML='<summary>ดูตัวอย่างการพิมพ์แนวทาง</summary><p class="storytelling-example"></p><button type="button" class="button ghost compact">เพิ่มตัวอย่างในช่องพิมพ์</button><small role="status"></small>';
    panel.before(help);
    help.querySelector('button').addEventListener('click',()=>{
      const example=examples[read().mode];
      if(!anchor.value.includes(example)){
        anchor.value+=(anchor.value? '\n\n':'')+example;
        anchor.dispatchEvent(new Event('input',{bubbles:true}));
        help.querySelector('[role=status]').textContent='เพิ่มตัวอย่างแล้ว • ข้อความเดิมยังอยู่ แก้ไขต่อได้';
      }else help.querySelector('[role=status]').textContent='มีตัวอย่างนี้อยู่แล้ว • ไม่เพิ่มซ้ำ';
      anchor.focus();
    });
    if(key!=='drama'&&window.mountCreativePicker){
      const structureHost=document.createElement('div');structureHost.className='storytelling-structure';
      panel.querySelector('.storytelling-advanced-note').after(structureHost);
      structures.set(key,window.mountCreativePicker({host:structureHost,kind:'story',id:key+'-structure',value:'legacy',label:'โครงเรื่อง',onChange:refreshAdvancedSummary}));
    }
    const find=s=>panel.querySelector(s);let previousAudio=null,previousSpeakingAudio=null,lastMode='narrator';
    function read(){return {version:1,mode:find('[data-telling=mode]').value,tone:find('[data-telling=tone]').value,
      hook:find('[data-telling=hook]').value,ending:find('[data-telling=ending]').value,cta_enabled:find('[data-telling=cta_enabled]').checked};}
    function refreshAdvancedSummary(){
      const selected=read(),count=['tone','hook','ending'].filter(key=>selected[key]!=='auto').length
        +Number(selected.cta_enabled)+Number(!!structures.get(key)&&structures.get(key).get()!=='legacy');
      find('.storytelling-advanced-state').textContent=count?`ตั้งไว้ ${count} รายการ`:'';
    }
    function refresh(){
      const selected=read(),acting=selected.mode!=='narrator',speaking=['solo','dialogue'].includes(selected.mode);
      if(lastMode!==selected.mode){
        const current=window.mediaAudioChoice?.(key);
        if(lastMode==='narrator'&&acting)previousAudio=current?{...current}:null;
        if(['solo','dialogue'].includes(lastMode)&&selected.mode==='visual')previousSpeakingAudio=current?{...current}:null;
        if(selected.mode==='visual')window.setMediaAudioChoice?.(key,{...current,mode:'none',subtitle:false,keep_video_audio:false,allow_silent:false});
        else if(speaking&&lastMode==='visual')window.setMediaAudioChoice?.(key,{...(previousSpeakingAudio||current),mode:key==='drama'&&previousSpeakingAudio?.mode==='api'?'api':'flow_original',subtitle:false,keep_video_audio:false,allow_silent:false});
        else if(speaking&&lastMode==='narrator')window.setMediaAudioChoice?.(key,{...current,mode:'flow_original',subtitle:false,keep_video_audio:false,allow_silent:false,video_audio_volume:100});
        else if(selected.mode==='narrator'&&previousAudio){window.setMediaAudioChoice?.(key,previousAudio);previousAudio=null;}
        lastMode=selected.mode;
      }
      find('.storytelling-intro').textContent=modes.find(mode=>mode[0]===selected.mode)[2]+(key==='drama'?' • ใช้รูปแบบเดียวกันทุก EP':'');
      help.querySelector('.storytelling-example').textContent=examples[selected.mode];
      help.querySelector('[role=status]').textContent='';
      find('[data-telling=cta_enabled]').disabled=selected.mode==='visual';
      if(selected.mode==='visual')find('[data-telling=cta_enabled]').checked=false;
      const provider=document.getElementById(key+'-video-mode')?.value;
      const unsupported=speaking&&!['google_flow','meta_ai'].includes(provider);
      const warning=find('.storytelling-warning');warning.hidden=!unsupported;
      warning.textContent='โหมดตัวละครพูดต้องใช้ Google Flow หรือ Meta AI • ละครสั้นเลือกเสียงจากคลิปหรือพากย์ SmartSub แยกตัวละครได้';
      refreshAdvancedSummary();
      window.refreshMediaAudio?.(key);
      if(key==='drama'){
        refreshDramaVoices();
        if(acting&&disclosure)disclosure.open=true;
      }
    }
    panels.set(key,{read,refresh,set(value){find('[data-telling=mode]').value=value.mode;
      for(const field of ['tone','hook','ending'])find(`[data-telling=${field}]`).value=value[field];
      find('[data-telling=cta_enabled]').checked=!!value.cta_enabled;refresh();}});
    panel.addEventListener('change',refresh);document.getElementById(key+'-video-mode')?.addEventListener('change',refresh);
    // Audio locates its own legacy adapter by form identity, not the provider's
    // next sibling (Flow/cover/intro controls also mount at that anchor).
    refresh();
  }
  window.prepareStorytellingBatch=()=>{
    panels.get('story-batch')?.set(panels.get('story').read());
    window.setMediaAudioChoice?.('story-batch',window.mediaAudioChoice('story'));
    if(structures.has('story-batch'))structures.get('story-batch').set(structures.get('story').get());
    window.setGeneratedMusicChoice?.('story-batch',window.generatedMusicChoice?.('story'));
    panels.get('story-batch')?.refresh();
  };
  function refreshDramaVoices(){
    const dubbed=window.mediaAudioChoice?.('drama')?.mode==='api'&&window.storytellingModeFor?.('drama')!=='visual';
    const fields=[...document.querySelectorAll('[id^="drama-character-"][id$="-voice"]')];
    fields.forEach(node=>{node.closest('label').hidden=!dubbed;});
    const note=document.getElementById('drama-cast-voice-note');
    if(note){note.hidden=!dubbed&&!fields.some(node=>node.value);note.textContent=dubbed
      ? 'พากย์ SmartSub: เลือกเสียงรายตัวละครได้ • โปรแกรมเพิ่มเสียงหลังสร้างภาพ ไม่ซิงก์ปากอัตโนมัติ'
      : 'เสียงรายตัวละครที่เลือกไว้จะไม่ถูกใช้ในโหมดเสียงจากคลิปหรือภาพล้วน';}
  }
  document.addEventListener('change',refreshDramaVoices);
  disclosure=document.querySelector('.drama-character-disclosure');
  if(disclosure){
    disclosure.open=false;
    disclosure.querySelector('summary small').textContent='ไม่บังคับสำหรับผู้บรรยาย • โหมดตัวละครสนทนาต้องมีอย่างน้อย 2 คน';
    const grid=disclosure.querySelector('.character-grid'),template=grid.children[1];
    const voiceNote=document.createElement('small');voiceNote.id='drama-cast-voice-note';voiceNote.hidden=true;grid.before(voiceNote);
    const error=document.createElement('p');error.className='field-error';error.id='drama-cast-error';error.hidden=true;error.setAttribute('role','alert');grid.before(error);
    grid.addEventListener('input',()=>{error.hidden=true;});
    for(const index of [3,4]){
      const card=template.cloneNode(true);card.hidden=true;
      card.querySelector('header i').textContent=String.fromCharCode(64+index);
      for(const node of card.querySelectorAll('[id]'))node.id=node.id.replace('character-2-','character-'+index+'-');
      card.querySelector('[data-drama-image]').dataset.dramaImage=String(index);
      for(const input of card.querySelectorAll('input,textarea'))input.value='';
      const file=card.querySelector('input[type=file]'),button=card.querySelector('[data-drama-image]');
      button.addEventListener('click',()=>{file.value='';file.click();});
      file.addEventListener('change',async()=>{if(!file.files[0])return;button.disabled=true;
        try{const result=await uploadReferenceImage(file.files[0],'drama');ui.dramaImages[index]=result.asset_id?`asset:${result.asset_id}`:result.path;
          card.querySelector(`[id$="-image"]`).value=ui.dramaImages[index];card.querySelector(`[id$="-image-name"]`).textContent=file.files[0].name;
          const preview=card.querySelector('img');if(preview.dataset.objectUrl)URL.revokeObjectURL(preview.dataset.objectUrl);
          preview.src=preview.dataset.objectUrl=URL.createObjectURL(file.files[0]);preview.hidden=false;
        }catch(error){toast(error.message,'error');}finally{button.disabled=false;}});
      grid.append(card);
    }
    if(!template.querySelector('input').value)template.hidden=true;
    const add=document.createElement('button');add.type='button';add.className='button secondary compact';add.textContent='＋ เพิ่มตัวละคร';
    add.addEventListener('click',()=>{const next=[...grid.children].find(c=>c.hidden);if(next){next.hidden=false;next.querySelector('input').focus();}
      add.disabled=![...grid.children].some(c=>c.hidden);refreshDramaVoices();});grid.after(add);
  }
  const dramaEpisodes=document.getElementById('drama-episodes'),dramaScenes=document.getElementById('drama-scenes'),dramaWorkload=document.getElementById('drama-workload-summary');
  const updateDramaWorkload=()=>{if(!dramaEpisodes||!dramaScenes||!dramaWorkload)return;const episodes=Number(dramaEpisodes.value||1),scenes=Number(dramaScenes.value||6);dramaWorkload.textContent=`${episodes} EP × ${scenes} ฉาก = ${episodes*scenes} ฉากโดยประมาณ • ทำทีละตอนและบันทึกจุดต่อเนื่อง`;};
  dramaEpisodes?.addEventListener('input',updateDramaWorkload);dramaScenes?.addEventListener('input',updateDramaWorkload);updateDramaWorkload();
  const aside=document.querySelector('.drama-options-card');
  if(aside){
    const advanced=document.createElement('details');advanced.className='workflow-disclosure drama-render-advanced';
    advanced.innerHTML='<summary>ภาพ เสียง และการประกอบเพิ่มเติม</summary>';aside.append(advanced);
    for(const id of ['drama-timing','drama-tail','drama-cover-theme']){const field=document.getElementById(id)?.closest('label');if(field)advanced.append(field);}
    for(const selector of ['.drama-footage-picker','#drama-presenter-anchor']){const node=aside.querySelector(selector);if(node)advanced.append(node);}
    const continuity=aside.querySelector('.continuity-card span');if(continuity)continuity.textContent='ส่งข้อมูลตัวละคร ภาพ และเหตุการณ์ต่อไปยัง EP ถัดไป • ตรวจผลจริงใน Storyboard';
    const auto=aside.querySelector('.story-auto-list');if(auto)auto.hidden=true;
  }
  const queueButton=document.getElementById('drama-queue-toggle');
  if(queueButton){queueButton.hidden=true;const note=queueButton.nextElementSibling;if(note?.classList.contains('usability-note'))note.hidden=true;
    const go=document.createElement('button');go.type='button';go.className='button ghost compact';go.dataset.page='creation';go.textContent='ดูและจัดการคิวสร้างคลิป →';queueButton.after(go);}
  const original=postAction;
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey?.(action,payload);
    if(panels.has(key)&&!payload.job_id&&!payload.creative_context&&!payload.long_video&&!payload.flow_smoke_test&&action!=='creation_edit'){
      const selected=panels.get(key).read(),provider=payload.video_generation_mode||payload.render_options?.video_generation_mode;
      if(['solo','dialogue'].includes(selected.mode)&&!['google_flow','meta_ai'].includes(provider))throw Error('กรุณาเลือก Google Flow หรือ Meta AI สำหรับโหมดตัวละครพูด');
      if(key==='drama'){
        const count=(payload.characters||[]).length,needed=selected.mode==='narrator'?0:selected.mode==='dialogue'?2:1;
        if(count<needed){
          const message=`กรุณาเพิ่มตัวละครอย่างน้อย ${needed} คนสำหรับรูปแบบนี้`;
          if(disclosure){disclosure.open=true;const error=document.getElementById('drama-cast-error');error.textContent=message;error.hidden=false;
            const card=disclosure.querySelectorAll('.character-card')[Math.min(count,3)];if(card){card.hidden=false;card.querySelector('input').focus();}}
          throw Error(message);
        }
      }
      payload={...payload,storytelling_options:{...selected},actor_dialogue:selected.mode!=='narrator'};
      const structure=structures.get(key)?.get();
      if(structure&&structure!=='legacy')payload.story_structure_options={version:1,structure};
      if(payload.render_options)payload.render_options={...payload.render_options,storytelling_options:{...selected}};
    }
    return original(action,payload);
  };
  if(typeof window.renderDramaSeries==='function'){
    const render=window.renderDramaSeries;
    window.renderDramaSeries=(...args)=>{
      render(...args);
      document.querySelectorAll('.drama-series-item .drama-series-actions').forEach(actions=>{
        const secondary=[...actions.querySelectorAll('[data-open-series],[data-cancel-drama-series]')];
        if(!secondary.length)return;
        const menu=document.createElement('details');menu.className='drama-manage-menu';
        const summary=document.createElement('summary');summary.textContent='จัดการ';summary.className='button ghost compact';menu.append(summary);
        const content=document.createElement('div');content.className='drama-manage-items';content.append(...secondary);menu.append(content);actions.append(menu);
      });
    };
  }
  refreshDramaVoices();
})();
