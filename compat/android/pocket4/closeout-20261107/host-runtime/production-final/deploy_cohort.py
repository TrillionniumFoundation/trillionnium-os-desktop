"""Explicit Pocket4 host/consumer/storage cohort. Default check is read-only.
No lifecycle command, Android command, or readiness request exists here.
"""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import tempfile

ROOT = pathlib.Path('/home/alex/work/pocket4-status-readiness-finalize-20261107-r1/deployment')
TARGETS = {
    '/usr/bin/droidloom-supervisor', '/usr/bin/droidloomd',
    '/usr/bin/droidloomctl', '/usr/bin/droidloom-applications',
    '/usr/local/bin/android-app', '/usr/local/bin/android-app-digitalis-validation',
    '/usr/local/bin/android-app-digitalis',
    '/usr/local/libexec/android-digitalis-observe-helper',
    '/usr/local/libexec/android-digitalis-validation-helper',
    '/usr/local/libexec/android-digitalis-helper',
    '/opt/pocket4-wifi-disabled-api-20261023-chat2-v2/payload/services-candidate.jar',
}
STORAGE_TARGET = '/opt/pocket4-wifi-disabled-api-20261023-chat2-v2/payload/services-candidate.jar'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def snapshot(path):
    path = pathlib.Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode):
            raise RuntimeError('NOT_REGULAR_FILE: ' + str(path))
        h = hashlib.sha256()
        while True:
            b = os.read(fd, 1048576)
            if not b:
                break
            h.update(b)
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns, named.st_ctime_ns):
            raise RuntimeError('NAMED_FILE_CHANGED_DURING_READ: ' + str(path))
        if (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise RuntimeError('FILE_CHANGED_DURING_READ: ' + str(path))
        return dict(path=str(path), sha256=h.hexdigest(), bytes=s.st_size, device=s.st_dev,
                    inode=s.st_ino, link_count=s.st_nlink, uid=s.st_uid, gid=s.st_gid, mode=stat.S_IMODE(s.st_mode),
                    mtime_ns=s.st_mtime_ns, atime_ns=s.st_atime_ns, ctime_ns=s.st_ctime_ns,
                    xattrs={n: base64.b64encode(os.getxattr(fd, n)).decode() for n in os.listxattr(fd)})
    finally:
        os.close(fd)

def same_attributes(actual, expected):
    return all(actual[k] == expected[k] for k in ('uid', 'gid', 'mode', 'mtime_ns', 'xattrs'))

def check_baseline(targets):
    current = {t['name']: snapshot(t['host_path']) for t in targets}
    for t in targets:
        s = current[t['name']]
        if s['sha256'] != t['baseline']['sha256'] or s['link_count'] != 1 or not same_attributes(s, t['baseline']):
            raise RuntimeError('BASELINE_PAIR_CHANGED: ' + t['name'])
    return current

def data_root_identity(manifest):
    p = pathlib.Path(manifest['data_root']['path'])
    s = p.lstat()
    if not stat.S_ISDIR(s.st_mode):
        raise RuntimeError('DATA_ROOT_NOT_DIRECTORY')
    observed = {'path': str(p), 'device': s.st_dev, 'inode': s.st_ino}
    if observed != manifest['data_root']:
        raise RuntimeError('DATA_ROOT_IDENTITY_CHANGED')
    return observed

def proc_identity(pid):
    p = pathlib.Path('/proc') / str(pid)
    s = (p / 'stat').read_text()
    a = s[s.rfind(')') + 2:].split()
    return dict(pid=pid, starttime=int(a[19]), ppid=int(a[1]), state=a[0])

def run_read(argv, timeout=10):
    q = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if q.returncode != 0:
        raise RuntimeError('READ_COMMAND_FAILED: ' + repr(argv) + ': ' + q.stderr[:2000])
    return q.stdout

def protect(manifest):
    data_root_identity(manifest)
    for path, expected in manifest['protected_files'].items():
        actual = snapshot(path)
        if actual['sha256'] != expected['sha256']:
            raise RuntimeError('PROTECTED_FILE_CHANGED: ' + path)
    alias = manifest['current_alias']
    if os.readlink(alias['path']) != alias['symlink'] or str(pathlib.Path(alias['path']).resolve(strict=True)) != alias['resolved']:
        raise RuntimeError('CURRENT_ALIAS_CHANGED')
    state = json.loads(pathlib.Path('/etc/droidloom/package-state.json').read_text())
    version = json.loads(pathlib.Path('/usr/share/droidloom/package.json').read_text())
    if state['uid'] != 1000 or state['version'] != version:
        raise RuntimeError('PACKAGE_HELPER_FAST_PATH_CHANGED')

def service_state(unit, *, user=False):
    argv = ['/usr/bin/systemctl']
    options = {}
    if user:
        argv.append('--user')
        options.update(user=1000, group=1000, extra_groups=[],
                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C',
                            'XDG_RUNTIME_DIR': '/run/user/1000',
                            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'})
    argv += ['show', unit, '--property=ActiveState', '--property=MainPID', '--property=ControlPID']
    p = subprocess.run(argv, capture_output=True, text=True, timeout=15, **options)
    if p.returncode != 0:
        raise RuntimeError('SERVICE_STATE_READ_FAILED: ' + unit + ': ' + p.stderr[:1000])
    fields = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
    if fields != {'ActiveState': 'inactive', 'MainPID': '0', 'ControlPID': '0'}:
        raise RuntimeError('SERVICE_NOT_QUIESCENT: ' + unit + ': ' + repr(fields))
    return fields

def require_stopped(manifest):
    # Check units before touching any target. No Status RPC can create a child.
    states = {'system/droidloomd.service': service_state('droidloomd.service')}
    for unit in ('droidloom.service', 'droidloom-applications.service'):
        states['user/' + unit] = service_state(unit, user=True)
    if pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip() != manifest['old_boot_id']:
        raise RuntimeError('BOOT_CHANGED_SINCE_PREPARATION')
    for item in manifest['old_generation'].values():
        try:
            now = proc_identity(item['pid'])
        except FileNotFoundError:
            continue
        if now['starttime'] == item['starttime']:
            raise RuntimeError('OLD_GENERATION_STILL_ALIVE')
    for p in pathlib.Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if os.readlink(p / 'ns/pid') == manifest['old_pid_namespace']:
                raise RuntimeError('OLD_ANDROID_NAMESPACE_STILL_HAS_PROCESSES')
        except (FileNotFoundError, ProcessLookupError):
            pass
    protect(manifest)
    return {'services': states, 'old_eight_roles_absent': True,
            'old_android_pid_namespace_empty': True, 'lifecycle_operations': 0}

def fsync_directory(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def stage(target, payload, expected_digest, metadata):
    payload = pathlib.Path(payload)
    p = snapshot(payload)
    if p['sha256'] != expected_digest:
        raise RuntimeError('PAYLOAD_HASH_CHANGED')
    data = payload.read_bytes()
    if digest(data) != expected_digest:
        raise RuntimeError('PAYLOAD_CHANGED_DURING_COPY')
    fd, tmp = tempfile.mkstemp(prefix='.pocket4-closeout-cohort-', dir=str(pathlib.Path(target).parent))
    tmp = pathlib.Path(tmp)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fchown(f.fileno(), metadata['uid'], metadata['gid'])
            os.fchmod(f.fileno(), metadata['mode'])
            for name, value in metadata['xattrs'].items():
                os.setxattr(f.fileno(), name, base64.b64decode(value, validate=True))
            os.utime(f.fileno(), ns=(metadata['atime_ns'], metadata['mtime_ns']))
            os.fsync(f.fileno())
        s = snapshot(tmp)
        if s['sha256'] != expected_digest or not same_attributes(s, metadata):
            raise RuntimeError('STAGED_FILE_VERIFICATION_FAILED')
        return tmp, s
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise

def transact(targets, variant, guard, note, replace=os.replace):
    """Filesystem core; tests use temporary paths and a fake stopped-state guard."""
    if variant not in ('candidate', 'rollback'):
        raise ValueError(variant)
    guard()
    before = {}
    for t in targets:
        actual = snapshot(t['host_path'])
        allowed = {t['baseline']['sha256']} if variant == 'candidate' else {t['baseline']['sha256'], t['candidate']['sha256']}
        if actual['link_count'] != 1 or actual['sha256'] not in allowed or not same_attributes(actual, t['baseline']):
            raise RuntimeError('CURRENT_PAIR_HASH_OR_ATTRIBUTES_CHANGED: ' + t['host_path'])
        before[t['name']] = actual
    pending = []; committed = []; attempted = []; restoring = []; result = dict(success=False, changed=[], rollback_completed=False)
    try:
        for t in targets:
            source = t['candidate' if variant == 'candidate' else 'rollback']
            tmp, info = stage(t['host_path'], source['path'], source['sha256'], t['baseline'])
            pending.append((t, tmp, info))
        note('staged_cohort', {'paths': [str(x[1]) for x in pending]})
        guard()
        for t, tmp, info in pending:
            guard()
            attempted.append(t['name'])
            replace(tmp, t['host_path'])
            committed.append(t['name'])
            fsync_directory(pathlib.Path(t['host_path']).parent)
            note('committed_file', {'name': t['name'], 'sha256': info['sha256'], 'inode': info['inode']})
        after = {t['name']: snapshot(t['host_path']) for t in targets}
        for t in targets:
            expected = t['candidate' if variant == 'candidate' else 'rollback']['sha256']
            if after[t['name']]['sha256'] != expected or not same_attributes(after[t['name']], t['baseline']):
                raise RuntimeError('PAIR_READBACK_FAILED')
            if after[t['name']]['inode'] == before[t['name']]['inode']:
                raise RuntimeError('EXPECTED_NEW_INODE_NOT_OBSERVED')
        guard()
        result.update(success=True, changed=committed, before=before, after=after, final_pair=variant)
        note('pair_verified', result)
        return result
    except BaseException as original:
        result.update(error=type(original).__name__ + ': ' + str(original), changed=committed, attempted=attempted)
        if attempted:
            try:
                guard()
                for t in targets:
                    current = snapshot(t['host_path'])
                    if current['sha256'] not in {t['baseline']['sha256'], t['candidate']['sha256']} or current['link_count'] != 1 or not same_attributes(current, t['baseline']):
                        raise RuntimeError('UNKNOWN_BYTES_OR_ATTRIBUTES_PREVENT_AUTOMATIC_ROLLBACK')
                for t in targets:
                    guard()
                    b = t['rollback']
                    tmp, info = stage(t['host_path'], b['path'], b['sha256'], t['baseline'])
                    restoring.append((tmp, info))
                    os.replace(tmp, t['host_path'])
                    fsync_directory(pathlib.Path(t['host_path']).parent)
                restored = {t['name']: snapshot(t['host_path']) for t in targets}
                if not all(restored[t['name']]['sha256'] == t['baseline']['sha256'] and same_attributes(restored[t['name']], t['baseline']) for t in targets):
                    raise RuntimeError('ROLLBACK_READBACK_FAILED')
                guard()
                result.update(rollback_completed=True, final_pair='rollback', after=restored)
                note('automatic_pair_rollback_verified', result)
            except BaseException as recovery:
                result['rollback_error'] = type(recovery).__name__ + ': ' + str(recovery)
        else:
            result['final_pair'] = 'unchanged'
        note('transaction_failed', result)
        return result
    finally:
        cleanup = []
        for tmp, info in [(x[1], x[2]) for x in pending] + restoring:
            try:
                if tmp.exists():
                    actual = snapshot(tmp)
                    if (actual['device'], actual['inode'], actual['sha256']) != (info['device'], info['inode'], info['sha256']):
                        raise RuntimeError('TEMPORARY_FILE_CHANGED')
                    tmp.unlink()
            except BaseException as e:
                cleanup.append({'path': str(tmp), 'error': str(e)})
        if cleanup:
            result['cleanup_errors'] = cleanup
            result['success'] = False


def load_manifest(expected):
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise RuntimeError('EXTERNAL_MANIFEST_SHA256_REQUIRED')
    path = ROOT / 'manifest.json'
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise RuntimeError('DEPLOYMENT_MANIFEST_PIN_CHANGED')
    m = json.loads(raw)
    if m.get('schema') != 'pocket4-closeout-cohort-v1':
        raise RuntimeError('DEPLOYMENT_MANIFEST_SCHEMA_CHANGED')
    rows = m.get('targets', [])
    if len(rows) != len(TARGETS) or {t['host_path'] for t in rows} != TARGETS:
        raise RuntimeError('EXACT_ELEVEN_TARGETS_REQUIRED')
    if len({t['name'] for t in rows}) != len(rows):
        raise RuntimeError('DUPLICATE_TARGET_NAME')
    for t in rows:
        expected_uid = 1000 if t['host_path'] in (
            '/usr/bin/droidloomctl', '/usr/bin/droidloom-applications') else 0
        expected_mode = 0o444 if t['host_path'] == STORAGE_TARGET else 0o755
        base = t['baseline']
        if (base['uid'], base['gid'], base['mode'], base['link_count']) != (
                expected_uid, expected_uid, expected_mode, 1):
            raise RuntimeError('EXACT_INSTALL_ATTRIBUTES_REQUIRED')
        for variant in ('candidate', 'rollback'):
            p = pathlib.Path(t[variant]['path'])
            if p.parent != ROOT / ('payloads' if variant == 'candidate' else 'rollback'):
                raise RuntimeError('PAYLOAD_OUTSIDE_FROZEN_DEPLOYMENT_DIRECTORY')
            s = snapshot(p)
            if s['sha256'] != t[variant]['sha256'] or s['bytes'] != t[variant]['bytes'] or s['link_count'] != 1:
                raise RuntimeError('FROZEN_PAYLOAD_CHANGED')
    if snapshot(__file__)['sha256'] != m['transaction_script_sha256']:
        raise RuntimeError('TRANSACTION_SOURCE_CHANGED')
    for name, pin in m['evidence'].items():
        p = ROOT / 'evidence' / name
        s = snapshot(p)
        if s['sha256'] != pin['sha256'] or s['bytes'] != pin['bytes']:
            raise RuntimeError('DEPLOYMENT_EVIDENCE_CHANGED: ' + name)
    return m

def write_new(path, value):
    data = (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    fsync_directory(pathlib.Path(path).parent)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('check', 'apply-stopped', 'rollback-stopped'), default='check')
    ap.add_argument('--manifest-sha256', required=True)
    a = ap.parse_args()
    m = load_manifest(a.manifest_sha256)
    protect(m)
    if a.mode == 'check':
        result = dict(success=True, mode='check', manifest_sha256=a.manifest_sha256, writes=0,
                      target_count=len(m['targets']), current=check_baseline(m['targets']),
                      data_root=data_root_identity(m), lifecycle_operations=0)
    else:
        if os.geteuid() != 0:
            raise RuntimeError('ROOT_REQUIRED_FOR_COHORT_TRANSACTION')
        os.umask(0o077)
        locks = []
        for path in (ROOT / 'transaction.lock', pathlib.Path('/run/lock/android-digitalis-actions.lock')):
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            s = os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != 0:
                os.close(fd); raise RuntimeError('UNSAFE_TRANSACTION_LOCK')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); locks.append(fd)
        operation = 'apply' if a.mode == 'apply-stopped' else 'rollback'
        write_new(ROOT / (operation + '.execution-guard.json'),
                  {'utc': utc(), 'operation': operation, 'manifest_sha256': a.manifest_sha256,
                   'automatic_retry': False})
        with (ROOT / (operation + '.journal.jsonl')).open('x') as journal:
            def note(event, fields):
                journal.write(json.dumps({'utc': utc(), 'event': event, **fields}) + '\n')
                journal.flush(); os.fsync(journal.fileno())
            try:
                result = transact(m['targets'], 'candidate' if operation == 'apply' else 'rollback',
                                  lambda: require_stopped(m), note)
            except BaseException as e:
                result = dict(success=False, error=type(e).__name__ + ': ' + str(e),
                              outcome_unknown=True, automatic_retry=False)
        result.update(operation=operation, schema='pocket4-closeout-cohort-result-v1',
                      manifest_sha256=a.manifest_sha256, ended_utc=utc(),
                      target_count=len(m['targets']), lifecycle_operations=0, app_launches=0)
        write_new(ROOT / (operation + '-result.json'), result)
        for fd in reversed(locks): os.close(fd)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['success'] else 1)

if __name__ == '__main__':
    main()

