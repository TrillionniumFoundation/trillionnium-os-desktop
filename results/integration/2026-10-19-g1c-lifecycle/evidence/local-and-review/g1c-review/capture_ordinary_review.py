#!/usr/bin/env python3
"""Read-only review of both local ordinary G1-c runs; never invokes a runner."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tomllib

WORK = Path('/workspace/scratch/499c7902de8e')
ROOT = WORK / 'r12-g1c'
EVIDENCE = WORK / 'r12-evidence'
OUT = EVIDENCE / 'g1c-review/ordinary-10420401-review.json'
HEAD = '104204016dcdea57ab73c091b1edd13008ae9a19'
TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
BEFORE_NAME = 'local-ordinary-candidate'
FINAL_NAME = 'local-ordinary-candidate-final'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
SECURITY = ['HEPTA_EXEC_PREIMAGE_QUERYABI_OK', 'HEPTA_EXEC_EPOCH_DENIED', 'HEPTA_EXEC_CAPSPACE_ROTATED',
            'HEPTA_FORK_INHERITED_FD_DENIED', 'HEPTA_FORK_CAPSPACE_DISTINCT', 'HEPTA_NONROOT_OPEN_DENIED',
            'HEPTA_DUP_SESSION_STABLE']
LIFECYCLE = ['HEPTA_EXEC_EFAULT_SESSION_STABLE', 'HEPTA_EXEC_ENOENT_SESSION_STABLE',
             'HEPTA_THREAD_SESSION_SHARED', 'HEPTA_NONLAST_THREAD_EXIT_SESSION_STABLE']
DISABLED = ['HEPTA_DISABLED_READ_USAGE_OK', 'HEPTA_DISABLED_INSTALL_BUDGET_OK',
            'HEPTA_DISABLED_QUERY_DELIVERY_OK', 'HEPTA_DISABLED_RETIRE_THROUGH_OK']
SUCCESS = 'HEPTA_QUERYABI_OK ops=QueryAbi_only, process_bound_session=yes, denied_invalid=yes'
CANDIDATE = 'HEPTA_QUERYABI_CANDIDATE_OK disabled_operations=4'
BOOT_DONE = 'TRILLIONNIUM_A01_BOOT_OK'
BOOT_MARKERS = ['OSTD initialized. Preparing components.', 'TRILLIONNIUM_A01_INIT_BEGIN',
                'TRILLIONNIUM_A01_CPU_COUNT=1', 'Successfully booted.', BOOT_DONE]
FATAL = ['panicked at', 'An uncaught panic occurred:', 'Uncaught panic:',
         'unknown panic payload! (fatal panic handling error', 'Non-resettable panic!',
         'The panic handler panicked', 'Panicked in `PanicGuard`, aborting the system',
         'Kernel panic', 'HEPTA_QUERYABI_FAIL']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def file_record(path):
    data = path.read_bytes()
    try:
        name = str(path.relative_to(EVIDENCE))
    except ValueError:
        name = str(path)
    return {'path': name, 'bytes': len(data), 'sha256': sha(data)}


def unpack_newc(compressed):
    raw = gzip.decompress(compressed)
    assert len(raw) <= 16 * 1024 * 1024
    position = 0
    entries = []
    names = set()
    while True:
        header = raw[position:position + 110]
        assert len(header) == 110 and header[:6] == b'070701'
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        position += 110
        name_bytes = raw[position:position + fields[11]]
        assert fields[11] > 0 and len(name_bytes) == fields[11] and name_bytes[-1:] == b'\0'
        name = name_bytes[:-1].decode()
        assert '\x00' not in name and not name.startswith('/') and '..' not in name.split('/')
        position = (position + fields[11] + 3) & ~3
        content = raw[position:position + fields[6]]
        assert len(content) == fields[6]
        position = (position + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            assert not content and not any(raw[position:])
            break
        assert name not in names
        names.add(name)
        entries.append((name, fields, content))
    return entries


def verify_snapshot(snapshot):
    assert snapshot['head'] == HEAD and snapshot['tree'] == TREE
    assert snapshot['root'] == str(ROOT) and snapshot['schema'] == 'a06.g1-source-snapshot.v1'
    rows = {}
    for row in git('ls-tree', '-r', '-z', HEAD).split(b'\0'):
        if row:
            metadata, name = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            assert kind == 'blob' and mode in ('100644', '100755', '120000')
            rows[name.decode()] = (mode, oid)
    assert set(rows) == set(snapshot['files']) and len(rows) == 7346
    child = subprocess.Popen(['git', '-C', str(ROOT), 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    cache = {}
    total = 0
    for name, (mode, oid) in rows.items():
        item = snapshot['files'][name]
        assert item['mode'] == mode and item['git_blob'] == oid
        if oid not in cache:
            child.stdin.write((oid + '\n').encode())
            child.stdin.flush()
            output_oid, kind, length = child.stdout.readline().decode().split()
            length = int(length)
            assert output_oid == oid and kind == 'blob'
            digest = hashlib.sha256()
            blob_digest = hashlib.sha1(('blob ' + str(length) + '\0').encode())
            left = length
            while left:
                block = child.stdout.read(min(left, 1024 * 1024))
                assert block
                left -= len(block)
                digest.update(block)
                blob_digest.update(block)
            assert child.stdout.read(1) == b'\n' and blob_digest.hexdigest() == oid
            cache[oid] = (length, digest.hexdigest())
        size, digest = cache[oid]
        assert item['size'] == size and item['sha256'] == digest, name
        total += size
    child.stdin.close()
    assert child.wait() == 0
    return {'verified_path_count': len(rows), 'distinct_verified_blob_count': len(cache),
            'aggregate_path_content_bytes': total, 'exact_path_set_matches_git_tree': True,
            'all_modes_blobs_sizes_and_sha256_match_git_objects': True}


assert git('rev-parse', HEAD + '^{tree}').decode().strip() == TREE
snapshot_bytes = (EVIDENCE / FINAL_NAME / 'source-before.json').read_bytes()
snapshot = json.loads(snapshot_bytes)
source_check = verify_snapshot(snapshot)
snapshot_identities = []
for directory, names in [(BEFORE_NAME, ['source-before.json', 'source-after-boot.json']),
                         (FINAL_NAME, ['source-before.json', 'source-after-boot.json', 'source-after-guest.json'])]:
    for name in names:
        path = EVIDENCE / directory / name
        assert path.read_bytes() == snapshot_bytes
        snapshot_identities.append(file_record(path))
assert not (EVIDENCE / BEFORE_NAME / 'source-after-guest.json').exists()

selected_names = ['support/build/kernel.sh', 'support/build/minimal.mk', 'support/build/minimal/OSDK.toml',
                  'support/build/minimal/Cargo.lock', 'support/build/check-boot.py', 'support/build/record-qemu.py',
                  'support/build/verify-source.py', 'tests/kernel/control/run_queryabi_candidate_guest.py',
                  'tests/kernel/control/queryabi_candidate_guest.c', 'tests/kernel/control/run_queryabi_guest.py',
                  'tests/kernel/control/queryabi_guest.c', 'kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs']
selected_inputs = [{'path': name, **snapshot['files'][name]} for name in selected_names]
for name in ['tests/kernel/control/run_queryabi_candidate_guest.py', 'tests/kernel/control/queryabi_candidate_guest.c']:
    text = git('show', HEAD + ':' + name).decode()
    assert all(marker in text for marker in LIFECYCLE + DISABLED)
control_text = git('show', HEAD + ':kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs').decode()
assert 'Errno::EOPNOTSUPP' in control_text
assert 'errno != EOPNOTSUPP' in git('show', HEAD + ':tests/kernel/control/queryabi_candidate_guest.c').decode()

generated = EVIDENCE / 'local-ordinary-target/osdk/asterinas-run-base/Cargo.lock'
generated_bytes = generated.read_bytes()
assert generated_bytes == git('show', HEAD + ':support/build/minimal/Cargo.lock')
assert len(tomllib.loads(generated_bytes.decode())['package']) == 204
saved_lock = EVIDENCE / 'g1c-review/ordinary-final-generated.Cargo.lock'
if saved_lock.exists():
    assert saved_lock.read_bytes() == generated_bytes
else:
    with saved_lock.open('xb') as destination:
        destination.write(generated_bytes)
run_reviews = []
for directory, expected_success in [(BEFORE_NAME, False), (FINAL_NAME, True)]:
    run = EVIDENCE / directory
    boot = run / 'product-boot'
    label = 'ordinary-candidate-final' if expected_success else 'ordinary-candidate'
    attempt_path = EVIDENCE / 'local-host' / (label + '-attempt.json')
    attempt = json.loads(attempt_path.read_bytes())
    assert attempt['source_head'] == HEAD and attempt['source_tree'] == TREE
    assert type(attempt['exit_code']) is int and attempt['exit_code'] == (0 if expected_success else 1)
    assert file_record(EVIDENCE / 'local-host' / (label + '.log'))['sha256'] == attempt['log_sha256']
    result = json.loads((run / 'result.json').read_bytes())
    assert result['passed'] is expected_success and result['source_head'] == HEAD and result['source_tree'] == TREE
    assert result['source_file_count'] == 7346
    if expected_success:
        assert result['stage'] == 'complete' and result['source_inputs_unchanged'] is True
        assert 'error' not in result and attempt['source_status_after'] == ''
    else:
        assert result['stage'] == 'queryabi_candidate_guest'
        assert result['error'] == 'ValueError: source checkout is dirty or has untracked inputs'
        assert 'source_inputs_unchanged' not in result
    assert all(result[key] is False for key in ['native_grants', 'native_resource_effects', 'hepta_durability',
                                               'smp_qualification', 'production_ready'])
    assert result['compile_exit'] == 0 and (run / 'compile.log').read_bytes() == b''
    assert result['compiler_command'] == ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread', '-static',
                                           str(ROOT / 'tests/kernel/control/queryabi_candidate_guest.c'), '-o', str(run / 'hos2-queryabi')]
    assert result['product_wrapper_exit'] == 0 and result['product_boot_raw_exit'] == 33
    assert result['minimal_generated_lock_sha256'] == sha(generated_bytes)
    assert result['minimal_generated_package_count'] == 204
    assert result['cargo_target_dir'] == str(EVIDENCE / 'local-ordinary-target')
    assert result['product_configuration'] == 'ActionChoice::Run; no --cfg ktest'
    assert all((boot / name).read_bytes() == b'0\n' for name in ['make-exit-code.txt', 'log-exit-code.txt', 'run-exit-code.txt'])
    env_log = (boot / 'environment.log').read_text()
    assert env_log.splitlines().count(HEAD) == 1 and 'CARGO_BUILD_JOBS=2\n' in env_log
    assert 'rustc 1.99.0-nightly (87e5904f5 2026-07-20)' in env_log
    assert 'cargo 1.99.0-nightly (3efb1f477 2026-07-17)' in env_log
    assert '27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3' in env_log
    command = shlex.split((boot / 'command.sh').read_text())
    expected_command = ['make', '-C', str(ROOT / 'kernel/asterinas'), '-f', 'Makefile', '-f',
                        str(ROOT / 'support/build/minimal.mk'), 'run_kernel',
                        'CARGO_OSDK=' + str(WORK / 'r12-cargo/bin/cargo-osdk'),
                        'A01_INITRAMFS=' + str(boot / 'initramfs.cpio.gz'),
                        'A01_QEMU_WRAPPER=' + str(ROOT / 'support/build/record-qemu.py'),
                        'TARGET_ARCH=x86_64', 'SMP=1', 'MEM=512M', 'ENABLE_KVM=0',
                        'BOOT_PROTOCOL=multiboot', 'INITRAMFS=on', 'AUTO_TEST=none']
    assert command == expected_command
    assert '--cfg ktest' not in (boot / 'run_kernel.log').read_text()
    qemu = json.loads((boot / 'qemu.json').read_bytes())
    assert sha((boot / 'qemu.json').read_bytes()) == result['product_qemu_record_sha256']
    assert type(qemu['raw_exit_code']) is int and qemu['raw_exit_code'] == 33 and qemu['timed_out'] is False
    assert qemu['qemu_sha256'] == '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854'
    assert file_record(Path(qemu['argv'][0]))['sha256'] == qemu['qemu_sha256']
    pairs = {}
    flags = []
    i = 1
    allowed_flags = {'-nodefaults', '-no-user-config', '-no-reboot', '-nographic'}
    while i < len(qemu['argv']):
        name = qemu['argv'][i]
        if name in allowed_flags:
            assert name not in flags
            flags.append(name)
            i += 1
        else:
            assert name not in pairs
            pairs[name] = qemu['argv'][i + 1]
            i += 2
    fixed_pairs = {'-machine': 'q35', '-accel': 'tcg', '-cpu': 'max', '-m': '512M', '-smp': '1',
                   '-display': 'none', '-monitor': 'none', '-serial': 'chardev:serial',
                   '-chardev': 'stdio,id=serial,signal=off,logfile=qemu.log',
                   '-device': 'isa-debug-exit,iobase=0xf4,iosize=0x04'}
    assert set(pairs) == set(fixed_pairs) | {'-kernel', '-initrd', '-append', '-bios'}
    assert set(flags) == allowed_flags and all(pairs[name] == value for name, value in fixed_pairs.items())
    assert qemu['shell_command'] == shlex.join(qemu['argv'])
    assert pairs['-initrd'] == str(boot / 'initramfs.cpio.gz')
    assert pairs['-kernel'] == str(EVIDENCE / 'local-ordinary-target/osdk/asterinas/asterinas-osdk-bin.elf')
    assert pairs['-bios'] == '/usr/share/seabios/bios-256k.bin'
    kernel = (run / 'product-kernel.elf').read_bytes()
    original = (boot / 'initramfs.cpio.gz').read_bytes()
    bios = (run / 'bios.bin').read_bytes()
    for option, data in [('-kernel', kernel), ('-initrd', original), ('-bios', bios)]:
        record = qemu['artifacts'][option]
        assert sha(data) == record['sha256'] and len(data) == record['size']
    assert sha(kernel) == result['kernel_elf_sha256']
    assert sha(original) == result['original_initramfs_sha256'] == '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3'
    assert sha(bios) == result['bios_sha256'] == '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735'
    assert kernel[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<HH', kernel, 16) == (2, 3)
    probe = (run / 'hos2-queryabi').read_bytes()
    assert sha(probe) == result['probe_sha256']
    assert probe[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<HH', probe, 16) == (2, 62)
    phoff = struct.unpack_from('<Q', probe, 32)[0]
    phsize, phcount = struct.unpack_from('<HH', probe, 54)
    assert phsize >= 56 and phoff + phsize * phcount <= len(probe)
    assert 3 not in [struct.unpack_from('<I', probe, phoff + phsize * index)[0] for index in range(phcount)]
    injected = (run / 'initramfs.cpio.gz').read_bytes()
    assert sha(injected) == result['injected_initramfs_sha256'] and injected[4:8] == b'\0\0\0\0'
    old_entries, new_entries = unpack_newc(original), unpack_newc(injected)
    assert len(new_entries) == len(old_entries) + 1
    init_count = 0
    boot_command = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    for old, new in zip(old_entries, new_entries[:-1], strict=True):
        name, fields, content = old
        assert new[0] == name
        if name.lstrip('./') == 'init':
            init_count += 1
            assert content.count(boot_command) == 1 and b'set -eu' in content
            expected_content = content.replace(boot_command, b'/bin/hos2-queryabi\n' + boot_command)
            expected_fields = fields.copy()
            expected_fields[6] = len(expected_content)
            assert new == (name, expected_fields, expected_content)
        else:
            assert new == old
    assert init_count == 1
    name, fields, content = new_entries[-1]
    assert name == 'bin/hos2-queryabi' and content == probe
    assert fields == [max(item[1][0] for item in old_entries) + 1, 0o100755, 0, 0, 1, 0, len(probe), 0, 0, 0, 0, len(name.encode()) + 1, 0]
    boot_raw = (boot / 'serial.log').read_bytes()
    assert sha(boot_raw) == qemu['serial_sha256'] and len(boot_raw) == qemu['serial_size']
    boot_text = ANSI.sub('', boot_raw.decode()).replace('\r', '')
    boot_lines = boot_text.splitlines()
    assert all(boot_lines.count(marker) == 1 for marker in BOOT_MARKERS)
    assert not any(marker in boot_text for marker in FATAL) and '[ktest runner]' not in boot_text
    raw = (run / 'serial.log').read_bytes()
    assert sha(raw) == result['raw_serial_sha256'] and len(raw) == result['raw_serial_size']
    text = ANSI.sub('', raw.decode()).replace('\r', '')
    lines = text.splitlines()
    expected_markers = SECURITY + LIFECYCLE + DISABLED + [SUCCESS, CANDIDATE, BOOT_DONE]
    assert len(expected_markers) == len(set(expected_markers)) == 18
    counts = {marker: lines.count(marker) for marker in expected_markers}
    assert set(counts.values()) == {1} and counts == result['marker_counts']
    order = SECURITY + [SUCCESS] + LIFECYCLE + DISABLED + [CANDIDATE, BOOT_DONE]
    positions = [lines.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert not any(marker in text for marker in FATAL) and '[ktest runner]' not in text
    assert type(result['qemu_exit']) is int and result['qemu_exit'] == 33 and result['timed_out'] is False
    assert result['exact_one_markers'] is True and result['ordered_root_completion'] is True and result['no_guest_failure'] is True
    expected_guest_argv = ['/usr/bin/qemu-system-x86_64', '-kernel', str(run / 'product-kernel.elf'),
                           '-initrd', str(run / 'initramfs.cpio.gz'), '-append',
                           'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
                           '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(run / 'bios.bin'),
                           '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot', '-nographic',
                           '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                           '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    assert result['qemu_argv'] == expected_guest_argv
    run_reviews.append({'directory': directory, 'attempt': attempt, 'attempt_identity': file_record(attempt_path),
                        'result': file_record(run / 'result.json'), 'overall_accepted': expected_success,
                        'ordinary_boot': {'raw_qemu_exit': 33, 'wrapper_exit': 0, 'serial': file_record(boot / 'serial.log'),
                                          'qemu_record': file_record(boot / 'qemu.json'), 'boot_markers_exact_once': BOOT_MARKERS},
                        'queryabi_guest': {'raw_qemu_exit': 33, 'timed_out': False, 'serial': file_record(run / 'serial.log'),
                                           'marker_counts': counts, 'independently_checked_order': order},
                        'artifacts': [file_record(run / name) for name in ['product-kernel.elf', 'bios.bin', 'hos2-queryabi', 'initramfs.cpio.gz']],
                        'original_initramfs': file_record(boot / 'initramfs.cpio.gz'),
                        'initramfs_change': {'original_entries': len(old_entries), 'injected_entries': len(new_entries),
                                             'only_init_command_and_one_exact_static_probe_added': True},
                        'source_snapshot_qualification': 'all three complete snapshots verified' if expected_success else 'after-guest snapshot rejected; original failure retained',
                        'retained_files': [file_record(path) for path in sorted(run.rglob('*')) if path.is_file()]})

observation_path = EVIDENCE / 'local-host/ordinary-untracked-manifest-observation.json'
recovery_path = EVIDENCE / 'local-host/ordinary-residue-recovery.json'
observation = json.loads(observation_path.read_bytes())
recovery = json.loads(recovery_path.read_bytes())
residue_path = EVIDENCE / 'local-host/ordinary-residue/OSDK.toml'
residue = residue_path.read_bytes()
assert sha(residue) == observation['sha256'] == recovery['sha256']
assert len(residue) == observation['bytes'] and residue.decode() == observation['content']
assert residue == git('show', HEAD + ':support/build/minimal/OSDK.toml')
assert observation['git_status'] == '?? kernel/asterinas/kernel/OSDK.toml\n'
assert recovery['source_clean'] is True and 'not established' in recovery['causal_claim']
assert recovery['at'] <= run_reviews[1]['attempt']['started_at']

review = {
    'schema_version': 1, 'kind': 'independent_two_attempt_ordinary_g1c_review',
    'reviewer': '/root/g1c_review', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_head': HEAD, 'source_tree': TREE,
    'decision': 'Accept the fresh final local ordinary build/boot and QueryAbi guest run at 10420401 after complete source snapshot verification. Keep the preceding ordinary attempt failed at its after-guest source gate. Residue provenance is unresolved; no product bug-fix claim is made.',
    'blocking_findings_for_final_run': [],
    'complete_source_verification': source_check,
    'five_available_snapshot_identities': snapshot_identities,
    'five_available_snapshots_byte_identical': True,
    'first_after_guest_snapshot_missing_due_to_failed_gate': True,
    'reviewed_execution_inputs_at_git_head': selected_inputs,
    'ordinary_generated_lock': {**file_record(saved_lock), 'package_count': 204, 'matches_fixed_source_bytes': True},
    'runs': run_reviews,
    'residue_history': {'observation': observation, 'recovery': recovery,
                        'original_observation_identity': file_record(observation_path),
                        'original_recovery_identity': file_record(recovery_path),
                        'preserved_manifest': file_record(residue_path),
                        'independent_scope': 'Preserved bytes equal the known temporary minimal manifest. Recorded mtime/ctime/status do not identify the creation/restoration mechanism.'},
    'scope_limits': ['Only local ordinary N0 single-vCPU TCG profile accepted here; no hosted A06 claim',
                     'QueryAbi is the only advertised operation; four valid resource-operation frames were rejected with EOPNOTSUPP',
                     'Lifecycle guest covers pre-boundary EFAULT/ENOENT, thread sharing, non-last exit and original successful exec/fork semantics',
                     'No post-boundary fatal exec injection or final-exit self-ioctl qualification',
                     'No immutable static image authentication, native grant, resource effects, Hepta durability, general SMP, device or mobile qualification',
                     'SCM/RLIMIT/Linux full32 and CPU runs remain separate evidence'],
    'activities': {'product_source_writes': 0, 'runners_or_probes_executed': 0, 'builds_or_compiles': 0,
                   'tool_installations': 0, 'remote_reads': 0, 'remote_writes': 0,
                   'git_blob_reads': source_check['distinct_verified_blob_count'],
                   'in_memory_newc_parsing_only': True},
}
OUT.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({**file_record(OUT), 'verified_source_paths': 7346, 'available_identical_snapshots': 5,
                  'final_exact_markers': 18, 'first_attempt_kept_failed': True, 'final_accepted': True}))
