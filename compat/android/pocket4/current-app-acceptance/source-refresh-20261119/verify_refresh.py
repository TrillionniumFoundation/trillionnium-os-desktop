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
    complete_szzc_receipt = name == 'szzc/inputs/source-receipt.json'
    if complete_szzc_receipt:
        require(info.st_size == 4231750, 'exact complete SZZC source receipt size before read')
    else:
        require(info.st_size <= 2 * 1024 * 1024, 'bounded metadata member before read')
    body = path.read_bytes()
    require(len(body) == info.st_size, 'metadata member byte count remains unchanged')
    if complete_szzc_receipt:
        require(hashlib.sha256(body).hexdigest() == '7cc2ef5420115fd3c75a137ae48c6794b45cee509b332a357657e44cb29c3eec',
                'the only larger metadata member is the exact actual complete SZZC receipt')
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


def current_szzc_native_inventory(index, selected_szzc):
    """Consume the fixed original diagnosis; retain every native runtime gate."""
    fixed = {'path':'compat/android/pocket4/current-app-acceptance/source-refresh-20261119/szzc/inputs/NATIVE-INVENTORY-DIAGNOSTIC.json',
             'bytes':91834,'sha256':'6ca274d5ecfa097ad67a50ab4a5aacdcf2bb0f2ed26d74067acc2ab9b04fc4fd'}
    api = selected_szzc['native_inventory_diagnostic']
    require(api['pin'] == fixed, 'exact original native diagnosis selected by SZZC receipt')
    body = read('szzc/inputs/NATIVE-INVENTORY-DIAGNOSTIC.json')
    check_pin(body, fixed)
    diagnosis = json.loads(body)
    require(diagnosis['schema'] == api['schema'] == 'pocket4-szzc-original-native-inventory-diagnostic-v1'
            and diagnosis['native_member_count'] == api['native_member_count'] == 118
            and diagnosis['mismatch_count'] == api['cross_ABI_member_count'] == 4
            and diagnosis['directory_ABIs'] == ['arm64-v8a','armeabi-v7a'],
            'complete original SZZC native inventory has two directories and four header mismatches')
    expected = {
        'lib/arm64-v8a/libexecmain_x86.so':(211616,'f2358a1888e0321f773875cffdce6629b3987f5237aca10d80bb4b51cfbee0ad',2,62,'arm64-v8a'),
        'lib/arm64-v8a/libexec_x86.so':(667144,'7ad636af838b62daa7fb02bb440504c46b58d03040aee4bdb137b2686d5e7f89',2,62,'arm64-v8a'),
        'lib/armeabi-v7a/libexecmain_x86.so':(132520,'937776804511269ce1d0c375fdac2d4ac3dfba6704bdf59a8e1be83851cd1cfb',1,3,'armeabi-v7a'),
        'lib/armeabi-v7a/libexec_x86.so':(556824,'db40145f67b021701ede31205357fc81e69a67825f061bc9d01e9bd739d79bd4',1,3,'armeabi-v7a')}
    rows = diagnosis['native_members']
    require(len(rows) == len({row['name'] for row in rows}) == 118, 'all original native member names are distinct')
    mismatch = []
    for row in rows:
        header = bytes.fromhex(row['header_hex'])
        require(len(header) == 64 and header[:4] == b'\x7fELF' and header[5] == 1,
                'complete original little-endian ELF header metadata')
        actual = (header[4], int.from_bytes(header[18:20], 'little'))
        declared = {'arm64-v8a':(2,183),'armeabi-v7a':(1,40)}[row['directory_ABI']]
        require(row['name'].startswith('lib/' + row['directory_ABI'] + '/')
                and actual == (row['actual_class'],row['actual_machine'])
                and list(declared) == row['expected_class_machine']
                and row['directory_ABI_matches_ELF'] is (actual == declared)
                and row['complete_EOF_CRC_verified'] is True
                and row['APK_or_library_executed'] is False
                and row['native_compatibility_qualified'] is False,
                'original header facts retain native non-execution and exact directory relationship')
        if actual != declared:
            mismatch.append(row)
    require(mismatch == diagnosis['mismatches'], 'original diagnostic mismatches equal the full118 inventory projection')
    fields = ('bytes','sha256','actual_class','actual_machine','directory_ABI')
    for values in (mismatch, api['members']):
        require(len(values) == 4 and len({row['name'] for row in values}) == 4
                and {row['name']:tuple(row[key] for key in fields) for row in values} == expected,
                'four exact original cross-ABI members and full member SHA identities')
    require(api['selected_arm64_directory_cross_ABI_members'] == 2
            and selected_szzc['native_runtime_blocker_retained'] is True,
            'two cross-ABI helpers in selected arm64 directory keep the native runtime blocker open')
    for key in ('path','bytes','sha256','identity'):
        require(diagnosis['APK'][key] == selected_szzc['selected_source_identity']['APK'][key],
                'original diagnosis and completed SDK evidence identify the same unmodified APK')
    require(diagnosis['generic_validator_changed'] is False and diagnosis['source_identity_verified'] is False
            and diagnosis['signature_verified'] is False and diagnosis['all_input_bookends_unchanged'] is True,
            'original pre-SDK failure diagnosis remains a diagnosis, with no generic validator relaxation')
    for key in ('installed','native_compatibility_qualified','runtime_qualified','business_qualified','production_ready'):
        require(diagnosis[key] is False, 'native diagnosis grants no runtime acceptance: ' + key)
    for key in ('APK_or_library_executions','Android_actions','SDK_commands','user_data_reads'):
        require(type(diagnosis[key]) is int and diagnosis[key] == 0, 'native diagnosis original action boundary: ' + key)
    require(index['current_SZZC_native_runtime_blocker'] == {
        'diagnostic':api,'retained':True,'native_compatibility_qualified':False,
        'runtime_qualified':False,'business_qualified':False,'production_ready':False},
        'current source index preserves the exact unresolved native inventory blocker')


def current_szzc_source_inputs(index, previous_index):
    """Consume the real four-output SZZC successor after historical reconstruction."""
    prefix = 'compat/android/pocket4/current-app-acceptance/source-refresh-20261119/szzc/'
    selected = {'current_source_packet_manifest': 'SELECTION.json',
                'current_source_packet_verifier': 'verify_current_inputs.py'}
    for key, member in selected.items():
        row = index[key]
        require(row['path'] == prefix + member and set(row) == {'path','bytes','sha256'},
                'fixed selected SZZC source consumer member')
        check_pin(read('szzc/' + member), row)
    source = read('szzc/verify_current_inputs.py')
    spec = importlib.util.spec_from_file_location('selected_szzc_source_inputs', ROOT / 'szzc/verify_current_inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(read('szzc/verify_current_inputs.py') == source, 'selected SZZC consumer source bookend')
    result = module.verify()
    require(read('szzc/verify_current_inputs.py') == source, 'selected SZZC consumer complete verification bookend')
    require(result['state'] == 'PASSED_RECORDED_SOURCE_JOIN_ONLY' and result['current_outputs_reconstructed'] == 4,
            'all four actual selected SZZC source outputs reconstructed')
    selection = json.loads(read('szzc/SELECTION.json'))
    current_result = dict(selection['metadata_join_result'])
    require(current_result['path'] == prefix + 'actual/RESULT.json', 'fixed actual SZZC result member')
    current_result['path'] = 'szzc/actual/RESULT.json'
    require(index['current_SZZC_successor'] == current_result, 'selected SZZC result is the actually verified result')
    check_pin(read(current_result['path']), current_result)
    require(index['current_system_provider_cohort'] == previous_index['current_system_provider_cohort'],
            'current four-provider cohort is the exact verified predecessor cohort')
    mapping = {'current_registry':'current-source-inputs.json',
               'current_freshness':'current-source-freshness.json',
               'current_source_state':'CURRENT-SOURCE-STATE.json',
               'current_business_preflight':'CURRENT-BUSINESS-PLAN.json'}
    require(set(result['current_outputs']) == set(mapping.values()), 'exact four current output identities')
    for key, name in mapping.items():
        expected = result['current_outputs'][name]
        require(expected['path'] == prefix + 'actual/' + name, 'fixed SZZC current output path')
        chosen = dict(expected)
        if key != 'current_business_preflight':
            chosen['path'] = 'szzc/actual/' + name
        require(index[key] == chosen, 'source-refresh actually selects the SZZC successor: ' + key)
        check_pin(read('szzc/actual/' + name), expected)
        original = read(previous_index[key]['path']) if key != 'current_business_preflight' else None
        if original is not None:
            require(read('szzc/inputs/base-' + name) == original, 'actual United output is SZZC predecessor')
    prior_plan = ROOT.parents[4] / SELECTED_CURRENT_PATHS['current_business_preflight']
    info = prior_plan.lstat()
    require(prior_plan.resolve() == prior_plan and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_size == previous_index['current_business_preflight']['bytes']
            and info.st_size <= 2 * 1024 * 1024,
            'ordinary fixed previous provider preflight')
    body = prior_plan.read_bytes()
    check_pin(body, previous_index['current_business_preflight'])
    require(body == read('szzc/inputs/base-CURRENT-BUSINESS-PLAN.json'), 'actual previous provider preflight is SZZC base')
    for key in ('other38_state_and_preflight_rows_unchanged',
                'other28_required_registry_rows_and_companion_unchanged',
                'all_installation_migration_runtime_gates_preserved',
                'previous_archives_and_receipts_not_modified',
                'public_metadata_does_not_renew_restricted_Play_TTL',
                'publisher_artifact_drift_resolved_by_actual_SDK_evidence'):
        require(result[key] is True, 'complete selected current source contract: ' + key)
    for key in ('all_39_latest_qualified','all_39_runtime_accepted','installed',
                'native_source_layout_qualified','native_compatibility_qualified',
                'runtime_qualified','business_qualified','production_ready'):
        require(result[key] is False, 'no source-to-runtime promotion: ' + key)
    for key in ('APK_bodies_read_here','SDK_commands_here','network_requests_here','Android_actions'):
        require(type(result[key]) is int and result[key] == 0, 'recorded evidence consumer has no actions: ' + key)
    require(result['owner_CURRENT_changed'] is False and result['latest_release_recheck_required_before_activation'] is True,
            'source selection preserves owner and activation admission')
    registry = json.loads(read(index['current_registry']['path']))
    plan = json.loads(read('szzc/actual/CURRENT-BUSINESS-PLAN.json'))
    identity = result['selected_source_identity']
    selected_row = next(row for row in registry['applications'] if row['package'] == 'com.szzc')
    planned_row = next(row for row in plan['packages'] if row['package'] == 'com.szzc')
    require(identity['package'] == selected_row['package'] and identity['version_name'] == selected_row['version_name']
            and identity['version_code'] == selected_row['version_code']
            and all(identity['APK'][k] == selected_row['input'][k] for k in ('path','bytes','sha256'))
            and planned_row['source_body_pin_metadata'] == selected_row['input'],
            'actual current registry and business plan share one qualified SZZC body')
    require(index['resolved_publisher_artifact_drift'] == {
        'package':'com.szzc',
        'previous_selected_APK':{'bytes':220522994,'sha256':'7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96'},
        'new_selected_source_identity':identity,
        'actual_SDK_source_qualified':True,'metadata_observation_alone_grants_no_qualification':True,
        'installed':False,'runtime_qualified':False,'business_qualified':False,'production_ready':False},
        'publisher drift resolution index exactly reflects independently qualified source identity')
    current_szzc_native_inventory(index, result)
    return result


def late_public_metadata(index, previous_index, selected_szzc):
    fixed = {'late_public_metadata_consumer':'late-metadata/verify_late_metadata.py',
             'late_public_metadata_summary':'late-metadata/OBSERVATION-SUMMARY.json'}
    for key, name in fixed.items():
        require(index[key]['path'] == name, 'fixed late-public-metadata selection')
        check_pin(read(name), index[key])
    source = read(fixed['late_public_metadata_consumer'])
    spec = importlib.util.spec_from_file_location('late_public_source_metadata', ROOT / fixed['late_public_metadata_consumer'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(read(fixed['late_public_metadata_consumer']) == source, 'late consumer complete source bookend')
    basis = {key:read(previous_index[key]['path']) for key in
             ('current_source_state','current_registry','current_freshness')}
    result = module.verify(basis, previous_index['current_business_preflight'])
    require(read(fixed['late_public_metadata_consumer']) == source, 'late consumer complete verification bookend')
    require(result['state'] == 'PASS_PUBLIC_METADATA_EVIDENCE_ONLY'
            and result['matching_public_version_or_exact_build_observations'] == 28
            and result['publisher_body_identity_pending_at_observation'] == ['com.szzc']
            and result['system_GSI_publication_observations'] == 2
            and result['system_apps_bound_to_original_CP3A'] == 10,
            'actual public observations retain their original source-selection basis')
    require(read('szzc/inputs/PUBLISHER-REDIRECT-HEAD.json')
            == read('late-metadata/inputs/actual/PUBLISHER-REDIRECT-HEAD.json'),
            'SZZC SDK successor starts from the exact observed publisher drift')
    pending = next(row for row in result['rows'] if row['package'] == 'com.szzc')
    require(selected_szzc['publisher_artifact_drift_resolved_by_actual_SDK_evidence'] is True
            and selected_szzc['selected_source_identity']['APK']['bytes'] == pending['publisher_content_length'],
            'the pending publisher drift has a separate actual SDK/custody resolution')
    for key in ('all39_latest_qualified','authoritative_play_metadata_TTL_renewed',
                'activation_metadata_revalidated','installed','runtime_qualified','business_qualified','production_ready'):
        require(result[key] is False, 'public metadata does not clear qualification gate: ' + key)
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
    require(index['historical_source_overrides'] == ['com.lianjia.beike', 'com.united.mobile.android', 'com.szzc'],
            'preserved Beike and United history plus the actual SZZC source successor')
    previous_pin = index['previous_refresh_index']
    require(previous_pin == {'path': 'history-before-united/SOURCE-REFRESH.json', 'bytes': 2153,
            'sha256': '3e6d6c9365760bc727d0f66cfb366cd71090b0626623a6789df2e575f0c522ae'},
            'exact prior Beike selection index remains history')
    check_pin(read(previous_pin['path']), previous_pin)
    previous_index = json.loads(read(previous_pin['path']))
    previous_united_pin = index['previous_united_refresh_index']
    require(previous_united_pin == {'path':'history-before-szzc/SOURCE-REFRESH.json','bytes':3948,
        'sha256':'0c8f37157a90bae96c1f567f739f54dcdc9d67ec94d13df2aa2532266def0afe'},
        'exact previous United/provider source selection remains history')
    check_pin(read(previous_united_pin['path']), previous_united_pin)
    previous_united_index = json.loads(read(previous_united_pin['path']))
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
        row = previous_united_index[key]
        require(row['path'] == 'united/actual/' + name and
                row['bytes'] == united_result['outputs'][name]['bytes'] and
                row['sha256'] == united_result['outputs'][name]['sha256'], 'selected current United successor')
    registry = json.loads(read(previous_united_index['current_registry']['path']))
    freshness = json.loads(read(previous_united_index['current_freshness']['path']))
    state = json.loads(read(previous_united_index['current_source_state']['path']))
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
    current_inputs = current_source_inputs(previous_united_index)
    selected_szzc = current_szzc_source_inputs(index, previous_united_index)
    late_observations = late_public_metadata(index, previous_united_index, selected_szzc)
    print(json.dumps({'state': 'PASS_SOURCE_REFRESH_EVIDENCE_ONLY', 'packet_files': len(inventory),
        'current_Beike_version': '3.06.80', 'current_United_version': '4.2.104',
        'current_United_version_code': 3622, 'actual_successor_outputs_reconstructed': 6,
        'current_provider_and_preflight_outputs_reconstructed': current_inputs['current_outputs_reconstructed'],
        'current_provider_source_identities_consumed': current_inputs['selected_provider_source_identities'],
        'historical_provider_source_consumer_state': current_inputs['state'],
        'current_source_consumer_state': selected_szzc['state'],
        'current_SZZC_outputs_reconstructed': selected_szzc['current_outputs_reconstructed'],
        'current_SZZC_version': selected_szzc['selected_source_identity']['version_name'],
        'current_SZZC_version_code': selected_szzc['selected_source_identity']['version_code'],
        'current_SZZC_publisher_identity_drift_resolved': True,
        'current_SZZC_native_members': selected_szzc['native_inventory_diagnostic']['native_member_count'],
        'current_SZZC_cross_ABI_members': selected_szzc['native_inventory_diagnostic']['cross_ABI_member_count'],
        'current_SZZC_selected_arm64_cross_ABI_members': selected_szzc['native_inventory_diagnostic']['selected_arm64_directory_cross_ABI_members'],
        'current_SZZC_native_runtime_blocker_retained': selected_szzc['native_runtime_blocker_retained'],
        'native_source_layout_qualified': False,
        'native_compatibility_qualified': False,
        'installed': False,
        'runtime_qualified': False,
        'business_qualified': False,
        'all_39_latest_qualified': False,
        'all_39_runtime_accepted': False,
        'provider_preflight_reconstruction_is_pre_SZZC_history': True,
        'late_public_version_or_build_matches': late_observations['matching_public_version_or_exact_build_observations'],
        'late_public_observation_original_Play_TTL_renewed': False,
        'required_apps': 39, 'public_version_observations_with_supplement': 28,
        'United_4_2_104_payload_pending': False, 'SDK_commands': 0, 'Android_actions': 0,
        'APK_or_GSI_bodies_read': 0, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
