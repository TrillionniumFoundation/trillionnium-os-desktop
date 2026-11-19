#!/usr/bin/env python3
"""One conditional GET of the newly observed publisher artifact; no installation."""
import datetime
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
SIZE = 220498418
ETAG = '"108948280DD69A433DD2AEFD4585FD2B"'
LAST_MODIFIED = 'Wed, 18 Nov 2026 13:23:40 GMT'
HEAD_SHA = '73fc14312fe687859899e9a1f9fa2d2ed3d3a52d90dcdd29ee1642a7845c64fd'
R = {'schema': 'pocket4-szzc-observed-publisher-candidate-transport-v1',
     'complete': False, 'source_identity_verified': False, 'signature_verified': False,
     'previous_selected_APK_changed': False, 'source_registry_changed': False,
     'APK_installed': False, 'Android_calls': 0, 'SDK_calls': 0,
     'credentials_or_userdata_accessed': False, 'authentication_used': False,
     'cookies_used': False, 'redirects_followed': 0,
     'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}


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
        raise ValueError('24GiB free-disk floor during exact candidate transfer')


def main():
    if os.getuid() != 1000 or os.sched_getaffinity(0) != {31}:
        raise ValueError('ordinary qq and explicit CPU31 required')
    resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    for directory in (ROOT, ROOT / 'inputs'):
        ds = directory.lstat()
        if directory.resolve() != directory or not stat.S_ISDIR(ds.st_mode) or ds.st_uid != 1000:
            raise ValueError('canonical owned source directory required')
    head_path = ROOT / 'inputs/PUBLISHER-REDIRECT-HEAD.json'
    if head_path.resolve() != head_path:
        raise ValueError('aliased HEAD pathname rejected')
    hd = os.open(head_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(hd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 1000 or st.st_nlink != 1:
            raise ValueError('HEAD source ownership')
        if f9(head_path.lstat()) != f9(st):
            raise ValueError('HEAD pathname/FD identity mismatch')
        raw = os.pread(hd, 1503, 0)
        if len(raw) != 1502 or sha(raw) != HEAD_SHA:
            raise ValueError('original observed HEAD pin')
        head = json.loads(raw)
        if (head['http_status'] != 200 or head['content_length'] != str(SIZE)
                or head['etag'] != ETAG or head['last_modified'] != LAST_MODIFIED
                or head['request_url'] != 'https://edfs.zuchecdn.com/android-package/SZZC.apk'):
            raise ValueError('original observed publisher identity')
        R['original_HEAD'] = {'bytes': len(raw), 'sha256': sha(raw), 'identity': f9(st)}
        OUT.mkdir(mode=0o700, exist_ok=False)
        disk_floor(SIZE)
        R['started_utc'] = now()
        start = time.monotonic()
        part = OUT / 'com.szzc.publisher-current.apk.part'
        target = OUT / 'com.szzc.publisher-current.apk'
        conn = http.client.HTTPSConnection('edfs.zuchecdn.com', 443, timeout=15,
                                           context=ssl.create_default_context())
        total = 0
        digest = hashlib.sha256()
        md5 = hashlib.md5()
        try:
            conn.request('GET', '/android-package/SZZC.apk', headers={
                'User-Agent': 'Pocket4-publisher-source-qualification',
                'Accept': 'application/vnd.android.package-archive',
                'Accept-Encoding': 'identity', 'Connection': 'close', 'If-Match': ETAG})
            response = conn.getresponse()
            R['http'] = {'method': 'GET', 'url': head['request_url'],
                         'conditional_if_match': ETAG, 'status': response.status,
                         'date': response.getheader('Date'),
                         'content_length': response.getheader('Content-Length'),
                         'content_type': response.getheader('Content-Type'),
                         'etag': response.getheader('ETag'),
                         'last_modified': response.getheader('Last-Modified'),
                         'content_encoding': response.getheader('Content-Encoding', 'identity'),
                         'location': response.getheader('Location')}
            h = R['http']
            if (h['status'] != 200 or h['content_length'] != str(SIZE) or h['etag'] != ETAG
                    or h['last_modified'] != LAST_MODIFIED or h['content_encoding'] != 'identity'
                    or h['content_type'] != 'application/vnd.android.package-archive'):
                raise ValueError('conditional GET differs from frozen HEAD; no body accepted')
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                while True:
                    if time.monotonic() - start > 150:
                        raise TimeoutError('whole transfer deadline')
                    disk_floor()
                    block = response.read(min(1024 * 1024, SIZE - total + 1))
                    if not block:
                        break
                    if total + len(block) > SIZE:
                        raise ValueError('body exceeds exact observed size')
                    digest.update(block)
                    md5.update(block)
                    view = memoryview(block)
                    while view:
                        disk_floor(len(view))
                        n = os.write(fd, view)
                        if n <= 0:
                            raise OSError('short file write')
                        view = view[n:]
                    total += len(block)
                    disk_floor()
                os.fsync(fd)
            finally:
                os.close(fd)
            if total != SIZE:
                raise ValueError('incomplete exact-size publisher body')
            os.rename(part, target)
            os.chmod(target, 0o444)
            pin = {'path': str(target), 'bytes': total, 'sha256': digest.hexdigest(),
                   'identity': f9(os.stat(target, follow_symlinks=False)),
                   'sha256_scope': 'all bytes streamed to the new owned output; SDK stage rechecks full on-disk SHA'}
            R.update(artifact=pin, complete=True, source_input_candidate_obtained=True,
                     full_SHA_readback_verified=False, body_md5=md5.hexdigest(),
                     observed_ETag_equals_body_md5=(ETAG.strip('"').lower() == md5.hexdigest()),
                     total_downloaded_bytes=total)
        finally:
            conn.close()
            R['total_bytes_received_before_terminal'] = total
            R['elapsed_seconds'] = time.monotonic() - start
        if (f9(os.fstat(hd)) != f9(st) or f9(head_path.lstat()) != f9(st)
                or sha(os.pread(hd, 1503, 0)) != HEAD_SHA):
            raise ValueError('HEAD source bookends changed')
        R['original_HEAD_bookends_unchanged'] = True
    finally:
        os.close(hd)


try:
    main()
except Exception as exc:
    R.update(complete=False, error=repr(exc), traceback=traceback.format_exc())
finally:
    R['completed_utc'] = now()
    if OUT.exists():
        data = (json.dumps(R, sort_keys=True, indent=2) + '\n').encode()
        if len(data) > 32768:
            raise RuntimeError('terminal receipt budget')
        p = OUT / 'TRANSPORT-RESULT.json'
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        print(json.dumps({'complete': R['complete'], 'artifact': R.get('artifact'),
                          'result': {'path': str(p), 'bytes': len(data), 'sha256': sha(data)},
                          'error': R.get('error')}, sort_keys=True), flush=True)
raise SystemExit(0 if R['complete'] else 1)
