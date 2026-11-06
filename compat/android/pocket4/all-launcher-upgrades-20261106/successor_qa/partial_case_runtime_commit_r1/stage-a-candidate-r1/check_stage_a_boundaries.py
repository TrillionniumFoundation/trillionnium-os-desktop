#!/usr/bin/env python3
"""Small local protocol/owned-file controls, never a Main qualification."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def load(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


def require(value, code):
    if not value:
        raise AssertionError(code)


def reject(function):
    try:
        function()
    except (RuntimeError, AssertionError, FileExistsError):
        return
    raise AssertionError('EXPECTED_REJECTION_DID_NOT_OCCUR')


def main():
    worker = load(HERE / 'runtime_stage_a_once.py', 'local_stage_a_definitions_only')
    host = load(PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/verify_partial_case_host.py',
                'local_actual_host_definitions_only')
    partial = load(PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/partial_case_core.py',
                   'local_frozen_partial_definitions_only')
    recorder = load(PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/recorder.py',
                    'local_original_write_new_only')
    ns = load(PROJECT / 'successor_qa/owned_postcondition_reconciler_r1/candidate-r2/test_namespace_identity.py',
              'local_existing_synthetic_identity_fixture')
    base = load(PROJECT / 'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py',
                'local_original_normal_exit_gate_only')
    baseline = host.census()
    cases = []
    actual_raw = (PROJECT / 'successor_qa/inspect_after_search_rejection_r1/actual/adapter.stdout.original.json').read_bytes()
    require(len(actual_raw) == 5752 and hashlib.sha256(actual_raw).hexdigest() ==
            'c4d26149b4e68b686dd84a5fe8c69c73a45b93f0e9ea2e37541b0ad8ab6f8162', 'ACTUAL_OBSERVER_FIXTURE_PIN')
    actual = json.loads(actual_raw)
    rows = {worker.HOST_STDOUT['path']: (HERE / 'host.stdout.original.jsonl').read_bytes(),
            worker.HOST_TERMINAL['path']: (HERE / 'host.terminal.original.json').read_bytes()}
    class FixedPublicInputs:
        @staticmethod
        def pinned(pin):
            raw = rows[pin['path']]
            require(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'LOCAL_ACTUAL_PUBLIC_PIN')
            return raw
    gate = worker.actual_host_gate(FixedPublicInputs(), host, partial)
    require(gate['job_id'] == '1a1b2b679c3-fc05-7f6e', 'ACTUAL_HOST_JOB_NOT_RELABELED')
    terminal = json.loads(rows[worker.HOST_TERMINAL['path']])
    for key, value in (('state', 'failed'), ('exit_code', 1), ('output_complete', False),
                       ('timed_out', True), ('job_id', 'wrong-job')):
        changed = copy.deepcopy(terminal); changed[key] = value
        reject(lambda: host.original_terminal(changed, worker.HOST_JOB, worker.HOST_STDOUT['bytes']))
    cases.append('actual_host_stdout_terminal_pins_and_incomplete_or_failed_terminal_rejected')

    class ExplicitLocalSessionFixture:
        def __init__(self, changed=None):
            self.calls = []; self.changed = changed
        def installed(self):
            self.calls.append('installed')
            value = copy.deepcopy(actual['installed_before'])
            if self.changed == 'helper_uid': value['uid'] += 1
            if self.changed == 'helper_APK': value['apk_sha256'] = '0' * 64
            return value
        def task(self):
            self.calls.append('task')
            value = copy.deepcopy(actual['owned_task'])
            if self.changed == 'task': value['task'] += 1
            return value
        def foreground(self):
            self.calls.append('foreground')
            value = copy.deepcopy(actual['foreground_before'])
            if self.changed in ('package', 'activity', 'window_token', 'runtime_epoch_sha256'):
                value[self.changed] = 'EXPLICIT_LOCAL_CHANGED_FIXTURE'
            return value
    arguments = (actual['installed_before'], actual['owned_task'], actual['foreground_before'])
    valid = ExplicitLocalSessionFixture()
    returned = worker.two_original_rounds(valid, *arguments)
    require(len(returned) == 2 and valid.calls == ['installed', 'task', 'foreground'] * 2,
            'EXACT_TWO_ROUND_ORDER')
    for difference in ('helper_uid', 'helper_APK', 'task', 'package', 'activity', 'window_token', 'runtime_epoch_sha256'):
        reject(lambda difference=difference: worker.two_original_rounds(ExplicitLocalSessionFixture(difference), *arguments))
    cases.append('actual_observer_values_used_only_as_local_fixture_full_scope_and_helper_task_changes_rejected')

    original, later = ns.fixture()
    result = ns.core.compare_held_bindings(original, later)
    require(result['all_other_binding_fields_exactly_equal'] is True and
            len(result['namespace_mtime_differences']) == 5, 'EXISTING_NSFS_ONLY_CONTRACT')
    for path in ('/target/namespaces/pid/inode', '/target/namespaces/pid/device',
                 '/target/init/start', '/classpath/files/0/mtime_ns'):
        changed = copy.deepcopy(later); owner, key = ns.at(changed, path)
        owner[key] = 'DIFFERENT_START' if type(owner[key]) is str else owner[key] + 1
        reject(lambda: ns.core.compare_held_bindings(original, changed))
    require(original == ns.fixture()[0] and later == ns.fixture()[1], 'FIXTURES_NOT_REWRITTEN')
    cases.append('same_frozen_nsfs_mtime_only_projection_rejects_inode_device_process_start_and_file_mtime_change')

    real_child = json.loads((PROJECT / 'successor_qa/inspect_after_search_rejection_r1/actual/stdout.original.json').read_bytes())['child_lifecycle']
    base.require_owned_exit(real_child, b'')
    for key, value in (('returncode', 1), ('pidfd_exit_observed', False), ('pidfd_closed', False),
                       ('parent_descriptors_restored', False), ('timeout', True), ('owned_child_sigkill_count', 1)):
        changed = copy.deepcopy(real_child); changed[key] = value
        reject(lambda: base.require_owned_exit(changed, b''))
    reject(lambda: base.require_owned_exit(real_child, b'not empty'))
    cases.append('actual_normal_owned_child_gate_rejects_nonzero_timeout_signal_unclosed_fd_and_stderr')

    with tempfile.TemporaryDirectory(prefix='p4-stage-a-local-own-') as name:
        target = Path(name) / 'candidate.json'
        recorder.write_new(target, b'{"local_owned_IO_control":true}\n')
        before = target.read_bytes()
        reject(lambda: recorder.write_new(target, b'forbidden replacement'))
        require(target.read_bytes() == before, 'ORIGINAL_O_EXCL_WRITE_DID_NOT_PRESERVE_FILE')
    cases.append('actual_UID_local_temp_original_O_EXCL_write_preserves_existing_bytes_and_closes_FDs')

    source = (HERE / 'runtime_stage_a_once.py').read_bytes()
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    require(not any(isinstance(node.func, ast.Attribute) and node.func.attr in
            ('reconcile', 'instrument', 'sequence', 'execve', 'system', 'Popen') for node in calls),
            'NO_ALTERNATE_UI_OR_COMMIT_ENTRY_IN_STAGE_A')
    require(not any(isinstance(node.func, ast.Name) and node.func.id == 'commit_envelope' for node in calls),
            'STAGE_B_NOT_IMPLEMENTED')
    require(worker.request_value((HERE / 'request.json').read_bytes(), partial) == worker.FIXED_REQUEST,
            'ACTUAL_STAGE_A_REQUEST')
    changed = copy.deepcopy(worker.FIXED_REQUEST); changed['reconciliation_published'] = True
    reject(lambda: worker.request_value(worker.canonical(changed) + b'\n', partial))
    cases.append('closed_stage_A_request_and_no_new_instrumentation_reconcile_or_commit_call')
    after = host.census()
    require(after == baseline, 'LOCAL_WHOLE_PROCESS_FD_IDENTITY_CHANGED')
    report = {'schema': 'pocket4-stage-a-minimal-local-controls-v1', 'ok': True, 'case_count': len(cases),
        'cases': [{'name': name, 'passed': True} for name in cases],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'Main_or_remote_actions': 0,
        'real_runtime_candidate_executed': False, 'stage_B_created_or_executed': False,
        'session_rounds_were_explicit_local_fixture_not_Main_observation': True,
        'namespace_identity_fixture_synthetic_with_five_actual_timestamp_pairs': True,
        'whole_process_fd_identities_unchanged': True, 'before': baseline, 'after': after,
        'source_sha256': hashlib.sha256(source).hexdigest()}
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
