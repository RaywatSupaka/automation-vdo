import csv, uuid
from datetime import datetime
from pathlib import Path

FIELDS="id video_path caption product status created_at started_at posted_at retry_count last_step error post_result".split()
class JobManager:
    def __init__(self,path): self.path=Path(path); self._migrate()
    def _migrate(self):
        rows=[]
        if self.path.exists():
            with self.path.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
        self.save([{k:r.get(k,"") for k in FIELDS} for r in rows])
    def load(self):
        with self.path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
    def save(self,rows):
        with self.path.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    def add(self,path):
        rows=self.load(); value=str(Path(path).resolve())
        if any(r["video_path"]==value and r["status"] not in {"failed","success"} for r in rows): return False
        row={k:"" for k in FIELDS}; row.update(id=f"JOB-{uuid.uuid4().hex[:6].upper()}",video_path=value,status="pending",created_at=datetime.now().isoformat(timespec="seconds"),retry_count="0",last_step="CHECK_DEVICE")
        rows.append(row); self.save(rows); return True
