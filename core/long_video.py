"""Long-video settings and bounded chapter contracts, separate from Shorts."""
import math
import copy


# One supervised Meta submission produced a playable 1280×720, 10-second MP4
# from a landscape image. This proves 16:9 output capability, not the full
# installed Extension → 18–50-scene workflow; retain strict per-clip validation.
META_LANDSCAPE_GENERATION_VERIFIED = True


def source_audio_version(value=0):
    """Absent/0 is the historical render contract; only new work captures 1."""
    if type(value) is not int or value not in (0, 1):
        raise ValueError('สัญญาเก็บเสียงต้นฉบับคลิปยาวไม่ถูกต้อง')
    return value


def meta_landscape_available():
    return META_LANDSCAPE_GENERATION_VERIFIED


def require_meta_landscape_available():
    if not meta_landscape_available():
        raise ValueError('Meta AI คลิปยาว 16:9 ยังรอยืนยันผลวิดีโอจริง • เลือก Google Flow หรือ Motion ในเครื่องก่อน')


def validate_landscape_image(payload, *, require_16_9=False):
    from io import BytesIO
    from PIL import Image, ImageOps
    with Image.open(BytesIO(payload)) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.width <= image.height:
            raise ValueError('ภาพคลิปยาวไม่ใช่แนวนอน • เก็บงานเดิมไว้ให้ตรวจ ไม่ส่งสร้างซ้ำ')
        if require_16_9 and abs(image.width / image.height - 16 / 9) > .08:
            raise ValueError('ภาพคลิปยาว Meta ต้องใกล้เคียง 16:9 • ไม่บันทึกภาพผิดสัดส่วนเพื่อส่งสร้างวิดีโอ')
        image.verify() if image is opened else image.load()


def long_video_settings(value):
    value = dict(value or {})
    version = int(value.get('version') or 2)
    if version not in (1, 2):
        raise ValueError('รูปแบบแผนคลิปยาวไม่ถูกต้อง')
    seconds = float(value.get('duration_seconds', 180))
    maximum = 300 if version == 1 else 600
    if not math.isfinite(seconds) or not 180 <= seconds <= maximum:
        raise ValueError(f'คลิปยาวต้องมีความยาว 180–{maximum} วินาที')
    count = value.get('scene_count')
    count = min(50, math.ceil(seconds / 8)) if count in (None, '', 'auto') else int(count)
    if not 18 <= count <= 50:
        raise ValueError('คลิปยาวต้องมี 18–50 ฉาก')
    mode = value.get('video_generation_mode', 'image_motion')
    if mode not in ('image_motion', 'google_flow', 'meta_ai'):
        raise ValueError('วิธีสร้างวิดีโอไม่ถูกต้อง')
    return {'version': version, 'job_type': 'long_video', 'aspect_ratio': '16:9',
            'width': 1920, 'height': 1080, 'duration_seconds': seconds,
            'scene_count': count, 'batch_size': 10 if version == 2 else 0,
            'video_generation_mode': mode,
            'subtitle_mode': 'script', 'timing_mode': 'scene_voice'}


def chapter_ranges(scene_count, batch_size=10):
    """One-based, inclusive scene boundaries. The final chapter may be short."""
    count = int(scene_count)
    size = int(batch_size)
    if not 1 <= count <= 50 or size != 10:
        raise ValueError('ชุดภาพคลิปยาวต้องมีชุดละ 10 ภาพ และรวมไม่เกิน 50 ภาพ')
    return [(start, min(count, start + size - 1)) for start in range(1, count + 1, size)]


def validate_outline(outline, job_id, scene_count):
    if not isinstance(outline, dict) or outline.get('job_id') != job_id:
        raise ValueError('โครงเรื่องคลิปยาวไม่ตรงกับงาน')
    beats = outline.get('chapter_beats')
    if not isinstance(beats, list) or len(beats) != len(chapter_ranges(scene_count)):
        raise ValueError('โครงเรื่องต้องมีหัวข้อครบทุกชุด 10 ภาพ')
    if any(not isinstance(beat, str) or not beat.strip() or len(beat) > 1500 for beat in beats):
        raise ValueError('หัวข้อแต่ละชุดต้องเป็นข้อความที่สมบูรณ์')
    if not isinstance(outline.get('video_title'), str) or not outline['video_title'].strip():
        raise ValueError('โครงเรื่องยังไม่มีชื่อคลิป')
    if not isinstance(outline.get('visual_bible'), (str, dict)) or not outline['visual_bible']:
        raise ValueError('โครงเรื่องยังไม่มีข้อมูลภาพจำ')
    entities = outline.get('story_entities')
    if not isinstance(entities, list) or len(entities) > 64:
        raise ValueError('รายชื่อตัวละครในโครงเรื่องไม่ถูกต้อง')
    ids = set()
    for entity in entities:
        if (not isinstance(entity, dict) or not isinstance(entity.get('id'), str)
                or not entity['id'].strip() or entity['id'] in ids
                or not isinstance(entity.get('name'), str) or not entity['name'].strip()
                or not isinstance(entity.get('aliases', []), list)
                or not isinstance(entity.get('visual_identity'), (str, dict))
                or not entity['visual_identity']):
            raise ValueError('ข้อมูลตัวละครในโครงเรื่องไม่ครบหรือซ้ำ')
        ids.add(entity['id'])
    return copy.deepcopy(outline)


def validate_chapter(chapter, job_id, scene_count, chapter_index):
    ranges = chapter_ranges(scene_count)
    if not 1 <= chapter_index <= len(ranges):
        raise ValueError('เลขชุดภาพไม่ถูกต้อง')
    start, end = ranges[chapter_index - 1]
    expected = end - start + 1
    if not isinstance(chapter, dict) or chapter.get('job_id') != job_id:
        raise ValueError('บทของชุดภาพไม่ตรงกับงาน')
    if chapter.get('chapter_index') != chapter_index:
        raise ValueError('บทของชุดภาพไม่ตรงลำดับ')
    for key in ('scene_prompts', 'scene_narrations', 'scene_durations', 'scene_entities'):
        values = chapter.get(key)
        if not isinstance(values, list) or len(values) != expected:
            raise ValueError(f'{key} ของชุด {chapter_index} ต้องมี {expected} รายการ')
    for key in ('scene_prompts', 'scene_narrations'):
        if any(not isinstance(value, str) or not value.strip() for value in chapter[key]):
            raise ValueError(f'{key} ของชุด {chapter_index} มีข้อความว่าง')
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
           for value in chapter['scene_durations']):
        raise ValueError('ระยะเวลาฉากของชุดภาพไม่ถูกต้อง')
    if any(not isinstance(value, list) or any(not isinstance(item, str) for item in value)
           for value in chapter['scene_entities']):
        raise ValueError('ตัวละครรายฉากของชุดภาพไม่ถูกต้อง')
    if not isinstance(chapter.get('continuity_summary'), str) or not chapter['continuity_summary'].strip():
        raise ValueError('ชุดภาพยังไม่มีสรุปส่งต่อชุดถัดไป')
    return copy.deepcopy(chapter)


def combine_chapters(outline, chapters, job_id, scene_count):
    outline = validate_outline(outline, job_id, scene_count)
    ranges = chapter_ranges(scene_count)
    if len(chapters) != len(ranges):
        raise ValueError('บทคลิปยาวยังไม่ครบทุกชุด')
    validated = [validate_chapter(chapter, job_id, scene_count, index)
                 for index, chapter in enumerate(chapters, 1)]
    scenes = {key: [value for chapter in validated for value in chapter[key]]
              for key in ('scene_prompts', 'scene_narrations', 'scene_durations', 'scene_entities')}
    return {
        'job_id': job_id,
        'video_title': outline['video_title'],
        'video_description': str(outline.get('video_description') or outline['video_title']),
        'hashtags': outline.get('hashtags') or [],
        'visual_bible': outline['visual_bible'],
        'story_entities': outline['story_entities'],
        'narration_script': ' '.join(scenes['scene_narrations']),
        'pronunciation_notes': outline.get('pronunciation_notes') if isinstance(outline.get('pronunciation_notes'), dict) else {},
        **scenes,
    }
