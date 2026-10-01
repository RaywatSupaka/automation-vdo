"""Apply a prepared ChatGPT result and exactly three generated images to a Product Job."""

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.product_manager import ProductManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--generated", type=Path, action="append", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()

    if len(args.generated) != 3:
        raise ValueError("ต้องมีรูปที่สร้างแล้ว 3 รูปพอดี")
    manager = ProductManager(args.root)
    if args.source:
        manager.curate_source_images(args.job, args.source)
    result = json.loads(args.result.read_text(encoding="utf-8"))
    result["job_id"] = args.job
    result["generated_images"] = [
        base64.b64encode(path.read_bytes()).decode("ascii") for path in args.generated
    ]
    saved = manager.apply_ai_result(result)
    if args.approve:
        saved = manager.approve_ai_result(args.job)
    print(json.dumps({
        "job_id": saved["id"],
        "ai_status": saved["ai_status"],
        "ai_review_status": saved["ai_review_status"],
        "source_images": saved["source_images"],
        "generated_images": saved["generated_images"],
        "spoken_segments": len(saved.get("spoken_script_segments") or []),
        "flow_shots": len(saved.get("flow_shot_prompts") or []),
        "tts_issues": saved.get("tts_script_issues") or [],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
