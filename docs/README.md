# SmartFlow AI Documentation

เอกสารในโฟลเดอร์นี้เป็นข้อมูลประกอบย้อนหลัง ไม่ใช่จุดเริ่มอ่านซอร์สหลัก รุ่นติดตั้งและสถานะจริงให้อ่าน `../CURRENT_RELEASE.json` กับ `../PROJECT_STATE.md`

## เริ่มอ่านโปรเจกต์

1. อ่าน `../CURRENT_RELEASE.json` และ `../PROJECT_STATE.md`
2. อ่าน `../CODEX_START_HERE.md` เพื่อดูแผนที่ระบบแบบสั้น
3. เปิดเฉพาะหัวข้อที่เกี่ยวข้องใน `../PROGRAM_BLUEPRINT.md`
4. งาน Chrome Extension ให้อ่าน `../EXTENSION_BLUEPRINT.md`
5. ใช้ `../README.md` สำหรับวิธีเปิดและใช้งานโปรแกรม

## หมวดเอกสาร

- `reports/` — รายงานทดสอบและผลทดลองย้อนหลัง ไม่ใช่สถานะปัจจุบันของโปรแกรม
- `reports/PROJECT_AUDIT_2026-09-04.md` — รายงานวิเคราะห์ทั้งโปรเจกต์ แผนจัดระเบียบ และลำดับแก้ความเสี่ยง
- `releases/extension/` — Release note ย้อนหลัง ใช้เป็นหลักฐาน ไม่ใช่คำสั่งเลือกตัวติดตั้ง
- `history/` — เอกสารเดิมก่อนจัดโครงสร้างหรือข้อมูลที่ถูกแทนที่แล้ว
- `integrations/` — เอกสารการเชื่อมต่อระบบภายนอก รวมผลวิเคราะห์ PD App Companion Extension เพื่อใช้เป็นแนวทางแบบ clean-room
- `design/` — แนวคิดและโครงสร้างหน้าจอสำหรับงานออกแบบ

## ตัวเปิดโปรแกรมที่ใช้งานอยู่

- `../SmartFlow AI.exe` — ตัวเปิดหลักสำหรับผู้ใช้
- `../RUN.bat` — ตัวเปิดสำหรับพัฒนาและซ่อม
- `../CREATE_SMARTFLOW_SHORTCUT.ps1` — สร้าง Shortcut บน Desktop
- `../launcher/SmartFlowLauncher.cs` — ซอร์สของตัวเปิด EXE

ทั้งสี่รายการเป็นส่วนปัจจุบันของโปรเจกต์ ไม่ใช่ไฟล์ Launcher ซ้ำหรือรุ่นเก่า

## ข้อมูลที่ห้ามจัดเป็นขยะซอร์ส

`workspace/`, `data/`, `videos/`, `deliverables/`, `backups/`, `logs/` และ `screenshots/` อาจมี Job, Checkpoint หรือผลงานของผู้ใช้ การล้างต้องผ่านระบบ Smart Storage ของโปรแกรมและกฎในพิมพ์เขียวเท่านั้น
