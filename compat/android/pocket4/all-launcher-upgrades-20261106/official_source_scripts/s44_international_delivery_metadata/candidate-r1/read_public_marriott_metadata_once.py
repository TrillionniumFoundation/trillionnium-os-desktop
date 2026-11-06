#!/usr/bin/env python3
"""Read two observed public store HTML pages once; never retrieve an APK."""
import datetime
import fcntl
import hashlib
import html.parser
import json
import os
from pathlib import Path
import signal
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/home/alex/work/pocket4-marriott-official-delivery-metadata-20261106-s44-r1')
URLS = (
    'https://a.app.qq.com/o/simple.jsp?pkgname=com.marriott.mrt',
    'https://sj.qq.com/appdetail/com.marriott.mrt',
)
HOSTS = {'a.app.qq.com', 'sj.qq.com'}
PACKAGE = 'com.marriott.mrt'
MAX_BODY = 2 * 1024 * 1024
MAX_ERROR_BODY = 65536
MAX_TOTAL_SECONDS = 120
TLS = ssl.create_default_context()


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def census():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            value = os.fstat(fd)
            result[name] = [os.readlink('/proc/self/fd/' + name), value.st_dev, value.st_ino,
                           value.st_mode, value.st_uid, value.st_gid, value.st_nlink,
                           fcntl.fcntl(fd, fcntl.F_GETFD), fcntl.fcntl(fd, fcntl.F_GETFL)]
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno == 9:
                continue
            raise
    return result


def save(name, raw):
    need(name in {'page-01.html', 'page-02.html', 'page-01.error-body', 'page-02.error-body', 'result.json'},
         'CLOSED_OUTPUT_NAME')
    target = ROOT / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        need(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink == 1, 'OWNED_REGULAR_OUTPUT')
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'WRITE_PROGRESS')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(target), 'bytes': len(raw), 'sha256': digest(raw)}


class ObservedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, record):
        self.record = record

    def redirect_request(self, request, response, code, message, headers, newurl):
        self.record.append({'from': request.full_url, 'to': newurl, 'status': code})
        value = urllib.parse.urlsplit(newurl)
        need(len(self.record) <= 4 and value.scheme == 'https' and value.hostname in HOSTS
             and value.username is None and value.password is None and value.port in (None, 443),
             'UNREVIEWED_REDIRECT_STOP_NO_ALTERNATIVE_ROUTE')
        return super().redirect_request(request, response, code, message, headers, newurl)


class PublicScripts(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.collect = None
        self.scripts = []
        self.apk_links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == 'script' and (attrs.get('id') == '__NEXT_DATA__' or attrs.get('type') == 'application/json'):
            self.collect = {'id': attrs.get('id'), 'type': attrs.get('type'), 'text': ''}
        if tag.lower() == 'a' and '.apk' in attrs.get('href', '').lower():
            self.apk_links.append({'source': 'literal_anchor_href', 'url': attrs['href'],
                                   'target_package_explicit_match': False})

    def handle_data(self, text):
        if self.collect is not None:
            self.collect['text'] += text

    def handle_endtag(self, tag):
        if tag.lower() == 'script' and self.collect is not None:
            self.scripts.append(self.collect)
            self.collect = None


def observe_public_fields(raw):
    text = raw.decode('utf-8', 'strict')
    parser = PublicScripts()
    parser.feed(text)
    rows, parse_errors, visited = [], [], 0
    package_keys = {'pkgName', 'pkgname', 'pkg_name', 'packageName', 'package_name', 'apkPackageName'}
    download_keys = {'download_url', 'downloadUrl', 'apk_url', 'apkUrl', 'apkDownloadUrl', 'apk_download_url'}
    version_keys = {'version', 'versionName', 'version_name', 'versionCode', 'version_code', 'apkVersionName'}

    def walk(value, path, package_context, package_context_path, depth):
        nonlocal visited
        visited += 1
        need(visited <= 30000 and depth <= 32 and len(rows) <= 2000, 'PUBLIC_JSON_TRAVERSAL_BOUND')
        if isinstance(value, dict):
            context = {k: value[k] for k in package_keys if k in value and isinstance(value[k], str)}
            context_path = path if context else package_context_path
            context = context or package_context
            for key, item in value.items():
                if key in download_keys | version_keys and isinstance(item, (str, int)):
                    rows.append({'json_path': path + '/' + key, 'field': key, 'value': item,
                                 'package_context': context,
                                 'package_context_json_path': context_path,
                                 'target_package_explicit_match': context_path == path and bool(context) and all(v == PACKAGE for v in context.values()),
                                 'target_package_inherited_context_only': context_path != path and bool(context) and all(v == PACKAGE for v in context.values())})
                walk(item, path + '/' + str(key), context, context_path, depth + 1)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + '/' + str(index), package_context, package_context_path, depth + 1)

    for index, script in enumerate(parser.scripts):
        try:
            value = json.loads(script['text'])
            walk(value, '/script-' + str(index), {}, None, 0)
        except (ValueError, RuntimeError) as error:
            parse_errors.append({'script': index, 'type': type(error).__name__, 'reason': str(error)[:200]})
    direct = []
    for row in rows:
        if row['field'] in download_keys and isinstance(row['value'], str):
            parsed = urllib.parse.urlsplit(row['value'])
            if parsed.scheme == 'https' and not parsed.username and not parsed.password:
                direct.append(row)
    return {'recognized_public_JSON_script_count': len(parser.scripts), 'parse_errors': parse_errors,
            'public_version_and_delivery_fields': rows, 'unfetched_https_delivery_fields': direct,
            'literal_unfetched_apk_links': parser.apk_links,
            'rendered_package_name_present': PACKAGE in text,
            'parser_did_not_execute_JavaScript': True,
            'package_or_signature_of_any_delivery_not_verified': True}


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--read-two-published-store-pages-once'], 'EXACT_NORMAL_OWNER_ENTRY')
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'NORMAL_EXISTING_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    started = time.monotonic()
    ROOT.mkdir(mode=0o700)
    result = {'schema': 'pocket4-s44-public-marriott-store-metadata-v1', 'started_utc': now(),
              'ok': False, 'meaning_of_ok': 'two bounded normal public HTML captures completed only',
              'ordinary_uid': os.getuid(), 'requests': [], 'errors': [], 'automatic_retry': False,
              'APK_downloads': 0, 'APK_signature_verified': False, 'APK_candidate_qualified': False,
              'Main_actions': 0, 'Android_commands': 0, 'UI_actions': 0, 'installs': 0,
              'permission_changes': 0, 'existing_private_files_read': 0,
              'DNS_IP_proxy_TLS_modifications': False, 'user_agent_policy': 'urllib default unmodified',
              'maximum_application_entry_requests': 2, 'maximum_redirects_per_entry': 4,
              'ordinary_resolver_internal_attempts_not_instrumented': True,
              'python_full_file_identity_verified_by_this_probe': False,
              'before_descriptor_identities': before,
              'production_ready': False, 'cleanup_eligible': False}
    try:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, MAX_TOTAL_SECONDS, 0)
        for index, url in enumerate(URLS, 1):
            remaining = MAX_TOTAL_SECONDS - (time.monotonic() - started)
            need(remaining > 5, 'TOTAL_DEADLINE_BEFORE_NEW_REQUEST')
            row = {'url': url, 'started_utc': now(), 'redirects': [], 'attempts': 1, 'automatic_retry': False}
            result['requests'].append(row)
            opener = urllib.request.build_opener(ObservedRedirect(row['redirects']), urllib.request.HTTPSHandler(context=TLS))
            try:
                with opener.open(url, timeout=min(20, remaining)) as response:
                    row.update(status=response.status, final_url=response.geturl(), headers=list(response.headers.items()))
                    need(response.status == 200, 'NON200_RESPONSE_STOP')
                    content_type = response.headers.get_content_type()
                    need(content_type in ('text/html', 'application/json', 'text/plain'), 'NON_METADATA_RESPONSE_BODY_NOT_READ')
                    length = response.headers.get('Content-Length')
                    need(length is None or (length.isdigit() and int(length) <= MAX_BODY), 'BODY_LENGTH_BOUND')
                    need(response.headers.get('Content-Encoding', 'identity').lower() == 'identity', 'UNREQUESTED_CONTENT_ENCODING_STOP')
                    body = bytearray()
                    while True:
                        need(time.monotonic() - started < MAX_TOTAL_SECONDS, 'TOTAL_READ_DEADLINE')
                        part = response.read(min(65536, MAX_BODY + 1 - len(body)))
                        if not part:
                            break
                        body.extend(part)
                        need(len(body) <= MAX_BODY, 'BODY_BYTE_BOUND')
                    row['body'] = save('page-%02d.html' % index, bytes(body))
                    need(length is None or int(length) == len(body), 'DECLARED_CONTENT_LENGTH_NOT_COMPLETE')
                    row['public_metadata_observation'] = observe_public_fields(bytes(body))
                    row['complete'] = True
            except urllib.error.HTTPError as error:
                with error:
                    row.update(status=error.code, final_url=error.geturl(), headers=list(error.headers.items()),
                               retry_after=error.headers.get('Retry-After'))
                    raw = error.read(MAX_ERROR_BODY + 1)
                    row['error_body_truncated_at_bound'] = len(raw) > MAX_ERROR_BODY
                    row['error_body'] = save('page-%02d.error-body' % index, raw[:MAX_ERROR_BODY])
                raise RuntimeError('HTTP_ERROR_STOP_NO_RETRY:' + str(error.code))
            finally:
                row['ended_utc'] = now()
        result['ok'] = len(result['requests']) == 2 and all(row.get('complete') is True for row in result['requests'])
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
        result['ok'] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
    result['after_descriptor_identities'] = census()
    result['original_descriptor_identities_restored'] = result['after_descriptor_identities'] == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored'] and not result['errors']
    result['ended_utc'] = now()
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_OUTPUT_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
