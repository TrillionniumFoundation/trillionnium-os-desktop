#!/usr/bin/env python3
"""Narrow local controls for actual-A prerequisites and owned no-replace I/O."""
import ast
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
STAGE_A = HERE.parent / 'stage-a-candidate-r1'


def load(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


def require(value, code):
    if not value:
        raise AssertionError(code)


def rejected(call):
    try:
        call()
    except (RuntimeError, AssertionError, OSError) as error:
        return error
    raise AssertionError('EXPECTED_REJECTION_MISSING')


def main():
    worker = load(HERE / 'commit_stage_b_once.py', 'local_stage_b_definitions_only')
    a = load(STAGE_A / 'runtime_stage_a_once.py', 'local_actually_passed_stage_a_definitions_only')
    host = load(PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/verify_partial_case_host.py',
                'local_frozen_host_gate_only')
    partial = load(PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/partial_case_core.py',
                   'local_frozen_protocol_only')
    base = load(PROJECT / 'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py', 'local_owned_exit_gate_only')
    recorder = load(PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/recorder.py',
                    'local_original_consumer_file_reader_only')
    before = host.census(); cases = []
    raw = (HERE / 'stage-a.stdout.original.jsonl').read_bytes()
    term_raw = (HERE / 'stage-a.terminal.original.json').read_bytes()
    require(len(raw) == 15030 and worker.sha(raw) == worker.STAGE_A_STDOUT['sha256'] and
            len(term_raw) == 733 and worker.sha(term_raw) == worker.STAGE_A_TERMINAL['sha256'],
            'ACTUAL_A_INPUT_PINS')
    terminal = json.loads(term_raw)
    outer, child = worker.validate_actual_stage_a(raw, terminal, host, partial, base, a)
    require(outer['child_lifecycle']['child_pid'] == 2349898 and child['ok'], 'ACTUAL_A_RESULT_NOT_SYNTHETIC')
    for key, value in (('state', 'failed'), ('exit_code', 1), ('output_complete', False),
                       ('output_durable', False), ('timed_out', True), ('job_id', 'wrong-job')):
        changed = copy.deepcopy(terminal); changed[key] = value
        rejected(lambda: worker.validate_actual_stage_a(raw, changed, host, partial, base, a))
    cases.append('actual_A_controller_child_and_source_gate_accepts_original_and_rejects_failed_or_incomplete_terminal')

    stage = json.loads(raw.splitlines()[0])
    for mutation in ('pidfd', 'signal', 'old_unknown', 'source'):
        changed = copy.deepcopy(outer)
        if mutation == 'pidfd': changed['child_lifecycle']['pidfd_exit_observed'] = False
        elif mutation == 'signal': changed['child_lifecycle']['owned_child_sigkill_count'] = 1
        elif mutation == 'old_unknown': changed['original_case_outcome_unknown'] = False
        else: changed['source']['sha256'] = '0' * 64
        changed_raw = json.dumps(stage, sort_keys=True).encode() + b'\n' + worker.canonical(changed) + b'\n'
        fake_term = copy.deepcopy(terminal)
        fake_term['log_bytes']['stdout'] = {'seen': len(changed_raw), 'stored': len(changed_raw)}
        rejected(lambda: worker.validate_actual_stage_a(changed_raw, fake_term, host, partial, base, a))
    cases.append('explicit_local_corruptions_of_A_pidfd_signal_unknown_or_source_never_qualify')

    actual_path = PROJECT / 'successor_qa/inspect_after_search_rejection_r1/actual/adapter.stdout.original.json'
    actual_raw = actual_path.read_bytes()
    require(len(actual_raw) == 5752 and worker.sha(actual_raw) ==
            'c4d26149b4e68b686dd84a5fe8c69c73a45b93f0e9ea2e37541b0ad8ab6f8162', 'ACTUAL_OBSERVER_VALUES_PIN')
    actual = json.loads(actual_raw)
    class LocalSessionFixture:
        def __init__(self, token=None): self.token = token; self.calls = []
        def installed(self): self.calls.append('installed'); return copy.deepcopy(actual['installed_before'])
        def task(self): self.calls.append('task'); return copy.deepcopy(actual['owned_task'])
        def foreground(self):
            self.calls.append('foreground'); value = copy.deepcopy(actual['foreground_before'])
            if self.token is not None: value['window_token'] = self.token
            return value
    good = LocalSessionFixture()
    args = (actual['installed_before'], actual['owned_task'], actual['foreground_before'])
    worker.two_original_rounds(good, *args)
    require(good.calls == ['installed', 'task', 'foreground'] * 2, 'SAME_ORIGINAL_TWO_ROUNDS')
    rejected(lambda: worker.two_original_rounds(LocalSessionFixture('changed-current-window'), *args))
    cases.append('unchanged_full_foreground_equality_rejects_changed_window_no_resume_or_fallback')

    with tempfile.TemporaryDirectory(prefix='p4-stage-b-own-io-') as directory:
        root = Path(directory); path = root / 'one.json'; original = b'{"local_owned_commit_control":true}\n'
        outcome = worker.commit_envelope(path, original, '0' * 32)
        require(path.read_bytes() == original and path.stat().st_nlink == 1 and outcome['sha256'] == worker.sha(original),
                'OWNED_REAL_NO_REPLACE_COMMIT')
        existing = rejected(lambda: worker.commit_envelope(path, b'replacement prohibited', '1' * 32))
        require(isinstance(existing, FileExistsError) and existing.publication_attempted is True and
                path.read_bytes() == original, 'EXISTING_DESTINATION_WAS_NOT_PRESERVED')
        class FailWrite:
            def __getattr__(self, key): return getattr(os, key)
            def write(self, fd, raw): raise OSError(errno.EIO, 'local injected write failure')
        failing = types.FunctionType(worker.commit_envelope.__code__, {**worker.__dict__, 'os': FailWrite()})
        failed_path = root / 'before-link.json'
        error = rejected(lambda: failing(failed_path, original, '2' * 32))
        require(error.publication_attempted is False and not failed_path.exists(), 'WRITE_FAILURE_MUST_NOT_PUBLISH')
        class FailUnlink:
            def __getattr__(self, key): return getattr(os, key)
            def unlink(self, *args, **kwargs): raise OSError(errno.EIO, 'local injected unlink failure')
        linked = types.FunctionType(worker.commit_envelope.__code__, {**worker.__dict__, 'os': FailUnlink()})
        linked_path = root / 'after-link.json'
        error = rejected(lambda: linked(linked_path, original, '3' * 32))
        require(error.publication_attempted is True and linked_path.exists() and linked_path.stat().st_nlink == 2,
                'POSTLINK_FAILURE_MUST_REMAIN_EXPLICIT_UNKNOWN_WITH_TWO_LINKS')
        unsafe = rejected(lambda: recorder.read_regular(linked_path))
        require(str(unsafe) == 'UNSAFE_INPUT_FILE', 'FROZEN_CONSUMER_MUST_REJECT_TWO_LINK_INTERMEDIATE')
    cases.append('real_UID1000_owned_temp_commit_no_overwrite_prelink_failure_and_postlink_nlink2_consumer_rejection')

    source = (HERE / 'commit_stage_b_once.py').read_bytes(); tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    require(sum(isinstance(node.func, ast.Name) and node.func.id == 'commit_envelope' for node in calls) == 1,
            'ONE_EXPLICIT_COMMIT_CALL_ONLY')
    require(not any(isinstance(node.func, ast.Attribute) and node.func.attr in
            ('reconcile', 'instrument', 'sequence', 'execve', 'system', 'Popen') for node in calls),
            'NO_UI_OR_ALTERNATE_LIFECYCLE_CHANNEL')
    request_raw = (HERE / 'request.json').read_bytes()
    require(worker.request_value(request_raw, partial) == worker.FIXED_REQUEST, 'ACTUAL_FIXED_B_REQUEST')
    changed = copy.deepcopy(worker.FIXED_REQUEST); changed['completed_stage_A_candidate']['sha256'] = '0' * 64
    rejected(lambda: worker.request_value(worker.canonical(changed) + b'\n', partial))
    cases.append('closed_B_request_binds_actual_A_candidate_and_has_no_UI_or_old_reconcile_call')
    after = host.census(); require(after == before, 'LOCAL_WHOLE_PROCESS_FD_IDENTITY')
    print(json.dumps({'schema': 'pocket4-stage-b-minimal-local-controls-v1', 'ok': True,
        'case_count': len(cases), 'cases': [{'name': name, 'passed': True} for name in cases],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'Main_or_remote_actions': 0,
        'real_runtime_commit_executed': False, 'original_flow_or_receipt_modified': False,
        'local_session_fixture_is_not_Main_observation': True,
        'IO_controls_used_only_actual_owned_local_temporary_directory': True,
        'whole_process_fd_identities_unchanged': True, 'before': before, 'after': after,
        'source_sha256': hashlib.sha256(source).hexdigest()}, sort_keys=True))


if __name__ == '__main__':
    main()
