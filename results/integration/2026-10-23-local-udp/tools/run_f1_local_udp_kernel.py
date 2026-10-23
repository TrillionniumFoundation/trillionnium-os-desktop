#!/usr/bin/env python3
"""Run the unchanged F1 fixture with the ordinary kernel plus the local UDP error fix.

Only the kernel image differs from the ordinary warn-mode guest. Original
Agentd/helper/launcher/payload, PID topology, environment and deadlines remain
unchanged. The reused Agentd is the existing diagnostic ELF; even a successful
lifecycle does not establish production build attestation or G2 authority.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/qian-qi/work/trillionnium-os-20261021-b2da20752f15')
REFERENCE = ROOT / 'f1-closure-stop-diagnostic-20261023-v1/guest'
HARNESS = ROOT / 'f1-guest-harness-afunix-kernel-v1'
BASE_HEAD = 'b824d80d44456c131a6cb9d4fcc84be95c6af273'
FIXED_HEAD = 'c8f0c88ecb640117686ff05f850a73e60688eac7'
FIXED_TREE = '641c6627ba9aaf79ca3506154831a6c51abe521f'
PATCH_SHA = 'ec6348c6c9428e899b670d293ae65783264cf9fcc024dbd81a15c2f321e01150'
APPEND = 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
EXPECTED = {
    'payload.raw': 'f125011a069ddab81030bd31129883d1fd97a44f2a874d7e8d96e9d1ca6003af',
    'f1-guest-probe': '2052c5d30ac4a6fbbf056a6e6e844d0a733c06a50e43c69b3b98156bfdfbd673',
    'kernel.elf': '956438a6f2cad39a2d73093004909e34cf66e9b7d4bdccda67287cf62bb2d14d',
    'bios.bin': '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735',
}
HARNESS_PINS = {
    'run_f1_guest.py': 'c880f66d6b5032dd859ed9bb99d4c90b1c320f9ca5a58f72d10da7b039dfb718',
    'f1_guest_probe.c': 'd5f4f27659ecf80b640618459fcd1a37aca6bf700c4ad6e23101d52bc98b7a37',
    'frozen_support.py': 'ea62b61b283340e61fd2d11fdce873ddefe007846bdeb6f1298c5a2d74726d1d',
    'cpio_codec.py': 'fc037a65aaf25fb3425befe8c74220e6ed76ea1767c368ba5d351e90a81f47e2',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda: source.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def save(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')


def regular_file(path, limit):
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            'expected absolute regular file: ' + str(path))
    require(0 < path.stat().st_size <= limit, 'file size outside bound: ' + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'f1-local-udp-lifecycle-v1')
    args = parser.parse_args()
    out = args.output
    require(out.is_absolute() and out.parent.resolve() == ROOT.resolve() and not out.exists()
            and not out.is_symlink() and all(c not in str(out) for c in (',', '\n', '\r')),
            'output must be a fresh direct child of the project root')
    regular_file(args.build_receipt, 2 * 1024 * 1024)
    build = json.loads(args.build_receipt.read_text())
    require(build.get('base_head') == BASE_HEAD
            and build.get('source_patch_sha256') == PATCH_SHA,
            'kernel build is not the approved ordinary base plus the reviewed UDP patch')
    require(type(build.get('build_returncode')) is int and build['build_returncode'] == 0
            and build.get('build_timed_out') is False, 'kernel build did not complete successfully')
    require(build.get('source_head') == FIXED_HEAD and build.get('source_tree') == FIXED_TREE,
            'fixed source must be the reviewed ordinary UDP commit and tree')
    kernel = Path(build['kernel_path'])
    actual_build_result = Path(build['actual_build_result_path'])
    regular_file(actual_build_result, 8 * 1024 * 1024)
    regular_file(kernel, 64 * 1024 * 1024)
    kernel_hash = sha(kernel)
    require(kernel_hash == build.get('kernel_sha256') and kernel_hash != EXPECTED['kernel.elf'],
            'fixed kernel SHA differs or is still the old ordinary image')
    kernel_bytes = kernel.read_bytes()
    require(kernel_bytes.startswith(b'\x7fELF') and b'HEPTA_KTRACE_V1' not in kernel_bytes,
            'the ordinary fixed kernel must be an ELF without stop tracing')
    previous = json.loads((REFERENCE / 'result.json').read_text())
    invocation = json.loads((REFERENCE / 'invocation.json').read_text())
    require(previous.get('qemu_exit') == 33 and previous.get('timed_out') is False
            and previous.get('inputs_unchanged') is True, 'ordinary guest receipt differs')
    require(invocation['child_argv'] == ['/payload/bin/native_lifecycle', '/payload/bin/codex-hepta-agentd', '/data/f1']
            and invocation['child_environment'] == {'PATH': '/bin:/usr/bin', 'LANG': 'C', 'LC_ALL': 'C'},
            'original helper invocation differs')
    require(all(sha(REFERENCE / name) == digest for name, digest in EXPECTED.items()),
            'original immutable guest input changed')
    input_pins = previous['input_identities']
    require(input_pins['agentd']['sha256'] == 'fcef743f93a126364a9dbc0ee1c18ca6c0542f9ea4cb674c7d95ef870b66e84f'
            and input_pins['helper']['sha256'] == '92aaeeb437b4c497a047cfc248951df402fcf9ac80a17885a75c9b69b8483ac6',
            'original Agentd/helper identity differs')
    original_image = Path(input_pins['original_initramfs']['path'])
    require(sha(original_image) == '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3',
            'original initramfs changed')
    require(all(sha(HARNESS / name) == digest for name, digest in HARNESS_PINS.items()),
            'original reviewed harness changed')
    sys.path.insert(0, str(HARNESS))
    spec = importlib.util.spec_from_file_location('f1_reference_runner', HARNESS / 'run_f1_guest.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    argv = list(invocation['argv'])
    require(all(argv.count(flag) == 1 for flag in ('-initrd', '-append', '-kernel', '-bios'))
            and argv.count('-drive') == 2, 'original QEMU invocation differs')
    require(argv[argv.index('-append') + 1] == APPEND, 'original warn-mode boot arguments differ')
    require(sha(Path(argv[0])) == '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854',
            'QEMU changed')
    mkfs = Path(previous['tool_identities']['mkfs']['path'])
    require(sha(mkfs) == '07cd24ce58a410cc9cee93c55ae5ac95986df016c5907dc7a49b55389bd41ed2', 'mkfs changed')
    for flag, name in (('-kernel', 'kernel.elf'), ('-bios', 'bios.bin')):
        require(sha(Path(argv[argv.index(flag) + 1])) == EXPECTED[name], 'original boot artifact changed')
    old_data = 'if=none,format=raw,id=f1data,file=' + str(REFERENCE / 'data.raw')
    require(argv.count(old_data) == 1, 'original writable data drive differs')
    require(argv.count('if=none,format=raw,id=f1payload,readonly=on,file=' + str(REFERENCE / 'payload.raw')) == 1,
            'original payload is not read-only')
    out.mkdir(mode=0o700)
    frozen_kernel = out / 'kernel.elf'
    frozen_kernel.write_bytes(kernel_bytes)
    shutil.copyfile(args.build_receipt, out / 'kernel-build-receipt.json')
    shutil.copyfile(actual_build_result, out / 'actual-kernel-build-result.json')
    nonce = os.urandom(32).hex()
    image = out / 'initramfs.cpio.gz'
    image.write_bytes(runner.build_initramfs(original_image.read_bytes(),
                                           (REFERENCE / 'f1-guest-probe').read_bytes(), nonce))
    data = out / 'data.raw'
    with data.open('xb') as output:
        output.truncate(256 * 1024 * 1024)
    formatter = [str(mkfs), '-F', '-q', '-b', '4096', '-I', '256', '-m', '0', '-O', 'none,filetype', str(data)]
    save(out / 'format-invocation.json', {'argv': formatter, 'timeout_seconds': 60})
    with (out / 'format.log').open('xb') as log:
        formatted = subprocess.run(formatter, env=ENV, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=60, check=False)
    save(out / 'format-result.json', {'exit_code': formatted.returncode})
    require(formatted.returncode == 0, 'fresh data formatting failed')
    data_before = sha(data)
    argv[argv.index('-kernel') + 1] = str(frozen_kernel)
    argv[argv.index('-initrd') + 1] = str(image)
    argv[argv.index(old_data)] = 'if=none,format=raw,id=f1data,file=' + str(data)
    receipt = {
        'schema': 'hepta.f1-local-udp-kernel.v1', 'diagnostic_only': True,
        'original_agentd_lifecycle_qualified': False, 'original_deadlines_unchanged': True,
        'previous_agentd_build_exit_receipt_recovered': False, 'started_ns': time.time_ns(),
        'source_patch_sha256_before_pinned_rustfmt': PATCH_SHA,
        'ordinary_source_head': BASE_HEAD,
        'kernel_build': build, 'kernel_build_receipt_sha256': sha(args.build_receipt),
        'actual_kernel_build_result_sha256': sha(actual_build_result),
        'fixed_kernel_sha256': kernel_hash, 'original_guest_receipt_sha256': sha(REFERENCE / 'result.json'),
        'original_guest_invocation_sha256': sha(REFERENCE / 'invocation.json'),
        'unchanged_input_pins': EXPECTED, 'original_agentd_helper': input_pins,
        'argv': argv, 'nonce': nonce, 'child_argv': invocation['child_argv'],
        'child_environment': invocation['child_environment'], 'append': APPEND,
        'initramfs_sha256': sha(image), 'data_before_sha256': data_before,
        'timeout_seconds': 600, 'serial_limit_bytes': runner.SERIAL_LIMIT,
        'observer_unchanged': True, 'kernel_stop_tracing': False,
        'guest_resolver_configuration_unchanged': True,
    }
    save(out / 'invocation.json', receipt)
    raw, code, timed_out, excessive = runner.run_qemu(argv, out, 600, receipt)
    observed, streams = runner.observe(raw, nonce)
    for name, content in streams.items():
        (out / ('guest-' + name.lower() + '.bin')).write_bytes(content)
    unchanged = (all(sha(REFERENCE / name) == digest for name, digest in EXPECTED.items())
                 and all(sha(HARNESS / name) == digest for name, digest in HARNESS_PINS.items())
                 and sha(frozen_kernel) == kernel_hash
                 and sha(out / 'kernel-build-receipt.json') == receipt['kernel_build_receipt_sha256']
                 and sha(out / 'actual-kernel-build-result.json') == receipt['actual_kernel_build_result_sha256'])
    capture_succeeded = (code == 33 and not timed_out and not excessive and unchanged
                         and 'STDOUT' in streams and 'STDERR' in streams
                         and b'HEPTA_KTRACE_V1' not in raw)
    passed = capture_succeeded and runner.oracle(raw, code, timed_out, excessive, nonce)
    receipt.update(
        finished_ns=time.time_ns(), qemu_exit=code, timed_out=timed_out, serial_excessive=excessive,
        serial_bytes=len(raw), serial_sha256=hashlib.sha256(raw).hexdigest(), data_after_sha256=sha(data),
        observed=observed, inputs_unchanged=unchanged,
        diagnostic_capture_succeeded=capture_succeeded,
        diagnostic_lifecycle_passed=passed, original_agentd_lifecycle_qualified=False)
    save(out / 'result.json', receipt)
    print(json.dumps({key: receipt[key] for key in (
        'qemu_exit', 'timed_out', 'serial_bytes', 'diagnostic_capture_succeeded',
        'diagnostic_lifecycle_passed', 'original_agentd_lifecycle_qualified')}
        | {'output': str(out), 'stage_names': observed['stage_names']}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
