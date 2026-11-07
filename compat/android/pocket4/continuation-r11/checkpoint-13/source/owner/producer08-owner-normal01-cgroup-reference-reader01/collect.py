"""Six fixed source files only. No search, child, write, namespace or runtime."""
import base64
import gzip
import hashlib
import json
import os
import stat
import traceback

AOSP = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source'
FILES = (
    ('actual-supervisor-asset', '/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01/candidate/runtime/droidloom-supervisor/assets/development-cgroups.json', 4096,
     876, 'f03de3fc015e9fce4630ccdeb3db7f300d7c1d122f30a7fb54654a642690f3c7'),
    ('aosp-cgroup-setup-reference', AOSP + '/system/core/libprocessgroup/setup/cgroup_map_write.cpp', 262144, None, None),
    ('aosp-cgroup-util-reference', AOSP + '/system/core/libprocessgroup/util.cpp', 262144, None, None),
    ('aosp-processgroup-reference', AOSP + '/system/core/libprocessgroup/processgroup.cpp', 262144, None, None),
    ('aosp-init-service-reference', AOSP + '/system/core/init/service.cpp', 262144, None, None),
    ('aosp-kernel-logger-reference', AOSP + '/system/libbase/logging.cpp', 262144, None, None),
)
MAX_TOTAL = 1024 * 1024


def sha(body):
    return hashlib.sha256(body).hexdigest()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def collect(path, limit, expected_bytes, expected_sha):
    parts = path.split('/')
    need(parts[0] == '' and all(x not in ('', '.', '..') for x in parts[1:]), 'fixed path is not normalized')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    file = None
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.close(parent)
            parent = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(file)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'fixed source type/size rejected')
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(file, min(32768, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        need(len(raw) == before.st_size and identity(before) == identity(os.fstat(file))
             == identity(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)), 'fixed source changed')
        digest = sha(raw)
        if expected_sha is not None:
            need(len(raw) == expected_bytes and digest == expected_sha, 'known source asset pin differs')
        return {'bytes': len(raw), 'sha256': digest, 'identity': identity(before),
                'utf8': raw.decode('utf-8', 'strict'), 'external_pin_checked': expected_sha is not None,
                'binary_source_binding_proved': False}
    finally:
        if file is not None:
            os.close(file)
        os.close(parent)


def main():
    result = {'schema': 1, 'kind': 'owner08-fixed-cgroup-source-reference-read01',
        'uid': os.getuid(), 'read_only': True, 'runtime_executed': False, 'qualification': False,
        'scope': 'SIX_FIXED_SOURCE_FILES; AOSP_REFERENCE_NOT_PROOF_OF_ACTUAL_INIT_DSO_BUILD',
        'files': [], 'errors': [], 'total_bytes': 0, 'all_files_read': False}
    try:
        need(os.getuid() == os.geteuid() == 1000, 'ordinary device reader identity differs')
        for label, path, limit, expected_bytes, expected_sha in FILES:
            record = {'label': label, 'path': path}
            try:
                item = collect(path, min(limit, MAX_TOTAL - result['total_bytes']), expected_bytes, expected_sha)
                record.update(item)
                result['total_bytes'] += item['bytes']
                need(result['total_bytes'] <= MAX_TOTAL, 'aggregate source limit exceeded')
            except BaseException as error:
                record['error'] = repr(error)
                result['errors'].append({'label': label, 'error': repr(error)})
            result['files'].append(record)
        result['all_files_read'] = len(result['files']) == len(FILES) and not result['errors']
    except BaseException as error:
        result['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(raw) <= 2 * 1024 * 1024, 'source envelope too large')
    packed = gzip.compress(raw, mtime=0)
    print(json.dumps({'all_files_read': result['all_files_read'], 'qualification': False,
        'bytes': len(raw), 'sha256': sha(raw), 'gzip_bytes': len(packed), 'gzip_sha256': sha(packed),
        'gzip_base64': base64.b64encode(packed).decode('ascii')}, sort_keys=True))
    return 0 if result['all_files_read'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
