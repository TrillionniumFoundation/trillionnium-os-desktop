#!/usr/bin/env python3
"""Qualify ExFAT mode/exec behavior on Linux and two ordinary product kernels.

All mount, loop and guest operations require the disposable cloud profile. The
same ELF and frozen image are used throughout. A complete old-mode credential
transition is required; a build failure or arbitrary failing guest is not RED.
"""
import argparse
import gzip
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
ROOT = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).with_name('exfat_exec_probe.c')
IMAGE_SIZE = 512 * 1024 * 1024
LOG_LIMIT = 64 * 1024 * 1024
PATCH_NAME = 'tests/organ_backend/exfat_synthesized_setid_negative.patch'
PATCH_SHA = '525e11369a5aefe9ae79358b83a293aa40e4b63de53b476b22cf220c55cd7024'
INODE = 'kernel/asterinas/kernel/core/src/fs/fs_impls/exfat/inode.rs'
BOOT = 'TRILLIONNIUM_A01_BOOT_OK'
PROCESS_EXIT = 'EXFAT_PROCESS_EXIT=0'
COMPLETE = 'EXFAT_COMPLETE metadata=3 executions=2'
IDS = 'ruid euid suid fsuid rgid egid sgid fsgid'.split()
CAPS = 'effective permitted inheritable bounding ambient'.split()
CREDS = ['phase', 'condition', *IDS, 'groups', *CAPS, 'nnp', 'securebits', 'keepcaps']
SOURCE_PATHS = (
    'tests/workloads/linux/run_exfat_exec_guest.py',
    'tests/workloads/linux/exfat_exec_probe.c',
    'tests/workloads/linux/run_rlimit_nofile_guest.py',
    'tests/workloads/linux/run_scm_rights_cloexec_guest.py',
    'tests/integration/hepta/run_original_agentd.py',
    'tests/organ_backend/run_guest_probe.py',
    'tests/organ_backend/run_cpu_owner_negative.py',
    'tests/kernel/control/run_queryabi_candidate_guest.py',
    'tests/kernel/control/run_queryabi_guest.py',
    'support/build/check-boot.py', PATCH_NAME,
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=LOG_LIMIT):
    require(path.is_file() and not path.is_symlink(), f'not a regular input: {path}')
    require(path.stat().st_size <= limit, f'input too large: {path}')
    return path.read_bytes()


def digest_file(path, size=None):
    require(path.is_file() and not path.is_symlink(), f'not a regular input: {path}')
    if size is not None:
        require(path.stat().st_size == size, f'input size differs: {path}')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    # Oracle tests deliberately import no execution helpers or repository state.
    shared = load_module('exfat_shared', ROOT / 'tests/workloads/linux/run_rlimit_nofile_guest.py')
    product = load_module('exfat_product', ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py')
    negative = load_module('exfat_negative', ROOT / 'tests/organ_backend/run_cpu_owner_negative.py')
    return shared, product, negative


def source_inputs():
    return {name: {'sha256': sha(raw), 'size': len(raw)}
            for name in SOURCE_PATHS for raw in [read(ROOT / name)]}


def record(line, prefix, keys, words=()):
    tokens = line.split(' ')
    if tokens[0] != prefix or len(tokens) != len(keys) + 1:
        return None
    pairs = [token.split('=', 1) for token in tokens[1:]]
    if any(len(pair) != 2 for pair in pairs) or [p[0] for p in pairs] != keys:
        return None
    for key, value in pairs:
        pattern = r'[a-z0-9]+' if key in words else r'-?[0-9]{1,20}'
        if re.fullmatch(pattern, value) is None:
            return None
    return {key: value if key in words else int(value) for key, value in pairs}


def evaluate(raw, code, timed_out, source_head, probe_size, *, guest, old=False):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace'))
    lines = text.splitlines()
    observed = [line for line in lines if line.startswith('EXFAT_')]
    failed = []
    expected_sequence = [
        'EXFAT_MOUNT', 'EXFAT_METADATA', 'EXFAT_METADATA', 'EXFAT_METADATA',
        'EXFAT_ELF_MATCH', 'EXFAT_CREDENTIALS', 'EXFAT_CREDENTIALS', 'EXFAT_CHILD',
        'EXFAT_CREDENTIALS', 'EXFAT_CREDENTIALS', 'EXFAT_CHILD',
        'EXFAT_COMPLETE', 'EXFAT_CLEANUP',
    ]
    if not guest:
        expected_sequence.insert(0, 'EXFAT_LOOP')
    else:
        expected_sequence.append('EXFAT_PROCESS_EXIT=0')
    if [line.split(' ', 1)[0] for line in observed] != expected_sequence:
        failed.append('exact_observation_sequence')
    rows = {}
    for prefix, keys, words in (
        ('EXFAT_MOUNT', ['type', 'flags'], ()),
        ('EXFAT_METADATA', ['object', 'uid', 'gid', 'mode', 'type', 'inode', 'device'], ('object',)),
        ('EXFAT_ELF_MATCH', ['source', 'bytes'], ('source',)),
        ('EXFAT_CREDENTIALS', CREDS, ('phase', 'condition')),
        ('EXFAT_CHILD', ['condition', 'exit', 'signal'], ('condition',)),
    ):
        rows[prefix] = [record(line, prefix, keys, words)
                        for line in observed if line.startswith(prefix)]
        if any(row is None for row in rows[prefix]):
            failed.append('malformed_' + prefix)
    mount = rows['EXFAT_MOUNT']
    # The reviewed Asterinas ExfatFs::sb currently exposes BOOT_SIGNATURE,
    # whereas Linux exposes EXFAT_SUPER_MAGIC. Record this existing ABI gap;
    # this permission/exec qualification must not silently claim ABI equality.
    expected_type = 0xAA55 if guest else 0x2011BAB0
    if (len(mount) != 1 or mount[0] is None or mount[0]['type'] != expected_type
            or mount[0]['flags'] < 0 or mount[0]['flags'] & 15 != 5):
        failed.append('real_exfat_readonly_nodev_with_exec_and_setid_enabled')
    metadata = rows['EXFAT_METADATA']
    if (len(metadata) != 3 or any(row is None for row in metadata)
            or [row['object'] for row in metadata] != ['root', 'subject', 'directory']):
        failed.append('metadata_identity')
    else:
        mode = 0o7777 if old else 0o777
        for row, kind in zip(metadata, (0o40000, 0o100000, 0o40000)):
            if (row['uid'], row['gid'], row['mode'], row['type']) != (0, 0, mode, kind):
                failed.append('metadata_' + row['object'])
            if not 0 <= row['device'] < 1 << 64 or not 0 < row['inode'] < 1 << 64:
                failed.append('metadata_unsigned_identity')
        if len({row['device'] for row in metadata}) != 1 or len({row['inode'] for row in metadata}) != 3:
            failed.append('same_filesystem_distinct_inodes')
    if rows['EXFAT_ELF_MATCH'] != [{'source': source_head, 'bytes': probe_size}]:
        failed.append('same_executable_and_frozen_source_marker')
    expected_creds = []
    for condition in ('plain', 'nnp'):
        for phase in ('before', 'after'):
            row = {key: 65534 for key in IDS}
            if old and condition == 'plain' and phase == 'after':
                row.update({key: 0 for key in ('euid', 'suid', 'fsuid', 'egid', 'sgid', 'fsgid')})
            row.update({key: 0 for key in CAPS})
            row.update(phase=phase, condition=condition, groups=0,
                       nnp=int(condition == 'nnp'), securebits=0, keepcaps=0)
            expected_creds.append(row)
    if rows['EXFAT_CREDENTIALS'] != expected_creds:
        failed.append('exact_pre_and_post_exec_credentials')
    if rows['EXFAT_CHILD'] != [{'condition': name, 'exit': 0, 'signal': 0} for name in ('plain', 'nnp')]:
        failed.append('both_actual_exec_children_completed')
    cleanup = 'EXFAT_CLEANUP unmounted=1 backing=' + ('virtio detached=0' if guest else 'loop detached=1')
    if lines.count(COMPLETE) != 1 or lines.count(cleanup) != 1:
        failed.append('completed_and_cleaned_up')
    if not guest:
        loops = [record(line, 'EXFAT_LOOP', ['readonly', 'autoclear', 'inode', 'device'])
                 for line in observed if line.startswith('EXFAT_LOOP')]
        if (len(loops) != 1 or loops[0] is None or loops[0]['readonly'] != 1
                or loops[0]['autoclear'] != 1 or loops[0]['inode'] <= 0 or loops[0]['device'] < 0):
            failed.append('owned_readonly_loop')
        if len(lines) != len(observed):
            failed.append('unexpected_linux_output')
    elif (lines.count(COMPLETE) != 1 or lines.count(BOOT) != 1 or lines.count(PROCESS_EXIT) != 1
          or not lines.index(COMPLETE) < lines.index(PROCESS_EXIT) < lines.index(BOOT)):
        failed.append('guest_boot_after_real_process_exit')
    if re.search(r'(?i)kernel panic|panicked at|fatal exception|EXFAT_ERROR', text):
        failed.append('runtime_failure')
    if type(code) is not int or code != (33 if guest else 0) or timed_out is not False:
        failed.append('real_process_status')
    if len(raw) > LOG_LIMIT or not re.fullmatch('[0-9a-f]{40}', source_head) or not 0 < probe_size < 16 * 1024 * 1024:
        failed.append('evidence_bounds')
    return {'passed': not failed, 'failed_conditions': failed, 'observations': rows,
            'expected_statfs_type': expected_type, 'linux_statfs_type_compatible': not guest,
            'expected_old_behavior': old, 'actual_exec_count': len(rows['EXFAT_CHILD']),
            'raw_sha256': sha(raw), 'raw_bytes': len(raw)}


def bounded_command(command, output, groups, timeout, *, env=None, log_limit=LOG_LIMIT):
    output.mkdir(mode=0o700)
    require(groups.child_anchor_available(), 'waitable process group anchor unavailable')
    receipt = {'command': command, 'timeout_seconds': timeout, 'log_limit': log_limit}
    save(output / 'command.json', receipt)
    started = time.monotonic()
    stop = None
    with (output / 'stdout.log').open('xb') as stdout, (output / 'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True, env=env)
        group = groups.ChildGroup(process)
        try:
            while True:
                try:
                    group.wait_exit(0.25)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started > timeout:
                        stop = 'timeout'
                    elif os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > log_limit:
                        stop = 'log_limit'
                    elif shutil.disk_usage(output).free < 1024 * 1024 * 1024:
                        stop = 'disk_reserve'
                    if stop:
                        break
        finally:
            code = groups.terminate_group(group)
    receipt.update(process_exit=code, timed_out=stop == 'timeout', stop_reason=stop,
                   process_group_cleanup_completed=True, elapsed_seconds=time.monotonic() - started,
                   stdout_sha256=digest_file(output / 'stdout.log'), stderr_sha256=digest_file(output / 'stderr.log'))
    save(output / 'result.json', receipt)
    return receipt


def require_command(receipt):
    require(receipt['process_exit'] == 0 and receipt['stop_reason'] is None, 'bounded command failed')


def checked_probe(path, expected, shared):
    probe = read(path, 16 * 1024 * 1024)
    require(sha(probe) == expected, 'frozen probe hash differs')
    shared.require_static_probe(path, probe)
    return probe


def run_reference(args, out, report, shared):
    require(os.geteuid() == 0, 'reference requires disposable Linux root')
    probe = checked_probe(args.probe_elf, args.expected_probe_sha256, shared)
    frozen = out / 'probe.elf'
    frozen.write_bytes(probe)
    frozen.chmod(0o700)
    compile_raw = read(args.compile_receipt, 1024 * 1024)
    compile_record = json.loads(compile_raw)
    require(compile_record['exit'] == 0 and compile_record['probe_sha256'] == sha(probe)
            and compile_record['source_sha256'] == sha(read(PROBE)), 'compiler receipt differs')
    (out / 'compile.json').write_bytes(compile_raw)
    report.update(probe_sha256=sha(probe), probe_bytes=len(probe), host_kernel=os.uname().release,
                  host_arch=os.uname().machine, source_head=args.expected_source_head,
                  private_mount_namespace=True, compiler_receipt_sha256=sha(compile_raw))
    template = out / 'image.raw'
    with template.open('xb'):
        pass
    for name, command in (
        ('allocate', ['fallocate', '-l', str(IMAGE_SIZE), str(template)]),
        ('format', ['mkfs.exfat', str(template)]),
    ):
        binary = shutil.which(command[0])
        require(binary is not None, 'missing formatter/allocation tool')
        command[0] = binary
        report[name + '_tool'] = {'path': binary, 'sha256': digest_file(Path(binary))}
        require_command(bounded_command(command, out / name, shared.groups, 60))
    version = bounded_command(['mkfs.exfat', '-V'], out / 'formatter-version', shared.groups, 10)
    require_command(version)
    unshare = shutil.which('unshare')
    require(unshare is not None, 'unshare unavailable')
    report['unshare_sha256'] = digest_file(Path(unshare))
    prepare = [unshare, '--mount', '--propagation', 'private', '--', str(frozen),
               '--prepare-image', str(template), str(out / 'prepare-mount'), args.expected_source_head]
    save(out / 'input.json', {'source_head': args.expected_source_head, 'source_inputs': report['source_inputs'],
                             'probe_sha256': sha(probe), 'empty_image_sha256': digest_file(template, IMAGE_SIZE),
                             'command': prepare, 'private_mount_namespace': True})
    report['input_sha256'] = digest_file(out / 'input.json')
    prepared = bounded_command(prepare, out / 'prepare', shared.groups, 120)
    require_command(prepared)
    prepare_lines = read(out / 'prepare/stdout.log').decode().splitlines()
    require(len(prepare_lines) == 3 and prepare_lines[0].startswith('EXFAT_LOOP readonly=0 autoclear=1 ')
            and prepare_lines[1] == f'EXFAT_PREPARED source={args.expected_source_head} bytes={len(probe)}'
            and prepare_lines[2] == 'EXFAT_CLEANUP unmounted=1 backing=loop detached=1'
            and read(out / 'prepare/stderr.log') == b'', 'image population/cleanup incomplete')
    report['image_sha256'] = digest_file(template, IMAGE_SIZE)
    copy = out / 'linux-copy.raw'
    shutil.copyfile(template, copy)
    require(digest_file(copy, IMAGE_SIZE) == report['image_sha256'], 'Linux image copy differs')
    command = [unshare, '--mount', '--propagation', 'private', '--', str(frozen),
               '--reference-image', str(copy), str(out / 'reference-mount'), args.expected_source_head]
    execution = bounded_command(command, out / 'execution', shared.groups, 120)
    report['execution'] = execution
    verdict = evaluate(read(out / 'execution/stdout.log'), execution['process_exit'], execution['timed_out'],
                       args.expected_source_head, len(probe), guest=False)
    report['verdict'] = verdict
    report['image_after_sha256'] = digest_file(copy, IMAGE_SIZE)
    require(execution['stop_reason'] is None and read(out / 'execution/stderr.log') == b''
            and verdict['passed'], 'Linux reference failed independent observation checks')
    require(report['image_after_sha256'] == report['image_sha256'], 'read-only Linux image changed')
    require(digest_file(template, IMAGE_SIZE) == report['image_sha256'], 'frozen image changed')
    require(read(frozen) == probe and checked_probe(args.probe_elf, args.expected_probe_sha256, shared) == probe,
            'original or frozen observation ELF changed')
    require(digest_file(Path(unshare)) == report['unshare_sha256']
            and all(digest_file(Path(report[name + '_tool']['path'])) == report[name + '_tool']['sha256']
                    for name in ('allocate', 'format')), 'reference executable changed')
    with template.open('rb') as source, (out / 'image.raw.gz').open('xb') as destination:
        with gzip.GzipFile(fileobj=destination, mode='wb', filename='', mtime=0) as zipped:
            shutil.copyfileobj(source, zipped, 1024 * 1024)
    require((out / 'image.raw.gz').stat().st_size <= 32 * 1024 * 1024, 'compressed fixture unexpectedly large')
    report['compressed_image_sha256'] = digest_file(out / 'image.raw.gz')
    # Only our verified disposable reference copy is removed; all receipts stay.
    copy.unlink()
    report.update(passed=True, disposable_reference_copy_removed=True, probe_inputs_unchanged=True)


def load_reference(directory, expected, head, shared):
    raw = read(directory / 'result.json', 1024 * 1024)
    report = json.loads(raw)
    require(report['schema'] == 'a06.exfat-linux.v1' and report['passed'] is True
            and report['runner_inputs_unchanged'] is True and report['private_mount_namespace'] is True
            and report['probe_inputs_unchanged'] is True, 'reference did not qualify')
    require(report['source_inputs'] == source_inputs() and report['source_head'] == head,
            'reference source identity differs')
    probe = checked_probe(directory / 'probe.elf', expected, shared)
    require(report['probe_sha256'] == expected and report['probe_bytes'] == len(probe), 'reference ELF differs')
    require(digest_file(directory / 'compile.json') == report['compiler_receipt_sha256']
            and digest_file(directory / 'input.json') == report['input_sha256'], 'reference frozen inputs changed')
    execution = report['execution']
    stdout, stderr = read(directory / 'execution/stdout.log'), read(directory / 'execution/stderr.log')
    require(sha(stdout) == execution['stdout_sha256'] and sha(stderr) == execution['stderr_sha256']
            and stderr == b'' and execution['stop_reason'] is None
            and execution['process_group_cleanup_completed'] is True, 'reference execution changed')
    require(evaluate(stdout, execution['process_exit'], execution['timed_out'], head, len(probe), guest=False)['passed'],
            'reference raw observations do not qualify')
    require(digest_file(directory / 'image.raw', IMAGE_SIZE) == report['image_sha256'], 'frozen image changed')
    return probe, report['image_sha256'], sha(raw)


def build_initramfs(original, probe, head, common):
    require(re.fullmatch('[0-9a-f]{40}', head), 'invalid image source identity')
    entries = common.unpack(gzip.decompress(original))
    require(common.unpack(common.pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = (f'if EXFAT_DISPOSABLE_GUEST=1 /bin/exfat-exec-probe --guest {head}; then\n'
                '    exfat_exit=0\nelse\n    exfat_exit=$?\nfi\n'
                'echo "EXFAT_PROCESS_EXIT=$exfat_exit"\n').encode()
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') != 'bin/exfat-exec-probe', 'probe already in original initramfs')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'ambiguous original init')
            content = content.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(content)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init missing')
    name = 'bin/exfat-exec-probe'
    changed.append((name, [max(e[1][0] for e in entries) + 1, 0o100755, 0, 0, 1, 0,
                           len(probe), 0, 0, 0, 0, len(name) + 1, 0], probe))
    require(common.unpack(common.pack(changed)) == changed and len(changed) == len(entries) + 1,
            'injected newc did not preserve original entries')
    return gzip.compress(common.pack(changed), mtime=0)


def run_guest(args, out, product_dir, source_head, source_tree, original_head, old, shared):
    out.mkdir(mode=0o700)
    common = shared.common
    kernel, product_sha = common.product_input(product_dir, source_head, source_tree)
    probe, image_sha, reference_sha = load_reference(args.linux_reference, args.expected_probe_sha256, original_head, shared)
    snapshot = json.loads(read(product_dir / 'source-before.json'))['files']
    require(all(snapshot[name]['sha256'] == identity['sha256'] and snapshot[name]['size'] == identity['size']
                for name, identity in source_inputs().items()), 'executed source differs from product snapshot')
    original = common.read_pinned(product_dir / 'product-boot/initramfs.cpio.gz', common.INITRD_SHA, 8 * 1024 * 1024)
    bios = common.read_pinned(product_dir / 'bios.bin', common.BIOS_SHA, 2 * 1024 * 1024)
    initrd = build_initramfs(original, probe, original_head, common)
    for name, data in (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd)):
        (out / name).write_bytes(data)
    image = out / 'disk.raw'
    shutil.copyfile(args.linux_reference / 'image.raw', image)
    require(digest_file(image, IMAGE_SIZE) == image_sha, 'guest image differs from frozen Linux image')
    binary = shutil.which(args.qemu)
    require(binary is not None, 'QEMU unavailable')
    version = subprocess.check_output([binary, '--version'], timeout=10).decode()
    require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
    command = [binary, '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
               '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
               '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
               '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
               '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
               '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
               '-drive', f'if=none,format=raw,id=exfat,file={image}',
               '-device', 'virtio-blk-pci,bus=pcie.0,addr=0x7,drive=exfat,serial=vexfat,disable-legacy=on,'
                          'disable-modern=off,queue-size=64,num-queues=1,request-merging=off,backend_defaults=off,'
                          'discard=off,write-zeroes=off,event_idx=off,indirect_desc=off,queue_reset=off']
    report = {'schema': 'a06.exfat-guest.v1', 'passed': False, 'source_head': source_head,
              'source_tree': source_tree, 'frozen_candidate_head': original_head,
              'kernel_sha256': sha(kernel), 'probe_sha256': sha(probe), 'image_before_sha256': image_sha,
              'bios_sha256': sha(bios), 'original_initramfs_sha256': sha(original), 'initramfs_sha256': sha(initrd),
              'product_receipt_sha256': product_sha, 'linux_reference_receipt_sha256': reference_sha,
              'qemu_sha256': digest_file(Path(binary)), 'qemu_version': version, 'command': command}
    save(out / 'input.json', report)
    execution = bounded_command(command, out / 'execution', shared.groups, 180)
    report['execution'] = execution
    raw = read(out / 'execution/stdout.log') + read(out / 'execution/stderr.log')
    # Save the exact streams separately; this combined stream is only an oracle
    # convenience. QEMU's stdout carries guest serial, stderr must be empty.
    report['image_after_sha256'] = digest_file(image, IMAGE_SIZE)
    report['positive_oracle'] = evaluate(raw, execution['process_exit'], execution['timed_out'],
                                         original_head, len(probe), guest=True)
    report['old_behavior_oracle'] = evaluate(raw, execution['process_exit'], execution['timed_out'],
                                             original_head, len(probe), guest=True, old=True)
    expected = report['old_behavior_oracle' if old else 'positive_oracle']['passed']
    opposite = report['positive_oracle' if old else 'old_behavior_oracle']['passed']
    report['passed'] = (expected and not opposite and execution['stop_reason'] is None
                        and read(out / 'execution/stderr.log') == b'')
    for name, data in (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd)):
        require(read(out / name) == data, 'frozen guest input changed: ' + name)
    require(load_reference(args.linux_reference, args.expected_probe_sha256, original_head, shared)
            == (probe, image_sha, reference_sha), 'reference changed during guest')
    require(common.product_input(product_dir, source_head, source_tree) == (kernel, product_sha), 'product evidence changed')
    require(digest_file(Path(binary)) == report['qemu_sha256'], 'QEMU executable changed')
    report['frozen_inputs_unchanged'] = True
    # Retain output disk bytes if the driver wrote them despite the read-only
    # mount. The pristine template and all three before hashes remain distinct.
    with image.open('rb') as source, (out / 'disk-after.raw.gz').open('xb') as destination:
        with gzip.GzipFile(fileobj=destination, mode='wb', filename='', mtime=0) as zipped:
            shutil.copyfileobj(source, zipped, 1024 * 1024)
    require((out / 'disk-after.raw.gz').stat().st_size <= 32 * 1024 * 1024, 'guest disk output exceeds artifact bound')
    report['compressed_output_sha256'] = digest_file(out / 'disk-after.raw.gz')
    image.unlink()
    save(out / 'result.json', report)
    require(report['passed'], 'guest did not prove the required complete phenotype')
    return report


def build_product(args, out, head, tree, shared):
    require(shutil.disk_usage(out.parent).free >= 8 * 1024 * 1024 * 1024, 'less than 8 GiB before product build')
    command = [sys.executable, '-I', '-B', str(ROOT / 'tests/kernel/control/run_queryabi_candidate_guest.py'),
               '--expected-source-head', head, '--expected-source-tree', tree,
               '--target-dir', str(args.target_dir), '--output', str(out), '--cc', args.cc, '--qemu', args.qemu]
    env = dict(os.environ, CARGO_BUILD_JOBS='2')
    execution = bounded_command(command, out.with_name(out.name + '-command'), shared.groups, 1800, env=env)
    require_command(execution)
    shared.common.product_input(out, head, tree)


def run_qualification(args, out, report, shared, product, negative):
    require(os.geteuid() != 0, 'product builds and guests must run as the CI checkout owner')
    head, tree = args.expected_source_head, args.expected_source_tree
    before = product.source_snapshot(ROOT, head, tree)
    save(out / 'source-before.json', before)
    report.update(source_head=head, source_tree=tree, configuration='ordinary product; one disk; one CPU',
                  no_original_gate_replacement=True, hepta_durability=False, production_ready=False)
    load_reference(args.linux_reference, args.expected_probe_sha256, head, shared)
    require(not args.target_dir.exists(), 'qualification target must be a new owned directory')
    require(not args.target_dir.resolve().is_relative_to(ROOT), 'build target must be outside checkout')
    build_product(args, out / 'positive-product', head, tree, shared)
    report['positive'] = run_guest(args, out / 'positive', out / 'positive-product', head, tree, head, False, shared)
    patch = read(ROOT / PATCH_NAME)
    require(sha(patch) == PATCH_SHA, 'frozen production negative changed')
    (out / 'negative.patch').write_bytes(patch)
    env = dict(os.environ, GIT_INDEX_FILE=str(out / 'negative-index'),
               GIT_AUTHOR_NAME='ExFAT qualification', GIT_AUTHOR_EMAIL='qualification@invalid',
               GIT_COMMITTER_NAME='ExFAT qualification', GIT_COMMITTER_EMAIL='qualification@invalid')
    def git(*argv):
        return subprocess.check_output(['git', *argv], cwd=ROOT, env=env)
    git('read-tree', head)
    git('apply', '--cached', '--check', str(out / 'negative.patch'))
    git('apply', '--cached', str(out / 'negative.patch'))
    require(git('diff', '--cached', '--name-only', head).decode().splitlines() == [INODE],
            'negative changed more than the reviewed production helper')
    negative_tree = git('write-tree').decode().strip()
    negative_head = git('commit-tree', negative_tree, '-p', head, '-m',
                        'LOCAL QUALIFICATION ONLY: restore old ExFAT synthesized set-ID mode').decode().strip()
    report.update(negative_head=negative_head, negative_tree=negative_tree, negative_patch_sha256=PATCH_SHA)
    save(out / 'negative-identity.json', {'head': negative_head, 'tree': negative_tree, 'parent': head,
                                        'only_changed_path': INODE, 'patch_sha256': PATCH_SHA})
    with negative.identified_checkout(ROOT, head, negative_head):
        snapshot = product.source_snapshot(ROOT, negative_head, negative_tree)
        save(out / 'negative-source.json', snapshot)
        differences = [name for name in set(before['files']) | set(snapshot['files'])
                       if before['files'].get(name) != snapshot['files'].get(name)]
        require(differences == [INODE], 'negative source conservation failed')
        build_product(args, out / 'negative-product', negative_head, negative_tree, shared)
        report['negative'] = run_guest(args, out / 'negative', out / 'negative-product',
                                       negative_head, negative_tree, head, True, shared)
    after = product.source_snapshot(ROOT, head, tree)
    save(out / 'source-after.json', after)
    require(after == before, 'candidate was not fully restored')
    require(report['positive']['kernel_sha256'] != report['negative']['kernel_sha256'], 'negative kernel did not change')
    require(report['positive']['probe_sha256'] == report['negative']['probe_sha256'] == args.expected_probe_sha256
            and report['positive']['image_before_sha256'] == report['negative']['image_before_sha256'],
            'positive and negative did not execute the same frozen ELF/image')
    report.update(passed=True, source_restored=True, guest_execs=4, linux_execs=2,
                  negative_requires_real_setid_transition=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    reference = commands.add_parser('reference')
    reference.add_argument('--probe-elf', type=Path, required=True)
    reference.add_argument('--compile-receipt', type=Path, required=True)
    qualification = commands.add_parser('qualify')
    qualification.add_argument('--linux-reference', type=Path, required=True)
    qualification.add_argument('--expected-source-tree', required=True)
    qualification.add_argument('--target-dir', type=Path, required=True)
    qualification.add_argument('--cc', default='gcc-13')
    qualification.add_argument('--qemu', default='qemu-system-x86_64')
    for command in (reference, qualification):
        command.add_argument('--expected-source-head', required=True)
        command.add_argument('--expected-probe-sha256', required=True)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('EXFAT_DISPOSABLE_CI') == '1',
            'mount/guest execution is restricted to the explicit disposable CI profile')
    require(re.fullmatch('[0-9a-f]{40}', args.expected_source_head), 'invalid source identity')
    require(re.fullmatch('[0-9a-f]{64}', args.expected_probe_sha256), 'invalid probe identity')
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT),
            'output must be a new directory outside the checkout')
    out.mkdir(parents=True, mode=0o700)
    shared, product, negative = helpers()
    report = {'schema': 'a06.exfat-' + ('linux' if args.mode == 'reference' else 'qualification') + '.v1',
              'passed': False, 'source_inputs': source_inputs()}
    try:
        if args.mode == 'reference':
            run_reference(args, out, report, shared)
        else:
            run_qualification(args, out, report, shared, product, negative)
        require(source_inputs() == report['source_inputs'], 'runner/source inputs changed')
        report['runner_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, shared.groups.GateError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    save(out / 'result.json', report)
    print(json.dumps({key: report[key] for key in ('passed', 'schema', 'error') if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
