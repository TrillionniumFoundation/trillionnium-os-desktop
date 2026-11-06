#!/usr/bin/env python3
"""One fixed public Gitiles HTTPS GET; no Git or filesystem mutation."""
import base64
import hashlib
import http.client
import json
import signal
import ssl
import sys
import time

HOST = 'android.googlesource.com'
PATH = '/platform/prebuilts/misc/+/be7c3a630b5dc5eb3260035d77a81b2f322754f8/common/robolectric-native-prebuilt/Android.bp?format=TEXT'
EXPECTED_BLOB = '68246c4206ea702c8a66b73c37bfcacb51524086'
EXPECTED_PARENT_TREE = '28d2e7b2d373edc79f6782bcad189ad598727c06'
DECODED_MAX = 65536
WIRE_MAX = 88408
QUALIFICATION_SECONDS = 10.0

def need(ok, code):
    if not ok:
        raise RuntimeError(code)

def safe_error(error):
    row = {'type': type(error).__name__}
    if isinstance(error, RuntimeError) and str(error) in {
            'HTTP_STATUS_NOT_200', 'FIXED_WIRE_BOUND', 'FIXED_BASE64_NOT_CANONICAL',
            'FIXED_DECODED_BOUND', 'EXACT_LOCKED_BLOB_MISMATCH',
            'SOURCE_HAS_NUL', 'QUALIFICATION_DEADLINE', 'HTTP_BODY_INCOMPLETE'}:
        row['code'] = str(error)
    if isinstance(error, OSError):
        row['errno'] = error.errno
    return row

def run():
    started = time.monotonic()
    deadline = started + QUALIFICATION_SECONDS
    result = {'schema': 1, 'source_sha256': SOURCE_SHA256,
              'state': 'FAILED', 'collection_complete': False,
              'fixed_url': 'https://' + HOST + PATH,
              'expected_blob_sha1': EXPECTED_BLOB,
              'actual_observed_parent_tree_sha1': EXPECTED_PARENT_TREE,
              'prior_device_reader_collection_complete': False,
              'prior_actual_stdout_sha256': '246bea15800fc155abebfefbc6d68a187f97302402803090cc05284f4090c922',
              'request_attempted': False, 'HTTP_status': None, 'wire': None,
              'source': None, 'errors': [], 'cleanup_errors': [],
              'response_closed': False, 'connection_closed': False,
              'redirects_followed': 0, 'retries': 0, 'subprocesses': 0,
              'proxy_environment_used': False, 'cookies_or_credentials_used': False,
              'TLS_default_certificate_and_hostname_verification': True,
              'filesystem_writes': 0, 'Git_commands': 0, 'Main_actions': 0,
              'Android_actions': 0, 'source_reuse_or_normal_build_authorized': False,
              'qualification_seconds': QUALIFICATION_SECONDS}
    connection = None
    response = None
    def expired(_signum, _frame):
        raise RuntimeError('QUALIFICATION_DEADLINE')
    previous_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, QUALIFICATION_SECONDS)
    try:
        # HTTPSConnection does not consult proxy/authentication/cookie handlers.
        # Normal system trust roots are read by the standard TLS implementation.
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(HOST, 443, timeout=5.0, context=context)
        result['request_attempted'] = True
        connection.request('GET', PATH, headers={'Accept': 'text/plain',
                            'Accept-Encoding': 'identity',
                            'User-Agent': 'Pocket4-fixed-source-reader/1',
                            'Connection': 'close'})
        response = connection.getresponse()
        result['HTTP_status'] = response.status
        need(response.status == 200, 'HTTP_STATUS_NOT_200')
        wire = response.read(WIRE_MAX + 1)
        need(len(wire) <= WIRE_MAX, 'FIXED_WIRE_BOUND')
        need(response.read(1) == b'' and response.length in (None, 0), 'HTTP_BODY_INCOMPLETE')
        result['wire'] = {'bytes': len(wire), 'sha256': hashlib.sha256(wire).hexdigest()}
        compact = wire.replace(b'\r', b'').replace(b'\n', b'')
        decoded = base64.b64decode(compact, validate=True)
        need(base64.b64encode(decoded) == compact, 'FIXED_BASE64_NOT_CANONICAL')
        need(0 < len(decoded) <= DECODED_MAX, 'FIXED_DECODED_BOUND')
        blob = hashlib.sha1(b'blob ' + str(len(decoded)).encode('ascii') + b'\0' + decoded).hexdigest()
        need(blob == EXPECTED_BLOB, 'EXACT_LOCKED_BLOB_MISMATCH')
        text = decoded.decode('utf-8', errors='strict')
        need('\0' not in text, 'SOURCE_HAS_NUL')
        need(time.monotonic() < deadline, 'QUALIFICATION_DEADLINE')
        result['source'] = {'bytes': len(decoded), 'sha256': hashlib.sha256(decoded).hexdigest(),
                            'git_blob_sha1': blob, 'text': text,
                            'mode_observed_in_prior_locked_tree': '100644'}
    except BaseException as error:
        result['errors'].append(safe_error(error))
    finally:
        if response is not None:
            try:
                response.close()
                result['response_closed'] = True
            except BaseException as error:
                result['cleanup_errors'].append(safe_error(error))
        if connection is not None:
            try:
                connection.close()
                result['connection_closed'] = True
            except BaseException as error:
                result['cleanup_errors'].append(safe_error(error))
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    result['seconds'] = time.monotonic() - started
    result['qualification_deadline_met'] = time.monotonic() < deadline
    result['collection_complete'] = bool(not result['errors'] and not result['cleanup_errors']
        and result['qualification_deadline_met'] and result['source'] is not None
        and result['response_closed'] and result['connection_closed'])
    if result['collection_complete']:
        result['state'] = 'PASS_EXACT_PUBLIC_LOCKED_BLUEPRINT_ONLY'
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
    need(len(raw) <= 524288, 'FIXED_WIRE_BOUND')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if result['collection_complete'] else 1

if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'fixed_url': 'https://' + HOST + PATH,
                          'expected_blob_sha1': EXPECTED_BLOB, 'network_requests': 0,
                          'filesystem_writes': 0, 'Main_actions': 0}, sort_keys=True))
    else:
        raise SystemExit(run())
