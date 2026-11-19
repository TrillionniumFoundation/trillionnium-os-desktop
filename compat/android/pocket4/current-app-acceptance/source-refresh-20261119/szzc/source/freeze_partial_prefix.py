#!/usr/bin/env python3
"""Read-only proof of the retired download and complete owned partial prefix."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import subprocess

ROOT = Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
UNIT = 'p4-szzc-current-download-5cd1-r1.service'
FAILURE_SHA = '25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'
assert os.getuid() == 1000 and os.sched_getaffinity(0) == {31}
resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))


def f9(st):
    return [str(x) for x in (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
                            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)]


show = subprocess.run(['/usr/bin/systemctl', '--user', 'show', UNIT,
                       '--property=LoadState,ActiveState,SubState,ExecMainPID,ControlGroup'],
                      text=True, capture_output=True, timeout=10)
props = dict(x.split('=', 1) for x in show.stdout.splitlines() if '=' in x)
assert show.returncode == 0 and props == {'LoadState': 'not-found', 'ActiveState': 'inactive',
                                        'SubState': 'dead', 'ExecMainPID': '0', 'ControlGroup': ''}
cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / UNIT
assert not cgroup.exists()
records = []
failure = None
for path, expected_size, expected_sha in [
        (ROOT / 'download/TRANSPORT-RESULT.json', 2031, FAILURE_SHA),
        (ROOT / 'download/com.szzc.publisher-current.apk.part', 58720256, None)]:
    assert path.resolve() == path
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_uid == 1000 and st.st_nlink == 1
        assert st.st_size == expected_size and f9(path.lstat()) == f9(st)
        digest = hashlib.sha256()
        offset = 0
        while True:
            data = os.pread(fd, 1024 * 1024, offset)
            if not data:
                break
            digest.update(data)
            offset += len(data)
        assert offset == expected_size and (expected_sha is None or digest.hexdigest() == expected_sha)
        assert f9(os.fstat(fd)) == f9(st) and f9(path.lstat()) == f9(st)
        records.append({'path': str(path), 'bytes': offset, 'sha256': digest.hexdigest(),
                        'identity': f9(st), 'held_FD_and_path_bookends_unchanged': True})
        if path.name == 'TRANSPORT-RESULT.json':
            failure = json.loads(os.pread(fd, 2031, 0))
    finally:
        os.close(fd)
assert failure['complete'] is False and failure['total_bytes_received_before_terminal'] == 58720256
assert failure['error'] == "TimeoutError('whole transfer deadline')"
result = {'schema': 'pocket4-szzc-retired-partial-prefix-freeze-v1',
          'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'original_unit': {'name': UNIT, 'exit': show.returncode, 'stdout': show.stdout,
                            'stderr': show.stderr, 'cgroup_exists': False, 'retired': True},
          'original_failed_transport': records[0], 'prefix': records[1],
          'prefix_is_not_a_complete_APK': True, 'full_candidate_bytes': 220498418,
          'remaining_bytes': 161778162, 'source_identity_verified': False,
          'old_selected_APK_read_or_changed': False, 'Android_or_SDK_calls': 0,
          'installed': False, 'runtime_qualified': False,
          'business_qualified': False, 'production_ready': False}
data = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
out = ROOT / 'inputs/PARTIAL-PREFIX-FREEZE.json'
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps({'result': {'path': str(out), 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest()},
                  'prefix': records[1], 'original_unit_retired': True}, sort_keys=True), flush=True)
