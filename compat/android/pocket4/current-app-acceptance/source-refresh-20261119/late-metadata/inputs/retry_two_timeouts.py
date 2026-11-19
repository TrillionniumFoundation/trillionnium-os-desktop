#!/usr/bin/env python3
"""One bounded retry of the two recorded public-page read timeouts only."""
import datetime
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import resource
import ssl
import urllib.parse

ROOT = Path('/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1')
COLLECTION_SHA = 'f8ff39d718e624cdceb817affb760980333c7c3d9e115e90510be384c5efa5ac'
PARSER_SHA = '54a6d148801a824d4309184408f43913688f5f0eead540ac4fe9bd6513a30e18'
PARSER_BYTES = 15142
TARGETS = ('com.lianjia.beike', 'tv.danmaku.bili')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_new(path, data):
    if len(data) > 3 * 1024 * 1024:
        raise RuntimeError('single output budget')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def main():
    if os.getuid() == 0 or os.sched_getaffinity(0) != {31}:
        raise RuntimeError('ordinary account and CPU31 required')
    resource.setrlimit(resource.RLIMIT_AS, (224 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (3 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser_path = ROOT / 'parse_public_metadata.py'
    fd = os.open(parser_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        parser = source.read(PARSER_BYTES + 1)
    if len(parser) != PARSER_BYTES or sha(parser) != PARSER_SHA:
        raise RuntimeError('frozen source parser pin mismatch')
    ns = {'__name__': 'frozen_public_metadata_parser', '__file__': str(parser_path)}
    exec(compile(parser, str(parser_path), 'exec'), ns)
    receipt = ns['read_pinned'](ROOT / 'actual/HTTP-OBSERVATIONS.json', COLLECTION_SHA, 128 * 1024)
    original = json.loads(receipt)
    by_package = {r['package']: r for r in original['rows']}
    failed = {r['package'] for r in original['rows'] if r['status'] == 'ERROR_NO_LATEST_CLAIM'}
    if failed != set(TARGETS):
        raise RuntimeError('original timeout set changed')
    rows = []
    started = now()
    for package in TARGETS:
        previous = by_package[package]
        if previous.get('error') != 'TimeoutError: The read operation timed out':
            raise RuntimeError('retry is restricted to the original read timeout')
        url = 'https://m.app.mi.com/details?id=' + package
        if previous['url'] != url:
            raise RuntimeError('original fixed public URL mismatch')
        row = {k: previous[k] for k in ('package', 'name', 'url', 'selected_version', 'selected_version_code')}
        row.update(started_utc=now(), original_failure_preserved=True,
                   original_failure_completed_utc=previous['completed_utc'],
                   authentication_used=False, cookies_used=False, redirects_followed=0,
                   APK_or_delivery_requested=False)
        conn = http.client.HTTPSConnection('m.app.mi.com', 443, timeout=20,
                                           context=ssl.create_default_context())
        try:
            conn.request('GET', '/details?id=' + package, headers={
                'User-Agent': 'Pocket4-public-version-metadata-audit',
                'Accept': 'text/html', 'Accept-Encoding': 'identity', 'Connection': 'close'})
            response = conn.getresponse()
            ctype = response.getheader('Content-Type', '')
            row.update(http_status=response.status, http_date=response.getheader('Date'),
                       content_type=ctype, final_url=url)
            if response.status != 200 or not ctype.lower().startswith('text/html'):
                raise ValueError('not an ordinary successful public HTML response')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('unexpected content encoding')
            length = response.getheader('Content-Length')
            if length and int(length) > 2 * 1024 * 1024:
                raise ValueError('declared metadata body budget')
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024 or (length and len(body) != int(length)):
                raise ValueError('complete metadata body budget/length')
            row.update(body_bytes=len(body), body_sha256=sha(body), retained_body=write_new(
                ROOT / 'actual/public-response-bodies' / ('timeout-retry-' + package + '.http-body.gz'),
                gzip.compress(body, compresslevel=1, mtime=0)))
            observed = ns['parse_xiaomi'](body.decode('utf-8'), package)
            row.update(observation=observed, comparison=ns['compare'](row, observed),
                       status='PUBLIC_METADATA_PARSED')
        except Exception as exc:
            row.update(status='NO_CURRENT_VERSION_CLAIM', comparison='UNRESOLVED',
                       error=type(exc).__name__ + ': ' + str(exc)[:500])
        finally:
            conn.close()
        row['completed_utc'] = now()
        rows.append(row)
        print(json.dumps({'package': package, 'status': row['status'],
                          'comparison': row['comparison'],
                          'version': row.get('observation', {}).get('version'),
                          'error': row.get('error')}, sort_keys=True), flush=True)
    if ns['read_pinned'](ROOT / 'actual/HTTP-OBSERVATIONS.json', COLLECTION_SHA, 128 * 1024) != receipt:
        raise RuntimeError('original failure evidence changed')
    result = {'schema': 'pocket4-public-source-two-timeout-retry-v1',
              'started_utc': started, 'completed_utc': now(),
              'original_HTTP_receipt': {'bytes': len(receipt), 'sha256': COLLECTION_SHA},
              'frozen_parser': {'bytes': PARSER_BYTES, 'sha256': PARSER_SHA},
              'original_failure_evidence_unchanged': True, 'requests': 2,
              'APK_or_delivery_requests': 0, 'Android_or_SDK_calls': 0,
              'account_or_credentials_accessed': False, 'source_inputs_changed': False,
              'authoritative_play_metadata_TTL_renewed': False,
              'activation_metadata_revalidated': False,
              'installed': False, 'runtime_qualified': False,
              'business_qualified': False, 'production_ready': False, 'rows': rows}
    pin = write_new(ROOT / 'actual/TWO-TIMEOUT-RETRY.json',
                    (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'result': pin}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
