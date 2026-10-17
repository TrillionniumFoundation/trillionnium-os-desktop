"""Anti-false-positive A08 serial parser tests. Synthetic serial, NOT a QEMU run."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[3]/'support/android/run_asterinas_abi.py'
spec=importlib.util.spec_from_file_location('a08_abi_result_parser', SCRIPT)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def serial(*, abi=None, binder='blocked', seccomp='filter_install_missing', page_size=4096):
    abi=abi or {name: 'PASS' for name in runner.ABI_TESTS}
    lines=['TRILLIONNIUM_A01_INIT_BEGIN', 'A08_GUEST_ABI_BEGIN',
           f'# host=syscall_probe page_size={page_size} uid=0']
    lines.extend(f'{name}\t{status}\terrno={0 if status=="PASS" else 38}' for name,status in abi.items())
    lines.append('binder_device_open\t'+ ('BLOCKED\terrno=2' if binder=='blocked' else 'PRESENT_UNVERIFIED\terrno=0'))
    lines.append('A08_GUEST_ABI_PASS')
    lines.append('# binder_abi_probe uapi_expected=8 type=48')
    if binder == 'blocked':
        lines.extend(('binder_device_open\tBLOCKED\terrno=2', 'A08_GUEST_BINDER_EXIT:77'))
    elif binder == 'primitives':
        lines.extend(f'{name}\tPASS\terrno=0' for name in runner.BINDER_PRIMITIVES)
        lines.extend(('binder_transactions\tNOT_TESTED\terrno=0',
                      'binder_identity_death_fd_MAC\tNOT_TESTED\terrno=0',
                      'A08_GUEST_BINDER_PRIMITIVES_PASS'))
    lines.append('A08_GUEST_SECCOMP_BEGIN')
    if seccomp == 'filter_install_missing':
        lines.extend(('no_new_privs\tPASS\terrno=0',
                      'seccomp_filter_install\tFAIL\terrno=38',
                      'A08_GUEST_SECCOMP_EXIT:13'))
    elif seccomp == 'filter_works':
        lines.extend((name+'\tPASS\terrno=0' for name in
                      ('no_new_privs','seccomp_filter_install',
                       'seccomp_deny_getpid','seccomp_allow_getppid')))
        lines.extend(('seccomp_child\tPASS\texit=0',
                      'seccomp_TSYNC_multithread\tNOT_TESTED\terrno=0',
                      'Android_process_filters\tNOT_TESTED\terrno=0',
                      'A08_GUEST_SECCOMP_FILTER_PASS'))
    elif seccomp == 'compile_missing':
        lines.extend(('seccomp_syscall_available\tUNSUPPORTED_BUILD\terrno=0',
                      'A08_GUEST_SECCOMP_EXIT:77'))
    elif seccomp == 'marker_only':
        lines.append('A08_GUEST_SECCOMP_FILTER_PASS')
    lines.extend(('A08_GUEST_SECCOMP_END','A08_GUEST_ABI_END',
                  'TRILLIONNIUM_A01_BOOT_OK'))
    return '\n'.join(lines)+'\n'


class AbiResultParserTests(unittest.TestCase):
    def test_basic_syscalls_pass_with_missing_binder_stays_separately_blocked(self):
        r=runner.assess(33,serial())
        self.assertEqual(r['linux_abi_probe'],'pass',r['failure_reasons'])
        self.assertEqual(r['binder_probe'],'blocked_no_device')
        self.assertEqual(set(r['abi_syscalls']),set(runner.ABI_TESTS))
        self.assertFalse(r['binder_full_transactions_verified'])
        self.assertFalse(r['android_runtime_verified'])

    def test_actual_successful_ioctl_mmap_is_primitive_only(self):
        r=runner.assess(33,serial(binder='primitives'))
        self.assertEqual(r['linux_abi_probe'],'pass',r['failure_reasons'])
        self.assertEqual(r['binder_probe'],'primitive_ioctl_mmap_only')
        self.assertFalse(r['binder_full_transactions_verified'])

    def test_explicit_mmap_failure_cannot_be_overruled_by_exit33(self):
        abi={name:'PASS' for name in runner.ABI_TESTS};abi['mmap']='FAIL'
        r=runner.assess(33,serial(abi=abi))
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('abi_mmap_not_pass',r['failure_reasons'])

    def test_unavailable_memfd_is_failure_not_untested_pass(self):
        abi={name:'PASS' for name in runner.ABI_TESTS}
        abi['memfd_create']='UNAVAILABLE_AT_COMPILE_TIME'
        r=runner.assess(33,serial(abi=abi))
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('abi_memfd_create_not_pass',r['failure_reasons'])

    def test_missing_result_cannot_be_overruled_by_markers(self):
        abi={name:'PASS' for name in runner.ABI_TESTS if name!='SCM_RIGHTS'}
        r=runner.assess(33,serial(abi=abi))
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('abi_SCM_RIGHTS_missing',r['failure_reasons'])

    def test_duplicate_syscall_result_cannot_fake_reliability(self):
        raw=serial().replace('mmap\tPASS\terrno=0','mmap\tPASS\terrno=0\nmmap\tPASS\terrno=0')
        r=runner.assess(33,raw)
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('abi_mmap_duplicated',r['failure_reasons'])

    def test_marker_only_serial_is_not_syscall_evidence(self):
        raw='\n'.join(runner.REQUIRED)+'\nA08_GUEST_BINDER_PRIMITIVES_PASS\n'
        r=runner.assess(33,raw)
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertNotEqual(r['binder_probe'],'primitive_ioctl_mmap_only')

    def test_markers_must_be_ordered(self):
        lines=serial().splitlines()
        lines[0],lines[-1]=lines[-1],lines[0]
        r=runner.assess(33,'\n'.join(lines)+'\n')
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('guest_marker_order_invalid',r['failure_reasons'])

    def test_duplicate_marker_rejected(self):
        raw=serial()+'TRILLIONNIUM_A01_BOOT_OK\n'
        r=runner.assess(33,raw)
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('marker_TRILLIONNIUM_A01_BOOT_OK_duplicated',r['failure_reasons'])

    def test_mismatched_page_size_rejected(self):
        r=runner.assess(33,serial(page_size=16384))
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('guest_page_size_not_4096_or_missing',r['failure_reasons'])

    def test_panic_before_boot_marker_rejected(self):
        r=runner.assess(33,serial().replace('A08_GUEST_ABI_END','panicked at core/src\nA08_GUEST_ABI_END'))
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('kernel_panic_in_serial',r['failure_reasons'])

    def test_qemu_bad_raw_exit_even_valid_serial(self):
        r=runner.assess(0,serial())
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertIn('qemu_raw_exit_not_33',r['failure_reasons'])

    def test_binder_marker_alone_cannot_pass_ioctl(self):
        raw=serial(binder='primitives').replace('binder_mmap\tPASS\terrno=0\n','')
        r=runner.assess(33,raw)
        self.assertEqual(r['binder_probe'],'unproven_primitives')
        self.assertEqual(r['linux_abi_probe'],'fail')

    def test_binder_unverified_device_open_inconsistent_with_77(self):
        raw=serial(binder='blocked').replace('binder_device_open\tBLOCKED\terrno=2',
                                              'binder_device_open\tPRESENT_UNVERIFIED\terrno=0',1)
        r=runner.assess(33,raw)
        self.assertEqual(r['binder_probe'],'inconsistent_open_status')
        self.assertEqual(r['linux_abi_probe'],'fail')

    def test_binder_no_device_marker_needs_errno_line(self):
        raw=serial().replace('binder_device_open\tBLOCKED\terrno=2\nA08_GUEST_BINDER_EXIT:77',
                              'A08_GUEST_BINDER_EXIT:77')
        r=runner.assess(33,raw)
        self.assertEqual(r['binder_probe'],'unproven_open_failure')
        self.assertEqual(r['linux_abi_probe'],'fail')

    def test_binder_failed_exit_never_counts_as_ioctl_primitive(self):
        raw=serial().replace('A08_GUEST_BINDER_EXIT:77','A08_GUEST_BINDER_EXIT:1')
        r=runner.assess(33,raw)
        self.assertEqual(r['binder_probe'],'probe_failed')
        self.assertNotEqual(r['binder_probe'],'primitive_ioctl_mmap_only')

    def test_qemu_kernel_override_blocked(self):
        cmd=['qemu-system-x86_64','-kernel','old','-initrd','old-init',
             '-append','console=ttyS0 init=/bin/sh', '-machine','q35','-accel','tcg',
             '-cpu','max','-bios','old-bios','-m','512M','-smp','1',
             '-nodefaults','-no-user-config','-no-reboot','-nographic',
             '-display','none','-monitor','none','-serial','chardev:serial',
             '-chardev','stdio,id=serial,signal=off,logfile=qemu.log',
             '-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaisesRegex(ValueError,'unsafe or unrecognized'):
                runner.safe_argv({'argv':cmd},kernel=root/'k',initramfs=root/'i',
                                  bios=root/'b',qemu=root/'q',log=root/'serial')

    def test_qemu_known_A01_duplicate_environment_is_accepted(self):
        cmd=['qemu-system-x86_64','-kernel','old','-initrd','old-init',
             '-append','earlycon console=ttyS0 console=ttyS0 loglevel=info '
                       'SHELL=/bin/sh SHELL=/bin/sh LOGNAME=root HOME=/ USER=root '
                       'PATH=/bin:/sbin PATH=/bin:/sbin --',
             '-machine','q35','-accel','tcg','-cpu','max','-bios','old-bios',
             '-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot',
             '-nographic','-display','none','-monitor','none','-serial','chardev:serial',
             '-chardev','stdio,id=serial,signal=off,logfile=qemu.log',
             '-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            r=runner.safe_argv({'argv':cmd},kernel=root/'k',initramfs=root/'i',
                               bios=root/'b',qemu=root/'q',log=root/'serial')
            self.assertIn('earlycon',r[r.index('-append')+1])

    def test_qemu_reject_chardev_additional_host_options(self):
        cmd=['qemu-system-x86_64','-kernel','old','-initrd','old-init','-append','console=ttyS0',
             '-machine','q35','-accel','tcg','-cpu','max','-bios','bios',
             '-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot',
             '-nographic','-display','none','-monitor','none', '-serial','chardev:serial',
             '-chardev','stdio,id=serial,signal=off,logfile=qemu.log,append=on',
             '-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaisesRegex(ValueError,'exact A01 logging profile'):
                runner.safe_argv({'argv':cmd},kernel=root/'k',initramfs=root/'i',
                                  bios=root/'b',qemu=root/'q',log=root/'serial')

if __name__=='__main__': unittest.main()
