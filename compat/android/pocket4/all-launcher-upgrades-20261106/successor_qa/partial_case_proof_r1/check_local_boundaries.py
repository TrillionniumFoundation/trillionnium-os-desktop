#!/usr/bin/env python3
"""Small local boundary checks using actual controller receipts and source pins.

No host archive, Android, root UID, current runtime or end-to-end proof is
simulated. The complete 257/81-file verification must run against real files.
"""
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def module(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


def main():
    root = HERE / 'candidate-r1'
    worker = module(root / 'verify_partial_case_host.py', 'local_host_predicates_only')
    before = worker.census()
    partial = module(root / 'partial_case_core.py', 'local_partial_protocol')
    common = module(PROJECT / 'successor_qa/owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py',
                    'local_frozen_common')
    reader = module(root / 'read_failed_case.frozen.py', 'local_original_reader')
    cases = []
    def passed(name):
        cases.append({'name': name, 'passed': True})
    def reject(name, call, expected):
        try:
            call()
        except RuntimeError as error:
            if str(error) != expected:
                raise
        else:
            raise RuntimeError('EXPECTED_REJECTION_ABSENT:' + name)
        passed(name)
    original, life = reader.validate_actual(common)
    assert original['ok'] is False and original['outcome_unknown'] is True and life['returncode'] == 1
    passed('real_original_failed_controller_and_child_retirement_remain_failed')
    terminal = json.loads((root / 'observation.terminal.original.json').read_bytes())
    worker.original_terminal(terminal, '1a1b285c279-fc05-7e67', 13961)
    passed('actual_later_observer_durable_complete_terminal')
    reject('failed_observer_exit_not_accepted', lambda: worker.original_terminal(
        {**terminal, 'exit_code': 1}, '1a1b285c279-fc05-7e67', 13961),
        'ACTUAL_AUTHORITATIVE_OBSERVER_DURABLE_COMPLETE_ZERO')
    reject('observer_incomplete_durable_output_not_accepted', lambda: worker.original_terminal(
        {**terminal, 'output_durable': False}, '1a1b285c279-fc05-7e67', 13961),
        'ACTUAL_AUTHORITATIVE_OBSERVER_DURABLE_COMPLETE_ZERO')
    outer = json.loads((root / 'observation.stdout.original.json').read_bytes())
    child = json.loads(outer['child_stdout_original']); original_observer = json.loads(child['original_stdout'])
    launch = original_observer['owned_task']; partial.fixed_launch(launch, common)
    reject('another_task_not_accepted_for_original_native_scope',
           lambda: partial.fixed_launch({**launch, 'task': 876}, common),
           'EXACT_ACTUAL_TASK878_NATIVE_SCOPE')
    reject('cleanup_authority_not_invented',
           lambda: partial.fixed_launch({**launch, 'cleanup_allowed': False}, common),
           'EXACT_ACTUAL_TASK878_NATIVE_SCOPE')
    reject('duplicate_original_json_field_not_silently_accepted',
           lambda: partial.document(b'{"outcome_unknown":true,"outcome_unknown":false}'),
           'DUPLICATE_ORIGINAL_JSON_KEY')
    reject('nonfinite_json_cannot_enter_new_proof', lambda: partial.document(b'{"x":NaN}'),
           'NONFINITE_ORIGINAL_JSON')
    source_pins = json.loads((root / 'SOURCE_PINS.json').read_bytes())
    packet = json.loads((root / 'process-request.review-only.json').read_bytes())
    payload = json.loads(packet['stdin']); inputs = json.loads((root / 'inputs.json').read_bytes())
    import base64
    assert set(payload['files']) == set(source_pins['staged_files'])
    for name, pin in source_pins['staged_files'].items():
        raw = (root / name).read_bytes(); packed = base64.b64decode(payload['files'][name]['base64'], validate=True)
        assert raw == packed and len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
    assert inputs['historical_build_receipt_owner_observed']['uid'] == 1000
    assert packet['idempotency_key'] == 'pocket4-beike-task878-partial-case-host-verifier-r1-20261106'
    assert packet['args'][:5] == ['-n', '/usr/bin/python3', '-I', '-B', '-c']
    assert packet['args'][5].encode() == (root / 'stage_verify_host_once.py').read_bytes()
    passed('sealed_exact_byte_closure_and_truthful_uid1000_archival_input')
    after = worker.census(); assert after == before
    print(json.dumps({'schema': 'pocket4-partial-case-local-boundary-controls-v1',
        'ok': True, 'actual_local_uid': os.getuid(), 'actual_local_euid': os.geteuid(),
        'cases': cases, 'whole_process_fd_identity_unchanged': True,
        'process_fds_before': before, 'process_fds_after': after,
        'real_private_case_or_observer_bundle_verified_locally': False,
        'Main_operations': 0, 'target_jobs': 0, 'compatibility_publications': 0,
        'production_ready': False}, sort_keys=True))


if __name__ == '__main__':
    main()
