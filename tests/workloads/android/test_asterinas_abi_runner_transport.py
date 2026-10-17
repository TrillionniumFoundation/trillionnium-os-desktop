"""Real host subprocess + fake QEMU executable. Synthetic serial is NOT guest evidence."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_abi_result_parser import serial

SCRIPT=Path(__file__).resolve().parents[3]/'support/android/run_asterinas_abi.py'
spec=importlib.util.spec_from_file_location('a08_qemu_host_transport',SCRIPT)
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class GuestSubprocessTransportTests(unittest.TestCase):
    def fixture(self, root, guest_serial=None):
        root=Path(root)
        kernel=root/'kernel.elf';kernel.write_bytes(b'SYNTHETIC_KERNEL_NOT_REAL_A01')
        initrd=root/'a08-init.cpio.gz';initrd.write_bytes(b'SYNTHETIC_INITRAMFS')
        bios=root/'bios.bin';bios.write_bytes(b'SYNTHETIC_BIOS')
        manifest=root/'manifest.json'
        manifest.write_text(json.dumps({'kind':'a08_asterinas_abi_initramfs',
                                        'image_sha256':run.sha(initrd)}))
        qemu=root/'qemu-system-x86_64'
        trace=serial() if guest_serial is None else guest_serial
        qemu.write_text('#!'+sys.executable+'\n'
                        'import pathlib,sys\n'
                        'if "--version" in sys.argv:\n'
                        ' print("QEMU emulator version FAKE_HOST_TRANSPORT")\n'
                        ' sys.exit(0)\n'
                        'entry=sys.argv[sys.argv.index("-chardev")+1]\n'
                        'path=entry.split("logfile=",1)[1]\n'
                        'pathlib.Path(path).write_bytes('+repr(trace.encode()+b'\xff')+')\n'
                        'sys.stdout.buffer.write(b"synthetic fake qemu\\xff\\n")\n'
                        'sys.stderr.buffer.write(b"not a real qemu guest\\xfe\\n")\n'
                        'sys.exit(33)\n')
        qemu.chmod(0o755)
        argv=[str(qemu),'-kernel','old.elf','-initrd','old.img',
              '-append','earlycon console=ttyS0 loglevel=info SHELL=/bin/sh '
                        'LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
              '-machine','q35','-accel','tcg','-cpu','max','-bios','old-bios',
              '-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot',
              '-nographic','-display','none','-monitor','none',
              '-serial','chardev:serial',
              '-chardev','stdio,id=serial,signal=off,logfile=qemu.log',
              '-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
        template=root/'a01-qemu.json'
        template.write_text(json.dumps({'argv':argv,'raw_exit_code':33,'timed_out':False,
                    'qemu_sha256':run.sha(qemu),'artifacts':{
                    '-kernel':{'sha256':run.sha(kernel)},
                    '-bios':{'sha256':run.sha(bios)}}}))
        return [template,kernel,run.sha(kernel),initrd,manifest,bios,qemu,root/'fresh-evidence']

    def test_real_host_subprocess_and_raw_serial_hash(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            report=run.execute(*args)
            self.assertEqual(report['qemu_exit'],33)
            self.assertEqual(report['result']['linux_abi_probe'],'pass',report['result']['failure_reasons'])
            self.assertEqual(report['result']['binder_probe'],'blocked_no_device')
            self.assertFalse(report['result']['android_runtime_verified'])
            self.assertTrue((args[-1]/'stdout.log').read_bytes().endswith(b'\xff\n'))
            self.assertTrue((args[-1]/'stderr.log').read_bytes().endswith(b'\xfe\n'))
            self.assertEqual(report['serial_sha256'],run.sha(args[-1]/'serial.log'))
            self.assertTrue((args[-1]/'serial.log').read_bytes().endswith(b'\xff'))
            self.assertEqual(json.loads((args[-1]/'result.json').read_text())['qemu_exit'],33)

    def test_marker_only_stdout_with_fake_qemu_exit33_is_red(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td, '\n'.join(run.REQUIRED)+'\n')
            report=run.execute(*args)
            self.assertEqual(report['result']['linux_abi_probe'],'fail')
            self.assertNotEqual(report['result']['binder_probe'],'primitive_ioctl_mmap_only')

    def test_modified_qemu_executable_sha_is_blocked_before_run(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            args[-2].write_text(args[-2].read_text()+'\n# MALICIOUS MODIFICATION\n')
            with self.assertRaisesRegex(ValueError,'QEMU binary differs'):
                run.execute(*args)
            self.assertFalse(args[-1].exists())

    def test_failed_a01_reference_boot_is_not_reused(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            t=json.loads(args[0].read_text());t['raw_exit_code']=65
            args[0].write_text(json.dumps(t))
            with self.assertRaisesRegex(ValueError,'no verified success exit'):
                run.execute(*args)
            self.assertFalse(args[-1].exists())

    def test_modified_abi_image_is_blocked_before_run(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            args[3].write_bytes(b'BOGUS_SILENT_SWAP')
            with self.assertRaisesRegex(ValueError,'initramfs image does not match'):
                run.execute(*args)
            self.assertFalse(args[-1].exists())

    def test_nonpositive_timeout_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            with self.assertRaisesRegex(ValueError,'timeout must be between'):
                run.execute(*args,timeout=0)
            self.assertFalse(args[-1].exists())

if __name__=='__main__': unittest.main()
