#!/usr/bin/env python3
"""Small local-only controls for unbound templates and immutable source inputs."""
import errno
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent


def need(test, message):
    if not test:
        raise RuntimeError(message)


def load(name, path):
    mod = types.ModuleType(name); mod.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), mod.__dict__)
    return mod


def census():
    out = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name); st = os.fstat(fd)
            out[name] = [os.readlink('/proc/self/fd/' + name), st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid]
        except OSError as exc:
            if exc.errno not in (errno.ENOENT, errno.EBADF):
                raise
    return out


def rejected(call, code):
    try:
        call()
    except RuntimeError as exc:
        need(str(exc) == code, 'UNEXPECTED_REJECTION:' + str(exc))
    else:
        raise RuntimeError('EXPECTED_REFUSAL_MISSING:' + code)


def main():
    before = census(); cases = []
    prep = load('fixed_local_preparation', HERE / 'prepare_unsealed.py')
    contract = load('pure_future_scope_relation', HERE / 'scope49_contract.py')
    originals = {key: prep.source(key) for key in prep.PINS}
    plan = json.loads((HERE / 'PLAN.unsealed.json').read_bytes())
    original_partition = json.loads(originals['original_partition'])
    need(len(plan['batches']) == 14 and plan['target_packages'][-1] == 'com.example.ndk_tests' and
         len(plan['target_packages']) == len(set(plan['target_packages'])) == 46, 'FIXED46_PARTITION')
    need(all(row['targets'] == old['packages'] and row['batch'] == old['batch']
             for row, old in zip(plan['batches'][:13], original_partition['batches'])), 'ORIGINAL13_CHANGED')
    need(sum(len(row['Android_commands']) for row in plan['batches']) == 106 and
         plan['packets_sealed'] == plan['claims_created'] == plan['remote_jobs_submitted'] == 0 and
         plan['actual_bound_scope'] is None and plan['current_new_helper_UID'] is None and
         all(row['target_identities'] is None and row['process_request'] is None for row in plan['batches']),
         'MISSING_ACTUAL49_MUST_NOT_BE_FILLED')
    cases.append({'name': 'actual46_original13_plus_NDK14_unbound_inputs', 'passed': True})

    for name in ('worker.normal.template.py', 'worker.microg.template.py'):
        path = HERE / name; raw = path.read_bytes()
        rejected(lambda: exec(compile(raw, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)}),
                 'UNSEALED_TEMPLATE_NOT_AN_EXECUTABLE_REQUEST')
        mod = load('unsealed_' + name.replace('.', '_'), path)
        need(mod.SOURCE_SEALED is False and mod.APP_SCOPE is None and mod.PACKAGES is None and
             mod.NEW_HELPER is None and mod.TRANSPORT is None and mod.OUTPUT is None, 'UNSEALED_RUNTIME_BINDINGS')
    cases.append({'name': 'both_real_template_entrypoints_refuse_before_Main', 'passed': True})

    microg = load('actual_budget_functions_in_template', HERE / 'worker.microg.template.py')
    commands = microg.CORRECTION_COMMANDS
    need(microg.capture_limits_for(1, commands[0]) == {'stdout': 262144, 'stderr': 262144} and
         microg.capture_limits_for(2, commands[1]) == {'stdout': 2097152, 'stderr': 262144} and
         microg.capture_limits_for(3, commands[2]) == {'stdout': 262144, 'stderr': 262144}, 'PRECISE_ACTUAL_MICROG_BUDGET')
    rejected(lambda: microg.capture_limits_for(2, ['/system/bin/cmd', 'package', 'dump-package', 'com.lianjia.beike']),
             'EXACT_READ_COMMAND_SUFFIX_REQUIRED')
    rejected(lambda: microg.capture_limits_for(4, commands[1]), 'EXACT_THREE_READ_COMMANDS_ONLY')
    high = [(row['batch'], index) for row in plan['batches'] for index, limits in enumerate(row['stream_limits'], 1)
            if limits['stdout'] != 262144]
    need(high == [(2, 2)] and all(limits['stderr'] == 262144 for row in plan['batches'] for limits in row['stream_limits']),
         'NO_OTHER_CAP_CHANGED')
    cases.append({'name': 'only_microG_exact_second_stdout_2MiB', 'passed': True, 'children_spawned': 0})

    old48 = originals['prior_scope48']
    real_old_pin = {'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json',
                   'bytes': len(old48), 'sha256': hashlib.sha256(old48).hexdigest()}
    rejected(lambda: contract.validate_preserved49(old48, old48, real_old_pin, None, None),
             'ACTUAL49_REQUIRED_CURRENT48_IS_NOT_A_SUBSTITUTE')
    rejected(lambda: contract.validate_preserved49(old48, None, None, None, None),
             'ACTUAL_PINNED_FUTURE_SCOPE_INPUT_REQUIRED')
    rejected(lambda: contract.decode(b'{"x":1,"x":2}'), 'DUPLICATE_JSON_KEY')
    need(all(prep.source(key) == raw for key, raw in originals.items()), 'FROZEN_INPUT_OR_OLD_STOP_CHANGED')
    cases.append({'name': 'actual_post_ZBJ48_cannot_substitute_future49_old_STOP_unchanged', 'passed': True,
                  'future49_positive_qualification_tested': False})
    after = census(); need(before == after, 'LOCAL_FD_IDENTITIES_CHANGED')
    print(json.dumps({'schema': 'pocket4-fixed46-unsealed-local-controls-v1', 'ok': True, 'uid': os.getuid(), 'euid': os.geteuid(),
        'cases': cases, 'case_count': len(cases), 'before': before, 'after': after,
        'whole_process_FD_identities_unchanged': True, 'Main_or_remote_actions': 0, 'subprocesses_spawned': 0,
        'actual_new_scope_or_new_helper_qualified': False, 'packets_or_claims_created': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
