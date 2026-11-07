"""Bind the one actual preparation receipt to the frozen Owner16 runtime template.

This local generator does not dispatch a request or execute a runtime.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266')
SOURCE = BASE / 'android-owner16-normal01-freeze-01'
OUT = Path('/workspace/scratch/94990735b266/android-owner16-normal01-runtime-freeze-01')
SOURCE_MANIFEST_SHA256 = 'b9a9cbdc3dcdd1a7c54f72c29eea762cd18d7f1b6e64a5e0a2d33c46d296913d'


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
    assert plan['kind'] == 'owned-real-producer16-normal01-bounded-init-log01'
    assert plan['scope'] == 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
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
    assert actual['main_before'] == actual['main_after'] == actual['main_final']
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
    compile(stdin, '<Owner16 exact runtime>', 'exec')
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
        'binding-result.json': pretty(result), 'freeze_runtime16.py': Path(__file__).read_bytes(),
        'README.md': b"# Exact fresh Owner16 NORMAL01 runtime request\n\nOnly the externally observed actual prepared SHA and stable key are filled into the already frozen runtime template. This local generator has not dispatched a request. Actual Host16 compile, 39 relay / 136 supervisor ordinary tests, two retirement tests, seven IPC controls, context/ABI3, and paired C16 DSO are bound by the preparation plan. Root must review the original actual prepared receipt and hold the runtime while heavy framework work occupies its resource window.\n\nThe new bounded generation-private init logger and dedicated response/actor capacities do not qualify Android logging until both actual markers reach the held channel before broker start. Full-stream completeness and per-line writer attribution remain false. Original authority, ABI3, ACTIVE, Stop, retirement, Main and exact cleanup gates remain. Owner15's original failed broker receipt is preserved, not reclassified. Actual runtime success or failure and all cleanup evidence remain required; this package does not grant whole-App or production qualification.\n"}

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
