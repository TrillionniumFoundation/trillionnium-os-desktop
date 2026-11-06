"""Independent retained-record review; no target execution or module imports."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'android-owner17-host-ordinary-actual-review01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner17-host-ordinary01/run-result.json'
COMPILE = ROOT / 'root-recovery-20261104-02/evidence/owner17-host-mode-compile01/compile-result.json'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def main():
    assert not OUT.exists()
    raw, compile_raw = ACTUAL.read_bytes(), COMPILE.read_bytes()
    assert len(raw) == 37889 and sha(raw) == 'b6a1349a8b0d147d6dfe5b0defcef51ce4b3d478325d6bb104e02229c0a2c14a'
    assert len(compile_raw) == 50235 and sha(compile_raw) == '86c8078472a4e6ecc271ccb39e86cf8aba24bc7a4828dcabfdf3d3f38bbd5466'
    value, compiled = json.loads(raw), json.loads(compile_raw)
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    check('actual successful ordinary-only receipt', value['success'] is True and value['ordinary_controls_only'] is True and value.get('error') is None and value['revision'] == 'producer17-owned-bootstrap-modes01')
    check('actual compile pin', value['external_compile_sha256'] == sha(compile_raw))
    check('all33 inputs and complete inventory retained', value['inputs_before'] == value['inputs_after'] == compiled['inputs_before'] == compiled['inputs_after'] and len(value['inputs_before']) == 33 and value['all_source_inventory_before_sha256'] == value['all_source_inventory_after_sha256'] == compiled['all_source_inventory_after_sha256'])
    check('no higher qualification or compilation claimed', all(value[k] is False for k in ('cargo_invoked', 'full_owner_runtime_qualified', 'real_broker_generation_qualified', 'android_runtime_started', 'barrier_constructor_executed', 'pressure_or_namespace_effects_requested', 'installed_files_changed', 'main_fence_claimed')))
    targets = ['lifecycle_bootstrap::tests::producer05_three_second_retirement_is_rejected_before_transport', 'lifecycle_bootstrap::tests::shared_retirement_bound_sends_exact_request_and_receives_terminal_ack']
    check('both original public retirement controls', value['targeted_public_retirement_controls'] == [{'passed': 1, 'failed': 0, 'ignored': 0, 'measured': 0, 'filtered_out': 38, 'name': name} for name in targets])
    tests = {row['target_name']: row for row in compiled['compiled_test_artifacts']}
    artifacts = [tests['droidloom_pressure_relay']] * 3 + [tests['droidloom_supervisor']]
    artifacts += [compiled['artifacts']['owned-ipc-controls']] * 2 + [compiled['artifacts']['droidloom-supervisor']]
    argv = [['--exact', name, '--test-threads=1', '--nocapture'] for name in targets]
    argv += [['--test-threads=1'], ['--test-threads=1'], [], ['--worker-context-control'], ['relay-entry-abi']]
    commands = value['commands']
    check('seven commands exact cardinality', len(commands) == len(artifacts) == len(argv) == 7)
    check('unique direct child PIDs', len({r['exact_child_pid'] for r in commands}) == 7)
    for index, (command, artifact, suffix) in enumerate(zip(commands, artifacts, argv)):
        check('command%d held actual ELF argv and exit' % index,
            command['actual_held_elf'] == {k: artifact[k] for k in ('path', 'bytes', 'sha256', 'device', 'inode', 'mode')} and
            re.fullmatch('/proc/self/fd/[0-9]+', command['argv'][0]) is not None and command['argv'][1:] == suffix and
            command['cwd'] == compiled['candidate'] and command['returncode'] == 0 and command['timed_out'] is False and command['exact_child_pid'] > 0)
        check('command%d stderr fully empty' % index, command['stderr_pin']['bytes'] == 0 and command['stderr_pin']['sha256'] == sha(b'') and command['stderr_excerpt'] == '')
        if command['stdout_pin']['bytes'] <= 4096:
            body = command['stdout_excerpt'].encode()
            check('command%d complete stdout excerpt hash' % index, len(body) == command['stdout_pin']['bytes'] and sha(body) == command['stdout_pin']['sha256'])
    check('actual39 and139 no filtered or ignored cases', value['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 139} and value['rust_test_binary_counts'] == {'droidloom_pressure_relay:lib': 39, 'droidloom_supervisor:lib': 139} and all(('test result: ok. %d passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;' % count) in commands[index]['stdout_excerpt'] for index, count in ((2, 39), (3, 139))))
    new_tests = ['guest_search_mode_changes_only_the_held_owned_directory', 'guest_search_mode_preserves_failed_fchmod_errno', 'guest_search_mode_rejects_replaced_or_symlink_name_before_chmod']
    for name in new_tests:
        check('actual new test ' + name, commands[3]['stdout_excerpt'].count('test relay_lifecycle::entry::tests::' + name + ' ... ok\n') == 1)
    check('actual seven IPC and leader context exact summaries', value['ordinary_ipc_passed'] == 7 and value['worker_context_passed'] is True and len(re.findall('^PASS ', commands[4]['stdout_excerpt'], re.M)) == 7 and commands[4]['stdout_excerpt'].endswith('RESULT PASS mode=host-negative-controls\n') and commands[5]['stdout_excerpt'].endswith('RESULT PASS mode=worker-context-without-namespace-or-pressure-effects\n'))
    check('actual compiled ABI3 unchanged', value['actual_compiled_entry_abi_passed'] is True and commands[6]['stdout_excerpt'] == 'droidloom-relay-entry-v3\n')
    h = value['resource_health']; before, after = h['before'], h['after']
    check('finite own resource gate', h['held_own_cgroup_gate_passed'] is True and h['cgroup_files_written'] is False and h['expected_cpu_count'] == 1 and h['expected_memory_max'] == 536870912)
    check('own cgroup identity and limits unchanged', all(before[k] == after[k] for k in ('membership', 'cgroup_identity', 'mount_identity', 'namespaces', 'limits', 'pid')) and after['limits']['memory.max'] == 536870912 and after['limits']['cpu.max'] == [100000, 100000])
    check('actual peak and events', after['memory_peak'] == 58748928 and after['memory_swap_current'] == after['memory_swap_peak'] == 0 and all(v == 0 for v in h['memory_event_delta'].values()))
    terminal_raw = ACTUAL.with_name('stdout.log').read_bytes()
    check('actual original stdout hash', len(terminal_raw) == 392 and sha(terminal_raw) == '3db4f3e4ddf3927a77633ce40d21549dbc2d44fc45f2b7301dae755110d6f141')
    terminal = json.loads(terminal_raw)
    check('actual original stdout binds report', terminal['success'] is True and terminal['bytes'] == len(raw) and terminal['sha256'] == sha(raw) and terminal['report'].endswith('/ordinary-run-01/run-result.json') and terminal['error'] is None)
    report = {'schema': 1, 'result': 'ACTUAL_ORDINARY_CONTROLS_PASS_OWNER17_RUNTIME_PENDING', 'ordinary_receipt': {'path': str(ACTUAL), 'bytes': len(raw), 'sha256': sha(raw)}, 'compile_receipt': {'path': str(COMPILE), 'bytes': len(compile_raw), 'sha256': sha(compile_raw)}, 'checks': checks, 'check_count': len(checks), 'actual_tests': value['rust_tests_passed'], 'new_mode_tests_actual_named_pass': new_tests, 'new_test_excerpt_source': {'bytes': commands[3]['stdout_pin']['bytes'], 'sha256': commands[3]['stdout_pin']['sha256'], 'report_contains_final4096_bytes_only': True}, 'exact_retirement_tests': targets, 'IPC_controls': 7, 'worker_context': True, 'entry_ABI': 3, 'direct_children': [{'pid': c['exact_child_pid'], 'returncode': c['returncode'], 'timed_out': c['timed_out']} for c in commands], 'own_resource': {'memory_peak': 58748928, 'memory_max': 536870912, 'observed_swap_current_and_peak_zero': True, 'memory_swap_max': after['limits']['memory.swap.max'], 'all_event_deltas_zero': True}, 'limits': ['Actual ordinary invokes only seven bound compiled ELFs; Cargo and Rust tools are not invoked here.', 'Children are waited by the exact frozen runner; no new process scan or independent remote rerun.', 'New mode controls are ordinary owned FD tests, not a privileged synthetic Android mount or an LMKD execution proof.', 'The complete supervisor stdout is pinned by actual report; this local review reads its retained final4096 excerpt, which includes all three new named test PASS lines.', 'Original Owner16 failure and HWS critical abort remain unresolved by these host tests.'], 'full_owner_runtime_qualified': False, 'LMKD_exec_fixed_on_Android': False, 'HWS_health_qualified': False, 'main_changed_or_guard_rebound': False}
    OUT.mkdir()
    body = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    files = {'report.json': body, 'check.py': Path(__file__).read_bytes()}
    files['SOURCE_PINS.json'] = (json.dumps({n: {'bytes': len(b), 'sha256': sha(b)} for n, b in files.items()}, indent=2, sort_keys=True) + '\n').encode()
    for name, value in files.items(): (OUT / name).open('xb').write(value)
    print(json.dumps({'root': str(OUT), 'checks': len(checks), 'files': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in files.items()}}))


if __name__ == '__main__':
    main()
