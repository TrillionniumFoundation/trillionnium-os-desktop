#!/usr/bin/env python3
"""Prepare one data-only search click + independent inspect; no Main execution."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import types

HERE = Path(__file__).resolve().parent
QA_ROOT = HERE.parent
PROJECT = QA_ROOT.parent
PRIVATE = PROJECT.parent / 'p4_private_ui/beike-inspect-after-partial-commit-reader-r1/stdout.original.json'
PRIVATE_BYTES = 243205
PRIVATE_SHA = '6a1c770b862a47a5a64021392e58e9b36a9bc583a261a7412333bf9355513790'
STEP = 'search-click-after-partial-commit-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def put(name, raw):
    path = HERE / name
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    assert path.read_bytes() == raw
    return pin(path)


def main():
    old_generator_path = QA_ROOT / 'explore_home_search_case_r1/prepare_case_packet.py'
    original = exact(old_generator_path, 9788,
        'b58863c0460fcb351f04836cbd73c1992fc5e3bebb60839c57f9006620f7aef9')
    parent = types.ModuleType('existing_local_prepare_functions_only')
    parent.__file__ = str(old_generator_path)
    exec(compile(original, str(old_generator_path), 'exec'), parent.__dict__)
    canonical = parent.canonical
    terminal_path = QA_ROOT / 'inspect_after_partial_commit_reader_r1/actual-public/terminal.original.json'
    terminal_raw = exact(terminal_path, 735,
        '7b49af035e02661b7d4fb0044892c1ed84d5e2a48f1d81605e4122d44df4a369')
    public_path = QA_ROOT / 'inspect_after_partial_commit_reader_r1/actual-public/ACTUAL_READER_SUMMARY.derived.json'
    public = json.loads(exact(public_path, 1522,
        '89ae66bfa5ce1395af28edd326ded69b000bd3124f8c462c5fa244e084f4a46d'))
    terminal = json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1b2f97545-fc05-8050' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ('audit_recorded','output_complete','output_durable','terminal_publication_confirmed'))
    assert all(terminal[key] is False for key in ('automatic_retry','timed_out','cancelled'))
    assert terminal['log_bytes'] == {'stdout': {'seen': PRIVATE_BYTES, 'stored': PRIVATE_BYTES}, 'stderr': {'seen': 0, 'stored': 0}}
    assert terminal['log_errors'] == {'stdout': None, 'stderr': None}
    assert terminal['log_synced'] == {'stdout': True, 'stderr': True}
    assert terminal['log_truncated'] == {'stdout': False, 'stderr': False}
    # The private body stays outside the Git tree. Only exact hashes/counts and
    # the already identified public Search selector are copied into outputs.
    observed = json.loads(exact(PRIVATE, PRIVATE_BYTES, PRIVATE_SHA))
    assert public['private_stdout'] == {'bytes': PRIVATE_BYTES, 'sha256': PRIVATE_SHA}
    assert observed['ok'] is True and observed['flow'] == parent.FLOW and observed['historical_task'] == 878
    assert observed['historical_job'] == '1a1b2f182c1-fc05-803d'
    assert observed['step'] == 'inspect-after-partial-commit-01'
    assert observed['nonce'] == '9cd6bf0cba03a95b40b7197ba6df22af'
    assert observed['wire_sha256'] == 'ee9a3d6b4e89147c4df2b6c8675f5cc35b01e79f5e9f0da6bd3a6273fd1bfee0'
    assert observed['original_files_count'] == 21 and observed['original_files_bytes'] == 600424
    assert observed['whole_process_fd_identities_unchanged'] is True
    assert observed['all_file_bytes_and_stat_rechecked'] is True
    assert observed['complete_original_tree'] is True and observed['all_original_node_count'] == 245
    assert observed['inspection_tree_sha256'] == public['historical_inspection_tree_sha256']
    assert observed['inspection_window_sha256'] == public['historical_inspection_window_sha256']
    nodes = observed['selected_visible_nonpassword_nodes']
    assert len(nodes) == 228 and observed['omitted_invisible_or_password_nodes'] == 17
    selector = {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
                'class': 'android.widget.TextView', 'text': '搜索'}
    assert public['unique_observed_search_selector'] == selector and public['selector_fields_untruncated'] is True
    matches = [node for node in nodes if node.get('package') == 'com.lianjia.beike' and
        all(node.get(key) == value and node.get(key + '_truncated') is False for key, value in selector.items()) and
        node.get('visible') is True and node.get('password') is False and
        node.get('enabled') is True and node.get('clickable') is True]
    assert len(matches) == 1 and matches[0]['node_sha256'] == '794068244e4f4112309b9f08ee56a9f09225dc20cad32676728de484668f7d97'
    assert not any(node.get('editable') is True for node in nodes)

    adapter = parent.load('reconstructed/source-generation-r2/helper/qa_adapter.py', 29378,
        'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c', 'existing_plan_validator_only')
    qa = parent.load('reconstructed/source-generation-r2/helper/qa_contract.py', 52359,
        'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e', 'existing_wire_policy_only')
    cases = parent.load('reconstructed/source-generation-r2/helper/run_case.py', 9595,
        'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b', 'existing_case_validator_only')
    core = parent.load('owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', 28714,
        '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41', 'existing_json_parser_only')
    wrapper = parent.load('reusable_owned_ui_r1/owned_ui_request_once.py', parent.UI['bytes'],
        parent.UI['sha256'], 'existing_request_validator_only')
    previous_data_paths = [QA_ROOT / path for path in (
        'explore_home_search_case_r1/case.review-only.json',
        'inspect_after_partial_commit_r1/inspect.review-only.json',
        'inspect_after_search_rejection_r1/inspect.review-only.json',
        'reusable_owned_ui_r1/inspect-new-session-01.plan.json')]
    prior_nonces = set()
    def collect(value):
        if isinstance(value, dict):
            if 'nonces' in value:
                prior_nonces.update(value['nonces'].values())
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for path in previous_data_paths:
        collect(json.loads(path.read_bytes()))
    new_nonces = set()
    def nonce():
        value = secrets.token_hex(16)
        assert value not in prior_nonces and value not in new_nonces
        new_nonces.add(value)
        return value
    click = {'schema': 1, 'operation': 'click', 'selector': selector,
             'nonces': {phase: nonce() for phase in ('before','inspect','action','after')}}
    inspect = {'schema': 1, 'operation': 'inspect',
               'nonces': {phase: nonce() for phase in ('before','inspect','after')}}
    condition = {'text': '搜索', 'class': 'android.widget.TextView', 'enabled': True}
    case = {'schema': 'pocket4-owned-scoped-qa-case-v1', 'name': 'beike-search-click-observe-01',
            'steps': [{'plan': click, 'post_inspection': inspect, 'postcondition': condition}]}
    assert len(new_nonces) == 7 and cases.validate_case(case, adapter, qa) == case
    assert len(case['steps']) == 1 and click['operation'] == 'click' and inspect['operation'] == 'inspect'
    body = canonical(case) + b'\n'
    request = {'schema': 'pocket4-fixed-beike-owned-ui-request-v1', 'kind': 'case',
               'step': STEP, 'payload_text': body.decode(), 'payload_sha256': sha(body)}
    request_raw = canonical(request) + b'\n'
    parsed_request, parsed_body, parsed_case, mutation = wrapper.declared_request(request_raw, core, adapter, qa, cases)
    assert parsed_request == request and parsed_body == body and parsed_case == case and mutation is True
    old_packet_path = QA_ROOT / 'explore_home_search_case_r1/process-request.review-only.json'
    old_packet = json.loads(exact(old_packet_path, 2899,
        '955cd7c32d7db3f17363613acbbeef5e4c8f7a5026914f514acbc32de5aedd63'))
    packet = dict(old_packet)
    packet['args'] = list(old_packet['args'])
    packet['args'][packet['args'].index('--request-sha256') + 1] = sha(request_raw)
    packet['args'][packet['args'].index('--request-bytes') + 1] = str(len(request_raw))
    packet['stdin'] = request_raw.decode()
    packet['idempotency_key'] = 'pocket4-beike-task878-search-click-after-partial-commit-case-r1-20261106'
    assert packet['args'][:10] == old_packet['args'][:10]
    assert {k:v for k,v in packet.items() if k not in ('args','stdin','idempotency_key')} == {
        k:v for k,v in old_packet.items() if k not in ('args','stdin','idempotency_key')}
    case_pin = put('case.review-only.json', body)
    request_pin = put('request.review-only.json', request_raw)
    packet_pin = put('process-request.review-only.json', json.dumps(packet, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    evidence = {
        'schema': 'pocket4-completed-inspect-search-selector-safe-provenance-v1',
        'reader_job': terminal['job_id'], 'reader_terminal': pin(terminal_path),
        'reader_public_summary': pin(public_path),
        'private_stdout': {'path': str(PRIVATE), 'bytes': PRIVATE_BYTES, 'sha256': PRIVATE_SHA,
                           'contents_copied_to_Git': False},
        'historical_inspection_job': observed['historical_job'], 'historical_task': 878,
        'historical_wire_sha256': observed['wire_sha256'],
        'historical_tree_sha256': observed['inspection_tree_sha256'],
        'historical_window_sha256': observed['inspection_window_sha256'],
        'all_nodes': 245, 'visible_nonpassword_nodes': 228, 'editable_nodes': 0,
        'exact_search_selector': selector, 'exact_eligible_match_count': 1,
        'selected_search_node_sha256': matches[0]['node_sha256'],
        'selector_fields_untruncated': True, 'all_21_files_bytes_and_stat_rechecked': True,
        'whole_process_FD_identities_unchanged': True,
        'private_UI_body_or_unrelated_node_text_exported': False,
        'selected_old_node_path_or_hash_used_as_action_authority': False,
        'new_action_still_requires_original_fresh_inspection_unique_eligible_selector': True,
        'current_action_authority': False, 'production_ready': False,
    }
    evidence_pin = put('OBSERVATION_PUBLIC_HASHES.json', json.dumps(evidence, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    boundary = {
        'schema': 'pocket4-single-search-click-independent-assertion-boundary-v1',
        'declared_UI_mutations': ['one click of the fresh unique observed Search selector'],
        'independent_post_inspection': True, 'postcondition': condition,
        'postcondition_exact_meaning': 'Exactly one fresh node in the target package is visible, nonpassword, enabled, has untruncated text Search (搜索), and untruncated class android.widget.TextView.',
        'postcondition_NOT_proven': ['navigation occurred', 'a particular new page is open',
            'a search editor exists', 'a query was entered', 'network request succeeded',
            'search results exist', 'business flow succeeded', 'whole App production readiness'],
        'valid_navigation_may_still_fail_this_assertion': True,
        'zero_or_multiple_matches': 'Original ONE_FRESH_REAL_POSTCONDITION_NODE_REQUIRED failure; no alternative selector or automatic retry.',
        'click_plan_fresh_preinspect': 'Original Session and helper select and bind a fresh eligible node; no stale node hash, coordinates or window substitute.',
        'foreground_rules': 'Original click path permits observed activity/window change while retaining exact package, owned task and helper identity. Independent inspect retains its original full foreground equality. No guard change.',
        'after_any_attempted_click': 'Original run_case preserves action outcome unknown_retained and outcome_unknown=true, even if the independent assertion passes. No automatic close replay, second click, input, or retry.',
        'subsequent_decision': 'Collect full actual command/inspection/child/FD/guard evidence; any new mutation requires the existing Flow consumer and explicit postcondition reconciliation. This data packet does not publish reconciliation.',
        'no_new_source_contract_or_security_exception': True,
        'old_close_and_failed_case_and_UNKNOWN_preserved': True,
        'new_NDK_inventory_not_qualified_by_this_case': True,
        'production_ready': False,
    }
    boundary_pin = put('POSTCONDITION_AND_UNKNOWN_BOUNDARY.json', json.dumps(boundary, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    proof = {
        'schema': 'pocket4-one-observed-search-click-data-preparation-v1', 'ok': True,
        'existing_worker': parent.UI, 'flow': parent.FLOW, 'task': 878, 'step': STEP,
        'case': case_pin, 'request': request_pin, 'packet': packet_pin,
        'observed_selector_evidence': evidence_pin, 'postcondition_boundary': boundary_pin,
        'original_case_validator_passed': True, 'original_request_validator_passed': True,
        'original_worker_adapter_case_core_guard_sources_modified': False,
        'new_source_stage_or_runner': False, 'case_entries': 1, 'declared_clicks': 1,
        'independent_post_inspections': 1, 'distinct_new_nonces': 7,
        'distinct_from_previous_fixed_plan_and_case_nonces': True,
        'old_close_replayed': False, 'set_text_steps': 0, 'Chinese_input_performed': False,
        'postcondition_unverified_independent_assertion_only': True,
        'postcondition_proves_navigation_or_business': False,
        'original_UNKNOWN_rewritten': False, 'reconciliation_published': False,
        'remote_submitted': False, 'Main_commands': 0,
        'local_private_source_read': True, 'private_body_copied_to_Git': False,
        'actual_local_uid': os.getuid(), 'production_ready': False,
    }
    proof_pin = put('LOCAL_PREPARATION_PROOF.json', json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    inputs = [pin(path) for path in [old_generator_path, old_packet_path, terminal_path, public_path,
        *previous_data_paths, QA_ROOT / 'reconstructed/source-generation-r2/helper/qa_adapter.py',
        QA_ROOT / 'reconstructed/source-generation-r2/helper/qa_contract.py',
        QA_ROOT / 'reconstructed/source-generation-r2/helper/run_case.py',
        QA_ROOT / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py',
        QA_ROOT / 'reusable_owned_ui_r1/owned_ui_request_once.py']]
    pins = {'schema': 'pocket4-one-search-click-data-source-pins-v1', 'inputs': inputs,
        'private_input_reference_not_repository_member': evidence['private_stdout'],
        'outputs': [case_pin, request_pin, packet_pin, evidence_pin, boundary_pin, proof_pin, pin(Path(__file__))],
        'remote_submitted': False, 'runtime_source_modified': False, 'private_UI_body_included': False,
        'based_on_checkpoint': 'c79a17933966b5c61c76adfb0b4995f2ce5b7c25'}
    pins_pin = put('SOURCE_PINS.json', json.dumps(pins, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'case': case_pin, 'request': request_pin, 'packet': packet_pin, 'pins': pins_pin,
                      'proof': proof_pin, 'boundary': boundary_pin,
                      'declared_clicks': 1, 'remote_submitted': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
