/* Presentation only. No job mutation, provider commands, or autoplay. */
(() => {
  let mode = 'grid', coverReturn = '';
  const groups = new Map();
  try { if (localStorage.getItem('smartflow.library.view') === 'list') mode = 'list'; } catch (_) {}
  const grid = document.querySelector('#library-grid');
  if (!grid) return;
  function applyMode() {
    grid.dataset.mode = mode;
    document.querySelectorAll('[data-library-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.libraryView === mode)));
  }
  document.querySelectorAll('[data-library-view]').forEach(button => button.addEventListener('click', () => {
    mode = button.dataset.libraryView;
    try { localStorage.setItem('smartflow.library.view', mode); } catch (_) {}
    applyMode(); renderLibrary(ui.state?.library || []);
  }));
  const filters = document.querySelector('[aria-label="กรองประเภทวิดีโอ"]');
  const long = document.createElement('button'); long.className = 'filter-chip'; long.dataset.filter = 'longvideo';
  long.setAttribute('aria-pressed', 'false'); long.textContent = 'คลิปยาว'; filters?.append(long);
  grid.addEventListener('toggle', event => {
    if (event.target.matches('details[data-series-group]')) groups.set(event.target.dataset.seriesGroup, event.target.open);
  }, true);
  const detailModal = document.querySelector('#detail-modal');
  detailModal.addEventListener('close', () => { ++ui.libraryDetailTicket; document.querySelector('#detail-content video')?.pause(); });
  document.querySelector('.clip-cover-dialog')?.addEventListener('close', () => {
    if (coverReturn && document.querySelector('#detail-content').dataset.itemId === coverReturn) {
      const image = document.querySelector('#detail-content .library-cover-preview');
      const item = libraryItem(coverReturn);
      if (image && item?.cover_url) image.src = item.cover_url;
      detailModal.showModal();
    }
    coverReturn = '';
  });
  window.libraryView = {
    updateGrid(markup) {
      const template = document.createElement('template'); template.innerHTML = markup;
      const key = (node, index) => node.dataset.cardId || node.dataset.seriesGroup || `extra-${index}`;
      const previous = new Map([...grid.children].map((node, index) => [key(node, index), node]));
      [...template.content.children].forEach((fresh, index) => {
        const id = key(fresh, index), old = previous.get(id), html = fresh.outerHTML;
        const node = old?._libraryMarkup === html ? old : fresh;
        node._libraryMarkup = html;
        if (grid.children[index] !== node) grid.insertBefore(node, grid.children[index] || null);
        if (old && old !== node) old.remove();
        previous.delete(id);
      });
      previous.forEach(node => node.remove());
    },
    mode: () => mode,
    seriesOpen: key => Boolean(groups.get(key)),
    returnFromCover: id => { coverReturn = id; },
    card(item) {
      const image = item.thumbnail_url || item.cover_url || item.preview_url || '';
      const episode = Number(item.episode_no || 0);
      const duration = Number(item.duration_seconds || 0);
      const length = Number.isFinite(duration) && duration > 0 ? formatDuration(duration) : '';
      const coverNotice = item.ai_cover_state?.phase && item.ai_cover_state.phase !== 'ready'
        ? '<span class="cover-hint">ปก AI ยังไม่สำเร็จ • ภาพที่แสดงเป็นภาพเดิม</span>' : '';
      return `<article class="video-card library-compact-card" data-card-id="${escapeHtml(item.item_id)}"><div class="video-cover">${image ? `<img loading="lazy" decoding="async" src="${escapeHtml(image)}" alt="ปก ${escapeHtml(item.title)}">` : '<span class="library-no-cover">ไม่มีภาพปก</span>'}<span class="play-mark" aria-hidden="true">▶</span>${length ? `<span class="library-duration">${escapeHtml(length)}</span>` : ''}</div><div class="video-card-body"><span class="library-kind">${escapeHtml(item.kind_label || '')}${episode ? ` • EP ${episode}` : ''}</span><h3 title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h3>${coverNotice}<div class="video-meta"><span>${escapeHtml(formatDate(item.updated_at))}</span><span>${escapeHtml(item.aspect_ratio || '9:16')}</span></div></div><button class="video-card-button" data-library-id="${escapeHtml(item.item_id)}" aria-label="ดูรายละเอียด ${escapeHtml(item.title)}"></button></article>`;
    },
    decorateDetail(content, item) {
      detailModal.classList.add('library-detail-modal');
      const info = content.querySelector('.detail-info');
      const actions = info.querySelector('.detail-actions');
      const tabs = document.createElement('div'); tabs.className = 'library-detail-tabs'; tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'รายละเอียดผลงาน');
      const panels = ['ข้อมูลโพสต์', 'ปกคลิป', 'รายละเอียดไฟล์'].map((label, index) => {
        const panel = document.createElement('section'); panel.id = `library-tab-panel-${index}`; panel.setAttribute('role', 'tabpanel'); panel.hidden = index !== 0;
        panel.setAttribute('aria-labelledby', `library-tab-${index}`);
        const button = document.createElement('button'); button.type = 'button'; button.id = `library-tab-${index}`; button.textContent = label; button.setAttribute('role', 'tab'); button.setAttribute('aria-controls', panel.id);
        button.setAttribute('aria-selected', String(index === 0)); button.tabIndex = index === 0 ? 0 : -1;
        button.onclick = () => {
          tabs.querySelectorAll('button').forEach((b, i) => { b.setAttribute('aria-selected', String(i === index)); b.tabIndex = i === index ? 0 : -1; panels[i].hidden = i !== index; });
        };
        tabs.append(button); return panel;
      });
      tabs.addEventListener('keydown', event => {
        const buttons = [...tabs.querySelectorAll('button')]; const index = buttons.indexOf(document.activeElement);
        const next = event.key === 'ArrowRight' ? (index + 1) % 3 : event.key === 'ArrowLeft' ? (index + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : -1;
        if (next >= 0) { event.preventDefault(); buttons[next].click(); buttons[next].focus(); }
      });
      info.querySelectorAll('.detail-field').forEach(field => {
        (field.querySelector('[data-copy-key="video_source_label"]') ? panels[2] : panels[0]).append(field);
      });
      const cover = item.cover_url || item.preview_url;
      if(item.ai_cover_state?.phase){const note=document.createElement('p');note.className='cover-hint';
        note.textContent=item.ai_cover_state.phase==='ready'?'ปก AI สร้างสำเร็จแล้ว':`ปก AI ยังไม่สำเร็จ • ภาพที่แสดงเป็นภาพเดิม ไม่ใช่ผลปก AI รอบนี้ • ${window.smartflowSafeError?.(item.ai_cover_state.message || item.ai_cover_state.phase)||'ตรวจรายละเอียดงาน'}`;panels[1].append(note);}
      if (cover) { const img = document.createElement('img'); img.src = cover; img.alt = item.cover_url ? 'ปกคลิปที่บันทึกไว้' : 'ภาพฉากตัวอย่าง ยังไม่มีปกแยก'; img.className = 'library-cover-preview'; panels[1].append(img); }
      content.querySelectorAll('.detail-cover-button').forEach(button => panels[1].append(button));
      for (const [label, value] of [['รหัสงาน', item.job_id], ['ขนาดไฟล์', formatBytes(item.size_bytes)], ['สัดส่วน', item.aspect_ratio || '9:16'], ['ไฟล์', item.file_name]]) {
        const line = document.createElement('p'); line.className = 'library-file-row'; line.textContent = `${label}: ${value || '—'}`; panels[2].append(line);
      }
      info.insertBefore(tabs, actions); panels.forEach(panel => info.insertBefore(panel, actions));
      const menu = document.createElement('details'); menu.className = 'library-detail-menu';
      const summary = document.createElement('summary'); summary.className = 'button ghost'; summary.textContent = '⋯ เพิ่มเติม'; menu.append(summary);
      const list = document.createElement('div'); menu.append(list);
      [...actions.children].forEach(button => { if (button.matches('[data-detail-play],[data-detail-delete-video],[data-detail-delete-project]')) list.append(button); });
      actions.append(menu);
    }
  };
  applyMode();
  if (ui.state?.library) renderLibrary(ui.state.library);
})();
