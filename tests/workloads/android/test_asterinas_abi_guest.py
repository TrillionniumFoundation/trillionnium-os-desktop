"""Host-only A08 initramfs/QEMU template tests; no QEMU guest actually boots."""
import gzip
import importlib.util
import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


def load(name):
    p=ROOT/'support/android'/name
    spec=importlib.util.spec_from_file_location(name.replace('.py',''),p)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

prep=load('prepare_asterinas_abi.py')
runner=load('run_asterinas_abi.py')

# Test double for A01 packer API only; use real ELF executable compiler and
# actual gzip/newc bytes in the tested A08 packer. A01 source is NOT modified.
PACKER='''import struct\nimport stat\nAPPLETS=("sh","mount","poweroff","cat","uname","test","grep")\n\ndef check_static_x86_64_elf(data):\n if data[:7]!=b"\\x7fELF\\x02\\x01\\x01" or struct.unpack_from("<H",data,18)[0]!=62: raise ValueError("not x86_64 ELF64")\n offset=struct.unpack_from("<Q",data,32)[0]\n size,count=struct.unpack_from("<HH",data,54)\n for i in range(count):\n  if struct.unpack_from("<I",data,offset+size*i)[0]==3: raise ValueError("PT_INTERP")\n\ndef cpio_entry(name, mode, data, inode):\n name=(name.encode()+b"\\0")\n fields=(inode,mode,0,0,2 if stat.S_ISDIR(mode) else 1,0,len(data),0,0,0,0,len(name),0)\n head=b"070701"+b"".join(f"{v:08x}".encode() for v in fields)\n out=head+name\n out+=b"\\0"*(-len(out)%4)\n out+=data\n return out+b"\\0"*(-len(data)%4)\n'''
INIT='''#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_INIT_BEGIN"\n/bin/busybox sh /test/boot_hello.sh\necho "TRILLIONNIUM_A01_BOOT_OK"\nexec /bin/busybox poweroff -f\n'''
TEMPLATE=['/usr/bin/qemu-system-x86_64','-kernel','/prior/asterinas.elf',
 '-initrd','/prior/initramfs.cpio.gz','-append','console=ttyS0',
 '-machine','q35','-accel','tcg','-cpu','max','-bios','/usr/share/seabios/bios-256k.bin',
 '-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot',
 '-nographic','-display','none','-monitor','none','-serial','chardev:serial',
 '-chardev','stdio,id=serial,signal=off,logfile=qemu.log',
 '-device','isa-debug-exit,iobase=0xf4,iosize=0x04']


def newc_files(data):
    found={}
    i=0
    while i+110<=len(data):
        assert data[i:i+6]==b'070701'
        fields=[int(data[i+6+j*8:i+14+j*8],16) for j in range(13)]
        size,namesize=fields[6],fields[11]
        name=data[i+110:i+110+namesize-1].decode()
        p=i+110+namesize;p+=-p%4
        contents=data[p:p+size]
        found[name]=contents
        i=p+size;i+=-i%4
        if name=='TRAILER!!!':break
    return found


class GuestAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):
            raise unittest.SkipTest('C compiler missing')

    def fixture(self,root):
        root=Path(root)
        a01=root/'a01_packer.py';a01.write_text(PACKER)
        init=root/'init';init.write_text(INIT)
        boot=root/'boot_hello.sh';boot.write_text('echo UPSTREAM_BOOT\n')
        source=root/'stub.c';source.write_text('int main(void) { return 0; }\n')
        exe=root/'static-stub'
        cmd=['cc','-static','-O2',str(source),'-o',str(exe)]
        run=subprocess.run(cmd,capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,0,run.stderr)
        return {'busybox':exe,'kernel_probe':exe,'binder_probe':exe, 'seccomp_probe':exe,
                'dest':root/'a08.cpio.gz','manifest':root/'a08.json',
                'builder':a01,'a01_init':init,'smoke':boot}

    def test_pack_a08_without_changing_a01(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            original=args['a01_init'].read_bytes()
            record=prep.prepare(**args)
            self.assertEqual(args['a01_init'].read_bytes(),original)
            self.assertFalse(record['guest_executed'])
            self.assertFalse(record['android_qualified'])
            self.assertEqual(record['image_sha256'],runner.sha(args['dest']))
            archive=newc_files(gzip.decompress(args['dest'].read_bytes()))
            self.assertIn('test/a08-kernel-abi',archive)
            self.assertIn('test/a08-binder-abi',archive)
            self.assertIn('test/a08-seccomp-abi',archive)
            self.assertIn('A08_GUEST_ABI_BEGIN',archive['init'].decode())
            self.assertIn('TRILLIONNIUM_A01_BOOT_OK',archive['init'].decode())

    def test_packer_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            first=prep.prepare(**args)['image_sha256']
            args['dest']=Path(td)/'second.cpio.gz'
            args['manifest']=Path(td)/'second.json'
            self.assertEqual(prep.prepare(**args)['image_sha256'],first)

    def test_prevent_overwriting_existing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            prep.prepare(**args)
            with self.assertRaisesRegex(ValueError,'already exist'):
                prep.prepare(**args)

    def test_missing_or_dynamic_binary_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            args['kernel_probe']=Path(td)/'missing.elf'
            with self.assertRaisesRegex(ValueError,'missing static executable'):
                prep.prepare(**args)

    def test_malformed_a01_init_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.fixture(td)
            args['a01_init'].write_text('echo only_some_other_marker\n')
            with self.assertRaisesRegex(ValueError,'profile changed'):
                prep.prepare(**args)

    def test_accept_only_A01_safe_TCG_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            args=runner.safe_argv({'argv':TEMPLATE},kernel=root/'kernel',
             initramfs=root/'initrd',bios=root/'bios',qemu=root/'qemu',log=root/'serial')
            self.assertIn('-accel',args)
            self.assertIn('tcg',args)
            self.assertNotIn('-enable-kvm',args)
            self.assertTrue(args[args.index('-chardev')+1].endswith('/serial'))

    def test_reject_device_or_network_qemu_template(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            argv=list(TEMPLATE)+['-drive','file=hostdisk.qcow2']
            with self.assertRaisesRegex(ValueError,'unsafe host'):
                runner.safe_argv({'argv':argv},kernel=root/'k',initramfs=root/'i',
                                 bios=root/'b',qemu=root/'q',log=root/'s')

    def test_reject_unrecognized_qmp_host_socket(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            argv=list(TEMPLATE)+['-qmp','unix:/tmp/qmp,server=on']
            with self.assertRaisesRegex(ValueError,'unsafe host'):
                runner.safe_argv({'argv':argv},kernel=root/'k',initramfs=root/'i',
                                 bios=root/'b',qemu=root/'q',log=root/'s')

    def test_reject_smp_profile_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            argv=list(TEMPLATE);argv[argv.index('-smp')+1]='8'
            with self.assertRaisesRegex(ValueError,'profile mismatch'):
                runner.safe_argv({'argv':argv},kernel=root/'k',initramfs=root/'i',
                                 bios=root/'b',qemu=root/'q',log=root/'s')

    def test_no_guest_marker_even_exit33_fails(self):
        r=runner.assess(33,'TRILLIONNIUM_A01_BOOT_OK\n')
        self.assertEqual(r['linux_abi_probe'],'fail')
        self.assertFalse(r['android_runtime_verified'])

    def test_guest_abi_pass_binder_missing_is_still_blocked(self):
        from test_abi_result_parser import serial
        r=runner.assess(33,serial())
        self.assertEqual(r['linux_abi_probe'],'pass')
        self.assertEqual(r['binder_probe'],'blocked_no_device')
        self.assertFalse(r['android_runtime_verified'])

    def test_one_command_static_builder_isolated_and_no_A01_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            inputs=self.fixture(root)
            checkout=root/'checkout'
            scripts=checkout/'support/android'
            scripts.mkdir(parents=True)
            for item in ('build_asterinas_abi.sh','prepare_asterinas_abi.py'):
                shutil.copy2(ROOT/'support/android'/item,scripts/item)
            upstream=checkout/'support/build/minimal'
            upstream.mkdir(parents=True)
            (upstream/'prepare-initramfs.py').write_text(PACKER)
            (upstream/'init').write_text(INIT)
            boot=checkout/'kernel/asterinas/test/initramfs/src/boot_hello.sh'
            boot.parent.mkdir(parents=True)
            boot.write_text('echo UPSTREAM_BOOT\n')
            probe_dir=checkout/'tests/workloads/android'
            probe_dir.mkdir(parents=True)
            for name in ('kernel_abi_probe.c','binder_abi_probe.c','seccomp_abi_probe.c'):
                (probe_dir/name).write_text('int main(void){return 0;}\n')
            evidence=root/'isolated-evidence'
            args=['bash',str(scripts/'build_asterinas_abi.sh')]
            env={**os.environ,'A08_ABI_OUTPUT':str(evidence),
                 'A08_BUSYBOX_STATIC':str(inputs['busybox'])}
            built=subprocess.run(args,capture_output=True,text=True,
                                 env=env,timeout=60,check=False)
            self.assertEqual(built.returncode,0,built.stderr)
            result=json.loads((evidence/'manifest.json').read_text())
            self.assertFalse(result['guest_executed'])
            self.assertEqual(result['image_sha256'],runner.sha(evidence/'a08-initramfs.cpio.gz'))
            self.assertEqual((upstream/'init').read_text(),INIT)
            rejected=subprocess.run(args,capture_output=True,text=True,
                                    env=env,timeout=10,check=False)
            self.assertEqual(rejected.returncode,2)
            self.assertIn('Refusing to overwrite',rejected.stderr)

    def test_kernel_sha_mismatch_rejected_before_qemu_launch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            kernel=root/'kernel';kernel.write_bytes(b'not-an-A01-build')
            with self.assertRaisesRegex(ValueError,'SHA256'):
                runner.execute(root/'a01.json',kernel,'0'*64,root/'image',
                               root/'manifest',root/'bios',root/'qemu',root/'results')
            self.assertFalse((root/'results').exists())

if __name__=='__main__':unittest.main()
