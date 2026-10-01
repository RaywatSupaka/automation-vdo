"""Run the saved Catfufu VoiceClone settings for one Product Job."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config, save_voice_settings
from core.external_tts import ExternalTtsClient, ExternalTtsError
from core.chunked_tts import render_chunked_voice
from core.external_tts import MAX_TTS_REQUEST_CHARS
from core.product_manager import ProductManager
from core.secure_store import WindowsCredentialStore
from core.thai_tts import prepare_thai_tts_script


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--subtitle", action="store_true")
    args = parser.parse_args()

    config = load_config()
    manager = ProductManager(args.root)
    job_path = manager.root / args.job / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    script, issues = prepare_thai_tts_script(job.get("spoken_script") or "")
    if issues:
        raise ExternalTtsError("บทพูดยังไม่พร้อม: " + " • ".join(issues))
    api_key = WindowsCredentialStore().load()
    if not api_key:
        raise ExternalTtsError("ยังไม่ได้บันทึก API Key ของ AI Voice")

    reference_id = str(config.get("voice_reference_id") or "").strip()
    reference_file = Path(str(config.get("voice_reference_file") or ""))
    client = ExternalTtsClient(api_key, config.get("voice_api_base_url", "https://www.catfufu.com"))

    def upload_reference():
        if not reference_file.is_file():
            raise ExternalTtsError("ไม่พบไฟล์เสียงต้นแบบที่บันทึกไว้")
        return str(client.upload_reference(reference_file)["reference_id"])

    if not reference_id:
        reference_id = upload_reference()

    options = {
        "language": config.get("voice_language", "th"),
        "emotion_id": config.get("voice_emotion_id", "normal"),
        "engine": "auto",
        "speed": float(config.get("voice_speed", 0.92)),
        "silence_sec": float(config.get("voice_silence_sec", 0.3)),
    }
    manager.set_subtitle_requested(args.job, args.subtitle)
    output_format = str(config.get("voice_output_format") or "mp3")
    target = manager.root / args.job / "audio" / f"voiceover.{output_format}"
    if len(script) > MAX_TTS_REQUEST_CHARS:
        external_job_id, output_id, reference_id = render_chunked_voice(
            client, script, reference_id, target, scope=f"product:{args.job}:narration",
            options={key: options[key] for key in ("language", "engine", "silence_sec")},
            ffmpeg_path=config.get("ffmpeg_path"),
            on_progress=lambda message: print(message, flush=True),
            on_checkpoint=lambda remote, ref: manager.mark_voice_queued(args.job, remote, ref),
            repair_reference=lambda _: upload_reference(),
            legacy_job_id=str(job.get("voice_job_id") or ""), legacy_output_id=str(job.get("voice_output_id") or ""),
        )
        final = {"status": "done"}
    else:
        try:
            queued = client.synthesize(script, reference_id, **options)
        except ExternalTtsError as exc:
            if "HTTP 404" not in str(exc) and "ไม่พบไฟล์เสียงต้นแบบ" not in str(exc):
                raise
            reference_id = upload_reference()
            queued = client.synthesize(script, reference_id, **options)
        external_job_id = str(queued["job_id"])
        manager.mark_voice_queued(args.job, external_job_id, reference_id)
        final, output_id = client.wait_until_done(
            external_job_id, poll_interval=5,
            on_status=lambda status, _result: print(f"VOICE {status}", flush=True),
        )
        client.download(output_id, target, output_format)
    saved = manager.save_voice_result(args.job, target, external_job_id, reference_id, output_id)
    save_voice_settings({"voice_reference_id": reference_id})
    print(json.dumps({
        "job_id": args.job,
        "external_job_id": external_job_id,
        "output_id": output_id,
        "voice_path": saved.get("voice_path"),
        "voice_status": saved.get("voice_status"),
        "subtitle_requested": saved.get("subtitle_requested"),
        "api_status": final.get("status"),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
