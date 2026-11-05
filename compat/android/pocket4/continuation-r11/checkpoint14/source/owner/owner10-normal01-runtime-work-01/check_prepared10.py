"""Local retained prepared receipt binding. No runtime, subprocess or remote I/O."""
from pathlib import Path
import hashlib
import json
import re

BASE = Path('/workspace/scratch/94990735b266')
SOURCE = BASE/'lmkd-recovery-20261105-01/owner10-normal01-freeze-01'
EVIDENCE = BASE/'root-recovery-20261104-02/evidence/owner10-normal01-prepared-read01'
OUT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


raw = (EVIDENCE/'prepared.json').read_bytes()
reader_raw = (EVIDENCE/'reader-report.json').read_bytes()
assert len(raw) == 55139 and sha(raw) == '53f327728b4daf732653a189d690f0c1d4e6374aeab5f7b9df7d666598f978e3'
assert len(reader_raw) == 61076 and sha(reader_raw) == '62addf99b256865994905b58add0e9b4a4520de5142211ebd713683cb798dd64'
actual, reader = json.loads(raw), json.loads(reader_raw)
assert reader['collection_complete'] is True and reader['errors'] == []
assert reader['files']['prepared.json']['content'].encode() == raw
plan = json.loads((SOURCE/'plan.json').read_bytes())
assert plan['canonical_spec_sha256'] == sha(json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode())
assert actual['plan_sha256'] == sha((json.dumps(plan, sort_keys=True, indent=2)+'\n').encode())
assert json.loads((SOURCE/'cell.json').read_bytes()) == plan['spec']
assert actual['attempt_nonce'] == plan['attempt_nonce']
assert actual['canonical_spec_sha256'] == plan['canonical_spec_sha256']
assert actual['success'] is True and actual['errors'] == []
assert actual['runtime_executed'] is False and actual['namespace_or_network_changed'] is False
assert actual['production_ready'] is False
sources = {p.name: {'bytes': len(p.read_bytes()), 'sha256': sha(p.read_bytes())}
           for p in (SOURCE/'source').glob('*.py')}
assert sources == actual['source_files'] and len(sources) == 6
base_rows = {r['relative']: r for r in plan['base']['records']}
assert len(base_rows) == 86 and len(actual['base_before']) == 86
assert actual['base_before'] == actual['base_after']
for row in actual['base_before']:
    expected = base_rows[row['relative']]
    assert row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256']
    assert all(row['identity'][k] > 0 for k in ['device', 'inode'])
assert actual['main_before'] == actual['main_after'] == actual['main_final']
for name in ['main_before', 'main_after', 'main_final']:
    row = actual[name]
    assert row['framework_sha256'] == plan['main']['framework_sha256']
    assert row['daemon'] == plan['main']['daemon'] and row['resources'] == plan['main']['resources']
    assert row['installed_contract_unchanged'] is True
    assert row['original_processes_alive_and_unchanged'] is True
assert len(actual['copied_artifacts']) == 5 and set(actual['copied_artifacts']) == set(plan['artifacts'])
for name, row in actual['copied_artifacts'].items():
    expected = plan['artifacts'][name]
    assert row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256']
    assert row['path'] == plan['package']+'/'+expected['destination']
    assert all(row['identity'][k] > 0 for k in ['device', 'inode'])
assert set(actual['tools']) == set(plan['tools_fixed_paths']) == set(plan['tools_sha256'])
for name, row in actual['tools'].items():
    assert row['path'] == name and row['sha256'] == plan['tools_sha256'][name]
    assert row['mode'] == 0o755 and row['bytes'] > 0
# The frozen presenter contract pins path and whole-file SHA, not a bytes key.
assert actual['presenter']['sha256'] == plan['presenter']['sha256']
assert actual['presenter']['path'] == plan['presenter']['path'] and actual['presenter']['bytes'] > 0
ids = actual['id_availability']
assert ids['available_at_observation'] is True and ids['host_uid'] == 61282 == plan['spec']['host_uid']
assert ids['subordinate_range'] == plan['spec']['subordinate_uids'] == plan['spec']['subordinate_gids'] == {'start': 20500000, 'count': 100000}
assert ids['reservation_created_in_passwd_or_subid_tables'] is False
assert len(actual['data_images']) == 2
for row, expected in zip(actual['data_images'], plan['data_images']):
    assert row['name'] == expected['name'] and row['bytes'] == expected['bytes'] and row['returncode'] == 0
    assert row['fresh_sparse_created'] is True and row['existing_userdata_copied'] is False
identities = [actual['package_identity'], actual['state_identity']]
identities += [r['identity'] for r in actual['copied_artifacts'].values()]
identities += [r['identity'] for r in actual['data_images']]
assert len({(r['device'], r['inode']) for r in identities}) == 9
resources = actual['resources_before']
full = float(re.search(r'^full avg10=([0-9.]+)', resources['memory_pressure'], re.M).group(1))
assert resources['MemAvailable_bytes'] >= plan['mem_available_min_bytes']
assert resources['disk_available_bytes'] >= plan['disk_available_min_bytes']
assert full <= plan['host_memory_full_avg10_max']
assert plan['outer_limits'] == {'memory.max': '5368709120', 'memory.high': '4831838208',
    'memory.swap.max': '0', 'cpu.max': '100000 100000', 'pids.max': '4096'}
result = {'schema': 1, 'state': 'ACTUAL_PREPARED_INPUTS_LOCALLY_REVALIDATED_NO_RUNTIME',
    'actual_prepared': pin(EVIDENCE/'prepared.json'), 'actual_reader': pin(EVIDENCE/'reader-report.json'),
    'source_manifest': pin(SOURCE/'manifest.json'), 'published_plan': pin(SOURCE/'plan.json'),
    'prepared_plan_serializer_sha256': actual['plan_sha256'], 'canonical_spec_sha256': actual['canonical_spec_sha256'],
    'six_source_files_exact': True, 'five_copy_bytes_SHA_destination_and_recorded_identity_match_plan': True,
    'base86_matches_frozen_plan_before_after': True, 'main_three_equal_and_match_frozen_daemon_resources_framework': True,
    'eight_tools_and_presenter_match': True, 'presenter_expected_length_not_present_in_frozen_plan': True,
    'fresh_owned_data_images': [{k: row[k] for k in ['name', 'bytes', 'identity', 'returncode',
        'fresh_sparse_created', 'existing_userdata_copied']} for row in actual['data_images']],
    'distinct_owned_directory_file_identities': 9, 'host_uid': ids['host_uid'], 'subordinate_range': ids['subordinate_range'],
    'uid_available_at_observation_only': True, 'passwd_subid_reservation_not_created': True,
    'resource_observation': {'MemAvailable_bytes': resources['MemAvailable_bytes'],
        'disk_available_bytes': resources['disk_available_bytes'], 'host_memory_full_avg10': full},
    'planned_outer_limits': plan['outer_limits'], 'runtime_resource_gate_still_required': True,
    'continuous_Main_noninterference_not_claimed': True, 'full_Owner_or_Android_lifecycle_qualified': False,
    'no_Hepta_or_Android_execution': True}
path = OUT/'actual-prepared-admission.json'
with path.open('xb') as stream:
    stream.write((json.dumps(result, sort_keys=True, indent=2)+'\n').encode())
print(json.dumps(pin(path)))
