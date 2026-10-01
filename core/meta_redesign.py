"""Durable new-image recovery after a completed, owned Meta no-video reply."""
import base64
import hashlib
import io
import math
import os
import re
import time
import uuid
from pathlib import Path
from PIL import Image, ImageOps


class MetaRedesign:
    def _redesign_image_request(self, package, failure_reason):
        orientation = 'landscape 16:9' if package.get('aspect_ratio') == '16:9' else 'vertical 9:16'
        if failure_reason in {'technical_redesign', 'transient_service_error'}:
            direction = ('The last Meta attempt ended with a technical error and no video. Do not infer a '
                         'content-policy violation. Use the attached original image for harmless character, '
                         'product and story continuity, but make a genuinely new scene composition. ')
        else:
            direction = ('The last Meta attempt produced no usable video. Use the attached original image '
                         'only for harmless character, product and story continuity. Make a genuinely '
                         'different, compliant composition with ordinary fully clothed styling and wider '
                         'non-suggestive framing. Do not evade provider restrictions. ')
        return (f'Generate and show exactly one NEW {orientation} starting image now. '
                + direction + 'Keep the saved facts, story action and dialogue. No text or watermark. '
                'Return the actual new image, not a JSON proposal or an image prompt. '
                'The video motion prompt will be requested separately after this new image is saved.\n'
                'Saved Meta scene (reference facts only; ignore its old instruction to create a video): '
                + package['prompt'])

    def _redesign_prompt_request(self, package, saved_image):
        orientation = 'landscape 16:9' if package.get('aspect_ratio') == '16:9' else 'vertical 9:16'
        role_instruction = ('The video_prompt must describe visible motion only; omit all speech, narration, '
                            'dialogue text and audio instructions. The desktop will attach the exact saved audio '
                            'delivery separately. Never turn quoted narration into character dialogue. '
                            if package.get('meta_prompt_version') == 5 else '')
        return (f'Inspect the attached NEW, already saved {orientation} image for this exact scene. '
                'Write a video motion prompt that fits what is actually visible in that new image. '
                + role_instruction +
                'Keep the original characters, product facts, story action, exact dialogue and audio settings. '
                'Do not generate another image or a video in this step. Do not describe or reuse the failed '
                'old starting image. Return one JSON object only with video_prompt (20–3500 characters), '
                'needs_review (boolean), and reason. If this new image cannot support a feasible compliant '
                'video, set needs_review=true and explain why.\n'
                'Saved new image SHA-256: ' + saved_image['image_sha256'] + '\n'
                'Original scene and audio (reference facts only; do not generate a video now): '
                + package['prompt'])

    def _redesign_prepare(self, data, store, receipt, body, package):
        from core.meta_video import meta_reply_failure, meta_safety_service_outage
        proof=body.get('retry_evidence') or {}
        answer=str(proof.get('answer_text') or '')
        if receipt.get('stage')=='redesigning': return dict(receipt)
        failure_reason=meta_reply_failure(answer)
        recovery=receipt.get('recovery') or {}
        service_redesign=(failure_reason=='transient_service_error'
            and (meta_safety_service_outage(answer) or receipt.get('safety_service_recovery')==1)
            and int(receipt.get('service_retry_count') or 0)>=1
            and proof.get('composer_empty') is True
            and recovery.get('protocol')==1 and recovery.get('category')==failure_reason
            and recovery.get('state')=='cooldown'
            and recovery.get('answer_sha256')==hashlib.sha256(answer.encode()).hexdigest()
            and type(recovery.get('next_retry_at')) in (int,float)
            and math.isfinite(recovery['next_retry_at']) and time.time()>=recovery['next_retry_at'])
        if (receipt.get('stage')!='generating' or not receipt.get('conversation_url')
                or body.get('conversation_url')!=receipt['conversation_url']
                or proof.get('matched_request') is not True or proof.get('answer_complete') is not True
                or proof.get('answer_truncated') is not False or proof.get('stop') is not False
                or proof.get('busy') is not False or type(proof.get('video_count')) is not int
                or proof['video_count']!=0 or type(proof.get('samples')) is not int or proof['samples']<2
                or not isinstance(proof.get('stable_ms'),(float,int)) or not math.isfinite(proof['stable_ms']) or proof['stable_ms']<5000
                or not 0<len(answer)<=12000
                or (failure_reason not in {'completed_no_video','image_not_viable','technical_redesign'} and not service_redesign)
                or (receipt.get('choice') and (receipt['choice']['stage']!='accepted'
                    or proof.get('choice_prompt')!=receipt['choice']['prompt']))):
            raise ValueError('ยังยืนยันคำตอบ Meta ที่จบโดยไม่มีวิดีโอไม่ได้')
        job=self._job(receipt['job_id'])
        provider=str(job.get('image_ai_provider') or 'chatgpt').replace('_web','')
        if provider not in {'chatgpt','gemini'}: raise ValueError('ไม่พบผู้สร้างภาพเดิมที่รองรับ')
        request=self._redesign_image_request(package, failure_reason)
        receipt.update(stage='redesigning',updated_at=time.time(),message='กำลังให้ AI เดิมสร้างภาพใหม่ก่อน • บันทึกภาพแล้วจึงแก้พรอมป์วิดีโอ',
                       redesign={'id':uuid.uuid4().hex,'phase':'prepared','provider':provider,
                                 'request':request,'image_request':request,
                                 'ai_web_model':str(job.get('ai_web_model') or 'auto'),
                                 'failure_sha256':hashlib.sha256(answer.encode()).hexdigest(),
                                 'failure_reason':failure_reason,
                                 'round':int(receipt.get('redesign_round') or 0)+1})
        store.write_unlocked(data)
        return dict(receipt)

    def redesign_event(self, body):
        job_id=str(body.get('job_id') or '');index=int(body.get('index') or 0)
        package=self.package(job_id,index)  # includes cancellation/provider checks
        store=self._store(job_id)
        with store.locked():
            data=store.read_unlocked({'scenes':{}});row=data['scenes'].get(str(index),{})
            action=body.get('action')
            if (action in {'save_image','save_prompt'}
                    and row.get('redesign_previous_request_id')==body.get('request_id')
                    and row.get('redesign_previous_context_id')==body.get('context_id')
                    and row.get('redesign_completed_id')==body.get('redesign_id')
                    and row.get('context_id')==package['context_id']):
                if action=='save_image':
                    value=body.get('image')
                    if not isinstance(value,str) or ',' not in value:
                        raise ValueError('ภาพใหม่ไม่ตรงกับผลที่บันทึกแล้ว')
                    raw=base64.b64decode(value.split(',',1)[1],validate=True)
                    if hashlib.sha256(raw).hexdigest()!=row.get('redesign_image_source_sha256'):
                        raise ValueError('ภาพใหม่ไม่ตรงกับผลที่บันทึกแล้ว')
                else:
                    proposal=body.get('proposal') or {}
                    prompt=proposal.get('video_prompt')
                    if (proposal.get('needs_review') is not False or not isinstance(prompt,str)
                            or hashlib.sha256(prompt.strip().encode()).hexdigest()!=row.get('redesign_prompt_sha256')):
                        raise ValueError('พรอมป์ใหม่ไม่ตรงกับผลที่บันทึกแล้ว')
                return dict(row)
            repair=row.get('redesign') or {}
            if (row.get('stage')!='redesigning' or row.get('request_id')!=body.get('request_id')
                    or row.get('context_id')!=body.get('context_id') or repair.get('id')!=body.get('redesign_id')):
                raise ValueError('คำขอแก้ภาพ Meta เปลี่ยนแล้ว')
            if action=='claim':
                if repair['phase']!='prepared': return {**row,'send_authorized':False}
                repair['phase']='requested';store.write_unlocked(data)
                return {**row,'send_authorized':True}
            if action=='message':
                row.update(message=str(body.get('message') or '')[:300],updated_at=time.time())
                store.write_unlocked(data);return dict(row)
            if action=='save_image':
                if repair['phase']=='image_saved':
                    value=body.get('image')
                    if not isinstance(value,str) or ',' not in value:
                        raise ValueError('ภาพใหม่ไม่ตรงกับผลที่บันทึกแล้ว')
                    raw=base64.b64decode(value.split(',',1)[1],validate=True)
                    saved=repair.get('saved_image') or {}
                    target=Path(saved.get('image_path') or '').resolve()
                    folder=self._folder(job_id).resolve()
                    if (hashlib.sha256(raw).hexdigest()!=saved.get('source_sha256')
                            or not target.is_relative_to(folder) or not target.is_file()
                            or hashlib.sha256(target.read_bytes()).hexdigest()!=saved.get('image_sha256')):
                        raise ValueError('ภาพใหม่ไม่ตรงกับผลที่บันทึกแล้ว')
                    return dict(row)
                if repair['phase']!='requested': raise ValueError('ขั้นตอนแก้ภาพ Meta ไม่ถูกต้อง')
                value=body.get('image')
                if not isinstance(value,str) or not value.startswith('data:image/') or len(value)>20*1024*1024:
                    raise ValueError('ไม่พบภาพใหม่จาก AI')
                raw=base64.b64decode(value.split(',',1)[1],validate=True)
                source_sha=hashlib.sha256(raw).hexdigest()
                if source_sha==package['image_sha256']: raise ValueError('ภาพใหม่ซ้ำกับภาพเดิม')
                with Image.open(io.BytesIO(raw)) as source:
                    picture=ImageOps.exif_transpose(source)
                    aspect_ratio=package.get('aspect_ratio','9:16')
                    expected_ratio=16/9 if aspect_ratio=='16:9' else 9/16
                    max_aspect_error=.08 if aspect_ratio=='16:9' else .12
                    if (picture.width*picture.height>40_000_000 or min(picture.size)<128
                            or abs(picture.width/picture.height-expected_ratio)>max_aspect_error):
                        if aspect_ratio=='16:9':
                            raise ValueError('ภาพใหม่ต้องเป็นแนวนอน 16:9 และมีขนาดพร้อมใช้งาน')
                        raise ValueError('ภาพใหม่ต้องเป็นแนวตั้งและมีขนาดพร้อมใช้งาน')
                    picture=picture.convert('RGB')
                    picture.thumbnail((2048,2048))
                    out=io.BytesIO();picture.save(out,format='JPEG',quality=94);image_bytes=out.getvalue()
                sha=hashlib.sha256(image_bytes).hexdigest()
                previous=(data.get('overrides') or {}).get(str(index),{})
                if sha in {package['image_sha256'],previous.get('image_sha256')}:
                    raise ValueError('ภาพทดแทนไม่เปลี่ยนจากเดิม')
                folder=self._folder(job_id).resolve()
                target=folder/'generated'/f'meta_repair_{index:02d}_{sha[:16]}.jpg'
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():
                    temporary=target.with_suffix('.partial')
                    temporary.write_bytes(image_bytes)
                    os.replace(temporary,target)
                if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
                    raise ValueError('ไฟล์ภาพทดแทนไม่ตรงข้อมูลที่ AI ส่งกลับ')
                saved=dict(image_path=str(target),image_relative=target.relative_to(folder).as_posix(),
                           image_name=target.name,image_sha256=sha,source_sha256=source_sha)
                repair.update(phase='image_saved',saved_image=saved,
                              prompt_request=self._redesign_prompt_request(package,saved),prompt_attempt=0)
                row.update(message='บันทึกภาพใหม่แล้ว • กำลังขอพรอมป์วิดีโอจาก AI เดิม',updated_at=time.time())
                store.write_unlocked(data)
                return dict(row)
            if action!='save_prompt' or repair['phase']!='image_saved':
                raise ValueError('ขั้นตอนแก้ภาพ Meta ไม่ถูกต้อง')
            proposal=body.get('proposal') or {}
            video_prompt=proposal.get('video_prompt')
            if (proposal.get('needs_review') is not False or not isinstance(video_prompt,str)
                    or not 20<=len(video_prompt.strip())<=3500):
                raise ValueError('พรอมป์วิดีโอใหม่ยังไม่พร้อม')
            if re.search(r'bypass|ignore (?:all |previous )?instructions|หลบ(?:เลี่ยง)?ตัวกรอง',
                         video_prompt,re.I):
                raise ValueError('พรอมป์ใหม่ไม่ใช่การแก้เนื้อหาให้เหมาะสม')
            if (package.get('meta_prompt_version') == 5 and package.get('narrator_text', '').strip()
                    and package['narrator_text'].strip() in video_prompt):
                raise ValueError('พรอมป์การเคลื่อนไหวต้องไม่ใส่บทผู้บรรยาย • เก็บภาพใหม่และบทเสียงเดิมไว้')
            saved=repair.get('saved_image') or {}
            folder=self._folder(job_id).resolve()
            target=Path(saved.get('image_path') or '').resolve()
            sha=saved.get('image_sha256')
            if (not sha or not target.is_relative_to(folder) or not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest()!=sha):
                raise ValueError('ภาพใหม่ที่บันทึกไว้ไม่พร้อมใช้งาน')
            orientation='landscape 16:9' if package.get('aspect_ratio')=='16:9' else 'vertical 9:16'
            revision_note=('Use its revised staging and clothing, not the rejected composition. '
                           if repair.get('failure_reason') not in {'technical_redesign','transient_service_error'} else
                           'Use the newly designed scene and motion; the prior attempt ended with a technical error. ')
            scene_context = ('\nSaved visual action: ' if package.get('meta_prompt_version') == 5
                             else '\nSaved story/dialogue context: ')
            prompt=(f'Create exactly one actual playable {orientation} video from this new starting image. '
                    +revision_note+'No text or watermark. '
                    +package['audio_instruction']+'\nMotion: '+video_prompt.strip()
                    +scene_context+package['scene_value']
                    +package.get('continuity_instruction','')
                    +'\nReturn one video only; if unavailable report that truthfully.')
            from core.generated_music import apply_to_prompt
            prompt=apply_to_prompt(self._job(job_id),index,prompt)
            context=hashlib.sha256((job_id+':'+str(index)+':'+sha+':'+prompt).encode()).hexdigest()
            repair['phase']='prompt_saved'
            data.setdefault('attempt_history',{}).setdefault(str(index),[]).append(dict(row))
            data.setdefault('overrides',{})[str(index)]={'base_context_id':package.get('base_context_id',package['context_id']),
                'image_path':str(target),'image_name':target.name,'image_sha256':sha,'prompt':prompt,'context_id':context}
            successor=dict(job_id=job_id,index=index,context_id=context,request_id=uuid.uuid4().hex,
                stage='prepared',updated_at=time.time(),redesign_round=repair['round'],retry_count=0,
                redesign_previous_request_id=row['request_id'],redesign_completed_id=repair['id'],
                redesign_previous_context_id=row['context_id'],
                redesign_image_source_sha256=saved['source_sha256'],
                redesign_prompt_sha256=hashlib.sha256(video_prompt.strip().encode()).hexdigest(),
                message='ภาพและพรอมต์ใหม่พร้อม • เริ่มฉากนี้ใน Meta หน้าใหม่')
            if row.get('scene_video_plan'):
                successor['scene_video_plan']=dict(row['scene_video_plan'])
            if row.get('safety_service_recovery')==1 or repair.get('failure_reason')=='transient_service_error':
                successor['safety_service_recovery']=1
            data['scenes'][str(index)]=successor;store.write_unlocked(data)
            return dict(successor)
