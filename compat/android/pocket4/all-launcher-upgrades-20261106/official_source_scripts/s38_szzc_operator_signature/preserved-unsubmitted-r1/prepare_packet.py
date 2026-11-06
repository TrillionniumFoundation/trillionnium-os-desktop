#!/usr/bin/env python3
"""Seal one ordinary-UID signature observation, preserving every prior failure."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(relative, size, digest):
    raw = (BASE / relative).read_bytes()
    assert len(raw) == size and sha(raw) == digest, relative
    return raw


def definition(raw, name):
    text = raw.decode()
    node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node) + '\n\n'


def once(name, body):
    with (HERE / name).open('xb') as stream:
        stream.write(body)


def main():
    old = pinned('official_source_scripts/s37_szzc_signature/observe_signature.py', 8194,
                 'd97020c147dd6cbaacbba80d44f6ea89393e5f36b8e3db53c50ed75aa5f3e88b')
    runner = pinned('successor_audit_requests/reference/audit_successor_apks.py', 29242,
                    'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a')
    proof = pinned('successor_audit_requests/actual/batches-final-r1/batch-04/artifact.original.json', 132796,
                   'd2df2ac82742d7cbc69b43df878af8372e2df617113492e2e8ab25c69bbc0605')
    delivery = pinned('official_source_scripts/s36_szzc_finite_tail/actual/stdout.original.jsonl', 2370,
                      '4aac9ddb12c913683f322a7443c1212e1fc13f6d8fc26845437b78e659ef8e87')
    evidence, apk = json.loads(proof), json.loads(delivery)
    assert evidence['status'] == 'ACTUAL_APK_AUDIT_VERIFIED' and evidence['all_commands_succeeded'] is True
    assert apk['ok'] is True and apk['complete_body_rehashed'] is True and apk['original_files_full_hash_and_identity_unchanged'] is True
    bindings = evidence['tool_binding']
    assert len(bindings) == 12 and all(row['pin']['sha256'] == row['observed']['sha256'] and
        row['pin']['bytes'] == row['observed']['bytes'] for row in bindings.values())
    header = '''#!/usr/bin/env python3
"""Observe one downloaded APK signature as the existing ordinary tool owner."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/home/alex/work/pocket4-szzc-operator-signature-20261106-s38')
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
SAVED_PM_SIGNER = 'd85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'
'''
    constants = {
        'TOOL_BINDINGS': bindings,
        'EXPECTED_TOOL_NAMES': set(bindings),
        'TOOL_EVIDENCE': {'bytes': len(proof), 'sha256': sha(proof), 'schema': evidence['schema'], 'kind': 'prior actual successful batch04 tool bindings; full current identity recheck required'},
        'RUNNER_EVIDENCE': {'bytes': len(runner), 'sha256': sha(runner), 'copied_functions_unchanged': ['now', 'run_tool']},
        'APK_PIN': {'declared_path': apk['path'], 'resolved_path': apk['path'], 'bytes': apk['bytes'], 'sha256': apk['sha256']},
        'APK_IDENTITY': apk['final_identity'],
    }
    source = header + '\n'.join(key + ' = ' + repr(value) for key, value in constants.items()) + '\n\n'
    source += ''.join(definition(old, name) for name in ['need', 'ident', 'digest_fd', 'census', 'save'])
    source += ''.join(definition(runner, name) for name in ['now', 'run_tool'])
    source += (HERE / 'body.py').read_text()
    body = source.encode(); compile(body, 'observe_signature_as_owner.py', 'exec')
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3',
        'args': ['-I', '-B', '-c', source, '--observe-signature-as-existing-owner-once'],
        'idempotency_key': 'pocket4-szzc-operator-signature-s38-20261106-r1',
        'timeout_seconds': 210, 'memory_max_bytes': 536870912, 'cpu_quota_percent': 100, 'nice': 10}
    encoded = (json.dumps(request, sort_keys=True, indent=2) + '\n').encode()
    once('observe_signature_as_owner.py', body)
    once('process-request.json', encoded)
    pins = {'schema': 'pocket4-operator-signature-source-pins-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'source_bytes': len(body), 'source_sha256': sha(body), 'request_bytes': len(encoded), 'request_sha256': sha(encoded),
        'actual_uid_required': 1000, 'root_execution': False, 'Main_operations': 0,
        'tool_identity_policy': 'All twelve original tool full stat identities and full SHA256 must still agree; no ownership or writable-mode wildcard.',
        'old_s37_failure_preserved': True, 'original_runner_unchanged': True, 'production_ready': False}
    once('SOURCE_PINS.json', (json.dumps(pins, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(pins, sort_keys=True))


if __name__ == '__main__':
    main()
