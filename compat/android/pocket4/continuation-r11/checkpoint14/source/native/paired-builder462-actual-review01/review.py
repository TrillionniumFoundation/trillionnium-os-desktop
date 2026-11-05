#!/usr/bin/env python3
"""Offline reconciliation of the already completed, root-collected build.

This reads receipts and frozen source only. It never executes the builder,
tests, remote operations, or any received code.
"""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
FROZEN = BASE / 'paired-builder462-compile01'
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/paired-builder462-compile01-transport02')
OUT = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def check(value, message):
    if not value:
        raise RuntimeError(message)


raw = (ACTUAL / 'result.json').read_bytes()
check(len(raw) == 136350 and digest(raw) == 'f9a3dd01d9ebdb60a0e6a34ee99e3b1a2f646a30191eda3643cee5ca36ff544f', 'actual result pin')
result = json.loads(raw)
pages = json.loads((ACTUAL / 'binary-metadata.json').read_bytes())
offset = 0
for page in pages:
    check(page['offset'] == offset and page['size'] == len(raw), 'page range')
    end = offset + page['bytes']
    check(page['next_offset'] == end and digest(raw[offset:end]) == page['chunk_sha256'], 'page digest')
    check(page['version'] == pages[0]['version'] and page['eof'] == (end == len(raw)), 'page version/end')
    offset = end
check(offset == len(raw), 'complete pages')

source_pins = json.loads((FROZEN / 'SOURCE_PINS.json').read_bytes())['files']
for name, expected in source_pins.items():
    actual = pin(FROZEN / name)
    check(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'], 'frozen source pin: ' + name)

constants = {}
for node in ast.parse((FROZEN / 'compile_builder.py').read_text()).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        try:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass
names = constants['TESTS'] + constants['PAIR_TESTS'] + constants['ART_PROJECTION_TESTS']
check(len(names) == len(set(names)) == 24 and result['expected_test_names'] == names, '24 exact selected names')
parent = json.loads((FROZEN / 'compiled-parent451-result.json').read_bytes())
check(parent['expected_test_names'] == names[:22] and parent['focused_tests_passed'] == 22, 'retained 22 parent cases')

old = json.loads((FROZEN / 'compiled-parent451-manifest.json').read_bytes())
new_raw = (FROZEN / 'expected-builder462-manifest.json').read_bytes()
new = json.loads(new_raw)
check(len(old) == 451 and len(new) == 462 and set(old) <= set(new), 'full source counts')
changed = sorted(name for name in new if new[name] != old.get(name))
check(changed == constants['FIXED_ART_DELTA'], 'exact 13 source delta')
changed_old = [name for name in changed if name in old]
added = [name for name in changed if name not in old]
check(len(changed_old) == 2 and len(added) == 11, '2 edits and 11 additions')
for name in changed:
    value = pin(FROZEN / 'delta' / name)
    check(value['sha256'] == new[name]['sha256'] and value['bytes'] == new[name]['bytes'], 'exact delta bytes')
check(result['copied_manifest']['sha256'] == digest(new_raw) == constants['MANIFEST_462'] and result['copied_manifest']['bytes'] == len(new_raw), 'actual source manifest binding')
# The controller serializes the parent row fields in a different order. This
# explains the distinct hash without pretending the two serializations match.
reserialized_old = {name: {'kind': 'file', 'sha256': row['sha256'], 'bytes': row['bytes'], 'mode': row['mode']} for name, row in old.items()}
old_raw = (json.dumps(reserialized_old, indent=2) + '\n').encode()
check(result['original_manifest']['sha256'] == digest(old_raw) and result['original_manifest']['bytes'] == len(old_raw), 'actual parent serialization')
check(result['source_delta']['changed_existing'] == changed_old and result['source_delta']['added'] == added and result['source_delta']['unchanged_existing'] == 449, 'reported source delta')
check(result['source_delta']['ART_sources_executed_or_built'] is False and result['source_delta']['engine_source_files_changed'] == 0, 'ART source data scope')

authorities = {
    'actual_parent451_compile_authority': 'compiled-parent451-result.json',
    'actual_Go_comparison_gate': 'go-control-result.json',
    'actual_selected_dependency_authority': 'selection-result.json',
    'actual_registry_archive_authority': 'registry-result.json',
    'actual_image_tools_authority': 'image-tools-result.json',
}
for key, name in authorities.items():
    local = pin(FROZEN / name)
    check(result[key]['bytes'] == local['bytes'] and result[key]['sha256'] == local['sha256'], key)

commands = result['commands']
check(len(commands) == 57 and len({row['label'] for row in commands}) == 57, 'command count/uniqueness')
check(all(row['returncode'] == 0 and row['timed_out'] is False for row in commands), 'all commands completed')
by_name = {row['label']: row for row in commands}
for label in ('workspace-no-deps', 'selected-build', 'selected-test', 'builder-compile', 'builder-test-compile'):
    argv = by_name[label]['argv']
    check('--offline' in argv and '--locked' in argv, 'offline locked selection/compile')
check(result['actual_build_packages'] == result['actual_test_compile_packages'] and len(result['actual_build_packages']) == 49, 'selected compiler package closure')
registry = json.loads((FROZEN / 'registry-result.json').read_bytes())
observed_registry = {entry.split('#', 1)[1] for entry in result['actual_build_packages'] if entry.startswith('registry+')}
expected_registry = {entry['name'] + '@' + entry['version'] for entry in registry['packages']}
check(observed_registry == expected_registry and len(observed_registry) == 45, '45 exact qualified registry packages')
check(sum(entry.startswith('path+file://') for entry in result['actual_build_packages']) == 4, 'four workspace packages')
check(result['actual_toolchain']['repository_version'] == '1.93.0' and result['actual_toolchain']['global_stable_1_95_not_used'] is True and result['actual_toolchain']['selection_installs_or_updates'] is False, 'pinned repository toolchain')
check(all(row['absent'] is True for row in result['cargo_config_inputs_before']), 'no ambient Cargo config')

test_rows = []
for index, name in enumerate(names):
    row = by_name['projection-test-' + str(index)]
    check(row['argv'] == [result['test_elf']['path'], '--exact', name, '--test-threads=1', '--nocapture', '--logfile', row['independent_libtest_result']['path']], 'exact test argv')
    expected_line = ('ok ' + name + '\n').encode()
    observed = row['independent_libtest_result']
    check(observed['bytes'] == len(expected_line) and observed['sha256'] == digest(expected_line), 'one independent success result')
    gate = {'exact_name': name, 'expected_stdout_runs': 2 if index == 20 else 1, 'filtered_out_per_run': 196, 'outer_results': 1, 'registered_tests': 197, 'summary_and_independent_result_agree': True}
    check(row['focused_result_gate'] == gate == result['focused_result_gates'][index], 'registered/summary agreement')
    test_rows.append({'index': index, 'name': name, 'rc': row['returncode'], 'independent_result_sha256': observed['sha256'], 'independent_result_bytes': observed['bytes'], 'expected_stdout_runs': gate['expected_stdout_runs']})
check(result['actual_registered_test_count'] == 197 and result['focused_tests_passed'] == 24 and result['original_projection_tests_passed'] == 7 and result['pairing_tests_passed'] == 15 and result['ART_projection_tests_passed'] == 2, 'test scope counts')
retirement = by_name['projection-test-20']['normal_fakeroot_daemon_retirement']
check(retirement['remaining'] == [] and retirement['signal_actions'] == 0 and len(retirement['reaped']) == 1 and retirement['reaped'][0]['status'] == 0, 'observed fakeroot retirement')

check(result['state'] == 'PASS' and result['observed_signals'] == [], 'terminal result/signals')
for key in ('original_source_unchanged_after', 'copied_source_unchanged_after', 'cargo_configs_unchanged_after'):
    check(result[key] is True, key)
check(result['dependency_changes'] == [] and result['tool_changes'] == [], 'unchanged dependencies/tools')
check(result['cleanup'] == {'errors': [], 'forced_cleanup': False, 'initial_owned_children': [], 'reaped': [], 'remaining': []}, 'final owned cleanup')
before, after = result['owned_resources_before'], result['owned_resources_after']
for key in ('controller_pid', 'directory_identity', 'membership', 'path'):
    check(before[key] == after[key], 'same owned resource identity')
for key in ('cpu.max', 'memory.max', 'memory.high', 'memory.swap.max'):
    check(before['fields'][key] == after['fields'][key], 'same resource limit')
check(before['fields']['cpu.max'] == '100000 100000' and before['fields']['memory.max'] == '1073741824', 'actual one CPU/one GiB')
deltas = {name: after['events'][name] - value for name, value in before['events'].items()}
check(deltas == result['owned_memory_events_delta'] and all(value == 0 for value in deltas.values()), 'all recorded event deltas zero')
check(result['owned_resource_gate']['pass'] is True and result['owned_resource_gate']['resource_settings_changed'] is False, 'owned resource gate')
check(result['owned_memory_peak'] == int(after['fields']['memory.peak']) == 1014640640 and result['owned_memory_swap_peak'] == 0 and after['fields']['memory.swap.current'] == '0' and after['fields']['memory.swap.max'] == 'max', 'peak and unbounded swap caveat')
check(result['Main_actions'] == result['install_actions'] == 0 and result['Main_identity_observed'] is False and result['platform_APEX_signature_validated'] is False and result['actual_enabled_ART_lifecycle_validated'] is False, 'unclaimed scope')

report = {
    'schema': 1,
    'state': 'ACTUAL_RECEIPT_RECONCILED_SCOPED_PASS',
    'reviewer': '/root/native_bridge_repair',
    'job': '1a1aafae618-fc05-4932',
    'authority_terminal': 'Root observed exit 0, output complete and durable; no independent Hepta call by reviewer.',
    'inputs': [pin(ACTUAL / 'result.json'), pin(ACTUAL / 'binary-metadata.json'), pin(FROZEN / 'SOURCE_PINS.json'), pin(FROZEN / 'compile_builder.py'), pin(FROZEN / 'expected-builder462-manifest.json'), pin(FROZEN / 'compiled-parent451-manifest.json')],
    'source': {'frozen_payload_pins_verified': len(source_pins), 'parent_files': 451, 'candidate_files': 462, 'unchanged_parent_files': 449, 'changed_existing': changed_old, 'added': added, 'candidate_manifest': result['copied_manifest'], 'parent_actual_serialization': result['original_manifest'], 'parent_semantic_map_matches_frozen451': True, 'ART_sources_are_data_not_compiled': True},
    'build': {'commands': len(commands), 'all_rc_zero': True, 'all_timeout_false': True, 'Rust_toolchain': '1.93.0', 'offline_locked': True, 'selected_packages': 49, 'registry_packages': 45, 'workspace_packages': 4, 'source_dependencies_tools_configs_unchanged': True, 'builder_elf': result['builder_elf'], 'test_elf': result['test_elf'], 'remote_input_manifests': {key: result[key] for key in ('tool_inputs', 'image_and_compiler_tool_inputs', 'dependency_inputs')}},
    'tests': {'registered': 197, 'targeted': 24, 'full_197_suite_executed': False, 'parent22_preserved_in_order': True, 'original_projection': 7, 'pairing': 15, 'new_ART_projection': 2, 'actual_image_fixture_cases': 5, 'independent_one_line_success_hashes_recomputed': 24, 'cases': test_rows, 'fakeroot_retirement': retirement},
    'resource': {'cgroup_identity': before['directory_identity'], 'membership': before['membership'], 'cpu_max': before['fields']['cpu.max'], 'memory_max': before['fields']['memory.max'], 'memory_peak': result['owned_memory_peak'], 'swap_peak': 0, 'swap_current_after': 0, 'swap_max_observed': 'max', 'swap_was_not_capped': True, 'all_recorded_event_deltas': deltas, 'identity_and_limits_unchanged': True},
    'cleanup': result['cleanup'],
    'limitations': [
        'This review consumes the complete Root-collected receipt and its exact source contract. It does not rerun tests or independently reopen remote tools, dependency files, or ELF artifacts.',
        'All 24 observed independent libtest result hashes and lengths equal exactly one expected success line. Stdout summary consistency is recorded by the executed controller; raw stdout for all commands is not separately fetched in this review.',
        '197 is the registered count, not a claim that all 197 tests executed. Case 20 intentionally has two stdout runs and one outer independent result.',
        'Image tests use fixture components and actual host image tools. They do not qualify platform signing, a complete production ART APEX, deployed images, or enabled lifecycle behavior.',
        'No Soong/native-engine rebuild or installed candidate07 change occurred. Ordinary V2 and the 26 NOFILE cases are outside this builder run.',
        'Main_actions=0 does not establish Main invariance; Main_identity_observed is explicitly false.',
        'memory.swap.max was max. Zero observed swap usage is not a swap limit guarantee.',
    ],
    'new_test_or_service_execution_by_reviewer': False,
    'Main_actions_by_reviewer': 0,
    'Hepta_calls_by_reviewer': 0,
}
payload = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
with (OUT / 'report.json').open('xb') as stream:
    stream.write(payload)
print(json.dumps({'state': report['state'], 'report': pin(OUT / 'report.json'), 'builder_elf': result['builder_elf'], 'reviewed_targeted_tests': 24, 'registered': 197}))
