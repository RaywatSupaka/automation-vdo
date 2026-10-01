import subprocess
import unittest
from pathlib import Path
from tests import test_ai_cover
from core.ai_cover import ai_cover_options


class CoverContract451(unittest.TestCase):
    def setUp(self):
        self.fixture = test_ai_cover.AICoverTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.service = self.fixture.service

    def chain(self, rid, accepted=False):
        return dict(version=1, request_id=rid, provider='gemini',
            conversation_url='https://gemini.google.com/app/0123456789abcdef', reference_count=1,
            reference_user=dict(index=0, id='original-user'),
            retry_user=dict(index=1, id='retry-user') if accepted else None)

    def test_retry_chain_durable_monotonic_collect_only_and_no_source_bytes(self):
        rid = self.fixture.claim()
        pending = self.chain(rid)
        self.service.event(rid, dict(phase='running', retry_count=1, reference_chain=pending))
        self.assertEqual(self.service.get(rid)['reference_chain'], pending)
        accepted = self.chain(rid, True)
        self.service.event(rid, dict(phase='running', reference_chain=accepted))
        self.service.event(rid, dict(phase='needs_review'))
        self.service.recover_result(rid, self.fixture.job)
        package = self.service.package(rid)
        self.assertEqual(package['reference_chain'], accepted)
        self.assertNotIn('source_data', package)
        with self.assertRaises(ValueError):
            self.service.event(rid, dict(phase='running', reference_chain=pending))
        self.assertEqual((self.fixture.folder/'video.mp4').read_bytes(), b'preserve this final video')

    def test_chain_rejects_foreign_owner_count_and_rebinding(self):
        rid = self.fixture.claim()
        self.service.event(rid, dict(phase='running', retry_count=1, reference_chain=self.chain(rid)))
        for field, value in [('request_id','other'),('provider','chatgpt'),('reference_count',2),
                             ('conversation_url','https://evil.invalid/chat'),('reference_user',dict(index=0,id='other'))]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                bad = self.chain(rid, True); bad[field] = value
                self.service.event(rid, dict(phase='running', reference_chain=bad))

    def test_custom_and_empty_headline_are_versioned_new_requests(self):
        row = self.service.request(self.fixture.job, options=dict(enabled=True, headline='หัวข้อที่กำหนด 😀'))
        self.assertEqual(row.get('cover_prompt_version'), 2)
        self.assertEqual(row['headline'], 'หัวข้อที่กำหนด 😀')
        self.service.event(row['request_id'], dict(phase='cancelled'))
        blank = self.service.request(self.fixture.job, force=True, options=dict(enabled=True, headline=''))
        self.assertEqual(blank['headline'], '')

    def test_native_retry_collection(self):
        result = subprocess.run(['node','tests/cover_retry_reference_451.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding='utf-8', timeout=50)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_studio_limits_prompt_and_unicode_contract(self):
        for text in ['ก'*40, '😀'*40, 'กำ'*20, '']:
            self.assertEqual(ai_cover_options({'headline':text})['headline'], text)
        for text in ['ก'*41, '😀'*41, 'ก'*60]:
            with self.assertRaises(ValueError):
                ai_cover_options({'headline':text})
        result = subprocess.run(['node','tests/cover_studio_contract_451.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding='utf-8', timeout=50)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
