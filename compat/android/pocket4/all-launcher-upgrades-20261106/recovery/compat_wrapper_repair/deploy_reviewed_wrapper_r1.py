#!/usr/bin/env python3
"""Deploy one actually host-tested compatibility wrapper; no runtime action.

The old running Python launcher is not modified or signalled. A later explicit
native lifecycle operation must activate the repaired source and qualify its
new processes. Old bytes, exact metadata, source closure and real test receipts
are retained before the single atomic replacement. There is no automatic retry.
"""
import sys
sys.dont_write_bytecode = True
import errno
import fcntl
import hashlib
import json
import os
import stat
import time

ROOT = '/home/alex/work/pocket4-compat-wrapper-deployment-20261106-r1'
TEST_ROOT = '/home/alex/work/pocket4-compat-wrapper-host-controls-20261106-r2/revision-3'
TARGET = '/usr/local/libexec/droidloom-compat/unshare'
LOCK = '/run/lock/android-digitalis-actions.lock'
OLD_SHA = 'fe3a685034ed0dc948597436965dfd35ea183fc2b0519d9b0c5730c79d7c060b'
NEW_SHA = 'df2365c026cc578048ce22ebd1b22bfefc25ccc144146683d845ec828c61bf1f'
NATIVE_SHA = '41c65e55107cbbb1a1f6994784a938dd7dbbe255d1fea6b7a58ec96eabe382ef'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')
OLD_STAT = {'st_dev': 66306, 'st_ino': 6422533, 'st_mode': 33261, 'st_uid': 0,
            'st_gid': 0, 'st_nlink': 1, 'st_size': 560,
            'st_mtime_ns': 1791345260151856165, 'st_ctime_ns': 1791345260153600777}
SOURCES = {
    'unshare_wrapper.py': (6290, NEW_SHA),
    'pidns_fixture.py': (1013, 'da61ecac210799f4626cdc7afa83476049374f4a36e9b87ba0e6a92e664016d1'),
    'test_host_lifecycle.py': (16463, '86195ddeeed6d1a6f2ee20913e180c6259b6ff1bd36121abfd3369345a644649'),
}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def metadata(fd):
    s = os.fstat(fd)
    return {k: getattr(s, k) for k in FIELDS}


class Descriptors:
    def __init__(self):
        self.live = set()
        self.acquired = self.closed = 0

    def own(self, fd):
        need(fd >= 3 and fd not in self.live, 'OWNED_FD_REQUIRED')
        self.live.add(fd)
        self.acquired += 1
        return fd

    def close(self, fd):
        need(fd in self.live, 'UNOWNED_CLOSE')
        os.close(fd)
        self.live.remove(fd)
        self.closed += 1

    def close_all(self):
        failures = []
        for fd in list(self.live):
            try:
                self.close(fd)
            except BaseException as error:
                failures.append(type(error).__name__)
        return {'acquired': self.acquired, 'closed': self.closed,
                'remaining': len(self.live), 'errors': failures}


def opened(pool, path, flags=os.O_RDONLY):
    need(path.startswith('/') and all(x not in ('', '.', '..') for x in path[1:].split('/')),
         'CANONICAL_PATH_REQUIRED')
    parents = []
    try:
        d = pool.own(os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        parents.append(d)
        parts = path[1:].split('/')
        for name in parts[:-1]:
            d = pool.own(os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d))
            parents.append(d)
        return pool.own(os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d))
    finally:
        for d in reversed(parents):
            pool.close(d)


def read_pinned(pool, path, count, digest):
    fd = opened(pool, path)
    before = metadata(fd)
    need(stat.S_ISREG(before['st_mode']) and before['st_nlink'] == 1 and
         before['st_size'] == count and count <= 262144, 'REGULAR_PINNED_FILE_REQUIRED')
    raw = bytearray()
    while len(raw) <= count:
        block = os.read(fd, min(65536, count + 1 - len(raw)))
        if not block:
            break
        raw.extend(block)
    need(len(raw) == count and sha(raw) == digest and metadata(fd) == before, 'PINNED_BYTES_CHANGED')
    again = opened(pool, path)
    try:
        need(metadata(again) == before, 'PINNED_PATH_REPLACED')
    finally:
        pool.close(again)
    return fd, bytes(raw), {'path': path, 'bytes': count, 'sha256': digest, 'stat': before}


def recheck(pool, fd, record):
    need(metadata(fd) == record['stat'], 'HELD_FILE_CHANGED')
    other = opened(pool, record['path'])
    try:
        need(metadata(other) == record['stat'], 'FILE_PATH_CHANGED')
    finally:
        pool.close(other)


def write_file(pool, directory, name, raw, mode=0o400):
    need('/' not in name and name not in ('.', '..'), 'CLOSED_OUTPUT_NAME')
    fd = pool.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                          mode, dir_fd=directory))
    try:
        data = memoryview(raw)
        while data:
            n = os.write(fd, data)
            need(n > 0, 'WRITE_PROGRESS')
            data = data[n:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        pool.close(fd)
    os.fsync(directory)


def run(source):
    need(os.getuid() == os.geteuid() == 0 and sys.platform == 'linux', 'ROOT_LINUX_REQUIRED')
    need(type(source) is str and 1000 < len(source.encode()) <= 65536, 'SELF_SOURCE_REQUIRED')
    pool = Descriptors()
    result = {'schema': 'pocket4-compat-unshare-deployment-result-v1', 'ok': False,
              'replacement_attempted': False, 'outcome_unknown': False, 'automatic_retry': False,
              'new_source_runtime_activated': False, 'Android_commands': 0,
              'namespace_entries': 0, 'UI_actions': 0, 'installs': 0, 'restarts': 0,
              'existing_process_signals': 0, 'production_ready': False, 'errors': []}
    output = None
    try:
        unused, predecessor_raw, unused_record = read_pinned(pool,
            '/home/alex/work/pocket4-cell-successor-20261106-r1/predecessor.private.json',
            110738, '6b781af9d0d037e14d7f4b3174937f3a101ab4cf313b7c5c34fec1c13df9dec3')
        original_lock = json.loads(predecessor_raw)['action_lock_identity']
        lock = opened(pool, LOCK, os.O_RDWR)
        lock_meta = metadata(lock)
        need(stat.S_ISREG(lock_meta['st_mode']) and lock_meta['st_uid'] == 0 and lock_meta['st_nlink'] == 1,
             'EXISTING_ACTION_LOCK_REQUIRED')
        need({key: lock_meta[key] for key in ('st_dev', 'st_ino')} == original_lock,
             'ORIGINAL_ACTION_LOCK_INODE_REQUIRED')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_pin = {'path': LOCK, 'stat': lock_meta}
        recheck(pool, lock, lock_pin)
        manifest_pin = {'path': TEST_ROOT + '/source/SOURCE_PINS.json', 'bytes': 402,
                        'sha256': '31b037052fee007650c92cd8706f0e4405eb67fe224813c153a8e4973639747c'}
        unused, manifest_raw, unused_record = read_pinned(pool, **{'path': manifest_pin['path'],
            'count': manifest_pin['bytes'], 'digest': manifest_pin['sha256']})
        manifest = json.loads(manifest_raw)
        need(manifest == {'schema': 'pocket4-compat-wrapper-repair-source-v1',
             'files': {name: {'bytes': row[0], 'sha256': row[1]} for name, row in SOURCES.items()}},
             'EXACT_TESTED_SOURCE_MANIFEST')
        source_rows = {}
        for name, (count, digest) in SOURCES.items():
            fd, raw, record = read_pinned(pool, TEST_ROOT + '/source/' + name, count, digest)
            source_rows[name] = (fd, raw, record)
            compile(raw, record['path'], 'exec')
        test_pin = {'path': TEST_ROOT + '/host-controls/result.json', 'bytes': 9109,
                    'sha256': '069996c902d66cbed7de4a5c96881bbaa69e95247627344d7e16a66de40c5fa8'}
        unused, test_raw, unused_record = read_pinned(pool, test_pin['path'], test_pin['bytes'], test_pin['sha256'])
        test = json.loads(test_raw)
        need(test['schema'] == 'pocket4-compat-wrapper-real-host-controls-v1' and test['ok'] is True and
             test['errors'] == [] and test['candidate']['sha256'] == NEW_SHA and
             test['test_revision'] == 'r3-inline-pinned-fixture' and
             test['fixture_transport'] == 'pinned_utf8_source_via_python_c' and
             test['fixture_sha256'] == SOURCES['pidns_fixture.py'][1] and
             test['FD_count_before'] == test['FD_count_after'] == 5 and
             len(test['cases']) == 4 and all(row['passed'] is True for row in test['cases']), 'ACTUAL_HOST_CONTROLS_REQUIRED')
        for row in test['cases'][-2:]:
            need(row['all_four_original_test_pidfds_dead'] is True and
                 row['unrelated_same_process_group_sentinel_unchanged'] is True and
                 row['pidfds'] == {'acquired': 5, 'closed': 5} and row['cleanup_error'] is None,
                 'ACTUAL_ISOLATED_DEATH_CHAIN_REQUIRED')
        terminal_pin = {'path': TEST_ROOT + '/completion-evidence/r3-stage.terminal.raw.json', 'bytes': 733,
                        'sha256': 'c2a1e69a811960ea3107823a9edefe20f4d861d2e01689253099f44fce7619fb'}
        unused, terminal_raw, unused_record = read_pinned(pool, terminal_pin['path'], terminal_pin['bytes'], terminal_pin['sha256'])
        terminal = json.loads(terminal_raw)
        need(terminal['job_id'] == '1a1b0d8d8e9-fc05-734d' and terminal['state'] == 'succeeded' and
             terminal['exit_code'] == 0 and not terminal['timed_out'] and
             all(terminal[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed')),
             'DURABLE_REAL_HOST_TEST_SUCCESS_REQUIRED')
        native_fd, native_raw, native_record = read_pinned(pool, '/usr/bin/unshare', 47800, NATIVE_SHA)
        need(test['native_unshare']['sha256'] == NATIVE_SHA and
             not native_record['stat']['st_mode'] & (stat.S_ISUID | stat.S_ISGID), 'TESTED_NATIVE_EXEC_REQUIRED')
        try:
            capability = os.getxattr(native_fd, 'security.capability')
        except OSError as error:
            need(error.errno == errno.ENODATA, 'NATIVE_CAPABILITIES_UNKNOWN')
            capability = b''
        need(not capability, 'NATIVE_CAPABILITY_ABSENT_REQUIRED')
        native_record.update(file_capabilities_absent=True, help_sha256=test['native_unshare']['help_sha256'],
                             version=test['native_unshare']['version'])
        old_fd, old_raw, old_record = read_pinned(pool, TARGET, 560, OLD_SHA)
        need(old_record['stat'] == OLD_STAT and os.listxattr(old_fd) == [], 'ORIGINAL_WRAPPER_IDENTITY_OR_XATTRS_CHANGED')
        target_parent = opened(pool, TARGET.rsplit('/', 1)[0], os.O_RDONLY | os.O_DIRECTORY)
        parent_meta = metadata(target_parent)
        need(parent_meta['st_uid'] == 0 and stat.S_ISDIR(parent_meta['st_mode']) and
             not parent_meta['st_mode'] & 0o022, 'ROOT_PROTECTED_WRAPPER_DIRECTORY_REQUIRED')
        work = opened(pool, '/home/alex/work', os.O_RDONLY | os.O_DIRECTORY)
        os.mkdir(ROOT.rsplit('/', 1)[1], 0o700, dir_fd=work)
        os.fsync(work)
        output = opened(pool, ROOT, os.O_RDONLY | os.O_DIRECTORY)
        write_file(pool, output, 'deploy_wrapper_r1.py', source.encode())
        write_file(pool, output, 'previous-unshare.py', old_raw)
        backup_fd, unused, backup = read_pinned(pool, ROOT + '/previous-unshare.py', 560, OLD_SHA)
        need(backup['stat']['st_uid'] == 0 and stat.S_IMODE(backup['stat']['st_mode']) == 0o400, 'PRIVATE_BACKUP_REQUIRED')
        write_file(pool, output, 'host-tests.terminal.raw.json', terminal_raw)
        write_file(pool, output, 'host-tests.result.raw.json', test_raw)
        result.update(old_wrapper=old_record, retained_old_wrapper=backup,
                      native_unshare=native_record, source_manifest=manifest_pin,
                      host_test_receipt=test_pin, host_test_terminal=terminal_pin,
                      host_test_job_id=terminal['job_id'])
        name = '.unshare-pocket4-repaired-20261106-r1'
        write_file(pool, target_parent, name, source_rows['unshare_wrapper.py'][1], 0o755)
        temp_path = TARGET.rsplit('/', 1)[0] + '/' + name
        temp_fd, unused, temp_record = read_pinned(pool, temp_path, 6290, NEW_SHA)
        need(temp_record['stat']['st_uid'] == 0 and temp_record['stat']['st_gid'] == 0 and
             stat.S_IMODE(temp_record['stat']['st_mode']) == 0o755 and os.listxattr(temp_fd) == [], 'NEW_WRAPPER_OWNER_MODE_REQUIRED')
        for fd, unused, record in source_rows.values():
            recheck(pool, fd, record)
        recheck(pool, native_fd, native_record)
        recheck(pool, old_fd, old_record)
        recheck(pool, backup_fd, backup)
        recheck(pool, temp_fd, temp_record)
        recheck(pool, lock, lock_pin)
        result['intent'] = {'only_mutation': 'atomic_replace_one_fixed_compatibility_wrapper',
                            'target': TARGET, 'from_sha256': OLD_SHA, 'to_sha256': NEW_SHA,
                            'automatic_retry': False, 'created_monotonic_ns': time.monotonic_ns()}
        write_file(pool, output, 'replacement-intent.json', canonical(result['intent']) + b'\n')
        result['replacement_attempted'] = result['outcome_unknown'] = True
        os.replace(name, 'unshare', src_dir_fd=target_parent, dst_dir_fd=target_parent)
        os.fsync(target_parent)
        new_fd, unused, new_record = read_pinned(pool, TARGET, 6290, NEW_SHA)
        need(new_record['stat']['st_dev'] == temp_record['stat']['st_dev'] and
             new_record['stat']['st_ino'] == temp_record['stat']['st_ino'] and
             new_record['stat']['st_uid'] == new_record['stat']['st_gid'] == 0 and
             stat.S_IMODE(new_record['stat']['st_mode']) == 0o755 and os.listxattr(new_fd) == [], 'ATOMIC_NEW_WRAPPER_READBACK_REQUIRED')
        recheck(pool, native_fd, native_record)
        recheck(pool, backup_fd, backup)
        recheck(pool, lock, lock_pin)
        result.update(new_wrapper=new_record, ok=True, outcome_unknown=False)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:200]})
        result['ok'] = False
        result['outcome_unknown'] = result['replacement_attempted']
    finally:
        if output is not None:
            try:
                write_file(pool, output, 'operation-result.json', canonical(result) + b'\n')
            except BaseException as error:
                result['errors'].append({'stage': 'operation_receipt', 'type': type(error).__name__})
                result['ok'] = False
        result['descriptors'] = pool.close_all()
        if result['descriptors']['errors'] or result['descriptors']['remaining']:
            result['ok'] = False
        result['outcome_unknown'] = bool(result['replacement_attempted'] and not result['ok'])
    if output is not None:
        final = Descriptors()
        try:
            d = opened(final, ROOT, os.O_RDONLY | os.O_DIRECTORY)
            raw = canonical(result) + b'\n'
            write_file(final, d, 'result.json', raw)
            result['result_artifact'] = {'path': ROOT + '/result.json', 'bytes': len(raw), 'sha256': sha(raw)}
        except BaseException as error:
            result.update(ok=False, outcome_unknown=result['replacement_attempted'])
            result['errors'].append({'stage': 'final_receipt', 'type': type(error).__name__})
        finally:
            result['final_receipt_descriptors'] = final.close_all()
            if result['final_receipt_descriptors']['errors'] or result['final_receipt_descriptors']['remaining']:
                result.update(ok=False, outcome_unknown=result['replacement_attempted'])
    return result


if __name__ == '__main__':
    os.umask(0o077)
    need(sys.argv[1:] == ['--execute'], 'EXPLICIT_DEPLOYMENT_REQUIRED')
    payload = json.loads(sys.stdin.read(131073))
    need(set(payload) == {'source'}, 'CLOSED_SELF_SOURCE_PACKET')
    result = run(payload['source'])
    print(json.dumps(result, sort_keys=True, separators=(',', ':')), flush=True)
    raise SystemExit(0 if result['ok'] else 1)
