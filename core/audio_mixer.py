import json
import math
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

from core.cancellable_process import check_cancelled, hidden_process_kwargs
from core.render_backend import run_render as run_cancellable
from core.video_logo import VideoLogoError, locate_ffmpeg


class AudioMixer:
    AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

    @staticmethod
    def _replace_rendered_output(temporary, output, retries=6, delay=0.2):
        """Publish a render safely even when Windows is previewing the old file."""
        temporary, output = Path(temporary), Path(output)
        last_error = None
        for attempt in range(max(1, int(retries))):
            try:
                os.replace(temporary, output)
                return output
            except PermissionError as exc:
                last_error = exc
                if attempt + 1 < max(1, int(retries)):
                    time.sleep(max(0.0, float(delay)) * (attempt + 1))
        # Explorer, Media Player, WebView2 preview, or antivirus may keep the
        # existing Final open.  The completed render is still valid, so publish
        # it under a fresh Windows-safe name and let the manifest/library point
        # at that file instead of failing the whole AI job.
        for index in range(1, 100):
            suffix = "_windows" if index == 1 else f"_windows_{index}"
            fallback = output.with_name(f"{output.stem}{suffix}{output.suffix}")
            if fallback.exists():
                continue
            try:
                os.replace(temporary, fallback)
                return fallback
            except PermissionError as exc:
                last_error = exc
        raise last_error or PermissionError(f"Windows ล็อกไฟล์ผลลัพธ์ {output}")

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)
        if not self.ffprobe.is_file():
            found = shutil.which("ffprobe")
            if not found:
                raise VideoLogoError("ไม่พบ FFprobe สำหรับระบบเสียง")
            self.ffprobe = Path(found)

    @classmethod
    def scan_audio(cls, folder):
        folder = Path(folder)
        if not folder.exists():
            return []
        return sorted((path.resolve() for path in folder.iterdir() if path.is_file() and path.suffix.lower() in cls.AUDIO_EXTENSIONS), key=lambda path: path.name.lower())

    def duration(self, source):
        result = subprocess.run(
            [str(self.ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            **hidden_process_kwargs(),
        )
        if result.returncode:
            raise VideoLogoError("อ่านความยาววิดีโอไม่สำเร็จ")
        return float((json.loads(result.stdout or "{}").get("format") or {}).get("duration") or 0)

    def speech_intervals(self, source, noise_db=-42, min_silence=0.16, edge_padding=0.04, cancel_event=None):
        """Return wall-clock ranges that contain speech.

        Story subtitles use the approved narration text so no words are lost,
        but spreading that text over the whole file makes captions drift every
        time the voice pauses.  FFmpeg's silence detector gives us a cheap,
        local timing map without sending the narration to another API.
        """
        source = Path(source).resolve()
        duration = self.duration(source)
        if duration <= 0:
            return []
        command = [
            str(self.ffmpeg), "-hide_banner", "-nostats", "-i", str(source),
            "-af", f"silencedetect=noise={float(noise_db):g}dB:d={float(min_silence):g}",
            "-f", "null", os.devnull,
        ]
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=max(60, duration * 2))
        except (OSError, subprocess.SubprocessError):
            return [(0.0, duration)]
        if result.returncode:
            return [(0.0, duration)]

        silence_ranges = []
        silence_start = None
        for line in str(result.stderr or "").splitlines():
            start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
            if start_match:
                silence_start = max(0.0, float(start_match.group(1)))
            end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
            if end_match and silence_start is not None:
                silence_end = min(duration, float(end_match.group(1)))
                if silence_end > silence_start:
                    silence_ranges.append((silence_start, silence_end))
                silence_start = None
        if silence_start is not None and silence_start < duration:
            silence_ranges.append((silence_start, duration))
        if not silence_ranges:
            return [(0.0, duration)]

        # Preserve a small amount at both speech edges so soft Thai consonants
        # are not classified as silence.  Adjacent ranges are then merged.
        padding = max(0.0, min(0.12, float(edge_padding)))
        speech, cursor = [], 0.0
        for silence_start, silence_end in silence_ranges:
            speech_end = min(duration, silence_start + padding)
            if speech_end - cursor >= 0.04:
                speech.append((cursor, speech_end))
            cursor = max(cursor, silence_end - padding)
        if duration - cursor >= 0.04:
            speech.append((cursor, duration))
        merged = []
        for start, end in speech:
            if merged and start - merged[-1][1] < 0.08:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        voiced_duration = sum(end - start for start, end in merged)
        return merged if merged and voiced_duration >= duration * 0.15 else [(0.0, duration)]

    @staticmethod
    def cue_times(srt_path):
        path = Path(srt_path)
        if not path.is_file():
            return []
        values = []
        for hours, minutes, seconds, milliseconds in re.findall(r"(?m)^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->", path.read_text(encoding="utf-8-sig", errors="replace")):
            values.append(int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000)
        return values

    @staticmethod
    def _validate_audio(paths, label):
        valid = []
        for value in paths or []:
            path = Path(value).resolve()
            if not path.is_file() or path.suffix.lower() not in AudioMixer.AUDIO_EXTENSIONS:
                raise ValueError(f"ไฟล์{label}ไม่ถูกต้อง: {path.name}")
            valid.append(path)
        return valid

    @staticmethod
    def build_sfx_events(cue_times, duration, files, min_interval=6.0, max_count=6, seed=""):
        files = list(files or [])
        if not files or max_count <= 0:
            return []
        rng = random.Random(str(seed))
        candidates = [float(value) for value in cue_times or [] if 1.0 <= float(value) <= max(1.0, duration - 1.0)]
        events, last = [], -999.0
        for value in candidates:
            if value - last < float(min_interval):
                continue
            events.append({"time": value, "file": rng.choice(files)})
            last = value
            if len(events) >= int(max_count):
                break
        return events

    @staticmethod
    def _spread_music_offset(track_duration, segment_duration, used_ranges, rng):
        """Choose a deterministic source offset with the least overlap against earlier cuts."""
        available = max(0.0, float(track_duration) - float(segment_duration))
        if available <= 0.2:
            return 0.0
        if not used_ranges:
            return rng.uniform(0.0, available)
        candidates = [available * index / 11 for index in range(12)]
        candidates.extend(rng.uniform(0.0, available) for _ in range(8))

        def score(offset):
            end = offset + segment_duration
            overlap = sum(max(0.0, min(end, old_end) - max(offset, old_start)) for old_start, old_end in used_ranges)
            distance = min((abs(offset - old_start) for old_start, _ in used_ranges), default=track_duration)
            return overlap, -distance, offset

        return min(candidates, key=score)

    @classmethod
    def build_music_plan(
        cls, duration, tracks, seed="", min_segment_sec=8.0, max_segment_sec=12.0, crossfade_sec=1.0,
    ):
        """Build balanced random cuts that cover the video and never exceed the requested cap."""
        duration = max(0.0, float(duration))
        records = [
            {"file": str(item["file"]), "duration": max(0.1, float(item["duration"]))}
            for item in (tracks or []) if item.get("file")
        ]
        if duration <= 0 or not records:
            return []
        minimum = max(2.0, min(12.0, float(min_segment_sec)))
        maximum = max(minimum, min(12.0, float(max_segment_sec)))
        crossfade = max(0.15, min(2.0, float(crossfade_sec)))
        rng = random.Random(str(seed))
        exposure = {item["file"]: 0.0 for item in records}
        used_ranges = {item["file"]: [] for item in records}
        plan, coverage, previous = [], 0.0, ""

        # Use the smallest number of cuts that can cover the video while obeying
        # the hard maximum.  Distribute the remaining duration first so the last
        # cut never becomes a tiny accidental fragment.
        effective_capacity = max(0.1, maximum - crossfade)
        segment_count = max(1, math.ceil(max(0.0, duration - crossfade) / effective_capacity))
        required_audio = duration + crossfade * (segment_count - 1)
        feasible_minimum = min(minimum, required_audio / segment_count)
        durations, remaining_audio = [], required_audio
        for index in range(segment_count):
            remaining_count = segment_count - index - 1
            if not remaining_count:
                segment_duration = remaining_audio
            else:
                lower = max(feasible_minimum, remaining_audio - remaining_count * maximum)
                upper = min(maximum, remaining_audio - remaining_count * feasible_minimum)
                segment_duration = rng.uniform(lower, upper) if upper > lower + 0.001 else lower
            durations.append(segment_duration)
            remaining_audio -= segment_duration

        for segment_duration in durations:
            choices = [item for item in records if len(records) == 1 or item["file"] != previous]
            least_used = min(exposure[item["file"]] for item in choices)
            balanced = [item for item in choices if exposure[item["file"]] <= least_used + 0.25]
            track = rng.choice(balanced)
            offset = cls._spread_music_offset(
                track["duration"], segment_duration, used_ranges[track["file"]], rng,
            )
            timeline_start = 0.0 if not plan else max(0.0, coverage - crossfade)
            timeline_end = min(duration, timeline_start + segment_duration)
            plan.append({
                "file": track["file"],
                "offset": round(offset, 3),
                "duration": round(segment_duration, 3),
                "timeline_start": round(timeline_start, 3),
                "timeline_end": round(timeline_end, 3),
            })
            used_ranges[track["file"]].append((offset, offset + segment_duration))
            exposure[track["file"]] += segment_duration
            previous = track["file"]
            coverage = timeline_end
        return plan

    def render(
        self, source_path, output_path, background_files=None, background_mode="auto",
        background_volume=0.12, sfx_files=None, sfx_mode="auto", sfx_volume=0.22,
        cue_times=None, min_sfx_interval=6.0, max_sfx_count=6, seed="", cancel_event=None,
        music_segment_max_sec=12.0, music_duck_ratio=0.38, source_silent=False, music_track_count=None,
    ):
        check_cancelled(cancel_event)
        source, output = Path(source_path).resolve(), Path(output_path).resolve()
        if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("ไม่พบวิดีโอสำหรับผสมเสียง")
        background_files = self._validate_audio(background_files, "พื้นหลัง")
        sfx_files = self._validate_audio(sfx_files, "ข้อความ")
        duration = self.duration(source)
        if duration <= 0:
            raise ValueError("วิดีโอไม่มีความยาวที่ใช้งานได้")
        background_volume = max(0.0, min(0.5, float(background_volume)))
        sfx_volume = max(0.0, min(0.8, float(sfx_volume)))
        music_segment_max_sec = max(8.0, min(12.0, float(music_segment_max_sec)))
        music_duck_ratio = max(0.2, min(0.65, float(music_duck_ratio)))
        rng = random.Random(str(seed))

        music = list(dict.fromkeys(background_files))
        rng.shuffle(music)
        if music_track_count is not None:
            if type(music_track_count) is not int or music_track_count < 1:
                raise ValueError('จำนวนเพลงไม่ถูกต้อง')
            music = music[:music_track_count]
        elif background_mode == "selected":
            music = music[:1]
        elif background_mode == "random":
            music = music[:rng.randint(min(2, len(music)), min(4, len(music)))] if music else []
        else:
            music = music[:min(4, len(music))]

        track_records = [{"file": str(path), "duration": max(1.0, self.duration(path))} for path in music]
        crossfade = 1.0
        music_plan = self.build_music_plan(
            duration, track_records, seed=seed,
            min_segment_sec=min(8.0, music_segment_max_sec),
            max_segment_sec=music_segment_max_sec,
            crossfade_sec=crossfade,
        )
        music_warnings = []
        unique_music = len({item["file"] for item in music_plan})
        if music_track_count and music and unique_music < music_track_count:
            music_warnings.append(f'ตั้งไว้ {music_track_count} เพลง ใช้จริง {unique_music} เพลง ตามความยาวคลิปและจำนวนไฟล์ที่มี')
        if music_plan and unique_music < 3 and music_track_count is None:
            music_warnings.append("คลังเพลงที่ใช้มีน้อยกว่า 3 เพลง • ระบบตัดเป็นท่อนสั้นแล้ว แต่แนะนำเพิ่มเพลงที่มีสิทธิ์ใช้งาน")
        if music_plan and max(item["duration"] for item in music_plan) > music_segment_max_sec + 0.01:
            raise VideoLogoError("แผนเพลงมีท่อนยาวเกินค่าความปลอดภัย")
        if background_volume <= 0:
            music_plan, music_warnings, unique_music = [], [], 0

        sfx_pool = list(sfx_files)
        if sfx_mode == "selected":
            sfx_pool = sfx_pool[:1]
        elif sfx_mode == "off":
            sfx_pool = []
        events = self.build_sfx_events(cue_times, duration, sfx_pool, min_sfx_interval, max_sfx_count, seed)

        command = [str(self.ffmpeg), "-y", "-i", str(source)]
        filters = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1,asplit=2[main][duckkey]"] if music_plan else ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1[main]"]
        if source_silent:
            silent = f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f}"
            filters = [silent + (",asplit=2[main][duckkey]" if music_plan else "[main]")]
        input_index = 1
        mix_labels = ["[main]"]
        if music_plan and background_volume > 0:
            music_labels = []
            for index, segment in enumerate(music_plan):
                path = Path(segment["file"])
                segment_duration = float(segment["duration"])
                offset = float(segment["offset"])
                command.extend(["-stream_loop", "-1", "-ss", f"{offset:.3f}", "-t", f"{segment_duration:.3f}", "-i", str(path)])
                label = f"music{index}"
                filters.append(f"[{input_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{segment_duration:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-24:LRA=11:TP=-2,aresample=48000[{label}]")
                music_labels.append(f"[{label}]")
                input_index += 1
            if len(music_labels) == 1:
                bed_label = music_labels[0]
            else:
                current = music_labels[0]
                for index, next_label in enumerate(music_labels[1:], 1):
                    output_label = f"cross{index}"
                    filters.append(f"{current}{next_label}acrossfade=d={crossfade}:c1=qsin:c2=qsin[{output_label}]")
                    current = f"[{output_label}]"
                bed_label = current
            fade_out_start = max(0.0, duration - 0.8)
            filters.append(f"{bed_label}atrim=0:{duration:.3f},afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out_start:.3f}:d=0.8,volume={background_volume:.4f}[bedlevel]")
            compression_ratio = max(2.0, min(20.0, 4.0 / music_duck_ratio))
            filters.append(f"[bedlevel][duckkey]sidechaincompress=threshold=0.012:ratio={compression_ratio:.3f}:attack=35:release=320:makeup=1[bed]")
            mix_labels.append("[bed]")

        event_plan = []
        for index, event in enumerate(events):
            command.extend(["-i", str(event["file"])])
            delay_ms = max(0, round(event["time"] * 1000))
            label = f"sfx{index}"
            filters.append(f"[{input_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:2,afade=t=out:st=1.5:d=0.45,adelay={delay_ms}:all=1,volume={sfx_volume:.4f}[{label}]")
            mix_labels.append(f"[{label}]")
            event_plan.append({"time": round(event["time"], 3), "file": str(event["file"])})
            input_index += 1

        if len(mix_labels) == 1:
            filters.append("[main]anull[mixed]")
        else:
            filters.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[mixed]")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.mixing{output.suffix}")
        command.extend([
            "-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[mixed]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{duration:.3f}", str(temporary),
        ])
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600,
                duration=duration, label='มิกซ์เสียง • คัดลอกภาพเดิม ไม่เข้ารหัสภาพซ้ำ')
            if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                raise VideoLogoError("ผสมเสียงไม่สำเร็จ: " + result.stderr.strip()[-1200:])
            output = self._replace_rendered_output(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "output": output, "source": source, "duration": duration,
            "background_mode": background_mode, "background_volume": background_volume,
            "music_plan": music_plan, "sfx_mode": sfx_mode, "sfx_volume": sfx_volume,
            "sfx_events": event_plan, "min_sfx_interval": float(min_sfx_interval),
            "audio_mix_version": 2,
            "music_segment_max_sec": music_segment_max_sec,
            "music_crossfade_sec": crossfade,
            "music_duck_ratio": music_duck_ratio,
            "music_unique_tracks": unique_music,
            "music_requested_tracks": music_track_count,
            "music_selected_files": [str(p) for p in music],
            "music_warnings": music_warnings,
        }
