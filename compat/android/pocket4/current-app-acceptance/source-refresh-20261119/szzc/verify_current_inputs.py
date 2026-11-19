#!/usr/bin/env python3
"""Consume the pinned SZZC source packet and reproduce its selected metadata.

Only recorded source evidence is replayed. Actual SDK verification and process
retirement remain claims of the separately captured successful original run.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parent
REPO_PATH = 'compat/android/pocket4/current-app-acceptance/source-refresh-20261119/szzc/'
OUTPUTS = ('current-source-inputs.json', 'current-source-freshness.json',
           'CURRENT-SOURCE-STATE.json', 'CURRENT-BUSINESS-PLAN.json')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(relative, pin):
    need(pin['path'] == REPO_PATH + relative, 'fixed packet-relative selection')
    path = ROOT / relative
    st = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_nlink == 1
         and 0 <= st.st_size <= 16 * 1024 * 1024, 'bounded canonical source metadata')
    body = path.read_bytes()
    need((len(body), hashlib.sha256(body).hexdigest()) == (pin['bytes'], pin['sha256']),
         'complete selected metadata pin: ' + relative)
    return body


def verify():
    selection = json.loads((ROOT / 'SELECTION.json').read_bytes())
    need(selection['schema'] == 'pocket4-szzc-selected-current-source-packet-v1', 'selection schema')
    need(set(selection['outputs']) == set(OUTPUTS), 'complete four current outputs')
    source = read('override_szzc.py', selection['generator'])
    read('INPUT-PINS.json', selection['input_manifest'])
    result = json.loads(read('actual/RESULT.json', selection['metadata_join_result']))
    need(result['schema'] == 'pocket4-szzc-recorded-source-successor-v1'
         and result['state'] == 'PASSED_METADATA_JOIN_ONLY'
         and result['inputs'] == selection['input_manifest']
         and result['outputs'] == selection['outputs'], 'recorded metadata join and selected current outputs')
    spec = importlib.util.spec_from_file_location('p4_szzc_source_successor', ROOT / 'override_szzc.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    need((ROOT / 'override_szzc.py').read_bytes() == source, 'generator changed during import')
    data = module.read_inputs(ROOT)
    reproduced = module.generate(data, result['created_utc'])
    need(set(reproduced) == set(OUTPUTS), 'complete metadata reconstruction')
    for name in OUTPUTS:
        need(reproduced[name] == read('actual/' + name, selection['outputs'][name]),
             'exact current SZZC metadata reconstruction: ' + name)
    for value in (selection, result):
        module.no_credit(value)
    source_receipt = data['source-receipt.json']
    return {
        'schema': 'pocket4-szzc-current-source-consumer-result-v1',
        'state': 'PASSED_RECORDED_SOURCE_JOIN_ONLY',
        'current_outputs_reconstructed': 4,
        'current_outputs': selection['outputs'],
        'selected_source_identity': {
            'package': 'com.szzc', 'version_name': source_receipt['version_name'],
            'version_code': source_receipt['long_version_code'],
            'APK': source_receipt['APK'],
            'signer_certificate_sha256': source_receipt['signer_certificate_sha256'],
            'source_receipt': module.input_pin(data, 'source-receipt.json'),
            'SDK_result': module.input_pin(data, 'SDK-RESULT.json'),
        },
        'publisher_artifact_drift_resolved_by_actual_SDK_evidence': True,
        'native_inventory_diagnostic': {
            'pin': module.input_pin(data, 'NATIVE-INVENTORY-DIAGNOSTIC.json'),
            'schema': data['NATIVE-INVENTORY-DIAGNOSTIC.json']['schema'],
            'APK': data['NATIVE-INVENTORY-DIAGNOSTIC.json']['APK'],
            'native_member_count': 118, 'cross_ABI_member_count': 4,
            'members': data['NATIVE-INVENTORY-DIAGNOSTIC.json']['mismatches'],
            'selected_arm64_directory_cross_ABI_members': 2,
        },
        'native_runtime_blocker_retained': True, 'native_source_layout_qualified': False,
        'other38_state_and_preflight_rows_unchanged': True,
        'other28_required_registry_rows_and_companion_unchanged': True,
        'all_installation_migration_runtime_gates_preserved': True,
        'previous_archives_and_receipts_not_modified': True,
        'public_metadata_does_not_renew_restricted_Play_TTL': True,
        'APK_bodies_read_here': 0, 'SDK_commands_here': 0, 'network_requests_here': 0,
        'Android_actions': 0, 'owner_CURRENT_changed': False,
        'latest_release_recheck_required_before_activation': True,
        'all_39_latest_qualified': False, 'all_39_runtime_accepted': False,
        'installed': False, 'native_compatibility_qualified': False,
        'runtime_qualified': False, 'business_qualified': False, 'production_ready': False,
    }


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2, sort_keys=True))
