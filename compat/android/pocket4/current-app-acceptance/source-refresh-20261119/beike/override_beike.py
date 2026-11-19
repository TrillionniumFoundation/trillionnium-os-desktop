"""Bind one actually qualified Beike successor without rewriting source history.

This joins immutable metadata; it never invokes SDK tools or an Android process.
The final APK remains the only live payload. Retired HTTP range bodies are
historical transport evidence, not dependencies of this source-state successor.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat


PACKAGE = 'com.lianjia.beike'
VERSION = '3.06.80'
CODE = 3068010
SIGNER = '0b66624117621bb9bc3e7d12a1fe5436794cf8999b0253d9ff9bec71e0932178'
APK_SHA = '2338cf0c67ab23896bf4d5042314c6a94fb1710c250cb079247205a335417f74'
APK_BYTES = 230624085
ROOT = Path('/home/alex/work/p4-beike-current-arm64-11ea-20261119-r1')
QUAL = ROOT / 'source-qualification-r1'
APK = ROOT / 'beike-3.06.80-arm64.apk'
URL = 'https://imtt.dd.qq.com/sjy.00022/sjy.00004/16891/apk/31FDA322E15845B12B37E5779391351B.apk?fsname=com.lianjia.beike_3.06.80.apk'
EXEMPT = {'com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab'}
COMPANION = 'com.android.vending'
MEITUAN = 'com.sankuai.meituan.takeoutnew'
SYSTEM = {'com.android.' + name for name in ('calendar', 'camera2', 'contacts',
    'deskclock', 'dialer', 'documentsui', 'gallery3d', 'messaging', 'quicksearchbox', 'settings')}
NO_CREDIT = ('installed', 'runtime_qualified', 'native_compatibility_qualified',
             'business_qualified', 'production_ready')
DENIED_CREDIT = set(NO_CREDIT) | {'device_profile_match_qualified',
    'abi_compatibility_verified', 'dispatch_runtime_observed', 'native_execution_qualified',
    'all_39_runtime_accepted', 'signer_migration_qualified'}
BASE_ROOT = '/home/qq/work/p4-required39-source-state-11ea-20261119-r1/source-state-r1/'
PINS = {
    'base-state.json': (148477, '733a61ccfa1479beb83c20c3a00ad7748b8632544ae0f469707ec2998eb4148b'),
    'base-registry.json': (107093, 'df11d911c3df0fe502f8d628f2b33d2ddc343dc3ab2c3c2ef7cc9990ef92e8db'),
    'base-freshness.json': (102138, '13ab206ba669d57d368260d28f3c97eb66d9bff6eae65cc4f60dd1af122ad6d2'),
    'candidate.json': (1770, '48754c4fe4c3d7f51b152facf4807c58fd12988a26f9a74540b81ea3d2163cea'),
    'source-receipt.json': (13179, '46452cb13bfc8ed0b47bc929be5870d286d47107124d4daafc7c04f77609924c'),
    'native-input.json': (1046, 'e748d497a2ea0c50c329991fe36d16ef30d0cf8076a7ea8e5a00083c6dcad923'),
    'SOURCE.json': (5851, 'ae6f31e0007c84889decf37dcda9b714838b236fa6f597d1eefd0de81e481542'),
    'RESULT.json': (12247, '2a4a525f0321d1e0f4e2ca082f978383e7848bc6935d5a8a7756411f719c44bb'),
    'NATIVE-PAYLOADS.json': (18933, 'b4548c2d6ad302c47f8685dfd790de2ce3c437c36491a32c41a8b9453bc76bd1'),
    'PAGES.json': (4495, '4d29f7fb8e9935b57302cdbda24a2717219cecaf8c08ed166b7a6ecf2f5e75b4'),
    'transport-cleanup.json': (24120, 'b3266b3daf41e0b5bfb3474ffd2faaa60dccd38913c257826c84158eb9a4d62e'),
}
CROSS = {'path': 'lib/arm64-v8a/libjgclb_x86.so', 'kind': 'cross_arch_shared_library',
         'bytes': 992840, 'sha256': '7341951a925105ba15263c0f90943f41c740754a52821750d1317c23a1ae4676',
         'elf_class': 2, 'elf_machine': 62, 'elf_type': 3, 'entry_point': 0,
         'has_interpreter': False, 'soname': 'libjiagu.so'}


def need(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def constant(value):
        raise ValueError('nonfinite JSON number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def f9(value):
    return [getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def ref(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def p3(value):
    return {key: value[key] for key in ('path', 'bytes', 'sha256')}


def original_ref(name):
    path = {'base-state.json': BASE_ROOT + 'CURRENT-SOURCE-STATE.json',
            'base-registry.json': BASE_ROOT + 'current-source-inputs.json',
            'base-freshness.json': BASE_ROOT + 'current-source-freshness.json',
            'transport-cleanup.json': str(ROOT / 'transport-cleanup-r1/RESULT.json')}.get(name, str(QUAL / name))
    size, sha = PINS[name]
    return {'path': path, 'bytes': size, 'sha256': sha}


def read_inputs(directory, held=None):
    directory = Path(directory)
    need(directory.is_absolute() and directory.resolve(strict=True) == directory,
         'canonical immutable input directory required')
    data, refs = {}, {}
    for name, (size, sha) in PINS.items():
        path = directory / name
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == size,
                 'complete independent metadata file required: ' + name)
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(size + 1)
            need(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha and
                 f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'input pin or F9 changed: ' + name)
            if held is not None:
                need(held.setdefault(name, f9(before)) == f9(before), 'input bookend changed')
            data[name], refs[name] = parse(raw), ref(path, raw)
        finally:
            os.close(fd)
    return data, refs


def check_original_metadata(data, held):
    """Reopen only retained JSON proofs, never the retired transport bodies."""
    refs = [original_ref(name) for name in PINS if not name.startswith('base-')]
    source = data['SOURCE.json']
    refs += [p3(source['download_controller_receipt']),
             p3(source['download_closure']['original_failed_recovery']),
             p3(source['download_closure']['original_failed_short_GET']),
             p3(source['historical_public_candidate'])]
    need(len({row['path'] for row in refs}) == len(refs), 'unique live source JSON proof paths required')
    for row in refs:
        path = Path(row['path'])
        need(path.is_relative_to(ROOT) and path.suffix == '.json' and
             path.resolve(strict=True) == path and 0 <= row['bytes'] <= 2 * 1024**2,
             'bounded canonical original JSON proof required')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == row['bytes'],
                 'original proof identity differs')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(row['bytes'] + 1)
            need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'] and
                 f9(before) == f9(os.fstat(fd)) == f9(path.lstat()) and
                 held.setdefault(str(path), f9(before)) == f9(before), 'original JSON proof bookend differs')
        finally:
            os.close(fd)
    return refs


def no_credit(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DENIED_CREDIT:
                need(child is False, 'source-only execution boundary changed: ' + key)
            no_credit(child)
    elif isinstance(value, list):
        for child in value:
            no_credit(child)


def indexed(rows, count):
    need(type(rows) is list and len(rows) == count, 'complete package count required')
    out = {row['package']: row for row in rows}
    need(len(out) == count, 'duplicate or omitted package')
    return out


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(result.tzinfo is not None, 'timezone required')
    return result


def validate(data, at):
    """Check semantic joins as well as the fixed-byte admission in read_inputs."""
    base, registry, freshness = (data[name] for name in
        ('base-state.json', 'base-registry.json', 'base-freshness.json'))
    for value in data.values():
        no_credit(value)
    required = indexed(base['applications'], 39)
    apps, rows = indexed(registry['applications'], 30), indexed(freshness['rows'], 29)
    need(base['required_count'] == 39 and base['selected_count'] == 42 and
         len(base['exemptions']) == 3 and {x['package'] for x in base['exemptions']} == EXEMPT and
         SYSTEM <= set(required) and not (EXEMPT & set(required)) and
         set(apps) == (set(required) - SYSTEM) | {COMPANION} and
         set(rows) == set(required) - SYSTEM, '39/42 scope or exact three exemptions changed')
    need(base['source_evidence_count'] == 39 and base['system_source_evidence_count'] == 10 and
         base['third_party_source_evidence_count'] == 29 and base['remaining_missing_source_inputs'] == [] and
         base['all_39_latest_qualified'] is False and base['individual_system_APK_installation_allowed'] is False,
         'source coverage and full-GSI boundary changed')
    need(base['full_GSI_dependency']['sha256'] ==
         'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4' and
         base['full_GSI_dependency']['bytes'] == 2294853632, 'coherent original GSI required')
    need(base['current29_registry'] == original_ref('base-registry.json') and
         base['current29_freshness'] == original_ref('base-freshness.json'), 'historical base pins differ')
    need(apps[PACKAGE]['version_name'] == '3.06.71' and apps[PACKAGE]['version_code'] == 3067100 and
         required[PACKAGE]['unchanged_current_registry_record'] == apps[PACKAGE] and
         rows[PACKAGE]['selected_input_version'] == '3.06.71', 'one exact historical Beike input required')
    need(apps[MEITUAN]['signer_migration_qualified'] is False, 'Meituan migration remains pending')
    candidate, receipt, native, source, result, pages = (data[name] for name in
        ('candidate.json', 'source-receipt.json', 'native-input.json', 'SOURCE.json', 'RESULT.json', 'PAGES.json'))
    expected_apk = {'name': 'base.apk', 'bytes': APK_BYTES, 'sha256': APK_SHA}
    need(candidate['schema'] == 'pocket4-official-apk-candidate-v3' and
         candidate['package'] == PACKAGE and candidate['version_name'] == VERSION and
         candidate['version_code'] == CODE and candidate['version_code_major'] == 0 and
         candidate['min_sdk_version'] == 23 and candidate['target_sdk_version'] == 31 and
         candidate['native_abis'] == ['arm64-v8a'] and candidate['apk'] == expected_apk and
         candidate['signer_certificate_sha256'] == [SIGNER] and
         candidate['native_layout_exceptions'] == [CROSS], 'current unchanged V3 candidate contract differs')
    identity = receipt['identity']
    need(identity['package'] == PACKAGE and identity['version_name'] == VERSION and
         identity['version_code'] == identity['long_version_code'] == CODE and identity['version_code_major'] == 0 and
         identity['bytes'] == APK_BYTES and identity['sha256'] == APK_SHA and
         identity['metadata_outputs_bound_to_apk_sha256'] == APK_SHA and
         identity['signer_certificate_sha256'] == [SIGNER] and identity['signature_verified'] is True and
         identity['executed'] is False and identity['verification_SDK_range'] == [37, 37] and
         identity['tool_exits'] == {'signature': 0, 'badging': 0, 'manifest': 0} and
         identity['native_abis'] == ['arm64-v8a'] and identity['split_name'] is None and
         identity['config_for_split'] is None and identity['uses_splits'] == [] and
         identity['manifest_split_fields'] == [], 'actual complete SDK37 standalone signed identity required')
    need(receipt['candidate'] == native['candidate'] == original_ref('candidate.json') and
         receipt['source_observation'] == candidate['source'] and
         candidate['source']['apk_url'] == candidate['source']['version_metadata_url'] == URL and
         candidate['source']['version_metadata_kind'] == 'signed_apk_android_manifest' and
         candidate['source']['signer_reference_kind'] == 'public_historical_candidate',
         'actual receipt/candidate source join differs')
    expected_input = {'apks': [expected_apk], 'source_receipt': original_ref('source-receipt.json'),
                      'version_code': CODE}
    need(native['application'] == {'package': PACKAGE, 'expected_input': expected_input} and
         native['source_distribution'] == 'public_mirror', 'normal native-input receipt or distribution differs')
    observed_native = data['NATIVE-PAYLOADS.json']
    nmap = {row['path']: row for row in observed_native}
    libs = receipt['binary_metadata']['native_libraries']
    need(len(nmap) == len(observed_native) == len(libs) == 68 and
         len({row['path'] for row in libs}) == 68 and {row['path'] for row in libs} == set(nmap),
         'every actual native member must be unique and covered')
    for row in libs:
        original = nmap[row['path']]
        need((row['elf_class'], row['elf_machine']) == (original['elf_class'], original['elf_machine']),
             'native observation and SDK source receipt differ')
        if row['path'] == CROSS['path']:
            need(original['bytes'] == CROSS['bytes'] and original['sha256'] == CROSS['sha256'] and
                 original['counted_as_arm64_native_library'] is False and
                 row['elf_class'] == 2 and row['elf_machine'] == 62, 'cross-ISA source is not ARM64 runtime credit')
        else:
            need(row['elf_class'] == 2 and row['elf_machine'] == 183 and
                 original['counted_as_arm64_native_library'] is True, 'actual ARM64 ELF identity differs')
    special = receipt['binary_metadata']['cross_arch_shared_libraries']
    need(len(special) == 1 and {key: special[0][key] for key in CROSS} == CROSS and
         all(receipt['binary_metadata'][name] == [] for name in
             ('embedded_archives', 'empty_placeholders', 'interpreter_tagged_et_dyn')),
         'unchanged exact cross-architecture source model required')
    need(source['package'] == PACKAGE and source['version'] == VERSION and source['version_code'] == CODE and
         source['distribution'] == 'public_mirror' and source['actual_SDK37_source_gate_passed'] is True and
         source['whole_ZIP_EOF_CRC_passed'] is True and source['all_original_input_bookends_equal'] is True,
         'current complete qualified public-mirror source required')
    for name, key in (('candidate.json', 'candidate'), ('source-receipt.json', 'source_receipt'),
                      ('native-input.json', 'native_input')):
        need(p3(source[key]) == p3(result[key]) == original_ref(name), 'source qualification pin differs: ' + key)
    need(p3(result['SOURCE']) == original_ref('SOURCE.json') and
         p3(source['pages']) == original_ref('PAGES.json') and
         p3(result['native_payload_observations']) == original_ref('NATIVE-PAYLOADS.json'),
         'complete source observation pins differ')
    need(source['APK'] == result['APK'] and p3(source['APK']) ==
         {'path': str(APK), 'bytes': APK_BYTES, 'sha256': APK_SHA} and
         len(source['APK']['f9']) == 9 and source['APK']['f9'][6] == APK_BYTES,
         'final full APK custody differs')
    need(result['state'] == 'PASSED' and result['source_gate_passed'] is True and
         result['all_original_input_bookends_equal'] is True and result['errors'] == [] and
         result['temporary_remaining_members'] == [] and
         all(result[key] == 0 for key in ('APK_downloads', 'Android_starts', 'network_requests')),
         'actual successful non-executing qualification result required')
    need(result['ZIP'] == {'all_members_EOF_CRC_verified': True, 'arm64_ELF_count': 67,
        'cross_arch_source_count': 1, 'decoded_bytes': 479561413, 'member_count': 26227, 'native_count': 68},
        'whole ZIP closure or ARM64 count differs')
    closure = source['download_closure']
    need(closure == result['delivery_closure'] and closure['complete_contiguous_range_count'] == 50 and
         closure['reused_range_count'] == 8 and closure['actual_sequential_request_count'] == 42 and
         closure['all_piece_hashes_checked_from_final_APK'] is True and
         closure['prior_failure_or_retry_history_rewritten'] is False,
         'historical actual complete transport comparison required')
    cleanup = data['transport-cleanup.json']
    need(cleanup['schema'] == 'p4-owned-beike-transport-cleanup-result-v1' and
         cleanup['state'] == 'PASSED' and cleanup['errors'] == [] and
         cleanup['full_APK_and_source_proofs_unchanged'] is True and cleanup['user_data_touched'] is False and
         cleanup['all_selected_temporary_paths_absent'] is True and len(cleanup['deleted_files']) == 51 and
         len({row['path'] for row in cleanup['deleted_files']}) == 51 and
         len(cleanup['deleted_directories']) == 2 and
         cleanup['started_ns'] >= int(utc(result['finished_utc']).timestamp() * 10**9) and
         cleanup['started_ns'] <= cleanup['finished_ns'] <= int(at.timestamp() * 10**9),
         'successful post-qualification temporary cleanup must preserve final APK and all source proofs')
    need(all(Path(row['path']).is_relative_to(ROOT) and row['path'] != str(APK)
             for row in cleanup['deleted_files']), 'cleanup cannot target the live final APK')
    observed = {row['name']: row for row in pages['requests']}
    need(len(observed) == len(pages['requests']), 'duplicate page observation')
    page_urls = {'xiaomi': 'https://m.app.mi.com/details?id=' + PACKAGE,
                 'tencent': 'https://a.app.qq.com/o/simple.jsp?pkgname=' + PACKAGE}
    for name, url in page_urls.items():
        page = observed[name]
        need(page['status'] == 200 and page['url'] == url and VERSION in page['version_strings'] and
             timedelta(0) <= at - utc(page['observed_utc']) <= timedelta(hours=24),
             'fresh current Android listing observation required')
    need(any(URL.replace('https://', 'http://') in value for value in observed['tencent']['version_contexts']),
         'selected literal ARM64 route must be bound to the Tencent page')
    need(utc(candidate['source']['observed_utc']) <= utc(receipt['verified_utc']) <=
         utc(result['finished_utc']) <= at, 'actual source/signature observation order differs')
    return apps, rows, required


def generate(data, out, now):
    apps, rows, required = validate(data, now)
    registry, freshness, state = (copy.deepcopy(data[name]) for name in
        ('base-registry.json', 'base-freshness.json', 'base-state.json'))
    native, source, receipt = (data[name] for name in ('native-input.json', 'SOURCE.json', 'source-receipt.json'))
    proof_refs = {name: original_ref(name) for name in
        ('candidate.json', 'source-receipt.json', 'native-input.json', 'SOURCE.json', 'RESULT.json', 'PAGES.json',
         'transport-cleanup.json')}
    new_app = {'package': PACKAGE, 'label': apps[PACKAGE]['label'], 'version_name': VERSION,
        'version_code': CODE, 'required39_member': True, 'retained_dependency_outside_required39': False,
        'source_identity_verified': True, 'signature_verified': True, 'selected_abi': 'arm64-v8a',
        'selected_abi_native_members': 67, 'cross_architecture_source_members': 1,
        'expected_input': copy.deepcopy(native['application']['expected_input']),
        'input': p3(source['APK']), 'proofs': proof_refs, 'source_distribution': 'public_mirror',
        'source_observed_utc': data['candidate.json']['source']['observed_utc'],
        'source_verified_utc': receipt['verified_utc'],
        'source_receipt_origin': 'Actual unchanged SDK37/V3 verification of signed current Tencent ARM64 payload; public historical signer reference retained',
        'replaces_historical_registry_record': {'registry': original_ref('base-registry.json'),
            'package': PACKAGE, 'version_name': '3.06.71', 'version_code': 3067100},
        'storage': {'kind': 'pinned_original_host_files', 'host': 'pocket4',
            'verified_input_kind': 'original_public_mirror_standalone_apk',
            'local_container_is_publisher_archive': False,
            'fresh_destination_custody_required_before_installation': True,
            'keep_until_root_archive_and_actual_installation_custody': True,
            'historical_HTTP_range_bodies_required_for_installation': False},
        'device_profile_match_qualified': False, **{key: False for key in NO_CREDIT}}
    registry['applications'] = [new_app if row['package'] == PACKAGE else row for row in registry['applications']]
    registry['source_overrides'] = [{'package': PACKAGE, 'previous_registry': original_ref('base-registry.json'),
        'qualified_source': original_ref('SOURCE.json'), 'qualification_result': original_ref('RESULT.json'),
        'previous_registry_and_archive_bytes_unchanged': True, 'other_28_required_records_unchanged': True,
        'companion_record_unchanged': True, **{key: False for key in NO_CREDIT}}]
    registry['source_evidence_batches'].append({'kind': 'Beike_current_signed_public_mirror_successor',
        'packages': [PACKAGE], 'source': original_ref('SOURCE.json'), 'result': original_ref('RESULT.json'),
        'contains_apk_bytes': False, **{key: False for key in NO_CREDIT}})
    beike = copy.deepcopy(rows[PACKAGE])
    beike.update({'previous_selected_input_version': '3.06.71', 'selected_input_version': VERSION,
        'selected_input_version_code': CODE, 'current_acquired_version': VERSION,
        'source_input_selected': True, 'source_input_closed_by': original_ref('source-receipt.json'),
        'input_blocker': None, 'latest_release_recheck_required_before_activation': True,
        'difference': 'The signed 3.06.80/code3068010 ARM64 public-mirror payload matches both current Android listing observations. The older publisher-direct 3.06.71 record and its age remain historical evidence. No native, installation or business acceptance is granted.',
        **{key: False for key in NO_CREDIT}})
    beike['complete_inputs'].append({'role': 'selected_current_source_input', 'host': 'pocket4',
        **p3(source['APK']), 'version': VERSION, 'version_code': CODE, 'source_kind': 'public_mirror',
        'source_receipt': original_ref('source-receipt.json'), 'source_observation': original_ref('SOURCE.json'),
        'signature_verified_by_SDK37': True, 'all_outer_zip_members_crc_verified': True,
        'abi_directories': ['arm64-v8a'], 'cross_architecture_source_is_not_native_compatibility': True,
        **{key: False for key in NO_CREDIT}})
    for page in data['PAGES.json']['requests']:
        if page['name'] in ('xiaomi', 'tencent'):
            beike['version_observations'].append({'version': VERSION, 'platform': 'Android',
                'url': page['url'], 'observed_utc': page['observed_utc'],
                'source_kind': 'public_' + page['name'] + '_Android_listing',
                'page_observation': original_ref('PAGES.json'),
                'versionCode_is_from_signed_APK_not_listing': True})
    freshness['rows'] = [beike if row['package'] == PACKAGE else row for row in freshness['rows']]
    freshness['reconciled_utc'] = now.isoformat()
    freshness['current_refresh_scope'] = [PACKAGE]
    freshness['previous_freshness'] = original_ref('base-freshness.json')
    registry_raw, freshness_raw = encoded(registry), encoded(freshness)
    registry_ref = ref(out / 'current-source-inputs.json', registry_raw)
    freshness_ref = ref(out / 'current-source-freshness.json', freshness_raw)
    state.update({'schema': 'pocket4-required39-source-state-successor-v2', 'created_utc': now.isoformat(),
        'previous_source_state': original_ref('base-state.json'), 'current29_registry': registry_ref,
        'current29_freshness': freshness_ref, 'source_override_packages': [PACKAGE],
        'existing_23_registry_records_unchanged': False,
        'previous23_history': {'original_merge_preserved_all23': True, 'unchanged_records_in_this_successor': 22,
            'explicit_successor_packages': [PACKAGE], 'historical_registry_bytes_unchanged': True},
        'other38_application_state_records_unchanged': True, 'historical_range_bodies_required_for_installation': False,
        'original_system10_reverified_in_this_successor': False, 'new_SDK_commands': 0,
        'APK_or_image_bodies_read': 0, 'Android_actions': 0, 'new_downloads': 0,
        'historical_qualification_result': original_ref('RESULT.json'),
        'historical_transport_comparison_is_not_live_range_retention_requirement': True})
    state['historical_original_system10_receipts_rechecked'] = state.pop('original_system10_receipts_rechecked')
    state['source_inputs']['registry'], state['source_inputs']['freshness'] = registry_ref, freshness_ref
    state['source_inputs']['Beike_current_source'] = original_ref('SOURCE.json')
    state['applications'] = [({'package': PACKAGE, 'kind': 'third_party', 'source_identity_verified': True,
        'latest_qualified_at_merge_time': True, 'latest_release_recheck_required_before_activation': True,
        'current_registry_record': new_app, 'historical_state_record': required[PACKAGE],
        **{key: False for key in NO_CREDIT}} if row['package'] == PACKAGE else row) for row in state['applications']]
    state['required_before_installation']['Beike_current_publisher_refresh_and_qualification'] = {
        'status': 'SOURCE_QUALIFIED_AT_PINNED_ANDROID_OBSERVATIONS', 'distribution': 'public_mirror',
        'source': original_ref('SOURCE.json'), 'source_receipt': original_ref('source-receipt.json'),
        'latest_release_recheck_required_before_activation': True}
    state['live_Beike_dependencies'] = {'final_APK': p3(source['APK']), 'qualified_metadata': proof_refs,
        'temporary_download_prefix_or_ranges': [], 'original_destination_custody_must_be_rechecked': True}
    validate_output(data, registry, freshness, state)
    return {'current-source-inputs.json': registry_raw, 'current-source-freshness.json': freshness_raw,
            'CURRENT-SOURCE-STATE.json': encoded(state)}


def validate_output(data, registry, freshness, state):
    old_apps = indexed(data['base-registry.json']['applications'], 30)
    new_apps = indexed(registry['applications'], 30)
    old_rows = indexed(data['base-freshness.json']['rows'], 29)
    new_rows = indexed(freshness['rows'], 29)
    old_states = indexed(data['base-state.json']['applications'], 39)
    new_states = indexed(state['applications'], 39)
    need(set(old_apps) == set(new_apps) and set(old_rows) == set(new_rows) and
         set(old_states) == set(new_states), 'successor scope changed')
    for package in old_apps.keys() - {PACKAGE}:
        need(old_apps[package] == new_apps[package], 'unrelated app registry changed')
    for package in old_rows.keys() - {PACKAGE}:
        need(old_rows[package] == new_rows[package], 'unrelated app freshness changed')
    for package in old_states.keys() - {PACKAGE}:
        need(old_states[package] == new_states[package], 'unrelated required app state changed')
    need(registry['scope'] == data['base-registry.json']['scope'] and
         registry['archives'] == data['base-registry.json']['archives'] and
         state['full_GSI_dependency'] == data['base-state.json']['full_GSI_dependency'] and
         state['exemptions'] == data['base-state.json']['exemptions'] and
         state['all_39_latest_qualified'] is False and state['all_39_runtime_accepted'] is False and
         new_apps[MEITUAN]['signer_migration_qualified'] is False, 'original boundary changed')
    old_gates = data['base-state.json']['required_before_installation']
    for key in old_gates.keys() - {'Beike_current_publisher_refresh_and_qualification'}:
        need(state['required_before_installation'][key] == old_gates[key], 'unrelated installation gate changed')
    for value in (registry, freshness, state):
        no_credit(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=Path(__file__).resolve().parent / 'inputs')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true', help='historical metadata replay, no current/latest credit')
    mode.add_argument('--out', type=Path, help='new create-only current source-state directory on pocket4')
    args = parser.parse_args()
    held = {}
    data, refs = read_inputs(args.inputs.resolve(strict=True), held)
    if args.check_only:
        at = datetime.fromtimestamp(data['transport-cleanup.json']['finished_ns'] / 10**9, timezone.utc) + timedelta(microseconds=1)
        validate(data, at)
        generate(data, Path('/not-published-historical-replay'), at)
        need(read_inputs(args.inputs.resolve(strict=True), held)[0] == data, 'input bookends differ')
        print(json.dumps({'state': 'PASSED', 'historical_metadata_replay_only': True,
            'current_latest_credit': False, 'SDK_commands': 0, 'Android_actions': 0,
            'all_runtime_credit': False, 'fixed_inputs': refs}, sort_keys=True))
        return 0
    out = args.out
    need(out.is_absolute() and out.parent.resolve(strict=True) == ROOT and
         out.name == 'source-state-successor-r1' and not out.exists(), 'new isolated pocket4 successor required')
    need(APK.resolve(strict=True) == APK, 'canonical final APK required')
    fd = os.open(APK, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             f9(before) == data['SOURCE.json']['APK']['f9'] == f9(APK.lstat()),
             'final APK custody differs from actual qualified source')
        original_held = {}
        original_refs = check_original_metadata(data, original_held)
        now = datetime.now(timezone.utc)
        output = generate(data, out, now)
        os.umask(0o077)
        out.mkdir(mode=0o700)
        outputs = {}
        for name, raw in output.items():
            path = out / name
            with path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            outputs[name] = ref(path, raw)
        need(read_inputs(args.inputs.resolve(strict=True), held)[0] == data and
             check_original_metadata(data, original_held) == original_refs and
             f9(before) == f9(os.fstat(fd)) == f9(APK.lstat()), 'final actual input bookends differ')
        result = {'schema': 'p4-Beike-source-state-successor-result-v1', 'state': 'PASSED',
            'created_utc': now.isoformat(), 'input_metadata': refs, 'outputs': outputs,
            'source_override_packages': [PACKAGE], 'other_28_and_companion_unchanged': True,
            'other38_state_records_unchanged': True, 'historical_bytes_unchanged': True,
            'snapshot_metadata_and_final_APK_F9_bookends_equal': True,
            'pocket4_qualified_metadata_F9_SHA_bookends_equal': True,
            'original_live_JSON_proofs': original_refs, 'historical_ai395_base_documents_reopened': False,
            'APK_or_image_bodies_read': 0, 'SDK_commands': 0, 'Android_actions': 0,
            'range_bodies_checked_or_required': False, 'latest_release_recheck_required_before_activation': True,
            **{key: False for key in NO_CREDIT}}
        raw = encoded(result)
        with (out / 'RESULT.json').open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'state': 'PASSED', 'result': ref(out / 'RESULT.json', raw), 'outputs': outputs}, sort_keys=True))
    finally:
        os.close(fd)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
