#!/usr/bin/env python3
"""Read only the retired Owner08 NORMAL01 attempt's fixed records and helper logs."""
import hashlib, json, os, stat, sys, traceback
from pathlib import PurePosixPath

ROOT = '/opt/p4-owner08-normal-20261105-01-state'
ATTEMPT = '1263e33ed55e57b4ec42ead6afd051ed1b8265e9bead44653b8a87e70ca74498'
PREPARED_SHA = '7972563f7c4e56c89e51424a06c01d3250f51fa1c7836ec6d67ab9a06057e0fa'
RUNTIME_SHA = '027848bec17ae20259e3ab2ddd8637bc820608b7f62e580c06b019f0e9ff8f16'
INVOCATION = '68550c01a9fd402687a3d36d3e69c2c8'
ACTOR_PID = 1204471
RECORDS = ('preparation-claim.json', 'prepared.json', 'coordinator-claim.json',
           'gate.json', 'runtime-claim.json', 'actor-result.json', 'runtime-result.json')
LOGS = tuple(role + '.' + stream for role in ('bus', 'sway', 'presenter', 'daemon')
             for stream in ('stdout', 'stderr'))
PER_FILE = 1024 * 1024
TOTAL = 4 * 1024 * 1024

def need(value, message):
    if not value: raise RuntimeError(message)

def stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def directory(path):
    parts = PurePosixPath(path).parts
    need(parts[0] == '/' and '..' not in parts, 'invalid fixed directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            st = os.fstat(fd)
            need(st.st_uid == st.st_gid == 0 and not st.st_mode & 0o022,
                 'fixed evidence ancestor is not protected/root-owned')
        answer, fd = fd, -1
        return answer
    finally:
        if fd >= 0: os.close(fd)

def read_at(parent, name, expected=None):
    need('/' not in name, 'not an allowlisted leaf')
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_uid == before.st_gid == 0 and not before.st_mode & 0o6022 and
             0 <= before.st_size <= PER_FILE, 'fixed file metadata or bound differs: ' + name)
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, PER_FILE + 1 - len(raw)))
            if not part: break
            raw.extend(part); need(len(raw) <= PER_FILE, 'fixed file grew beyond bound')
        need(len(raw) == before.st_size and stamp(os.fstat(fd)) == stamp(before), 'fixed file changed while reading')
        digest = hashlib.sha256(raw).hexdigest()
        need(expected is None or digest == expected, 'external actual receipt digest differs: ' + name)
        return {'bytes': len(raw), 'sha256': digest, 'device': before.st_dev,
                'inode': before.st_ino, 'content': bytes(raw).decode('utf-8', 'strict')}
    finally:
        os.close(fd)

def main():
    report = {'schema': 1, 'kind': 'owner08-normal01-retired-evidence-read01',
              'collection_complete': False, 'qualification': False,
              'runtime_executed': False, 'mutations': False,
              'root': ROOT, 'attempt_nonce': ATTEMPT, 'files': {}, 'errors': []}
    root = logs = -1
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'fixed reader requires original root')
        root = directory(ROOT)
        prepared = read_at(root, 'prepared.json', PREPARED_SHA)
        runtime = read_at(root, 'runtime-result.json', RUNTIME_SHA)
        p, r = json.loads(prepared['content']), json.loads(runtime['content'])
        st = os.fstat(root)
        need(p['state_identity'] == {'device': st.st_dev, 'inode': st.st_ino} and
             p['attempt_nonce'] == r['attempt_nonce'] == ATTEMPT and
             r['prepared_sha256'] == PREPARED_SHA and
             r['terminal']['InvocationID'] == INVOCATION and
             r['terminal']['ExecMainPID'] == str(ACTOR_PID), 'original preparation/unit attempt binding differs')
        cleanup = r['exact_unit_cleanup']
        need(cleanup['unit_not_found'] is True and cleanup['cgroup_absent'] is True and
             cleanup['original_actor_dead'] is True and cleanup['invocation'] == INVOCATION,
             'actual original cleanup evidence is incomplete')
        report['files']['prepared.json'] = prepared
        report['files']['runtime-result.json'] = runtime
        total = prepared['bytes'] + runtime['bytes']
        for name in RECORDS:
            if name in report['files']: continue
            expected = {'actor-result.json': r['actor_result_sha256'], 'gate.json': r['gate_sha256']}.get(name)
            row = read_at(root, name, expected)
            total += row['bytes']; need(total <= TOTAL, 'aggregate evidence exceeds bound')
            report['files'][name] = row
        logs = os.open('evidence', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=root)
        st = os.fstat(logs)
        need(st.st_uid == st.st_gid == 0 and not st.st_mode & 0o022, 'owned log directory differs')
        for name in LOGS:
            row = read_at(logs, name)
            total += row['bytes']; need(total <= TOTAL, 'aggregate log bound exceeded')
            report['files']['evidence/' + name] = row
        need(read_at(root, 'prepared.json', PREPARED_SHA) == prepared and
             read_at(root, 'runtime-result.json', RUNTIME_SHA) == runtime, 'bound actual receipts changed')
        report['aggregate_bytes'] = total
        report['collection_complete'] = len(report['files']) == len(RECORDS) + len(LOGS)
    except BaseException as error:
        report['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        if logs >= 0: os.close(logs)
        if root >= 0: os.close(root)
    sys.stdout.write(json.dumps(report, sort_keys=True, ensure_ascii=False) + '\n')
    return 0 if report['collection_complete'] and not report['errors'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
