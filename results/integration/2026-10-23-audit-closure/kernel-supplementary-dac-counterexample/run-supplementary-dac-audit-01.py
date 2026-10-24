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
output = data / 'supplementary-dac-audit-01'
output.mkdir(mode=0o700, exist_ok=False)
source = base / 'work/supplementary_dac_probe.c'
frozen = data / 'signal-argument-bounds'
sys.dont_write_bytecode = True
sys.path.insert(0, str(frozen / 'tests/kernel/control'))
from run_proc_boot_identity import pack, unpack
from run_g1c_guest import inspect_probe_elf

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

report = {'schema': 'trillionnium.supplementary-dac-controlled-audit.v1', 'source_sha256': sha(source),
    'expected_native_defect_observed': False, 'production_qualification': False, 'status': 'running', 'commands': []}

def save():
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

def run(name, argv, deadline):
    start = time.monotonic()
    with (output / (name + '.log')).open('xb') as log:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=deadline)
    report['commands'].append({'stage': name, 'argv': argv, 'exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 3)})
    save()
    return result.returncode

binary = output / 'supplementary-dac-probe'
compiler = '/usr/bin/x86_64-linux-gnu-gcc-13'
report['compiler_sha256'] = sha(Path(compiler))
assert run('compile', [compiler, '-static', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], 120) == 0
report.update(binary_sha256=sha(binary), elf_shape=inspect_probe_elf(binary.read_bytes()))
assert run('linux-reference', ['sudo', '-n', str(binary)], 30) == 0
linux = (output / 'linux-reference.log').read_text()
assert linux.count('SUPPLEMENTARY_DAC_CHECK') == 6
assert 'SUPPLEMENTARY_DAC_COMPLETE pass=1 reaped=2 production_ready=0' in linux
report['linux_reference_passed'] = True
ordinary = data / 'signal-bounds-native-0252-01/ordinary'
receipt = json.loads((ordinary / 'result.json').read_text())
kernel = ordinary / 'product-kernel.elf'
assert receipt['passed'] and receipt['source_inputs_unchanged']
assert sha(kernel) == receipt['kernel_elf_sha256'] == '202baef98b167989a85744f30290da3a85b9ce49d8e1e71c5acae662ed511014'
report.update(kernel_source=receipt['source_head'], kernel_sha256=sha(kernel), original_build_receipt=str(ordinary / 'result.json'))
original = frozen / 'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'
entries = unpack(gzip.decompress(original.read_bytes()))
invocation = b'''if /bin/supplementary-dac-probe; then
  echo SUPPLEMENTARY_DAC_PROBE_EXIT=0
else
  echo SUPPLEMENTARY_DAC_PROBE_EXIT=$?
fi
'''
marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
patched, found = [], 0
for name, fields, content in entries:
    if name.lstrip('./') == 'init':
        assert content.count(marker) == 1
        content = content.replace(marker, invocation + marker)
        found += 1
    assert name.lstrip('./') != 'bin/supplementary-dac-probe'
    patched.append((name, fields, content))
assert found == 1
inode = max(fields[0] for _, fields, _ in entries) + 1
patched.append(('bin/supplementary-dac-probe', [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], binary.read_bytes()))
archive = pack(patched)
assert len(unpack(archive)) == len(entries) + 1
initramfs = output / 'initramfs.cpio.gz'
initramfs.write_bytes(gzip.compress(archive, mtime=0))
assert initramfs.stat().st_size <= 8 * 1024 * 1024
shutil.copyfile('/usr/share/seabios/bios-256k.bin', output / 'bios.bin')
command = ['/usr/bin/qemu-system-x86_64', '-kernel', str(kernel), '-initrd', str(initramfs),
    '-bios', str(output / 'bios.bin'), '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
    '-machine', 'q35', '-accel', 'kvm', '-cpu', 'host', '-m', '512M', '-smp', '1',
    '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none', '-monitor', 'none',
    '-serial', 'stdio', '-nic', 'none', '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
assert run('native-baseline', command, 120) == 33
serial = re.sub(r'\x1b\[[0-9;]*m', '', (output / 'native-baseline.log').read_text(errors='replace')).replace('\r', '')
report['expected_native_defect_observed'] = (
    serial.count('SUPPLEMENTARY_DAC_CHECK') == 6
    and 'name=supplementary_file_read actual=0 expected=1 errno=13' in serial
    and 'name=supplementary_directory_search actual=0 expected=1 errno=13' in serial
    and 'SUPPLEMENTARY_DAC_COMPLETE pass=0 reaped=2 production_ready=0' in serial
    and 'SUPPLEMENTARY_DAC_PROBE_EXIT=42' in serial
    and serial.count('TRILLIONNIUM_A01_BOOT_OK') == 1)
report.update(status='complete', native_probe_exit=42 if report['expected_native_defect_observed'] else None,
    linux_log_sha256=sha(output / 'linux-reference.log'), native_log_sha256=sha(output / 'native-baseline.log'))
save()
assert report['expected_native_defect_observed'], 'baseline differed from the specific source hypothesis; inspect original logs'
