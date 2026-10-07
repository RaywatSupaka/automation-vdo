# ส่งมอบงานออกแบบ UX/UI SmartFlow AI: ส่วนที่เหลือ (ขั้น 2–4 และงานเก็บกวาด)

เอกสารนี้เขียนให้ AI หรือนักพัฒนาอีกคนทำงานต่อได้โดยไม่ต้องถามผู้เขียน อ่านจบแล้วควรรู้ว่าทำอะไร ทำที่ไหน ทดสอบอย่างไร และอะไรห้ามแตะ

- วันที่: 2026-10-07 · branch `dev` · ขั้น 1 อยู่ใน commit `7237d19` (`feat(ui): add shared status vocabulary, one palette and grouped sidebar`)
- เจ้าของโปรเจกต์พูดไทย: ข้อความที่ผู้ใช้เห็นทั้งหมดเป็นภาษาไทย
- ดีไซน์อ้างอิง (ซอร์ส): `docs/design/ux-redesign-2026-10/*.dc.html` เปิดดูเป็นข้อความได้ แต่เรนเดอร์เองไม่ได้ เพราะต้องใช้ runtime ของ canvas ภาพที่เรนเดอร์แล้วอยู่ใน canvas "SmartFlow AI UX Redesign" (ส่วนตัวของเจ้าของ ต้องให้เจ้าของแชร์)
- ให้อ่าน `AGENTS.md` ก่อนทุกครั้ง กติกาใน `AGENTS.md` ชนะเอกสารนี้

---

## 0. กติกาที่ต้องรักษา (ละเมิดแล้วเสียหายจริง)

1. **เปลี่ยนเฉพาะชั้นหน้าจอ** ห้ามเปลี่ยนชื่อ action, endpoint, Job schema, checkpoint, receipt และกฎ "ห้ามส่งซ้ำเมื่อ Send ไม่แน่ใจ" ธุรกิจต้องอยู่ใน backend (`ui/main_window.py`, `core/*`)
2. **ห้ามรีสตาร์ตหน้าต่าง DEV หรือรีโหลด Extension** ถ้าคิวของเจ้าของกำลังทำงาน (อ่าน `CODEX_START_HERE.md` และบนสุดของ `PROJECT_STATE.md`) แก้ซอร์สแล้วรายงานว่า "รอเปิดใหม่ตอนว่าง"
3. **ต้องใช้ข้อมูลจริงเท่านั้น** ห้ามแสดงสถานะที่ระบบไม่มีข้อมูลรองรับ ดูหัวข้อ 3.3 ซึ่งดีไซน์เดิมวาดเช็กลิสต์ที่ข้อมูลยังไม่มี
4. **ห้ามรีเซ็ต ห้าม clean และห้ามกู้ไฟล์ทั้งไฟล์จาก backup** working tree อาจมีงานค้างของคนอื่น เช็ก `git status` ก่อนแก้ ดูวิธี commit แยกงานในหัวข้อ 7
5. **ทุกขั้นต้องมี focused test** และ mapping ใน `tools/run_focused_tests.py` (CI ล้มเมื่อไฟล์โค้ดที่แก้ไม่มี mapping)

## 1. สิ่งที่ขั้น 1 ทำไว้แล้ว (ใช้ต่อ อย่าทำซ้ำ)

| ของที่มีแล้ว | อยู่ที่ | ใช้ยังไง |
|---|---|---|
| คำสถานะ 6 แบบ | `web_ui/status_vocabulary.js` → `window.SmartFlowStatus` | `SmartFlowStatus.pill(code, {resumable, extraClass, label})`, `.label(code)`, `.tone(code)`, `.resolve(code)`, `.pauseReason(key)` |
| โทเคนสีชุดเดียวและสไตล์ pill | `web_ui/foundation.css` (โหลดหลังสุด) | ตัวแปร `--bg --surface --text --muted --cyan ...` และ `--st-<state>-bg/-fg` |
| เมนูข้างแบบกลุ่ม | `web_ui/index.html` (`<details class="nav-group">`) | `showPage()` ใน `app.js` เปิดกลุ่มของหน้าปัจจุบันเอง |
| suite ทดสอบ | `--feature ui-foundation` | static contract, logic, เบราว์เซอร์ (layout, contrast) |

คำสถานะทั้ง 6 และการตัดสินใจเรื่อง "ทำต่อได้":

| รหัส backend ตัวอย่าง | แสดงว่า | ใช้เมื่อ |
|---|---|---|
| `queued` | รอคิว | อยู่ในคิว ยังไม่เริ่ม |
| `running` | กำลังสร้าง | ทำอยู่ |
| `action_required`, `needs_attention`, `login_required`, `image_review` | รอคุณ | โปรแกรมทำต่อเองไม่ได้ ต้องให้คนทำ |
| `failed`, `error` | สะดุด (หรือ `สะดุด · ทำต่อได้`) | ใส่ `resumable:true` **เฉพาะ**หน้าที่มีปุ่มทำต่อจริง |
| `cancelled` + มี `job_id` | หยุดไว้ | หยุดแล้วทำต่อได้ |
| `completed` | เสร็จแล้ว | มีวิดีโอในคลัง |

ตัวอย่างการใช้:

```js
// แถวงานในหน้าใหม่ (ห้ามเขียนป้ายสถานะเองแบบ 'รอทำงาน' อีก)
const info = SmartFlowStatus.resolve(row.status, {resumable: Boolean(row.job_id) && row.mode !== 'drama'});
const html = `<article class="job-row" data-tone="${info.tone}">
  ${SmartFlowStatus.pill(row.status, {resumable: Boolean(row.job_id) && row.mode !== 'drama'})}
  <h3>${escapeHtml(row.topic || row.link || '')}</h3></article>`;
```

**เมื่อ backend เพิ่มเหตุผลที่คิวพักเอง** (`story_queue.pause("xxx")`) ต้องเพิ่มข้อความใน `PAUSE_REASONS` ของ `status_vocabulary.js` ไม่งั้น `tests/test_ui_foundation.py` จะ fail (ตั้งใจให้เป็นแบบนั้น)

## 2. ขั้น 2: หน้า "งานของฉัน" (รวมคิว งานค้าง และโปรเจกต์ละคร)

**เป้าหมาย** ผู้ใช้เปิดหน้าเดียวแล้วรู้ว่า (1) คิวกำลังทำอะไร (2) มีงานไหนรอตัวเอง (3) ทำต่อที่ไหน

**ปัจจุบันงานแบบนี้กระจาย 5 ที่ (ต้องรวมเข้าหน้าเดียว)**

| ที่ | ซอร์ส (หาด้วย grep) |
|---|---|
| หน้าคิว (`data-view="creation"`) | `web_ui/creation_queue.js` → `window.renderCreationQueue`, ปุ่ม `#creation-start/#creation-pause/#creation-cancel` |
| แท็บ "งานเดิม" ของ Story | `web_ui/app.js` → `renderStories`, `story-recovery-item` |
| รายการงานค้างสินค้า | `web_ui/product_continue.js` |
| โปรเจกต์ละครสั้น | `web_ui/app.js` → `renderDramaSeries`, `drama-series-item` |
| งานเก่านอกคิว | `#creation-old-panel` ใน `creation_queue.js` |

**ดีไซน์:** `docs/design/ux-redesign-2026-10/Jobs.dc.html` (ข้อความจริง สี และพฤติกรรมตัวกรองอยู่ในสคริปต์ท้ายไฟล์)

**โครงหน้า**

```
[แถบสถานะคิว]  จุดสี + "คิวพักไว้ชั่วคราว" + เหตุผล (SmartFlowStatus.pauseReason) + [เดินคิวต่อ] [⋯ จัดการคิว]
[ชิปกรอง] ยังไม่เสร็จ N · ต้องจัดการ N · กำลังทำ/รอคิว N · หยุดไว้ N · เสร็จแล้ว N
[แถวงาน] ภาพหน้าปก | pill + ประเภท | ชื่อ | บรรทัดอธิบาย 1 บรรทัด | แถบความคืบหน้า | [ปุ่มหลัก 1 ปุ่ม] [⋯]
```

**ปุ่มหลักต่อสถานะ** (หนึ่งปุ่มเท่านั้น ที่เหลือซ่อนใน `⋯`)

| สถานะ | ปุ่มหลัก | ไปที่ |
|---|---|---|
| รอคุณ | ดูวิธีแก้ | หน้ากู้งาน (ขั้น 4) |
| สะดุด | ทำต่อจากจุดเดิม | action เดิมที่ปุ่ม `data-cq="retry"` / `data-retry-story` เรียกอยู่ |
| หยุดไว้ | ทำต่อ | เหมือนกัน |
| กำลังสร้าง | ดูความคืบหน้า | เปิด progress modal เดิม |
| รอคิว | แก้ไข | editor เดิม (`creation-editor`) |
| เสร็จแล้ว | ดูวิดีโอ | `data-cq="result"` เดิม |

**วิธีทำที่ปลอดภัย (เพิ่มแบบ additive)**
1. เก็บ id ที่ test และโค้ดอื่นพึ่งอยู่ให้ครบ: `#creation-list #creation-state #creation-summary #creation-hint #creation-start #creation-pause #creation-cancel #creation-resume-unfinished #creation-cancel-all #creation-clear-cache #nav-creation-count` (ค้นด้วย `grep -rn "creation-list" tests/` เพื่อดูว่า harness ไหนใช้)
2. เปลี่ยนการเรนเดอร์ในแถว ไม่ย้ายตรรกะ action ให้เรียก `window.routeCreationQueue` และ `postAction(...)` ชุดเดิม
3. ลำดับแถวต้องรักษา rule ของงานค้างของอีก session ที่อาจยังไม่ commit: "งานที่หยุด/สะดุด ขึ้นก่อนงานรอคิว" (`rank` ใน `renderCreationQueue`) ตรวจ `git diff -- web_ui/creation_queue.js` ก่อนแก้
4. ตัวอย่าง test ที่ต้องเขียน (`tests/jobs_page_ui.cjs`, Playwright เหมือน `tests/ui_foundation_ui.cjs`):

```js
// ทุกสถานะมีปุ่มหลักปุ่มเดียว และปุ่มลบไม่ใช่ปุ่มหลัก
for (const row of await page.locator('.job-row').all()) {
  assert.equal(await row.locator('.btn-primary, .btn-warn').count(), 1);
  assert.equal(await row.locator('[data-cq="remove"].btn-primary').count(), 0);
}
// เมื่อคิวพักเพราะ job_needs_attention ต้องมีเหตุผลเป็นภาษาคนบนแถบ
await page.evaluate(() => renderCreationQueue({creation_queue: {paused: true, pause_reason: 'job_needs_attention', counts: {queued: 1}, items: [...]}}));
assert.match(await page.locator('#creation-hint').textContent(), /มีงานรอคุณ/);
```

**เสร็จเมื่อ** harness เดิมทั้ง 10 ตัวที่โหลด `creation_queue.js` ยังผ่าน (รายชื่ออยู่ใน suite `ui-foundation`) และมี test ใหม่ข้างบน

## 3. ขั้น 3: ฟอร์มสร้างงานแบบสไลด์ (ใช้ร่วมทุกประเภทงาน)

**ดีไซน์:** `Create.dc.html` (6 สไลด์: ประเภท → เนื้อหา → คนพูด → ภาพและวิดีโอ → เสียงและตกแต่ง → ตรวจแล้วเริ่ม)

### 3.1 ปัญหาโครงสร้างที่ต้องเข้าใจก่อน

หน้า Product/Story/Drama ใน `index.html` เป็นแค่โครง สคริปต์อย่างน้อย 14 ตัวแทรกหรือย้ายกล่องของตัวเองเข้าไปตอนโหลด (`.after()`, `insertAdjacentHTML`) ลำดับบนจอจึงขึ้นกับลำดับโหลดสคริปต์: `media_audio.js green_screen.js ai_cover.js flow_settings.js flow_motion.js video_intro.js presenter.js creator_ux.js queue_choice.js product_story.js storytelling.js creative_controls.js function_controls.js generation_notice.js` ดูรายชื่อล่าสุดด้วย `grep -ln "\.after(\|insertAdjacent" web_ui/*.js`

### 3.2 วิธีทำที่แนะนำ: ทำ "ชั้นแสดงผลทับฟอร์มเดิม" ไม่เขียนตรรกะใหม่

ฟอร์มเดิมและ id ของมัน (`#product-link`, `#story-topic`, `#product-video-provider`, ฯลฯ) คือแหล่งความจริงที่ `postAction('create_product' | 'create_story' | ...)` อ่านค่า (ดู `app.js` ค้น `postAction('create_story'`) และที่ `product_snapshot.js` ใช้บันทึกตัวเลือกตอนเข้าคิว ดังนั้น **ให้สไลด์เขียนค่าลงช่องเดิม** แล้วยิง event:

```js
// สไลด์ "จำนวนฉาก" ตั้งค่าลงช่องเดิม ไม่สร้าง state ใหม่ที่ payload ไม่รู้จัก
function setField(selector, value) {
  const el = document.querySelector(selector);
  el.value = String(value);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
}
setField('#story-scenes', 8);      // ช่วง 6–15 (ตรวจ min/max จาก attribute ของช่อง ไม่ฮาร์ดโค้ดซ้ำ)
```

ขั้นตอน:
1. สร้าง `web_ui/create_wizard.js` + `create_wizard.css` (เพิ่มลง `index.html` หลังสคริปต์ที่แทรกฟอร์ม และเพิ่ม mapping ในรันเนอร์)
2. ซ่อนฟอร์มเดิมด้วย CSS ไม่ลบ (`.create-legacy-form{display:none}`) เพื่อให้ harness เดิมที่ query ช่องเหล่านี้ยังผ่าน
3. ปุ่มท้ายสไลด์เรียกปุ่ม submit เดิมด้วย `.click()` (`#create-product`, `#create-story`, `#create-drama-series`, `#create-longvideo` และปุ่มเข้าคิวของแต่ละหน้า) เพื่อให้ validation, snapshot และ generation notice เดิมทำงานต่อ

### 3.3 ⚠ ข้อมูลที่ "ไม่มี" ให้แสดง (ดีไซน์เดิมวาดเกินจริง)

สไลด์สุดท้ายในดีไซน์มีรายการ "เข้าสู่ระบบ ChatGPT แล้ว / Google Flow แล้ว" **ระบบไม่มีข้อมูลนี้ใน state** ค่าที่มีจริงมีแค่ (ดู `app.js` ค้น `product-readiness`):

| เช็กลิสต์ที่แสดงได้จริง | ค่าใน state |
|---|---|
| ส่วนเสริม Chrome พร้อมและรุ่นตรงกัน | `sys.extension_compatible` (รุ่นที่ต้องการ: `state.app.extension_required`) |
| เสียงพากย์ AI พร้อม (ต้องมีทั้งคีย์และเสียงต้นแบบ) | `sys.voice_configured && sys.voice_reference_configured` (ต้องการเมื่อโหมดเสียงเป็น `api`) |
| ซับไตเติลเชื่อมแล้ว | `sys.subtitle_connected` (ต้องการเมื่อเลือกซับ) |
| มีงานอื่นในคิวกำลังรัน (กดเริ่มไม่ได้) | ดู guard ที่ `ui/main_window.py` ค้น "ยังมีคิว" |

ถ้าจะแสดงว่า login แล้วหรือยัง ต้องเพิ่มข้อมูลจริงจาก backend ก่อน (นอกขอบเขตงาน UI) **จนกว่าจะมี ให้เขียนเป็นคำแนะนำ ไม่ใช่เครื่องหมายถูก** เช่น: "ก่อนเริ่ม ให้เข้าสู่ระบบ ChatGPT ใน Chrome ตัวที่ติดตั้งส่วนเสริมไว้ ถ้ายังไม่ได้เข้า งานจะหยุดรอแล้วแจ้งให้คุณทราบ" และอย่าเขียนข้อความว่า "ตรวจล่าสุดเมื่อ ... นาทีที่แล้ว" ถ้าไม่มีค่าจริง

### 3.4 กฎธุรกิจที่สไลด์ต้องรักษา (ล้วนมีอยู่แล้ว อย่าเขียนใหม่ ให้อ่านจากช่องเดิม)

| สไลด์ | กฎ | ที่มา |
|---|---|---|
| ลิงก์สินค้า | ต้องเป็น `shopee.co.th` / `s.shopee.co.th` ไม่งั้นปุ่มเริ่มปิด | `app.js` ค้น `shopee.co.th` ข้อความผิด: "กรุณาใช้ลิงก์ shopee.co.th หรือ s.shopee.co.th" |
| จำนวนฉาก | สินค้า 3–15 (ค่าเริ่มต้น 3), Story/ละคร 6–15 (10), จำนวนตอน 1–10 ในฟอร์ม (`#drama-episodes`) แต่ backend รับถึง 20 | ช่อง `min/max` เดิม: Story `#story-scenes`, ละคร `#drama-scenes`, คลิปยาว `#long-scenes` ส่วนช่องจำนวนฉากของ **สินค้าไม่ได้อยู่ใน `index.html`** แต่ถูกแทรกโดย `web_ui/product_story.js` (ค้น `จำนวนฉาก` ในไฟล์นั้น) และจำค่าใน localStorage |
| คนพูด | `ตัวละครพูดเอง` และ `ตัวละครสนทนา` ต้องใช้ Google Flow หรือ Meta AI และ storytelling จะเขียนทับตัวเลือกเสียงเอง | `web_ui/storytelling.js` ค้น `warning.textContent` และ `previousSpeakingAudio` |
| เสียง | โหมด `api` ต้องมีคีย์+เสียงต้นแบบ | ดูตารางข้างบน |
| ละคร | โหมดผู้บรรยาย: ตัวละคร 0–4 (AI สร้างให้), `solo` ≥ 1, `dialogue` ≥ 2 | `storytelling.js`, `core/drama_series.py` |

### 3.5 ของที่ต้องแก้พร้อมกัน

- กล่อง "ก่อนเริ่มสร้างคลิป" (`web_ui/generation_notice.js`) พูดเรื่องนายแบบและเสื้อผ้า แต่ขึ้นกับ Story/ละครด้วย: ให้ข้อความตามประเภทงาน
- มี `เก็บเข้าคิวไว้ก่อน` สองชุดในฟอร์มละคร (checkbox จาก `queue_choice.js` ซ้ำกับปุ่ม `เพิ่มลงคิวไว้ก่อน`) เหลืออย่างเดียว
- ตัวเลือกเสียง/ตกแต่ง 6 อัน (`ซับ, เพลง, ปกด้วย AI, ผู้บรรยาย, กรีนสกรีน, อินโทร`) มีที่มาแยกกัน ตรวจว่าแต่ละอันเขียนลงช่องเดิมของ `media_audio.js`, `ai_cover.js`, `presenter.js`, `green_screen.js`, `video_intro.js` (อินโทรไม่มีใน Product)

**ตัวอย่าง test** (`tests/create_wizard_ui.cjs`): (1) เลือก "เรื่องเล่า" → ช่อง `#story-topic` ว่างทำให้ปุ่มถัดไปปิด (2) เลือก "ตัวละครพูดเอง" แล้ววิธีทำวิดีโอเป็นภาพเคลื่อนไหว → เห็นคำเตือน และไม่ยอมไปขั้นถัดไป (3) กดเริ่มแล้ว payload ที่ `postAction` ได้รับ **เท่ากับ** payload ที่ฟอร์มเดิมสร้าง (เทียบ JSON ทั้งก้อน ใช้ stub `postAction`) (4) ไม่มี request ไปที่ provider

## 4. ขั้น 4: ตั้งค่ารวม + ตั้งค่าครั้งแรก + กู้งานแบบสไลด์

### 4.1 หน้าตั้งค่ารวม (`Settings.dc.html`)

ปัญหา: ค่าเดียวกันอยู่หลายที่ และ **สวิตช์ซับไตเติลมี 3 ที่ที่ผูกกับคนละค่า**:

| ที่ | ผูกกับ | ที่มา |
|---|---|---|
| `#setting-subtitle` | `state.settings.subtitle_auto` | `app.js` ~บรรทัดที่ตั้ง `.checked = state.settings.subtitle_auto` |
| `#subtitle-auto` | `subtitle.auto` ของสไตล์ซับ | `app.js` ค้น `subtitle-auto` |
| checkbox ต่องาน | ค่าที่บันทึกกับงาน | `media_audio.js` |

งานก่อนลงมือ: **อ่าน backend ก่อนว่าสองค่านี้ใช้ต่างกันจริงหรือไม่** (`ui/main_window.py` ค้น `subtitle_auto` และ `save_quick_settings`) ถ้าเป็นค่าเดียวกันในความหมาย ให้เหลือสวิตช์เดียวที่ตั้งค่า ถ้าต่างกันจริง ต้องถามเจ้าของว่าจะรวมไหม ห้ามเดา

หลักการหน้าตั้งค่า: ค่าเริ่มต้นรวมที่เดียว แต่ละหมวดมีข้อความย้ำ "มีผลกับงานใหม่ งานในคิวใช้ค่าที่บันทึกไว้ตอนเพิ่ม" (`creator_ux.js` มีข้อความ scope นี้อยู่แล้ว ให้ย้ายมาใช้ร่วมกัน) และมีปุ่มแยก "ทำวิดีโอนี้ใหม่ด้วยค่าล่าสุด" ในคลังวิดีโอ (ตอนนี้หน้าเสียง ซับ เพลง โลโก้ มีตัวเลือก "Product Job" ปนอยู่กับค่าเริ่มต้น และชื่อ "Product Job" ผิดสำหรับงาน Story)

### 4.2 ตั้งค่าครั้งแรก (`Setup.dc.html`)

เมนู "ตั้งค่า → ตั้งค่าครั้งแรกและคู่มือ" (หน้า `guide`) มีอยู่แล้ว แต่เป็นหน้ายาว ให้ทำเป็นสไลด์ 7 ขั้น ใช้ข้อมูลจริงตามหัวข้อ 3.3 เท่านั้น:

| ขั้น | ตรวจจาก |
|---|---|
| ส่วนเสริม Chrome | `sys.extension_online`, `sys.extension_compatible` |
| เสียงพากย์ AI | `voice_configured`, `voice_reference_configured` |
| ซับไตเติล | `subtitle_connected` |
| เข้าสู่ระบบเว็บ | **ไม่มีข้อมูล** ให้ปุ่ม "เปิดและเข้าสู่ระบบ" ที่มีอยู่ (`data-action="open-shopee"`, ChatGPT/Gemini/Flow ใน `index.html` ค้น `web-login-grid`) และให้ผู้ใช้กด "ฉันเข้าสู่ระบบแล้ว" เอง |
| มือถือ (ไม่บังคับ) | ฟอร์ม Android Wi-Fi เดิม `#android-wifi` + `web_ui/android_wifi.js` |

หน้าแรกต้องมีแถบ "ตั้งค่าครบ N จาก M ข้อ" เมื่อยังไม่ครบ (ข้อมูลเดียวกัน)

### 4.3 กู้งานแบบ 3 สไลด์ (`Recovery.dc.html`)

โครง: **เกิดอะไรขึ้น → ต้องทำอะไร → ทำต่อ** ข้อความที่ผู้ใช้เห็นต้องไม่มีรหัสภายใน รหัสไว้ใน `<details>` "รายละเอียดสำหรับทีมช่วยเหลือ" เท่านั้น

ตารางกรณี (ไฟล์ดีไซน์มีข้อความครบทั้ง 6 กรณีในตัวแปร `R` ท้ายไฟล์) **ต้องผูกกับรหัสจริงก่อน** โดยอ่านจาก `core/story_pipeline.py` (ค้น `AI_WEB_`, `STORY_IMAGE_REFUSED`, ส่วนที่แยก "ต้องให้คนทำ" กับ "ลองซ้ำเอง"), `ui/main_window.py` ค้น `action_required` และ `ฉันยอมรับ`, `core/ai_web_resume.py` (เหตุผล `draft_present`, `conversation_present`, `composer_not_ready`):

| กรณี | หน้าตา | ข้อห้ามสำคัญ |
|---|---|---|
| ต้องเข้าสู่ระบบ / ติ๊กไม่ใช่บอท / กดยอมรับใน Flow | ขั้นตอนเป็นข้อ ๆ + ปุ่ม "เปิด Chrome ที่หน้า…" ใช้ action เดิม `open_chatgpt`, `open_flow`, `focus_browser` | ห้ามเขียนว่า "ตรวจพบแล้ว" ถ้าไม่มีสัญญาณจริง ใช้ปุ่ม "ฉันทำแล้ว ทำต่อ" |
| ช่องพิมพ์มีข้อความค้าง | ให้ผู้ใช้เลือก | ห้ามลบข้อความที่ไม่ใช่ของงานนี้ |
| **ส่งคำขอแล้วไม่รู้ผล** | "มีภาพแล้ว ใช้ภาพนั้น" / "ไม่มีภาพ อนุญาตให้ส่งใหม่ 1 ครั้ง" | **ห้ามส่งซ้ำอัตโนมัติ** ต้องผูกกับกลไก owner-authorized replay ที่มีอยู่ (`PROGRAM_BLUEPRINT.md` ค้น "owner-authorized" และ `tests/story_manual_replay_harness.cjs`) ห้ามสร้างทางลัดใหม่ |
| ChatGPT ไม่ยอมสร้างภาพ | แสดงคำขอของฉากนั้นให้แก้ | อย่าส่งคำขอเดิมซ้ำ |
| เครดิต Flow หมด | เปลี่ยนบัญชี หรือเปลี่ยนฉากที่เหลือเป็นภาพเคลื่อนไหว | **ข้อความในดีไซน์ที่ว่า "คลังจะระบุว่าคลิปผสม Flow/ภาพเคลื่อนไหว" ต้องตรงกับกฎจริง:** Product Final ปกติต้องมาจาก Flow จริง ให้ผสมได้เฉพาะ `google_flow_hybrid_composite` ตาม `README.md` หัวข้อ "ข้อมูลสำคัญ" ถ้ากฎไม่อนุญาต ให้ตัดตัวเลือกนี้ออก |
| ต้องอัปเดตส่วนเสริม Chrome | ปุ่มเดียว "อัปเดตตอนนี้" | คิวพักเองอยู่แล้ว (`extension_update`) |

คำสั่งดู/รวมจุดกู้งานที่กระจาย 5 ที่ (แท็บงานเดิม, หน้าคิว, หน้าต่างโปรเจกต์ละคร, Storyboard, หน้าต่างข้อผิดพลาด `#automation-error-modal`) แล้วชี้ทั้งหมดไปหน้ากู้งานเดียว และเลิกแสดงข้อความ error ดิบ/prompt เต็มต่อผู้ใช้

## 5. งานเก็บกวาด (ทำเมื่อแตะหน้านั้น ไม่ต้องรอ)

หาตำแหน่งปัจจุบันด้วย grep เสมอ เลขบรรทัดเก่าเลื่อนไปแล้ว

| เรื่อง | หาอย่างไร | ทำอะไร |
|---|---|---|
| ข้อความ "×3" ค้าง ทั้งที่จำนวนฉากเลือก 3–15 | `grep -n "×3\|ช็อต n/3\|3 ช็อต" web_ui/*.js web_ui/index.html ui/main_window.py` | ใช้จำนวนจริงของงาน (ตัวอย่างที่ผิด: การ์ดคิวแสดง "3 ช็อต" ตายตัวสำหรับสินค้า; ปุ่ม "สร้างวิดีโอ Google Flow ×3" ในเครื่องมือเดิม) |
| ป้ายผิด "ธีมภาพประจำซีรีส์" ที่ช่องผู้ให้บริการในหน้าต่าง "สร้างตอนต่อ" | `grep -n "ธีมภาพประจำซีรีส์" web_ui/index.html` | แก้เป็น "สร้างภาพด้วย" |
| ตัวเลื่อนจำนวนตอนสูงสุด 10 แต่ backend รับ 20 | `grep -n "drama-episodes\|episode_count" web_ui/index.html core/drama_series.py` | ตรวจว่าตั้งใจหรือไม่ ถามเจ้าของก่อนปรับ |
| ศัพท์ที่ผู้ใช้เห็น | `grep -rn "Checkpoint\|Local Bridge\|Product Job\|reference_id\|Token SOT\|UI Hierarchy\|Run Queue" web_ui/` | แทนด้วย: บันทึกความคืบหน้าแล้ว · การเชื่อมต่อ Chrome · งาน · เสียงต้นแบบ · รหัสเชื่อมต่อบริการซับไตเติล · (ตัดปุ่มบันทึก UI hierarchy ของ Android ไปไว้ใต้ "สำหรับทีมช่วยเหลือ") · "เริ่มคิว" |
| ขั้นตอนความคืบหน้ามี 3 ชุดคำ | `app.js` ค้น `const story = [['เขียนบท'` และ `const phases=[['images'` | ใช้ชุดเดียว ดู `Recovery.dc.html` ฝั่งขวา |
| ข้อความผิดพลาดเป็น toast ดิบ ๆ จาก `error.message` | `grep -n "toast(e.message\|toast(error.message" web_ui/*.js` | แปลงด้วยแคตตาล็อกรหัส ไม่แสดงข้อความ exception ของ Python ตรง ๆ |
| `confirm()`/`alert()` ของเบราว์เซอร์ 15 จุดในไฟล์ที่ถูกโหลด (อีก 1 จุดอยู่ใน `facebook_post.js` ที่ไม่ถูกโหลด) ปนกับ modal ของโปรแกรม | `grep -n "confirm(\|alert(" web_ui/*.js` | ใช้ `#confirm-modal` เดิม ปุ่มลบทำลายข้อมูลไม่ใช่สีหลัก |
| โค้ดที่ไม่ถูกโหลด | `web_ui/facebook_post.js`, `web_ui/flow_smoke.js` (test ยืนยันว่าไม่ถูกโหลด) | ลบได้ถ้ายืนยันไม่มีใครพึ่ง (`grep -rn facebook_post tests/`) |
| สีฮาร์ดโค้ด ~640 จุด และตัวหนังสือ 10px ~42 จุด | `grep -o "#[0-9a-fA-F]\{3,8\}" web_ui/*.css | wc -l` | ค่อย ๆ แทนด้วยโทเคนใน `foundation.css` ตอนแก้แต่ละหน้า อย่าแทนทั้งไฟล์ในครั้งเดียว (เสี่ยง layout แตก) |
| คำนำหน้าภาษาอังกฤษบนทุกหน้า (`eyebrow`) | `pageMeta` ใน `app.js` และ `<span class="eyebrow">` | ทยอยเป็นไทยหรือตัดออก |
| สวิตช์ซับไตเติลซ้ำ 3 จุด | หัวข้อ 4.1 | |

## 6. การทดสอบและเครื่องมือ (ตามเครื่องนี้)

```powershell
# ใน C:\Users\RaywatSupaka\Documents\ChatGPT\automation-vdo 2
$env:NODE_PATH = "C:/Users/RaywatSupaka/Desktop/project/frontend/node_modules"   # repo นี้ไม่มี Playwright ติดตั้งเอง
.venv\Scripts\python.exe tools\run_focused_tests.py --feature ui-foundation
.venv\Scripts\python.exe tools\run_focused_tests.py --feature story-recovery-ui --feature story-setup-ui --feature notification-layout
.venv\Scripts\python.exe tools\run_focused_tests.py --changed --plan     # ดู suite ที่ถูกเลือก
```

- ตัวตรวจ UI ของขั้น 1 เป็นต้นแบบให้เขียนต่อ: `tests/ui_foundation_ui.cjs` (โหลด `index.html` จริงกับ CSS จริง, รัน `showPage()` จริง, ตรวจ contrast ≥ 4.5, ขนาดตัวอักษร ≥ 11px, ปุ่มสูง ≥ 44px, บันทึกภาพไว้ที่ `build/ui-foundation/`)
- **ถ่ายภาพหน้าจอให้รอ transition จบก่อน** (รออย่างน้อย 1 วินาที) ไม่งั้นได้ภาพ "สีเพี้ยน" ที่ไม่ใช่ของจริง (เคยโดนมาแล้ว)
- harness ที่โหลด `creation_queue.js` ต้องโหลด `status_vocabulary.js` ก่อน ถ้าเพิ่มตัวแปร global ใหม่ที่ไฟล์ใดพึ่ง ต้องเติมในทุก harness (รายชื่ออยู่ใน suite `ui-foundation`)
- เทสต์ที่ **ล้มอยู่แล้วก่อนเริ่ม** (อย่านับเป็น regression ของคุณ):
  - `tests/test_hybrid_ui.py::...test_story_page_is_creation_focused_and_primary_modes_are_premium` ล้มตั้งแต่ `HEAD` (เช็กหัวข้อ `งานที่ต้องดำเนินการต่อ` ที่ไม่อยู่ใน `index.html` แล้ว) มีงานแยกรออยู่
  - `tests/test_creative_picker_layout_20260927.py` ใช้เวลา 94–113 วินาที ติดเพดาน timeout 120 วินาทีที่ฮาร์ดโค้ดไว้ อาจล้มสุ่มบนเครื่องช้า (ไม่ใช่เพราะโค้ด) ควรเพิ่ม timeout ในไฟล์เทสต์นั้น
- CI (`.github/workflows/focused-checks.yml`) ไม่ได้ติดตั้ง Playwright ตรวจว่าเทสต์เบราว์เซอร์ใน CI รันได้จริงไหม (suite เดิมอย่าง `notification-layout` ก็พึ่ง Playwright)

## 7. ข้อควรระวังเรื่องไฟล์และการ commit

- **ปลายบรรทัดต่างกันต่อไฟล์:** `web_ui/*.js|css`, `tests/*`, `tools/run_focused_tests.py`, `docs/*.md`, `PROJECT_STATE.md`, `PROGRAM_BLUEPRINT.md` เป็น CRLF แต่ `web_ui/index.html` เป็น LF แก้ด้วย Python ต้องเปิดด้วย `newline=''` เครื่องมือ Edit อาจจับ string หลายบรรทัดในไฟล์ CRLF ไม่เจอ
- **อย่าพิมพ์ path Windows ใน string ของ Python โดยตรง** `tools\run_focused_tests.py` ในโค้ด Python จะกลายเป็น `\r` (carriage return) สร้างด้วย `chr(92)` หรือใช้ `/`
- **การ commit แยกงานเมื่อ working tree ปนกับของคนอื่น** (วิธีที่ใช้ได้ผลแล้วในขั้น 1): อย่าใช้ `git add -p` กับไฟล์ที่ปน ให้เอาไฟล์จาก `git show HEAD:<path>` มาทำซ้ำเฉพาะการแก้ของตัวเอง แล้ว `git hash-object -w --path <path> <ไฟล์>` + `git update-index --cacheinfo 100644,<sha>,<path>` จากนั้นเทียบ (`diff`) กับไฟล์จริงเพื่อพิสูจน์ว่าส่วนที่เหลือเป็นของคนอื่นทั้งหมด และ **ส่งออกเฉพาะที่ stage ไปโฟลเดอร์ว่าง** (`git checkout-index -a -f --prefix=<dir>/`) แล้วรันเทสต์ที่นั่นก่อน commit เพื่อพิสูจน์ว่าไม่พึ่งงานค้างของคนอื่น
- อัปเดต `PROGRAM_BLUEPRINT.md` (route/สถานะ/โครงสร้าง), บนสุดของ `PROJECT_STATE.md` และ `docs/TESTING.md` ทุกครั้งที่เปลี่ยนสัญญา ตามที่ `AGENTS.md` กำหนด

## 8. จุดที่ต้องถามเจ้าของก่อน (อย่าตัดสินใจเอง)

1. สวิตช์ซับไตเติลทั้ง 3 จุด รวมเป็นค่าเดียวได้ไหม (หัวข้อ 4.1)
2. ตัวเลื่อนจำนวนตอนจำกัด 10 หรือขยายเป็น 20 ตาม backend
3. กรณี "เครดิต Flow หมด → ทำฉากที่เหลือเป็นภาพเคลื่อนไหว" อนุญาตตามกฎ Product/Story จริงไหม (หัวข้อ 4.3)
4. ถ้าอยากแสดงสถานะ login ChatGPT/Flow ต้องให้ backend ส่งข้อมูลนั้นก่อน (นอกขอบเขตงานนี้ ต้องทำเป็นงานแยกพร้อมความเสี่ยงเรื่อง provider)
5. ลบ `facebook_post.js`/`flow_smoke.js` (โค้ดตาย) หรือเก็บไว้
