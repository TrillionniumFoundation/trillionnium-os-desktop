#!/usr/bin/env python3
"""Local-only deterministic assembly of one new no-action candidate; no dispatch."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OUT = HERE / 'stage-a-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def checked(path, length, digest):
    raw = (PROJECT / path).read_bytes()
    assert len(raw) == length and sha(raw) == digest, path
    return raw


def pin(path, raw):
    return {'path': path, 'bytes': len(raw), 'sha256': sha(raw)}


def definition(raw, name):
    text = raw.decode(); tree = ast.parse(text)
    rows = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    assert len(rows) == 1, name
    row = rows[0]
    return ''.join(text.splitlines(True)[row.lineno - 1:row.end_lineno]).rstrip() + '\n'


def literals(raw):
    values = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def replace_exact(text, old, new, count=None):
    found = text.count(old)
    assert found > 0 and (count is None or found == count), (old, found, count)
    return text.replace(old, new)


def put(name, body):
    raw = body.encode() if isinstance(body, str) else body
    with (OUT / name).open('xb') as f:
        f.write(raw)
    assert (OUT / name).read_bytes() == raw


def main():
    old_a = checked('successor_qa/partial_case_runtime_commit_r1/stage-a-candidate-r1/runtime_stage_a_once.py',
        44063, '52784825ed50fc6178468ca80d05af7c060d48ca1da4dc2d38094b2778df02f1')
    old_partial = checked('successor_qa/partial_case_proof_r1/candidate-r1/partial_case_core.py',
        34105, '13ff07c305afcd2894b240fae52b436567784cf605623361723a86253d33fb96')
    old_host = checked('successor_qa/partial_case_proof_r1/candidate-r1/verify_partial_case_host.py',
        27116, 'afd9a9410051a4e72e4f5c7e9434bfa60b592fdb02672e7d1df1b3bd8d1ecd34')
    reader = checked('successor_qa/search_click_failure_reader_r1/read_failed_search_click.py',
        42818, '4525a588639a695b9afcbee17d7dfc6d2a9f3445ad9a678c80e6cba3dd5e4b5b')
    reader_stdout = checked('successor_qa/search_click_failure_reader_r1/actual-public/stdout.original.json',
        15496, 'c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b')
    reader_terminal = checked('successor_qa/search_click_failure_reader_r1/actual-public/status-01.original.json',
        733, 'f3b1a5e3a34df13bcfcf906c3eb3da63c90e28c174385dcc0578691a14c34d5a')
    prior_stdout = checked('successor_qa/inspect_after_partial_commit_r1/actual/stdout.original.jsonl',
        13947, '23639dfd1822118c1379e306ba45bf2a1e0d5c8b30ee660c6b50125e8b7cdf84')
    prior_terminal = checked('successor_qa/inspect_after_partial_commit_r1/actual/terminal.original.json',
        733, '8c1b239ea57641d497f59f8f417ec66c663d4290366bb4f2fa008f0460109037')
    old = literals(old_a); orig = literals(old_partial); cfg = literals(reader)['CONFIG']
    inputs = json.loads((PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1/inputs.json').read_bytes())
    diagnosis = json.loads(reader_stdout)
    assert diagnosis['private_bundle'] == {'bytes': 1102634,
        'path': '/home/alex/work/pocket4-beike-search-click-failure-evidence-20261106-r1/bundle.private.json',
        'sha256': '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4'}
    common = {
        'FLOW': old['FLOW'], 'CASE_STEP': 'search-click-after-partial-commit-01', 'TASK': 878,
        'HELPER_UID': 10157, 'SCOPE_SHA': orig['SCOPE_SHA'], 'LAUNCH_SHA': orig['LAUNCH_SHA'],
        'NATIVE_RECEIPT_SHA': orig['NATIVE_RECEIPT_SHA'], 'HELD_HELPER': orig['HELD_HELPER'],
        'CASE_SHA': cfg['case']['sha256'], 'FAILED_JOB': '1a1b30305de-fc05-8072',
        'FAILED_WIRE_SHA': 'e901b1431e5df17493158a9222f27deaf9b29b0e22f2053fcca2ae4cba1d86ae',
        'INSPECTION_WIRE_SHA': '3d5cf94834c0a7234b9b0e364ebc35abd1329defada5ee26acc42a867672854e',
        'BUNDLE': diagnosis['private_bundle'], 'POSTCONDITION': None,
        'PRIOR_JOB': '1a1b2f182c1-fc05-803d', 'UI_SOURCE': old['UI_SOURCE'],
        'PRIOR_STDOUT': pin(ROOT + '/prior-inspect.stdout.original.jsonl', prior_stdout),
        'PRIOR_TERMINAL': pin(ROOT + '/prior-inspect.terminal.original.json', prior_terminal),
        'STAT_FIELDS': ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev',
                        'st_size', 'st_mtime_ns', 'st_ctime_ns'),
    }
    core_header = '''#!/usr/bin/env python3
"""Strict, pure reparser for one actual rejected-before-dispatch owned-QA case.

The OriginalSequence grammar is inherited verbatim. No current authority,
namespace entry, instrumentation or compatibility publication is provided.
"""
import base64
import hashlib
import json
import re
import stat

'''
    core_header += '\n'.join(k + ' = ' + repr(v) for k, v in common.items()) + '\nEMPTY_SHA = hashlib.sha256(b\'\').hexdigest()\n\n\n'
    inherited_core = ('Rejected', 'need', 'sha', 'canonical', 'document', 'fixed_launch', 'binding_identity', 'OriginalSequence')
    core_parts = [definition(old_partial, name) for name in inherited_core[:-1]]
    failure = definition(old_partial, 'require_original_failed_suffix')
    failure = replace_exact(failure, "value['self_pid'] == 60531", "value['self_pid'] == 80169", 1)
    failure = replace_exact(failure, 'start == 1020981386 and finish == 1020981900',
                            'start == 1030402143 and finish == 1030402433', 1)
    core_parts += [failure, definition(old_partial, 'OriginalSequence'), definition(old_host, 'original_terminal')]
    core_extra = (HERE / 'no_action_core_extra.fragment.py').read_bytes()
    core_raw = (core_header + '\n\n'.join(core_parts) + '\n\n').encode() + core_extra
    compile(core_raw, ROOT + '/no_action_core.py', 'exec')

    constants = {k: old[k] for k in ('BASE', 'UI_SOURCE', 'BUILD_PATH', 'BUILD_FILE_VERSION', 'APK_SHA', 'RECORDER_ROOT')}
    constants.update(ROOT=ROOT, FLOW=common['FLOW'], STEP='no-action-runtime-proof-01',
        CASE_STEP=common['CASE_STEP'], OBSERVATION_STEP=None, TASK=878, HELPER_UID=10157,
        FAILED_JOB=common['FAILED_JOB'], OPERATION='owned-qa-no-action-runtime-proof',
        CANDIDATE_SCHEMA='pocket4-owned-qa-no-action-runtime-candidate-v1',
        CHILD_SCHEMA='pocket4-owned-qa-no-action-runtime-child-v1',
        PARENT_SCHEMA='pocket4-owned-qa-no-action-runtime-owned-result-v1',
        PARTIAL_SOURCE=pin(ROOT + '/no_action_core.py', core_raw),
        READER_SOURCE=pin(ROOT + '/read_failed_search_click.frozen.py', reader),
        HOST_SOURCE=pin(ROOT + '/read_failed_search_click.frozen.py', reader),
        HOST_JOB='1a1b30c6205-fc05-8083',
        HOST_STDOUT=pin(ROOT + '/reader.stdout.original.json', reader_stdout),
        HOST_TERMINAL=pin(ROOT + '/reader.terminal.original.json', reader_terminal),
        HISTORY_BUNDLE=diagnosis['private_bundle'],
        PRIOR_STDOUT=common['PRIOR_STDOUT'], PRIOR_TERMINAL=common['PRIOR_TERMINAL'],
        TASK_SOURCE=inputs['task_source'], SOURCE_MANIFESTS=inputs['source_manifests'])
    manifest = json.loads((PROJECT / 'successor_qa/reconstructed/source-generation-r2/helper/SOURCE_PINS.json').read_bytes())
    java_rel = 'src/org/droidloom/qa/successor/p8f89f253350ba2fa/r1/ActionRunner.java'
    constants['ACTION_SOURCE'] = {'path': str(Path(inputs['source_manifests']['helper']['path']).parent / java_rel),
                                  **manifest['files'][java_rel]}
    request = {'schema': 'pocket4-fixed-no-action-runtime-only-request-v1', 'flow': constants['FLOW'],
        'step': constants['STEP'], 'operation': constants['OPERATION'], 'original_failed_case': common['CASE_STEP'],
        'original_failed_controller': common['FAILED_JOB'], 'private_original_bundle': common['BUNDLE'],
        'history_reader_job': constants['HOST_JOB'], 'independent_later_observer_available': False,
        'source_revision': 'stage-a-candidate-r1', 'UI_actions': 0, 'instrumentation_calls': 0,
        'permission_changes': 0, 'installs': 0, 'reconciliation_published': False,
        'original_UNKNOWN_retained': True, 'stage_B_unsealed': True, 'automatic_retry': False}
    constants['FIXED_REQUEST'] = request
    header = '''#!/usr/bin/env python3
"""Stage A: strictly prove this old click was rejected before dispatch.

Reparse the actual failure, keep FAILED/UNKNOWN, and run only the original
two readonly helper/task/foreground rounds. There is no publish function.
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
    header += '\n'.join(k + ' = ' + repr(v) for k, v in constants.items()) + '\nSELF = REQUEST = None\n\n\n'
    new_history = (HERE / 'history.fragment.py').read_bytes()
    substitutions = {'actual_host_gate', 'history_context', 'recheck_history'}
    functions = []
    old_names = [n.name for n in ast.parse(old_a).body if isinstance(n, ast.FunctionDef)]
    for name in old_names:
        if name in substitutions:
            functions.append(definition(new_history, name)); continue
        body = definition(old_a, name)
        body = body.replace('HOST_PROOF', 'HISTORY_BUNDLE')
        body = body.replace('original_historical_proof', 'original_private_bundle')
        body = body.replace("'historical_proof'", "'private_original_bundle'")
        body = body.replace('historical_proof=HISTORY_BUNDLE', 'private_original_bundle=HISTORY_BUNDLE')
        body = body.replace("'host-historical-proof.json'", "'no-action-history.json'")
        body = body.replace("'host-controller.stdout.original.jsonl'", "'history-reader.stdout.original.json'")
        body = body.replace("'host-controller.terminal.original.json'", "'history-reader.terminal.original.json'")
        body = body.replace("('case_binding', 'observer_binding')", "('case_binding',)")
        body = body.replace('pocket4-owned-qa-stage-a-step-result-v1', 'pocket4-owned-qa-no-action-stage-a-step-result-v1')
        if name == 'child':
            body = replace_exact(body, "'later_observation': OBSERVATION_STEP,", "'later_observation': None,\n            'independent_later_observer_available': False,\n            'business_postcondition_observed': False,\n            'helper_requested_click_dispatch_attempted': False,\n            'no_action_history_sha256': sha(context['proof_raw']),", 1)
        if name == 'candidate_gate':
            body = replace_exact(body, "value.get('later_observation') == OBSERVATION_STEP and", "value.get('later_observation') is None and\n         value.get('independent_later_observer_available') is False and\n         value.get('business_postcondition_observed') is False and\n         value.get('helper_requested_click_dispatch_attempted') is False and\n         re.fullmatch('[0-9a-f]{64}', value.get('no_action_history_sha256', '')) and", 1)
        if name == 'parent':
            anchor = 'candidate_gate(candidate, SELF, REQUEST)'
            addition = '''candidate_gate(candidate, SELF, REQUEST)
        proof_raw, _ = base.read(FLOW + '/steps/' + STEP + '/no-action-history.json')
        need(sha(proof_raw) == candidate['no_action_history_sha256'], 'ACTUAL_NEW_NO_ACTION_HISTORY_COPY_PIN')
        history = partial.document(proof_raw)
        need(history.get('schema') == 'pocket4-owned-qa-rejected-before-dispatch-history-v1' and
             history.get('original_case') == CASE_STEP and history.get('original_case_outcome_unknown') is True and
             history.get('helper_requested_click_dispatch_attempted') is False and
             history.get('independent_later_observer_available') is False and
             history.get('business_postcondition_observed') is False,
             'NO_ACTION_TYPED_HISTORY_DOES_NOT_MANUFACTURE_A_POSTCONDITION')'''
            body = replace_exact(body, anchor, addition, 1)
        functions.append(body)
    functions.insert(old_names.index('history_context'), definition(new_history, 'original_directory_identity'))
    original_entry = old_a.decode().split("if __name__ == '__main__':\n")
    assert len(original_entry) == 2
    entry = "if __name__ == '__main__':\n" + original_entry[1]
    worker = (header + '\n\n'.join(functions) + '\n\n' + entry).encode()
    compile(worker, ROOT + '/runtime_stage_a_once.py', 'exec')
    OUT.mkdir(mode=0o700, exist_ok=False)
    for name, body in {'runtime_stage_a_once.py': worker, 'no_action_core.py': core_raw,
        'read_failed_search_click.frozen.py': reader, 'request.json': canonical(request) + b'\n',
        'reader.stdout.original.json': reader_stdout, 'reader.terminal.original.json': reader_terminal,
        'prior-inspect.stdout.original.jsonl': prior_stdout, 'prior-inspect.terminal.original.json': prior_terminal}.items():
        put(name, body)
    put('worker-against-actual-partial-stage-a.diff', ''.join(difflib.unified_diff(old_a.decode().splitlines(True),
        worker.decode().splitlines(True), fromfile='actual-partial-stage-a', tofile='new-no-action-stage-a', n=3)))
    put('failure-wire-against-actual-partial.diff', ''.join(difflib.unified_diff(
        definition(old_partial, 'require_original_failed_suffix').splitlines(True), failure.splitlines(True),
        fromfile='actual-partial-failure-wire', tofile='this-exact-no-action-failure-wire', n=3)))
    exact_a = {name: sha(definition(worker, name).encode()) for name in old_names
               if definition(worker, name) == definition(old_a, name)}
    inheritance = {'schema': 'pocket4-no-action-stage-a-inheritance-v1',
        'original_source_modified': False, 'device_calls': 0,
        'actual_stage_a': {'bytes': len(old_a), 'sha256': sha(old_a)},
        'exact_stage_a_definitions': exact_a,
        'exact_original_sequence_methods': [n.name for n in ast.parse(definition(old_partial, 'OriginalSequence')).body[0].body
                                             if isinstance(n, ast.FunctionDef)],
        'exact_core_definitions': {name: sha(definition(core_raw, name).encode()) for name in inherited_core},
        'original_sequence_same_bytes': definition(core_raw, 'OriginalSequence') == definition(old_partial, 'OriginalSequence'),
        'failure_wire_changes': 'Only actual helper PID and actual start/finish constants; exact new wire hash is separately pinned.',
        'original_entry_SystemExit_and_explicit_modes_same_bytes': True,
        'new_runtime_source': pin(ROOT + '/runtime_stage_a_once.py', worker),
        'new_core_source': pin(ROOT + '/no_action_core.py', core_raw),
        'no_action_scope': common['CASE_STEP'], 'stage_B_sealed': False}
    put('SOURCE_INHERITANCE.json', json.dumps(inheritance, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'state': 'LOCAL_NO_ACTION_STAGE_A_ASSEMBLED_NOT_RUN',
        'worker': inheritance['new_runtime_source'], 'core': inheritance['new_core_source'],
        'exact_original_stage_a_definitions': len(exact_a), 'stage_B_sealed': False}))


if __name__ == '__main__':
    main()
