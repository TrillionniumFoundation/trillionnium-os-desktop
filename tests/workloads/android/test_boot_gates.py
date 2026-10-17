#!/usr/bin/env python3
"""Synthetic ADB transcript tests only; NO Android boot took place."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

P=Path(__file__).with_name('boot_gates.py')
spec=importlib.util.spec_from_file_location('a08boot',P)
import sys
sys.path.insert(0,str(P.parent))
boot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class FakeAdb:
    serial='cf-test-only'
    def __init__(self, binder=True, build='aosp_cf_x86_64_phone',
                 art_lib=True, boot_completed='1'):
        self.binder=binder; self.build=build; self.calls=[]
        self.art_lib=art_lib; self.boot_completed=boot_completed
    def cmd(self,*args,**kwargs):
        self.calls.append(args)
        if args==('get-state',): return 'device'
        if args==('get-serialno',): return self.serial
        if args==('shell','getprop','sys.boot_completed'):
            return self.boot_completed
        if args[:2]==('shell','getprop'):
            return {'ro.product.name':self.build,'ro.product.device':'vsoc_x86_64',
                'ro.product.cpu.abi':'x86_64','ro.hardware':'cutf_cvm',
                'ro.build.id':'BP1A.250505.005.D1','ro.build.version.release':'15',
                'ro.build.fingerprint':'test/a08','ro.build.version.sdk':'35'}[args[2]]
        if args==('shell','getconf','PAGESIZE'):return '4096'
        if args==('shell','uname','-a'):return 'Linux fake guest 6.1'
        if args==('shell','cat','/proc/1/comm'):return 'init\n'
        if args==('shell','service','list'):
            return '1 activity: [android.app.IActivityManager]\n2 package: [android.content.pm.IPackageManager]\n' if self.binder else 'Error: cannot find servicemanager'
        if args[0:3]==('shell','pidof','zygote64'):return '123\n'
        if args[0:3]==('shell','pidof','system_server'):return '456\n'
        if args[0:3]==('shell','pidof','surfaceflinger'):return '20\n'
        if args[0:3]==('shell','pidof','lmkd'):return '30\n'
        if args==('shell','sh','-c',
                  'test -r /apex/com.android.art/lib64/libart.so && echo A08_ART_LIB_PRESENT'):
            return 'A08_ART_LIB_PRESENT' if self.art_lib else ''
        if args==('shell','cmd','package','list','packages'):return 'package:com.android.shell\n'
        if args==('shell','getenforce'):return 'Enforcing'
        if args[0]=='logcat':return 'SYNTHETIC NO REAL BOOT\n'
        raise AssertionError(f'Unexpected read: {args}')

class BootTests(unittest.TestCase):
    def test_reference_gate_transcript_only(self):
        with tempfile.TemporaryDirectory() as td:
            r=boot.run_boot_gates(FakeAdb(),Path(td))
            self.assertEqual(r['status'],'pass',r)
            self.assertEqual(len(r['gates']),10)
            self.assertFalse(r['native_asterinas_qualified'])
            self.assertTrue((Path(td)/'boot-gates.json').is_file())
    def test_missing_binder_fails_even_with_pids(self):
        with tempfile.TemporaryDirectory() as td:
            r=boot.run_boot_gates(FakeAdb(binder=False),Path(td))
            self.assertEqual(r['classification'],'binder_servicemanager_roundtrip')
            self.assertEqual(r['status'],'fail')
    def test_missing_mounted_art_library_fails_not_fabricated(self):
        with tempfile.TemporaryDirectory() as td:
            fake=FakeAdb(art_lib=False)
            r=boot.run_boot_gates(fake,Path(td))
            self.assertEqual(r['status'],'fail')
            self.assertEqual(r['classification'],'art_runtime_library_accessible')
            self.assertFalse(r['native_asterinas_qualified'])

    def test_unfinished_framework_boot_fails(self):
        with tempfile.TemporaryDirectory() as td:
            r=boot.run_boot_gates(FakeAdb(boot_completed='0'),Path(td))
            self.assertEqual(r['status'],'fail')
            self.assertEqual(r['classification'],'framework_boot_completed')

    def test_reject_real_phone_before_other_reads_and_logcat(self):
        with tempfile.TemporaryDirectory() as td:
            fake=FakeAdb(build='production_phone')
            r=boot.run_boot_gates(fake,Path(td))
            self.assertEqual(r['classification'],'device_identity')
            self.assertFalse(any(c[0]=='logcat' for c in fake.calls))
            self.assertFalse(any(c==('shell','service','list') for c in fake.calls))

if __name__=='__main__':unittest.main()
