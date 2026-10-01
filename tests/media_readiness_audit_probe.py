"""Isolated local-media audit; no user jobs, provider calls, or production writes."""
import hashlib
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from core.audio_mixer import AudioMixer
from core.cancellable_process import run_cancellable
from core.green_screen import GreenLibrary, finish_product_green
from core.story_video import StoryVideoComposer
from core.video_composer import MultiFlowComposer
from core.video_intro import inspect_video


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    evidence = {}
    with tempfile.TemporaryDirectory(prefix="smartflow-media-audit-") as temporary:
        root = Path(temporary)
        ffmpeg = str(AudioMixer().ffmpeg)

        def video(name, color="blue", effect=False):
            target = root / name
            command = [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                       f"color=c={'0x00ff00' if effect else color}:s=192x108:r=24:d=1"]
            if effect:
                command += ["-vf", f"drawbox=x=10:y=10:w=40:h=40:color={color}:t=fill"]
            result = run_cancellable(command + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)])
            if result.returncode:
                raise RuntimeError(result.stderr)
            return target

        base = video("base.mp4")
        images = []
        for index, color in enumerate(("red", "green", "blue", "yellow", "cyan")):
            image = root / f"scene-{index}.png"
            Image.new("RGB", (360, 640), color).save(image)
            images.append(image)

        for method in ("compose", "render_scene_motion_clip"):
            output = root / f"previous-{method}.mp4"
            output.write_bytes(base.read_bytes())
            before = digest(output)
            event = threading.Event()

            def cancel_after_encode(command, **kwargs):
                result = run_cancellable(command, **kwargs)
                event.set()
                return result

            error = None
            try:
                composer = StoryVideoComposer()
                with patch("core.story_video.run_cancellable", side_effect=cancel_after_encode):
                    if method == "compose":
                        composer.compose(images, output, durations=[.5] * 5,
                                         width=360, height=640, fps=24, cancel_event=event)
                    else:
                        composer.render_scene_motion_clip(images[0], output, duration=2,
                                                          width=360, height=640, fps=24, cancel_event=event)
            except Exception as exc:
                error = type(exc).__name__
            evidence[method + "_late_cancel"] = {
                "cancel_requested": event.is_set(), "raised": error,
                "previous_output_preserved": digest(output) == before,
            }

        native = root / "native.mp4"
        encoder_crf = []

        def native_encode(command, **kwargs):
            from core.render_backend import run_render
            if "-crf" in command:
                encoder_crf.append(command[command.index("-crf") + 1])
            return run_render(command, **kwargs)

        with patch("core.flow_native_audio.run_cancellable", side_effect=native_encode):
            plan = MultiFlowComposer().compose([base], native, width=360, height=640, fps=24, crf=23,
                                               audio_choices={"mode": "none"})
        evidence["native_render_choices"] = {"requested_fps": 24, "actual_fps": inspect_video(native)["fps"],
                                            "encoder_crf": encoder_crf, "plan_fps": plan.get("fps"), "plan_crf": plan.get("crf")}

        folder = root / "products" / "JOB-AUDIT"
        (folder / "videos").mkdir(parents=True)
        source = folder / "videos" / "base.mp4"
        source.write_bytes(base.read_bytes())
        asset = GreenLibrary(root).import_file(video("effect.mp4", "red", effect=True))["asset"]
        job = {"id": "JOB-AUDIT", "video_path": "videos/base.mp4",
               "green_options": {"enabled": True, "clips": [{"file": asset["file"]}], "opacity": .3}}

        def update(change):
            job.update(change(dict(job)))

        products = SimpleNamespace(root=folder.parent, get_job=lambda _: dict(job),
                                   _manifest_store=lambda _: SimpleNamespace(update=update))
        output = finish_product_green(products, "JOB-AUDIT", root)
        before = digest(output)
        previous_opacity = job["green_result"]["opacity"]
        job["green_options"]["opacity"] = .8

        def fail_update(_):
            raise OSError("fixture manifest write failed")

        products._manifest_store = lambda _: SimpleNamespace(update=fail_update)
        error = None
        try:
            finish_product_green(products, "JOB-AUDIT", root)
        except Exception as exc:
            error = type(exc).__name__
        evidence["product_green_manifest_failure"] = {
            "raised": error, "previous_output_preserved": digest(output) == before,
            "manifest_opacity": job["green_result"]["opacity"], "previous_opacity": previous_opacity,
            "unreferenced_candidates": [p.name for p in folder.joinpath("videos").glob("final_with_green_*.mp4") if p != output],
        }

        from core.green_screen import render_green
        event = threading.Event()

        def cancel_after_green(*args, **kwargs):
            result = render_green(*args, **kwargs)
            event.set()
            return result

        products._manifest_store = lambda _: SimpleNamespace(update=update)
        error = None
        try:
            with patch("core.green_screen.render_green", side_effect=cancel_after_green):
                finish_product_green(products, "JOB-AUDIT", root, cancel_event=event)
        except Exception as exc:
            error = type(exc).__name__
        evidence["product_green_late_cancel"] = {
            "raised": error, "previous_output_preserved": digest(output) == before,
            "manifest_output_unchanged": job["green_result"]["output"] == str(output),
            "unreferenced_candidates": [p.name for p in folder.joinpath("videos").glob("final_with_green_*.mp4") if p != output],
        }

        def commit_then_lose_ack(change):
            update(change)
            raise OSError("fixture manifest commit acknowledgement lost")

        products._manifest_store = lambda _: SimpleNamespace(update=commit_then_lose_ack)
        error = None
        try:
            finish_product_green(products, "JOB-AUDIT", root)
        except Exception as exc:
            error = type(exc).__name__
        promoted = folder / job["video_path"]
        evidence["product_green_committed_ack_lost"] = {
            "raised": error, "previous_output_preserved": digest(output) == before,
            "promoted_output_retained": promoted.is_file(), "promoted_is_new_version": promoted != output,
            "manifest_matches_promoted": job["green_result"]["output"] == str(promoted),
        }
    return evidence


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=True))
