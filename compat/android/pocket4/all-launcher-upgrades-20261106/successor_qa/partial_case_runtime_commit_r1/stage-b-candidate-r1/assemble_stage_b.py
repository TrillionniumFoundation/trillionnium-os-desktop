#!/usr/bin/env python3
"""Local-only explicit Stage B assembly from actually completed Stage A."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE_A = HERE.parent / 'stage-a-candidate-r1'
PROJECT = HERE.parents[2]
ROOT = '/home/alex/work/pocket4-beike-partial-case-commit-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def checked(path, length, digest):
    raw = path.read_bytes()
    assert len(raw) == length and sha(raw) == digest, path
    return raw


def definition(raw, name):
    text = raw.decode(); nodes = [node for node in ast.parse(text).body if
        isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    assert len(nodes) == 1, name
    node = nodes[0]
    return ''.join(text.splitlines(True)[node.lineno - 1:node.end_lineno]).rstrip() + '\n'


def main():
    a_raw = checked(STAGE_A / 'runtime_stage_a_once.py', 44063,
        '52784825ed50fc6178468ca80d05af7c060d48ca1da4dc2d38094b2778df02f1')
    a_stdout = checked(STAGE_A / 'actual/stdout.original.jsonl', 15030,
        '6891adc64b25707ce078b2e57ec24f10afb5ca74a80d0dc2e89632104c38aec4')
    a_terminal = checked(STAGE_A / 'actual/terminal.original.json', 733,
        '720ab02fbee47261645eee5312d577f73b010f50788728150bdcb4698e338f37')
    a_stage, actual = map(json.loads, a_stdout.splitlines())
    terminal = json.loads(a_terminal)
    assert terminal['job_id'] == '1a1b2d13973-fc05-7fe2' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert terminal['output_durable'] and terminal['output_complete'] and not terminal['timed_out']
    assert terminal['log_bytes'] == {'stdout': {'seen': 15030, 'stored': 15030}, 'stderr': {'seen': 0, 'stored': 0}}
    assert actual['ok'] and actual['errors'] == [] and actual['child_lifecycle']['returncode'] == 0
    assert actual['child_lifecycle']['pidfd_exit_observed'] and actual['child_lifecycle']['pidfd_closed']
    assert actual['child_lifecycle']['owned_child_sigkill_count'] == 0 and actual['original_case_outcome_unknown']
    old_publisher = checked(PROJECT / 'successor_qa/owned_postcondition_reconciler_r1/candidate-r2/publish_owned_reconciliation.py',
        41838, '1c20f6ffb7c8fc260e161a1ac5a95df0852d0daa23bc833c71533ef6964b55a2')
    constants = {}
    for node in ast.parse(a_raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key not in ('SELF', 'REQUEST'):
                constants[key] = ast.literal_eval(node.value)
    constants.update(ROOT=ROOT, STEP='partial-case-commit-01', OPERATION='owned-qa-partial-case-commit',
        PROOF_SCHEMA='pocket4-owned-qa-partial-case-committed-proof-v1',
        CHILD_SCHEMA='pocket4-owned-qa-partial-case-commit-child-v1',
        PARENT_SCHEMA='pocket4-owned-qa-partial-case-commit-owned-result-v1',
        STAGE_A_SOURCE=actual['source'], STAGE_A_REQUEST=actual['request'],
        STAGE_A_JOB=terminal['job_id'], STAGE_A_STEP=actual['step'],
        STAGE_A_CANDIDATE=actual['candidate'], STAGE_A_RESULT=actual['step_result'], STAGE_A_JOINT=actual['joint_artifact'],
        STAGE_A_STDOUT={'path': ROOT + '/stage-a.stdout.original.jsonl', 'bytes': len(a_stdout), 'sha256': sha(a_stdout)},
        STAGE_A_TERMINAL={'path': ROOT + '/stage-a.terminal.original.json', 'bytes': len(a_terminal), 'sha256': sha(a_terminal)},
        ACTUAL_STAGE_A_STAGE=a_stage,
        COMMIT_NONCE=sha((ROOT + '\n' + sha(a_stdout) + '\nno-replace-r1').encode())[:32])
    del constants['CANDIDATE_SCHEMA']
    request = {'schema': 'pocket4-fixed-partial-case-commit-only-request-v1',
        'flow': constants['FLOW'], 'step': constants['STEP'], 'operation': constants['OPERATION'],
        'original_failed_case': constants['CASE_STEP'], 'later_observation': constants['OBSERVATION_STEP'],
        'historical_proof': constants['HOST_PROOF'], 'completed_stage_A_job': constants['STAGE_A_JOB'],
        'completed_stage_A_source': constants['STAGE_A_SOURCE'], 'completed_stage_A_request': constants['STAGE_A_REQUEST'],
        'completed_stage_A_stdout': constants['STAGE_A_STDOUT'], 'completed_stage_A_terminal': constants['STAGE_A_TERMINAL'],
        'completed_stage_A_candidate': constants['STAGE_A_CANDIDATE'],
        'completed_stage_A_result': constants['STAGE_A_RESULT'], 'completed_stage_A_joint': constants['STAGE_A_JOINT'],
        'source_revision': 'stage-b-candidate-r1', 'UI_actions': 0, 'instrumentation_calls': 0,
        'permission_changes': 0, 'installs': 0, 'original_UNKNOWN_retained': True,
        'publication': 'one_new_no_replace_compatibility_record_after_same_original_runtime_predicates',
        'commit_nonce': constants['COMMIT_NONCE'], 'automatic_retry': False,
        'next_UI_decision_requires_actual_stage_B_durable_terminal_and_fresh_original_checks': True}
    request_raw = canonical(request) + b'\n'; constants['FIXED_REQUEST'] = request
    header = '''#!/usr/bin/env python3
"""Explicit partial-case producer after actual Stage A normal retirement.

Original case FAILED/UNKNOWN and original Flow/helper predicates are retained.
This new operation rechecks the same runtime, then writes one no-replace typed
compatibility record. It does not execute UI, and its own real durable terminal
must be collected before the coordinator permits any new decision.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

sys.dont_write_bytecode = True
'''
    header += '\n'.join(key + ' = ' + repr(value) for key, value in constants.items()) + '\nSELF = REQUEST = None\n\n\n'
    exact_names = ('need', 'sha', 'canonical', 'load_base', 'write_once', 'actual_host_gate',
        'no_publication_or_replay', 'read_exact', 'history_context', 'recheck_history', 'qualified_current_build',
        'base_stat_fields', 'two_original_rounds', 'checked_lock', 'final_descriptors')
    inherited = '\n\n'.join(definition(a_raw, name).rstrip() for name in exact_names) + '\n\n\n'
    entry = definition(a_raw, 'entry').replace('runtime_stage_a_once.py', 'commit_stage_b_once.py').replace('STAGE_A', 'STAGE_B')
    request_def = definition(a_raw, 'request_value').replace('CLOSED_STAGE_A_ONLY_REQUEST_NO_ARBITRARY_COMMAND_OR_COMMIT',
                                                          'CLOSED_STAGE_B_ONLY_REQUEST_NO_ARBITRARY_COMMAND_OR_PATH')
    verify = definition(a_raw, 'verify_six_commands').replace("'stage_a_only'", "'stage_b_only'")
    failure = definition(a_raw, 'safe_failure').replace('STAGE_A_STRICT_REJECTION', 'STAGE_B_STRICT_REJECTION')
    commit = definition(old_publisher, 'commit_envelope')
    worker = (header + inherited + '\n\n'.join((entry, request_def, verify, failure, commit)) + '\n\n' +
        (HERE / 'stage_b_new_functions.fragment.py').read_text() + '\n\n' +
        (HERE / 'stage_b_owner.fragment.py').read_text()).encode()
    compile(worker, str(HERE / 'commit_stage_b_once.py'), 'exec')
    (HERE / 'commit_stage_b_once.py').write_bytes(worker)
    (HERE / 'request.json').write_bytes(request_raw)
    (HERE / 'stage-a.stdout.original.jsonl').write_bytes(a_stdout)
    (HERE / 'stage-a.terminal.original.json').write_bytes(a_terminal)
    full_diff = ''.join(difflib.unified_diff(a_raw.decode().splitlines(True), worker.decode().splitlines(True),
        fromfile='actually-passed-stage-a/runtime_stage_a_once.py', tofile='stage-b/commit_stage_b_once.py', n=3))
    (HERE / 'worker-against-actual-stage-a.diff').write_text(full_diff)
    small_parts = []
    for name, changed in (('entry', entry), ('request_value', request_def), ('verify_six_commands', verify), ('safe_failure', failure)):
        small_parts.extend(difflib.unified_diff(definition(a_raw, name).splitlines(True), changed.splitlines(True),
            fromfile='actual-stage-a/' + name, tofile='stage-b/' + name, n=3))
    (HERE / 'inherited-interface-only.diff').write_text(''.join(small_parts))
    proof = {'schema': 'pocket4-stage-b-source-inheritance-v1',
        'actually_completed_stage_A': {'job_id': constants['STAGE_A_JOB'], 'source': constants['STAGE_A_SOURCE'],
            'stdout': constants['STAGE_A_STDOUT'], 'terminal': constants['STAGE_A_TERMINAL'],
            'candidate': constants['STAGE_A_CANDIDATE'], 'joint': constants['STAGE_A_JOINT']},
        'exact_inherited_definitions': {name: {'bytes': len(definition(a_raw, name).encode()),
            'sha256': sha(definition(a_raw, name).encode()), 'same_bytes': definition(a_raw, name) == definition(worker, name)}
            for name in exact_names},
        'four_narrow_interface_edits': ['entry only filename/phase labels', 'closed request error label',
            'new explicit intent request key stage_b_only', 'safe error phase label'],
        'same_original_no_replace_commit': {'source': 'successor_qa/owned_postcondition_reconciler_r1/candidate-r2/publish_owned_reconciliation.py',
            'file_sha256': sha(old_publisher), 'definition_sha256': sha(commit.encode()),
            'same_bytes': commit == definition(worker, 'commit_envelope')},
        'original_Flow_consumer_helper_guard_or_partial_core_modified': False,
        'new_UI_or_instrumentation_call': False, 'preparation_submitted_device_or_Git_actions': 0,
        'source': {'bytes': len(worker), 'sha256': sha(worker)},
        'request': {'bytes': len(request_raw), 'sha256': sha(request_raw)}}
    (HERE / 'SOURCE_INHERITANCE.json').write_bytes(json.dumps(proof, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'state': 'LOCAL_STAGE_B_SOURCE_ASSEMBLED_NOT_EXECUTED', 'source': proof['source'],
                      'request': proof['request'], 'exact_inherited_definitions': len(exact_names)}))


if __name__ == '__main__':
    main()
