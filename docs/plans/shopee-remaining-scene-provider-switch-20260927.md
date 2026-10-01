# แผน: เปลี่ยนผู้สร้างวิดีโอเฉพาะฉากที่เหลือจากหน้า “ดูงาน”

วันที่ตรวจ: 2026-09-27 — วิเคราะห์และวางแผนเท่านั้น ยังไม่แก้โปรแกรมหรือ Extension

## 1. ขอบเขตและหลักฐาน

ผู้ใช้ต้องการเปิดงาน Shopee เดิม เปลี่ยนฉากที่ยังไม่มีวิดีโอระหว่าง Google Flow / Meta AI และเลือกโมเดล/รายละเอียด Flow โดยเก็บฉากที่สำเร็จแล้วไว้ ไม่สร้างบท ภาพ เสียง หรือคลิปเดิมซ้ำ

ภาพหน้าจอเป็นงานรหัส STORY- จึงเข้าหน้า Story Studio ผ่าน `web_ui/product_continue.js:47` ไม่ใช่หน้า legacy Product JOB- ต้องแก้เส้นทางที่ใช้จริงก่อน

สถานะที่อ่านในรอบนี้: source/desktop required/Extension ที่เชื่อมต่อเป็น 0.15.456; มี Story active แม้คิวกลาง paused และ running=0 ไม่ได้สั่งหยุด/รีโหลด/เปิดหน้า AI/สร้างสื่อ

### สิ่งที่ยืนยันจากซอร์ส

| จุด | พฤติกรรมปัจจุบันและผลกระทบ | หลักฐาน |
|---|---|---|
| เปลี่ยนผู้สร้าง | มีปุ่มอยู่แล้ว แต่เปลี่ยน provider ทั้งงาน ข้อความยืนยันบอกว่าจะสร้างใหม่ครบทุกฉาก ไม่ใช่เปลี่ยนเฉพาะที่เหลือ | `web_ui/studio.js:100`, `:185` |
| คลิปเดิมหลังเปลี่ยน | เก็บไฟล์/แผนที่คลิปเก่า แต่เปลี่ยน global mode และตั้ง scene_pipeline_version=0 การเก็บไฟล์ไม่ได้แปลว่านำมารวม Final ต่อ | `core/story_manager.py:328`, `:396` |
| หน้ารีวิว/ตัวทำงาน | เลือกคลิปเฉพาะ provider ปัจจุบัน; Meta collector ต้องมี Meta ทุกฉาก ส่วน Flow collector อ่าน Flow/local ไม่ได้รวมคลิปต่าง provider | `core/studio_review.py:97`, `ui/main_window.py:2907`, `:3236`, `core/meta_video.py:875` |
| ขณะงานทำงาน | ปิดการแก้ทั้งงาน ไม่มีการจองค่าให้ฉากอนาคต ข้อความล็อกไม่ได้อยู่ติดตัวเลือกผู้สร้างโดยตรง | `core/studio_review.py:144`, `ui/main_window.py:10740`, `web_ui/studio.js:100` |
| โมเดลรายฉาก | มี model+prompt override แต่ต้องกรอก prompt ด้วย ยังไม่มี duration/resolution/type รายฉาก และใช้รายการโมเดลตายตัว | `core/flow_scene_edit.py:25`, `web_ui/studio.js:64`, `core/story_manager.py:1871` |
| ค่าตั้งละเอียด | มีในหน้าตั้งค่าและคิวก่อนสร้างงาน ไม่ใช่ตัวแก้ saved Story; คิวที่มี job_id แล้วห้ามแก้ผ่าน queue editor | `web_ui/flow_settings.js:29`, `core/creation_queue.py:456`, `ui/main_window.py:2377` |
| สถานะอ่านเมนูโมเดลตกหล่น | UI ใช้ model_menu_open แต่ Extension ตัดออกจากคำตอบ และ desktop whitelist ไม่ส่งต่อ ทำให้แสดงเหมือนยังไม่เห็นเมนูทั้งหมดแม้มีรายการโมเดลแล้ว | `browser_extension/flow_settings.js:36`, `browser_extension/background.js:7880`, `core/flow_settings.py:35`, `web_ui/flow_settings.js:15` |

การทดสอบฟังก์ชันแปลงข้อมูลยืนยันว่า input model_menu_open=true ถูกคืนเป็นไม่มีฟิลด์นี้ ส่วนรายชื่อ model ยังอยู่ เป็นบั๊กของข้อมูลสถานะ ไม่ใช่หลักฐานว่า Flow ไม่เปิดเมนูจริง

### ช่องว่างที่ต้องปิดก่อนเพิ่มการสลับรายฉาก

- Setter ปัจจุบันตรวจบาง local workers และ Meta ledger แต่ยังไม่ครอบคลุม Flow accepted/unknown receipt และคำสั่งที่ค้างส่ง ห้ามปลด disabled UI อย่างเดียว (`ui/main_window.py:10741`, `core/story_manager.py:346`)
- Flow editor เดิมตรวจ Flow/local แต่ไม่ตรวจ Meta clip เพราะออกแบบบน provider เดียว (`core/flow_scene_edit.py:7`)
- Flow Stop ธรรมดาล้าง monitor/submission receipts; preserve-checkpoint pause รองรับ Presenter เท่านั้น จึงใช้ Stop เป็นวิธีสลับผู้สร้างไม่ได้ (`browser_extension/background.js:3699`, `:3753`)
- คำสั่งตั้งค่า Flow ยังไม่มีการตรวจเจ้าของ job/run/settings revision แบบครบเส้นทาง แม้ฝั่ง Generate มี job/shot/run receipt แล้ว ต้องเสริม ไม่ลบทิ้ง (`background.js:7638`, `:9542`)
- Meta มี request/context/cancel guard และตรวจดาวน์โหลดก่อนถือว่าแท็บหายอยู่แล้ว ต้องคงไว้และเพิ่มแผนรายฉาก ไม่ลดความเข้ม (`src/platforms/meta-ai/video.js:402`, `:607`, `:836`, `core/meta_video.py:546`)
- Audio audit, subtitle provenance และ cache บางส่วนอิง global provider จึงแก้เพียง dropdown หรือ collector ไม่พอ (`core/story_finisher.py:122`, `:144`)

ทั้งหมดนี้เป็นข้อจำกัด/ช่องว่างจาก source ไม่ใช่คำกล่าวว่าผู้ใช้เกิด race ทุกกรณีแล้ว

## 2. UX ที่เสนอ

เส้นทาง: **ดูงาน → การสร้างวิดีโอที่เหลือ** อยู่ด้านบนก่อนรายฉาก

1. สรุป “เก็บคลิปเดิม N ฉาก / กำลังสร้าง K ฉาก / ยังไม่เริ่ม M ฉาก” นับจากหลักฐานไฟล์และผลรับจริง ไม่ใช้ global provider นับแทน
2. เลือก Google Flow หรือ Meta AI; ค่าเริ่มต้นของขอบเขตคือ “ฉากที่ยังไม่มีคลิป” มีการเลือกเป็นรายฉากในส่วนพับ “ตั้งค่ารายฉาก”
3. เลือก Flow แล้วเปิดแผงโมเดล, รูปแบบอ้างอิง, ความละเอียด, เวลาต่อฉาก แยกจากช่องแก้ prompt ไม่ต้องแก้คำสั่งเพื่อเปลี่ยนโมเดล
4. แสดงสัดส่วนเดิมของงานแบบอ่านอย่างเดียว และผลลัพธ์ 1 คลิปต่อฉาก ไม่เปลี่ยนสัดส่วน/ความยาวเป้าหมาย/วิธีเล่า/เสียงอัตโนมัติ
5. แสดงค่าที่บันทึกไว้กับค่าที่ตรวจพบในบัญชีแยกกัน พร้อมเวลาที่ตรวจ หากตัวเลือกหาย แสดง “ไม่พบในบัญชีล่าสุด” ไม่ลบค่างานเดิมหรือแอบเลือกโมเดลแพง/ต่างรุ่นแทน
6. ก่อนบันทึกแสดงรายการฉากที่จะเปลี่ยน และจำนวนที่เก็บเดิม ปุ่ม “บันทึก” ไม่สร้างงานเอง; “บันทึกและทำต่อ” เป็นการสั่งรันแยกอย่างชัดเจน
7. ขณะกำลังรันอนุญาตจัดเตรียมค่าฉากอนาคต แสดง “รอใช้ตั้งแต่ฉากถัดไปที่ยังไม่เริ่ม” โดยไม่กด Stop งานปัจจุบัน ปุ่มอ่านตัวเลือกสดไม่แย่งเมนู/แท็บที่กำลังสร้าง ใช้ผลอ่านล่าสุดหรือรอจุดว่างที่ปลอดภัย

ตัวอย่าง: Flow เสร็จฉาก 1–2 แล้วเปลี่ยนที่เหลือเป็น Meta → เก็บคลิป 1–2 เดิม สร้างเฉพาะ 3–10 ด้วย Meta → รวมตามลำดับ 1–10 เป็นงานเดิม

## 3. กติกาสถานะรายฉาก

| สถานะเมื่อบันทึก/ก่อนส่ง | การทำงานที่ต้องได้ |
|---|---|
| มีคลิปสำเร็จที่ตรวจแล้ว | ตรึงไฟล์ ผู้สร้าง hash และ checkpoint; ไม่อยู่ในรายการสร้างใหม่ |
| ยังไม่เริ่ม | ใช้ provider/settings ใหม่ได้เมื่อบันทึกสำเร็จ |
| กำลังเตรียมแต่ยังไม่ส่ง | ต้องมี acknowledgement ว่า attempt เดิมไม่มีสิทธิ์ส่งแล้วก่อนเปลี่ยน; ถ้ายืนยันไม่ได้ให้รอ ไม่ล้าง draft/receipt |
| ส่งแล้ว/กำลังสร้าง/กำลังดาวน์โหลด | ทำขั้นเดิมให้จบและบันทึกผลก่อน การเปลี่ยนไม่หยุดหรือส่งซ้ำฉากนี้ |
| ไม่ทราบว่าส่งสำเร็จหรือไม่ | ตรวจ owned receipt/ผลดาวน์โหลด/งานเดิมตามระบบกู้คืนก่อน ไม่ใช้ timeout ตัดสินว่าไม่มีงาน |
| ยืนยันว่าล้มเหลวและไม่มีผลสำเร็จ | สร้าง attempt ใหม่ด้วยค่าที่บันทึกไว้ เก็บประวัติ attempt เดิม |
| มีคำตอบเก่ามาถึงระหว่างเปลี่ยน | ตรวจเจ้าของและเวลา acceptance; ผลของ attempt ที่ยังมีสิทธิ์ต้องเก็บก่อน freeze ฉาก ห้ามข้อมูลเก่าเขียนทับแผน/คลิปใหม่ |

การทำงานค้างของฉากหนึ่งไม่ควรเปิด worker ซ้ำหรือทำให้คิวเปลี่ยนเป็นสำเร็จปลอม ต้องแสดงสถานะรอผล/รอใช้ค่าใหม่ให้ตรงจริง

## 4. แผนโปรแกรม

### A. เพิ่มแผนผู้สร้างรายฉากโดยรักษางานเก่า

- เพิ่ม schema version ใหม่และข้อมูลแต่ละฉาก: scene identity, selected provider, settings snapshot, image/prompt/audio identity, plan revision, attempt และผลที่ยืนยันแล้ว ชื่อฟิลด์จริงให้เลือกตามโครงสร้างเดิมตอนลงมือ
- เพิ่ม revision ของแผนแยกจาก progress revision ที่เปลี่ยนบ่อย เพื่อให้การรายงานความคืบหน้าไม่ทำให้ผู้ใช้บันทึกฉากอนาคตไม่ได้ตลอดเวลา
- งานเก่าไม่มี schema ใหม่ให้อ่านด้วย contract เดิม ไม่ migrate ขณะเปิดดู/Resume; สร้างแผนใหม่เฉพาะเมื่อผู้ใช้ยืนยันการเปลี่ยน
- เปลี่ยนเฉพาะ target scene IDs ที่ผู้ใช้เห็นและยืนยัน หากระหว่างนั้นฉากสำเร็จแล้วให้เก็บคลิปนั้นและคืนสรุปผลจริง ไม่รวมฉาก/งานใหม่โดยเงียบ
- ใช้ durable atomic handoff กับ per-scene claim และ revision; ไม่ถือ manifest lock ขณะรอ network หรือรอ Chrome
- คิวเดิมชี้กลับ job manifest/แผนที่บันทึกแล้ว ไม่ copy queue defaults เก่ามาทับ provider/model ที่ผู้ใช้เพิ่งแก้

### B. ใช้ตัวเลือกคลิปกลางตัวเดียว

- Review, progress, worker และ Final ใช้ ordered verified scene assets ชุดเดียวกัน ไม่เลือกด้วย global provider
- ข้ามทุกฉากที่มีผลสำเร็จตรง identity และไฟล์จริง ใช้ worker ของ provider ที่ฉากนั้นเลือกเฉพาะส่วนที่ขาด
- ไม่ถือว่ามีคลิปจากชื่อไฟล์อย่างเดียว และไม่สวมชื่อ Meta/Flow ให้ local fallback
- ใช้ตัวประกอบสื่อเดิมที่รับ ordered paths ได้ (`core/video_composer.py:32`) แต่แก้ collector, source counts และ provenance ให้รองรับหลายผู้สร้างจริง
- คง completed segment/เสียงที่จ่ายแล้ว (`core/scene_pipeline.py:98`, `core/scene_voice.py:69`); ไม่ตั้ง scene_pipeline_version=0 เพื่อแก้ปัญหาด้วยการข้าม checkpoint เดิม
- ตรวจเวลาคลิป เสียงจริง สัดส่วน และคุณภาพไฟล์ของฉากใหม่ตาม output contract งานเดิม ป้องกันเสียงพูดซ้ำ/เสียงหายเมื่อเปลี่ยน Flow ↔ Meta
- งาน native speech ต้องเลือกผู้สร้างจริงของแต่ละฉากในการตรวจ/ซ่อมเสียง; งาน API voice ต้องใช้เสียงที่บันทึกแล้ว ไม่จ่ายซ้ำเพราะสลับ provider

### C. แก้ Flow settings ที่หน้า “ดูงาน”

- ใช้ editor/schema ร่วมกับค่าตั้ง Flow เดิม แต่บันทึกกับ job/scene ไม่เปลี่ยน defaults หรือคิวอื่น
- แยกการเปลี่ยน model/type/resolution/duration จากการแก้ prompt รองรับ override รายฉากและ apply-to-remaining
- ส่งสถานะ “อ่านรายการโมเดลครบในเมนูที่ผูกกับปุ่มนี้แล้ว” แบบ boolean/context ผ่าน Extension → bridge → UI ให้ครบ แยกจากพิกัด/DOM target ซึ่งไม่ต้องส่งให้ UI
- Capability เป็นหลักฐานจากบัญชี/โปรเจกต์/โมเดล/type/aspect/เวลาที่อ่าน ไม่ใช่ catalog สากล ห้ามนำความสามารถของโมเดลหนึ่งไปยืนยันอีกโมเดล
- หากเลือกค่าขึ้นต่อกันแล้วไม่รองรับ ให้แสดงค่าที่ขัดกันและตรวจใหม่ ไม่ reset แล้วส่งด้วยค่าเว็บเงียบ ๆ

## 5. แผน Extension รุ่นใหม่

1. เพิ่ม job/scene/attempt/plan revision/settings identity ในคำสั่งตั้งค่าและสร้างวิดีโอทั้งสอง provider โดยคง request/run/context guard เดิม
2. ตรวจสิทธิ์ก่อนเปลี่ยนค่าบนหน้าเว็บ ก่อน Send/Generate หลัง await และก่อนรับผล/save คำสั่งเก่าที่หมดสิทธิ์ต้องไม่สร้างเพิ่ม
3. เพิ่ม handoff ที่รักษา receipts/completed assets ไม่ใช้ stop_flow_generation ธรรมดา ไม่กด Stop เพียงเพราะผู้ใช้เปลี่ยน dropdown
4. ก่อน Generate ตรวจชื่อโมเดลตรงตัวและค่าที่เลือกครบอีกครั้ง รวม dependent resets; ไม่แทน Lite [Lower Priority] ด้วย Lite ปกติเอง และไม่ถือชื่อในรายการตายตัวเป็นหลักฐานว่าบัญชีมีโมเดลนั้น
5. ส่งผลที่ระบุ provider/settings ที่ใช้จริงกลับโปรแกรม แล้วจึงยืนยัน checkpoint/counts ของฉากนั้น
6. รักษาระบบ ChatGPT/Gemini สร้างภาพ, Meta recovery และ Flow recovery ที่สำเร็จอยู่ ไม่ refactor เส้นทางอื่นเพราะเพิ่มหน้าตั้งค่า

รุ่นใหม่ต้องจับคู่ desktop/Extension ที่ใหม่กว่า 0.15.456 และไม่ต่ำกว่างาน staged ที่อนุมัติแล้ว ตรวจเลขว่างอีกครั้งก่อนลงมือ ไม่ถือเลข 457 ว่าถูกจองแล้ว ทุก marker/helper/required version/release metadata ต้องตรงกัน

## 6. ลำดับดำเนินงาน

1. เขียน regression จากข้อจำกัดที่พบ รวมกรณีฟิลด์ model-menu ตกหล่นและคลิปต่าง provider ถูกกันออกจาก review/Final
2. ทำ schema/atomic handoff/resolver และ compatibility ของงานเก่า ก่อนปลดล็อก UI
3. ปรับ worker/collector/finalization/เสียง/progress ให้รายฉาก ทดสอบ Flow-only/Meta-only ไม่เสียพฤติกรรมเดิม
4. ปรับ Extension ownership/settings/result contract พร้อมการทดสอบคำสั่งเก่าและ race
5. เพิ่มหน้า “การสร้างวิดีโอที่เหลือ” และ editor รายฉากที่พับได้ พร้อม validation/ข้อความรอใช้ค่า
6. ตรวจ legacy Shopee JOB- แยกจาก Product Story: legacy มี selected-provider-only และ Meta slot constraints เดิม (`core/product_manager.py:322`, `:1470`, `core/product_pipeline.py:256`) ต้องมี adapter/resolver/tests ของตัวเองก่อนอ้างว่ารองรับครบ ห้ามพา JOB- เก่าไปใช้ schema STORY- โดยตรง
7. ทดสอบรวมหนึ่งรอบหลังแก้ซอร์สเสร็จ ตรวจคู่เวอร์ชัน และแพ็ก Extension แบบ versioned ลง deliverables ไม่ทับ ZIP รุ่นเดิม ไม่บิลด์ตัวติดตั้งในงานนี้
8. ติดตั้ง/ยืนยันการทำงานจริงหลังงานผู้ใช้จบและมีคำสั่งให้เปิดใช้; การสร้างวิดีโอจริงต้องอยู่ในขอบเขตเครดิตที่ผู้ใช้อนุญาต

ฟีเจอร์รอบแรกโฟกัส Shopee ตามภาพ ไม่ปลดเปิด mixed-provider ให้ Long/Drama/Presenter อัตโนมัติ เพราะมีข้อกำหนดเสียงและ cache แยก ต้องคงพฤติกรรมเดิมและมี tests กันผลกระทบ

## 7. เกณฑ์รับงาน/ทดสอบก่อนส่ง

- Flow เสร็จ 2 จาก 10 → เปลี่ยน Meta → มีคำสั่งใหม่เฉพาะ 8 ฉาก; ทดสอบทิศกลับและเปลี่ยนกลับหลายครั้ง
- ไฟล์คลิปเดิม รูป บท พรอมต์อ้างอิง เสียง และ receipt เดิมมี hash เท่าเดิม ไม่สร้างภาพ/เสียง/คลิปเดิมซ้ำ
- รวม Final ตามลำดับถูกต้อง รายงาน Flow/Meta/local ตามจริง ไม่ค้างรอให้ provider เดียวมีครบทุกฉาก
- Native audio/API voice/music/subtitle ใช้แผนเดิม ไม่มีเสียงพากย์ซ้ำหรือเสียงหาย และ Final ยังเป็นรูปแบบวิดีโอที่โปรแกรมรองรับ
- Job active, unsent draft, accepted, unknown Send, download pending, offline และผลมาช้าแยกกรณี มีผู้สร้างฉากเดียวในเวลาเดียวกัน
- Double click, lost ACK, restart และ stale revision ไม่สร้าง attempt ซ้ำหรือรับคำสั่งเก่าทับ
- อ่านเมนูสำเร็จแล้ว UI แสดงสถานะตรงข้อมูล; model removed/unsupported combination/dependent reset ต้องถูกตรวจพบก่อน Generate
- ค่าที่เลือกตรงกันตลอด UI → job/scene → command → เว็บ → result และ resume ไม่โดน queue snapshot เก่าทับ
- หน้าจอเล็ก เลื่อน/พับ/ย้อนกลับได้ อ่านเหตุผลที่เปลี่ยนไม่ได้ข้างตัวเลือก ไม่ซ่อนในส่วนแก้เสียง
- Legacy JOB-, pure Flow, pure Meta, Long, Drama, Presenter และงานเสร็จแล้วไม่ถูกเปลี่ยนจากการเปิดดู

## 8. สิ่งที่ทดสอบจริงในรอบวิเคราะห์

ผ่าน 23 tests ใน 0.791 วินาที: `test_flow_scene_edit`, `test_studio_review` และ selected tests ของ `test_flow_settings` / `test_long_meta_desktop_440` ครอบคลุม override/model snapshot, busy guards, revision, media paths และการเก็บ Flow เก่าเมื่อเปลี่ยน mode

ผลผ่านนี้ยืนยันพฤติกรรมเดิมเท่านั้น ไม่ใช่ผ่านฟีเจอร์ mixed-provider ที่ยังไม่ได้สร้าง และไม่ใช่ installed E2E ไม่ได้อ่านเมนู Flow สด ไม่ได้ส่งคำสั่ง Extension ไม่สร้างสื่อ/ใช้เครดิต ไม่แก้ข้อมูลผู้ใช้ ไม่มี app/browser test session ที่ต้องปิด สร้างเฉพาะเอกสารแผนนี้
