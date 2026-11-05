"""Bind the one actual preparation receipt to the frozen Owner11 runtime template.

This local generator does not dispatch a request or execute a runtime.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
SOURCE = BASE / 'owner11-normal01-freeze-01'
OUT = BASE / 'owner11-normal01-runtime-freeze-01'
SOURCE_MANIFEST_SHA256 = '1cc0ff739afbe642255103e035d1379ac686b77c8b8ac3d1849f56ff984ecb3e'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def pretty(value):
    # This is the serializer actually used by prepare.py for plan_sha256.
    # The published plan's UTF-8 presentation may have a different byte hash.
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}', args.sha256)
    body = args.prepared.read_bytes()
    assert sha(body) == args.sha256
    actual = json.loads(body)
    manifest_raw = (SOURCE / 'manifest.json').read_bytes()
    assert sha(manifest_raw) == SOURCE_MANIFEST_SHA256
    for row in json.loads(manifest_raw)['files']:
        data = (SOURCE / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    plan_raw = (SOURCE / 'plan.json').read_bytes()
    plan = json.loads(plan_raw)
    assert plan['kind'] == 'owned-real-producer11-normal01-retirement-cause01'
    assert plan['scope'] == 'REAL_OWNER_ABI3_RETAINED_CAUSE_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
    assert plan['init_protocol_abi'] == 3 and plan['entry_abi'] == 'droidloom-relay-entry-v3'
    assert actual['success'] is True and actual['errors'] == []
    assert actual['attempt_nonce'] == plan['attempt_nonce'] and actual['plan_sha256'] == sha(pretty(plan))
    assert actual['canonical_spec_sha256'] == plan['canonical_spec_sha256']
    assert actual['runtime_executed'] is False and actual['namespace_or_network_changed'] is False
    expected_source = {f.name: {'bytes': len(f.read_bytes()), 'sha256': sha(f.read_bytes())}
                       for f in (SOURCE / 'source').glob('*.py')}
    assert actual['source_files'] == expected_source and len(expected_source) == 6
    assert set(actual['copied_artifacts']) == set(plan['artifacts'])
    for name, row in actual['copied_artifacts'].items():
        expected = plan['artifacts'][name]
        assert row['path'] == plan['package'] + '/' + expected['destination']
        assert row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256']
        assert row['identity']['device'] > 0 and row['identity']['inode'] > 0
    assert actual['base_before'] == actual['base_after'] and len(actual['base_before']) == 86
    for name in ('main_before', 'main_after', 'main_final'):
        row = actual[name]
        assert row['framework_sha256'] == plan['main']['framework_sha256']
        assert row['installed_contract_unchanged'] is True and row['original_processes_alive_and_unchanged'] is True
    ids = actual['id_availability']
    assert ids['available_at_observation'] is True and ids['host_uid'] == plan['spec']['host_uid']
    assert ids['subordinate_range'] == plan['spec']['subordinate_uids'] == plan['spec']['subordinate_gids']
    assert ids['reservation_created_in_passwd_or_subid_tables'] is False
    assert len(actual['data_images']) == 2
    for row, expected in zip(actual['data_images'], plan['data_images']):
        assert row['name'] == expected['name'] and row['bytes'] == expected['bytes'] and row['returncode'] == 0
        assert row['fresh_sparse_created'] is True and row['existing_userdata_copied'] is False
    template = (SOURCE / 'requests/runtime-stdin-template.py').read_text()
    request = json.loads((SOURCE / 'requests/runtime-request-template.json').read_bytes())
    assert request['stdin'] == template and template.count('__ACTUAL_PREPARED_SHA256__') == 1
    stdin = template.replace('__ACTUAL_PREPARED_SHA256__', args.sha256)
    request['stdin'] = stdin
    assert request['idempotency_key'].count('__ACTUAL_PREPARED_SHA256_PREFIX16__') == 1
    request['idempotency_key'] = request['idempotency_key'].replace('__ACTUAL_PREPARED_SHA256_PREFIX16__', args.sha256[:16])
    assert stdin.replace(args.sha256, '__ACTUAL_PREPARED_SHA256__') == template
    ast.parse(stdin)
    compile(stdin, '<Owner11 exact runtime>', 'exec')
    raw = pretty(request)
    result = {'schema': 1, 'actual_prepared_sha256': args.sha256,
        'source_manifest_sha256': sha(manifest_raw), 'actual_prepared_plan_and_six_sources_and_five_artifacts_match': True,
        'actual_Main_before_after_final_unchanged': True, 'actual_base86_unchanged': True,
        'actual_fresh_two_images_and_proposed_ID_admission_passed': True,
        'only_prepared_SHA_literal_and_stable_key_filled': True, 'request_sha256': sha(raw),
        'stdin_sha256': sha(stdin.encode()), 'key': request['idempotency_key'],
        'runtime_executed': False, 'production_or_App_qualification': False}
    OUT.mkdir(exist_ok=False)
    members = {'request.json': raw, 'stdin.py': stdin.encode(), 'actual-prepared.json': body,
        'binding-result.json': pretty(result), 'freeze_runtime10.py': Path(__file__).read_bytes(),
        'README.md': b'# Exact fresh Owner11 NORMAL01 runtime request\n\nOnly the externally observed actual prepared SHA and its stable key were filled into the previously frozen runtime template. The local generator has not submitted this request. The explicit P4BOOT2/layout3 broker with retained retirement-cause diagnostics, ABI3 holding-view and bootstrap-leaf producer, and init library are bound to actual matching build and ordinary receipts. Original Owner07, Owner08, Owner09 and Owner10 failures remain unchanged; this is a separate fresh cell. Runtime authorization, durable terminal, actual success/failure evidence, original retirement and exact cleanup remain the root coordinator\'s responsibility. This package does not qualify property reload, installed operation, pressure effects or commercial Apps.\n'}
    rows = []
    for name, data in members.items():
        (OUT / name).write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    manifest = pretty({'schema': 1, 'files': rows, 'runtime_executed': False})
    (OUT / 'manifest.json').write_bytes(manifest)
    print(json.dumps({'freeze': str(OUT), 'manifest_sha256': sha(manifest), 'request_bytes': len(raw),
                      'stdin_bytes': len(stdin.encode()), **result}, indent=2))


if __name__ == '__main__':
    main()
