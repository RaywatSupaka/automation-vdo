/* Display-only summaries: never dispatch creation, alter saved jobs or control AI tabs. */
(() => {
  const $ = selector => document.querySelector(selector);
  const text = selector => $(selector)?.selectedOptions?.[0]?.textContent?.trim() || '';
  function selectedCreativeLabel(key) {
    const pickerLabel=id=>document.getElementById(id)?.textContent?.replace(/\s*·\s*เปลี่ยน\s*$/,'').trim()||'';
    if(key==='product-batch'){
      for(const [id,prefix] of [['creation-saved-product-style','แนวบท'],['creation-saved-story-structure','โครงเรื่อง']]){
        const button=document.getElementById(id),panel=button?.closest('.creative-picker'),group=button?.closest('.creative-queue-pickers');
        if(panel&&!panel.hidden&&group&&!group.hidden){const label=pickerLabel(id);return label&&label!=='ตามเนื้อเรื่องเดิม'?`${prefix}: ${label}`:'';}
      }
    }
    if(key==='product'||key==='product-batch'){
      const name=key==='product'?'ps-script-style':'creation-product-script';
      const value=document.querySelector(`input[name="${name}"]:checked`)?.value;
      return value&&window.creativeLabel?'แนวบท: '+window.creativeLabel('product',value):'';
    }
    if(key==='story'||key==='story-batch'){
      const label=pickerLabel(key+'-structure');
      return label&&label!=='ตามเนื้อเรื่องเดิม'?'โครงเรื่อง: '+label:'';
    }
    return '';
  }
  const specs = [
    ['product','#create-product','#product-video-provider','#product-provider',null,'9:16'],
    ['story','#create-story','#story-video-mode','#story-provider','#story-scenes','9:16'],
    ['drama','#create-drama-series','#drama-video-mode','#drama-provider','#drama-scenes','9:16'],
    ['long','#create-longvideo','#long-mode','#long-provider','#long-scenes','16:9'],
    ['story-batch','#story-batch-submit','#story-batch-video-mode','#story-batch-provider','#story-batch-scenes','9:16'],
    ['product-batch','#creation-editor-submit','#creation-product-video-provider','#creation-product-provider','#creation-product-scenes','9:16'],
  ];
  const mounted = specs.flatMap(spec => {
    const button = $(spec[1]); if (!button) return [];
    const summary = document.createElement('section'); summary.className='creator-review';
    summary.setAttribute('aria-label','สรุปการตั้งค่าก่อนสร้าง');
    const heading=document.createElement('strong');heading.textContent=spec[0].includes('batch')?'การตั้งค่าที่บันทึกลงคิว':'สรุปก่อนสร้าง';
    const content=document.createElement('p'); const note=document.createElement('small');
    note.textContent='ตรวจตัวเลือกก่อนเริ่ม • การเพิ่มลงคิวยังไม่เรียก AI';
    summary.append(heading,content,note);
    const footer=button.closest('footer,.create-submit-stack,.cq-buttons') || button;
    footer.before(summary);
    return [{spec,summary,content}];
  });
  function refresh() {
    for (const {spec,content} of mounted) {
      const [key,,mode,provider,scenes,ratio]=spec;
      const audio=window.mediaAudioChoice?.(key); if(!audio) continue;
      const parts=[ratio,provider?text(provider):'ผู้สร้างภาพตามค่าของรายการ',mode?text(mode):'Google Flow'];
      if(scenes && $(scenes))parts.push(text(scenes).includes('ภาพ')?text(scenes):`${$(scenes).value} ฉาก`);
      if(key==='product' && $('#ps-count'))parts.push(`${$('#ps-count').value} ฉาก`);
      if(key==='drama')parts.push(`${$('#drama-episodes').value} EP`);
      const creative=selectedCreativeLabel(key);if(creative)parts.push(creative);
      if(window.storytellingLabelFor?.(key))parts.push(window.storytellingLabelFor(key));
      if(audio.keep_video_audio)parts.push(`ผสมเสียงวิดีโอเดิม ${audio.video_audio_volume ?? 35}%`);
      if(document.getElementById(`${key}-queue-only`)?.checked)parts.push('เก็บเข้าคิว • รอกดเริ่ม');
      const generatedMusic=window.generatedMusicChoice?.(key)?.enabled===true;
      const musicLabel=generatedMusic?(audio.music?'ขอดนตรี AI บางฉาก + เพลงพื้นหลังจากคลัง':'ขอดนตรี AI บางฉาก'):(audio.music?'เพิ่มเพลงพื้นหลัง':'ไม่เพิ่มเพลง');
      parts.push(audio.mode==='api'?'เสียงพากย์ API SmartSub':audio.mode==='flow_original'?'เสียงต้นฉบับจากคลิป':'ไม่ใส่เสียงหลัก',audio.subtitle?'เปิดซับ':'ปิดซับ',musicLabel,audio.sfx?'เพิ่มเสียงเน้นข้อความ':'ไม่เพิ่มเสียงเน้นข้อความ');
      const presenter=$('#presenter-use-'+key);
      if(presenter)parts.push(presenter.checked?'ใส่ผู้บรรยาย':'ไม่ใส่ผู้บรรยาย');
      if(audio.mode==='flow_original' && audio.subtitle)parts.push('ซับใช้ API ถอดเสียงจริง');
      if(audio.mode==='none' && audio.subtitle)parts.push('ตรวจว่ามีบท/คำบรรยายพร้อมใช้');
      const value=parts.filter(Boolean).join(' · ');if(content.textContent!==value)content.textContent=value;
    }
    const productAudio=window.mediaAudioChoice?.('product');
    const productVideo=document.querySelector('#product-video-provider')?.selectedOptions?.[0]?.textContent?.trim()||'Google Flow';
    const intro=$('[data-view="products"] .page-intro p');
    if(intro && productAudio)intro.textContent='นำเข้าสินค้า → สร้างภาพ → '+productVideo+' → '+(productAudio.mode==='api'?'เสียงพากย์ → ':'')+(productAudio.subtitle?'ซับไตเติ้ล → ':'')+'ประกอบคลิปตามตัวเลือก → ผลงานพร้อมใช้';
    const steps=document.querySelectorAll('[data-view="products"] .step-strip span');
    if(steps[3] && productAudio)steps[3].lastChild.textContent=productAudio.subtitle?' เสียงและซับ':productAudio.mode==='api'?' เสียงพากย์':' ประกอบเสียงที่เลือก';
  }
  document.addEventListener('change',refresh);
  document.addEventListener('click',()=>queueMicrotask(refresh));
  const renderCatalog=window.renderCreativeCatalog;
  if(renderCatalog)window.renderCreativeCatalog=value=>{renderCatalog(value);refresh();};
  // Recalculate after an existing dialog is hydrated programmatically.
  document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(refresh).observe(dialog,{attributes:true,attributeFilter:['open']}));
  refresh();
  // Clarify defaults versus actions on existing output without changing controls.
  for(const page of ['settings','voice','subtitle','audio','logo','presenter-settings']) {
    const root=$(`[data-view="${page}"]`);if(!root)continue;
    const note=document.createElement('p');note.className='settings-scope-note';
    note.textContent='ค่าที่บันทึกใช้สำหรับงานใหม่ • งานในคิวเก็บค่าของรายการนั้นไว้ • การประกอบงานเดิมใหม่ต้องเลือกงานและกดสั่งแยก';
    const intro=root.querySelector('.page-intro');if(intro)intro.after(note);else root.prepend(note);
  }
  // Decorative movement stops while this window is not visible.
  document.addEventListener('visibilitychange',()=>document.body.classList.toggle('ux-background-paused',document.hidden));
})();
