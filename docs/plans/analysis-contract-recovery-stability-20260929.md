# แผนแก้สัญญาข้อมูลและวงรอบกู้คืน SmartFlow

วันที่: 2026-09-29

สถานะ: แผนเสนอ ยังไม่แก้ runtime ไม่ย้ายงาน ไม่ส่ง AI ไม่รีโหลด Extension ไม่บิลด์หรือติดตั้ง

## 1. เป้าหมายและความหมายของคำว่า “ทำต่อจนได้วิดีโอ”

ลูกค้าสั่งงานครั้งเดียว ระบบต้องเก็บคำตอบที่ได้รับ แก้ปัญหาที่กู้ได้ในขั้นตอนเดิม สร้างและบันทึกฉากตามลำดับ แล้วประกอบเป็นไฟล์ Final ที่ตรวจสอบได้ โดยไม่ให้ลูกค้าคอยกดแก้รูปแบบ JSON หรือเริ่มเรื่องใหม่ทุกครั้ง

ไม่ตัดจบงานที่ยังแก้รูปแบบได้เพียงเพราะครบสองรอบ แต่ไม่เท่ากับการส่งคำขอเดิมซ้ำตลอดเวลา: ทุกวงรอบต้องมีหลักฐาน สถานะถาวร เหตุผลว่าจะทำอะไรต่อ และช่วงเว้นระยะ ไม่มีการซ่อน failure หรือประกาศว่ามีวิดีโอทั้งที่ไม่มีไฟล์จริง

สิ่งที่รับประกันเชิงออกแบบได้คือการรักษางานเดิม การไม่ส่งซ้ำโดยไม่ตรวจ และการแสดงสถานะตามจริง ไม่สามารถรับประกันว่าบริการภายนอกจะตอบสำเร็จตลอดเวลา หากต้องล็อกอิน ยืนยัน CAPTCHA เติมโควตา แก้ข้อมูลที่ขัดกัน หรือแก้ข้อบกพร่องในตัวโปรแกรม ต้องแจ้งการช่วยเหลือที่จำเป็นเพียงครั้งต่อเหตุการณ์ ไม่พยายามข้ามเงื่อนไขนั้น

การวางแผนครั้งนี้ไม่ใช่การอนุญาตรันทดสอบเสียเครดิตแบบไม่จำกัด การทดสอบจริงต้องมีจำนวนงาน/ผลลัพธ์และงบที่อนุมัติก่อน

## 2. หลักฐานตั้งต้นและข้อจำกัดที่ยืนยันแล้ว

- ฐานปัจจุบัน canonical, desktop-required และ Extension ที่เชื่อมต่อเป็น 0.15.469 มีหนึ่ง client; Setup เดิม beta.21 ห้ามเขียนทับ
- บั๊ก `STORY-20260929-0589D9`: คำตอบมีสามคู่ `{term, reading}` แต่ตัวรับยอมรับเฉพาะ mapping หรือ `{term, pronunciation}` และ saved Product prompt ไม่ระบุรูปแบบชัด
- ทดสอบ in-memory กับฟังก์ชันจริงแล้ว: รูปแบบเดิมเกิด error เดียวกัน; เปลี่ยนชื่อ field อย่างเดียวผ่าน โดยค่าทั้งสามไม่เปลี่ยน นี่ไม่ใช่หลักฐานว่าเนื้อหาส่วนอื่นหรือ E2E ผ่านแล้ว
- `save_analysis_checkpoint` ตรวจหลายเงื่อนไขก่อนบันทึกร่าง เช่น speaker, creative brief, จำนวนฉาก และ pronunciation จึงต้องแก้ตำแหน่งรับคำตอบ ไม่ใช่เพิ่ม alias อย่างเดียว
- ขีดจำกัดสองรอบมีทั้ง `core/product_editorial.py::MAX_REPAIRS/accept` และ `browser_extension/chatgpt.js::checkpointEditorialAnalysis` ตัวอ่านฝั่ง Extension ยังปฏิเสธ attempts มากกว่าสอง
- malformed JSON ของรอบแก้ยังอาจออกจากวงรอบที่ `analysisFormatGuard`/`extractJson`/`validateAnalysis` จึงต้องรวมเข้าแผนทดสอบด้วย
- `ui/main_window.py::_schedule_story_recovery` ไม่กู้ editorial error ผ่าน generic recovery และ `ui/creation_queue.py::_creation_story_failure` อาจพักคิวเมื่อข้อผิดพลาดไม่เข้าข้อยกเว้นแคบ ๆ ต้องส่งสถานะ recovering ที่มีเจ้าของ ไม่ใช่ขยาย generic retry ให้ส่งวิเคราะห์ใหม่
- สัญญาลำดับฉากมีหลายแบบ: `meta_scene_sequence` ใช้เฉพาะบาง Story ChatGPT→Meta และตัด Product Story ออก; `ScenePipeline` ใช้ใน Flow/แผนวิดีโอรายฉาก ทั้งสองอย่างไม่ใช่ flag ที่แทนกันได้ ต้องทำ route matrix ก่อนอ้างว่าทุกโหมดเป็นภาพ N→วิดีโอ N
- status helper เห็น worker ที่เปิดเผยว่างและคิวพัก แต่ไม่ได้พิสูจน์ Meta/pending Send ทั้งหมดว่าง จึงไม่ใช่อำนาจรีโหลดหรือเปลี่ยนไฟล์ขณะเปิดโปรแกรม
- release preflight แบบอ่านอย่างเดียวผ่าน static checks แต่ `customer_ready=false`; installed provider workflows, clean Windows, update/uninstall และด่านอื่นยังไม่พิสูจน์ด้วยการตรวจครั้งนี้

หลักฐานรายละเอียด: `docs/reports/pronunciation-contract-469-20260929.md` และ `docs/reports/editorial-persistence-468.md`

## 3. ขอบเขตและสิ่งที่ห้ามเปลี่ยนระหว่างแก้

เริ่มจาก Product analysis/editorial ซึ่งเป็นจุดที่พิสูจน์ว่าผิด แล้วเชื่อมสัญญาร่วม ChatGPT/Gemini และสถานะ UI/queue จากนั้นตรวจทางส่งต่อ Meta/Flow และ Final โดยคงตัวควบคุมเฉพาะ provider เดิม ไม่เขียนตัวกดเว็บทั้งหมดใหม่ในคราวเดียว

ต้องรักษา job/run/request identity, ตัวเลือกที่บันทึกไว้, ผู้พูด, รูปอ้างอิง, บทที่อนุมัติ, ลำดับฉาก, ภาพ/เสียง/คลิปที่สำเร็จ, ปุ่มยกเลิก และประวัติความพยายามเดิม ห้ามคืนชีพงานที่ลบ/ยกเลิก ห้ามสร้างคิวทดสอบปะปนคิวลูกค้า

ห้ามเปลี่ยน provider/model/aspect/audio หรือแทนวิดีโอจริงด้วยภาพเคลื่อนไหวโดยเงียบ ๆ ห้ามกด Stop เพื่อเคลียร์สถานะ ห้ามรีเซ็ตใบรับ Send เมื่อไม่รู้ว่าส่งแล้วหรือไม่ ห้ามแก้ปัญหาคุณภาพด้วยการปิดตัวตรวจทั้งหมด

การอัปเดต Extension ยังเป็นของผู้ใช้ตามข้อตกลงเดิม ไม่อัตโนมัติ reload/install และไม่เปิด monitor ที่ผู้ใช้ปิดไว้

## 4. สัญญาข้อมูลกลาง: writer และ reader ต้องใช้ข้อกำหนดเดียวกัน

### 4.1 โครงสร้าง

เสนอ schema กลางที่มี version สำหรับแผนบท/ฉาก และ recovery protocol version แยกจากหมายเลข Extension ใช้ schema + ตัวอย่างร่วมกันสร้างข้อความกำกับ AI และตรวจข้อมูลทั้ง Python/JavaScript มี cross-language conformance fixtures ป้องกัน validator สองชุดตีความต่างกัน

แยกสามชั้น:

1. transport/ownership: คำตอบของ job/run/request ใด และอ่านครบหรือยัง
2. structural format: JSON, types, จำนวนรายการ, field ที่จำเป็น
3. semantic/editorial: บทสัมพันธ์ฉาก ข้อมูลสินค้ามีหลักฐาน ผู้พูดถูกคน ความยาว/คุณภาพตามตัวเลือก

ผิดชั้นที่สองไม่ใช่หลักฐานว่าขั้น Send ล้มเหลว และการผ่านชั้นสองไม่ใช่การอนุมัติเนื้อหา

### 4.2 คำอ่าน

รูปแบบ canonical: `pronunciation_notes = {"original term": "คำอ่าน"}`; ไม่มีคำที่ต้องกำหนดเป็น `{}` ระบุสิ่งนี้พร้อมตัวอย่างในทุก prompt branch ที่ขอ field นี้ รวมถึงข้อความแก้ format

รองรับ input เดิมแบบ lossless เฉพาะชุดที่กำหนดชัด:

- mapping ของ string ไม่ว่าง
- array ของ `{term, pronunciation}`
- array ของ `{term, reading}` ที่พบจริงครั้งนี้
- คู่ซ้ำที่ชื่อ/คำอ่านตรงกันทุกตัวรวมได้ พร้อม normalization audit

ถ้าคู่ชื่อเดียวกันอ่านไม่ตรงกัน มีสอง alias ที่ขัดกัน ค่าไม่ใช่ string หรือมีโครงสร้างที่กำกวม: ส่ง structured issue พร้อม field path ห้ามเลือกเอง ห้ามแปลงวัตถุเป็น string ห้ามล้างเหลือ `{}` แล้วถือว่าผ่าน เก็บข้อมูลดิบเดิมไว้

ข้อมูลเสริมที่ไม่รู้จักต้องเก็บใน raw draft; อย่าทิ้งเพียงเพื่อให้ผ่าน และอย่านำมาใช้เป็นคำสั่งหรือ field ของการอนุมัติ

### 4.3 กฎร่วมอื่นที่ต้องตรวจความสอดคล้อง

- scene_count มาจากตัวเลือกที่บันทึก ไม่ให้ AI เปลี่ยนเอง; ลำดับภาพ/บท/การเคลื่อนไหว/เวลาใช้ index เดียวกัน
- การเปลี่ยน field ที่สัมพันธ์กัน เช่น narration กับ dialogue turns ต้องแก้เป็นชุดเดียวและตรวจทั้งชุดก่อนอนุมัติ
- ชื่อผู้พูดใช้ตัวตนเดิม; `@ชื่อ` เป็นตัวกำกับ ไม่เอาไปอ่านออกเสียงและไม่ถือว่า provider รองรับ voice asset โดยอัตโนมัติ
- คำสั่งกล้อง/เสียง, metadata, warnings และหลักฐานสินค้าไม่ปะปนกับบทพูด
- กฎเขียนบทต้องไม่ขัดกับ duration/โหมดเสียงที่ผู้ใช้เลือก; แยกข้อบังคับกับคำแนะนำให้ชัด
- ยังคงข้อจำกัดข้อมูลจริง ไม่แต่งสเปก ราคา ประสบการณ์ หรือคำรับรองเพื่อให้ตัวตรวจยอมรับ
- ค่าเริ่มต้นของข้อมูล optional ใช้เฉพาะที่สัญญากำหนด และต้องถูก canonicalize ก่อนคำนวณ approval hash เสมอ

## 5. บันทึกคำตอบก่อนตรวจ แต่ไม่อนุมัติก่อนตรวจ

เพิ่มจุดรับผลที่บันทึก completed owned answer ก่อน JSON/semantic validation โดยจำกัดขนาด/ความลึก/ชนิดข้อมูลและตรวจสิทธิ์กับตัวตนคำขอก่อนเสมอ ข้อความบนเว็บเป็นข้อมูลที่ไม่เชื่อถือ ไม่ execute และไม่ให้ AI กำหนด path, job ownership หรือสถานะ approved

เก็บ raw draft แยกจาก approved checkpoint: job/run/request, conversation/message identity เมื่อมี, schema version, draft revision, answer hash, เวลา, errors, normalization audit และสถานะ ไม่เก็บ tokens/cookies; log ปกติเก็บ reason/field path/hash ไม่พิมพ์พรอมต์เต็ม

การบันทึกต้อง atomic และอ่านยืนยันได้ก่อนตอบ ACK ใช้ request+answer identity กัน callback ซ้ำ เก็บ draft เก่า/ใหม่แบบไม่ทับ approval เดิม การเขียนสองไฟล์ต้องมี commit/revision ที่กู้ได้เมื่อเครื่องดับ ไม่เกิด approved ACK ก่อน durable commit

ไฟล์ raw draft อยู่ในพื้นที่งานลูกค้าเท่านั้น ไม่รวม installer/fixtures หรือส่ง telemetry ภายนอก จำกัดการสะสมและหมุน log โดยห้ามลบหลักฐานของ pending/unknown Send หรือผลที่ยัง reconcile ไม่เสร็จ

ถ้าดิสก์เต็มหรือเขียนไม่ได้ ให้เข้า `waiting_storage` และคงผลในช่องทางที่กู้ได้ ห้ามส่ง AI ซ้ำเพื่อแก้การบันทึก และห้ามถือว่าบันทึกสำเร็จ

## 6. วงรอบกู้คืนที่เสนอ

ลำดับหลัก: รับคำตอบเดิม → บันทึกร่าง → แปลงรูปแบบที่รู้แน่ → ตรวจ → ถ้าผ่านบันทึกอนุมัติ → ถ้าไม่ผ่านเลือกวิธีแก้เฉพาะจุด → บันทึกผลใหม่ → ตรวจซ้ำ

### 6.1 กลยุทธ์ตามลำดับ

A. **แก้ในเครื่องก่อน:** aliases/รูปแบบที่แปลงได้แน่นอน เช่นกรณี reading ครั้งนี้ ไม่ต้องถาม AI และไม่กินโควตาสร้างสื่อ

B. **ขอแก้เฉพาะ field:** ส่ง schema ย่อย ตัวอย่าง ข้อมูลเดิม และ issues ของ field ที่ผิด โดยให้อีกฝ่ายคืน replacement เฉพาะ allowlisted paths ผูก draft revision กับ repair request ไม่ส่งทั้งเรื่องให้เขียนใหม่ถ้าไม่จำเป็น

C. **เปลี่ยนกลยุทธ์เมื่อไม่ดีขึ้น:** ถ้าคำตอบสองครั้งติดมี answer/issues signature เดิม ให้เปลี่ยนเป็นชุดคำถามย่อยหรือ schema ตัวอย่างที่ชัดขึ้น ไม่คัดลอกคำสั่งเดิมยิงซ้ำ สิ่งนี้เป็นเกณฑ์เปลี่ยนวิธี ไม่ใช่เพดานตัดจบงานหลังสองครั้ง

D. **เริ่มบริบทข้อความใหม่เมื่อพิสูจน์ว่าจำเป็นและปลอดภัย:** เฉพาะรอบเดิมตอบจบและไม่มี pending/unknown Send ใช้ provider เดิม นำเฉพาะ saved scope/draft/field ที่ผิดไปต่อ สร้าง repair owner ใหม่และเก็บ chain เดิม ไม่เริ่มภาพหรือวิดีโอใหม่ ห้ามใช้การเปิดแชตใหม่หลบ login/quota/refusal

E. **เว้นระยะแล้ววนต่อ:** transient service/network/rate-limit ที่ทราบเวลาลองใหม่ใช้ scheduler ไม่ใช้ลูปค้างใน callback และไม่ส่งอีกก่อนอ่านผลเดิม การเปลี่ยนกลยุทธ์ไม่รีเซ็ตยอดใช้หรือประวัติ

ค่าตั้งต้นที่เสนอเพื่อทดสอบ: local recheck ไม่ต้องเรียก AI; format repair เว้น 5→15→30→60 วินาทีพร้อม jitter หลังตรวจ completed ownership ทุกครั้ง; provider outage เว้น 30→60→120→300 วินาทีและยึดเวลาที่ provider ระบุหากนานกว่า ใช้ค่าของ adapter เดิมหากเข้มกว่า จนกว่า migration ใหม่ผ่านเทสต์

ไม่ใช้ timeout เดียวตัดสินทุก provider และห้ามสร้าง repair round ใหม่จาก timer ทั้งที่ round เดิมยังอ่านไม่จบ

### 6.2 ประเมินว่าดีขึ้นจริง

เทียบ field-level issues, valid fields ที่คงอยู่, schema version และ candidate hash ไม่ใช้จำนวนตัวอักษรหรือคำว่า approved จาก AI เป็นหลักฐาน

หากแก้ A แล้ว B ที่เคยผ่านเสีย ให้ reject เฉพาะ candidate ใหม่และใช้ best valid draft เดิมต่อ ติดตามการสลับไปมาระหว่าง hashes เพื่อป้องกัน oscillation ถ้า validator/prompt ขัดกันเองหรือเจอ internal exception ให้เปิด circuit สำหรับ Send ใหม่ เก็บ diagnostic และแจ้งข้อผิดพลาดโปรแกรมที่ต้องแก้ ไม่เผาโควตาแล้วอ้างว่า “กำลังกู้คืน” ไม่สิ้นสุด

ไม่กำหนด lifetime cap สองครั้งสำหรับ recoverable format/service errors ใน protocol ใหม่ แต่ยังมีขอบเขตงบ/อัตราคำขอของบัญชีและปุ่มหยุด การทดสอบเสียเครดิตมีวงเงินแยกจากนโยบายงานลูกค้า การเปลี่ยน provider/model หรืออนุมัติค่าใช้จ่ายเกินงบไม่ทำเอง

### 6.3 สถานะและคำตอบระหว่างโปรแกรมกับ Extension

เสนอ typed response: `ok`, `protocol_version`, `status`, `draft_revision`, `request_id`, `next_action`, `retry_after`, `issues[]`, `approved_hash` โดย approved_hash มีได้หลัง commit เท่านั้น

สถานะภายในแยก `answer_saved`, `normalizing`, `validating`, `repair_prepared`, `repair_send_pending`, `awaiting_answer`, `waiting_service`, `waiting_connection`, `waiting_storage`, `approved`, `awaiting_user`, `cancelled`, `internal_fault` และ map เข้าสถานะ UI เดิมอย่างมีเวอร์ชัน

ความผิดรูปแบบที่กู้ได้ต้องเป็น typed result ไม่ใช่ exception หลุดเป็น job error; transport/auth/storage/internal fault ยังจำแนกแยก ห้าม return ok/approved ปลอมเพื่อให้ลูปเดิน

## 7. ป้องกันส่งซ้ำ งานชน และการกู้หลังปิดโปรแกรม

- มีผู้ตัดสิน next action เพียงชุดเดียวต่อ job+stage+scene+revision; ใช้ locks/compare-and-swap และ generation epoch ป้องกัน callback เก่าทับรอบใหม่
- บันทึก repair intent ก่อนการส่ง, ผูก exact request/expected draft hash; แยก “เตรียม”, “เริ่มส่ง”, “เว็บรับแล้ว”, “คำตอบครบ”, “บันทึกแล้ว”
- ACK หายหลังบันทึก: client ถาม read-only status ด้วย identity เดิมและรับผลเดิม ไม่สร้าง attempt ใหม่
- ปิดโปรแกรม/Extension ขณะ Send: เปิดมาอ่านคำขอเดิมก่อน หากยังไม่ทราบผลให้คง pending ห้าม replay จาก elapsed time อย่างเดียว
- late result ของ attempt เดิมไม่ทับฉากที่บันทึกแล้ว; เก็บเป็นหลักฐานและ reconcile เฉพาะ owner ที่พิสูจน์ได้ ไม่ถือว่า request ID ใหม่ทำให้ provider มี idempotency ตามไปด้วย
- clear button/draft/Stop ต้องใช้ provider-specific proof เดิม; textarea ว่างอย่างเดียวไม่ใช่หลักฐาน accepted
- cancellation และการลบมีลำดับสูงกว่า retry; scheduler ที่ตื่นภายหลังต้องไม่คืนชีพงาน
- read-only status ทุกตัวต้องไม่แจก command/lease หรือเริ่ม repair; เพิ่ม endpoint อ่านสถานะเฉพาะเมื่อพิสูจน์ว่าเดิมไม่พอ ห้ามใช้ command GET เป็น inventory
- มี watchdog สำหรับการไม่มี progress แต่ให้ reattach reader/reconcile ก่อน ไม่กด Generate/Stop อัตโนมัติ

## 8. นโยบายตามชนิดปัญหา

| ปัญหา | ทำต่ออย่างไร | สิ่งที่ห้ามทำ |
|---|---|---|
| JSON/คำอ่าน/ชื่อ field ผิดรูปแบบ | normalize หรือแก้ข้อความเฉพาะจุดจากร่างที่บันทึก | เริ่มวิเคราะห์ทั้งงานหรือสร้างภาพใหม่ |
| บทไม่เป็นธรรมชาติ/อ้างข้อมูลไม่มีหลักฐาน | แก้ affected fields/scenes พร้อมคำพูดที่เกี่ยวข้อง ตรวจใหม่ | แต่งข้อเท็จจริง เปลี่ยนผู้พูด หรือยืนยันผ่านเอง |
| เว็บยังสร้างคำตอบ/อยู่คิวจริง | รอและแสดงความคืบหน้า อ่านผลของคำขอเดิม | กด Stop หรือส่งซ้ำเพราะครบเวลา |
| ส่งแล้วแต่ไม่รู้ว่าเว็บรับหรือไม่ | ตรวจ user turn/receipt/ผลเดิม; ใช้ข้อยกเว้น recovery ที่มีหลักฐานและเวอร์ชันรองรับเท่านั้น | ล้าง receipt หรือถือว่าหายเท่ากับไม่ส่ง |
| ChatGPT conversation-load failure ที่ตรงเงื่อนไข | ใช้ guarded refresh→อ่านแชตเดิม→replacement และ pending-step successor ตามสัญญาเดิม | ขยายข้อยกเว้นไปหา active/login/quota ทุกกรณี |
| Meta safety-check service unavailable | แยกจาก content refusal; หลังคำตอบจบ/ไม่มีคลิป ใช้ backoff และ fresh context ของฉากเดิมตาม adapter | ถือว่าเป็น policy denial หรือ retry ทั้งที่มีวิดีโอแล้ว |
| รูป/คลิปสร้างแล้วแต่ save/download ขัดข้อง | ตรวจไฟล์/receipt และรับผลเดิมให้ครบ | สร้างสื่อใหม่เพื่อแก้ ACK หาย |
| Extension/เน็ตหลุด | เก็บ intent/ผล รอ reconnect แล้ว reconcile | ทิ้ง job แล้วสร้างใหม่ |
| โควตาชั่วคราวมี reset time | รออัตโนมัติตามเวลาที่พิสูจน์ได้ พร้อมสถานะ | ซื้อเครดิต เปลี่ยนบัญชี หรือส่งถี่ |
| login/CAPTCHA/เครดิตหมด/สิทธิ์บัญชี | เก็บงานและขอผู้ใช้จัดการหนึ่งครั้ง | หลบ security หรืออ้างว่าแก้เองได้ |
| provider ปฏิเสธเนื้อหาจริง | ใช้เฉพาะทางเลือกที่ปลอดภัยและได้รับอนุญาต; หากยังปฏิเสธให้แจ้ง | วนปรับเพื่อหลบ safeguard |
| conflict/internal bug/file permission/disk full | circuit เฉพาะขอบเขตที่กระทบ เก็บหลักฐาน บอกสิ่งที่ต้องแก้ | บังคับผ่านหรือลูปยิง AI ไม่จบ |

## 9. ฉากและ Final: ป้องกันงานพังย้อนกลับทั้งเรื่อง

เป้าหมายโหมดที่รองรับ scene-serial: บทที่ผ่านตรวจ → ภาพ1บันทึกจริง → วิดีโอ1บันทึกจริง → ภาพ2 → วิดีโอ2 → … → เสียง/ประกอบตามโหมด → ตรวจ Final

ก่อนเปลี่ยนอะไรต้องทำ route matrix ของ Product Story/Story Shorts/Long/Drama, image provider, video mode, per-scene mixed plan, native/API voice และ cover ว่าใช้ barrier ใด ห้ามเอา Meta stored-video flag ไปแทน Flow segment+audio complete หรือเปิด scene_pipeline_version ให้ทุกงานเพื่อแก้เร็ว

งานใหม่ที่ต้องขยาย serial ให้ Product/Gemini→Meta ใช้ capability/version ใหม่และทดสอบ route นั้นโดยเฉพาะ ส่วน Long/Drama/legacy ที่ยังไม่ได้เปลี่ยนต้องรายงานตามจริงและคงพฤติกรรมเดิม ไม่อ้างว่าการแก้ pronunciation เปลี่ยนลำดับเหล่านี้ให้แล้ว

กฎไฟล์และความคืบหน้า:

- ฉากจะพร้อมเมื่อไฟล์อยู่จริง เปิดได้ มีชนิด/ขนาด/ระยะเวลาที่ผ่าน และ hash/receipt ตรง job+scene+revision ไม่ใช่แค่เห็น thumbnail บนเว็บ
- ฉาก2เสียต้องกู้ฉาก2 ไม่ย้อนสร้างฉาก1; ถ้าภาพ2มีแล้วให้ทำเฉพาะคลิป2; ถ้าเสียงมีแล้วให้ประกอบจากเสียงเดิม
- แยก saved source image จาก redesigned helper image และ actual video ห้ามเปลี่ยน reference ของฉากถัดไปโดยไม่ผ่านกฎเดิม
- metadata repair หลังอนุมัติแล้วไม่ทำให้ approved_hash/media identity เปลี่ยนโดยพลการ ต้องตรวจ revision/ผลกระทบก่อน หากกระทบคำพูด/เสียงจริง ใช้เส้นทางแก้ฉากที่ได้รับอนุญาตเท่านั้น
- Final ต้องมีครบตาม selected scene plan เรียงถูก decode ได้ มี H.264/yuv420p และ AAC เมื่อโหมดต้องมีเสียง ระยะเวลา/aspect/audio ตามแผน ไม่มี missing/duplicate segments
- render/download failure กู้จากไฟล์เดิม ไม่ส่ง provider ใหม่; commit Final ด้วย path/hash/read-back แล้วจึงปล่อยสถานะ completed
- cover เป็นงานแยก: เก็บ Final ที่สำเร็จแม้ปกขัดข้อง แสดง video_ready/cover_pending ตามจริง และคิวจบตามตัวเลือกปกของงาน ไม่อ้างว่าปกเสร็จแล้ว
- การตรวจด้วยกฎ/AI ไม่พิสูจน์ว่าภาพสวย บทขายได้ หรือ lip-sync ถูกทุกคำ ต้องมีเกณฑ์สุ่มตรวจคุณภาพที่ระบุข้อจำกัดชัด

## 10. Queue และ UX ที่ไม่ให้ลูกค้าต้องแก้รายรอบ

สถานะลูกค้าใช้คำตรงงาน: “กำลังตรวจบท”, “กำลังแก้ข้อมูลคำอ่าน”, “รอ AI กลับมาและจะลองต่อ”, “กำลังบันทึกวิดีโอฉาก 2/3”, “กำลังประกอบคลิป”, “ต้องเข้าสู่ระบบ” พร้อมเหตุผล/เวลาตรวจครั้งถัดไปและปุ่มหยุด

ไม่แสดงกล่อง error ทุก retry ไม่ซ่อนรายละเอียดแต่ให้กดดูรอบ/ขั้นตอน/รหัสอ้างอิงได้ ไม่แสดงเปอร์เซ็นต์หรือเวลาสำเร็จที่เดาเอง

recovering/waiting ไม่ใช่ failed ไม่เรียก outer job restart ซ้ำ งานที่พักเพื่อรอบริการยังอยู่ในคิวเดิม ไม่หลุดไปเป็น completed หรือ skip ทิ้ง

หากจะปล่อยคิวอื่นทำต่อ ต้องพิสูจน์ว่าไม่มี Send/worker/result ที่ยังใช้ resource เดียวกัน แล้วจึง release lease ของขอบเขตนั้นและตั้ง next_retry_at; คงลำดับ/ความยุติธรรม ไม่สลับคิวจริงระหว่างการทดสอบ อาการระดับบัญชี/provider circuit กั้นงานที่ใช้บัญชีเดียวกัน ไม่วนเอางานทุกชิ้นไปชนข้อผิดพลาดเดิม

progress มีสองแกน: จำนวนฉากที่บันทึกแล้วเพิ่มเท่านั้นสำหรับ revision เดิม กับ recovery stage ที่เปลี่ยนได้ callback เก่าห้ามลดความสำเร็จหรือปิดงานรอบใหม่

## 11. แผนแก้ไฟล์และลำดับส่งมอบ

ชื่อ module ใหม่ด้านล่างเป็นข้อเสนอ ต้องตรวจไม่มีงานอื่นแก้ชนก่อนสร้าง ไม่ใช่รายงานว่ามี implementation แล้ว

| ชุดงาน | จุดหลัก | ผลที่ต้องได้ก่อนผ่าน |
|---|---|---|
| A: fixture และสัญญากลาง | เสนอ `core/analysis_contract.py`/schema resource; `core/product_story.py`, `core/story_manager.py`, prompt branches ที่เกี่ยวข้อง | เคส reading ผ่านแบบไม่เสียข้อมูล; prompt และ Python/JS ตรงกัน |
| B: durable raw intake | `core/story_manager.py`, `core/atomic_json.py` เฉพาะเมื่อจำเป็น, `core/local_bridge.py`, `browser_extension/background.js` | malformed answer ถูกเก็บก่อนตรวจ; ACK/restart ไม่สร้างซ้ำ |
| C: recovery protocol ใหม่ | `core/product_editorial.py`, เสนอ `core/analysis_recovery.py`, `browser_extension/chatgpt.js` ที่ใช้ร่วม ChatGPT/Gemini | recoverable errors วนได้เกินสองรอบ; เปลี่ยนวิธีเมื่อไม่ดีขึ้น; no-progress/account/unknown แยกชัด |
| D: queue/progress | `ui/main_window.py`, `ui/creation_queue.py`, `core/creation_queue.py` และ progress view เฉพาะจุด | ไม่เรียก generic restart, ไม่พักทุกคิวจาก format error, cancel ทำงาน |
| E: downstream compatibility | `core/speech_delivery.py`, `core/scene_pipeline.py`, `core/meta_scene_sequence.py`, Meta/Flow/scene-plan adapters | approved canonical data ผ่านได้เหมือนเดิม; existing media/choices ไม่เปลี่ยน |
| F: serial route gaps | เฉพาะ routes ที่ matrix พิสูจน์ว่ายังไม่เป็นตามเป้าหมาย | เพิ่มแบบ versioned แยกจาก A–D; ทดสอบครบก่อนรวม ไม่พลิก flags งานเก่า |
| G: release pair | manifest, desktop required, helper/capability, release markers/blueprint และ guarded builder เดิม | tested bytes ตรง artifact; เวอร์ชันไม่ย้อน; activate ได้โดยคง profile/ID/storage |

ไม่แก้ทุก module พร้อมกัน: ทำ A→B→C→D ให้ผ่านก่อน แล้วตรวจ E/F และ freeze ก่อน final suite ใช้ patch review แยกแต่ละชุด เพื่อย้อนเฉพาะการแก้ของเราได้โดยไม่ลบ cumulative user work

## 12. ชุดทดสอบที่ต้องมี

### 12.1 แบบข้อมูลและบท

- observed `{term, reading}`, canonical map, supported legacy list, empty/optional, duplicate equal/conflicting, mixed types, extra/unknown keys, missing fields, Unicode/ไทย, over-size/deep input
- JSON มี code fence/ข้อความนำ, ถูกตัดกลาง, สองคำตอบ, null/NaN/boolean ผิด type; ห้ามรวมหลายทางเลือกเป็นคำตอบเดียว
- prompt ทุก branch มี schema ที่ถูกต้อง; ตัวอย่างจาก prompt ต้องผ่าน validator; model flags ไม่อนุมัติตัวเอง
- field repair ห้ามเปลี่ยน job/count/provider/model/speakers/scenes ที่ไม่เกี่ยว; narration/turns/pronunciation ต้องสัมพันธ์กัน
- บทไม่มีภาษารายงาน “ตามข้อมูลที่ระบุไว้”, ไม่มีคำสั่งกล้อง/ความยาวหลุดเป็นเสียง; คำเตือนใช้งานจริงและข้อความผู้ใช้ที่ล็อกไว้ไม่ถูกลบมั่ว

### 12.2 การวนและคงสถานะ

- ตอบผิด format ต่อเนื่องเกินสองรอบ แล้วรอบถัดมาถูก: ไปต่อได้และสร้างสื่อเพียงหลัง approval
- ตอบเดิม/สลับสองคำตอบ: เปลี่ยน strategy ไม่ยิง prompt เดิมถี่ และไม่ล้าง counters
- service outage→กลับมา, rate-limit พร้อมเวลารอ, login/quota/policy: จำแนกถูกและใช้ next_action ถูก
- restart ก่อน Send, หลัง press ก่อน accepted, หลัง received ก่อน save, หลัง save ก่อน ACK, หลัง approval ก่อน image1, หลัง image/video stored ก่อน release next scene
- duplicate callbacks, stale run/epoch, old draft revision, lost ACK, late previous answer/result, สอง client แย่งงาน, token/lease หมด
- cancel/delete ระหว่าง backoff/Send/download, disk full/permission denied, file missing/corrupt, read-only status ไม่เกิด dispatch
- recoverable queue waiting ไม่หลุด/ซ้ำ/ข้ามงาน และ manual pause ยังอยู่หลัง restart

### 12.3 งานปกติข้างเคียงและไฟล์สื่อ

รัน fixtures เดิมที่เกี่ยวข้อง เช่น `test_editorial_persistence_468.py`, `test_product_editorial_465.py`, `editorial_persistence_468.cjs`, `product_editorial_465.cjs`, `test_speech_delivery.py`, `speech_delivery_contract.cjs`, `test_provider_send_receipt_466.py`, `test_meta_scene_sequence_460.py`, per-scene video-plan และ selected Meta/Flow/Gemini regression cases

เพิ่ม integration ที่ใช้ writer→actual browser helper→bridge→saved file→ACK→resume ไม่ใช่ mock ที่คืนรูปแบบถูกอยู่แล้วตลอด ทดสอบ Chrome storage key ordering, DOM remount/zoom/resize ที่เกี่ยวข้องและการ reconnect โดยไม่ปิด guard

ทดสอบ assembly จากไฟล์ที่มีอยู่ก่อน ใช้ synthetic/read-only fixture แทนงานลูกค้า ห้ามเผาเครดิตเพื่อทดสอบ type conversion

### 12.4 เกณฑ์ผ่านที่วัดได้

- observed bug เดิมไม่เกิดซ้ำใน fixture และ canonical values เท่าเดิมทุกตัว
- recoverable format case จบด้วย approved+durable checkpoint ไม่ใช่ generic error
- duplicate dispatch ที่เกิดจากระบบกู้ใน deterministic fault tests ต้องเป็นศูนย์; ไม่อ้าง distributed exactly-once ของ provider ที่ไม่ได้รองรับ และบันทึกข้อยกเว้น authorized fresh replay ว่าเสี่ยง duplicate หลังบ้าน
- saved media/ตัวเลือก/บทฉากที่ไม่เกี่ยว SHA หรือ canonical identity ไม่เปลี่ยน
- unknown Send ไม่เกิด additional submission; true active generation ไม่ถูก Stop
- restart ทุก critical boundary กลับสู่สถานะเดียวที่กู้ได้; cancellation ทำให้ไม่มี dispatch ใหม่หลังรับรู้การยกเลิก
- ไม่ส่งต่อ media จาก raw/unapproved draft และไม่ completed ถ้า Final/ผลตามตัวเลือกไม่ครบ
- test failures/critical skips ต้องปิดหรือระบุเป็น release blocker ห้ามลด assertion หรือแก้ fixtureให้ผ่านโดยไม่ยืนยัน expected contract

## 13. ทดสอบติดตั้งจริงและเกณฑ์ก่อนขาย

1. Focused tests ตาม A–F ก่อน จากนั้น freeze source/tests และบันทึก hashes
2. รัน full suite หนึ่งครั้งบน source ที่นิ่ง หากต้องแก้ runtime เพิ่มต้อง freeze และรันทวนรอบสุดท้ายใหม่ แยก documentation-only/input-environment failure ออกจาก runtime failureตามจริง
3. ตรวจ syntax, version/capability pairing, source/folder/ZIP parity และ compatibility ของ approved legacy jobs แยกจากผล test suite
4. ใช้แอปผ่าน EXE และ Extension ที่ติดตั้งจริง ไม่ใช้ manual browser Send เป็นผล E2E ของ SmartFlow
5. แผน E2E ขั้นต่ำที่เสนอหลังอนุมัติงบ: งานใหม่สองงาน งานละสามฉาก — ChatGPT→Meta หนึ่งงานและ Gemini→Flow หนึ่งงาน รวมฐานหกภาพ/หกคลิป ไม่เปิด cover/music/paid voice เพิ่มโดยไม่ได้อนุมัติ; บันทึกค่าใช้จริงหรือระบุว่าไม่ทราบ คุม recovery attempts ของการทดสอบแยกต่างหาก
6. ทดสอบ natural successful path จริงก่อน; fault injection ทำในสภาพแวดล้อมแยก ใช้ผลเดิมสำหรับ resume/assembly ไม่ทำงานจริงพังเพื่อทดสอบทุกจุด การผ่านสองงานไม่ใช่การอ้างว่าทุก model/mode ผ่านแล้ว ต้องเผย coverage matrix และเพิ่มเคสของฟีเจอร์ที่จะขาย
7. เมื่อต้อง build ใช้ guarded builder เดิมเท่านั้น แล้วติดตั้งบน Windows 11 ที่ไม่มี Python/Node/ไฟล์ developer และบัญชีผู้ใช้ใหม่ พร้อม Chrome/เงื่อนไข WebView ที่รองรับ ตรวจ path ไทย/ช่องว่าง, DPI/window sizes, download directory, write permissions, port conflict, antivirus/quarantine diagnostics โดยไม่ปิด security
8. ทดสอบ upgrade และ uninstall: งาน/queue/options/profile/Extension identity/storage ไม่หาย ไม่ย้อนเวอร์ชัน ไม่มีข้อมูลลับหรืองาน developer ใน payload; runtime/dependency/prerequisite ต้องใช้งานได้จริงไม่ใช่แค่มีไฟล์
9. ผ่านคุณภาพเสียง/ภาพ/ลำดับ/Final และทดสอบติดตั้งจริงก่อนเปลี่ยนจาก “พร้อมทดสอบ” เป็น “พร้อมส่งลูกค้าตามขอบเขตที่ทดสอบ” ไม่โฆษณารองรับทุกเครื่องหรือไม่เกิด error อีกเลยจาก sample เล็ก

เครื่องมือ/เครดิต/บัญชีที่ยังไม่ได้รับอำนาจใช้เป็นข้อจำกัดของหลักฐาน ไม่ใช่เหตุให้ทำเครื่องหมายผ่านเอง

## 14. เวอร์ชัน การเปิดใช้ และงานที่ค้างอยู่

ฐานที่จะต่อคือ cumulative469 ไม่เอา archive เก่ามาทับ เสนอ Extension รุ่นถัดไป 0.15.470 เฉพาะเมื่อยังไม่ชนตอนเริ่มงานจริง ส่วน Setup ถัดไปคาด beta.22 จาก preflight แต่ต้องให้ build guard ตรวจซ้ำเมื่อมีคำสั่งบิลด์

protocol ใหม่เปิดด้วย capability และ version ของ job/recovery state ที่ชัดเจน จับคู่ desktop/helper/content scripts และตรวจไฟล์จริง ไม่ใช่แก้เลขให้ผ่าน popup เมื่อข้อมูลคนละสัญญาให้แจ้งอัปเดตก่อนเริ่มงาน ไม่ปล่อย workerคนละรุ่นทำงานปน

งานเก่าไม่ migrate ตอนอ่านหรือ Resume โดยอัตโนมัติ สำหรับ `0589D9` เสนอ recovery เฉพาะงานเมื่อเปิดใช้รุ่นใหม่และยืนยันไม่มี active/unknown Send: อ่านคำตอบเดิมของ exact job/request → บันทึกร่าง → normalize reading → ตรวจบทครบชุด → commit → ทำต่อจากขั้นตอนที่ยังไม่เกิดสื่อ ไม่สร้าง job/เรื่องใหม่ ไม่เขียน job.json ตรงเพื่อหลบ validator

ก่อนรวม source ตรวจ loaded paths/process/worker/pending state ตามจริง ถ้ายังมีงานหรือไม่รู้ loaded path ให้เตรียม patch/fixtures แยกและรอช่วงปลอดภัย ไม่แก้ไฟล์ที่ process อาจโหลดใหม่ได้กลางงาน

สำรองเฉพาะไฟล์ที่จะเปลี่ยนและตรวจ hash ก่อน handoff เก็บ artifact เก่าทุกตัวไว้; rollback ผ่าน compatibility/migration ของ ledger ใหม่ ห้ามให้โค้ดเก่าอ่านสถานะใหม่แล้วตีความเป็น Send ใหม่ และไม่ restore queue/job/media ย้อนหลัง

## 15. Definition of Done และสิ่งส่งมอบ

- สัญญาข้อมูลกลาง + normalizer + durable recovery protocol ผ่าน test matrix
- โปรแกรม/Extension คู่ใหม่พร้อม fixture ของข้อผิดพลาดจริง ไม่ใช่ number-only release
- งานปกติข้างเคียงไม่เสีย, format error กู้ได้, saved results ไม่ถูกสร้างทับ, cancel/resume ใช้งานจริง
- รายงานแยก source tests / installed command / real output / clean-machine / untested cases พร้อม hashesและงบทดสอบจริง
- คู่มือสั้น: อัปเดตโปรแกรม/Extension, ทำต่อจากงานเดิม, เมื่อใดต้องล็อกอินหรือแก้โควตา, เก็บ diagnostic อย่างไร
- Installer เป็นขั้นตอนถัดไปเมื่อมีคำสั่ง build และ source ผ่านด่าน ไม่ใช่ผลลัพธ์ที่สร้างในการวางแผนนี้

การเปลี่ยนครั้งนี้มีเพียงเอกสารแผน ไม่แก้ runtime/source version, user jobs, queues, Extension installation หรือ monitor ไม่รัน provider generation และไม่รัน full suite ซ้ำเพื่อเอกสาร
