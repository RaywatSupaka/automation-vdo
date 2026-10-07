(() => {
  pageMeta['product-cast']=['PRODUCT CAST','นายแบบ / นางแบบสินค้า'];
  pageMeta.products=['SHOPEE VIDEO','ทำคลิปสินค้า shopee'];
  document.querySelectorAll('[data-page="products"] span').forEach(n=>{if(n.textContent.includes('สินค้า')){const title=n.querySelector('strong');if(title)title.textContent='คลิปสินค้า Shopee';else n.textContent='คลิปสินค้า Shopee';}});
  const intro=document.querySelector('[data-view="products"] .page-intro');
  intro.querySelector('h1').textContent='ทำคลิปสินค้า shopee';
  intro.querySelector('p').textContent='วางลิงก์สินค้า เลือกตัวละครและจำนวนฉาก แล้วสร้างคลิปอัตโนมัติ';
  const step=document.querySelector('[data-view="products"] .step-strip');if(step)step.querySelectorAll('span')[2].innerHTML='<b>3</b> วิดีโอรายฉาก';
  const fields=document.createElement('div');fields.innerHTML=`<label class="field"><span>นายแบบ / นางแบบที่บันทึกไว้</span><select id="ps-cast"><option value="">ไม่เลือก — ให้ AI วางตัวละคร</option></select></label><label class="field"><span>รายละเอียดเพิ่มเติม (ไม่บังคับ)</span><textarea id="ps-details" rows="3" placeholder="แนวเรื่อง เหตุการณ์ หรือสิ่งที่อยากเน้น — เว้นว่างให้ AI คิดให้"></textarea></label><label class="field"><span>จำนวนฉาก</span><select id="ps-count" disabled><option value="3" selected>3 ฉาก — เปิดเรื่อง / ใช้สินค้า / สรุป</option></select></label>`;
  document.querySelector('.product-form-footer').before(fields);
  const sceneCount=fields.querySelector('#ps-count');sceneCount.disabled=false;sceneCount.replaceChildren();
  for(let n=3;n<=15;n++){const option=document.createElement('option');option.value=String(n);option.textContent=`${n} ฉาก`;sceneCount.append(option);}
  const countKey='smartflow.product.scene-count.v1';
  try{const saved=Number(localStorage.getItem(countKey));sceneCount.value=String(Number.isInteger(saved)&&saved>=3&&saved<=15?saved:3);}catch{sceneCount.value='3';}
  const planning=document.createElement('section');planning.className='product-options';
  const heading=document.createElement('h3');heading.textContent='วางแผนคลิปสินค้า';
  const summary=document.createElement('p');summary.setAttribute('role','status');
  const saveCount=document.createElement('button');saveCount.type='button';saveCount.className='button ghost';saveCount.textContent='บันทึกจำนวนฉากใช้ครั้งหน้า';
  const countLabel=sceneCount.closest('label');countLabel.before(planning);planning.append(heading,countLabel,summary,saveCount);
  const scriptKey='smartflow.product.script-style.v1';
  const scriptLabel=document.createElement('fieldset');scriptLabel.className='ps-script-styles';
  scriptLabel.innerHTML=`<legend>แนวบทของคลิป</legend><div class="ps-style-grid">
    <label><input type="radio" name="ps-script-style" id="ps-script-standard" value="standard" checked><span><strong>แบบเดิม</strong><small>เล่าเรื่องและนำเสนอสินค้า</small></span></label>
    <label><input type="radio" name="ps-script-style" id="ps-story-first" value="story_first_review" aria-describedby="ps-story-first-hint"><span><strong>เล่าเรื่องก่อนรีวิว</strong><small>ผู้รีวิวเล่าเหตุการณ์อย่างเป็นธรรมชาติ</small></span></label>
    <label><input type="radio" name="ps-script-style" id="ps-short-film" value="short_film_ad" aria-describedby="ps-film-hint"><span><strong>หนังสั้นโฆษณา</strong><small>เรื่องนำ สินค้าตาม</small></span></label></div>`;
  const scriptHint=document.createElement('p');scriptHint.id='ps-story-first-hint';
  scriptHint.textContent='เปิดด้วยเหตุการณ์น่าสนใจ ให้ตัวละครเล่า แล้วค่อยเชื่อมเข้าสินค้า ไม่เน้นขายตรง';
  const scriptExample=document.createElement('p');scriptExample.id='ps-story-first-example';
  scriptExample.textContent='เช่น “ว่าจะอ่านอีกแค่หน้าเดียว… รู้ตัวอีกทีบ้านเงียบหมดแล้ว” แล้วค่อยเชื่อมโคมไฟเข้ากับเรื่อง • กำหนดแนวเรื่องได้ในช่องรายละเอียดเดิม';
  const filmOptions=document.createElement('div');filmOptions.className='ps-film-options';filmOptions.hidden=true;
  filmOptions.innerHTML=`<p id="ps-film-hint">เปิดด้วยเหตุการณ์ชวนติดตาม ค่อยเชื่อมสินค้า และปิดเรื่องก่อนชวนดูตะกร้า</p>
    <label class="field"><span>แนวหนังสั้น</span><select id="ps-film-genre"><option value="auto">ให้ AI เลือก</option><option value="warm">อบอุ่น</option><option value="comedy">ตลก</option><option value="twist">หักมุม</option></select></label>
    <label class="check-field"><input type="checkbox" id="ps-film-cta" checked><span>ชวนดูสินค้าที่ตะกร้าตอนจบ</span></label>
    <p id="ps-film-count-hint"></p>`;
  summary.before(scriptLabel,scriptHint,scriptExample,filmOptions);
  const storyFirst=scriptLabel.querySelector('#ps-story-first'),shortFilm=scriptLabel.querySelector('#ps-short-film');
  const filmGenre=filmOptions.querySelector('#ps-film-genre'),filmCta=filmOptions.querySelector('#ps-film-cta');
  const filmKey='smartflow.product.short-film.v2';
  try{
    const saved=localStorage.getItem(scriptKey);
    if(saved==='story_first_review')storyFirst.checked=true;
    if(saved==='short_film_ad')shortFilm.checked=true;
    const details=JSON.parse(localStorage.getItem(filmKey)||'{}');
    if(['auto','warm','comedy','twist'].includes(details.genre))filmGenre.value=details.genre;
    if(typeof details.ending_cta==='boolean')filmCta.checked=details.ending_cta;
  }catch{}
  const updateScript=()=>{scriptHint.hidden=scriptExample.hidden=!storyFirst.checked;filmOptions.hidden=!shortFilm.checked;};updateScript();
  const updatePlan=()=>{const n=Number(sceneCount.value);const meta=document.querySelector('#product-video-provider')?.value==='meta_ai';summary.textContent=`${n} ภาพ → ${n} คลิป → รวมเป็น 1 วิดีโอ • ${meta?'Meta AI รุ่นทดลอง แนวตั้ง • ความยาวตามผลที่เว็บสร้าง':'ความยาวขึ้นอยู่กับระยะเวลาคลิปที่เลือกใน Google Flow'}${shortFilm.checked?' • หนังสั้นโฆษณา':storyFirst.checked?' • เล่าเรื่องก่อน รีวิวธรรมชาติ':''}`;filmOptions.querySelector('#ps-film-count-hint').textContent=n<6?'แนะนำ 6 ฉากเพื่อเล่าเรื่องได้เต็มขึ้น • ตอนนี้ใช้ '+n+' ฉากตามที่คุณเลือก โดยย่อเรื่องให้กระชับ':'ใช้ช่องรายละเอียดเดิมกำหนดเหตุการณ์หรือแนวเรื่องได้';};
  const saveScript=()=>{updateScript();updatePlan();try{localStorage.setItem(scriptKey,shortFilm.checked?'short_film_ad':storyFirst.checked?'story_first_review':'standard');localStorage.setItem(filmKey,JSON.stringify({genre:filmGenre.value,ending_cta:filmCta.checked}));}catch{toast('ยังเลือกใช้กับงานนี้ได้ แต่จำค่าสำหรับครั้งหน้าไม่สำเร็จ','info');}};
  const creativePicker=window.mountCreativeRadioPicker?.({host:scriptLabel,id:'ps-creative-style',radioName:'ps-script-style',grid:'.ps-style-grid',onChange:()=>{updateScript();updatePlan();}});
  if(creativePicker){
    try{const selected=localStorage.getItem(scriptKey);if(selected)creativePicker.set(selected);}catch{}
    scriptLabel.addEventListener('change',()=>{updateScript();updatePlan();try{localStorage.setItem(scriptKey,creativePicker.get());}catch{}});
  }
  scriptLabel.querySelectorAll('input').forEach(input=>input.addEventListener('change',saveScript));
  filmGenre.addEventListener('change',saveScript);filmCta.addEventListener('change',saveScript);
  document.querySelector('#product-video-provider')?.addEventListener('change',updatePlan);
  sceneCount.addEventListener('change',updatePlan);updatePlan();
  saveCount.onclick=()=>{try{localStorage.setItem(countKey,sceneCount.value);summary.textContent+=' • บันทึกแล้ว ใช้กับงานใหม่ ไม่เปลี่ยนคิวเดิม';}catch{summary.textContent='บันทึกค่าไม่สำเร็จ แต่ยังเลือกจำนวนฉากสำหรับงานนี้ได้';}};
  const castToggle=document.createElement('label');castToggle.className='check-field';castToggle.innerHTML='<input type="checkbox" id="ps-use-cast"><span>ใช้นายแบบ / นางแบบจากคลัง</span>';fields.prepend(castToggle);
  document.querySelector('#ps-cast').addEventListener('change',()=>{document.querySelector('#ps-use-cast').checked=Boolean(document.querySelector('#ps-cast').value);});
  document.querySelector('#ps-cast').closest('label').hidden=true;
  const gallery=document.createElement('div');gallery.id='ps-cast-gallery';gallery.style='display:flex;flex-wrap:wrap;gap:12px';castToggle.after(gallery);
  const outfitChoice=document.createElement('label');outfitChoice.className='field';outfitChoice.innerHTML='<span>ชุดของตัวละคร</span><select id="ps-outfit-mode"><option value="auto">ให้ AI เลือกชุดสุภาพ</option><option value="product">สวมเสื้อผ้าที่เป็นสินค้านี้</option><option value="saved">ใช้รูปชุดที่บันทึกกับนายแบบ / นางแบบ</option></select><small>เลือกชุดก่อนเริ่มงาน • รูปและตัวเลือกจะถูกเก็บไว้กับงานนี้</small>';
  gallery.after(outfitChoice);
  const manage=document.createElement('button');manage.type='button';manage.className='button ghost';manage.textContent='เปิดคลัง / อัปโหลด / สร้างคนใหม่';manage.onclick=()=>{showPage('product-cast');run(assets);};gallery.after(manage);
  const castPanel=document.createElement('div');castPanel.id='ps-cast-panel';castPanel.hidden=true;
  castToggle.after(castPanel);castPanel.append(gallery,manage);
  document.querySelector('#ps-use-cast').setAttribute('aria-controls','ps-cast-panel');
  const outfitDetails=document.createElement('details');outfitDetails.className='ps-outfit-options';
  const outfitTitle=document.createElement('summary');outfitTitle.textContent='เสื้อผ้าของตัวละคร • เลือกเพิ่มเติม';
  outfitChoice.before(outfitDetails);outfitDetails.append(outfitTitle,outfitChoice);
  const hint=document.createElement('p');hint.textContent='ใส่ลิงก์สินค้าเท่านั้น ระบบดึงชื่อ รายละเอียด และรูปสินค้าผ่าน Extension ให้เอง';fields.prepend(hint);
  const page=document.createElement('section');page.className='page';page.dataset.view='product-cast';
  page.innerHTML=`<section class="page-intro"><h1>นายแบบ / นางแบบสินค้า</h1><p>บันทึกรูปไว้เลือกใช้ในเรื่องเล่าสินค้า ไม่ใช่ตัวละครผู้บรรยายซ้อนคลิป</p></section><section class="panel" style="padding:24px"><label class="field"><span>ชื่อที่ใช้ในคลัง</span><input id="cast-name" maxlength="100"></label><label class="field"><span>อัปโหลดรูปของคุณ</span><input id="cast-file" type="file" accept="image/png,image/jpeg,image/webp"></label><button class="button primary" id="cast-upload">บันทึกรูปเข้าคลัง</button><h2>หรือให้ AI สร้างบุคคลใหม่</h2><label class="field"><span>ลักษณะที่ต้องการ (เว้นว่างได้)</span><textarea id="cast-details" rows="3"></textarea></label><select id="cast-provider"><option value="chatgpt">ChatGPT Web</option><option value="gemini">Gemini Web</option></select><button class="button primary" id="cast-generate">สร้างภาพด้วย AI</button><p>เมื่อภาพพร้อม กดรีเฟรช ดูตัวอย่าง แล้วกดบันทึกก่อนเลือกใช้</p><button class="button ghost" id="cast-refresh">รีเฟรชคลัง</button><p id="cast-notice" role="status"></p><div id="cast-assets" style="display:flex;gap:16px;flex-wrap:wrap"></div></section>`;
  page.querySelector('.page-intro p').textContent='บันทึกรูปไว้เลือกใช้ในทำคลิปสินค้า shopee ไม่ใช่ตัวละครผู้บรรยายซ้อนคลิป';
  document.querySelector('[data-view="settings"]').after(page);
  const q=s=>document.querySelector(s),original=postAction;let busy=false,castAssets=[];
  const preparation=document.createElement('section');preparation.className='panel product-preparation';preparation.hidden=true;
  preparation.setAttribute('role','status');preparation.setAttribute('aria-live','polite');
  const preparationTitle=document.createElement('strong'),preparationDetail=document.createElement('p');
  preparation.append(preparationTitle,preparationDetail);fields.after(preparation);
  let productPreparing=false,productPreparationUnknown=false;
  const unknownPreparationRequests=new Set(),preparationStoragePrefix='smartflow.product.prepare.pending.v1:';
  window.productPreparationActive=false;
  const showPreparation=(title,detail,state='working')=>{
    preparation.hidden=false;preparation.dataset.state=state;
    preparationTitle.textContent=title;preparationDetail.textContent=detail;
  };
  const preparationCall=async(action,payload,timeout=45000,identityId='')=>{
    let timer,timeoutHit=false;
    const requestId=String(identityId||payload?.request_id||'');
    const request=Promise.resolve().then(()=>original(action,payload));
    const releaseUnknown=()=>{if(timeoutHit&&requestId){unknownPreparationRequests.delete(requestId);productPreparationUnknown=unknownPreparationRequests.size>0;if(!productPreparing)window.productPreparationActive=productPreparationUnknown;}};
    request.then(releaseUnknown,releaseUnknown);
    try{return await Promise.race([request,new Promise((_,reject)=>{
      timer=setTimeout(()=>{timeoutHit=true;if(requestId){unknownPreparationRequests.add(requestId);productPreparationUnknown=true;}reject(Error('โปรแกรมยังไม่ตอบกลับขั้นเตรียมสินค้า • คำขอเดิมถูกเก็บไว้ ลองทำต่อด้วยลิงก์เดิมได้โดยไม่สร้างงานซ้ำ'));},timeout);
    })]);}finally{clearTimeout(timer);}
  };
  async function preparationIdentity(link){
    const source=String(link||'').trim();let digest='';
    try{const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));digest=[...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');}
    catch{let h=2166136261;for(const ch of source){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}digest=(h>>>0).toString(16).padStart(8,'0');}
    const key=preparationStoragePrefix+digest.slice(0,40);let id='';
    try{id=localStorage.getItem(key)||'';}catch{}
    if(!id){id='PSP-'+(crypto.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`);try{localStorage.setItem(key,id);}catch{}}
    return {id,key};
  }
  function clearPreparationIdentity(identity){
    try{
      const id=String(identity?.id||identity||'');
      if(identity?.key)localStorage.removeItem(identity.key);
      else for(let i=localStorage.length-1;i>=0;i--){const key=localStorage.key(i);if(key?.startsWith(preparationStoragePrefix)&&localStorage.getItem(key)===id)localStorage.removeItem(key);}
      if(id)unknownPreparationRequests.delete(id);
    }catch{}
    productPreparationUnknown=unknownPreparationRequests.size>0;
  }
  function syncCastVisibility(){castPanel.hidden=!q('#ps-use-cast').checked;q('#ps-use-cast').setAttribute('aria-expanded',String(!castPanel.hidden));}
  function selectCast(id){q('#ps-cast').value=id;q('#ps-use-cast').checked=Boolean(id);if(!id&&q('#ps-outfit-mode').value==='saved')q('#ps-outfit-mode').value='auto';document.querySelectorAll('[data-cast-choice]').forEach(b=>b.checked=b.dataset.castChoice===id);syncCastVisibility();}
  q('#ps-use-cast').onchange=()=>{if(!q('#ps-use-cast').checked)selectCast('');syncCastVisibility();};
  async function assets(){const r=await original('product_cast_state',{});castAssets=r.assets||[];const selected=q('#ps-cast').value;q('#ps-cast').innerHTML='<option value="">ไม่เลือก — ให้ AI วางตัวละคร</option>';q('#cast-assets').replaceChildren();
    for(const a of r.assets||[]){if(a.approved&&a.available!==false){const o=document.createElement('option');o.value=a.id;o.textContent=a.name;q('#ps-cast').append(o);}
      const card=document.createElement('div'),img=document.createElement('img'),name=document.createElement('p');card.dataset.castAsset=a.id;img.src=a.preview;img.style='width:120px;height:160px;object-fit:contain';name.textContent=a.name;card.append(img,name);
      if(a.warning){const warning=document.createElement('p');warning.textContent=a.warning;warning.setAttribute('role','status');card.append(warning);}
      if(a.approved){const outfit=document.createElement('details');outfit.className='ps-cast-outfit';const title=document.createElement('summary');title.textContent=a.outfit_preview?'ชุดที่บันทึกไว้':'เพิ่มรูปชุด';outfit.append(title);
        const preview=document.createElement('img');if(a.outfit_preview){preview.src=a.outfit_preview;preview.alt='รูปชุดที่บันทึกไว้';preview.style='width:72px;height:96px;object-fit:contain';outfit.append(preview);}
        const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.setAttribute('aria-label','เลือกรูปชุดสำหรับ '+a.name);
        const save=document.createElement('button');save.type='button';save.textContent=a.outfit_preview?'เปลี่ยนรูปชุด':'เพิ่มรูปชุด';save.onclick=()=>run(async()=>{const file=input.files[0];if(!file)throw Error('เลือกรูปชุดก่อน');if(file.size>8*1024*1024)throw Error('รูปชุดต้องไม่เกิน 8 MB');const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});await original('product_cast_outfit_upload',{id:a.id,image});await assets();q('#cast-notice').textContent='บันทึกรูปชุดแล้ว • ใช้กับงานใหม่เท่านั้น';});
        outfit.append(input,save);
        if(a.outfit_preview){const clear=document.createElement('button');clear.type='button';clear.className='button ghost';clear.textContent='เลิกใช้รูปชุด';clear.onclick=()=>run(async()=>{await original('product_cast_outfit_clear',{id:a.id});if(q('#ps-cast').value===a.id&&q('#ps-outfit-mode').value==='saved')q('#ps-outfit-mode').value='auto';await assets();q('#cast-notice').textContent='เลิกใช้รูปชุดกับงานใหม่แล้ว • งานเก่ายังคงเดิม';});outfit.append(clear);}
        card.append(outfit);}
      if(!a.approved){const b=document.createElement('button');b.textContent='บันทึกเข้าคลัง';b.onclick=()=>run(async()=>{await original('product_cast_save',{id:a.id});await assets();});card.append(b);}
      const rename=document.createElement('button');rename.textContent='เปลี่ยนชื่อ';rename.onclick=()=>run(async()=>{const name=prompt('ชื่อในคลัง',a.name);if(name!==null){await original('product_cast_edit',{id:a.id,name});await assets();}});card.append(rename);
      const remove=document.createElement('button');remove.textContent='นำออกจากคลัง';remove.onclick=()=>run(async()=>{if(confirm('นำออกจากรายการเลือก? รูปของงานและคิวเดิมยังอยู่')){await original('product_cast_edit',{id:a.id,hidden:true});await assets();}});card.append(remove);q('#cast-assets').append(card);}
    q('#ps-cast').value=selected;
    for(const container of [q('#ps-cast-gallery'),q('#cast-assets')]){
      if(container.id==='ps-cast-gallery')container.replaceChildren();
      for(const a of (r.assets||[]).filter(a=>a.approved&&a.available!==false)){
        const label=document.createElement('label');label.style='display:flex;flex-direction:column;align-items:center;padding:12px;border:1px solid #475569;border-radius:12px;cursor:pointer';
        const box=document.createElement('input');box.type='checkbox';box.dataset.castChoice=a.id;box.checked=a.id===q('#ps-cast').value&&q('#ps-use-cast').checked;
        box.onchange=()=>selectCast(box.checked?a.id:'');
        const img=document.createElement('img');img.src=a.preview;img.style='width:110px;height:140px;object-fit:contain';
        const name=document.createElement('span');name.textContent='เลือกใช้ '+a.name;
        if(container.id==='ps-cast-gallery'){label.append(img,box,name);if(a.outfit_preview){const outfit=document.createElement('img');outfit.src=a.outfit_preview;outfit.alt='ชุดที่บันทึกกับ '+a.name;outfit.style='width:52px;height:68px;object-fit:contain';label.append(outfit);}container.append(label);}
        else{label.append(box,name);Array.from(container.children).find(c=>c.dataset.castAsset===a.id).prepend(label);}
      }
    }
    if(!q('#ps-cast').value&&selected)q('#ps-use-cast').checked=false;
    syncCastVisibility();
  }
  window.loadProductCastLibrary=assets;
  async function run(fn){if(busy)return;busy=true;try{await fn();}catch(e){q('#cast-notice').textContent=e.message;toast(e.message,'error');}finally{busy=false;}}
  q('#cast-upload').onclick=()=>run(async()=>{const file=q('#cast-file').files[0];if(!file)throw Error('เลือกรูปก่อน');if(file.size>8*1024*1024)throw Error('รูปต้องไม่เกิน 8 MB');const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});await original('product_cast_upload',{name:q('#cast-name').value,image});await assets();q('#cast-notice').textContent='บันทึกรูปแล้ว';});
  q('#cast-generate').onclick=()=>run(async()=>{await original('product_cast_generate',{topic:q('#cast-name').value||'นายแบบ / นางแบบ AI',story_text:q('#cast-details').value,provider:q('#cast-provider').value});q('#cast-notice').textContent='ส่งสร้างภาพแล้ว รอผลใน AI Web และกดรีเฟรชคลังเมื่อเสร็จ';});
  q('#cast-refresh').onclick=()=>run(assets);
  document.querySelector('[data-page="product-cast"]').addEventListener('click',()=>run(assets));
  document.querySelectorAll('[data-page="products"]').forEach(n=>n.addEventListener('click',()=>run(assets)));
  postAction=async(action,payload={})=>{
    const newProduct=action==='create_product'&&payload.link&&!payload.job_id;
    let queueProduct=action==='creation_enqueue'&&(!payload.mode||payload.mode==='product')&&!payload.creative_context;
    if(!newProduct&&!queueProduct)return original(action,payload);
    if(productPreparing)throw Error('กำลังอ่านสินค้าเพื่อเริ่มงานอยู่ ดูสถานะใต้แบบฟอร์ม • ไม่สร้างคำขอซ้ำ');
    const links=newProduct?[payload.link]:Array.isArray(payload.values)?payload.values:String(payload.values||'').split('\n').filter(Boolean);
    if(!links.length)throw Error('ใส่ลิงก์สินค้าอย่างน้อยหนึ่งรายการ');
    const hasBatchCast=Object.prototype.hasOwnProperty.call(payload,'product_cast_id');
    const selectedCast=hasBatchCast?String(payload.product_cast_id||''):(q('#ps-use-cast').checked?q('#ps-cast').value:'');
    const selectedOutfit=hasBatchCast?String(payload.product_outfit_mode||'auto'):q('#ps-outfit-mode').value;
    if(q('#ps-use-cast').checked&&!hasBatchCast&&!q('#ps-cast').value)throw Error('ติ๊กเลือกนายแบบ / นางแบบจากรูปในคลังก่อนเริ่ม');
    if(selectedCast&&![...q('#ps-cast').options].some(option=>option.value===selectedCast))throw Error('ตัวละครที่เลือกไม่พร้อมในคลัง • รีเฟรชคลังแล้วเลือกใหม่');
    if(!['auto','product','saved'].includes(selectedOutfit))throw Error('เลือกชุดของตัวละครใหม่');
    if(selectedOutfit==='saved'&&(!selectedCast||!castAssets.some(asset=>asset.id===selectedCast&&asset.outfit_preview)))throw Error('เลือกรูปชุดที่บันทึกกับนายแบบ / นางแบบก่อนเริ่ม');
    const directions=Object.prototype.hasOwnProperty.call(payload,'product_story_text')?String(payload.product_story_text||''):q('#ps-details').value;
    const selectedSceneCount=Number(payload.scene_count||sceneCount.value);
    const selectedScript=payload.product_script_options || (creativePicker ? window.creativeProductOptions(creativePicker.get(),filmGenre.value,filmCta.checked) : shortFilm.checked
      ?{version:2,style:'short_film_ad',genre:filmGenre.value,ending_cta:filmCta.checked}
      :{version:1,style:storyFirst.checked?'story_first_review':'standard'});
    const selectedVideoMode=(payload.video_generation_mode || payload.video_provider || q('#product-video-provider')?.value)==='meta_ai'?'meta_ai':'google_flow';
    if(!Number.isInteger(selectedSceneCount)||selectedSceneCount<3||selectedSceneCount>15)throw Error('เลือกจำนวนฉาก 3–15');
    productPreparing=true;window.productPreparationActive=true;
    let requestIdentities;
    try{
      if(!window.productOptionSnapshot)throw Error('หน้าสร้างสินค้ายังโหลดไม่ครบ • เปิดหน้าโปรแกรมใหม่ก่อนเริ่ม');
      const captured=await window.productOptionSnapshot.capture(action,{...payload,
        video_generation_mode:selectedVideoMode},original);
      action=captured.action;payload=captured.payload;queueProduct=action==='creation_enqueue';
      requestIdentities=await Promise.all(links.map(preparationIdentity));
      if(productPreparationUnknown&&requestIdentities.some(identity=>!unknownPreparationRequests.has(identity.id)))
        throw Error('คำขอเตรียมสินค้าเดิมยังไม่ยืนยัน • ลองต่อด้วยลิงก์เดิมก่อน เพื่อไม่เปิดงานซ้ำ');
    }catch(error){productPreparing=false;window.productPreparationActive=productPreparationUnknown;throw error;}
    let result,elapsedTimer,preparedCount=0,queuedCount=0,duplicateCount=0;
    const inputDuplicateCount=queueProduct?Number(payload._batch_duplicate_count||0):0;
    try{
    for(let i=0;i<links.length;i++){
      const castId=selectedCast;
      const identity=requestIdentities[i];
      const requestOptions={
        provider:payload.provider||'chatgpt',ai_web_model:payload.ai_web_model||'',video_generation_mode:selectedVideoMode,
        scene_count:selectedSceneCount,product_script_options:{...selectedScript},story_text:directions,cast_id:castId,outfit_mode:selectedOutfit,
        handoff_mode:queueProduct?'queue':'immediate',audio_choices:payload.audio_choices,
        product_option_snapshot:payload.product_option_snapshot,presenter:payload.presenter,
        flow_settings:payload.flow_settings,storytelling_options:payload.storytelling_options,
        generated_music_options:payload.generated_music_options,
        intro_options:payload.intro_options,green_options:payload.green_options,ai_cover_options:payload.ai_cover_options,
        render:payload.render,finish_config:payload.finish_config,actor_dialogue:payload.actor_dialogue,
        fictional_ai_characters_confirmed:payload.fictional_ai_characters_confirmed,
        subtitle:payload.subtitle,subtitle_enabled:payload.subtitle_enabled,visual_style:payload.visual_style,
        visual_style_custom:payload.visual_style_custom,
      };
      const started=Date.now();let phase='กำลังเปิดลิงก์และอ่านข้อมูลสินค้า';
      const updatePreparation=()=>{
        const title=`เตรียมสินค้า ${i+1}/${links.length}`;
        const detail=`${phase} • ${Math.floor((Date.now()-started)/1000)} วินาที • เพิ่มแล้ว ${queuedCount} • ซ้ำ ${duplicateCount+inputDuplicateCount} • ขั้นถัดไป ${payload.provider==='gemini'?'Gemini Web':'ChatGPT Web'}`;
        showPreparation(title,detail);
        if(queueProduct)window.dispatchEvent(new CustomEvent('smartflow:product-batch-progress',{detail:{title,detail,state:'working'}}));
      };
      updatePreparation();elapsedTimer=setInterval(updatePreparation,1000);
      let prepared=await preparationCall('product_story_prepare',{link:links[i],request_id:identity.id,...requestOptions},180000,identity.id);
      if(prepared.pending)toast('กำลังดึงข้อมูลและรูปจากลิงก์สินค้าใน Shopee','info');
      while(prepared.pending){
        phase=prepared.message||'กำลังรอ Extension อ่านชื่อและบันทึกรูปสินค้า';updatePreparation();
        if(Date.now()-started>150000)throw Error('ยังดึงข้อมูลสินค้าไม่ครบ ตรวจหน้า Shopee หรือการเข้าสู่ระบบ แล้วลองใหม่');
        await new Promise(resolve=>setTimeout(resolve,1000));
        prepared=await preparationCall('product_story_prepare',{product_id:prepared.product_id,request_id:prepared.prepare_request_id||identity.id,cast_id:castId,outfit_mode:selectedOutfit},45000,identity.id);
      }
      if(!prepared.creative_context?.snapshot_id || !prepared.topic)throw Error('ข้อมูลสินค้าสำหรับส่ง AI ยังไม่ครบ • ยังไม่ได้เริ่มสร้างคลิป');
      phase='ข้อมูลสินค้าพร้อม กำลังส่งเข้าขั้นสร้างคลิป';updatePreparation();
      const frozen=window.productOptionSnapshot.restore({...requestOptions,...(prepared.prepare_options||{})},payload.product_option_snapshot.form);
      const handoff={...payload,...frozen};delete handoff.product_cast_id;delete handoff.product_story_text;delete handoff._batch_duplicate_count;
      delete handoff.handoff_mode;delete handoff.cast_id;delete handoff.outfit_mode;delete handoff.request_id;
      const sourceId=String(prepared.creative_context.source_product_id||prepared.product_id||'');
      const itemResult=await preparationCall(action,{...handoff,creative_context:prepared.creative_context,topic:prepared.topic,
        story_text:String(frozen.story_text??directions),scene_count:Number(frozen.scene_count)||selectedSceneCount,
        product_script_options:{...(frozen.product_script_options||selectedScript)},
        video_generation_mode:frozen.video_generation_mode||selectedVideoMode,
        provider:frozen.provider||payload.provider||'chatgpt',ai_web_model:frozen.ai_web_model||payload.ai_web_model||'',
        ...(queueProduct?{mode:'story',values:[prepared.topic],request_id:`product-story-${sourceId||identity.id}`}:{})},180000,identity.id);
      if(itemResult?.ok===false)throw Error(itemResult.error||'โปรแกรมยังไม่รับงานสร้างคลิป');
      result=itemResult;
      if(queueProduct){
        queuedCount+=Number(itemResult?.queued||0);
        duplicateCount+=Number(itemResult?.duplicates||0);
        preparedCount++;
        updatePreparation();
      }
      clearPreparationIdentity(identity);
      clearInterval(elapsedTimer);elapsedTimer=null;
    }
    if(queueProduct){
      result={...result,queued:queuedCount,duplicates:duplicateCount+inputDuplicateCount};
      window.dispatchEvent(new CustomEvent('smartflow:product-batch-progress',{detail:{title:'เพิ่มชุดสินค้าเข้าคิวแล้ว',detail:`${preparedCount}/${links.length} รายการ • เพิ่ม ${queuedCount} • ซ้ำ ${duplicateCount+inputDuplicateCount}`,state:'ready'}}));
    }
    showPreparation(queueProduct?'เตรียมสินค้าและเพิ่มเข้าคิวแล้ว':'ส่งข้อมูลสินค้าเข้าขั้นสร้างคลิปแล้ว',
      queueProduct?'ดูรายการและเริ่มงานที่หน้าคิวสร้างคลิป':'ติดตามขั้นตอนต่อในหน้าสถานะงาน ไม่ต้องกดสร้างซ้ำ','ready');
    return result;
    }catch(error){
      const partial=queueProduct&&(preparedCount>0||queuedCount>0||duplicateCount>0)
        ?` • ทำถึง ${preparedCount}/${links.length} สินค้าแล้ว (เพิ่มคิว ${queuedCount} • ซ้ำ ${duplicateCount+inputDuplicateCount}) ตรวจหน้าคิวก่อนลองใหม่ เพื่อไม่เพิ่มซ้ำ`
        :queueProduct?` • ตรวจหน้าคิวก่อนลองใหม่ หากคำสั่งล่าสุดส่งไปแล้ว เพื่อไม่เพิ่มซ้ำ`:'';
      const message=String(error.message||error)+partial;
      showPreparation('เตรียมคลิปสินค้ายังไม่สำเร็จ',message,'error');
      if(queueProduct)window.dispatchEvent(new CustomEvent('smartflow:product-batch-progress',{detail:{title:'หยุดระหว่างเตรียมชุดสินค้า',detail:message,state:'error'}}));
      if(message!==error.message)error.message=message;
      throw error;
    }finally{clearInterval(elapsedTimer);productPreparing=false;window.productPreparationActive=productPreparationUnknown;}
  };
  window.addEventListener('smartflow:resume-product-source',async event=>{
    const detail=event.detail||{},productId=String(detail.product_id||''),requestId=String(detail.request_id||'');
    if(!productId||productPreparing)return;
    productPreparing=true;window.productPreparationActive=true;
    let elapsedTimer;const started=Date.now();let options={};
    try{
      const row=(ui.state?.product_preparations||[]).find(item=>item.id===productId);
      options=row?.prepare_options&&typeof row.prepare_options==='object'?row.prepare_options:{};
      if(options.handoff_mode!=='queue'&&window.smartflowConfirmGeneration&&!(await window.smartflowConfirmGeneration()))return;
      showPreparation('กำลังทำต่อจากสินค้าเดิม','ตรวจชื่อและไฟล์รูปในงานเตรียมเดิม • ยังไม่สร้างงานซ้ำ');
      const update=()=>showPreparation('กำลังทำต่อจากสินค้าเดิม',`กำลังอ่านชื่อและตรวจไฟล์รูปสินค้า • ${Math.floor((Date.now()-started)/1000)} วินาที`);
      elapsedTimer=setInterval(update,1000);
      let prepared=await preparationCall('product_story_prepare',{product_id:productId,request_id:requestId,cast_id:options.cast_id,outfit_mode:options.outfit_mode,retry_capture:true},180000,requestId);
      while(prepared.pending){
        if(Date.now()-started>210000)throw Error('กำลังอ่านสินค้าจากงานเดิมอยู่ • กดทำต่อรายการเดิมอีกครั้งได้ ไม่ต้องวางลิงก์ใหม่');
        await new Promise(resolve=>setTimeout(resolve,1000));
        prepared=await preparationCall('product_story_prepare',{product_id:productId,request_id:prepared.prepare_request_id||requestId,cast_id:options.cast_id,outfit_mode:options.outfit_mode},45000,requestId);
      }
      if(!prepared.creative_context?.snapshot_id||!prepared.topic)throw Error('ข้อมูลสินค้าในงานเดิมยังไม่พร้อม • ยังไม่ได้ส่งเข้า AI');
      if(!window.productOptionSnapshot)throw Error('หน้าสร้างสินค้ายังโหลดไม่ครบ • เปิดหน้าโปรแกรมใหม่ก่อนทำต่อ');
      const frozen=window.productOptionSnapshot.restore({...options,...(prepared.prepare_options||{})},options.handoff_mode==='queue'?'product-batch':'product');
      const payload={...frozen,topic:prepared.topic,creative_context:prepared.creative_context,
        provider:frozen.provider||'chatgpt',ai_web_model:frozen.ai_web_model||'',
        scene_count:Number(frozen.scene_count)||3,video_generation_mode:frozen.video_generation_mode||'google_flow',
        product_script_options:frozen.product_script_options||{version:1,style:'standard'},story_text:String(frozen.story_text||'')};
      delete payload.handoff_mode;delete payload.cast_id;delete payload.outfit_mode;
      const queue=frozen.handoff_mode==='queue';
      const result=await preparationCall(queue?'creation_enqueue':'create_product',queue
        ?{...payload,mode:'story',values:[prepared.topic],request_id:`product-story-${productId}`}
        :payload,180000,requestId);
      if(result?.ok===false)throw Error(result.error||'โปรแกรมยังไม่รับงานสร้างคลิป');
      clearPreparationIdentity({id:requestId});
      showPreparation(queue?'เพิ่มงานสินค้าเดิมเข้าคิวแล้ว':'ส่งสินค้าเดิมไปสร้างคลิปแล้ว',
        queue?'ดูคิวสร้างคลิปเพื่อเริ่มงาน':'ติดตามสถานะในรายการงานต่อ • ไม่สร้างซ้ำ','ready');
      await poll(true);
    }catch(error){
      showPreparation('ทำต่อจากสินค้าเดิมไม่ได้',String(error.message||error),'error');toast(error.message||String(error),'error');
    }finally{clearInterval(elapsedTimer);productPreparing=false;window.productPreparationActive=productPreparationUnknown;}
  });
  if(location.hash==='#product-cast')showPage('product-cast');
})();
