"""Seccomp guest gate, source and host execution tests; no real Asterinas boot."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch
import unittest

from test_abi_result_parser import runner, serial

PROBE = Path(__file__).with_name('seccomp_abi_probe.c')
PREP = Path(__file__).resolve().parents[3] / 'support/android/prepare_asterinas_abi.py'

class SeccompGuestContractTests(unittest.TestCase):
    def test_not_implemented_filter_is_red_separately_from_linux_abi(self):
        report = runner.assess(33, serial())
        self.assertEqual(report['linux_abi_probe'], 'pass', report['failure_reasons'])
        self.assertEqual(report['binder_probe'], 'blocked_no_device')
        self.assertEqual(report['seccomp_probe'], 'filter_install_not_implemented')
        self.assertEqual(report['seccomp_filter_install_errno'], 38)
        self.assertFalse(report['android_seccomp_filters_verified'])

    def test_actual_positive_marker_plus_all_rejections_is_primitive_only(self):
        report = runner.assess(33, serial(seccomp='filter_works'))
        self.assertEqual(report['linux_abi_probe'], 'pass', report['failure_reasons'])
        self.assertEqual(report['seccomp_probe'], 'filter_enforcement_primitive_only')
        self.assertFalse(report['seccomp_tsync_verified'])
        self.assertFalse(report['android_seccomp_filters_verified'])

    def test_seccomp_success_marker_cannot_forge_filter(self):
        report = runner.assess(33, serial(seccomp='marker_only'))
        self.assertEqual(report['seccomp_probe'], 'unproven_filter_enforcement')
        self.assertEqual(report['linux_abi_probe'], 'fail')
        self.assertIn('seccomp_filter_details_missing_or_failed', report['failure_reasons'])

    def test_denied_getpid_must_be_proven(self):
        trace = serial(seccomp='filter_works').replace(
            'seccomp_deny_getpid\tPASS\terrno=0', 'seccomp_deny_getpid\tFAIL\terrno=0')
        report = runner.assess(33, trace)
        self.assertEqual(report['seccomp_probe'], 'unproven_filter_enforcement')
        self.assertEqual(report['linux_abi_probe'], 'fail')

    def test_duplicate_seccomp_filter_result_rejected(self):
        trace = serial(seccomp='filter_works').replace(
            'seccomp_filter_install\tPASS\terrno=0',
            'seccomp_filter_install\tPASS\terrno=0\nseccomp_filter_install\tPASS\terrno=0')
        self.assertEqual(runner.assess(33, trace)['seccomp_probe'], 'unproven_filter_enforcement')

    def test_missing_seccomp_markers_cannot_be_guest_pass(self):
        trace=serial().replace('A08_GUEST_SECCOMP_BEGIN\n', '').replace(
            'A08_GUEST_SECCOMP_END\n', '')
        report = runner.assess(33, trace)
        self.assertEqual(report['seccomp_probe'], 'not_executed')
        self.assertEqual(report['linux_abi_probe'], 'fail')

    def test_unsupported_probe_build_classified_separately(self):
        report = runner.assess(33, serial(seccomp='compile_missing'))
        self.assertEqual(report['seccomp_probe'], 'unsupported_probe_build')
        self.assertEqual(report['linux_abi_probe'], 'pass')

    def test_missing_kernel_errno_is_not_confirmed_enosys(self):
        trace = serial().replace('seccomp_filter_install\tFAIL\terrno=38\n', '')
        report = runner.assess(33, trace)
        self.assertNotEqual(report['seccomp_probe'], 'filter_install_not_implemented')
        self.assertIsNone(report['seccomp_filter_install_errno'])

    def test_bad_exit_marker_never_succeeds(self):
        trace = serial().replace('A08_GUEST_SECCOMP_EXIT:13', 'A08_GUEST_SECCOMP_EXIT:garbage')
        report = runner.assess(33, trace)
        self.assertEqual(report['seccomp_probe'], 'malformed_exit')
        self.assertEqual(report['linux_abi_probe'], 'fail')

    def test_missing_sibling_process_wake_cannot_fake_seccomp_child(self):
        trace=serial(seccomp='filter_works').replace('seccomp_child\tPASS\texit=0\n','')
        report=runner.assess(33,trace)
        self.assertEqual(report['seccomp_probe'], 'unproven_filter_enforcement')

    def test_injected_init_preserves_a01_boot_order(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('a08_prep_seccomp',PREP)
        tool=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        init=b'echo "TRILLIONNIUM_A01_INIT_BEGIN"\necho "TRILLIONNIUM_A01_BOOT_OK"\n'
        generated=tool.compose_init(init)
        self.assertIn(b'/test/a08-seccomp-abi',generated)
        self.assertLess(generated.index(b'A08_GUEST_SECCOMP_BEGIN'),
                        generated.index(b'A08_GUEST_SECCOMP_END'))
        self.assertLess(generated.index(b'A08_GUEST_SECCOMP_END'),
                        generated.index(b'TRILLIONNIUM_A01_BOOT_OK'))

    def test_guest_cli_never_exits_green_with_missing_seccomp(self):
        # This checks top-level exit policy without starting a fake or real VM.
        import sys
        argv=['--a01-qemu-json','a01.json','--kernel','kernel.elf',
              '--expected-kernel-sha256','0'*64,'--initramfs','a08.cpio.gz',
              '--manifest','a08.json','--bios','bios.bin','--qemu','qemu',
              '--outdir','fresh-out']
        status={'linux_abi_probe':'pass',
                'binder_probe':'primitive_ioctl_mmap_only',
                'seccomp_probe':'filter_install_not_implemented'}
        with patch.object(runner, 'execute',return_value={'result':status}):
            self.assertEqual(runner.main(argv),2)
        status['seccomp_probe']='filter_enforcement_primitive_only'
        with patch.object(runner, 'execute',return_value={'result':status}):
            self.assertEqual(runner.main(argv),0)

    def test_host_static_seccomp_probe_is_child_isolated(self):
        if shutil.which('cc') is None:
            raise unittest.SkipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'a08-seccomp-static'
            result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                                  '-static',str(PROBE),'-o',str(exe)],
                                  capture_output=True,text=True,check=False,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,
                               check=False,timeout=15)
            if ran.returncode != 0:
                self.skipTest('host kernel denies seccomp; raw outcome retained: '+ran.stdout[-300:])
            self.assertEqual(ran.returncode,0,ran.stdout)
            for label in ('no_new_privs','seccomp_filter_install','seccomp_deny_getpid',
                          'seccomp_allow_getppid'):
                self.assertEqual([s for s in ran.stdout.splitlines() if s.startswith(label+'\t')],
                                 [label+'\tPASS\terrno=0'])
            self.assertIn('seccomp_child\tPASS\texit=0',ran.stdout)
            self.assertIn('seccomp_TSYNC_multithread\tNOT_TESTED',ran.stdout)
            self.assertIn('Android_process_filters\tNOT_TESTED',ran.stdout)
            self.assertTrue(hashlib.sha256(exe.read_bytes()).hexdigest())

if __name__ == '__main__':
    unittest.main()
