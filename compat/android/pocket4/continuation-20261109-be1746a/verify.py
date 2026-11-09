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
