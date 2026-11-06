#!/usr/bin/env python3
"""Prepare data only for the frozen owned case entry; never execute Main."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
QA_ROOT = PROJECT / 'successor_qa'
PRIVATE = Path('/workspace/scratch/265e5bca485a/p4_private_ui/inspect878-reader-r1/stdout.private.original.json')
PRIVATE_SHA = '7dd40d2079fbfcc081cffcce9ed60308060f3fad696300d2a4cc0bdc27b1c63d'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
ROOT = '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1'
STEP = 'close-and-observe-search-01'
UI = {'path': ROOT + '/owned_ui_request_once.py', 'bytes': 25377,
      'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def write(name, raw):
    with (HERE / name).open('xb') as handle:
        handle.write(raw)
    return {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}


def load(relative, size, digest, name):
    path = QA_ROOT / relative
    raw = exact(path, size, digest)
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def main():
    # This completed private observation is read locally only. No UI tree or
    # original node strings are copied into any output or proof file below.
    observed = json.loads(exact(PRIVATE, 18671, PRIVATE_SHA))
    terminal_raw = exact(QA_ROOT / 'inspect878_reader_r1/actual-public/status-1.original.txt', 733,
                        '13b9b00fcde0170fae25383fe57cb1b54ae1c5070848f635c92946a44999a92b')
    terminal = json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1b262379a-fc05-7dd2' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[key] is False for key in ('automatic_retry', 'timed_out', 'cancelled'))
    assert terminal['log_bytes'] == {'stdout': {'seen': 18671, 'stored': 18671}, 'stderr': {'seen': 0, 'stored': 0}}
    assert observed['ok'] is True and observed['flow'] == FLOW and observed['historical_task'] == 878
    assert observed['nonce'] == '8f3efa4249d24d303984ec1887d5914b'
    assert observed['wire_sha256'] == 'cb49f560bdc90f13fa5a314019e4f2948d4c9e63e3b62571c8f0a4cc37fe4647'
    assert observed['original_files_count'] == 21 and observed['whole_process_fd_identities_unchanged'] is True
    assert observed['complete_original_tree'] is True and observed['all_original_node_count'] == 7
    nodes = observed['selected_visible_nonpassword_nodes']
    assert len(nodes) == 7 and observed['omitted_invisible_or_password_nodes'] == 0
    selector_close = {'resource_id': 'com.lianjia.beike:id/iv_close_icon', 'class': 'android.widget.ImageView'}
    close = [node for node in nodes if all(node.get(key) == value and node.get(key + '_truncated') is False
        for key, value in selector_close.items()) and node.get('visible') is True and node.get('password') is False and
        node.get('enabled') is True and node.get('clickable') is True]
    assert len(close) == 1 and close[0]['node_sha256'] == '116ff8efdb274562cb788e1a0543e714abcfebfe3e6fc666d1517e9e48fca672'
    assert not any(node.get('editable') is True or node.get('supports_set_text') is True for node in nodes)

    adapter = load('reconstructed/source-generation-r2/helper/qa_adapter.py', 29378,
        'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c', 'unchanged_plan_validator_only')
    qa = load('reconstructed/source-generation-r2/helper/qa_contract.py', 52359,
        'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e', 'unchanged_wire_policy_only')
    cases = load('reconstructed/source-generation-r2/helper/run_case.py', 9595,
        'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b', 'unchanged_case_validator_only')
    core = load('owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', 28714,
        '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41', 'unchanged_json_parser_only')
    wrapper = load('reusable_owned_ui_r1/owned_ui_request_once.py', UI['bytes'], UI['sha256'], 'unchanged_data_request_validator_only')
    # Previously observed by the root coordinator in the complete successful
    # inspect-after-close-02 tree. This is a selector proposal, not a claim that
    # the button is already visible in task 878. The original helper must find
    # it uniquely in a NEW inspection before the second declared click.
    selector_search = {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
                       'class': 'android.widget.TextView', 'text': '搜索'}
    declared_nonces = set()
    def nonce():
        value = secrets.token_hex(16)
        assert value not in declared_nonces
        declared_nonces.add(value)
        return value
    def plan(operation, selector=None):
        names = ('before', 'inspect', 'after') if operation == 'inspect' else ('before', 'inspect', 'action', 'after')
        result = {'schema': 1, 'operation': operation, 'nonces': {name: nonce() for name in names}}
        if selector is not None:
            result['selector'] = selector
        return result
    case = {'schema': 'pocket4-owned-scoped-qa-case-v1', 'name': 'beike-close-and-observe-search-01', 'steps': [
        {'plan': plan('click', selector_close), 'post_inspection': plan('inspect'),
         'postcondition': {**selector_search, 'enabled': True, 'clickable': True}},
        {'plan': plan('click', selector_search), 'post_inspection': plan('inspect'),
         'postcondition': {'text': '搜索', 'class': 'android.widget.TextView', 'enabled': True}},
    ]}
    assert len(declared_nonces) == 14
    assert cases.validate_case(case, adapter, qa) == case
    body = canonical(case) + b'\n'
    request = {'schema': 'pocket4-fixed-beike-owned-ui-request-v1', 'kind': 'case',
               'step': STEP, 'payload_text': body.decode('ascii'), 'payload_sha256': sha(body)}
    request_raw = canonical(request) + b'\n'
    parsed_request, parsed_body, parsed_case, mutation = wrapper.declared_request(request_raw, core, adapter, qa, cases)
    assert parsed_request == request and parsed_body == body and parsed_case == case and mutation is True
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', UI['path'], '--publish-and-execute',
                 '--source-sha256', UI['sha256'], '--source-bytes', str(UI['bytes']),
                 '--request-sha256', sha(request_raw), '--request-bytes', str(len(request_raw))],
        'stdin': request_raw.decode('ascii'), 'cwd': '/home/alex/work',
        'timeout_seconds': 660, 'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-close-observe-search-case-r1-20261106'}
    case_pin = write('case.review-only.json', body)
    request_pin = write('request.review-only.json', request_raw)
    packet_pin = write('process-request.review-only.json', json.dumps(packet, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    public_observation = {'schema': 'pocket4-inspect878-safe-hash-count-summary-v1', 'reader_job_id': terminal['job_id'],
        'reader_private_stdout': {'bytes': 18671, 'sha256': PRIVATE_SHA, 'contents_copied_to_Git': False},
        'reader_terminal': {'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'inspection_wire_sha256': observed['wire_sha256'], 'inspection_tree_sha256': observed['inspection_tree_sha256'],
        'inspection_window_sha256': observed['inspection_window_sha256'], 'historical_task': 878,
        'visible_nonpassword_nodes': 7, 'editable_nodes': 0, 'supports_set_text_nodes': 0,
        'selected_close_node_sha256': close[0]['node_sha256'], 'original_files_count': 21,
        'original_files_bytes': observed['original_files_bytes'], 'all_original_files_rechecked': True,
        'whole_process_fd_identities_unchanged': True, 'current_action_authority': False,
        'private_node_texts_or_raw_UI_exported': False, 'production_ready': False}
    write('OBSERVATION_PUBLIC_HASHES.json', json.dumps(public_observation, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    proof = {'schema': 'pocket4-two-observed-selector-case-preparation-v1', 'ok': True, 'actual_local_uid': os.getuid(),
        'original_case_validator_passed': True, 'original_reusable_request_validator_passed': True,
        'existing_worker': UI, 'flow': FLOW, 'task': 878, 'step': STEP,
        'case': case_pin, 'request': request_pin, 'packet': packet_pin,
        'distinct_new_nonces': 14, 'declared_clicks': 2, 'independent_post_inspections': 2,
        'set_text_steps': 0, 'Chinese_text_input_performed': False,
        'last_postcondition_is_unverified_test_assertion_only': True,
        'last_postcondition_proves_search_page_or_search_results': False,
        'unknown_outcomes_remain_unchanged': True, 'reconciliation_published': False,
        'remote_submitted': False, 'Main_commands': 0, 'production_ready': False}
    write('LOCAL_PREPARATION_PROOF.json', json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps(proof, sort_keys=True))


if __name__ == '__main__':
    main()
