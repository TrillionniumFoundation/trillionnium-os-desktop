"""Fill only the externally observed prepared SHA and stable key; no execution."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
SOURCE = BASE / 'owner07-normal03-diagnostic-freeze-01'
OUT = BASE / 'owner07-normal03-runtime01-freeze-02'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def pretty(value):
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
    assert sha(manifest_raw) == 'bd15e64b0df1945e92432af37769350e1959f7b7d7aa564e142b59d15ec56896'
    for row in json.loads(manifest_raw)['files']:
        data = (SOURCE / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    plan_raw = (SOURCE / 'plan.json').read_bytes()
    plan = json.loads(plan_raw)
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
    assert ids['available_at_observation'] is True and ids['host_uid'] == 61279
    assert ids['subordinate_range'] == {'start': 20200000, 'count': 100000}
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
    compile(stdin, '<NORMAL03 exact runtime>', 'exec')
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
        'binding-result.json': pretty(result), 'make_runtime03_revision02.py': Path(__file__).read_bytes(),
        'local-generator01-failure.json': (Path(__file__).parent / 'runtime03-generator01-failure.json').read_bytes(),
        'generator01-to02.diff': (Path(__file__).parent / 'runtime03-generator01-to02.diff').read_bytes(),
        'README.md': b'# Exact fresh NORMAL03 runtime request\n\nOnly the actual prepared SHA and stable key were filled into the previously reviewed runtime template. This request has not been submitted by this local generator. Original NORMAL01 runtime and NORMAL02 preparation remain failed and are not replayed. Runtime authorization, durable terminal, original success/failure evidence and exact cleanup remain the root coordinator\'s responsibility.\n'}
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
