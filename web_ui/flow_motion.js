/* Explicit provenance confirmation; never infer fictional identity from a face. */
(() => {
  const controls = new Map();
  for (const [key,selector] of Object.entries({product:'#product-video-provider',story:'#story-video-mode','story-batch':'#story-batch-video-mode',drama:'#drama-video-mode',long:'#long-mode','product-batch':'#creation-form .cq-buttons'})) {
    const anchor=document.querySelector(selector); if(!anchor)continue;
    const label=document.createElement('label');label.className='check-row';
    const input=document.createElement('input');input.type='checkbox';input.dataset.flowFictional=key;
    label.append(input,document.createTextNode(' ยืนยันว่าบุคคลทุกคนในภาพเป็นตัวละครสมมติจาก AI ไม่ใช่บุคคลจริง'));
    (anchor.closest('label') || anchor).after(label);controls.set(key,input);
  }
  const previousPrepare=window.prepareAudioQueue;
  window.prepareAudioQueue=item=>{
    previousPrepare?.(item);
    const control=controls.get('product-batch');if(control)control.checked=(item?.settings?.fictional_ai_characters_confirmed ?? controls.get('product')?.checked) === true;
  };
  const previous=postAction;
  postAction=async(action,payload={})=>{
    const key=window.smartflowCreationFormKey(action,payload);
    if(key && !payload.job_id && controls.has(key))payload={...payload,fictional_ai_characters_confirmed:controls.get(key).checked};
    return previous(action,payload);
  };
})();
