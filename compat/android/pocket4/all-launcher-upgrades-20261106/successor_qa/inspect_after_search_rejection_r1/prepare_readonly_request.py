#!/usr/bin/env python3
"""Data-only request for the unchanged, already staged owned UI worker."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import types

HERE = Path(__file__).resolve().parent
QA = HERE.parent
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
ROOT = '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1'
STEP = 'inspect-after-search-rejection-01'
WORKER = {'path': ROOT + '/owned_ui_request_once.py', 'bytes': 25377,
          'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def write(name, raw):
    with (HERE / name).open('xb') as stream:
        stream.write(raw)
    return {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}


def module(relative, size, digest, name):
    path = QA / relative
    raw = exact(path, size, digest)
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def main():
    actual_raw = exact(QA / 'case_failure_reader_r1/actual-public/stdout.original.json', 34515,
        '49adfc22a9aa4a35d810835534ca578282d1d76fd38a862d480f59651fc6b0b2')
    terminal_raw = (QA / 'case_failure_reader_r1/actual-public/status-01.original.txt').read_bytes()
    actual, terminal = json.loads(actual_raw), json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1b27f06b8-fc05-7e46' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[key] is False for key in ('automatic_retry', 'timed_out', 'cancelled'))
    assert terminal['log_bytes'] == {'stdout': {'seen': 34515, 'stored': 34515}, 'stderr': {'seen': 0, 'stored': 0}}
    assert actual['ok'] is True and actual['diagnosis_completed'] is True and actual['diagnosis_error'] is None
    assert actual['flow'] == FLOW and actual['task'] == 878 and actual['historical_job'] == '1a1b272ec9d-fc05-7e0d'
    assert actual['original_case_success'] is False and actual['old_UNKNOWN_modified'] is False
    assert actual['whole_process_fd_identities_unchanged'] is True
    diagnosis = actual['diagnosis']; phases = diagnosis['phases']
    rejected = [row for row in phases if row.get('failed_assessment_present') is True]
    assert len(rejected) == 1
    rejected = rejected[0]
    assert (rejected['index'], rejected['kind'], rejected['phase'], rejected['nonce'], rejected['command_index']) == (
        1, 'operation', 'action', '50e2673f0308c07c66e2b551f355bfae', 25)
    helper = rejected['helper_rejection']
    assert helper['error'] == 'INSPECTED_TREE_OR_WINDOW_CHANGED' and helper['action_attempted'] is False
    assert helper['outcome_unknown'] is False and helper['qualified_success'] is False and helper['instrumentation_finish_code'] == 0
    assert diagnosis['all_recorded_commands_normal_zero_joined'] is True and diagnosis['all_recorded_transports_verified'] is True
    assert len(diagnosis['commands']) == 29 and len(diagnosis['transports']) == 38
    assert all(row['request_present'] is False for row in phases if row['index'] == 1 and row['kind'] == 'post_inspection')
    assert diagnosis['first_declared_postcondition_reparsed'] is True and diagnosis['failure_remains_unknown'] is True

    adapter = module('reconstructed/source-generation-r2/helper/qa_adapter.py', 29378,
        'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c', 'unchanged_readonly_plan_validator')
    wire = module('reconstructed/source-generation-r2/helper/qa_contract.py', 52359,
        'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e', 'unchanged_wire_validator')
    cases = module('reconstructed/source-generation-r2/helper/run_case.py', 9595,
        'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b', 'unchanged_case_validator_unused')
    core = module('owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', 28714,
        '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41', 'unchanged_json_definitions')
    wrapper = module('reusable_owned_ui_r1/owned_ui_request_once.py', WORKER['bytes'], WORKER['sha256'], 'unchanged_request_validator')
    prior_nonces = {row['nonce'] for row in phases}
    prior_plan = json.loads((QA / 'reusable_owned_ui_r1/inspect-new-session-01.plan.json').read_bytes())
    prior_nonces.update(prior_plan['nonces'].values())
    nonces = {}
    for phase in ('before', 'inspect', 'after'):
        nonce = secrets.token_hex(16)
        assert nonce not in prior_nonces and nonce not in nonces.values()
        nonces[phase] = nonce
    plan = {'schema': 1, 'operation': 'inspect', 'nonces': nonces}
    assert adapter.validate_plan(plan, wire) == plan
    plan_raw = canonical(plan) + b'\n'
    request = {'schema': 'pocket4-fixed-beike-owned-ui-request-v1', 'kind': 'plan', 'step': STEP,
               'payload_text': plan_raw.decode('ascii'), 'payload_sha256': sha(plan_raw)}
    request_raw = canonical(request) + b'\n'
    parsed, body, checked_plan, mutation = wrapper.declared_request(request_raw, core, adapter, wire, cases)
    assert parsed == request and body == plan_raw and checked_plan == plan and mutation is False
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', WORKER['path'], '--publish-and-execute',
                 '--source-sha256', WORKER['sha256'], '--source-bytes', str(WORKER['bytes']),
                 '--request-sha256', sha(request_raw), '--request-bytes', str(len(request_raw))],
        'stdin': request_raw.decode('ascii'), 'cwd': '/home/alex/work', 'timeout_seconds': 480,
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-inspect-after-search-rejection-r1-20261106'}
    plan_pin = write('inspect.review-only.json', plan_raw)
    request_pin = write('request.review-only.json', request_raw)
    packet_pin = write('process-request.review-only.json', json.dumps(packet, ensure_ascii=True,
        sort_keys=True, indent=2).encode('ascii') + b'\n')
    proof = {'schema': 'pocket4-readonly-inspect-after-rejected-click-preparation-v1', 'ok': True,
        'local_only': True, 'actual_uid': os.getuid(), 'remote_submitted': False, 'Main_commands': 0,
        'same_existing_flow': FLOW, 'same_owned_task': 878, 'existing_unchanged_worker': WORKER,
        'step': STEP, 'plan': plan_pin, 'request': request_pin, 'packet': packet_pin,
        'original_declared_request_mutation': mutation, 'declared_click_or_set_text_operations': 0,
        'declared_selector_fields': 0, 'new_distinct_nonces': 3,
        'actual_failure_reader': {'job_id': terminal['job_id'], 'stdout_bytes': len(actual_raw),
            'stdout_sha256': sha(actual_raw), 'terminal_bytes': len(terminal_raw), 'terminal_sha256': sha(terminal_raw)},
        'actual_case_remains_failed_and_unknown': True, 'actual_search_click_helper_declined_before_action': True,
        'new_source_or_helper_required': False, 'reconciliation_published': False,
        'search_page_or_new_current_state_preclaimed': False, 'production_ready': False}
    write('LOCAL_PREPARATION_PROOF.json', json.dumps(proof, ensure_ascii=True, indent=2, sort_keys=True).encode() + b'\n')
    print(json.dumps(proof, sort_keys=True))


if __name__ == '__main__':
    main()
