"""Bind the one actual preparation receipt to the frozen Owner18 runtime template.

This local generator does not dispatch a request or execute a runtime.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266')
SOURCE = BASE / 'android-owner18-normal01-freeze-01'
OUT = Path('/workspace/scratch/94990735b266/android-owner18-normal01-runtime-freeze-01')
SOURCE_MANIFEST_SHA256 = '12db23737188644c67a8a60cff57ab77ed8f46a58512544e6129190c8355bd60'


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
    assert plan['kind'] == 'owned-real-producer18-normal01-private-crash-buffer01'
    assert plan['scope'] == 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
    assert plan['init_protocol_abi'] == 3 and plan['entry_abi'] == 'droidloom-relay-entry-v3'
    assert actual['success'] is True and actual['errors'] == []
    assert actual['attempt_nonce'] == plan['attempt_nonce'] and actual['plan_sha256'] == sha(pretty(plan))
    assert actual['canonical_spec_sha256'] == plan['canonical_spec_sha256']
    assert actual['runtime_executed'] is False and actual['namespace_or_network_changed'] is False
    expected_source = {f.name: {'bytes': len(f.read_bytes()), 'sha256': sha(f.read_bytes())}
                       for f in (SOURCE / 'source').glob('*.py')}
    assert actual['source_files'] == expected_source and len(expected_source) == 7
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
    compile(stdin, '<Owner18 exact runtime>', 'exec')
    raw = pretty(request)
    result = {'schema': 1, 'actual_prepared_sha256': args.sha256,
        'source_manifest_sha256': sha(manifest_raw), 'actual_prepared_plan_and_seven_sources_and_five_artifacts_match': True,
        'actual_Main_before_after_final_unchanged': True, 'actual_base86_unchanged': True,
        'actual_fresh_two_images_and_proposed_ID_admission_passed': True,
        'only_prepared_SHA_literal_and_stable_key_filled': True, 'request_sha256': sha(raw),
        'stdin_sha256': sha(stdin.encode()), 'key': request['idempotency_key'],
        'runtime_executed': False, 'production_or_App_qualification': False}
    OUT.mkdir(exist_ok=False)
    members = {'request.json': raw, 'stdin.py': stdin.encode(), 'actual-prepared.json': body,
        'binding-result.json': pretty(result), 'freeze_runtime18.py': Path(__file__).read_bytes(),
        'README.md': b"# Exact fresh Owner18 NORMAL01 runtime request\n\nOnly the actual prepared SHA and stable key are filled into the reviewed runtime template. No dispatch occurs here. Actual Host17 artifacts and ordinary 39/139/7 controls, unchanged LMKD and C16 DSO remain bound. Seven sources include the exact frozen actor and generation-private crash-buffer observer.\n\nOriginal authority, ABI3, first-ACTIVE Stop, failure retirement, Main and exact cleanup gates remain. The observer must qualify fresh init/peer pidfd/root/ELF/domain before its single read request. Its private bounded packet file grants no HWS health or native enrollment; empty or failed capture is not success evidence. The raw packet file is not included in general runtime JSON or this package. The actor's legacy owner17 implementation label is retained; this actual prepared digest and unique plan/nonce/unit identify Owner18.\n\nOwner17's failed runtime stays failed. Root must independently review preparation and serialize the new runtime within its resource window. This package grants neither production nor App qualification.\n"}

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
