#!/usr/bin/env python3
"""Freeze the actual same-inode prefix after the bounded Range timeout."""
import datetime, hashlib, json, os, resource, signal, stat, subprocess, threading
from pathlib import Path
ROOT = Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
SIZE = 168361302
ORIGINAL_SIZE = 58720256
ORIGINAL_SHA = 'f6132a3989b706664209dda867c0c5d0816bc76b2fef3488abc144cd80a28c0d'
assert os.getuid() == 1000 and os.sched_getaffinity(0) == {31}
assert signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL
assert threading.get_native_id() == os.getpid() and os.listdir('/proc/self/task') == [str(os.getpid())]
resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))
os.umask(0o077)


def f9(st):
    return [str(x) for x in (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
                            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)]


units = []
for unit in ('p4-szzc-current-download-5cd1-r1.service', 'p4-szzc-current-resume-5cd1-r1.service'):
    command = ['/usr/bin/systemctl', '--user', 'show', unit,
               '--property=LoadState,ActiveState,SubState,ExecMainPID,ControlGroup']
    show = subprocess.run(command, text=True, capture_output=True, timeout=10)
    props = dict(x.split('=', 1) for x in show.stdout.splitlines() if '=' in x)
    assert show.returncode == 0 and not show.stderr
    assert props == {'LoadState': 'not-found', 'ActiveState': 'inactive',
                     'SubState': 'dead', 'ExecMainPID': '0', 'ControlGroup': ''}
    cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
    try:
        cgroup.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('old transfer cgroup still exists')
    units.append({'name': unit, 'exit': show.returncode, 'stdout': show.stdout,
                  'stderr': show.stderr, 'cgroup_exists': False, 'retired': True})
specs = [
    ('original_failed_transport', ROOT / 'download/TRANSPORT-RESULT.json', 2031,
     '25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'),
    ('first_prefix_freeze', ROOT / 'inputs/PARTIAL-PREFIX-FREEZE.json', 1662,
     '01536a3d7139e58e176a739414a29500700df4cece2895df9c7a5277a0f030c2'),
    ('failed_first_resume', ROOT / 'download/RESUME-TRANSPORT-RESULT.json', 4818,
     'b8ee3b641bdfdce72a1e0cdab1f9f2af057af0a415e5a82397876676dc4c5ce8'),
    ('prefix', ROOT / 'download/com.szzc.publisher-current.apk.part', SIZE, None),
]
held = []
pins = {}
docs = {}
try:
    for label, path, expected_size, expected_sha in specs:
        assert path.resolve() == path and path.parent.lstat().st_uid == 1000
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        held.append((fd, path))
        st = os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_uid == 1000 and st.st_nlink == 1
        assert st.st_size == expected_size and f9(path.lstat()) == f9(st)
        digest = hashlib.sha256()
        original = hashlib.sha256()
        offset = 0
        while offset < expected_size:
            block = os.pread(fd, min(1024 * 1024, expected_size - offset), offset)
            assert block
            digest.update(block)
            if label == 'prefix' and offset < ORIGINAL_SIZE:
                original.update(block[:ORIGINAL_SIZE - offset])
            offset += len(block)
        assert expected_sha is None or digest.hexdigest() == expected_sha
        assert f9(os.fstat(fd)) == f9(st) and f9(path.lstat()) == f9(st)
        pin = {'path': str(path), 'bytes': offset, 'sha256': digest.hexdigest(),
               'identity': f9(st), 'held_FD_and_path_bookends_unchanged': True}
        pins[label] = pin
        if label == 'prefix':
            assert original.hexdigest() == ORIGINAL_SHA
        else:
            docs[label] = json.loads(os.pread(fd, expected_size, 0))
    assert docs['original_failed_transport']['complete'] is False
    failed = docs['failed_first_resume']
    assert failed['complete'] is False and failed['actual_inode_size_at_terminal'] == SIZE
    assert failed['tail_complete_blocks_recorded_bytes'] + ORIGINAL_SIZE == SIZE
    assert failed['all_three_input_bookends_unchanged'] is True
    assert failed['error'] == "TimeoutError('whole continuation deadline after read')"
    assert pins['prefix']['identity'][:6] == docs['first_prefix_freeze']['prefix']['identity'][:6]
    for (fd, path), (label, _, _, _) in zip(held, specs, strict=True):
        assert f9(os.fstat(fd)) == f9(path.lstat()) == pins[label]['identity']
    result = {'schema': 'pocket4-szzc-retired-second-prefix-freeze-v1',
        'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'original_units': units, 'both_original_units_retired': True, **pins,
        'original_58720256_prefix': {'bytes': ORIGINAL_SIZE, 'sha256': ORIGINAL_SHA,
                                    'full_readback_unchanged': True},
        'prefix_is_not_a_complete_APK': True, 'full_candidate_bytes': 220498418,
        'remaining_bytes': 220498418 - SIZE, 'source_identity_verified': False,
        'old_selected_APK_read_or_changed': False, 'Android_or_SDK_calls': 0,
        'installed': False, 'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}
    data = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    assert len(data) <= 16384
    out = ROOT / 'inputs/SECOND-PREFIX-FREEZE.json'
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'result': {'path': str(out), 'bytes': len(data),
                                'sha256': hashlib.sha256(data).hexdigest()},
                      'prefix': pins['prefix'], 'original_units_retired': True}, sort_keys=True), flush=True)
finally:
    for fd, path in held:
        os.close(fd)
