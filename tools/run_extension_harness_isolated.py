from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="smartflow-extension-") as temp:
        temp_root = Path(temp)
        products = ProductManager(temp_root / "products")
        job, _ = products.import_product(
            {
                "shop_id": "123456",
                "product_id": "987654",
                "product_name": "Extension isolated integration test",
                "product_url": "https://shopee.co.th/test-i.123456.987654",
                "images": [],
            },
            force_new=True,
        )
        source = temp_root / "source.png"
        Image.new("RGB", (48, 48), "white").save(source)
        products.attach_images(job["id"], [source])
        encoded = base64.b64encode(source.read_bytes()).decode("ascii")
        products.apply_ai_result(
            {
                "job_id": job["id"],
                "caption_short": "integration test",
                "hashtags": ["#test"],
                "video_prompt": "Vertical product video integration test",
                "flow_shot_prompts": ["shot one", "shot two", "shot three"],
                "spoken_script": "integration test",
                "spoken_script_segments": ["one", "two", "three"],
                "generated_images": [encoded, encoded, encoded],
                "warnings": [],
            }
        )
        bridge = LocalBridge(
            "127.0.0.1",
            0,
            products,
            logging.getLogger("isolated-extension-harness"),
            desktop_state=lambda: {"products": products.list_jobs()},
        ).start()
        port = int(bridge.server.server_address[1])
        env = dict(os.environ)
        env["SMARTPOST_TEST_BRIDGE"] = f"http://127.0.0.1:{port}"
        try:
            completed = subprocess.run(
                ["node", "tests/extension_bridge_harness.js"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
            )
            result = {
                "ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "bridge": env["SMARTPOST_TEST_BRIDGE"],
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
            }
            report = ROOT / "logs" / "extension_harness_isolated.json"
            report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(result, ensure_ascii=False))
            return completed.returncode
        finally:
            bridge.stop()


if __name__ == "__main__":
    raise SystemExit(main())
