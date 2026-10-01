# แผน SmartFlow — ระบบ → โพสนายหน้า Shopee

## ข้อตกลงล่าสุดและส่วนที่ลงมือแล้ว

ผู้ใช้เลือก **ADB ผ่าน Wi-Fi อย่างเดียว** (คอมต่อ LAN ได้เมื่อเข้าถึงมือถือในเครือข่ายเดียวกัน) ไม่ผสม Phone Link/scrcpy ในโฟลว์โพสต์ ข้อเสนอหลายช่องทางด้านล่างเป็นประวัติการวางแผนก่อนผู้ใช้เลือก ไม่ใช่ขอบเขต implementation ปัจจุบัน

2026-09-19 เพิ่มการจับคู่ในโปรแกรม: ฟอร์มแยกพอร์ตจับคู่/เชื่อมต่อ, รหัส6หลักชั่วคราว, ค้นหา mDNS, เลือกเครื่อง, ตรวจตัวตน, บันทึกเครื่องที่เลือก, สถานะสด และป้องกันเลือกเครื่องแรกแทนเครื่องเดิมที่หายไป ดู `docs/reports/android-wifi-20260919/README.md` การส่งไฟล์/เลือกคลิป/ใส่ปก/Caption/สินค้า/โพสต์และตรวจ receipt ยังเป็นงานระยะถัดไป ไม่ถือว่าจับคู่สำเร็จเท่ากับโพสต์ได้ครบขั้น

---

วันที่ 2026-09-19 • สถานะ: วิเคราะห์ source + ภาพประกอบ + เอกสารทางการเท่านั้น

ยังไม่ได้แก้ source โปรแกรม/Extension/บอทตัวอย่าง ไม่ส่งไฟล์เข้าโทรศัพท์ ไม่เปิดหรือควบคุม Shopee ไม่โพสต์ ไม่เปลี่ยนการเชื่อมต่อ ADB และไม่ใช้เครดิต AI ในรอบวางแผนนี้

## 1. ผลวิเคราะห์และข้อเสนอหลัก

ทำต่อยอดได้ แต่ควรทำเป็น **ตัวควบคุมโพสต์บน Android ใน SmartFlow** ไม่ใช่เพิ่มคำสั่งคลิกใน Chrome Extension และไม่ยกบอทเกมทั้งหมดมาใช้

เส้นทางข้อมูลตามคำขอ: **คลิป Final + ปก + Caption + ลิงก์สินค้าที่ SmartFlow เก็บไว้ → โทรศัพท์ที่ผู้ใช้เลือก → Shopee Video → ตรวจผลโพสต์กลับ SmartFlow** ไม่สร้างภาพ/คลิป/บทใหม่เพื่อโพสต์ และไม่ดึงข้อมูลโทรศัพท์ส่วนอื่นโดยไม่จำเป็น

Phone Link ใช้แสดง/ควบคุมมือถือและเป็นช่องทางส่งไฟล์ได้บนเครื่องที่รองรับ ส่วนช่องทางอัตโนมัติที่แนะนำคือ ADB ผ่าน USB หรือ Wireless debugging ที่ผู้ใช้ยอมรับ โดยยังเปิด Phone Link ดูการทำงานได้ การเชื่อม Phone Link ไม่เท่ากับอนุญาต ADB

เวอร์ชันแรก: หนึ่งโทรศัพท์/หนึ่งบัญชีที่เลือกต่อรอบ ทำทีละคลิป เลือกหลายคลิปจากคลังได้ มีโหมดตรวจอย่างเดียว เตรียมถึงหน้าก่อนโพสต์ และโพสต์ชุดที่อนุมัติ ไม่รวมหลายมือถือขนานหรือการตั้งเวลาแบบเซิร์ฟเวอร์ในระยะแรก

## 2. สิ่งที่ตรวจพบจริง

### SmartFlow ปัจจุบัน

- `core/adb_manager.py`: มีค้นหาอุปกรณ์ อ่านข้อมูลเครื่อง เปิดแพ็กเกจ Shopee จับภาพ และ dump UI hierarchy แต่ยังไม่มี transfer/เลือกคลิป/ใส่ข้อความ/ติดสินค้า/ยืนยันผลโพสต์แบบครบขั้น
- `core/job_manager.py`: คิว CSV เก็บ video_path, caption, product, status, last_step และ post_result; `add()` รับเพียงไฟล์วิดีโอ ยังไม่เชื่อมข้อมูลจากคลังเข้าชุดงานโพสต์ และ `save()` เขียน CSV ตรง ไม่เหมาะเป็นหลักฐานกันส่งซ้ำสำหรับ worker ใหม่
- `ui/main_window.py` เส้นทาง `_check`, `_shopee`, `_dump`, `queue_add_video`, `queue_add_folder`, `queue_safety`: เป็นเครื่องมือเตรียม/ตรวจเครื่องและเพิ่มแถว ยังไม่พบ worker โพสต์ครบแปดขั้นในเส้นทางคิวที่ตรวจ
- `_check()` ถ้าไม่พบ serial เดิมจะเลือกเครื่องแรกในรายการ: ต้องไม่ใช้พฤติกรรมนี้ในงานโพสต์จริง ต้องยึดเครื่องและบัญชีที่ผู้ใช้อนุมัติ
- `web_ui/index.html` มีเมนู “ระบบ → คิวมือถือ Android” อยู่แล้ว ควรพัฒนาหน้านี้เป็น “โพสนายหน้า Shopee” พร้อมรักษาทางเข้าคิวเก่า ไม่ทำสองหน้าที่กดรันงานเดียวกันได้
- `core/video_library.py:item_detail()` ส่ง title, description, hashtags, affiliate_link, cover_path และข้อมูล Final ได้; **affiliate_link ในงาน Story อาจเป็น reference_url ที่ไม่ใช่สินค้าจริง** จึงต้องสร้างตัวดึงข้อมูล Shopee โดยเฉพาะ ไม่เอาทุกลิงก์ในคลังมาแนบสินค้า
- `core/product_story.py` เก็บ posting_product_url/source_url สำหรับเรื่องเล่าสินค้าอยู่แล้ว ใช้เป็นต้นทางร่วมกับข้อมูล Product ที่สัมพันธ์กัน
- `core/facebook_planner.py`: นำแนวคิดเลือกคลิป เก็บแบบร่าง revision lock และกันส่งซ้ำมาใช้ได้ แต่ไม่ยก API/Token/สถานะ scheduled ของ Facebook มาใช้กับ Shopee
- Bridge ปัจจุบันอ่านได้: engine13192, paired Extension0.15.383, ไม่มีงาน Product/Story/Presenter active ณ เวลาตรวจ ไม่ได้ restart หรือ reload

### บอทตัวอย่างที่ผู้ใช้ให้

อ่านจาก `C:/Users/keera/Downloads/cookie_image_bot_full_20260731_173001/cookie_image_bot` เป็น reference เท่านั้น

| ส่วนที่ใช้เป็นต้นแบบได้ | ต้องปรับก่อนใช้จริง |
|---|---|
| `adb_manager.py`: explicit serial, unauthorized/offline, screencap, coordinate mapping | แยกเป็น adapter ของ SmartFlow; ไม่คัดลอกการหา Desktop/phone หรือค่า serial ของโปรเจกต์อื่น |
| `cookie_image_bot.py`: template หลายขนาด, ปฏิเสธภาพว่าง, `revalidate_match_before_action()` | ใช้ภาพสดและหน้าจอ Shopee ที่คาดหมาย ไม่ยึดชื่อหน้าต่างเกมหรือภาพจากทั้ง Desktop |
| `local_vision.py`: อ่าน OCR เฉพาะบริเวณและ cache ตามภาพ | ยังไม่ยืนยันภาษาไทย/อิโมจิ; label repair เดิมมี Play/Confirm/Open all/OK ต้องแยกออก |
| การตรวจภาพก่อนคลิกและตรวจขนาดหน้าต่างเปลี่ยน | รักษาหลักการ แต่เพิ่มการยืนยันหน้าหลังคลิกและตัวตนไฟล์/สินค้าของงาน |
| ระบบ pause/cancel และตรวจ process | บันทึก checkpoint แบบทน crash; ไม่ให้ watchdog เริ่มโพสต์ใหม่หลัง process หาย |

**ไม่ควรนำมาใช้:** randomized click, burst tap, “ภาพยังอยู่ให้กดซ้ำ”, loop เปิด/ย่อยของเกม, reset watchdog budget, fuzzy OCR ที่ยอมรับปุ่มคล้ายกัน รวมถึงการแตะค้างแบบ zero-distance swipe ของเกมโดยไม่ทดสอบ เพราะมีโอกาสเปิดเมนูกดค้างหรือโพสต์ซ้ำใน Shopee

ภาพที่ผู้ใช้ส่งทั้งเก้าภาพช่วยระบุเส้นทางได้ แต่หลายภาพมีวง/กากบาทสีแดงและเป็นภาพตัด ต้องเก็บ screenshot ดิบของหน้าจอจริงเพื่อสร้าง fixture/template ก่อนพัฒนา ไม่ใช้ตำแหน่งหรือรอยวงเป็นหลักฐานปุ่ม

## 3. ขั้น 0 — ส่งวิดีโอและปกจากคอมเข้าโทรศัพท์

### ทางเลือก A: Phone Link ตามที่ผู้ใช้ระบุ

Microsoft ระบุเส้นทางไฟล์ในเครื่อง: คลิกขวาไฟล์ → Share → Phone Link; ดูแจ้งเตือนส่งสำเร็จ และไฟล์รับอยู่ `Downloads > Sent from your PC` ต้องตรวจเวอร์ชัน Windows/Android/Phone Link/Link to Windows ให้รองรับก่อน ส่วนลากวางขึ้นอยู่กับอุปกรณ์และแอปเป้าหมาย ไม่สมมติว่าลากลงหน้าต่าง Shopee ได้ทุกเครื่อง [Microsoft: โอนไฟล์ระหว่างอุปกรณ์](https://support.microsoft.com/en-us/windows/apps/phonelink/seamlessly-transfer-content-between-your-devices)

- ปุ่มใน SmartFlow: “ส่งคลิปและปกเข้าโทรศัพท์” เปิดเส้นทางแชร์ที่รองรับจริง หลังทดสอบบนรุ่นเครื่องนั้น
- ส่งไฟล์วิดีโอจริง ไม่ส่งเพียง URL ไปยังไฟล์บน cloud; URL สินค้าเป็นข้อมูลอีกช่องหนึ่ง
- การลากคลิปลงหน้าจอไม่ใช่การโพสต์ และ notification ส่งเสร็จไม่ยืนยันว่า Gallery ของ Shopee เห็นไฟล์
- ถ้าไม่มีหลักฐานระบุตัวไฟล์บนโทรศัพท์ได้ ให้ผู้ใช้ยืนยันไฟล์ในขั้นเตรียม ห้ามประกาศเป็นเส้นทางอัตโนมัติเต็มรูปแบบ

### ทางเลือก B: ADB สำหรับรันอัตโนมัติ — แนะนำถ้าผู้ใช้สะดวก

ADB รองรับ push/pull และต้องอนุญาต USB debugging หรือจับคู่ Wireless debugging แยกจาก Phone Link [Android: ADB](https://developer.android.com/tools/adb)

1. เลือกอุปกรณ์อย่างชัดเจน ตรวจ online/สิทธิ์/พื้นที่ว่างและบัญชี Shopee
2. ตรวจ Final อ่านได้ ระยะเวลา/codec/เสียง/ขนาดไฟล์ตามข้อกำหนด UI ที่พบ ไม่ re-encode หรือเปลี่ยนเสียงอัตโนมัติ
3. สร้าง snapshot: job/item id, SHA256, ขนาด, duration, caption, ปก revision/hash และรายการ URL สินค้าที่เลือก
4. ส่งทีละงานไปอัลบั้มเฉพาะ เช่น `Movies/SmartFlow/<post_id>/` และปก `Pictures/SmartFlow/<post_id>/` ใช้ชื่อ ASCII ที่ไม่ซ้ำ ไม่ปนกับ Gallery ส่วนตัว
5. ใช้ไฟล์ staging ที่ไม่ถูกมองเป็นคลิปสมบูรณ์ระหว่างส่ง ตรวจ bytes/hash ฝั่งเครื่องปลายทางถ้ารองรับ หรือวิธีอ่านกลับเฉพาะไฟล์นั้น ก่อนย้ายเป็นชื่อพร้อมใช้ ไม่อ่าน/ลบโฟลเดอร์ส่วนตัว
6. ตรวจว่า MediaStore ลงรายการแล้ว **ไฟล์อยู่บนดิสก์กับปรากฏใน Gallery เป็นคนละ checkpoint** เส้นทาง scan/publish ต้องทดสอบกับ Android รุ่นจริง; ถ้าต้องมี companion ใช้ MediaStore/MediaScannerConnection พร้อม callback ไม่ถือว่า shell broadcast สำเร็จแปลว่า Gallery พร้อม [Android: Shared media](https://developer.android.com/training/data-storage/shared/media), [MediaScannerConnection](https://developer.android.com/reference/android/media/MediaScannerConnection)
7. อ่านชื่อ/URI/ขนาด/ระยะเวลา และตรวจ thumbnail/preview ในตัวเลือกไฟล์ของ Shopee ว่าตรงงาน ถ้าเลือกอัลบั้มไม่ได้หรือเห็นแต่ thumbnail ที่แยกไม่ออก ให้ช่วยเลือกครั้งแรก ไม่กดรายการแรกแบบเดา

ไม่ติดตั้ง companion/คีย์บอร์ด/driver หรือเปิด debugging แทนผู้ใช้โดยเงียบ หากจำเป็นต้องเพิ่มให้แสดงเหตุผลและให้ผู้ใช้อนุญาตก่อน ระยะแรกทดลอง ADB และเครื่องมือที่มีอยู่ก่อนเพิ่ม APK

## 4. ขั้นตอน Shopee และหลักฐานที่ต้องผ่าน

UI hierarchy ของ Android ไม่ใช่ DOM ของ Chrome: ใช้ resource-id/text/content-description/bounds ที่อ่านได้จากแอปที่กำลังเปิดเป็นหลัก แล้วใช้ OCR/ภาพเฉพาะจุดเมื่อปุ่มเป็น custom view ทั้งหมดต้องสำรวจจากเครื่องจริงก่อนระบุ selector [Android: UI Automator](https://developer.android.com/training/testing/other-components/ui-automator)

| ขั้นของผู้ใช้ | การทำงานและเงื่อนไขผ่าน |
|---|---|
| 1. เปิด Shopee/ปิดโฆษณา | ต้องอยู่แอป/บัญชีที่เลือก; ตรวจ popup overlay แล้วหาปุ่มปิดในกรอบโฆษณา ไม่ผูกกับภาพแคมเปญเดียว และไม่กด X บนแถบ Windows/ปุ่มล้างข้อมูล |
| 2. Live & Video | กด navigation ที่มี label/บริบทตรง ตรวจว่าหน้า Video เปิด ไม่ใช่ Live อย่างเดียว |
| 3. ปุ่ม + | จำกัดขอบเขตที่ toolbar ของหน้า Video; หลังแตะต้องเห็นหน้าเริ่มสร้างวิดีโอ/คลังภาพ |
| 4. คลังภาพ → คลิป → ถัดไป 2 ครั้ง | เลือก Videos/อัลบั้ม SmartFlow; คลิปตรง snapshot, เลือกเพียงหนึ่ง, ปุ่มถัดไป enabled; ตรวจหน้าใหม่ก่อนกดถัดไปครั้งที่สอง ไม่ส่ง double-click |
| 5a. Caption | title/description/hashtags แยกจาก product URL; ตั้งข้อความไทย+อิโมจิผ่านวิธี Unicode ที่ทดสอบแล้ว อ่านกลับและตรวจการตัดข้อความ ไม่พึ่ง shell input text แบบพื้นฐานอย่างเดียว |
| 5b. ปก | ต้องสำรวจหน้าปกจริงก่อน: ถ้านำเข้ารูปได้ให้เลือกปก snapshot และตรวจ crop/preview; ถ้าเลือกได้เฉพาะเฟรม ให้ผู้ใช้เลือกโหมดปกจากคลิป ไม่สัญญาว่าอัปโหลด JPEG ได้ และไม่ตัดต่อคลิปเพิ่มเอง |
| 5c–6. เพิ่มสินค้า → ไอคอนลิงก์ → วาง URL → นำเข้า | ตรวจ URL เป็น Shopee ของงานนั้น เก็บ affiliate URL เดิม; short link ต้องยืนยันปลายทางสินค้าที่เกี่ยวข้อง ไม่ตามลิงก์นอกขอบเขต/localhost ตามข้อมูลที่ไม่เชื่อถือ |
| 7. เลือกสินค้า → เพิ่ม | รอผลนำเข้าจริง; ชื่อ/รูป/รหัสสินค้าถ้ามีตรงรายการ; “เลือกทั้งหมด” ได้เฉพาะเมื่อทั้งชุดคือสินค้าที่ตั้งใจแนบ ไม่มีของเก่าหรือแนะนำแทรก มิฉะนั้นเลือกทีละรายการ; ตรวจเพิ่ม(N) และการ์ดสินค้ากลับบนหน้าร่าง |
| 8. โพสต์ | ตรวจบัญชี+คลิป+caption+cover+สินค้าอีกครั้ง; บันทึกหลักฐานก่อนกดอย่างทน crash แล้วกดเพียงครั้งเดียว รอผล/ตรวจผลงานของบัญชีเดิม ไม่ถือว่าปุ่มหายหรือกลับหน้าฟีดคือสำเร็จ |

การโพสต์วิดีโอพร้อมสินค้าไม่รับประกันว่าทุกสินค้ามีสิทธิ์นายหน้าหรือได้ค่าคอมมิชชัน ให้แสดงผลที่ Shopee ยืนยัน ไม่สร้างตัวเลขรายได้หรืออ้างสิทธิ์แทนผู้ใช้ [Shopee: Video](https://help.shopee.co.th/portal/10/article/164132-Shopee-Video-%E0%B8%84%E0%B8%B7%E0%B8%AD%E0%B8%AD%E0%B8%B0%E0%B9%84%E0%B8%A3?previousPage=secondary+category)

## 5. ป้องกันอาการค้างและโพสต์ซ้ำ

สถานะหลัก:

`ร่าง → ตรวจเครื่อง → ส่งไฟล์ → รอคลังภาพ → เลือกคลิป → เตรียมโพสต์ → แนบสินค้า → พร้อมโพสต์ → ส่งแล้วกำลังตรวจ → โพสต์สำเร็จ`

สถานะเสริม: `รอการเชื่อมต่อ`, `รอสิทธิ์`, `รอประมวลผล`, `พักโดยผู้ใช้`, `ต้องตรวจด้วยผู้ใช้`, `ผลการโพสต์ยังไม่ชัดเจน`

- แต่ละขั้นมี precondition/action/postcondition แยก ไม่ใช้ sleep แล้วถือว่าสำเร็จ
- อ่านหน้าจอแบบปรับจังหวะตามงาน: เป้าทดลอง UI0.5–1วินาที, ช่วงรอ upload/ประมวลผล2–5วินาที; OCRเฉพาะเมื่อเนื้อหา ROI เปลี่ยน ตัวเลขนี้เป็นค่าตั้งต้น benchmark ไม่ใช่ timeout รวมของงาน
- ดู progress/bytes/สถานะรายการเฉพาะงาน ไม่เอา feed video, animation โฆษณา หรือ spinner หมุนอย่างเดียวมาเป็นหลักฐานว่าคลิปเดินหน้า
- ถ้าหน้าจอนิ่งนาน ให้จับภาพ/UI tree ใหม่ ตรวจการเชื่อมต่อและสถานะเดิมก่อน ฟื้นฟูเฉพาะจุดที่ยังไม่ส่ง เช่น เปิดอัลบั้มเดิมใหม่ ไม่ใช้ F5 กับแอปมือถือ
- การกลับหน้าเดิม/reopen แอปต้องตรวจ draft และ checkpoint ก่อน ไม่ force-stop/ล้างข้อมูล/ลบทิ้งเพื่อเริ่มใหม่อัตโนมัติ และไม่ให้เกิด loop ไม่มีขอบเขต
- ล็อกต่อ device/account/worker; ถ้ามีหลายมือถือหรือ serial เดิมหาย ห้ามเลือกเครื่องแรกแทน
- ถ้าผู้ใช้สลับบัญชี ย้ายออกจากหน้า หรือแตะหน้าจอจน state เปลี่ยน ให้พักและตรวจใหม่ ไม่แย่งควบคุม
- ก่อน Post บันทึก `post_intent` ผูก account/device/video hash/caption hash/product ids/run id; ดับหรือหลุดช่วงกดแล้วต้องกลับมา `ผลยังไม่ชัดเจน` และตรวจโพสต์เดิมก่อน ห้าม reset แล้วกดใหม่
- ไม่มี idempotency จาก Shopee ที่ยืนยันในแผนนี้ จึงไม่รับประกัน exactly-once บนเซิร์ฟเวอร์ แต่ต้องกัน blind resubmit ในเครื่อง
- แยก `อัปโหลดเสร็จ`, `รอประมวลผล/ตรวจสอบแพลตฟอร์ม`, `เผยแพร่แล้ว` และ `ถูกปฏิเสธ`; ถ้าไม่มีหลักฐานพอให้ผู้ใช้ตรวจ ไม่แจ้งสำเร็จปลอม
- Post สำเร็จเก็บ post id/URL ถ้า UI เปิดให้ พร้อมวันเวลาและหลักฐานเฉพาะงาน ตรวจผลพร้อมกันหลายจุด; ไม่ใช้ชื่อคลิปหรือ toast อย่างเดียว
- CAPTCHA/OTP/login/สิทธิ์อุปกรณ์/ข้อจำกัดแพลตฟอร์มให้ผู้ใช้ดำเนินการ ไม่หลบหรือแก้ระบบตรวจจับ
- ปุ่มหยุดหยุด action ถัดไปทันที; ถ้ากด Post ไปแล้วบอกว่าอาจส่งสำเร็จแล้วและตรวจผลต่อได้ ไม่สั่งลบโพสต์อัตโนมัติ

## 6. UX/UI ของหน้าใหม่

ปรับเมนูเดิมในหมวด **ระบบ → โพสนายหน้า Shopee**

ส่วนบน: ชื่อมือถือ/บัญชี/ช่องทาง ADB หรือ Phone Link/สถานะพร้อม ปุ่มตรวจเชื่อมต่อและเปิดหน้าจอมือถือ

ส่วนคลิป: “เลือกจากคลัง SmartFlow” เป็นทางหลัก + นำเข้าไฟล์เอง มีภาพปก ชื่อคลิป ระยะเวลา วันที่ และช่องติ๊ก; แสดงเฉพาะ Final ที่พร้อมหรือบอกเหตุผลที่ยังไม่พร้อม ไม่ใช้ไฟล์ intermediate

ส่วนเตรียม: Caption แก้ได้ ปกพรีวิว รายการสินค้า+URLและผลยืนยัน แสดง “ต้องเติมลิงก์สินค้า” หากเป็นคลิปไม่มีข้อมูลสินค้า ห้ามสรุปว่า reference URL ของเรื่องเล่าเป็น affiliate link

ส่วนคิว: รายการที่เลือก ลำดับ ปุ่มเริ่ม/พัก/ทำต่อ/นำออกจากคิว นำออกไม่ลบต้นฉบับหรือโพสต์ที่เคยเผยแพร่ ระหว่างรันล็อก snapshot ไม่ให้การแก้ caption/ปกของอีกหน้ามาเปลี่ยนของที่กำลังโพสต์

โหมด:

1. **ตรวจอย่างเดียว (Dry Run)** — ตรวจไฟล์/แผน/ความพร้อม ไม่มี tap/upload/post
2. **เตรียมถึงหน้าก่อนโพสต์** — ส่งไฟล์ เลือกคลิป เติมข้อมูลและสินค้าจริง หยุดก่อนปุ่มเผยแพร่
3. **โพสต์รายการที่เลือก** — ผู้ใช้ยืนยันบัญชี จำนวนรายการ และข้อมูล snapshot ก่อนเริ่ม; ตัวเลือกยืนยันทุกคลิปเปิดเป็นค่าเริ่มต้น ตาม contract เดิม หรืออนุมัติทั้งชุดอย่างชัดเจนแล้วไม่ถามซ้ำทุกขั้น

สถานะ real-time มาจาก checkpoint ของ worker พร้อมข้อความ “กำลังตรวจอะไร/พบอะไร/รออะไร” ไม่ค้าง99% ทุกกรณี เสร็จแล้วแสดงผลในประวัติและยุบ popup ตามระบบปัจจุบัน ข้อผิดพลาดมีปุ่ม “เปิดดูหน้ามือถือ”, “ตรวจผลเดิม”, “ทำต่อจากจุดนี้” ตามสิทธิ์ของ state

## 7. โครงสร้างโค้ดที่เสนอ

แยกโมดูลใหม่ ไม่เพิ่ม state machine ทั้งหมดใน `ui/main_window.py` หรือคัดลอกไฟล์บอทเกมขนาดใหญ่:

- `core/shopee_posting/package.py`: ดึง Final/cover/caption/product URL จาก item+manifest ตรวจและ freeze snapshot
- `core/shopee_posting/store.py`: AtomicJsonFile, revision, lock/lease, event/checkpoint, post intent, การกู้หลัง restart
- `core/shopee_posting/transport.py`: ADB transfer/verify/MediaStore + interface เส้นทาง Phone Link แยก capability
- `core/shopee_posting/device.py`: explicit serial/account, cancellation, screenshot/UI hierarchy และ single tap
- `core/shopee_posting/recognizer.py`: Shopee screen/selector/OCR/image anchors, Thai support, ROI/fresh-frame/coordinate mapping
- `core/shopee_posting/worker.py`: state machine และ recovery เฉพาะก่อน/หลัง Post
- `ui/shopee_posting.py`: เริ่ม/พัก/ทำต่อ/checkpoint→UI; ไม่ block GUI thread
- `web_ui/shopee_posting.js/.css`: คลิป/ข้อมูลโพสต์/คิว/ประวัติในหน้าใช้งานง่าย
- `workspace/shopee_posting.json`: คิวใหม่แยกจากคิวสร้างคลิปและ Facebook; นำ CSV เก่าเข้าแบบร่างเฉพาะผู้ใช้ยืนยัน ไม่เขียนทับหรือทิ้ง field เก่า

ข้อมูลขั้นต่ำ: post_id, revision, source_item_id, video_path/hash/bytes/duration, cover_path/hash/revision, caption, product_urls/product identities, device/account identity, mode/approval, step/checkpoint, transfer receipt, post intent, observed result, error reason, timestamps และ screenshot/UI excerpt ที่กรองข้อมูลแล้ว

ใช้ `core/adb_manager.py` ผ่าน adapter ที่เพิ่มเฉพาะ capability จำเป็น รักษา behavior ของเครื่องมือเดิมจนมี regression test; คิวใหม่ไม่ใช้ `_check()` ที่ fallback ไป first device

Extension0.15.383 ไม่จำเป็นต้องเปลี่ยนเพื่อควบคุมแอป Android ส่วนที่เกี่ยวกันคือข้อมูลสินค้าที่ capture ไว้และคลิป/ปกที่บันทึกจริง ตรวจสัญญาข้อมูลเดิมและไม่เปลี่ยน ChatGPT/Gemini/Flow/Meta Send/DOM เพื่อฟังก์ชันนี้ หากการทดสอบพบ metadata ขาด ให้แก้ producer แบบมีเวอร์ชันเฉพาะหลังมีหลักฐาน

## 8. การทดสอบและลำดับพัฒนา

### ระยะ 1 — พิสูจน์เส้นทางบนมือถือจริงก่อนสร้าง UI เต็ม

- ยืนยันยี่ห้อ/รุ่น Android, Windows/Phone Link และทางเลือก ADB; สำรวจหน้าที่ขาดจากภาพคือ editor ระหว่างถัดไป/ใส่ปก/พร้อม Post/ผลสำเร็จ
- เรียกดู UI hierarchy และภาพดิบเฉพาะ Shopee; ตรวจว่าปุ่มอ่าน semantic ได้ตรงไหน ไม่อ้างว่ามี source DOM ของแอปทั้งหมด
- ทดสอบส่งคลิปที่ผู้ใช้เลือกหนึ่งไฟล์+ปกไปพื้นที่ของงาน ตรวจ bytes/MediaStore/อัลบั้ม/เลือกไฟล์ถูก
- ทดสอบ Caption ไทย+emoji+บรรทัดใหม่ และแนบสินค้าจาก URL ของงานเดียว ตรวจกลับครบ
- จบที่หน้าก่อน Post; หากไม่มีสิทธิ์นำเข้าปก/อ่าน account/แยกคลิป ให้สรุป capability ที่ไม่ผ่านก่อนพัฒนาส่วนรันต่อ

### ระยะ 2 — Package + durable worker + UI + recovery

- สร้างแบบร่างจากคลัง/ไฟล์เอง พร้อม validation, checkpoint และยึด account/device
- Offline fixtures จากภาพทั้งเก้าขั้นและ raw UI ที่เก็บเพิ่ม; ไม่มี touch หรือ network write ใน dry-run tests
- Negative cases: โฆษณาเปลี่ยน, Xหลายตำแหน่ง, หน้าไม่มี popup, phone window resize/DPI/ขอบดำ, ภาพ stale/ว่าง, XMLว่าง, ไทยOCRผิด, keyboardบังปุ่ม, Videosไม่พบไฟล์, limited media permission, สินค้าเพิ่มเกินหนึ่ง, ลิงก์ผิด/หมดอายุ, สลับบัญชี/มือถือ, diskfull/disconnect
- Crash injection ก่อน/หลัง transfer, กด Next, แนบสินค้า และก่อน/หลัง Post; กรณี Post ไม่ทราบผลต้องไม่กดซ้ำ
- ทดสอบ user pause/cancel/manual intervention, leaseสองโปรแกรม, duplicate action/reconnect, media hash/cover revision เปลี่ยนระหว่างคิว

### ระยะ 3 — ทดสอบโพสต์จริงแบบมีขอบเขต

- หลังผู้ใช้อนุมัติ implementation และการโพสต์จริง: หนึ่งคลิป/หนึ่งบัญชี/สินค้าที่ระบุ ตรวจผลงานจริงใน Shopee และข้อมูลที่บันทึกกลับ SmartFlow
- จากนั้นจึงทดสอบคิวสองคลิป รวมกรณีเครื่องหลุดและทำต่อ โดยไม่ลบ/โพสต์ซ้ำเอง
- ทดสอบ installed SmartFlow EXE จริง แยกจาก fixture/headless; ปิดเฉพาะโปรเซสทดสอบที่เราสร้าง ไม่ปิด Chrome/Phone Link/ADB server ของผู้ใช้
- ผ่าน targeted tests แล้ว full suite และ paired Extension data/controller regressions ก่อนส่งให้ใช้

### ระยะ 4 — เครื่องอื่น/ไฟล์ติดตั้ง

- แพ็ก runtime ของโมดูลภาพ/OCR, รุ่นโมเดลที่รองรับไทย, media tools, driver/prerequisite ตามสิทธิ์แจกจ่าย
- ADB/Phone Link/scrcpy ตรวจหา/ติดตั้งจากทางการอย่างโปร่งใส ไม่อ้างพาธ Desktop/Downloads ของผู้พัฒนา ไม่ copyโปรไฟล์/บัญชี/คุกกี้
- เครื่องใหม่ต้องจับคู่และอนุญาตเอง ทดสอบ update/uninstall ไม่ลบ queue/receipt/media; ไม่ kill ADB server ที่แอปอื่นใช้อยู่

## 9. สิ่งที่ยังต้องยืนยัน ไม่ใช่ข้อสรุปว่าทำได้แล้ว

1. รุ่นมือถือ/Android และยอมใช้ USB/Wireless debugging หรือจำกัด Phone Link เท่านั้น (ส่งคำถามไว้แล้ว ไม่ขวางการวางแผนส่วนอื่น)
2. หน้าใส่ปกบน Shopee รุ่นที่ใช้อยู่รองรับรูปจาก Gallery หรือเฉพาะเฟรมในคลิป
3. UI อ่าน account identity, clip identity, product identities และผลโพสต์ได้ชัดเพียงใด; บางส่วนอาจต้องผู้ใช้ช่วยยืนยัน
4. ข้อจำกัดไฟล์/Caption/จำนวนสินค้า/สิทธิ์ Affiliate ของบัญชีจริง ต้องตรวจตอน preflight ไม่เดาคงที่
5. ไม่มีการรับรองว่าบอทเกมทำงานกับ Shopee อยู่แล้ว ไม่มีการโพสต์จริงหรือทดสอบ installed end-to-end ในรอบนี้

ข้อเสนอเริ่มทำ: **พิสูจน์ส่งไฟล์→เลือกคลิปถูก→Captionไทย→แนบสินค้าถูก→หยุดก่อนโพสต์ ให้ครบหนึ่งงานบนเครื่องจริงก่อน** แล้วจึงเปิดการโพสต์ชุดและการกู้ทำต่อ ไม่เริ่มจาก auto-click loop ยาวที่ไม่มีหลักฐานแต่ละขั้น

## 10. ผลดำเนินการและข้อยุติล่าสุด — 2026-09-19

ส่วนด้านบนเป็นแผนก่อนทดสอบ ข้อสรุปจากผู้ใช้และมือถือจริงดังนี้:

- เลือก **ADB Wi-Fi อย่างเดียว** ไม่ผสม Phone Link/USB/scrcpy; PC LAN ใช้กับมือถือ Wi-Fi ที่เข้าถึงกันได้ ตัว pairing เสร็จแยกจาก workerโพสต์
- Samsung S25 Ultra Android16 อ่าน identity/account/Thai UI ได้ โพสต์คลิป Anata จริงหนึ่งโพสต์ตามอนุญาต ตรวจบัญชี/แคปชัน/สินค้าตรงแล้ว ไม่โพสต์เพิ่ม
- หน้า Shopee นี้จำกัดแคปชัน150 UTF-16 units และไม่รองรับ external Gallery cover ตาม UI ที่พบ ผู้ใช้สั่งล่าสุดให้ตัดปกออก: **ส่งเฉพาะวิดีโอ ไม่เปิด cover picker ใช้ปกอัตโนมัติ Shopee** รักษาปกใน Library/อัลบั้มเก่า ไม่ลบ
- เพิ่มชื่ออัลบั้มสินค้าที่อ่านง่าย + รหัสงาน และ stemเดียวกัน `_video.mp4` ตรวจ hash/MediaStoreและใช้โฟลเดอร์เดิมเมื่อทำต่อ ไม่อัปโหลดซ้ำหากไฟล์ตรง ไม่ส่ง `_cover` สำหรับงานใหม่
- Source UI/worker/checkpoints/duplicate guards implemented ที่ `core/shopee_posting/` และ `web_ui/shopee_posting.*`; คิวจริงใช้ `workspace/shopee_posting/queue.json` แทนพาธเสนอเดิม ไม่แก้ CSV หรือคิวสร้างคลิป
- UI/fixture/EXE-backed read-only smokeผ่าน แต่ยังไม่ใช่ unattended multi-post Desktop E2E; โฆษณาหรือหน้าที่ไม่รู้จักให้พัก ไม่กด X เดา ผล Postไม่ทราบให้ unknownไม่ส่งซ้ำ
- รายงานปัจจุบันและผลทดสอบ: `docs/reports/shopee-posting-20260919/README.md` โปรแกรมผู้ใช้ต้องปิดเปิดตามปกติ ไม่มี Extension update/installerในงานนี้
