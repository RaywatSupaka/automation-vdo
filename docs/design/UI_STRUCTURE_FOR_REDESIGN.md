# SmartPost AI — โครงสร้างหน้าจอสำหรับออกแบบ UI ใหม่

> เอกสารประวัติ: เนื้อหานี้อธิบาย Tk UI เดิม ไม่ใช่ Hybrid runtime ปัจจุบัน แผนที่ใช้งานวันที่ 5 กันยายน 2026 อยู่ที่ `UX_UI_STABILITY_PLAN_20260905.md` และ PROGRAM_BLUEPRINT.md หัวข้อ 3

เอกสารนี้อธิบายหน้าจอและพฤติกรรมปัจจุบันของโปรแกรม `SmartPost AI — Shopee Affiliate Studio` เพื่อส่งให้ AI/นักออกแบบวิเคราะห์และเสนอ UI ใหม่ โดยต้องไม่เปลี่ยนลอจิกธุรกิจหรือความปลอดภัยของระบบ

## 1. โครงสร้างหน้าต่างหลัก

- Desktop GUI: Python Tkinter
- ขนาดปกติ: สูงสุดประมาณ `1280 × 820`
- ขนาดต่ำสุด: `1080 × 700`
- ธีม: Dark navy / cyan / purple
- แถบซ้ายกว้าง 248 px พร้อมแถบ cyan แสดงเมนูที่เลือก
- พื้นที่กลางเป็น Page Host เปลี่ยนหน้าตามเมนู
- Footer แสดงไฟสถานะและงานปัจจุบันทางซ้าย และคำอธิบาย `SAFE MODE` ทางขวา
- ด้านล่าง sidebar รวม Local Bridge, Chrome Extension และ `ChatGPT Web • ไม่ใช้ API Key` เป็นการ์ด Connection เดียวกัน
- Design system: dark navy, surface 3 ระดับ, border แบบอ่อน, cyan/blue/purple accents
- ลำดับปุ่มกลาง: `PrimaryLarge` สำหรับงานหลักหนึ่งปุ่ม, `Primary`, `Accent`, `Ghost`, `Quiet`
- Combobox, Treeview และ Progressbar ใช้ธีมมืดเดียวกันทุกหน้า

### เมนู sidebar ปัจจุบัน

1. ภาพรวม
2. สินค้าจาก Affiliate
3. เล่าเรื่อง Shorts
4. คลังวิดีโอ
5. AI Voice / บทพูด
6. AI Subtitle
7. เสียงประกอบ
8. โลโก้วิดีโอ
9. คิววิดีโอ
10. ระบบและ Log

## 2. หน้า “ภาพรวม”

หน้าที่: แสดงสุขภาพระบบและทางลัดเริ่มงาน

- การ์ด Android Device
  - สถานะอุปกรณ์
  - ปุ่มตรวจ Connection
  - ปุ่มเปิดมือถือผ่าน scrcpy
- การ์ดสถิติ 4 ช่อง
  - จำนวนสินค้า
  - AI พร้อม
  - มีวิดีโอ
  - โพสต์สำเร็จ
- Content Pipeline 5 ขั้น
  1. วางลิงก์สินค้า
  2. สร้างคอนเทนต์ผ่าน ChatGPT Web
  3. สร้างวิดีโอผ่าน Google Flow
  4. ส่งเข้ามือถือผ่าน ADB
  5. ตรวจและโพสต์แบบ Safe Dry Run
- Automation
  - Checkbox สร้าง Subtitle ทุกงานอัตโนมัติและจำค่า
- Quick Actions
  - Auto Google Flow
  - เพิ่มลิงก์สินค้า
  - เปิด Shopee Affiliate
  - ติดตั้ง/เปิด Extension
  - เปิดโฟลเดอร์สินค้า

## 3. หน้า “สินค้าจาก Affiliate”

หน้าที่: ศูนย์กลาง Product Job ตั้งแต่นำเข้าลิงก์จนพร้อมส่งมือถือ

- ช่องวางลิงก์สินค้านายหน้า
- ปุ่มวางจาก Clipboard และเพิ่มลิงก์
- Checkbox ใช้ Subtitle ทุกงาน
- ตาราง Product Job
  - Job ID
  - ชื่อสินค้า
  - Product ID
  - ลิงก์
  - สถานะ AI
  - เสียง
  - Subtitle
  - วิดีโอ
  - ความพร้อม
  - สถานะโพสต์
- ปุ่มจัดการ
  - Refresh
  - เปิด Job folder
  - คัดลอกลิงก์
  - ตรวจความพร้อม
  - อนุมัติผล AI
  - แก้ข้อมูลสินค้า
  - เพิ่มวิดีโอ
  - เพิ่มรูปสินค้าจริง
  - สร้างผ่าน ChatGPT Web
  - เปิด Shopee Affiliate
- Automation actions
  - Auto Google Flow
  - Multi Flow ×3
  - AI Voice
  - AI Subtitle
  - ใส่โลโก้
  - เอฟเฟกต์สินค้า

## 4. หน้า “เล่าเรื่อง Shorts”

หน้าที่: สร้างคลิปเรื่องเล่าจากภาพต่อเนื่อง ไม่ใช่ Google Flow

- หัวหน้า `Story Shorts Studio` พร้อม badge `Automation Ready`
- แถบอธิบายงานอัตโนมัติ 4 ขั้น: เขียนบท / สร้างภาพ / สร้างเสียง / ประกอบคลิป
- ช่องหัวข้อที่มี helper บอกเงื่อนไขการกรอก
- ช่องเรื่องเล่า/แนวเรื่องขนาดใหญ่
- รูปหลักแบบไม่บังคับ แสดงชื่อไฟล์ที่เลือก
- จำนวนฉาก 6–15 ค่าเริ่มต้น 10 พร้อม slider และ badge ค่าปัจจุบัน
- ปุ่มหลักเดียว: “สร้าง Story Shorts อัตโนมัติจนเสร็จ”
- เมื่อกด ระบบตรวจข้อมูล/Extension/AI Voice ก่อนส่งให้ ChatGPT Web คิดบท ชื่อ คำอธิบาย Visual Bible และสร้างภาพครบทุกฉาก แล้วทำเสียงและวิดีโอต่อเอง
- Popup Automation โทนเดียวกับโปรแกรม แสดง Job ID, เปอร์เซ็นต์จริง, สถานะปัจจุบัน และ 4 ขั้น: ChatGPT Web / AI Voice / ประกอบฉาก / เก็บรายละเอียด
- เปอร์เซ็นต์อิงจำนวนภาพ สถานะ API และขั้น render ที่เสร็จจริง ไม่เดินตามเวลา
- Popup มีปุ่มยกเลิกที่หยุด Browser workflow, การรอ Voice และ FFmpeg และมีปุ่มเปิดโฟลเดอร์เมื่อสำเร็จ
- การ์ดงานล่าสุด: Story Job selector, สถานะ และประเภทแหล่งภาพ
- การ์ดผลลัพธ์แบบ Live Result แสดงบทและข้อมูลจาก ChatGPT Web
- เปิดโฟลเดอร์เรื่องเล่า
- เปิดผลงานของ Job

## 5. หน้า “คลังวิดีโอ”

หน้าที่: แสดงเฉพาะไฟล์ผลงานหลักที่พร้อมใช้งาน

- รายการ/การ์ดผลงาน Product และ Story
- ข้อมูลชื่อ Job, ชื่อผลงาน, เวลาแก้ไข และขนาดไฟล์
- ปุ่มเปิดดูวิดีโอ
- ปุ่มเปิดโฟลเดอร์
- ปุ่ม Refresh
- ปุ่มลบไฟล์
- การลบย้ายเฉพาะไฟล์ Final ไป Recycle Bin
- ห้ามลบ Job, รูป, บท, Prompt, เสียง หรือไฟล์ต้นทาง
- ไม่แสดง Flow shot และไฟล์ระหว่างเรนเดอร์

## 6. หน้า “AI Voice / บทพูด”

หน้าที่: จัดการบทพูดและ Catfufu Voice API

- Product Job selector
- ช่อง API Key
  - แสดง/ซ่อน
  - บันทึกใน Windows Credential Manager
  - ลบคีย์
  - ห้ามเขียนลง config หรือ Log
- เสียงอ้างอิง 5–30 วินาที
  - เลือกไฟล์
  - อัปโหลดเพื่อรับ reference_id
  - ช่อง reference_id
- ช่องบทพูดจาก ChatGPT Plugin
  - แก้ไขได้
  - ให้ ChatGPT สร้างบท
  - โหลดบทจาก Job
- ตัวเลือกเสียง
  - ภาษา
  - Emotion
  - Engine
  - Speed
  - Silence ท้ายเสียง
  - Output format
- ปุ่มสร้างและดาวน์โหลดเสียง
- ปุ่มเปิดโฟลเดอร์เสียง

## 7. หน้า “AI Subtitle”

หน้าที่: เชื่อมต่อ SmartSub Online, สร้าง SRT และกำหนดรูปแบบข้อความก่อนเรนเดอร์

### ฝั่งซ้าย: การเชื่อมต่อและสร้างคำบรรยาย

- ช่อง Token SOT ใช้ครั้งแรก
- ปุ่มเชื่อมต่อเพื่อรับ SOD และเก็บใน Windows Credential Manager
- แสดง/ซ่อน Token
- ลบรหัสเครื่อง
- Product Job selector
- ภาษา
- จำนวนพยางค์ต่อ cue 1–5 ค่าเริ่มต้น 3
- Checkbox ใช้ Subtitle ทุกงานและจำค่า
- ปุ่มสร้างคำบรรยายจากเสียงของ Job
- ปุ่มเปิดโฟลเดอร์คำบรรยาย

### ฝั่งขวา: รูปแบบข้อความ

- Theme selector
- สุ่มธีมทุกงาน / สุ่มทันที
- Animation selector
- สุ่ม animation
- Font selector
- อัปโหลด TTF/OTF
- Font size 14–72 px
- ช่องไฟสระ–วรรณยุกต์ 0–20% (ค่าเริ่มต้น 14%)
  - ยกเฉพาะ glyph วรรณยุกต์ไทย ไม่ยืดพยัญชนะหรือทั้งบรรทัด
  - ห้ามนำช่องไฟแนวนอนมาใช้แก้สระทับกัน
  - ห้ามแยกสระ/วรรณยุกต์จากพยัญชนะ
- Outline width 0–8 px
- Position preset: บน / กลาง / ล่าง
- Vertical position 5–95% ของเฟรม
- สีข้อความ
- สี highlight
- สีขอบ
- สีพื้นหลัง
- เปิด/ปิดพื้นหลัง
- Background opacity
- ปุ่มบันทึกและสร้างวิดีโอใหม่

### พรีวิว Subtitle

- อัตราส่วนแนวตั้ง 720×1280
- ใช้ FFmpeg/libass renderer ตัวเดียวกับวิดีโอจริง
- ต้องตรงกับ font file, font size, ช่องไฟสระ–วรรณยุกต์, outline, background, theme และ Y position
- แสดงข้อมูล font / size / ช่องไฟสระ–วรรณยุกต์ / Y เหนือพรีวิว
- ไม่มี Tk font scale จำลอง
- Animation แสดงเป็นเฟรมหลังช่วงเปิดประมาณ 0.5 วินาที

## 8. หน้า “เสียงประกอบ”

หน้าที่: ผสมเพลงพื้นหลังและ SFX เน้นข้อความ

- Product Job selector
- เปิดโฟลเดอร์วิดีโอ
- เพลงพื้นหลัง
  - เปิดใช้อัตโนมัติทุกงาน
  - โหมด Auto mix 3 ช่วง / สุ่ม / เลือกไฟล์เดียว
  - เพิ่มเพลงเข้าคลัง
  - Volume
- เสียงเน้นข้อความ
  - เปิดใช้อัตโนมัติ
  - Auto / Random / Manual
  - เพิ่มเสียงเข้าคลัง
  - Volume
  - ระยะห่างขั้นต่ำ
  - จำนวนสูงสุด
- สุ่มตัวเลือกใหม่
- สร้างวิดีโอพร้อมเสียงประกอบ

## 9. หน้า “โลโก้วิดีโอ”

หน้าที่: วางโลโก้และตรวจองค์ประกอบก่อนสร้าง Final

- Product Job selector
- เลือกไฟล์ PNG/JPG/WEBP
- Opacity
- Size percent
- Margin
- Position 9 จุด
  - บนซ้าย / บนกลาง / บนขวา
  - กลางซ้าย / กลาง / กลางขวา
  - ล่างซ้าย / ล่างกลาง / ล่างขวา
- พรีวิวเฟรมจริง
- สร้างวิดีโอใส่โลโก้
- เปิดโฟลเดอร์วิดีโอ
- ห้ามเขียนทับไฟล์ต้นฉบับ

## 10. หน้า “คิววิดีโอ Android”

หน้าที่: เตรียมคิวไฟล์ก่อนส่งเข้ามือถือและโพสต์

- ตารางคิววิดีโอ
- เพิ่มคลิป
- เพิ่มโฟลเดอร์
- Refresh
- Checkbox Dry Run
- Checkbox ยืนยันก่อนโพสต์
- ต้องคง Safe Mode เป็นค่าเริ่มต้น

## 11. หน้า “ระบบและ Log”

หน้าที่: ตรวจเครื่องมือ การเชื่อมต่อ และข้อผิดพลาด

- Console log
- ตรวจ Android connection
- เปิด scrcpy
- เปิด Shopee บนมือถือ
- บันทึก UI hierarchy
- เปิดโฟลเดอร์ Log
- แสดง Local Bridge และ Extension status

## 12. Dialog สำคัญ

- แก้ข้อมูลสินค้า: 580×470
- AI Review: 900×650
  - ตรวจรูป, caption, spoken script และ Flow prompts
  - อนุมัติ AI result ก่อนดำเนิน pipeline ต่อ
- Confirmation ก่อนลบไฟล์หรือทำ action ที่กระทบงาน
- Error/Warning dialog สำหรับ credential, media และ readiness

## 13. สถานะและ Data Flow ที่ UI ใหม่ต้องรักษา

```text
Chrome Extension
→ Local Bridge
→ Product/Story Job
→ ChatGPT Web
→ Google Flow หรือ Story image sequence
→ Voice
→ Subtitle
→ Logo / Effects / Music / SFX
→ Final video library
→ Android queue / Safe post
```

- ทุก background job ส่งสถานะกลับผ่าน event queue ห้ามทำงานหนักบน UI thread
- ต้องแสดงสถานะกำลังทำ/สำเร็จ/ผิดพลาดให้สัมพันธ์กับ Job ที่เลือก
- Auto option ต้องจำค่าได้ข้ามการเปิดโปรแกรม
- API Key, SOT และ SOD ต้องไม่ปรากฏในไฟล์ config, log หรือ UI ที่ไม่ได้กดแสดง
- Product Mode และ Story Mode ต้องแยก provenance ชัดเจน
- ปุ่มที่ยังใช้ไม่ได้ควร disabled พร้อมข้อความว่าขาดอะไร แทนการปล่อยให้กดแล้วค่อย error

## 14. จุดที่ควรให้ AI ออกแบบ UI ใหม่วิเคราะห์

- Sidebar มี 10 รายการระดับเดียวกัน ทำให้ลำดับงานไม่ชัด ควรพิจารณาจัดกลุ่ม `สร้างงาน`, `ตกแต่ง`, `ส่งออก`, `ระบบ`
- หน้า Product มี action จำนวนมาก ควรใช้ workflow stepper และ primary action เพียงหนึ่งปุ่มตามสถานะ Job
- หน้า Subtitle มี controls มาก ควรแยกเป็น section: Typography / Color & Box / Motion / Position / Preview
- ควรมี Inspector panel ด้านขวาที่ใช้ร่วมกันสำหรับ Job, validation และ missing requirements
- ควรมี progress bar และ activity history ต่อ Job แทนข้อความสถานะหลายจุด
- ใช้คำไทยสม่ำเสมอ ลดป้ายภาษาอังกฤษที่ไม่จำเป็น
- รองรับหน้าต่าง 1080×700 โดยใช้ scrollable content ไม่บีบ slider หรือปุ่ม
- ปุ่ม destructive ต้องแยกสี/ตำแหน่งจาก primary action
- Preview ทุกประเภทควรระบุว่าเป็น `พรีวิวจริง` หรือ `ภาพจำลอง`
- UI ใหม่ต้องไม่เปลี่ยน endpoint, Job schema, credential storage, Safe Mode หรือแหล่งกำเนิดสื่อ

## 15. ไฟล์โค้ดที่ AI/Codex ต้องแก้เมื่อทำ UI ใหม่

- `ui/main_window.py`: shell, sidebar, page layout, widgets และ event presentation
- `core/subtitle_renderer.py`: ห้ามเปลี่ยนสูตร typography โดยไม่มี media regression test
- `core/config.py`: เพิ่มเฉพาะ setting ที่ไม่ใช่ความลับและต้องใส่ allowlist
- `core/subtitle_styles.py`: theme defaults
- `PROGRAM_BLUEPRINT.md`: อัปเดตโครงสร้างและ invariant หลัง UI ใหม่

ห้ามแก้ backend business logic เพียงเพื่อให้จัด layout ง่ายขึ้น หากต้องการ ViewModel หรือ component ใหม่ให้เพิ่มชั้น presentation โดยคง method เดิมไว้ก่อน
