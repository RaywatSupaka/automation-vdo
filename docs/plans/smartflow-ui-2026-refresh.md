# SmartFlow AI — แผนปรับ UX/UI 2026 และต้นแบบตรวจได้

วันที่: 2026-09-20
สถานะล่าสุด: ผู้ใช้อนุมัติและลงมือแก้ source โปรแกรมหลักแล้ว ดู `../reports/ux-2026-implementation/README.md`; installed EXE/WebView2/DPIจริงยังรอตรวจเมื่อเปิดโปรแกรมใหม่ ข้อความการวิเคราะห์/ต้นแบบด้านล่างเป็นหลักฐานก่อนลงมือ

## เป้าหมายและขอบเขต

แก้ป๊อปอัปเบลอไม่เต็มจอ ทำความคืบหน้าให้มีชีวิตแต่ไม่โกหกสถานะ ลดความรกของ Extension ในโปรแกรม ทำไอคอนเมนูเป็นชุดเดียว และแสดงแบรนด์ครบตามไฟล์ต้นฉบับ ไม่เปลี่ยนคิว/การสร้าง/การส่ง Prompt/การจับคู่/สมาชิก/การตัดเครดิต

ใช้ smartflow-operator ตรวจสัญญาปัจจุบันและสถานะแบบอ่านอย่างเดียว พบ engine44652, Story active, Extension required0.15.384 ทั้งก่อนและหลัง จึงไม่รีสตาร์ต/รีโหลดโปรแกรมหรือ Extension ไม่เปิดงานจริง ไม่รบกวนเซิร์ฟเวอร์

## สาเหตุที่ยืนยันจากโค้ด

| จุด | หลักฐาน | แนวแก้ |
| --- | --- | --- |
| เบลอไม่เต็มจอ | `web_ui/styles.css:38` ใส่ blur บน `.modal` ขนาด100vh แต่ `web_ui/usability.css:16` ซึ่งโหลดทีหลังบังคับ `max-height:94dvh`; `::backdrop` โปร่งใส | ให้ native dialog backdrop เป็นเจ้าของฉากหลังเต็ม viewport ส่วนความสูงจำกัดเฉพาะการ์ด/เนื้อหาภายใน |
| จอเล็กเสี่ยงเว้นแถบข้าง | `usability.css:23` ลดความกว้าง `.modal` ไม่ใช่เฉพาะการ์ด | ห้ามผูกพื้นที่ฉากหลังกับขนาดการ์ด |
| เมนูไม่เป็นชุดเดียว | `index.html` ใช้ Unicode ⌂ ▦ ◆ ✦ ◉ ▰ ☷ ฯลฯ และขนาด/พื้นปุ่ม creator ต่างจากปุ่มธรรมดา | SVGชุดเดียว กริด24px strokeคงที่ สีสถานะชัด ไม่พึ่งฟอนต์ตีความสัญลักษณ์ |
| การ์ด Extension รก | ภาพผู้ใช้เป็น `.side-status` แบบแสดงตลอด ไม่ใช่ popupจริงของ Chrome; มีหัวข้อ สถานะ รุ่น/provider และลิงก์ติดตั้งพร้อมกัน | สถานะย่อหนึ่งแถบ; คลิกเปิดรายละเอียดทีละชั้น |
| โลโก้ดูขาด | `ui/main_window.py:9351` ให้ `__brand__` เป็น `assets/smartflow_icon.png` ซึ่งตัวS/แสงชิดกรอบมาก; CSSเดิมเป็นobject-fit:containอยู่แล้ว | ใช้แบรนด์เต็มต้นฉบับในตำแหน่งแบรนด์หลัก ไม่แก้ด้วยการเปลี่ยนcontainเป็นcover; แยกข้อกำหนดไอคอนขนาดเล็ก |
| สไตล์ควบคุมซ้อนหลายชั้น | styles.cssมีfoundationเพิ่มเติมและusability.cssoverride controls/modalภายหลัง | กำหนดเจ้าของmodal/button/icon tokensหนึ่งแห่ง แล้วลดoverrideที่ชนกันอย่างเจาะจง |

ทำซ้ำด้วย CSSจริงในหน้า fixture ที่ไม่โหลด app.js: viewport1890×995 ได้กล่องmodalสูง935.296875px, max-height935.3px, backdropโปร่งใส เหลือประมาณ59.7pxไม่ถูกblur ตรงกับลักษณะภาพผู้ใช้ นี่เป็นข้อผิดพลาดการจัดกรอบ ไม่ใช่เพียงต้องเพิ่มz-index

## ทิศทางภาพ: Midnight Creator Studio

- เก็บอัตลักษณ์ดำ/navy + cyan/blue/violet จากโลโก้ผู้ใช้
- ผิวปุ่ม/การ์ดเรียบชัด ใช้แสงและgradientเฉพาะจุดสำคัญ ไม่ทำทุกปุ่มเรืองแสง
- แบ่งข้อมูล3ชั้น: สิ่งที่กำลังทำ → ความคืบหน้า/ฉาก → ข้อมูลเทคนิคที่กางดูได้
- ปุ่มหลัก1ปุ่มต่อบริบท; secondaryสีสงบ; หยุด/ลบแยกสีและตำแหน่ง ลดคลิกผิด
- Production target: เนื้อหาไทย14–16px, ข้อมูลรอง12–13px, ปุ่ม40–44px, focusชัด, contrastเป้าหมายWCAG AA; ต้องวัดจริงก่อนส่งไม่อ้างจากภาพต้นแบบ
- spacing4/8/12/16/24/32, radiusปุ่ม10–12/การ์ด14–16/modal20–24
- ตัวอย่างใช้Anuphanที่มีอยู่ในโปรเจกต์; ก่อนแพ็กต้องตรวจlicense/asset inventoryตามclean-machine contract

## 1. ระบบป๊อปอัปกลาง — ทำก่อน

1. แยก full viewport backdrop ออกจาก card; ใช้ `dialog.showModal()` และ `dialog::backdrop` ที่เต็มหน้าต่าง ตั้งdim+blurคงที่
2. cardมีmax-heightตามdvhและscrollภายใน ไม่จำกัดbackdropเป็น94dvh/ลดความกว้างบนจอเล็ก
3. ถ้าWebViewไม่รองรับblur ให้ใช้พื้นมืดทึบขึ้นแทน; ไม่ยอมให้หลุดเป็นพื้นที่กดได้
4. ตรวจทุกdialogที่ใช้`.modal` ได้แก่progress/error/detail/batch/update ไม่แก้เฉพาะภาพเดียวแล้วทำส่วนอื่นพัง
5. รักษาfocus trap/คืนfocus/keyboard; Escapeในprogressหมายถึงย่อ ไม่ยกเลิกงาน
6. ย่อแล้วไม่เด้งกลับทุกheartbeat; มีแถบย่อขนาดเล็กหนึ่งอันและเปิดดูได้
7. งานสำเร็จให้ปิดprogressทันทีตามสัญญาปัจจุบัน แล้วtoast/ไฮไลต์ผลงาน ไม่รอแอนิเมชันเพื่อเริ่มคิวถัดไป

ไฟล์ที่คาดว่าจะเปลี่ยนเมื่ออนุมัติ: `web_ui/styles.css`, `usability.css`, `index.html`; ถ้าแยกให้ใช้ `modal.css` เป็นเจ้าของเดียวและจัดลำดับโหลดชัดเจน

## 2. Motion ตามสถานะจริง

| สถานะ | ภาพเคลื่อนไหว/การแสดงผล | สิ่งที่ห้ามทำ |
| --- | --- | --- |
| เขียนบท/วิเคราะห์ | เส้นเขียนปรากฏสั้น ๆ | เพิ่มเปอร์เซ็นต์เองตามเวลา |
| สร้างภาพ | กรอบภาพ + แสงสแกนเบา ๆ | แสดงภาพเก่าว่าเป็นภาพใหม่ |
| สร้างวิดีโอ | เฟรมซ้อนเคลื่อนเบา + active step | เอาชื่อproviderจากฟอร์มใหม่แทนsaved job |
| เสียง | waveformแบบตกแต่ง ไม่ใช่มิเตอร์เสียงจริง | สื่อว่ามีเสียงพร้อมแล้วทั้งที่ยังรอAPI |
| ประกอบคลิป | ชั้นคลิป/วงแหวน + frame progressถ้ามีข้อมูลจริง | ปลอมETA/บอกGPUทำงานโดยไม่ตรวจbackend |
| ต้องให้ผู้ใช้ช่วย | สีอำพันนิ่ง + CTAตามaction_requiredเดิม | เรียกRetry/Sendอัตโนมัติ |
| ขาดการเชื่อมต่อ | สัญญาณช้า + เวลารายงานล่าสุด | เปลี่ยนเป็นสำเร็จ/ล้มเหลวเพราะไม่มีheartbeat |
| พัก/หยุด | ภาพนิ่ง + อธิบายว่าไฟล์อยู่ครบ | แอนิเมชันวิ่งเหมือนยังส่งงาน |
| สำเร็จ | checkครั้งเดียวในtoast/ผลงาน | ค้างmodalบังคิวหรือใช้Extension scene completeเป็นFinal |

เพิ่มerror/review/cancelling variantsเมื่อทำจริง: errorสีroseนิ่ง+สาเหตุสั้นและlogซ่อน; reviewไม่เป็นfailed; cancellingปิดปุ่มซ้ำและรอdesktopยืนยัน ไม่แปลงเป็นpausedทันที

### State adapter

- แยกฟังก์ชันpure `deriveProgressVisualState(current, observation)` จากrenderer
- อ่านjob_id/type/stage/scene_phase/scene_index/scene_total/scenes_complete/active/action_required เดิม
- observationเป็นหลักฐานเสริม ต้องเป็นjobปัจจุบัน ไม่ใช่เจ้าของpercent/Final
- phaseไม่รู้จักใช้ “กำลังทำงาน” แบบneutral ไม่เดาว่าเสร็จจากเปอร์เซ็นต์
- subtitle/native audio/Meta/Flow/cover/Drama/Presenter/Shopeeมีขั้นตอนไม่เหมือนกัน จึงซ่อนขั้นที่ไม่ใช้แทนการแสดงว่าdone
- เปลี่ยนDOMของmotionเฉพาะphaseเปลี่ยน; heartbeatแก้ข้อความ/ค่าที่เปลี่ยนเท่านั้น ไม่resetanimationทุกวินาที
- เส้นทางย่อ/คืน/หยุด/เปิดChrome/ดูผลใช้handlerเดิม ห้ามผูกปุ่มจากต้นแบบเข้าproductionตรง ๆ
- adapterไม่เขียนstate ไม่ล้างreceipt ไม่ส่งPrompt และไม่เพิ่มpolling

ไฟล์ที่คาดว่าจะเปลี่ยน: `app.js::renderProgress`, `automation_status.js`, `presenter_progress.js`, ส่วนsharedvisualของ`shopee_post_progress.js/css` โดยรักษาcontrollerของแต่ละระบบ

### งบการเคลื่อนไหว

- hover/press120–180ms, modalเข้า200–260ms, phasecrossfade180–240ms
- animationใช้SVG/CSSเล็ก ๆ; ไม่ใช้วิดีโอloop/WebGL/particle engineเพิ่ม
- ไม่animateblurทั้งหน้า; หยุดdecorative motionเมื่อwindowซ่อนหรือmodalย่อ
- รองรับprefers-reduced-motionและเพิ่มตัวเลือก “ลดเอฟเฟกต์” ในอนาคต หากจำเป็น
- ไม่อ้างว่าประหยัดCPU/GPUจนกว่าจะวัดก่อน/หลังบนWebView2จริงขณะrender

## 3. Sidebar และไอคอน

ใช้ไอคอนชุดเดียว เช่นLucideSVGที่เก็บในโปรแกรมพร้อมlicense ไม่ดึงจากCDN ไม่ใช้ภาพPNGต่างสไตล์ปนกัน

ข้อเสนอmapping: ภาพรวมHouse, สินค้าShoppingBag, ShortsPanels/Clapperboard, ละครClapperboard, คลิปยาวFilm, คิวListVideo, คลังLibrary/Video, ตัวละครUsers, อินโทรSparkles, กรีนสกรีนLayers, เสียงAudioLines, การตั้งค่าSlidersHorizontal, โพสต์Send, LogTerminal

ต้นแบบใช้SVGวาดเป็นชุดเดียวเพื่อเสนอหน้าตา ไม่ใช่ไฟล์Lucideที่ดาวน์โหลดแล้ว

- ลดcreator cardที่มีgradientถาวร เหลือhighlightเมนูที่เลือก
- แบ่งสร้าง / งานและผลงาน / ตกแต่ง / เผยแพร่ อ่านลำดับง่าย
- กลุ่มที่รวมในภาพต้นแบบเป็นข้อเสนอการจัดเมนู ไม่ใช่อนุญาตลบฟังก์ชัน; ของจริงต้องคงrouteทั้งหมดและแสดงsubmenuเมื่อจำเป็น
- เลื่อนเฉพาะnavigationเมื่อจอสั้น แบรนด์และconnectionยังอยู่ครบ ไม่ตัดโลโก้หรือปุ่ม
- ทดสอบsidebarย่อ/ขยายและfont scalingก่อนปรับขนาดจริง

## 4. Extension panel ในโปรแกรม

- จุดแสดงถาวร: ไฟสถานะ + “Extension เชื่อมต่อแล้ว” + ปุ่มเปิดรายละเอียด
- panelรายละเอียด: สถานะจริง, Chrome, รุ่นจริง/ตรงตามrequiredหรือไม่, งานปัจจุบัน
- ตรวจการเชื่อมต่อเป็นread-only; คู่มือติดตั้งซ่อนไว้ในaccordion
- แยกonline/offline/version mismatch/license required ไม่ทำทุกกรณีเป็นไฟเขียว
- ไม่แสดงAPI Tokenเต็ม, rawproviderชื่อภายใน, heartbeatlogยาวในแถบซ้าย
- ไม่แก้Chrome Extension popup/backgroundในเฟสนี้; หากภายหลังเปลี่ยนsourceExtensionต้องเพิ่มรุ่นและpairตามAGENTS

## 5. โลโก้และปุ่ม

- ใช้`C:/Users/keera/Desktop/LOGO/SmartFlow AI.png` เป็นแหล่งแบรนด์หลัก; ต้นแบบสำเนาแบบbyte-identicalด้วยSHA256 `9BDD74B5C726B8C546C7923850B9B47BC7E0058538A96728B7EECB0C0F549DE5`
- ใช้contain ไม่cover ไม่บีบสัดส่วน ไม่วาดwordmarkทับ/ตัดปลายS
- แยกfull lockupสำหรับพื้นที่กว้างและicon markสำหรับfavicon/พื้นที่เล็ก; ต้องเตรียมicon markที่มีsafe paddingเป็นงานassetแยก หากผู้ใช้เลือกแนวนี้ ห้ามนำโลโก้เต็มย่อลง16pxแล้วอ้างว่าอ่านได้
- ปุ่มPrimary / Secondary / Quiet / Destructive ใช้ชุดเดียวทั่วapp; loading/error/disabledมีlabelไม่ใช้สีอย่างเดียว
- คงprimaryCTAชัดเจน ไม่ย้ายหรือเปลี่ยนความหมายStart/Pause/Cancelโดยไม่ตรวจสัญญาworker

## ลำดับลงมือที่เสนอ

1. P1: แก้backdropเต็มจอ + regressionทุกmodal (บั๊กยืนยันแล้ว ทำก่อน)
2. P2: design tokens/button/icon/brandและconnectionpanel (ไม่แตะautomation)
3. P3: state adapter + motion9สถานะ + exception states + minimized view
4. P4: นำไปใช้ทีละกลุ่มProduct/Shorts/Drama/Presenter/Shopee และตรวจqueue-transition
5. P5: source tests → full suiteเมื่อแก้production → isolatedUI → idle customerEXE/WebView2จริงหลังผู้ใช้พร้อม → ส่งภาพเทียบก่อน/หลัง

การทำงานจริงไม่ต้องเปลี่ยนระบบLogin/อัปเดต/เซิร์ฟเวอร์สำหรับเฟสนี้ ไม่แพ็กinstallerหรือreloadExtensionจากคำขอวางแผนนี้

## Acceptance ที่ต้องผ่านก่อนนำใช้จริง

- Modalทุกชนิดครอบทุกขอบviewportที่1366×768,1440×900,1920×1080,จอย่อ; WindowsDPI100/125/150/200%, resizeขณะเปิด
- ไม่มีhorizontal overflowหรือbottom unblurred strip; inner scrollใช้งานได้; fallbackblur/keyboard/focus/คืนfocusถูก
- รับstateซ้ำ10ครั้งไม่เริ่มanimationใหม่และไม่เพิ่มlistener/DOMซ้ำ
- รับ100%แต่activeยังtrueห้ามประกาศFinal; oldjob100%ห้ามปิดpopupnewjob
- ย่อไม่หยุดworkerและไม่เด้งกลับ; กดหยุดยังใช้cancelcontractและconfirmationเดิม ไม่เกิดdouble action
- Offline/stale/login/credits/review/errorไม่กลายเป็นdead-endเพราะUIซ่อนCTA; providerphaseไม่รู้จักมีfallbackอ่านง่าย
- สำเร็จปิดmodalทันทีและไม่ชะลอคิว; ไม่toastซ้ำทุกpoll
- ลดmotionได้ หยุดเมื่อhidden/minimized; วัดframe/CPUเทียบbaselineพร้อมงานrenderจริงแบบไม่สร้างAIใหม่
- Extension0.15.384 pathคงเดิมและตรวจcompatibilityแบบfocused; installedE2Eรายงานแยกจากfixtures

## สิ่งที่ทำและทดสอบในรอบวางแผนนี้

- เขียนเฉพาะ`docs/plans/smartflow-ui-2026-concept/`และเอกสารแผนนี้ ไม่แก้`web_ui/`, `core/`, `ui/`, `browser_extension/` หรือreleasemetadata
- HTML/CSS/JSต้นแบบแบบoffline ไม่มีfetch ไม่มีaction ไม่มีstorage ไม่มีprovidergeneration
- Chromiumheadlessภาพจริง7ภาพ; ตรวจ14กลุ่มผ่าน รวมnativebackdrop, logo contain, phaseaction, pausedmotion, Escape/minimize/restore, completeclose, collapsedExtensiondetails,390px/1366×768, reducedmotion และไม่มีpageerror
- ทำซ้ำบั๊กด้วยCSSจริงจากstyles/workspace/usabilityโดยไม่โหลดapp.js
- Browserทดสอบปิดในfinally ไม่เปิดserver/testport ไม่ปิดผู้ใช้engine44652
- ยังไม่ได้แก้และทดสอบโปรแกรมจริง/WebView2/DPIทุกค่า จึงไม่ถือว่าproductionfixเสร็จ

## เปิดดูตัวอย่าง

- `smartflow-ui-2026-concept/index.html` เปิดด้วยbrowserเพื่อกด “ดูความคืบหน้า”, “Extension เชื่อมต่อแล้ว” หรือ “ดูแอนิเมชันทุกสถานะ”
- `01-workspace.png`: เมนู/แบรนด์/แถบExtensionและปุ่ม
- `02-progress-video.png`: ป๊อปอัปเต็มviewport
- `03-needs-attention.png`: รอผู้ใช้และCTA
- `04-extension-panel.png`: รายละเอียดExtensionแบบกระชับ
- `05-motion-states.png`: motionboard9สถานะ
- `06-mobile-progress.png`, `07-1366-progress.png`: จอแคบ/จอสั้น
- คำสั่งทำซ้ำ: existingNode + NODE_PATHของCodex bundle → `capture.cjs` ไม่เปิดโปรแกรมจริง

ภาพเป็นต้นแบบข้อมูลจำลอง และภาพหน้าจอไม่สามารถแสดงการเคลื่อนไหวได้ ต้องเปิดHTMLดูanimation

## แหล่งอ้างอิงด้านการออกแบบ/แพลตฟอร์ม

- Native dialog/backdrop/top layer: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog และ https://developer.mozilla.org/docs/Web/CSS/::backdrop
- Reduced motion: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- ชุดไอคอนที่เสนอ: https://lucide.dev/ ; licenseหลักISCและต้องคงnoticeของไอคอนที่นำใช้: https://github.com/lucide-icons/lucide/blob/main/LICENSE

คำว่า “2026” ในแผนหมายถึงแนวออกแบบที่เสนอ ไม่ใช่มาตรฐานUIทางการที่ทุกโปรแกรมต้องทำตาม
