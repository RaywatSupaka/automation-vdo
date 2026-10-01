"""Post-video AI covers. Independent durable requests; never mutate video media."""
import base64
import io
import re
import time
import uuid
from functools import wraps
from pathlib import Path
from PIL import Image, ImageOps
from core.atomic_json import AtomicJsonFile
from core.clip_cover import image_choices, cover_settings
from core.job_file_guard import guard_for


def _claim_cover_files(by_request=False):
    """Use the same start/delete lock before acquiring the cover ledger lock."""
    def decorate(method):
        @wraps(method)
        def guarded(self, *args, **kwargs):
            identity = args[0] if args else kwargs['rid' if by_request else 'job_id']
            job_id = self.get(identity)['job_id'] if by_request else identity
            with guard_for(Path(self.products.root).parent.parent).start(job_id):
                return method(self, *args, **kwargs)
        return guarded
    return decorate


def ai_cover_options(value=None):
    value = value if isinstance(value, dict) else {}
    text = str(value.get('headline') or '').strip()
    if len(text) > 40 or '\n' in text:
        raise ValueError('ข้อความปกต้องเป็นวลีสั้นไม่เกิน 40 ตัวอักษร')
    index = value.get('scene_index', 0)
    if type(index) is not int or not 0 <= index <= 50:
        raise ValueError('เลขภาพปกไม่ถูกต้อง')
    return dict(enabled=value.get('enabled') is True, headline=text, scene_index=index)


class AICovers:
    TERMINAL = {'ready', 'needs_review', 'cancelled'}
    PREPARATION_REASONS = {'composer_not_ready', 'opener_missing', 'opener_disabled',
        'menu_missing', 'menu_ambiguous', 'option_detached', 'chip_unconfirmed',
        'response_active', 'draft_changed', 'owner_changed', 'conversation_not_empty',
        'attachment_present', 'upload_busy', 'upload_failed', 'tool_pending', 'ready'}

    @staticmethod
    def _state(row):
        return {k:row[k] for k in ('request_id', 'phase', 'message', 'provider',
            'reference_proof', 'result_proof', 'collector_state', 'collect_only',
            'send_state', 'send_diagnostics', 'preparation_state', 'error_code',
            'notDispatched', 'successor_request_id', 'parent_request_id',
            'download_failure', 'download_replacement_count') if k in row}

    @staticmethod
    def _has_send_evidence(row):
        detail = row.get('send_diagnostics') or {}
        collector = row.get('collector_state') or {}
        return (row.get('send_state') in {'accepted', 'unconfirmed'}
            or any(detail.get(k) is True for k in (
                'dispatch_completed', 'trusted_click_seen', 'release_on_send_target'))
            or detail.get('gesture_phase') in {'pressed', 'released', 'release_uncertain'}
            or bool(row.get('result_proof')) or collector.get('owned') is True
            or bool(collector.get('candidates')) or bool(row.get('retry_count')))

    @classmethod
    def _not_dispatched(cls, row):
        state = row.get('preparation_state') or {}
        return (state.get('stage') == 'image_tool' and state.get('request_id') == row.get('request_id')
            and state.get('not_dispatched') is True and not cls._has_send_evidence(row))

    def __init__(self, products, stories=None):
        self.products, self.stories = products, stories

    @property
    def store(self):
        # Bridge command-only adapters need no media store until cover work.
        return AtomicJsonFile(Path(self.products.root).parent / 'ai_cover_requests.json')

    def folder(self, job_id):
        if not re.fullmatch(r'(?:STORY|JOB)-[A-Z0-9-]+', str(job_id)):
            raise ValueError('รหัสงานปกไม่ถูกต้อง')
        manager = self.stories if job_id.startswith('STORY-') else self.products
        if manager is None:
            raise ValueError('ไม่พบคลังงาน')
        root = Path(manager.root).resolve()
        folder = (root / job_id).resolve()
        if folder.parent != root or not (folder / 'job.json').is_file():
            raise ValueError('ไม่พบงานปก')
        return folder

    def get(self, request_id):
        row = self.store.read({}).get(str(request_id))
        if not row:
            raise ValueError('ไม่พบคำขอปก')
        return row

    @_claim_cover_files()
    def request(self, job_id, force=False, options=None):
        folder = self.folder(job_id)
        manifest = AtomicJsonFile(folder / 'job.json').read()
        settings = ai_cover_options(options if options is not None else manifest.get('ai_cover_options'))
        if not settings['enabled']:
            return None
        video = (folder / str(manifest.get('video_path') or '')).resolve()
        if folder not in video.parents or not video.is_file() or not video.stat().st_size:
            raise ValueError('ต้องมีวิดีโอสำเร็จก่อนสร้างปก AI')
        choices = image_choices(folder, manifest)
        cover = cover_settings(manifest, choices)
        index = settings['scene_index'] or cover['scene_index']
        source = next((path for number, path in choices if number == index), None)
        if source is None:
            raise ValueError('ไม่พบภาพที่สร้างสำเร็จสำหรับทำปก')
        sources = [source] + [path for _, path in choices if path != source][:1]
        provider = manifest.get('image_ai_provider') or 'chatgpt'
        if provider not in {'chatgpt', 'gemini'}:
            raise ValueError('ผู้ให้บริการของงานไม่ถูกต้อง')
        title = str(manifest.get('video_title') or manifest.get('topic') or manifest.get('product_name') or manifest.get('title') or 'คลิปนี้')[:500]
        headline = settings['headline']
        ratio = '16:9' if manifest.get('aspect_ratio') == '16:9' or manifest.get('long_video') else '9:16'
        with self.store.locked():
            records = self.store.read_unlocked({})
            previous = [r for r in records.values() if r['job_id'] == job_id]
            if previous:
                latest = max(previous, key=lambda r: r['created_at'])
                if not force or latest['phase'] not in self.TERMINAL:
                    return latest
            rid = uuid.uuid4().hex
            row = dict(request_id=rid, job_id=job_id, provider=provider, phase='queued',
                       ai_web_model=str(manifest.get('ai_web_model') or 'auto'),
                       source=str(source.relative_to(folder)), scene_index=index,
                       sources=[str(path.relative_to(folder)) for path in sources],
                       title=title, headline=headline, aspect_ratio=ratio, created_at=time.time(), updated_at=time.time(),
                       previous_cover_revision=manifest.get('cover_revision'), retry_count=0,
                       single_image_only=True, cover_prompt_version=2)
            records[rid] = row
            self.store.write_unlocked(records)
            AtomicJsonFile(folder / 'job.json').update(lambda current: {**current,
                'ai_cover_state':dict(request_id=rid, phase='queued', message='รอสร้างปก AI', provider=provider)})
        return row

    def pending(self):
        return [r for r in self.store.read({}).values() if r['phase'] == 'queued'][:1]

    @_claim_cover_files(by_request=True)
    def recover_result(self, rid, job_id):
        """Explicit collect-only recovery of the SAME request; never resubmit."""
        with self.store.locked():
            records = self.store.read_unlocked({})
            row = records.get(str(rid))
            if not row or row['job_id'] != job_id:
                raise ValueError('คำขอปกไม่ตรงงาน')
            latest = max((r for r in records.values() if r['job_id'] == job_id), key=lambda r:r['created_at'])
            if latest['request_id'] != rid:
                raise ValueError('มีคำขอปกใหม่กว่าแล้ว • ไม่ดึงปกเก่ามาทับ')
            if row['phase'] != 'needs_review':
                raise ValueError('ดึงปกเดิมได้เฉพาะงานที่พักรอตรวจ • ไม่ทำซ้อนหรือเปิดงานที่ยกเลิก')
            if self._not_dispatched(row):
                raise ValueError('ปกนี้ยังไม่ส่งคำขอ • ใช้ทำปกต่อเพื่อเตรียมสร้างปก')
            self.folder(job_id)
            history = list(row.get('collection_history') or [])
            history.append({'at':time.time(), 'previous_message':row.get('message','')[:500]})
            row.update(phase='queued', collect_only=True, updated_at=time.time(), active=False,
                       message='รอดึงภาพปกจากคำตอบเดิม • ไม่ส่งพรอมต์หรือสร้างภาพซ้ำ', collection_history=history[-10:])
            records[rid] = row
            self.store.write_unlocked(records)
            AtomicJsonFile(self.folder(job_id)/'job.json').update(lambda manifest:{**manifest,
                'ai_cover_state':self._state(row)})
            return row

    def active(self):
        return [r for r in self.store.read({}).values() if r['phase'] not in self.TERMINAL]

    def completion(self, job_id):
        """Read-only queue gate: saved video and terminal cover are not synonyms."""
        folder = self.folder(job_id)
        # Same lock order as event(): otherwise an old manifest plus a newly
        # ready ledger can falsely look like a missing image at the save boundary.
        with self.store.locked():
            records = [r for r in self.store.read_unlocked({}).values() if r.get('job_id') == job_id]
            manifest = AtomicJsonFile(folder / 'job.json').read()
        if not ai_cover_options(manifest.get('ai_cover_options'))['enabled']:
            return dict(ready=True, required=False, phase='disabled', message='')
        state = manifest.get('ai_cover_state') or {}
        row = max(records, key=lambda r: r.get('created_at', 0)) if records else state
        phase, rid = row.get('phase', 'missing'), row.get('request_id', '')
        ready = False
        if phase == 'ready' and rid:
            # A retained old/manual cover alone does not prove this AI request
            # finished. The exact saved history file does; manual edits win.
            paths = [r.get('path') for r in manifest.get('ai_cover_history', [])
                     if r.get('request_id') == rid]
            if manifest.get('cover_revision') == rid:
                paths.append(manifest.get('cover_path'))
            for relative in paths:
                target = (folder / str(relative or '')).resolve()
                if folder in target.parents and target.is_file() and target.stat().st_size > 0:
                    ready = True
                    break
        waiting = phase in {'queued', 'claimed', 'preparing', 'recovering', 'running'}
        message = '' if ready else ('วิดีโอเสร็จแล้ว • กำลังเตรียมสร้างปก • ยังไม่เริ่มหัวข้อถัดไป'
            if phase in {'preparing', 'recovering'} else 'วิดีโอเสร็จแล้ว • รอปก AI • ยังไม่เริ่มหัวข้อถัดไป' if waiting else
            'วิดีโอเสร็จแล้ว • พักคิวรอปก AI • เปิดจัดการปก AI เพื่อดึงปกเดิมหรือสร้างปกใหม่ • เมื่อบันทึกปกสำเร็จแล้วจึงกด Run Queue ต่อ')
        if not ready and row.get('message'):
            message += ' • ' + str(row['message'])[:500]
        return dict(ready=ready, required=True, phase=phase, waiting=waiting,
                    request_id=rid, message=message)

    def recover_startup(self):
        # Preserve unknown outcomes after restart; never reset the Send budget.
        for row in self.active():
            self.event(row['request_id'],{'phase':'needs_review','message':'โปรแกรมถูกเปิดใหม่ • ตรวจปกเดิมก่อนสั่งสร้างใหม่'})

    def package(self, rid):
        row = self.get(rid)
        if row.get('collect_only'):
            return row  # Existing reply recovery needs identity, not re-upload bytes.
        if row.get('sources'):
            images = [self._image_data(row, relative) for relative in row['sources']]
            if not 1 <= len(images) <= 2:
                raise ValueError('ปก AI ต้องมีรูปอ้างอิง 1–2 รูป')
            return {**row, 'source_images': images, 'source_data': images[0]}
        return {**row, 'source_data': self._image_data(row, row['source'])}

    def _image_data(self, row, relative):
        source = (self.folder(row['job_id']) / relative).resolve()
        if self.folder(row['job_id']) not in source.parents:
            raise ValueError('รูปอยู่นอกงาน')
        if source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('รูปต้นแบบใหญ่เกินไป')
        with Image.open(source) as image:
            image.load()
            buffer = io.BytesIO()
            image.convert('RGB').save(buffer, 'JPEG', quality=94)
        return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')

    def _download_replacement(self, parent, records, event):
        """A completed owned image download may create one durable successor."""
        failure = event['download_failure']
        proof = parent.get('result_proof') or {}
        collector = parent.get('collector_state') or {}
        if (event.get('phase') != 'needs_review' or parent['phase'] not in {'claimed', 'running'}
                or not isinstance(failure, dict) or set(failure) != {'attempts', 'owned', 'idle'}
                or type(failure.get('attempts')) is not int or failure['attempts'] != 3
                or failure.get('owned') is not True or failure.get('idle') is not True
                or proof.get('request_id') != parent['request_id']
                or proof.get('scope') != 'latest_assistant_turn'
                or type(proof.get('images')) is not int or proof['images'] != 1
                or any(type(proof.get(k)) is not int or not 256 <= proof[k] <= 20000
                       for k in ('width', 'height'))
                or collector.get('stage') != 'downloading' or collector.get('owned') is not True
                or type(collector.get('loaded')) is not int or collector['loaded'] < 1
                or type(collector.get('candidates')) is not int
                or not collector['loaded'] <= collector['candidates'] <= 10):
            raise ValueError('ยังไม่มีหลักฐานว่าดาวน์โหลดภาพปกของคำขอนี้ไม่สำเร็จจริง')
        latest = max((r for r in records.values() if r['job_id'] == parent['job_id']),
                     key=lambda r: r['created_at'])
        if latest['request_id'] != parent['request_id']:
            raise ValueError('มีคำขอปกใหม่กว่าแล้ว • ไม่สร้างปกซ้ำ')
        manifest = AtomicJsonFile(self.folder(parent['job_id']) / 'job.json').read()
        if manifest.get('cover_revision') != parent['previous_cover_revision']:
            raise ValueError('ปกถูกแก้ไขระหว่างทำงาน • ไม่สร้างปกใหม่แทน')
        count = parent.get('download_replacement_count', 0)
        if type(count) is not int or count < 0:
            raise ValueError('ประวัติการดาวน์โหลดปกไม่ถูกต้อง')
        rid = uuid.uuid4().hex
        stamp = max(time.time(), parent['created_at'] + .000001)
        child = {k:parent[k] for k in ('job_id', 'provider', 'ai_web_model', 'source',
            'sources', 'scene_index', 'title', 'headline', 'aspect_ratio', 'prompt',
            'previous_cover_revision', 'cover_prompt_version') if k in parent}
        child.update(request_id=rid, phase='queued', created_at=stamp, updated_at=stamp,
                     retry_count=0, parent_request_id=parent['request_id'],
                     download_replacement_count=count + 1, single_image_only=True,
                     message='ดาวน์โหลดปกเดิมไม่สำเร็จ • รอสร้างปกใหม่หนึ่งภาพ')
        records[rid] = child
        return child

    @_claim_cover_files(by_request=True)
    def event(self, rid, event):
        with self.store.locked():
            records = self.store.read_unlocked({})
            row = records.get(rid)
            if not row:
                raise ValueError('ไม่พบคำขอปก')
            if row['phase'] in self.TERMINAL:
                return row
            # Only previously acknowledged result/download evidence authorizes
            # a fresh request; fields supplied with this failure cannot invent it.
            download_parent = dict(row) if 'download_failure' in event else None
            phase = event.get('phase')
            if phase == 'claimed':
                if row['phase'] != 'queued':
                    raise ValueError('คำขอปกนี้ถูกรับไปแล้ว ห้ามส่งซ้ำ')
            elif phase not in {'preparing', 'recovering', 'running', 'ready', 'needs_review', 'cancelled'}:
                raise ValueError('สถานะปกไม่ถูกต้อง')
            retry = event.get('retry_count', row.get('retry_count', 0))
            if 'send_diagnostics' in event:
                detail = event['send_diagnostics']
                if not isinstance(detail, dict):
                    raise ValueError('หลักฐานการส่งปกไม่ถูกต้อง')
                previous_detail = row.get('send_diagnostics') or {}
                row['send_diagnostics'] = {**previous_detail, **{k:v for k,v in detail.items()
                    if k in {'dispatch_completed','trusted_click_seen','release_on_send_target','target_stable_before_press'}
                    and type(v) is bool}}
                if detail.get('gesture_phase') in {'not_started','pressed','released','release_uncertain'}:
                    row['send_diagnostics']['gesture_phase'] = detail['gesture_phase']
                # Later observations cannot erase evidence of a physical Send.
                for key in ('dispatch_completed', 'trusted_click_seen', 'release_on_send_target'):
                    if previous_detail.get(key) is True:
                        row['send_diagnostics'][key] = True
                if (previous_detail.get('gesture_phase') in {'pressed', 'released', 'release_uncertain'}
                        and row['send_diagnostics'].get('gesture_phase') == 'not_started'):
                    row['send_diagnostics']['gesture_phase'] = previous_detail['gesture_phase']
            if 'send_state' in event:
                if event['send_state'] not in {'unconfirmed', 'accepted'}:
                    raise ValueError('สถานะการส่งปกไม่ถูกต้อง')
                row['send_state'] = event['send_state']
            if type(retry) is not int or not row.get('retry_count',0) <= retry <= 1:
                raise ValueError('เกินสิทธิ์ลองสร้างปกใหม่')
            row['retry_count'] = retry
            if 'reference_chain' in event:
                chain = event['reference_chain']
                expected = len(row.get('sources') or [row['source']])
                url_pattern = (r'https://chatgpt\.com/c/[A-Za-z0-9-]+'
                    if row['provider'] == 'chatgpt' else r'https://gemini\.google\.com/app/[a-fA-F0-9]{16}')
                def valid_user(user, index):
                    return (isinstance(user, dict) and set(user) == {'index', 'id'}
                        and type(user.get('index')) is int and user['index'] == index
                        and isinstance(user.get('id'), str) and 1 <= len(user['id']) <= 250
                        and re.fullmatch(r'[\w:.-]+', user['id'], flags=re.ASCII))
                if (not isinstance(chain, dict) or set(chain) != {'version','request_id','provider',
                        'conversation_url','reference_count','reference_user','retry_user'}
                    or type(chain.get('version')) is not int or chain['version'] != 1
                    or chain.get('request_id') != rid or chain.get('provider') != row['provider']
                    or not isinstance(chain.get('conversation_url'), str)
                    or not re.fullmatch(url_pattern, chain['conversation_url'])
                    or type(chain.get('reference_count')) is not int or chain['reference_count'] != expected
                    or not valid_user(chain.get('reference_user'), 0) or retry != 1
                    or (chain.get('retry_user') is not None and
                        (not valid_user(chain['retry_user'], 1)
                         or chain['retry_user']['id'] == chain['reference_user']['id']))):
                    raise ValueError('หลักฐานข้อความลองปกใหม่ไม่ตรงคำขอและรูปอ้างอิงเดิม')
                previous = row.get('reference_chain')
                if not previous and chain.get('retry_user') is not None:
                    raise ValueError('ยังไม่มีใบรับรูปอ้างอิงก่อนส่งข้อความลองปกใหม่')
                if previous and (any(previous[k] != chain[k] for k in previous if k != 'retry_user')
                    or previous.get('retry_user') and previous['retry_user'] != chain['retry_user']):
                    raise ValueError('เจ้าของข้อความลองปกใหม่เปลี่ยน • เก็บใบรับเดิม')
                row['reference_chain'] = {**chain, 'reference_user':dict(chain['reference_user']),
                    'retry_user':dict(chain['retry_user']) if chain['retry_user'] else None}
            if 'preparation_state' in event:
                state = event['preparation_state']
                previous = row.get('preparation_state') or {}
                if (not isinstance(state, dict) or state.get('stage') != 'image_tool'
                        or state.get('request_id') != rid or state.get('not_dispatched') is not True
                        or type(state.get('reason')) is not str or state['reason'] not in self.PREPARATION_REASONS
                        or type(state.get('attempt')) is not int or not 0 <= state['attempt'] <= 1000000
                        or state['attempt'] < previous.get('attempt', 0)
                        or row.get('collect_only') or self._has_send_evidence(row)
                        or retry or event.get('result_proof')):
                    raise ValueError('หลักฐานเตรียมปกก่อนส่งไม่ตรงคำขอหรือมีการส่งแล้ว')
                row['preparation_state'] = {k:state[k] for k in (
                    'stage', 'reason', 'attempt', 'not_dispatched', 'request_id')}
                if 'checks' in state:
                    checks = state['checks']
                    boolean_keys = ('owner_current', 'composer_ready', 'draft_present',
                        'attachment_busy', 'attachment_failed', 'response_active')
                    count_keys = ('user_turns', 'assistant_turns', 'attachment_count')
                    if (not isinstance(checks, dict) or set(checks) != set(boolean_keys + count_keys)
                            or any(type(checks[k]) is not bool for k in boolean_keys)
                            or any(type(checks[k]) is not int or not 0 <= checks[k] <= 1000
                                   for k in count_keys)):
                        raise ValueError('ข้อมูลตรวจการเตรียมปกไม่ถูกต้อง')
                    # Diagnostic observations only; the request-bound no-Send
                    # proof above remains the authority, including for legacy448.
                    row['preparation_state']['checks'] = {
                        k:checks[k] for k in boolean_keys + count_keys}
                row['notDispatched'] = True
            if phase in {'preparing', 'recovering'} and not self._not_dispatched(row):
                raise ValueError('ยังไม่มีหลักฐานเตรียมปกที่ยืนยันว่าไม่ส่งคำขอ')
            if 'error_code' in event:
                if event['error_code'] != 'AI_SEND_NOT_READY':
                    raise ValueError('รหัสข้อผิดพลาดการเตรียมปกไม่ถูกต้อง')
                row['error_code'] = event['error_code']
            if 'notDispatched' in event:
                if event['notDispatched'] is not True or not self._not_dispatched(row):
                    raise ValueError('ยังยืนยันไม่ได้ว่าปกนี้ไม่ส่งคำขอ')
                row['notDispatched'] = True
            if (row.get('preparation_state') or {}).get('reason') == 'ready' and 'error_code' not in event:
                row.pop('error_code', None)
            # Store only bounded attachment evidence, never source bytes, URLs,
            # filenames or arbitrary browser data. Optional for legacy requests.
            if 'reference_proof' in event:
                proof = event['reference_proof']
                expected = len(row.get('sources') or [row['source']])
                if (not isinstance(proof, dict)
                    or proof.get('status') not in {'verified', 'review'}
                    or type(proof.get('expected')) is not int or proof['expected'] != expected
                    or type(proof.get('loaded')) is not int or not 0 <= proof['loaded'] <= 10
                    or proof.get('method') not in {'none', 'filename', 'input_files'}
                    or proof.get('reason') not in {'ready', 'owner_changed', 'upload_failed', 'files_changed',
                                                 'upload_busy', 'preview_incomplete', 'identity_missing', 'preview_unstable'}
                    or (proof['status'] == 'verified' and (proof['loaded'] != expected
                        or proof['method'] == 'none' or proof['reason'] != 'ready'))):
                    raise ValueError('หลักฐานรูปอ้างอิงปกไม่ตรงคำขอ')
                row['reference_proof'] = {k:proof[k] for k in ('status','expected','loaded','method','reason')}
                # Optional live attachment diagnostics, bounded and content-free.
                # Readiness still requires a saved cover image, never these counts.
                for key, maximum in (('observed', 10), ('elapsed_ms', 120000)):
                    if key in proof:
                        if type(proof[key]) is not int or not 0 <= proof[key] <= maximum:
                            raise ValueError('สถานะการรอรูปอ้างอิงปกไม่ถูกต้อง')
                        row['reference_proof'][key] = proof[key]
            if 'collector_state' in event:
                state = event['collector_state']
                if (not isinstance(state, dict)
                    or state.get('stage') not in {'request_missing', 'answer_missing', 'generating', 'multiple_images',
                                                  'waiting_image', 'loading_image', 'stabilizing', 'downloading'}
                    or type(state.get('owned')) is not bool
                    or any(type(state.get(k)) is not int or not 0 <= state[k] <= 10 for k in ('candidates', 'loaded'))
                    or state['loaded'] > state['candidates']):
                    raise ValueError('สถานะตัวอ่านปกไม่ถูกต้อง')
                row['collector_state'] = {k:state[k] for k in ('stage', 'owned', 'candidates', 'loaded')}
            if 'result_proof' in event:
                proof = event['result_proof']
                if (not isinstance(proof, dict) or proof.get('request_id') != rid
                    or proof.get('scope') != 'latest_assistant_turn' or type(proof.get('images')) is not int or proof['images'] != 1
                    or any(type(proof.get(k)) is not int or not 256 <= proof[k] <= 20000 for k in ('width','height'))):
                    raise ValueError('หลักฐานภาพปกไม่ตรงคำตอบของงานนี้')
                row['result_proof'] = {k:proof[k] for k in ('request_id','scope','images','width','height')}
            if ((phase in {'preparing', 'recovering'} or 'preparation_state' in event
                    or event.get('notDispatched') is True) and self._has_send_evidence(row)):
                raise ValueError('มีหลักฐานการส่งปกแล้ว • ไม่ย้อนกลับไปเตรียมก่อนส่ง')
            replacement = None
            if download_parent is not None:
                replacement = self._download_replacement(download_parent, records, event)
                row['download_failure'] = {k:event['download_failure'][k] for k in ('attempts', 'owned', 'idle')}
                row['successor_request_id'] = replacement['request_id']
            if phase == 'ready':
                if row['phase'] not in {'claimed', 'preparing', 'recovering', 'running'}:
                    raise ValueError('ยังไม่ได้เริ่มคำขอปก')
                if row.get('collect_only') and not row.get('result_proof'):
                    raise ValueError('ยังไม่มีหลักฐานภาพจากคำตอบเดิม • ไม่บันทึกปก')
                raw = str(event.get('image') or '')
                if not re.match(r'^data:image/(?:png|jpeg|webp);base64,', raw):
                    raise ValueError('ข้อมูลภาพปกไม่ถูกต้อง')
                data = base64.b64decode(raw.split(',', 1)[1], validate=True)
                if len(data) > 25 * 1024 * 1024:
                    raise ValueError('ไฟล์ปกใหญ่เกินไป')
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 40000000:
                        raise ValueError('ภาพใหญ่เกินไป')
                    expected = 16/9 if row['aspect_ratio'] == '16:9' else 9/16
                    ratio = image.width/image.height
                    if min(image.size) < 256 or not ((1.3 <= ratio <= 2.2) if expected > 1 else (.4 <= ratio <= .8)):
                        raise ValueError('ขนาดหรือสัดส่วนปกไม่ตรงคำขอ')
                    image.load()
                    folder = self.folder(row['job_id'])
                    target = folder / 'covers' / f'ai_cover_{rid}.jpg'
                    target.parent.mkdir(exist_ok=True)
                    size = (1920,1080) if expected > 1 else (1080,1920)
                    # Some providers return2:3 despite a9:16 request. Pad, never
                    # crop away the headline/face, and publish the exact job ratio.
                    ImageOps.pad(image.convert('RGB'), size, color=(12,15,24)).save(target, 'JPEG', quality=95)
                store = AtomicJsonFile(folder / 'job.json')
                def apply(manifest):
                    history = list(manifest.get('ai_cover_history') or [])
                    relative = str(target.relative_to(folder))
                    if not any(r.get('request_id') == rid for r in history):
                        history.append(dict(request_id=rid, path=relative, previous_path=manifest.get('cover_path'), provider=row['provider']))
                    manifest['ai_cover_history'] = history
                    # A manual cover edit during generation must win.
                    if manifest.get('cover_revision') == row['previous_cover_revision']:
                        manifest.update(cover_path=relative, cover_status='ready', cover_size=list(size),
                                        cover_revision=rid, cover_renderer='ai-web-cover-v1')
                    return manifest
                store.update(apply)
            row['retry_count'] = retry
            if self._has_send_evidence(row) or phase == 'ready':
                if row.get('preparation_state'):
                    row['preparation_state'] = {**row['preparation_state'], 'not_dispatched':False}
                row['notDispatched'] = False
                row.pop('error_code', None)
            row.update(phase=phase, updated_at=time.time(), message=str(event.get('message') or '')[:500], active=event.get('active') is True)
            records[rid] = row
            self.store.write_unlocked(records)
            try:
                folder = self.folder(row['job_id'])
            except ValueError:
                if phase in self.TERMINAL:
                    return row  # Deleted jobs cannot block engine startup/recovery.
                raise
            AtomicJsonFile(folder / 'job.json').update(lambda manifest: {
                **manifest, 'ai_cover_state':self._state(replacement or row)})
            return row
