# Meta AI video — ผลทดสอบจริงและแผนเชื่อม SmartFlow

วันที่ 2026-09-17 • สถานะล่าสุด: ผู้ใช้สั่งลงมือเพิ่มทั้งสองส่วนแล้ว พัฒนา provider ใหม่ใน candidate377; installed end-to-end ยังรอตรวจหลังติดตั้งคู่รุ่น ดู `docs/reports/meta-video-377.md` ส่วนผลสำรวจและแผนข้างล่างเป็นประวัติก่อน implementation

**ผลต่อเนื่องหลังเปิดสิทธิ์ไฟล์:** ภาพ→วิดีโอทดสอบผ่านหนึ่งคลิปแล้ว แนบภาพ720×1280ในcomposer, ส่งหนึ่งครั้ง, ดาวน์โหลดMP4จริง10วินาที/H264/yuv420p24fps ไม่มีaudio และdecodeผ่าน ดู `docs/reports/meta-image-video-20260917.md` ซึ่งแทนสถานะติดสิทธิ์ในบันทึกรอบแรกด้านล่าง ยังไม่ใช่ installed Extension E2E; ต่อมา377เพิ่มเมนู Meta ในโปรแกรมและเส้นทาง Extension แยกแล้ว

ผู้ใช้สั่งให้เพิ่ม Meta AI เป็นตัวเลือกสร้างวิดีโอ และอนุญาตให้ทดสอบจริงเพื่อวิเคราะห์/วางแผน นี่เป็นคำสั่งใหม่ที่อนุญาตให้พิจารณา Meta อีกครั้ง ไม่ใช่การนำโค้ด Meta รุ่นเก่ากลับมาทับ Flow ที่ใช้งานอยู่

## 1. หลักฐานที่ทดสอบแล้ว

- โปรแกรมที่เปิดอยู่: engine PID 34544 ต้องการ Extension 0.15.375; Product/Story/Presenter ไม่ active และ queue paused ตอนตรวจ Source candidate เป็น 0.15.376 ไม่ได้ restart/reload หรือแตะงานเดิม
- เข้าหน้า `https://www.meta.ai/?locale=th_TH` ด้วย Chrome profile เดิม บัญชีพร้อมใช้งาน มีลิงก์สื่อ `/create` และแชทใหม่
- ส่งข้อความผ่านหน้า `/create` **หนึ่งครั้ง** ขอวิดีโอแก้วเซรามิกบนโต๊ะริมหน้าต่าง แนวตั้ง 9:16 ไม่มีคน/ข้อความ/เพลง/เสียงพูด ไม่มีการส่งซ้ำหรือสร้างคลิปที่สอง
- หน้าเปลี่ยนเป็น `https://www.meta.ai/prompt/05fd5e55-ca7b-4836-98a0-66a8399cc61e` มี user article ตรงกับคำขอ ตามด้วย Meta reply และปุ่มหยุด ต่อมาพบ video จริงกับปุ่มดูวิดีโอ/ดาวน์โหลด
- DOM ของ video ในคำตอบปัจจุบัน: readyState=4, 720×1280, duration=10, ไม่มี media error; media host ที่เห็นคือ `scontent.xx.fbcdn.net` ไม่บันทึก signed URL
- กดดาวน์โหลดจากหน้าต่างวิดีโอ ได้ `C:/Users/keera/Downloads/morning_steam_mug.mp4` ขนาด 2,673,086 bytes
- ตรวจไฟล์จริง: H.264 High, yuv420p, 720×1280, 24fps, 10 วินาที; มี AAC LC mono 24kHz ยาว 10 วินาที Decode ทั้งไฟล์ด้วย FFmpeg ผ่าน exit 0 ภาพที่วินาที 1 ตรงกับแก้วบนโต๊ะ ไม่มีบุคคล
- SHA256: `EED9ABE4379889817B9131962CE7350B42AEA293EBF1B9F3A948C6E2073DAFCD`
- มี audio stream แม้ขอไม่ใส่เพลง/เสียงพูด และข้อความตอบกล่าวถึงเสียงบรรยากาศ ยังไม่ได้ตรวจเนื้อหาเสียงด้วยการฟัง จึงห้ามสรุปว่าเป็นคลิปเงียบจากพรอมต์หรือ browser muted
- ยังวัดเครดิต/โควตาที่ใช้ไม่ได้ ไม่มีหลักฐานว่าไม่จำกัด หรือทุกบัญชีได้ความยาว/ความละเอียดเหมือนกัน

นี่คือ **manual browser test** ไม่ใช่ SmartFlow Extension end-to-end และไม่ได้ทดสอบการเคลื่อนไหวจากรูปอ้างอิงสำเร็จแล้ว

## 2. DOM ที่พบจริงและข้อควรระวัง

| จุด | หลักฐานปัจจุบัน | ใช้ใน adapter อย่างไร |
|---|---|---|
| Composer | `div[role="textbox"][contenteditable="true"][data-lexical-editor="true"]` | จำกัดช่องที่มองเห็นใน composer; หน้าเดียวกันมี input ชื่อแชทด้วย ห้ามเลือก textbox แรกทั้งหมด |
| แนบรูป | ปุ่ม `เพิ่มไฟล์แนบ` | เปิดหน้าต่างสื่อก่อน ไม่ใช่ file chooser ทันที |
| หน้าต่างเลือกสื่อ | heading `เพิ่มสื่อและไฟล์`, ปุ่ม `คลิกเพื่อดู หรือลากแล้ววางที่นี่` | กด Browse ที่อยู่ในหน้าต่างนี้ แล้วรอ input/preview จริง |
| File input | พบ input type=file 2 ตัว, multiple=true, ยังไม่ได้เลือกไฟล์ | จำนวน input ไม่ใช่หลักฐานอัปโหลด; เลือก input ที่สัมพันธ์กับ dialog ที่ใช้งาน |
| ส่ง | `button[aria-label="ส่ง"]` | รอรูปพร้อม + exact prompt + enabled + durable claim แล้ว trusted click ครั้งเดียว |
| ยืนยันคำขอ | `[role="article"][aria-label="ข้อความของคุณ"]` | เทียบข้อความและ reference fingerprint กับงาน/ฉากปัจจุบัน พร้อม URL `/prompt/<id>` |
| คำตอบ | `[role="article"][aria-label="การตอบกลับของ Meta AI"]` | อ่านเฉพาะคำตอบหลัง user article ที่ยืนยันแล้ว ไม่อ่านจากประวัติหรือ gallery ทั้งหน้า |
| กำลังทำงาน | ปุ่ม `หยุด`, ข้อความกำลังสร้างในคำตอบ | เป็น activity ไม่ใช่หลักฐาน success; ไม่ timeout เพราะครบ 6 นาทีอย่างเดียว |
| ผลจริง | video metadata + ปุ่ม `ดูวิดีโอ`/`ดาวน์โหลด` ในคำตอบนั้น | รอ video เปิดอ่านได้ และยืนยัน downloaded file ก่อน commit |
| หน้าขยาย | heading `วิดีโอที่สร้างขึ้น`, ปุ่มดาวน์โหลด | จำกัดปุ่มตาม modal/asset ที่ผูกไว้ มีปุ่มดาวน์โหลดซ้ำใน underlying article ได้ |

ชื่อ/role ภาษาอังกฤษยังไม่ได้สำรวจ ต้องใช้ fixture ที่ได้จาก DOM จริงก่อนเพิ่ม selector ภาษาอื่น อย่าใช้ class สุ่มหรือ Radix ID เป็นตัวหลัก และอย่าคลิกปุ่มในแถบ Vibes/ผลงานเก่า

**ข้อจำกัดตอนทดสอบแนบรูป:** ใช้ frame ที่สกัดจากคลิปทดสอบเอง ไม่ใช่รูปส่วนตัวของผู้ใช้ พบหน้าต่างสื่อและ file chooser แต่ `setFiles` ถูก browser-control ปฏิเสธ `Not allowed` จึงยังไม่มีรูปแนบ และไม่ได้ส่งคำขอที่สอง ต้องให้ผู้ใช้เปิด Allow access to file URLs ของ ChatGPT browser extension ก่อนทดสอบต่อ การปฏิเสธนี้ไม่ใช่หลักฐานว่า Meta AI ไม่รองรับภาพ หรือว่า SmartFlow upload มีบั๊ก ห้ามแก้สิทธิ์ให้เอง

การเข้าหน้าเว็บตรวจได้เฉพาะ DOM ที่แสดงบน browser ไม่ใช่ source ฝั่งเซิร์ฟเวอร์ของ Meta ไม่เรียก private API หรืออ่าน cookie/token

## 3. จุดในโค้ดที่ต้องแก้ก่อนเพิ่มเมนูจริง

1. `browser_extension/manifest.json` ยังไม่มี Meta host/content script; `background.js` และ `core/local_bridge.py` ไม่มีคำสั่ง Meta การเพิ่ม option อย่างเดียวจะไม่มีผู้รับงาน
2. `ui/main_window.py` มี VIDEO_AI_PROVIDERS เฉพาะ Flow, label คืน Google Flow ตายตัว และหลายเส้นทางบังคับ `video_provider="flow"`
3. คลิปสินค้าใหม่วิ่งผ่าน Story: `web_ui/product_story.js` บังคับ `video_generation_mode='google_flow'`; `_desktop_execute_action` แปลง create_product เป็น create_story แล้วบังคับ Flow อีกชั้น ต้องแก้ทั้ง UI และ backend ไม่ใช่เฉพาะ Legacy Product
4. `StoryManager._video_generation_mode`, `CreationQueue.enqueue` และ desktop action validation รับแค่ image_motion/google_flow; scene pipeline/ready/recovery/finalization หลายจุดผูกกับ google_flow โดยตรง
5. `ProductManager._migrate_retired_video_provider` เปลี่ยน `meta` เป็น Flow และเปลี่ยน source/status/history; ห้ามให้ migration นี้แตะงาน Meta ใหม่
6. `core/media_audio.py` รับ flow_original/keep_video_audio เฉพาะ Flow ตอนนี้; หน้า UI และ caption/native-audio path ต้องไม่อ้างว่ามีเสียงไทยหรือลิปซิงก์ Meta โดยยังไม่ทดสอบ
7. `tests/test_video_provider_retirement.py` ตั้งใจห้าม Meta กลับมา; ต้องแทนด้วย contract แยก legacy migration กับ Meta ใหม่ที่ผู้ใช้อนุญาต ไม่ใช่ลบ tests เพื่อให้ผ่าน

## 4. UX ที่จะเพิ่ม

- แยก “สร้างภาพด้วย” ChatGPT/Gemini เดิม ออกจาก “สร้างวิดีโอด้วย” Google Flow / Meta AI สำหรับคลิปสินค้า, Story Shorts, ละครสั้น และวิดีโอยาวตามขอบเขตที่แต่ละโหมดทดสอบแล้ว
- Story คงตัวเลือก Motion ในเครื่อง ไม่เปลี่ยนค่าเริ่มต้นหรือ provider ของงานเก่า
- เมื่อเลือก Meta ให้ซ่อน Flow model/resolution controls และแสดงเฉพาะความสามารถที่ตรวจได้จริง พร้อมปุ่มตรวจการเข้าสู่ระบบ ไม่เดาชื่อโมเดลหรือรับประกัน 10 วินาทีทุกงาน
- บันทึก provider ลง job/queue snapshot; Resume ใช้ provider ของงานที่บันทึก ไม่ตาม dropdown ที่เพิ่งเปลี่ยน งานที่มีคลิปแล้วห้ามสลับเอง
- แสดง “กำลังแนบภาพ → ส่งแล้ว → กำลังสร้าง → กำลังดาวน์โหลด → ตรวจไฟล์ → บันทึกแล้ว” จากหลักฐานจริง แยกขาดการเชื่อมต่อ/รอผู้ใช้/กำลังกู้ผลออกจาก error
- เสียงพากย์แยกและไม่มีเสียงใช้เส้นทางเดิม; ตัวเลือกเสียงจาก Meta ต้องแยกจาก flow_original และเปิดหลังทดสอบเสียงจริง การเลือกไม่มีเสียงต้องถอด audio track ตอนประกอบ ไม่พึ่งคำสั่งใน prompt

## 5. สถาปัตยกรรมที่เสนอ

### Desktop / durable checkpoint

- เพิ่ม provider identifier ใหม่ `meta_ai` และ schema/provider-contract version ชัดเจน ไม่ใช้ legacy `meta`; คง migration เฉพาะงานเก่าที่ไม่มี contract ใหม่ งานที่ถูกย้าย Flow ไปแล้วไม่ย้อนเปลี่ยน
- เพิ่ม Meta package/result/receipt แยกจาก Flow: job_id, scene_index, run_id, attempt_id, provider, reference SHA256, prompt hash, conversation URL, stage, result identity, local path/hash, desktop-ACK revision
- ใช้ worker/final renderer ร่วมเท่าที่ contract เหมือนกัน แต่ไม่เปลี่ยน `flow_clips` ให้หมายถึง Meta เก็บ provider provenance ตามจริงและไม่อ้างเป็น Google Flow clip
- เปลี่ยนการตรวจ mode แบบ hard-coded ในเส้นทางที่รองรับแล้วเป็น provider capability helper แบบ additive รักษา Google Flow settings/scene-gate/voice/final contract เดิม
- บันทึกภาพและพรอมต์ก่อน dispatch; หลังรับไฟล์ต้องตรวจขนาด/ระยะเวลา/codec, SHAซ้ำต่างฉาก, file decode และ atomic commit ก่อนปล่อยคิวถัดไป
- คำสั่ง/result/heartbeat ต้องรับเฉพาะ current lease/run/scene; duplicate result คืน ACK เดิม ไม่รับ late result หลัง cancel หรือเขียนทับไฟล์ดี

### Extension adapter

- เพิ่มโมดูลใหม่ใต้ `browser_extension/src/platforms/meta-ai/` สำหรับ DOM, lifecycle, receipt และ download ไม่คัดลอก Flow controller ทั้งก้อนหรือเปลี่ยน ChatGPT/Gemini Send
- เพิ่ม host เฉพาะ Meta และ media hosts ที่พิสูจน์ว่าจำเป็น; เลือก native Chrome download จากปุ่มก่อนหลีกเลี่ยงการขอ CDN permission กว้างโดยไม่จำเป็น ผู้ใช้ต้องอนุญาตสิทธิ์ใหม่ผ่าน Chrome ตามปกติ
- Router/bridge แยกคำสั่งเปิด/ทำต่อ/ตรวจผล/ดาวน์โหลด Meta ออกจาก Flow แต่ใช้ owned-tab registry/lease/cancel/ACK ที่มีอยู่
- Prompt ระบุสร้างวิดีโอจริงหนึ่งคลิปจากภาพแนบ รักษาสินค้า/ตัวละคร การกระทำ กล้อง อัตราส่วนและโหมดเสียง ห้ามขอ JSON พร้อม media ในคำสั่งเดียว รูป/บทมาจาก AI Web ที่เลือกเหมือนเดิม
- ก่อน Send ต้องตรวจ uploaded preview โหลดสำเร็จจริงและตรงรูป; อย่ากดจาก filename/fileSet อย่างเดียว อย่าเอารูปใน Recent Uploads เป็นหลักฐานแนบ
- หลัง Send เก็บ `/prompt/<id>` และ user article ของรอบนี้ ปุ่มส่งหาย/composer ว่าง/ข้อความ “เสร็จแล้ว” อย่างใดอย่างหนึ่งไม่พอเป็นการรับงานหรือสำเร็จ
- หลายวิดีโอให้เลือกผลใหม่ตัวแรกที่ผ่าน validation ใน owned reply เท่านั้น เก็บ asset identity เพื่อ download/resume ชิ้นเดิม ไม่สุ่มหยิบคลิปเก่า
- จับ native download ID จาก owned action แล้วส่งเฉพาะไฟล์นั้นเข้าโปรแกรม ไม่ค้น MP4 ล่าสุดทั้ง Downloads; ชื่อไฟล์เป็นข้อมูลประกอบ ไม่ใช่หลักฐานเจ้าของ
- เมื่อ desktop ACK บันทึกสำเร็จค่อยปิด owned tab ถ้าไม่มี pending stage/cover งานอื่น ห้ามปิดแท็บส่วนตัว

## 6. ลำดับทำงานและการกู้ผล

`queued → opening → login_ready → attaching → attachment_ready → draft_ready → sending → accepted → generating → result_ready → downloading → validating → saved/ACK → next_scene`

- หลักฐานกำลังสร้าง/ตอบเปลี่ยนยังเดิน: รอต่อและอัปเดตสถานะ ไม่ error จากจำนวนนาที
- Send ไม่ทราบผล: กลับตรวจ receipt/แชทเดิม ห้ามเปิดแชทใหม่หรือส่งซ้ำ
- Result พร้อมแม้ข้อความกำลังสร้างค้าง: ตรวจ owned video/ไฟล์ก่อน ใช้ผลจริงเป็นหลัก
- หน้าไม่ขยับ: ตรวจ connection, route, exact request, existing result ก่อน อนุญาต refresh เดิมแบบมี durable guard และ cancellation check เมื่อยืนยันว่าไม่ทำให้งาน/ร่างหาย แล้วกลับมาอ่าน ไม่ refresh วนทุก poll
- Download ไม่ครบ: รับ/ดาวน์โหลด asset เดิม ไม่สร้างวิดีโอใหม่; ไฟล์ไม่ผ่านให้เก็บหลักฐาน ไม่ใช้ภาพนิ่งเป็นคลิป
- Login/CAPTCHA/สิทธิ์/โควตา: user-action-required เก็บ checkpoint ไม่รายงาน success ไม่เปลี่ยน provider หรือกดซื้อเอง
- Provider ยืนยัน service failure: แยกจาก unknown send แล้วใช้ retry ที่มี receipt และขอบเขตชัดเจน
- Provider ยืนยัน content refusal: ขอทางเลือกเนื้อหาที่ปลอดภัยจริงตามการอนุญาตของผู้ใช้ ไม่กดซ้ำเพื่อเลี่ยงข้อจำกัดหรือเปลี่ยน flags ว่าผ่านเอง

## 7. แบ่งงานพัฒนาและเกณฑ์ผ่าน

1. **ทำหลักฐานภาพ→วิดีโอให้ครบก่อน:** ผู้ใช้เปิดสิทธิ์แล้ว แนบภาพ/ready/user-reference/reply-video/download/ตรวจไฟล์ผ่านเคสแนวตั้งไม่มีเสียงหนึ่งคลิป ตามรายงานต่อเนื่อง ยังต้องมีfixture slow/failed uploadและทดสอบความสามารถอื่นก่อนเปิดcontrolsที่ยังไม่ยืนยัน ห้ามclearช่องLexicalทั้งหมดหลังแนบ เพราะรูปเป็นinline nodeภายในcomposer
2. **เพิ่ม core contract แบบไม่เปิด dropdown:** provider validation, typed package/result, persistent receipt, queue freeze, legacy migration tests และเสียง ตรวจว่าผิด provider ถูกปฏิเสธ ไม่ silently Flow
3. **เพิ่ม Meta adapter:** ใช้ fixtureจาก DOM จริง ทดสอบ Send หนึ่งครั้ง, receive, native download และ ACK; login/limit/unknown ownership ต้องแสดงสถานะที่แก้ต่อได้
4. **เชื่อม UI และ scene pipeline:** เริ่มด้วย single-scene smoke ก่อน จากนั้นสินค้า 3 ฉาก/Story/Drama/long ตามจำนวนที่ได้รับอนุญาต; เนื้อหา ภาพ ตัวละคร เสียงและปกยังใช้เส้นทางเดิม
5. **ทดสอบ regression ทั้งโปรแกรมและ Extension:** รัน targeted แล้ว full suite ครั้งสุดท้ายหลังโค้ดลงตัว ทดสอบติดตั้งจริงด้วยเวอร์ชันคู่ใหม่ก่อนกล่าวว่าใช้งาน end-to-end ได้ ไม่ใช้ manual test นี้แทนผลนั้น

Regression ต้องครอบคลุม: legacy meta migration; new meta_aiไม่ถูก rewrite; queue/restart provider freeze; duplicate upload/Send; slow preview >6min; empty/changed prompt; old reply/video in history; two outputs; wrong scene/run; reload during generation; detached worker; stale heartbeat; completed video with stale busy UI; expired result URL; partial download; bad/duplicate MP4; desktop disk/ACK failure; cancel/late result; quota/login; audio mute; final codec; owned-tab cleanup; unchanged ChatGPT/Gemini→Flow และ cover.

**Definition of Done:** เลือก Meta ในโปรแกรม → snapshotคงเดิม → Extensionแนบรูป/ส่งหนึ่งครั้ง → ได้วิดีโอจริงตรงฉาก → ดาวน์โหลด/ตรวจ/บันทึกและ ACK → ทำฉากถัดไป/ประกอบFinal/ทำปก → ปิดเฉพาะแท็บเสร็จ; Resume ไม่สร้างซ้ำ แสดงสาเหตุเมื่อรอผู้ใช้ และมี installed command evidence ครบ ไม่อ้างว่าไม่บั๊กทุกกรณี

## 8. ขอบเขตการส่งมอบรอบแรก (ประวัติก่อนผู้ใช้เปิดสิทธิ์)

ได้ผลทดสอบหนึ่งคลิป + ตรวจ DOM + ตรวจจุดเชื่อมในโค้ด + แผนนี้ ยังไม่ได้แก้ runtime, เพิ่มเมนู, ส่ง Extension รุ่นใหม่ หรือทดสอบ installed Meta command คลิปและแท็บผลทดสอบเก็บให้ผู้ใช้ดู; ไม่ปิด Chrome/โปรแกรมของผู้ใช้ ไม่มีภาพอ้างอิงอัปโหลดสำเร็จ ไม่มี queue/jobเดิมเปลี่ยนแปลง ไฟล์ frameทดสอบเป็น temporary local artifact ไม่ได้ส่งออกสำเร็จ
