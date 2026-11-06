#!/usr/bin/env python3
"""Local-only assembly; no target, subprocess, Git or network operation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ROOT = '/home/alex/work/pocket4-beike-partial-case-runtime-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path, length, digest):
    raw = (PROJECT / path).read_bytes()
    assert len(raw) == length and sha(raw) == digest, path
    return raw


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def definition(raw, name):
    text = raw.decode(); tree = ast.parse(text)
    found = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    assert len(found) == 1, name
    node = found[0]
    return ''.join(text.splitlines(True)[node.lineno - 1:node.end_lineno]).rstrip() + '\n'


def main():
    ui = pin('successor_qa/reusable_owned_ui_r1/owned_ui_request_once.py', 25377,
             'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38')
    host = pin('successor_qa/partial_case_proof_r1/candidate-r1/verify_partial_case_host.py', 27116,
               'afd9a9410051a4e72e4f5c7e9434bfa60b592fdb02672e7d1df1b3bd8d1ecd34')
    host_stdout = pin('successor_qa/partial_case_proof_r1/candidate-r1/actual/stdout.original.jsonl', 3405,
                      '0033cfad5c04b9ed1b5ff8691c59a983ae790ed35a91282fc916a0c197240c4e')
    host_terminal = pin('successor_qa/partial_case_proof_r1/candidate-r1/actual/terminal.original.json', 731,
                        '4c755da48c16bdca5c577ab528ca21e43f60cd776f378a5fbba09e1fd866a351')
    old_stage = pin('successor_qa/partial_case_proof_r1/candidate-r1/stage_verify_host_once.py', 6215,
                   '9819ce596773c1b66bb45335d07e2c4a6d777c0e9566cb9939fc40fc12ff35ed')
    inputs = json.loads((PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/inputs.json').read_bytes())
    assert sha(canonical(inputs) + b'\n') == '2bb7778d62d614ccd4514a2d7a573879e0fd0e01dd5046afba8a59cc4386cfce'
    stage, actual = map(json.loads, host_stdout.splitlines())
    host_root = inputs['root']
    constants = {
        'ROOT': ROOT,
        'FLOW': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe',
        'STEP': 'partial-case-runtime-proof-01',
        'CASE_STEP': 'close-and-observe-search-01',
        'OBSERVATION_STEP': 'inspect-after-search-rejection-01',
        'TASK': 878, 'HELPER_UID': 10157,
        'OPERATION': 'owned-qa-partial-case-runtime-proof',
        'CANDIDATE_SCHEMA': 'pocket4-owned-qa-partial-case-runtime-candidate-v1',
        'CHILD_SCHEMA': 'pocket4-owned-qa-partial-case-runtime-child-v1',
        'PARENT_SCHEMA': 'pocket4-owned-qa-partial-case-runtime-owned-result-v1',
        'BASE': {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py',
                 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'},
        'UI_SOURCE': {'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/owned_ui_request_once.py',
                      'bytes': 25377, 'sha256': sha(ui)},
        'HOST_SOURCE': {'path': host_root + '/verify_partial_case_host.py', 'bytes': 27116, 'sha256': sha(host)},
        'PARTIAL_SOURCE': inputs['new_core'], 'HOST_JOB': '1a1b2b679c3-fc05-7f6e',
        'HOST_STDOUT': {'path': ROOT + '/host.stdout.original.jsonl', 'bytes': len(host_stdout), 'sha256': sha(host_stdout)},
        'HOST_TERMINAL': {'path': ROOT + '/host.terminal.original.json', 'bytes': len(host_terminal), 'sha256': sha(host_terminal)},
        'HOST_STAGE': stage, 'HOST_PROOF': actual['proof'], 'OBSERVER_ARCHIVE': actual['private_observer_archive'],
        'BUILD_PATH': inputs['historical_build_receipt']['path'],
        'BUILD_FILE_VERSION': inputs['historical_build_receipt_owner_observed']['file_version'],
        'APK_SHA': '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9',
        'RECORDER_ROOT': '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder',
    }
    request = {'schema': 'pocket4-fixed-partial-case-runtime-only-request-v1', 'flow': constants['FLOW'],
        'step': constants['STEP'], 'operation': constants['OPERATION'],
        'original_failed_case': constants['CASE_STEP'], 'later_observation': constants['OBSERVATION_STEP'],
        'historical_proof': actual['proof'], 'historical_controller_job': constants['HOST_JOB'],
        'source_revision': 'stage-a-candidate-r1', 'UI_actions': 0, 'instrumentation_calls': 0,
        'permission_changes': 0, 'installs': 0, 'reconciliation_published': False,
        'original_UNKNOWN_retained': True, 'stage_B_unsealed': True, 'automatic_retry': False}
    request_raw = canonical(request) + b'\n'; constants['FIXED_REQUEST'] = request
    header = '''#!/usr/bin/env python3
"""Stage A only: the actual partial-case history and original runtime predicates.

No compatibility publication function or UI mutation entry is provided.
The original recorder/helper/core remain frozen; a normally retired owned
child AND its separately collected durable controller terminal are required.
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
    header += '\n'.join(name + ' = ' + repr(value) for name, value in constants.items()) + '\nSELF = REQUEST = None\n\n\n'
    exact_names = ('need', 'sha', 'canonical', 'load_base')
    body = '\n\n'.join(definition(ui, name).rstrip() for name in exact_names) + '\n\n\n'
    write = definition(ui, 'write_once')
    narrowed = write.replace("path.parent.as_posix() in (ROOT, FLOW)", "path.parent.as_posix() == ROOT")
    assert narrowed != write and narrowed.replace("path.parent.as_posix() == ROOT", "path.parent.as_posix() in (ROOT, FLOW)") == write
    worker = (header + body + narrowed + '\n\n' + (HERE / 'runtime_body.fragment.py').read_text()).encode()
    compile(worker, str(HERE / 'runtime_stage_a_once.py'), 'exec')
    (HERE / 'runtime_stage_a_once.py').write_bytes(worker)
    (HERE / 'request.json').write_bytes(request_raw)
    (HERE / 'host.stdout.original.jsonl').write_bytes(host_stdout)
    (HERE / 'host.terminal.original.json').write_bytes(host_terminal)
    (HERE / 'write-helper-against-actual-ui.diff').write_text(''.join(difflib.unified_diff(
        write.splitlines(True), narrowed.splitlines(True), fromfile='actual-reusable-ui/write_once',
        tofile='stage-a/write_once-root-only', n=3)))
    inheritance = {'schema': 'pocket4-stage-a-source-inheritance-v1',
        'device_or_Git_actions': 0, 'original_Flow_helper_consumer_or_core_modified': False,
        'exact_copied_definitions': {name: {'source': 'successor_qa/reusable_owned_ui_r1/owned_ui_request_once.py',
            'file_sha256': sha(ui), 'definition_sha256': sha(definition(ui, name).encode()),
            'same_bytes_in_new_source': definition(ui, name) == definition(worker, name)} for name in exact_names},
        'write_helper_change': 'Only output parent narrowed from ROOT-or-FLOW to ROOT; original O_EXCL/fsync/readback unchanged.',
        'frozen_runtime_calls': {
            'qa_adapter.py': ['own_source', 'qualified_build', 'Session.__init__', 'Session.installed', 'Session.task', 'Session.foreground'],
            'recorder.py': ['Flow.__init__', 'Flow.begin(mutation=False)', 'Flow.bind', 'Flow.guard', 'Flow.close', 'lock_file', 'write_new'],
            'partial_case_core.py': ['binding_identity', 'OriginalSequence.packages', 'OriginalSequence.task',
                'OriginalSequence.foreground', 'OriginalSequence.complete(6, 8)'],
            'owned_postcondition_core.py': ['compare_held_bindings', 'installed_identity'],
            'verify_partial_case_host.py': ['collect_and_verify', 'original_terminal'],
            'prepare_beike_owned_lifetime.py': ['initialize_library', 'probe_proof', 'pin_runtime_files', 'stable_library'],
            'probe_ffi_bootstrap.py': ['run_owned_child', 'census', 'same_descriptors']},
        'fixed_source_pins': {name: value for name, value in constants.items() if name in
                             ('BASE', 'UI_SOURCE', 'HOST_SOURCE', 'PARTIAL_SOURCE')},
        'actual_host_prerequisites': {key: constants[key] for key in ('HOST_JOB', 'HOST_STDOUT', 'HOST_TERMINAL', 'HOST_PROOF')},
        'new_source': {'bytes': len(worker), 'sha256': sha(worker)},
        'request': {'bytes': len(request_raw), 'sha256': sha(request_raw)},
        'stage_B_source_or_request_created': False}
    (HERE / 'SOURCE_INHERITANCE.json').write_bytes(json.dumps(inheritance, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'state': 'LOCAL_SOURCE_ASSEMBLED_NOT_EXECUTED', 'source': inheritance['new_source'],
        'request': inheritance['request'], 'exact_definition_count': len(exact_names), 'stage_B_created': False}))


if __name__ == '__main__':
    main()
