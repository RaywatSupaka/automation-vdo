"""Interactive full-pipeline smoke runner. Never posts because Safe Mode remains authoritative."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from core.config import load_config
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", default="")
    parser.add_argument("--job-id", default="", help="Resume an existing Product Job from its checkpoints")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--fresh", action="store_true", help="Create a new Product Job even when the product already exists")
    parser.add_argument("--exit-on-terminal", action="store_true", help="Close the smoke-runner window after success/error")
    args = parser.parse_args()
    if bool(args.link) == bool(args.job_id):
        parser.error("choose exactly one of --link or --job-id")
    if args.fresh and args.job_id:
        parser.error("--fresh cannot be combined with --job-id")

    window = MainWindow(load_config())
    window._show_page("products")
    active_job_id = ""
    terminal_state = {"value": ""}
    attempts = max(1, args.timeout_seconds * 2)

    def select_job(job_id):
        window._refresh()
        for item in window.product_table.get_children():
            values = window.product_table.item(item, "values")
            if values and str(values[0]) == str(job_id):
                window.product_table.selection_set(item)
                window.product_table.focus(item)
                return True
        return False

    def prepare_job():
        nonlocal active_job_id
        if args.job_id:
            window.products.get_job(args.job_id)
            active_job_id = args.job_id
            if not select_job(active_job_id):
                raise RuntimeError("พบ Product Job แต่เลือกในตารางไม่ได้")
            window.product_link.set("")
        elif args.fresh:
            job, _created = window.products.import_link(args.link, force_new=True)
            active_job_id = job["id"]
            if not select_job(active_job_id):
                raise RuntimeError("สร้าง Product Job ใหม่แล้วแต่เลือกในตารางไม่ได้")
            window.product_link.set("")
        else:
            window.product_link.set(args.link)
        print(f"E2E_JOB_ID={active_job_id or 'PENDING_FROM_LINK'}", flush=True)

    def monitor():
        nonlocal active_job_id
        if not active_job_id and str(window._product_pipeline_job_id).startswith("JOB-"):
            active_job_id = str(window._product_pipeline_job_id)
            print(f"E2E_JOB_ID={active_job_id}", flush=True)
        if active_job_id:
            try:
                job = window.products.get_job(active_job_id)
                state = {
                    "automation": job.get("automation_status"),
                    "stage": job.get("automation_stage"),
                    "ai": job.get("ai_status"),
                    "images": len(job.get("generated_images") or job.get("partial_generated_images") or []),
                    "voice": job.get("voice_status"),
                    "flow_clips": int(job.get("flow_clip_count") or 0),
                    "video": job.get("video_status"),
                    "subtitle": job.get("subtitle_status"),
                    "audio": job.get("audio_mix_status"),
                    "error": job.get("automation_error") or "",
                }
                encoded = json.dumps(state, ensure_ascii=False, sort_keys=True)
                if encoded != monitor.last_state:
                    print(f"E2E_STATUS {encoded}", flush=True)
                    monitor.last_state = encoded
                if state["automation"] in {"completed", "error", "cancelled"}:
                    terminal_state["value"] = str(state["automation"])
                    print(f"E2E_TERMINAL {encoded}", flush=True)
                    if args.exit_on_terminal:
                        window.root.after(800, window.root.destroy)
                        return
            except Exception as exc:
                print(f"E2E_MONITOR_ERROR={exc}", flush=True)
        window.root.after(2000, monitor)

    monitor.last_state = ""

    def start_when_extension_ready(remaining=attempts):
        status = window.bridge.extension_status()
        compatible = any(
            str(item.get("version") or "") == window.bridge.REQUIRED_EXTENSION_VERSION
            for item in status.get("clients") or []
        )
        if status.get("connected") and compatible:
            prepare_job()
            window._create_product_and_run()
            window.root.after(1000, monitor)
            return
        if remaining <= 0:
            prepare_job()
            window._create_product_and_run()
            window.root.after(1000, monitor)
            return
        window.status.set(f"กำลังรอ Chrome Extension เชื่อมต่อ • เหลือ {remaining / 2:.1f} วินาที")
        window.root.after(500, lambda: start_when_extension_ready(remaining - 1))

    window.root.after(1000, start_when_extension_ready)
    window.run()
    if terminal_state["value"] in {"error", "cancelled"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
