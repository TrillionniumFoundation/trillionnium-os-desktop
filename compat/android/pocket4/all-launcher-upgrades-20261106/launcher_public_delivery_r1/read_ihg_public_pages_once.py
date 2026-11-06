#!/usr/bin/env python3
"""Observe two ordinary public HTML pages; never fetch an APK or enter Android."""
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

ROOT = Path('/home/alex/work/pocket4-ihg-public-distribution-pages-20261106-r1')
VARIANT_URL = 'https://www.apkmirror.com/apk/ihg-mobile/ihg-hotel-deals-rewards/ihg-one-rewards-book-hotels-5-110-0-release/ihg-one-rewards-book-hotels-5-110-0-android-apk-download/'
PACKAGE = 'com.ihg.apps.android'
MAX_BODY = 2 * 1024 * 1024
MAX_ERROR_BODY = 65536
TOTAL_SECONDS = 120
MINIMUM_ORDINARY_WAIT_SECONDS = 15
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


def select_intermediate(raw):
    parser, title = parse_html(raw)
    selected = set()
    expected_path = urllib.parse.urlsplit(VARIANT_URL).path + 'download/'
    for anchor in parser.rows:
        href = anchor['href']
        if not href:
            continue
        absolute = urllib.parse.urljoin(VARIANT_URL, href)
        item = urllib.parse.urlsplit(absolute)
        if item.hostname != 'www.apkmirror.com' or item.path != expected_path:
            continue
        normal_https_url(absolute)
        pairs = urllib.parse.parse_qsl(item.query, keep_blank_values=True, strict_parsing=True)
        need(len(pairs) == 1 and pairs[0][0] == 'key'
             and re.fullmatch(r'[A-Za-z0-9_-]{1,256}', pairs[0][1]), 'OBSERVED_SINGLE_LITERAL_KEY_REQUIRED')
        selected.add(absolute)
    need(len(selected) == 1, 'ONE_FRESH_LITERAL_INTERMEDIATE_LINK_REQUIRED')
    return {'title': title, 'literal_intermediate_url': next(iter(selected)),
            'source': 'single_unique_literal_anchor_in_this_complete_page',
            'key_from_prior_web_observation_used': False}


def select_unfetched_delivery(raw, base):
    parser, title = parse_html(raw)
    selected = set()
    for anchor in parser.rows:
        if ' '.join(anchor['text'].split()).casefold() != 'here' or not anchor['href']:
            continue
        absolute = urllib.parse.urljoin(base, anchor['href'])
        normal_https_url(absolute)
        selected.add(absolute)
    need(len(selected) == 1, 'ONE_LITERAL_HERE_LINK_REQUIRED')
    return {'title': title, 'unfetched_literal_delivery_url': next(iter(selected)),
            'source': 'single_unique_literal_here_anchor_in_this_complete_page',
            'delivery_url_followed': False, 'needs_separate_bounded_acquisition_request': True}


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
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000
         and sys.argv[1:] == ['--observe-two-public-pages-no-apk'], 'EXACT_ORDINARY_OWNER_ENTRY')
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'EXISTING_NORMAL_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    result = {'schema': 'pocket4-ihg-public-third-party-page-observation-v1', 'ok': False,
              'meaning_of_ok': 'two ordinary complete HTML observations and one unfetched literal URL only',
              'distribution_class': 'public-third-party-distribution', 'publisher_direct_APK': False,
              'started_utc': now(), 'requests': [], 'errors': [], 'ordinary_uid': os.getuid(),
              'maximum_HTTP_GET_requests': 2, 'maximum_bytes_per_HTML': MAX_BODY,
              'maximum_total_seconds': TOTAL_SECONDS, 'minimum_wait_seconds': MINIMUM_ORDINARY_WAIT_SECONDS,
              'user_agent_policy': 'urllib default unmodified', 'TLS_policy': 'system trust/default verification',
              'automatic_redirects': False, 'automatic_retry': False, 'challenge_solving': False,
              'DNS_IP_proxy_TLS_modifications': False, 'ordinary_resolver_internal_attempts_not_instrumented': True,
              'APK_downloads': 0, 'APK_signature_verified': False, 'APK_candidate_qualified': False,
              'existing_private_files_read': 0, 'subprocesses_started': 0,
              'Main_actions': 0, 'Android_commands': 0, 'UI_actions': 0, 'installs': 0,
              'permission_changes': 0, 'production_ready': False, 'cleanup_eligible': False,
              'before_descriptor_identities': before}
    previous_handler = signal.signal(signal.SIGALRM, deadline_signal)
    try:
        end = time.monotonic() + TOTAL_SECONDS
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS, 0)
        first, first_row = fetch_html_once(1, VARIANT_URL, end, result)
        observed = select_intermediate(first)
        first_row['parsed_observation'] = observed
        need(time.monotonic() + MINIMUM_ORDINARY_WAIT_SECONDS + 5 < end, 'WAIT_AND_SECOND_GET_BUDGET')
        waiting_started = time.monotonic()
        time.sleep(MINIMUM_ORDINARY_WAIT_SECONDS)
        result['actual_wait_seconds'] = time.monotonic() - waiting_started
        second, second_row = fetch_html_once(2, observed['literal_intermediate_url'], end, result)
        second_row['parsed_observation'] = select_unfetched_delivery(second, observed['literal_intermediate_url'])
        result['ok'] = len(result['requests']) == 2 and all(row['complete'] for row in result['requests'])
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
