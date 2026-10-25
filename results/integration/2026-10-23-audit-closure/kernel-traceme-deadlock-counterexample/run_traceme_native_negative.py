"""Disposable prebuilt-kernel negative; never builds a kernel or touches SDK."""
from pathlib import Path
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time

audit = Path(__file__).resolve().parent
data = Path('/data/asterinas-audit-build.8tdrjboi')
source = data / 'inline-signal-rtqueue'
sys.dont_write_bytecode = True
sys.path.insert(0, str(source / 'tests/kernel/control'))
from run_proc_boot_identity import pack, unpack
from run_g1c_guest import inspect_probe_elf

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
cases = {
    'traceme': ('traceme-v1/traceme-probe', 'traceme-linux-reference-01.json',
                'signal-bounds-native-0252-01', ''),
}
assert len(sys.argv) == 2 and sys.argv[1] in cases
kind = sys.argv[1]
binary_rel, linux_name, kernel_dir, arguments = cases[kind]
out = audit / 'traceme-native-0252-negative-01'
out.mkdir(mode=0o700, exist_ok=False)
binary = audit / binary_rel
linux = json.loads((audit / linux_name).read_text())
assert linux['exit'] == 0 and linux['inputs_unchanged']
binary_sha = linux.get('binary_sha256', linux.get('input_sha256', {}).get('lifecycle-probe'))
assert sha(binary) == binary_sha
ordinary = data / kernel_dir / 'ordinary'
receipt = ordinary / 'result.json'
original_result = json.loads(receipt.read_text())
kernel = ordinary / 'product-kernel.elf'
assert original_result['passed'] and original_result['source_inputs_unchanged']
assert sha(kernel) == original_result['kernel_elf_sha256']
shape = inspect_probe_elf(binary.read_bytes())
original = source / 'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'
assert sha(original) == original_result['original_initramfs_sha256']
entries = unpack(gzip.decompress(original.read_bytes()))
marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
probe_name = f'bin/dumpable-lifecycle-{kind}'
invocation = (f'if /{probe_name} {arguments}; then\n'
              ' echo DUMPABLE_LIFECYCLE_EXIT=0\nelse\n'
              ' echo DUMPABLE_LIFECYCLE_EXIT=$?\nfi\n').encode()
new, found = [], 0
for name, fields, content in entries:
    assert name.lstrip('./') != probe_name
    if name.lstrip('./') == 'init':
        assert content.count(marker) == 1
        content = content.replace(marker, invocation + marker)
        found += 1
    new.append((name, fields, content))
assert found == 1
inode = max(fields[0] for _, fields, _ in entries) + 1
new.append((probe_name, [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], binary.read_bytes()))
archive = pack(new)
assert len(unpack(archive)) == len(entries) + 1
initrd = out / 'initramfs.cpio.gz'
initrd.write_bytes(gzip.compress(archive, mtime=0))
assert initrd.stat().st_size <= 8 * 1024 * 1024
bios = out / 'bios.bin'
shutil.copyfile('/usr/share/seabios/bios-256k.bin', bios)
qemu = Path('/usr/bin/qemu-system-x86_64')
assert sha(qemu) == '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854'
command = [str(qemu), '-kernel', str(kernel), '-initrd', str(initrd), '-bios', str(bios),
           '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
           '-machine', 'q35', '-accel', 'kvm', '-cpu', 'host', '-m', '512M', '-smp', '1',
           '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
           '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
           '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
r = {'schema_version': 1, 'command': command, 'status': 'running', 'passed': False,
     'expected_negative': True, 'original_kernel_receipt': str(receipt),
     'kernel_receipt_sha256': sha(receipt), 'kernel_sha256': sha(kernel),
     'kernel_source': original_result['source_head'], 'kernel_tree': original_result['source_tree'],
     'probe_binary': str(binary), 'probe_sha256': binary_sha, 'shape': shape,
     'linux_receipt': str(audit / linux_name), 'linux_receipt_sha256': sha(audit / linux_name),
     'original_initrd_sha256': sha(original), 'injected_initrd_sha256': sha(initrd),
     'bios_sha256': sha(bios), 'qemu_sha256': sha(qemu), 'timeout_seconds': 120,
     'memory_mib': 512, 'smp': 1, 'sdk_or_kernel_rebuilt': False, 'production_isolation_qualified': False}
(out / 'result.json').write_text(json.dumps(r, indent=2) + '\n')
start = time.monotonic()
with (out / 'serial.log').open('xb') as f:
    try:
        rc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=f,
                            stderr=subprocess.STDOUT, timeout=120).returncode
    except subprocess.TimeoutExpired:
        rc = None
text = re.sub(r'\x1b\[[0-9;]*m', '', (out / 'serial.log').read_text(errors='replace')).replace('\r', '')
observations = []
for line in text.splitlines():
    if line.startswith('{'):
        try:
            observations.append(json.loads(line))
        except json.JSONDecodeError:
            pass
summaries = [v for v in observations if v.get('summary')]
failures = [v for v in observations if v.get('passed') is False]
negative = (rc == 33 and text.count('DUMPABLE_LIFECYCLE_EXIT=42') == 1
            and text.count('TRILLIONNIUM_A01_BOOT_OK') == 1
            and len(summaries) == 1 and summaries[0].get('all_children_reaped') is True
            and len(failures) > 0)
r.update(status='complete', raw_qemu_exit=rc, seconds=time.monotonic() - start,
         probe_exit_42=text.count('DUMPABLE_LIFECYCLE_EXIT=42') == 1,
         serial_sha256=sha(out / 'serial.log'), observations=observations,
         failed_observations=failures, summaries=summaries, expected_negative_reproduced=negative,
         inputs_unchanged=sha(binary) == binary_sha and sha(receipt) == r['kernel_receipt_sha256']
         and sha(kernel) == r['kernel_sha256'])
(out / 'result.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps({'out': str(out), 'raw_qemu_exit': rc, 'expected_negative_reproduced': negative,
                  'failed_observations': len(failures), 'summaries': summaries}), flush=True)
assert negative and r['inputs_unchanged']
