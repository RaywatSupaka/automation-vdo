import copy
import unittest
from core.subtitle_chunks import merge_subtitle_segments

class SubtitleTailRecoveryTests(unittest.TestCase):
    def test_exact_failed_job_boundary(self):
        cues=[{'start':28.765,'end':29.0,'text':'แบน'},
              {'start':29.976,'end':30.016,'text':'คำท้าย'}]
        cues += [{'start':30.016+i*.04,'end':30.056+i*.04,'text':'หางนอกเสียง'} for i in range(5)]
        parts=[{'offset_seconds':0,'duration_seconds':30.016,'segments':cues}]
        original=copy.deepcopy(parts);audit=[]
        result=merge_subtitle_segments(parts,audit)
        self.assertEqual(len(result),2);self.assertEqual(len(audit),5)
        self.assertEqual(parts,original);self.assertEqual(result[-1]['end'],30.016)

    def test_clip_end_and_next_chunk_offset(self):
        audit=[]
        result=merge_subtitle_segments([
            {'offset_seconds':0,'duration_seconds':60,'segments':[{'start':59,'end':60.2,'text':'a'}]},
            {'offset_seconds':60,'duration_seconds':2,'segments':[{'start':0,'end':1,'text':'b'}]}],audit)
        self.assertEqual(result[0]['end'],60);self.assertEqual(result[1]['start'],60)
        self.assertEqual(audit[0]['action'],'clip_end')

    def test_corrupt_or_overlapping_still_rejected(self):
        for cues in [[{'start':-1,'end':1}], [{'start':1,'end':1}], [{'start':0,'end':float('nan')}],
                     [{'start':0,'end':2},{'start':1,'end':3}], [{'start':31,'end':32}]]:
            with self.subTest(cues=cues),self.assertRaises(ValueError):
                merge_subtitle_segments([{'offset_seconds':0,'duration_seconds':30.016,'segments':cues}])

    def test_global_timestamps_in_second_chunk_not_silently_lost(self):
        with self.assertRaises(ValueError):
            merge_subtitle_segments([
                {'offset_seconds':0,'duration_seconds':60,'segments':[{'start':0,'end':2}]},
                {'offset_seconds':60,'duration_seconds':4,'segments':[{'start':61,'end':63}]}])
