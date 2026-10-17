"""Actual host C probe; host Linux success is not target Asterinas evidence."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).with_name('kernel_abi_probe.c')
ABI=('mmap','memfd_create','SCM_RIGHTS','futex_wait_wake','signal')


class RealHostKernelAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):
            raise unittest.SkipTest('no C compiler on this host')

    def test_actual_static_userspace_syscall_probe(self):
        with tempfile.TemporaryDirectory(prefix='a08-real-host-') as td:
            exe=Path(td)/'kernel-abi-static'
            compiled=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                                    '-static','-pthread',str(SOURCE),'-o',str(exe)],
                                     capture_output=True,text=True,check=False,timeout=90)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,
                               check=False,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr+'\n'+run.stdout)
            for name in ABI:
                matches=[line for line in run.stdout.splitlines() if line.startswith(name+'\t')]
                self.assertEqual(matches,[name+'\tPASS\terrno=0'],run.stdout)
            binder=[line for line in run.stdout.splitlines()
                    if line.startswith('binder_device_open\t')]
            self.assertEqual(len(binder),1)
            self.assertRegex(binder[0],r'^binder_device_open\t(?:BLOCKED|PRESENT_UNVERIFIED)\terrno=\d+$')
            self.assertNotIn('binder_device_open\tPASS',run.stdout)
            self.assertFalse('A08_GUEST_ABI_PASS' in run.stdout)

    def test_unavailable_syscall_cannot_count_as_host_pass(self):
        source=SOURCE.read_text()
        self.assertIn('!strcmp(state, "UNAVAILABLE_AT_COMPILE_TIME")',source)
        self.assertIn('sent.st_dev==got.st_dev',source)
        self.assertIn('sent.st_ino==got.st_ino',source)

if __name__=='__main__': unittest.main()
