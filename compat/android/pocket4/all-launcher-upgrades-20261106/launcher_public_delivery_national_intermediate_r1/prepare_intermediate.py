#!/usr/bin/env python3
"""Prepare one ordinary intermediate-page request; never execute it."""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
LITERAL = 'https://en.softonic.com/download/national-car-rental/android/post-download?dt=internalDownload'
REFERENCE = {'path': '/home/alex/work/pocket4-national-public-distribution-page-20261107-r1/page-01.html',
             'bytes': 302453, 'sha256': 'abad1338055c580f8fff71da6b68983995262d6c8f0cb5ca6cbfe4967311a6bb',
             'uid': 1000, 'gid': 1000, 'mode': 0o600, 'parent_mode': 0o700}


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def exact(path, size, digest):
    row = pin(PROJECT / path)
    assert row['bytes'] == size and row['sha256'] == digest
    return row


def write(name, value):
    raw = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str) else
        (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())
    fd = os.open(HERE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            assert count > 0
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    assert (HERE / name).read_bytes() == raw
    return pin(HERE / name)


def definitions(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def main():
    inputs = [
        exact('launcher_public_delivery_independent_r2/observe_independent_public_page.py', 12985,
              'bcddbe70c5e3c650026c186fa6c249827a90cad9ff6f2081d650afb5ad22c039'),
        exact('launcher_public_delivery_independent_r2/actual/stdout.original.json', 6889,
              '2f8ddda1e64f7c830fb930183e86172f3ee941dc7e90510611cd9f19dcde72a0'),
        exact('launcher_public_delivery_independent_r2/actual/terminal.original.json', 731,
              'c54687d2b1fd64dbdf76ef1390d324cb2f33f6beb90ff3778f493f9e7a5fdb93'),
        exact('launcher_public_delivery_independent_r2/actual/root-validation.actual.json', 1350,
              '6b4f10060af36744a2ee8f883d3540d952175f45438c4898723fb7f7533f0234'),
    ]
    previous = json.loads((PROJECT / inputs[1]['path']).read_bytes())
    terminal = json.loads((PROJECT / inputs[2]['path']).read_bytes())
    assert terminal['job_id'] == '1a1b356f0cc-fc05-8238' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert terminal['timed_out'] is False and terminal['automatic_retry'] is False
    assert terminal['log_truncated'] == {'stdout': False, 'stderr': False}
    assert terminal['log_errors'] == {'stdout': None, 'stderr': None}
    assert previous['ok'] is True and previous['original_descriptor_identities_restored'] is True
    assert len(previous['requests']) == 1
    row = previous['requests'][0]
    assert row['status'] == 200 and row['complete'] is True and row['redirects_followed'] == 0
    assert row['body'] == {k: REFERENCE[k] for k in ('path', 'bytes', 'sha256')}
    assert row['parsed_observation']['candidate_control_urls'] == [LITERAL]
    assert all(row['parsed_observation']['expected_web_literals_present_in_HTML_not_verified_metadata'].values())
    original = (PROJECT / inputs[0]['path']).read_text()
    source = original.replace('Observe one fixed independent public HTML page; never follow a delivery URL or enter Android.',
                              'Rebind one actual public HTML input and observe its exact literal intermediate page once.')
    start, end = source.index('PROFILES = '), source.index('\n\ndef need')
    constants = ("ROOT = Path('/home/alex/work/pocket4-national-public-distribution-post-page-20261107-r1')\n"
        'INPUT = ' + repr(REFERENCE) + '\n'
        "SOURCE_PAGE_URL = 'https://national-car-rental.en.softonic.com/android/download'\n"
        'INTERMEDIATE_URL = ' + repr(LITERAL) + '\n'
        'MAX_BODY = 2 * 1024 * 1024\nMAX_ERROR_BODY = 65536\nTOTAL_SECONDS = 120\n'
        'TLS = ssl.create_default_context()\n')
    source = source[:start] + constants + source[end:]
    start, end = source.index('def observe_unfollowed_controls('), source.index('def deadline_signal(')
    source = source[:start] + (HERE / 'input_and_control_functions.py.inc').read_text() + '\n\n' + source[end:]
    assert source.count('headers=list(response.headers.items())') == 1
    assert source.count('headers=list(error.headers.items())') == 1
    source = source.replace('headers=list(response.headers.items())',
                            'headers=public_response_headers(response.headers.items())')
    source = source.replace('headers=list(error.headers.items())',
                            'headers=public_response_headers(error.headers.items())')
    source = source[:source.index('def main():')] + (HERE / 'main.py.inc').read_text()
    compile(source, 'observe_national_intermediate_page.py', 'exec')
    olddefs, newdefs = definitions(original), definitions(source)
    inherited = ['need', 'now', 'census', 'save', 'NoAutomaticRedirect', 'Anchors', 'parse_html',
                 'normal_https_url', 'deadline_signal']
    assert all(olddefs[k] == newdefs[k] for k in inherited)
    expected_fetch = olddefs['fetch_html_once'].replace('headers=list(response.headers.items())',
        'headers=public_response_headers(response.headers.items())').replace('headers=list(error.headers.items())',
        'headers=public_response_headers(error.headers.items())')
    assert expected_fetch == newdefs['fetch_html_once']
    write('observe_national_intermediate_page.py', source)
    write('worker-against-actual-national-page.diff', ''.join(difflib.unified_diff(
        original.splitlines(True), source.splitlines(True), fromfile=inputs[0]['path'],
        tofile='launcher_public_delivery_national_intermediate_r1/observe_national_intermediate_page.py')))
    write('INPUT_PINS.json', {'schema': 'pocket4-national-intermediate-input-pins-v1', 'files': inputs,
        'remote_fixed_HTML': REFERENCE, 'runtime_reads_only_remote_fixed_HTML_not_prior_cookie_headers': True})
    write('PRIOR_PUBLIC_EVIDENCE.json', {
        'schema': 'pocket4-national-actual-page-public-projection-v1',
        'job_id': terminal['job_id'], 'terminal': inputs[2], 'stdout_original': inputs[1],
        'HTTP_status': 200, 'body': row['body'], 'literal_control': LITERAL,
        'descriptor_identities_restored': True, 'cookie_header_values_copied': False,
        'cookie_headers_received_count': sum(k.casefold() in ('set-cookie', 'set-cookie2') for k, v in row['headers']),
        'APK_downloads': 0, 'literal_delivery_file_or_container_qualified': False,
    })
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', source, '--observe-pinned-national-intermediate-only'],
        'cwd': '/home/alex/work', 'timeout_seconds': 180, 'cpu_quota_percent': 100,
        'memory_max_bytes': 268435456, 'nice': 10,
        'idempotency_key': 'sidecar-evidence-20261106-national-public-post-page-r1'}
    write('exact-process-request.review-only.json', request)
    ns = {'__name__': 'local_control_without_network_or_runtime_entry'}
    exec(compile(source, 'observe_national_intermediate_page.py', 'exec'), ns)
    baseline = ns['census']()
    token = 'a901bc4949fe241750cd7ea3fb5df690d00b21e217b2212be813bbd51e5a36bb'
    fixture = ('<title>National</title><p>com.ehi.national.mobile 6.16.0.9403 ' + token + '</p>'
               '<a href="' + LITERAL + '">Free XAPK Download for Android</a>').encode()
    controls = []
    assert ns['derive_exact_intermediate'](fixture)['literal_url'] == LITERAL
    controls.append('exact_actual_literal_rederived_without_URI_inference')
    try:
        ns['derive_exact_intermediate'](fixture + b'<a href="https://example.invalid/other">Free XAPK Download for Android</a>')
    except RuntimeError as error:
        assert str(error) == 'ONE_ACTUAL_PINNED_LITERAL_INTERMEDIATE_REQUIRED'
    else:
        raise AssertionError('ambiguous control accepted')
    controls.append('extra_same_label_control_rejected')
    headers = [('Content-Type', 'text/html'), ('sEt-CoOkIe', 'anonymous-test-cookie=value; Secure')]
    sanitized = ns['public_response_headers'](headers)
    assert sanitized[0] == headers[0] and sanitized[1][0] == headers[1][0]
    assert 'anonymous-test-cookie' not in str(sanitized) and 'sha256=' in sanitized[1][1]
    controls.append('response_cookie_value_redacted_without_cookie_jar')
    with tempfile.TemporaryDirectory(prefix='own-input-fixture-', dir=HERE) as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        path = directory / 'page.html'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        try:
            assert os.write(fd, fixture) == len(fixture)
            os.fsync(fd)
        finally:
            os.close(fd)
        ns['INPUT'] = {'path': str(path), 'bytes': len(fixture), 'sha256': hashlib.sha256(fixture).hexdigest(),
                       'uid': os.getuid(), 'gid': os.getgid(), 'mode': 0o600, 'parent_mode': 0o700}
        accounting = {'acquired': 0, 'closed': 0, 'errors': []}
        held = ns['FixedPriorHTML'](ns['time'].monotonic() + 20, accounting)
        try:
            assert held.raw == fixture and held.recheck() == fixture
            replacement = directory / 'replacement.html'
            replacement.write_bytes(fixture)
            os.chmod(replacement, 0o600)
            os.replace(replacement, path)
            try:
                held.recheck()
            except RuntimeError as error:
                assert str(error) in ('HELD_PRIOR_HTML_STAT_CHANGED', 'NAMED_PRIOR_HTML_STAT_CHANGED')
            else:
                raise AssertionError('path replacement accepted')
        finally:
            held.close()
        assert accounting['acquired'] == accounting['closed'] and not accounting['errors']
    controls.append('real_owned_file_byte_pin_and_path_replacement_refusal_all_FDs_closed')
    final = ns['census']()
    assert baseline == final
    write('LOCAL_CONTROLS.json', {'schema': 'pocket4-national-intermediate-local-controls-v1',
        'ok': True, 'controls': [{'name': c, 'passed': True} for c in controls],
        'unchanged_original_definitions': inherited,
        'fetch_delta_is_only_two_header_sanitization_calls': True,
        'real_local_fixture_uid': os.getuid(), 'real_local_fixture_gid': os.getgid(),
        'fixture_owner_does_not_claim_remote_owner_observed': True,
        'real_fixture_owned_descriptors': accounting, 'before': baseline, 'after': final,
        'descriptor_identities_restored': True, 'HTTP_requests': 0, 'remote_processes': 0,
        'Main_actions': 0, 'APK_downloads': 0})
    write('SOURCE_PINS.json', {'schema': 'pocket4-national-intermediate-reviewed-source-v1',
        'state': 'FROZEN_LOCAL_UNSUBMITTED',
        'files': [pin(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name != 'SOURCE_PINS.json']})
    print(json.dumps({'ok': True, 'worker': pin(HERE / 'observe_national_intermediate_page.py'),
        'request': pin(HERE / 'exact-process-request.review-only.json'),
        'manifest': pin(HERE / 'SOURCE_PINS.json'), 'HTTP_requests': 0, 'remote_submissions': 0}))


if __name__ == '__main__':
    main()
