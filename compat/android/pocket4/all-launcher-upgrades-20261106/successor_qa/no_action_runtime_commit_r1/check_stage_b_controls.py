#!/usr/bin/env python3
"""Local-only actual-A gate and frozen-consumer compatibility controls."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
A = HERE / 'stage-a-candidate-r1'
B = HERE / 'stage-b-candidate-r1'


def load(path, name):
    obj = types.ModuleType(name); obj.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), obj.__dict__)
    return obj


def need(value, code):
    if not value:
        raise AssertionError(code)


def rejected(call):
    try:
        call()
    except (RuntimeError, AssertionError, OSError):
        return
    raise AssertionError('EXPECTED_REFUSAL_MISSING')


def main():
    helper = load(HERE / 'check_history_controls.py', 'local_control_helpers_only')
    before = helper.census()
    worker = load(B / 'commit_stage_b_once.py', 'new_no_action_stage_b_definitions_only')
    source = (B / 'commit_stage_b_once.py').read_bytes(); helper.static_globals(source)
    stage_a = load(A / 'runtime_stage_a_once.py', 'actually_completed_no_action_stage_a_definitions')
    partial = load(A / 'no_action_core.py', 'actual_no_action_pure_history_contract')
    reader = load(A / 'read_failed_search_click.frozen.py', 'actual_frozen_failure_reader')
    base = load(PROJECT / 'successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py', 'frozen_normal_owned_exit_gate')
    recorder = load(PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/recorder.py', 'frozen_consumer_only')
    raw = (B / 'stage-a.stdout.original.jsonl').read_bytes()
    terminal = partial.document((B / 'stage-a.terminal.original.json').read_bytes())
    outer, child = worker.validate_actual_stage_a(raw, terminal, reader, partial, base, stage_a)
    need(outer['child_lifecycle']['child_pid'] == 2531797 and child['ok'] is True,
         'NEW_ACTUAL_A_NOT_SYNTHETIC_OR_PRIOR_PARTIAL_A')
    cases = []
    for field, value in [('state', 'failed'), ('exit_code', 1), ('output_durable', False), ('timed_out', True)]:
        changed = copy.deepcopy(terminal); changed[field] = value
        rejected(lambda: worker.validate_actual_stage_a(raw, changed, reader, partial, base, stage_a))
    stage = partial.document(raw.splitlines()[0])
    for field, value in [('pidfd_exit_observed', False), ('owned_child_sigkill_count', 1)]:
        changed = copy.deepcopy(outer); changed['child_lifecycle'][field] = value
        bad = json.dumps(stage, sort_keys=True).encode() + b'\n' + worker.canonical(changed) + b'\n'
        term = copy.deepcopy(terminal); term['log_bytes']['stdout'] = {'seen': len(bad), 'stored': len(bad)}
        rejected(lambda: worker.validate_actual_stage_a(bad, term, reader, partial, base, stage_a))
    cases.append({'name': 'actual_new_A_complete_joint_and_incomplete_or_abnormal_refusal', 'passed': True,
                  'actual_A_job': '1a1b33331ac-fc05-8102'})

    # Structural fixtures only: these names/digests do not assert a live proof.
    closure = {name: '0' * 64 for name in ('scope.json', 'launch-scope.json',
        'qa-' + worker.CASE_STEP + '.case.json', 'baseline.json', 'baseline-qualification.json')}
    for step, count in [(worker.CASE_STEP, 90), (worker.STAGE_A_STEP, 57), (worker.STEP, 59)]:
        closure.update({'steps/' + step + '/local-fixture-%03d' % i: '0' * 64 for i in range(count)})
    worker.published_member_set(closure)
    missing = dict(closure); del missing['steps/' + worker.CASE_STEP + '/local-fixture-000']
    rejected(lambda: worker.published_member_set(missing))
    diverted = dict(closure)
    del diverted['steps/' + worker.CASE_STEP + '/local-fixture-000']
    diverted['steps/unobserved-or-different-case/local-fixture-000'] = '0' * 64
    rejected(lambda: worker.published_member_set(diverted))
    cases.append({'name': 'exact_211_structural_closure_missing_or_other_step_refused', 'passed': True,
                  'fixture_is_not_runtime_evidence': True})

    with tempfile.TemporaryDirectory(prefix='p4-no-action-consumer-owned-') as folder:
        root = Path(folder); (root / 'reconciliations').mkdir(mode=0o700)
        scope_raw = b'{"epoch_sha256":"local-only-not-Main"}\n'
        (root / 'scope.json').write_bytes(scope_raw)
        body = b'local consumer contract control, not a runtime proof\n'
        (root / 'local-evidence.txt').write_bytes(body)
        envelope = {'schema': 'pocket4-flow-explicit-reconciliation-v1', 'unknown_step': worker.CASE_STEP,
            'epoch_sha256': 'local-only-not-Main', 'scope_sha256': worker.sha(scope_raw),
            'original_action_outcome': 'unknown_retained', 'allows_new_decisions_only': True,
            'evidence_sha256': {'local-evidence.txt': worker.sha(body)},
            'observation_step': None, 'postcondition': None,
            'new_owned_qa_producer': {'schema': 'local-non-Main-contract-fixture', 'actual_Main_proof': False}}
        dest = root / 'reconciliations' / (worker.CASE_STEP + '.json')
        published = worker.commit_envelope(dest, worker.canonical(envelope) + b'\n', 'c' * 32)
        fixture = object.__new__(recorder.Flow)
        fixture.root = root; fixture.scope = {'epoch_sha256': 'local-only-not-Main'}
        need(recorder.Flow.reconciled(fixture, worker.CASE_STEP) is True, 'FROZEN_COMPATIBILITY_FIELDS_ACCEPT_NULL_OBSERVER')
        original = dest.read_bytes()
        rejected(lambda: worker.commit_envelope(dest, b'overwrite forbidden', 'd' * 32))
        need(dest.read_bytes() == original and dest.stat().st_nlink == 1, 'NO_REPLACEMENT_OF_EXISTING_LOCAL_RECORD')
        (root / 'local-evidence.txt').write_bytes(body + b'changed')
        rejected(lambda: recorder.Flow.reconciled(fixture, worker.CASE_STEP))
    cases.append({'name': 'frozen_consumer_null_observer_hash_contract_and_real_no_replace', 'passed': True,
        'local_owned_temporary_files_only': True, 'does_not_test_or_claim_actual_producer_semantic_qualification': True})

    worker.request_value((B / 'request.json').read_bytes(), partial)
    altered = copy.deepcopy(worker.FIXED_REQUEST); altered['stage_A_candidate']['sha256'] = '0' * 64
    rejected(lambda: worker.request_value(worker.canonical(altered) + b'\n', partial))
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)]
    need(sum(isinstance(n.func, ast.Name) and n.func.id == 'commit_envelope' for n in calls) == 1,
         'ONE_PUBLICATION_ENTRY')
    need(not any(isinstance(n.func, ast.Attribute) and n.func.attr in
                 ('reconcile', 'instrument', 'sequence', 'Popen', 'execve', 'system') for n in calls),
         'NO_NEW_UI_OR_OLD_RECONCILE_ENTRY')
    cases.append({'name': 'closed_actual_A_request_single_commit_and_no_UI_entry', 'passed': True})
    after = helper.census(); need(before == after, 'WHOLE_LOCAL_FD_IDENTITY_UNCHANGED')
    print(json.dumps({'schema': 'pocket4-no-action-stage-b-local-controls-v1', 'ok': True,
        'source_sha256': hashlib.sha256(source).hexdigest(), 'case_count': len(cases), 'cases': cases,
        'uid': os.getuid(), 'euid': os.geteuid(), 'process_fds_before': before, 'process_fds_after': after,
        'whole_process_fd_identities_unchanged': True, 'Main_or_remote_actions': 0,
        'actual_runtime_or_actual_publication_executed': False, 'old_case_or_claim_modified': False,
        'private_UI_content_in_output': False}, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
