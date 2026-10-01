# SmartFlow AI Extension 0.15.207

วันที่: 2026-09-03

## แก้ไข Google Flow

- แก้การตีความ `asset-item-active` ผิดเป็นรูปที่เลือกแล้ว ทั้งที่ Flow รายงาน `aria-selected="false"`
- คลิกรูปใน Media picker หนึ่งครั้งก่อนกด `เพิ่มไปยังพรอมต์` หรือปุ่มยืนยัน
- รองรับปุ่มยืนยันของ Material UI ที่แสดงเป็นไอคอน/`mat-mdc-button-touch-target`
- ตรวจว่ารูปปรากฏอยู่ใน Composer เดียวกับ Prompt ก่อนกดสร้าง
- คงกฎห้ามอัปโหลดซ้ำ และคง Submission receipt เพื่อไม่ให้กดสร้างซ้ำ

## ความเข้ากันได้

- โปรแกรมและ Local Bridge ต้องใช้ Extension 0.15.207 ตรงกัน
- Service worker: `src/background/service-worker.js`
- Google Flow helper build: `flow-0.15.207-20260903.1`

## ผลตรวจอัตโนมัติ

- JavaScript syntax check: ผ่าน
- Python unittest: 407/407 ผ่าน
- Extension/Bridge isolated harness: ผ่าน
- Flow snapshot harness: ผ่าน
