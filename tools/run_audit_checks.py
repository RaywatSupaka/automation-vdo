"""Offline whole-suite audit with bounded, readable failure diagnostics."""
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.chdir(ROOT)


if __name__=='__main__':
    stream=io.StringIO()
    started=time.monotonic()
    suite=(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv)>1 else
           unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py'))
    result=unittest.TextTestRunner(stream=stream,verbosity=0).run(suite)
    report={'ran':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'duration_seconds':round(time.monotonic()-started,3),
            'skip_details':[{'test':test.id(),'reason':reason} for test,reason in result.skipped],
            'details':[{'test':test.id(),'traceback':detail[:5000]+'\n…\n'+detail[-1500:] if len(detail)>6500 else detail} for test,detail in result.failures+result.errors]}
    target=ROOT/'build'/'audit-426-results.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='details'},ensure_ascii=False))
    for entry in report['details']: print(entry['test'])
    print('Report:',target)
    sys.exit(0 if result.wasSuccessful() else 1)
