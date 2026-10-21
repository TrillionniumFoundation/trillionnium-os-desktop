#!/usr/bin/env python3
"""Qualify ExFAT modes using one frozen ELF and fresh, isolated disk copies.

The Linux reference owns one loop attachment to its newly created image copy.
The guest receives exactly one disposable virtio disk, no NIC or host sharing.
Every Rust/C build and device execution belongs to the project cloud workflow.
"""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


shared = module('exfat_shared', Path(__file__).with_name('run_rlimit_nofile_guest.py'))
oracle = module('exfat_oracle', Path(__file__).with_name('exfat_mode_evidence.py'))
product = module('exfat_product', ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py')
common, require, sha = shared.common, shared.common.require, shared.common.sha
IMAGE_BYTES = 512 * 1024 * 1024
LOG_LIMIT = 8 * 1024 * 1024
SOURCE_PATHS = tuple(str(path.relative_to(ROOT)) for path in (
    Path(__file__).resolve(), Path(__file__).with_name('exfat_mode_evidence.py'),
    Path(__file__).with_name('exfat_mode_probe.c'),
    Path(__file__).with_name('run_rlimit_nofile_guest.py'), shared.COMMON_PATH,
    shared.GROUP_PATH, ROOT / 'tests/organ_backend/run_guest_probe.py',
    ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py',
))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def source_inputs():
    return {name: {'sha256': sha(common.read_file(ROOT / name, LOG_LIMIT)),
                   'bytes': (ROOT / name).stat().st_size} for name in SOURCE_PATHS}


def disk_hash(path):
    """Hash a retained regular-file descriptor, rejecting links and size changes."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_size == IMAGE_BYTES, 'disk is not our fixed-size regular image')
        digest = hashlib.sha256()
        while data := os.read(fd, 2 * 1024 * 1024):
            digest.update(data)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'image changed while hashing')
        named = os.stat(path, follow_symlinks=False)
        require((named.st_dev, named.st_ino) == (after.st_dev, after.st_ino), 'image pathname changed')
        return digest.hexdigest()
    finally:
        os.close(fd)


def copy_image(source, destination, expected):
    require(disk_hash(source) == expected, 'frozen blank image changed')
    # Exclusive destination creation prevents accepting any existing device/file.
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst, 2 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    require(disk_hash(destination) == expected and disk_hash(source) == expected,
            'disposable image copy differs from the frozen input')


def tool_identity(name):
    path = shutil.which(name)
    require(path is not None, 'required tool unavailable: ' + name)
    return {'path': path, 'sha256': sha(Path(path).read_bytes())}


def run_logged(command, out, name, *, timeout=60, cwd=None, env=None):
    save(out / (name + '-command.json'), command)
    with (out / (name + '.stdout.log')).open('xb') as stdout, (out / (name + '.stderr.log')).open('xb') as stderr:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                timeout=timeout, check=False, cwd=cwd, env=env)
    (out / (name + '.exit-code.txt')).write_text(str(result.returncode) + '\n')
    require(result.returncode == 0, name + ' failed; original stdout/stderr retained')


def prepare(args, out, report):
    # Keep the actual rejected paths if the preceding build stages dirtied the
    # checkout. The original source_snapshot gate must still reject them.
    run_logged(['git', 'status', '--porcelain', '--untracked-files=all'],
               out, 'git-status-before-prepare', cwd=ROOT)
    before = product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'source-before.json', before)
    compiler, formatter = tool_identity(args.cc), tool_identity('mkfs.exfat')
    run_logged([compiler['path'], '--version'], out, 'compiler-version')
    run_logged([formatter['path'], '-V'], out, 'formatter-version')
    run_logged([compiler['path'], '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-static',
                str(ROOT / 'tests/workloads/linux/exfat_mode_probe.c'), '-o', str(out / 'probe.elf')],
               out, 'compile')
    probe = common.read_file(out / 'probe.elf', 16 * 1024 * 1024)
    shared.require_static_probe(out / 'probe.elf', probe)
    run_logged(['readelf', '-h', '-l', str(out / 'probe.elf')], out, 'probe-elf')
    blank = out / 'blank.raw'
    with blank.open('xb') as image:
        # Same fixed 512 MiB geometry as the original initramfs Makefile target.
        image.truncate(IMAGE_BYTES)
        image.flush()
        os.fsync(image.fileno())
    before_format = blank.stat()
    run_logged([formatter['path'], str(blank)], out, 'format')
    require((blank.stat().st_dev, blank.stat().st_ino) == (before_format.st_dev, before_format.st_ino),
            'formatter replaced the owned image')
    require(source_inputs() == report['source_inputs'], 'compile changed the reviewed source inputs')
    after = product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'source-after.json', after)
    require(before == after, 'prepare changed source tree')
    require(tool_identity(args.cc) == compiler and tool_identity('mkfs.exfat') == formatter,
            'compiler or formatter changed during preparation')
    report.update(passed=True, source_head=args.expected_source_head, source_tree=args.expected_source_tree,
                  source_inputs_unchanged=True, probe_sha256=sha(probe), probe_bytes=len(probe),
                  image_sha256=disk_hash(blank), image_bytes=IMAGE_BYTES,
                  compiler=compiler, formatter=formatter,
                  compiler_version_sha256=sha(common.read_file(out / 'compiler-version.stdout.log')),
                  formatter_version_sha256=sha(common.read_file(out / 'formatter-version.stdout.log')))
    save(out / 'inputs.json', report)
    (out / 'inputs.sha256').write_text(sha((out / 'inputs.json').read_bytes()) + '  inputs.json\n')


def bundle_input(directory, expected):
    raw = common.read_pinned(directory / 'inputs.json', expected, LOG_LIMIT)
    record = json.loads(raw)
    require(record['schema'] == 'a06.exfat-prepare.v1' and record['passed'] is True
            and record['source_inputs_unchanged'] is True, 'unqualified frozen bundle')
    require(record['source_inputs'] == source_inputs(), 'source inputs differ from frozen bundle')
    require(record['image_bytes'] == IMAGE_BYTES and disk_hash(directory / 'blank.raw') == record['image_sha256'],
            'blank image identity differs')
    probe = common.read_pinned(directory / 'probe.elf', record['probe_sha256'], 16 * 1024 * 1024)
    require(len(probe) == record['probe_bytes'], 'probe length differs')
    require(common.read_file(directory / 'inputs.sha256', 128) == (expected + '  inputs.json\n').encode(),
            'original frozen digest changed')
    return record, probe


def loop_binding(fd, image_stat):
    """LOOP_GET_STATUS64 binds the held block descriptor to our fresh image inode."""
    value = bytearray(232)
    fcntl.ioctl(fd, 0x4C05, value, True)
    device, inode, _rdevice, offset, limit, number, crypt, key_bytes, flags = struct.unpack_from('=QQQQQIIII', value)
    require((device, inode) == (image_stat.st_dev, image_stat.st_ino)
            and offset == limit == crypt == key_bytes == flags == 0,
            'loop descriptor is not exclusively attached to the owned unencrypted whole image')
    return {'backing_device': device, 'backing_inode': inode, 'offset': offset,
            'size_limit': limit, 'number': number, 'flags': flags}


def reference(args, out, report):
    require(os.geteuid() == 0, 'Linux reference requires the disposable project CI root context')
    bundle, probe = bundle_input(args.bundle, args.expected_input_sha256)
    image = out / 'disk.raw'
    copy_image(args.bundle / 'blank.raw', image, bundle['image_sha256'])
    image_stat = image.stat()
    unshare, losetup = tool_identity('unshare'), tool_identity('losetup')
    command = [losetup['path'], '--find', '--show', '--nooverlap', str(image)]
    run_logged(command, out, 'loop-attach')
    device = common.read_file(out / 'loop-attach.stdout.log', 1024).decode().strip()
    require(re.fullmatch('/dev/loop[0-9]+', device) is not None, 'unexpected loop-device response')
    fd = os.open(device, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        require(stat.S_ISBLK(os.fstat(fd).st_mode), 'loop result is not a block descriptor')
        binding = loop_binding(fd, image_stat)
        command = [unshare['path'], '--mount', '--propagation', 'private', '--',
                   str(args.bundle / 'probe.elf'), '--device', device, '--mountpoint', str(out / 'mount')]
        report.update(bundle_sha256=args.expected_input_sha256, probe_sha256=sha(probe),
                      image_before_sha256=bundle['image_sha256'], image_bytes=IMAGE_BYTES,
                      private_mount_namespace=True, command=command, loop_binding=binding,
                      host_kernel=os.uname().release, host_arch=os.uname().machine,
                      unshare=unshare, losetup=losetup)
        save(out / 'input.json', report)
        report['frozen_input_sha256'] = sha((out / 'input.json').read_bytes())
        started = time.monotonic()
        code, timed_out = shared.reference_process(command, out, timeout_seconds=args.timeout)
        report.update(process_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - started,
                      process_group_cleanup_completed=True)
        (out / 'exit-code.txt').write_text(str(code) + '\n')
        stdout, stderr = common.read_file(out / 'stdout.log', LOG_LIMIT), common.read_file(out / 'stderr.log', LOG_LIMIT)
        report.update(stdout_sha256=sha(stdout), stderr_sha256=sha(stderr),
                      verdict=oracle.evaluate(stdout, guest=False, negative=False, process_exit=code,
                                              timed_out=timed_out, probe_bytes=len(probe), stderr=stderr))
        require(loop_binding(fd, image_stat) == binding, 'owned loop binding changed during reference')
        report['passed'] = report['verdict']['passed']
    finally:
        # Only clear this held descriptor while it still names our exact image inode.
        # Keeping it open until CLR_FD prevents accidental reuse during cleanup.
        try:
            loop_binding(fd, image_stat)
            fcntl.ioctl(fd, 0x4C01)
            report['owned_loop_detach_requested'] = True
        finally:
            os.close(fd)
    report['image_after_sha256'] = disk_hash(image)
    require(bundle_input(args.bundle, args.expected_input_sha256) == (bundle, probe), 'frozen bundle changed')
    require(tool_identity('unshare') == unshare and tool_identity('losetup') == losetup, 'reference executable changed')
    report['inputs_unchanged'] = True


def reference_input(directory, bundle, expected):
    raw = common.read_file(directory / 'result.json', LOG_LIMIT)
    record = json.loads(raw)
    require(record['schema'] == 'a06.exfat-reference.v1' and record['passed'] is True
            and all(record[key] is True for key in ('private_mount_namespace', 'process_group_cleanup_completed',
                                                    'owned_loop_detach_requested', 'inputs_unchanged')),
            'Linux reference did not finish its owned execution/cleanup')
    require(record['bundle_sha256'] == expected and record['probe_sha256'] == bundle['probe_sha256']
            and record['source_inputs'] == source_inputs(), 'reference was not executed from this frozen bundle')
    before = json.loads(common.read_pinned(directory / 'input.json', record['frozen_input_sha256'], LOG_LIMIT))
    require(before['bundle_sha256'] == expected and before['command'] == record['command']
            and before['loop_binding'] == record['loop_binding'], 'pre-execution reference changed')
    stdout = common.read_pinned(directory / 'stdout.log', record['stdout_sha256'], LOG_LIMIT)
    stderr = common.read_pinned(directory / 'stderr.log', record['stderr_sha256'], LOG_LIMIT)
    require(common.read_file(directory / 'exit-code.txt', 64) == (str(record['process_exit']) + '\n').encode(),
            'recorded reference exit differs')
    check = oracle.evaluate(stdout, guest=False, negative=False, process_exit=record['process_exit'],
                            timed_out=record['timed_out'], probe_bytes=bundle['probe_bytes'], stderr=stderr)
    require(check['passed'] and check == record['verdict'], 'reference raw observations failed independent validation')
    require(disk_hash(directory / 'disk.raw') == record['image_after_sha256'], 'reference output image changed')
    return sha(raw)


def build_initramfs(original, probe):
    entries = common.unpack(gzip.decompress(original))
    require(common.unpack(common.pack(entries)) == entries, 'original initramfs roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if ! /bin/busybox grep -q '^[^ ]* /dev devtmpfs ' /proc/mounts; then
    /bin/busybox mount -t devtmpfs devtmpfs /dev
fi
if /bin/exfat-mode-probe --device /dev/vda --mountpoint /exfat-observation; then
    exfat_probe_exit=0
else
    exfat_probe_exit=$?
fi
echo "EXFAT_PROCESS_EXIT=$exfat_probe_exit"
'''
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') not in (oracle.PROBE_PATH, 'exfat-observation'), 'disk probe already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'ambiguous original init')
            content = content.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(content)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init is absent or ambiguous')
    ino = max(entry[1][0] for entry in entries) + 1
    changed.append((oracle.PROBE_PATH,
                    [ino, 0o100755, 0, 0, 1, 0, len(probe), 0, 0, 0, 0, len(oracle.PROBE_PATH) + 1, 0], probe))
    require(common.unpack(common.pack(changed)) == changed, 'injected initramfs roundtrip differs')
    return gzip.compress(common.pack(changed), mtime=0)


def guest(args, out, report):
    before = product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'source-before.json', before)
    bundle, probe = bundle_input(args.bundle, args.expected_input_sha256)
    reference_sha = reference_input(args.linux_reference, bundle, args.expected_input_sha256)
    kernel, receipt_sha = common.product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
    built_source = json.loads(common.read_file(args.product_evidence / 'source-before.json', LOG_LIMIT))
    require(built_source['files'] == before['files'], 'guest runner/source differs from the ordinary product snapshot')
    # Ordinary production is admitted only at the original bundle source identity.
    require((bundle['source_head'], bundle['source_tree']) == (args.expected_source_head, args.expected_source_tree),
            'guest product differs from the frozen reviewed source')
    report.update(source_head=args.expected_source_head, source_tree=args.expected_source_tree)
    run_disk_guest(args, out, report, bundle, probe, kernel, receipt_sha, reference_sha, negative=False)
    after = product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'source-after.json', after)
    require(before == after, 'guest execution changed the source checkout')
    require(common.product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
            == (kernel, receipt_sha), 'ordinary product evidence changed during guest')
    report['source_inputs_unchanged'] = True


def run_disk_guest(args, out, report, bundle, probe, kernel, receipt_sha, reference_sha, *, negative):
    original = common.read_pinned(args.a01_initramfs, common.INITRD_SHA, LOG_LIMIT)
    bios = common.read_pinned(args.bios, common.BIOS_SHA, 2 * 1024 * 1024)
    initrd = build_initramfs(original, probe)
    inputs = (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd))
    for name, data in inputs:
        (out / name).write_bytes(data)
    image = out / 'disk.raw'
    copy_image(args.bundle / 'blank.raw', image, bundle['image_sha256'])
    qemu = tool_identity(args.qemu)
    version = subprocess.check_output([qemu['path'], '--version'], timeout=10).decode()
    require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
    # One fixed modern virtio block device, matching the original Q35 ExFAT profile.
    drive = 'if=none,format=raw,id=exfat,file=' + str(image)
    require(',' not in str(image), 'image path cannot alter QEMU drive options')
    block = ('virtio-blk-pci,bus=pcie.0,addr=0x7,drive=exfat,serial=vexfat,'
             'disable-legacy=on,disable-modern=off,queue-size=64,num-queues=1,'
             'request-merging=off,backend_defaults=off,discard=off,write-zeroes=off,'
             'event_idx=off,indirect_desc=off,queue_reset=off')
    command = [qemu['path'], '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
               '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
               '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
               '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
               '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
               '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04', '-drive', drive, '-device', block]
    report.update(bundle_sha256=args.expected_input_sha256, product_receipt_sha256=receipt_sha,
                  linux_reference_receipt_sha256=reference_sha, kernel_sha256=sha(kernel),
                  probe_sha256=sha(probe), bios_sha256=sha(bios), initramfs_sha256=sha(initrd),
                  original_initramfs_sha256=sha(original), image_before_sha256=bundle['image_sha256'],
                  qemu=qemu, qemu_version=version, command=command, negative_control=negative)
    save(out / 'input.json', report)
    report['frozen_input_sha256'] = sha((out / 'input.json').read_bytes())
    started, code, timed_out = time.monotonic(), None, False
    with (out / 'serial.log').open('xb') as log:
        try:
            code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    raw = common.read_file(out / 'serial.log', 64 * 1024 * 1024)
    report.update(qemu_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - started,
                  serial_sha256=sha(raw), serial_bytes=len(raw), image_after_sha256=disk_hash(image))
    (out / 'exit-code.txt').write_text(str(code) + '\n')
    report['verdict'] = oracle.evaluate(raw, guest=True, negative=negative, process_exit=code,
                                        timed_out=timed_out, probe_bytes=len(probe))
    for name, data in inputs:
        require(common.read_file(out / name) == data, 'guest input changed: ' + name)
    require(bundle_input(args.bundle, args.expected_input_sha256) == (bundle, probe), 'bundle changed during guest')
    require(reference_input(args.linux_reference, bundle, args.expected_input_sha256) == reference_sha,
            'Linux reference changed during guest')
    require(tool_identity(args.qemu) == qemu, 'QEMU executable changed during guest')
    report.update(passed=report['verdict']['passed'], inputs_unchanged=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--cc', default='cc')
    linux = commands.add_parser('reference')
    target = commands.add_parser('guest')
    for command in (build, target):
        command.add_argument('--expected-source-head', required=True)
        command.add_argument('--expected-source-tree', required=True)
    for command in (linux, target):
        command.add_argument('--bundle', type=Path, required=True)
        command.add_argument('--expected-input-sha256', required=True)
        command.add_argument('--timeout', type=int, default=120)
    target.add_argument('--product-evidence', type=Path, required=True)
    target.add_argument('--linux-reference', type=Path, required=True)
    target.add_argument('--a01-initramfs', type=Path, required=True)
    target.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    target.add_argument('--qemu', default='qemu-system-x86_64')
    for command in (build, linux, target):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink() and not out.is_relative_to(ROOT), 'output must be new and outside source')
    require(not hasattr(args, 'timeout') or 1 <= args.timeout <= 180, 'timeout must be 1..180 seconds')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema': 'a06.exfat-' + args.mode + '.v1', 'passed': False, 'source_inputs': source_inputs(),
              'hepta_hos2_qualification': False, 'physical_device_qualification': False}
    try:
        {'prepare': prepare, 'reference': reference, 'guest': guest}[args.mode](args, out, report)
        require(source_inputs() == report['source_inputs'], 'source input changed')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, shared.groups.GateError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    save(out / 'result.json', report)
    print(json.dumps({key: report[key] for key in ('passed', 'error', 'verdict') if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
