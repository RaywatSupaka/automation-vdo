"""Silent, ordered green-screen overlays; local media only, never AI dispatch."""
import math
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

from core.video_intro import IntroLibrary, inspect_video, _digest
from core.audio_mixer import AudioMixer
from core.cancellable_process import check_cancelled, run_cancellable
from core.green_cache import cycle_key, restore_cycle, remember_cycle
from core.green_progress import progress_notice
from core.render_backend import run_render, optimized_render, green_filter_threads


def green_options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or type(value.get('enabled', False)) is not bool:
        raise ValueError('ตัวเลือกกรีนสกรีนไม่ถูกต้อง')
    clips = value.get('clips', [])
    if not isinstance(clips, list) or len(clips) > 3:
        raise ValueError('เลือกกรีนสกรีนได้ไม่เกิน 3 ไฟล์')
    result = {'enabled':value.get('enabled', False), 'clips':[], 'opacity':value.get('opacity', .5),
              'fit':value.get('fit', 'contain')}
    if (type(result['opacity']) not in (int, float) or not math.isfinite(result['opacity'])
            or not 0 < result['opacity'] <= 1 or result['fit'] not in {'contain','cover'}):
        raise ValueError('ความเข้มหรือรูปแบบจัดภาพกรีนสกรีนไม่ถูกต้อง')
    seen = set()
    for clip in clips:
        if not isinstance(clip, dict):
            raise ValueError('ไฟล์กรีนสกรีนไม่ถูกต้อง')
        file = clip.get('file', '')
        color = clip.get('color', '#00ff00')
        similarity, blend = clip.get('similarity', .15), clip.get('blend', .08)
        if (not isinstance(file, str) or not re.fullmatch(r'assets/screenfx/[a-f0-9]{64}\.(mp4|mov|mkv|webm|m4v|avi)',file)
                or file in seen or not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color)
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in (similarity,blend))
                or not .01 <= similarity <= 1 or not 0 <= blend <= 1):
            raise ValueError('ไฟล์ซ้ำหรือค่าลบพื้นเขียวไม่ถูกต้อง')
        seen.add(file)
        result['clips'].append({'file':file,'color':color,'similarity':similarity,'blend':blend})
    if result['enabled'] and not result['clips']:
        raise ValueError('กรุณาเลือกกรีนสกรีน 1–3 ไฟล์ก่อนเปิดใช้งาน')
    return result


class GreenLibrary(IntroLibrary):
    asset_folder = 'screenfx'
    settings_name = 'green_screen_settings.json'

    def __init__(self, root, ffmpeg_path=''):
        super().__init__(root, ffmpeg_path)
        self.preview_lock = threading.Lock()

    def state(self):
        data = self.store.read({})
        return {'settings':green_options(data.get('settings')), 'assets':data.get('assets', []),
                'targets':self.targets(data.get('targets', {}))}

    @staticmethod
    def targets(value):
        if not isinstance(value, dict) or any(k not in {'story','drama','product'} for k in value):
            raise ValueError('ประเภทงานกรีนสกรีนไม่ถูกต้อง')
        result = {k:value.get(k,False) for k in ('story','drama','product')}
        if any(type(v) is not bool for v in result.values()):
            raise ValueError('ประเภทงานกรีนสกรีนต้องเป็นเปิดหรือปิด')
        return result

    def resolve(self, file, verify=True):
        options = green_options({'enabled':True,'clips':[{'file':file}]})
        path = (self.root/options['clips'][0]['file']).resolve()
        if path.parent != self.root/'assets'/'screenfx' or not path.is_file() or (verify and _digest(path) != path.stem):
            raise ValueError('ไฟล์กรีนสกรีนหายหรือถูกเปลี่ยน กรุณาอัปโหลดใหม่')
        return path

    def validate(self, value):
        options = green_options(value)
        if options['enabled']:
            for clip in options['clips']:
                self.resolve(clip['file'])
        return options

    def save(self, value, targets):
        targets = self.targets(targets)
        options = green_options(value)
        options['enabled'] = any(targets.values())
        self.validate(options)
        self.store.update(lambda data:{**data,'settings':options,'targets':targets},default={})
        return self.state()

    def import_file(self, path):
        try:
            return super().import_file(path)
        except ValueError as exc:
            raise ValueError(str(exc).replace('อินโทร','กรีนสกรีน')) from exc

    def remove_from_library(self, file):
        self.resolve(file)
        def update(data):
            if any(c.get('file')==file for c in (data.get('settings') or {}).get('clips',[])):
                raise ValueError('ยกเลิกเลือกไฟล์นี้และบันทึกก่อนเอาออกจากคลัง')
            return {**data,'assets':[a for a in data.get('assets',[]) if a.get('file')!=file]}
        self.store.update(update,default={})
        # Keep the content-addressed bytes: existing jobs/queues may own them.
        return self.state()

    def import_stream(self, stream, size, filename):
        try:
            return super().import_stream(stream,size,filename)
        except ValueError as exc:
            raise ValueError(str(exc).replace('อินโทร','กรีนสกรีน')) from exc

    def preview(self, value):
        options = self.validate({**green_options(value), 'enabled':True})
        if not self.preview_lock.acquire(blocking=False):
            raise ValueError('กำลังทำตัวอย่างกรีนสกรีน กรุณารอ')
        try:
            folder = self.root/'workspace'/'preview'/'screenfx'
            folder.mkdir(parents=True, exist_ok=True)
            duration = min(30., sum(inspect_video(self.resolve(c['file']),self.ffmpeg_path)['duration'] for c in options['clips'])+1)
            with tempfile.TemporaryDirectory(prefix='base-',dir=folder) as temp:
                base = Path(temp)/'base.mp4'
                mixer = AudioMixer(self.ffmpeg_path)
                result = run_cancellable([str(mixer.ffmpeg),'-v','error','-y','-f','lavfi','-i',
                    f'color=c=0x273650:s=360x640:r=24:d={duration}', '-c:v','libx264','-pix_fmt','yuv420p',str(base)],timeout=90)
                if result.returncode:
                    raise ValueError('สร้างพื้นหลังตัวอย่างไม่สำเร็จ')
                token = uuid.uuid4().hex
                render_green(self.root,base,folder/(token+'.mp4'),options,self.ffmpeg_path)
            return {'ok':True,'url':'/api/desktop/green-preview?token='+token,'duration':duration}
        finally:
            self.preview_lock.release()


def _effect_filter(index, clip, options, width, height, fps, duration=None):
    # Reduce pixels/frames before expensive chroma keying. Pad AFTER keying so
    # letterboxing stays transparent even when the configured key is not green.
    fit = ('decrease' if options['fit'] == 'contain' else 'increase')
    placement = (f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000'
                 if options['fit'] == 'contain' else f'crop={width}:{height}')
    trim = f'trim=duration={duration:.8f},' if duration is not None else ''
    return (f'[{index}:v:0]{trim}setpts=PTS-STARTPTS,fps={fps:.8f},'
            f'scale={width}:{height}:force_original_aspect_ratio={fit},'
            f'chromakey=0x{clip["color"][1:]}:{clip["similarity"]}:{clip["blend"]},'
            f'format=rgba,{placement},setsar=1,colorchannelmixer=aa={options["opacity"]}')


def render_green(root, source, output, value, ffmpeg_path='', cancel_event=None, progress=None, *, filter_threads=None):
    if filter_threads is None:
        filter_threads = green_filter_threads()
    if type(filter_threads) is not int or filter_threads not in {0, 1, 2, 4}:
        raise ValueError('จำนวนเธรดกรีนสกรีนไม่ถูกต้อง')
    library = GreenLibrary(root,ffmpeg_path)
    options = green_options(value)
    if not options['enabled']:
        return Path(source), {'enabled':False}
    check_cancelled(cancel_event)
    source, output = Path(source).resolve(), Path(output).resolve()
    assets = [library.resolve(c['file']) for c in options['clips']]
    if output == source or output in assets:
        raise ValueError('ต้องเก็บวิดีโอต้นฉบับไว้ก่อนใส่กรีนสกรีน')
    info = inspect_video(source,ffmpeg_path,cancel_event)
    width, height = info['width']//2*2, info['height']//2*2
    fps, duration = info['fps'], info['duration']
    mixer = AudioMixer(ffmpeg_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    prepare_seconds, overlay_seconds, cache_hit = 0., 0., False
    with tempfile.TemporaryDirectory(prefix='green-render-',dir=output.parent) as temp:
        cycle, candidate = Path(temp)/'cycle.mkv', Path(temp)/'candidate.mp4'
        elapsed=0.
        used, durations = [], []
        for asset in assets:
            if elapsed>=duration:break
            clip_duration=min(inspect_video(asset,ffmpeg_path,cancel_event)['duration'],duration-elapsed)
            elapsed+=clip_duration
            used.append(asset)
            durations.append(clip_duration)

        def run(command, label, length, name, timeout):
            if optimized_render() and '-c:v' in command and command[command.index('-c:v')+1] == 'libx264':
                return run_render(command, cancel_event=cancel_event, timeout=timeout,
                                  duration=length, label=label)
            progress_file = Path(temp) / (name + '.progress')
            notice = progress_notice(progress_file, length, label, progress)
            if progress:
                progress(label)
            result = run_cancellable(command[:1] + ['-nostats','-stats_period','0.5','-progress',str(progress_file)] + command[1:],
                                     cancel_event=cancel_event, timeout=timeout, on_wait=notice)
            notice(0)
            return result

        # Short effects repeated many times are cheaper to key once and loop.
        if len(used) == 1 and duration <= durations[0] * 2:
            strategy = 'single_pass'
            effect_source = used[0]
            effect_graph = _effect_filter(1, options['clips'][0], options, width, height, fps) + '[fx];'
        else:
            strategy = 'cached_cycle'
            started = time.perf_counter()
            key_options = {**options, 'filter_threads': filter_threads} if filter_threads != 1 else options
            key = cycle_key(key_options, width, height, fps, durations)
            cache_hit = restore_cycle(root, key, cycle, cancel_event)
            if cache_hit:
                if progress:
                    progress('ใช้กรีนสกรีนที่เตรียมไว้ • ตรวจไฟล์และค่าตั้งตรงกันแล้ว')
            else:
                command = [str(mixer.ffmpeg),'-v','error','-y']
                graph=[]
                for i, asset in enumerate(used):
                    command += ['-i',str(asset)]
                    graph.append(_effect_filter(i, options['clips'][i], options, width, height, fps, durations[i]) + f'[f{i}]')
                graph.append(''.join(f'[f{i}]' for i in range(len(used)))+f'concat=n={len(used)}:v=1:a=0[cycle]')
                command += ['-filter_complex_threads',str(filter_threads),'-filter_complex',';'.join(graph),'-map','[cycle]',
                            '-an','-c:v','ffv1','-pix_fmt','bgra',str(cycle)]
                result = run(command, 'เตรียมกรีนสกรีนสำหรับวนซ้ำ', elapsed, 'prepare', 1800)
                if result.returncode:
                    raise ValueError('GREEN_SCREEN_REVIEW • เตรียมภาพกรีนสกรีนไม่สำเร็จ')
                inspect_video(cycle, ffmpeg_path, cancel_event)
                remember_cycle(root, key, cycle, cancel_event)
            prepare_seconds = time.perf_counter() - started
            effect_source = cycle
            effect_graph = '[1:v:0]setpts=PTS-STARTPTS[fx];'
        graph = '[0:v:0]setpts=PTS-STARTPTS[base];' + effect_graph + '[base][fx]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]'
        started = time.perf_counter()
        result = run([str(mixer.ffmpeg),'-v','error','-y','-i',str(source),'-stream_loop','-1','-i',str(effect_source),
            '-filter_complex_threads',str(filter_threads),'-filter_complex',graph,'-map','[v]','-map','0:a?',
            '-c:v','libx264','-profile:v','high','-pix_fmt','yuv420p','-preset','veryfast','-crf','18',
            '-c:a','copy','-t',str(duration),'-movflags','+faststart',str(candidate)],
            'ซ้อนกรีนสกรีนบนคลิป • ไม่ใช้เสียงเอฟเฟกต์', duration, 'overlay', 3600)
        overlay_seconds = time.perf_counter() - started
        if result.returncode:
            raise ValueError('GREEN_SCREEN_REVIEW • ซ้อนกรีนสกรีนไม่สำเร็จ • เก็บคลิปเดิมไว้')
        actual = inspect_video(candidate,ffmpeg_path,cancel_event)
        if (abs(actual['duration']-duration)>max(.15,2/fps) or actual['has_audio']!=info['has_audio']
                or actual['width'] != width or actual['height'] != height or abs(actual['fps']-fps) > .1):
            raise ValueError('GREEN_SCREEN_REVIEW • ความยาวหรือเสียงคลิปไม่ตรง • ไม่แทนที่ผลงานเดิม')
        check_cancelled(cancel_event)
        os.replace(candidate,output)
        if progress:
            progress('ซ้อนกรีนสกรีน 100% • ตรวจวิดีโอและบันทึกแล้ว')
    return output, {**options,'duration':actual['duration'],'audio':'base_only_effect_audio_discarded',
                    'order':[c['file'] for c in options['clips']],'source':str(source),
                    'renderer_version':2, 'filter_threads':filter_threads, 'strategy':strategy, 'cache_hit':cache_hit,
                    'prepare_seconds':round(prepare_seconds,3), 'overlay_seconds':round(overlay_seconds,3)}


def finish_product_green(products, job_id, root, ffmpeg_path='', cancel_event=None, progress=None):
    job = products.get_job(job_id)
    folder = products.root/job_id
    source = (folder/job['video_path']).resolve()
    old = job.get('green_result') or {}
    if old.get('output') == str(source):
        source = Path(old['source'])  # Never overlay the already-overlaid Final.
    expected_options = green_options(job.get('green_options'))
    # Each completed version has its own path. A failed manifest write must
    # leave the previous Final and the metadata describing it consistent.
    video_folder = (folder/'videos').resolve()
    candidate = video_folder/f'final_with_green_{uuid.uuid4().hex}.mp4'
    committed = False
    try:
        output, plan = render_green(root,source,candidate,expected_options,ffmpeg_path,cancel_event,progress=progress)
        check_cancelled(cancel_event)
        def promote(current):
            check_cancelled(cancel_event)
            if (current.get('video_path') != job['video_path']
                    or green_options(current.get('green_options')) != expected_options):
                raise ValueError('GREEN_SCREEN_REVIEW • ผลงานหรือค่ากรีนสกรีนเปลี่ยนระหว่างประกอบ • เก็บผลงานเดิมไว้')
            return {**current, 'video_path':output.relative_to(folder).as_posix(),
                    'green_result':{**plan,'output':str(output)}}
        products._manifest_store(folder/'job.json').update(promote)
        committed = True
        return output
    finally:
        if not committed and candidate.is_file():
            # Only this invocation's candidate may be removed. A lost write
            # acknowledgement is uncertain: retain it if the manifest already
            # references it, or if the manifest cannot be read for verification.
            try:
                current = products.get_job(job_id)
                referenced = (folder/str(current.get('video_path') or '')).resolve() == candidate
                referenced = referenced or (current.get('green_result') or {}).get('output') == str(candidate)
                if not referenced and candidate.resolve().parent == video_folder:
                    candidate.unlink(missing_ok=True)
            except Exception:
                pass
