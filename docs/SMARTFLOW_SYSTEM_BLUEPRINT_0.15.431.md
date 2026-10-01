# พิมพ์เขียวระบบ SmartFlow AI: โปรแกรม Windows + Chrome Extension

สถานะอ้างอิง: ซอร์สคู่กันที่กำหนด Extension `0.15.431` ณ 24 กันยายน 2026  
ขอบเขต: โครงสร้างที่มีในซอร์สปัจจุบัน, สัญญาระหว่างส่วนประกอบ, การกู้คืน, การทดสอบ และสิ่งที่ยังไม่ยืนยัน  
เอกสารนี้ **ไม่ใช่หลักฐานว่ารุ่น 0.15.431 ถูกติดตั้งหรือทำงานครบกับผู้ให้บริการจริง**

ภาคผนวกซอร์ส 24 กันยายน 2026: การแสดงคิว/คลัง/ประวัติงานเป็นการอ่านอย่างเดียว (`AtomicJsonFile.peek`) แม้ต้องอ่านไฟล์สำรอง; การเปิดรายละเอียดงานโดยเจตนายังคงกู้ไฟล์หลักจากสำรองที่ใช้ได้ ไดเรกทอรีงานที่ไฟล์สถานะเสียหรือหายจะแสดงคำเตือนและเปิดโฟลเดอร์ได้โดยไม่สร้างงานใหม่ทับ โหมดสร้างหลาย Story ที่เข้าจากคิวต้องรักษาค่าร่างเดิมไว้ ส่วนป้ายโมเดล Flow แยกค่าบันทึกกับค่าที่อ่านพบจากเมนูบัญชีจริง และไม่สลับโมเดลเอง การแก้ชุดนี้เป็นซอร์สหลัก/หน้าจอและ test harness เท่านั้น ไม่เปลี่ยน Extension runtime/receipt/version 431; ดู `docs/reports/workspace-visibility-ux-20260924.md`

## 1. วิธีอ่านและแหล่งความจริง

1. ถ้าเอกสารเก่าขัดกัน ให้ตรวจซอร์สและ regression test ปัจจุบันก่อน แล้วตรวจ `CURRENT_RELEASE.json` กับ `PROJECT_STATE.md` ตามลำดับ
2. `PROGRAM_BLUEPRINT.md` และ `EXTENSION_BLUEPRINT.md` เก็บประวัติหลายรุ่น คำว่า “ปัจจุบัน” ในหัวข้อเก่า **ไม่ใช่สถานะติดตั้งวันนี้**
3. รุ่นซอร์สคู่กันคือ `core/local_bridge.py:REQUIRED_EXTENSION_VERSION = 0.15.431` และ `browser_extension/manifest.json:version = 0.15.431` ส่วน EXE beta.14 ที่เคยบิลด์จับคู่กับ Extension `0.15.421` เท่านั้น
4. `deliverables/SmartFlow_AI_Extension_0.15.431.zip` เป็นแพ็กเกจ candidate ยังไม่ได้เปิดใช้ใน Chrome/โปรแกรมลูกค้า; ยังไม่มี EXE รุ่นที่จับคู่ 0.15.431 และยังไม่มี installed-provider end-to-end ของรุ่นนี้
5. การทดสอบออฟไลน์ของการแก้ 431: Python 2,231 รายการ (ผ่าน 2,226 ข้าม 5), ตรวจไวยากรณ์ JS 29 ไฟล์, ความตรงกันซอร์ส/โฟลเดอร์/ZIP 39 ไฟล์ รายละเอียดและข้อจำกัดอยู่ใน `docs/reports/long-video-cross-contract-431.md`

| ระดับหลักฐาน | ใช้อ้างอะไรได้ | ใช้อ้างอะไรไม่ได้ |
|---|---|---|
| ซอร์ส + unit/harness | สัญญา, validator, transition, regression ที่ทดสอบไว้ | DOM/บัญชี AI จริงหรือการใช้เครดิตจริง |
| Browser fixture/Chromium smoke | พฤติกรรมตาม DOM จำลองและ UI fixture | ผลงานที่สร้างในบัญชีผู้ใช้จริง |
| งานจริงรุ่นก่อนในรายงาน | อาการและเส้นทางที่เคยพิสูจน์เฉพาะกรณี | ความสำเร็จอัตโนมัติของรุ่น 431 |
| Installed E2E รุ่น 431 | ยังไม่มีหลักฐาน | ห้ามประกาศว่าพร้อมใช้งานครบทุกเครื่อง |

## 2. เป้าหมายผลิตภัณฑ์และขอบเขต

SmartFlow เป็นโปรแกรมสร้างคลิปบน Windows โดยโปรแกรมเป็นเจ้าของ Job, คิว, ไฟล์, เสียง, การเรนเดอร์, การตั้งค่าที่บันทึก และการแสดงผล ส่วน Extension เป็นผู้ปฏิบัติงานบนเว็บไซต์ Shopee, ChatGPT/Gemini Web, Google Flow และ Meta AI ตามคำสั่งที่ผูกกับ Job/รอบงาน ไม่ใช่ฐานข้อมูลหลักของผลงาน

ผลลัพธ์ที่ต้องรักษา:

- ผู้ใช้เพิ่มงานสินค้า/เรื่องเล่าจากจุดสร้าง แล้วดู/พัก/ทำต่อที่คิวเดียว งานที่เสร็จอยู่ในคลัง
- ทุกงานเก็บตัวเลือกที่ใช้จริงใน Job/Queue snapshot; เปลี่ยนฟอร์มภายหลังไม่เปลี่ยนงานเก่า
- การทำต่อใช้ไฟล์และ receipt ที่มีจริง ทำเฉพาะส่วนที่ขาด และไม่อ้างภาพนิ่งว่าเป็นวิดีโอจาก Flow/Meta
- การส่ง Prompt, แนบภาพ, เริ่มเจน, ดาวน์โหลด และบริการเสียเครดิตต้องมีเจ้าของกับหลักฐาน ไม่ใช้ timeout อย่างเดียวเป็นใบอนุญาตให้ส่งซ้ำ
- ทุกข้อความขอ AI ให้เลือกผลลัพธ์เดียว ไม่สร้างหน้าตัวเลือก A/B ให้ระบบตัดสินแทน แต่ตัวตรวจยังต้องยืนยันโครงสร้าง/ไฟล์จริง
- ห้ามสลับ ChatGPT↔Gemini, Flow↔Meta, หรือโมเดล Flow ที่บันทึกไว้เองเมื่อค่าที่เลือกหายจากบัญชี ผู้ใช้เปลี่ยนได้ผ่านเส้นทางที่บันทึกและตรวจใหม่
- Login/ยืนยันตัวตน, CAPTCHA, สิทธิ์รูป, เครดิต/โควตา, สถานะ Send ไม่ทราบผล และการปฏิเสธที่ไม่อนุญาตให้แก้ซ้ำต้องหยุดอย่างซื่อสัตย์ ไม่วนคลิกหรืออ้างว่าสำเร็จ

## 3. แผนผังส่วนประกอบและเจ้าของข้อมูล

```text
ผู้ใช้ → Hybrid UI (web_ui + desktop/hybrid.py)
              ↓ คำสั่ง / สถานะ
       Hidden Python engine (ui/main_window.py)
              ├─ CreationQueue / ProductManager / StoryManager / DramaSeriesManager
              ├─ Voice / Subtitle / Local renderer / Library / Posting
              └─ LocalBridge HTTP 127.0.0.1:8765
                        ⇅ command lease + heartbeat + event/receipt + file
              Chrome MV3 service worker (browser_extension)
              ├─ Shopee capture content script
              ├─ ChatGPT/Gemini content script
              ├─ Google Flow content script + passive result observer
              └─ Meta AI video adapter
```

| เจ้าของ | หน้าที่หลัก | ซอร์สเริ่มอ่าน |
|---|---|---|
| UI | ฟอร์ม, สถานะ, คิว, คลัง, แผงทำต่อ | `web_ui/index.html`, `web_ui/app.js`, `web_ui/creation_queue.js` |
| Desktop controller | เริ่ม/ต่อ pipeline, จัด worker, ส่งเหตุการณ์ UI | `ui/main_window.py`, `ui/creation_queue.py` |
| Durable model | Job/Series/Queue และ atomic JSON | `core/product_manager.py`, `core/story_manager.py`, `core/drama_series.py`, `core/creation_queue.py`, `core/atomic_json.py` |
| Bridge | คำสั่ง Extension, version/owner/lease, ไฟล์และผลกลับ | `core/local_bridge.py` |
| Extension | ควบคุมแท็บ/เว็บไซต์, ตรวจ Send/ผลจริง, ดาวน์โหลด | `browser_extension/src/background/service-worker.js`, `browser_extension/background.js`, `browser_extension/chatgpt.js`, `browser_extension/flow.js` |
| Media | สร้าง/รวมคลิป เสียง ซับ ปก แสง/โลโก้ | `core/video_composer.py`, `core/story_finisher.py`, `core/long_video_render.py` |

ในซอร์สมี `browser_extension/src/core/bridge-transport.js` สำหรับ WebSocket แต่ **runtime ที่เปิดใช้อยู่ยังเป็น HTTP heartbeat/poll ใน `background.js`**; ห้ามวาด WebSocket เป็นทางหลักหรือย้าย transport ด้วยการอัปเดตเอกสารอย่างเดียว

### สิทธิ์ใช้งานไม่ใช่ Token ของ Extension

`core/membership.py` เป็น client ของสิทธิ์ SmartFlow ที่ `www.catfufu.com`: ผู้ใช้กรอก activation token ในโปรแกรม Windows; หลักฐานติดตั้ง/renewal credential อยู่ใน Windows Credential Manager, lease อยู่ในหน่วยความจำและต้องตรวจเซิร์ฟเวอร์เมื่อเปิดใหม่ หนึ่ง token ผูกหนึ่งเครื่องตามสัญญาสมาชิก; การเตะ/หมดอายุ/เซิร์ฟเวอร์ล่มต้องสื่อสถานะจริง ไม่ให้ Extension เก็บ credential สมาชิกอีกชุด Extension ใช้เพียง capability ของ Local Bridge ที่ออกใหม่ในแต่ละ engine session (รายละเอียด §9)

## 4. โมเดลข้อมูล, อายุงาน และการทำต่อ

```text
CreationQueue item (CQ-*) → product JOB-* หรือ story STORY-*
Drama SERIES-* → episode → STORY-* (job_type=drama_episode)
Product Story: Shopee source JOB-* → STORY-* ที่ผูก source_job_id
Job/Series manifest → prompts + receipts + media checkpoints → final video → Library
```

- `core/creation_queue.py` ใช้ FIFO ร่วมของ Product/Story; เพิ่มครั้งละ 1–10 งาน คิวไม่เสร็จรวมไม่เกิน 30, ข้าม fingerprint ซ้ำ, สถานะ queued/running/completed/failed/cancelled และเก็บตัวเลือกที่อนุญาตแบบตัด secret ก่อนบันทึก
- เพิ่มงานขณะคิวพักยังไม่เริ่มเอง; เพิ่มขณะคิวรันจะต่อท้าย ไม่แทรกงานปัจจุบัน; พักหลังจบคลิป, ยกเลิก, ทำต่อ และล้างสถานะค้างเป็นคนละคำสั่ง
- Product Job อยู่ใต้ `workspace/products/JOB-*/` และ Story Job ใต้ `workspace/stories/STORY-*/` ตาม root ที่ manager กำหนด; Drama Series มี `SERIES-*/series.json` และ EP ผูกกับ Story Job จริง **ห้ามเดาว่าแถว UI คือไฟล์สื่อพร้อมใช้**
- Job manifest เป็น source of truth ของ provider, โมเดล, จำนวนฉาก, flow_settings, audio choices และไฟล์จริง; Extension storage เป็น checkpoint/receipt ของ browser ไม่ใช่ตัวแทน Job manifest
- โหมดซอร์สใช้ root ของ checkout; EXE แบบ frozen ใช้ข้อมูลผู้ใช้ใต้ `%LOCALAPPDATA%/SmartFlowAI/data` ตาม `core/customer_runtime.py` ไม่เก็บงานลูกค้าไว้ในโฟลเดอร์ติดตั้ง การแก้ซอร์สบนเครื่องผู้พัฒนาจึงไม่เท่ากับเปลี่ยนข้อมูล/ไบนารีบนเครื่องลูกค้า
- การบันทึก manifest/queue สำคัญผ่าน `core/atomic_json.py` เพื่อกันข้อมูลหายเมื่อ UI, worker, Bridge ชนกัน; อย่าอ่าน JSON เสียแล้วคืน “ไม่มีงาน” อย่างเงียบ ๆ
- ไฟล์รูปสินค้าจาก Shopee ต้องเก็บ/อ้างแบบ **relative ต่อ Job** (`original/...`) ไม่เติม `JOB-id` ซ้ำ; import เสร็จต้องยืนยันไฟล์อ่านได้จริงก่อนส่ง AI
- ทำต่อหลัง crash: อ่าน checkpoint และเจ้าของคำขอเดิมก่อน คำสั่ง Continue อาจเป็น read-only inspection ของแชตเดิม ไม่เท่ากับสั่ง Send ใหม่ หรือเริ่ม Job ใหม่ทั้งหมด

### สถานะกลางที่ทุกหน้าใช้ร่วมกัน

| ระยะ | หลักฐานที่ต้องมี | หน้าจอควรสื่อ |
|---|---|---|
| เตรียม | Job/queue item + settings snapshot | กำลังตรวจข้อมูล/รอคิว |
| รอ AI | คำขอที่บันทึก, provider และ run | กำลังเปิดเว็บหรือรอคำตอบ |
| AI พร้อม | JSON ผ่าน schema + ไฟล์ภาพครบ/อ่านได้ | พร้อมเสียงหรือวิดีโอ |
| รอวิดีโอ | shot/scene owner + package + result receipt | กำลังเตรียม/เจน/ดาวน์โหลดตามสถานะจริง |
| งานสื่อในเครื่อง | เสียง/คลิป/ซับ/เรนเดอร์ที่บันทึก | กำลังประกอบ/ตรวจไฟล์ |
| เสร็จ | final media ที่เปิดอ่านได้ + manifest | แสดงในคลังและทำขั้นโพสต์ต่อได้ |
| พักตรวจ | เหตุผลจำแนก + checkpoint ที่เก็บอยู่ | สิ่งที่รอผู้ใช้/วิธีทำต่อ; ไม่ขึ้นความสำเร็จปลอม |

## 5. หน้าจอและ UX ของโปรแกรม

| หน้า/ทางเข้า | งานของผู้ใช้ | กฎลดความรก |
|---|---|---|
| ภาพรวม | สถานะระบบ, เครดิตบริการ, ผลงานล่าสุด, เริ่มสร้าง | แสดงสัญญาณจริง ไม่ใช้เปอร์เซ็นต์เดาจากเวลา |
| สร้างคลิปสินค้า | ลิงก์ Shopee, AI Web/model, Flow หรือ Meta, ตัวเลือกหลัก | แสดง Flow settings เมื่อเลือก Flow; เครื่องมือซ่อมเฉพาะขั้นอยู่ใน disclosure |
| เล่าเรื่อง Shorts | หัวข้อ/แนวเรื่อง, บท/สไตล์/เสียง/วิดีโอ | ตัวเลือกเสริมเปิดเมื่อใช้; ปุ่มคิวพาไปคิวเดียว |
| ละครสั้น AI | ซีรีส์, ตัวละคร, EP, เสียง/การแสดง | ตั้งค่าหลักเป็นขั้นสั้น ๆ; รายละเอียดตัวละคร/แผน EP เปิดตามต้องการ |
| คลิปยาว | เมนูซ้ายหมวด “สร้าง” และ “＋ สร้างใหม่”; เรื่องแนวนอน 16:9, 3–10 นาที, 18–50 ฉาก | บอกจำนวนชุดละ 10 และรูป/วิดีโอที่จะใช้ก่อนเริ่ม |
| คิวสร้างคลิป | งานสินค้า, Shorts, คลิปยาว, Drama | ตัวกรองประเภท/สถานะ, เริ่ม/พัก/ทำต่อ; ลบแถวเก่าไม่ลบไฟล์โดยปริยาย |
| คลังวิดีโอ | ดูผลจริง, ค้นหา/กรอง, เปิดงาน/โฟลเดอร์ | ปุ่มเล่นใช้ได้เมื่อ final มีจริง; แยกงานยังไม่เสร็จ |
| เครื่องมือประกอบ | AI Voice, Subtitle, Audio, Logo, Intro, Green screen, Presenter, Product Cast | เครื่องมือขั้นสูงอยู่หน้าเฉพาะ; ค่าใหม่ไม่เปลี่ยน Job ที่เริ่มแล้ว |
| โพสต์ | Shopee Android/ADB และ Facebook | เป็น workflow หลังสร้างคลิป ไม่ถือว่าการสร้างคลิปอนุญาตให้โพสต์จริงเอง |
| ระบบ/Log/Guide | ตรวจ Bridge/Extension/บริการ, คัดลอกเหตุการณ์ | แสดงขั้นตอน Job/scene/เวลาและสาเหตุจริง โดยไม่เปิดเผย credential |

การเลือกนายแบบ/นางแบบหรือชุดเป็นตัวเลือก: ปิดอยู่ต้องไม่แสดง control ย่อย เมื่อเปิดจึงเลือกบุคคล, ใช้ชุดมิดชิดอัตโนมัติ/เสื้อสินค้าจริง/รูปชุดอ้างอิง และบันทึก snapshot ลงงาน Product Story ใหม่ (`core/product_story.py`). คำเตือนก่อนเริ่มอธิบายว่าภาพบุคคลที่แต่งกายเหมาะสมช่วยลดการปฏิเสธวิดีโอ แต่ไม่รับประกันผ่านนโยบายของทุกบริการ

## 6. Pipeline รายประเภท

### 6.1 คลิปสินค้า Shopee แบบ Product Job

1. ตรวจลิงก์ Shopee ไทยและสร้าง/เลือก `JOB-*` ที่ตรงคำขอ; ส่ง Extension จับสินค้า/ภาพ/รายละเอียดด้วย capture command ที่ผูก request/command ID
2. ยืนยันข้อมูลสินค้าและภาพต้นฉบับใน `original/`; รูป `.webp` เป็นอินพุตที่รองรับเมื่อเปิดอ่าน/แปลงถูกต้อง ไม่ใช่เหตุให้ข้ามการตรวจไฟล์
3. ส่งข้อมูลจริงให้ ChatGPT Web หรือ Gemini Web **ตามที่ Job บันทึก** เพื่อรับ JSON วิเคราะห์, รูปขาย 3 รูป, บทพูด, caption และพรอมต์ฉากที่ตรวจ schema แล้ว; บันทึกภาพแต่ละใบเป็น partial checkpoint
4. สร้างเสียงเมื่อโหมดต้องใช้ API; เก็บ remote voice-job ID ก่อน poll เพื่อไม่ส่งบริการเสียเครดิตซ้ำ
5. เลือก Google Flow หรือ Meta ตาม Job: Flow ใช้ source slots 3 ช็อตและโมเดลที่ snapshot ไว้; Meta ต้องรับวิดีโอเล่นได้จริงก่อนนับช็อต
6. รวมช็อตตามลำดับ, ใส่เสียง/ซับ/เอฟเฟกต์/โลโก้/ปกตามตัวเลือก, ตรวจ final แล้วส่งเข้าคลัง; ขั้นโพสต์ Shopee แยกจากการสร้าง

Product Story เป็นทางแยกที่ผู้ใช้ต้องเลือก: เตรียม Shopee source `JOB-*`, สร้าง `STORY-*` แบบคลิปสินค้าเชิงเรื่องเล่า, ล็อกสินค้า/บุคคล/ชุด/บทและความต่อเนื่อง แล้วใช้ Story scene pipeline ไม่ควรสับสนกับ Product Job สามช็อต (`core/product_story.py`, `core/product_script.py`, `ui/main_window.py`)

### 6.2 Story Shorts

1. รับหัวข้อหรือเรื่องอย่างน้อยหนึ่งอย่าง, จำนวนปกติ 6–15 ฉาก, สไตล์ภาพและแหล่ง AI Web ที่บันทึก; รูปอ้างอิงไม่บังคับ
2. AI Web ตอบโครงเรื่อง/ตัวละคร/บทพากย์/scene prompts เป็นข้อมูลมี schema; ต่อด้วยภาพรายฉาก บันทึกทันทีทีละภาพและตรวจว่าภาพตรงฉาก/ไม่ใช่สื่อเก่า
3. การเล่าเลือกโหมดผู้บรรยาย, สนทนาตัวละคร, ภาพเล่าเรื่องไร้คำบรรยายตาม validator (`core/storytelling.py`, `core/story_performance.py`); บทที่ต้องพูดต้องไม่ถูกยัดซ้ำเป็นทั้ง narration และเสียงในคลิป
4. สร้างวิดีโอจากภาพในเครื่อง, Google Flow หรือ Meta AI ตามค่า Job; local image motion ไม่ต้องเปิดเว็บวิดีโอ ส่วน Flow/Meta ต้องรอไฟล์วิดีโอจริงทุกฉาก
5. เสียง API หรือเสียงต้นฉบับจากคลิปหรือไม่มีเสียง, ซับ/ดนตรี/SFX/ปก/intro/green/presenter ตามตัวเลือกที่รองรับ; ตรวจ final ก่อนคลัง

### 6.3 ละครสั้น AI

- `SERIES-*` เก็บชื่อเรื่อง, premise, plot board, character bible, ความต่อเนื่อง, theme ปก, ตัวเลือกเสียง/วิดีโอ/เรนเดอร์ และแถว EP; แต่ละ EP เป็น `STORY-*` ที่ผูก `series_id + episode_no`
- EP แรกอาจสร้าง/ล็อก cast จากคำบรรยายเมื่อใช้ narrator; dialogue ต้องมีผู้พูดอย่างน้อยสองคนและชื่อไม่ชน “ผู้บรรยาย”; ค่าเสียงตัวละครและการแสดงต้องถูกตรึงกับ Series/EP ไม่อ่านจากฟอร์มสด
- หลัง EP เสร็จ อัปเดต summary/hook/continuity และจึงเริ่ม EP ต่อไป; EP ล้มต้องพักซีรีส์ไว้ที่ EP นั้น เก็บไฟล์เดิม ไม่ข้ามไป EP ถัดไป
- ฟุตเทจผู้ใช้และผู้บรรยายเป็นชั้นประกอบหลังงานภาพ/วิดีโอ ไม่ใช้เพื่อปลอมว่าฉากที่ Flow/Meta ไม่สำเร็จได้วิดีโอจากผู้ให้บริการแล้ว

### 6.4 คลิปยาว v2

- งานใหม่ `long_video.version=2`: แนวนอน 16:9, 1920×1080 เป็นเป้าหมาย, duration target 180–600 วินาที, 18–50 ฉาก; Meta ไม่รองรับโหมดนี้ใน validator ปัจจุบัน
- AI Web ให้ outline เดียวที่มี `visual_bible`, `story_entities`, ชื่อเรื่อง และ chapter beats จากนั้นตอบทีละชุด 10 ฉาก (ชุดสุดท้ายอาจสั้นกว่า) แต่ละชุดมี prompt, narration, duration, entities และ continuity summary ครบ
- บันทึก **คำขอ outline/chapter/format-repair ที่แน่นอนก่อน Send** ใน `prompts/long_video_plan.json`; Continue อ่านคำตอบของ request ที่มีเจ้าของ ไม่สร้าง master prompt ใหม่หรือส่งซ้ำเมื่อสถานะ Send ไม่ทราบผล
- ตรวจและ checkpoint ภาพแนวนอนแต่ละฉาก; ซอร์ส/Bridge รองรับ scene index ถึง 50 สำหรับ long job เท่านั้น Shorts ยังใช้จำนวนจริงของตน
- Local image-motion หรือ Flow นำสื่อครบมาเรนเดอร์เป็นบทละ 10 ฉาก, reuse ได้เฉพาะบทที่ hash อินพุตและการตั้งค่าตรง, แล้วผสมเสียงพากย์เต็ม **ครั้งเดียวหลังต่อบท** เพื่อไม่พูดซ้ำที่รอยต่อ; `duration_seconds` เป็นเป้าหมายการเขียน ไม่ใช่คำรับประกันความยาวผลจริง
- Outline งานใหม่ขอ `video_description` สำหรับผู้ชม 2–3 ประโยค และ `hashtags` แยก 3–6 คำ; โปรแกรมกันข้อความแผนผลิต (เช่น เวลาเป้าหมาย/จำนวนภาพ/จำนวนชุด) ก่อนเก็บแคปชั่น โดยใช้ข้อความสำรองจากหัวข้อเมื่อ AI ส่งข้อมูลผิดประเภท ไม่ต้องเรนเดอร์คลิปซ้ำ
- Extension ใช้สัญญาเดียวกันในคำถามซ่อม outline ที่ตอบผิดรูปแบบ: ขอ `hashtags` และคำอธิบายพร้อมโพสต์อีกครั้ง แล้วส่งฟิลด์แฮชแท็กในผลรวม; outline เก่าที่ไม่มีฟิลด์นี้ยังทำต่อได้และให้โปรแกรมเติมแฮชแท็กสำรอง แก้เฉพาะซอร์ส/fixture ไม่ถือว่า Chrome ที่โหลดอยู่เปลี่ยนตามอัตโนมัติ
- คลังเรื่องเล่าที่เสร็จแล้วให้แก้ข้อความโพสต์ได้ด้วย `captions/post_metadata.json` แบบ atomic override เท่านั้น; `job.json`, แผน AI, ภาพและ final video คงเดิม ใช้ `post_revision` ป้องกันการเขียนทับจากหน้าต่างเก่า และปุ่มคัดลอกทั้งหมดต้องอ่านข้อความที่แก้ล่าสุด

## 7. สัญญา AI Web: Prompt, JSON, รูป และคำตอบเดียว

| จุด | ข้อกำหนด |
|---|---|
| เลือกผู้ให้บริการ | ChatGPT หรือ Gemini ตาม Job; โมเดลเว็บต้องเป็นค่าที่ผู้ใช้เลือก/ที่งานบันทึก |
| Prompt wire | ต่อคำสั่ง “ขอคำตอบเดียว ไม่ให้เลือก/ถามกลับ” ที่ชั้นส่งเว็บ; อย่าเปลี่ยน canonical job prompt/receipt hash โดยไม่ควบคุม |
| JSON | ต้องตรง schema ของ Product/Story/Drama/Long Video; งานใหม่ขอ fenced JSON block ที่ parse ตามโค้ด, ตรวจ `job_id`, จำนวนรายการ, ชนิดข้อมูลและเจ้าของคำขอ |
| Format repair | ทำเมื่อคำตอบ **เสร็จแล้ว**, ผูกกับคำขอเดิมและเป็นปัญหารูปแบบจริง; บันทึก prompt ซ่อมก่อน Send, ไม่สร้างภาพ/วิดีโอจาก JSON ที่ยังไม่ผ่าน |
| คำตอบผิดประเภท | ตัวเลือก A/B, คำอธิบาย, ข้อความสตรีมพัง หรือรูปไม่ครบไม่ใช่ผลสำเร็จ; จำแนก completed/busy/unknown ก่อน recovery |
| รูป | รูปใหม่ต้องจับคู่ scene/slot และเปิดอ่านได้; partial checkpoint เก็บทันที ไม่ใช้รูปในแชตเก่าเป็นรูปใหม่เพียงเพราะมองเห็น |
| ทำต่อ | อ่าน receipt/trace/URL กับ request hash ก่อน; หลัง accepted Send อาจเปิดแชตเดิมเพื่อ **อ่านอย่างเดียว**; เปิดหน้าใหม่ได้เฉพาะธุรกรรมใหม่ที่มีหลักฐานว่าส่งเดิมล้มเหลวและ archive รอบก่อนอย่างปลอดภัย |

ตัวอย่างบั๊กที่ 430 แก้ในซอร์ส: ChatGPT เปลี่ยน URL ชั่วคราวเป็น canonical แล้ว React remount ทำให้ยังไม่เห็น user turn; อีกทั้งคำสั่ง inline Markdown ที่กล่าวถึง fenced JSON ถูกแสดงเป็นคำว่า `json`. ตัวจับคู่ยอมรับเฉพาะรูปแบบแสดงผลที่รู้แน่และคำขอที่มีเจ้าของเดียว ห้ามลดเหลือ “เห็นข้อความคล้าย ๆ กัน” หรือส่ง Prompt ซ้ำ

## 8. Google Flow, Meta AI และการเรนเดอร์ในเครื่อง

### Google Flow

ก่อน Generate ต้องตรวจ Project/shot owner, รูปอยู่ **ใน composer** ไม่ใช่เพียง Media Library, prompt สด, model/type/resolution/duration ที่บันทึกและยังเลือกได้, 1 output, aspect และปุ่มสร้างจริง การตั้งค่าใน `core/flow_settings.py` ใช้ label ที่อ่านจากเมนูบัญชีจริง (`visible_menu_only`) ไม่ใช่ catalog รุ่นถาวร; ถ้า `Veo 3.1 - Lite [Lower Priority]` หายไปต้องพักเพื่อให้ผู้ใช้เลือกใหม่หรือรอคืน ไม่แทนด้วย Lite คนละ tier

หลัง Generate เก็บ receipt ต่อ job/run/scene/project/attempt และเปลี่ยนเป็นเฝ้าดู ห้ามกดซ้ำเพราะเปอร์เซ็นต์หายหรือหน้าเว็บช้า การ์ดใหม่/วิดีโอเล่นได้/ไฟล์ดาวน์โหลดจริงต้องตรงเจ้าของและใหม่กว่า baseline ผลภาพนิ่ง, การ์ดเก่า, promotional video, text answer หรือการ์ด 100% ที่ยังไม่มีวิดีโอไม่ถือว่าสำเร็จ

ข้อผิดพลาด Flow เช่น timeout, sound failure, policy ต้องจำแนกจาก **การ์ดปัจจุบันที่เป็นเจ้าของ**; กู้ด้วยรูป/พรอมต์ที่แก้ให้สอดคล้องกฎของบริการเมื่อมีหลักฐานว่ารอบก่อนจบแล้วเท่านั้น งาน active/ไม่ทราบผล/เครดิต/สิทธิ์/ยืนยันตัวตนห้ามวนอัตโนมัติแบบไม่มีขอบเขต หากใช้ local fallback ที่ policy/attachment terminal อนุญาต ให้แสดง provenance เป็น local/hybrid ตามจริง ไม่รายงานว่าเป็น Flow ทั้งหมด

### Meta AI (ทดลอง)

รับผลเฉพาะไฟล์วิดีโอที่เล่นได้จริง ไม่ถือข้อความ “สร้างแล้ว” หรือ file unavailable เป็นคลิป; ตรวจคำตอบเสนอเวอร์ชันปลอดภัยแบบเสร็จแล้วและเป็นเจ้าของ อาจรับข้อเสนอหนึ่งครั้งในแชตเดิม แล้วตรวจผลวิดีโอใหม่ ถ้ายังไม่มีวิดีโอและเส้นทางอนุญาต จึงขอรูป/พรอมต์ใหม่ที่สอดคล้องกฎจาก **AI ภาพเดิมที่ Job เลือก** และเปิด Meta context ใหม่โดย archive รอบก่อน; ห้ามโหวตเลือก A/B อัตโนมัติ, ส่งซ้ำเมื่อ busy/unknown หรืออ้างว่าการปรับภาพรับประกันผ่านนโยบาย

### ในเครื่องและ Final

`image_motion` ใช้ภาพที่บันทึกจริงและ FFmpeg/renderer ในเครื่อง; Google Flow/Meta ใช้ไฟล์คลิปจริงก่อน compose. เสียงพากย์ API, native video audio หรือ silence เป็น snapshot `audio_choices` (`api`, `flow_original`, `none`); native mode ใช้ได้เฉพาะ Flow/Meta ไม่ใช่ image-motion. ซับเสียงต้นฉบับต้องมีบริการ Subtitle ที่เชื่อมต่อ, ส่วนเสียง API ใช้บท/เวลาที่ตรวจแล้ว. งาน final ต้องตรวจการเปิดไฟล์, ความยาว, codec/profile/pixel format ที่รองรับ Windows/มือถือ และ provenance; เสียงพูดซ้ำใน Flow มี audit/scene retry แบบจำกัดเฉพาะเมื่อมีหลักฐานเสียงและเงื่อนไขรองรับ ไม่ใช่การลบคลิปเดิม

## 9. พิมพ์เขียว Extension: ชั้นทำงานจริง

| ชั้น | ไฟล์ | หน้าที่ |
|---|---|---|
| MV3 entry | `manifest.json`, `src/background/service-worker.js` | ประกาศสิทธิ์/host, import bootstrap และตัวควบคุม runtime |
| Modular scaffolding | `src/background/bootstrap.js`, `src/background/job-router.js`, `src/background/tab-manager.js`, `src/platforms/*` | router, state/tab/transfer store และ adapter; หลายงานยังทำจริงใน legacy background |
| Active orchestration | `background.js` | heartbeat, command poll/ACK, owner/lease, tab routing, delivery/outbox, recovery, receipt |
| Shopee | `content.js`, `src/platforms/shopee/adapter.js` | อ่านข้อมูลสินค้าในหน้าที่ login แล้ว; ส่งผลพร้อมภาพ/หลักฐานกลับ Desktop |
| ChatGPT/Gemini | `single_answer.js`, `chatgpt.js`, `src/platforms/ai-web/*` | composer, attach, one-answer wire, trusted Send, JSON/ภาพ/receipt/repair |
| Google Flow | `flow_settings.js`, `flow.js`, `src/platforms/google-flow/*` | discover ตั้งค่า, attach, Generate, เฝ้าดูการ์ดใหม่, ดาวน์โหลด/ตรวจผล; observer เป็น passive |
| Meta | `src/platforms/meta-ai/video.js` ผ่าน service worker | ข้อความตอบที่ไม่ใช่วิดีโอ, ข้อเสนอ safe take, ตรวจผล playable, ธุรกรรม context ใหม่ |
| Popup | `popup.html`, `popup.js` | สถานะ Bridge/หน้าเว็บและเครื่องมือเสริม; ไม่มีช่อง API Token ของ Extension |

### การเชื่อมต่อและความปลอดภัย

1. โปรแกรมเปิด Local Bridge บน `127.0.0.1:8765`; Extension ส่ง heartbeat รับ **session capability ภายใน service worker** แล้วใช้ `X-SmartFlow-Token` กับ route ส่วนตัว ผู้ใช้ใส่ Token สมาชิกที่โปรแกรม Windows เท่านั้น ไม่ต้องกรอกใน Extension
2. Extension poll คำสั่งจาก `/api/extension/commands`, ส่ง ACK พร้อม lease/client/run, progress/trace/result กลับ Bridge; version ต้องตรง 0.15.431 ก่อนส่งงานใหม่ ความเงียบของ heartbeat ไม่ใช่หลักฐานว่า provider งานเสร็จ
3. เจ้าของ Browser action อย่างต่ำต้องมี `job_id`, `run_id`, provider, `shot_index` เมื่อเป็นวิดีโอ, tab/project, request/attempt/receipt ID ที่เกี่ยวข้อง; ACK ของคำสั่งไม่ใช่หลักฐานว่า Generate สำเร็จ
4. สิทธิ์ `tabs`, `scripting`, `downloads`, `storage`, `alarms`, `debugger` และ host ที่ระบุใน manifest ต้องใช้เฉพาะงาน/โดเมนที่ประกาศ; ห้ามอ่านหรือเก็บรหัสผ่าน, OTP, cookie หรือส่ง capability ใน URL/log/popup
5. โฟลเดอร์ถาวรฝั่งซอร์สคือ `browser_extension/`; เครื่องลูกค้าติดตั้งจากสำเนาที่ถูก seed ใน data root ครั้งแรกตาม `core/customer_runtime.py`. ต้องตรวจ path ที่ Chrome โหลดจริงก่อนเปลี่ยนไฟล์ การอัปเดต/โหลดซ้ำทำเมื่อไม่มีงาน active โดยรักษา extension identity/storage ไม่ถอนแล้วลงใหม่โดยไม่จำเป็น

### State machine ของหนึ่งคำขอเว็บ

```text
DESKTOP_PENDING
  → LEASED_TO_EXTENSION
  → OWNER_TAB_READY
  → DRAFT/ATTACHMENT_VERIFIED
  → SEND_CLAIMED → SEND_ACCEPTED | SEND_UNKNOWN | SEND_REJECTED
  → RESPONSE_BUSY → RESPONSE_COMPLETED
  → SCHEMA_OR_MEDIA_VERIFIED
  → DESKTOP_CHECKPOINT_ACK
  → NEXT_SCENE_OR_FINAL
```

- `SEND_UNKNOWN` เป็นสถานะป้องกันการส่งซ้ำ: reload อ่านผลเดิม/ตรวจหลักฐานได้ แต่ไม่เปิดแท็บใหม่เพื่อยิง Prompt เดิมทันที
- `RESPONSE_COMPLETED` ยังไม่ใช่ผลสำเร็จของงาน: JSON/รูป/คลิปต้องผ่าน validator และ Desktop ต้องบันทึก checkpoint แล้ว
- ถ้าหน้าตอบค้างเกินหนึ่งนาที ให้ตรวจ activity/Stop/current draft ก่อน; refresh อย่างมี guard และอ่านผลเดิมได้เมื่อเงื่อนไขตรงเท่านั้น; busy จริงรอต่อ
- ทุก recovery ต้องผูก attempt เดิม/ใหม่และเก็บ archive; ห้ามรีเซ็ต receipt เพื่อหลอกว่ากดใหม่ได้

## 10. Recovery matrix ที่ใช้ตัดสินจริง

| หลักฐานที่พบ | การกระทำที่อนุญาต | ขอบเขตที่ห้ามข้าม |
|---|---|---|
| JSON ตอบเสร็จแต่ malformed/schema ไม่ครบ | ขอจัดรูปแบบ/ข้อมูลที่ขาดจาก owner เดิม, บันทึก exact pending prompt ก่อน Send | อย่าเดาข้อมูล/สร้างสื่อจาก JSON ไม่ผ่าน; unknown Send ห้ามยิงซ้ำ |
| ChatGPT/Gemini stream/network error ที่ยืนยันว่า completed failure | guarded refresh อ่านผล, จากนั้นสร้างธุรกรรมใหม่ด้วย prompt/รูปที่บันทึกเมื่อพิสูจน์ว่ารอบเก่าจบ | งาน busy/response ยังอาจมา ห้ามทำใหม่ |
| AI ตอบตัวเลือกหรือถามกลับ | ถ้าเป็นคำตอบเสร็จและเป็นข้อเสนอที่ classifier รองรับ อาจขอผลเดียว/ยอมรับหนึ่งครั้ง หรือขอ reformulation | ห้ามเลือกด้วยการคลิก preference UI สุ่มและห้ามนับข้อความเป็นสื่อ |
| รูป AI ไม่ครบหรือ failed แต่มี checkpoint | สร้างเฉพาะรูปที่ขาด, คง analysis/รูปที่ดีไว้ | ห้ามลบรูป/สร้างซ้ำทั้ง Job |
| Flow/Meta สร้างวิดีโอไม่ผ่านที่ยืนยันเป็น terminal | ซ่อมรูป/พรอมต์หรือเริ่มฉากใหม่ตาม provider-specific transaction และ owner guard | ห้ามใช้ URL โครงการเก่าผิดรอบ, ไม่กดซ้ำใน run ที่ยัง active |
| Flow model ที่บันทึกไม่ปรากฏ | พักก่อน Send แสดง label ที่หาย ให้ผู้ใช้เลือกใหม่หรือรอ | ห้ามแทนด้วย model/tier ใกล้เคียงเอง |
| หน้าเว็บ Login/CAPTCHA/rights/quota/credit | พักพร้อมเหตุผลและ checkpoint ผู้ใช้จัดการแล้วตรวจต่อ | ห้าม bypass consent/policy หรือสัญญาว่าจะรันจนสำเร็จแน่นอน |
| Extension/โปรแกรมหลุด | reconnect, ตรวจ version/lease และไฟล์/receipt เดิมก่อนทำต่อ | ห้ามคิวคำสั่งเดิมสองชุดหรือเปิดแท็บใหม่โดยไม่มีเจ้าของ |
| Final/คลิปมีไฟล์แล้ว | ตรวจ hash/provenance แล้วข้ามรายการสำเร็จ | ห้ามทับไฟล์ดีเพราะ UI ไม่ทันอัปเดต |

คำว่า “แก้ไม่จำกัดจนสำเร็จ” เป็นความต้องการด้าน UX ที่ทำได้เฉพาะ **ความล้มเหลวที่พิสูจน์แล้วและปลอดภัยต่อการลองใหม่**; ข้อจำกัดของบัญชี/นโยบาย/เครดิต และผล Send ที่ยังไม่ทราบไม่สามารถวนโดยรับประกันความถูกต้องหรือค่าใช้จ่ายได้ การแสดงสถานะ “พักตรวจ” ที่มีหลักฐานดีกว่าการส่งซ้ำเงียบ ๆ

## 11. ทะเบียนไฟล์และขั้นตอนดูปัญหา

| อาการ | อ่านก่อน | หลักฐานขั้นต่ำ |
|---|---|---|
| Shopee เปิดแล้วไม่ไป AI | `core/product_story.py`, `core/product_manager.py`, `ui/main_window.py`, `content.js`, `background.js` | source `JOB-*`, capture command ID, รูปใน `original/`, ACK และหน้าเว็บจริง |
| AI JSON ไม่ครบ/Send ค้าง | `core/analysis_json_transport.py`, `core/ai_web_resume.py`, `chatgpt.js`, `single_answer.js` | prompt hash, user turn, send receipt, reply completion, schema error |
| รูปฉากหาย/ค้าง | `core/story_manager.py`, `core/story_receipt_recovery.py`, `chatgpt.js` | scene index, partial image, request/response owner,ไฟล์จริง |
| Flow พร้อมแล้วไม่กด/ค้าง | `core/flow_settings.py`, `flow.js`, `background.js`, `core/local_bridge.py` | selected model, composer media/prompt, project/scene, submission receipt, current card |
| Meta ตอบข้อความแทนคลิป | `src/platforms/meta-ai/video.js`, `core/meta_redesign.py`, `core/meta_video.py` | owned reply, offer/busy/terminal, playable file, redesign transaction |
| เสียง/ซับ/Final ผิด | `core/media_audio.py`, `core/story_finisher.py`, `core/long_video_render.py` | source media, voice job ID, transcript, ffprobe, output hash |
| คิว/คลังงานหาย | `core/creation_queue.py`, `core/atomic_json.py`, `core/video_library.py` | manifest/queue file, backup last-known-good, filter UI, ไม่ลบ/เขียนทับ |

ข้อมูลวินิจฉัยที่ส่งให้ผู้พัฒนาควรมีเวลา, Job/Series ID, mode, scene/shot, version ของโปรแกรม/Extension, ขั้นตอนล่าสุด, URL ที่ไม่เปิดเผย token, ข้อความการ์ด/คำตอบ, checkpoint และไฟล์ที่มีจริง; ไม่ต้องส่งรหัสผ่าน, API key, cookie หรือสมาชิก Token

## 12. เกณฑ์ทดสอบและการส่งรุ่น

1. ทดสอบ validator/model/queue/manifest และ regression ชุดที่เกี่ยวกับไฟล์ที่แก้; สร้าง browser fixture ที่มีคำตอบครบ/ไม่ครบ, busy, unknown Send, A/B, stream error, policy/quota, model หาย และรีสตาร์ตกลางขั้น
2. ทดสอบ Source ↔ Extension version/command/package/result parity โดยเฉพาะ Product Shopee capture → AI, Story/Drama/Long scene count, Flow settings และ Meta video receipt
3. ทดสอบไฟล์สื่อที่เรนเดอร์จริงแบบไม่ใช้เครดิต: ภาพ 16:9/9:16, เสียง, ซับ, H.264/yuv420p/AAC, chapter hash reuse, ล้มเหลวระหว่างบทแล้วทำต่อ
4. ทดสอบ UI กดจริง: ฟอร์ม/ตัวเลือกที่เปิดจึงแสดง, คิวและคลังไม่ซ้ำ, งานเก่าไม่หาย, Continue เปิดขั้นตาม checkpoint, ข้อความไม่ล้น/ไม่บังเนื้อหา
5. ก่อน E2E ต้องจับคู่ Extension ที่ติดตั้งกับ Desktop และยืนยัน Browser/Bridge online. ทดสอบ **ด้วยงานทดลองใหม่ที่ผู้ใช้อนุญาต**, ระบุเครดิตที่อาจใช้, อย่าแตะ Job จริงที่กำลังทำ
6. การออก installer ต้องเพิ่ม version อย่างมีหลักฐาน, แพ็ก Extension คู่กัน, ตรวจ hash/files/package, ติดตั้งเครื่องสะอาด, เปิด GUI/Chrome/Bridge, ทำ Product และ Story smoke, ตรวจ upgrade เก็บ Job/credential/storage และ rollback; แยก “build สำเร็จ” ออกจาก “ใช้งานจริงบนเครื่องลูกค้าผ่าน”

### สัญญาอัปเดตโปรแกรมและ Extension

- `core/app_updates.py` ตรวจ manifest ที่เซ็น Ed25519, version/platform/app ID, URL ต้นทาง `www.catfufu.com`, ขนาดและ SHA-256 ของ patch/Extension/installer ก่อนรับไฟล์; `desktop/update_api.py` เป็นทาง UI เช็ก/ดาวน์โหลด
- Patch โค้ดรันผ่าน `tools/customer_updater.py` แบบ stage, สำรองไฟล์ที่จะแก้, journal และ rollback หากตรวจสุขภาพไม่ผ่าน; ปฏิเสธ path ย้อนออกนอกที่ติดตั้งและ path ข้อมูลผู้ใช้ (`data`, `workspace`, `logs`, `config.json`, `videos`)
- Asset Extension ที่ดาวน์โหลด **ยังไม่แปลว่า Chrome โหลดรุ่นใหม่**: ต้องเปลี่ยนไฟล์ที่โฟลเดอร์ที่ Chrome ใช้จริงและกด Reload เมื่อปลอดงาน; Bridge ตรวจ version ตรงก่อนส่งงานต่อ
- `BUILD_SMARTFLOW_INSTALLER.bat`/`tools/build_installer_one_click.py` เป็นเครื่องมือสร้าง **test Setup** แบบมี gate; ไม่ได้ติดตั้ง, เผยแพร่, ลงลายเซ็น release, เปลี่ยนรุ่นซอร์ส หรือทำ E2E ให้โดยอัตโนมัติ

### สิ่งที่ยังไม่ยืนยันหรือควรตรวจเป็นลำดับแรก

- 0.15.431 ยังไม่มีการโหลดใน Chrome ที่ติดตั้ง, ไม่มี EXE คู่รุ่น, ไม่มี provider Send/เครดิต/คลิปจริง หรือทดสอบเครื่องลูกค้าหลังลง installer
- เส้นทาง Product Shopee capture → AI บนเครื่องอื่นเคยมีรายงานค้าง; แม้ซอร์สมี diagnostics/hand-off fix ยังต้องพิสูจน์บน clean PC พร้อมไฟล์ภาพจริงและ command ACK
- Flow model เป็นความสามารถตามบัญชี ณ เวลานั้น; โมเดล Lite Lower Priority ที่หายไปไม่ควรถูกระบุว่า “รองรับแน่นอน” ใน UI/คู่มือ
- การซ่อม Meta ด้วยภาพ/พรอมต์ใหม่และฉากพูดจริงหลายภาษาเป็นซอร์ส candidate/การทดสอบเฉพาะกรณี ไม่ใช่หลักฐานว่าทำครบ 10 ฉากทุกบัญชี
- เส้นทางคลิปยาว 50 ภาพผ่าน harness แต่ยังต้องทดสอบ installed provider จริง, เวลา/หน่วยความจำ/พื้นที่ดิสก์, การดาวน์โหลดและ final ขนาดใหญ่ก่อนขายเป็นความสามารถรับประกัน
- เอกสารรุ่นเก่ามี recovery หลายยุคที่ขัดกัน; ก่อนแก้บั๊กให้ยึดสัญญา/โค้ดล่าสุด และเพิ่ม regression เฉพาะเหตุการณ์จริง ไม่ย้อนคืนไฟล์ทั้งก้อน

## 13. ลำดับดำเนินงานต่อเมื่อจะเปิดใช้จริง

1. ตรึง source candidate 0.15.431 และตรวจ parity/ผลทดสอบอีกครั้งหลังการเปลี่ยนซอร์สใด ๆ
2. เตรียม installer **ที่จับคู่ 0.15.431 โดยเฉพาะ**; ไม่ใช้ beta.14/Extension 0.15.421 ปะปน
3. ทดสอบในเครื่องแยก/โปรไฟล์ทดลอง: Login โปรแกรม → Extension folder ถาวร → Bridge → Shopee capture → AI Web JSON/ภาพ → เลือก Flow/Meta ที่บัญชีมีจริง → คลิป/เสียง/Final; เก็บหลักฐานแต่ละ checkpoint
4. ทดสอบ resume หลังปิดโปรแกรม/Chrome และ error classes ใน §10 โดยไม่ทำให้ Send ซ้ำหรือไฟล์เก่าหาย
5. บันทึกผล pass/fail ตามโหมด, เครื่อง, provider, เครดิต, เวอร์ชัน และ hash artifact ใน `CURRENT_RELEASE.json`/รายงาน release ก่อนประกาศให้ลูกค้าใช้
