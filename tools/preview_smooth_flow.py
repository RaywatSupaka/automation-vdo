"""Render a separate local motion/voice preview; never update job metadata."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.video_composer import MultiFlowComposer

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--job-folder',required=True)
    p.add_argument('--clips-folder',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    folder=Path(a.job_folder);job=json.loads((folder/'job.json').read_text(encoding='utf-8'))
    clips=[Path(a.clips_folder)/f'flow-shot-{i:02d}.mp4' for i in range(1,job['scene_count']+1)]
    out=Path(a.output)
    if out.exists():raise ValueError('Preview exists; choose another output')
    plan=MultiFlowComposer().compose(clips,out,folder/job['voice_path'],width=360,height=640,fps=30,
        scene_durations=job['render_plan']['scene_output_durations'],extend_mode='smooth')
    print(json.dumps({k:plan[k] for k in ['duration','source_duration','voice_duration','extend_mode']}))
