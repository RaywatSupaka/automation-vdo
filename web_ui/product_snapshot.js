/* Capture the existing option wrapper stack locally before any Shopee request. */
(() => {
  const captureKey=Symbol('product option capture');
  const copy=value=>JSON.parse(JSON.stringify(value));
  const object=value=>value && typeof value==='object' && !Array.isArray(value);
  function freeze(value){
    if(value && typeof value==='object' && !Object.isFrozen(value)){
      Object.values(value).forEach(freeze);Object.freeze(value);
    }
    return value;
  }
  function marker(payload){
    const saved=payload?.product_option_snapshot;
    if(saved===undefined)return null;
    if(!object(saved)||Object.keys(saved).sort().join(',')!=='form,version'||saved.version!==1||!['product','product-batch'].includes(saved.form))
      throw Error('ข้อมูลตัวเลือกสินค้าที่บันทึกไว้ไม่ถูกต้อง • ยังไม่ได้เริ่มงาน');
    return saved;
  }
  function savedOptions(payload,form){
    const selected=copy(payload),saved=marker(selected);
    // An old preparation may have explicit choices but no schema marker. Missing
    // paid-audio choices need review; current controls are never recovery data.
    if(!object(selected.audio_choices)||!['api','flow_original','none'].includes(selected.audio_choices.mode))
      throw Error('ตัวเลือกเสียงของงานเตรียมสินค้าเดิมไม่ครบ • เก็บงานเดิมไว้และตรวจตัวเลือกก่อนทำต่อ');
    selected.product_option_snapshot={version:1,form:saved?.form||form};
    selected.subtitle=selected.audio_choices.subtitle===true;
    selected.subtitle_enabled=selected.subtitle;
    for(const [key,fallback] of Object.entries({flow_settings:{},ai_cover_options:{enabled:false,headline:'',scene_index:0},
      intro_options:{enabled:false,file:''},green_options:{enabled:false,clips:[],opacity:.5,fit:'contain'},presenter:{enabled:false}})){
      if(selected[key]!==undefined&&!object(selected[key]))throw Error('ข้อมูลตัวเลือกสินค้าที่บันทึกไว้ไม่ครบ • ยังไม่ได้เริ่มงาน');
      if(selected[key]===undefined)selected[key]=fallback;
    }
    selected.fictional_ai_characters_confirmed=selected.fictional_ai_characters_confirmed===true;
    selected.actor_dialogue=selected.actor_dialogue===true;
    return freeze(selected);
  }
  window.productOptionSnapshot={
    isFrozen:payload=>Boolean(marker(payload)),
    async capture(action,payload,dispatch){
      const form=action==='creation_enqueue'?'product-batch':'product';
      const draft=copy(payload);delete draft.product_option_snapshot;
      // Symbol survives object spreads but can never become a backend field.
      return dispatch(action,{...draft,[captureKey]:form});
    },
    finish(action,payload){
      const form=payload[captureKey];if(!form)return null;
      const routed=window.routeCreationQueue?.(action,payload)||{action,payload};
      return freeze({action:routed.action,payload:savedOptions(routed.payload,form)});
    },
    restore:(payload,form='product')=>savedOptions(payload,form),
  };
})();
