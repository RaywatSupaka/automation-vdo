import json
import os
import shutil
import threading
from core.story_styles import normalize_story_style
from core.drama_options import drama_render_options
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.ai_web_models import normalize_ai_web_model
from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path


def generated_drama_cast(value):
    """Validate a first-episode AI cast before it becomes series identity."""
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ValueError('ละครสั้นที่ไม่ได้กำหนดตัวละครต้องให้ AI สร้างข้อมูลตัวละคร 1–4 คน')
    result, seen = [], set()
    for index, raw in enumerate(value, 1):
        if not isinstance(raw, dict):
            raise ValueError('ข้อมูลตัวละครที่ AI สร้างไม่ถูกต้อง')
        name = str(raw.get('name') or '').strip()
        description = str(raw.get('description') or raw.get('appearance') or '').strip()
        if (not name or not description or len(name) > 80 or len(description) > 1200
                or name.casefold() in seen or name.casefold() in {'ผู้บรรยาย', 'narrator', 'voiceover'}):
            raise ValueError('AI ต้องระบุชื่อและลักษณะตัวละครที่ไม่ซ้ำก่อนเริ่มสร้างภาพ')
        seen.add(name.casefold())
        result.append({'id': f'CHAR-{index:02d}', 'name': name,
                       'role': 'ตัวละครหลัก' if index == 1 else 'ตัวละครร่วม',
                       'description': description, 'source_image': '',
                       'voice_reference_id': '', 'voice_label': ''})
    return result


class DramaSeriesManager:
    """Persistent series bible and episode continuity for Drama Shorts."""

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    MAX_EPISODES = 20
    COVER_THEMES = {"cinematic", "romance", "thriller", "clean"}

    def __init__(self, root):
        self.project_root = Path(root).resolve()
        self.root = self.project_root / "workspace" / "drama_series"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    def create(
        self,
        title,
        premise="",
        episode_count=3,
        scene_count=10,
        provider="chatgpt",
        characters=None,
        footage=None,
        plot_board=None,
        cover_theme="cinematic",
        ai_web_model="",
        visual_style="auto",
        visual_style_custom="",
        render_options=None,
    ):
        visual_style, visual_style_custom = normalize_story_style(visual_style, visual_style_custom)
        options = drama_render_options(render_options) if render_options is not None else None
        title = str(title or "").strip()
        premise = str(premise or "").strip()
        if not title:
            raise ValueError("กรุณาใส่ชื่อเรื่องละครสั้น")
        episode_count = max(1, min(self.MAX_EPISODES, int(episode_count or 3)))
        scene_count = max(6, min(15, int(scene_count or 10)))
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("รองรับผู้สร้างภาพเฉพาะ ChatGPT Web หรือ Gemini Web")
        ai_web_model = normalize_ai_web_model(provider, ai_web_model)
        cover_theme = str(cover_theme or "cinematic").strip().lower()
        if cover_theme not in self.COVER_THEMES:
            raise ValueError("ธีมปกละครไม่ถูกต้อง")

        cleaned_characters = []
        character_sources = []
        for index, raw in enumerate(list(characters or [])[:4], 1):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            description = str(raw.get("description") or "").strip()
            image = str(raw.get("image") or "").strip()
            if not name and not description and not image:
                continue
            if image:
                source = Path(image)
                if not source.is_file() or source.suffix.lower() not in self.IMAGE_EXTENSIONS:
                    raise ValueError(f"รูปอ้างอิงตัวละครที่ {index} ต้องเป็น PNG, JPG หรือ WEBP")
            cleaned_characters.append({
                "id": f"CHAR-{index:02d}",
                "name": name or f"ตัวละคร {index}",
                "role": str(raw.get("role") or ("ตัวละครหลัก" if index == 1 else "ตัวละครร่วม")).strip(),
                "description": description,
                "source_image": "",
                "voice_reference_id": str(raw.get("voice_reference_id") or "").strip(),
                "voice_label": str(raw.get("voice_label") or "").strip(),
            })
            character_sources.append(image)
        auto_cast = not cleaned_characters and bool(options and (options.get('storytelling_options') or {}).get('mode') == 'narrator')
        if not cleaned_characters and not auto_cast:
            raise ValueError("กรุณาใส่ข้อมูลตัวละครอย่างน้อย 1 คน")
        if options and options.get('storytelling_options'):
            names = [c['name'] for c in cleaned_characters]
            if len(names) != len(set(names)) or any(n.lower() in {'ผู้บรรยาย', 'narrator', 'voiceover'} for n in names):
                raise ValueError('ชื่อตัวละครต้องไม่ซ้ำและไม่ใช้ชื่อผู้บรรยาย')
            if options['storytelling_options']['mode'] == 'dialogue' and len(names) < 2:
                raise ValueError('โหมดสนทนาต้องมีตัวละครอย่างน้อยสองคน')

        series_id = f"SERIES-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        folder = self.root / series_id
        for name in ("characters", "continuity", "covers", "footage"):
            (folder / name).mkdir(parents=True, exist_ok=True)
        if options and options.get('primary_voice_reference_file'):
            primary_source = Path(options['primary_voice_reference_file'])
            if not primary_source.is_file() or primary_source.suffix.lower() not in {'.wav', '.mp3', '.m4a', '.flac', '.ogg'}:
                raise ValueError('ไฟล์เสียงหลักของซีรีส์ไม่พร้อมใช้')
            primary_target = folder / 'voices' / ('primary' + primary_source.suffix.lower())
            primary_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(primary_source, primary_target)
            options['primary_voice_reference_file'] = primary_target.relative_to(folder).as_posix()
        for index, (record, image) in enumerate(zip(cleaned_characters, character_sources), 1):
            if image:
                source = Path(image)
                target = folder / "characters" / f"character_{index:02d}{source.suffix.lower()}"
                shutil.copy2(source, target)
                record["source_image"] = str(target.relative_to(folder))
        saved_footage = []
        for index, value in enumerate(list(footage or [])[:6], 1):
            source = Path(str(value or ""))
            if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
                raise ValueError(f"ฟุตเทจที่ {index} ต้องเป็นไฟล์วิดีโอ MP4, MOV, MKV, AVI หรือ WEBM")
            target = folder / "footage" / f"footage_{index:02d}{source.suffix.lower()}"
            shutil.copy2(source, target)
            saved_footage.append(str(target.relative_to(folder)))

        now = self._now()
        planned_episodes = self._normalize_plot_board(title, premise, episode_count, plot_board)
        manifest = {
            "id": series_id,
            "title": title,
            "premise": premise,
            "episode_count": episode_count,
            "scene_count": scene_count,
            "provider": provider,
            "ai_web_model": ai_web_model,
            "cover_theme": cover_theme,
            "visual_style": visual_style,
            "visual_style_custom": visual_style_custom,
            **({"render_options": options} if options is not None else {}),
            "status": "queued",
            "characters": cleaned_characters,
            "auto_cast_pending": auto_cast,
            "visual_bible": {},
            "continuity_state": {},
            "continuity_reference_images": [],
            "footage": saved_footage,
            "plot_board": planned_episodes,
            "episodes": [
                {
                    "episode_no": number,
                    "status": "queued",
                    "story_job_id": "",
                    "title": "",
                    "summary": "",
                    "next_episode_hook": "",
                    "video_path": "",
                    "planned_summary": planned_episodes[number - 1]["summary"],
                    "planned_hook": planned_episodes[number - 1]["hook"],
                    "retry_count": 0,
                    "automation_retry_count": 0,
                    "duration_seconds": 0,
                }
                for number in range(1, episode_count + 1)
            ],
            "created_at": now,
            "updated_at": now,
        }
        self._save(manifest)
        return manifest

    def list_series(self):
        rows = []
        for folder in self.root.glob("SERIES-*"):
            path = folder / "series.json"
            if not path.is_file() and not runtime_backup_path(self.project_root, path).is_file():
                continue
            try:
                value = self._manifest_store(path).peek()
                if isinstance(value, dict):
                    rows.append(self._recovered_series_status(value))
            except (OSError, ValueError, JsonPersistenceError):
                continue
        return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)

    def get(self, series_id):
        path = self._folder(series_id) / "series.json"
        if not path.is_file() and not runtime_backup_path(self.project_root, path).is_file():
            raise ValueError("ไม่พบโปรเจกต์ละครสั้น")
        with self._lock:
            try:
                value = self._manifest_store(path).read()
            except (OSError, ValueError, JsonPersistenceError) as exc:
                raise ValueError("Series manifest ว่างเปล่าหรือเสียหาย") from exc
            if not isinstance(value, dict):
                raise ValueError("Series manifest ว่างเปล่าหรือเสียหาย")
            return self._recovered_series_status(value)

    @staticmethod
    def _recovered_series_status(series):
        """Derive a stale failure badge from saved EPs, without writing on read.

        Never clear a failed, running, cancelled or unknown episode. This is not
        queue resume authority and does not change any episode or media file.
        """
        episodes = series.get("episodes") or []
        states = [row.get("status") for row in episodes]
        if (series.get("status") == "needs_attention" and "completed" in states
                and len(episodes) == int(series.get("episode_count") or 0)
                and all(state in {"completed", "queued"} for state in states)):
            series["status"] = "queued" if "queued" in states else "completed"
        return series

    def append_episode(self, series_id, continuation_prompt="", provider="", scene_count=None):
        """Append one new episode after a completed series without losing continuity."""
        with self._lock:
            series = self.get(series_id)
            episodes = list(series.get("episodes") or [])
            unfinished = [row for row in episodes if row.get("status") != "completed"]
            if unfinished:
                episode_no = int(unfinished[0].get("episode_no") or 0)
                raise ValueError(f"กรุณาทำหรือกู้ EP {episode_no} ให้เสร็จก่อนสร้างตอนต่อ")
            next_episode = max([int(row.get("episode_no") or 0) for row in episodes] or [0]) + 1
            if next_episode > self.MAX_EPISODES:
                raise ValueError(f"ซีรีส์รองรับสูงสุด {self.MAX_EPISODES} EP")
            provider = str(
                provider or series.get("last_successful_provider") or series.get("provider") or "chatgpt"
            ).strip().lower()
            if provider not in {"chatgpt", "gemini"}:
                raise ValueError("รองรับผู้สร้างภาพเฉพาะ ChatGPT Web หรือ Gemini Web")
            scene_count = max(6, min(15, int(scene_count or series.get("scene_count") or 10)))
            episode = {
                "episode_no": next_episode,
                "status": "queued",
                "story_job_id": "",
                "title": "",
                "summary": "",
                "next_episode_hook": "",
                "video_path": "",
                "continuation_prompt": str(continuation_prompt or "").strip(),
                "open_ended": True,
                "created_at": self._now(),
                "planned_summary": str(continuation_prompt or "").strip() or f"ต่อเรื่องจากจุดค้างของ EP {next_episode - 1}",
                "planned_hook": "ทิ้งจุดชวนติดตามสำหรับ EP ถัดไป",
                "retry_count": 0,
                "automation_retry_count": 0,
                "duration_seconds": 0,
            }
            episodes.append(episode)
            plot_board = list(series.get("plot_board") or [])
            plot_board.append({
                "episode_no": next_episode,
                "summary": episode["planned_summary"],
                "hook": episode["planned_hook"],
            })
            series.update({
                "episode_count": next_episode,
                "scene_count": scene_count,
                "provider": provider,
                "status": "queued",
                "episodes": episodes,
                "plot_board": plot_board,
                "updated_at": self._now(),
            })
            self._save(series)
            return {"series": series, "episode": dict(episode)}

    def episode_context(self, series_id, episode_no):
        series = self.get(series_id)
        episode_no = int(episode_no or 0)
        if episode_no < 1 or episode_no > int(series["episode_count"]):
            raise ValueError("ลำดับ EP ไม่ถูกต้อง")
        episode = self._episode(series, episode_no)
        previous = next((row for row in series["episodes"] if int(row["episode_no"]) == episode_no - 1), None)
        character_lines = []
        for character in series.get("characters") or []:
            character_lines.append(
                f"- {character.get('name')}: บทบาท {character.get('role')}; "
                f"ลักษณะคงที่ {character.get('description') or 'ให้กำหนดจากรูปอ้างอิงและห้ามเปลี่ยน'}"
            )
        previous_summary = str((previous or {}).get("summary") or "").strip()
        previous_hook = str((previous or {}).get("next_episode_hook") or "").strip()
        continuation_prompt = str(episode.get("continuation_prompt") or "").strip()
        planned_episode = {
            "episode_no": episode_no,
            "summary": str(episode.get("planned_summary") or "").strip(),
            "hook": str(episode.get("planned_hook") or "").strip(),
        }
        story_text = f"""ซีรีส์: {series['title']}
เรื่องหลัก: {series.get('premise') or 'ให้วางเรื่องจากชื่อซีรีส์'}
ตอนที่: EP {episode_no} จาก {series['episode_count']}

ตัวละครที่ต้องคงเดิมทุก EP:
{chr(10).join(character_lines)}

สรุปตอนก่อนหน้า: {previous_summary or ('นี่คือตอนแรกของซีรีส์' if episode_no == 1 else 'ให้ต่อจาก continuity_state ที่แนบ')}
จุดค้างตอนก่อนหน้า: {previous_hook or 'ไม่มี'}
แนวทางตอนต่อจากผู้ใช้: {continuation_prompt or 'ต่อเรื่องจากจุดค้างและข้อมูลความต่อเนื่องเดิมอย่างเป็นธรรมชาติ'}
พล็อตที่อนุมัติไว้สำหรับตอนนี้: {planned_episode['summary'] or 'ดำเนินเรื่องตามโครงหลัก'}
จุดจบ/Hook ที่วางไว้: {planned_episode['hook'] or 'จบตอนอย่างสมเหตุผล'}

เขียนตอนนี้ให้ดูรู้เรื่องในตัวเอง แต่ต่อเนื่องจากตอนก่อนหน้า รักษาใบหน้า ทรงผม อายุ เสื้อผ้าหลัก บุคลิก ความสัมพันธ์ สถานที่สำคัญ และโทนภาพเดิม ปิดตอนด้วยจุดชวนติดตาม EP ถัดไปสำหรับซีรีส์ที่ยังทำต่อได้"""
        if (series.get('render_options') or {}).get('storytelling_options'):
            from core.storytelling import ending_instruction
            story_text = story_text.replace('ปิดตอนด้วยจุดชวนติดตาม EP ถัดไปสำหรับซีรีส์ที่ยังทำต่อได้',
                ending_instruction({'job_type': 'drama_episode', 'episode_no': episode_no,
                    'episode_count': series['episode_count'], 'open_ended': episode.get('open_ended'),
                    'storytelling_options': series['render_options']['storytelling_options']}))
        source_images = []
        folder = self._folder(series_id)
        for character in series.get("characters") or []:
            relative = str(character.get("source_image") or "")
            if relative and (folder / relative).is_file():
                source_images.append(str((folder / relative).resolve()))
        for relative in series.get("continuity_reference_images") or []:
            target = folder / str(relative)
            if target.is_file():
                source_images.append(str(target.resolve()))
        footage_paths = []
        for relative in series.get("footage") or []:
            target = folder / str(relative)
            if target.is_file():
                footage_paths.append(str(target.resolve()))
        primary_voice = str((series.get('render_options') or {}).get('primary_voice_reference_file') or '')
        primary_voice_file = str((folder / primary_voice).resolve()) if primary_voice else ''
        return {
            "series_id": series_id,
            "series_title": series["title"],
            "episode_no": episode_no,
            "episode_count": int(series["episode_count"]),
            "topic": f"{series['title']} • EP {episode_no}",
            "story_text": story_text,
            "provider": series["provider"],
            "ai_web_model": normalize_ai_web_model(series["provider"], series.get("ai_web_model")),
            "scene_count": int(series["scene_count"]),
            "characters": series.get("characters") or [],
            "auto_cast_pending": bool(series.get('auto_cast_pending')),
            "visual_bible": series.get("visual_bible") or {},
            "continuity_state": series.get("continuity_state") or {},
            "previous_episode_summary": previous_summary,
            "previous_episode_hook": previous_hook,
            "continuation_prompt": continuation_prompt,
            "open_ended": bool(episode.get("open_ended")),
            "plot_board": list(series.get("plot_board") or []),
            "planned_episode": planned_episode,
            "cover_theme": str(series.get("cover_theme") or "cinematic"),
            "visual_style": str(series.get("visual_style") or "auto"),
            "visual_style_custom": str(series.get("visual_style_custom") or ""),
            "source_images": source_images,
            "footage_paths": footage_paths,
            "primary_voice_reference_id": str((series.get('render_options') or {}).get('primary_voice_reference_id') or ''),
            "primary_voice_reference_file": primary_voice_file if primary_voice and Path(primary_voice_file).is_file() else '',
            **({"render_options": drama_render_options(series["render_options"]),
                "video_generation_mode": series["render_options"]["video_generation_mode"]}
               if "render_options" in series else {}),
        }

    def attach_story_job(self, series_id, episode_no, story_job_id):
        with self._lock:
            series = self.get(series_id)
            episode = self._episode(series, episode_no)
            started_at = self._now()
            episode.update({"status": "running", "story_job_id": str(story_job_id or ""), "started_at": started_at})
            episode.setdefault("first_started_at", started_at)
            series["status"] = "running"
            series["updated_at"] = self._now()
            self._save(series)
            return series

    def bind_first_episode_voice(self, series_id, reference_id='', reference_file=''):
        """Freeze a queued series' voice when EP 1 actually starts.

        A series may be enqueued before AI Voice is configured. Later episodes
        must not inherit whichever voice happens to be selected in the UI.
        """
        with self._lock:
            series = self.get(series_id)
            options = series.get('render_options') or {}
            if (options.get('audio_choices') or {}).get('mode', 'api') != 'api':
                return series
            if options.get('primary_voice_reference_id') or options.get('primary_voice_reference_file'):
                return series
            first = self._episode(series, 1)
            if first.get('story_job_id') or first.get('status') in {'completed', 'cancelled'}:
                return series  # Legacy series retain their existing voice behavior.
            reference_id = str(reference_id or '').strip()
            reference_file = str(reference_file or '').strip()
            if not reference_id and not reference_file:
                raise ValueError('กรุณาเลือกเสียงหลักก่อนเริ่ม EP แรก')
            if reference_file:
                source = Path(reference_file)
                if not source.is_file() or source.suffix.lower() not in {'.wav', '.mp3', '.m4a', '.flac', '.ogg'}:
                    raise ValueError('ไฟล์เสียงหลักของซีรีส์ไม่พร้อมใช้')
                target = self._folder(series_id) / 'voices' / ('primary' + source.suffix.lower())
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
                options['primary_voice_reference_file'] = target.relative_to(self._folder(series_id)).as_posix()
            options['primary_voice_reference_id'] = reference_id
            series['render_options'] = options
            series['updated_at'] = self._now()
            self._save(series)
            return series

    @staticmethod
    def _owns_story_result(series, episode, story_job):
        """Reject late results before changing the series bible or copying media."""
        if series.get("status") == "cancelled" or episode.get("status") in {"cancelled", "completed"}:
            return False
        bound = str(episode.get("story_job_id") or "")
        if bound:
            return str(story_job.get("id") or "") == bound
        # Old first-attempt manifests may be genuinely unbound. A retry clears
        # the old binding explicitly; wait for attach_story_job in that window.
        return not episode.get("retry_count")

    def update_from_story(self, story_job):
        series_id = str(story_job.get("series_id") or "")
        if not series_id:
            return None
        with self._lock:
            series = self.get(series_id)
            episode = self._episode(series, story_job.get("episode_no"))
            if not self._owns_story_result(series, episode, story_job):
                return series
            episode.update({
                "title": str(story_job.get("episode_title") or story_job.get("video_title") or ""),
                "summary": str(story_job.get("episode_summary") or story_job.get("video_description") or ""),
                "next_episode_hook": str(story_job.get("next_episode_hook") or ""),
                "continuity_validation": dict(story_job.get("continuity_validation") or {}),
                "automation_retry_count": int(story_job.get("auto_recovery_total") or 0),
            })
            if story_job.get("visual_bible"):
                series["visual_bible"] = story_job["visual_bible"]
            if series.get('auto_cast_pending'):
                series['characters'] = generated_drama_cast(story_job.get('character_bible'))
                series['auto_cast_pending'] = False
            if story_job.get("continuity_state"):
                series["continuity_state"] = story_job["continuity_state"]
            successful_provider = str(story_job.get("image_ai_provider") or "").strip().lower()
            if successful_provider in {"chatgpt", "gemini"}:
                series["last_successful_provider"] = successful_provider
                series["provider"] = successful_provider
            self._save_continuity_references(series, story_job)
            series["updated_at"] = self._now()
            self._save(series)
            return series

    def mark_episode_ready(self, story_job, output_path=""):
        series_id = str(story_job.get("series_id") or "")
        if not series_id:
            return None
        with self._lock:
            series = self.get(series_id)
            episode = self._episode(series, story_job.get("episode_no"))
            if not self._owns_story_result(series, episode, story_job):
                return series
            series = self.update_from_story(story_job)
            episode = self._episode(series, story_job.get("episode_no"))
            finished_at = self._now()
            episode.update({"status": "completed", "video_path": str(output_path or ""), "finished_at": finished_at})
            attempt_seconds = self._elapsed_seconds(episode.get("started_at"), finished_at)
            episode["duration_seconds"] = int(episode.get("duration_seconds") or 0) + attempt_seconds
            # A recovered EP may have an earlier browser/voice error saved on it.
            # Once the final video passes, that stale error must not keep showing
            # in the series UI or make the completed episode look unhealthy.
            episode.pop("error", None)
            self._save_episode_cover(series, story_job)
            if all(row.get("status") == "completed" for row in series["episodes"]):
                series["status"] = "completed"
            else:
                self._recovered_series_status(series)
            self._save(series)
            return series

    def mark_episode_failed(self, series_id, episode_no, error, job_id=""):
        if not series_id:
            return None
        with self._lock:
            series = self.get(series_id)
            episode = self._episode(series, episode_no)
            if series.get("status") == "cancelled" or episode.get("status") in {"cancelled", "completed"}:
                return series
            if job_id and not self._owns_story_result(series, episode, {"id": job_id}):
                return series
            finished_at = self._now()
            episode.update({"status": "failed", "error": str(error or "")[:1500], "finished_at": finished_at})
            attempt_seconds = self._elapsed_seconds(episode.get("started_at"), finished_at)
            episode["duration_seconds"] = int(episode.get("duration_seconds") or 0) + attempt_seconds
            series["status"] = "needs_attention"
            series["updated_at"] = self._now()
            self._save(series)
            return series

    def reset_episode_for_retry(self, series_id, episode_no):
        """Put one failed EP back in the queue without creating a duplicate EP."""
        with self._lock:
            series = self.get(series_id)
            episode = self._episode(series, episode_no)
            if episode.get("status") != "failed":
                raise ValueError(f"EP {int(episode_no)} ไม่ได้อยู่ในสถานะที่ต้องกู้")
            previous_error = str(episode.get("error") or "").strip()
            episode.update({
                "status": "queued",
                "story_job_id": "",
                "error": "",
                "started_at": "",
                "finished_at": "",
                "retry_count": int(episode.get("retry_count") or 0) + 1,
            })
            if previous_error:
                episode["previous_error"] = previous_error
            series["status"] = "queued"
            series["updated_at"] = self._now()
            self._save(series)
            return {"series": series, "episode": dict(episode)}

    def cancel_series(self, series_id, reason="ผู้ใช้ยกเลิกคิวซีรีส์"):
        """Cancel unfinished episodes while preserving completed episodes and files."""
        reason = str(reason or "ผู้ใช้ยกเลิกคิวซีรีส์")[:500]
        with self._lock:
            series = self.get(series_id)
            cancelled_at = self._now()
            cancelled = 0
            for episode in series.get("episodes") or []:
                if episode.get("status") not in {"queued", "running", "failed"}:
                    continue
                previous_error = str(episode.get("error") or "").strip()
                if previous_error and previous_error != reason:
                    episode["previous_error"] = previous_error
                episode.update({
                    "status": "cancelled",
                    "error": reason,
                    "cancel_reason": reason,
                    "cancelled_at": cancelled_at,
                    "finished_at": cancelled_at,
                })
                cancelled += 1
            if cancelled:
                series.update({
                    "status": "cancelled",
                    "cancel_reason": reason,
                    "cancelled_at": cancelled_at,
                    "updated_at": cancelled_at,
                })
                self._save(series)
            return {"series": series, "cancelled": cancelled}

    def folder_path(self, series_id):
        return self._folder(series_id).resolve()

    def snapshot(self):
        rows = self.list_series()
        return {
            "items": rows,
            "total_count": len(rows),
            "active_count": sum(row.get("status") in {"queued", "running"} for row in rows),
            "running_count": sum(row.get("status") == "running" for row in rows),
            "needs_attention_count": sum(row.get("status") == "needs_attention" for row in rows),
            "cancelled_count": sum(row.get("status") == "cancelled" for row in rows),
        }

    def _save_continuity_references(self, series, story_job):
        story_root = Path(story_job.get("_folder") or "")
        if not story_root.is_dir():
            return
        generated = list(story_job.get("generated_images") or [])
        if not generated:
            return
        series_folder = self._folder(series["id"])
        episode_no = int(story_job.get("episode_no") or 0)
        selected = [generated[0]]
        if len(generated) > 1:
            selected.append(generated[-1])
        references = []
        for index, relative in enumerate(selected, 1):
            source = story_root / str(relative)
            if not source.is_file():
                continue
            target = series_folder / "continuity" / f"ep_{episode_no:02d}_reference_{index:02d}{source.suffix.lower()}"
            shutil.copy2(source, target)
            references.append(str(target.relative_to(series_folder)))
        if references:
            series["continuity_reference_images"] = references

    def _save_episode_cover(self, series, story_job):
        story_root = Path(story_job.get("_folder") or "")
        source = story_root / str(story_job.get("cover_path") or "")
        if not source.is_file():
            return
        episode_no = int(story_job.get("episode_no") or 0)
        target = self._folder(series["id"]) / "covers" / f"episode_{episode_no:02d}_cover.jpg"
        shutil.copy2(source, target)
        episode = self._episode(series, episode_no)
        episode["cover_path"] = str(target.relative_to(self._folder(series["id"])))

    @staticmethod
    def _episode(series, episode_no):
        episode_no = int(episode_no or 0)
        episode = next((row for row in series.get("episodes") or [] if int(row.get("episode_no") or 0) == episode_no), None)
        if not episode:
            raise ValueError("ไม่พบ EP ในโปรเจกต์ละคร")
        return episode

    @staticmethod
    def _normalize_plot_board(title, premise, episode_count, plot_board):
        """Create a complete, immutable-at-queue-time plan for every requested EP."""
        supplied = list(plot_board or []) if isinstance(plot_board, list) else []
        rows = []
        for index in range(int(episode_count)):
            episode_no = index + 1
            source = supplied[index] if index < len(supplied) and isinstance(supplied[index], dict) else {}
            summary = str(source.get("summary") or "").strip()
            hook = str(source.get("hook") or "").strip()
            if not summary:
                if episode_no == 1:
                    summary = str(premise or "").strip() or f"เปิดเรื่อง {title} แนะนำตัวละครและปมหลัก"
                elif episode_no == int(episode_count):
                    summary = "คลี่คลายปมหลัก สรุปการเปลี่ยนแปลงของตัวละคร และปิดเรื่องให้ครบ"
                else:
                    summary = f"ขยายความขัดแย้งจาก EP {episode_no - 1} และพาเรื่องไปสู่จุดเปลี่ยนใหม่"
            if not hook:
                hook = "ปิดตอนอย่างสมบูรณ์" if episode_no == int(episode_count) else f"ทิ้งคำถามหรือเหตุการณ์ชวนติดตาม EP {episode_no + 1}"
            rows.append({"episode_no": episode_no, "summary": summary, "hook": hook})
        return rows

    @staticmethod
    def _elapsed_seconds(started_at, finished_at):
        try:
            started = datetime.fromisoformat(str(started_at or ""))
            finished = datetime.fromisoformat(str(finished_at or ""))
            return max(0, int((finished - started).total_seconds()))
        except (TypeError, ValueError):
            return 0

    def _folder(self, series_id):
        series_id = str(series_id or "")
        if not series_id.startswith("SERIES-") or any(value in series_id for value in ("/", "\\", "..")):
            raise ValueError("Series ID ไม่ถูกต้อง")
        return self.root / series_id

    def _manifest_store(self, target):
        target = Path(target)
        return AtomicJsonFile(
            target,
            backup_path=runtime_backup_path(self.project_root, target),
        )

    def _save(self, manifest):
        folder = self._folder(manifest["id"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "series.json"
        store = self._manifest_store(target)
        with self._lock, store.locked():
            current_revision = 0
            if target.is_file():
                current = store.read_unlocked()
                if not isinstance(current, dict):
                    raise JsonPersistenceError(f"Series manifest ไม่ใช่ JSON object: {target}")
                try:
                    current_revision = int(current.get("revision") or 0)
                except (TypeError, ValueError):
                    current_revision = 0
            manifest["revision"] = max(current_revision, int(manifest.get("revision") or 0)) + 1
            store.write_unlocked(manifest)
        return manifest
