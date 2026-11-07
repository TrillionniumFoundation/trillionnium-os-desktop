#!/usr/bin/env python3
"""Observe one fixed independent public HTML page; never follow a delivery URL or enter Android."""
import datetime
import fcntl
import hashlib
import html.parser
import json
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROFILES = {'national': {'package': 'com.ehi.national.mobile', 'url': 'https://national-car-rental.en.softonic.com/android/download', 'output_root': '/home/alex/work/pocket4-national-public-distribution-page-20261107-r1', 'expected_web_version_label': '6.16.0.9403', 'expected_web_container_sha256': 'a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb', 'literal_control_label': 'free xapk download for android', 'literal_control_meaning': 'published standalone XAPK download control; destination still unfetched'}}
ROOT = Path(PROFILES['national']['output_root'])
MAX_BODY = 2 * 1024 * 1024
MAX_ERROR_BODY = 65536
TOTAL_SECONDS = 120
TLS = ssl.create_default_context()


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


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
    names = {'page-01.html', 'page-02.html', 'page-01.partial', 'page-02.partial',
             'page-01.error-body', 'page-02.error-body', 'result.json'}
    need(name in names and isinstance(raw, bytes), 'CLOSED_OUTPUT_NAME_AND_BYTES')
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == 1000, 'OWNED_REGULAR_OUTPUT')
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'WRITE_PROGRESS')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(ROOT / name), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


class NoAutomaticRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


class Anchors(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.anchor = None
        self.title_depth = 0
        self.title = ''

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self.title_depth += 1
        if tag.lower() == 'a':
            need(self.anchor is None, 'NESTED_ANCHOR_NOT_ACCEPTED')
            hrefs = [v for k, v in attrs if k.lower() == 'href']
            need(len(hrefs) <= 1, 'AMBIGUOUS_HREF_ATTRIBUTE')
            self.anchor = {'href': hrefs[0] if hrefs else None, 'text': ''}

    def handle_data(self, text):
        if self.title_depth:
            self.title += text
        if self.anchor is not None:
            self.anchor['text'] += text

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.title_depth = max(0, self.title_depth - 1)
        if tag.lower() == 'a' and self.anchor is not None:
            self.rows.append(self.anchor)
            self.anchor = None


def parse_html(raw):
    parser = Anchors()
    parser.feed(raw.decode('utf-8', 'strict'))
    parser.close()
    title = ' '.join(parser.title.split())
    need(not any(x in title.casefold() for x in
                 ('just a moment', 'attention required', 'verify you are human', 'checking your browser')),
         'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY')
    return parser, title


def normal_https_url(value):
    need(isinstance(value, str) and 0 < len(value) <= 4096
         and value.isascii() and not any(ord(c) < 33 or ord(c) == 127 for c in value), 'LITERAL_URL_FORM')
    item = urllib.parse.urlsplit(value)
    need(item.scheme == 'https' and item.hostname and item.username is None
         and item.password is None and item.port in (None, 443) and not item.fragment, 'LITERAL_HTTPS_URL_REQUIRED')
    return item


def observe_unfollowed_controls(raw, profile):
    parser, title = parse_html(raw)
    literal_controls = []
    candidate_control_urls = set()
    ignored_non_https_controls = 0
    for anchor in parser.rows:
        label = ' '.join(anchor['text'].split())
        href = anchor['href']
        if not href or not any(word in label.casefold() for word in ('download', 'variant', 'xapk', 'apk')):
            continue
        absolute = urllib.parse.urljoin(profile['url'], href)
        parsed = urllib.parse.urlsplit(absolute)
        if parsed.scheme != 'https' or parsed.fragment:
            ignored_non_https_controls += 1
            continue
        normal_https_url(absolute)
        need(len(literal_controls) < 64 and len(label) <= 512, 'BOUNDED_PUBLIC_CONTROL_OBSERVATION')
        literal_controls.append({'literal_label': label, 'literal_url': absolute,
                                 'followed': False, 'file_or_installer_identity_verified': False})
        if label.casefold() == profile['literal_control_label']:
            candidate_control_urls.add(absolute)
    text = raw.decode('utf-8', 'strict')
    return {
        'title': title,
        'literal_download_or_variant_anchors': literal_controls,
        'ignored_non_https_or_fragment_controls': ignored_non_https_controls,
        'expected_web_literals_present_in_HTML_not_verified_metadata': {
            'package': profile['package'] in text,
            'version_label': profile['expected_web_version_label'] in text,
            'container_sha256_label': profile['expected_web_container_sha256'] in text,
        },
        'candidate_control_urls': sorted(candidate_control_urls),
        'candidate_control_state': ('ONE_LITERAL_UNFOLLOWED_CONTROL' if len(candidate_control_urls) == 1
                                    else 'UNRESOLVED_OR_AMBIGUOUS_NO_INFERRED_URL'),
        'automatic_script_execution': False, 'all_links_followed': 0,
        'APK_or_container_obtained': False, 'direct_binary_delivery_qualified': False,
        'a_complete_HTML_observation_is_not_download_or_signature_success': True,
    }


def deadline_signal(signum, frame):
    raise TimeoutError('TOTAL_PUBLIC_HTML_DEADLINE')


def fetch_html_once(index, url, end, result):
    normal_https_url(url)
    need(time.monotonic() + 5 < end, 'DEADLINE_BEFORE_NEW_GET')
    row = {'url': url, 'attempts': 1, 'automatic_retry': False, 'started_utc': now(),
           'complete': False, 'redirects_followed': 0}
    result['requests'].append(row)
    body = bytearray()
    complete_saved = False
    opener = urllib.request.build_opener(NoAutomaticRedirect(), urllib.request.HTTPSHandler(context=TLS))
    try:
        with opener.open(url, timeout=min(20, end - time.monotonic())) as response:
            row.update(status=response.status, final_url=response.geturl(), headers=list(response.headers.items()))
            need(response.status == 200 and response.geturl() == url, 'EXACT_URL_HTTP200_REQUIRED')
            need(response.headers.get_content_type() == 'text/html', 'HTML_ONLY_BODY_NOT_READ')
            need(response.headers.get('Content-Encoding', 'identity').lower() == 'identity', 'UNREQUESTED_ENCODING_STOP')
            length = response.headers.get('Content-Length')
            need(length is None or (length.isdigit() and int(length) <= MAX_BODY), 'DECLARED_HTML_BYTE_BOUND')
            while True:
                need(time.monotonic() < end, 'TOTAL_READ_DEADLINE')
                part = response.read(min(65536, MAX_BODY + 1 - len(body)))
                if not part:
                    break
                body.extend(part)
                need(len(body) <= MAX_BODY, 'HTML_BYTE_BOUND')
            need(length is None or len(body) == int(length), 'DECLARED_LENGTH_INCOMPLETE')
            row['body'] = save('page-%02d.html' % index, bytes(body))
            complete_saved = True
            row['complete'] = True
        return bytes(body), row
    except urllib.error.HTTPError as error:
        with error:
            row.update(status=error.code, final_url=error.geturl(), headers=list(error.headers.items()),
                       retry_after=error.headers.get('Retry-After'))
            raw = error.read(MAX_ERROR_BODY + 1)
            row['error_body_truncated_at_bound'] = len(raw) > MAX_ERROR_BODY
            row['error_body'] = save('page-%02d.error-body' % index, raw[:MAX_ERROR_BODY])
        raise RuntimeError('HTTP_ERROR_OR_REDIRECT_STOP_NO_RETRY:' + str(error.code))
    finally:
        if body and not complete_saved:
            row['incomplete_body'] = save('page-%02d.partial' % index, bytes(body))
            row['incomplete_body_is_not_valid_metadata'] = True
        row['ended_utc'] = now()


def main():
    global ROOT
    flags = {'--observe-national-page-only': 'national'}
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000
         and len(sys.argv) == 2 and sys.argv[1] in flags, 'EXACT_ORDINARY_OWNER_CLOSED_PAGE_ENTRY')
    key = flags[sys.argv[1]]
    profile = PROFILES[key]
    ROOT = Path(profile['output_root'])
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'EXISTING_NORMAL_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    result = {
        'schema': 'pocket4-independent-public-single-page-observation-v2',
        'ok': False, 'candidate_id': key, 'package': profile['package'],
        'meaning_of_ok': 'one complete ordinary public HTML response and bounded untrusted control observation only',
        'distribution_class': 'public-third-party-distribution', 'publisher_direct_APK': False,
        'started_utc': now(), 'requests': [], 'errors': [], 'ordinary_uid': os.getuid(),
        'maximum_HTTP_GET_requests': 1, 'maximum_bytes_per_HTML': MAX_BODY,
        'maximum_total_seconds': TOTAL_SECONDS,
        'user_agent_policy': 'urllib default unmodified', 'TLS_policy': 'system trust/default verification',
        'automatic_redirects': False, 'automatic_retry': False, 'challenge_solving': False,
        'DNS_IP_proxy_TLS_modifications': False, 'ordinary_resolver_internal_attempts_not_instrumented': True,
        'APK_downloads': 0, 'APK_signature_verified': False, 'APK_candidate_qualified': False,
        'delivery_link_requests': 0, 'distributor_installer_used': False,
        'existing_private_files_read': 0, 'subprocesses_started': 0,
        'Main_actions': 0, 'Android_commands': 0, 'UI_actions': 0, 'installs': 0,
        'permission_changes': 0, 'production_ready': False, 'cleanup_eligible': False,
        'before_descriptor_identities': before,
        'artifact_pin_semantics': 'hash of bytes written; no separate disk readback or directory crash-persistence proof',
    }
    previous_handler = signal.signal(signal.SIGALRM, deadline_signal)
    try:
        end = time.monotonic() + TOTAL_SECONDS
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS, 0)
        raw, row = fetch_html_once(1, profile['url'], end, result)
        need(not any(name.lower() == 'cf-mitigated' and value.casefold() == 'challenge'
                     for name, value in row['headers']), 'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY')
        row['parsed_observation'] = observe_unfollowed_controls(raw, profile)
        result['ok'] = len(result['requests']) == 1 and row['complete'] is True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
        result['ok'] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    result['after_descriptor_identities'] = census()
    result['original_descriptor_identities_restored'] = result['after_descriptor_identities'] == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored'] and not result['errors']
    result['ended_utc'] = now()
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
