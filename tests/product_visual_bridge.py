"""Offline stdin bridge for Extension tests. Never talks to a running app."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import motion_plan_action, plan_context, saved_motion_prompt

payload = json.loads(sys.stdin.buffer.read().decode('utf-8'))
root, job = Path(payload['folder']), payload['job']
try:
    if payload.get('seed'):
        base = plan_context(root, job, 2)
        row = {'phase': 'answered', 'context': base, 'request': 'LEGACY_DASHBOARD_CUT', 'content_recheck_attempt': 1,
               'result': {**{k: base[k] for k in ('job_id', 'index', 'context_id')},
                          'prompt': 'Create one vertical 9:16 video of the stationary device with a slow studio push-in.',
                          'needs_review': True, 'reference_compatible': True, 'material_change': True,
                          'review_reason': 'Removing the split-screen demonstration materially changes the original story beat.'}}
        AtomicJsonFile(root / 'prompts/flow_motion_plans.json').write({'schema': 1, 'plans': {base['context_id']: row}})
        result = {'ok': True, 'base': base}
    elif payload.get('saved'):
        result = {'ok': True, 'prompt': saved_motion_prompt(root, job, 2, 'generated/selling_image_02.png')}
    else:
        result = motion_plan_action(root, job, payload['body'])
        result['context']['image_url'] = 'http://fixture-only/selling_image_02.png'
except (ValueError, KeyError) as error:
    result = {'ok': False, 'error': str(error)}
sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
