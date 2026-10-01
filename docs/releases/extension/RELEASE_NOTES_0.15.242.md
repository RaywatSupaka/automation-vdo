# SmartFlow AI Extension 0.15.242

สถานะ: **Runtime Candidate สำหรับติดตั้งทดสอบ** — ออกต่อจาก `0.15.241` เพื่อปิดเส้นทางที่อาจนำรูปซึ่ง Google Flow ปฏิเสธกลับไปส่งซ้ำ และเพิ่มการกู้คืน Hybrid แบบ fail-closed

## พฤติกรรมเมื่อ Google Flow ปฏิเสธเพราะ Policy

- รับเป็น terminal เฉพาะ `FLOW_POLICY_BLOCKED` จากการ์ดปัจจุบันที่พิสูจน์ Policy + ไม่หักเครดิต + ปุ่ม Retry และมี Run/Fingerprint ครบ
- บันทึก Policy Checkpoint ก่อน แล้วสร้าง Local Motion จากรูป canonical เดิมทันที
- ห้ามเปิด Flow, อัปโหลด, แนบ, Generate, Approve หรือ Download สำหรับ source/scene ที่ถูกปิดแล้ว
- เดินไปทำรูปหรือฉากถัดไปตามปกติ คลิปที่ผ่าน Flow ยังใช้วิดีโอจริง ส่วนช่องที่ถูกปฏิเสธใช้ภาพเดิมประกอบในเครื่อง
- เมื่อปิด–เปิดโปรแกรมใหม่จาก `render_pending` จะสร้าง Local Motion ต่อโดยไม่แตะ Flow และไม่เพิ่มประวัติซ้ำ

## Story / Drama และความถูกต้องของผลงาน

- `flow_package()` ปฏิเสธคำสั่งเก่าหลังมี Policy Checkpoint
- Local fallback ต้องมีหลักฐาน Policy ที่ authenticated และ `action=local_motion_fallback`
- คลิป Flow จริงห้ามเขียนทับฉากที่ถูก Policy/fallback ปิดแล้ว
- Drama ใช้โหมดวิดีโอที่ผู้ใช้หรือคิวเลือก ไม่ถูกบังคับกลับเป็น Motion ในเครื่องแบบซ่อนอยู่
- Library แสดงจำนวนเป้าหมายตามจริง เช่น `Flow 1 + Local 1 / 3`
- หลัง Final-only cleanup แล้วผู้ใช้ลบ Final ระบบคืน fallback เป็น `render_pending` โดยคง Policy history เพื่อไม่ส่งรูปเดิมเข้า Flow ซ้ำ

## Release gates

- Python full suite: 518/518
- Flow snapshot harness: ต้องผ่าน
- Isolated Extension bridge harness: ต้องผ่าน
- JavaScript syntax: ต้องผ่าน
- Source/folder/ZIP parity: ต้องตรงทุกไฟล์
- Real installed policy-hybrid smoke: ยังต้องทดสอบก่อนเลื่อนเป็น Golden

แพ็กติดตั้ง: `deliverables/SmartFlow_AI_Extension_0.15.242`  
ZIP: `deliverables/SmartFlow_AI_Extension_0.15.242.zip`

SHA-256: `48D5F749B1C929AF1E3EBD443D79A0E9376A2A646D32C98E3893373884D7D9D5`  
Source/folder/ZIP parity: `36/36` ไฟล์ตรงกันทุกไบต์ และ `manifest.json` อยู่ที่ราก ZIP
