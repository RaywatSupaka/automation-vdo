"""Build a three-shot demo Product Job from an existing reviewed Job and three images."""

import argparse
import base64
import json
from pathlib import Path

from core.product_manager import ProductManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--target-job", default="")
    parser.add_argument("images", nargs=3, type=Path)
    args = parser.parse_args()

    manager = ProductManager(args.root)
    source_folder = manager.root / args.source_job
    source_job = json.loads((source_folder / "job.json").read_text(encoding="utf-8"))
    if args.target_job:
        job_id = args.target_job
    else:
        fields = (
            "product_id", "shop_id", "product_name", "product_url", "posting_product_url",
            "affiliate_url", "resolved_product_url", "product_source", "link_status", "price",
            "commission", "description",
        )
        job, _ = manager.import_product({key: source_job.get(key, "") for key in fields}, force_new=True)
        job_id = job["id"]
        original = next((source_folder / "original").glob("product_01.*"))
        manager.attach_images(job_id, [original])

    segments = [
        "อยากเก็บบรรยากาศรอบตัวได้ครบ แล้วค่อยกลับมาเลือกมุมที่ชอบภายหลังไหมครับ [pause:0.5] ลองดู โกโปร แม็กซ์ สามร้อยหกสิบ รายการนี้",
        "เหมาะสำหรับสายเที่ยวและสายทำคอนเทนต์ ที่อยากบันทึกภาพรอบทิศทางในอุปกรณ์ขนาดกะทัดรัด [pause:0.5] ช่วยให้วางแผนมุมเล่าเรื่องได้หลากหลายขึ้น",
        "ตอนตรวจรายการ ราคาแสดงหนึ่งหมื่นสามพันเก้าร้อยแปดสิบบาท คะแนนสี่จุดเก้า และขายแล้วสิบเก้าชิ้น [pause:0.5] เป็นสินค้ามือสอง จึงควรตรวจเลนส์ แบตเตอรี่ อุปกรณ์ และประกันกับร้านอีกครั้ง แล้วกดดูรายละเอียดจากลิงก์สินค้าได้เลยครับ",
    ]
    result = {
        "job_id": job_id,
        "caption_short": "เก็บบรรยากาศรอบตัวให้ครบทุกมุมด้วย โกโปร แม็กซ์ สามร้อยหกสิบ มือสองสภาพสวย ก่อนสั่งอย่าลืมตรวจเลนส์ แบตเตอรี่ อุปกรณ์ และเงื่อนไขประกันจากร้าน กดดูรายละเอียดได้จากลิงก์สินค้าครับ",
        "caption_alternatives": ["สายเที่ยวและสายทำคอนเทนต์ ลองดู โกโปร แม็กซ์ สามร้อยหกสิบ รายการนี้ เช็กสภาพสินค้ามือสองให้เรียบร้อยก่อนสั่งซื้อ"],
        "hashtags": ["#GoProMAX", "#กล้อง360", "#กล้องมือสอง", "#สายเที่ยว"],
        "image_prompts": ["ภาพเปิดสินค้าแบบฮีโร่ในสตูดิโอสีน้ำเงิน", "ภาพใกล้เน้นเลนส์และหน้าจอ", "ภาพไลฟ์สไตล์บนโขดหินฉากภูเขา"],
        "video_prompt": "วิดีโอโฆษณาสินค้าแนวตั้งสามช็อต สไตล์ premium consumer technology commercial มี Motion GUI แบบ glassmorphism และ cinematic HUD ฝังอยู่ในฉาก",
        "flow_gui_design": [
            {
                "visual_style": "premium cinematic glassmorphism hero interface",
                "ui_elements": ["volumetric concentric light portals", "floating translucent glass panels", "luminous particles"],
                "animation": "layered parallax, slow orbital drift, soft energy sweep",
                "composition": "GUI floats behind and around the product without covering it",
                "accent_colors": ["#24D8FF", "#8A4DFF"],
            },
            {
                "visual_style": "high-end precision lens analysis HUD",
                "ui_elements": ["radial lens interface", "four rounded tracking brackets", "depth-layered micro data chips without text"],
                "animation": "macro scan, focus lock pulse, elegant depth parallax",
                "composition": "GUI follows the lens area and leaves the product silhouette clear",
                "accent_colors": ["#37E7FF", "#BE5CFF"],
            },
            {
                "visual_style": "aspirational travel technology closing interface",
                "ui_elements": ["soft three-dimensional waypoint halo", "curved luminous ribbon", "translucent depth cards without text"],
                "animation": "cinematic reveal, ribbon sweep, refined closing lockup",
                "composition": "GUI frames the product against the mountain and never becomes a physical accessory",
                "accent_colors": ["#20D5FF", "#A847FF"],
            },
        ],
        "flow_shot_prompts": [
            "Vertical 9:16, ten-second premium consumer-technology commercial. Preserve exactly one black 360 action camera from the reference image: identical silhouette, single visible front lens, front screen, buttons, vents, proportions and matte-black material in every frame. Begin with a clean studio hero shot and a slow cinematic dolly-in. Build sophisticated Motion GUI directly into the scene: large volumetric cyan and violet concentric light portals floating behind the camera, translucent glassmorphism panels drifting at different depth layers, a soft energy sweep passing behind the silhouette, tiny controlled luminous particles and refined cinematic UI parallax. The interface must feel like a high-budget global technology advertisement, three-dimensional, soft, minimal and elegant. GUI stays behind and around the product and never covers it. No flat circles, no hand-drawn outline, no simple arrow, no readable text, no numbers, no price and no fake specifications. Do not add people, hands, tripods, mounts, bases, cables, batteries, accessories, extra lenses, duplicate cameras or physical objects.",
            "Vertical 9:16, ten-second high-end precision product commercial. Preserve exactly one black 360 action camera from the reference image with unchanged body geometry, single visible front lens, front screen and ports. Perform a smooth macro camera move from the lens toward the screen. Integrate an advanced premium Motion GUI into the generated video: a multi-layer radial lens-analysis interface made of translucent glass, four rounded luminous tracking brackets that smoothly lock around the lens, subtle depth-layered data chips with no readable text, elegant focus-lock pulses, refractive cyan-to-violet light and shallow parallax. The interface must look like polished broadcast motion design, not basic lines or a drawn arrow. Keep the product fully visible and sharp. No readable letters, numbers, price, discount or invented specification. Do not add a second lens, second camera, people, hands, stand, mount, base, cable or accessory.",
            "Vertical 9:16, ten-second aspirational travel-technology commercial. Preserve exactly one black 360 action camera resting directly on the rock from the reference image. Use a smooth lateral cinematic reveal with the mountain background at blue hour. Generate professional Motion GUI as part of the scene: a soft three-dimensional cyan waypoint halo positioned behind the product, a curved violet-and-cyan luminous ribbon sweeping through depth without touching the camera, floating translucent glass cards with no readable text, subtle particles and an elegant closing interface lockup. Finish on a clean premium hero frame with layered depth and negative space. The GUI must look like expensive commercial motion graphics, never like simple line art, a flat circle or a basic arrow. No readable text, numbers, price, promotion or fake specification. Do not add people, hands, tripod, mount, base, selfie stick, cable, accessory, duplicate product, extra lens or floating physical object.",
        ],
        "spoken_script_segments": segments,
        "spoken_script": " [pause:0.5] ".join(segment.replace(" [pause:0.5] ", " ") for segment in segments),
        "spoken_script_short": "เก็บภาพรอบตัวได้ครบด้วย โกโปร แม็กซ์ สามร้อยหกสิบ เช็กสภาพสินค้ามือสอง แล้วกดดูรายละเอียดได้เลยครับ",
        "pronunciation_notes": {"GoPro": "โกโปร", "MAX": "แม็กซ์", "360": "สามร้อยหกสิบ"},
        "warnings": [
            "สินค้านี้เป็นของมือสอง ต้องตรวจสภาพตัวจริง เลนส์ แบตเตอรี่ อุปกรณ์ และเงื่อนไขประกันจากร้านก่อนสั่งซื้อ",
            "ราคา คะแนน และยอดขายเป็นข้อมูลที่เห็นตอนตรวจและอาจเปลี่ยนแปลงภายหลัง",
            "รูปทั้งสามเป็นภาพเอไอสำหรับทำคอนเทนต์ ไม่ใช่หลักฐานยืนยันสภาพสินค้าจริง",
        ],
        "generated_images": [base64.b64encode(path.read_bytes()).decode("ascii") for path in args.images],
    }
    saved = manager.apply_ai_result(result)
    print(json.dumps({
        "job_id": job_id,
        "images": saved["generated_images"],
        "shots": len(saved["flow_shot_prompts"]),
        "segments": len(saved["spoken_script_segments"]),
        "tts_issues": saved["tts_script_issues"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
