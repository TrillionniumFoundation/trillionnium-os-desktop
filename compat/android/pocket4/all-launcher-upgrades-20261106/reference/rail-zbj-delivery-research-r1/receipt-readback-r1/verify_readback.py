#!/usr/bin/env python3
"""Recheck saved Hepta text payloads and exact bytes. No network or Android."""
from pathlib import Path
import base64
import hashlib
import json
import stat

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE.parent / 'bounded-receipt-read-plan.json').read_bytes())
actual = json.loads((HERE / 'verification.json').read_bytes())
assert plan['aggregate_expected_bytes'] == 7103 and len(plan['files']) == 3
rows = []
for index, declaration in enumerate(plan['files']):
    info = json.loads((HERE / f'receipt-{index:04d}.file-info.content-0.original.txt').read_bytes())
    binary = json.loads((HERE / f'receipt-{index:04d}.binary-read.content-0.original.txt').read_bytes())
    original = (HERE / f'receipt-{index:04d}.original.json').read_bytes()
    decoded = base64.b64decode(binary['data_base64'], validate=True)
    assert decoded == original
    assert info['path'] == binary['path'] == declaration['path']
    assert binary['version'] == info['version'] and binary['offset'] == 0 and binary['eof'] is True
    assert len(original) == binary['size'] == binary['next_offset'] == info['size'] == declaration['bytes']
    assert hashlib.sha256(original).hexdigest() == binary['chunk_sha256'] == info['sha256'] == declaration['sha256']
    assert info['mode'] == info['metadata']['mode'] == 384
    assert info['metadata']['uid'] == info['metadata']['gid'] == 1000
    assert info['metadata']['link_count'] == 1
    receipt = json.loads(original)
    assert receipt['index'] == index and receipt['status'] == 'COMPLETE'
    assert receipt['request_attempts'] == 1 and receipt['automatic_retries'] == 0
    assert receipt['joined'] is True and receipt['returncode'] == 0
    assert receipt['pidfd_closed'] is True and receipt['pidfd_exit_observed'] is True
    assert receipt['outcome_unknown'] is False and receipt['timed_out'] is False
    assert receipt['owned_curl_signal_count'] == 0
    assert receipt['start'] == 124370944 + index * 1048576
    assert receipt['end'] == 124370944 + (index + 1) * 1048576 - 1
    assert receipt['bytes'] == receipt['expected_bytes'] == 1048576
    assert receipt['curl']['http_code'] == 206 and receipt['curl']['size_download'] == 1048576
    assert receipt['curl']['num_retries'] == receipt['curl']['num_redirects'] == 0
    assert receipt['curl']['ssl_verify_result'] == receipt['curl']['exitcode'] == 0
    assert receipt['etag'] == []
    body = json.loads((HERE / f'body-{index:04d}.file-info.content-0.original.txt').read_bytes())
    identity = receipt['stat']
    assert body['path'] == receipt['path'] == (
        '/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s34/'
        f'com.zhubajie.client-tail-1m/{index:04d}.part')
    assert body['size'] == identity['st_size'] == receipt['bytes']
    assert body['sha256'] == receipt['sha256']
    assert stat.S_ISREG(identity['st_mode'])
    assert body['mode'] == body['metadata']['mode'] == stat.S_IMODE(identity['st_mode'])
    assert body['metadata']['uid'] == identity['st_uid'] == 1000
    assert body['metadata']['gid'] == identity['st_gid'] == 1000
    assert body['metadata']['link_count'] == identity['st_nlink'] == 1
    assert type(identity['st_mtime_ns']) is int and type(identity['st_ctime_ns']) is int
    version = ':'.join(str(identity[key]) for key in (
        'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    assert body['version'] == version
    rows.append({'path': body['path'], 'bytes': body['size'], 'sha256': body['sha256'],
                 'version': version, 'actual_metadata': body['metadata'],
                 'receipt_stat_match': True, 'ns_parsed_with_python_int': True,
                 'body_transferred': False})
assert actual['state'] == 'READBACK_AND_THREE_BODY_IDENTITIES_VERIFIED'
assert actual['results'] == rows and actual['all_ns_exact'] is True
assert actual['receipts_read'] == 3 and actual['receipt_bytes'] == 7103
assert actual['body_file_info_only'] == 3 and actual['body_bytes_transferred'] == 0
assert actual['body_total_bytes_hashed_by_file_info'] == 3145728
assert actual['new_DNS_observation'] is False and actual['remote_process_submissions'] == 0
print(json.dumps({'verification': 'ORIGINAL_RECEIPT_AND_BODY_FILE_INFO_RECHECKED',
                  'receipts': 3, 'receipt_bytes': 7103,
                  'body_file_info_only': 3, 'ns_exact': True,
                  'network_calls_in_this_verifier': 0,
                  'Android_calls_in_this_verifier': 0}, sort_keys=True))
