#!/usr/bin/env python3
"""Reconstruct a single SZZC source successor from recorded SDK37 evidence.

This consumes captured proof metadata. It does not reopen an APK, start Android,
refresh a network observation, or award installation/runtime/business credit.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent
REPO_PATH = 'compat/android/pocket4/current-app-acceptance/source-refresh-20261119/szzc/'
PACKAGE = 'com.szzc'
OLD_BYTES = 220522994
OLD_SHA = '7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96'
NEW_BYTES = 220498418
PREFIX_BYTES = 58720256
PREFIX_SHA = 'f6132a3989b706664209dda867c0c5d0816bc76b2fef3488abc144cd80a28c0d'
SECOND_PREFIX_SHA = '64300f2c18df066c0b9d667eba858c85fe30f759de62aea6d9776d4e914e7242'
SIGNER = 'd85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'
BASE_PINS = {
    'base-current-source-inputs.json': (116810, '62df07622afa60960863dd9721cfd8b46a67b74076355c150534052f1f58abb1'),
    'base-current-source-freshness.json': (109341, '459a5fd3b74ac186bb0bd19d30874b36ba9b54e2453824b38410843e24289918'),
    'base-CURRENT-SOURCE-STATE.json': (169275, '79a3b9063fa9140d2eff7709632378e7ed2c0520aa28293993ec389d3f5b7b31'),
    'base-CURRENT-BUSINESS-PLAN.json': (146172, '8f209ce7c4be9d8330f8a4280babcb2ad8f62595b6fb5462adb3b0e88c7d282e'),
    'CANDIDATE42.json': (283411, '3fd428793499f4811ff5a73c912c95ed23dfd2c82987f3a737a84624e79f5669'),
    'PUBLISHER-REDIRECT-HEAD.json': (1502, '73fc14312fe687859899e9a1f9fa2d2ed3d3a52d90dcdd29ee1642a7845c64fd'),
    'FAILED-TRANSPORT-RESULT.json': (2031, '25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07'),
    'PARTIAL-PREFIX-FREEZE.json': (1662, '01536a3d7139e58e176a739414a29500700df4cece2895df9c7a5277a0f030c2'),
    'FAILED-RESUME1-TRANSPORT-RESULT.json': (4818, 'b8ee3b641bdfdce72a1e0cdab1f9f2af057af0a415e5a82397876676dc4c5ce8'),
    'SECOND-PREFIX-FREEZE.json': (3108, 'ed046d71ca079dded74e0a074980ca17340c322a1dfcc6c7b9020bd56fc9527d'),
    'NATIVE-INVENTORY-DIAGNOSTIC.json': (91834, '6ca274d5ecfa097ad67a50ab4a5aacdcf2bb0f2ed26d74067acc2ab9b04fc4fd'),
    'SDK-FIRST-FAILED-RESULT.json': (13681, '39b9ef57cb36527de9caf1b4002f1776ad7cdd0bf5a4628fa5978b2b9dd30b82'),
    'SDK-R3-FAILURE-INDEPENDENT-RETIREMENT.json': (11566, 'eab10669b9c73dc43cb86cfc6939ee54bd9ff6609066092963dae93b201cb48f'),
    'UNIT-RETIREMENT.json': (18092, '804d4a05972c11feff8021be67c0bbda6508a53ddde0ebdb29f08077a26acc85'),
    'SDK-RESULT.json': (30397, 'eea02bf9e2bddd7752e65f6e1718a48aad1b3173606d084b9af50ccec6d78062'),
    'source-receipt.json': (4231750, '7cc2ef5420115fd3c75a137ae48c6794b45cee509b332a357657e44cb29c3eec'),
    'RESUME2-TRANSPORT-RESULT.json': (7051, '450a84ed4b1c70b092c175fa8e3c8fd1d8912fd86295b80518dd960fdffe33d5'),
}
NO_CREDIT = ('installed', 'runtime_qualified', 'native_compatibility_qualified',
             'business_qualified', 'production_ready', 'native_source_layout_qualified')
OUTPUT_NAMES = ('current-source-inputs.json', 'current-source-freshness.json',
                'CURRENT-SOURCE-STATE.json', 'CURRENT-BUSINESS-PLAN.json')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(result.tzinfo is not None, 'timezone required')
    return result


def file_pin(relative, body):
    return {'path': REPO_PATH + relative, 'bytes': len(body), 'sha256': digest(body)}


def input_pin(data, name):
    return file_pin('inputs/' + name, data['_raw']['inputs/' + name])


def check_source_pin(actual, data, name):
    expected = input_pin(data, name)
    need((actual['bytes'], actual['sha256']) == (expected['bytes'], expected['sha256']),
         'recorded source pin mismatch: ' + name)


def no_credit(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in NO_CREDIT or key in ('all_39_latest_qualified', 'all_39_runtime_accepted',
                                         'whole_app_business_accepted', 'execution_ready'):
                need(item is False, 'borrowed qualification: ' + key)
            no_credit(item)
    elif isinstance(value, list):
        for item in value:
            no_credit(item)


def indexed(rows, size):
    result = {row['package']: row for row in rows}
    need(len(rows) == len(result) == size, 'unique complete package cohort')
    return result


def read_inputs(root=ROOT):
    root = Path(root).resolve()
    pins = json.loads((root / 'INPUT-PINS.json').read_bytes())
    need(pins['schema'] == 'pocket4-szzc-recorded-source-input-pins-v1', 'input manifest schema')
    entries = pins['files']
    need(len(entries) == len({x['path'] for x in entries}), 'duplicate input path')
    data = {'_raw': {}, '_root': root}
    for item in entries:
        name = item['path']
        parts = Path(name).parts
        need(parts and parts[0] in ('inputs', 'source', 'reviews') and '..' not in parts
             and not Path(name).is_absolute(), 'only packet-owned input path')
        path = root / name
        st = path.lstat()
        need(path.resolve() == path and stat.S_ISREG(st.st_mode) and st.st_nlink == 1
             and 0 <= st.st_size <= 16 * 1024 * 1024, 'bounded regular input')
        raw = path.read_bytes()
        need((len(raw), digest(raw)) == (item['bytes'], item['sha256']), 'full input pin: ' + name)
        data['_raw'][name] = raw
        if name.startswith('inputs/') and name.endswith('.json'):
            data[name[7:]] = json.loads(raw)
    for name, pin in BASE_PINS.items():
        raw = data['_raw']['inputs/' + name]
        need((len(raw), digest(raw)) == pin, 'original fixed baseline: ' + name)
    worker = data['_raw']['source/qualify_current_szzc_r4.py']
    need((len(worker), digest(worker)) == (30722, 'a532640ead889c0b73345b45c9ddab7d34bc5eccb157d473222d6b099b2e4b7c'),
         'actual reviewed SDK worker')
    return data


def validate(data, at):
    at = utc(at) if isinstance(at, str) else at
    apps = indexed(data['base-current-source-inputs.json']['applications'], 30)
    fresh = indexed(data['base-current-source-freshness.json']['rows'], 29)
    states = indexed(data['base-CURRENT-SOURCE-STATE.json']['applications'], 39)
    plans = indexed(data['base-CURRENT-BUSINESS-PLAN.json']['packages'], 39)
    old = apps[PACKAGE]
    need((old['version_name'], old['version_code'], old['input']['bytes'], old['input']['sha256']) ==
         ('9.6.3', 329, OLD_BYTES, OLD_SHA), 'actual selected329 predecessor')
    head = data['PUBLISHER-REDIRECT-HEAD.json']
    failure = data['FAILED-TRANSPORT-RESULT.json']
    freeze = data['PARTIAL-PREFIX-FREEZE.json']
    transport = data['RESUME2-TRANSPORT-RESULT.json']
    sdk = data['SDK-RESULT.json']
    receipt = data['source-receipt.json']
    need(failure['complete'] is False and failure['total_bytes_received_before_terminal'] == PREFIX_BYTES,
         'original timeout is retained as a failure')
    need(freeze['prefix']['bytes'] == PREFIX_BYTES and freeze['prefix']['sha256'] == PREFIX_SHA
         and freeze['original_unit']['retired'] is True, 'original retired prefix freeze')
    need(head['http_status'] == 200 and head['content_length'] == str(NEW_BYTES)
         and head['selected_APK_bytes'] == OLD_BYTES
         and head['etag'] == '"108948280DD69A433DD2AEFD4585FD2B"', 'actual observed publisher identity drift')
    need(transport['complete'] is True and transport['source_identity_verified'] is False
         and transport['signature_verified'] is False
         and transport['http']['status'] == 206
         and transport['http']['content_range'] == 'bytes 168361302-220498417/220498418'
         and transport['http']['content_length'] == '52137116'
         and transport['http']['etag'] == head['etag']
         and transport['http']['last_modified'] == head['last_modified']
         and transport['http']['url'] == head['request_url']
         and transport['http']['conditional_if_match'] == head['etag'], 'exact conditional Range identity')
    need(transport['all_five_input_bookends_unchanged'] is True
         and transport['full_SHA_readback_verified'] is True
         and transport['prefix_SHA_readback_unchanged'] is True
         and transport['same_inode_append_only'] is True
         and transport['prefix_bytes_redownloaded'] == 0
         and transport['prefix_before']['sha256'] == transport['prefix_after']['sha256'] == SECOND_PREFIX_SHA,
         'complete file readback and preserved original prefix')
    failed_range = data['FAILED-RESUME1-TRANSPORT-RESULT.json']
    second_freeze = data['SECOND-PREFIX-FREEZE.json']
    need(failed_range['complete'] is False and failed_range['actual_inode_size_at_terminal'] == 168361302
         and failed_range['all_three_input_bookends_unchanged'] is True
         and second_freeze['prefix']['bytes'] == 168361302
         and second_freeze['prefix']['sha256'] == SECOND_PREFIX_SHA
         and second_freeze['both_original_units_retired'] is True
         and second_freeze['original_58720256_prefix'] == {'bytes': PREFIX_BYTES, 'sha256': PREFIX_SHA, 'full_readback_unchanged': True}
         and transport['tail_bytes_downloaded'] == 52137116, 'both true bounded failures and complete final segment')
    need(sdk['success'] is True and sdk['source_identity_verified'] is True
         and sdk['source_candidate_only'] is True and sdk['current_input_selected'] is False
         and sdk['candidate_full_disk_SHA_readback_verified'] is True, 'actual successful source-only SDK terminal')
    need(sdk['worker_source']['sha256'] == digest(data['_raw']['source/qualify_current_szzc_r4.py']),
         'recorded SDK worker and retained source')
    check_source_pin(sdk['transport'], data, 'RESUME2-TRANSPORT-RESULT.json')
    check_source_pin(sdk['source_receipt'], data, 'source-receipt.json')
    check_source_pin(sdk['previous_current_registry'], data, 'base-current-source-inputs.json')
    check_source_pin(sdk['historical_signer_reference'], data, 'CANDIDATE42.json')
    check_source_pin(sdk['original_HEAD'], data, 'PUBLISHER-REDIRECT-HEAD.json')
    check_source_pin(sdk['original_failed_transport'], data, 'FAILED-TRANSPORT-RESULT.json')
    check_source_pin(sdk['retired_prefix_freeze'], data, 'PARTIAL-PREFIX-FREEZE.json')
    check_source_pin(sdk['first_failed_range'], data, 'FAILED-RESUME1-TRANSPORT-RESULT.json')
    check_source_pin(sdk['retired_second_prefix_freeze'], data, 'SECOND-PREFIX-FREEZE.json')
    check_source_pin(sdk['prior_failed_SDK'], data, 'SDK-FIRST-FAILED-RESULT.json')
    check_source_pin(sdk['original_native_inventory_diagnostic'], data, 'NATIVE-INVENTORY-DIAGNOSTIC.json')
    check_source_pin(receipt['original_native_inventory_diagnostic'], data, 'NATIVE-INVENTORY-DIAGNOSTIC.json')
    failed_sdk = data['SDK-FIRST-FAILED-RESULT.json']
    need(failed_sdk['success'] is False and failed_sdk['source_identity_verified'] is False
         and failed_sdk['SDK_commands'] == [], 'original strict native inventory failure retained')
    apk = receipt['APK']
    need(apk == sdk['candidate'] and apk['path'] == transport['artifact']['path']
         and apk['bytes'] == transport['artifact']['bytes'] == NEW_BYTES
         and apk['sha256'] == transport['artifact']['sha256'] and apk['sha256'] != OLD_SHA
         and apk['identity'] == transport['artifact']['identity'], 'full new source APK custody chain')
    need(receipt['package'] == sdk['package'] == PACKAGE
         and receipt['version_name'] == receipt['version_name_axml'] == sdk['version_name']
         and receipt['version_code'] == sdk['version_code']
         and receipt['long_version_code'] == sdk['long_version_code'] >= 329,
         'package and no-downgrade current329 version relation')
    need(receipt['long_version_code'] > 329 or receipt['version_name'] == '9.6.3',
         'same versionCode with changed versionName requires separate review')
    need(receipt['source_qualification_is_conditional_on_successful_terminal_RESULT_and_all_bookends'] is True
         and receipt['source_identity_verified'] is True
         and receipt['signature_verified_for_API'] == 37
         and receipt['signer_certificate_sha256'] == sdk['signer_certificate_sha256'] == [SIGNER]
         and receipt['selected_signing_scheme']['certificate_sha256'] == [SIGNER],
         'SDK37 signature and successful terminal conditions')
    historical = indexed(data['CANDIDATE42.json']['selected_candidates'], 42)[PACKAGE]['proposed_official_input']
    need(historical['version_code'] == 328 and historical['signer_certificate_sha256'] == [SIGNER],
         'historical328 used only for signer continuity')
    commands = sdk['SDK_commands']
    need(commands == receipt['commands'] and len(commands) == 3
         and [x['name'] for x in commands] == ['szzc-badging', 'szzc-manifest', 'szzc-signature'],
         'exact three captured SDK commands')
    for command in commands:
        need(command['exit'] == 0 and command['actual_child_reaped'] is True
             and command['after_reap_echild'] is True and command['original_pidfd_held_until_reaped'] is True
             and command['output_complete'] is True and not command.get('termination'),
             'original SDK child complete and reaped')
        for channel in ('stdout', 'stderr'):
            raw = data['_raw']['inputs/' + command['name'] + '.' + channel]
            pin = command[channel]
            need((len(raw), digest(raw)) == (pin['bytes'], pin['sha256']), 'complete captured SDK output pin')
    need(sdk['remaining_children'] == '' and len(sdk['bookends']) >= 15
         and all(x['F9_and_full_SHA_equal'] is True for x in sdk['bookends']), 'complete held input and tool bookends')
    need({(x['bytes'], x['sha256']) for x in sdk['bookends']} >=
         {(apk['bytes'], apk['sha256']), BASE_PINS['CANDIDATE42.json'], BASE_PINS['base-current-source-inputs.json']},
         'new APK and both source history inputs actually bookended')
    before = dict(line.split() for line in sdk['memory_events_before'].splitlines())
    after = dict(line.split() for line in sdk['memory_events_after'].splitlines())
    need(all(before[k] == after[k] for k in ('oom', 'oom_kill', 'oom_group_kill')), 'no SDK cgroup OOM')
    need(receipt['all_ZIP_members_CRC_and_SHA_verified'] is True
         and sdk['complete_ZIP_member_count'] == len(receipt['complete_zip_members']) > 0,
         'complete ZIP integrity inventory')
    members = {x['name']: x for x in receipt['complete_zip_members']}
    need(len(members) == sdk['complete_ZIP_member_count'] and all(x['complete_eof_crc_verified'] is True
         and re.fullmatch('[0-9a-f]{64}', x['sha256']) for x in members.values()), 'every original ZIP member')
    native = receipt['native_members']
    need(sdk['native_member_count'] == len(native)
         and sdk['native_ABIs'] == receipt['native_ABIs'] == sorted({x['abi'] for x in native}),
         'actual native ABI inventory')
    for lib in native:
        member = members[lib['name']]
        need(all(lib[k] == member[k] for k in member) and lib['execution_qualified'] is False,
             'native member source digest without runtime credit')
    diagnostic = data['NATIVE-INVENTORY-DIAGNOSTIC.json']
    original_native = {row['name']: row for row in diagnostic['native_members']}
    cross = receipt['cross_ABI_source_members']
    expected_cross = {
        'lib/arm64-v8a/libexecmain_x86.so': (211616, 'f2358a1888e0321f773875cffdce6629b3987f5237aca10d80bb4b51cfbee0ad', 2, 62),
        'lib/arm64-v8a/libexec_x86.so': (667144, '7ad636af838b62daa7fb02bb440504c46b58d03040aee4bdb137b2686d5e7f89', 2, 62),
        'lib/armeabi-v7a/libexecmain_x86.so': (132520, '937776804511269ce1d0c375fdac2d4ac3dfba6704bdf59a8e1be83851cd1cfb', 1, 3),
        'lib/armeabi-v7a/libexec_x86.so': (556824, 'db40145f67b021701ede31205357fc81e69a67825f061bc9d01e9bd739d79bd4', 1, 3),
    }
    need(diagnostic['schema'] == 'pocket4-szzc-original-native-inventory-diagnostic-v1'
         and diagnostic['APK'] == apk and diagnostic['all_input_bookends_unchanged'] is True
         and diagnostic['native_member_count'] == len(original_native) == len(native) == 118
         and diagnostic['mismatch_count'] == len(cross) == 4
         and {x['name'] for x in cross} == set(expected_cross)
         and {x['name'] for x in diagnostic['mismatches']} == set(expected_cross),
         'complete actual native diagnostic and exact four cross-ABI source facts')
    for lib in native:
        original = original_native[lib['name']]
        need((lib['bytes'], lib['sha256'], lib['crc32'], lib['elf_class'], lib['elf_machine'], lib['abi']) ==
             (original['bytes'], original['sha256'], original['crc32'], original['actual_class'],
              original['actual_machine'], original['directory_ABI']), 'all118 native records joined to original diagnostic')
        if lib['name'] in expected_cross:
            need((lib['bytes'], lib['sha256'], lib['elf_class'], lib['elf_machine']) == expected_cross[lib['name']]
                 and lib['directory_ABI_matches_ELF'] is False and lib['generic_native_guard_passed'] is False
                 and lib['cross_ABI_source_inventory_only'] is True
                 and lib['native_runtime_blocker_retained'] is True, 'explicit cross-ABI payload gets no native approval')
        else:
            need(lib['directory_ABI_matches_ELF'] is True and lib['generic_native_guard_passed'] is True
                 and lib['cross_ABI_source_inventory_only'] is False, 'unchanged native guard for other114')
    need(cross == [x for x in native if x['name'] in expected_cross]
         and sdk['cross_ABI_source_members'] == cross, 'exact source cross-ABI receipt/terminal relation')
    selected_cross = [x for x in cross if x['abi'] == 'arm64-v8a']
    need(len(selected_cross) == 2 and receipt['selected_arm64_directory_cross_ABI_members'] == selected_cross
         and sdk['selected_arm64_directory_cross_ABI_members'] == selected_cross,
         'both mismatches in the selected ARM64 directory stay visible')
    for record in (sdk, receipt):
        need(record['native_runtime_blocker_retained'] is True and record['native_source_layout_qualified'] is False
             and record['all_native_members_match_directory_ABI'] is False
             and record['generic_native_validator_changed'] is False
             and record['generic_native_guard_passed_member_count'] == 114
             and record['cross_ABI_source_member_count'] == 4
             and record['selected_arm64_directory_cross_ABI_member_count'] == 2,
             'source signature qualification does not erase native layout blocker')
    retirement = data['UNIT-RETIREMENT.json']
    need(retirement['schema'] == 'pocket4-szzc-source-independent-retirement-v3'
         and retirement['passed'] is True and retirement['original_clients_independently_observed'] is True
         and retirement['all_original_client_outputs_complete_and_unmodified'] is True,
         'actual independent five-client retirement receipt')
    clients = {x['session_id']: x for x in retirement['original_clients']}
    expected_clients = [
        ('DOWNLOAD-EXECUTION.json', 1, 'dpty-7cc463c11a090b00909074e35f085c6f131e75401467727ed0f0bfbbdb19bcfe'),
        ('RESUME1-EXECUTION.json', 1, 'dpty-e3114b8d37ec1ecccec3f6fec62efd367c21beb501839d8b4493238db1df31b5'),
        ('RESUME2-EXECUTION.json', 0, 'dpty-1fc0cbe32da6816affde397cf4bcb2e011109c66d206de24cab7dd4e9f6930d5'),
        ('SDK-FIRST-EXECUTION.json', 1, 'dpty-38a05f1243df46e2eada63f530ae988e99dd61629e6256825fb4f9783f25a11a'),
        ('SDK-EXECUTION.json', 0, 'dpty-6326cc29940ae6606e76e1cb04eebc07f9a4ff90640d727ab68640c7c4fcfc52'),
    ]
    need(len(clients) == len(retirement['original_clients']) == 5
         and set(clients) == {x[2] for x in expected_clients}, 'exact five independently observed original clients')
    for key, exit_code, session in expected_clients:
        terminal = data[key]
        raw_text = terminal['text'].encode('utf-8')
        independent = clients[session]
        need(terminal['session_id'] == session and terminal['status']['exit_code'] == exit_code
             and terminal['output_complete'] is True and terminal['status']['output_complete'] is True
             and terminal['status']['state'] == 'exited' and terminal['text_is_lossy'] is False
             and terminal['status']['capture_error'] is None and terminal['utf8_pending'] is False
             and terminal['truncated_before_offset'] is False and terminal['offset'] == 0
             and terminal['next_offset'] == terminal['available_end'] == len(raw_text)
             and terminal['status']['bytes_stored'] == terminal['status']['bytes_seen'] == len(raw_text)
             and terminal['chunk_sha256'] == digest(raw_text)
             and independent['whole_output_bytes'] == len(raw_text)
             and independent['whole_output_sha256'] == digest(raw_text)
             and independent['exit_code'] == exit_code and independent['output_complete'] is True,
             'complete exact original terminal and independent full-output identity: ' + key)
    need(retirement['all_five_units_retired'] is True, 'all original source units retired')
    units = retirement['units']
    expected_units = {'p4-szzc-current-download-5cd1-r1.service', 'p4-szzc-current-resume-5cd1-r1.service',
                      'p4-szzc-current-resume2-5cd1-r1.service', 'p4-szzc-current-sdk37-5cd1-r1.service',
                      'p4-szzc-current-sdk37-5cd1-r2.service'}
    need(len(units) == 5 and {x['name'] for x in units} == expected_units,
         'exact five original source units')
    for unit in units:
        need(unit['unit_properties'] == {'LoadState': 'not-found', 'ActiveState': 'inactive',
             'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''}
             and unit['cgroup_exists'] is False and unit['exit_code'] == 0,
             'original unit and cgroup actually retired')
    need(retirement['actual_candidate'] == apk
         and retirement['candidate_full_post_retirement_SHA_F9_verified'] is True
         and retirement['all_three_SDK_children_pidfd_reaped_echild'] is True,
         'independent final APK custody and SDK retirement')
    for role, name in [('original_failed_transport', 'FAILED-TRANSPORT-RESULT.json'),
                       ('first_failed_resume', 'FAILED-RESUME1-TRANSPORT-RESULT.json'),
                       ('resumed_transport', 'RESUME2-TRANSPORT-RESULT.json'),
                       ('sdk_qualification', 'SDK-RESULT.json'), ('prior_failed_sdk', 'SDK-FIRST-FAILED-RESULT.json')]:
        check_source_pin(retirement['terminal_pins'][role], data, name)
    need(all(retirement['source_receipt'][k] == sdk['source_receipt'][k] for k in ('path', 'bytes', 'sha256'))
         and receipt['required_terminal_RESULT_path'] == retirement['terminal_pins']['sdk_qualification']['path'],
         'actual complete source receipt and original successful terminal pathname')
    check_source_pin(retirement['source_receipt'], data, 'source-receipt.json')
    need(utc(sdk['started_utc']) <= utc(sdk['completed_utc']) <= at, 'actual SDK completion before metadata join')
    for value in (sdk, receipt, transport, data['base-current-source-inputs.json'],
                  data['base-current-source-freshness.json'], data['base-CURRENT-SOURCE-STATE.json'],
                  data['base-CURRENT-BUSINESS-PLAN.json']):
        no_credit(value)
    return apps, fresh, states, plans


def construct(data, at):
    apps, rows, states, plans = validate(data, at)
    at = utc(at) if isinstance(at, str) else at
    registry, freshness, state, plan = [copy.deepcopy(data[name]) for name in
        ('base-current-source-inputs.json', 'base-current-source-freshness.json',
         'base-CURRENT-SOURCE-STATE.json', 'base-CURRENT-BUSINESS-PLAN.json')]
    sdk, receipt, transport = [data[name] for name in
        ('SDK-RESULT.json', 'source-receipt.json', 'RESUME2-TRANSPORT-RESULT.json')]
    version, code = receipt['version_name'], receipt['long_version_code']
    apk = receipt['APK']
    source_input = {k: apk[k] for k in ('path', 'bytes', 'sha256')}
    source_input['f9'] = [int(value) for value in apk['identity']]
    expected = {'version_code': code, 'apks': [{'name': 'base.apk', 'bytes': apk['bytes'], 'sha256': apk['sha256']}],
                'source_receipt': input_pin(data, 'source-receipt.json')}
    selected_abi = 'arm64-v8a' if 'arm64-v8a' in receipt['native_ABIs'] else None
    proof_names = ('PUBLISHER-REDIRECT-HEAD.json', 'FAILED-TRANSPORT-RESULT.json',
                   'PARTIAL-PREFIX-FREEZE.json', 'FAILED-RESUME1-TRANSPORT-RESULT.json',
                   'SECOND-PREFIX-FREEZE.json', 'RESUME2-TRANSPORT-RESULT.json',
                   'SDK-RESULT.json', 'source-receipt.json', 'UNIT-RETIREMENT.json',
                   'NATIVE-INVENTORY-DIAGNOSTIC.json', 'SDK-FIRST-FAILED-RESULT.json',
                   'SDK-R3-FAILURE-INDEPENDENT-RETIREMENT.json')
    new = {'package': PACKAGE, 'label': apps[PACKAGE]['label'], 'version_name': version,
           'version_code': code, 'required39_member': True, 'retained_dependency_outside_required39': False,
           'source_identity_verified': True, 'signature_verified': True,
           'signer_certificate_sha256': [SIGNER], 'selected_abi': selected_abi,
           'selected_abi_native_members': sum(x['abi'] == selected_abi for x in receipt['native_members']),
           'native_ABIs': receipt['native_ABIs'], 'actual_native_ELF_ABIs': receipt['actual_native_ELF_ABIs'],
           'cross_architecture_source_members': 4, 'selected_abi_cross_architecture_source_members': 2,
           'selected_abi_matching_ELF_native_members': sum(x['abi'] == selected_abi and x['directory_ABI_matches_ELF'] for x in receipt['native_members']),
           'native_inventory_diagnostic': input_pin(data, 'NATIVE-INVENTORY-DIAGNOSTIC.json'),
           'cross_ABI_source_members': copy.deepcopy(receipt['cross_ABI_source_members']),
           'selected_arm64_directory_cross_ABI_members': copy.deepcopy(receipt['selected_arm64_directory_cross_ABI_members']),
           'native_runtime_blocker_retained': True, 'expected_input': expected, 'input': source_input,
           'proofs': {name: input_pin(data, name) for name in proof_names},
           'source_distribution': 'publisher_direct', 'source_observed_utc': transport['completed_utc'],
           'source_verified_utc': sdk['completed_utc'],
           'source_receipt_origin': 'Actual SDK37 [37,37] source verification of the complete current publisher standalone APK; all ZIP members, manifest, signer and native headers checked.',
           'replaces_historical_registry_record': {'registry': input_pin(data, 'base-current-source-inputs.json'),
               'package': PACKAGE, 'version_name': '9.6.3', 'version_code': 329, 'input': copy.deepcopy(apps[PACKAGE]['input'])},
           'storage': {'kind': 'pinned_original_host_files', 'host': 'ai395',
               'verified_input_kind': 'original_publisher_standalone_apk',
               'local_container_is_publisher_archive': False,
               'fresh_destination_custody_required_before_installation': True,
               'keep_until_root_archive_and_actual_installation_custody': True},
           'device_profile_match_qualified': False, **{k: False for k in NO_CREDIT}}
    registry['applications'] = [new if row['package'] == PACKAGE else row for row in registry['applications']]
    registry['source_overrides'].append({'package': PACKAGE,
        'previous_registry': input_pin(data, 'base-current-source-inputs.json'),
        'qualification_result': input_pin(data, 'SDK-RESULT.json'),
        'qualified_source': input_pin(data, 'source-receipt.json'),
        'previous_registry_and_archive_bytes_unchanged': True, 'other_28_required_records_unchanged': True,
        'companion_record_unchanged': True, **{k: False for k in NO_CREDIT}})
    registry['source_evidence_batches'].append({'kind': 'SZZC_current_publisher_artifact_source_successor',
        'packages': [PACKAGE], 'source': input_pin(data, 'source-receipt.json'),
        'result': input_pin(data, 'SDK-RESULT.json'), 'contains_apk_bytes': False,
        **{k: False for k in NO_CREDIT}})
    fresh_row = copy.deepcopy(rows[PACKAGE])
    fresh_row.update({'previous_selected_input_version': '9.6.3', 'previous_selected_input_version_code': 329,
        'selected_input_version': version, 'selected_input_version_code': code, 'current_acquired_version': version,
        'source_input_selected': True, 'source_input_closed_by': input_pin(data, 'source-receipt.json'),
        'input_blocker': None, 'latest_release_recheck_required_before_activation': True,
        'difference': 'The actual publisher artifact changed by 24,576 bytes. It retains four cross-ABI helper payloads, including two in the selected ARM64 directory, whose native/runtime qualification remains blocked. The new complete APK passed SDK37 source verification and the pinned historical signer comparison. This selects its exact new source identity; previous current package and the failed transfer remain retained. Installation, native runtime and whole-app business qualification remain pending.',
        **{k: False for k in NO_CREDIT}})
    fresh_row['complete_inputs'].append({'role': 'selected_current_source_input', 'host': 'ai395',
        'verified_input': source_input, 'version': version, 'version_code': code,
        'source_kind': 'publisher_direct', 'source_receipt': input_pin(data, 'source-receipt.json'),
        'observed_utc': transport['completed_utc'], 'verified_utc': sdk['completed_utc'],
        'signature_verified_by_sdk37': True, 'all_outer_zip_members_crc_verified': True,
        **{k: False for k in NO_CREDIT}})
    fresh_row['version_observations'].append({'version': version, 'version_code': code, 'platform': 'Android',
        'source_kind': 'current_publisher_signed_APK_manifest', 'observed_utc': sdk['completed_utc'],
        'url': transport['http']['url'], 'APK_sha256': apk['sha256'],
        'source_receipt': input_pin(data, 'source-receipt.json'),
        'scope': 'Actual observed publisher source identity; no other channel TTL or device compatibility renewal'})
    freshness['rows'] = [fresh_row if row['package'] == PACKAGE else row for row in freshness['rows']]
    freshness['previous_freshness'] = input_pin(data, 'base-current-source-freshness.json')
    freshness['reconciled_utc'] = at.isoformat()
    if PACKAGE not in freshness['current_refresh_scope']:
        freshness['current_refresh_scope'].append(PACKAGE)
    registry_pin = file_pin('actual/current-source-inputs.json', encoded(registry))
    fresh_pin = file_pin('actual/current-source-freshness.json', encoded(freshness))
    state.update({'created_utc': at.isoformat(),
        'previous_source_state': input_pin(data, 'base-CURRENT-SOURCE-STATE.json'),
        'current29_registry': registry_pin, 'current29_freshness': fresh_pin,
        'current_source_successor': {'package': PACKAGE, 'previous_version': '9.6.3',
            'previous_version_code': 329, 'version': version, 'version_code': code,
            'qualification': input_pin(data, 'SDK-RESULT.json'),
            'source_receipt': input_pin(data, 'source-receipt.json'), 'metadata_join_only': True}})
    if PACKAGE not in state['source_override_packages']:
        state['source_override_packages'].append(PACKAGE)
    state['source_inputs']['registry'], state['source_inputs']['freshness'] = registry_pin, fresh_pin
    state['source_inputs']['SZZC_current_publisher_source'] = input_pin(data, 'source-receipt.json')
    new_state = {'package': PACKAGE, 'kind': 'third_party', 'source_identity_verified': True,
        'latest_qualified_at_merge_time': True, 'latest_release_recheck_required_before_activation': True,
        'current_registry_record': copy.deepcopy(new), 'historical_state_record': copy.deepcopy(states[PACKAGE]),
        'native_runtime_blocker_retained': True,
        **{k: False for k in NO_CREDIT}}
    state['applications'] = [new_state if row['package'] == PACKAGE else row for row in state['applications']]
    new_plan = copy.deepcopy(plans[PACKAGE])
    new_plan.update(source_body_pin_metadata=copy.deepcopy(source_input), source_version=version,
                    source_version_code=code, source_identity_verified_in_fixed_receipts=True,
                    source_native_inventory={'diagnostic': input_pin(data, 'NATIVE-INVENTORY-DIAGNOSTIC.json'),
                        'native_member_count': 118, 'cross_ABI_member_count': 4,
                        'selected_arm64_directory_cross_ABI_member_count': 2,
                        'cross_ABI_source_members': copy.deepcopy(receipt['cross_ABI_source_members']),
                        'native_compatibility_qualified': False}, native_runtime_blocker_retained=True)
    plan['packages'] = [new_plan if row['package'] == PACKAGE else row for row in plan['packages']]
    plan['prior_SZZC_source_preflight_plan'] = input_pin(data, 'base-CURRENT-BUSINESS-PLAN.json')
    previous_successor = copy.deepcopy(plan['current_source_successor'])
    plan['current_source_successor'] = {'changed_packages': [PACKAGE], 'other38_package_rows_unchanged': True,
        'registry': registry_pin, 'freshness': fresh_pin,
        'source_state': file_pin('actual/CURRENT-SOURCE-STATE.json', encoded(state)),
        'previous_current_source_successor': previous_successor,
        'remaining_latest_release_recheck_before_activation': True,
        'scope': 'The actual current publisher SZZC source identity is joined into the selected preflight; all runtime bindings and business checks remain pending.'}
    return registry, freshness, state, plan


def validate_output(data, outputs, at):
    registry, freshness, state, plan = outputs
    for old_name, new, key, size in [
        ('base-current-source-inputs.json', registry, 'applications', 30),
        ('base-current-source-freshness.json', freshness, 'rows', 29),
        ('base-CURRENT-SOURCE-STATE.json', state, 'applications', 39),
        ('base-CURRENT-BUSINESS-PLAN.json', plan, 'packages', 39)]:
        old_rows, new_rows = indexed(data[old_name][key], size), indexed(new[key], size)
        need(set(old_rows) == set(new_rows) and all(old_rows[k] == new_rows[k] for k in old_rows if k != PACKAGE),
             'unrelated package or companion changed: ' + old_name)
    for field in ('required_before_installation', 'full_GSI_dependency', 'exemptions',
                  'retained_dependency_outside_required39', 'live_Beike_dependencies'):
        need(state[field] == data['base-CURRENT-SOURCE-STATE.json'][field], 'source state gate changed: ' + field)
    for field in ('required_before_installation', 'global_unresolved_gates', 'common_gate_definitions',
                  'exemptions', 'counts', 'retained_companion_not_required39'):
        need(plan[field] == data['base-CURRENT-BUSINESS-PLAN.json'][field], 'business gate changed: ' + field)
    new_plan, old_plan = indexed(plan['packages'], 39)[PACKAGE], indexed(data['base-CURRENT-BUSINESS-PLAN.json']['packages'], 39)[PACKAGE]
    allowed = {'source_body_pin_metadata', 'source_version', 'source_version_code', 'source_identity_verified_in_fixed_receipts', 'source_native_inventory', 'native_runtime_blocker_retained'}
    need({k: v for k, v in new_plan.items() if k not in allowed} ==
         {k: v for k, v in old_plan.items() if k not in allowed}, 'SZZC business/runtime binding changed')
    need(new_plan['source_body_pin_metadata'] == indexed(registry['applications'], 30)[PACKAGE]['input'],
         'selected preflight really consumes new source bytes')
    for value in outputs:
        no_credit(value)


def generate(data, at):
    outputs = construct(data, at)
    validate_output(data, outputs, at)
    return dict(zip(OUTPUT_NAMES, map(encoded, outputs), strict=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--at', required=True)
    args = parser.parse_args()
    data = read_inputs(args.root)
    bodies = generate(data, args.at)
    args.out.mkdir(mode=0o700, exist_ok=False)
    result = {'schema': 'pocket4-szzc-recorded-source-successor-v1',
        'state': 'PASSED_METADATA_JOIN_ONLY', 'created_utc': utc(args.at).isoformat(), 'package': PACKAGE,
        'version_name': data['source-receipt.json']['version_name'],
        'version_code': data['source-receipt.json']['long_version_code'],
        'inputs': file_pin('INPUT-PINS.json', (args.root / 'INPUT-PINS.json').read_bytes()),
        'outputs': {name: file_pin('actual/' + name, raw) for name, raw in bodies.items()},
        'other38_state_and_preflight_rows_unchanged': True, 'other28_required_registry_rows_unchanged': True,
        'companion_unchanged': True, 'all_installation_migration_runtime_gates_preserved': True,
        'APK_bodies_read': 0, 'new_SDK_commands': 0, 'network_requests': 0, 'Android_actions': 0,
        'owner_CURRENT_changed': False, **{k: False for k in NO_CREDIT}}
    for name, body in {**bodies, 'RESULT.json': encoded(result)}.items():
        (args.out / name).write_bytes(body)
    print(json.dumps({'state': result['state'], 'package': PACKAGE, 'version_code': result['version_code'],
                      'current_outputs_reconstructed': len(bodies), 'production_ready': False}, sort_keys=True))


if __name__ == '__main__':
    main()
