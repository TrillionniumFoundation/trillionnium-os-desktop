#!/usr/bin/env python3
"""Preserve one actual CI test harness; never execute an ignored test or ELF."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time

HERE = Path(__file__).resolve().parent
KEY = ('droidloom-supervisor', 'droidloom_supervisor')
CASE = 'production_namespace::tree::tests::persistent_syscalls::privileged_private_persistent_data_syscall_controls'
STATE = 'ALL_CURRENT_ORDINARY_AND19_NORMAL_RELEASE_BUILDS_PASSED'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def check_terminal(result, source, catalog, bins, docs, head, run_id, inventory):
    """Pure report checks; source, logs and actual OFD checks are separate below."""
    ordinary = sum(len(row['all']) - len(row['ignored']) for row in catalog.values())
    ignored = [{'package': p, 'target': t, 'case': name}
               for (p, t), row in sorted(catalog.items()) for name in row['ignored']]
    need(result['schema'] == 'p4-native-leaf-complete-source-and-release-ci-v1'
         and result['state'] == STATE and result['errors'] == [], 'complete successful original CI required')
    need(type(head) is str and re.fullmatch('[0-9a-f]{40}', head)
         and integer(run_id, 1) and result['github_commit'] == head
         and type(result['github_run_id']) is int and result['github_run_id'] == run_id,
         'actual same GitHub head and run required')
    need(result['current_packet_inventory_sha256'] == inventory
         and result['source_tree'] == source['tree']
         and type(result['source_files']) is int and result['source_files'] == source['files']
         and type(result['source_bytes']) is int and result['source_bytes'] == source['bytes'],
         'exact complete source and packet required')
    for field in ('all_source_bookends_equal', 'all_input_packet_bookends_equal', 'doc_test_commands_executed'):
        need(result[field] is True, 'required actual CI proof missing: ' + field)
    for field in ('historical_ELFs_reused', 'runtime_qualified', 'production_ready',
                  'example_mains_executed', 'full_workspace_qualified', 'positive_hardware_branches_inferred'):
        need(result[field] is False, 'source-only boundary changed: ' + field)
    for field, value in [('fresh_ordinary_passed', ordinary), ('fresh_test_targets', 49),
                         ('historical_tests_counted_as_fresh', 0), ('Android_builds', 0),
                         ('Android_starts', 0), ('fresh_example_tests_passed', 9),
                         ('fresh_doc_tests_passed', 0), ('jobs', 1), ('test_threads', 1)]:
        need(type(result[field]) is int and result[field] == value, 'exact actual CI count: ' + field)
    need(result['ignored_not_executed'] == ignored and len(ignored) == 31
         and CASE in catalog[KEY]['ignored'], 'all original ignored cases and one new case remain unexecuted')
    need(type(result['fresh_release_binaries']) is dict
         and set(result['fresh_release_binaries']) == {key[1] for key in bins}
         and len(result['fresh_release_binaries']) == 19, 'original nineteen production releases remain separate')
    need(type(result['fresh_example_binaries']) is dict and len(result['fresh_example_binaries']) == 3,
         'three actual example builds required')
    need(type(result['doc_targets_checked']) is list
         and all(type(row['passed_cases']) is int for row in result['doc_targets_checked'])
         and result['doc_targets_checked'] == [{'package': row['package'], 'target': row['target'], 'passed_cases': 0}
                                          for row in docs] and len(docs) == 20,
         'complete actual rustdoc target list required')
    need(result['final_descendant_retirement'] == [], 'no unexpected descendant at original finalizer')
    need(integer(result['started_ns'], 1) and integer(result['finished_ns'], 1)
         and result['started_ns'] < result['finished_ns'], 'actual CI interval required')


def check_command(row):
    need(type(row['name']) is str and re.fullmatch('[a-z0-9-]+', row['name'])
         and type(row['argv']) is list and row['argv']
         and all(type(value) is str for value in row['argv']), 'original bounded command shape')
    need(type(row['exit_code']) is int and row['exit_code'] == 0 and row['error'] is None
         and row['cleanup_errors'] == [] and row['timed_out'] is False
         and row['actual_child_reaped'] is True and row['original_pidfd_held_until_reaped'] is True
         and type(row['owned_descendants_remaining']) is int and row['owned_descendants_remaining'] == 0
         and type(row['retired_descendants']) is list
         and not any(item.get('forced') for item in row['retired_descendants']),
         'original command failure or unknown retirement')
    need(integer(row['pid'], 1) and integer(row['start_ticks'], 1)
         and integer(row['started_ns'], 1) and integer(row['finished_ns'], 1)
         and row['started_ns'] <= row['finished_ns'], 'actual child and bounded execution interval')
    need('--ignored' not in row['argv'] or '--list' in row['argv'], 'ignored execution is never authorized here')
    need(CASE not in row['argv'], 'the privileged case cannot have been selected for execution')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(os.geteuid() != 0 and os.uname().machine == 'x86_64', 'ordinary original Linux CI user required')
    spec = importlib.util.spec_from_file_location('actual_test_driver_ci', HERE / 'run_ci.py')
    ci = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci)
    verify = ci.VERIFY
    started = time.monotonic()
    capsule = verify.verify_capsule(args.inventory_sha256)
    producer, work, report = [p.absolute() for p in (args.producer, args.work, args.report)]
    need(all(p.resolve() == p for p in (producer, work, report)), 'canonical actual CI inputs required')
    snapshot = verify.source_snapshot(producer, capsule['rows'], verify.HEAD_TREE)
    report_body = verify.regular(report)
    report_pin = {'path': str(report), **verify.digest(report_body), 'identity': verify.f9(report.lstat())}
    result = verify.decode(report_body)
    expected_tests, expected_bins, catalogs, _ = ci.configuration()
    head, raw_run = os.environ.get('P4_NATIVE_SOURCE_COMMIT', ''), os.environ.get('GITHUB_RUN_ID', '')
    need(re.fullmatch('[1-9][0-9]*', raw_run), 'actual current GitHub run identity required')
    source = {'files': verify.SOURCE_FILES, 'bytes': verify.SOURCE_BYTES, 'tree': verify.HEAD_TREE}
    need(type(result['commands']) is list and len(result['commands']) == 244,
         'complete original 244 actual commands required')
    commands, bodies, log_pins = {}, {}, []
    for row in result['commands']:
        check_command(row)
        name = row['name']
        need(name not in commands and result['started_ns'] <= row['started_ns']
             <= row['finished_ns'] <= result['finished_ns'], 'unique actual command within CI interval')
        commands[name] = row
        for stream in ('stdout', 'stderr'):
            ref = row[stream]
            path = work / 'logs' / (name + '.' + stream)
            need(set(ref) == {'path', 'bytes', 'sha256'} and ref['path'] == str(path)
                 and integer(ref['bytes']) and type(ref['sha256']) is str
                 and re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'exact original stream pin required')
            raw = verify.regular(path)
            need(verify.digest(raw) == {key: ref[key] for key in ('bytes', 'sha256')},
                 'complete original command stream changed')
            log_pins.append(dict(ref, identity=verify.f9(path.lstat())))
            if stream == 'stdout':
                bodies[name] = raw
    need(commands['actual-github-source-head']['argv'] == ['git', 'rev-parse', 'HEAD']
         and bodies['actual-github-source-head'] == (head + '\n').encode('ascii'),
         'actual checked-out head command differs')
    ids = ci.metadata_targets(bodies['workspace-metadata'], producer, expected_tests, expected_bins)
    _, docs, _ = ci.auxiliary_targets(bodies['workspace-metadata'], producer)
    check_terminal(result, source, catalogs, expected_bins, docs, head, int(raw_run), args.inventory_sha256)
    need(result['source_chain'] == capsule['source_chain'], 'actual complete source lineage differs')
    compiled = {}
    for name, selected in [('compile-updater', lambda k: k[0] == 'droidloom-update'),
                           ('compile-remaining27', lambda k: k[0] != 'droidloom-update')]:
        expected = {key: value for key, value in expected_tests.items() if selected(key)}
        actual = ci.artifacts(bodies[name], ids, producer, work / 'target', expected, True)
        need(not set(compiled).intersection(actual), 'duplicate actual compiler-artifact target')
        compiled.update(actual)
    need(set(compiled) == set(expected_tests), 'all 49 actual compilation targets required')
    harnesses = {}
    for ref in result['harnesses']:
        need(set(ref) == {'package', 'target', 'path', 'bytes', 'sha256', 'identity'}, 'exact recorded harness pin')
        need(all(type(ref[key]) is str for key in ('package', 'target', 'path', 'sha256'))
             and re.fullmatch('[0-9a-f]{64}', ref['sha256']) and integer(ref['bytes'], 1)
             and type(ref['identity']) is list and len(ref['identity']) == 9
             and all(integer(value) for value in ref['identity']), 'typed actual executable identity')
        key = (ref['package'], ref['target'])
        need(key in compiled and key not in harnesses and ref['path'] == str(compiled[key]['path']),
             'harness pin must join to one actual compiler-artifact executable')
        harnesses[key] = ref
    need(set(harnesses) == set(expected_tests), 'complete original harness pins required')
    selected_ref = harnesses[KEY]
    original_ref = {key: selected_ref[key] for key in ('path', 'bytes', 'sha256', 'identity')}
    original = compiled[KEY]['path']
    need(ci.elf(original) == original_ref, 'actual original compiler ELF differs from executed CI pin')
    index = sorted(compiled).index(KEY)
    prefix = 'target-%02d' % index
    for suffix, argv, expected in [
        ('-catalog', [str(original), '--list', '--color', 'never'], catalogs[KEY]['all']),
        ('-ignored', [str(original), '--ignored', '--list', '--color', 'never'], catalogs[KEY]['ignored']),
    ]:
        need(commands[prefix + suffix]['argv'] == argv, 'actual selected harness catalog argv differs')
        ci.catalog(bodies[prefix + suffix], expected)
    ordinary = set(catalogs[KEY]['all']) - set(catalogs[KEY]['ignored'])
    need(commands[prefix + '-ordinary']['argv'] == [str(original), '--test-threads=1', '--color', 'never'],
         'selected harness ordinary command must not execute ignored tests')
    verify.test_terminal(bodies[prefix + '-ordinary'].decode('utf-8', 'strict'), ordinary,
                         catalogs[KEY]['ignored'], 0, catalog=catalogs[KEY]['all'])
    output = verify.fresh_destination(args.output, [HERE, producer, work, report])
    output.mkdir(mode=0o700)
    source_fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(verify.f9(os.fstat(source_fd)) == original_ref['identity']
             and verify.f9(original.lstat()) == original_ref['identity'], 'hold exact actual original test ELF OFD')
        destination = output / 'droidloom_supervisor-test-driver'
        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o500)
        digest, total = hashlib.sha256(), 0
        try:
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                total += len(block)
                need(total <= original_ref['bytes'], 'test ELF grew during copy')
                digest.update(block)
                view = memoryview(block)
                while view:
                    count = os.write(destination_fd, view)
                    need(count > 0, 'incomplete artifact copy')
                    view = view[count:]
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
        need(total == original_ref['bytes'] and digest.hexdigest() == original_ref['sha256'],
             'whole copied driver differs from original actual harness')
        copied = ci.elf(destination)
        need({k: copied[k] for k in ('bytes', 'sha256')} == {k: original_ref[k] for k in ('bytes', 'sha256')},
             'fresh artifact readback differs')
        need(verify.regular(report) == report_body and verify.f9(report.lstat()) == report_pin['identity'],
             'original CI report changed during custody')
        need(verify.source_snapshot(producer, capsule['rows'], verify.HEAD_TREE) == snapshot,
             'complete producer source changed during custody')
        after = verify.verify_capsule(args.inventory_sha256)
        need(after['rows'] == capsule['rows'] and after['source_chain'] == capsule['source_chain']
             and after['source_packet_snapshot'] == capsule['source_packet_snapshot'],
             'complete source packet changed during custody')
        for ref in log_pins:
            path = Path(ref['path'])
            need(verify.digest(verify.regular(path)) == {key: ref[key] for key in ('bytes', 'sha256')}
                 and verify.f9(path.lstat()) == ref['identity'], 'original stream bookend changed')
        need(verify.f9(os.fstat(source_fd)) == verify.f9(original.lstat()) == original_ref['identity']
             and ci.elf(original) == original_ref, 'original held executable changed during final source checks')
        need(time.monotonic() - started < 120, 'bounded read-only artifact custody interval expired')
        with (output / 'CURRENT-CI.json').open('xb') as file:
            file.write(report_body)
        manifest = {
            'schema': 'p4-actual-compiled-disposable-syscall-test-driver-v1',
            'state': 'ACTUAL_CI_HARNESS_COPIED_IGNORED_SYSCALL_CASE_NOT_EXECUTED',
            'github_commit': head, 'github_run_id': int(raw_run),
            'source': source, 'source_chain': capsule['source_chain'],
            'packet_inventory_sha256': args.inventory_sha256,
            'original_ci_report': report_pin, 'original_harness': selected_ref,
            'artifact': copied, 'archive_driver_path': destination.name,
            'archive_original_ci_report_path': 'CURRENT-CI.json',
            'compiler_command': commands['compile-remaining27'],
            'compiler_artifact': compiled[KEY]['message'],
            'original_command_streams': log_pins,
            'ordinary_ci_cases_passed': result['fresh_ordinary_passed'],
            'original_production_release_count': 19,
            'ignored_case': CASE, 'ignored_case_present_in_actual_ignored_list': True,
            'all_source_and_packet_bookends_equal': True,
            'original_harness_OFD_held_through_copy_and_final_checks': True,
            'test_driver_executed_by_exporter': False,
            'privileged_syscall_case_executed': False,
            'production_binary': False, 'runtime_qualified': False, 'production_ready': False,
        }
        with (output / 'COMPILE-ONLY-MANIFEST.json').open('x', encoding='utf-8') as file:
            file.write(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        need(ci.elf(destination) == copied, 'published copied artifact changed')
    finally:
        os.close(source_fd)
    print(json.dumps({'state': manifest['state'], 'output': str(output), 'driver_bytes': copied['bytes'],
                      'driver_sha256': copied['sha256'], 'privileged_syscall_case_executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
