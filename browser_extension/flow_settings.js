/* Pure visible-menu reader. No clicks, text entry, account data or generation. */
globalThis.SmartFlowSettings = {
  // Arm only after an exact visible-menu verification and closing the menu.
  // Any subsequent settings mutation invalidates that proof, not the draft or receipt.
  watch: function(token) {
    const previous = globalThis.__smartFlowSettingsWatch;
    previous?.observer?.disconnect();
    const selector = 'flow-prompt-box-settings,button[aria-label="Settings trigger"],button[aria-label="ทริกเกอร์การตั้งค่า"],.base-prompt-box button[aria-label="Settings"],button[aria-label="settings"],button[aria-label="การตั้งค่า"]';
    const touches = node => node?.nodeType === 1
      ? Boolean(node.matches?.(selector) || node.closest?.(selector))
      : Boolean(node?.parentElement?.closest?.(selector));
    const state = {token, url:location.href, valid:true};
    state.inspect = records => {
      if (records.some(record => touches(record.target)
        || [...record.addedNodes,...record.removedNodes].some(node=>touches(node) || node.querySelector?.(selector)))) state.valid=false;
    };
    state.observer = new MutationObserver(state.inspect);
    state.observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true});
    globalThis.__smartFlowSettingsWatch=state;
    return true;
  },
  checkWatch: function(token, consume=false) {
    const state=globalThis.__smartFlowSettingsWatch;
    if (!state || !token || state.token!==token) return false;
    state.inspect(state.observer.takeRecords());
    const valid=state.valid && state.url===location.href;
    if (consume) {state.valid=false;state.observer.disconnect();}
    return valid;
  },
  selectProjectTab: function(activeTabs=[],allTabs=[]) {
    const project=tab=>/^https:\/\/(?:flow\.google\.com\/project\/[^/?#]+|labs\.google\/[^?#]*\/project\/[^/?#]+)/i.test(tab?.url||'');
    const active=activeTabs.filter(project);
    if(active.length===1)return active[0];
    const candidates=allTabs.filter(project);
    if(candidates.length===1)return candidates[0];
    throw new Error(candidates.length ? 'มีหลายโปรเจกต์ Flow กรุณาเลือกแท็บโปรเจกต์ที่จะตรวจ แล้วอ่านค่าอีกครั้ง' : 'เปิดโปรเจกต์ Google Flow ก่อนอ่านตัวเลือก');
  },
  read: function(requested = {}) {
    const visible = e => { const r=e?.getBoundingClientRect(), s=e && getComputedStyle(e); return !!(r && r.width>0 && r.height>0 && r.bottom>0 && r.top<innerHeight && s.visibility!=='hidden' && s.display!=='none'); };
    const enabled = e => !e.disabled && e.getAttribute('aria-disabled')!=='true';
    const text = e => {const c=e?.cloneNode(true);c?.querySelectorAll('mat-icon,[aria-hidden="true"]').forEach(n=>n.remove());return (c?.textContent||'').trim().replace(/\s+/g,' ');};
    const point = e => {if(!e || !visible(e) || !enabled(e))return null; const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,h=document.elementFromPoint(x,y);return h&&(h===e||e.contains(h))?{x,y}:null;};
    const panels=[...document.querySelectorAll('flow-prompt-box-settings')].filter(visible);
    if(panels.length!==1)return {available:false,selected:{},targets:{}};
    const panel=panels[0],selected={},targets={},result={available:true,scope:'visible_menu_only',selected,targets,states:{}};
    const translations={'Video type':'ประเภทวิดีโอ','Video resolution':'ความละเอียดของวิดีโอ','Video duration':'ระยะเวลาของวิดีโอ'};
    const canonical=(key,value)=>key==='video_type'?({'เฟรม':'Frames','องค์ประกอบ':'Ingredients'}[value]||value):key==='duration'?value.replace(/^(\d+)\s*(?:วินาที|seconds?|s)$/i,'$1s'):value;
    for(const [key,label] of Object.entries({video_type:'Video type',resolution:'Video resolution',duration:'Video duration'})){
      const group=panel.querySelector(`flow-toggles[aria-label="${label}"],flow-toggles[aria-label="${translations[label]}"]`);
      const radios=[...(group?.querySelectorAll('[role="radio"]')||[])].filter(visible);
      result[key]=radios.filter(enabled).map(e=>canonical(key,text(e)));
      const checked=radios.find(e=>e.getAttribute('aria-checked')==='true');
      selected[key]=checked&&enabled(checked)?canonical(key,text(checked)):'';
      result.states[key]=checked&&!enabled(checked)?'disabled':group?'selectable':'unknown';
      targets[key]=point(radios.find(e=>canonical(key,text(e))===canonical(key,requested[key]||'')));
    }
    const model=panel.querySelector('button[aria-label="Select model family"],button[aria-label="เลือกกลุ่มผลิตภัณฑ์โมเดล"]');
    selected.model=text(model);result.model=selected.model?[selected.model]:[];result.model_open=point(model);
    const menus=[...document.querySelectorAll('[role="listbox"],[role="menu"]')].filter(visible);
    // A model option must belong to the popup controlled by the model button.
    const controlled=model?.getAttribute('aria-controls');
    const menu=controlled ? menus.find(e=>e.id===controlled) : null;
    result.model_menu_open=Boolean(menu);
    if(menu){const options=[...menu.querySelectorAll('[role="option"],[role="menuitem"],[role="menuitemradio"]')].filter(e=>visible(e)&&enabled(e));result.model=[...new Set([...result.model,...options.map(text)])];targets.model=point(options.find(e=>text(e)===requested.model));}
    const summaries=[...document.querySelectorAll('button[aria-label="Settings trigger"],button[aria-label="ทริกเกอร์การตั้งค่า"]')].filter(visible);
    if(result.states.resolution==='unknown' && summaries.length===1){
      const fixed=text(summaries[0]).match(/\b(360p|480p|720p|1080p|1440p|2160p|4K)\b/i)?.[1];
      if(fixed){selected.resolution=fixed;result.resolution=[fixed];result.states.resolution='fixed_from_summary';}
    }
    result.context={model:selected.model,video_type:selected.video_type,
      aspect_ratio:text(panel.querySelector('flow-toggles[aria-label="Aspect ratio"] [aria-checked="true"],flow-toggles[aria-label="สัดส่วนภาพ"] [aria-checked="true"]')),
      layout:innerWidth<=600?'compact':'desktop'};
    result.credit_notice=(panel.textContent||'').match(/(?:Generating will use\s*\d+\s*credits|การสร้างจะใช้\s*\d+\s*เครดิต)/i)?.[0]?.replace(/\s+/g,' ')||'';
    return result;
  }
};
