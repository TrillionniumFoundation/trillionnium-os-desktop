#!/usr/bin/env python3
"""Fixed-path, read-only export of this one successful readonly Bilibili admission attempt."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import types

ROOT = Path('/home/alex/work/pocket4-bilibili-readonly-r3-01')
OUT = Path('/home/alex/work/pocket4-bilibili-readonly-r3-export-01')
EXPECTED_RESULT = 'cae3833ffb97c6879c523a8396b08cf1a88bfd145d17f1eae95e740aab766808'
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
EPOCH_FILE = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SOURCE_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
STEP = 'flow/steps/readonly-admission-01/'
FILES = ['result.json', 'flow/scope.json'] + [
    'evidence/' + phase + suffix
    for phase in ('01-init', '02-admission')
    for suffix in ('.intent.json', '.result.json', '.stdout', '.stderr')
] + [STEP + name for name in (
    'intent.json', 'result.json', 'held-main-binding.json',
    'command-001.intent.json', 'command-001.result.json', 'command-001.stdout', 'command-001.stderr',
    'transport-001.intent.json', 'transport-001.command-result.json',
    'transport-001.verified-result.json', 'transport-001.failure.json')]


def read(path, maximum=131072):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= maximum
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        after = os.fstat(fd)
        assert len(data) == before.st_size and all(getattr(before, k) == getattr(after, k)
            for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
        return bytes(data)
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main_guard():
    epoch_raw = read(EPOCH_FILE)
    assert sha(epoch_raw) == EPOCH_SOURCE_SHA
    epoch = types.ModuleType('readonly_after_bili_epoch')
    epoch.__file__ = str(EPOCH_FILE)
    exec(compile(epoch_raw, str(EPOCH_FILE), 'exec'), epoch.__dict__)
    raw = read(ACTIVATION)
    assert sha(raw) == ACTIVATION_SHA
    activation = json.loads(raw)
    assert activation['framework_epoch']['sha256'] == EPOCH_SHA
    epoch.require_unchanged(activation['framework_epoch'])
    for key in ('daemon_process', 'launcher_process', 'presenter_process'):
        expected = activation[key]
        assert epoch.process_identity(expected['host_pid']) == expected
    assert sha(read('/etc/droidloom/cell.json')) == 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
    limits = {key: (Path('/sys/fs/cgroup/system.slice/droidloomd.service') / key).read_text().strip()
              for key in activation['limits']}
    assert limits == activation['limits']
    epoch.require_unchanged(activation['framework_epoch'])
    return {'Main_epoch_sha256': EPOCH_SHA, 'three_host_processes_unchanged': True,
            'config_and_limits_unchanged': True, 'activation_body_exported': False}


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


assert os.geteuid() == 0
os.umask(0o022)
before = main_guard()
records, absent, total = [], [], 0
for name in FILES:
    try:
        raw = read(ROOT / name)
    except FileNotFoundError:
        absent.append(name)
        continue
    total += len(raw)
    assert total <= 1024 * 1024
    records.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw),
                    'data_base64': base64.b64encode(raw).decode()})
by_name = {row['path']: row for row in records}
assert by_name['result.json']['sha256'] == EXPECTED_RESULT
original = json.loads(base64.b64decode(by_name['result.json']['data_base64']))
assert original['success'] is True
after = main_guard()
bundle = {'schema': 1, 'scope': 'fixed allowlist for the original successful readonly admission; no activation or unrelated logs',
          'original_result_sha256': EXPECTED_RESULT, 'original_success': True,
          'Main_before': before, 'Main_after': after, 'files': records, 'absent': absent}
OUT.mkdir(mode=0o755)
raw = (json.dumps(bundle, sort_keys=True, indent=2) + '\n').encode()
archive = gzip.compress(raw, mtime=0)
archive_pin = write_new(OUT / 'evidence.json.gz', archive)
phases = {}
for phase in ('01-init', '02-admission'):
    row = by_name.get('evidence/' + phase + '.result.json')
    if row:
        value = json.loads(base64.b64decode(row['data_base64']))
        phases[phase] = {k: value.get(k) for k in ('returncode', 'spawned', 'joined', 'timed_out', 'primary_error', 'secondary_errors')}
admission = by_name.get(STEP + 'result.json')
admission_value = json.loads(base64.b64decode(admission['data_base64'])) if admission else None
report = {'schema': 1, 'collector_success': True, 'original_success': True,
          'original_result_sha256': EXPECTED_RESULT, 'archive': archive_pin,
          'file_count': len(records), 'payload_bytes': total, 'Main_after': after,
          'phases': phases, 'admission_result': admission_value, 'absent': absent,
          'UI_audio_launch_close': False}
report_pin = write_new(OUT / 'report.json', (json.dumps(report, sort_keys=True, indent=2) + '\n').encode())
directory = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
try:
    os.fsync(directory)
finally:
    os.close(directory)
print(json.dumps({'collector_success': True, 'original_success': True, 'report': report_pin,
                  'archive': archive_pin, 'phases': phases, 'admission_result': admission_value,
                  'Main_preserved': True}), flush=True)
