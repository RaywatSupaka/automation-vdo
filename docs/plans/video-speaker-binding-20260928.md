# แผนผูกบทพูดกับตัวละครในวิดีโอด้วย @ชื่อ

วันที่ตรวจ: 2026-09-28 — research / source inspection / plan only

## เป้าหมายและขอบเขต

ผู้ใช้ต้องการเขียน เช่น `@พ่อ พูดว่า "สวัสดีจ้า"` แล้วให้พ่อเป็นผู้พูด ไม่ให้แม่ ลูก หรือตัวประกอบอ่านบทแทนหรือพูดแทรก แนวทางนี้เพิ่มการผูกตัวละครกับบทเดิม ไม่เปลี่ยนเนื้อเรื่อง รูปแบบเสียง ผู้ให้บริการ จำนวนฉาก หรือการทำภาพ N → วิดีโอ N → ฉากถัดไป

รอบนี้ไม่ได้แก้ runtime, สร้างวิดีโอ, ใช้เครดิต, เปลี่ยนคิว, เรียก endpoint แจก commands, รีโหลด Extension, เปิด monitor หรือบิลด์ installer เปลี่ยนเฉพาะเอกสารแผนนี้ ยังไม่รับรองว่าจะแก้การพูดผิดคนจากโมเดลได้ทุกครั้ง

## หลักฐานจากระบบเรา

ตรวจ canonical 0.15.460 และ source ที่เตรียมไว้ `build/pointing-review-463/source` ซึ่งรวมงานที่อนุมัติ 461–463 แล้ว ไม่ใช้ Git HEAD เก่าเป็นฐาน ซอร์สที่เตรียมไว้ยังไม่เท่ากับรุ่นติดตั้งจริง ตัวอ่านสถานะ localhost รอบนี้ตอบ `bridge_unreachable_or_invalid` จึงยังยืนยัน runtime/Chrome ที่กำลังใช้อยู่ไม่ได้ ไม่ถือว่า idle

1. `core/story_performance.py::validate_plan` มี `character_bible`, `scene_dialogue_turns`, `speaker`, `listener` อยู่แล้ว ตรวจชื่อกับ cast และ scene entities; `_audio_instruction` ส่ง ordered dialogue และ cast พร้อมคำสั่งให้พูดตรงตัว ห้ามอ่านชื่อ/คำกำกับ แต่ยังเป็นการอ้างชื่อและคำสั่งภาษา ไม่ใช่ตัวผูกผู้พูดที่พิสูจน์จากภาพจริง
2. `browser_extension/chatgpt.js::validateStorytellingPlan` ตรวจชื่อ/ฉาก/ลำดับบททั้ง GPT และ Gemini ก่อนภาพ แต่ยังไม่ได้มีสัญญา @tag → stable entity → ตัวละครในภาพ → ผู้พูดในวิดีโอครบเส้นทาง
3. `core/story_visual_plan.py::MOTION_RULE` บอกให้ใช้ visible roles แทน personal names และไม่ทวนรูปลักษณ์/เสื้อผ้า ขณะที่ actor branch ขอให้คง speaker-to-visible-role assignments นี่เป็นความกำกวมในคำสั่งที่ควรแก้เฉพาะสัญญาใหม่ ไม่ใช่หลักฐานว่ามันเป็นสาเหตุของคลิปที่ผู้ใช้พบทุกคลิป
4. `core/media_audio.py::_flow_audio_instruction` แยก actor / หนังสั้นสินค้า / รีวิว / ผู้บรรยาย; `core/product_pointing.py::native_audio` ใน candidate463 เป็นคนพูดหลังกล้อง ต้องไม่ถูกสัญญาใหม่บังคับให้เห็นหน้า
5. `core/flow_motion_plan.py::plan_context` มี image hash และ audio instruction ใน identity; `core/meta_video.py::package` และ `core/meta_redesign.py` ประกอบ motion/audio ของฉาก เป็นจุดที่ต้องส่งต่อข้อมูลผู้พูดเดียวกัน รวมถึงเมื่อขอแก้ฉาก
6. `core/flow_speech_quality.py` ตรวจประโยคยาวที่พูดซ้ำจาก transcript เท่านั้น ผล `no_clear_repeat` ไม่ได้พิสูจน์ว่าคนที่ขยับปากเป็นคนถูกต้อง ส่วนงานที่ปิดซับไม่ได้มีหลักฐานถอดเสียงครบทุกงาน จึงห้ามนำตัวตรวจนี้มาอ้างว่า speaker verification ผ่าน

ยังไม่ได้ตรวจคลิปตัวอย่างที่สลับผู้พูดจริงในคำขอนี้ จึงแยก source risks ออกจาก confirmed video failure

## ผลค้นคว้าจากแหล่งทางการ

- Google DeepMind แนะนำให้บรรยายรูปลักษณ์ เสียง การกระทำ และบทของแต่ละตัวละครอย่างเจาะจง รองรับการระบุคำพูดรายตัว: [Veo prompting guide](https://deepmind.google/models/veo/prompt-guide/). ข้อนี้สนับสนุนการส่งข้อมูลตัวละครพร้อมบท ไม่ได้เป็นคำรับประกันเรื่องการพูดถูกคน
- Google Flow ระบุการอ้างตัวละครด้วย `@` ตามชื่อ และการเลือก uploaded assets ด้วย `@`: [Create videos in Google Flow](https://support.google.com/flow/answer/16353334?hl=en). ดังนั้นต้องแยก native character/asset reference ออกจากข้อความ `@พ่อ` ที่พิมพ์ไว้แต่ยังไม่ได้ผูกทรัพยากรจริง
- Flow มีการสร้าง character จากภาพอ้างอิง ตั้งชื่อ และเลือกเสียง: [Manage characters](https://support.google.com/flow/answer/16935308). การมีฟังก์ชันในคู่มือไม่ได้พิสูจน์ว่า account/model/mode ปัจจุบันของผู้ใช้ หรือ Extension ของเราใช้งานได้แล้ว
- Meta อธิบายการสร้าง Vibes พร้อม lip-synced dialogue และ voiceover: [Meta Vibes](https://ai.meta.com/vibes/). คู่มือที่พบในการค้นครั้งนี้ยังไม่ยืนยันว่า arbitrary `@พ่อ` ในช่องสนทนาเว็บเป็นคำสั่งล็อกผู้พูด จึงต้องปฏิบัติต่อมันเป็นป้ายกำกับในพรอมต์จนกว่าจะมีหลักฐาน native binding ของเส้นทางจริง
- Meta แนะนำพรอมต์ที่มีเป้าหมาย เงื่อนไข และรายละเอียดที่เกี่ยวข้อง: [Official prompt examples](https://ai.meta.com/learn/ai-basics/ways-people-use-meta-ai-prompt-examples-to-get-started/). ไม่ใช้บทความวิจัย Movie Gen หรือฟังก์ชัน avatar คนละผลิตภัณฑ์มายืนยันความสามารถของช่องสร้างวิดีโอที่ SmartFlow ใช้อยู่

ข้อสรุปออกแบบ: ใช้ @tag เป็นวิธีเขียนและแสดงตัวละครใน SmartFlow ได้ แต่ต้องแปลงเป็นข้อมูลจับคู่และคำกำกับที่ครบ ไม่ใช่เพิ่มเครื่องหมาย @ แล้วถือว่าโมเดลล็อกคนให้แน่นอน

## สัญญาที่เสนอ

### 1. ทะเบียนตัวละครและผู้พูดที่บันทึกครั้งเดียว

เพิ่ม opt-in/versioned `speaker_binding_version: 1` สำหรับงานใหม่ที่มีบทตัวละคร ใช้ entity ID / cast / ภาพอ้างอิงเดิมเป็นฐาน ห้ามสร้างทะเบียนอีกชุดที่เปลี่ยนชื่อเองในแต่ละฉาก

- `character_id`: อ้าง `story_entities.id` เดิมเมื่อมี; กรณี reviewer ใช้ role ID ที่บันทึกพร้อมงานใหม่ ไม่สร้างตัวละครเพิ่มจากการเดา
- `display_name` และ `tag`: เช่น พ่อ / `@พ่อ`; alias ต้องไม่ชนและไม่เปลี่ยนระหว่าง resume
- ลักษณะและไฟล์อ้างอิงยึดตัวละครเดิม; คำบรรยายเสียงเป็นคำกำกับ ไม่อ้างว่าเป็น voice lock ของ native provider
- รักษา `speaker` ชื่อเดิมเพื่อ compatibility และเพิ่ม `speaker_id`/binding แยก ไม่เปลี่ยนชื่อ cast ทุกจุดให้ขึ้นต้นด้วย @ จนชนตัวเลือกเสียงหรือ validator เดิม
- รับ tag ที่ส่วนผู้พูดของบท/metadata เท่านั้น จับคู่ตรงทะเบียน ไม่ทำ global replace ในข้อความ เช่น email/ข้อความอ้างอิง และไม่ตัด @ ทุกตัวทิ้ง
- ชื่อไม่รู้จักหรือกำกวมต้องไม่แอบเปลี่ยนเป็นผู้บรรยาย/ตัวแรก ใช้เส้นทางแก้โครงสร้างบทก่อนสั่งสร้างสื่อ โดยไม่แต่งผู้พูดใหม่แทนผู้ใช้

### 2. ผูกกับภาพของฉากจริง

บันทึก scene binding ต่อฉาก: image SHA256, ตัวละครที่อยู่ในภาพ, คำอธิบายจำแนกที่สอดคล้องภาพ เช่น “ชายเสื้อฟ้าด้านซ้าย”, และสถานะ `on_screen` / `off_camera` / `voiceover`

ตำแหน่งซ้าย/ขวาเป็นข้อมูลรายฉาก ไม่ติดถาวรกับตัวละคร เมื่อภาพใหม่หรือ recovery เปลี่ยนตำแหน่ง ต้องทบทวน binding เฉพาะฉาก ห้ามใช้ตำแหน่งเก่าแบบไม่ตรวจ และห้ามถือว่าการกล่าวชื่อใน scene prompt พิสูจน์ว่าภาพสร้างตรงจริงแล้ว

ใช้ภาพเดิมที่พร้อมใช้งานเป็นหลัก ไม่สร้าง character sheets เพิ่มโดยอัตโนมัติ ไม่สร้างหน้าคนให้ POV “นิ้วชี้” เพื่อให้ผ่านการตรวจ visible actor

### 3. บทพูดแยกจากคำกำกับอย่างเด็ดขาด

แต่ละ turn มี `speaker_id`, `listener_ids`, `text`, `delivery`, `order` และ silent-list ของช่วงนั้น

- `text` เก็บเฉพาะสิ่งที่ต้องพูด เช่น `สวัสดีจ้า` ไม่มี `@พ่อ`, ชื่อผู้พูด หรือคำสั่ง “พูดว่า”
- ขณะพ่อพูด แม่/ลูกฟังและไม่ขยับปากพูดบทเดียวกัน; เมื่อถึง turn ของแม่ ให้เปลี่ยน silent-list ตามลำดับ ไม่สั่งให้แม่เงียบทั้งคลิป
- ไม่มีเสียงแทรก/ผู้บรรยายเพิ่มในโหมดสนทนา; มีช่วงพักและปฏิกิริยาฟังที่เหมาะกับเวลาเดิม
- บทสั้นพอกับระยะคลิป ไม่สั่งเร่งพูดเพื่อยัดบททั้งหมด ไม่แบ่งฉากหรือเพิ่มคลิป/เครดิตเอง
- Native audio ใช้ speech direction; API dubbing ส่งเฉพาะ `text` กับ voice mapping เดิมและไม่ให้ provider สร้างเสียงซ้อน; narrator/visual-only คงพฤติกรรมเดิม

### 4. ตัวประกอบพรอมต์กลาง ก่อนแตกตามผู้ให้บริการ

เพิ่ม helper แบบ pure function เช่น `core/video_speaker_binding.py` สร้าง block เดียวจากข้อมูลที่ตรวจแล้ว ให้ Flow/Meta และ helper AI ใช้ข้อมูลเดียวกัน ไม่ฝาก AI เขียนชื่อกับบทใหม่อิสระหลายรอบ

สำหรับสัญญาใหม่ แก้ข้อกำหนด motion ที่ “never personal names” ให้อนุญาต symbolic tags และการจับคู่กับ visible roles เท่าที่จำเป็น โดยยังไม่จำเป็นต้องบรรยาย cast ทั้งเรื่องในทุกฉาก ตัวเขียน motion ส่งเฉพาะท่าทาง/กล้อง ส่วน canonical speaker block เติมครั้งเดียวหลังตรวจผล ห้ามมีบทพูดสองชุดขัดกัน หรือถูกตัดทิ้งด้วยความยาวพรอมต์

ตัวอย่างสมมติ (รูปลักษณ์/ตำแหน่งต้องมาจากภาพจริงของงาน ไม่ hard-code ตัวอย่างนี้):

```text
CHARACTER MAP — labels are instructions, not spoken words:
@พ่อ = father, the man in the blue shirt on the left in this reference image.
@แม่ = mother, the woman on the right in this reference image.

TURN 1:
@พ่อ alone says in Thai, exactly once: "สวัสดีจ้า"
Only @พ่อ performs speaking mouth movements during this line.
@แม่ listens silently with natural non-speaking reactions.
Keep the saved character appearances. No extra speech, overlapping voices,
narrator, spoken character labels, or labels printed in the video.
```

ถัดจากตัวอย่างนี้ถ้ามี turn แม่ ให้ระบุบทแม่แยก ไม่ใช้เพียง “ทั้งสองสนทนากัน” ที่เปิดช่องให้สลับบท

### 5. แยก Meta กับ native Flow references

- Meta: รุ่นแรกส่ง tagged natural-language block พร้อมภาพฉากจริง โดยยังไม่กล่าวอ้าง native @ binding ห้ามกด mentions/บัญชีบุคคลจาก tag โดยเดา
- Flow ทางเดิม: ส่ง block ที่ผูกกับ saved frame โดยไม่แอบเปลี่ยน model, mode หรือ settings ของงาน
- Flow native character references เป็นเฟสเสริม: ตรวจตัวเลือกที่เห็นจริงใน account/model ก่อน; ผูก internal character ID กับ exact native asset ที่มีอยู่และตรวจว่าเลือกใน composer จริง ไม่ถือว่าพิมพ์ @name สำเร็จเท่ากับผูก asset แล้ว ชื่อซ้ำเลือกอัตโนมัติไม่ได้
- หากผู้ใช้เลือก native reference แต่ binding ไม่พร้อม ต้องรายงานว่าไม่รองรับ/ยังไม่ผูก ไม่สลับเป็น prompt-only แบบไม่แจ้ง และไม่ย้าย Frames ไป Ingredients หรือสร้าง asset ใหม่เอง
- ตรวจ model/audio support จาก UI จริงก่อนทดสอบ; ไม่เพิ่ม API ใหม่ ไม่เปิดใช้ฟีเจอร์ voice reference ที่จะเปลี่ยนค่า/ค่าใช้จ่ายโดยอัตโนมัติ

## จุดแก้เมื่ออนุมัติให้ลงมือ

| ชั้นงาน | จุดหลัก | สิ่งที่ต้องคงไว้ |
|---|---|---|
| บทและข้อมูลตัวละคร | `core/story_performance.py`, `core/story_manager.py`, Product film adapters | ข้อความเดิม, cast เดิม, ไม่ส่งชื่อเข้าเสียง |
| รับผล AI | `browser_extension/chatgpt.js` validators / request contract | GPT/Gemini ตรวจ schema ตรง backend ก่อนสร้างภาพ; owner/Send เดิม |
| Motion และ audio | `core/media_audio.py`, `core/flow_motion_plan.py`, `core/story_visual_plan.py`, helper ใหม่ | speaker block เดียว, binding เข้า context identity, ไม่แก้ legacy hash |
| ส่งวิดีโอ | `core/meta_video.py`, Flow package/Extension preflight | prompt + ภาพ + scene binding ตรงกัน; capability ของโปรแกรม/Extensionเข้าคู่ |
| แก้ฉาก | `core/meta_redesign.py`, scene revision / Flow helper | binding ตาม revision ของฉาก, ไม่สลับผู้พูดหรือใช้ฉากอื่น |
| เสียงและผลตรวจ | scene voice / native audio / speech audit | คง audio choice; transcript ไม่ใช่หลักฐาน lip-sync/ผู้พูด |

ตรวจจาก cumulative candidate463 ก่อนทำจริง และเลือกเลขรุ่นถัดไปที่ไม่ชนในตอนนั้น ไม่จอง/ขยับรุ่นจากเอกสารนี้ ต้องรักษา461–463และUIใหม่ ไม่ใช้canonical460ทับงานใหม่

## การบันทึกและกู้คืน

- Snapshot registry + per-scene binding + exact turn text + audio mode + source image hash + revision ลงงาน/คิวก่อนส่ง
- Binding digest เข้า context ใหม่/รายการส่ง/ผลรับ ไม่เขียนทับ digest หรือ receipt ของงานที่ส่งแล้ว
- การแก้ภาพต้อง remap visible role ของฉากนั้น; เปลี่ยนเพียงกล้อง/ท่าทางห้ามเปลี่ยนบทหรือผู้พูด
- เส้นทาง creative recovery ที่เดิมอนุญาตแก้เนื้อเรื่อง/บทโดยชัดแจ้ง ต้องบันทึก scene revision ใหม่พร้อมบทและ binding ที่ตรวจครบแบบ atomic ไม่ยึด mapping เก่ากับภาพ/บทใหม่ และไม่ขยายสิทธิ์ recovery ในงานนี้
- งานเก่าไม่มี version ใช้ behavior/bytes เดิม ไม่ migrate ตอนอ่านหรือ Resume ไม่แก้คลิปสำเร็จแล้ว การนำมาใช้กับงานเก่าต้องเป็นคำขอแก้เฉพาะฉากที่ยังไม่ทำและยืนยันว่าไม่มี Send ค้าง
- ไม่ใช้การรอเงียบเป็นเหตุส่งซ้ำ; ผลที่มีอยู่ต้องอ่านก่อนกู้คืน ไม่มี unlimited regeneration เพิ่มขึ้นจากฟีเจอร์แท็ก

## แผนทดสอบและเกณฑ์รับงาน

เริ่ม offline fixtures ก่อน ไม่ใช้คิวลูกค้าเป็นสนามทดสอบ จากนั้นจึงทดสอบติดตั้ง/สร้างจริงแบบจำกัดจำนวนเมื่อได้รับอนุญาต

1. พ่อพูดคนเดียวแต่แม่/ลูกอยู่ในภาพ: ชื่อผูกถูก; มี exact line หนึ่งครั้ง; silent-list ครบ
2. พ่อ → แม่ → พ่อ: turn order ถูก, silent-list สลับถูก, ไม่มีคำสั่ง “แม่เงียบทั้งคลิป”
3. ชื่อไทย/ชื่อคล้าย/alias ซ้ำ/ไม่พบชื่อ/ป้ายอยู่ในข้อความอ้างอิง: normalize เฉพาะ metadata; ไม่เดาเป็น narrator; ไม่อ่าน @ ออกเสียง
4. เสื้อ/ตำแหน่งในภาพเปลี่ยน, ภาพคนละฉาก, helper แก้ภาพ, Resume/retry: binding hash และ revision ตรงเจ้าของงาน ไม่รับ mapping/คลิปเก่า
5. รีวิวปกติ / หนังสั้นสินค้า / Story / Drama / POV นิ้วชี้ / narrator / silent / API: ใช้สัญญาถูกทาง POV ยังคงคนพูดหลังกล้องและไม่สร้างหน้าคน
6. ตรวจข้อความจริงจาก package → composer → trusted Send fixtures ทั้ง Flow และ Meta รวม helper จาก GPT/Gemini ไม่ตรวจแค่ string helper ตัวเดียว; plain @ ไม่ถูกนับเป็น native asset
7. Legacy parity: งานที่ไม่เปิด version ใหม่ได้ prompt/receipt/media/เสียงเหมือนเดิม รวม image N → video N barrier และตัวแก้461–463
8. หลัง runtime นิ่ง: focused → full suiteหนึ่งครั้ง, syntax, paired markersและ package parity ตามมาตรฐานเดิม แยก fixture pass จาก installed E2E

สำหรับสร้างจริง เสนอเริ่มทีละผู้ให้บริการจาก 3กรณี: คนเดียวพูด, สองคนผลัดพูด, POVคนเดียวหลังกล้อง x1output (รวมสูงสุด6คลิปหากตรวจทั้งสอง provider) ไม่มี auto retry ของชุดทดสอบ เก็บการใช้เครดิตตามจริงและขออนุมัติขอบเขตก่อนส่ง ไม่เริ่มทดสอบในรอบวางแผนนี้

ผลตรวจต้องแยกกัน: `prompt_binding_verified` / transcript ตรงบท / การพูดตรงคนจากเสียงและภาพ / lip-sync ไม่เอา “ไฟล์ MP4 มีเสียง” หรือ “ไม่พบคำซ้ำ” มาแทนผลพูดถูกคน การวิเคราะห์ transcript/diarizationอย่างเดียวบอกไม่ได้ว่าหน้าไหนพูด ต้องฟังและดูคลิป หรือพัฒนาตัวตรวจเสียง-ภาพแยกต่างหากที่ยอมตอบ unverified ได้

## ลำดับส่งมอบที่แนะนำ

1. เพิ่ม internal @tag + deterministic per-turn binding และตัดคำกำกับขัดกันเฉพาะสัญญาใหม่ก่อน ครอบคลุม Meta/Flow ทางเดิม ไม่เปลี่ยนการจัดคิว
2. ทดสอบการเก็บ/ส่งข้อมูลครบเส้นทางและเปิดใช้เป็นรุ่นคู่เมื่อปลอดภัย ตรวจคลิปจริงแบบจำกัดก่อนสรุปประสิทธิผล
3. ค่อยเพิ่ม native Flow characters เมื่อยืนยัน UI/account/mode ที่รองรับจริง; ไม่ผูกความสำเร็จของเฟสแรกกับฟีเจอร์ภายนอกที่ยังไม่ได้ทดสอบ

ผลที่คาดหวังคือคำสั่งผู้พูดชัดและไม่หลุดระหว่างขั้นตอนมากขึ้น ไม่ใช่การรับประกันว่าแท็ก @ ควบคุมโมเดลได้100% การเปลี่ยนเป็นตัดช็อตต่อคนหรือพากย์ภายนอกอาจช่วยคุมเพิ่มเติม แต่เป็นการเปลี่ยน workflow/ต้นทุนและต้องแยกอนุมัติ ไม่ทำแทรกในฟีเจอร์นี้
