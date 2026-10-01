/* One set of controls, used before immediate creation AND queue insertion. */
(() => {
  window.smartflowCreationFormKey=(action,payload={})=>{
    if(payload.job_id || window.productOptionSnapshot?.isFrozen(payload)
      || payload.creative_context?.kind==='product_story')return '';
    const fixed={create_product:'product',enqueue_long_video:'long',create_drama_series:'drama',enqueue_story_batch:'story-batch',creation_edit:'product-batch'};
    return fixed[action] || (action==='create_story'?(payload.long_video?'long':'story'):action==='creation_enqueue'?(payload.mode==='product'?'product-batch':'story'):'');
  };
  const panels = new Map();
  window.mediaAudioChoice=key=>panels.get(key)?.read();
  window.generatedMusicChoice=key=>panels.get(key)?.musicRead();
  window.setGeneratedMusicChoice=(key,value)=>panels.get(key)?.musicSet(value);
  window.setMediaAudioChoice=(key,value)=>panels.get(key)?.set(value);
  window.setMediaAudioProvider=(key,value)=>panels.get(key)?.provider(value);
  window.refreshMediaAudio=key=>panels.get(key)?.refresh();
  window.hydrateMediaAudioDefaults=settings=>{
    if(typeof settings?.subtitle_auto!=='boolean')return;
    for(const entry of panels.values())entry.defaults(settings.subtitle_auto);
  };
  function mount(key, selector, fixedFlow=false) {
    const anchor = document.querySelector(selector); if (!anchor) return;
    const panel = document.createElement('fieldset'); panel.className='media-audio-controls';
    panel.dataset.audioForm=key;
    panel.innerHTML=`<legend>เสียงและคำบรรยาย</legend>
      <div class="audio-heading"><div><strong>เลือกเสียงให้คลิปของคุณ</strong><small>ตั้งค่าสำหรับงานใหม่ • งานที่กดทำต่อใช้ค่าที่บันทึกไว้</small></div><span class="audio-badge">AUDIO STUDIO</span></div>
      <select data-main-audio hidden aria-label="เสียงหลัก"><option value="api">เสียงพากย์ API SmartSub</option><option value="flow_original">เสียงต้นฉบับจากคลิป</option><option value="none">ไม่ใช้เสียงหลัก</option></select>
      <div class="audio-mode-cards" role="radiogroup" aria-label="เลือกเสียงหลัก">
        <label class="audio-mode-card"><input type="radio" name="audio-mode-${key}" value="flow_original" data-audio-mode><span><b>เสียงต้นฉบับจากคลิป</b><small>ใช้เสียงพูดและบรรยากาศในวิดีโอ ไม่สร้างเสียงพากย์เพิ่ม</small></span></label>
        <label class="audio-mode-card"><input type="radio" name="audio-mode-${key}" value="api" data-audio-mode checked><span><b>เสียงพากย์ API SmartSub</b><small>สร้างเสียงพากย์จากบท ด้วยเสียงที่คุณตั้งไว้</small></span></label>
      </div>
      <small data-audio-capability></small>
      <div class="audio-settings-row" data-api-settings><span>ใช้เสียง SmartSub ที่บันทึกไว้กับงาน</span><button type="button" class="button ghost compact" data-page="voice">เลือกเสียง / ตั้งค่า SmartSub →</button></div>
      <div class="audio-section"><div class="audio-settings-row"><label><input type="checkbox" data-audio-subtitle checked> <b>คำบรรยาย</b></label><button type="button" class="button ghost compact" data-page="subtitle">รูปแบบ / ขนาด / ตำแหน่ง / พรีวิว →</button></div><small data-subtitle-source></small><small>หน้าพรีวิวใช้รูปแบบซับที่บันทึกไว้ • ไม่ใช่ผลถอดเสียงของคลิปนี้</small></div>
      <div class="audio-section"><div class="audio-settings-row"><b>เสียงประกอบ</b><button type="button" class="button ghost compact" data-page="audio">เลือกเพลง / ปรับระดับเสียง →</button></div><div class="media-audio-checks"><label><input type="checkbox" data-audio-music> เพลงพื้นหลังที่ตั้งไว้</label><label><input type="checkbox" data-audio-sfx> เอฟเฟกต์เสียง</label></div><small>ปุ่มนี้ควบคุมเสียงที่โปรแกรมเพิ่ม ไม่ลบเพลงหรือเสียงที่ฝังมากับคลิป</small></div>
      <details class="audio-advanced"><summary>ตัวเลือกเพิ่มเติม</summary><label><input type="radio" name="audio-mode-${key}" value="none" data-audio-mode> ไม่ใช้เสียงหลัก (เลือกเพลงและเอฟเฟกต์แยกได้)</label><div data-audio-mix-slot></div><label data-silent-wrap hidden><input type="checkbox" data-audio-silent> ยอมรับช่วงเงียบหากฉากไม่มีเสียง • ไม่ใช้เสียง API แทนอัตโนมัติ</label></details>
      <small class="audio-summary" data-audio-summary role="status" aria-live="polite"></small>`;
    if(key==='product-batch') anchor.before(panel); else (anchor.closest('label') || anchor).after(panel);
    const keepLabel=document.createElement('label');
    keepLabel.innerHTML='<input type="checkbox" data-audio-keep> เก็บเสียงต้นฉบับจากวิดีโอไว้ด้วย (ผสมเบา ๆ กับเสียงพากย์)';
    keepLabel.dataset.audioKeepWrap='';
    panel.querySelector('[data-audio-mix-slot]').append(keepLabel);
    const volumeLabel=document.createElement('label');volumeLabel.dataset.audioVolumeWrap='';
    volumeLabel.innerHTML='ระดับเสียงต้นฉบับจากคลิป <output data-audio-volume-value>35%</output><input aria-label="ระดับเสียงต้นฉบับจากคลิป" type="range" min="0" max="100" step="1" value="35" data-audio-volume><small>0% = ปิดเสียงคลิป • 100% = เสียงเดิม • ไม่ลดเสียงพากย์ API</small><small data-mix-warning>การผสมอาจทำให้เสียงพูดซ้อนกัน ระบบไม่ได้แยกเสียงพูดออกจากบรรยากาศ</small>';
    panel.querySelector('.audio-advanced').before(volumeLabel);
    const get = sel => panel.querySelector(sel);
    let defaultsHydrated=false,defaultsProtected=false;
    const musicBlock=document.createElement('details');musicBlock.className='audio-generated-music';
    musicBlock.innerHTML=`<summary>ดนตรีจาก AI <span data-generated-music-badge>ปิด</span></summary>
      <label class="generated-music-switch"><input type="checkbox" data-generated-music-enabled><span><b>เพิ่มดนตรีคลอบางฉากด้วย AI</b><small>สร้างเพลงเบา ๆ พร้อมวิดีโอ ไม่เพิ่มทุกฉาก • เมื่อใช้เสียงพากย์ จะเก็บเสียงจากวิดีโอไว้ผสมด้วย</small></span></label>
      <div data-generated-music-options hidden><div class="generated-music-grid"><label>อารมณ์เพลง<select data-generated-music-mood><option value="auto">ให้ AI เลือกตามเรื่อง</option><option value="warm">อบอุ่น</option><option value="bright">สดใส</option><option value="gentle_suspense">ลุ้นเบา ๆ</option><option value="tender">ซึ้ง</option></select></label><label>ความถี่<select data-generated-music-frequency><option value="sparse">น้อย</option><option value="moderate" selected>พอดี · ประมาณ 30%</option></select></label></div><small>สุ่มฉากครั้งเดียวและจำไว้เมื่อทำต่อ • ไม่มีเสียงร้อง • ความดังขึ้นอยู่กับผลที่ AI สร้าง ไม่ใช่แทร็กเพลงแยก</small></div>
      <small data-generated-music-status role="status"></small>`;
    get('.audio-advanced').before(musicBlock);
    let musicPreviousKeep=null;
    const musicRead=()=>({version:1,enabled:get('[data-generated-music-enabled]').checked,
      mood:get('[data-generated-music-mood]').value,frequency:get('[data-generated-music-frequency]').value});
    const musicSet=value=>{value=value||{};get('[data-generated-music-enabled]').checked=value.enabled===true;
      get('[data-generated-music-mood]').value=value.mood||'auto';get('[data-generated-music-frequency]').value=value.frequency||'moderate';
      musicBlock.open=value.enabled===true;musicPreviousKeep=null;refresh();};
    get('[data-generated-music-enabled]').addEventListener('change',()=>{
      const enabled=musicRead().enabled;
      if(enabled&&get('[data-main-audio]').value==='api'){
        musicPreviousKeep=get('[data-audio-keep]').checked;get('[data-audio-keep]').checked=true;
      }else if(!enabled&&musicPreviousKeep!==null){get('[data-audio-keep]').checked=musicPreviousKeep;musicPreviousKeep=null;}
      refresh();
    });
    get('[data-audio-keep]').addEventListener('change',()=>{musicPreviousKeep=null;});
    let actorToggle=null, previousAudio=null;
    if(['story','story-batch'].includes(key)){
      const block=document.createElement('div');block.className='audio-section';
      block.innerHTML='<label><input type="checkbox" data-actor-dialogue> <b>ตัวละครสนทนา — พูดโต้ตอบแบบละคร</b></label><small>เปิด: ตัวละครสนทนาภาษาไทย ไม่มีผู้บรรยาย ไม่มีซับ • ปิด: เล่าเรื่องแบบผู้บรรยายตามการตั้งค่าเสียง</small>';
      get('.audio-mode-cards').before(block);actorToggle=block.querySelector('input');
      actorToggle.addEventListener('change',()=>{
        // New storytelling owns these roles. Keep the legacy adapter inert even
        // when another module dispatches change on the hidden checkbox.
        if(window.storytellingModeFor?.(key)){refresh();return;}
        if(actorToggle.checked){previousAudio=read();get('[data-main-audio]').value='flow_original';get('[data-audio-subtitle]').checked=false;get('[data-audio-keep]').checked=false;get('[data-audio-silent]').checked=false;if(!panel.dataset.volumeChosen)get('[data-audio-volume]').value=100;}
        else if(previousAudio){get('[data-main-audio]').value=previousAudio.mode;get('[data-audio-subtitle]').checked=previousAudio.subtitle;get('[data-audio-keep]').checked=previousAudio.keep_video_audio;get('[data-audio-silent]').checked=previousAudio.allow_silent;get('[data-audio-volume]').value=previousAudio.video_audio_volume;previousAudio=null;}
        refresh();
      });
    }
    function read(){const mode=get('[data-main-audio]').value;return {mode,subtitle:get('[data-audio-subtitle]').checked,music:get('[data-audio-music]').checked,sfx:get('[data-audio-sfx]').checked,allow_silent:get('[data-audio-silent]').checked,keep_video_audio:mode==='api'&&get('[data-audio-keep]').checked,video_audio_volume:Number(get('[data-audio-volume]').value),...(musicRead().enabled?{generated_music_version:1}:{})};}
    function refresh(){
      const v=read(); const provider=panel.dataset.videoMode || anchor.value;
      const flow=fixedFlow || provider==='google_flow' || provider==='meta_ai';
      const generated=musicRead();
      get('[data-generated-music-enabled]').disabled=!flow&&!generated.enabled;
      get('[data-generated-music-options]').hidden=!generated.enabled;
      get('[data-generated-music-badge]').textContent=generated.enabled?'เปิด · บางฉาก':'ปิด';
      const musicError=!flow?'วิธีสร้างนี้ไม่มีขั้นเจนวิดีโอ • ใช้เพลงจากคลังแทนได้ในหน้าเสียงประกอบ':
        generated.enabled&&v.mode==='none'?'ดนตรี AI ต้องเก็บเสียงจากคลิป • เลือกเสียงต้นฉบับหรือเสียงพากย์พร้อมเก็บเสียงคลิป':
        generated.enabled&&v.music?'เปิดเพลงจากคลังอยู่ด้วย • เลือกใช้ดนตรีเพียงแหล่งเดียวก่อนเริ่ม':
        generated.enabled&&v.mode==='api'&&!v.keep_video_audio?'กรุณาเปิดเก็บเสียงต้นฉบับด้วย มิฉะนั้นดนตรี AI จะหายตอนรวมคลิป':'';
      get('[data-generated-music-status]').textContent=musicError;
      musicBlock.classList.toggle('has-conflict',Boolean(generated.enabled&&musicError));
      const telling=window.storytellingModeFor?.(key);
      const acting=telling? telling!=='narrator':!!actorToggle?.checked;
      const speaking=['solo','dialogue'].includes(telling)||(!telling&&acting);
      const visual=telling==='visual';
      if(visual&&!flow&&v.mode==='flow_original'){get('[data-main-audio]').value='none';v.mode='none';}
      const noSubtitles=visual||(!telling&&acting);
      get('[data-audio-subtitle]').disabled=noSubtitles;
      if(noSubtitles){get('[data-audio-subtitle]').checked=false;v.subtitle=false;}
      const legacySubtitle=document.getElementById(key+'-subtitle');
      if(legacySubtitle)legacySubtitle.checked=v.subtitle;
      if(actorToggle){actorToggle.closest('.audio-section').hidden=Boolean(telling);actorToggle.disabled=Boolean(telling)||(!flow&&!acting);}
      get('[data-audio-volume-wrap]').hidden=!flow || !(v.mode==='flow_original'||(v.mode==='api'&&v.keep_video_audio));
      get('[data-audio-volume-value]').textContent=v.video_audio_volume+'%';
      get('option[value="flow_original"]').disabled=!flow;
      for(const radio of panel.querySelectorAll('[data-audio-mode]')){
        radio.disabled=(radio.value==='flow_original'&&!flow)||
          (speaking&&(radio.value==='none'||(radio.value==='api'&&key!=='drama')))||
          (visual&&radio.value==='api');
        // An unsupported remembered choice stays blocked by validation; it is
        // not displayed as a simultaneously selected and disabled radio.
        radio.checked=radio.value===v.mode&&!radio.disabled;
        radio.closest('label').classList.toggle('is-selected',radio.checked);
        radio.closest('label').classList.toggle('is-unavailable',radio.disabled);
      }
      get('[data-api-settings]').hidden=v.mode!=='api';
      get('[data-audio-keep-wrap]').hidden=v.mode!=='api'&&!v.keep_video_audio;
      get('[data-mix-warning]').hidden=v.mode!=='api'||!v.keep_video_audio;
      get('[data-audio-capability]').textContent=flow?`เสียงต้นฉบับ: ใช้กับ ${provider==='meta_ai'?'Meta AI':'Google Flow'} • ตรวจเสียงจากไฟล์จริงก่อนประกอบ หากคลิปไม่มีเสียงจะแจ้งให้ตรวจ ไม่เปลี่ยนเป็นเสียง API เอง`:'วิธีสร้างนี้ไม่มีเสียงต้นฉบับจากคลิป • เลือกเสียง API SmartSub หรือไม่ใช้เสียงหลัก';
      get('[data-subtitle-source]').textContent=!v.subtitle?'ปิดคำบรรยาย • ไม่เรียกบริการถอดเสียง':v.mode==='flow_original'?'ถอดคำพูดจากเสียงจริงในคลิปผ่าน Subtitle API • ไม่ใช้บทที่วางแผนแทนเสียง':v.mode==='api'?'จัดคำบรรยายตามเสียงพากย์ SmartSub และบทที่บันทึกไว้':'ใช้ข้อความจากบท • ไม่มีเสียงหลักให้ถอด';
      get('[data-audio-keep]').disabled=!v.keep_video_audio && (!flow || v.mode!=='api');
      get('[data-silent-wrap]').hidden=v.mode!=='flow_original'&&!v.keep_video_audio;
      if(speaking)get('[data-silent-wrap]').hidden=true;
      if(speaking&&key==='drama')get('[data-audio-capability]').textContent='เลือกเสียงจากคลิป หรือพากย์ SmartSub แยกตัวละคร • พากย์แยกเพิ่มหลังสร้างภาพ ไม่ซิงก์ปากอัตโนมัติ';
      if(visual)get('[data-audio-capability]').textContent=flow?'เล่าด้วยภาพ • เลือกไม่มีเสียงหลัก หรือเก็บเฉพาะเสียงบรรยากาศจากคลิป':'เล่าด้วยภาพในเครื่อง • ไม่มีเสียงหลัก สามารถเพิ่มเพลงหรือเอฟเฟกต์ได้';
      get('[data-audio-summary]').textContent=(!flow&&v.mode==='flow_original'?'กรุณาเลือกเสียงใหม่: วิธีสร้างนี้ยังไม่รองรับเสียงต้นฉบับ • ':'') + (v.mode==='api'?'เสียงพากย์ API SmartSub':v.mode==='none'?'ไม่มีเสียงหลัก':'เสียงต้นฉบับจากคลิป') + ' • '+(v.subtitle?'เปิดซับ':'ปิดซับ')+' • '+(v.music?'เพิ่มเพลง':'ไม่เพิ่มเพลง')+' • '+(v.sfx?'เปิดเอฟเฟกต์':'ปิดเอฟเฟกต์')+(v.mode==='flow_original'&&v.subtitle?' • ใช้ Subtitle API ถอดเสียงจริง':'');
      if(generated.enabled)get('[data-audio-summary]').textContent+=' • ดนตรี AI บางฉาก';
      if(actorToggle&&!telling)get('[data-audio-summary]').textContent=(acting?'ตัวละครสนทนา • ไม่มีผู้บรรยาย • ไม่มีซับ • ':'เล่าเรื่องแบบผู้บรรยาย • ')+get('[data-audio-summary]').textContent;
    }
    // Switching the main audio must not silently discard independent choices.
    get('[data-main-audio]').addEventListener('change',refresh);
    for(const radio of panel.querySelectorAll('[data-audio-mode]'))radio.addEventListener('change',()=>{
      if(!radio.checked)return;
      get('[data-main-audio]').value=radio.value;
      if(radio.value==='api'&&musicRead().enabled){musicPreviousKeep=get('[data-audio-keep]').checked;get('[data-audio-keep]').checked=true;}
      // First native selection should preserve the original loudness; once the
      // user sets a level, never overwrite it on mode changes or queue edits.
      if(radio.value==='flow_original'&&!panel.dataset.volumeChosen)get('[data-audio-volume]').value=100;
      refresh();
    });
    get('[data-audio-volume]').addEventListener('input',()=>{panel.dataset.volumeChosen='true';});
    get('[data-audio-volume]').addEventListener('input',refresh);
    panel.addEventListener('input',()=>{defaultsProtected=true;});
    panel.addEventListener('change',()=>{defaultsProtected=true;refresh();if(key==='product' && typeof ui!=='undefined' && ui.state && typeof renderSystem==='function')renderSystem(ui.state);});anchor.addEventListener('change',refresh);
    const entry={read,refresh,musicRead,musicSet,acting:()=>window.storytellingModeFor?.(key)?window.storytellingModeFor(key)!=='narrator':!!actorToggle?.checked,subtitle(value){get('[data-audio-subtitle]').checked=value;refresh();},defaults(value){if(defaultsHydrated)return;defaultsHydrated=true;if(!defaultsProtected)entry.subtitle(value);},provider(value){panel.dataset.videoMode=value||'';refresh();},set(v){defaultsProtected=true;v=v||{mode:'api',subtitle:true,music:false,sfx:false,allow_silent:false};get('[data-main-audio]').value=v.mode;for(const k of ['subtitle','music','sfx'])get('[data-audio-'+k+']').checked=!!v[k];get('[data-audio-silent]').checked=!!v.allow_silent;refresh();}};
    panels.set(key,entry);refresh();
    const originalSet=entry.set;entry.set=v=>{get('[data-audio-keep]').checked=!!v?.keep_video_audio;get('[data-audio-volume]').value=v?.video_audio_volume ?? (v?.mode==='flow_original'?100:35);panel.dataset.volumeChosen='true';get('.audio-advanced').open=v?.mode==='none'||!!v?.keep_video_audio||!!v?.allow_silent;originalSet(v);};
  }
  mount('product','#product-video-provider',true);mount('story','#story-video-mode');mount('story-batch','#story-batch-video-mode');mount('drama','#drama-video-mode');mount('long','#long-mode');mount('product-batch','#creation-form .cq-buttons',true);
  window.prepareStoryAudioBatch=()=>{
    if(window.prepareStorytellingBatch)return window.prepareStorytellingBatch();
    const source=panels.get('story'), target=panels.get('story-batch');
    const toggle=document.querySelector('#story-batch-video-mode').closest('label').nextElementSibling.querySelector('[data-actor-dialogue]');
    // Reset previous draft before copying, so disabling acting restores the right audio.
    if(toggle.checked)toggle.click();
    target.set(source.read());
    if(source.acting())toggle.click();
    target.refresh();
  };
  for(const id of ['product-subtitle','drama-subtitle']){const old=document.querySelector('#'+id);if(old){panels.get(id.split('-')[0])?.subtitle(old.checked);const legacy=old.closest('label')||old;legacy.hidden=true;legacy.dataset.legacyAudioControl='true';}}
  // State may have arrived before this module, or hydrateForms may arrive later.
  window.hydrateMediaAudioDefaults(typeof ui!=='undefined'?ui.state?.settings:null);
  window.prepareAudioQueue=item=>{const panel=panels.get('product-batch');panel?.provider(item?.video_generation_mode || item?.render_options?.video_generation_mode || document.querySelector('#product-video-provider')?.value);panel?.set(item?.settings?.audio_choices || panels.get('product')?.read());panel?.musicSet(item?item.settings?.generated_music_options:panels.get('product')?.musicRead());};
  const renderQueue=window.renderCreationQueue;
  if(renderQueue)window.renderCreationQueue=state=>{
    renderQueue(state);
    for(const row of state?.creation_queue?.items || []){
      const node=document.querySelector(`[data-id="${CSS.escape(row.queue_id)}"]`)?.closest('.cq-row');
      if(!node)continue;
      const v=row.settings?.audio_choices || row.render_options?.audio_choices;
      let label=node.querySelector('.media-audio-queue-summary');
      if(!label){label=document.createElement('small');label.className='media-audio-queue-summary';node.append(label);}
      label.textContent=v?`${v.mode==='api'?'เสียง API SmartSub':v.mode==='none'?'ไม่มีเสียงหลัก':'เสียงต้นฉบับจากคลิป'} • ${v.subtitle?'เปิดซับ':'ปิดซับ'} • ${v.music?'เพิ่มเพลง':'ไม่เพิ่มเพลง'}`:'ค่าของงานเดิม';
      const tellingMode=row.settings?.storytelling_options?.mode||row.render_options?.storytelling_options?.mode;
      const tellingLabel={narrator:'ผู้บรรยายเล่าเรื่อง',solo:'ตัวละครพูดเอง',dialogue:'ตัวละครสนทนา',visual:'เล่าเรื่องด้วยภาพ'}[tellingMode];
      if(tellingLabel)label.textContent=tellingLabel+' • '+label.textContent;
      else if(row.settings?.actor_dialogue)label.textContent='ตัวละครสนทนา • ไม่มีผู้บรรยาย • '+label.textContent;
      if(v && (v.mode==='flow_original'||v.keep_video_audio))label.textContent+=` • เสียงคลิป ${v.video_audio_volume ?? (v.mode==='flow_original'?100:35)}%`;
      if((row.settings||row.render_options)?.generated_music_options?.enabled)label.textContent+=' • ดนตรี AI บางฉาก';
    }
  };
  const original=postAction;
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey(action,payload);
    if(key && !payload.job_id && panels.has(key)){
      const choice=panels.get(key).read();
      const generated=panels.get(key).musicRead();
      if(['story','story-batch'].includes(key)&&!payload.creative_context){
        const acting=panels.get(key).acting();
        const telling=window.storytellingModeFor?.(key);
        if(telling==='visual'&&!['none','flow_original'].includes(choice.mode))throw new Error('เล่าเรื่องด้วยภาพต้องไม่มีเสียงพากย์');
        if(acting&&telling!=='visual'&&choice.mode!=='flow_original')throw new Error('Story Shorts แบบตัวละครพูดต้องใช้เสียงจากคลิป');
        payload={...payload,actor_dialogue:acting};
      }
      const mode=payload.video_generation_mode || payload.render_options?.video_generation_mode || (payload.video_provider==='meta_ai'?'meta_ai':key.startsWith('product')?'google_flow':'image_motion');
      if(choice.mode==='flow_original' && !['google_flow','meta_ai'].includes(mode))throw new Error('เสียงต้นฉบับใช้ได้กับ Google Flow หรือ Meta AI');
      if(choice.keep_video_audio && (!['google_flow','meta_ai'].includes(mode)||choice.mode!=='api'))throw new Error('กรุณาปิดการผสมเสียงวิดีโอ หรือเลือกเสียงพากย์ API และ Google Flow / Meta AI');
      if(generated.enabled&&(!['google_flow','meta_ai'].includes(mode)||choice.mode==='none'||choice.music||(choice.mode==='api'&&!choice.keep_video_audio)))throw new Error('ดนตรี AI: ใช้ Flow หรือ Meta พร้อมเก็บเสียงคลิป และปิดเพลงจากคลังก่อนเริ่ม');
      payload={...payload,audio_choices:choice,subtitle:choice.subtitle,generated_music_options:generated};
      if(payload.render_options)payload.render_options={...payload.render_options,subtitle_enabled:choice.subtitle,audio_choices:choice,generated_music_options:generated};
    }
    return original(action,payload);
  };
})();
