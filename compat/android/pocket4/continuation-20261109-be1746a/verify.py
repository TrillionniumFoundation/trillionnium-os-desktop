#!/usr/bin/env python3
"""Verify this frozen source/input capsule; this never grants runtime acceptance."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def verify(root):
    root = root.resolve(strict=True)
    manifest = json.loads((root / 'FILES.json').read_bytes())
    require(manifest.get('schema') == 'pocket4-continuation-source-inputs-v1', 'Unexpected manifest schema')
    require(manifest.get('runtime_qualified') is False, 'Source inventory cannot qualify runtime')
    require(manifest.get('production_ready') is False, 'Source inventory cannot qualify production')
    members = manifest.get('files')
    require(type(members) is list and members, 'Nonempty exact inventory required')
    expected = set()
    total = 0
    for entry in members:
        name = entry.get('path')
        require(type(name) is str, 'Member path must be text')
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and all(p not in ('', '.', '..') for p in relative.parts), 'Unsafe member path')
        require(name == relative.as_posix() and name not in expected and name != 'FILES.json', 'Duplicate or noncanonical member')
        expected.add(name)
        path = root.joinpath(*relative.parts)
        for parent in (path, *path.parents):
            if parent == root:
                break
            require(not parent.is_symlink(), 'Symlink member or parent: ' + name)
        require(stat.S_ISREG(path.lstat().st_mode), 'Nonregular member: ' + name)
        raw = path.read_bytes()
        require(type(entry.get('bytes')) is int and len(raw) == entry['bytes'], 'Size differs: ' + name)
        require(hashlib.sha256(raw).hexdigest() == entry.get('sha256'), 'SHA256 differs: ' + name)
        total += len(raw)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual == expected | {'FILES.json'}, 'Unexpected or absent capsule members')

    native = json.loads((root / 'native/HANDOFF.json').read_bytes())
    require(native['actual_tests'] == {
        'droidloom_source_library': {'failed': 0, 'ignored': 0, 'passed': 26},
        'native_generation_pair_build': {'failed': 0, 'ignored': 0, 'passed': 16},
    }, 'Native executed test counts changed')
    require(native['normal_cli_verify_lock']['projects'] == 600 and native['normal_cli_verify_lock']['returncode'] == 0,
            'Native lock verification absent')
    for key in ('production_ready', 'runtime_qualified', 'shared_aosp_mutated', 'new_aosp_source_materialized_qualified'):
        require(native['limits'][key] is False, 'Native host result cannot grant ' + key)
    native_full = json.loads((root / 'native/full-r8-observation.json').read_bytes())
    require(native_full['outer_H_status']['state'] == 'failed'
            and native_full['outer_H_status']['exit_code'] == 1
            and native_full['outer_H_status']['output_complete'] is True
            and native_full['outer_H_status']['output_durable'] is True,
            'Native r8 is a preserved complete failure, not a successful artifact build')
    require('"deprecated-renderscript-tools" depends on undefined module "bcc_compat"'
            in native_full['first_actual_error']['message'],
            'Native r8 actual first failure changed')
    require(native_full['input_after_qualified'] is True
            and native_full['source_projection_restored'] is True
            and native_full['owned_retirement_complete'] is True,
            'Native r8 restoration or owned retirement absent')
    for key in ('build_success', 'complete_engine_ART_pair_qualified', 'runtime_qualified', 'production_ready'):
        require(native_full[key] is False, 'Failed full build cannot grant ' + key)
    native_retired = json.loads((root / 'native/helper-retirement/retirement-result.json').read_bytes())
    native_terminal = json.loads((root / 'native/helper-retirement/h-terminal.json').read_bytes())
    require(native_retired['state'] == 'RETIRED_EXACT_FOUR_OWN_PAYLOADS'
            and native_retired['errors'] == [] and native_retired['protected_unchanged'] is True
            and native_retired['protected_before']['sha256'] == native_retired['protected_after']['sha256']
            and len(native_retired['removed_roots']) == 4
            and all(row['absent_after'] is True for row in native_retired['removed_roots']),
            'Exact Native helper retirement or protected source readback absent')
    require(native_terminal['state'] == 'succeeded' and native_terminal['exit_code'] == 0
            and native_terminal['output_complete'] is True and native_terminal['output_durable'] is True
            and native_retired['payload_unique_inode_bytes'] == 1316931505
            and native_retired['full_builds_started'] == 0 and native_retired['Android_starts'] == 0,
            'Native helper retirement must preserve its exact completed operation boundary')
    native_current = json.loads((root / 'native/helper-retirement/native-current-observation.json').read_bytes())
    require(native_current['current_generation'] == 'full-ai395-r10'
            and native_current['outer_h_job'] == '1a1bffe0c63-5e21-848'
            and native_current['actual_h_state']['state'] == 'running'
            and native_current['full_build_qualified'] is False
            and native_current['production_ready'] is False,
            'Frozen Native successor observation cannot be promoted into a full build pass')
    audio = json.loads((root / 'audio/test-receipt-rust193.json').read_bytes())
    require(audio['compile_tests']['returncode'] == 0 and audio['tests']['returncode'] == 0, 'Audio actual controls failed')
    marker = 'test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;'
    require(audio['tests']['stdout'].count(marker) == 1, 'All seven Audio controls must have executed')
    audio_full = json.loads((root / 'audio/full-r10-observation.json').read_bytes())
    require(audio_full['ordinary_tools']['command_count'] == 24
            and audio_full['ordinary_tools']['all_commands_exit_zero'] is True
            and audio_full['ordinary_tools']['all_commands_retired'] is True,
            'Audio PASIT ordinary-tool qualification absent')
    require(audio_full['source_continuation']['command_count'] == 17
            and audio_full['source_continuation']['all_commands_exit_zero'] is True
            and audio_full['source_continuation']['all_commands_retired'] is True
            and audio_full['source_continuation']['project_count'] == 430,
            'Audio PASIT materialized-source qualification absent')
    require(audio_full['old_r10_request']['must_not_execute'] is True
            and audio_full['current_r10_r2']['must_not_duplicate_or_replay'] is True,
            'Superseded or running Audio requests must not be relaunched')
    for key in ('full_pass', 'artifact_pass', 'runtime_pass', 'production_ready'):
        require(audio_full['qualifications'][key] is False, 'Running full build cannot grant ' + key)
    audio_failure = json.loads((root / 'audio/full-r10-failure-followup.json').read_bytes())
    require(audio_failure['job_id'] == audio_full['current_r10_r2']['job_id']
            and audio_failure['normal_build_driver']['observed_exited'] is True
            and audio_failure['normal_build_driver']['command_exit_status_reported_by_stderr'] == 1,
            'Audio later failure must bind the same actual full driver')
    require({error['undefined_module'] for error in audio_failure['actual_source_errors']} == {
        'service-ondeviceintelligence.api.combined.system-server.latest',
        'service-ondeviceintelligence-removed.api.combined.system-server.latest',
    }, 'Audio actual generated-provider errors changed')
    for key in ('build_success', 'full_qualified', 'artifact_qualified', 'runtime_qualified', 'production_ready'):
        require(audio_failure[key] is False, 'Failed Audio full driver cannot grant ' + key)
    audio_terminal = json.loads((root / 'audio/full-r10-terminal-completion.json').read_bytes())
    terminal = audio_terminal['job_terminal']
    require(audio_terminal['job_id'] == audio_failure['job_id']
            and terminal['job_id'] == audio_terminal['job_id']
            and terminal['state'] == 'failed' and terminal['exit_code'] == 1
            and terminal['output_complete'] is True and terminal['output_durable'] is True,
            'Audio final terminal must preserve the same failed full generation')
    for key in ('input_after_qualified', 'owned_retirement_complete',
                'owned_unit_retired', 'source_projection_absent_after', 'source_projection_restored'):
        require(audio_terminal['retirement'][key] is True, 'Audio terminal lacks ' + key)
    for key in ('full_qualified', 'runtime_qualified', 'production_ready'):
        require(audio_terminal[key] is False, 'Retired failed build cannot grant ' + key)
    api_root = root / 'audio/api-inputs'
    api = json.loads((api_root / 'source-manifest.json').read_bytes())
    require(api['base_commit'] == 'a0e5114a1728e5ac5a96cdffbf68a84958218765'
            and api['normal_test_counts'] == {
                'audio_filtered_outside_scope': 174, 'audio_passed': 45, 'ignored': 0,
                'new_input_regression_passed': 1, 'source_unit_passed': 24}
            and api['normal_verify_lock'] == {'exit': 0, 'projects': 430, 'root_links': 8},
            'Independent Audio API normal qualification differs')
    green = json.loads((api_root / 'evidence/test-result-r2.json').read_bytes())
    require(green['baseline_regression_reproduced'] is True and len(green['commands']) == 8
            and all(row['exit'] == 0 and row['leader_reaped'] is True
                    and row['timed_out'] is False for row in green['commands']),
            'Audio red regression or complete green command results absent')
    source_stdout = (api_root / 'evidence/commands-r2/normal-source-tests-green.stdout').read_text()
    audio_stdout = (api_root / 'evidence/commands-r2/normal-audio-tests-green.stdout').read_text()
    for marker in ('test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;',
                   'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;'):
        require(source_stdout.count(marker) == 1, 'All declared Audio source controls must execute')
    require(audio_stdout.count('test result: ok. 45 passed; 0 failed; 0 ignored; 0 measured; 174 filtered out;') == 1,
            'All 45 focused Audio controls must execute')
    require(api['historical_425_sha256_unchanged'] == '1dd0671551fb3c07cac4bb9b587346421321a6e4809494299f7b6daa4c49371c'
            and api['historical_pasit_430_sha256_unchanged'] == '78cc10ee7459926ec151e6224e6341d1b33397801330499e5d7f1a13fadb997a',
            'Historical Audio generations must retain their original identities')
    api_review = json.loads((api_root / 'audio-api-independent-review.json').read_bytes())
    require(api_review['findings'] == [] and len(api_review['checks']) == 7
            and api_review['exact_reconstruction']['helper_postimages_verified'] == 6
            and api_review['exact_reconstruction']['owner_postimages_verified'] == 9,
            'Independent Audio helper and successor review incomplete')
    api_handoff = json.loads((api_root / 'handoff.json').read_bytes())
    require(api_handoff['do_not_duplicate_apply'] is True
            and api_handoff['owner_api_successor']['candidate_commit'] == '0342210a3bd82bf46067a1dbaf740e16f291a38a'
            and api_handoff['bcc_same_reconcile_gate']['required_narrow_cone'] == 'tools/bcc_compat'
            and api_handoff['bcc_same_reconcile_gate']['ancestor_materialization_must_be_verified'] is True,
            'Audio owner adoption and exact BCC materialization boundaries changed')
    api_retirement = json.loads((api_root / 'evidence/retirement-receipt.json').read_bytes())
    require(api_retirement['all_removed_absent'] is True
            and api_retirement['active_owned_build_processes'] == []
            and sum(row['logical_bytes'] for row in api_retirement['removed']) == 807595635,
            'Audio helper temporary build and cache retirement absent')
    for key in ('full_qualified', 'runtime_qualified', 'production_ready'):
        require(api[key] is False and green[key] is False, 'Audio host controls cannot grant ' + key)
    broker = json.loads((root / 'broker/qualification.json').read_bytes())
    require(broker['unique_ordinary_passed'] == 184 and broker['ordinary_ignored'] == 24,
            'Integrated supervisor ordinary test counts changed')
    for key in ('production_admission', 'runtime_qualified', 'production_ready'):
        require(broker[key] is False, 'Integrated source controls cannot grant ' + key)
    private = json.loads((root / 'broker/private-userns.json').read_bytes())
    require(private['returncode'] == 0 and private['actual_private_control_passed'] is True,
            'Fixed private syscall control did not pass')
    require(private['protected_equal'] is True and private['terminal_cgroup_retired'] is True,
            'Fixed private control did not preserve or retire its scope')
    require(private['production_admission'] is False and private['android'] == 0,
            'Private control cannot grant production admission or Android acceptance')
    replay = json.loads((root / 'broker/source-replay.json').read_bytes())
    require(replay['replay_passed'] is True and len(replay['files']) == 13,
            'Thirteen-file integrated source replay absent')
    owner_current = json.loads((root / 'broker/current-owner-observation.json').read_bytes())
    owner_empty_base = json.loads((root / 'broker/empty-base-r2-observation.json').read_bytes())
    owner_normal = owner_empty_base['actual_qualification']
    require(owner_normal['passed'] is True and owner_normal['normal_tests_passed'] == 81
            and owner_normal['normal_binaries_built'] == 2
            and owner_normal['negative_cli_controls_passed'] == 8
            and owner_normal['private_controls_executed'] == 0,
            'Latest observed owner empty-base r2 normal qualification differs')
    require(owner_empty_base['runtime_qualified'] is False
            and owner_empty_base['all_blockers_closed'] is False
            and owner_current['runtime_gate']['runtime_qualified'] is False,
            'Owner source observations cannot grant runtime acceptance')
    later_owner = json.loads((root / 'broker/latest-owner-adoption-observation.json').read_bytes())
    nss = later_owner['NSS_owned_probe']
    require(nss['passed'] is True and nss['workers_exited_and_reaped'] == 2
            and nss['observation_only'] is True and nss['authority_issued'] is False
            and nss['lease_or_grant_created'] is False and nss['production_admission'] is False,
            'NSS observation must not issue production authority')
    empty = later_owner['private_empty_base']
    require(empty['passed'] is True and empty['actual_tests_passed'] == 1
            and empty['actual_tests_failed'] == 0 and empty['Android_starts'] == 0
            and empty['production_admission'] is False,
            'Private empty-base fixture must preserve its runtime boundary')
    lifecycle = json.loads((root / 'owner-lifecycle/source-manifest.json').read_bytes())
    lifecycle_inventory_raw = (root / 'owner-lifecycle/FILES.json').read_bytes()
    require(hashlib.sha256(lifecycle_inventory_raw).hexdigest() == '31f1de25436e6497b238235ff05e4dca0962ea371e4c791995c5a6317300f507',
            'Latest frozen lifecycle inventory pin differs')
    lifecycle_inventory = json.loads(lifecycle_inventory_raw)
    lifecycle_names = {row['path'] for row in lifecycle_inventory['files']}
    require(len(lifecycle_inventory['files']) == len(lifecycle_names) == 50
            and {path.relative_to(root / 'owner-lifecycle').as_posix()
                 for path in (root / 'owner-lifecycle').rglob('*') if path.is_file()}
                == lifecycle_names | {'FILES.json'},
            'Lifecycle publication contains missing or prior-generation members')
    for row in lifecycle_inventory['files']:
        raw = (root / 'owner-lifecycle' / row['path']).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                'Frozen lifecycle publication member differs')
    freeze = json.loads((root / 'owner-lifecycle/freeze-manifest.json').read_bytes())
    require(freeze['before_copy_after_identical'] is True
            and freeze['qualified_owner_pinned_sources_match'] is True
            and freeze['owner_paths_before'] == freeze['owner_paths_after'] == 408
            and freeze['owner_manifest_before_sha256'] == freeze['copied_manifest_sha256'] == freeze['owner_manifest_after_sha256']
            and lifecycle['frozen_source_files'] == 408
            and lifecycle['modified_source_files'] == len(lifecycle['changes']) == 3
            and lifecycle['unchanged_source_files'] == 405,
            'Owner lifecycle integration must retain its exact frozen scope')
    normal = json.loads((root / 'owner-lifecycle/normal/result.json').read_bytes())
    require(normal['passed'] is True and len(normal['binaries']) == 2,
            'Owner lifecycle normal build qualification absent')
    marker92 = 'test result: ok. 92 passed; 0 failed; 0 ignored; 0 measured; 151 filtered out;'
    require((root / 'owner-lifecycle/normal/production-normal-tests.stdout').read_text().count(marker92) == 1,
            'All 92 owner lifecycle ordinary controls must have executed')
    fixed = json.loads((root / 'owner-lifecycle/private-r1/result.json').read_bytes())
    require(fixed['passed'] is True and fixed['protected_unchanged'] is True
            and {control['name'] for control in fixed['controls']} == {'userns', 'pid1'}
            and len(fixed['controls']) == 2,
            'Exactly two protected fixed private controls are required')
    for control in fixed['controls']:
        require(control['passed'] is True and control['returncode'] == 0
                and control['owned_unit_terminal'] is True and control['owned_cgroup_absent'] is True,
                'Fixed lifecycle control failed or retained its owned process')
        output = (root / 'owner-lifecycle/private-r1' / control['name'] / 'normal.stdout').read_text()
        require(output.count('test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 242 filtered out;') == 1,
                'Private fixture must have actually executed once')
    review = json.loads((root / 'owner-lifecycle/independent-review.json').read_bytes())
    require(review['findings'] == [] and len(review['checks']) == 7
            and all(check['result'] == 'PASS' for check in review['checks']),
            'Independent frozen lifecycle review has unresolved findings')
    for key in ('production_admission', 'runtime_qualified', 'production_ready'):
        require(lifecycle[key] is False, 'Lifecycle source controls cannot grant ' + key)
    require(lifecycle['Android_starts'] == 0 and fixed['Android_starts'] == 0
            and fixed['production_admission'] is False,
            'Fixed private fixtures cannot grant Android or production admission')
    retirement = json.loads((root / 'owner-lifecycle/private-stage-retirement.json').read_bytes())
    require(len(retirement['exact_binary_files_retired']) == 1
            and all(entry['absent_after'] is True for entry in retirement['exact_binary_files_retired']),
            'Private lifecycle staging binary retirement absent')
    firefox = json.loads((root / 'firefox/delivery.json').read_bytes())['result']
    readback = json.loads((root / 'firefox/independent-readback.json').read_bytes())
    require(firefox['artifact'] == readback['artifact'], 'Firefox delivery/readback identity differs')
    require(readback['full_readback_passed'] is True and readback['bytes_read'] == firefox['artifact']['bytes'],
            'Firefox independent full readback absent')
    require(firefox['installed'] is False and readback['runtime_accepted'] is False,
            'Physical delivery cannot grant application acceptance')
    apps = json.loads((root / 'apps/source-increment.json').read_bytes())
    require(apps['schema'] == 'pocket4-official-four-app-source-increment-v1',
            'Unexpected official-app observation schema')
    app_rows = {row['package']: row for row in apps['candidates']}
    require(len(app_rows) == len(apps['candidates']) == 4,
            'Expected three current candidates and the unresolved Uber row')
    versions = {
        'com.taobao.taobao': ('10.69.0', 866, 'taobao-inspection.json'),
        'com.szzc': ('9.6.2', 328, 'szzc-inspection.json'),
        'com.ss.android.ugc.aweme': ('41.0.0', 410001, 'douyin-inspection.json'),
    }
    refs = apps['canonical_final_receipts']
    artifacts = {entry['sha256']: entry for entry in refs['candidate_artifacts']}
    require(len(artifacts) == 3, 'Expected three canonical APK artifacts')
    for package, (version, code, inspection_name) in versions.items():
        row = app_rows[package]
        inspected = json.loads((root / 'apps' / inspection_name).read_bytes())['result']
        require((row['official_version_name'], row['official_version_code']) == (version, code),
                'Current official version changed: ' + package)
        require(row['signature_verified'] is True and row['new_signature_execution'] is True
                and row['verifier']['exit'] == 0 and inspected['signature_verified'] is True,
                'New signature execution absent: ' + package)
        require(row['signer_certificate_sha256'] == inspected['signer_certificate_sha256']
                and row['native_abis'] == inspected['native_abis'],
                'Inspected signer or ABI differs: ' + package)
        artifact = row['canonical_artifact']
        require(artifacts.get(artifact['sha256']) == artifact,
                'Canonical artifact not bound: ' + package)
        require(artifact['bytes'] == inspected.get('download_bytes', inspected.get('bytes'))
                and artifact['sha256'] == inspected.get('download_sha256', inspected.get('sha256')),
                'Inspected body differs from delivered body: ' + package)
        for key in ('selected', 'installed', 'runtime_accepted', 'production_ready'):
            require(row[key] is False, 'Official delivery cannot grant ' + key)
    require(app_rows['com.ubercab']['current_currency_status'] == 'OFFICIAL_LATEST_BINARY_UNKNOWN',
            'No verified latest complete Uber delivery was obtained')
    require(apps['qualification']['installs'] == 0 and apps['qualification']['selector_mutated'] is False
            and apps['qualification']['current_mutated'] is False
            and apps['qualification']['runtime_accepted'] is False
            and apps['qualification']['production_ready'] is False,
            'Official input qualification cannot alter deployment status')
    independent = json.loads((root / 'apps/independent-readback-receipt.json').read_bytes())
    require(independent['result']['full_readback_passed'] is True
            and independent['result']['manifest_bound_files'] == refs['manifest_bound_files'] == 29
            and independent['result']['manifest_bound_bytes'] == refs['manifest_bound_bytes'] == 680054973
            and independent['result']['selector_unchanged'] is True,
            'Complete canonical app readback absent')
    app_handoff = json.loads((root / 'apps/app-handoff.json').read_bytes())
    require(app_handoff['independent_readback'] == independent['receipt']
            and app_handoff['canonical_final_receipts'] == refs,
            'App handoff is not bound to the verified canonical inputs')
    for key in ('CURRENT_modified', 'global_selector_modified', 'installs',
                'runtime_accepted', 'production_ready', 'all_blockers_closed'):
        require(app_handoff[key] in (False, 0), 'App handoff cannot grant ' + key)
    bili = json.loads((root / 'apps/bilibili/inspection.json').read_bytes())['result']
    require(bili['download_complete'] is True and bili['static_candidate_pass'] is True
            and bili['download_bytes'] == 242067951
            and bili['download_sha256'] == '33b302b285bdbb5ee1e3030c5d65a88b8229ff3d7bbf78df105600e968109bfc'
            and bili['package_fields']['name'] == 'tv.danmaku.bili'
            and bili['package_fields']['versionName'] == '9.18.0'
            and bili['package_fields']['versionCode'] == '9180300',
            'Bilibili current complete official APK identity differs')
    require(bili['signature_verified'] is True and len(bili['commands']) == 2
            and all(command['exit'] == 0 for command in bili['commands'])
            and bili['signer_certificate_sha256'] == ['93ba270f5521139ecafe4bb638ac5b1198bc548f62d9fd8f8580a079faf5910e']
            and bili['installed_comparison']['binary_exact_match'] is True
            and bili['installed_comparison']['signer_exact_match'] is True,
            'Bilibili fresh inspection or historical identity comparison failed')
    bili_custody = json.loads((root / 'apps/bilibili/custody.json').read_bytes())['result']
    bili_readback = json.loads((root / 'apps/bilibili/independent-readback.json').read_bytes())['result']
    require(bili_custody['artifact']['sha256'] == bili['download_sha256']
            and bili_custody['full_readback_passed'] is True
            and bili_readback['full_readback_passed'] is True
            and bili_readback['manifest_bound_files'] == 11
            and bili_readback['manifest_bound_bytes'] == 242129471
            and bili_readback['selector_unchanged'] is True
            and bili_readback['duplicate_and_parts_absent'] is True,
            'Bilibili complete canonical custody and retirement are required')
    for record in (bili, bili_custody, bili_readback):
        require(record['runtime_accepted'] is False and record['production_ready'] is False,
                'Bilibili input observation cannot grant runtime acceptance')
    overlay = json.loads((root / 'apps/previous-three-current-overlay/overlay.json').read_bytes())
    require(overlay['new_full_APK_downloads'] == 0 and overlay['APK_body_files_created'] == 0
            and overlay['APK_partial_files_created'] == 0 and overlay['APK_bytes_explicitly_read'] == 1
            and overlay['new_installations'] == 0 and overlay['new_runtime_acceptances'] == 0
            and overlay['selector_mutations'] == 0 and overlay['production_ready'] is False,
            'Later route metadata must not be promoted to new complete downloads or runtime passes')
    final_observation = json.loads((root / 'final-runtime-observation.json').read_bytes())
    current = final_observation['CURRENT']
    require(current['counters']['production_qualification_limits.final42_passed'] == 0
            and current['counters']['production_qualification_limits.Android_runtime_acceptances'] == 0
            and current['known_final42_denominator'] == 42
            and all(current[key] is False for key in ('production_ready', 'runtime_qualified', 'all_blockers_closed')),
            'Observed final application and runtime gates remain unqualified')
    require(final_observation['owner_lifecycle_source']['all_three_match_r2_preimages'] is True
            and final_observation['owner_lifecycle_source']['all_three_match_r2_postimages'] is False
            and final_observation['boot']['result']['selected_bools_status_and_error_fields']['state']
                == 'BOOT_ATTEMPT_DID_NOT_COMPLETE',
            'Frozen runtime observation must not imply keeper adoption or Android boot success')
    return {'schema': 'pocket4-continuation-source-verification-v1', 'files': len(expected), 'bytes': total,
            'source_and_receipt_integrity': True, 'runtime_qualified': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).parent)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = verify(args.root)
    rendered = json.dumps(result, sort_keys=True, indent=2) + '\n'
    if args.out:
        args.out.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
