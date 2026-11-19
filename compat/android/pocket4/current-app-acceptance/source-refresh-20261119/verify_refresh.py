#!/usr/bin/env python3
"""Verify source refresh evidence without network, APK, or Android actions."""
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import stat

ROOT = Path(__file__).resolve().parent
EXCLUDED = ['com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab']


def require(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'relative packet path')
    path = ROOT / name
    info = path.lstat()
    require(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            'ordinary packet member: ' + name)
    body = path.read_bytes()
    require(len(body) <= 2 * 1024 * 1024, 'bounded metadata member')
    return body


def check_pin(body, row):
    require(len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'],
            'complete source size/SHA pin')


def main():
    inventory = {}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        expected, name = line.split('  ', 1)
        require(name not in inventory and len(expected) == 64, 'unique packet inventory')
        require(hashlib.sha256(read(name)).hexdigest() == expected, 'packet SHA: ' + name)
        inventory[name] = expected
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    require(actual == set(inventory) | {'FILES.sha256'}, 'complete exact packet inventory')
    index = json.loads(read('SOURCE-REFRESH.json'))
    require(index['schema'] == 'pocket4-required39-source-refresh-index-v1', 'refresh schema')
    require(index['scope'] == {'selected': 42, 'required': 39, 'third_party': 29,
                               'system': 10, 'excluded_packages': EXCLUDED}, 'original requested scope')
    require(index['historical_source_overrides'] == ['com.lianjia.beike'], 'explicit source override')
    for name in ('current_source_state', 'current_registry', 'current_freshness'):
        row = index[name]
        check_pin(read(row['path']), row)
    for row in index['public_version_observations']:
        check_pin(read(row['path']), row)
    spec = importlib.util.spec_from_file_location('beike_source_override', ROOT / 'beike/override_beike.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data, _ = module.read_inputs(ROOT / 'beike/inputs')
    actual_result = json.loads(read('beike/actual/RESULT.json'))
    check_pin(read('beike/actual/RESULT.json'), index['independently_verified_actual_successor'])
    require(actual_result['state'] == 'PASSED' and
            actual_result['snapshot_metadata_and_final_APK_F9_bookends_equal'] is True and
            actual_result['pocket4_qualified_metadata_F9_SHA_bookends_equal'] is True,
            'actual source-state execution and custody evidence')
    require(len(actual_result['original_live_JSON_proofs']) == 12 and
            actual_result['range_bodies_checked_or_required'] is False,
            'retained proof set excludes retired transport bodies')
    timestamp = datetime.fromisoformat(actual_result['created_utc'])
    outputs = actual_result['outputs']
    original_destination = Path(outputs['CURRENT-SOURCE-STATE.json']['path']).parent
    reconstructed = module.generate(data, original_destination, timestamp)
    require(set(reconstructed) == set(outputs), 'all three actual successor outputs')
    for name, body in reconstructed.items():
        check_pin(body, outputs[name])
        require(body == read('beike/actual/' + name), 'exact source-state reconstruction: ' + name)
    registry = json.loads(read(index['current_registry']['path']))
    freshness = json.loads(read(index['current_freshness']['path']))
    state = json.loads(read(index['current_source_state']['path']))
    module.validate_output(data, registry, freshness, state)
    require(len(state['applications']) == 39 and len(freshness['rows']) == 29 and
            len(registry['applications']) == 30, '39 required apps plus one companion dependency')
    metadata = json.loads(read('public-metadata/OBSERVATIONS.json'))
    supplement = json.loads(read('public-metadata/DIDI-TENCENT-SUPPLEMENT.json'))
    check_pin(read('public-metadata/OBSERVATIONS.json'), supplement['parent_observation'])
    rows = {row['package']: row for row in metadata['rows']}
    require(len(rows) == len(metadata['rows']) == 29 and set(rows) ==
            {row['package'] for row in freshness['rows']}, 'complete 29-package metadata matrix')
    observation = supplement['observation']
    require(observation['package'] == 'com.sdu.didi.psnger' and
            observation['http_status'] == 200 and observation['version'] == '8.0.20' and
            observation['authentication_used'] is False and observation['apk_downloaded'] is False,
            'independent public DiDi observation')
    require(supplement['identity_disambiguation']['unrelated_store_version_not_used'] is True,
            'store version cannot replace target application version')
    united = rows['com.united.mobile.android']
    require(united['selected_input_version'] == '4.2.103' and
            united['fresh_observation']['version'] == '4.2.104' and
            united['fresh_observation']['http_status'] == 200,
            'new United source requirement remains explicit')
    require(index['required_current_source_updates'] == [{'package': 'com.united.mobile.android',
            'selected_version': '4.2.103', 'observed_version': '4.2.104',
            'new_payload_qualified': False}], 'listing is not a new APK qualification')
    for value in (index, registry, freshness, state, actual_result):
        module.no_credit(value)
    require(index['all_39_latest_qualified'] is False and index['all_39_runtime_accepted'] is False,
            'no global latest or runtime admission from source evidence')
    print(json.dumps({'state': 'PASS_SOURCE_REFRESH_EVIDENCE_ONLY', 'packet_files': len(inventory),
        'current_Beike_version': '3.06.80', 'actual_successor_outputs_reconstructed': 3,
        'required_apps': 39, 'public_version_observations_with_supplement': 28,
        'United_4_2_104_payload_pending': True, 'SDK_commands': 0, 'Android_actions': 0,
        'APK_or_GSI_bodies_read': 0, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
