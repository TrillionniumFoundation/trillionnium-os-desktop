#!/usr/bin/env python3
"""HEAD only at the exact HTTPS publisher target observed in the retained 301."""
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import resource
import ssl

root = Path('/home/qq/work/p4-source-freshness-check-5cd1-20261119-r1')
source_sha = '8a250dedce22889e967e498e7c5a29afdee900751fd61b3412c0aca1b1d8f637'
target = 'https://edfs.zuchecdn.com/android-package/SZZC.apk'
assert os.getuid() != 0 and os.sched_getaffinity(0) == {31}
resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
fd = os.open(root / 'actual/SELECTED-ORIGIN-SUPPLEMENT.json', os.O_RDONLY | os.O_NOFOLLOW)
with os.fdopen(fd, 'rb') as f:
    raw = f.read(5148)
assert len(raw) == 5147 and hashlib.sha256(raw).hexdigest() == source_sha
old = next(x for x in json.loads(raw)['rows'] if x['package'] == 'com.szzc')
assert old['http_status'] == 301 and old['redirect_location'] == target
assert old['method'] == 'HEAD' and old['APK_body_read'] is False
row = {'schema': 'pocket4-observed-publisher-redirect-head-v1',
       'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'parent_receipt': {'bytes': len(raw), 'sha256': source_sha},
       'package': 'com.szzc', 'selected_version': '9.6.3',
       'selected_APK_bytes': 220522994,
       'selected_APK_sha256': '7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96',
       'request_url': target, 'method': 'HEAD', 'automatic_redirects_followed': 0,
       'prior_observed_publisher_redirect_target_used': True,
       'authentication_used': False, 'cookies_used': False,
       'HTTP_body_read_calls': 0, 'APK_body_bytes_read': 0,
       'version_observed_from_headers': None, 'source_identity_requalified': False,
       'equal_length_does_not_prove_equal_content': True,
       'SDK_or_Android_calls': 0, 'source_inputs_changed': False,
       'installed': False, 'runtime_qualified': False,
       'business_qualified': False, 'production_ready': False}
conn = http.client.HTTPSConnection('edfs.zuchecdn.com', 443, timeout=15,
                                   context=ssl.create_default_context())
try:
    conn.request('HEAD', '/android-package/SZZC.apk', headers={
        'User-Agent': 'Pocket4-public-version-metadata-audit',
        'Accept-Encoding': 'identity', 'Connection': 'close'})
    response = conn.getresponse()
    row.update(http_status=response.status, http_date=response.getheader('Date'),
               content_length=response.getheader('Content-Length'),
               content_type=response.getheader('Content-Type'),
               etag=response.getheader('ETag'), last_modified=response.getheader('Last-Modified'),
               redirect_location=response.getheader('Location'))
    row['content_length_matches_selected_APK'] = response.status == 200 and row['content_length'] == '220522994'
    row['status'] = 'PUBLISHER_HEADERS_OBSERVED_NO_APK_VERSION_OR_SHA_CLAIM'
    response.close()
except Exception as exc:
    row.update(status='HEAD_UNRESOLVED', error=type(exc).__name__ + ': ' + str(exc)[:500])
finally:
    conn.close()
row['completed_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
data = (json.dumps(row, indent=2, sort_keys=True) + '\n').encode()
out = root / 'actual/PUBLISHER-REDIRECT-HEAD.json'
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps({'result': {'path': str(out), 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest()},
                  'observation': row}, sort_keys=True), flush=True)
