"""Resumable local 16:9 chapter rendering for long Story jobs.

Only completed, input-hash-matched ten-image chapters are reused. The final
voice is mixed once after concatenation, so chapter boundaries do not repeat
speech, subtitles, music or a call to the voice provider.
"""
import hashlib
import json
import math
import os
import wave
from pathlib import Path

from core.atomic_json import AtomicJsonFile
from core.cancellable_process import check_cancelled
from core.long_video import chapter_ranges
from core.render_backend import run_render
from core.story_video import StoryVideoComposer
from core.video_composer import MultiFlowComposer


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _allocated_seconds(durations, count, target):
    weights = list(durations or [])
    if (len(weights) != count or any(not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0 for value in weights)):
        weights = [1.0] * count
    return [float(target) * value / sum(weights) for value in weights]


class LongVideoBatchComposer:
    def __init__(self, ffmpeg_path=''):
        self.scenes = StoryVideoComposer(ffmpeg_path)
        self.ffmpeg = self.scenes.ffmpeg

    def compose(self, images, output_path, durations, voice_path='', *, target_seconds=300,
                width=1920, height=1080, fps=30, crf=18, motion_strength=1.0,
                transition_sec=.22, cancel_event=None, progress=None):
        check_cancelled(cancel_event)
        images = [Path(path) for path in images]
        if not 18 <= len(images) <= 50 or any(not path.is_file() for path in images):
            raise ValueError('คลิปยาวต้องมีภาพจริงครบ 18–50 ฉาก')
        if (int(width) * 9 != int(height) * 16 or int(width) % 2 or int(height) % 2):
            raise ValueError('คลิปยาวต้องเป็นภาพแนวนอน 16:9')
        voice = Path(voice_path) if voice_path else None
        if voice and not voice.is_file():
            raise ValueError('ไม่พบเสียงพากย์คลิปยาว')
        seconds = self.scenes.duration(voice) if voice else float(target_seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('ความยาวเสียงหรือคลิปยาวไม่ถูกต้อง')
        if voice and seconds < len(images) * 2:
            raise ValueError('บทพากย์สั้นเกินจำนวนภาพ • เก็บภาพและเสียงเดิมไว้ให้ปรับบท')
        allocated = _allocated_seconds(durations, len(images), seconds)
        output = Path(output_path)
        chapter_dir = output.parent / 'long_chapters'
        chapter_dir.mkdir(parents=True, exist_ok=True)
        chapters = []
        ranges = chapter_ranges(len(images))
        for number, (start, end) in enumerate(ranges, 1):
            check_cancelled(cancel_event)
            source = images[start - 1:end]
            target = chapter_dir / f'chapter_{number:02d}.mp4'
            ledger = AtomicJsonFile(chapter_dir / f'chapter_{number:02d}.json')
            identity = {
                'version': 1, 'range': [start, end],
                'images': [_sha256(path) for path in source],
                'durations': [round(value, 6) for value in allocated[start - 1:end]],
                'render': [int(width), int(height), int(fps), int(crf),
                           float(motion_strength), float(transition_sec)],
            }
            saved = ledger.read(default=None)
            reused = (isinstance(saved, dict) and saved.get('identity') == identity
                      and target.is_file() and target.stat().st_size > 1024
                      and saved.get('output_sha256') == _sha256(target))
            if not reused:
                self.scenes.compose(source, target, allocated[start - 1:end], '',
                    width=width, height=height, fps=fps, crf=crf,
                    motion_strength=motion_strength, transition_sec=transition_sec,
                    cancel_event=cancel_event, min_images=1, fade_edges=False)
                ledger.write({'identity': identity, 'output_sha256': _sha256(target),
                              'duration': self.scenes.duration(target)})
            chapters.append(target)
            if progress:
                progress(number, len(ranges), start, end, reused)
        check_cancelled(cancel_event)
        concat_file = chapter_dir / 'concat.txt'
        concat_file.write_text('\n'.join("file '" + path.resolve().as_posix().replace("'", "'\\''") + "'"
                                     for path in chapters), encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f'.{output.stem}.long-rendering{output.suffix}')
        command = [str(self.ffmpeg), '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file)]
        if voice:
            command += ['-i', str(voice), '-map', '0:v:0', '-map', '1:a:0',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest']
        else:
            command += ['-map', '0:v:0', '-c:v', 'copy', '-an']
        command += ['-movflags', '+faststart', str(temporary)]
        try:
            result = run_render(command, cancel_event=cancel_event, timeout=3600,
                                duration=seconds, label='รวมคลิปยาวทีละชุด')
            check_cancelled(cancel_event)
            if result.returncode or not temporary.is_file() or temporary.stat().st_size < 1024:
                raise RuntimeError('รวมคลิปยาวไม่สำเร็จ: ' + str(result.stderr or '')[-900:])
            measured = self.scenes.duration(temporary)
            if abs(measured - seconds) > max(1.0, seconds * .02):
                raise RuntimeError('เวลาคลิปยาวไม่ตรงบทพากย์ • เก็บไฟล์แต่ละชุดไว้ทำต่อ')
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {'output': str(output), 'scene_count': len(images), 'chapter_count': len(chapters),
                'chapter_files': [str(path) for path in chapters], 'duration': measured,
                'voice_included': bool(voice), 'source_type': 'story_image_sequence',
                'width': int(width), 'height': int(height), 'fps': int(fps), 'crf': int(crf),
                'motion_strength': float(motion_strength), 'transition_sec': float(transition_sec)}


class LongFlowBatchComposer:
    """Compose real provider clips in bounded chapters; never substitute stills."""

    def __init__(self, ffmpeg_path='', *, source_provider='google_flow'):
        if source_provider not in {'google_flow', 'meta_ai'}:
            raise ValueError('ผู้สร้างคลิปยาวไม่ถูกต้อง')
        self.source_provider = source_provider
        self.flow = MultiFlowComposer(ffmpeg_path)
        self.ffmpeg = self.flow.ffmpeg

    def compose(self, clips, output_path, durations, voice_path='', *, target_seconds=300,
                width=1920, height=1080, fps=30, crf=18, transition_sec=.22,
                audio_choices=None, cancel_event=None, progress=None, source_audio_version=0):
        check_cancelled(cancel_event)
        from core.long_video import source_audio_version as validate_source_audio_version
        source_audio_version = validate_source_audio_version(source_audio_version)
        clips = [Path(path) for path in clips]
        provider_name = 'Meta AI' if self.source_provider == 'meta_ai' else 'Google Flow'
        if not 18 <= len(clips) <= 50 or any(not path.is_file() for path in clips):
            raise ValueError(f'คลิปยาว {provider_name} ต้องมีวิดีโอจริงครบทุกฉาก')
        if int(width) * 9 != int(height) * 16:
            raise ValueError(f'คลิปยาว {provider_name} ต้องเป็น 16:9')
        voice = Path(voice_path) if voice_path else None
        if voice and not voice.is_file():
            raise ValueError('ไม่พบเสียงพากย์คลิปยาว')
        voice_seconds = self.flow.media_info(voice)['duration'] if voice else 0
        if voice and voice_seconds < len(clips) * 2:
            raise ValueError('บทพากย์สั้นเกินจำนวนฉาก Flow • เก็บคลิปเดิมไว้')
        allocated = _allocated_seconds(durations, len(clips), voice_seconds or target_seconds)
        native = not voice and (audio_choices or {}).get('mode') == 'flow_original'
        music_source = bool(voice and (audio_choices or {}).get('generated_music_version') == 1
                            and (audio_choices or {}).get('keep_video_audio'))
        keep_source = music_source or bool(source_audio_version == 1 and voice
            and (audio_choices or {}).get('mode') == 'api' and (audio_choices or {}).get('keep_video_audio'))
        output = Path(output_path)
        chapter_dir = output.parent / ('long_meta_chapters' if self.source_provider == 'meta_ai' else 'long_flow_chapters')
        chapter_dir.mkdir(parents=True, exist_ok=True)
        chapters = []
        ranges = chapter_ranges(len(clips))
        for number, (start, end) in enumerate(ranges, 1):
            check_cancelled(cancel_event)
            source = clips[start - 1:end]
            target = chapter_dir / f'chapter_{number:02d}.mp4'
            ledger = AtomicJsonFile(chapter_dir / f'chapter_{number:02d}.json')
            identity = {'version': 1, 'range': [start, end],
                        **({'generated_music_audio_version': 1} if music_source else {}),
                        **({'source_audio_version': source_audio_version} if source_audio_version else {}),
                        **({'source_provider': 'meta_ai'} if self.source_provider == 'meta_ai' else {}),
                        'clips': [_sha256(path) for path in source],
                        'voice_sha256': _sha256(voice) if voice else '',
                        'durations': [round(value, 6) for value in allocated[start - 1:end]],
                        'render': [int(width), int(height), int(fps), int(crf), float(transition_sec),
                                   bool(native), audio_choices or {}]}
            saved = ledger.read(default=None)
            reused = (isinstance(saved, dict) and saved.get('identity') == identity
                      and target.is_file() and target.stat().st_size > 1024
                      and saved.get('output_sha256') == _sha256(target))
            if not reused:
                timing_voice = ''
                if voice:
                    # Silent chapter audio is only a timing guide. The intact
                    # narration is mixed once after all chapters are joined.
                    timing_voice = chapter_dir / f'chapter_{number:02d}_timing.wav'
                    samples = max(1, round(sum(allocated[start - 1:end]) * 8000))
                    with wave.open(str(timing_voice), 'wb') as stream:
                        stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                        stream.writeframes(b'\0\0' * samples)
                chapter_audio = ({**audio_choices, 'mode': 'api', 'video_audio_volume': 100}
                                 if keep_source else {'mode': 'api'} if voice else audio_choices)
                self.flow.compose(source, target, voice_path=timing_voice,
                    width=width, height=height, fps=fps, crf=crf, transition_sec=transition_sec,
                    timing_mode='voice_fit' if voice else 'original', tail_seconds=0,
                    scene_durations=allocated[start - 1:end], extend_mode='loop' if voice else 'smooth',
                    audio_choices=chapter_audio,
                    cancel_event=cancel_event)
                ledger.write({'identity': identity, 'output_sha256': _sha256(target),
                              'duration': self.flow.media_info(target)['duration']})
            chapters.append(target)
            if progress:
                progress(number, len(ranges), start, end, reused)
        check_cancelled(cancel_event)
        concat_file = chapter_dir / 'concat.txt'
        concat_file.write_text('\n'.join("file '" + path.resolve().as_posix().replace("'", "'\\''") + "'"
                                     for path in chapters), encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f'.{output.stem}.long-{"meta" if self.source_provider == "meta_ai" else "flow"}-rendering{output.suffix}')
        command = [str(self.ffmpeg), '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file)]
        if keep_source:
            from core.media_audio import video_audio_volume
            gain = video_audio_volume(audio_choices.get('video_audio_volume', 35)) / 100
            command += ['-i', str(voice), '-filter_complex',
                        f'[0:a:0]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.4f}[source];'
                        '[1:a:0]aresample=48000,aformat=channel_layouts=stereo[voice];'
                        '[voice][source]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mixed]',
                        '-map', '0:v:0', '-map', '[mixed]', '-c:v', 'copy', '-c:a', 'aac',
                        '-b:a', '192k', '-t', f'{voice_seconds:.6f}', '-shortest']
        elif voice:
            command += ['-i', str(voice), '-map', '0:v:0', '-map', '1:a:0',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest']
        elif native:
            command += ['-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', '-c:a', 'copy']
        else:
            command += ['-map', '0:v:0', '-c:v', 'copy', '-an']
        command += ['-movflags', '+faststart', str(temporary)]
        try:
            result = run_render(command, cancel_event=cancel_event, timeout=3600,
                                duration=voice_seconds or target_seconds, label=f'รวมคลิป {provider_name} ทีละชุด')
            check_cancelled(cancel_event)
            if result.returncode or not temporary.is_file() or temporary.stat().st_size < 1024:
                raise RuntimeError(f'รวมคลิป {provider_name} ไม่สำเร็จ: ' + str(result.stderr or '')[-900:])
            measured = self.flow.media_info(temporary)['duration']
            if voice and abs(measured - voice_seconds) > max(1.0, voice_seconds * .02):
                raise RuntimeError(f'คลิป {provider_name} ไม่ตรงเสียงพากย์ • เก็บไฟล์ชุดเดิมไว้')
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {'output': str(output), 'clip_count': len(clips), 'chapter_count': len(chapters),
                'duration': measured, 'voice_duration': voice_seconds, 'voice_included': bool(voice),
                'width': int(width), 'height': int(height), 'fps': int(fps), 'crf': int(crf),
                'transition_sec': float(transition_sec),
                'source_type': 'meta_ai_story_composite' if self.source_provider == 'meta_ai' else 'google_flow_story_composite'}


class LongMetaBatchComposer(LongFlowBatchComposer):
    """Long Meta clips use their own cache and the same once-only final voice join."""

    def __init__(self, ffmpeg_path=''):
        super().__init__(ffmpeg_path, source_provider='meta_ai')
