#!/usr/bin/env python3
"""Resolve public, observed publisher download controls without App actions."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path('/home/alex/work/pocket4-vendor-metadata-20261106-r3')
REQUESTS = [
    {'name': 'didi_main_js', 'url': 'https://website.didiglobal.com/dist/js/main.9a074ac6.js'},
    {'name': 'jd_download_js', 'url': 'https://storage.360buyimg.com/jxfe/legos/u/fireye_download/page/downloadApp/js/index.9b319da8.js'},
    {'name': 'zbj_index_js', 'url': 'https://app.zbj.com/bz/pc/js/index.js?13213'},
    {'name': 'railway_live_download', 'url': 'https://mobile.12306.cn/otsmobile/ah5/otsmobile/down/appDown',
     'method': 'POST', 'data': b'', 'headers': {'Content-Type': 'text/plain;charset=UTF-8', 'cn': 'otherBrowser-offlineH5-'}},
    {'name': 'ctrip_version', 'url': 'https://m.ctrip.com/restapi/soa2/14984/json/getConfigUrl',
     'method': 'POST', 'data': b'{"config":"versionInfo"}', 'headers': {'Content-Type': 'application/json;charset=utf-8'}},
]


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise RuntimeError('NON_HTTPS_REDIRECT:' + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(item):
    name, url = item['name'], item['url']
    if name == 'railway_live_download':
        url += '?' + urllib.parse.urlencode({'baseDTO.time_str': datetime.datetime.now().strftime('%Y%m%d%H%M%S')})
    row = {'name': name, 'source_url': url, 'method': item.get('method', 'GET'),
           'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'automatic_retry': False, 'account_actions': 0, 'App_actions': 0}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 17) AppleWebKit/537.36', **item.get('headers', {})}
        request = urllib.request.Request(url, data=item.get('data'), headers=headers, method=row['method'])
        opener = urllib.request.build_opener(HttpsOnly)
        with opener.open(request, timeout=30) as response:
            row.update(final_url=response.url, http_status=response.status, content_type=response.headers.get('Content-Type'))
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise RuntimeError('PUBLIC_METADATA_RESPONSE_BOUND')
        with (ROOT / (name + '.response')).open('xb') as out:
            out.write(raw)
        text = raw.decode('utf-8', 'strict')
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        row['links'] = sorted(set(re.findall(r'''(?:https?:)?//[^\s<>"']+''', text)))[:100]
        row['download_contexts'] = [text[max(0, m.start() - 180):m.end() + 300]
                                    for m in list(re.finditer(r'(?i)\.apk|androidurl|android_url|downloadurl|download_url', text))[:20]]
        if name in ('railway_live_download', 'ctrip_version'):
            row['public_response'] = text[:16000]
        row['status'] = 'PUBLIC_METADATA_READ'
    except BaseException as error:
        row.update(status='PUBLIC_METADATA_FAILED', error_type=type(error).__name__, error=str(error)[:500])
    print(json.dumps(row), flush=True)
    return row


def main():
    ROOT.mkdir(mode=0o700)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(fetch, REQUESTS))
    with (ROOT / 'result.json').open('x') as out:
        json.dump({'schema': 'pocket4-public-vendor-download-metadata-v1', 'records': rows}, out, indent=2)


if __name__ == '__main__':
    main()
