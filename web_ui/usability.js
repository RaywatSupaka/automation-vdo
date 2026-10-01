/* Presentation only: retain existing actions, queue ownership and saved settings. */
(() => {
  const longButton = document.querySelector('#create-longvideo');
  if (longButton) {
    const queue = document.createElement('button'); queue.type='button'; queue.className='button secondary'; queue.textContent='เพิ่มลงคิว';
    queue.addEventListener('click',()=>submitLongVideo(true)); longButton.after(queue);
    const start = document.createElement('button'); start.type='button'; start.className='button ghost'; start.textContent='ดูคิวสร้างคลิป';
    start.addEventListener('click',()=>document.querySelector('.navigation [data-page="creation"]').click()); queue.after(start);
  }
  const find = selector => document.querySelector(selector);
  const dashboard = find('[data-view="dashboard"]');
  const overview = dashboard?.querySelector('.dashboard-grid');
  if (overview) dashboard.prepend(overview);
  document.querySelectorAll('select option[value="google_flow"]').forEach(option => {
    option.textContent = 'สร้างวิดีโอด้วย Google Flow';
    const field = option.closest('.field');
    if (!field || field.querySelector('.flow-policy-note')) return;
    const note = document.createElement('small');
    note.className = 'flow-policy-note';
    note.textContent = 'หากถูกปฏิเสธ ระบบกู้คืนตามเงื่อนไขของงาน หากใช้ภาพฉากเดิมแทนคลิป Flow จะแจ้งในผลลัพธ์ • คิวบริการหนาแน่นไม่ใช่งานล้มเหลว';
    field.append(note);
  });
  const saveStyle = find('#subtitle-save-style');
  if (saveStyle) saveStyle.textContent = 'บันทึกค่า Subtitle';
  const applyStyle = find('#subtitle-apply-style');
  if (applyStyle) applyStyle.textContent = 'บันทึกและประกอบงานที่เลือกใหม่';
  const dramaQueue = find('#drama-queue-toggle');
  if (dramaQueue) {
    const note = document.createElement('p');
    note.className = 'usability-note';
    note.textContent = 'พักคิว: คลิปที่กำลังทำจะทำจนจบ แล้วพักก่อนเริ่มคลิปถัดไป';
    dramaQueue.after(note);
  }
  const version = find('.side-version b');
  if (version?.textContent === 'PREVIEW 1') version.textContent = 'DESKTOP';
})();
