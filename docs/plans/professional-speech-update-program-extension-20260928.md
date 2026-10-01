# แผนอัปเดตโปรแกรมและ Extension — บทพูดมืออาชีพ

วันที่ 2026-09-28 • สถานะ: แผนละเอียด ยังไม่แก้ runtime / บิลด์ / ติดตั้ง

## 1. เป้าหมายและขอบเขตที่ยึด

นำชุดพรอมต์ที่สรุปกับผู้ใช้เข้า SmartFlow ให้บทรีวิวและเรื่องเล่าน่าสนใจ พูดเป็นธรรมชาติ ไม่อ่านข้อมูลหลังบ้าน รักษาข้อเท็จจริงและผู้พูด ผ่าน SmartSub Voice Clone และเสียงในคลิป Meta AI / Google Flow พร้อมโปรแกรมและ Extension รุ่นคู่กัน

เอกสารต้นทาง:

- [แผนเสียง](professional-speech-20260928.md)
- [พรอมต์ทั้ง 8 ส่วนและตัวอย่างก่อน–หลัง](professional-speech-prompt-pack-20260928.md)
- [แผนผูกผู้พูด](video-speaker-binding-20260928.md)
- [ฐานโปรแกรมหลัก463](../reports/main-upgrade-pointing-463.md)

รอบนี้ใช้ smartflow-operator → smartflow-extension-tester → smartflow-release-builder อ่านโค้ดและข้อกำหนด ตรวจสถานะสาธารณะกับ static preflight เท่านั้น ไม่สั่งสร้างสื่อ ไม่ตรวจ endpoint แจก commands ไม่ใช้เครดิต ไม่แตะคิว ไม่เปิด monitor ไม่อ่านข้อมูลลับ และไม่ติดตั้ง Extension ซึ่งผู้ใช้ระบุว่าจะทำเอง

ไม่รวม: ออกแบบ UI ใหม่ทั้งโปรแกรมตาม mockup เก่า, เพิ่มผู้ให้บริการ/โมเดล, เปลี่ยนระบบสมาชิก, แก้บริการ SmartSub ฝั่งเซิร์ฟเวอร์, อัปโหลดเผยแพร่เว็บ, ล้างงาน, เปลี่ยน retry policy ทั้งระบบ หรือทำ native Flow voice assets เพิ่มโดยอัตโนมัติ

## 2. ฐานที่ตรวจได้ในรอบวางแผน

| รายการ | หลักฐาน ณ เวลาตรวจ | ความหมาย |
| --- | --- | --- |
| Canonical source / desktop requirement / release runtime | 0.15.463 | ฐานสะสมปัจจุบัน ห้ามเริ่มจาก457/460หรือ Git HEAD เก่า |
| Extension เชื่อมต่อ | 0.15.463 หนึ่ง client compatible | ยืนยัน heartbeat เท่านั้น ไม่ใช่ทุก content script/พรอมต์/คุณภาพคลิป |
| งานที่สถานะสาธารณะแสดง | observed_idle; คิว paused; queued/running0 | ไม่ได้ยืนยัน provider tab / pending Send / loaded source path ครบ ห้ามถือเป็นสิทธิ์ reload |
| Artifact Extension ล่าสุดตาม preflight | 0.15.463 | รุ่นใหม่ต้องไม่ทับ folder/ZIP นี้ |
| Customer Setup ล่าสุด | 0.3.0-beta.17 คู่ Extension457 | เป็นแพ็ก frozen คนละฐานกับโปรแกรมหลัก463 ไม่ควรนำมาติดตั้งทับเพื่อรับฟีเจอร์ใหม่ |
| Static release preflight | static_checks_passed=true, customer_ready=false | inputs/markers/guards ผ่าน แต่ยังไม่ได้ build/test รุ่นที่กำลังวางแผน |
| Customer candidate ถัดไปที่ helper เสนอ | 0.3.0-beta.18 | เป็นเลขเสนอ ณ เวลาตรวจ ต้องตรวจไม่ชนอีกครั้งก่อนออกจริง |

เลข Extension เป้าหมายเสนอ **0.15.464 หากยังว่างและไม่มี approved รุ่นใหม่กว่าระหว่างลงมือ**; ตอนวางแผนนี้ไม่เปลี่ยนเลขในไฟล์ใด และไม่ประกาศ464พร้อมใช้

ฐาน463รวม scene-serial460, conversation-load461, Meta service-outage462 และนิ้วชี้463แล้ว ต้องรักษา cumulative fixes เหล่านี้ ไม่ apply staged patches เก่าซ้ำ

## 3. ข้อสรุปเชิงออกแบบ

### 3.1 แก้ปัญหา “ความยาวตามที่ระบุไว้” ที่ต้นทางบท

แบ่งข้อมูลเป็นข้อเท็จจริงของรุ่นที่เลือก, รายละเอียดที่เห็นจริง, unknown/conflict และข้อจำกัดสำคัญต่อการใช้ ข้อมูลสินค้าที่ดึงมาเป็น data ไม่ใช่คำสั่งให้ AI ทำตาม

- รู้ค่าจริง: เล่าให้ตรง เช่น “สายรุ่นนี้ยาวสองเมตรครับ” ไม่ต้องเติมภาษารายงาน
- ไม่รู้: ไม่แต่งค่า ไม่อ้างว่ามีหลายขนาด และไม่เติม “ตามที่ระบุไว้” ให้ข้ามประเด็นที่ไม่จำเป็น
- ข้อจำกัดสำคัญ: บอกอย่างเป็นธรรมชาติ ไม่ลบคำว่า “ประมาณ” หรือเงื่อนไขของรุ่นเพื่อทำให้ดูมั่นใจเกินข้อมูล
- แยกขนาด/ความยาวสินค้าออกจากระยะเวลาคลิป/จำนวนฉากอย่างเด็ดขาด
- ไม่ลบคำต้องห้ามแบบ regex ทั้งงาน เพราะบางบริบทเป็นคำพูดที่ผู้ใช้ล็อกไว้หรือบทเปรียบเทียบที่ต้องอ้างแหล่ง

ยังไม่มี job ID/คลิปล่าสุดที่แน่ชัดสำหรับตัวอย่างของผู้ใช้ จึงเพิ่ม synthetic fixture ตามข้อความที่รายงานก่อน ไม่อ้างว่าพิสูจน์ root cause ของไฟล์จริงแล้ว และไม่สุ่มเปิดงานส่วนตัวทุกงาน

### 3.2 บทเดียว ส่งต่อหลายบริการ

บทพูดจริงเป็นแหล่งเดียว มีผู้พูด/ผู้ฟังแยกจาก text; ข้อมูลน้ำเสียงและกล้องไม่ปนลงเสียงหรือซับ

สรุปโฟลว์: ข้อมูลสินค้า/เรื่อง → บทที่ตรวจแล้ว + แผนฉาก → ภาพและ motion → แปลงเสียงตามโหมด → บันทึกผลรายฉากตาม gate เดิม → ประกอบ Final

พรอมต์8ส่วนไม่ใช่ AI8รอบ: คัดข้อมูล/เขียนบท/แบ่งฉาก/ร่างภาพใช้คำขอวิเคราะห์เดิม ตัวเตรียม SmartSub เป็น deterministic code ไม่เรียก LLM เพิ่มทุก turn

### 3.3 ค่าเริ่มต้นใช้ง่ายและไม่ย้อนแก้งานเก่า

- งานใหม่จากฟอร์มหลังอัปเดตใช้ speech contract รุ่นใหม่ โดยเลือก profile จากแนวบทและโทนที่บันทึกอยู่แล้ว ไม่ต้องให้ผู้ใช้ตั้งค่าหลายช่องเพิ่ม
- งาน/คิวที่บันทึกก่อนอัปเดตและไม่มี version ใหม่นี้ต้องทำต่อแบบเดิม ไม่เติม default ใหม่ตอนอ่านหรือ Resume แม้ยังมีฉากไม่ครบ
- เปลี่ยนเฉพาะฉากค้างของงานเก่าได้เมื่อมีคำสั่งแก้ฉากนั้นโดยตรงและ revision ที่ตรวจแล้ว ไม่ migrate ทั้งคลังอัตโนมัติ
- ไม่เพิ่มหน้า UI ใหม่ทั้งหน้า; ใช้ส่วนดู/แก้บทเดิม แสดง “บทที่จะพูด” แยกจาก “คำกำกับ” และ “ข้อมูลตรวจงาน” ถ้าต้องเพิ่มการแสดงผล ให้ยุบส่วนละเอียดไว้ก่อน
- บท exact ของผู้ใช้และฉากที่สร้างสำเร็จแล้วมีลำดับความสำคัญสูงกว่ากฎการปรับสไตล์

## 4. สัญญาข้อมูลใหม่ที่เสนอ

เพิ่ม `speech_delivery_version: 1` และ `speech_delivery_plan` ที่ backend ตรวจและ freeze ก่อนการผลิตครั้งแรก เป็นข้อมูลเสริม ไม่แทน fields เดิมอย่าง narration_script / scene_narrations / scene_dialogue_turns

ส่วนหลักใน plan:

| ข้อมูล | แหล่ง/หน้าที่ |
| --- | --- |
| resolved profile / tone / CTA rule | ใช้ค่าเลือกของงาน ไม่อ่าน global settings ใหม่ระหว่าง Resume |
| scene index / effective duration / revision | ผูกกับ scene_video_plan และ revision ที่ใช้จริง ไม่ hard-code8วินาที |
| speaker binding / listener / placement | อ้าง cast/entity เดิม; on-screen, off-camera หรือ narrator |
| speech text reference / hash | อ้างข้อความเดิมที่อนุมัติ ไม่สร้างอีกชุดที่แก้ไม่ตรงกัน |
| pace / emphasis / pauses / restrained delivery | เฉพาะค่าที่ตรวจได้; emphasis ต้องเป็นข้อความที่มีในบทจริง |
| provenance / review warnings | หลักฐานข้อมูลและข้อจำกัด ไม่ส่งเข้าเสียง |
| compiler version / supported controls | ระบุว่าทางบริการนั้นใช้คำกำกับอะไรได้จริง |

เลือก stable character ID จาก entity เดิม หากต้องสร้าง role ID ให้สร้างครั้งเดียวตอนรับงานใหม่ ชื่อผู้พูดเดิมยังใช้ได้ ห้ามเปลี่ยนชื่อ cast ทุกจุดเป็น @ชื่อ

`@พ่อ` เป็น label ที่แสดง/จับคู่กับตัวละคร ไม่อยู่ใน text; การจับคู่ในโปรแกรมไม่ได้เป็นหลักฐานว่า Meta/Flow รองรับ native @tag หรือว่าคนในวิดีโอพูดถูกแน่นอน

ตั้งขอบเขตชนิดข้อมูล ความยาว ขนาดแผน และจำนวน turn ตามสัญญาเดิม ไม่มี field ที่ AI ใช้เปลี่ยน provider, credits, queue หรือ permission ได้ ข้อมูล optional ด้านสไตล์หายให้ใช้ deterministic default ที่ freeze แล้ว ไม่ไปสร้างบทเพิ่มโดยเดา

## 5. แผนแก้ฝั่งโปรแกรมหลัก

| งาน | จุดที่จะตรวจ/แก้ | เกณฑ์ผ่าน |
| --- | --- | --- |
| กฎเขียนบทกลาง | helperใหม่ `core/speech_delivery.py` (ชื่อเสนอ), product_script.py, product_story.py, creative_brief.py, storytelling.py, story_manager.py | คำสั่งไม่ขัดกัน; mode/CTA/facts/POVเดิมอยู่ครบ |
| เก็บ options ตอนสร้าง/เข้าคิว | creation_queue.py, product_runtime_snapshot.py, product_prepare_options.py และ call sitesสร้างงานใน ui/main_window.py | snapshot ไม่หลุดจาก allowlist; งานเก่าไม่มี version ยังเหมือนเดิม |
| รับผลวิเคราะห์ | Story/Product validators และ checkpoint setters | จำนวนฉาก/text/turns ตรงกัน; unknown speaker ไม่ถูกเปลี่ยนเป็นคนแรกเอง |
| แปลงเสียง SmartSub | scene_voice.py, story_script.py, thai_tts.py, external_tts.py, chunked_tts.py, story_finisher.py | text/notes/ซับตรงกัน คง normal1.0x/reference/ledger ไม่ส่งคำกำกับให้พูด |
| Native delivery | media_audio.py, story_performance.py, product_pointing.py | blockเสียงชุดเดียว; reviewer/narrator/dialogue/POV/silent ถูก branch |
| Motion และการส่งวิดีโอ | story_visual_plan.py, flow_motion_plan.py, meta_prompt.py, meta_video.py, meta_redesign.py | context/hash ตรงภาพและบทฉากจริง ไม่แต่งเสียงซ้ำ |
| ฉากที่เขียนใหม่อย่างได้รับอนุญาต | scene_context_revision.py และ motion revision record | ใช้บทฉบับใหม่ที่ตรวจแล้วเฉพาะฉากนั้น ไม่ใช้เสียงเก่าปะกับบทใหม่ |
| การแสดงบท | หน้าเดิม web_ui/product_story.js, storytelling.js และจุดดูบทจริงที่ตรวจพบ | ไม่เพิ่มความรก/fieldบังคับ; คำกำกับไม่แสดงเป็นบทอ่าน |

ก่อนแก้ caller ใดให้ยืนยัน symbol/owner จริงด้วย rg ไม่แก้ทุกไฟล์ในตารางโดยไม่มีเหตุ ตารางคือแผนเส้นทาง ไม่ใช่คำสั่ง rewrite ทั้งระบบ

### SmartSub โดยเฉพาะ

1. ทำตัวเตรียม effective speech กลางให้ voice/preview/subtitle ใช้ pronunciation notes ชุดเดียวกัน โดยแก้ช่องว่าง scene_voice ที่ไม่ส่ง notes พร้อม fixture
2. รักษาอังกฤษที่ไม่รู้จักให้ผ่านตาม regression เดิม ไม่คืนข้อห้ามอังกฤษที่เคยทำให้คิวหยุด
3. `normal / 1.0x` ยังคงเป็น invariant ไม่แปลง delivery emotion เป็น API emotion_id
4. ไม่เพิ่ม SSML/แท็กอารมณ์ใหม่จากการเดา whitelist ที่โค้ดยอมรับยังต้องแยกจากความสามารถ engine จริง ใช้ pause metadata เมื่อยืนยันวิธีรองรับ ไม่คาดหวัง newline ให้พักแน่นอน
5. ไม่เพิ่มคำขอ TTS ทุกประโยค คง chunk2000ตัวอักษรและ idempotency เดิม
6. ห้ามเปลี่ยน identity ของไฟล์เสียงเก่าเพียงเพราะเพิ่ม metadata; งานใหม่คำนวณ key จาก effective audible payload/voice และค่าที่มีผลจริง ใส่ version discriminator เฉพาะ contract ใหม่
7. เสียงจริงยาวเกินให้ตรวจเส้นทาง fit เดิม ไม่ speed-up หรือตัดคำท้ายโดยพลการ

## 6. แผนแก้ฝั่ง Extension

### 6.1 ChatGPT/Gemini ผู้วิเคราะห์และผู้ช่วยเขียน motion

- จุดหลัก `browser_extension/chatgpt.js`: ตรวจส่วน validateProductCreativePlan, validateStorytellingPlan, storytellingRepairInstruction, creative context และ helper motion/repair
- ให้รับ schema/version และส่งต่อแผนที่ตรวจแล้วครบทั้งการอ่านผลปกติ/JSON repair/Resume ห้ามตัด fields ใหม่ทิ้งหรือเติมค่าให้ legacyเอง
- Gemini ที่ใช้ parser/transportร่วมต้องมี fixtureยืนยัน ไม่อ้างว่าทดสอบ GPTแล้วเท่ากับ Geminiผ่าน
- เลิกคำสั่งขัดกันเฉพาะ branch ใหม่ เช่น helperเขียนเสียงชุดใหม่ทับ canonical dialogue; ไม่เปลี่ยน selector การแนบรูป การคลิก Send การอ่านภาพ หรือ timeout เพียงเพื่ออัปเดตบท
- ตรวจทุกจุดจำกัดความยาว prompt: ห้ามตัดกลาง exact line/ผู้พูด ถ้าเนื้อหายาวต้องจัด composition ให้พอก่อน Send ไม่ truncate แบบเงียบ

### 6.2 Background / Flow / Meta

- `background.js`: พก version/revision/hash และ audio mode ผ่าน package/helper/recovery checkpoints; อย่าใส่ flagsใหม่ที่ทำให้คำสั่งเก่าถูกส่งซ้ำ
- `flow.js`: เส้นทางช่วยเขียน motion ต้องรักษา canonical audio block; helperBuild อัปเดตเป็นรุ่นคู่ ตรวจไม่ให้ content script รุ่นเก่ารับงานใหม่ก่อน matching readiness
- `src/platforms/meta-ai/video.js`: ยืนยันว่าผู้ส่งอ่าน promptฉบับสุดท้ายตรง saved package ถ้าไม่ต้องแก้ behaviorไฟล์นี้ให้ใช้bytesเดิม ไม่แก้ Send/Stop/download/classifier โดยไม่มีข้อผิดพลาดใหม่
- API dubbing: ปิด competing provider speechตามbranchเดิม; native: ใช้exact lineพร้อมdelivery; silent: ไม่เพิ่มเสียง; music/SFXตามค่าเดิม
- one answer / owned request / request_id / run_id / scene / cancellation / download receipt ใช้เดิมทั้งหมด ไม่ย้ายผู้รับผิดชอบจากdesktopไปExtensionซ้ำ

### 6.3 แยก recovery สองประเภท (ข้อเพิ่มเติมจาก source)

**A. อ่านผล/ดาวน์โหลด/บันทึก/บริการชั่วคราว:** บทและเสียงฉากที่อนุมัติคงเดิม กู้เฉพาะขั้นค้าง ภาพมีแล้วต้องอ่านก่อน ไม่ใช้ความเงียบเป็นเหตุส่งซ้ำ

**B. creative revision ที่ได้รับอนุญาตตาม contract เดิม:** ใน background.js มี creative_revision_version1 ที่อนุญาตเปลี่ยนเรื่องและบทของฉากที่ล้มเหลว; scene_context_revision.py มีการยืนยันและประกอบฉบับใหม่ ต้องคงสิทธิ์นี้ไว้ เมื่อบทใหม่ผ่านvalidatorให้สร้าง delivery snapshot/hashของ revisionใหม่นั้น ไม่ฝืนแนบบทเก่าหรือเสียงเก่า บทก่อนหน้าถูกเก็บ audit ไม่ถูกลบ

ห้ามใช้แผนอัปเดตพรอมต์เป็นอำนาจเริ่มcreative revisionเอง หรือเปลี่ยนการปฏิเสธจริงของผู้ให้บริการเป็นเหตุ retry เพื่อหลบข้อจำกัด

## 7. งานทีละฉากและข้อมูลเก่า

คงลำดับที่ผู้ใช้ต้องการ: ภาพ1 → วิดีโอ1 → บันทึกผลฉาก1 → ภาพ2 → วิดีโอ2 → บันทึกผลฉาก2 แล้วประกอบตามโฟลว์เดิม ไม่ส่งทุกฉากพร้อมกัน

- Meta serial gate ต้องอ้าง durable owned clip receiptเดิม ไม่ใช้ Flow rendered-audio complete flagแทน
- บททั้งเรื่อง/outlineยังเตรียมตามโฟลว์เดิม การทำmediaทีละฉากไม่ใช่การแต่งเรื่องใหม่ทุกฉาก
- เพิ่มสไตล์ไม่ทำให้ image/video/voice/coverที่เสร็จแล้ว staleทั้งงาน
- เปลี่ยนค่าหน้าฟอร์มหลังเข้าคิวไม่เปลี่ยน snapshotของคิวเดิม
- Cancel/ลบแล้วยังยกเลิก/ลบ ไม่ resurrect งานเพื่อทดสอบ
- เพลง ซับ โลโก้ ปก aspect ratio model และ providerเดิมไม่เปลี่ยนเงียบ ๆ
- Finalสำเร็จไม่เท่ากับปกสำเร็จ ต้องตรวจตามoptionsของงาน และไม่เปิดคิวเพิ่มจากความสำเร็จของชุดทดสอบ

## 8. ลำดับลงมือและด่านผ่าน

### P0 — ยืนยันฐานและเตรียมพื้นที่ปลอดภัย

อ่านสถานะล่าสุด/รุ่น/source changes/loaded pathก่อนแตะไฟล์ ถ้ายังมีงานหรือไม่รู้ไฟล์ที่ถูกโหลด ให้เตรียมpatchและทดสอบในพื้นที่แยก ไม่เปลี่ยนcanonicalที่อาจถูกโหลดใหม่ได้ ไม่หยุดคิวเพื่อความสะดวก

ถ้าต้องใช้ checkoutแยก ให้ตรวจworktreeที่มีอยู่ก่อน และรักษาworking-tree changesที่อนุมัติแล้ว ไม่เริ่มจากremote/GitHEADเก่าจนฟีเจอร์463หาย สร้างbaseline hashesและรายการไฟล์เฉพาะscope ไม่คัดลอกcredentials/profiles/userjobsไปแพ็กทดสอบ

ผ่านเมื่อ: ระบุฐานและrollbackของcodeได้ชัด พร้อมsynthetic fixtures ไม่มีผลต่อuserstate

### P1 — เพิ่ม failing fixtures และสัญญาบทใหม่

ใช้ประโยคที่ผู้ใช้รายงาน ข้อมูลขนาดขัดกัน และข้อมูลเวลาคลิปเป็นfixture กำหนด schema/defaults/freeze/legacy branch ก่อนปรับprompt เพิ่ม shared fixturesให้Python/JSใช้กรณีเดียวกัน

ผ่านเมื่อ: fixtureจับอาการที่ต้องแก้ได้ และ legacy parityมีbaseline ไม่เปลี่ยนexpectedเพื่อซ่อนproductionregression

### P2 — ตัวเขียนบทและ snapshot ฝั่งโปรแกรม

รวมกฎทั้ง8ส่วนตามจุดเรียกเดิม เลือกprofileตามmode ให้ข้อมูลตรวจงานแยกจากspeech รักษาบทexact/CTA/selectedvariant ตรวจไม่มีหน้าตั้งค่าหรือAIroundเพิ่มไม่จำเป็น

ผ่านเมื่อ: วิเคราะห์synthetic inputsได้schemaครบ บทไม่พูดmetadataและไม่แต่งfact งานเก่ายังเหมือนเดิม

### P3 — เสียงและผู้พูด

ทำcanonical speech preparationสำหรับSmartSubและnative compilerสำหรับMeta/Flow ผูกspeakerด้วยcastเดิมและplacementที่ตรงภาพ actual@asset integrationไม่รวมเฟสนี้

ผ่านเมื่อ: APIไม่อ่านคำกำกับ/nativeไม่เพิ่มบท/นิ้วชี้ยังหลังกล้อง/คนฟังไม่พูดแทรกในคำสั่ง; ไม่อ้างผลวิดีโอจริงจากfixture

### P4 — ต่อ Extension และ revision/recovery

ทำtransport/validator/format-repair/resume/creative-revisionให้ครบ ป้องกันshortened promptและstaleaudio ไม่แก้browsergesturesข้างเคียง

ผ่านเมื่อ: normal, service recovery, authorized creative revision, restart, late resultและcancelรักษาข้อมูลถูกrevision ไม่มี duplicate dispatch

### P5 — ทดสอบรวมและฟังตัวอย่างตามงบ

focused → JSsyntax/bridge/UI → fullsuiteหนึ่งครั้งเมื่อruntimeนิ่ง ผูกhashesกับผลทดสอบ ถ้าแก้fixture/docหลังfull ให้บันทึกแยกและรันเฉพาะที่กระทบ ถ้าruntimeเปลี่ยนต้องตรวจcoverage/fullใหม่ตามความเสี่ยง

Offline ผ่านแล้วจึงทดสอบinstalledและpaidตามขอบเขตที่อนุญาต ไม่มีสิทธิ์ใช้เครดิตจากการขอวางแผนนี้

ผ่านเมื่อ: มีผลแยกfixture/manualUI/installeddispatch/provideroutput ไม่เรียกcandidateว่าใช้งานจริงผ่านจากsyntaxอย่างเดียว

### P6 — จับคู่รุ่นและนำเข้าโปรแกรมหลัก

เลือกnextunusedversionหลังrecheck ทำmanifest/desktop/helper/releaseให้ตรงกัน ตรวจbasehashก่อนรวมเฉพาะdiffที่ผ่าน ไม่ทับunrelatedchanges สำรองcodeที่เปลี่ยนและsyncเอกสารปัจจุบัน

สำคัญ: ห้ามจบโดยเหลือฟีเจอร์เฉพาะstagingแล้วรายงานว่าโปรแกรมอัปเดตแล้ว ต้องตรวจcanonical bytesเท่ากับcandidateและpost-mergefocusedchecks หากlive/loaded safetyไม่ผ่าน ให้ส่งสถานะprepared-not-activatedตรง ๆ

ผ่านเมื่อ: canonicalได้รับdiffครบจริง ไม่มีversion-onlybump รุ่นก่อนคงเก็บได้ และงานผู้ใช้ไม่ถูกแตะ

### P7 — แพ็กและส่งมอบ

แพ็กExtensionผ่านtools/package_current_extension.py เฉพาะเมื่อruntimeนิ่ง ตรวจทุกไฟล์source/folder/ZIPและSHA256 คู่programruntimeตรงกัน พร้อมchange log/tests/ข้อจำกัด/activate steps

ถ้าถึงงานบิลด์ลูกค้าที่ได้รับอนุญาต: ใช้guardedbuilderเดิมtools/build_installer_one_click.py ไม่ใช้beta17/457เป็นsourceและไม่สร้างpipelineใหม่ ดูหัวข้อ9

ผ่านเมื่อ: artifactsไม่ทับรุ่นก่อนและตรวจกลับหาsourceที่ทดสอบได้

### P8 — เปิดใช้จริงและตรวจหลังอัปเดต

ผู้ใช้ติดตั้งExtensionเองตามข้อตกลง เปิดโปรแกรมใหม่เฉพาะเมื่อปลอดภัย ตรวจheartbeat/clientID/path/versionและreader/helperจริง ไม่โหลดExtensionตัวที่สามหรือย้ายstorageโดยเดา

ทำงานใหม่เล็ก ๆ ตามขอบเขตที่อนุญาต ตรวจบทที่ส่งจริงหนึ่งชุด ผลฉากและFinal/ปกเดิม ไม่เปิดmonitorที่เคยสั่งปิดเอง

ผ่านเมื่อ: ระบุได้ว่าขั้นใดactivated/verifiedจริง และไม่มีการอ้างว่าคลิปprofessionalผ่านก่อนฟัง

## 9. รุ่น แพตช์ และตัวติดตั้ง

### Runtime pair

รายการที่ต้องตรง: browser_extension/manifest.json, core/local_bridge.py REQUIRED_EXTENSION_VERSION, helperBuildในflow.jsและbackground.js, CURRENT_RELEASE runtime/artifact paths และdocumentationของรุ่นจริง

เพิ่มcontractcheckว่ารุ่นเดิม+bytesใหม่ห้ามแพ็กทับ และห้ามinstaller/updaterเลือก Extensionเก่าจากcustomer_distributionเมื่อruntimeใหม่กว่าพร้อมคู่ที่ทดสอบแล้ว

### โปรแกรมหลักบนเครื่องนี้

SmartFlow AI.exeเดิมเป็นlauncherของsourceหลัก ต้องรวมcodeเข้าcanonicalจริงและเปิดใหม่เมื่อปลอดภัย การวางZIPในdeliverablesอย่างเดียวไม่อัปเดตโปรแกรม ผู้ใช้เลือกinstallExtensionเอง จึงรายงานmain-merged / app-restarted / extension-connectedแยกกัน

### ลูกค้าที่ติดตั้งแล้ว / ลูกค้าใหม่ (เมื่อมีคำสั่งสร้างแพ็ก)

- แพตช์โปรแกรมต้องเป็นcumulativeจากฐานลูกค้าที่ระบุและทดสอบ ไม่ใช่แค่diff463→464 เพราะผู้ใช้beta17ยังมี457และขาด458–463
- ใช้supported_fromที่พิสูจน์แล้วเท่านั้น ทดสอบbeta17→candidate และไม่อ้างรองรับทุกเวอร์ชันจากการผ่านฐานเดียว
- รักษาsigned envelope/payload/hash/Extensionidentityผ่านpipelineเดิม; เครื่องมือsign_customer_releaseต้องตรวจinput/output, notesจริง และห้ามทับpatchชื่อเดิมก่อนเรียก ไม่อ่าน/พิมพ์privatekeyในการวางแผน
- Setupสำหรับเครื่องใหม่ใช้customer versionถัดไป เช่นbeta18ถ้ายังว่าง พร้อมExtensionรุ่นคู่ใหม่ ไม่จำเป็นให้เลขcustomerกับExtensionเหมือนกัน
- ตรวจBUILD/PAYLOAD/sourcehashes, frozenimports/UIassets/fonts/FFmpeg/FFprobe/WebView2และส่วนประกอบที่buildจริงใช้ ไม่อาศัยPATHหรือruntimeCodexบนเครื่องพัฒนา
- ไม่รวมworkspace, jobs, mediaส่วนตัว, configลับ, logs, profiles, cookies, keys หรือdeveloper-onlypaths
- cleanWindows/VMทดสอบinstall→normalEXE→pair→media→reopen→upgrade→failure recoveryและdataretention ถ้าไม่มีเครื่องสะอาดให้ระบุยังไม่ตรวจ ไม่ประกาศพร้อมแจกทุกเครื่อง
- การบิลด์ในเครื่องไม่ใช่สิทธิ์เผยแพร่หรือแก้liveupdate server; signingของpatchกับการเซ็นSetupเป็นคนละหลักฐาน ต้องรายงานแยก

Static preflightรอบนี้ผ่าน15checks แต่ยังไม่ตรวจ imports/runtime execution, testsของรุ่นใหม่, compiledSetup, installedprovider, cleanWindows, upgrade/uninstall จึงยังไม่พร้อมประกาศcustomerready

## 10. ชุดทดสอบที่ต้องมี

### Offline functional matrix

| กลุ่ม | ตัวอย่างสำคัญ | ผ่านเมื่อ |
| --- | --- | --- |
| ข้อมูลสินค้า | ขนาดรู้จริง/ไม่รู้/ขัดกัน/คนละvariant, visible-only, claimedbenefit | ไม่แต่งค่า ไม่พูดfillerและไม่ซ่อนข้อจำกัดสำคัญ |
| แยกmetadata | productlength vs clipduration, warnings, camera directions, @labels | ไม่มีproductiontextเข้าvoice/subtitle |
| แนวบท | normalreview, pointing, narrator, solo, dialogue, shortfilm, silent | บุคลิก/CTA/POV/จำนวนฉากเดิม; ทดสอบเฉพาะaudio combinationsที่ระบบรองรับ |
| เสียงAPI | pronunciationnotes, English, pause, >2000chars, savedvoice | normal1.0x, voiceเดิม, no duplicatepaidrequest, subtitleตรง |
| Native | exactline, once-only, listener, offcamera, repeatedaudio block | เลือกbranchถูกและไม่truncateบทสำคัญ |
| Snapshot | ฟอร์มเปลี่ยนหลังเข้าคิว, restart, settingslegacy | savedoptionsไม่ไหลตามหน้าฟอร์ม/รุ่นใหม่ |
| Recovery | service vs creativerevision, unknownSend, lateoriginal, staleACK, cancelled | รักษางานเดิม/ownerและใช้บทฉบับถูกต้อง |
| Serial scenes | ภาพNบันทึกแล้ววิดีโอNยังไม่stored, Voice/coverค้าง | ไม่ข้ามNไปN+1และไม่falsecompleted |
| Upgrade | mismatchpair, duplicateclient, tamperedzip, sameversiondifferentbytes, interruptedupdate | ปฏิเสธก่อนทำลายdata; ไม่ย้อน457หรือส่งคิวซ้ำ |

กลุ่มexistingtestsที่จะเลือกต่อยอด (ตรวจสภาพและisolatedresourcesก่อนรัน):

- test_pointing_review_463.py / pointing_review_463.cjs
- test_storytelling_397.py / test_story_performance.py / test_media_audio_choices.py
- test_external_tts.py / test_chunked_tts.py / test_tts_english_passthrough.py
- test_flow_motion_plan.py / test_flow_motion_bridge.py / test_scene_context_revision_349.py
- test_scene_video_plan.py และmedia/extension/UI variants
- test_single_answer_required_455.py และproviderrecoverycasesที่จุดเปลี่ยนได้รับผลกระทบ
- test_project_release_contract.py / test_build_installer_one_click.py / projectintegrityและinstaller/payloadchecksตามbuilderจริง

เพิ่มtestsใหม่ชื่อเช่น test_speech_delivery.py, test_product_fact_narration.py, speech_delivery_contract.cjs เป็นชื่อเสนอ ไม่อ้างว่ามีแล้ว

### UI และinstalled

ตรวจหน้าสร้าง/ดูบทเดิมในความกว้างปกติและแคบ ไม่คลิปข้อความ/ปุ่ม ดูว่าmodeที่เลือกตรงqueue/package/DOM/result ใช้EXEปกติในtestinstanceที่แยกและtrackPID/port/tabของตัวเอง ไม่แทนinstalledcommandด้วยmanualGenerate

### ตัวอย่างจริงแบบจำกัด ไม่เปิดทดสอบไม่จำกัด

เสนอpilotทีละprovider โดยระบุจำนวนคำขอสร้างจริงและต้นทุนก่อนส่ง: เริ่มนิ้วชี้2ฉากเพื่อดูการต่อเรื่อง, singlevoice, และserialbarrier; ต่อด้วยตัวอย่างสองคนผลัดพูดเฉพาะเมื่อทดสอบspeakerbinding แล้วจึงSmartSubจากสื่อที่มีสิทธิ์ reuse

การฟังเปรียบเทียบMeta/Flow/SmartSubใช้บทและข้อมูลเดียวกันเท่าที่modeรองรับ ไม่สรุปว่าเสียงหนึ่งดีกว่าโดยไม่มีตัวอย่างจริง ไม่ใช้คำขอทดสอบหนึ่งงานเป็นสิทธิ์retryหลายรอบ หากrunnerไม่สามารถรักษางบ/จำนวนGenerateที่อนุญาตได้ ต้องจัดวิธีควบคุมก่อนpaidtest ไม่กดStopกลางSendที่ไม่ชัดเจนเพื่อให้ดูเหมือนไม่เกินงบ

รายงาน5ผลแยก: prompt/schemaถูก, transcriptตรง, ผู้พูดถูกคนจากภาพและเสียง, จังหวะ/การออกเสียงที่ฟังจริง, Final/ปกพร้อม ไม่มีเสียงไม่เท่ากับผ่าน และno_clear_repeatไม่ใช่qualitypass

## 11. การกู้กลับเมื่ออัปเดตมีปัญหา

1. เก็บcodebackupและmanifest/hashesก่อนactivate ห้ามสำรอง/ย้ายChromeprofileหรือข้อมูลสมาชิกไปแพ็ก
2. พบปัญหาระหว่างงานให้เก็บreceipt/resultก่อน ไม่reload/rollbackทันทีขณะSendไม่ชัดเจน
3. เมื่อidleยืนยันครบและได้รับอนุญาต ค่อยคืนprogram+Extensionเป็นคู่ที่รู้ว่าเข้ากันได้ ไม่คืนเฉพาะเลขmanifestหรือdesktopอย่างเดียว
4. คืนcodeไม่คืนworkspaceทั้งก้อน เพราะอาจลบงานที่เกิดหลังอัปเดต เก็บfields/revisionsใหม่ไว้ ไม่นำoldruntimeที่อ่านschemaใหม่ไม่ได้มารับงานใหม่เหล่านั้น
5. Testrollbackต้องพิสูจน์ oldjobsยังอ่านได้ และnew-contractjobsไม่ถูกresumeด้วยlogicเก่าหรือสร้างซ้ำ; หากbackwardreadinessไม่พอให้ใช้forwardfixสำหรับงานนั้น ไม่ล้างcontractทิ้ง
6. rollbackนี้เป็นแผนฉุกเฉิน ไม่ใช่คำสั่งลดรุ่นผู้ใช้ตอนนี้ ไม่ยกเลิกงานหรือpausedqueueเอง

## 12. สิ่งที่จะส่งมอบและความหมายของคำว่าเสร็จ

เมื่อทำimplementationครบ:

- Main sourceรวมจริง ไม่ค้างอยู่เฉพาะstaging พร้อมpairedExtensionรุ่นใหม่
- Extensionfolder+ZIPimmutable และSHA256ตรงsourceทุกไฟล์
- เอกสารสรุปก่อน/หลังพรอมต์ทั้ง8ส่วน พร้อมอธิบายว่าตัวใดเรียกAIจริงและตัวใดเป็นcompilerในโปรแกรม
- รายงานfocused/full/syntax/UI/installed/liveที่ทำจริง รวมskips/blocked/creditsและhashของsourceที่ทดสอบ
- customerpatch/Setupเฉพาะเมื่อสร้างตามคำสั่งและผ่านgate พร้อมversionคู่และsupportedupgradepath
- ขั้นตอนเปิดใช้โดยผู้ใช้: programเมื่อปลอดภัย → Extensionโดยผู้ใช้ → ตรวจpair/readiness → ทดสอบใหม่จำกัด; ไม่อ้างติดตั้งChromeแล้วจากการแพ็กZIP
- ปิดเฉพาะtestprocess/tab/portที่เป็นของงานทดสอบ ไม่ปิดแอป/Chromeผู้ใช้ และไม่เปิดmonitorเอง

เกณฑ์ขั้นต่ำของฟีเจอร์: ไม่มีภาษาหลังบ้านเป็นบทเติม, ไม่แต่งข้อมูล, บุคลิกตรงแนว, บทตรงคนและฉากในcontract, metadataไม่หลุดเสียง, API/nativeไม่ซ้อน, oldjobsไม่เปลี่ยน, savedmediaไม่ซ้ำ และserialpipelineยังผ่าน

**สถานะปัจจุบัน:** แผนและread-onlypreflightเสร็จแล้วเท่านั้น ยังไม่มีsource464, ผลเทสของ464, installerbeta18, liveเสียงตัวอย่าง หรือการติดตั้งใหม่จากคำขอนี้
