#!/usr/bin/env python3
"""Rebind one actual public HTML input and observe its exact literal intermediate page once."""
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

ROOT = Path('/home/alex/work/pocket4-national-public-distribution-post-page-20261107-r1')
INPUT = {'path': '/home/alex/work/pocket4-national-public-distribution-page-20261107-r1/page-01.html', 'bytes': 302453, 'sha256': 'abad1338055c580f8fff71da6b68983995262d6c8f0cb5ca6cbfe4967311a6bb', 'uid': 1000, 'gid': 1000, 'mode': 384, 'parent_mode': 448}
SOURCE_PAGE_URL = 'https://national-car-rental.en.softonic.com/android/download'
INTERMEDIATE_URL = 'https://en.softonic.com/download/national-car-rental/android/post-download?dt=internalDownload'
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


def full_stat(st):
    return {key: getattr(st, key) for key in
            ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def directory_identity(st):
    return {key: getattr(st, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')}


class FixedPriorHTML:
    """Hold the sole pinned ordinary-owner input; no arbitrary-path argument."""
    def __init__(self, end, accounting):
        self.end, self.accounting = end, accounting
        self.owned, self.dirs = [], []
        self.fd = self.before = self.parent_fd = self.name = None
        try:
            parts = Path(INPUT['path']).parts
            need(parts[0] == '/' and len(parts) > 2 and all(x not in ('.', '..') for x in parts[1:]),
                 'FIXED_ABSOLUTE_INPUT_PATH')
            fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.owned.append(fd)
            accounting['acquired'] += 1
            self.dirs.append({'fd': fd, 'parent': None, 'name': '/', 'before': full_stat(os.fstat(fd))})
            for part in parts[1:-1]:
                parent = fd
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
                self.owned.append(fd)
                accounting['acquired'] += 1
                self.dirs.append({'fd': fd, 'parent': parent, 'name': part, 'before': full_stat(os.fstat(fd))})
            self.parent_fd, self.name = fd, parts[-1]
            parent_st = os.fstat(fd)
            need(parent_st.st_uid == INPUT['uid'] and parent_st.st_gid == INPUT['gid']
                 and stat.S_IMODE(parent_st.st_mode) == INPUT['parent_mode'], 'EXACT_PRIVATE_INPUT_PARENT')
            self.fd = os.open(self.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            self.owned.append(self.fd)
            accounting['acquired'] += 1
            st = os.fstat(self.fd)
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == INPUT['uid']
                 and st.st_gid == INPUT['gid'] and stat.S_IMODE(st.st_mode) == INPUT['mode']
                 and st.st_size == INPUT['bytes'], 'EXACT_PRIOR_HTML_REGULAR_OWNER_SIZE_MODE')
            self.before = full_stat(st)
            self.raw = self.recheck()
        except BaseException:
            self.close()
            raise

    def path_recheck(self):
        for row in self.dirs:
            st = os.fstat(row['fd'])
            need(stat.S_ISDIR(st.st_mode), 'HELD_INPUT_DIRECTORY_REQUIRED')
            saved = {k: row['before'][k] for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')}
            need(directory_identity(st) == saved, 'HELD_INPUT_DIRECTORY_IDENTITY_CHANGED')
            named = (os.stat('/', follow_symlinks=False) if row['parent'] is None else
                     os.stat(row['name'], dir_fd=row['parent'], follow_symlinks=False))
            need(directory_identity(named) == saved, 'NAMED_INPUT_DIRECTORY_IDENTITY_CHANGED')
        need(full_stat(os.fstat(self.fd)) == self.before, 'HELD_PRIOR_HTML_STAT_CHANGED')
        need(full_stat(os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)) == self.before,
             'NAMED_PRIOR_HTML_STAT_CHANGED')

    def recheck(self):
        need(time.monotonic() < self.end, 'PRIOR_HTML_READ_DEADLINE')
        self.path_recheck()
        chunks, offset, digest = [], 0, hashlib.sha256()
        while offset < INPUT['bytes']:
            need(time.monotonic() < self.end, 'PRIOR_HTML_READ_DEADLINE')
            part = os.pread(self.fd, min(65536, INPUT['bytes'] - offset), offset)
            need(bool(part), 'PRIOR_HTML_SHORT_READ')
            chunks.append(part)
            digest.update(part)
            offset += len(part)
        need(os.pread(self.fd, 1, offset) == b'' and digest.hexdigest() == INPUT['sha256'],
             'PRIOR_HTML_COMPLETE_BYTE_PIN_REQUIRED')
        self.path_recheck()
        return b''.join(chunks)

    def public_binding(self):
        return {'path': INPUT['path'], 'bytes': INPUT['bytes'], 'sha256': INPUT['sha256'],
                'file': self.before, 'held_directory_count': len(self.dirs),
                'directories': [{'name': x['name'], 'before_full_stat': x['before']} for x in self.dirs],
                'directory_stability_fields': ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid'],
                'file_stability_fields': list(self.before), 'read_only': True}

    def close(self):
        while self.owned:
            try:
                os.close(self.owned.pop())
                self.accounting['closed'] += 1
            except OSError as error:
                self.accounting['errors'].append({'errno': error.errno, 'operation': 'close_owned_input_fd'})


def public_response_headers(rows):
    """Do not persist or replay anonymous response cookie values."""
    result = []
    for name, value in rows:
        if name.casefold() in ('set-cookie', 'set-cookie2'):
            raw = value.encode('utf-8', 'strict')
            value = '[redacted value: bytes=' + str(len(raw)) + '; sha256=' + hashlib.sha256(raw).hexdigest() + ']'
        result.append((name, value))
    return result


def derive_exact_intermediate(raw):
    parser, title = parse_html(raw)
    selected = set()
    for row in parser.rows:
        if ' '.join(row['text'].split()).casefold() != 'free xapk download for android' or not row['href']:
            continue
        absolute = urllib.parse.urljoin(SOURCE_PAGE_URL, row['href'])
        normal_https_url(absolute)
        selected.add(absolute)
    need(selected == {INTERMEDIATE_URL}, 'ONE_ACTUAL_PINNED_LITERAL_INTERMEDIATE_REQUIRED')
    text = raw.decode('utf-8', 'strict')
    need(all(token in text for token in
             ('com.ehi.national.mobile', '6.16.0.9403',
              'a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb')),
         'PRIOR_ACTUAL_METADATA_LITERALS_CHANGED')
    return {'source_title': title, 'literal_url': next(iter(selected)),
            'url_rederived_from_exact_prior_HTML': True, 'URL_inferred_or_synthesized': False}


def observe_intermediate_controls(raw):
    parser, title = parse_html(raw)
    rows = []
    for anchor in parser.rows:
        label = ' '.join(anchor['text'].split())
        if not anchor['href']:
            continue
        absolute = urllib.parse.urljoin(INTERMEDIATE_URL, anchor['href'])
        item = urllib.parse.urlsplit(absolute)
        if not (any(x in label.casefold() for x in ('download', 'xapk', 'apk'))
                or label.casefold() in ('here', 'click here')
                or item.path.casefold().endswith(('.apk', '.xapk'))):
            continue
        if item.scheme != 'https' or item.fragment:
            continue
        normal_https_url(absolute)
        need(len(rows) < 64 and len(label) <= 512, 'BOUNDED_INTERMEDIATE_CONTROLS')
        rows.append({'literal_label': label, 'literal_url': absolute, 'followed': False,
                     'referenced_file_identity': 'UNKNOWN_NOT_FETCHED'})
    return {'title': title, 'unfollowed_literal_controls': rows,
            'automatic_script_execution': False, 'binary_URL_qualified': False,
            'APK_or_XAPK_downloaded': False, 'store_installer_used': False,
            'unknown_or_empty_control_requires_original_HTML_review': True}


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
            row.update(status=response.status, final_url=response.geturl(), headers=public_response_headers(response.headers.items()))
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
            row.update(status=error.code, final_url=error.geturl(), headers=public_response_headers(error.headers.items()),
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
         and sys.argv[1:] == ['--observe-pinned-national-intermediate-only'], 'EXACT_ORDINARY_OWNER_ENTRY')
    need(ROOT.parent.resolve(strict=True) == ROOT.parent, 'EXISTING_NORMAL_PARENT_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    accounting = {'acquired': 0, 'closed': 0, 'errors': []}
    result = {
        'schema': 'pocket4-national-literal-intermediate-observation-v1', 'ok': False,
        'meaning_of_ok': 'one complete ordinary intermediate HTML observation; no binary qualification',
        'package': 'com.ehi.national.mobile', 'started_utc': now(), 'requests': [], 'errors': [],
        'prior_successful_page_job': '1a1b356f0cc-fc05-8238',
        'prior_HTML_reference': INPUT, 'input_owned_descriptors': accounting,
        'maximum_HTTP_GET_requests': 1, 'maximum_HTML_bytes': MAX_BODY,
        'maximum_total_seconds': TOTAL_SECONDS, 'ordinary_uid': os.getuid(),
        'user_agent_policy': 'urllib default unmodified', 'TLS_policy': 'system trust/default verification',
        'cookie_jar_created': False, 'prior_cookie_values_read_or_replayed': False,
        'response_cookie_values_persisted': False, 'response_cookie_values_hashed_and_redacted': True,
        'automatic_redirects': False, 'automatic_retry': False, 'script_execution': False,
        'challenge_solving': False, 'DNS_IP_proxy_TLS_modifications': False,
        'ordinary_resolver_internal_attempts_not_instrumented': True,
        'delivery_link_requests': 0, 'APK_downloads': 0, 'APK_signature_verified': False,
        'APK_candidate_qualified': False, 'store_installer_used': False,
        'subprocesses_started': 0, 'Main_actions': 0, 'Android_commands': 0,
        'UI_actions': 0, 'installs': 0, 'permission_changes': 0,
        'production_ready': False, 'cleanup_eligible': False,
        'before_descriptor_identities': before,
        'output_pin_semantics': 'hash of bytes written; no separate output readback or directory crash-persistence proof',
    }
    held = None
    previous_handler = signal.signal(signal.SIGALRM, deadline_signal)
    try:
        end = time.monotonic() + TOTAL_SECONDS
        signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS, 0)
        held = FixedPriorHTML(end, accounting)
        result['prior_HTML_binding'] = held.public_binding()
        result['literal_rederivation'] = derive_exact_intermediate(held.raw)
        raw, row = fetch_html_once(1, result['literal_rederivation']['literal_url'], end, result)
        need(not any(name.casefold() == 'cf-mitigated' and value.casefold() == 'challenge'
                     for name, value in row['headers']), 'PUBLIC_CHALLENGE_STOP_NO_SOLVING_OR_ALTERNATE_IDENTITY')
        row['parsed_observation'] = observe_intermediate_controls(raw)
        need(held.recheck() == held.raw, 'PRIOR_HTML_BYTES_CHANGED_AFTER_REQUEST')
        result['prior_HTML_complete_bytes_stat_path_rechecked_after_request'] = True
        result['ok'] = len(result['requests']) == 1 and row['complete'] is True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
        result['ok'] = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if held is not None:
            try:
                held.path_recheck()
                result['prior_HTML_path_stat_stable_at_final_close'] = True
            except BaseException as error:
                result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512],
                                         'phase': 'input_final_path_stat'})
                result['ok'] = False
            finally:
                held.close()
    result['after_descriptor_identities'] = census()
    result['original_descriptor_identities_restored'] = result['after_descriptor_identities'] == before
    result['ok'] = (result['ok'] and result['original_descriptor_identities_restored']
                    and accounting['acquired'] == accounting['closed'] and not accounting['errors']
                    and not result['errors'])
    result['ended_utc'] = now()
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()
    save('result.json', raw)
    need(census() == before, 'FINAL_PUBLICATION_DESCRIPTOR_SET_CHANGED')
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
