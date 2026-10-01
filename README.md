# SmartFlow AI — AI Clip Creator

## สาขา dev — ซอร์สปัจจุบัน 0.15.486

สาขานี้เป็น snapshot ซอร์สโปรแกรมและเอ็กเทนชั่นคู่รุ่น `0.15.486` จากฐานเดิม466 พร้อมตัวแก้ ChatGPT Send/submit เฉพาะจุด. สถานะและข้อจำกัดล่าสุดให้อ่าน `CURRENT_RELEASE.json`, `PROJECT_STATE.md` และ `docs/reports/chatgpt-submit-contract-486-20261001.md`; ข้อความรุ่น399และโฟลว์ด้านล่างเป็นเอกสารย้อนหลัง ไม่ใช่หลักฐานของรุ่นที่เปิดใช้ใน Chrome ตอนนี้.

รีโปเก็บโค้ด, tests, เอกสารพัฒนาและ assets ของโปรแกรม. ไม่เก็บ `config.json`, โทเค็น/คีย์ส่วนตัว, โปรไฟล์ Chrome, งาน/คิว/สื่อของผู้ใช้, เพลง/intro/effect ที่นำเข้า, Python environment, เครื่องมือ Android ที่ดาวน์โหลด, build และตัวติดตั้ง. ไฟล์เหล่านี้ยังอยู่ในเครื่องเดิม; เครื่องใหม่ต้องเตรียม dependency และการตั้งค่าของตัวเอง ไม่คัดลอกบัญชีหรือ secret ผ่าน Git.

สำหรับพัฒนา ใช้ Python3.11 กับ `requirements.txt`; `RUN.bat` ใช้ตัว resolver เดียวกับ launcher. การบิลด์ EXE ใช้ `launcher/SmartFlowLauncher.cs` และไอคอน `assets/smartflow_icon.ico`; การแพ็กเอ็กเทนชั่นใช้ `tools/package_current_extension.py`. ต้องตรวจรุ่นโปรแกรม/เอ็กเทนชั่นคู่กันก่อนเปิดใช้. ผลทดสอบบนเครื่องพัฒนาไม่ใช่คำรับรอง clean-machine/installed-provider E2E.

รุ่น Runtime ล่าสุด **0.15.399 Candidate**: ตรวจความปลอดภัยการอ่านผลภาพ/วิดีโอและรีเฟรชก่อนเตรียมตัวติดตั้ง **0.3.0-beta.9** ตามคำขอผู้ใช้ ป้องกันรีเฟรชระหว่างสร้างหรือหลังยกเลิกงาน โดยรักษาภาพ คลิป และคำขอเดิม ไม่ส่งสร้างซ้ำ ดู `docs/reports/program-extension-audit-399/README.md` และ `CURRENT_RELEASE.json` สำหรับผลตรวจล่าสุด ขณะเตรียมรุ่นนี้ยังรอ full suite, build, clean-machine และ installed E2E; ไม่ใช่การยืนยันพร้อมแจกจาก fixture เพียงอย่างเดียว

### ผู้บรรยายในคลิปสินค้าและ Story Shorts

สร้างตัวละครให้พร้อม 3 คลิป → เปิด **ตั้งค่าผู้บรรยาย** เลือกคน ตำแหน่ง ขนาดและช่วงแสดง แล้วกด **บันทึกการตั้งค่า** → ในหน้าสินค้า/Story ติ๊ก **ใส่ตัวละครผู้บรรยาย** ใช้คลิปเดิมและเสียงพากย์เดิม ไม่สร้างซ้ำและไม่ซิงก์ปาก ค่าที่เปลี่ยนมีผลกับงานใหม่เท่านั้น งานคิว/ทำต่อใช้ค่าที่เก็บไว้กับงาน

หน้าตั้งค่า/ป๊อปอัพผู้บรรยายและตัวเลือกในคิวจากรอบก่อนยังคงอยู่ โปรแกรมและ Extension ต้องตรงกับรุ่น Runtime ที่ระบุใน `CURRENT_RELEASE.json` เสมอ

โปรแกรม Windows สำหรับสร้างคลิปสินค้า Shopee Affiliate, Story Shorts และละครสั้นหลาย EP โดยใช้ ChatGPT Web หรือ Gemini Web สร้างข้อมูล/ภาพ และใช้ Google Flow สร้างวิดีโอจริงผ่าน SmartFlow Chrome Extension

## เปิดโปรแกรม

- ผู้ใช้ทั่วไป: `SmartFlow AI.exe`
- นักพัฒนา: `RUN.bat`
- ทั้งสองทางต้องเปิด Hybrid UI เดียวกัน ไม่มี Legacy UI fallback
- ทั้งสองทางใช้ `launcher/resolve_python.ps1` หา Python แหล่งเดียวกัน เพื่อไม่ให้ EXE กับ RUN เปิดคนละ Runtime

## Extension ที่ต้องติดตั้ง

Runtime Candidate สำหรับติดตั้งทดสอบคือ `0.15.399` รายละเอียดและสถานะแพ็กเกจอยู่ใน `CURRENT_RELEASE.json` และ `docs/reports/program-extension-audit-399/README.md`

โฟลเดอร์ถาวรสำหรับการติดตั้งใหม่ในเครื่องพัฒนา: `browser_extension` ส่วน `deliverables/SmartFlow_AI_Extension_0.15.399` เป็นแพ็กเกจออกรุ่นที่ไม่แก้ทับหลังสร้าง ไม่ใช่คำสั่งให้ย้าย Extension ที่ติดตั้งอยู่แล้วทุกครั้ง

เมื่อติดตั้งใหม่ ให้เปิด `chrome://extensions` → เปิด Developer mode → Load unpacked → เลือกโฟลเดอร์ถาวรตามคู่มือ โปรแกรมและ Chrome ต้องแสดงรุ่นเดียวกัน การอัปเดตตัวเดิมต้องรักษา profile/ID/โฟลเดอร์ที่โหลดและข้อมูลคำขอ ห้ามถอนติดตั้งหรือล้าง storage เพื่อแก้บั๊ก รีโหลดหรือเปิดโปรแกรมใหม่เฉพาะเมื่อไม่มีงานกำลังทำอยู่

`0.15.112` เป็น Golden สำหรับอ้างอิงพฤติกรรม Google Flow และ `0.15.216` เป็น Modern E2E ที่พิสูจน์แล้ว ทั้งสองไม่ใช่ตัวติดตั้งปัจจุบัน ดูรายละเอียดที่ `PROJECT_STATE.md` และ `CURRENT_RELEASE.json`

## จุดเริ่มอ่านสำหรับพัฒนา

1. `CURRENT_RELEASE.json`
2. `PROJECT_STATE.md`
3. `CODEX_START_HERE.md`
4. เปิดเฉพาะหัวข้อที่เกี่ยวข้องใน `PROGRAM_BLUEPRINT.md`
5. งาน Extension ให้อ่าน `EXTENSION_BLUEPRINT.md` ก่อน Source

Source Extension มีเพียง `browser_extension/` ห้ามแก้จากแพ็กใน `deliverables/`, `archives/` หรือ `backups/`

## โฟลว์หลัก

```text
Product: Shopee → AI Web 3 รูป/บท → Voice → Google Flow ทีละรูป
         → คลิป Flow จริง หรือ local motion เฉพาะ policy-terminal slot
         → รวมตามลำดับ → Subtitle/Logo/Audio → Library

Story: หัวข้อ → AI Web หลายฉาก → Voice → Image motion หรือ Google Flow
       → Subtitle/Logo/Audio → Library

Drama: Series + Character Bible → EP Queue → Story pipeline เดิม → Library
```

ทุกโฟลว์ใช้ Checkpoint และต้องทำต่อเฉพาะส่วนที่ขาด ห้ามย้อนสร้างรูป เสียง หรือวิดีโอที่สำเร็จแล้ว

## ข้อมูลสำคัญ

- `workspace/`, `data/`, `videos/`, `config.json`, `backups/`, `logs/` และ `screenshots/` เป็นข้อมูล Runtime/ผู้ใช้ ห้ามล้างตรง ๆ
- รูปสินค้าใช้ session ChatGPT/Gemini ใน Chrome ไม่ใช้ Codex ImageGen และไม่ใช้ API key แทน
- Product Final เส้นทางปกติต้องมาจากวิดีโอ Google Flow จริง; อนุญาต local motion ได้เฉพาะช่องที่มี structured current-card `FLOW_POLICY_BLOCKED` พร้อมหลักฐานไม่หักเครดิต/Retry เท่านั้น งานผสมต้องระบุ `google_flow_hybrid_composite` และรายงานจำนวน Flow จริงกับ Local Motion แยกกัน ห้ามแอบอ้างภาพสำรองว่าเป็นคลิป Flow
- Meta AI Vibes ถูกถอดออกถาวร
- Output หลักต้องเป็น H.264 High, `yuv420p` และ AAC
- Config, Queue และ Manifest หลักต้องบันทึกผ่าน `core/atomic_json.py`; หากไฟล์หลักเสีย ระบบกู้จาก last-known-good backup และไม่ทำให้งานหายเงียบ ๆ

เอกสารย้อนหลังอยู่ใน `docs/`; อ่านสารบัญที่ `docs/README.md`
