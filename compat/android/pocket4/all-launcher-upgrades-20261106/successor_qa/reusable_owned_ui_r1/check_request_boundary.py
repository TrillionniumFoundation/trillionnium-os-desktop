#!/usr/bin/env python3
"""Local request parsing with exact frozen policy functions; no Android calls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / 'reconstructed/source-generation-r2/helper'


def load(path, expected, name):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def census():
    values = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            info = os.fstat(int(name)); link = os.readlink('/proc/self/fd/' + name)
            values[name] = (link, info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return values


def main():
    before = census()
    worker_path = HERE / 'owned_ui_request_once.py'
    worker = load(worker_path, hashlib.sha256(worker_path.read_bytes()).hexdigest(), 'new_definitions_only')
    core = load(HERE.parent / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py',
                '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41', 'frozen_pure_core')
    adapter = load(HELPER / 'qa_adapter.py', 'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c', 'frozen_plan_policy')
    qa = load(HELPER / 'qa_contract.py', 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e', 'frozen_qa_policy')
    cases = load(HELPER / 'run_case.py', 'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b', 'frozen_case_policy')
    raw = (HERE / 'inspect-new-session-01.request.json').read_bytes()
    request, body, payload, mutation = worker.declared_request(raw, core, adapter, qa, cases)
    assert not mutation and payload['operation'] == 'inspect' and set(payload) == {'schema', 'operation', 'nonces'}
    results = [{'name': 'new_readonly_inspect_plan_accepted', 'accepted': True}]
    bad = []
    item = copy.deepcopy(request); item['step'] = '../other-flow'; bad.append(('step_path_escape_rejected', item))
    item = copy.deepcopy(request); item['argv'] = ['cmd', 'package', 'grant']; bad.append(('extra_command_parameter_rejected', item))
    item = copy.deepcopy(request)
    wrong = {'schema': 1, 'operation': 'set_text', 'nonces': {**payload['nonces'], 'action': '1' * 32},
             'selector': {'resource_id': 'com.lianjia.beike:id/synthetic_negative_only', 'class': 'android.widget.EditText'},
             'value': 'unapproved text'}
    item['payload_text'] = json.dumps(wrong); item['payload_sha256'] = worker.sha(item['payload_text'].encode())
    bad.append(('compiled_public_text_policy_rejected', item))
    item = copy.deepcopy(request); item['kind'] = 'case'
    wrong = {'schema': 'pocket4-owned-scoped-qa-case-v1', 'name': 'negative-only', 'steps': [
        {'plan': payload, 'post_inspection': payload,
         'postcondition': {'resource_id': 'com.lianjia.beike:id/synthetic_negative_only'}}]}
    item['payload_text'] = json.dumps(wrong); item['payload_sha256'] = worker.sha(item['payload_text'].encode())
    bad.append(('original_case_nonce_reuse_rejected', item))
    for name, value in bad:
        try:
            worker.declared_request(json.dumps(value).encode(), core, adapter, qa, cases)
        except RuntimeError as error:
            results.append({'name': name, 'accepted': False, 'reason': str(error)})
        else:
            raise AssertionError(name)
    assert census() == before
    print(json.dumps({'schema': 'pocket4-fixed-ui-request-local-controls-v1', 'ok': True,
        'source_sha256': hashlib.sha256(worker_path.read_bytes()).hexdigest(), 'cases': results,
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'whole_descriptor_identities_unchanged': True,
        'original_qa_functions_called': ['validate_plan', 'validate_case', 'nonce'],
        'synthetic_negative_selectors_are_not_observed_UI_nodes': True,
        'Main_calls': 0, 'remote_calls': 0, 'UI_actions': 0}, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
