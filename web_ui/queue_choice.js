/* Route only fresh form submissions, after all option snapshots are collected. */
(() => {
  const forms=[['product','create-product'],['story','create-story'],['drama','create-drama-series'],['long','create-longvideo']];
  for(const [key,id] of forms){
    const button=document.getElementById(id);if(!button)continue;
    const label=document.createElement('label');label.className='cq-check';
    label.innerHTML=`<input type="checkbox" id="${key}-queue-only"> เก็บเข้าคิวไว้ก่อน — ค่อยกดเริ่มที่หน้าคิว (งานปัจจุบันทำต่อจนจบ)`;
    button.before(label);
  }
  window.routeCreationQueue=(action,payload)=>{
    if(payload.job_id||window.productOptionSnapshot?.isFrozen(payload)
      ||payload.creative_context?.kind==='product_story')return {action,payload};
    const key=action==='enqueue_long_video'?'long':action==='create_product'?'product':action==='create_story'?(payload.long_video?'long':'story'):action==='create_drama_series'?'drama':'';
    if(!key || !document.getElementById(`${key}-queue-only`)?.checked)return {action,payload};
    if(key==='drama')return {action,payload:{...payload,enqueue_only:true,queue_only:true},queued:true};
    if(key==='long')return {action:'enqueue_long_video',payload:{...payload,queue_only:true},queued:true};
    return {action:'creation_enqueue',payload:{...payload,mode:key,values:[key==='product'?payload.link:payload.topic],queue_only:true},queued:true};
  };
})();
