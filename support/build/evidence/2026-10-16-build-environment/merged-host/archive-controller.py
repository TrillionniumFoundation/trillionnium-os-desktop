#!/usr/bin/env python3
"""Read-only validation of frozen host evidence, then archive that exact package."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile

scratch = Path('/workspace/scratch/ae1a8cf05419')
repo = scratch / 'trillionnium-os-desktop'
source = scratch / 'next9-main-host/package'
destination = repo / 'support/build/evidence/2026-10-16-build-environment/merged-host'
local_commit = 'b1a15d9afc456346410af658d2164ee5fa085656'
remote_commit = '74ee9b3d62dc85f272681c5caed3a9c328e38539'
tree = '73b34b91910852917d4c6bea020c8b4dc1e62e10'
expected_sum = 'bce5ae22f52526db83dc34d1e80faab31845133367700047f17172a822b2fcc7'
sha = lambda data: hashlib.sha256(data).hexdigest()
git = lambda *args: subprocess.check_output(['git', *args], cwd=repo)


def stable_read(path):
    first = path.lstat()
    assert stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size < 128 * 1024**2
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(128 * 1024**2)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    for name in ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns'):
        assert getattr(first, name) == getattr(before, name) == getattr(after, name)
    assert len(data) == before.st_size
    return data


def tar_members(data):
    records = {}
    modes = {}
    directories = []
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        seen = set()
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts and member.name not in seen
            seen.add(member.name)
            assert member.isfile() or member.isdir()
            assert not member.issym() and not member.islnk()
            if member.isdir():
                directories.append({'path': member.name, 'archive_mode': format(member.mode, '06o')})
                continue
            content = archive.extractfile(member).read()
            assert len(content) == member.size
            records[member.name] = content
            modes[member.name] = member.mode
    return records, modes, directories


assert not destination.exists()
package = {path.name: stable_read(path) for path in sorted(source.iterdir())}
assert len(package) == 13 and sum(map(len, package.values())) == 76286
assert sha(package['SHA256SUMS']) == expected_sum
checksummed = []
for line in package['SHA256SUMS'].decode().splitlines():
    expected, name = line.split('  ', 1)
    assert name not in checksummed and sha(package[name]) == expected
    checksummed.append(name)
assert set(checksummed) == set(package) - {'SHA256SUMS'}
raw, raw_modes, raw_dirs = tar_members(package['raw.tar.gz'])
index = json.loads(package['members.json'])['members']
assert len(raw) == len(index) == 17 and not raw_dirs
for entry in index:
    content = raw[entry['path']]
    assert len(content) == entry['bytes'] and sha(content) == entry['sha256']
archived_source, archive_modes, directories = tar_members(package['source.tar.gz'])
inputs = json.loads(package['source-inputs.json'])
assert inputs['source_commit'] == local_commit and inputs['tree'] == tree
assert sha(package['source.tar.gz']) == inputs['source_archive_sha256']
assert git('rev-parse', local_commit + '^{tree}').decode().strip() == tree
assert git('show', '-s', '--format=%P', local_commit).decode().split() == inputs['ordered_parents']
assert len(archived_source) == len(inputs['files']) == 20 and len(directories) == 8
assert set(archived_source) == {entry['path'] for entry in inputs['files']}
mode_records = []
for entry in inputs['files']:
    name = entry['path']
    data = archived_source[name]
    assert len(data) == entry['bytes'] and sha(data) == entry['sha256']
    assert git('show', local_commit + ':' + name) == data
    listing = git('ls-tree', local_commit, '--', name).decode().strip()
    git_mode, kind, rest = listing.split(' ', 2)
    blob, listed_path = rest.split('\t')
    assert listed_path == name and kind == 'blob' and blob == entry['git_blob'] and git_mode == entry['mode']
    assert archive_modes[name] & 0o111 == int(git_mode, 8) & 0o111
    mode_records.append({'path': name, 'git_mode': git_mode, 'archive_permission_mode': format(archive_modes[name], '06o'),
                         'type_regular': True, 'execute_bits_match': True, 'bytes_sha256': sha(data),
                         'git_blob': blob, 'archive_group_write_bit': bool(archive_modes[name] & 0o020)})
seed_origin = inputs['seed_lock']['origin'].removeprefix('Git ')
seed_commit, seed_path = seed_origin.split(':', 1)
assert seed_commit == local_commit and git('show', seed_origin) == package['Cargo.lock'] == raw['Cargo.lock']
assert sha(package['Cargo.lock']) == inputs['seed_lock']['sha256']
report = json.loads(package['report.json'])
assert report['success'] is False and report['final_status'] == 'partial_pass_clippy_test_lints_failed'
assert report['source_commit'] == local_commit and report['source_tree'] == tree
commands = report['commands']
for command in commands:
    log = raw[command['log']]
    assert sha(log) == command['log_sha256'] and len(log) == command['log_bytes']
assert json.loads(raw['commands.json']) == commands
summaries = re.findall(rb'test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out', raw['cargo-test.log'])
assert sum(int(item[1]) for item in summaries) == 39
assert all(item[0] == b'ok' and all(int(value) == 0 for value in item[2:]) for item in summaries)
assert b'Ran 28 tests' in raw['python-abi.log'] and raw['python-abi.log'].rstrip().endswith(b'OK')
assert raw['golden-hos2.log'] == b'12 golden HOS2 vectors verified\n'
assert raw['golden-transport32.log'] == b'1 independent 32-byte HOS2 transport golden verified\n'
codes = {item['name']: item['returncode'] for item in commands}
assert codes == {'cargo-test': 0, 'cargo-clippy': 1, 'cargo-fmt': 0, 'python-abi': 0, 'golden-hos2': 0, 'golden-transport32': 0}
assert raw['cargo-fmt.log'] == b'' and b'not installed for the toolchain' in raw['cargo-clippy.log']
clippy = json.loads(package['clippy-after-install.json'])
assert clippy['dependency_install']['returncode'] == clippy['dependency_install']['actual_session_exit'] == 0
assert clippy['dependency_install']['toolchain_replaced'] is False and clippy['clippy']['returncode'] == 101
assert clippy['clippy']['argv'] == next(item['argv'] for item in commands if item['name'] == 'cargo-clippy')
assert sha(raw['clippy-install.log']) == clippy['dependency_install']['log_sha256']
assert sha(raw['cargo-clippy-after-install.log']) == clippy['clippy']['log_sha256']
assert b'tests/mutation_kill.rs:21:10' in raw['cargo-clippy-after-install.log']
assert b'tests/transport_vectors.rs:14:32' in raw['cargo-clippy-after-install.log']
assert raw['cargo-clippy-after-install.log'].count(b'error: using `chunks_exact` with a constant chunk size') == 2
for name in ('source-after.json', 'source-after-clippy.json'):
    after = json.loads(package[name])
    assert after['tracked_input_count'] == 20 and after['changed'] == []
    assert after['all_original_source_inputs_unchanged'] and after['seed_lock_unchanged']
    assert after['lock_after_sha256'] == sha(package['Cargo.lock'])
publication_bytes = stable_read(scratch / 'next9-publication-receipt.json')
publication = json.loads(publication_bytes)
selected = [item for item in publication['publications'] if item['local_commit'] == local_commit and item['remote_commit'] == remote_commit]
assert len(selected) == 1
selected = selected[0]
assert selected['tree'] == tree and selected['ordered_parents'] == inputs['ordered_parents']
assert selected['remote_git_tree_parents_message_verified'] and selected['all_15_remote_paths_mode_type_sha_readback_verified']

(destination / 'original-package').mkdir(parents=True)
for name, content in package.items():
    (destination / 'original-package' / name).write_bytes(content)
    assert (destination / 'original-package' / name).read_bytes() == content
(destination / 'publication-receipt.json').write_bytes(publication_bytes)


def write(name, value):
    (destination / name).write_text(json.dumps(value, indent=2) + '\n')


write('publication-binding.json', {'tested_local_commit': local_commit, 'published_remote_commit': remote_commit,
    'identical_tree': tree, 'ordered_parents': inputs['ordered_parents'],
    'local_tree_and_all_20_source_git_blobs_independently_verified': True,
    'remote_binding_source': 'unaltered saved publisher API verification receipt; no new network call',
    'publication_receipt_sha256': sha(publication_bytes), 'snapshot_publications_count': len(publication['publications']),
    'selected_phase': selected['phase'], 'original_package_SUM_sha256': expected_sum})
write('source-mode-comparison.json', {'source_file_count': 20, 'source_directory_members': directories,
    'files': mode_records, 'git_numeric_mode_and_tar_permission_mode_not_claimed_identical': True,
    'note': '19 Git100644 files are tar0664; one Git100755 is tar0775. File type and execute bits match; original archive is unmodified.'})
write('independent-review.json', {'passed_as_partial_host_result': True, 'all_green': False,
    'frozen_original_files': 13, 'frozen_original_bytes': 76286, 'original_SUM_sha256': expected_sum,
    'original_sum_entries_verified': 12, 'raw_unique_regular_members_size_SHA_verified': 17,
    'source_regular_members_byte_blob_mode_checked': 20, 'source_directory_members': 8,
    'mode_boundary': 'Exact Git modes independently checked; tar group-write differs as separately recorded; source archive preserved.',
    'results': {'rust_passed': 39, 'rust_failed_ignored_filtered': [0, 0, 0], 'python_passed': 28,
                'fmt_exit': 0, 'golden_hos2': 12, 'golden_transport32': 1,
                'initial_controller_exit': 1, 'fixed_nightly_clippy_install_actual_exit': 0, 'clippy_retry_exit': 101},
    'clippy_red_diagnostics': ['libs/os-abi/tests/mutation_kill.rs:21 chunks_exact_to_as_chunks',
                              'libs/os-abi/tests/transport_vectors.rs:14 chunks_exact_to_as_chunks'],
    'original_initial_failure_and_retry_logs_retained': True, 'initial_raw_report_success_false_preserved': True,
    'source_and_lock_after_records_unchanged': True,
    'second_read_only_reviewer': {'agent': '/root/next5_archive/repro_config', 'result': 'consistent partial result; no blocker in evidence',
        'review': 'Actual saved compiler/lint/test logs, commands and immutable source confirm the counts and two diagnostics. No new compiler/test/VM invoked.'},
    'limitations': ['Host ABI codec/test evidence only; no guest ioctl/copyin/copyout/authorization/scheduler validation',
                    'Rust source mutation matrix not executed this phase',
                    'Fixed toolchain/shared dependency cache reused; not all-cache cold or cross-host proof',
                    'Remote Git object absent locally; remote mapping comes from saved publisher API receipt, not new independent network lookup'],
    'archiver_scope': 'Only saved inputs and immutable Git objects read; no live targets/manifests, Cargo/rustc/probe/VM, source/Git writes, root README/lock or other evidence directory edits.'})
(destination / 'archive-controller.py').write_bytes(Path(__file__).read_bytes())
(destination / 'README.md').write_text('''# Merged-main host ABI verification — partial result

The original 13-file frozen package is retained byte for byte in
`original-package/`, including its original README, reports, two tar archives
and SHA256SUMS (`bce5ae22f52526db83dc34d1e80faab31845133367700047f17172a822b2fcc7`).
The outer checksum list also covers these review/publication records.

Tested local merge `b1a15d9afc456346410af658d2164ee5fa085656` and published
remote `74ee9b3d62dc85f272681c5caed3a9c328e38539` share exact tree
`73b34b91910852917d4c6bea020c8b4dc1e62e10`. Local tree, ordered parents,
all 20 source bytes/blob IDs/Git modes and the seed lock were independently
checked through immutable Git objects. Remote binding comes from the unaltered
saved publisher API receipt; this archival pass made no new network lookup.

Rust 39, Python 28, fmt and 12 HOS2 + 1 transport golden checks passed.
**The overall result remains partial.** Initial Clippy/controller exit1
reported its missing fixed-nightly component. Installing that component exited
0 without replacing the toolchain. The identical all-target `-D warnings`
retry exited101 with two `chunks_exact_to_as_chunks` errors in test helpers
`mutation_kill.rs:21` and `transport_vectors.rs:14`. Both red logs, the original
initial `success=false` report and retry receipt remain intact. No source or
lint suppression was applied by the archive/review agents.

The 17 raw archive members were independently read and checked for unique
regular paths, byte counts and SHA. The source archive contains 20 regular
files and eight directories. Git modes are 100644/100755; the original tar
permissions are 0664/0775. File types and execute bits match, while group-write
bits differ. Both mode values are recorded in source-mode-comparison.json;
the original archive was not normalized or rewritten.

These are saved host ABI codec/test results, not a kernel-device, ioctl
memory-safety, authorization, CapSpace or CPU-throttling result. The source
mutation matrix was not run this phase. No new test/probe/build/VM was run
for this review, and no live target/generated manifest or production source
was read. Only this evidence subdirectory was written.
''')
files = sorted(path for path in destination.rglob('*') if path.is_file())
(destination / 'SHA256SUMS').write_text(''.join(f'{sha(path.read_bytes())}  {path.relative_to(destination)}\n' for path in files))
for line in (destination / 'SHA256SUMS').read_text().splitlines():
    expected, name = line.split('  ', 1)
    assert sha((destination / name).read_bytes()) == expected
all_files = [path for path in destination.rglob('*') if path.is_file()]
print(json.dumps({'READY': True, 'files': len(all_files), 'bytes': sum(path.stat().st_size for path in all_files),
    'sum_entries': len(files), 'raw_members': 17, 'source_files': 20, 'source_directories': 8,
    'SHA256SUMS_sha256': sha((destination / 'SHA256SUMS').read_bytes())}, indent=2))
