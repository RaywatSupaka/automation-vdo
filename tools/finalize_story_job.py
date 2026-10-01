"""Create Story narration with the saved Catfufu credential and render the final Short."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import ROOT, load_config
from core.external_tts import ExternalTtsClient, ExternalTtsError
from core.external_tts import MAX_TTS_REQUEST_CHARS
from core.chunked_tts import render_chunked_voice
from core.secure_store import WindowsCredentialStore
from core.story_manager import StoryManager
from core.story_finisher import finish_story_media
from core.story_video import StoryVideoComposer
from core.thai_tts import prepare_thai_tts_script


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--reuse-voice", action="store_true")
    args = parser.parse_args()
    config = load_config()
    manager = StoryManager(ROOT)
    job = manager.get(args.job)
    folder = manager.root / args.job
    script, issues = prepare_thai_tts_script(job.get("narration_script") or "")
    if issues:
        raise RuntimeError("บทพากย์ไม่พร้อม: " + " • ".join(issues))
    existing_voice = folder / str(job.get("voice_path") or "") if job.get("voice_path") else None
    if args.reuse_voice and existing_voice and existing_voice.is_file():
        voice = existing_voice
        api_key = ""
    else:
        voice = None
        api_key = WindowsCredentialStore().load()
        if not api_key:
            raise RuntimeError("ยังไม่ได้บันทึก AI Voice API Key")
    reference_id = str(config.get("voice_reference_id") or "").strip()
    reference_file = Path(str(config.get("voice_reference_file") or ""))
    client = ExternalTtsClient(api_key, config.get("voice_api_base_url", "https://www.catfufu.com")) if api_key else None
    if client and not reference_id:
        reference_id = str(client.upload_reference(reference_file)["reference_id"])

    def submit():
        return client.synthesize(script, reference_id, language=str(config.get("voice_language") or "th"), emotion_id=str(config.get("voice_emotion_id") or "normal"), engine="auto", speed=float(config.get("voice_speed") or 0.92), silence_sec=float(config.get("voice_silence_sec") or 0.3))

    if client and len(script) > MAX_TTS_REQUEST_CHARS:
        voice = folder / "audio" / "narration.mp3"
        external_job_id, output_id, reference_id = render_chunked_voice(
            client, script, reference_id, voice, scope=f"story:{args.job}:narration",
            options={"language": str(config.get("voice_language") or "th"), "engine": "auto",
                     "silence_sec": float(config.get("voice_silence_sec", 0.3))},
            ffmpeg_path=config.get("ffmpeg_path"),
            on_progress=lambda message: print(message, flush=True),
            on_checkpoint=lambda remote, ref: manager.save_voice_checkpoint(
                args.job, external_job_id=remote, reference_id=ref, status="queued"),
            legacy_job_id=str(job.get("voice_job_id") or ""), legacy_output_id=str(job.get("voice_output_id") or ""),
        )
        manager.save_voice(args.job, voice, external_job_id, output_id, reference_id)
    elif client:
        try:
            queued = submit()
        except ExternalTtsError as exc:
            if ("HTTP 404" not in str(exc) and "ไม่พบไฟล์เสียงต้นแบบ" not in str(exc)) or not reference_file.is_file():
                raise
            reference_id = str(client.upload_reference(reference_file)["reference_id"])
            queued = submit()
        external_job_id = str(queued["job_id"])
        print(f"VOICE QUEUED {external_job_id}", flush=True)
        _, output_id = client.wait_until_done(external_job_id, on_status=lambda status, result: print(f"VOICE {status}", flush=True))
        voice = folder / "audio" / "narration.mp3"
        client.download(output_id, voice, "mp3")
        manager.save_voice(args.job, voice, external_job_id, output_id, reference_id)
    final = folder / "videos" / "story_short_final.mp4"
    images = [folder / item for item in job["generated_images"]]
    plan = StoryVideoComposer(config.get("ffmpeg_path", "")).compose(images, final, job.get("scene_durations"), voice)
    complete, finish_plan = finish_story_media(ROOT, manager, args.job, final, config)
    plan.update(finish_plan)
    saved = manager.save_video(args.job, complete, plan)
    print(json.dumps({"job_id": args.job, "title": saved.get("video_title"), "description": saved.get("video_description"), "final": str(complete), "voice": str(voice), "plan": plan}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
