"""Owned synthetic FFmpeg smoke; no API, GUI, or user jobs."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.flow_native_audio import compose_native, inspect_clips
from core.cancellable_process import run_cancellable

ffmpeg = sys.argv[1]
with tempfile.TemporaryDirectory(prefix="smartflow-native-smoke-") as directory:
    folder = Path(directory)
    clips = []
    for i in range(3):
        path = folder / f"{i}.mp4"
        command = [ffmpeg, "-n", "-f", "lavfi", "-i", f"color=c={'blue' if i == 0 else 'red'}:s=360x640:r=30:d=1"]
        if i != 1:
            command += ["-f", "lavfi", "-i", f"sine=frequency={440 + i * 220}:duration=1", "-c:a", "aac"]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        result = run_cancellable(command, timeout=30)
        assert result.returncode == 0, result.stderr
        clips.append(path)
    plan = compose_native(clips, folder / "native.mp4", ffmpeg, width=360, height=640, allow_silent=True)
    assert plan["silent_scenes"] == [2] and abs(plan["duration"] - 3) < .15, plan
    assert inspect_clips([plan["output"]], ffmpeg)[0]["has_audio"]
    muted = compose_native(clips, folder / "silent.mp4", ffmpeg, width=360, height=640, keep_audio=False)
    assert not inspect_clips([muted["output"]], ffmpeg)[0]["has_audio"]
    from core.story_finisher import finish_story_media
    from types import SimpleNamespace
    for mode, source in [('none', muted['output']), ('flow_original', plan['output'])]:
        job_folder = folder / ('STORY-' + mode)
        (job_folder / 'captions').mkdir(parents=True)
        (job_folder / 'videos').mkdir()
        job = {'audio_choices': {'mode': mode, 'subtitle': False, 'music': False, 'sfx': False}, 'narration_script': 'HUNTER', 'generated_images': []}
        manager = SimpleNamespace(root=folder, get=lambda job_id: job)
        finished, metadata = finish_story_media(folder, manager, job_folder.name, source, {'ffmpeg_path':ffmpeg})
        assert Path(finished).is_file() and not metadata['subtitle_included']
        assert metadata['voice_included'] == (mode != 'none')
        assert not (job_folder / 'captions' / 'story_subtitle.srt').exists()
    print("PASS: three scenes, native audio + silent middle, original duration, explicit mute. Temporary files removed on exit.")
