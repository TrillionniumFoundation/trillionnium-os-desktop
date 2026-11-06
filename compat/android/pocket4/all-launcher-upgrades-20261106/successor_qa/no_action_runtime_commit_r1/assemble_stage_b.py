#!/usr/bin/env python3
"""Local-only Stage B assembly from the exact, actually completed Stage A."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import secrets

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
A = HERE / 'stage-a-candidate-r1'
OUT = HERE / 'stage-b-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def checked(path, length, digest):
    raw = path.read_bytes()
    assert len(raw) == length and sha(raw) == digest, str(path)
    return raw


def pin(path, raw):
    return {'path': path, 'bytes': len(raw), 'sha256': sha(raw)}


def definition(raw, name):
    text = raw.decode(); rows = [n for n in ast.parse(text).body
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    assert len(rows) == 1, name
    node = rows[0]
    return ''.join(text.splitlines(True)[node.lineno - 1:node.end_lineno]).rstrip() + '\n'


def literals(raw):
    found = {}
    for n in ast.parse(raw).body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            try:
                found[n.targets[0].id] = ast.literal_eval(n.value)
            except (ValueError, TypeError):
                pass
    return found


def change(text, old, new, count=1):
    assert text.count(old) == count, (old, text.count(old), count)
    return text.replace(old, new)


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    with (OUT / name).open('xb') as f:
        f.write(raw)


def main():
    a = checked(A / 'runtime_stage_a_once.py', 49806,
        '2a6dfffa73fa7698e6d59039d992c78a17ddaf07f0a01eab0973c327870c5c1e')
    old = checked(PROJECT / 'successor_qa/partial_case_runtime_commit_r1/stage-b-candidate-r1/commit_stage_b_once.py',
        70203, '28673ff6509c51dd818140107acfdd5d5847b7baeee366527735ff164e337a63')
    stdout = checked(A / 'actual/stdout.original.jsonl', 15528,
        '099a24caac0527f24a97417419cea432b57663cde227d7c844204b2896b08561')
    terminal_raw = checked(A / 'actual/terminal.original.json', 733,
        '8ca15446afb6c5a4623632071495abafb57c007459257fc463bac3001529abbe')
    stage, outer = map(json.loads, stdout.splitlines())
    terminal = json.loads(terminal_raw); child_raw = outer['child_stdout_original'].encode()
    child = json.loads(child_raw); ac = literals(a); oc = literals(old)
    assert terminal['job_id'] == '1a1b33331ac-fc05-8102' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[k] is True for k in ('audit_recorded', 'output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[k] is False for k in ('timed_out', 'cancelled', 'automatic_retry'))
    assert terminal['log_bytes'] == {'stdout': {'seen': len(stdout), 'stored': len(stdout)}, 'stderr': {'seen': 0, 'stored': 0}}
    assert terminal['log_errors'] == {'stdout': None, 'stderr': None} and terminal['log_truncated'] == {'stdout': False, 'stderr': False}
    assert terminal['log_synced'] == {'stdout': True, 'stderr': True}
    assert outer['ok'] is True and outer['errors'] == [] and child['ok'] is True and child['errors'] == []
    assert outer['source'] == pin(ac['ROOT'] + '/runtime_stage_a_once.py', a)
    assert outer['request'] == pin(ac['ROOT'] + '/request.json', (A / 'request.json').read_bytes())
    assert outer['child_lifecycle'] == {'child_pid': 2531797, 'errors': [], 'owned_child_sigkill_count': 0,
        'parent_descriptors_restored': True, 'pidfd_acquired': True, 'pidfd_closed': True,
        'pidfd_exit_observed': True, 'returncode': 0, 'timeout': False}
    assert outer['child_stderr_original'] == '' and outer['child_stderr_bytes'] == 0 and outer['child_stderr_sha256'] == sha(b'')
    assert len(child_raw) == outer['child_stdout_bytes'] == 10714 and sha(child_raw) == outer['child_stdout_sha256'] == \
        '0904e07408ef6a9a0bdad224e132f054123d3b137e67aa5239f487cb7ccbff38'
    assert outer['stage_B_not_sealed_or_executed'] is True and outer['reconciliation_published'] is False
    assert child['runtime_commands']['recorded_command_count'] == 6 and child['runtime_commands']['transport_count'] == 8
    assert len(child['runtime_commands']['evidence_sha256']) == 50
    for name, row in stage['files'].items():
        body = (A / name).read_bytes(); assert len(body) == row['bytes'] and sha(body) == row['sha256']
    assert stage['schema'] == 'pocket4-no-action-runtime-proof-stage-v1' and stage['root'] == ac['ROOT']

    constants = {k: v for k, v in ac.items() if k not in ('CANDIDATE_SCHEMA', 'FIXED_REQUEST')}
    constants.update(ROOT=ROOT, STEP='no-action-commit-01', OPERATION='owned-qa-no-action-commit',
        PROOF_SCHEMA='pocket4-owned-qa-no-action-committed-proof-v1',
        CHILD_SCHEMA='pocket4-owned-qa-no-action-commit-child-v1',
        PARENT_SCHEMA='pocket4-owned-qa-no-action-commit-owned-result-v1',
        COMMIT_NONCE=secrets.token_hex(16), STAGE_A_JOB=terminal['job_id'],
        STAGE_A_STEP=ac['STEP'], STAGE_A_SOURCE=outer['source'], STAGE_A_REQUEST=outer['request'],
        STAGE_A_CANDIDATE=outer['candidate'], STAGE_A_RESULT=outer['step_result'], STAGE_A_JOINT=outer['joint_artifact'],
        STAGE_A_STDOUT=pin(ROOT + '/stage-a.stdout.original.jsonl', stdout),
        STAGE_A_TERMINAL=pin(ROOT + '/stage-a.terminal.original.json', terminal_raw),
        ACTUAL_STAGE_A_STAGE=stage, ACTUAL_STAGE_A_CHILD_PID=2531797,
        ACTUAL_STAGE_A_CHILD_BYTES=len(child_raw), ACTUAL_STAGE_A_CHILD_SHA256=sha(child_raw))
    request = {'schema': 'pocket4-fixed-no-action-commit-only-request-v1', 'flow': constants['FLOW'],
        'step': constants['STEP'], 'operation': constants['OPERATION'],
        'original_failed_case': constants['CASE_STEP'], 'original_failed_controller': constants['FAILED_JOB'],
        'private_original_bundle': constants['HISTORY_BUNDLE'], 'independent_later_observer_available': False,
        'business_postcondition_observed': False, 'stage_A_job': constants['STAGE_A_JOB'],
        'stage_A_source': constants['STAGE_A_SOURCE'], 'stage_A_request': constants['STAGE_A_REQUEST'],
        'stage_A_stdout': constants['STAGE_A_STDOUT'], 'stage_A_terminal': constants['STAGE_A_TERMINAL'],
        'stage_A_candidate': constants['STAGE_A_CANDIDATE'], 'stage_A_step_result': constants['STAGE_A_RESULT'],
        'stage_A_joint': constants['STAGE_A_JOINT'], 'commit_nonce': constants['COMMIT_NONCE'],
        'source_revision': 'stage-b-candidate-r1', 'UI_actions': 0, 'instrumentation_calls': 0,
        'installs': 0, 'permission_changes': 0, 'original_UNKNOWN_retained': True, 'automatic_retry': False,
        'requires_new_fresh_original_six_readonly_commands': True,
        'coordinator_must_wait_for_actual_stage_B_durable_terminal': True}
    constants['FIXED_REQUEST'] = request
    header = '''#!/usr/bin/env python3
"""One explicit no-action proof commit after actually completed Stage A.

The old case stays FAILED/UNKNOWN. No postcondition or later observer is
manufactured. The unchanged consumer sees only a fully bound compatible
envelope from this explicit new producer, after fresh original predicates.
"""
import errno
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
    header += '\n'.join(k + ' = ' + repr(v) for k, v in constants.items()) + '\nSELF = REQUEST = None\n\n\n'
    exact_a = {'need', 'sha', 'canonical', 'load_base', 'write_once', 'actual_host_gate',
        'no_publication_or_replay', 'read_exact', 'history_context', 'original_directory_identity',
        'recheck_history', 'qualified_current_build', 'base_stat_fields', 'two_original_rounds',
        'checked_lock', 'final_descriptors'}
    old_names = [n.name for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)]
    old_names.insert(old_names.index('history_context'), 'original_directory_identity')
    evidence = (HERE / 'stage_b_evidence.fragment.py').read_bytes()
    parts = []; diffs = {}
    for name in old_names:
        if name in exact_a:
            body = definition(a, name)
        elif name == 'verify_six_commands':
            body = change(definition(a, name), "'stage_a_only': FIXED_REQUEST", "'stage_b_only': FIXED_REQUEST")
        elif name == 'collect_relative_hashes':
            body = definition(evidence, name)
        else:
            body = definition(old, name)
            body = body.replace('HOST_PROOF', 'HISTORY_BUNDLE')
            body = body.replace('original_historical_proof', 'original_private_bundle')
            body = body.replace("'historical_proof'", "'private_original_bundle'")
            body = body.replace('historical_proof=HISTORY_BUNDLE', 'private_original_bundle=HISTORY_BUNDLE')
            body = body.replace("'host-historical-proof.json'", "'no-action-history.json'")
            body = body.replace("'host-controller.stdout.original.jsonl'", "'history-reader.stdout.original.json'")
            body = body.replace("'host-controller.terminal.original.json'", "'history-reader.terminal.original.json'")
            body = body.replace('owned-qa-partial-proof.json', 'owned-qa-no-action-proof.json')
            body = body.replace('pocket4-owned-qa-stage-a-step-result-v1', 'pocket4-owned-qa-no-action-stage-a-step-result-v1')
            body = body.replace('pocket4-owned-qa-partial-case-commit-step-result-v1', 'pocket4-owned-qa-no-action-commit-step-result-v1')
            body = body.replace("('case_binding', 'observer_binding', 'stage_A_binding')", "('case_binding', 'stage_A_binding')")
        if name == 'validate_actual_stage_a':
            body = change(body, 'host.original_terminal(terminal, STAGE_A_JOB, len(raw))',
                          'partial.original_terminal(terminal, STAGE_A_JOB, len(raw))')
            body = change(body, "outer['child_lifecycle']['child_pid'] == 2349898", "outer['child_lifecycle']['child_pid'] == ACTUAL_STAGE_A_CHILD_PID")
            body = change(body, "outer['child_stdout_bytes'] == 10728", "outer['child_stdout_bytes'] == ACTUAL_STAGE_A_CHILD_BYTES")
            body = change(body, "'2650042c12f8bb977b546209b7c65ff2e57020cede3dbf7fab1fb98ed9d5251f'", 'ACTUAL_STAGE_A_CHILD_SHA256')
        elif name == 'completed_stage_a':
            anchor = "stage_a.candidate_gate(candidate, STAGE_A_SOURCE, STAGE_A_REQUEST)"
            body = change(body, anchor, anchor + "\n    need(candidate['no_action_history_sha256'] == sha(context['proof_raw']),\n         'ACTUAL_STAGE_A_AND_CURRENT_REPARSED_NO_ACTION_HISTORY_IDENTICAL')")
        elif name == 'committed_envelope':
            body = change(body, "value.get('observation_step') == OBSERVATION_STEP and", "value.get('observation_step') is None and value.get('postcondition') is None and\n         value.get('helper_requested_click_dispatch_attempted') is False and\n         value.get('independent_later_observer_available') is False and\n         value.get('business_postcondition_observed') is False and")
            body = change(body, "need(type(hashes) is dict and 450 <= len(hashes) <= 512, 'COMPLETE_RELATIVE_RECONCILIATION_CLOSURE')", 'published_member_set(hashes)')
        elif name == 'child':
            body = change(body, "'original_case': CASE_STEP, 'later_observation': OBSERVATION_STEP,", "'original_case': CASE_STEP, 'later_observation': None,\n            'independent_later_observer_available': False, 'business_postcondition_observed': False,\n            'helper_requested_click_dispatch_attempted': False,\n            'no_action_history_sha256': sha(context['proof_raw']),")
            body = change(body, "Actual successful prefix plus rejected pre-dispatch suffix and later independent postcondition; original failed case remains failed.",
                "Actual single helper rejection before click dispatch plus independent state retirement; no later observer or business postcondition is claimed; original case remains FAILED/UNKNOWN.")
            body = change(body, "'unknown_step': CASE_STEP, 'observation_step': OBSERVATION_STEP,", "'unknown_step': CASE_STEP, 'observation_step': None,\n            'helper_requested_click_dispatch_attempted': False,\n            'independent_later_observer_available': False, 'business_postcondition_observed': False,")
            body = body.replace('write_explicit_partial_case_proof', 'write_explicit_no_action_proof')
        parts.append(body)
        if name in exact_a:
            assert definition(a, name) == body
        elif name in [n.name for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)]:
            diffs[name] = ''.join(difflib.unified_diff(definition(old, name).splitlines(True), body.splitlines(True),
                fromfile='actual-partial-stage-b/' + name, tofile='no-action-stage-b/' + name, n=3))
    parts.insert(old_names.index('committed_envelope'), definition(evidence, 'published_member_set'))
    old_entry = old.decode().split("if __name__ == '__main__':\n")
    assert len(old_entry) == 2
    worker = (header + '\n\n'.join(parts) + "\n\nif __name__ == '__main__':\n" + old_entry[1]).encode()
    compile(worker, ROOT + '/commit_stage_b_once.py', 'exec')
    assert definition(worker, 'commit_envelope') == definition(old, 'commit_envelope')
    OUT.mkdir(mode=0o700, exist_ok=False)
    for name, raw in {'commit_stage_b_once.py': worker, 'request.json': canonical(request) + b'\n',
        'stage-a.stdout.original.jsonl': stdout, 'stage-a.terminal.original.json': terminal_raw}.items():
        put(name, raw)
    put('worker-against-actual-partial-stage-b.diff', ''.join(difflib.unified_diff(old.decode().splitlines(True),
        worker.decode().splitlines(True), fromfile='actual-partial-stage-b', tofile='new-no-action-stage-b', n=3)))
    put('changed-stage-b-functions.diff', ''.join(diffs.values()))
    put('new-evidence-closure.fragment.py', evidence)
    inheritance = {'schema': 'pocket4-no-action-stage-b-source-inheritance-v1',
        'actual_stage_A_source': outer['source'], 'actual_stage_A_job': terminal['job_id'],
        'actual_stage_A_stdout': pin('actual/stdout.original.jsonl', stdout),
        'actual_stage_A_terminal': pin('actual/terminal.original.json', terminal_raw),
        'actual_original_stage_B': {'bytes': len(old), 'sha256': sha(old)},
        'exact_stage_A_functions': {name: sha(definition(worker, name).encode()) for name in sorted(exact_a)},
        'original_commit_envelope_exact': True,
        'commit_envelope_definition_sha256': sha(definition(worker, 'commit_envelope').encode()),
        'original_SystemExit_entry_exact': True, 'original_helper_consumer_Flow_modified': False,
        'original_failed_result_modified': False, 'private_UI_payload_included': False,
        'source': pin(ROOT + '/commit_stage_b_once.py', worker),
        'request': pin(ROOT + '/request.json', canonical(request) + b'\n'),
        'exact_evidence_members': {'original_failed_step': 90, 'actual_stage_A_step': 57,
            'original_flow_inputs': 5, 'new_prepublication_step': 59, 'total': 211}}
    put('SOURCE_INHERITANCE.json', json.dumps(inheritance, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'state': 'LOCAL_NO_ACTION_STAGE_B_ASSEMBLED_FROM_ACTUAL_STAGE_A_NOT_RUN',
        'source': inheritance['source'], 'request': inheritance['request'],
        'actual_stage_A_job': terminal['job_id'], 'exact_evidence_count': 211}))


if __name__ == '__main__':
    main()
