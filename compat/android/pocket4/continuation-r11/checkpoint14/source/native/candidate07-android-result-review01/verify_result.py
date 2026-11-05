#!/usr/bin/env python3
"""Offline cross-check of existing, exact candidate07 qualification receipts."""
from pathlib import Path
import hashlib
import json
import os
import re

NATIVE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
ENGINE = '3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a'
RESULT_SHA = '4e1899db8d0f82a3d80df231f10b09fed644028440a1d77e820e50413c3378d1'
CONTRACT = [('r2', 'svc', 0x7e001, False), ('r2', 'smc-handler', 0x7fffe, True),
            ('r2', 'smc-default', 0xfc0000, False), ('r3', 'smc-mask-edit', 0x707fffe, True)]


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def unique(pairs):
    value = {}
    for key, row in pairs:
        need(key not in value, 'duplicate JSON key: ' + key)
        value[key] = row
    return value


def pinned(path, digest, size=None):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == digest, 'SHA changed: ' + str(path))
    need(size is None or len(raw) == size, 'length changed: ' + str(path))
    return json.loads(raw, object_pairs_hook=unique)


def check_manifest(directory, name='SOURCE_PINS.json'):
    value = json.loads((directory / name).read_bytes(), object_pairs_hook=unique)
    for relative, row in value['files'].items():
        path = Path(relative)
        need(not path.is_absolute() and '..' not in path.parts, 'manifest path escapes')
        raw = (directory / path).read_bytes()
        need(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
             'frozen source changed: ' + str(path))
    return len(value['files'])


def counters(raw):
    return {key: int(value) for key, value in (line.split() for line in raw.splitlines())}


def main():
    old_source_count = check_manifest(NATIVE / 'engine-qualification-template-03')
    source_count = check_manifest(NATIVE / 'engine-qualification-template-04')
    binding = pinned(NATIVE / 'engine-qualification07-android-runtime-final01/binding.json',
                     '244132df6d226ffe704d0325a5bbf2f2e6260a7a5c2777874672d204b63291db')
    original = {}
    for name, row in {**binding['build'], 'host': binding['host_result'],
                      'prepared': binding['prepared'], 'review': binding['root_review']}.items():
        original[name] = pinned(row['local_path'], row['sha256'])
    runtime = pinned(EVIDENCE / 'candidate07-android-result-read01/runtime-result.json', RESULT_SHA, 30990)
    reader = pinned(EVIDENCE / 'candidate07-android-result-read01/reader-report.json',
                    '68ed4374c33f515b1cdd1122cf05c0c4139284a3a00269e45ea96a4963031db7', 34606)
    need(reader['state'] == 'ORIGINAL_ANDROID_RESULT_READ' and reader['sha256'] == RESULT_SHA and
         reader['bytes'] == 30990 and reader['text'].encode() ==
         (EVIDENCE / 'candidate07-android-result-read01/runtime-result.json').read_bytes(), 'reader binding differs')
    need(reader['named_before'] == reader['held_before'] == reader['held_after'] == reader['named_after'],
         'original was not stable during held read')
    need(reader['writes'] == reader['children_created'] == reader['Main_actions'] == 0, 'reader side effects')
    need(runtime['state'] == 'OWNED_SYNC_SIGNAL_CANARY_PASS' and runtime['run_returned'] is True and
         runtime['all_owned_contracts_complete'] is True and not runtime.get('error'), 'runtime did not complete')
    for key in ('evidence_errors', 'failure_evidence_errors', 'primary_command_failure', 'first_cleanup_error'):
        need(not runtime.get(key), 'runtime error field: ' + key)
    need(runtime['source_contract_preserved'] is True and
         runtime['source_contract_before'] == runtime['source_contract_after'], 'source contract changed')
    contract = runtime['source_contract_before']
    argv = original['review']['controller']['argv']
    for flag, key in [('--source-manifest-sha256', 'runtime_manifest_sha256'),
                      ('--inputs-sha256', 'input_sha256'), ('--prepared-sha256', 'prepared_sha256'),
                      ('--host-suite-sha256', 'host_suite_sha256'),
                      ('--host-launch-inputs-sha256', 'host_launch_inputs_sha256'),
                      ('--namespace-helper-sha256', 'namespace_helper_sha256'),
                      ('--namespace-helper-source-sha256', 'namespace_helper_source_sha256'),
                      ('--namespace-helper-qualification-sha256', 'namespace_helper_qualification_sha256')]:
        need(argv.count(flag) == 1 and argv[argv.index(flag) + 1] == contract[key], 'admitted pin differs: ' + key)
    template = NATIVE / 'engine-qualification-template-04'
    runtime_manifest = pinned(template / 'references/r5-source-manifest.json', contract['runtime_manifest_sha256'])
    refs = json.loads((template / 'reference-pins.json').read_bytes())
    for name, row in refs['files'].items():
        raw = (template / 'references' / name).read_bytes()
        need(hashlib.sha256(raw).hexdigest() == row['sha256'] and len(raw) == row['bytes'], 'reference differs')
    need(contract['host_qualification_wrapper_manifest_sha256'] ==
         hashlib.sha256((template / 'references/host-wrapper-source-manifest.json').read_bytes()).hexdigest(),
         'host wrapper manifest differs')
    need(contract['preparation_manifest_sha256'] == '3f12e8bcde951712a20208aaeed04f1125bac58993ce1a3f5a93e4f950a9b103',
         'preparation contract differs')
    host, prepared = original['host'], original['prepared']
    need(host['state'] == 'PASS_FULL_HOST_SUITE' and host['binding_before'] == host['binding_after'] and
         host['tests_complete'] is True and host['resources_complete'] is True, 'host suite incomplete')
    need(runtime['host_suite']['assessment'] == host['assessment'], 'host assessment changed')
    assessment = host['assessment']
    need([assessment[k] for k in ('registered_count', 'executed_count', 'completed_count')] == [3793, 3791, 3788]
         and len(assessment['disabled']) == 2 and len(assessment['skipped']) == 3 and
         assessment['all_expected_registered_executed'] is True and not assessment['failed_cases'], 'host policy differs')
    need(host['binding_before']['engine']['sha256'] == prepared['engine_sha256'] == runtime['boot']['engine_sha256'] == ENGINE,
         'engine binding differs')
    need(host['binding_before']['source_receipt']['sha256'] == binding['build']['receipt']['sha256'], 'build source differs')
    need(prepared['services_started'] is False and prepared['old_userdata_read'] is False and
         prepared['fresh_empty_data_images'] is True and len(prepared['copied_records']) == 86, 'prepared scope differs')
    need(original['review']['admitted'] is True and original['review']['main_deployment_admitted'] is False and
         original['review']['review_evidence']['metadata_generation_enabled'] is False, 'admission scope differs')
    need(runtime['main_preserved'] is True and runtime['main_after'] == prepared['main_before'], 'Main invariant changed')
    need(runtime['main_resources_before'] == runtime['main_resources_after'] == runtime['main_after']['resources'],
         'Main limits changed')
    need(runtime['boot']['sdk'] == '37' and runtime['boot']['android'] == '17' and runtime['boot']['completed'] == '1' and
         runtime['adbd_before_cleanup'] == 'stopped', 'private boot profile differs')
    need(len(runtime['cases']) == 4, 'case count differs')
    rows, pids = [], set()
    name = prepared['name']
    for value, (revision, case, mask, precise) in zip(runtime['cases'], CONTRACT):
        label = revision + '-' + case
        need(value['case'] == case and value['status'] == 'PASS' and value['nonce'] == prepared['nonces'][label] and
             value['package'] == prepared['apks'][revision]['package'], 'case identity differs')
        need(int(value['required_checks'], 16) == mask and int(value['checks'], 16) & mask == mask and
             value['precise_siginfo_observed'] is precise and value['commercial_app_claim'] is False, 'case contract differs')
        mapped = value['actual_mapped_engine']; engine = mapped['binding']; process = mapped['process']
        need(engine['engine_sha256'] == ENGINE and engine['hash_bound_by_held_file_before_and_after_case'] is True and
             engine['mapped_device'] == 66306 and engine['mapped_inode'] == 44182354, 'actual engine mapping differs')
        need(process['namespace_pids'] == [process['host_pid'], value['guest_pid']] and
             process['cmdline'] == [value['package']] and len(process['uids']) == 4 and
             len(set(process['uids'])) == 1 and process['host_pid'] not in pids, 'probe process identity differs')
        pids.add(process['host_pid'])
        need(process['cgroup'] == ['0::/system.slice/' + name + '-daemon.service/apps/uid_' +
                                  str(process['uids'][0]) + '/pid_' + str(value['guest_pid'])], 'probe outside owned daemon')
        maps = engine['actual_host_maps']; need(len(maps) == 4, 'engine mapping count differs')
        for line in maps:
            match = re.fullmatch(r'[0-9a-f]+-[0-9a-f]+ ([rwxps-]{4}) [0-9a-f]+ ([0-9a-f]+):([0-9a-f]+) (\d+) +/system/lib64/libberberis_arm64.so', line)
            need(match is not None and os.makedev(int(match[2],16),int(match[3],16)) == engine['mapped_device']
                 and int(match[4]) == engine['mapped_inode'], 'map line is not the held inode')
        need(any(' r-xp ' in line for line in maps), 'executable mapping missing')
        rows.append({key: value[key] for key in ('case','package','nonce','guest_pid','checks','required_checks')})
    need(runtime['own_packages_removed'] is True and runtime['private_package_baseline_restored'] is True and
         not runtime['package_cleanup_errors'], 'package retirement incomplete')
    cleanup = runtime['cleanup']; need(not cleanup['errors'] and not cleanup['reconciliations'], 'cleanup errors')
    units = {row['role']: row for row in cleanup['units']}
    need(set(units) == {'bus','sway','presenter','daemon'} and len(cleanup['retirements']) == 4, 'owned unit set differs')
    for row in cleanup['retirements']:
        unit = units[row['role']]
        need(row['unit'] == unit['unit'] == name + '-' + row['role'] + '.service' and unit['invocation'] and
             unit['description'] == name + ' ' + prepared['nonce'] + ' ' + row['role'], 'unit authority differs')
        need(row['retired'] is True and row['stop_attempted'] is True and row['stop_returncode'] == 0 and
             row['automatic_retry'] is False, 'retirement did not complete')
        before, after = row['before'], row['after']
        need(before['path'] == after['path'] == unit['group'] and before['held_identity'] == after['held_identity'] and
             before['filesystem_type'] == after['filesystem_type'] == 0x63677270 and
             before['hierarchical_population_checked'] is after['hierarchical_population_checked'] is True and
             after['absent'] is True, 'whole held hierarchy retirement differs')
        need(row['final']['LoadState'] == 'not-found' and row['final']['MainPID'] == '0' and
             row['final']['ControlGroup'] == '' and row['final']['InvocationID'] == '', 'unit remains')
    resources = runtime['cleanup_resource_observations']; need(len(resources) == 5, 'resource rows differ')
    resource_rows = []
    for row in resources:
        events = counters(row['memory.events'])
        need(all(events[k] == 0 for k in ('oom','oom_kill','oom_group_kill')), 'owned OOM event')
        if row['unit'] != 'current-owned-controller-actor':
            need(row['unit'] in {x['unit'] for x in units.values()} and all(v == 0 for v in events.values()),
                 'owned service event changed')
        resource_rows.append({'unit':row['unit'],'memory_events':events,
                              'memory_peak':row.get('memory.peak'), 'properties':row.get('properties')})
    need(runtime['production_ready'] is False and runtime['commercial_app_claim'] is False, 'scope broadened')
    print(json.dumps({'schema':1,'state':'OFFLINE_RECEIPT_CROSSCHECK_PASSED','runtime_sha256':RESULT_SHA,
        'original_template03_payloads_checked':old_source_count,'current_template04_payloads_checked':source_count,
        'reference_files_checked':len(refs['files']),'runtime_manifest_declared_files':len(runtime_manifest['files']),
        'runtime_130_remote_source_files_re_read_by_this_offline_review':False,
        'runtime_source_before_after_contract_matches_admission':True,
        'host_counts':{'registered':3793,'executed':3791,'completed':3788,'disabled':2,'skipped':3,'failed':0},
        'host_held_records_unchanged':len(host['binding_before']['records']), 'case_assessments':rows,
        'case_raw_native_assertions_independently_recomputed':False,
        'Main_after_equals_prepared_Main_before':True,'Main_resource_limits_unchanged':True,
        'Main_memory_event_delta_available_in_this_result':False,
        'four_owned_service_hierarchies_retired':True,'own_packages_removed':True,
        'resource_rows':resource_rows,'all_owned_memory_events_zero_is_not_a_valid_generalization':True,
        'actor_cgroup_absence_after_outer_terminal_independently_checked_here':False,
        'metadata_generation_enabled':False,'new_test_execution':False,'Main_deployment':False,
        'whole_app_qualification':False,'production_ready':False},indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
