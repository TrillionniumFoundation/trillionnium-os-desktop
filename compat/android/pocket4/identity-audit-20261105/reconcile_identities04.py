#!/usr/bin/env python3
"""Reconcile immutable identity/signature observations locally; no device calls."""
from pathlib import Path
import base64, copy, datetime, hashlib, json, re, types

HERE = Path(__file__).resolve().parent
OUT = HERE / 'public-metadata'
ANDROID = '{http://schemas.android.com/apk/res/android}'
PINS = {
    'actual01/result.json': '750cd5e2b690d8c7a881c88bb067e18ea7c3ad8cd48cca1470314f789c628a45',
    'actual02/result.json': '241fcdc1d7f84dfbb6ac2ee13245d26414051ddc6314e47bd4316d4b21aeaa1d',
    'actual03/result.json': '03929215f63de74ed9bfbe773a2cfd2f01804355cb4175553a27a0fd21b713a5',
    '../media-calendar08/read-metadata01-result.json': '8296ee292d7d95930b74cbecb7323c5de5aebf3e0d4a787f78e0f9a8b7e70848',
    '../webview-flow08/decode_manifest.py': '2483008850e6e6d2de61612e3e87833e9d4fc40251d9d43ce75a98fbd2445dd2',
}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(name):
    raw = (HERE / name).read_bytes(); need(sha(raw) == PINS[name], 'RETAINED_INPUT_CHANGED:' + name)
    return json.loads(raw)


def write(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    with path.open('xb') as out:
        out.write(raw)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def main():
    original, retained, extra, pair = (read(p) for p in list(PINS)[:4])
    decoder_source = (HERE / '../webview-flow08/decode_manifest.py').read_bytes()
    need(sha(decoder_source) == PINS['../webview-flow08/decode_manifest.py'], 'DECODER_CHANGED')
    module = types.ModuleType('existing_identity_axml_decoder')
    exec(compile(decoder_source, 'existing_decode_manifest.py', 'exec'), module.__dict__)
    need(original['state'] == 'COMPLETED_WITH_GAPS_OR_VERIFICATION_FAILURES' and
         original['identity_complete_count'] == original['signature_complete_count'] == 34,
         'ORIGINAL_EXIT2_BOUNDARY_CHANGED')
    need(len(original['apps']) == 45 and original['apk_count'] == 86 and original['tools_unchanged']
         and original['selected_pm_identity_before_after_equal'] and original['launcher_set_unchanged']
         and original['expected_45_launcher_set_equal'], 'ORIGINAL_COVERAGE_OR_INPUT_DRIFT')
    need(extra['state'] == 'NINE_EXACT_APK_MANIFESTS_AND_CURRENT_READBACK_RETAINED' and
         extra['original_result_sha256'] == PINS['actual01/result.json'] and extra['signature_verifier_runs'] == 0,
         'TARGETED_READBACK_INCOMPLETE')
    need(original['guard_before'] == original['guard_after'] == extra['guard_before'] == extra['guard_after']
         == pair['guard_before'] == pair['guard_after'], 'MAIN_EPOCH_DIFFERS')
    gaps = {x['package']: x for x in retained['gaps']}
    need(len(gaps) == 11 and set(extra['packages']) | set(pair['packages']) == set(gaps)
         and not (set(extra['packages']) & set(pair['packages'])), 'EXACT_GAP_COVERAGE_REQUIRED')
    rows, manifest_projection, warnings = [], {}, []
    for app in original['apps']:
        package, identity = app['package'], app['identity']
        row = {'package': package, 'android_user': 0, 'uid': identity['uid'],
               'app_id': identity['app_id'], 'version_code': identity['version_code'],
               'version_name': identity['version_name'], 'min_sdk': identity['min_sdk'],
               'target_sdk': identity['target_sdk'], 'cpu_abi': identity['cpu_abi'],
               'user_state_observed': identity['user_state'],
               'launcher_components': [c for c in original['launcher_after'] if c.split('/')[0] == package],
               'original_observation_window': {k: app[k] for k in ('started_utc', 'finished_utc')},
               'original_combined_gate_passed': app['identity_complete'] and app['signature_complete'],
               'prior_inventory_uid_and_version_equal': app['prior_inventory_identity_equal'],
               'identity_qualified': False, 'apk_signature_qualified': False,
               'runtime_engine': {'status': 'NOT_QUALIFIED_BY_THIS_AUDIT', 'process_mapping_observed': False},
               'business_flow_qualified_by_this_audit': False, 'apks': []}
        for apk in app['apks']:
            signature = apk['signature']
            need(signature['verified'] and signature['tool_exit_code'] == 0 and signature['joined']
                 and not signature['timed_out'] and signature['signer_certificate_sha256'], 'REAL_SIGNATURE_NOT_VERIFIED')
            entry = {'ordinal': apk['ordinal'], 'bytes': apk['bytes'], 'sha256': apk['sha256'],
                     'signature': {k: signature[k] for k in ['verified', 'tool_exit_code', 'signer_certificate_sha256',
                                      'verified_schemes', 'stdout_sha256', 'stderr_sha256']},
                     'original_held_hash_before_after_equal': apk.get('held_file_unchanged', False)}
            if 'manifest' in apk:
                entry['manifest_identity'] = copy.deepcopy(apk['manifest'])
                entry['manifest_source'] = 'ORIGINAL_AAPT_BADGING_EXIT0'
            row['apks'].append(entry)
        certs = [a['signature']['signer_certificate_sha256'] for a in app['apks']]
        need(all(c == certs[0] for c in certs), 'BASE_SPLIT_CERTIFICATE_DISAGREEMENT')
        if package not in gaps:
            need(app['identity_complete'] and app['signature_complete'] and app['current_path_inode_readback_equal']
                 and all(a['held_file_unchanged'] for a in app['apks']), 'ORIGINAL_COMPLETE_ROW_DRIFT')
            row['content_identity_readback'] = 'ORIGINAL_HELD_FD_HASH_AND_CURRENT_PATH_READBACK'
        else:
            need(len(app['apks']) == 1, 'GAP_IS_NOT_SINGLE_APK')
            old = app['apks'][0]
            if package in extra['packages']:
                observed = extra['packages'][package]
                need(observed['same_signature_verified_content'] and observed['apk_before'] == observed['apk_after']
                     and observed['apk_before']['sha256'] == old['sha256'] and observed['apk_before']['bytes'] == old['bytes'],
                     'TARGETED_APK_HASH_DIFFERS')
                need(all(observed['identity_before'][k] == identity[k] == observed['identity_after'][k]
                         for k in ('uid', 'version_code', 'min_sdk', 'target_sdk')), 'TARGETED_PM_IDENTITY_DIFFERS')
                record = observed['manifest']
                abis = observed['embedded_native_abis']
                row['supplemental_observation_window'] = {k: observed[k] for k in ('started_utc', 'finished_utc')}
                row['supplemental_source_result_sha256'] = PINS['actual03/result.json']
                row['content_identity_readback'] = 'TARGETED_SAME_APK_HASH_AND_HELD_CURRENT_PATH_READBACK'
            else:
                observed = pair['packages'][package]
                need(observed['apk_sha256'] == old['sha256'] and observed['apk_bytes'] == old['bytes']
                     and observed['uid'] == identity['uid'] and observed['version_code'] == identity['version_code'],
                     'INDEPENDENT_METADATA_APK_DIFFERS')
                # Their original full-file before/after hash and path readback
                # already completed before aapt's resource/icon gate failed.
                retained_app = gaps[package]['retained_record']
                need(old['held_file_unchanged'] and retained_app['apks'][0]['before'] == retained_app['apks'][0]['after'],
                     'PAIR_ORIGINAL_FILE_READBACK_MISSING')
                record = observed['manifest']; abis = None
                row['supplemental_observation_window'] = {k: pair[k] for k in ('started_utc', 'finished_utc')}
                row['supplemental_source_result_sha256'] = PINS['../media-calendar08/read-metadata01-result.json']
                row['content_identity_readback'] = 'ORIGINAL_STABLE_FILE_PLUS_INDEPENDENT_SAME_APK_MANIFEST_CAPTURE'
            data = base64.b64decode(record['base64'], validate=True)
            need(len(data) == record['bytes'] and sha(data) == record['sha256'], 'AXML_BYTES_CHANGED')
            elements = module.decode(data)
            root = [e['attributes'] for e in elements if e['path'] == 'manifest']
            sdk = [e['attributes'] for e in elements if e['path'] == 'manifest/uses-sdk']
            need(len(root) == len(sdk) == 1, 'UNIQUE_MANIFEST_AND_SDK_REQUIRED')
            root, sdk = root[0], sdk[0]
            need(root['package'] == package and 'split' not in root, 'MANIFEST_PACKAGE_OR_BASE_DIFFERS')
            declared = root.get(ANDROID + 'versionCode')
            if declared is None:
                need(package == 'local.pocket4.fixture' and identity['version_code'] == 0, 'UNEXPECTED_ABSENT_VERSION')
            else:
                need(type(declared) is int and declared == identity['version_code'], 'AXML_VERSION_DIFFERS')
            need(sdk[ANDROID + 'minSdkVersion'] == identity['min_sdk']
                 and sdk[ANDROID + 'targetSdkVersion'] == identity['target_sdk'], 'AXML_SDK_DIFFERS')
            selected = {'package': package, 'manifest_sha256': record['sha256'], 'manifest_bytes': record['bytes'],
                        'version_code_declared': declared is not None, 'declared_version_code': declared,
                        'package_manager_version_code': identity['version_code'],
                        'declared_version_name': root.get(ANDROID + 'versionName'),
                        'min_sdk': sdk[ANDROID + 'minSdkVersion'], 'target_sdk': sdk[ANDROID + 'targetSdkVersion'],
                        'split_name': None, 'embedded_native_abis': abis,
                        'embedded_native_abi_observation': 'ZIP_CENTRAL_DIRECTORY' if abis is not None else 'NOT_COLLECTED_IN_INDEPENDENT_PAIR_CAPTURE'}
            manifest_projection[package] = selected
            row['apks'][0]['manifest_identity'] = selected
            row['apks'][0]['manifest_source'] = 'EXACT_APK_BINARY_XML_DECODED_WITH_EXISTING_PINNED_DECODER'
            badge = gaps[package]['badging']
            errors = [s.split('error: ', 1)[-1] for s in badge['stderr'].splitlines() if 'error:' in s]
            warnings.append({'package': package, 'original_badging_rc': badge['status']['rc'],
                             'resource_type_warning_rows': sum('W ResourceType:' in s for s in badge['stderr'].splitlines()),
                             'errors': errors, 'stdout_sha256': badge['stdout_sha256'], 'stderr_sha256': badge['stderr_sha256'],
                             'fixture_missing_version_attribute': declared is None})
            row['original_gate_error_retained'] = app['error_code']
        row['identity_qualified'] = True; row['apk_signature_qualified'] = True
        row['base_split_certificate_identity_equal'] = True
        need(sum(a['manifest_identity'].get('split_name') in (None, '') for a in row['apks']) == 1,
             'ONE_BASE_APK_REQUIRED')
        rows.append(row)
    need(len(rows) == len({r['package'] for r in rows}) == 45 and sum(len(r['apks']) for r in rows) == 86,
         'FINAL_COVERAGE_DIFFERS')
    result = {'schema': 'pocket4-reconciled-installed-identities-v1',
              'state': '45_PACKAGE_IDENTITIES_AND_86_APK_SIGNATURES_VERIFIED_WITH_SEPARATE_METADATA_RECONCILIATION',
              'reconciled_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'observation_window': {'started_utc': original['started_utc'], 'finished_utc': extra['finished_utc']},
              'snapshot_scope': 'Per-app bounded observations across the stated window, not an atomic all-package snapshot.',
              'runtime_sdk': original['runtime_sdk'], 'main_epoch_sha256': original['guard_after']['epoch_sha256'],
              'same_held_main_epoch': True, 'packages_qualified': 45, 'apks_signature_verified': 86,
              'base_apks': 45, 'split_apks': 41, 'signature_rejections_observed': 0,
              'all_base_split_certificates_equal': True, 'current_45_launcher_set_unchanged_during_original_audit': True,
              'original_terminal': {'job_id': '1a1ab6034c5-fc05-4d19', 'exit_code': 2, 'identity_and_signature_combined_count': 34,
                                    'result_sha256': PINS['actual01/result.json'], 'preserved': True},
              'supplemental_terminal': {'retained_reader_job': '1a1ab67bda6-fc05-4d73', 'retained_reader_exit': 0,
                                        'nine_manifest_job': '1a1ab6e5161-fc05-4dcd', 'nine_manifest_exit': 0,
                                        'independent_calendar_gallery_job': '1a1ab68b882-fc05-4d89', 'independent_calendar_gallery_exit': 0},
              'source_pins': PINS, 'tools': original['tools'], 'tool_hashes_unchanged': original['tools_unchanged'],
              'system_native_shared_libraries_fully_frozen': False,
              'original_resource_observation': original['own_resources_after'],
              'supplemental_nine_resource_observation': extra['resources_after'],
              'retained_metadata_warnings': warnings, 'apps': rows,
              'UI_actions': 0, 'installs': 0, 'signing_operations': 0, 'signature_verifier_reruns': 0,
              'existing_app_permissions_changed': False, 'runtime_engine_mappings_qualified': 0,
              'business_flows_qualified_by_this_audit': 0, 'whole_app_production_ready': False,
              'limitations': [
                  'The original resource-table/icon errors remain retained. Independent AXML decoding qualifies manifest identity only, not every resource or actual UI rendering.',
                  'The fixture declares no versionCode; its observed PackageManager version is 0. The projection does not invent a declared version attribute.',
                  'Signature verification and certificate fingerprints establish cryptographic integrity of the observed files, not publisher trust or application behavior.',
                  'No running ARM-engine process mapping was collected; package ABI and embedded native libraries are not substituted for that evidence.',
                  'The first unit reached its 768 MiB memory ceiling and recorded 25708 memory.max events. OOM and OOM-kill were zero; this was not a zero-pressure run.',
                  'The selected SDK/JRE/signer dependencies were hash-frozen, but all host native shared libraries were not fully frozen.',
              ]}
    OUT.mkdir(exist_ok=False)
    p = write(OUT / 'installed-app-identities.json', result)
    write(OUT / 'manifest-gap-projection.json', {'decoder_sha256': PINS['../webview-flow08/decode_manifest.py'], 'packages': manifest_projection})
    private_pair = {'original_observation_window': {'started_utc': original['started_utc'], 'finished_utc': original['finished_utc']},
                    'source_result_sha256': PINS['actual01/result.json'], 'retained_reader_sha256': PINS['actual02/result.json'],
                    'packages': {}}
    for package in ('com.android.calendar', 'com.android.gallery3d'):
        permission_rows = retained['existing_permissions'][package]
        semantic = [{k: v for k, v in item.items() if k != 'dump_sha256'} for item in permission_rows]
        need(semantic[0] == semantic[1], 'ORIGINAL_PERMISSION_PROJECTION_CHANGED')
        private_pair['packages'][package] = {
            'pm_path': gaps[package]['retained_record']['apks'][0]['guest_path'],
            'unique_observed_launcher_component': next(r['launcher_components'][0] for r in rows if r['package'] == package),
            'component_source': 'Saved current query-activities output, not a new resolve-activity call',
            'permissions': semantic[0], 'permissions_before_after_equal': True,
            'permission_dump_sha256': [x['dump_sha256'] for x in permission_rows]}
    write(HERE / 'gallery-calendar-fixture-reference01-private.json', private_pair)
    print(json.dumps({'output': str(OUT / 'installed-app-identities.json'), **p,
                      'packages_qualified': 45, 'apks_verified': 86, 'original_exit2_preserved': True,
                      'business_flows_added': 0, 'device_queries': 0}))


if __name__ == '__main__':
    main()
