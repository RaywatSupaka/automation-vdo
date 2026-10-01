# SmartFlow AI Extension 0.15.228

- สืบทอดลอจิกแนบรูป, Generate, Monitor และ Download ของ `0.15.227` โดยไม่เพิ่มการกดหน้า Google Flow
- หลังดาวน์โหลดไฟล์ของช็อตเสร็จจริง เร่งอ่านคิวคำสั่งใหม่ที่ 250/1000/2500 มิลลิวินาที ช่วยเริ่มช็อตถัดไปเร็วขึ้นโดยไม่ส่ง Prompt ซ้ำ
- ตัด DOM click รอบสองของการอนุมัติเครดิต เหลือ trusted click เพียงครั้งเดียว; ถ้าไม่สำเร็จให้หยุดที่ Checkpoint
- Resume ของ Job/SHOT ใช้เฉพาะแท็บที่ลงทะเบียนหรือ URL Checkpoint เดิม ห้ามรับโปรเจกต์อื่นมาแทน
- การปิด Automation ปิดเฉพาะแท็บที่ Extension ลงทะเบียนไว้ ไม่ปิด Shopee, ChatGPT, Gemini หรือ Flow ของผู้ใช้จาก URL อย่างเดียว
- เลื่อนการ์ดวิดีโอผลลัพธ์ล่าสุดเข้าจอก่อน hit-test และกดเปิด ลดกรณีวิดีโอเสร็จแล้วแต่หาเมนูดาวน์โหลดไม่พบ
- สถานะ Overlay แสดงจำนวนช็อตจริง ไม่ hard-code `/3`
- เชื่อม regression file `test_flow_extension_reliability.py` เข้ากับ unittest discovery ทำให้กฎ Extension 21 รายการถูกรันจริง

สถานะ: Candidate รอ Real Google Flow 3-shot smoke ใหม่ ห้ามเรียก Golden จนกว่าจะผ่านงานจริง
