"""New creative settings use existing frozen job/queue routes, without providers."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

from core.cancellable_process import hidden_process_kwargs
from core.creation_queue import clean_settings
from core.drama_options import drama_render_options
from core.generated_music import validate_options, freeze_plan
from core.product_prepare_options import freeze_product_options

ROOT = Path(__file__).resolve().parents[1]


class CreativeRoutes452Tests(unittest.TestCase):
    def test_music_controls_native_and_backend_contract(self):
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        run = subprocess.run(['node', 'tests/generated_music_ui_452.cjs'], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding='utf-8', timeout=60, **hidden_process_kwargs())
        self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
        rows=json.loads(next(row.split('=',1)[1] for row in run.stdout.splitlines() if row.startswith('BACKEND_MUSIC=')))
        self.assertEqual(len(rows), 6)
        for row in rows:
            value=row['payload']
            mode=value.get('video_generation_mode') or value.get('render_options',{}).get('video_generation_mode') or 'google_flow'
            options=validate_options(value['generated_music_options'], mode, value['audio_choices'])
            saved=clean_settings(value)
            self.assertEqual(saved['generated_music_options'],options)
            job=dict(saved,id='STORY-SYNTHETIC-'+row['key'],scene_count=10,video_generation_mode=mode)
            freeze_plan(job)
            before=copy.deepcopy(job)
            freeze_plan(job)
            self.assertEqual(job,before)
            self.assertEqual(len(job['generated_music_plan']['scene_indices']),3)
            if row['key']=='drama':
                self.assertEqual(drama_render_options(value['render_options'])['generated_music_options'],options)

    def test_product_music_is_frozen_before_capture(self):
        value={'generated_music_options':{'version':1,'enabled':True,'mood':'warm','frequency':'sparse'},
               'audio_choices':{'mode':'api','keep_video_audio':True},
               'product_script_options':{'version':1,'style':'standard'}}
        frozen=freeze_product_options(value)
        value['generated_music_options']['enabled']=False
        self.assertTrue(frozen['generated_music_options']['enabled'])
        self.assertEqual(clean_settings(frozen)['generated_music_options']['frequency'],'sparse')

    def test_absent_new_features_leave_legacy_queue_shape(self):
        legacy={'audio_choices':{'mode':'api'},'finish_config':{'logo_position':'bottom_right'}}
        self.assertEqual(clean_settings(legacy),legacy)
        self.assertNotIn('generated_music_options',freeze_product_options({}))

    def test_disabled_music_cannot_keep_renderer_marker(self):
        raw={'audio_choices':{'mode':'api','generated_music_version':1},
             'generated_music_options':{'version':1,'enabled':False}}
        self.assertNotIn('generated_music_version',clean_settings(raw)['audio_choices'])
        self.assertNotIn('generated_music_version',drama_render_options(raw)['audio_choices'])

    def test_invalid_or_conflicting_music_fails_before_dispatch(self):
        options={'version':1,'enabled':True}
        for mode, audio in [('image_motion',{'mode':'api','keep_video_audio':True}),
                            ('google_flow',{'mode':'none'}),('meta_ai',{'mode':'api'}),
                            ('google_flow',{'mode':'flow_original','music':True})]:
            with self.subTest(mode=mode,audio=audio), self.assertRaises(ValueError):
                validate_options(options,mode,audio)


if __name__=='__main__':
    unittest.main()
