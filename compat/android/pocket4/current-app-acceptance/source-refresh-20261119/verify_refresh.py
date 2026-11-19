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
PROVIDER_PACKET = 'compat/android/pocket4/current-app-acceptance/system-cp3a-provider-source-20261119/'
SELECTED_CURRENT_PATHS = {
    'current_source_packet_manifest': PROVIDER_PACKET + 'FILES.sha256',
    'current_source_packet_verifier': PROVIDER_PACKET + 'verify_current_inputs.py',
    'current_business_preflight': PROVIDER_PACKET + 'current/CURRENT-BUSINESS-PLAN.json',
    'current_system_provider_cohort': PROVIDER_PACKET + 'current/CURRENT-CP3A-PROVIDER-COHORT.json',
}


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


def current_source_inputs(index):
    # The old packet reader still rejects traversal. Only these four fixed,
    # repository-relative sibling paths can enter the current-source consumer.
    repo = ROOT.parents[4]
    pins = {}
    for key, fixed_path in SELECTED_CURRENT_PATHS.items():
        row = index[key]
        require(row['path'] == fixed_path and set(row) == {'path', 'bytes', 'sha256'},
                'fixed selected current-source member: ' + key)
        path = repo / fixed_path
        info = path.lstat()
        require(path.resolve() == path and stat.S_ISREG(info.st_mode) and
                info.st_nlink == 1 and info.st_size <= 2 * 1024 * 1024,
                'bounded ordinary current-source member')
        body = path.read_bytes()
        check_pin(body, row)
        pins[key] = row
    spec = importlib.util.spec_from_file_location(
        'current_cp3a_source_selection', repo / SELECTED_CURRENT_PATHS['current_source_packet_verifier'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, expected in module.EXPECTED.items():
        require(pins[key] == {**expected, 'path': PROVIDER_PACKET + expected['path']},
                'current source consumer and selection pins agree')
    result = module.verify()
    require(result['state'] == 'PASS_CURRENT_SOURCE_INPUTS_RUNTIME_BLOCKED' and
            result['selected_provider_source_identities'] == 4 and
            result['current_outputs_reconstructed'] == 2 and result['required_apps'] == 39,
            'selected current provider/preflight inputs were actually consumed')
    require(result['United_version'] == '4.2.104' and result['United_version_code'] == 3622 and
            result['other38_package_rows_unchanged'] is True and
            result['installation_prerequisites_unchanged'] is True,
            'current United source and preserved other38/install gates')
    for key in ('provider_semantic_cleanup_qualified', 'runtime_qualified',
                'business_qualified', 'production_ready'):
        require(result[key] is False, 'no source-to-runtime promotion: ' + key)
    return result


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
    require(index['historical_source_overrides'] == ['com.lianjia.beike', 'com.united.mobile.android'],
            'explicit preserved Beike and additive United source overrides')
    previous_pin = index['previous_refresh_index']
    require(previous_pin == {'path': 'history-before-united/SOURCE-REFRESH.json', 'bytes': 2153,
            'sha256': '3e6d6c9365760bc727d0f66cfb366cd71090b0626623a6789df2e575f0c522ae'},
            'exact prior Beike selection index remains history')
    check_pin(read(previous_pin['path']), previous_pin)
    previous_index = json.loads(read(previous_pin['path']))
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
    # Validate the original Beike successor against its own unchanged output.
    # United is an additive second successor, never fed to Beike's other38 check.
    for name in ('current_source_state', 'current_registry', 'current_freshness'):
        check_pin(read(previous_index[name]['path']), previous_index[name])
    module.validate_output(data,
        json.loads(read(previous_index['current_registry']['path'])),
        json.loads(read(previous_index['current_freshness']['path'])),
        json.loads(read(previous_index['current_source_state']['path'])))
    united_spec = importlib.util.spec_from_file_location('united_source_override', ROOT / 'united/override_united.py')
    united_module = importlib.util.module_from_spec(united_spec)
    united_spec.loader.exec_module(united_module)
    united_data = united_module.read_inputs(ROOT / 'united/inputs')
    for name, original in (('base-CURRENT-SOURCE-STATE.json', 'CURRENT-SOURCE-STATE.json'),
                           ('base-current-source-inputs.json', 'current-source-inputs.json'),
                           ('base-current-source-freshness.json', 'current-source-freshness.json')):
        require(read('united/inputs/' + name) == read('beike/actual/' + original),
                'exact Beike output is United predecessor')
    united_result = json.loads(read('united/actual/RESULT.json'))
    require(index['current_united_successor']['path'] == 'united/actual/RESULT.json', 'fixed United result path')
    check_pin(read('united/actual/RESULT.json'), index['current_united_successor'])
    require(united_result['schema'] == 'pocket4-united-required39-source-successor-v1' and
            united_result['state'] == 'PASSED_METADATA_JOIN_ONLY' and
            united_result['version_code'] == 3622, 'actual United metadata join')
    united_time = datetime.fromisoformat(united_result['created_utc'])
    united_reconstructed = united_module.generate(united_data, united_time)
    require(set(united_reconstructed) == set(united_result['outputs']), 'complete United successor outputs')
    for name, body in united_reconstructed.items():
        check_pin(body, united_result['outputs'][name])
        require(body == read('united/actual/' + name), 'exact United source-state reconstruction: ' + name)
    for key, name in (('current_source_state', 'CURRENT-SOURCE-STATE.json'),
                      ('current_registry', 'current-source-inputs.json'),
                      ('current_freshness', 'current-source-freshness.json')):
        row = index[key]
        require(row['path'] == 'united/actual/' + name and
                row['bytes'] == united_result['outputs'][name]['bytes'] and
                row['sha256'] == united_result['outputs'][name]['sha256'], 'selected current United successor')
    registry = json.loads(read(index['current_registry']['path']))
    freshness = json.loads(read(index['current_freshness']['path']))
    state = json.loads(read(index['current_source_state']['path']))
    united_module.validate_output(united_data, registry, freshness, state, united_time)
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
            'historical United listing observation remains unchanged')
    require(index['required_current_source_updates'] == [], 'current United input blocker resolved by actual SDK receipt')
    receipt_pin = {'path': 'united/inputs/source-receipt.json', 'bytes': 31632,
        'sha256': '1023f326cc86f256fef91e873dcc8613b213d5ada5f692193fe41b747a5fb306'}
    check_pin(read(receipt_pin['path']), receipt_pin)
    require(index['resolved_current_source_updates'] == [{'package': 'com.united.mobile.android',
            'previous_selected_version': '4.2.103', 'selected_version': '4.2.104',
            'observed_version': '4.2.104', 'version_code': 3622, 'new_payload_qualified': True,
            'source_receipt': receipt_pin}], 'actual qualified United source resolution')
    for value in (index, registry, freshness, state, actual_result, united_result):
        module.no_credit(value)
    require(index['all_39_latest_qualified'] is False and index['all_39_runtime_accepted'] is False,
            'no global latest or runtime admission from source evidence')
    current_inputs = current_source_inputs(index)
    print(json.dumps({'state': 'PASS_SOURCE_REFRESH_EVIDENCE_ONLY', 'packet_files': len(inventory),
        'current_Beike_version': '3.06.80', 'current_United_version': '4.2.104',
        'current_United_version_code': 3622, 'actual_successor_outputs_reconstructed': 6,
        'current_provider_and_preflight_outputs_reconstructed': current_inputs['current_outputs_reconstructed'],
        'current_provider_source_identities_consumed': current_inputs['selected_provider_source_identities'],
        'current_source_consumer_state': current_inputs['state'],
        'required_apps': 39, 'public_version_observations_with_supplement': 28,
        'United_4_2_104_payload_pending': False, 'SDK_commands': 0, 'Android_actions': 0,
        'APK_or_GSI_bodies_read': 0, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
