"""Lossless local PCM splitting; no uploads and no server credentials."""
import hashlib
import math
import re
import uuid
import wave
from pathlib import Path

from core.atomic_json import AtomicJsonFile
from core.cancellable_process import check_cancelled


def prepare_subtitle_chunks(source, directory, seconds=60, cancel_event=None):
    seconds = float(seconds)
    if not math.isfinite(seconds) or not 15 <= seconds <= 60:
        raise ValueError('ช่วงเสียงต้องยาว 15–60 วินาที')
    source, directory = Path(source), Path(directory)
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            check_cancelled(cancel_event)
            digest.update(block)
    # Separate changed source audio/config from existing submitted checkpoints.
    identity = hashlib.sha256(f'{digest.hexdigest()}:{seconds}'.encode()).hexdigest()
    folder = directory / identity
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    with wave.open(str(source), 'rb') as audio:
        if audio.getcomptype() != 'NONE' or audio.getnframes() <= 0:
            raise ValueError('ต้องเป็นไฟล์เสียง PCM WAV ที่มีข้อมูล')
        rate = audio.getframerate()
        limit = max(1, int(rate * seconds))
        total = audio.getnframes()
        for index, start in enumerate(range(0, total, limit), 1):
            check_cancelled(cancel_event)
            audio.setpos(start)
            frames = audio.readframes(min(limit, total - start))
            target = folder / f'part-{index:03d}.wav'
            temporary = target.with_suffix('.partial')
            try:
                with wave.open(str(temporary), 'wb') as output:
                    output.setparams(audio.getparams())
                    output.writeframes(frames)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            entries.append({'index': index, 'path': str(target),
                            'start_frame': start, 'end_frame': min(total, start + limit),
                            'offset_seconds': start / rate,
                            'duration_seconds': min(limit, total - start) / rate})
    manifest = {'version': 1, 'source_sha256': digest.hexdigest(), 'sample_rate': rate,
                'total_frames': total, 'parts': entries}
    AtomicJsonFile(folder / 'chunks.json').write(manifest)
    return manifest


def merge_subtitle_segments(parts, adjustments=None):
    """Intersect local cues with actual PCM duration; retain raw provider data.

    A provider can append tiny hallucinated tail cues beyond EOF. They have
    no playable audio interval and must not fail an otherwise valid render.
    Non-finite, reversed or overlapping in-range cues still require review.
    """
    merged = []
    expected_offset = 0.0
    for part in parts:
        offset, duration = float(part['offset_seconds']), float(part['duration_seconds'])
        if not all(math.isfinite(v) for v in (offset, duration)) or duration <= 0 or abs(offset - expected_offset) > .001:
            raise ValueError('ช่วงเสียงหายหรือเรียงลำดับไม่ถูกต้อง')
        previous = 0.0
        part_start = len(merged)
        for cue_index, cue in enumerate(part['segments'], 1):
            start, end = float(cue['start']), float(cue['end'])
            if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
                raise ValueError('เวลาคำบรรยายไม่อยู่ในช่วงเสียงหรือซ้อนกัน')
            if start >= duration:
                if adjustments is not None:
                    adjustments.append({'offset_seconds':offset,'cue':cue_index,'action':'outside_audio',
                                        'start':start,'end':end,'duration_seconds':duration})
                continue
            if start < previous:
                raise ValueError('เวลาคำบรรยายไม่อยู่ในช่วงเสียงหรือซ้อนกัน')
            clipped_end = min(end, duration)
            if end > duration and adjustments is not None:
                adjustments.append({'offset_seconds':offset,'cue':cue_index,'action':'clip_end',
                                    'start':start,'end':end,'duration_seconds':duration})
            merged.append({'start': offset + start, 'end': offset + clipped_end, 'text': str(cue.get('text', ''))})
            previous = clipped_end
        if part['segments'] and len(merged) == part_start:
            raise ValueError('ไม่มีคำบรรยายที่อยู่ภายในช่วงเสียงจริง • เก็บผลเดิมไว้ตรวจสอบ')
        expected_offset += duration
    if parts and not merged:
        raise ValueError('ไม่มีคำบรรยายที่อยู่ภายในช่วงเสียงจริง • เก็บผลเดิมไว้ตรวจสอบ')
    return merged


def transcribe_chunks(client, source, directory, language='th', cancel_event=None, on_status=None):
    """Submit sequentially and persist each remote job before polling it."""
    plan = prepare_subtitle_chunks(source, directory, cancel_event=cancel_event)
    folder = Path(plan['parts'][0]['path']).parent
    store = AtomicJsonFile(folder / f'jobs-{language}.json')
    if not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]{2,8})?', language):
        raise ValueError('รหัสภาษาไม่ถูกต้อง')
    with store.locked():
        state = store.read(default={'version':1, 'parts':{}})
        results=[]
        for part in plan['parts']:
            check_cancelled(cancel_event)
            key=str(part['index'])
            record=state['parts'].setdefault(key,{})
            if on_status:on_status(f"ทำซับช่วง {key}/{len(plan['parts'])}", {})
            if 'result' not in record:
                if not record.get('job_id'):
                    # Unknown submissions are stopped rather than blindly paid again.
                    if record.get('submitting'):
                        raise ValueError(f'ยังไม่ยืนยันหมายเลขงาน API ช่วง {key} • ตรวจงานเดิมก่อนส่งซ้ำ')
                    record['submitting']=True
                    store.write(state)
                    request_key=str(uuid.uuid5(uuid.NAMESPACE_URL, f"subtitle:{folder.name}:{language}:{key}"))
                    created=client.create_job(part['path'], language, request_key)
                    record['job_id']=str(created.get('jobId') or created.get('job_id') or '')
                    if not record['job_id']:raise ValueError('API ไม่ส่งหมายเลขงาน')
                    store.write(state)
                record['result']=client.wait_until_done(record['job_id'],cancel_event=cancel_event,on_status=on_status)
                store.write(state)
            artifacts=client.extract_artifacts(record['result'])
            segments=artifacts.get('segments') or []
            if not segments and artifacts.get('srt'):
                pattern=r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.*?)(?=\n\s*\n|\Z)'
                for match in re.finditer(pattern,artifacts['srt'].replace('\r',''),re.S):
                    fields=match.groups()
                    stamp=lambda i: int(fields[i])*3600+int(fields[i+1])*60+int(fields[i+2])+int(fields[i+3])/1000
                    segments.append({'start':stamp(0),'end':stamp(4),'text':fields[8].strip()})
            if not segments:
                raise ValueError(f'API ช่วง {key} ไม่มีเวลาคำบรรยาย • เก็บผลไว้แล้ว ไม่ส่งซ้ำ')
            results.append({**part,'segments':segments})
        adjustments=[]
        merged=merge_subtitle_segments(results,adjustments)
        AtomicJsonFile(folder/'timing-normalization.json').write({
            'version':1,'source_sha256':plan['source_sha256'],'adjustments':adjustments})
        return {'status':'done','segments':merged,'transcript':'\n'.join(c['text'] for c in merged),
                'chunk_count':len(results),'source_sha256':plan['source_sha256']}
