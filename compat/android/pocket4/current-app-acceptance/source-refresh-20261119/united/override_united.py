#!/usr/bin/env python3
"""Join the qualified United 3622 metadata into the preserved required39 state.

No APK, SDK, network, Android, owner CURRENT, or installation operation is used.
Original signed-delivery and SDK receipts remain exact historical evidence.
"""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

PACKAGE = 'com.united.mobile.android'
VERSION, CODE = '4.2.104', 3622
OLD_VERSION, OLD_CODE = '4.2.103', 3621
SIGNER = 'e833171fd602255f030ed251c64a9989c7eabc4ebe1c3d7b097ae0f9aea8f946'
CONTAINER_SHA = '933e821cefae299301a1badfff898c213519dc94001424d50e86fe1915e72042'
CONTAINER_BYTES = 351042037
PREFIX = 'compat/android/pocket4/current-app-acceptance/source-refresh-20261119/united/'
EXEMPT = {'com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab'}
COMPANION = 'com.android.vending'
NO_CREDIT = ('installed', 'runtime_qualified', 'native_compatibility_qualified',
             'business_qualified', 'production_ready')
DENIED_CREDIT = set(NO_CREDIT) | {'device_profile_match_qualified',
    'device_configuration_match_qualified', 'abi_compatibility_verified',
    'dispatch_runtime_observed', 'native_execution_qualified',
    'all_39_runtime_accepted', 'signer_migration_qualified'}
MEMBERS = ('base.apk', 'split_config.arm64_v8a.apk',
           'split_config.en.apk', 'split_config.xxhdpi.apk')
SPLITS = (None, 'config.arm64_v8a', 'config.en', 'config.xxhdpi')
PINS = {
    "base-CURRENT-SOURCE-STATE.json": [
        157891,
        "4d25fc0aafd5668cc3f0c31be157bc617732902976aad821333a02de84ff9bf7"
    ],
    "base-current-source-inputs.json": [
        111728,
        "5d14f8af912f57e9c93290fa9aa3c62a686b57d82f3aa964beb5860b452df9ab"
    ],
    "base-current-source-freshness.json": [
        105899,
        "894162a5bb6fc31deadd2dfb4069b7a353fad3014c131f960a9cc14b3bb4258e"
    ],
    "sdk37-supervisor-RESULT.json": [
        64269,
        "87afa9e23691a376c36e42b0c256f4d3a17587d2d46a828388e2d61425ac11d6"
    ],
    "sdk37-worker-RESULT.json": [
        31564,
        "1556fdbcecc814429531a484d770389b94818a01fc1427865c0fc0fc86a3a1d3"
    ],
    "candidate.json": [
        3134,
        "95e52344a2b5e43c5fa2bba97bebf10d4f41a64cb569305062c20367337b804f"
    ],
    "source-receipt.json": [
        31632,
        "1023f326cc86f256fef91e873dcc8613b213d5ada5f692193fe41b747a5fb306"
    ],
    "native-input.json": [
        1654,
        "574ccf8820af5bbb20ced3d2368e3b3d25d96daaf9b73c86068092fed2310d85"
    ],
    "delivery-RESULT.json": [
        24048,
        "c8136d4500379f6df5c3c59edc7b8b5679ba0acc2de8e4f81a193bd240c04047"
    ],
    "TRANSPORT-RESULT.json": [
        8171,
        "3ca7c0cd8adacd778f02a9875309b3a65a905bae6ef772620b38b6a6f0121c51"
    ],
    "current-metadata.json": [
        462,
        "64dd05af437c1c2e04641d1c3bc905df4012bb36b2d83694eeeee51d2b11534d"
    ],
    "current-transport.json": [
        2786,
        "2c0fb0b267f2ae61e9fe812a5e0ac0c738c3bdb0865d217933a46cba5ebacf28"
    ],
    "TRANSPORT-CLEANUP.json": [
        870,
        "d66df416e53238f685e87fdf9ca1f1e3315b405d4b332e8474ad308bcfb9644b"
    ],
    "SDK37-CLEANUP.json": [
        946,
        "55cf097da1e9137937c6f882ed607930fabda5800a209b10cbda218815472b02"
    ],
    "SOURCE-HANDOFF.json": [
        7461,
        "1f7d574cf7f8d1d38b38416b4b84048373bf42b29ae04f88f8d1c601e8242da4"
    ]
}


def need(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def parse(body):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    def invalid(value):
        raise ValueError('non-finite JSON value: ' + value)
    return json.loads(body, object_pairs_hook=pairs, parse_constant=invalid)


def pin(name):
    size, digest = PINS[name]
    return {'path': PREFIX + 'inputs/' + name, 'bytes': size, 'sha256': digest}


def output_pin(name, body):
    return {'path': PREFIX + 'actual/' + name, 'bytes': len(body),
            'sha256': hashlib.sha256(body).hexdigest()}


def check_pin(row, name):
    need((row['bytes'], row['sha256']) == tuple(PINS[name]), 'metadata pin differs: ' + name)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_inputs(root):
    root = Path(root).absolute()
    need(root.resolve() == root, 'input root must not follow a symlink')
    data, before = {}, {}
    need({p.name for p in root.iterdir()} == set(PINS), 'complete exact metadata input set')
    for name, expected in PINS.items():
        path = root / name
        info = path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
             info.st_size <= 2 * 1024 * 1024, 'bounded single-link metadata input')
        before[name] = identity(info)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(identity(os.fstat(fd)) == before[name], 'opened metadata inode differs')
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                size += len(chunk)
                need(size <= expected[0], 'metadata grew')
                chunks.append(chunk)
            body = b''.join(chunks)
            need(identity(os.fstat(fd)) == before[name], 'metadata changed during read')
        finally:
            os.close(fd)
        need((len(body), hashlib.sha256(body).hexdigest()) == tuple(expected),
             'complete input size/SHA differs: ' + name)
        need(identity(path.lstat()) == before[name], 'named metadata changed')
        data[name] = parse(body)
    need(all(identity((root / name).lstat()) == row for name, row in before.items()),
         'complete metadata bookend differs')
    return data


def indexed(rows, count):
    need(type(rows) is list and len(rows) == count, 'complete package count')
    out = {row['package']: row for row in rows}
    need(len(out) == count, 'duplicate or omitted package')
    return out


def no_credit(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DENIED_CREDIT:
                need(child is False, 'source-only boundary changed: ' + key)
            no_credit(child)
    elif isinstance(value, list):
        for child in value:
            no_credit(child)


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(result.tzinfo is not None, 'timestamp requires timezone')
    return result


def validate(data, at):
    apps = indexed(data['base-current-source-inputs.json']['applications'], 30)
    rows = indexed(data['base-current-source-freshness.json']['rows'], 29)
    states = indexed(data['base-CURRENT-SOURCE-STATE.json']['applications'], 39)
    need(set(apps) == set(rows) | {COMPANION} and set(rows) <= set(states) and
         not set(states) & EXEMPT, 'exact original required scope')
    need((apps[PACKAGE]['version_name'], apps[PACKAGE]['version_code']) ==
         (OLD_VERSION, OLD_CODE), 'original United 3621 is the exact predecessor')
    c, r, native, handoff = (data[n] for n in
        ('candidate.json', 'source-receipt.json', 'native-input.json', 'SOURCE-HANDOFF.json'))
    worker, supervisor = data['sdk37-worker-RESULT.json'], data['sdk37-supervisor-RESULT.json']
    meta, transport = data['current-metadata.json'], data['current-transport.json']
    need(c['schema'] == 'pocket4-publisher-delivery-apk-set-candidate-v1' and
         r['schema'] == 'pocket4-verified-publisher-delivery-source-receipt-v1', 'original SDK schemas')
    for item in (c, handoff, meta, transport):
        need((item['package'], item['version_name'], item['version_code']) ==
             (PACKAGE, VERSION, CODE), 'United package/version/code join')
    need(c['min_sdk_version'] == handoff['min_sdk_version'] == 29 and
         c['target_sdk_version'] == handoff['target_sdk_version'] == 36 and
         c['version_code_major'] == 0, 'actual min/target/major SDK identity')
    need(c['selected_abi'] == r['selected_abi'] == 'arm64-v8a', 'actual selected ABI')
    need(c['signer_certificate_sha256'] == handoff['publisher_signer_certificate_sha256'] ==
         transport['official_signer_certificate_sha256'] == [SIGNER], 'actual common signer')
    need(meta['source'] == 'GET_ITEMS' and meta['restriction'] == 'AVAILABLE' and
         meta['restriction_code'] == 1, 'actual current available metadata')
    certs = [base64.urlsafe_b64decode(x['sha256_base64url'] + '==').hex()
             for x in meta['certificate_sets']]
    need(certs == [SIGNER], 'GET_ITEMS certificate SHA256 joins actual APK signer')
    need(c['source']['container_origin'] == handoff['final_input_origin'] ==
         'local_zip_stored_from_publisher_delivery_members_v1' and
         c['source']['distribution'] == 'google_play_publisher_delivery' and
         c['source']['publisher_archive_obtained'] is False and
         r['publisher_archive_obtained'] is False and handoff['publisher_archive_obtained'] is False,
         'local container never becomes a publisher archive')
    need(c['container'] == {'bytes': CONTAINER_BYTES, 'sha256': CONTAINER_SHA},
         'exact new qualified container')
    need(r['local_container'] == handoff['final_input'] and
         (r['local_container']['bytes'], r['local_container']['sha256']) ==
         (CONTAINER_BYTES, CONTAINER_SHA), 'complete qualified container F9 identity')
    need(r['source_observation'] == c['source'], 'receipt source observation')
    for field, name in [('metadata', 'current-metadata.json'), ('delivery', 'current-transport.json'),
                        ('transaction', 'TRANSPORT-RESULT.json')]:
        check_pin(c['source'][field], name)
        observed = r['original_evidence'][field]
        need({key: observed[key] for key in ('path', 'bytes', 'sha256')} == c['source'][field],
             'original source evidence join')
    need(utc(c['source']['observed_utc']) <= utc(r['verified_utc']) <= at and
         at <= utc(c['source']['observed_utc']) + timedelta(days=1),
         'actual source selection timestamp within original metadata interval')
    need([a['member'] for a in c['apks']] == list(MEMBERS) and
         [a['split_name'] for a in c['apks']] == list(SPLITS), 'one base and exact three split members')
    need(len({a['sha256'] for a in c['apks']}) == 4 and
         len({a['delivery_path'] for a in c['apks']}) == 4, 'distinct complete APK members')
    need(len(r['identities']) == len(r['binary_metadata']) ==
         len(r['complete_zip_integrity']) == len(r['original_delivery_apks']) == 4,
         'complete four-APK receipt')
    need(r['all_original_delivery_apks_verified'] is True and
         r['exclusive_content_directory_removed'] is True, 'complete SDK receipt')
    need(handoff['original_parts'] == c['apks'], 'handoff original members')
    for index, (apk, ident, original, binary, zipped, delivery) in enumerate(zip(
            c['apks'], r['identities'], r['original_delivery_apks'],
            r['binary_metadata'], r['complete_zip_integrity'], transport['files'], strict=True)):
        need((ident['filename'], ident['split_name'], ident['package'],
              ident['version_code'], ident['long_version_code'], ident['version_code_major']) ==
             (MEMBERS[index], SPLITS[index], PACKAGE, CODE, CODE, 0), 'SDK split/version identity')
        need(ident['version_name'] == (VERSION if index == 0 else '') and
             ident['native_abis'] == apk['native_abis'], 'SDK base version and ABI')
        need(ident['signature_verified'] is True and ident['signer_certificate_sha256'] == [SIGNER] and
             ident['verification_SDK_range'] == [37, 37] and
             ident['tool_exits'] == {'badging': 0, 'manifest': 0, 'signature': 0} and
             ident['executed'] is False, 'actual unchanged SDK37 identity/signature commands')
        need(ident['selected_verified_signing_scheme']['certificate_sha256'] == [SIGNER] and
             ident['selected_verified_signing_scheme']['scheme'] == 'v3', 'actual selected verified signature')
        need((ident['bytes'], ident['sha256'], ident['metadata_outputs_bound_to_apk_sha256']) ==
             (apk['bytes'], apk['sha256'], apk['sha256']), 'SDK outputs bound to exact APK')
        need((original['path'], original['bytes'], original['sha256'], original['sha1']) ==
             (apk['delivery_path'], apk['bytes'], apk['sha256'], apk['sha1']), 'original part custody')
        need((delivery['path'], delivery['bytes'], delivery['sha256'], delivery['sha1'],
              delivery['delivery_sha256'], delivery['delivery_sha1']) ==
             (apk['delivery_path'], apk['bytes'], apk['sha256'], apk['sha1'], apk['sha256'], apk['sha1']),
             'publisher transport identities')
        need(zipped['all_member_crc_verified'] is True and zipped['file_count'] > 0,
             'complete ZIP EOF/CRC evidence')
        manifest = binary['manifest']
        need((manifest['package'], manifest['version_code'], manifest['split_name']) ==
             (PACKAGE, CODE, SPLITS[index]), 'binary manifest joins SDK identity')
        for library in binary['native_libraries']:
            need(library['elf_class'] == 2 and library['elf_machine'] == 183 and
                 library['path'].startswith('lib/arm64-v8a/'), 'actual ARM64 ELF metadata')
    libs = [lib for b in r['binary_metadata'] for lib in b['native_libraries']]
    members = r['selected_abi_native_members']
    need(len(libs) == len(members) == 11 and len({x['path'] for x in members}) == 11 and
         all(x['member'] == MEMBERS[1] and len(x['sha256']) == 64 for x in members) and
         {(x['path'], x['bytes']) for x in members} == {(x['path'], x['bytes']) for x in libs},
         'eleven complete ARM64 native member identities')
    closure = r['split_closure']
    need(closure == handoff['source_qualification']['split_closure'] and
         closure['base_count'] == 1 and closure['split_count'] == 3 and
         closure['manifest_dependency_closure_verified'] is True and
         closure['offered_split_types'] == closure['required_split_types'] == ['base__abi', 'base__density'] and
         closure['dependencies'] == [{'split': s, 'target': None} for s in SPLITS[1:]],
         'full declared split closure')
    expected_apks = [{'name': a['member'], 'bytes': a['bytes'], 'sha256': a['sha256']} for a in c['apks']]
    expected = native['application']['expected_input']
    need(native['application']['package'] == PACKAGE and expected['version_code'] == CODE and
         expected['apks'] == expected_apks and native['application'] == handoff['final_source_mapping'],
         'complete native input mapping')
    check_pin(expected['source_receipt'], 'source-receipt.json')
    check_pin(native['candidate'], 'candidate.json')
    check_pin(r['candidate'], 'candidate.json')
    need(worker['united_source_verified'] is True and worker['source_bookends_equal'] is True and
         worker['sdk_tool_bookends_equal'] is True and worker['original_20_gate_files_unchanged'] is True and
         worker['source_before'] == worker['source_after'] and
         worker['sdk_tools_before'] == worker['sdk_tools_after'], 'actual SDK worker custody')
    one = indexed(worker['packages'], 1)[PACKAGE]
    need(one['status'] == 'publisher_delivery_source_verified' and
         (one['version_name'], one['version_code'], one['apk_count'],
          one['native_file_count'], one['selected_arm64_library_count']) == (VERSION, CODE, 4, 11, 11) and
         one['input'] == handoff['final_input'], 'actual SDK worker package result')
    for field, name in [('candidate','candidate.json'), ('receipt','source-receipt.json'),
                        ('result','native-input.json')]:
        check_pin(one[field], name)
    command = supervisor['command']
    need(supervisor['source_qualified'] is True and supervisor['source_input_bookends_equal'] is True and
         supervisor['inputs_before'] == supervisor['inputs_after'] and
         command['exit_code'] == 0 and command['after_reap_echild'] is True and
         command['output_complete'] is True and command['termination'] is None and
         supervisor['network_syscalls_denied'] is True and
         command['network_syscalls_denied'] is True and supervisor['remaining_children'] == '',
         'actual bounded SDK supervisor and reap')
    q = handoff['source_qualification']
    for field, name in [('supervisor_receipt','sdk37-supervisor-RESULT.json'),
                        ('worker_receipt','sdk37-worker-RESULT.json'), ('candidate','candidate.json'),
                        ('source_receipt','source-receipt.json'), ('native_input_equivalent','native-input.json'),
                        ('cleanup','SDK37-CLEANUP.json')]:
        check_pin(q[field], name)
    need(q['qualified'] is True and q['sdk_range'] == [37, 37] and
         q['native_member_count'] == 11 and q['all_input_bookends_equal'] is True,
         'handoff does not exceed actual source qualification')
    live, transaction = data['delivery-RESULT.json'], data['TRANSPORT-RESULT.json']
    need(live['passed'] is True and live['source_input_bookends_equal'] is True and
         live['before'] == live['after'] and live['remaining_children'] == '' and
         live['stop_reason'] is None and live['auth_requests'] == 0 and
         transaction['auth_requests'] == transaction['purchase_requests'] == 0,
         'actual original-profile finite delivery')
    for name, receipt_name, digest_field in [
            ('SDK37-CLEANUP.json', 'sdk37-supervisor-RESULT.json', 'supervisor_receipt_sha256'),
            ('TRANSPORT-CLEANUP.json', 'delivery-RESULT.json', 'live_receipt_sha256')]:
        cleanup = data[name]
        need(cleanup[digest_field] == PINS[receipt_name][1] and cleanup['cleanup_complete'] is True and
             cleanup['direct_worker_reaped_echild'] is True and cleanup['terminal_exit_code'] == 0 and
             cleanup['terminal_output_complete'] is True and cleanup['worker_remaining_children_empty'] is True and
             all(v is False for v in cleanup['original_pids_present'].values()) and
             cleanup['unit_properties']['MainPID'] == '0' and
             cleanup['unit_properties']['LoadState'] == 'not-found', 'original custody cleanup')
    for item in data.values():
        no_credit(item)
    return apps, rows, states


def construct(data, at):
    apps, rows, states = validate(data, at)
    registry, freshness, state = [copy.deepcopy(data[n]) for n in
        ('base-current-source-inputs.json','base-current-source-freshness.json','base-CURRENT-SOURCE-STATE.json')]
    c, receipt, native, handoff = [data[n] for n in
        ('candidate.json','source-receipt.json','native-input.json','SOURCE-HANDOFF.json')]
    new = {'package': PACKAGE, 'label': apps[PACKAGE]['label'], 'version_name': VERSION,
        'version_code': CODE, 'required39_member': True, 'retained_dependency_outside_required39': False,
        'source_identity_verified': True, 'signature_verified': True, 'selected_abi': 'arm64-v8a',
        'selected_abi_native_members': 11, 'expected_input': copy.deepcopy(native['application']['expected_input']),
        'input': copy.deepcopy(handoff['final_input']),
        'proofs': {n: pin(n) for n in PINS if not n.startswith('base-')},
        'source_distribution': 'google_play_publisher_delivery',
        'source_observed_utc': c['source']['observed_utc'], 'source_verified_utc': receipt['verified_utc'],
        'source_receipt_origin': 'Actual SDK37 [37,37] verification of all four original United 3622 delivery APKs; source evidence only',
        'replaces_historical_registry_record': {'registry': pin('base-current-source-inputs.json'),
            'package': PACKAGE, 'version_name': OLD_VERSION, 'version_code': OLD_CODE},
        'storage': {'kind': 'pinned_original_host_files', 'host': 'ai395',
            'verified_input_kind': 'local_zip_stored_apk_set', 'local_container_is_publisher_archive': False,
            'fresh_destination_custody_required_before_installation': True,
            'keep_until_root_archive_and_actual_installation_custody': True,
            'original_delivery_apks': copy.deepcopy(receipt['original_delivery_apks'])},
        'device_profile_match_qualified': False, **{k: False for k in NO_CREDIT}}
    registry['applications'] = [new if a['package'] == PACKAGE else a for a in registry['applications']]
    registry['source_overrides'].append({'package': PACKAGE, 'previous_registry': pin('base-current-source-inputs.json'),
        'qualified_source': pin('SOURCE-HANDOFF.json'), 'qualification_result': pin('sdk37-supervisor-RESULT.json'),
        'previous_registry_and_archive_bytes_unchanged': True, 'other_28_required_records_unchanged': True,
        'companion_record_unchanged': True, **{k: False for k in NO_CREDIT}})
    registry['source_evidence_batches'].append({'kind': 'United_current_official_delivery_successor',
        'packages': [PACKAGE], 'source': pin('SOURCE-HANDOFF.json'),
        'result': pin('sdk37-supervisor-RESULT.json'), 'contains_apk_bytes': False,
        **{k: False for k in NO_CREDIT}})
    row = copy.deepcopy(rows[PACKAGE])
    row.update({'previous_selected_input_version': OLD_VERSION, 'previous_selected_input_version_code': OLD_CODE,
        'selected_input_version': VERSION, 'selected_input_version_code': CODE, 'current_acquired_version': VERSION,
        'source_input_selected': True, 'source_input_closed_by': pin('source-receipt.json'), 'input_blocker': None,
        'latest_release_recheck_required_before_activation': True,
        'difference': 'The actual original-profile Google Play 4.2.104/code3622 delivery and all four APK SDK37 identities are qualified. Older3621 evidence remains history. Installation, device profile, runtime and business acceptance remain pending.',
        **{k: False for k in NO_CREDIT}})
    row['complete_inputs'].append({'role': 'selected_current_source_input', 'host': 'ai395',
        'verified_input': copy.deepcopy(handoff['final_input']), 'version': VERSION, 'version_code': CODE,
        'source_kind': 'official_google_play_delivery_via_original_aurora_sdk',
        'source_receipt': pin('source-receipt.json'), 'candidate': pin('candidate.json'),
        'observed_utc': c['source']['observed_utc'], 'verified_utc': receipt['verified_utc'],
        'original_delivery_apks': 4, 'original_delivery_bytes': sum(a['bytes'] for a in c['apks']),
        'selected_abi': 'arm64-v8a', 'signature_verified_by_sdk37': True,
        'all_outer_zip_members_crc_verified': True, 'local_container_is_publisher_archive': False,
        **{k: False for k in NO_CREDIT}})
    row['version_observations'].append({'version': VERSION, 'version_code': CODE, 'platform': 'Android',
        'source_kind': 'original_google_play_GET_ITEMS', 'metadata': pin('current-metadata.json'),
        'observed_utc': c['source']['observed_utc'],
        'scope': 'Original unchanged anonymous device/profile/locale transaction; no country or device compatibility inference'})
    freshness['rows'] = [row if a['package'] == PACKAGE else a for a in freshness['rows']]
    freshness['reconciled_utc'] = at.isoformat()
    freshness['previous_freshness'] = pin('base-current-source-freshness.json')
    freshness['current_refresh_scope'].append(PACKAGE)
    registry_bytes, freshness_bytes = encoded(registry), encoded(freshness)
    rr, fr = output_pin('current-source-inputs.json', registry_bytes), output_pin('current-source-freshness.json', freshness_bytes)
    state.update({'created_utc': at.isoformat(), 'previous_source_state': pin('base-CURRENT-SOURCE-STATE.json'),
        'current29_registry': rr, 'current29_freshness': fr,
        'current_source_successor': {'package': PACKAGE, 'previous_version': OLD_VERSION,
            'version': VERSION, 'version_code': CODE, 'qualification': pin('sdk37-supervisor-RESULT.json'),
            'source_receipt': pin('source-receipt.json'), 'metadata_join_only': True}})
    state['source_override_packages'].append(PACKAGE)
    state['source_inputs']['registry'], state['source_inputs']['freshness'] = rr, fr
    state['source_inputs']['United_current_source'] = pin('SOURCE-HANDOFF.json')
    state['applications'] = [({'package': PACKAGE, 'kind': 'third_party', 'source_identity_verified': True,
        'latest_qualified_at_merge_time': True, 'latest_release_recheck_required_before_activation': True,
        'current_registry_record': copy.deepcopy(new), 'historical_state_record': copy.deepcopy(states[PACKAGE]),
        **{k: False for k in NO_CREDIT}} if a['package'] == PACKAGE else a) for a in state['applications']]
    return registry, freshness, state


def validate_output(data, registry, freshness, state, at):
    """Check the whole deterministic update, all unrelated records, and input joins."""
    old_apps = indexed(data['base-current-source-inputs.json']['applications'], 30)
    old_rows = indexed(data['base-current-source-freshness.json']['rows'], 29)
    old_states = indexed(data['base-CURRENT-SOURCE-STATE.json']['applications'], 39)
    apps, rows, states = indexed(registry['applications'], 30), indexed(freshness['rows'], 29), indexed(state['applications'], 39)
    for old, new in ((old_apps, apps), (old_rows, rows), (old_states, states)):
        need(set(old) == set(new), 'original complete package set changed')
        need(all(old[p] == new[p] for p in old if p != PACKAGE), 'unrelated package changed')
    need(state['required_before_installation'] == data['base-CURRENT-SOURCE-STATE.json']['required_before_installation'],
         'complete installation prerequisite map changed')
    need(state['full_GSI_dependency'] == data['base-CURRENT-SOURCE-STATE.json']['full_GSI_dependency'] and
         state['exemptions'] == data['base-CURRENT-SOURCE-STATE.json']['exemptions'] and
         state['retained_dependency_outside_required39'] ==
         data['base-CURRENT-SOURCE-STATE.json']['retained_dependency_outside_required39'] and
         state['live_Beike_dependencies'] == data['base-CURRENT-SOURCE-STATE.json']['live_Beike_dependencies'],
         'GSI, exemptions, companion or Beike custody changed')
    need(apps[PACKAGE]['version_name'] == rows[PACKAGE]['selected_input_version'] == VERSION and
         apps[PACKAGE]['version_code'] == rows[PACKAGE]['selected_input_version_code'] == CODE and
         apps[PACKAGE]['expected_input'] == data['native-input.json']['application']['expected_input'] and
         apps[PACKAGE]['input'] == data['SOURCE-HANDOFF.json']['final_input'] and
         states[PACKAGE]['current_registry_record'] == apps[PACKAGE], 'selected version and exact input binding')
    expected = construct(data, at)
    need((registry, freshness, state) == expected, 'output differs from exact United-only metadata update')
    for item in (registry, freshness, state):
        no_credit(item)
    need(state['all_39_latest_qualified'] is False and state['all_39_runtime_accepted'] is False,
         'global source/latest/runtime boundary')


def generate(data, at):
    registry, freshness, state = construct(data, at)
    validate_output(data, registry, freshness, state, at)
    return {'current-source-inputs.json': encoded(registry),
            'current-source-freshness.json': encoded(freshness),
            'CURRENT-SOURCE-STATE.json': encoded(state)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=Path(__file__).resolve().parent / 'inputs')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--at', required=True)
    args = parser.parse_args(argv)
    at = utc(args.at)
    data = read_inputs(args.inputs)
    bodies = generate(data, at)
    out = args.out.absolute()
    need(out.parent.resolve() == out.parent and not os.path.lexists(out),
         'new ordinary output directory required')
    out.mkdir(mode=0o700)
    result = {'schema': 'pocket4-united-required39-source-successor-v1', 'state': 'PASSED_METADATA_JOIN_ONLY',
        'created_utc': at.isoformat(), 'package': PACKAGE, 'version_name': VERSION, 'version_code': CODE,
        'inputs': {name: pin(name) for name in PINS},
        'outputs': {name: output_pin(name, body) for name, body in bodies.items()},
        'other38_state_records_unchanged': True, 'other28_required_registry_records_unchanged': True,
        'companion_record_unchanged': True, 'Beike_source_replay_preserved': True,
        'complete_installation_prerequisites_unchanged': True, 'python_integer_F9_preserved': True,
        'APK_or_GSI_bodies_read': 0, 'SDK_commands': 0, 'new_downloads': 0, 'Android_actions': 0,
        'owner_CURRENT_changed': False, **{k: False for k in NO_CREDIT}}
    for name, body in {**bodies, 'RESULT.json': encoded(result)}.items():
        with (out / name).open('xb') as stream:
            stream.write(body)
    print(json.dumps({'state': result['state'], 'package': PACKAGE, 'version_code': CODE,
                      'required_apps': 39, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
