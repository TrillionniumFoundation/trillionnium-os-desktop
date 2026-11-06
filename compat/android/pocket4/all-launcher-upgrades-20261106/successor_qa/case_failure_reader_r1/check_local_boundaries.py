#!/usr/bin/env python3
"""Small host-only controls; no fake root or fabricated runtime success."""
import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent
QA = HERE.parent


def module(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


reader = module(HERE / 'read_failed_case.py', 'local_reader_definitions_only')
core = module(QA / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', 'pure_original_core')
case = json.loads((QA / 'explore_home_search_case_r1/case.review-only.json').read_bytes())
rows = reader.phases(case)
before = reader.census()
checks = []

original, life = reader.validate_actual(core)
assert original['ok'] is False and original['outcome_unknown'] is True and life['returncode'] == 1
assert len(original['steps']) == 1 and original['steps'][0]['index'] == 0
checks.append({'name': 'actual_failed_controller_and_case_remain_failed', 'passed': True})

bad = ['command-039.stdout', 'transport-051.intent.json', 'observation.png', '../intent.json',
       '00000000000000000000000000000000.request.json', 'other-flow/result.json']
for name in bad:
    try:
        reader.names_checked(['intent.json', 'result.json', 'held-main-binding.json', name], rows)
    except RuntimeError as error:
        assert str(error) == 'ONLY_FIXED_CASE_STEP_FILENAMES_NO_OTHER_CONTENT'
    else:
        raise AssertionError('unexpected file name admitted')
checks.append({'name': 'unrelated_ui_path_nonce_and_beyond_case_counts_rejected', 'passed': True, 'negative_names': len(bad)})

saved = copy.deepcopy(reader.CONFIG)
try:
    reader.CONFIG['actual_stdout_base64'] = reader.CONFIG['actual_stdout_base64'][:-4] + 'AAAA'
    try:
        reader.validate_actual(core)
    except RuntimeError as error:
        assert str(error) == 'EMBEDDED_ORIGINAL_CONTROLLER_EVIDENCE_BYTES'
    else:
        raise AssertionError('changed original controller evidence admitted')
finally:
    reader.CONFIG = saved
checks.append({'name': 'changed_actual_original_bytes_rejected', 'passed': True})

base = module(QA / 'owned_cleanup_r1/cleanup_owned_task_once.py', 'frozen_file_reader_definitions_only')
assert os.getuid() == os.geteuid() == 1000, 'Do not fake production root controls'
with tempfile.TemporaryDirectory(prefix='pocket4-own-reader-negative-') as directory:
    path = Path(directory) / 'owned.txt'; path.write_bytes(b'owned local fixture\n')
    linked = Path(directory) / 'linked.txt'; linked.symlink_to(path.name)
    for selected in (path, linked):
        try:
            base.read(selected)
        except (RuntimeError, OSError):
            pass
        else:
            raise AssertionError('unprivileged/symlink file admitted')
        assert reader.census() == before
checks.append({'name': 'real_unprivileged_file_and_symlink_rejected_fds_closed', 'passed': True,
               'actual_uid': os.getuid(), 'root_positive_claimed': False})

assert reader.census() == before
print(json.dumps({'local_only': True, 'count': len(checks), 'checks': checks,
    'all_passed': True, 'actual_uid': os.getuid(), 'whole_process_fd_identities_unchanged': True,
    'Main_commands': 0, 'remote_submitted': False, 'Android_or_case_acceptance_claimed': False}, sort_keys=True))
