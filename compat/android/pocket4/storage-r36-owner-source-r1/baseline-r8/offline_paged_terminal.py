"""Strict reconstruction from complete original H pages; never invent a single-page H."""
import base64
import hashlib
import json
import re

SCHEMA = 'p4-original-H-pagination-envelope-v2'
MAX_PAGES = 16
MAX_PAGE_RAW = 65536
MAX_RAW_TOTAL = 768 * 1024
MAX_ENVELOPE = 1024 * 1024
MAX_OUTPUT = 256 * 1024
MAX_CHUNK = 16384
ENVELOPE_KEYS = {'schema', 'host', 'session_id', 'original_single_page_json',
                 'original_pages', 'page_count', 'stdout_bytes', 'stdout_sha256'}
PAGE_KEYS = {'index', 'offset', 'bytes', 'sha256', 'raw_base64'}
STATUS_KEYS = ('boot', 'created_unix_ms', 'owner_pid', 'pid', 'state', 'exit_code',
               'bytes_seen', 'bytes_stored', 'capture_error', 'output_complete')
IDENTITY_KEYS = ('host', 'session_id', 'archive_path', 'available_end',
                 'persistent_across_runtime_restart', 'storage')


def need(ok, text):
    if not ok:
        raise RuntimeError(text)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON object member')
            value[key] = item
        return value
    def bad_constant(value):
        raise RuntimeError('non-JSON numeric constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def integer(value, low, high, label):
    need(type(value) is int and low <= value <= high, label)
    return value


def read_pages(raw_pages, expected_boot, expected_session):
    need(type(raw_pages) is list and 1 <= len(raw_pages) <= MAX_PAGES,
         'finite nonempty original H page sequence')
    need(type(expected_boot) is str and type(expected_session) is str and
         re.fullmatch(r'dpty-[0-9a-f]{64}', expected_session) is not None,
         'exact expected original H session and boot')
    cursor = 0
    raw_total = 0
    first = None
    first_status = None
    stdout = bytearray()
    receipts = []
    for number, raw in enumerate(raw_pages):
        need(type(raw) is bytes and 0 < len(raw) <= MAX_PAGE_RAW,
             'each whole original H JSON fits the fixed raw-page limit')
        raw_total += len(raw)
        need(raw_total <= MAX_RAW_TOTAL, 'fixed total original JSON byte limit')
        h = strict_json(raw)
        need(type(h) is dict and type(h.get('status')) is dict, 'actual H object and status')
        status = h['status']
        need(h['host'] == 'pocket4' and h['session_id'] == expected_session and
             h['archive_path'] == '/home/alex/.local/state/hepta-runtime-mac-worker/terminals/' +
                                  expected_session + '/output.log' and
             h['storage'] == 'target_archive' and h['persistent_across_runtime_restart'] is True,
             'same actual host/session/archive transport')
        total = integer(h['available_end'], 1, MAX_OUTPUT, 'bounded actual terminal byte total')
        integer(h['offset'], 0, total, 'actual page start')
        integer(h['next_offset'], 1, total, 'actual page end')
        need(h['offset'] == cursor and h['next_offset'] > cursor,
             'all original pages continuous from offset zero')
        need(h['output_complete'] is True and h['truncated_before_offset'] is False and
             h['utf8_pending'] is False and h['text_is_lossy'] is False and
             status['state'] == 'exited' and status['capture_error'] is None and
             status['output_complete'] is True and status['boot'] == expected_boot,
             'each page is an intact actual terminal observation')
        integer(status['exit_code'], 0, 1, 'original normal/stop terminal exit code')
        integer(status['created_unix_ms'], 1, 2**63 - 1, 'actual original creation timestamp')
        for key in ('pid', 'owner_pid'):
            integer(status[key], 2, 2**31 - 1, 'actual original H process identity')
        for key in ('bytes_seen', 'bytes_stored'):
            integer(status[key], 1, MAX_OUTPUT, 'actual terminal storage total')
            need(status[key] == total, 'complete archive without dropped output')
        need(type(h['bytes_hex']) is str and
             re.fullmatch(r'(?:[0-9a-f]{2})+', h['bytes_hex']) is not None,
             'actual exact raw chunk hex')
        chunk = bytes.fromhex(h['bytes_hex'])
        need(0 < len(chunk) <= MAX_CHUNK and len(chunk) == h['next_offset'] - h['offset'] and
             sha(chunk) == h['chunk_sha256'], 'each actual chunk length and SHA256')
        need(type(h['text']) is str and chunk.decode('ascii') == h['text'],
             'ASCII JSON terminal text agrees with original raw chunk')
        stable = {key: h[key] for key in IDENTITY_KEYS}
        stable_status = {key: status[key] for key in STATUS_KEYS}
        if first is None:
            first = stable
            first_status = stable_status
        else:
            need(stable == first and stable_status == first_status,
                 'all pages share original identity and the same final terminal totals/status')
        need(number == len(raw_pages) - 1 or h['next_offset'] < total,
             'no extra pages after the complete terminal')
        receipts.append({'index': number, 'offset': h['offset'], 'next_offset': h['next_offset'],
                         'raw_bytes': len(raw), 'raw_sha256': sha(raw),
                         'chunk_bytes': len(chunk), 'chunk_sha256': h['chunk_sha256']})
        stdout.extend(chunk)
        cursor = h['next_offset']
    need(cursor == first['available_end'] == len(stdout), 'complete terminal coverage through exact final byte')
    terminal = {'schema': 'p4-reconstructed-terminal-from-original-pages-v2',
                'host': 'pocket4', 'session_id': expected_session,
                'status': first_status, 'archive_path': first['archive_path'],
                'stdout_bytes': len(stdout), 'stdout_sha256': sha(stdout),
                'original_page_count': len(raw_pages), 'original_pages': receipts,
                'reconstructed_stdout': True, 'original_single_page_json': False}
    return terminal, bytes(stdout)


def make_envelope(raw_pages, expected_boot, expected_session):
    terminal, stdout = read_pages(raw_pages, expected_boot, expected_session)
    value = {'schema': SCHEMA, 'host': 'pocket4', 'session_id': expected_session,
             'original_single_page_json': False, 'page_count': len(raw_pages),
             'stdout_bytes': len(stdout), 'stdout_sha256': sha(stdout),
             'original_pages': [{'index': index, 'offset': strict_json(raw)['offset'],
                                 'bytes': len(raw), 'sha256': sha(raw),
                                 'raw_base64': base64.b64encode(raw).decode('ascii')}
                                for index, raw in enumerate(raw_pages)]}
    encoded = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')
    need(len(encoded) <= MAX_ENVELOPE, 'fixed complete pagination-envelope bound')
    return encoded


def decode_envelope(raw, expected_sha, expected_boot, expected_session):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_ENVELOPE and sha(raw) == expected_sha,
         'whole pinned explicit pagination envelope')
    value = strict_json(raw)
    need(type(value) is dict and set(value) == ENVELOPE_KEYS and value['schema'] == SCHEMA and
         value['host'] == 'pocket4' and value['session_id'] == expected_session and
         value['original_single_page_json'] is False and type(value['original_pages']) is list,
         'explicit pagination envelope, never a synthetic original H')
    integer(value['page_count'], 1, MAX_PAGES, 'finite declared page count')
    need(value['page_count'] == len(value['original_pages']), 'all declared original pages present')
    raw_pages = []
    for number, row in enumerate(value['original_pages']):
        need(type(row) is dict and set(row) == PAGE_KEYS and type(row['index']) is int and
             row['index'] == number and type(row['raw_base64']) is str,
             'ordered exact original page wrappers')
        integer(row['bytes'], 1, MAX_PAGE_RAW, 'bounded original page wrapper')
        integer(row['offset'], 0, MAX_OUTPUT, 'original page wrapper offset')
        part = base64.b64decode(row['raw_base64'], validate=True)
        need(len(part) == row['bytes'] and sha(part) == row['sha256'] and
             strict_json(part)['offset'] == row['offset'], 'original raw JSON preserved byte for byte')
        raw_pages.append(part)
    terminal, stdout = read_pages(raw_pages, expected_boot, expected_session)
    need(type(value['stdout_bytes']) is int and value['stdout_bytes'] == len(stdout) and
         value['stdout_sha256'] == sha(stdout), 'reconstructed whole terminal SHA and exact length')
    return terminal, stdout


def retirement_event(stdout):
    need(type(stdout) is bytes and len(stdout) <= MAX_OUTPUT, 'bounded complete retirement stdout')
    events = [strict_json(line) for line in stdout.decode('ascii').splitlines() if line.startswith('{')]
    need(events and type(events[-1]) is dict and set(events[-1]) == {'reference', 'body'},
         'actual saved retirement event from reconstructed original stdout')
    return events[-1]


# New explicit Pocket4 transport adapter. The original page guards above remain
# unchanged except for the declared host and its actual archive home directory.
MAIN_SESSION = 'dpty-2ea84f6d2b0ee264d5b6f3c71a518a4a76c897151393e6e31d14c9c88fa66e39'
MAIN_BOOT = '97d9600f-e081-465c-9e6e-62651e09806b'
MAIN_UNIT = 'p4-r5-offline-readonly-e6ac-r1.service'
MAIN_RESULT = '/home/alex/work/p4-r5-offline-readonly-e6ac-r1/RESULT.json'
BUNDLE_SCHEMA = 'p4-r5-offline-main-original-pagination-input-v1'
BUNDLE_KEYS = {'schema', 'pagination_envelope_base64', 'pagination_envelope_sha256',
               'archive_file_info_raw_base64', 'archive_file_info_raw_sha256'}
MAX_BUNDLE = 2 * 1024 * 1024


def main_event(terminal, stdout):
    need(terminal['host'] == 'pocket4' and terminal['session_id'] == MAIN_SESSION and
         terminal['status']['boot'] == MAIN_BOOT and
         terminal['status']['created_unix_ms'] == 1794793551279 and
         terminal['status']['owner_pid'] == 3523470 and terminal['status']['pid'] == 3523498,
         'exact actually launched original main H identity')
    events = [strict_json(line) for line in stdout.decode('ascii').splitlines() if line.startswith('{')]
    need(events and type(events[-1]) is dict and set(events[-1]) == {'passed', 'result', 'native'},
         'actual original main final event')
    event = events[-1]
    need(type(event['passed']) is bool and event['passed'] == (terminal['status']['exit_code'] == 0),
         'actual functional success or failure agrees with the original main exit')
    native = event['native']
    need(native['unit'] == MAIN_UNIT and native['boot'] == MAIN_BOOT and
         native['pid'] == 3523509 and native['start_ticks'] == '58204805' and
         native['InvocationID'] == '323ee75d02654dc48a8c3dbff80b04f6',
         'exact actual original native main generation')
    need(event['result']['path'] == MAIN_RESULT, 'fixed original main RESULT path')
    return event


def archive_reference(raw, expected_sha, terminal, stdout):
    need(type(raw) is bytes and 0 < len(raw) <= 16384 and sha(raw) == expected_sha,
         'complete original file_info JSON bytes and SHA')
    info = strict_json(raw)
    need(type(info) is dict and set(info) == {'metadata', 'mode', 'path', 'sha256', 'size', 'version'},
         'actual regular-file file_info schema')
    need(info['path'] == terminal['archive_path'] and info['sha256'] == sha(stdout) and
         type(info['size']) is int and info['size'] == len(stdout),
         'original archive whole bytes and SHA agree with every reconstructed actual H byte')
    need(type(info['version']) is str and re.fullmatch(r'[0-9]+(?::[0-9]+){4}', info['version']),
         'actual archive immutable-read version')
    dev, ino, size, mtime, ctime = map(int, info['version'].split(':'))
    need(dev == 66306 and ino > 0 and size == len(stdout) and mtime > 0 and ctime > 0,
         'actual archive version fields')
    metadata = info['metadata']
    need(type(metadata) is dict and metadata['metadata_platform'] == 'linux' and
         metadata['uid'] == metadata['gid'] == 1000 and metadata['link_count'] == 1 and
         type(info['mode']) is int and 0 <= info['mode'] <= 0o777 and
         metadata['mode'] == info['mode'], 'original archive regular mode and owner')
    return {'path': info['path'], 'bytes': size, 'sha256': info['sha256'],
            'identity': [dev, ino, 0o100000 | info['mode'], metadata['uid'], metadata['gid'],
                         metadata['link_count'], size, mtime, ctime]}


def decode_main_bundle(raw, expected_sha):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BUNDLE and sha(raw) == expected_sha,
         'whole explicit original-main pagination input')
    value = strict_json(raw)
    need(type(value) is dict and set(value) == BUNDLE_KEYS and value['schema'] == BUNDLE_SCHEMA,
         'separate original-pages input schema, never a single-page H')
    envelope = base64.b64decode(value['pagination_envelope_base64'], validate=True)
    terminal, stdout = decode_envelope(envelope, value['pagination_envelope_sha256'], MAIN_BOOT, MAIN_SESSION)
    event = main_event(terminal, stdout)
    archive_raw = base64.b64decode(value['archive_file_info_raw_base64'], validate=True)
    archive_ref = archive_reference(archive_raw, value['archive_file_info_raw_sha256'], terminal, stdout)
    return terminal, stdout, event, archive_ref


def make_main_bundle(raw_pages, archive_info_raw):
    envelope = make_envelope(raw_pages, MAIN_BOOT, MAIN_SESSION)
    value = {'schema': BUNDLE_SCHEMA,
             'pagination_envelope_base64': base64.b64encode(envelope).decode('ascii'),
             'pagination_envelope_sha256': sha(envelope),
             'archive_file_info_raw_base64': base64.b64encode(archive_info_raw).decode('ascii'),
             'archive_file_info_raw_sha256': sha(archive_info_raw)}
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')
    decode_main_bundle(raw, sha(raw))
    return raw
