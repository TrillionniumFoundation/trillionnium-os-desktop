#!/usr/bin/env python3
"""Exercise success and an actual post-success context-exit exception off-device."""
from pathlib import Path
import contextlib,hashlib,importlib.util,io,json,tempfile,types,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent

class TerminalExit(unittest.TestCase):
    def exercise(self,exit_error):
        spec=importlib.util.spec_from_file_location('capture_runtime02',HERE/'capture_runtime02.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        payload=b'\0'*11839391;stops=[]
        class Session:
            def __init__(self,*a):self.target=self
            def __enter__(self):return self
            def __exit__(self,*a):
                if exit_error:raise RuntimeError('INJECTED_SESSION_EXIT_FAILURE')
            def guard(self):return {'exact_test_identity':1}
            def read_file(self,*a,**kw):return payload,{'inode':101,'size':len(payload)}
        class Sampler:
            def __init__(self,*a):pass
            def start(self):pass
            def phase_changed(self,*a):pass
            def stop(self):
                stops.append(True)
                return {'thread_joined':True,'processes_observed':['com.android.contacts'],'sample_count':1}
        def write_new(path,value,**kw):
            with path.open('xb') as f:f.write(value if isinstance(value,bytes) else json.dumps(value).encode())
        tx=types.SimpleNamespace(ACTIVATION_SHA=m.ACTIVATION_SHA,CameraSession=Session,write_new=write_new)
        runtime=types.SimpleNamespace(TARGETS={'com.android.contacts':10055},PROCESS_NAMES={'com.android.contacts':{'com.android.contacts'}},RuntimeEvidence=Sampler)
        with tempfile.TemporaryDirectory() as directory:
            m.ROOT=Path(directory)/'runtime';m.CONTROLLER=Path(directory)/'no-controller'
            m.APK_SHA=hashlib.sha256(payload).hexdigest()
            def load(path,*a):return tx if path==m.TX else runtime
            with patch.object(m,'load',load),patch.object(m,'terminal_read',return_value={'state':'TEST_TERMINAL','sha256':'0'*64}),patch.object(m.os,'geteuid',return_value=0),patch.object(m.os,'chown'),patch.object(m.os,'sched_setaffinity'),contextlib.redirect_stdout(io.StringIO()):
                code=m.execute()
            result=json.loads((m.ROOT/'result.json').read_bytes())
        self.assertEqual(stops,[True])
        self.assertEqual(result['guard_before'],result['guard_after'])
        self.assertIn('separate_UI_flow_result',result)
        return code,result
    def test_completed_capture_exits_successfully(self):
        code,result=self.exercise(False)
        self.assertEqual(code,0);self.assertEqual(result['state'],'BOUNDED_CONTACTS_RUNTIME_OBSERVATIONS_CAPTURED_REVIEW_REQUIRED')
        self.assertNotIn('error',result)
    def test_context_exit_failure_cannot_retain_success(self):
        code,result=self.exercise(True)
        self.assertEqual(code,1);self.assertEqual(result['state'],'FAILED')
        self.assertEqual(result['error'],'RuntimeError:INJECTED_SESSION_EXIT_FAILURE')

if __name__=='__main__':unittest.main(verbosity=2)
