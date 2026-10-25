#!/usr/bin/env python3
"""Run the already verified UDP regression ELF on the ordinary fixed kernel."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/qian-qi/work/trillionnium-os-20261021-b2da20752f15')
SOURCE_GATES = ROOT / 'f1-udp-error-source-gates-v1'
HARNESS = ROOT / 'f1-guest-harness-afunix-kernel-v1'
REFERENCE = ROOT / 'f1-closure-stop-diagnostic-20261023-v1/guest'
BASE_HEAD = 'b824d80d44456c131a6cb9d4fcc84be95c6af273'
FIXED_HEAD = 'c8f0c88ecb640117686ff05f850a73e60688eac7'
FIXED_TREE = '641c6627ba9aaf79ca3506154831a6c51abe521f'
PATCH_SHA = 'ec6348c6c9428e899b670d293ae65783264cf9fcc024dbd81a15c2f321e01150'
EXECUTABLE_SHA = '90ace4da1f2a34200dc0952ea4419d7ad67c201a53994273b9f4a93d3f2ccc40'
LINUX_STDERR_SHA = '67178f9fdbe1e761bc9daad11b88f183658fc8ef7693c77db471464a627ac085'
APPEND = 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --'
EXPECTED_CASES = [
    ('connected_error_is_read_once_and_delivery_recovers', 11),
    ('receive_consumes_error', 7),
    ('send_consumes_error', 8),
    ('unconnected_socket_ignores_port_unreachable_without_recverr', 4),
    ('connected_socket_ignores_errors_for_another_destination', 8),
    ('self_delivery_has_no_error', 5),
]


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
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and 0 < path.stat().st_size <= limit, 'expected bounded regular file: ' + str(path))


def observe(data):
    plain = re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', data).replace(b'\r\n', b'\n')
    summaries = re.findall(rb'(?m)^test_([^:\n]+) summary: (\d+) tests passed, (\d+) tests failed$', plain)
    cases = [{'name': name.decode('ascii'), 'passed': int(passed), 'failed': int(failed)}
             for name, passed, failed in summaries]
    checks = re.findall(rb'(?m)^test_[^\n]+: [^\n]+ (?:passed|failed) \[got [^\n]+\]$', plain)
    complete = (len(cases) == len(EXPECTED_CASES) and len(checks) == 43
                and [(row['name'], row['passed'] + row['failed']) for row in cases] == EXPECTED_CASES
                and b'fatal error:' not in plain)
    return {'complete': complete, 'passed': complete and all(row['failed'] == 0 for row in cases),
            'check_count': len(checks), 'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'f1-local-udp-native-regression-v1')
    args = parser.parse_args()
    out = args.output
    require(out.is_absolute() and out.parent.resolve() == ROOT.resolve() and not out.exists()
            and not out.is_symlink() and all(c not in str(out) for c in (',', '\n', '\r')),
            'output must be a fresh direct child of the project root')
    regular_file(args.build_receipt, 2 * 1024 * 1024)
    build = json.loads(args.build_receipt.read_text())
    require(build.get('base_head') == BASE_HEAD and build.get('source_patch_sha256') == PATCH_SHA
            and build.get('source_head') == FIXED_HEAD and build.get('source_tree') == FIXED_TREE,
            'kernel build differs from the reviewed ordinary UDP source')
    require(type(build.get('build_returncode')) is int and build['build_returncode'] == 0
            and build.get('build_timed_out') is False, 'kernel build did not complete successfully')
    kernel = Path(build['kernel_path'])
    actual_build_result = Path(build['actual_build_result_path'])
    regular_file(kernel, 64 * 1024 * 1024)
    regular_file(actual_build_result, 8 * 1024 * 1024)
    kernel_hash = sha(kernel)
    kernel_bytes = kernel.read_bytes()
    require(kernel_hash == build['kernel_sha256']
            and kernel_hash != '956438a6f2cad39a2d73093004909e34cf66e9b7d4bdccda67287cf62bb2d14d'
            and kernel_bytes.startswith(b'\x7fELF') and b'HEPTA_KTRACE_V1' not in kernel_bytes,
            'fixed kernel must differ from the old ordinary image and contain no stop tracing')
    executable = SOURCE_GATES / 'udp-local-error'
    regular_file(executable, 8 * 1024 * 1024)
    require(sha(executable) == EXECUTABLE_SHA, 'the already verified Linux executable changed')
    require(sha(SOURCE_GATES / 'linux.stderr') == LINUX_STDERR_SHA
            and (SOURCE_GATES / 'linux.stdout').read_bytes() == b'', 'Linux control streams changed')
    host = json.loads((SOURCE_GATES / 'linux-result.json').read_text())
    compiled = json.loads((SOURCE_GATES / 'build-result.json').read_text())
    for name, receipt in (('Linux', host), ('compiler', compiled)):
        require(type(receipt.get('returncode')) is int and receipt['returncode'] == 0
                and receipt.get('timed_out') is False
                and receipt.get('source_head') == FIXED_HEAD and receipt.get('source_tree') == FIXED_TREE,
                name + ' receipt does not bind a successful result to the fixed source')
    host_observation = observe((SOURCE_GATES / 'linux.stderr').read_bytes())
    require(host_observation['passed'], 'Linux control must contain all 6 cases and 43 successful checks')
    previous = json.loads((REFERENCE / 'result.json').read_text())
    original_image = Path(previous['input_identities']['original_initramfs']['path'])
    require(sha(original_image) == '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3',
            'original initramfs changed')
    pins = {'run_f1_guest.py': 'c880f66d6b5032dd859ed9bb99d4c90b1c320f9ca5a58f72d10da7b039dfb718',
            'cpio_codec.py': 'fc037a65aaf25fb3425befe8c74220e6ed76ea1767c368ba5d351e90a81f47e2',
            'frozen_support.py': 'ea62b61b283340e61fd2d11fdce873ddefe007846bdeb6f1298c5a2d74726d1d'}
    require(all(sha(HARNESS / name) == digest for name, digest in pins.items()), 'reviewed harness changed')
    sys.path.insert(0, str(HARNESS))
    spec = importlib.util.spec_from_file_location('f1_reference_runner', HARNESS / 'run_f1_guest.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    readelf = previous['tool_identities']['readelf']
    require(sha(Path(readelf['path'])) == readelf['sha256'], 'readelf changed')
    elf = runner.support.elf_info(executable, readelf['path'])
    require(elf['type'] == 2 and elf['interpreter'] is None and elf['needed'] == [], 'regression must be static ELF')
    entries = runner.cpio_codec.unpack(gzip.decompress(original_image.read_bytes()))
    require(all(name.lstrip('./') != 'bin/udp-local-error' for name, _, _ in entries), 'regression path collision')
    nonce = os.urandom(32).hex()
    script = ('if /bin/udp-local-error; then udp_regression_code=0; else udp_regression_code=$?; fi\n'
              f'echo "HEPTA_UDP_REGRESSION_HARNESS nonce={nonce} exit=$udp_regression_code"\n').encode()
    changed, count = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(runner.BOOT) == 1 and b'set -eu' in data, 'unexpected original init')
            data = data.replace(runner.BOOT, script + runner.BOOT)
            count += 1
        changed.append((name, fields, data))
    require(count == 1, 'original init missing')
    fields = [max(row[1][0] for row in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    changed.append(('bin/udp-local-error', fields, executable.read_bytes()))
    prior = json.loads((REFERENCE / 'invocation.json').read_text())['argv']
    require(prior.count('-drive') == 2 and prior[prior.index('-append') + 1] == APPEND,
            'original ordinary QEMU configuration changed')
    require(sha(Path(prior[0])) == '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854',
            'QEMU changed')
    require(sha(Path(prior[prior.index('-bios') + 1])) ==
            '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735', 'BIOS changed')
    out.mkdir(mode=0o700)
    frozen_kernel = out / 'kernel.elf'
    frozen_kernel.write_bytes(kernel_bytes)
    shutil.copyfile(executable, out / 'udp-local-error')
    shutil.copyfile(args.build_receipt, out / 'kernel-build-receipt.json')
    shutil.copyfile(actual_build_result, out / 'actual-kernel-build-result.json')
    for name in ('linux-result.json', 'build-result.json', 'linux.stderr', 'linux.stdout'):
        shutil.copyfile(SOURCE_GATES / name, out / ('host-' + name))
    image = out / 'initramfs.cpio.gz'
    image.write_bytes(gzip.compress(runner.cpio_codec.pack(changed), mtime=0))
    argv, index = [], 0
    while index < len(prior):
        arg = prior[index]
        if arg == '-drive' or (arg == '-device' and prior[index + 1].startswith('virtio-blk-pci')):
            index += 2
            continue
        if arg in ('-initrd', '-kernel'):
            argv.extend((arg, str(image if arg == '-initrd' else frozen_kernel)))
            index += 2
            continue
        argv.append(arg)
        index += 1
    receipt = {'schema': 'hepta.f1-local-udp-native-regression.v1', 'diagnostic_only': True,
               'original_agentd_lifecycle_qualified': False, 'kernel_stop_tracing': False,
               'kernel_build': build, 'kernel_build_receipt_sha256': sha(args.build_receipt),
               'actual_kernel_build_result_sha256': sha(actual_build_result),
               'kernel_sha256': kernel_hash, 'source_patch_sha256_before_pinned_rustfmt': PATCH_SHA,
               'executable_sha256': EXECUTABLE_SHA, 'elf': elf, 'host_observation': host_observation,
               'host_linux_result_sha256': sha(SOURCE_GATES / 'linux-result.json'),
               'host_compile_result_sha256': sha(SOURCE_GATES / 'build-result.json'),
               'host_stderr_sha256': LINUX_STDERR_SHA, 'initramfs_sha256': sha(image),
               'argv': argv, 'timeout_seconds': 180, 'nonce': nonce, 'started_ns': time.time_ns()}
    save(out / 'invocation.json', receipt)
    raw, code, timed_out, excessive = runner.run_qemu(argv, out, 180, receipt)
    observed = observe(raw)
    markers = re.findall(rb'HEPTA_UDP_REGRESSION_HARNESS nonce=' + nonce.encode() + rb' exit=([0-9]+)', raw)
    harness_rc = int(markers[0]) if len(markers) == 1 else None
    unchanged = (sha(frozen_kernel) == kernel_hash and sha(executable) == EXECUTABLE_SHA
                 and sha(out / 'udp-local-error') == EXECUTABLE_SHA
                 and all(sha(HARNESS / name) == digest for name, digest in pins.items()))
    captured = (code == 33 and not timed_out and not excessive and observed['complete']
                and unchanged and harness_rc is not None and b'Kernel panic' not in raw
                and b'HEPTA_KTRACE_V1' not in raw)
    passed = captured and observed['passed'] and harness_rc == 0
    receipt.update(qemu_exit=code, timed_out=timed_out, serial_excessive=excessive,
                   observation=observed, harness_returncode=harness_rc, inputs_unchanged=unchanged,
                   diagnostic_capture_succeeded=captured, native_abi_passed=passed,
                   serial_sha256=hashlib.sha256(raw).hexdigest(), finished_ns=time.time_ns())
    save(out / 'result.json', receipt)
    print(json.dumps({'output': str(out), 'diagnostic_capture_succeeded': captured,
                      'native_abi_passed': passed, 'observation': observed}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
