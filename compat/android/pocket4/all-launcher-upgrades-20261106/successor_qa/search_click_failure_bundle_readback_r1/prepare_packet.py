#!/usr/bin/env python3
"""Prepare one fixed host-private bundle readback; never submit its request."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PARENT = PROJECT / 'successor_qa/owned_postcondition_reconciler_r1'
ACTUAL = PROJECT / 'successor_qa/search_click_failure_reader_r1/actual-public'
EXPECTED_STDOUT = (15496, 'c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b')
EXPECTED_TERMINAL = (733, 'f3b1a5e3a34df13bcfcf906c3eb3da63c90e28c174385dcc0578691a14c34d5a')
EXPECTED_BUNDLE = {'path': '/home/alex/work/pocket4-beike-search-click-failure-evidence-20261106-r1/bundle.private.json',
                   'bytes': 1102634, 'sha256': '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4'}


def need(value, code):
    if not value:
        raise RuntimeError(code)


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = HERE / name
    with path.open('xb') as handle:
        handle.write(raw)
    need(path.read_bytes() == raw, 'NEW_LOCAL_BYTES_READBACK')


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode()


def main():
    actual_raw = (ACTUAL / 'stdout.original.json').read_bytes()
    terminal_raw = (ACTUAL / 'status-01.original.json').read_bytes()
    for raw, expected in ((actual_raw, EXPECTED_STDOUT), (terminal_raw, EXPECTED_TERMINAL)):
        need((len(raw), hashlib.sha256(raw).hexdigest()) == expected, 'ORIGINAL_DIAGNOSTIC_RECEIPT_PIN')
    actual, terminal = json.loads(actual_raw), json.loads(terminal_raw)
    need(actual['ok'] is True and actual['diagnosis_completed'] is True and
         actual['private_bundle'] == EXPECTED_BUNDLE and actual['files'] == 101 and
         actual['original_bytes'] == 782840 and actual['step_file_count'] == 90 and
         actual['whole_process_fd_identities_unchanged'] is True, 'ACTUAL_SINGLE_BUNDLE_PROVENANCE')
    need(terminal['job_id'] == '1a1b30c6205-fc05-8083' and terminal['state'] == 'succeeded' and
         terminal['exit_code'] == 0 and terminal['output_complete'] is True and terminal['output_durable'] is True and
         terminal['terminal_publication_confirmed'] is True and terminal['log_errors'] == {'stdout': None, 'stderr': None} and
         terminal['log_truncated'] == {'stdout': False, 'stderr': False} and
         terminal['log_bytes'] == {'stdout': {'seen': len(actual_raw), 'stored': len(actual_raw)}, 'stderr': {'seen': 0, 'stored': 0}},
         'ACTUAL_COMPLETE_DIAGNOSTIC_TERMINAL')
    parent_raw = (PARENT / 'read_exact_binding_diff.py').read_bytes()
    need((len(parent_raw), hashlib.sha256(parent_raw).hexdigest()) ==
         (7801, 'a3796e8ffc5219f1613a0efdc6252f0f10f620f298b3943ac5bb33498b360e2c'), 'MATURE_ROOT_PRIVATE_READER_SOURCE')
    parent = parent_raw.decode()
    definitions = {node.name: ast.get_source_segment(parent, node) for node in ast.parse(parent).body
                   if isinstance(node, ast.FunctionDef)}
    inherited = ('need', 'sha', 'census', 'pinned_bundle')
    binding = {'diagnostic_job': terminal['job_id'], 'diagnostic_stdout_bytes': len(actual_raw),
               'diagnostic_stdout_sha256': hashlib.sha256(actual_raw).hexdigest(),
               'diagnostic_terminal_bytes': len(terminal_raw), 'diagnostic_terminal_sha256': hashlib.sha256(terminal_raw).hexdigest(),
               'original_failed_job': actual['historical_job'], 'original_failed_step': actual['step'],
               'original_failed_case_reclassified': False, 'files': actual['files'], 'original_bytes': actual['original_bytes']}
    source = '''#!/usr/bin/env python3
"""Return only one pinned private bundle as bounded zlib-base64; no Main API."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import zlib

'''
    source += 'BUNDLE = Path(' + repr(EXPECTED_BUNDLE['path']) + ')\n'
    source += 'BUNDLE_BYTES = ' + repr(EXPECTED_BUNDLE['bytes']) + '\nBUNDLE_SHA = ' + repr(EXPECTED_BUNDLE['sha256']) + '\n'
    source += "FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')\n"
    source += 'CAPTURE_BINDING = ' + repr(binding) + '\n'
    source += 'MAX_COMPRESSED_BYTES = BUNDLE_BYTES + 65536\nMAX_STDOUT_BYTES = 2097152\n\n\n'
    source += '\n\n\n'.join(definitions[name] for name in inherited)
    source += '''


def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    before = census()
    raw, identity = pinned_bundle()
    compressed = zlib.compress(raw, 9)
    need(0 < len(compressed) <= MAX_COMPRESSED_BYTES, 'FIXED_COMPRESSED_BYTE_BOUND')
    again, again_identity = pinned_bundle()
    need(again == raw and again_identity == identity, 'BUNDLE_UNCHANGED_AFTER_COMPRESSION')
    after = census()
    need(after == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result = {
        'schema': 'pocket4-one-fixed-private-bundle-zlib-readback-v1', 'ok': True,
        'encoding': 'zlib-base64', 'capture_binding': CAPTURE_BINDING,
        'bundle': {'path': str(BUNDLE), 'bytes': BUNDLE_BYTES, 'sha256': BUNDLE_SHA},
        'bundle_stat': dict(zip(FIELDS, identity)),
        'compressed_bytes': len(compressed), 'compressed_sha256': sha(compressed),
        'data': base64.b64encode(compressed).decode('ascii'),
        'process_fds_before': before, 'process_fds_after': after,
        'whole_process_fd_identities_unchanged': True, 'original_file_bytes_and_stat_unchanged': True,
        'raw_output_may_contain_private_state': True, 'raw_output_repository_publication_admitted': False,
        'Main_reads': 0, 'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'UI_actions': 0, 'installs': 0, 'permission_changes': 0, 'signals': 0,
        'originals_modified': False, 'automatic_retry': False, 'reconciliation_published': False,
        'old_UNKNOWN_modified': False, 'production_ready': False
    }
    output = (json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\\n').encode('ascii')
    need(len(output) <= MAX_STDOUT_BYTES, 'COMPLETE_PRIVATE_STDOUT_BYTE_BOUND')
    need(census() == before, 'FINAL_FD_IDENTITIES_CHANGED')
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
'''
    parsed = ast.parse(source)
    child_defs = {node.name: ast.get_source_segment(source, node) for node in parsed.body if isinstance(node, ast.FunctionDef)}
    need(all(child_defs[name] == definitions[name] for name in inherited), 'FOUR_INHERITED_FUNCTIONS_EXACT')
    need(set(child_defs) == set(inherited) | {'main'}, 'ONLY_ONE_FIXED_READER_ENTRY')
    compile(source, 'read_one_fixed_bundle.py', 'exec')
    save('read_one_fixed_bundle.py', source)
    packet = json.loads((PARENT / 'binding-diff.process-request.json').read_bytes())
    need(packet['args'][:5] == ['-n', '/usr/bin/python3', '-I', '-B', '-c'] and len(packet['args']) == 6,
         'INHERITED_ROOT_PRIVATE_ENTRY')
    packet['args'][-1] = source
    packet['idempotency_key'] = 'pocket4-beike-search-click-failure-one-bundle-zlib-readback-20261106-r1'
    save('process-request.review-only.json', encoded(packet))
    save('SOURCE_DIFF.patch', ''.join(difflib.unified_diff(parent.splitlines(True), source.splitlines(True),
         fromfile='mature-root-private-reader/read_exact_binding_diff.py', tofile='read_one_fixed_bundle.py')))
    private = PROJECT.parent / 'p4_private_ui/beike-search-click-failure-bundle-r1'
    plan = {'schema': 'pocket4-fixed-failed-search-private-bundle-readback-plan-v1',
            'fixed_bundle': EXPECTED_BUNDLE, 'capture_binding': binding,
            'maximum_compressed_bytes': EXPECTED_BUNDLE['bytes'] + 65536, 'maximum_stdout_bytes': 2097152,
            'private_directory': str(private), 'private_stdout': str(private / 'stdout.original.jsonl'),
            'private_decoded_bundle': str(private / 'bundle.private.original.json'),
            'public_actual_directory': str(HERE / 'actual-public'),
            'required_public_metadata_filenames': ['start.original.json', 'terminal.original.json'],
            'reader': pin(HERE / 'read_one_fixed_bundle.py'), 'process_request': pin(HERE / 'process-request.review-only.json'),
            'inherited_functions_exact': list(inherited),
            'inherited_request_limits': {key: packet[key] for key in ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
            'remote_execution_attempted': False, 'Main_reads': 0, 'UI_actions': 0,
            'private_content_may_be_published_to_Git': False, 'old_unknown_reclassified': False,
            'failed_action_current_tree_exported': False, 'specific_rejected_tree_difference': 'UNKNOWN'}
    save('READBACK_PLAN.json', encoded(plan))
    inputs = [PARENT / 'read_exact_binding_diff.py', PARENT / 'binding-diff.process-request.json',
              PROJECT / 'successor_audit_requests/effective_permissions_batch_readback_r2/batch-02/read_fixed_batch_private_logs.py',
              PROJECT / 'successor_audit_requests/effective_permissions_batch_readback_r2/decode_private_readback.py',
              ACTUAL / 'stdout.original.json', ACTUAL / 'status-01.original.json']
    outputs = [HERE / name for name in ('prepare_packet.py', 'read_one_fixed_bundle.py', 'process-request.review-only.json',
               'SOURCE_DIFF.patch', 'READBACK_PLAN.json', 'decode_private_readback.py')]
    save('SOURCE_PINS.json', encoded({'schema': 'pocket4-fixed-private-bundle-readback-source-pins-v1',
         'inputs': [pin(path) for path in inputs], 'outputs': [pin(path) for path in outputs],
         'four_parent_function_bodies_exact': True, 'raw_bundle_contents_in_source_or_pins': False,
         'remote_execution_attempted': False}))
    print(json.dumps({'prepared': True, 'reader': pin(HERE / 'read_one_fixed_bundle.py'),
                     'packet': pin(HERE / 'process-request.review-only.json'), 'plan': pin(HERE / 'READBACK_PLAN.json'),
                     'pins': pin(HERE / 'SOURCE_PINS.json'), 'inherited_function_count': len(inherited),
                     'remote_execution_attempted': False}, sort_keys=True))


if __name__ == '__main__':
    main()
