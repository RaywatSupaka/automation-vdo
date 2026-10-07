(() => {
  'use strict';
  const legacy=document.querySelector('#audio-background-file');
  if(!legacy)return;
  legacy.closest('label').hidden=true;
  legacy.closest('label').style.display='none';
  document.querySelector('#audio-background-mode').closest('label').hidden=true;
  document.querySelector('#audio-background-mode').closest('label').style.display='none';
  const randomButton=document.querySelector('#audio-random');if(randomButton)randomButton.hidden=true;
  const panel=document.createElement('section');panel.className='music-library';
  panel.innerHTML=`<b>เลือกเพลงที่จะสุ่มลงคลิป</b><div class="music-actions"><button type="button" data-music-all>เลือกทั้งหมด</button><button type="button" data-music-none>ล้างที่เลือก</button></div><div class="music-tracks" aria-label="คลังเพลงพื้นหลัง"></div><label for="music-count">จำนวนเพลงต่อคลิป (เล่นสลับกัน)</label><div class="music-actions">${[1,2,3,4,5].map(n=>`<button type="button" data-music-count="${n}" aria-pressed="false">${n}</button>`).join('')}<input id="music-count" aria-label="จำนวนเพลงที่สุ่มต่อคลิป" type="number" min="1" step="1" value="4"></div><p class="music-summary" role="status"></p><audio controls preload="none" hidden></audio><p class="music-preview-note" role="status"></p>`;
  legacy.closest('label').after(panel);
  let files=[],selected=new Set(),initialized=false,signature='',playing='',dirty=false;
  const count=panel.querySelector('#music-count'),player=panel.querySelector('audio'),summary=panel.querySelector('.music-summary'),note=panel.querySelector('.music-preview-note');
  function update(){
    count.max=String(Math.max(1,selected.size));
    panel.querySelectorAll('[data-music-count]').forEach(b=>{b.disabled=Number(b.dataset.musicCount)>selected.size;b.setAttribute('aria-pressed',String(Number(b.dataset.musicCount)===Number(count.value)));});
    summary.textContent=`เลือกไว้ ${selected.size} เพลง • สุ่มใช้ ${count.value||'—'} เพลงต่อคลิป${dirty?' • ยังไม่บันทึก':''}`;
    panel.querySelectorAll('[data-music-play]').forEach(b=>b.textContent=b.dataset.musicPlay===playing&&!player.paused?'⏸ หยุด':'▶ ฟัง');
  }
  function stop(){player.pause();playing='';update();}
  function render(audio){
    const next=(audio.background_files||[]).filter(n=>n!=='สุ่มจากคลัง');
    if(!initialized){selected=new Set(audio.background_selection??(String(audio.background_mode||'').startsWith('เลือกเพลงเดียว')?[audio.background_file]:next));count.value=String(audio.background_track_count??Math.max(1,Math.min(4,selected.size)));initialized=true;}
    const key=JSON.stringify(next);if(key===signature){update();return;}signature=key;files=next;
    const list=panel.querySelector('.music-tracks');list.replaceChildren();
    for(const name of new Set([...files,...selected])){
      const row=document.createElement('div');row.className='music-track';
      const label=document.createElement('label'),box=document.createElement('input'),title=document.createElement('span');
      box.type='checkbox';box.checked=selected.has(name);box.dataset.musicName=name;
      title.textContent=name+(files.includes(name)?'':' • ไม่พบไฟล์');title.title=name;label.append(box,title);
      const button=document.createElement('button');button.type='button';button.dataset.musicPlay=name;button.textContent='▶ ฟัง';button.disabled=!files.includes(name);row.append(label,button);list.append(row);
    }update();
  }
  panel.addEventListener('change',e=>{if(e.target.dataset.musicName){const n=e.target.dataset.musicName;e.target.checked?selected.add(n):selected.delete(n);count.value=String(Math.max(1,Math.min(Number(count.value)||1,selected.size)));}dirty=true;update();});
  count.addEventListener('input',()=>{dirty=true;update();});
  panel.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.hasAttribute('data-music-all')||b.hasAttribute('data-music-none')){selected=new Set(b.hasAttribute('data-music-all')?files:[]);count.value=String(Math.max(1,Math.min(Number(count.value)||1,selected.size)));dirty=true;signature='';render({background_files:files});}
    else if(b.dataset.musicCount){count.value=b.dataset.musicCount;dirty=true;update();}
    else if(b.dataset.musicPlay){
      const name=b.dataset.musicPlay;if(playing===name&&!player.paused){stop();return;}
      stop();playing=name;player.src='/api/desktop/music-preview?file='+encodeURIComponent(name);player.hidden=false;player.volume=.5;note.textContent='กำลังโหลด: '+name;
      try{await player.play();if(playing===name)note.textContent='กำลังฟัง: '+name;}catch(error){if(playing===name)note.textContent='ฟังไม่ได้: '+name+' • '+(window.smartflowSafeError?.(error.message)||'ตรวจไฟล์เสียงอีกครั้ง');}update();
    }
  });
  player.addEventListener('pause',update);player.addEventListener('play',update);player.addEventListener('ended',stop);
  player.addEventListener('loadedmetadata',()=>{if(playing&&Number.isFinite(player.duration))note.textContent=`${playing} • ${Math.round(player.duration)} วินาที`;});
  player.addEventListener('error',()=>{note.textContent='ไม่สามารถเล่นไฟล์นี้ได้ กรุณาตรวจรูปแบบหรือไฟล์ต้นฉบับ';stop();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  document.addEventListener('click',e=>{if(e.target.closest('[data-page]'))stop();});window.addEventListener('pagehide',stop);
  window.SmartFlowMusic={render,payload(){const n=Number(count.value);if(!Number.isInteger(n)||n<1||n>Math.max(1,selected.size))throw Error('จำนวนเพลงต้องไม่เกินจำนวนเพลงที่ติ๊กเลือก');if(document.querySelector('#audio-background-enabled').checked&&!selected.size)throw Error('เลือกเพลงอย่างน้อยหนึ่งเพลง หรือปิดเพลงพื้นหลัง');return {background_selection:[...selected],background_track_count:n};},saved(){dirty=false;update();}};
})();
