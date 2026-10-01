"""Read-only provider-specific diagnostics; never borrow an image worker's status."""
import re
from pathlib import Path
from urllib.parse import urlparse
from core.atomic_json import AtomicJsonFile


def safe_meta_url(value):
    parsed = urlparse(str(value or ''))
    if parsed.scheme == 'https' and parsed.netloc == 'www.meta.ai' and re.fullmatch(r'/(?:prompt/[\w-]+/?)?', parsed.path):
        return 'https://www.meta.ai' + parsed.path
    return ''


def story_service_label(job):
    kind = 'ละครสั้น AI' if job.get('series_id') else 'คลิปยาว' if job.get('long_video') else 'Story Shorts'
    provider = 'Gemini Web' if job.get('image_ai_provider') == 'gemini' else 'ChatGPT Web'
    mode = {'google_flow':'Google Flow', 'meta_ai':'Meta AI'}.get(job.get('video_generation_mode'), 'ประกอบวิดีโอในเครื่อง')
    return f'{kind} / {provider} / {mode}'


def read_meta_error(stories, job_id, message):
    if not re.fullmatch(r'STORY-[A-Za-z0-9-]+', job_id): return {}
    path = Path(stories.root) / job_id / 'prompts/meta_video_receipts.json'
    rows = list(AtomicJsonFile(path).peek(default={'scenes':{}}).get('scenes', {}).values())
    candidates = [row for row in rows if row.get('stage') == 'needs_attention'
                  and row.get('message') and row['message'] in message]
    if len(candidates) != 1: return {}
    row = candidates[0]
    return dict(index=row.get('index'), stage=row.get('stage'), message=row.get('message', ''),
                expected_url=safe_meta_url(row.get('conversation_url')),
                observed_url=safe_meta_url((row.get('page_diagnostic') or {}).get('observed_url')))
