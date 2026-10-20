#!/usr/bin/env python3
"""Archive only completed saved A/B outputs and immutable Git objects."""
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile

scratch = Path('/workspace/scratch/ae1a8cf05419')
repo = scratch / 'trillionnium-os-desktop'
source = scratch / 'next8-repeatability'
destination = repo / 'support/build/evidence/2026-10-16-clean-repeatability/clean-pair'
commit = '5bcec614c1a075782b6ffaa5a5212fdee29be37d'
tree = '00e70e58dfa0dbf4718db55240136683f0a23310'
sha = lambda data: hashlib.sha256(data).hexdigest()


def write(name, value):
    target = destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2) + '\n')


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=repo)


def read_saved(path):
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1 or initial.st_size > 128 * 1024**2:
        raise ValueError('saved evidence must be bounded regular nonlinked file: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            data = stream.read(128 * 1024**2 + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if not all(getattr(initial, key) == getattr(before, key) == getattr(after, key) for key in fields):
        raise ValueError('saved evidence changed during read: ' + str(path))
    if len(data) != before.st_size:
        raise ValueError('saved evidence size differs')
    return data


assert not destination.exists()
destination.mkdir(parents=True)
saved = {str(path.relative_to(source)): read_saved(path) for path in sorted(source.rglob('*')) if not path.is_dir()}
assert len(saved) == 35 and sum(map(len, saved.values())) < 1024**3
pair = json.loads(saved['pair.json'])
between = json.loads(saved['between-builds.json'])
assert pair['source_commit'] == commit and pair['source_tree'] == tree
assert git('rev-parse', commit + '^{tree}').decode().strip() == tree
assert pair['controller_sha256'] == sha(saved['controller.py'])
assert pair['all_public_boots_passed'] and pair['same_host_same_path_kernel_equal'] and pair['initramfs_equal']
assert pair['cross_directory_or_cross_host_reproducibility_claimed'] is False
assert between['artifacts_verified_before_deletion'] and between['custody_removed'] and between['target_absent']
assert between['original'] == pair['environment']['CARGO_TARGET_DIR']

# All fixed code/config bytes are read through Git objects, never through the active worktree.
paths = [
    'support/build/kernel.sh', 'support/build/kernel-supervisor.py', 'support/build/cleanup-manifest.py',
    'support/build/check-boot.py', 'support/build/verify-source.py', 'support/build/minimal/prepare-initramfs.py',
    'support/build/minimal/init', 'support/build/record-qemu.py',
    'support/build/minimal.mk', 'support/build/minimal/OSDK.toml', 'support/build/minimal/Cargo.lock',
    'kernel/asterinas/Cargo.lock', 'kernel/asterinas/Cargo.toml', 'kernel/asterinas/Makefile',
    'kernel/asterinas/OSDK.toml', 'kernel/asterinas/rust-toolchain.toml', 'kernel/asterinas/LICENSE-MPL',
    'kernel/asterinas/osdk/Cargo.lock', 'kernel/asterinas/osdk/src/commands/build/mod.rs',
    'kernel/asterinas/kernel/core/src/net/uts_ns.rs',
]
source_bindings = {}
for path in paths:
    content = git('show', commit + ':' + path)
    source_bindings[path] = {'git_blob': git('rev-parse', commit + ':' + path).decode().strip(),
                             'bytes': len(content), 'sha256': sha(content)}
subtrees = {path: git('rev-parse', commit + ':' + path).decode().strip()
            for path in ('kernel/asterinas/kernel', 'kernel/asterinas/ostd', 'kernel/asterinas/osdk', 'kernel/asterinas/osdk/deps')}
checker = git('show', commit + ':support/build/check-boot.py')
namespace = {'__name__': 'archive_check_boot', '__file__': 'git-object:support/build/check-boot.py'}
exec(compile(checker, namespace['__file__'], 'exec'), namespace)
checks = []
all_artifacts = []
for label, entry in zip(('a', 'b'), pair['runs']):
    invocation = json.loads(saved[label + '/invocation.json'])
    assert invocation == entry and entry['outer_exit'] == 0 and entry['raw_qemu_exit'] == 33
    assert entry['target_absent_before_launch'] is True and entry['git_status_after'] == ''
    console = saved[label + '/console.log']
    assert sha(console) == entry['console_sha256'] and len(console) == entry['console_bytes']
    qemu = json.loads(saved[label + '/run/qemu.json'])
    kernel_gzip = saved[label + '/kernel.elf.gz']
    kernel = gzip.decompress(kernel_gzip)
    initramfs = saved[label + '/run/initramfs.cpio.gz']
    serial = saved[label + '/run/serial.log']
    assert sha(kernel_gzip) == entry['kernel_gzip_sha256']
    for option, data in (('-kernel', kernel), ('-initrd', initramfs)):
        artifact = qemu['artifacts'][option]
        assert sha(data) == artifact['sha256'] and len(data) == artifact['size']
    assert kernel.startswith(b'\x7fELF') and len(kernel) == entry['kernel_size']
    assert sha(serial) == qemu['serial_sha256'] == entry['serial_sha256'] and len(serial) == qemu['serial_size']
    init_manifest = json.loads(saved[label + '/run/initramfs-manifest.json'])
    assert sha(initramfs) == init_manifest['image_sha256'] and len(initramfs) == init_manifest['image_size']
    unpacked = gzip.decompress(initramfs)
    assert sha(unpacked) == init_manifest['uncompressed_sha256'] and len(unpacked) == init_manifest['uncompressed_size']
    source_input = json.loads(saved[label + '/run/source-inputs.json'])
    assert source_input['passed'] is True and source_input['errors'] == [] and source_input['checked_files'] == 118
    for path, expected in source_input['input_sha256'].items():
        assert source_bindings['kernel/asterinas/' + path]['sha256'] == expected
    environment = saved[label + '/run/environment.log'].decode()
    for path in ('support/build/minimal/Cargo.lock', 'support/build/cleanup-manifest.py'):
        assert source_bindings[path]['sha256'] + '  ' in environment
    assert commit in environment and 'RUSTFLAGS=<unset>' in environment
    assert 'CARGO_ENCODED_RUSTFLAGS=<unset>' in environment
    assert 'ASTER_BUILD_TIMESTAMP=' + pair['environment']['ASTER_BUILD_TIMESTAMP'] in environment
    cleanup = json.loads(saved[label + '/run/manifest-cleanup.json'])
    assert cleanup['outcome'] == 'owned_removed' and cleanup['passed'] and cleanup['custody_removed']
    assert cleanup['anchor'] == cleanup['captured'] and cleanup['owned_fd'] == 8
    assert cleanup['helper_sha256'] == source_bindings['support/build/cleanup-manifest.py']['sha256']
    supervision = [json.loads(line.split('A01_KERNEL_SUPERVISOR ', 1)[1])
                   for line in console.decode().splitlines() if line.startswith('A01_KERNEL_SUPERVISOR ')]
    assert len(supervision) == 1
    supervisor = supervision[0]
    assert supervisor['worker_reaped'] and supervisor['raw_worker_exit'] == supervisor['exit_code'] == 0
    assert supervisor['external_reap_disarmed'] is False
    for name in ('make-exit-code.txt', 'run-exit-code.txt', 'log-exit-code.txt', 'manifest-cleanup-exit-code.txt'):
        assert saved[label + '/run/' + name].strip() == b'0'
    offline = namespace['check_boot'](source / label / 'run', False)
    assert offline['passed']
    elapsed = (datetime.fromisoformat(entry['completed_utc']) - datetime.fromisoformat(entry['started_utc'])).total_seconds()
    checks.append({'label': label, 'independent_offline_check_from_fixed_git': offline,
                   'controller_elapsed_seconds': elapsed, 'supervisor': supervisor,
                   'fixed_inputs_checked': len(source_input['input_sha256']), 'source_check_recorded_files': 118,
                   'compiling_lines': sum('Compiling ' in line for line in console.decode().splitlines()),
                   'finished_lines': [line.strip() for line in console.decode().splitlines() if 'Finished ' in line]})
    all_artifacts.append({'label': label, 'kernel_gzip_sha256': sha(kernel_gzip), 'kernel_sha256': sha(kernel),
                          'kernel_bytes': len(kernel), 'initramfs_sha256': sha(initramfs), 'initramfs_bytes': len(initramfs),
                          'serial_sha256': sha(serial), 'serial_bytes': len(serial)})
    # Readable records stay separate from the complete raw archive.
    for name in ('invocation.json',):
        (destination / label).mkdir(exist_ok=True)
        (destination / label / name).write_bytes(saved[label + '/' + name])
    for name in ('qemu.json', 'environment.log', 'command.sh', 'source-inputs.json', 'initramfs-manifest.json',
                 'manifest-cleanup.json', 'make-exit-code.txt', 'run-exit-code.txt', 'log-exit-code.txt', 'manifest-cleanup-exit-code.txt'):
        (destination / label / name).write_bytes(saved[label + '/run/' + name])
    (destination / label / 'serial.log.gz').write_bytes(gzip.compress(serial, mtime=0))
    write(label + '/independent-check.json', checks[-1])

assert gzip.decompress(saved['a/kernel.elf.gz']) == gzip.decompress(saved['b/kernel.elf.gz'])
assert saved['a/kernel.elf.gz'] == saved['b/kernel.elf.gz']
assert saved['a/run/initramfs.cpio.gz'] == saved['b/run/initramfs.cpio.gz']
(destination / 'artifacts').mkdir()
for label in ('a', 'b'):
    (destination / 'artifacts' / (label + '.kernel.elf.gz')).write_bytes(saved[label + '/kernel.elf.gz'])
(destination / 'artifacts/initramfs.cpio.gz').write_bytes(saved['a/run/initramfs.cpio.gz'])
for name in ('controller.py', 'pair.json', 'between-builds.json'):
    (destination / name).write_bytes(saved[name])
write('artifact-bindings.json', {'initramfs_deduplicated_only_after_full_byte_comparison': True,
                               'per_run_kernel_files': {'a': 'artifacts/a.kernel.elf.gz', 'b': 'artifacts/b.kernel.elf.gz'},
                               'shared_initramfs': 'artifacts/initramfs.cpio.gz',
                               'per_run': all_artifacts})
write('source-bindings.json', {'source_commit': commit, 'source_tree': tree, 'git_object_inputs': source_bindings,
                             'runtime_subtrees': subtrees, 'runtime_git_status_both': ['', ''],
                             'kernel_minimal_lock_enforced_by_fixed_source': 'OSDK_CARGO_LOCK + --locked',
                             'no_current_source_or_target_reads': True})
write('independent-checks.json', checks)

provenance = {}
for name in ('next8-pair-independent-bytes.json', 'next8-pair-B-lock.json', 'next8-pair-B-generated.Cargo.lock'):
    data = read_saved(scratch / name)
    (destination / 'provenance').mkdir(exist_ok=True)
    (destination / 'provenance' / name).write_bytes(data)
    provenance[name] = {'bytes': len(data), 'sha256': sha(data)}
b_lock = json.loads((destination / 'provenance/next8-pair-B-lock.json').read_text())
assert b_lock['stable_read'] and b_lock['before'] == b_lock['after'] and b_lock['matches_committed_minimal_lock']
assert b_lock['run_a_generated_lock_snapshot_retained'] is False
assert b_lock['sha256'] == sha((destination / 'provenance/next8-pair-B-generated.Cargo.lock').read_bytes())
assert b_lock['sha256'] == source_bindings['support/build/minimal/Cargo.lock']['sha256']

# Keep every original nonbinary output byte; binary aliases bind the two retained shared artifacts.
binary_aliases = {'a/kernel.elf.gz', 'b/kernel.elf.gz', 'a/run/initramfs.cpio.gz', 'b/run/initramfs.cpio.gz'}
members = []
raw_tar = io.BytesIO()
with tarfile.open(fileobj=raw_tar, mode='w', format=tarfile.PAX_FORMAT) as archive:
    for name, data in saved.items():
        if name in binary_aliases:
            continue
        member = tarfile.TarInfo(name)
        member.size = len(data)
        member.mode = 0o644
        member.mtime = 0
        archive.addfile(member, io.BytesIO(data))
        members.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
(destination / 'raw-logs.tar.gz').write_bytes(gzip.compress(raw_tar.getvalue(), mtime=0))
with tarfile.open(destination / 'raw-logs.tar.gz', 'r:gz') as archive:
    assert len(archive.getmembers()) == len(members) == 31
    for member, record in zip(archive.getmembers(), members):
        data = archive.extractfile(member).read()
        assert member.name == record['path'] and data == saved[member.name]
        assert len(data) == record['bytes'] and sha(data) == record['sha256']
write('raw-logs.members.json', {'members': members, 'independent_reopen_each_member_byte_sha_verified': True})
write('raw-output-inventory.json', {'original_files': [{'path': name, 'bytes': len(data), 'sha256': sha(data),
                                                       'storage': ('artifacts/' + name[0] + '.kernel.elf.gz' if name.endswith('kernel.elf.gz') else 'artifacts/initramfs.cpio.gz') if name in binary_aliases else 'raw-logs.tar.gz'}
                                                      for name, data in saved.items()],
                                  'original_file_count': len(saved), 'raw_tar_members': len(members),
                                  'root_followup_provenance': provenance})
write('independent-review.json', {
    'reviewer': '/root/next5_archive/repro_config',
    'scope': 'Read-only completed saved outputs plus fixed Git objects; no current target/manifest reads, no Cargo/rustc/VM or writes.',
    'passed': True, 'blockers': [],
    'observations': ['pair and invocations agree; controller SHA matches',
                     'six upstream hashes, minimal lock and helper match fixed Git blobs; 118-file checks pass',
                     'environment logs differ only in first timestamp line',
                     'workers 22 and 4946 reaped normally; all entry/worker/check statuses pass',
                     'FD8 manifest inode matched and was removed',
                     'A 279 Compiling lines/two Finished lines including SDK; B 177 Compiling lines/one Finished line',
                     'registry shared; SDK rebuilt during A and reused during B; not an all-tools cold build',
                     'serial SHA differs; logs are not claimed byte-identical']})
write('report.json', {'kind': 'actual_same_host_same_path_two_clean_kernel_target_builds_and_boots',
                      'source_commit': commit, 'source_tree': tree,
                      'actual_controller_tool_observation': {'session': 86915, 'exit_code': 0,
                                                            'source': 'parent actual completed tool result; distinct from per-entry receipts'},
                      'clean_target_before_each_launch': True, 'native_guests': 2, 'outer_exits': [0, 0], 'raw_qemu_exits': [33, 33],
                      'kernel_byte_equality_independently_verified': True, 'initramfs_byte_equality_independently_verified': True,
                      'kernel_sha256': all_artifacts[0]['kernel_sha256'], 'kernel_bytes': all_artifacts[0]['kernel_bytes'],
                      'initramfs_sha256': all_artifacts[0]['initramfs_sha256'], 'initramfs_bytes': all_artifacts[0]['initramfs_bytes'],
                      'serial_byte_equality_claimed': False, 'captured_all_original_outputs_before_cache_deletion': True,
                      'old_cache_custody_record': 'between-builds.json', 'offline_checks_passed': 2,
                      'fixed_upstream_files_recorded_checked_each': 118, 'fixed_input_hashes_independently_compared_each': 6,
                      'run_a_generated_lock_snapshot_retained': False, 'run_b_generated_lock_followup': 'provenance/next8-pair-B-lock.json',
                      'same_host_same_absolute_path': pair['cwd'], 'shared_registry_cache': True,
                      'sdk_rebuilt_a_reused_b': True, 'all_tool_caches_cold_claimed': False,
                      'cross_directory_or_cross_host_reproducibility_claimed': False,
                      'current_target_or_manifest_read_during_packaging': False,
                      'new_vm_cargo_rustc_or_git_writes_during_packaging': False})
(destination / 'archive-controller.py').write_bytes(Path(__file__).read_bytes())
(destination / 'README.md').write_text('''# Two real clean-target normal-kernel builds at one fixed path

Both source-to-kernel builds and QEMU boots completed at published source
`5bcec614c1a075782b6ffaa5a5212fdee29be37d`, tree
`00e70e58dfa0dbf4718db55240136683f0a23310`. Both public entries exited 0,
both normal workers were reaped, and both QEMU guests exited raw33 with full
initramfs markers. Independent saved-output boot checks passed twice.

| Result | A | B |
| --- | ---: | ---: |
| Controller elapsed seconds | 205.324 | 126.244 |
| Target absent before launch | true | true |
| Kernel bytes | 8,288,088 | 8,288,088 |
| Kernel SHA256 | `6c0c382ec88d2e59b58d50abb0ef3671635f30ce08c3b442d2bdc2204821d040` | same |
| Initramfs SHA256 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` | same |

The complete decompressed kernel bytes and initramfs bytes were independently
compared, not just their reported hashes. Each actual kernel gzip capture is
retained separately under artifacts/ and independently hashed; the identical
initramfs is retained once. artifact-bindings.json maps both original QEMU
receipts to those bytes. Serial logs differ and each keeps its own SHA.

The actual retained controller checks that target is absent before A. After
A has exited and copied every run output, it verifies stable-FD ELF bytes
against QEMU, writes and reopens gzip, and records completion. Under the
kernel lock it then rejects symlink/noncanonical target paths, confirms the
cache is ignored, moves only the newly generated target into private custody,
verifies device/inode, and deletes that custody tree. between-builds.json
records removal and target absence; B checks absence again before launch.
The archive never reads today's target or generated manifest.

pair.json and controller.py preserve selected environment, host/username,
exact workspace, epoch, TZ/locale and explicitly unset Rust flag variables.
Both environment logs and actual make commands remain readable. Source and
configuration Git blob/SHA bindings, six checked fixed upstream inputs, and
the source-enforced locked minimal dependency input are in source-bindings.
The separately retained B-only generated-lock follow-up was performed by the
root after the pair; its metadata was stable and bytes match committed b42d.
No A generated-lock snapshot survived cache deletion, and none is recreated.

This proves repeatability only on the recorded host, username and fixed
canonical workspace with the stated environment and two clean kernel target
directories. Cargo registry/download caches were shared. A rebuilt OSDK;
B reused that installed tool. This is not two fully cold toolchain/SDK builds,
and no cross-directory or cross-host bit-identity claim is made. No source
remap, component-metadata rewrite, VMX/SMP coverage or deterministic log claim
is inferred from this result. Historical e884/490 path analysis is separate.

All 35 original output files are indexed. raw-logs.tar.gz retains every byte
of the 31 nonbinary originals, including both full console/make/serial logs,
receipts and exact executed controller. Four original binary paths map to
the three separately indexed artifact files. Every tar member was independently reopened and
checked for byte equality, size and SHA. The three root follow-up records are
unaltered under provenance/. Archive generation used saved files and immutable
Git objects, with no new build, VM, source/Git writes or live target reads.
''')
files = sorted(path for path in destination.rglob('*') if path.is_file())
(destination / 'SHA256SUMS').write_text(''.join(f'{sha(path.read_bytes())}  {path.relative_to(destination)}\n' for path in files))
for line in (destination / 'SHA256SUMS').read_text().splitlines():
    expected, name = line.split('  ', 1)
    assert sha((destination / name).read_bytes()) == expected
for name, expected in ((label + '.kernel.elf.gz', all_artifacts[0]['kernel_sha256']) for label in ('a', 'b')):
    assert sha(gzip.decompress((destination / 'artifacts' / name).read_bytes())) == expected
all_files = [path for path in destination.rglob('*') if path.is_file()]
print(json.dumps({'READY': True, 'directory': str(destination), 'files': len(all_files),
                  'bytes': sum(path.stat().st_size for path in all_files), 'checksum_entries': len(files),
                  'raw_tar_members': len(members), 'source_original_files': len(saved),
                  'SHA256SUMS_sha256': sha((destination / 'SHA256SUMS').read_bytes())}, indent=2))
