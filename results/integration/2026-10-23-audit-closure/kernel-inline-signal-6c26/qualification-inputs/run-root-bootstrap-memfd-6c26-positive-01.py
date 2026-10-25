from pathlib import Path
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time

base = Path(__file__).resolve().parents[1]
data = Path('/data/asterinas-audit-build.8tdrjboi')
out = data / 'root-bootstrap-memfd-6c26-positive-01'
out.mkdir(mode=0o700, exist_ok=False)
source = data / 'inline-signal-rtqueue'
sys.dont_write_bytecode = True
sys.path.insert(0, str(source / 'tests/kernel/control'))
from run_proc_boot_identity import pack, unpack
from run_g1c_guest import inspect_probe_elf

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

build = data / 'root-bootstrap-memfd-build-01'
compiled = json.loads((build / 'result.json').read_text())
binary = build / 'root-bootstrap-memfd-probe'
assert compiled['exit_code'] == 0 and sha(binary) == compiled['binary_sha256']
shape = inspect_probe_elf(binary.read_bytes())
baseline = data / 'root-bootstrap-memfd-d5a21-baseline-01'
previous = json.loads((baseline / 'result.json').read_text())
assert previous['linux_reference_passed'] and previous['expected_nlink_one_refusal_observed']
assert previous['binary_sha256'] == sha(binary)
assert sha(baseline / 'linux.log') == previous['linux_log_sha256']
linux_command = previous['linux_command']

ordinary = data / 'inline-signal-native-6c26-01/ordinary'
receipt = json.loads((ordinary / 'result.json').read_text())
kernel = ordinary / 'product-kernel.elf'
assert receipt['passed'] and receipt['source_inputs_unchanged'] and sha(kernel) == receipt['kernel_elf_sha256']
original = source / 'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'
entries = unpack(gzip.decompress(original.read_bytes()))
invocation = b'''if /bin/root-bootstrap-memfd-probe --disposable-guest; then
  echo ROOT_BOOTSTRAP_MEMFD_PROBE_EXIT=0
else
  echo ROOT_BOOTSTRAP_MEMFD_PROBE_EXIT=$?
fi
'''
marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
patched = []
found = 0
for name, fields, content in entries:
    assert name.lstrip('./') != 'bin/root-bootstrap-memfd-probe'
    if name.lstrip('./') == 'init':
        assert content.count(marker) == 1
        content = content.replace(marker, invocation + marker)
        found += 1
    patched.append((name, fields, content))
assert found == 1
ino = max(fields[0] for _, fields, _ in entries) + 1
patched.append(('bin/root-bootstrap-memfd-probe', [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], binary.read_bytes()))
archive = pack(patched)
assert len(unpack(archive)) == len(entries) + 1
initramfs = out / 'initramfs.cpio.gz'
initramfs.write_bytes(gzip.compress(archive, mtime=0))
assert initramfs.stat().st_size <= 8 * 1024 * 1024
shutil.copyfile('/usr/share/seabios/bios-256k.bin', out / 'bios.bin')
command = ['/usr/bin/qemu-system-x86_64', '-kernel', str(kernel), '-initrd', str(initramfs),
           '-bios', str(out / 'bios.bin'), '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
           '-machine', 'q35', '-accel', 'kvm', '-cpu', 'host', '-m', '512M', '-smp', '1',
           '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
           '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
           '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
report = {'schema': 'hepta.root-bootstrap-memfd-qualification.v1', 'source_sha256': compiled['source_sha256'],
          'binary_sha256': sha(binary), 'shape': shape, 'linux_command': linux_command,
          'linux_reference_passed': True, 'kernel_source': receipt['source_head'], 'kernel_sha256': sha(kernel),
          'qemu_argv': command, 'guest_deadline_seconds': 120, 'native_qualification_passed': False, 'linux_reference_receipt': str(baseline / 'result.json'),
          'production_authority': False, 'status': 'running'}
def save():
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
save()
started = time.monotonic()
timed_out = False
with (out / 'serial.log').open('xb') as stream:
    try:
        code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                              stderr=subprocess.STDOUT, timeout=120).returncode
    except subprocess.TimeoutExpired:
        code = None
        timed_out = True
text = re.sub(r'\x1b\[[0-9;]*m', '', (out / 'serial.log').read_text(errors='replace')).replace('\r', '')
passed = (code == 33 and not timed_out
          and text.count('ROOT_BOOTSTRAP_MEMFD_OBSERVED uid=0 links=0 mode=400 seals=15') == 1
          and text.count('ROOT_BOOTSTRAP_MEMFD_CHILD uid=60001 caps=0 nnp=1 immutable=1') == 1
          and text.count('ROOT_BOOTSTRAP_MEMFD_COMPLETE pass=1 production_ready=0') == 1
          and text.count('ROOT_BOOTSTRAP_MEMFD_PROBE_EXIT=0') == 1
          and 'ROOT_BOOTSTRAP_MEMFD_FAIL' not in text
          and text.count('TRILLIONNIUM_A01_BOOT_OK') == 1)
report.update(raw_qemu_exit=code, timed_out=timed_out, native_qualification_passed=passed,
              native_probe_exit=0 if passed else None, seconds=round(time.monotonic() - started, 3),
              linux_log_sha256=sha(baseline / 'linux.log'), serial_sha256=sha(out / 'serial.log'), status='complete')
save()
assert passed, 'actual native Root sealed memfd handoff qualification failed'
