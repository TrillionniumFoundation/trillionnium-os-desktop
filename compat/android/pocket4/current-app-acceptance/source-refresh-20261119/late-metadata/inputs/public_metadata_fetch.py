#!/usr/bin/env python3
"""Fixed, unauthenticated public metadata GETs; no delivery or activation actions."""
import datetime
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import resource
import signal
import ssl
import stat
import time
import urllib.parse

ROOT = Path('/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1')
PLAN_SHA = '570b4ee5f0796f94066752b388dec66066a489dd21c5e2fd38356b4044cac725'
ALLOWED_HOSTS = {'play.google.com', 'm.app.mi.com', 'm.app.so.com',
                 'a.app.qq.com', 'api.github.com', 'product-details.mozilla.org',
                 'developer.android.com'}
MAX_BODY = 2 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned_regular(path, expected_sha=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid():
            raise RuntimeError('not an ordinary owned single-link input')
        data = os.read(fd, st.st_size + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                  'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(data) != st.st_size
                or any(getattr(after, k) != getattr(st, k) for k in fields)):
            raise RuntimeError('input changed during complete read')
        if expected_sha and sha(data) != expected_sha:
            raise RuntimeError('input SHA mismatch')
        return data, {'bytes': len(data), 'sha256': sha(data), 'device': st.st_dev,
                      'inode': st.st_ino, 'mtime_ns': st.st_mtime_ns,
                      'ctime_ns': st.st_ctime_ns}
    finally:
        os.close(fd)


def exclusive_write(path, data):
    if len(data) > 3 * 1024 * 1024:
        raise RuntimeError('output file budget')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as out:
            out.write(data)
            out.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def main():
    if os.getuid() == 0 or os.sched_getaffinity(0) != {31}:
        raise RuntimeError('requires ordinary account and explicit CPU31 affinity')
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise RuntimeError('unexpected inherited signal state')
    resource.setrlimit(resource.RLIMIT_AS, (224 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (3 * 1024 * 1024,) * 2)
    os.umask(0o077)
    plan_bytes, plan_pin = pinned_regular(ROOT / 'PLAN.json', PLAN_SHA)
    worker_bytes, worker_pin = pinned_regular(Path(__file__))
    plan = json.loads(plan_bytes)
    if len(plan['requests']) != 31 or len({x['package'] for x in plan['requests']}) != 31:
        raise RuntimeError('unexpected request roster')
    for x in plan['requests']:
        u = urllib.parse.urlsplit(x['url'])
        if (u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.port not in (None, 443)
                or u.username or u.password or u.fragment
                or u.path.endswith(('.apk', '.apks', '.zip', '.img', '.gz'))):
            raise RuntimeError('non-metadata URL rejected')
    outroot = ROOT / 'actual'
    outroot.mkdir(mode=0o700, exist_ok=False)
    rawdir = outroot / 'public-response-bodies'
    rawdir.mkdir(mode=0o700)
    started = now()
    start_mono = time.monotonic()
    context = ssl.create_default_context()
    rows = []
    total = 0
    for item in plan['requests']:
        if time.monotonic() - start_mono > 360:
            raise RuntimeError('whole collection wall deadline')
        row = dict(item, started_utc=now(), authentication_used=False,
                   cookies_used=False, account_or_device_profile_used=False,
                   APK_or_delivery_requested=False, redirects_followed=0)
        u = urllib.parse.urlsplit(item['url'])
        conn = http.client.HTTPSConnection(u.hostname, 443, timeout=12, context=context)
        try:
            target = u.path + ('?' + u.query if u.query else '')
            conn.request('GET', target, headers={
                'User-Agent': 'Pocket4-public-version-metadata-audit',
                'Accept': 'application/json,text/html;q=0.9',
                'Accept-Encoding': 'identity',
                'Connection': 'close'})
            response = conn.getresponse()
            ctype = response.getheader('Content-Type', '')
            row.update(http_status=response.status, http_date=response.getheader('Date'),
                       content_type=ctype, final_url=item['url'])
            if response.status != 200:
                row.update(status='HTTP_NOT_200_NO_LATEST_CLAIM',
                           redirect_location=response.getheader('Location'))
            elif not (ctype.lower().startswith('text/html')
                      or ctype.lower().startswith('application/json')):
                row['status'] = 'CONTENT_TYPE_REFUSED_NO_BODY_READ'
            elif response.getheader('Content-Encoding', 'identity') != 'identity':
                row['status'] = 'UNEXPECTED_CONTENT_ENCODING_REFUSED'
            else:
                length = response.getheader('Content-Length')
                if length and int(length) > MAX_BODY:
                    raise RuntimeError('declared metadata body exceeds cap')
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY or total + len(body) > MAX_TOTAL:
                    raise RuntimeError('actual metadata body budget exceeded')
                total += len(body)
                if length and len(body) != int(length):
                    raise RuntimeError('metadata content length mismatch')
                body.decode('utf-8', errors='strict')
                compressed = gzip.compress(body, compresslevel=1, mtime=0)
                pin = exclusive_write(rawdir / (item['package'] + '.http-body.gz'), compressed)
                row.update(status='PUBLIC_METADATA_BODY_RETAINED_PARSE_PENDING',
                           body_bytes=len(body), body_sha256=sha(body), retained_body=pin)
        except Exception as exc:
            row.update(status='ERROR_NO_LATEST_CLAIM', error=type(exc).__name__ + ': ' + str(exc)[:500])
        finally:
            conn.close()
        row['completed_utc'] = now()
        rows.append(row)
        print(json.dumps({'package': row['package'], 'status': row['status'],
                          'http_status': row.get('http_status'),
                          'body_bytes': row.get('body_bytes')}, sort_keys=True), flush=True)
    _, after_plan = pinned_regular(ROOT / 'PLAN.json', plan_pin['sha256'])
    _, after_worker = pinned_regular(Path(__file__), worker_pin['sha256'])
    if plan_pin != after_plan or worker_pin != after_worker:
        raise RuntimeError('source bookends changed')
    result = {
        'schema': 'pocket4-readonly-public-source-metadata-collection-v1',
        'started_utc': started, 'completed_utc': now(), 'plan': plan_pin,
        'worker': worker_pin, 'source_bookends_unchanged': True,
        'request_count': len(rows), 'total_metadata_body_bytes': total,
        'source_inputs_changed': False, 'APK_or_delivery_requests': 0,
        'Android_or_SDK_calls': 0, 'account_or_credentials_accessed': False,
        'source_authenticity_or_signature_reverified': False,
        'authoritative_play_metadata_TTL_renewed': False,
        'original_GET_ITEMS_expires_utc': plan['original_GET_ITEMS_expires_utc'],
        'excluded_packages': plan['excluded_packages'],
        'installed': False, 'runtime_qualified': False,
        'business_qualified': False, 'production_ready': False, 'rows': rows}
    pin = exclusive_write(outroot / 'HTTP-OBSERVATIONS.json',
                          (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'result': pin, 'request_count': len(rows),
                      'retained': sum(x['status'] == 'PUBLIC_METADATA_BODY_RETAINED_PARSE_PENDING' for x in rows),
                      'metadata_body_bytes': total, 'production_ready': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
