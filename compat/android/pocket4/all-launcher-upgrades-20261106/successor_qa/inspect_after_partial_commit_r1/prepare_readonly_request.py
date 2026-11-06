#!/usr/bin/env python3
"""Prepare only new inspect data for the unchanged existing QA worker."""
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import types

HERE = Path(__file__).resolve().parent
QA = HERE.parent
PROJECT = QA.parent
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
ROOT = '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1'
STEP = 'inspect-after-partial-commit-01'
WORKER = {'path': ROOT + '/owned_ui_request_once.py', 'bytes': 25377,
          'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}
B_SOURCE = {'bytes': 70203, 'sha256': '28673ff6509c51dd818140107acfdd5d5847b7baeee366527735ff164e337a63'}
B_REQUEST = {'bytes': 2596, 'sha256': 'ca6d11780cc7f6d6a3adf58f5f2bcbe10eefc07fde9c636398b55f2a11d7d82c'}
B_PACKET = {'bytes': 125249, 'sha256': '57bbcee17b33b9658a952a3a031866107d7bf9704386d547ab90357cb8c44479'}
HELPER_MANIFEST = {'bytes': 2431, 'sha256': 'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4'}
RECORDER_MANIFEST = {'bytes': 1759, 'sha256': '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def exact(path, expected):
    raw = path.read_bytes()
    assert pin(raw) == {key: expected[key] for key in ('bytes', 'sha256')}, str(path)
    return raw


def write(name, raw):
    fd = os.open(HERE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            assert count > 0
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    assert (HERE / name).read_bytes() == raw
    return {'path': name, **pin(raw)}


def module(path, expected, name):
    raw = exact(path, expected)
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def definition(text, path):
    nodes = ast.parse(text).body
    for name in path.split('.'):
        rows = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
        assert len(rows) == 1, path
        found = rows[0]; nodes = found.body
    return ''.join(text.splitlines(True)[found.lineno - 1:found.end_lineno]).encode()


def collect_nonces(value, found):
    if type(value) is dict:
        if type(value.get('nonces')) is dict:
            found.update(value['nonces'].values())
        for row in value.values():
            collect_nonces(row, found)
    elif type(value) is list:
        for row in value:
            collect_nonces(row, found)


def main():
    helper = QA / 'reconstructed/source-generation-r2/helper'
    recorder = QA / 'reconstructed/source-generation-r2/recorder'
    source_rows = []
    manifests = []
    for root, name, expected in ((helper, 'SOURCE_PINS.json', HELPER_MANIFEST),
                                  (recorder, 'source-manifest.json', RECORDER_MANIFEST)):
        raw = exact(root / name, expected)
        manifest = json.loads(raw)
        assert len(manifest['files']) == 13
        manifests.append({'path': (root / name).relative_to(PROJECT).as_posix(), **pin(raw)})
        for name, member in sorted(manifest['files'].items()):
            body = exact(root / name, member)
            source_rows.append({'path': (root / name).relative_to(PROJECT).as_posix(), **pin(body)})
    assert len(source_rows) == 26
    by_name = {row['path']: row for row in source_rows}
    def checked_module(root, name, label):
        path = root / name
        return module(path, by_name[path.relative_to(PROJECT).as_posix()], label)
    adapter = checked_module(helper, 'qa_adapter.py', 'unchanged_readonly_adapter_validation')
    wire = checked_module(helper, 'qa_contract.py', 'unchanged_wire_contract_validation')
    cases = checked_module(helper, 'run_case.py', 'unchanged_case_contract_not_executed')
    worker_path = QA / 'reusable_owned_ui_r1/owned_ui_request_once.py'
    worker = module(worker_path, WORKER, 'unchanged_existing_request_validator')
    core_path = QA / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py'
    core_pin = {'bytes': 28714, 'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'}
    core = module(core_path, core_pin, 'unchanged_closed_json_document_validator')
    b = QA / 'partial_case_runtime_commit_r1/stage-b-candidate-r1'
    for name, expected in (('commit_stage_b_once.py', B_SOURCE), ('request.json', B_REQUEST),
                           ('process-request.review-only.json', B_PACKET)):
        exact(b / name, expected)

    # Collision checks read only known plan data. This is not a new observation.
    old_plan_paths = (
        QA / 'reusable_owned_ui_r1/inspect-new-session-01.plan.json',
        QA / 'explore_home_search_case_r1/case.review-only.json',
        QA / 'inspect_after_search_rejection_r1/inspect.review-only.json',
    )
    old_nonces = set()
    old_plan_pins = []
    for path in old_plan_paths:
        raw = path.read_bytes()
        collect_nonces(json.loads(raw), old_nonces)
        old_plan_pins.append({'path': path.relative_to(PROJECT).as_posix(), **pin(raw)})
    nonces = {}
    for phase in ('before', 'inspect', 'after'):
        nonce = secrets.token_hex(16)
        assert nonce not in old_nonces and nonce not in nonces.values()
        nonces[phase] = nonce
    plan = {'schema': 1, 'operation': 'inspect', 'nonces': nonces}
    assert adapter.validate_plan(plan, wire) == plan
    plan_raw = canonical(plan) + b'\n'
    request = {'schema': 'pocket4-fixed-beike-owned-ui-request-v1', 'kind': 'plan', 'step': STEP,
               'payload_text': plan_raw.decode('ascii'), 'payload_sha256': sha(plan_raw)}
    request_raw = canonical(request) + b'\n'
    parsed, body, checked_plan, mutation = worker.declared_request(request_raw, core, adapter, wire, cases)
    assert parsed == request and body == plan_raw and checked_plan == plan and mutation is False
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', WORKER['path'], '--publish-and-execute',
                 '--source-sha256', WORKER['sha256'], '--source-bytes', str(WORKER['bytes']),
                 '--request-sha256', sha(request_raw), '--request-bytes', str(len(request_raw))],
        'stdin': request_raw.decode('ascii'), 'cwd': '/home/alex/work', 'timeout_seconds': 480,
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-inspect-after-partial-commit-r1-20261106'}
    plan_pin = write('inspect.review-only.json', plan_raw)
    request_pin = write('request.review-only.json', request_raw)
    packet_pin = write('process-request.review-only.json', json.dumps(packet, ensure_ascii=True,
        sort_keys=True, indent=2).encode('ascii') + b'\n')
    methods = {
        helper / 'qa_adapter.py': ['validate_plan', 'own_source', 'qualified_build', 'Session.installed',
                                  'Session.task', 'Session.foreground', 'Session.sequence'],
        helper / 'qa_contract.py': ['select_unique_clickable', 'select_unique_editable'],
        helper / 'run_case.py': ['validate_case', 'match_postcondition', 'execute'],
        recorder / 'recorder.py': ['Flow.begin', 'Flow.reconciled', 'Flow.reconcile'],
        worker_path: ['declared_request', 'launch_gate', 'original_argv', 'verify_original', 'child', 'parent'],
    }
    methods_rows = []
    for path, names in methods.items():
        raw = path.read_bytes()
        methods_rows.append({'path': path.relative_to(PROJECT).as_posix(), **pin(raw),
            'definitions': {name: pin(definition(raw.decode(), name)) for name in names}})
    index = {'schema': 'pocket4-existing-owned-QA-full-source-reference-v1',
        'scope': {'flow': FLOW, 'task': 878, 'package': 'com.lianjia.beike', 'helper_UID': 10157,
                  'helper_package': 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'},
        'source_origin': 'deterministic reconstruction from actual binding and pinned references; complete manifests previously match actual generated sources',
        'source_manifests': manifests, 'all_26_source_members': source_rows,
        'unchanged_existing_worker': {'local_path': worker_path.relative_to(PROJECT).as_posix(), **WORKER},
        'function_contract_references': methods_rows,
        'source_or_helper_or_Flow_modified': False, 'source_generation_qualification_flags_not_rewritten': True}
    index_pin = write('SOURCE_CONTRACT_INDEX.json', json.dumps(index, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    prerequisites = {'schema': 'pocket4-readonly-inspect-after-partial-commit-prerequisites-v1',
        'state_at_preparation': 'AWAIT_ACTUAL_COMPLETE_STAGE_B_SUCCESS_AND_ROOT_DISPATCH',
        'Stage_B_actual_job_or_terminal_claimed_here': False,
        'required_Stage_B_source': B_SOURCE, 'required_Stage_B_request': B_REQUEST, 'required_Stage_B_packet': B_PACKET,
        'required_Stage_B_joint_state': {'controller_durable_exit': 0, 'controller_complete_original_stdout_and_stderr': True,
            'parent_ok': True, 'child_normal_exit_held_pidfd_retired': True, 'parent_FDs_restored': True,
            'exact_typed_proof_and_compatibility_readback': True, 'publication_outcome_unknown': False,
            'original_failed_UNKNOWN_bytes_retained': True},
        'coordinator_must_check_actual_Stage_B_before_dispatch': True,
        'unchanged_inspect_worker_does_not_itself_validate_Stage_B_terminal': True,
        'read_only_plan_does_not_clear_UNKNOWN_or_publish_reconciliation': True,
        'new_UI_mutation_requires_original_Flow_consumer_and_fresh_inspection': True,
        'no_new_action_plan_or_selector_in_this_packet': True,
        'same_worker_no_new_stager_or_helper': True, 'automatic_retry': False,
        'unknown_launch_or_output_requires_same_job_reconciliation_no_new_key': True,
        'production_ready': False}
    prerequisites_pin = write('EXECUTION_PREREQUISITES.json', json.dumps(prerequisites,
        ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    proof = {'schema': 'pocket4-readonly-post-partial-commit-data-preparation-v1', 'ok': True,
        'local_only': True, 'actual_uid': os.getuid(), 'remote_submitted': False, 'Main_commands': 0,
        'existing_unchanged_worker': WORKER, 'plan': plan_pin, 'request': request_pin, 'packet': packet_pin,
        'source_contract_index': index_pin, 'execution_prerequisites': prerequisites_pin,
        'original_declared_request_mutation': mutation, 'declared_click_or_set_text_operations': 0,
        'declared_selector_fields': 0, 'new_distinct_nonces': 3, 'known_previous_plans': old_plan_pins,
        'old_close_button_not_replayed': True, 'current_page_or_search_operation_not_preclaimed': True,
        'original_case_UNKNOWN_not_rewritten_or_automatically_unlocked': True,
        'future_click_or_Chinese_input_packet_created': False, 'production_ready': False}
    write('LOCAL_PREPARATION_PROOF.json', json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    rows = [{'path': path.name, **pin(path.read_bytes())} for path in sorted(HERE.iterdir()) if path.is_file()]
    write('SOURCE_PINS.json', json.dumps({'schema': 'pocket4-readonly-data-request-closure-v1',
        'prepared_not_submitted': True, 'files': rows, 'private_UI_raw_included': False,
        'root_dispatch_after_actual_Stage_B_required': True}, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps(proof, sort_keys=True))


if __name__ == '__main__':
    main()
