"""Reverify retained official Play code-path sets against current release metadata.

This separate path does not change or replay the current-delivery verifier. A
country-unavailable response remains unavailable; no new delivery is claimed.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_apk as single
import verify_apk_set as sets
import verify_publisher_delivery as delivery

SCHEMA = 'pocket4-retained-google-play-apk-set-candidate-v1'
RECEIPT_SCHEMA = 'pocket4-verified-retained-google-play-source-receipt-v1'
COLLECTION_SOURCE = 'official Google Play acquisition in user-authenticated owned AVD'
IDENTITY_SOURCE = 'user-authenticated official Google Play code paths; complete original cohort preserved'
SOURCE_KIND = 'retained_official_google_play_owned_avd_code_paths'
EVIDENCE_KEYS = ('historical_collection', 'historical_identity',
                 'current_metadata', 'current_transaction')
NO_CREDIT = delivery.NO_CREDIT
need = sets._need

# Exact tools extracted from Google's build-tools_r37_linux.zip. The published
# archive SHA-1 is 70954e99f4c3d9d46ee70fa32624672fe7cd6ebe. No SDK is installed.
SDK37 = {
    'aapt2': (6274200, '0f1c0e560f99db510a76ebc99ad5c3e68438f62e8e8617018a716ca4a589a699'),
    'lib/apksigner.jar': (1181416, '2defad215d7ff52968a409cde528cdaef7918b115e276b8e3378ca7a178e4180'),
    'lib64/libc++.so': (1545448, '9d4c9036e8eca07cb7cf161128c362e8e5550ede7cd7f99078d559c14a5fdf9a'),
    'source.properties': (38, 'fbd87c8567afbc6dc78e140097fcde234f4a61fa7065e85081d43e442ccd3d24'),
}


def validate_candidate(candidate):
    single._fields(candidate, ('schema', 'package', 'version_name', 'version_code',
        'version_code_major', 'min_sdk_version', 'target_sdk_version',
        'signer_certificate_sha256', 'selected_abi', 'apks', 'source'), 'Retained candidate')
    need(candidate['schema'] == SCHEMA, 'Unsupported retained-source schema')
    need(type(candidate['package']) is str and re.fullmatch(
        r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', candidate['package']),
        'Invalid package')
    version = candidate['version_name']
    need(type(version) is str and 0 < len(version.encode()) <= 256
         and all(32 <= ord(c) != 127 for c in version), 'Invalid version name')
    for key, low, high in (('version_code', 1, 0xffffffff),
                          ('version_code_major', 0, 0x7fffffff),
                          ('min_sdk_version', 1, 37), ('target_sdk_version', 1, 1000)):
        need(type(candidate[key]) is int and low <= candidate[key] <= high, 'Invalid ' + key)
    certs = candidate['signer_certificate_sha256']
    need(type(certs) is list and 1 <= len(certs) <= 8 and all(single._sha(c) for c in certs)
         and certs == sorted(set(certs)), 'Invalid signer set')
    need(candidate['selected_abi'] == 'x86_64', 'Retained gate requires native x86_64 input')
    apks = candidate['apks']
    need(type(apks) is list and 2 <= len(apks) <= 64, 'Incomplete retained APK set')
    splits, paths, total, native = [], [], 0, 0
    for pin in apks:
        single._fields(pin, ('member', 'split_name', 'bytes', 'sha256', 'native_abis',
                            'retained_path'), 'Retained member')
        split = pin['split_name']
        need(split is None or sets._name(split), 'Invalid split name')
        need(pin['member'] == sets.normalized_name(split), 'Noncanonical APK name')
        need(type(pin['bytes']) is int and 0 < pin['bytes'] <= sets.APK_LIMIT
             and single._sha(pin['sha256']), 'Invalid APK digest/size')
        need(delivery.absolute_file(pin['retained_path']), 'Invalid retained APK path')
        need(type(pin['native_abis']) is list and pin['native_abis'] in ([], ['x86_64']),
             'Retained member contains an undeclared execution ABI')
        native += pin['native_abis'] == ['x86_64']
        splits.append(split)
        paths.append(pin['retained_path'])
        total += pin['bytes']
    need(total <= delivery.BUNDLE_LIMIT and native > 0 and splits.count(None) == 1
         and len(set(splits)) == len(splits) and len(set(paths)) == len(paths)
         and splits == sorted(splits, key=lambda s: '' if s is None else s),
         'Retained set is oversized, duplicated, unordered, or missing base/native input')
    source = candidate['source']
    single._fields(source, ('distribution', 'current_delivery_obtained', 'observed_utc')
                   + EVIDENCE_KEYS, 'Retained source')
    need(source['distribution'] == SOURCE_KIND and source['current_delivery_obtained'] is False,
         'Retained input cannot claim a new publisher delivery')
    delivery.utc(source['observed_utc'])
    for key in EVIDENCE_KEYS:
        delivery.pin_fields(source[key], key, delivery.EVIDENCE_LIMIT)
        paths.append(source[key]['path'])
    need(len(set(paths)) == len(paths), 'Retained APK/source evidence paths alias')
    return candidate


def validate_current(candidate, metadata, transaction, now=None):
    single._fields(metadata, ('package', 'version_name', 'version_code', 'source',
        'restriction', 'restriction_code', 'is_free', 'offer_type',
        'certificate_sets', 'certificate_sha1_base64url'), 'Current GET_ITEMS')
    long_code = (candidate['version_code_major'] << 32) | candidate['version_code']
    need(metadata['package'] == candidate['package']
         and metadata['version_name'] == candidate['version_name']
         and type(metadata['version_code']) is int and metadata['version_code'] == long_code,
         'Current publisher package/version differs from retained input')
    need(metadata['source'] == 'GET_ITEMS' and metadata['restriction'] == 'UNAVAILABLE_COUNTRY'
         and type(metadata['restriction_code']) is int and metadata['restriction_code'] == 4
         and metadata['is_free'] is True
         and type(metadata['offer_type']) is int and metadata['offer_type'] == 1,
         'Current unavailable-country metadata must be preserved unchanged')
    values = metadata['certificate_sets']
    need(type(values) is list and 1 <= len(values) <= 8, 'Missing current publisher signer')
    certs = []
    for value in values:
        single._fields(value, ('sha1_base64url', 'sha256_base64url'), 'Current signer')
        delivery.certificate_digest(value['sha1_base64url'], 20)
        certs.append(delivery.certificate_digest(value['sha256_base64url'], 32))
    need(len(set(certs)) == len(certs) and sorted(certs) == candidate['signer_certificate_sha256'],
         'Current publisher signer differs from retained input')
    legacy = metadata['certificate_sha1_base64url']
    need(type(legacy) is list and len(legacy) <= 8, 'Invalid auxiliary publisher certificate')
    for value in legacy:
        delivery.certificate_digest(value, 20)
    single._fields(transaction, ('schema', 'finished_utc', 'results', 'transport',
        'auth_requests', 'purchase_requests', 'android_starts', 'installed_apps',
        'production_ready'), 'Current transaction')
    need(transaction['schema'] == 'pocket4-aurora-official-client-result-v1'
         and transaction['finished_utc'] == candidate['source']['observed_utc']
         and transaction['production_ready'] is False
         and all(type(transaction[k]) is int and transaction[k] == 0
                 for k in ('auth_requests', 'purchase_requests', 'android_starts', 'installed_apps')),
         'Current transaction identity/claims differ')
    results = transaction['results']
    need(type(results) is list and 1 <= len(results) <= 64
         and all(type(x) is dict and type(x.get('package')) is str for x in results),
         'Invalid current transaction inventory')
    packages = [x['package'] for x in results]
    need(len(set(packages)) == len(packages), 'Duplicate current transaction package')
    expected = {'package': candidate['package'], 'status': 'unavailable',
                'reason': 'not_available_free_download'}
    need([x for x in results if x['package'] == candidate['package']] == [expected],
         'Current failed acquisition record was altered or does not match')
    need(type(transaction['transport']) is dict, 'Missing original transport observation')
    observed = delivery.utc(transaction['finished_utc'])
    now = datetime.now(timezone.utc) if now is None else now
    need(now.tzinfo is not None and timedelta(0) <= now - observed <= timedelta(hours=24),
         'Current publisher metadata is future-dated or older than 24 hours')
    return {'current_metadata_release_identity_matches': True,
            'current_metadata_restriction': 'UNAVAILABLE_COUNTRY',
            'current_metadata_restriction_code': 4,
            'current_transaction_package_result': expected,
            'current_delivery_obtained': False,
            'latest_release_identity_observed_utc': transaction['finished_utc'],
            'metadata_revalidation_due_utc': (observed + timedelta(hours=24)).isoformat(),
            'current_metadata_signer_sha256': sorted(certs)}


def validate_history(candidate, collection, history):
    single._fields(collection, ('package', 'source', 'installer', 'all_APK_code_paths_stable',
        'files', 'private_app_data_read', 'runtime_qualified_on_final_Android',
        'production_ready'), 'Historical official collection')
    need(collection['package'] == candidate['package'] and collection['source'] == COLLECTION_SOURCE
         and collection['installer'] == 'com.android.vending'
         and collection['all_APK_code_paths_stable'] is True
         and all(collection[k] is False for k in ('private_app_data_read',
                 'runtime_qualified_on_final_Android', 'production_ready')),
         'Historical acquisition is not the preserved official code-path collection')
    files = collection['files']
    need(type(files) is list and len(files) == len(candidate['apks']),
         'Historical complete collection member count differs')
    by_path, parents = {}, set()
    for item in files:
        single._fields(item, ('Android_APK_code_path', 'path', 'bytes', 'sha256', 'F9',
            'Android_SHA_before_and_after_equals_collected_whole_SHA'), 'Historical collected member')
        need(delivery.absolute_file(item['path']) and item['path'] not in by_path
             and type(item['bytes']) is int and 0 < item['bytes'] <= sets.APK_LIMIT
             and single._sha(item['sha256'])
             and item['Android_SHA_before_and_after_equals_collected_whole_SHA'] is True,
             'Historical collection was incomplete or its hashes were not stable')
        f9 = item['F9']
        need(type(f9) is list and len(f9) == 9 and all(type(x) is int for x in f9)
             and f9[5] == 1 and f9[6] == item['bytes'], 'Invalid historical file identity')
        android_path = item['Android_APK_code_path']
        need(type(android_path) is str and len(android_path) <= 4096
             and re.fullmatch(r'/data/app/~~[A-Za-z0-9_=-]+/'
                 + re.escape(candidate['package']) + r'-[A-Za-z0-9_=-]+/[^/]+\.apk', android_path),
             'Historical APK code path does not identify this package cohort')
        parents.add(str(Path(android_path).parent))
        by_path[item['path']] = item
    need(len(parents) == 1 and set(by_path) == {p['retained_path'] for p in candidate['apks']},
         'Historical collection mixes cohorts or omits/adds APKs')
    for pin in candidate['apks']:
        item = by_path[pin['retained_path']]
        need(item['bytes'] == pin['bytes'] and item['sha256'] == pin['sha256']
             and Path(item['Android_APK_code_path']).name == pin['member'],
             'Retained member differs from the exact official collection')
    need(type(history) is dict and type(history.get('all_static_identity_signatures_qualified')) is bool
         and history.get('runtime_qualified') is False and history.get('production_ready') is False,
         'Historical batch receipt has incompatible claims')
    apps = history.get('apps')
    need(type(apps) is list and 1 <= len(apps) <= 64
         and all(type(a) is dict and type(a.get('package')) is str for a in apps),
         'Invalid historical identity inventory')
    matches = [a for a in apps if a['package'] == candidate['package']]
    need(len(matches) == 1, 'Missing or duplicate historical application')
    app = matches[0]
    need(app.get('source') == IDENTITY_SOURCE and app.get('errors') == []
         and app.get('static_identity_signature_qualified') is True
         and app.get('all_split_package_version_signers_consistent') is True
         and app.get('historical_official_signers') == candidate['signer_certificate_sha256']
         and app.get('observed_split_names') == [p['split_name'] for p in candidate['apks']]
         and all(app.get(k) is False for k in ('runtime_qualified', 'production_ready', 'private_app_data_read')),
         'Historical identity/signers/split closure differ')
    base = app.get('base_identity')
    need(type(base) is dict and base.get('package') == candidate['package']
         and base.get('versionName') == candidate['version_name']
         and type(base.get('versionCode')) is int and base['versionCode'] == candidate['version_code']
         and type(base.get('longVersionCode')) is int and base['longVersionCode'] ==
             ((candidate['version_code_major'] << 32) | candidate['version_code'])
         and base.get('minSdk') == candidate['min_sdk_version']
         and base.get('targetSdk') == candidate['target_sdk_version'],
         'Historical signed base identity differs')
    members = app.get('APK_results')
    need(type(members) is list and len(members) == len(candidate['apks']),
         'Historical identity member count differs')
    by_path = {}
    for item in members:
        file = item.get('file') if type(item) is dict else None
        need(type(file) is dict and type(file.get('path')) is str and file['path'] not in by_path,
             'Historical identity paths are absent/duplicate')
        by_path[file['path']] = item
    need(set(by_path) == {p['retained_path'] for p in candidate['apks']},
         'Historical identity inventory differs from collection')
    for pin in candidate['apks']:
        item = by_path[pin['retained_path']]
        need(item['file'].get('bytes') == pin['bytes'] and item['file'].get('sha256') == pin['sha256']
             and item.get('actual_split_name') == pin['split_name']
             and item.get('sameFD_final_SHA_F9_verified') is True,
             'Historical identity APK pin differs')
        sig = item.get('signature')
        need(type(sig) is dict and sig.get('signature_verified_by_actual_tool') is True
             and sig.get('tool_exit_code') == 0 and sig.get('output_contract_complete') is True
             and sig.get('effective_signer_cert_SHA256') == candidate['signer_certificate_sha256'],
             'Historical APK signer is not verified')
    return {'historical_acquisition': SOURCE_KIND, 'historical_official_collection_complete': True,
            'historical_static_identity_matches': True, 'historical_member_count': len(files),
            'historical_batch_all_static_qualified': history['all_static_identity_signatures_qualified'],
            'qualification_scope': 'selected_package_only',
            'selected_package': candidate['package'],
            'publisher_download_digest_claimed': False, 'new_delivery_claimed': False}


def verify_retained(tools, candidate_path, expected_sha256, receipt_path):
    tools, candidate_path, receipt_path = map(Path, (tools, candidate_path, receipt_path))
    need(single._sha(expected_sha256), 'Invalid external candidate SHA-256')
    need(receipt_path.is_absolute() and not os.path.lexists(receipt_path),
         'Receipt output must be a new absolute file')
    identities, binaries, integrity, originals = [], [], [], []
    with ExitStack() as held:
        stream, candidate_pin = held.enter_context(sets._held(candidate_path, sets.CANDIDATE_LIMIT))
        need(candidate_pin['sha256'] == expected_sha256, 'External candidate SHA-256 differs')
        candidate = validate_candidate(sets._json(stream.read()))
        evidence, evidence_pins = {}, {}
        for key in EVIDENCE_KEYS:
            pin = candidate['source'][key]
            stream, actual = held.enter_context(sets._held(pin['path'], delivery.EVIDENCE_LIMIT, pin))
            evidence[key], evidence_pins[key] = sets._json(stream.read()), actual
        current = validate_current(candidate, evidence['current_metadata'], evidence['current_transaction'])
        historical = validate_history(candidate, evidence['historical_collection'], evidence['historical_identity'])
        sdk_pins = {}
        for relative, (size, sha) in SDK37.items():
            _, actual = held.enter_context(sets._held(tools / relative, 16 * 1024 * 1024,
                                                      {'bytes': size, 'sha256': sha}))
            sdk_pins[relative] = actual
        streams = []
        for pin in candidate['apks']:
            stream, actual = held.enter_context(sets._held(pin['retained_path'], sets.APK_LIMIT, pin))
            streams.append(stream)
            originals.append(actual)
        with tempfile.TemporaryDirectory(prefix='retained-play-verified-') as temporary:
            directory = Path(temporary)
            for pin, source in zip(candidate['apks'], streams):
                path = directory / pin['member']
                source.seek(0)
                size, h = 0, hashlib.sha256()
                with path.open('xb') as output:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        size += len(block)
                        need(size <= pin['bytes'], 'Retained copy exceeds its external pin')
                        h.update(block)
                        output.write(block)
                need(size == pin['bytes'] and h.hexdigest() == pin['sha256'],
                     'Retained copy differs from its external pin')
                result = single.verify(path, tools, candidate['package'], candidate['signer_certificate_sha256'])
                need(result['bytes'] == pin['bytes'] and result['sha256'] == pin['sha256']
                     and result['verification_SDK_range'] == [37, 37], 'Fresh SDK verification identity differs')
                binary = sets._binary_observation(path, result, candidate, pin)
                complete = delivery.full_zip_integrity(path)
                need({x['path'] for x in complete['native_members']} ==
                     {x['path'] for x in binary['native_libraries']}, 'Native inventory/hash coverage differs')
                need(single.digest(path) == pin['sha256'], 'Verified retained APK changed')
                identities.append(result)
                binaries.append(binary)
                integrity.append(complete)
            closure = sets.validate_closure([b['manifest'] for b in binaries])
            natives = [{'member': p['member'], **n} for p, full in zip(candidate['apks'], integrity)
                       for n in full['native_members'] if n['path'].startswith('lib/x86_64/')]
            need(natives, 'Actual retained native x86_64 payload is absent')
        # Full SHA-256 and inode bookends for every APK, proof, candidate and SDK tool.
    # SDK work can outlive the metadata lease. Recheck at publication, after all
    # original-source bookends, instead of accepting only the start-time check.
    current = validate_current(candidate, evidence['current_metadata'], evidence['current_transaction'])
    receipt = {'schema': RECEIPT_SCHEMA, 'verified_utc': datetime.now(timezone.utc).isoformat(),
        'candidate': candidate_pin, 'source_observation': candidate['source'],
        'original_evidence': evidence_pins, 'current_source_validation': current,
        'historical_source_validation': historical, 'original_retained_apks': originals,
        'sdk37_tools': sdk_pins, 'identities': identities, 'binary_metadata': binaries,
        'complete_zip_integrity': integrity, 'split_closure': closure,
        'selected_abi': 'x86_64', 'selected_abi_native_members': natives,
        'current_delivery_obtained': False, 'authenticated_transport_replayed': False,
        'publisher_archive_obtained': False, 'device_profile_match_qualified': False,
        'native_compatibility_qualified': False, 'business_qualified': False,
        'exclusive_content_directory_removed': True, **NO_CREDIT}
    body = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    sets._publish(receipt_path, body)
    receipt_pin = {'path': str(receipt_path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
    return {'application': {'package': candidate['package'], 'expected_input': {
        'version_code': (candidate['version_code_major'] << 32) | candidate['version_code'],
        'apks': [{'name': p['member'], 'bytes': p['bytes'], 'sha256': p['sha256']}
                 for p in candidate['apks']], 'source_receipt': receipt_pin}},
        'candidate': candidate_pin, 'current_delivery_obtained': False, **NO_CREDIT}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--expect-candidate-sha256', required=True)
    parser.add_argument('--receipt-output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_retained(args.build_tools, args.candidate,
        args.expect_candidate_sha256, args.receipt_output), indent=2))
