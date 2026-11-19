#!/usr/bin/env python3
"""One exact conditional Range continuation of the frozen owned prefix; source only."""
import datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import resource
import ssl
import stat
import time
import traceback

ROOT = Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
OUT = ROOT / 'download'
PART = OUT / 'com.szzc.publisher-current.apk.part'
TARGET = OUT / 'com.szzc.publisher-current.apk'
PREFIX_SIZE = 58720256
SIZE = 220498418
REMAINING = SIZE - PREFIX_SIZE
PREFIX_SHA = 'f6132a3989b706664209dda867c0c5d0816bc76b2fef3488abc144cd80a28c0d'
PREFIX_F9 = ['66306', '49548783', '33152', '1000', '1000', '1',
             '58720256', '1795089120794421309', '1795089120794421309']
ETAG = '"108948280DD69A433DD2AEFD4585FD2B"'
LAST_MODIFIED = 'Wed, 18 Nov 2026 13:23:40 GMT'
URL = 'https://edfs.zuchecdn.com/android-package/SZZC.apk'
RANGE = 'bytes=58720256-220498417'
CONTENT_RANGE = 'bytes 58720256-220498417/220498418'
PINS = [
    ('HEAD', ROOT / 'inputs/PUBLISHER-REDIRECT-HEAD.json', 1502,
     '73fc14312fe687859899e9a1f9fa2d2ed3d3a52d90dcdd29ee1642a7845c64fd'),
    ('original_failed_transport', OUT / 'TRANSPORT-RESULT.json', 2031,
     '25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'),
    ('prefix_freeze', ROOT / 'inputs/PARTIAL-PREFIX-FREEZE.json', 1662,
     '01536a3d7139e58e176a739414a29500700df4cece2895df9c7a5277a0f030c2'),
]
R = {'schema': 'pocket4-szzc-observed-publisher-candidate-range-transport-v1',
     'complete': False, 'source_identity_verified': False, 'signature_verified': False,
     'previous_selected_APK_changed': False, 'source_registry_changed': False,
     'APK_installed': False, 'Android_calls': 0, 'SDK_calls': 0,
     'credentials_or_userdata_accessed': False, 'authentication_used': False,
     'cookies_used': False, 'redirects_followed': 0, 'retry_count': 0,
     'runtime_qualified': False, 'business_qualified': False, 'production_ready': False,
     'prefix_bytes_redownloaded': 0, 'expected_prefix_bytes': PREFIX_SIZE,
     'expected_remaining_bytes': REMAINING, 'expected_complete_bytes': SIZE,
     'source_inputs': [], 'input_bookends': []}
HELD = []


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def f9(s):
    return [str(x) for x in (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
                            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)]


def disk_floor(extra=0):
    v = os.statvfs(OUT)
    free = v.f_bavail * v.f_frsize
    R['minimum_observed_free_bytes'] = min(R.get('minimum_observed_free_bytes', free), free)
    if free < 24 * 1024**3 + extra:
        raise ValueError('24GiB free-disk floor during exact candidate continuation')


def read_input(label, path, size, expected):
    if path.resolve() != path:
        raise ValueError('aliased input pathname')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    st = os.fstat(fd)
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 1000 or st.st_nlink != 1
            or st.st_size != size or f9(path.lstat()) != f9(st)):
        os.close(fd)
        raise ValueError('owned exact input identity')
    raw = os.pread(fd, size + 1, 0)
    if len(raw) != size or sha(raw) != expected:
        os.close(fd)
        raise ValueError('frozen input full SHA')
    item = {'label': label, 'path': str(path), 'bytes': size,
            'sha256': expected, 'identity': f9(st)}
    HELD.append((fd, path, size, expected, f9(st), label))
    R['source_inputs'].append(item)
    return json.loads(raw)


def bookends():
    valid = True
    for fd, path, size, expected, identity, label in HELD:
        try:
            ok = (f9(os.fstat(fd)) == identity and f9(path.lstat()) == identity
                  and sha(os.pread(fd, size + 1, 0)) == expected)
            item = {'label': label, 'unchanged': ok, 'path': str(path),
                    'bytes': size, 'sha256': expected}
        except Exception as exc:
            ok = False
            item = {'label': label, 'unchanged': False, 'error': repr(exc)}
        R['input_bookends'].append(item)
        valid = valid and ok
    R['all_three_input_bookends_unchanged'] = valid and len(HELD) == 3
    return R['all_three_input_bookends_unchanged']


def hash_fd(fd, size, both=False):
    digest = hashlib.sha256()
    md5 = hashlib.md5() if both else None
    position = 0
    while position < size:
        block = os.pread(fd, min(1024 * 1024, size - position), position)
        if not block:
            raise ValueError('short full-file readback')
        digest.update(block)
        if md5 is not None:
            md5.update(block)
        position += len(block)
    return digest, md5


def path_fd_size(fd, path, expected_size):
    st = os.fstat(fd)
    identity = f9(st)
    if (identity[:6] != PREFIX_F9[:6] or st.st_size != expected_size
            or f9(path.lstat()) != identity):
        raise ValueError('prefix inode/owner/mode/link/append-size identity changed')
    return identity


def main():
    if os.getuid() != 1000 or os.sched_getaffinity(0) != {31}:
        raise ValueError('ordinary qq and explicit CPU31 required')
    resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    for directory in (ROOT, ROOT / 'inputs', OUT):
        ds = directory.lstat()
        if directory.resolve() != directory or not stat.S_ISDIR(ds.st_mode) or ds.st_uid != 1000:
            raise ValueError('canonical owned source directory required')
    if os.path.lexists(TARGET) or os.path.lexists(OUT / 'RESUME-TRANSPORT-RESULT.json'):
        raise ValueError('one-shot continuation output already exists')
    head, failed, freeze = [read_input(*pin) for pin in PINS]
    if (head['http_status'] != 200 or head['content_length'] != str(SIZE)
            or head['etag'] != ETAG or head['last_modified'] != LAST_MODIFIED
            or head['request_url'] != URL):
        raise ValueError('original publisher HEAD identity')
    if (failed['complete'] is not False or failed['total_bytes_received_before_terminal'] != PREFIX_SIZE
            or failed['http']['status'] != 200 or failed['http']['etag'] != ETAG
            or failed['http']['content_length'] != str(SIZE)):
        raise ValueError('original failure is not the observed frozen prefix')
    if (freeze['prefix']['identity'] != PREFIX_F9 or freeze['prefix']['sha256'] != PREFIX_SHA
            or freeze['prefix']['bytes'] != PREFIX_SIZE or freeze['prefix']['path'] != str(PART)
            or not freeze['prefix']['held_FD_and_path_bookends_unchanged']
            or not freeze['original_unit']['retired'] or freeze['original_unit']['cgroup_exists']
            or freeze['original_failed_transport']['sha256'] != PINS[1][3]
            or not freeze['original_failed_transport']['held_FD_and_path_bookends_unchanged']):
        raise ValueError('original retired prefix freeze mismatch')
    old_cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/p4-szzc-current-download-5cd1-r1.service')
    if old_cgroup.exists():
        raise ValueError('original transfer cgroup is present')
    R['original_unit_retired_at_freeze_and_cgroup_still_absent'] = True
    disk_floor(REMAINING + 65536)
    fd = os.open(PART, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
    appended = 0
    start = time.monotonic()
    R['started_utc'] = now()
    conn = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path_fd_size(fd, PART, PREFIX_SIZE) != PREFIX_F9:
            raise ValueError('frozen F9 differs before continuation')
        digest, md5 = hash_fd(fd, PREFIX_SIZE, both=True)
        if digest.hexdigest() != PREFIX_SHA or path_fd_size(fd, PART, PREFIX_SIZE) != PREFIX_F9:
            raise ValueError('full original prefix digest before continuation')
        R['prefix_before'] = {'bytes': PREFIX_SIZE, 'sha256': digest.hexdigest(), 'identity': PREFIX_F9}
        conn = http.client.HTTPSConnection('edfs.zuchecdn.com', 443, timeout=15,
                                           context=ssl.create_default_context())
        conn.request('GET', '/android-package/SZZC.apk', headers={
            'User-Agent': 'Pocket4-publisher-source-qualification',
            'Accept': 'application/vnd.android.package-archive',
            'Accept-Encoding': 'identity', 'Connection': 'close',
            'If-Match': ETAG, 'Range': RANGE})
        response = conn.getresponse()
        R['http'] = {'method': 'GET', 'url': URL, 'conditional_if_match': ETAG,
                     'request_range': RANGE, 'status': response.status,
                     'date': response.getheader('Date'),
                     'content_length': response.getheader('Content-Length'),
                     'content_range': response.getheader('Content-Range'),
                     'content_type': response.getheader('Content-Type'),
                     'etag': response.getheader('ETag'),
                     'last_modified': response.getheader('Last-Modified'),
                     'content_encoding': response.getheader('Content-Encoding', 'identity'),
                     'transfer_encoding': response.getheader('Transfer-Encoding'),
                     'location': response.getheader('Location')}
        h = R['http']
        if (h['status'] != 206 or h['content_length'] != str(REMAINING)
                or h['content_range'] != CONTENT_RANGE or h['etag'] != ETAG
                or h['last_modified'] != LAST_MODIFIED or h['content_encoding'] != 'identity'
                or h['content_type'] != 'application/vnd.android.package-archive'
                or h['transfer_encoding'] is not None or h['location'] is not None):
            raise ValueError('conditional Range differs from exact frozen remainder; no body accepted')
        for name in ('Content-Length', 'Content-Range', 'Content-Type', 'ETag', 'Last-Modified'):
            if len(response.headers.get_all(name, [])) != 1:
                raise ValueError('ambiguous identity header')
        next_progress = 16 * 1024 * 1024
        while appended < REMAINING:
            if time.monotonic() - start > 540:
                raise TimeoutError('whole continuation deadline')
            disk_floor()
            path_fd_size(fd, PART, PREFIX_SIZE + appended)
            block = response.read1(min(1024 * 1024, REMAINING - appended))
            if time.monotonic() - start > 540:
                raise TimeoutError('whole continuation deadline after read')
            if not block:
                raise ValueError('incomplete exact Range body')
            if appended + len(block) > REMAINING:
                raise ValueError('Range body exceeds exact remainder')
            view = memoryview(block)
            written = 0
            while view:
                disk_floor(len(view))
                path_fd_size(fd, PART, PREFIX_SIZE + appended + written)
                n = os.write(fd, view)
                if n <= 0:
                    raise OSError('short append')
                written += n
                view = view[n:]
            digest.update(block)
            md5.update(block)
            appended += len(block)
            path_fd_size(fd, PART, PREFIX_SIZE + appended)
            disk_floor()
            if appended >= next_progress:
                print(json.dumps({'appended_bytes': appended, 'complete_bytes_so_far': PREFIX_SIZE + appended,
                                  'remaining_bytes': REMAINING - appended, 'observed_utc': now()}), flush=True)
                next_progress += 16 * 1024 * 1024
        os.fsync(fd)
        before_readback = path_fd_size(fd, PART, SIZE)
        prefix_after, unused = hash_fd(fd, PREFIX_SIZE)
        full_after, md5_after = hash_fd(fd, SIZE, both=True)
        if (prefix_after.hexdigest() != PREFIX_SHA or full_after.hexdigest() != digest.hexdigest()
                or md5_after.hexdigest() != md5.hexdigest()
                or path_fd_size(fd, PART, SIZE) != before_readback):
            raise ValueError('prefix/full SHA and stable file readback failed')
        if os.path.lexists(TARGET):
            raise ValueError('final owned destination appeared')
        # Same inode, no copied prefix; only the verified tail has been appended.
        os.rename(PART, TARGET)
        os.fchmod(fd, 0o444)
        os.fsync(fd)
        final_f9 = f9(os.fstat(fd))
        if (f9(TARGET.lstat()) != final_f9 or final_f9[0:2] != PREFIX_F9[0:2]
                or final_f9[3:6] != PREFIX_F9[3:6] or final_f9[6] != str(SIZE)):
            raise ValueError('final same-inode custody')
        directory_fd = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        R.update(complete=True, source_input_candidate_obtained=True,
                 full_SHA_readback_verified=True, prefix_SHA_readback_unchanged=True,
                 same_inode_append_only=True, tail_bytes_downloaded=appended,
                 full_candidate_bytes=SIZE, body_md5=md5_after.hexdigest(),
                 observed_ETag_equals_body_md5=(ETAG.strip('"').lower() == md5_after.hexdigest()),
                 artifact={'path': str(TARGET), 'bytes': SIZE, 'sha256': full_after.hexdigest(),
                           'identity': final_f9, 'sha256_scope': 'all complete on-disk bytes read back after append'},
                 prefix_after={'bytes': PREFIX_SIZE, 'sha256': prefix_after.hexdigest()})
    finally:
        if conn is not None:
            conn.close()
        R['tail_complete_blocks_recorded_bytes'] = appended
        R['actual_inode_size_at_terminal'] = os.fstat(fd).st_size
        R['elapsed_seconds'] = time.monotonic() - start
        os.close(fd)


try:
    main()
except Exception as exc:
    R.update(complete=False, error=repr(exc), traceback=traceback.format_exc())
finally:
    if not bookends():
        R.update(complete=False, input_bookends_error='one or more original held source inputs changed or missing')
    for fd, *_ in HELD:
        os.close(fd)
    R['completed_utc'] = now()
    try:
        data = (json.dumps(R, sort_keys=True, indent=2) + '\n').encode()
        if len(data) > 32768:
            raise ValueError('terminal receipt budget')
        p = OUT / 'RESUME-TRANSPORT-RESULT.json'
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'complete': R['complete'], 'artifact': R.get('artifact'),
                          'result': {'path': str(p), 'bytes': len(data), 'sha256': sha(data)},
                          'error': R.get('error')}, sort_keys=True), flush=True)
    except Exception:
        R['complete'] = False
        traceback.print_exc()
raise SystemExit(0 if R['complete'] else 1)
