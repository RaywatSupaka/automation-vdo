/* Compact, searchable selectors from the desktop-owned creative catalog. */
(() => {
  let catalog={product:[],story:[]};const pickers=[];
  const copy=value=>JSON.parse(JSON.stringify(value));
  window.creativeProductOptions=(style,genre='auto',ending_cta=true)=>style==='short_film_ad'
    ?{version:2,style,genre,ending_cta}:['standard','story_first_review'].includes(style)?{version:1,style}:{version:3,style};
  window.creativeLabel=(kind,value)=>catalog[kind]?.find(item=>item.value===value)?.label||value;
  window.creativeJobLabel=(row,state={})=>{
    const brief=row?.creative_brief||(state.stories||[]).find(job=>job.id===row?.job_id)?.creative_brief;
    if(brief?.title)return 'แนวที่ใช้: '+String(brief.title).slice(0,100);
    const product=row?.settings?.product_script_options,story=row?.settings?.story_structure_options;
    return product?'แนวบท: '+window.creativeLabel('product',product.style):story?'โครงเรื่อง: '+window.creativeLabel('story',story.structure):'';
  };
  window.mountCreativePicker=({host,kind,id,value,read,onChange,label})=>{
    let selected=value||(kind==='product'?'standard':'legacy');
    const box=document.createElement('div');box.className='creative-picker';box.dataset.creativeKind=kind;
    const caption=document.createElement('span');caption.textContent=label||(kind==='product'?'แนวบท':'โครงเรื่อง');
    const button=document.createElement('button');button.type='button';button.className='button ghost creative-current';button.id=id;
    button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-label',caption.textContent+' • เปลี่ยน');
    button.setAttribute('aria-controls',id+'-dialog');button.setAttribute('aria-expanded','false');
    const selectedLabel=document.createElement('span');selectedLabel.className='creative-current-label';
    const changeLabel=document.createElement('span');changeLabel.className='creative-current-action';changeLabel.textContent=' · เปลี่ยน';
    button.append(selectedLabel,changeLabel);
    const hint=document.createElement('small');hint.id=id+'-hint';button.setAttribute('aria-describedby',hint.id);
    box.append(caption,button,hint);host.append(box);
    const dialog=document.createElement('dialog');dialog.id=id+'-dialog';dialog.className='modal creative-dialog';dialog.setAttribute('aria-labelledby',id+'-title');
    const body=document.createElement('div');body.className='modal-card';
    const header=document.createElement('div');header.className='creative-header';
    const title=document.createElement('h2');title.id=id+'-title';title.textContent='เลือก'+caption.textContent;
    const dismiss=document.createElement('button');dismiss.type='button';dismiss.className='button ghost creative-close';dismiss.textContent='×';dismiss.setAttribute('aria-label','ปิดตัวเลือก'+caption.textContent);
    header.append(title,dismiss);
    const search=document.createElement('input');search.className='creative-search';search.type='search';search.placeholder='ค้นหาชื่อแนวหรือคำอธิบาย';search.setAttribute('aria-label','ค้นหา'+caption.textContent);
    const list=document.createElement('div');list.className='creative-options';
    const example=document.createElement('p');example.className='creative-example';example.setAttribute('aria-live','polite');
    const footer=document.createElement('div');footer.className='creative-footer';
    const note=document.createElement('small');note.textContent='เลือกแล้วใช้กับบทใหม่ • ไม่เปลี่ยนงานเดิม';
    const close=document.createElement('button');close.type='button';close.className='button ghost';close.textContent='กลับ';
    footer.append(note,close);body.append(header,search,example,list,footer);dialog.append(body);document.body.append(dialog);
    function current(){return read?.()||selected;}
    function refresh(){
      selected=current();const item=catalog[kind]?.find(row=>row.value===selected);
      selectedLabel.textContent=item?.label||({standard:'รีวิวปกติ',legacy:'ตามเนื้อเรื่องเดิม',auto:'ให้ AI คิดให้'}[selected])||selected;
      button.setAttribute('aria-label',caption.textContent+': '+selectedLabel.textContent+' • เปลี่ยน');
      hint.textContent=item?.description||'ใช้กับบทใหม่ • งานที่ทำต่อใช้แนวที่บันทึกไว้';
    }
    function options(){
      list.replaceChildren();const query=search.value.trim().toLowerCase();let lastGroup='',count=0;
      for(const item of catalog[kind]||[]){
        if(query&&!`${item.label} ${item.description}`.toLowerCase().includes(query))continue;
        const group=item.group||'แนวใหม่';if(group!==lastGroup){const heading=document.createElement('strong');heading.textContent=({เดิม:'รูปแบบหลัก',AI:'ให้ AI ช่วยเลือก',แนวใหม่:'ไอเดียเพิ่มเติม'}[group])||group;heading.className='creative-group';list.append(heading);lastGroup=group;}
        const option=document.createElement('button');option.type='button';option.className='creative-option';option.dataset.creativeValue=item.value;
        const name=document.createElement('span');name.className='creative-option-title';name.textContent=item.label;
        const description=document.createElement('small');description.textContent=item.description;
        option.append(name,description);option.setAttribute('aria-pressed',String(item.value===current()));count++;
        option.addEventListener('click',()=>{selected=item.value;onChange?.(item.value);refresh();dialog.close();button.focus();});list.append(option);
      }
      example.textContent=query?`พบ ${count} รูปแบบ`:`${count} รูปแบบ • เลือกได้ 1 แนว`;
      if(!list.children.length){const empty=document.createElement('p');empty.className='creative-empty';empty.textContent=query?'ไม่พบแนวที่ตรงกับคำค้น ลองใช้คำอื่น':'กำลังโหลดรายการแนวบท';list.append(empty);}
      list.scrollTop=0;
    }
    button.addEventListener('click',()=>{refresh();search.value='';options();dialog.showModal();button.setAttribute('aria-expanded','true');search.focus();});
    search.addEventListener('input',options);close.addEventListener('click',()=>dialog.close());dismiss.addEventListener('click',()=>dialog.close());
    dialog.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.isComposing){event.preventDefault();event.stopPropagation();dialog.close();}});
    dialog.addEventListener('close',()=>{button.setAttribute('aria-expanded','false');button.focus();});
    const picker={get:current,set(next){selected=next;onChange?.(next);refresh();},refresh,refreshCatalog(){refresh();if(dialog.open)options();},element:box};pickers.push(picker);refresh();return picker;
  };
  window.mountCreativeRadioPicker=({host,kind='product',id,radioName,grid,onChange})=>{
    const read=()=>host.querySelector(`input[name="${radioName}"]:checked`)?.value||'standard';
    const picker=window.mountCreativePicker({host,kind,id,read,onChange:value=>{
      let radio=host.querySelector(`input[name="${radioName}"][value="${value}"]`);
      if(!radio){radio=document.createElement('input');radio.type='radio';radio.name=radioName;radio.value=value;radio.hidden=true;host.append(radio);}
      radio.checked=true;onChange?.(value);host.dispatchEvent(new Event('change',{bubbles:true}));
    }});
    host.querySelector(grid)?.setAttribute('hidden','');
    host.addEventListener('change',()=>picker.refresh());return picker;
  };
  window.renderCreativeCatalog=value=>{
    if(value?.version!==1||!Array.isArray(value.product)||!Array.isArray(value.story))return;
    const next=copy(value);if(JSON.stringify(catalog)===JSON.stringify(next)){pickers.forEach(picker=>picker.refresh());return;}
    catalog=next;pickers.forEach(picker=>picker.refreshCatalog());
  };
})();
