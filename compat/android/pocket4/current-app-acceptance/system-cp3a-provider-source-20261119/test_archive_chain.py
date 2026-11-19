import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'apk-content-identity'))
import verify_apk_set
spec=importlib.util.spec_from_file_location('provider_worker_source_review',HERE/'source/verify_providers_r2.py')
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
worker.safe_members=verify_apk_set.safe_members

class ArchiveMemberChain(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'evidence').mkdir()
        (self.root/'logs').mkdir()
        worker.OUT=self.root
        worker.BOOKENDS=[]
        worker.COMMANDS.clear()
        worker.DEADLINE=time.monotonic()+10
        self.old_budget=worker.budget
        worker.budget=lambda:0

    def tearDown(self):
        for path,fd,pin in worker.BOOKENDS:
            os.close(fd)
        worker.BOOKENDS=[]
        worker.budget=self.old_budget
        self.tmp.cleanup()

    def archive(self,entries,corrupt=None):
        path=self.root/'source.capex'
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED) as z:
            for name,data in entries:
                z.writestr(name,data)
        if corrupt:
            data=path.read_bytes()
            self.assertIn(corrupt,data)
            data=data.replace(corrupt,bytes([corrupt[0]^1])+corrupt[1:],1)
            path.write_bytes(data)
        raw=path.read_bytes()
        fd=os.open(path,os.O_RDONLY)
        self.addCleanup(os.close,fd)
        return fd,{'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

    def test_exact_selected_member_and_all_other_crc_hashes(self):
        fd,pin=self.archive([('original_apex',b'CURRENT_APEX_BYTES'),('apex_manifest.pb',b'public metadata')])
        out=self.root/'original.apex'
        extracted,actual,proof=worker.zip_member(fd,pin,'original_apex',out,'chain')
        self.assertEqual(out.read_bytes(),b'CURRENT_APEX_BYTES')
        self.assertEqual(actual['sha256'],hashlib.sha256(b'CURRENT_APEX_BYTES').hexdigest())
        chain=json.loads(Path(proof['path']).read_bytes())
        self.assertEqual(chain['parent'],pin)
        self.assertEqual(chain['selected_member']['name'],'original_apex')
        self.assertEqual(len(chain['complete_members']),2)
        self.assertTrue(all(x['complete_eof_crc_verified'] for x in chain['complete_members']))
        self.assertFalse(chain['container_signature_or_AVB_qualified'])
        self.assertFalse(chain['runtime_qualified'])

    def test_corrupt_unselected_member_refuses_receipt(self):
        fd,pin=self.archive([('original_apex',b'CURRENT_APEX_BYTES'),('apex_manifest.pb',b'OTHER_MEMBER_BODY')],b'OTHER_MEMBER_BODY')
        with self.assertRaises(zipfile.BadZipFile):
            worker.zip_member(fd,pin,'original_apex',self.root/'original.apex','chain')
        self.assertFalse((self.root/'evidence/chain.json').exists())

    def test_duplicate_selected_name_refused_before_output(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            fd,pin=self.archive([('original_apex',b'FIRST'),('original_apex',b'SECOND')])
        with self.assertRaisesRegex(ValueError,'ZIP member names are duplicate or truncated'):
            worker.zip_member(fd,pin,'original_apex',self.root/'original.apex','chain')
        self.assertFalse((self.root/'original.apex').exists())

    def test_missing_exact_member_refused_before_output(self):
        fd,pin=self.archive([('other_original_apex',b'OTHER')])
        with self.assertRaisesRegex(ValueError,'required exact archive member'):
            worker.zip_member(fd,pin,'original_apex',self.root/'original.apex','chain')
        self.assertFalse((self.root/'original.apex').exists())

    def test_log_limit_stops_and_reaps_original_child(self):
        with self.assertRaisesRegex(ValueError,'command failed: flood'):
            worker.run('flood',[sys.executable,'-I','-c',
                'import os; block=b"x"*65536\nfor _ in range(160): os.write(1,block)'],timeout=5)
        row=worker.COMMANDS[-1]
        self.assertEqual(row['termination'],'log_byte_bound')
        self.assertTrue(row['actual_child_reaped'])
        self.assertTrue(row['after_reap_echild'])
        self.assertTrue(row['original_pidfd_held_until_reaped'])
        self.assertLessEqual((self.root/'logs/flood.stdout').stat().st_size,8*1024*1024)

    def test_declared_output_must_fit_before_creating_file(self):
        with self.assertRaisesRegex(ValueError,'output allocated reservation bound'):
            worker.space(worker.LIMIT)

    def test_sigchld_ignore_refuses_child_start(self):
        import signal
        from unittest import mock
        with mock.patch.object(worker.signal,'getsignal',return_value=signal.SIG_IGN):
            with self.assertRaisesRegex(ValueError,'default SIGCHLD required'):
                worker.run('never-started',[sys.executable,'-c','raise AssertionError()'])
        self.assertFalse((self.root/'logs/never-started.stdout').exists())

if __name__=='__main__':
    unittest.main()
