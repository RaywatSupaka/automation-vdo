# SmartFlow AI Extension 0.15.241

สถานะ: **Runtime Candidate สำหรับติดตั้งทดสอบ** — automated gate 513/513, Flow snapshot/isolated bridge harness และ source/folder/ZIP parity 36/36 ผ่านแล้ว เหลือทดสอบจริงด้วย Extension ที่ติดตั้งใน Chrome ก่อนเลื่อนเป็นรุ่นแนะนำ

## สัญญา Flow policy ใหม่

- Extension ส่ง `FLOW_POLICY_BLOCKED` ได้เฉพาะการ์ดปัจจุบันที่มีหลักฐาน Policy + ไม่หักเครดิต + ปุ่ม Retry ครบอยู่ในการ์ดเดียวกัน และ fingerprint ใหม่กว่าก่อนส่ง
- เมื่อพบ terminal ดังกล่าวเป็นครั้งแรก Product, Story และ Drama ใช้รูป canonical เดิมสร้าง local-motion segment ของ source slot/ฉากนั้นทันที แล้วเดิน source/scene ถัดไป
- ห้ามส่ง safe Prompt ซ้ำ ห้ามอัปโหลด/แนบรูปเดิมซ้ำ ห้าม reassign slot และห้ามสร้าง Alternate Take จากรูปอื่น
- Event เดิมที่มาถึงซ้ำต้องเป็น idempotent และห้ามก่อ physical action เพิ่ม
- ข้อความเข้าคิว, กำลังสร้าง, ระบบไม่ว่าง, ข้อผิดพลาดชั่วคราว, page excerpt หรือ Policy card เก่าไม่ใช่ terminal evidence ต้องรอหรือกู้ใน Run/โปรเจกต์เดิม

## Provenance ของผลงาน

- Product all-Flow ใช้ `google_flow_composite`; ถ้ามี local motion อย่างน้อยหนึ่ง slot ใช้ `google_flow_hybrid_composite`
- Story/Drama all-Flow ใช้ `google_flow_story_composite`; ถ้ามี local motion อย่างน้อยหนึ่งฉากใช้ `google_flow_story_hybrid_fallback` และเก็บ content-mix ของ Drama แยกจาก acquisition source
- Manifest, render plan และ Library ต้องรายงานจำนวน Flow จริง, local motion, จำนวนรวม/เป้าหมาย และ slot/ฉากที่ fallback ตามจริง ห้ามเรียก local motion ว่าคลิป Flow

## ส่วนที่ต้องคงเดิม

- ธุรกรรม Golden ของ Flow: แนบรูปและ Prompt ให้ตรงกัน → Generate หนึ่งครั้ง → Approve หนึ่งครั้ง → รอ → ดาวน์โหลดผลใหม่
- Queue/busy/transient recovery, owner tab/run/lease, download receipt และ Checkpoint ที่สำเร็จแล้วต้องไม่ถูกย้อนทำซ้ำ
- `0.15.112` ยังเป็น Golden behavior ที่ย้อน Source ได้, `0.15.216` ยังเป็น Modern E2E baseline และ `0.15.231` ยังเป็นหลักฐาน Product all-Flow 3/3; รุ่นเหล่านี้เป็นหลักฐานย้อนหลัง ไม่ใช่ตัวแทนสัญญา policy ของ `0.15.241`

## Release gates ก่อนแพ็ก

1. ทดสอบ immediate policy fallback, duplicate-event idempotency และ Resume ของ Product, Story และ Drama
2. ทดสอบว่า queue/busy/transient/stale policy card ไม่เข้า fallback
3. ทดสอบการประกอบ all-Flow และ hybrid พร้อม source type/Flow-local counts ที่ตรง manifest
4. รัน JavaScript syntax, Flow snapshot harness, isolated bridge harness และ Python unittest ทั้งชุด
5. ตรวจ source/package/ZIP parity, `manifest.json` อยู่ราก ZIP และบันทึก SHA-256
6. ติดตั้งแพ็กใน Chrome แล้วทดสอบจริงทั้ง all-Flow และ policy-hybrid โดยไม่มี upload/submit/approve ซ้ำ

เมื่อ Release gate ผ่านแล้ว โฟลเดอร์ติดตั้งต้องเป็น `deliverables/SmartFlow_AI_Extension_0.15.241` และรุ่นใน Chrome, heartbeat, helper, Local Bridge, tests, package และ `CURRENT_RELEASE.json` ต้องตรงกันทั้งหมด

แพ็ก Candidate ปัจจุบัน: `deliverables/SmartFlow_AI_Extension_0.15.241.zip`  
SHA-256: `A6E4C8A54A200A99D2EDF2A5A28174BEADD91FA4061EFFA08FFB44F936B6941A`
