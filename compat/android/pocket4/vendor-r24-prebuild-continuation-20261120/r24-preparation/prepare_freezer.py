#!/usr/bin/python3
"""Assemble a source-only R24 freezer while retaining all eleven old readers."""
from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'r23-preparation'
REVIEW = HERE.parent / 'r24-independent-review/SOURCE-INDEPENDENT-REVIEW.json'
READERS = ('need', 'f9', 'read', 'pinned', 'check', 'decode', 'document',
           'same_source_snapshot', 'module', 'write', 'save')


def pin(path):
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def definitions(text):
    lines = text.splitlines(keepends=True)
    return {node.name: ''.join(lines[node.lineno-1:node.end_lineno])
            for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}


def create(path, body):
    with path.open('xb') as output:
        output.write(body)


def main():
    assert pin(REVIEW) == (3238, '1eee7c9c1a25dd442c49f970cb386320d31e3273ffc8e95a165c8a33a5cd7994')
    create(HERE/'SOURCE-INDEPENDENT-REVIEW.json', REVIEW.read_bytes())
    before = (PREVIOUS/'freeze_r23.py').read_text()
    readers = definitions(before)
    names = ('r23_prebuild_admission.py', 'R23-PREBUILD-ACTUAL-CONTROLS.json',
             'test_r23_prebuild_actual.py', 'R23-PREBUILD-HELPER-INPUTS.json',
             'R23-ACTUAL-FILE-INFO.json', 'R23-PREBUILD-HELPER-HANDOFF.json',
             'SOURCE-INDEPENDENT-REVIEW.json', 'SOURCE-CONSERVATION.json',
             'R24-BOOTSTRAP-ADMISSION.py', 'source-r24-template.py',
             'outer-r24-template.py', 'CLIENTS-RAW.json', 'prepare_candidates.py')
    pins = {name: pin(HERE/name) for name in names}
    bootstrap = ast.parse((HERE/'R24-BOOTSTRAP-ADMISSION.py').read_text())
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in bootstrap.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in ('R24_CLIENTS', 'R24_EXTRA_TARGETS')}
    header = '''"""Freeze R24 from complete actual R23/R22 resource refusals; no build or source locks."""
from pathlib import Path
import ast
import hashlib
import json
import os
import resource
import signal
import stat
import sys
import types
sys.dont_write_bytecode = True
ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
PREP = Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
STAGE = Path('/home/qq/work/p4-r24-controller-preparation-20261120-3b9d-r1')
DEST = ROOT / 'control/vendor-build-20261120-9907-r24'
R23 = ROOT / 'control/vendor-build-20261120-9907-r23'
CURRENT = {'tree':'fd0ef624e436d1eb5c8d2c4083335088811a6a42','files':2367,'bytes':45262277}
INDEPENDENT_FREEZER_REVIEW_PIN = None
'''
    header += 'SOURCE_INPUT_PINS = ' + repr(pins) + '\n'
    header += 'CLIENT_ROSTER = ' + repr(constants['R24_CLIENTS']) + '\n'
    header += 'EXTRA_TARGETS = ' + repr(constants['R24_EXTRA_TARGETS']) + '\n\n'
    candidate = header + '\n\n\n'.join(readers[name] for name in READERS) + '\n\n\n'
    candidate += (HERE/'FREEZE-MAIN.py').read_text()
    after = definitions(candidate)
    assert all(after[name] == readers[name] for name in READERS)
    assert candidate.count('INDEPENDENT_FREEZER_REVIEW_PIN = None') == 1
    compile(candidate, 'freeze_r24_template.py', 'exec')
    create(HERE/'freeze_r24_template.py', candidate.encode())
    report = {'schema': 'p4-r24-freezer-source-conservation-v1',
        'source_only': True, 'host_execution': False, 'build_started': False,
        'source_locks_acquired': False, 'runtime_qualified': False, 'production_ready': False,
        'base': {'path': str(PREVIOUS/'freeze_r23.py'), 'pin': pin(PREVIOUS/'freeze_r23.py')},
        'candidate': {'path': str(HERE/'freeze_r24_template.py'), 'pin': pin(HERE/'freeze_r24_template.py')},
        'eleven_original_reader_function_bodies_byte_identical': list(READERS),
        'exact_staged_input_count': len(pins), 'actual_completed_client_count': 6,
        'future_preflight_output_in_inputs': False, 'independent_review_pin_unfrozen': True}
    create(HERE/'FREEZER-CONSERVATION.json', (json.dumps(report, indent=2, sort_keys=True)+'\n').encode())
    print(json.dumps(report))


if __name__ == '__main__':
    main()
