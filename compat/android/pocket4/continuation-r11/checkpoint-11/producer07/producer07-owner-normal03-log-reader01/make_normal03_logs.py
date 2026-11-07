#!/usr/bin/env python3
"""Bind the unchanged fifteen-member reader to one actual retired NORMAL03 run."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
PREIMAGE = BASE / 'owner07-normal01-logs-freeze-01'
SOURCE = BASE / 'owner07-normal03-diagnostic-freeze-01'
RUNTIME = BASE / 'owner07-normal03-runtime01-freeze-02'
OUT = BASE / 'owner07-normal03-logs-freeze-01'
PREPARED_SHA = 'a94417ecfb9cfb546f587fae7468091f8a503b4954ce7a2af1506bf0f3181329'
ROOT = '/opt/p4-owner07-normal-20261105-03-state'
ATTEMPT = '65e87d2663a795cf303cfd76affd9e5a17213fb7eab0ae7f39beb26e17e92bbb'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}', args.sha256)
    actual_raw = args.runtime.read_bytes()
    assert sha(actual_raw) == args.sha256
    actual = json.loads(actual_raw)
    prepared_raw = (RUNTIME / 'actual-prepared.json').read_bytes()
    assert sha(prepared_raw) == PREPARED_SHA
    prepared = json.loads(prepared_raw)
    plan = json.loads((SOURCE / 'plan.json').read_bytes())
    assert plan['state'] == ROOT and plan['attempt_nonce'] == ATTEMPT
    assert actual['attempt_nonce'] == prepared['attempt_nonce'] == ATTEMPT
    assert actual['prepared_sha256'] == PREPARED_SHA
    terminal = actual['terminal']
    invocation = terminal['InvocationID']
    assert re.fullmatch('[0-9a-f]{32}', invocation)
    actor_text = terminal['ExecMainPID']
    assert isinstance(actor_text, str) and re.fullmatch('[1-9][0-9]{0,9}', actor_text)
    actor = int(actor_text)
    assert 1 < actor < 2**31
    cleanup = actual['exact_unit_cleanup']
    assert cleanup['invocation'] == invocation
    assert cleanup['unit_not_found'] is True and cleanup['cgroup_absent'] is True
    assert cleanup['original_actor_dead'] is True
    for key in ('actor_result_sha256', 'gate_sha256'):
        assert re.fullmatch('[0-9a-f]{64}', actual[key])
    old_raw = (PREIMAGE / 'collect.py').read_bytes()
    assert sha(old_raw) == '01ca8e6b31e3a529100520b652c03b02409b237470999e7b3c0d13f5f4f2e6f4'
    old = old_raw.decode()
    substitutions = {
        'retired first NORMAL attempt': 'retired NORMAL03 attempt',
        '/opt/p4-owner07-normal-20261105-01-state': ROOT,
        '06ad67978c234fe35388a364f82523aadc8dc25755030cb61ee88128b9ca5979': ATTEMPT,
        'be45f40c6453182e8a4f71ecb5cb7398803f8945f4c3be156410c168722c26ae': PREPARED_SHA,
        '26f19099192d0bfd76740c535f30598c32e17718da58b9fbe63d134bfe5abd19': args.sha256,
        'dbf7eb9f900a4c0f8738c1f1f8c99c65': invocation,
        'ACTOR_PID = 1034770': f'ACTOR_PID = {actor}',
        'owner07-normal01-retired-evidence-read01': 'owner07-normal03-retired-evidence-read01',
    }
    source = old
    for before, after in substitutions.items():
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    reconstructed = source
    for before, after in reversed(list(substitutions.items())):
        assert reconstructed.count(after) == 1, after
        reconstructed = reconstructed.replace(after, before)
    assert reconstructed == old
    ast.parse(source)
    compile(source, '<fixed NORMAL03 read-only collector>', 'exec')
    request = json.loads((PREIMAGE / 'request.json').read_bytes())
    assert request['stdin'] == old
    request['stdin'] = source
    request['idempotency_key'] = 'p4-owner07-normal03-logs01-' + sha(source.encode())[:16]
    encoded_request = pretty(request)
    binding = {
        'schema': 1, 'kind': 'normal03-fixed-root-evidence-reader-static-binding',
        'expected_prepared_sha256': PREPARED_SHA, 'expected_runtime_sha256': args.sha256,
        'actual_invocation': invocation, 'actual_actor_pid': actor,
        'actual_original_retirement_fields_required': True,
        'only_fixed_literals_and_inert_labels_changed': True,
        'allowed_member_count': 15, 'per_member_max_bytes': 1048576,
        'aggregate_max_bytes': 4194304, 'source_AST_compile_passed': True,
        'source_sha256': sha(source.encode()), 'request_sha256': sha(encoded_request),
        'stdin_exact': True, 'executed': False, 'qualification': False,
    }
    members = {
        'collect.py': source.encode(), 'request.json': encoded_request,
        'source-binding-result.json': pretty(binding),
        'source.diff': ''.join(difflib.unified_diff(old.splitlines(True), source.splitlines(True),
                          fromfile='normal01/collect.py', tofile='normal03/collect.py')).encode(),
        'actual-runtime.json': actual_raw,
        'make_normal03_logs.py': Path(__file__).read_bytes(),
        'README.md': b'# Fixed NORMAL03 retirement evidence reader\n\nThis is the original fifteen-member root reader with only exact attempt, receipt, InvocationID, PID and inert labels substituted. No directory scan, write, mode change, process launch, namespace operation or runtime replay is added. Every source path remains fixed; collection success is never runtime qualification. The generator requires the original runtime result and its externally observed SHA, exact retired InvocationID, and all three cleanup fields before writing this reader.\n',
    }
    OUT.mkdir(exist_ok=False)
    rows = []
    for name, data in members.items():
        (OUT / name).write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    manifest = pretty({'schema': 1, 'files': rows, 'executed': False})
    (OUT / 'manifest.json').write_bytes(manifest)
    print(json.dumps({'freeze': str(OUT), 'manifest_sha256': sha(manifest),
                      'request_bytes': len(encoded_request), **binding}, indent=2))


if __name__ == '__main__':
    main()
