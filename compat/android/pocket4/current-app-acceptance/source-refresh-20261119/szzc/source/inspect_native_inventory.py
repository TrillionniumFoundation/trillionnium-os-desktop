#!/usr/bin/env python3
"""Read exact publisher APK native headers after the real inventory failure."""
import datetime, hashlib, json, os, resource, stat, struct, time, zipfile
from pathlib import Path
ROOT = Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
APK = ROOT / 'download/com.szzc.publisher-current.apk'
APK_SHA = '1461b66c3dc3497989eb4a71361b56584dca1caa6b8120ebc5c4c1f240782c03'
FAILURE_SHA = '39b9ef57cb36527de9caf1b4002f1776ad7cdd0bf5a4628fa5978b2b9dd30b82'
ABI = {'armeabi-v7a': (1, 40), 'arm64-v8a': (2, 183), 'x86': (1, 3), 'x86_64': (2, 62), 'riscv64': (2, 243)}
assert os.getuid() == 1000 and os.sched_getaffinity(0) == {31}
resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.umask(0o077)
started = time.monotonic()


def f9(st):
    return [str(x) for x in (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
                            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)]


def full_sha(fd, size):
    digest = hashlib.sha256()
    for off in range(0, size, 1024 * 1024):
        assert time.monotonic() - started < 90
        block = os.pread(fd, min(1024 * 1024, size - off), off)
        assert len(block) == min(1024 * 1024, size - off)
        digest.update(block)
    return digest.hexdigest()


held = []
try:
    for path, size, sha in [(ROOT / 'qualification/RESULT.json', 13681, FAILURE_SHA), (APK, 220498418, APK_SHA)]:
        assert path.resolve() == path
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        st = os.fstat(fd)
        held.append((path, fd, st, sha))
        assert stat.S_ISREG(st.st_mode) and st.st_uid == 1000 and st.st_nlink == 1 and st.st_size == size
        assert f9(path.lstat()) == f9(st) and full_sha(fd, size) == sha
    apkfd = held[1][1]
    rows = []
    expanded = 0
    with os.fdopen(os.dup(apkfd), 'rb') as stream, zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        assert len(infos) <= 100000 and len(infos) == len({x.filename for x in infos})
        for item in infos:
            if item.is_dir() or not item.filename.startswith('lib/'):
                continue
            assert time.monotonic() - started < 90
            expanded += item.file_size
            assert expanded <= 512 * 1024 * 1024
            digest = hashlib.sha256()
            size = 0
            header = b''
            with archive.open(item) as source:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
                    if len(header) < 64:
                        header = (header + block)[:64]
            assert size == item.file_size
            parts = item.filename.split('/')
            expected = ABI.get(parts[1]) if len(parts) == 3 else None
            elf = len(header) == 64 and header[:4] == b'\x7fELF'
            machine = struct.unpack_from('<H', header, 18)[0] if elf and header[5] == 1 else None
            cls = header[4] if elf else None
            matches = elf and expected is not None and (cls, machine) == expected
            rows.append({'name': item.filename, 'bytes': size, 'sha256': digest.hexdigest(),
                'crc32': f'{item.CRC:08x}', 'complete_EOF_CRC_verified': True,
                'header_hex': header.hex(), 'directory_ABI': parts[1] if len(parts) > 1 else None,
                'expected_class_machine': expected, 'actual_class': cls, 'actual_machine': machine,
                'actual_ABIs_matching_header': [key for key, value in ABI.items() if value == (cls, machine)],
                'directory_ABI_matches_ELF': matches, 'native_compatibility_qualified': False,
                'APK_or_library_executed': False})
    for path, fd, st, sha in held:
        assert f9(os.fstat(fd)) == f9(path.lstat()) == f9(st) and full_sha(fd, st.st_size) == sha
    anomalies = [row for row in rows if not row['directory_ABI_matches_ELF']]
    result = {'schema': 'pocket4-szzc-original-native-inventory-diagnostic-v1',
        'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'APK': {'path': str(APK), 'bytes': 220498418, 'sha256': APK_SHA, 'identity': f9(held[1][2])},
        'failed_qualification': {'path': str(held[0][0]), 'bytes': 13681, 'sha256': FAILURE_SHA},
        'native_members': rows, 'directory_ABIs': sorted({r['directory_ABI'] for r in rows}),
        'mismatches': anomalies, 'native_member_count': len(rows), 'mismatch_count': len(anomalies),
        'all_input_bookends_unchanged': True, 'generic_validator_changed': False,
        'source_identity_verified': False, 'signature_verified': False, 'SDK_commands': 0,
        'Android_actions': 0, 'user_data_reads': 0, 'APK_or_library_executions': 0,
        'installed': False, 'native_compatibility_qualified': False, 'runtime_qualified': False,
        'business_qualified': False, 'production_ready': False}
    body = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    assert len(body) <= 1024 * 1024
    out = ROOT / 'NATIVE-INVENTORY-DIAGNOSTIC.json'
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(body)
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps({'result': {'path': str(out), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()},
                      'native_member_count': len(rows), 'mismatch_count': len(anomalies), 'mismatches': anomalies}, sort_keys=True), flush=True)
finally:
    for path, fd, st, sha in held:
        os.close(fd)
