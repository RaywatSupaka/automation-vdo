/* Conversation transport recovery. It never clears a receipt or sends a prompt. */
(() => {
  function inspect() {
    const url = location.href.split(/[?#]/)[0];
    const home=/^https:\/\/chatgpt\.com\/?$/.test(url);
    if (!home && !/^https:\/\/chatgpt\.com\/c\/[a-zA-Z0-9_-]+\/?$/.test(url)) return {state:'outside',url};
    const visible = el => {
      const rect=el.getBoundingClientRect(), css=getComputedStyle(el);
      return rect.width>0 && rect.height>0 && css.display!=='none' && css.visibility!=='hidden';
    };
    const shown = selector => [...document.querySelectorAll(selector)].filter(visible);
    const excluded = '[data-message-author-role],[data-testid^="conversation-turn-"],[data-chatgpt-search-unit-key],nav,aside,pre,code,textarea,[contenteditable="true"]';
    const normalize = value => String(value||'').trim().replace(/\s+/g,' ');
    const error = /^(?:ไม่สามารถโหลดการสนทนา(?: ChatGPT)? ?(?:นี้)?ได้|Unable to load conversation(?: [a-zA-Z0-9_-]+)?|This conversation could not be loaded)\.?$/i;
    const titles=shown('h1,h2,h3,[role="heading"],div,p').filter(el=>!el.closest(excluded)
      && error.test(normalize(el.textContent)) && ![...el.children].some(child=>error.test(normalize(child.textContent))));
    const retry=shown('button,[role="button"]').filter(el=>!el.closest(excluded)
      && /^(?:ลองใหม่|Try again|Retry)$/i.test(normalize(el.textContent)));
    const editor=shown('#prompt-textarea,textarea,[contenteditable="true"]').find(el=>!el.closest('nav,aside'));
    const draft=Boolean(editor && normalize(editor.value||editor.textContent));
    const busy=shown('[data-testid="stop-button"],button[aria-label="Stop streaming"],button[aria-label="หยุดสตรีม"],[aria-busy="true"],[role="progressbar"]').length>0;
    const result=shown('[data-message-author-role="assistant"],[data-chatgpt-search-unit-key$=":assistant"],main video')
      .some(el=>normalize(el.textContent) || el.querySelector('img,video'));
    if(draft || busy) return {state:'protected',url};
    if(home) {
      const login=shown('button,a').some(el=>/^(?:Log in|Sign in|เข้าสู่ระบบ)$/i.test(normalize(el.textContent)));
      const attachments=shown('[data-testid*="attachment"],form img,form video');
      return {state:!login && editor && !result && !attachments.length
        && !shown('[data-message-author-role], [data-testid^="conversation-turn-"]').length
        && document.readyState==='complete'?'fresh_ready':'protected',url};
    }
    if(result)return {state:editor?'ready':'loading',url};
    // The panel must be a small, explicit error + retry surface, not quoted chat text.
    const panel=titles.find(title=>{
      for(let node=title.parentElement, depth=0;node && node!==document.body && depth<5;node=node.parentElement,depth++) {
        if(normalize(node.textContent).length>350)break;
        if(retry.some(button=>node.contains(button)) && !node.querySelector(excluded))return true;
      }
      return false;
    });
    if(panel && document.readyState==='complete')return {state:'unavailable',url};
    return {state:editor?'ready':'loading',url};
  }

  // One durable reload, then ONE tagged replacement tab of the SAME URL.
  // Only an explicitly authorized pending-step adapter can escalate a repeated
  // native error into a new conversation. It is not proof of backend failure.
  async function advance(io, record) {
    const current=await io.validate(record);
    if(!current)return;
    record=current;
    if(io.now()<Number(record.next_at||0))return;
    if(record.phase.startsWith('fresh_'))return io.fresh(record);
    let view=await io.inspect(record.tab_id);
    if(record.phase==='replacement' && view?.url===record.allocation_url) {
      await io.validate(record);await io.navigate(record.tab_id,record.url);return;
    }
    if(!view || view.url!==record.url || !view.document_id)return;
    const save=async patch=>{record=await io.save(record,patch);return record;};
    if(record.phase==='observing') {
      if(view.state!=='unavailable')return io.save(record,{phase:'aborted'});
      if(view.document_id!==record.document_id)return io.save(record,{phase:'aborted'});
      if(io.now()-record.first_at<10000)return;
      await save({phase:'reload_intent',previous_document_id:view.document_id,next_at:io.now()+15000});
      // Final post-storage check; a late result, draft or busy indicator wins.
      view=await io.inspect(record.tab_id);
      if(view?.state!=='unavailable'||view.document_id!==record.previous_document_id)
        return io.save(record,{phase:'aborted'});
      await io.validate(record);
      await io.reload(record.tab_id); // intent persists if ACK is lost
      return;
    }
    if(record.phase==='reload_intent') {
      if(view.document_id===record.previous_document_id)return; // Unknown reload is not a second reload.
      await save({phase:'checking',document_id:view.document_id,checked_at:io.now(),next_at:io.now()+10000});
      return;
    }
    if(['allocating','allocated'].includes(record.phase) && view.state!=='unavailable')
      return io.save(record,{phase:'aborted'});
    if(record.phase==='checking' && view.document_id!==record.document_id)
      return io.save(record,{document_id:view.document_id,checked_at:io.now(),next_at:io.now()+10000});
    if(['checking','replacement'].includes(record.phase) && view.state==='ready') {
      await save({phase:'resuming',document_id:view.document_id,next_at:io.now()+30000});
      await io.resume(record); // exact pending checkpoint; no new conversation/request
      return io.save(record,{phase:'resumed'});
    }
    if(record.phase==='resuming') {
      if(view.state==='ready') {await io.resume(record);return io.save(record,{phase:'resumed'});}
      return; // ambiguous Start ACK cannot allocate/replay another operation
    }
    if(record.phase==='checking' && view.state==='unavailable') {
      const allocation_url='about:blank#smartflow-conversation-recovery='+record.token;
      await save({phase:'allocating',allocation_url,next_at:0});
      await io.validate(record);
      const last=await io.inspect(record.tab_id);
      if(last?.state!=='unavailable'||last.document_id!==record.document_id)
        return io.save(record,{phase:'aborted'});
      const tab=await io.create(allocation_url); // durable intent BEFORE allocation
      await save({phase:'allocated',replacement_tab_id:tab.id});
    }
    if(record.phase==='allocating') {
      const matches=await io.find(record.allocation_url);
      if(matches.length!==1)return; // lost create ACK: no blind second tab
      await save({phase:'allocated',replacement_tab_id:matches[0].id});
    }
    if(record.phase==='allocated') {
      await io.transfer(record);
      await save({phase:'replacement',tab_id:record.replacement_tab_id,next_at:io.now()+15000});
      await io.navigate(record.tab_id,record.url);
      return;
    }
    if(record.phase==='replacement' && view.state==='unavailable') {
      if(record.replacement_document_id!==view.document_id)
        return io.save(record,{replacement_document_id:view.document_id,next_at:io.now()+15000});
      // Explicitly authorized exception: persistent native load failure, not
      // timeout or refusal. The original backend result remains UNKNOWN.
      if(record.allow_pending_fresh===true && ['analysis','image'].includes(record.resume?.stage))
        return io.fresh(record);
      return io.save(record,{next_at:io.now()+60000});
    }
  }
  globalThis.SmartFlowConversationRecovery={inspect,advance};
})();
