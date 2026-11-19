#!/usr/bin/env python3
"""Two original mirror metadata pages and publisher HEAD; never fetch APK bodies."""
import datetime
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import resource
import ssl
import urllib.parse

ROOT = Path('/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1')
PARSER_SHA = '54a6d148801a824d4309184408f43913688f5f0eead540ac4fe9bd6513a30e18'
TARGETS = [
    {'package': 'com.amazon.mShop.android.shopping', 'selected_version': '32.20.2.100',
     'method': 'GET', 'url': 'https://apk.house/amazon-shopping', 'kind': 'original_public_mirror_metadata'},
    {'package': 'com.rytong.airchina', 'selected_version': '7.53.4',
     'method': 'GET', 'url': 'https://www.996.com/download/30833/', 'kind': 'original_public_mirror_metadata'},
    {'package': 'com.szzc', 'selected_version': '9.6.3', 'selected_APK_bytes': 220522994,
     'selected_APK_sha256': '7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96',
     'method': 'HEAD', 'url': 'https://static.zuchecdn.com/download/SZZC.apk', 'kind': 'publisher_endpoint_headers_only'}]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_new(path, data):
    if len(data) > 2 * 1024 * 1024:
        raise RuntimeError('output budget')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def main():
    if os.getuid() == 0 or os.sched_getaffinity(0) != {31}:
        raise RuntimeError('ordinary account and CPU31 required')
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    fd = os.open(ROOT / 'parse_public_metadata.py', os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        parser = f.read(15143)
    if len(parser) != 15142 or sha(parser) != PARSER_SHA:
        raise RuntimeError('frozen parser mismatch')
    ns = {'__name__': 'frozen_public_parser', '__file__': str(ROOT / 'parse_public_metadata.py')}
    exec(compile(parser, ns['__file__'], 'exec'), ns)
    rows = []
    started = now()
    for item in TARGETS:
        row = dict(item, started_utc=now(), authentication_used=False, cookies_used=False,
                   redirects_followed=0, APK_body_read=False, source_identity_requalified=False)
        u = urllib.parse.urlsplit(item['url'])
        conn = http.client.HTTPSConnection(u.hostname, 443, timeout=15,
                                           context=ssl.create_default_context())
        try:
            conn.request(item['method'], u.path, headers={
                'User-Agent': 'Pocket4-public-version-metadata-audit',
                'Accept': 'text/html,*/*;q=0.1', 'Accept-Encoding': 'identity', 'Connection': 'close'})
            response = conn.getresponse()
            row.update(http_status=response.status, http_date=response.getheader('Date'),
                       content_type=response.getheader('Content-Type'),
                       content_length=response.getheader('Content-Length'),
                       etag=response.getheader('ETag'), last_modified=response.getheader('Last-Modified'),
                       redirect_location=response.getheader('Location'), final_url=item['url'])
            if response.status != 200:
                raise ValueError('non-200 response, no redirect or alternate origin requested')
            if item['method'] == 'HEAD':
                row.update(status='PUBLISHER_HEADERS_OBSERVED_NO_BODY_IDENTITY_CLAIM',
                           HTTP_body_read_calls=0, version_observed_from_headers=None,
                           content_length_matches_selected_APK=(row['content_length'] == str(item['selected_APK_bytes'])),
                           equal_length_does_not_prove_equal_content=True)
            else:
                if not (row['content_type'] or '').lower().startswith('text/html'):
                    raise ValueError('non-HTML body refused')
                if response.getheader('Content-Encoding', 'identity') != 'identity':
                    raise ValueError('unexpected content encoding')
                if row['content_length'] and int(row['content_length']) > 2 * 1024 * 1024:
                    raise ValueError('declared metadata body budget')
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise ValueError('actual metadata body budget')
                if row['content_length'] and len(body) != int(row['content_length']):
                    raise ValueError('metadata length mismatch')
                source = body.decode('utf-8')
                row.update(body_bytes=len(body), body_sha256=sha(body), retained_body=write_new(
                    ROOT / 'actual/public-response-bodies' / ('selected-origin-' + item['package'] + '.http-body.gz'),
                    gzip.compress(body, compresslevel=1, mtime=0)))
                if item['package'] == 'com.amazon.mShop.android.shopping':
                    headings = [ns['visible'](x) for x in re.findall(r'<h2\b[^>]*>(.*?)</h2>', source, re.S)]
                    versions = [m.group(1) for x in headings
                                if (m := re.fullmatch(r'Amazon Shopping\s+([0-9.]+)', x))]
                    if not versions:
                        raise ValueError('no Amazon main version heading')
                    row.update(observed_version=versions[0], version_field='first Amazon Shopping h2 version heading',
                               main_heading_versions=versions[:8], primary_package_manifest_checked=False)
                else:
                    text = ns['visible'](source)
                    versions = re.findall(r'版本\s*[：:]\s*([0-9.]+)', text)
                    if len(versions) != 1:
                        raise ValueError('not exactly one main 996 version field')
                    row.update(observed_version=versions[0], version_field='single visible 版本 field',
                               primary_package_manifest_checked=False)
                row.update(status='ORIGINAL_MIRROR_VERSION_OBSERVED',
                           comparison=ns['compare'](item, {'version': row['observed_version']}),
                           mirror_metadata_is_not_publisher_or_signature_verification=True)
        except Exception as exc:
            row.update(status='NO_CURRENT_VERSION_CLAIM',
                       error=type(exc).__name__ + ': ' + str(exc)[:500])
        finally:
            conn.close()
        row['completed_utc'] = now()
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False, sort_keys=True), flush=True)
    result = {'schema': 'pocket4-original-selected-channel-metadata-supplement-v1',
              'started_utc': started, 'completed_utc': now(),
              'frozen_parser_sha256': PARSER_SHA,
              'current_freshness_source_sha256': '459a5fd3b74ac186bb0bd19d30874b36ba9b54e2453824b38410843e24289918',
              'current_registry_source_sha256': '62df07622afa60960863dd9721cfd8b46a67b74076355c150534052f1f58abb1',
              'APK_body_downloads': 0, 'SDK_or_Android_calls': 0,
              'source_inputs_changed': False, 'account_or_credentials_accessed': False,
              'authoritative_play_metadata_TTL_renewed': False,
              'installed': False, 'runtime_qualified': False,
              'business_qualified': False, 'production_ready': False, 'rows': rows}
    pin = write_new(ROOT / 'actual/SELECTED-ORIGIN-SUPPLEMENT.json',
                    (json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'result': pin}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
