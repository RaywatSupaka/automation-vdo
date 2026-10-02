# SmartFlow AI — AI Clip Creator

## สาขา dev — ซอร์สปัจจุบัน 0.15.486

สาขานี้เป็น snapshot ซอร์สโปรแกรมและเอ็กเทนชั่นคู่รุ่น `0.15.486` จากฐานเดิม466 พร้อมตัวแก้ ChatGPT Send/submit เฉพาะจุด. สถานะและข้อจำกัดล่าสุดให้อ่าน `CURRENT_RELEASE.json`, `PROJECT_STATE.md` และ `docs/reports/chatgpt-submit-contract-486-20261001.md`; ข้อความรุ่น399และโฟลว์ด้านล่างเป็นเอกสารย้อนหลัง ไม่ใช่หลักฐานของรุ่นที่เปิดใช้ใน Chrome ตอนนี้.

รีโปเก็บโค้ด, tests, เอกสารพัฒนาและ assets ของโปรแกรม. ไม่เก็บ `config.json`, โทเค็น/คีย์ส่วนตัว, โปรไฟล์ Chrome, งาน/คิว/สื่อของผู้ใช้, เพลง/intro/effect ที่นำเข้า, Python environment, เครื่องมือ Android ที่ดาวน์โหลด, build และตัวติดตั้ง. ไฟล์เหล่านี้ยังอยู่ในเครื่องเดิม; เครื่องใหม่ต้องเตรียม dependency และการตั้งค่าของตัวเอง ไม่คัดลอกบัญชีหรือ secret ผ่าน Git.

เมื่อ source checkout ใหม่ยังไม่มี `config.json` โปรแกรมใช้ค่าเริ่มต้นที่ไม่ใช่ความลับจาก `core/customer_runtime.py` ได้ทันที และสร้าง `config.json` ในเครื่องนั้นเมื่อบันทึกการตั้งค่าครั้งแรก โดยไม่เขียนทับไฟล์เดิมหรือไฟล์ที่อ่านเสียหาย เครื่องใหม่ยังต้องติดตั้ง dependency และเครื่องมือ Android ที่ต้องใช้แยกต่างหาก.

สำหรับพัฒนา ใช้ Python3.11 กับ `requirements.txt`; `RUN.bat` ใช้ตัว resolver เดียวกับ launcher. การบิลด์ EXE ใช้ `launcher/SmartFlowLauncher.cs` และไอคอน `assets/smartflow_icon.ico`; การแพ็กเอ็กเทนชั่นใช้ `tools/package_current_extension.py`. ต้องตรวจรุ่นโปรแกรม/เอ็กเทนชั่นคู่กันก่อนเปิดใช้. ผลทดสอบบนเครื่องพัฒนาไม่ใช่คำรับรอง clean-machine/installed-provider E2E.

สถานะรุ่นล่าสุดให้ดู `CURRENT_RELEASE.json` และ `PROJECT_STATE.md` ก่อนเสมอ ซอร์สสาขา `dev` ปัจจุบันเป็นคู่รุ่น `0.15.496`; การเปิดใช้ Extension รุ่นนี้ใน Chrome ยืนยันแล้ว แต่ผลจากผู้ให้บริการจริงสำหรับตัวตรวจรูปอ้างอิงรุ่นนี้ยังไม่ได้ยืนยัน การทดสอบซอร์สไม่เท่ากับการส่งมอบรุ่นติดตั้ง

### ผู้บรรยายในคลิปสินค้าและ Story Shorts

สร้างตัวละครให้พร้อม 3 คลิป → เปิด **ตั้งค่าผู้บรรยาย** เลือกคน ตำแหน่ง ขนาดและช่วงแสดง แล้วกด **บันทึกการตั้งค่า** → ในหน้าสินค้า/Story ติ๊ก **ใส่ตัวละครผู้บรรยาย** ใช้คลิปเดิมและเสียงพากย์เดิม ไม่สร้างซ้ำและไม่ซิงก์ปาก ค่าที่เปลี่ยนมีผลกับงานใหม่เท่านั้น งานคิว/ทำต่อใช้ค่าที่เก็บไว้กับงาน

หน้าตั้งค่า/ป๊อปอัพผู้บรรยายและตัวเลือกในคิวจากรอบก่อนยังคงอยู่ โปรแกรมและ Extension ต้องตรงกับรุ่น Runtime ที่ระบุใน `CURRENT_RELEASE.json` เสมอ

โปรแกรม Windows สำหรับสร้างคลิปสินค้า Shopee Affiliate, Story Shorts และละครสั้นหลาย EP โดยใช้ ChatGPT Web หรือ Gemini Web สร้างข้อมูล/ภาพ และใช้ Google Flow สร้างวิดีโอจริงผ่าน SmartFlow Chrome Extension

## เปิดโปรแกรม

- ผู้ใช้ทั่วไป: `SmartFlow AI.exe`
- นักพัฒนา: `RUN.bat`
- นักพัฒนาที่ต้องการทดสอบ UI โดยยังไม่มี Token: `RUN_DEV.bat` เปิดการข้ามตรวจสมาชิกเฉพาะ source checkout ที่มี `.git` และ `.venv` เท่านั้น ต้องเลือกใช้ไฟล์นี้เอง; `RUN.bat` และ EXE ปกติยังตรวจ Token
- ทั้งสองทางต้องเปิด Hybrid UI เดียวกัน ไม่มี Legacy UI fallback
- ทั้งสองทางใช้ `launcher/resolve_python.ps1` หา Python แหล่งเดียวกัน เพื่อไม่ให้ EXE กับ RUN เปิดคนละ Runtime

## Extension ที่ต้องติดตั้ง

ตรวจรุ่นที่อนุมัติให้ติดตั้งจาก `CURRENT_RELEASE.json` ก่อนทุกครั้ง และเทียบกับรุ่นที่โปรแกรมต้องการกับรุ่นที่ Chrome เชื่อมต่อจริง

โฟลเดอร์ซอร์สสำหรับพัฒนาคือ `browser_extension` ส่วนแพ็กเกจใน `deliverables/` เป็นผลลัพธ์ออกรุ่นที่ไม่แก้ทับหลังสร้าง โฟลเดอร์ที่ Chrome ติดตั้งอยู่แล้วต้องตรวจ path จริงก่อนอัปเดต

เมื่อติดตั้งใหม่ ให้เปิด `chrome://extensions` → เปิด Developer mode → Load unpacked → เลือกโฟลเดอร์ถาวรตามคู่มือ โปรแกรมและ Chrome ต้องแสดงรุ่นเดียวกัน เมื่อต้องอัปเดต ให้ตรวจ path และโปรไฟล์ที่ติดตั้งจริง อัปเดตไฟล์ในโฟลเดอร์เดิม แล้วกด Reload ที่ Extension ตัวเดิมใน Chrome จากนั้นตรวจรุ่นที่เชื่อมต่อกลับมา การอัปเดตต้องรักษา profile/ID/โฟลเดอร์ที่โหลดและข้อมูลคำขอ ห้ามถอนติดตั้งหรือล้าง storage เพื่อแก้บั๊ก

`0.15.112` เป็น Golden สำหรับอ้างอิงพฤติกรรม Google Flow และ `0.15.216` เป็น Modern E2E ที่พิสูจน์แล้ว ทั้งสองไม่ใช่ตัวติดตั้งปัจจุบัน ดูรายละเอียดที่ `PROJECT_STATE.md` และ `CURRENT_RELEASE.json`

## จุดเริ่มอ่านสำหรับพัฒนา

1. `CURRENT_RELEASE.json`
2. `PROJECT_STATE.md`
3. `CODEX_START_HERE.md`
4. เปิดเฉพาะหัวข้อที่เกี่ยวข้องใน `PROGRAM_BLUEPRINT.md`
5. งาน Extension ให้อ่าน `EXTENSION_BLUEPRINT.md` ก่อน Source

Source Extension มีเพียง `browser_extension/` ห้ามแก้จากแพ็กใน `deliverables/`, `archives/` หรือ `backups/`

งานฟีเจอร์ใหม่ให้เริ่มบน branch `codex/<ชื่อฟีเจอร์>` จาก `dev` เมื่อ working tree ว่าง; งานที่เริ่มอยู่แล้วให้ทำต่อบน branch เดิม กติกาปัจจุบันอยู่ใน `AGENTS.md` และคำสั่งทดสอบเฉพาะฟีเจอร์อยู่ใน `docs/TESTING.md` เช่น `.venv\Scripts\python.exe tools\run_focused_tests.py --feature extension-update` CI เลือกชุดทดสอบจากไฟล์ที่เปลี่ยน และแจ้งเมื่อฟีเจอร์ใหม่ยังไม่มี mapping

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
