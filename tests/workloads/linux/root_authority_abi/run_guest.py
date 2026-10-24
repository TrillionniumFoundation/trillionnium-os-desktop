#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run the identical Root ABI ELF against an existing ordinary native kernel."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'tests/kernel/control'))
from run_proc_boot_identity import pack, unpack
from run_g1c_guest import inspect_probe_elf


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('kernel', 'initramfs', 'probe', 'output'):
        parser.add_argument('--'+field, type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    source_name = 'probe.c'
    probe_name = 'root-authority-abi-probe'
    marker_prefix = 'ROOT_AUTHORITY_ABI_PROBE_EXIT'
    out = args.output.resolve()
    require(not out.exists() and ',' not in str(out), 'new output without QEMU separators required')
    require(args.kernel.read_bytes()[:4] == b'\x7fELF', 'actual kernel ELF required')
    reference = json.loads(args.reference.read_text())
    require(reference.get('schema') == 'trillionnium.root-authority-abi-linux.v1' and
            reference.get('passed') is True and reference['exit_code'] == 0 and
            reference.get('g2_complete') is False, 'successful original-scope Linux reference required')
    require(reference['checker_sha256'] == sha(HERE/'check.py'), 'Linux checker changed')
    require(sha(HERE/source_name) == reference['source_sha256'], 'original source mismatch')
    require(sha(args.probe) == reference['binary_sha256'], 'requires the same Linux-referenced binary')
    shape = inspect_probe_elf(args.probe.read_bytes())
    kernel_hash = sha(args.kernel)
    input_paths = {'kernel': args.kernel, 'probe': args.probe, 'reference': args.reference,
                   'initramfs': args.initramfs, 'source': HERE/source_name,
                   'checker': HERE/'check.py', 'runner': Path(__file__)}
    input_before = {name: sha(path) for name, path in input_paths.items()}
    out.mkdir(parents=True)
    shutil.copyfile(args.probe, out/'probe.elf')
    shutil.copyfile(args.kernel, out/'kernel.elf')
    require(sha(out/'probe.elf') == reference['binary_sha256'], 'copied probe changed')
    require(sha(out/'kernel.elf') == kernel_hash, 'copied kernel changed')
    shutil.copyfile('/usr/share/seabios/bios-256k.bin', out/'bios.bin')
    entries = unpack(gzip.decompress(args.initramfs.read_bytes()))
    invocation = f'if /bin/{probe_name}; then\n  echo {marker_prefix}=0\nelse\n  echo {marker_prefix}=$?\nfi\n'.encode()
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    patched, found = [], 0
    for name, fields, content in entries:
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1, 'original boot marker must be unique')
            content = content.replace(marker, invocation+marker); found += 1
        require(name.lstrip('./') != 'bin/'+probe_name, 'duplicate probe entry')
        patched.append((name, fields, content))
    require(found == 1, 'original init required')
    inode = max(fields[0] for _, fields, _ in entries)+1
    patched.append(('bin/'+probe_name, [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], args.probe.read_bytes()))
    archive = pack(patched)
    require(len(unpack(archive)) == len(entries)+1, 'archive roundtrip mismatch')
    (out/'initramfs.cpio.gz').write_bytes(gzip.compress(archive, mtime=0))
    require((out/'initramfs.cpio.gz').stat().st_size <= 8*1024*1024, 'original 8 MiB archive bound')
    argv = ['/usr/bin/qemu-system-x86_64', '-kernel', str(out/'kernel.elf'), '-initrd', str(out/'initramfs.cpio.gz'),
            '-bios', str(out/'bios.bin'), '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'kvm', '-cpu', 'host', '-m', '512M', '-smp', '1',
            '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none', '-monitor', 'none',
            '-serial', 'stdio', '-nic', 'none', '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    start = time.monotonic(); timed_out = False
    with (out/'serial.log').open('wb') as log:
        try:
            code = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=120).returncode
        except subprocess.TimeoutExpired:
            code, timed_out = None, True
    spec = importlib.util.spec_from_file_location('root_authority_abi_oracle', HERE/'check.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    oracle = checker.check((out/'serial.log').read_bytes(), code, timed_out, guest=True)
    input_after = {name: sha(path) for name, path in input_paths.items()}
    inputs_unchanged = (input_before == input_after and sha(out/'probe.elf') == input_before['probe']
                        and sha(out/'kernel.elf') == input_before['kernel'])
    report = {'schema':'trillionnium.root-authority-abi-native.v1',
              'passed':oracle['passed'] and inputs_unchanged, 'oracle':oracle,
              'inputs_unchanged':inputs_unchanged, 'input_before':input_before, 'input_after':input_after,
              'qemu_exit':code, 'timed_out':timed_out,
              'elapsed_seconds':time.monotonic()-start, 'qemu_argv':argv, 'elf_shape':shape,
              'kernel_sha256':sha(out/'kernel.elf'), 'probe_sha256':sha(out/'probe.elf'),
              'probe_source_sha256':sha(HERE/source_name), 'linux_reference_receipt_sha256':sha(args.reference),
              'runner_source_sha256':sha(Path(__file__)), 'checker_source_sha256':sha(HERE/'check.py'),
              'original_initramfs_sha256':sha(args.initramfs), 'initramfs_sha256':sha(out/'initramfs.cpio.gz'),
              'bios_sha256':sha(out/'bios.bin'), 'serial_sha256':sha(out/'serial.log'), 'production_qualification':False,
              'original_writer_executed':False, 'persistent_cpu_qualified':False,
              'recovery_qualified':False, 'g2_complete':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','kernel_sha256','qemu_exit']},indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
