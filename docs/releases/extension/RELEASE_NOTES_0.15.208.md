# SmartFlow AI Extension 0.15.208

วันที่: 2026-09-03

## แก้ไขจากการทดสอบจริง

- รอบ 0.15.207 ยืนยันว่าอัปโหลดไฟล์และกรอก Prompt สำเร็จ แต่คืนค่า `media:null`
- รองรับ Google Flow Media picker แบบเต็มจอที่ไม่มี `role=dialog`, `role=listbox` และ `aria-controls`
- ใช้หลักฐานร่วมของแถบ `ทั้งหมด`, ค้นหา, อัปโหลด, ปิด และชื่อไฟล์รูป ก่อนอนุญาตให้หาแถวรูป
- คลิกเฉพาะแถวไฟล์ใน Picker แล้วตรวจรูปใน Composer ก่อนกดสร้าง
- คงกฎไม่อัปโหลดรูปซ้ำและไม่กดสร้างซ้ำ

## Version contract

- Extension/Local Bridge: 0.15.208
- Flow helper build: `flow-0.15.208-20260903.1`
