#!/usr/bin/env python3
"""Verify downloaded immutable workflow artifacts without executing ARM programs."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tarfile
from datetime import datetime, timezone
import zipfile

ROOT = Path('/workspace/scratch/98f315e377b2')
OUT = ROOT / 'next-tools/original-arm-r5'
RAW = OUT / 'extracted'
ELF_ZIP = Path('/dev/shm/trill-r5-arm-artifacts/hepta-original-agentd-elf-39037037916-1.zip')
DESKTOP = '1974d9a94037440da358253e1f449b395daa4b64'
LOCAL = '35f379101c0863027e971ccb91faf8da71cf929c'
HEPTA = 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
TREE = '48433c4f1e55de53e8c298193765949996eb18a0'

def hash_stream(stream):
    h = hashlib.sha256()
    n = 0
    for b in iter(lambda: stream.read(1024 * 1024), b''):
        n += len(b)
        h.update(b)
    return {'bytes': n, 'sha256': h.hexdigest()}

def hashed(path):
    with path.open('rb') as f:
        return hash_stream(f)

def git_blob(repo, rev, path):
    return subprocess.check_output(['git', '-C', str(ROOT / repo), 'show', rev + ':' + path])

record = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
          'verification_kind': 'downloaded_artifact_bytes_and_receipt_cross_check_not_new_runtime',
          'workflow_run': 39037037916, 'job': 117408854785,
          'desktop_commit': DESKTOP, 'desktop_local_equivalent': LOCAL,
          'desktop_tree': TREE, 'hepta_commit': HEPTA,
          'platform': 'aarch64-unknown-linux-gnu', 'artifacts': {}, 'checks': []}
for kind, path, expected_size, expected_hash in [
    ('evidence_zip', OUT / 'hepta-original-agentd-evidence-39037037916-1.zip', 456519,
     '7608b75c69fed1ff020fa3dff06f27650c316a9cd492779fb7da592991187a03'),
    ('elf_zip', ELF_ZIP, 80692154,
     '85214ef3134e50967d9737f67c2f1bfc9d1f44feee9942b836be01356989b8df')]:
    actual = hashed(path)
    assert actual == {'bytes': expected_size, 'sha256': expected_hash}, (kind, actual)
    record['artifacts'][kind] = actual

report_bytes = (RAW / 'report.json').read_bytes()
report = json.loads(report_bytes)
assert report['status'] == report['live_agentd_acceptance'] == 'passed'
assert report['runtime_probe_attempted'] and report['large_build_attempted']
assert all(s['status'] == 'passed' for s in report['steps'])
assert report['blockers'] == [] and (RAW / 'gate-exit-code.txt').read_bytes() == b'0\n'
assert report['upstream']['commit'] == HEPTA and report['upstream']['clean_checkout']
assert not any(report['profile'][key] for key in ['agentd_default_features', 'supervisor_production_authority',
    'objective_issuer', 'model_turn', 'device_effect_provider'])
accept = report['runtime_records'][-1]
assert accept['event'] == 'acceptance_pass'
assert accept['checks'] == ['original_starting', 'original_running', 'bounded_capabilities_events',
    'missing_run_read', 'same_process_draining', 'original_restart', 'old_spawn_rejected', 'controlled_stop']
assert not any(accept[key] for key in ['device_effect', 'model_turn', 'objective_submission'])
assert report['runtime_records'] == [json.loads(s) for s in (RAW / 'work/original_agentd_process_probe.log').read_text().splitlines()]
assert (RAW / 'logs/gate.log').read_bytes() == report_bytes
assert (RAW / 'work/probe/src/main.rs').read_bytes() == git_blob('next-native-ci', LOCAL, 'tests/integration/hepta/original_agentd_probe.rs')
assert report['probe_source_sha256'] == hashlib.sha256((RAW / 'work/probe/src/main.rs').read_bytes()).hexdigest()
assert report['probe_resolved_lock_sha256'] == hashed(RAW / 'work/probe/Cargo.lock')['sha256']
for path, expected in report['observer_source_sha256'].items():
    assert hashlib.sha256(git_blob('next-native-ci', LOCAL, path)).hexdigest() == expected, path
for line in (RAW / 'identity/desktop-inputs.sha256').read_text().splitlines():
    expected, path = line.split('  ', 1)
    assert hashlib.sha256(git_blob('next-native-ci', LOCAL, path)).hexdigest() == expected, path
for archive_name, source_path in [
    ('hepta-original-Cargo.lock', 'codex-rs/Cargo.lock'),
    ('hepta-original-Cargo.toml', 'codex-rs/Cargo.toml'),
    ('hepta-original-rust-toolchain.toml', 'codex-rs/rust-toolchain.toml')]:
    assert (RAW / 'locks' / archive_name).read_bytes() == git_blob('next-hepta-source', HEPTA, source_path)
final = json.loads((RAW / 'identity/final-checkouts.json').read_bytes())
for name, rev, tree in [('desktop', DESKTOP, TREE), ('hepta', HEPTA, '15c9d6ea07bf3832de82825a6cc1e8c958dd3d45')]:
    state = final['checkouts'][name]
    assert state['identity'] == {'exit_code': 0, 'stdout': rev + '\n' + tree + '\n', 'stderr': ''}
    assert state['status'] == {'exit_code': 0, 'stdout': '', 'stderr': ''}
record['checks'].append('runtime_receipt_log_steps_source_locks_final_clean_identity_match')

small_out = OUT / 'elf-manifest'
small_out.mkdir(exist_ok=True)
with zipfile.ZipFile(ELF_ZIP) as z:
    assert set(z.namelist()) == {'SHA256SUMS', 'archive.sha256', 'binary-manifest.json',
                                'hepta-original-agentd-aarch64-linux.tar.gz'}
    small = {name: z.read(name) for name in ['SHA256SUMS', 'archive.sha256', 'binary-manifest.json']}
    for name, data in small.items():
        (small_out / name).write_bytes(data)
    manifest = json.loads(small['binary-manifest.json'])
    assert manifest['desktop_commit'] == DESKTOP and manifest['hepta_commit'] == HEPTA
    assert manifest['report_sha256'] == hashlib.sha256(report_bytes).hexdigest()
    assert manifest['qualification'] == 'original_agentd_readonly_acceptance_passed'
    assert manifest['platform'] == 'aarch64-unknown-linux-gnu'
    expected_tar, tar_name = small['archive.sha256'].decode().strip().split('  ', 1)
    with z.open(tar_name) as f:
        actual_tar = hash_stream(f)
    assert actual_tar['sha256'] == expected_tar
    record['artifacts']['elf_tar_gz'] = actual_tar
    expected = {v['filename']: dict(v, role=k) for k, v in manifest['binaries'].items()}
    actual_binaries = {}
    members = []
    with z.open(tar_name) as f, tarfile.open(fileobj=f, mode='r|gz') as tar:
        for member in tar:
            assert member.isfile() and '/' not in member.name and member.name not in members
            members.append(member.name)
            stream = tar.extractfile(member)
            if member.name in expected:
                header = stream.read(64)
                h = hashlib.sha256(header)
                n = len(header)
                for b in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(b)
                    n += len(b)
                value = expected[member.name]
                assert header[:6] == b'\x7fELF\x02\x01' and struct.unpack('<H', header[18:20])[0] == 183
                assert n == member.size == value['bytes']
                assert h.hexdigest() == value['sha256'] == report['binary_sha256'][value['role']]
                assert member.mode & 0o111
                actual_binaries[value['role']] = {'filename': member.name, 'bytes': n, 'sha256': h.hexdigest(),
                    'elf_class': 64, 'little_endian': True, 'e_machine': 183, 'architecture': 'AArch64',
                    'tar_mode': oct(member.mode), 'elf_header_hex': header.hex()}
            else:
                assert member.name in {'report.json', 'binary-manifest.json', 'SHA256SUMS'}
                data = stream.read()
                assert data == (report_bytes if member.name == 'report.json' else small[member.name])
    assert set(members) == set(expected) | {'report.json', 'binary-manifest.json', 'SHA256SUMS'}
    assert set(actual_binaries) == {'agentd', 'probe', 'observer'}
    record['binaries'] = actual_binaries
    record['checks'].append('three_streamed_real_ARM64_executable_bytes_match_manifest_and_executed_report')
    record['checks'].append('nested_archive_manifest_report_and_SHA256SUMS_byte_identity')
record['runtime_checks'] = accept['checks']
record['passed'] = True
record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
(OUT / 'artifact-verification.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
