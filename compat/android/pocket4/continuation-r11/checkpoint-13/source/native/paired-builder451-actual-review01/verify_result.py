#!/usr/bin/env python3
"""Independently validate the complete, root-collected compile02 receipt.

This reads local evidence only. It does not rerun compilation, tests or tools,
and it does not turn the five test images into a signed production APEX.
"""
from pathlib import Path
import hashlib
import json

BASE = Path('/workspace/scratch/94990735b266')
HERE = Path(__file__).resolve().parent
RAW = BASE / 'root-recovery-20261104-02/evidence/paired-builder451-compile02/result.json'
FREEZE = BASE / 'native-recovery-20261105-02/paired-builder451-compile02'
EXPECTED_SHA = '8c72e771c9ed5bd440b36aa8c7c3379b31ce8acccdc2b222fadad9e64cb28096'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    raw = RAW.read_bytes()
    assert len(raw) == 129787 and sha(raw) == EXPECTED_SHA
    data = json.loads(raw)
    assert data['state'] == 'PASS'
    assert data['copied_manifest']['sha256'] == sha((FREEZE / 'expected-builder451-manifest.json').read_bytes())
    assert data['original_manifest']['sha256'] == sha((FREEZE / 'compiled-parent450-manifest.json').read_bytes())
    for key in ('original_source_unchanged_after', 'copied_source_unchanged_after', 'cargo_configs_unchanged_after'):
        assert data[key] is True
    assert data['dependency_changes'] == data['tool_changes'] == []
    assert data['source_delta']['unchanged_existing'] == 447
    assert len(data['source_delta']['changed_existing']) == 3
    assert data['source_delta']['added'] == ['tools/droidloom-update/src/native_generation.rs']
    assert data['source_delta']['engine_source_files_changed'] == 0
    for key, name in (
        ('actual_parent450_compile_authority', 'compiled-parent450-result.json'),
        ('actual_Go_comparison_gate', 'go-control-result.json'),
        ('actual_image_tools_authority', 'image-tools-result.json'),
        ('actual_registry_archive_authority', 'registry-result.json'),
        ('actual_selected_dependency_authority', 'selection-result.json'),
    ):
        content = (FREEZE / name).read_bytes()
        assert data[key]['sha256'] == sha(content) and data[key]['bytes'] == len(content)
    assert data['actual_toolchain']['repository_version'] == '1.93.0'
    assert data['actual_toolchain']['selection_installs_or_updates'] is False
    assert data['actual_toolchain']['global_stable_1_95_not_used'] is True
    assert len(data['actual_build_packages']) == 49
    assert data['actual_build_packages'] == data['actual_test_compile_packages']
    assert sum(x.startswith('registry+') for x in data['actual_build_packages']) == 45
    assert data['build_environment']['CARGO_NET_OFFLINE'] == 'true'
    assert data['build_environment']['CARGO_BUILD_JOBS'] == '1'
    assert data['network_downloads_permitted'] is False

    commands = data['commands']
    assert len(commands) == 55
    labels = [item['label'] for item in commands]
    assert len(labels) == len(set(labels))
    assert all(item['returncode'] == 0 and item['timed_out'] is False for item in commands)
    by_name = {item['label']: item for item in commands}
    for label in ('builder-compile', 'builder-test-compile'):
        assert '--offline' in by_name[label]['argv'] and '--locked' in by_name[label]['argv']
    assert data['actual_registered_test_count'] == 195
    assert data['actual_libtest_logfile_support'] is True
    names = data['expected_test_names']
    assert len(names) == len(set(names)) == 22
    assert len(data['focused_result_gates']) == 22
    checked_tests = []
    for index, (name, gate) in enumerate(zip(names, data['focused_result_gates'])):
        command = by_name['projection-test-' + str(index)]
        argv = command['argv']
        assert argv[argv.index('--exact') + 1] == name
        assert '--test-threads=1' in argv and '--nocapture' in argv
        independent = command['independent_libtest_result']
        expected = ('ok ' + name + '\n').encode()
        assert independent['sha256'] == sha(expected) and independent['bytes'] == len(expected)
        assert argv[argv.index('--logfile') + 1] == independent['path']
        assert gate == {
            'exact_name': name, 'expected_stdout_runs': 2 if index == 20 else 1,
            'filtered_out_per_run': 194, 'outer_results': 1,
            'registered_tests': 195, 'summary_and_independent_result_agree': True,
        }
        checked_tests.append({'name': name, 'independent_result_sha256': independent['sha256'],
                              'stdout_sha256': command['stdout']['sha256'],
                              'expected_stdout_runs': gate['expected_stdout_runs']})
    assert data['focused_tests_passed'] == 22
    assert data['original_projection_tests_passed'] == 7
    assert data['pairing_tests_passed'] == 15 and data['real_image_test_count'] == 5
    resources = data['owned_resource_gate']
    assert resources['pass'] is True and resources['resource_settings_changed'] is False
    before, after = resources['before'], resources['after']
    for field in ('path', 'membership', 'directory_identity', 'controller_pid'):
        assert before[field] == after[field]
    assert before['fields']['cpu.max'] == after['fields']['cpu.max'] == '100000 100000'
    assert before['fields']['memory.max'] == after['fields']['memory.max'] == '1073741824'
    assert all(value == 0 for value in resources['memory_events_delta'].values())
    assert data['owned_memory_peak'] == resources['memory_peak'] == 946839552
    assert data['owned_memory_swap_peak'] == resources['memory_swap_peak'] == 0
    assert data['cleanup'] == {'errors': [], 'forced_cleanup': False,
                               'initial_owned_children': [], 'reaped': [], 'remaining': []}
    assert data['observed_signals'] == []
    assert data['builder_elf']['bytes'] == 32654784
    assert data['builder_elf']['sha256'] == '34c04271f1a3095cedb0b57eece7749958622754a864202b17a54abb174e0e3e'
    assert data['Main_actions'] == data['install_actions'] == 0
    assert data['Main_identity_observed'] is False
    assert data['platform_APEX_signature_validated'] is False
    assert data['actual_enabled_ART_lifecycle_validated'] is False
    report = {
        'schema': 1, 'state': 'PASS_LOCAL_REVIEW_OF_COMPLETE_ACTUAL_RECEIPT',
        'authority': {'path': str(RAW), 'bytes': len(raw), 'sha256': EXPECTED_SHA},
        'source_manifest': data['copied_manifest'], 'builder_elf': data['builder_elf'],
        'source_delta': data['source_delta'], 'commands_returned_zero': 55,
        'registered_tests': 195, 'focused_tests': checked_tests,
        'original_projection_tests_passed': 7, 'pairing_tests_passed': 15,
        'real_test_image_controls': 5, 'owned_resource_gate': resources,
        'cleanup': data['cleanup'],
        'source_tools_dependencies_configs_unchanged_according_to_complete_receipt': True,
        'independent_remote_tool_or_ELF_reread_performed': False,
        'actual_commands_rerun_by_this_review': 0,
        'Main_actions': 0, 'Main_identity_observed': False,
        'platform_APEX_signature_validated': False,
        'actual_enabled_ART_lifecycle_validated': False,
        'next03_ART_sources_compiled_by_this_builder': False,
        'production_ready': False,
        'scope': 'Independent source/authority/result consistency review of the complete actual 451 compile02 receipt; not an ART image or runtime qualification.',
        'preserved_failures': ['451 compile01 noisy external stdout interrupted contiguous libtest name line'],
    }
    target = HERE / 'report.json'
    encoded = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    with target.open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'state': report['state'], 'file': str(target), 'bytes': len(encoded), 'sha256': sha(encoded)}))


if __name__ == '__main__':
    main()
