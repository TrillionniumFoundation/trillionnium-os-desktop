#!/usr/bin/python3
"""Replay actual immutable R22 inputs and narrow rejection controls locally."""
from pathlib import Path
import base64
import copy
import hashlib
import json
import os
import stat
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


held = []


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    before = f9(os.fstat(fd))
    assert stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= 1024 ** 2
    with os.fdopen(os.dup(fd), 'rb') as source:
        body = source.read(1024 ** 2 + 1)
    assert len(body) == before[6] and before == f9(os.fstat(fd)) == f9(path.lstat())
    held.append((path, fd, before, body))
    return body


def main():
    module_path = HERE.parent / 'r22_prebuild_admission.py'
    module_raw = read(module_path)
    module = types.ModuleType('actual_r22_prebuild_admission')
    exec(compile(module_raw, str(module_path), 'exec'), module.__dict__)
    capture = module.decode(read(HERE / 'ACTUAL-INPUT-CAPTURE.json'))
    assert capture['all_input_bookends_equal'] is True
    assert capture['fresh_lock_ownership_observed'] is False
    names = {'worker': ROOT / 'r22-preparation/source-r22.py',
             'outer': ROOT / 'r22-preparation/outer-r22.py',
             'contract': ROOT / 'r22-preparation/ACTUAL-CONTRACT.json',
             'bundle': ROOT / 'r22-preparation/ACTUAL-BUNDLE.json',
             'terminal': HERE / 'outer-terminal.json',
             'resource': HERE / 'outer-resource-probe.json',
             'serialized': HERE / 'serialized-heavy-admission.json'}
    inputs = {name: {'reference': capture['references'][name], 'raw': read(path)}
              for name, path in names.items()}
    inputs['preparation_outputs'] = {
        session: {'reference': value['reference'],
                  'raw': base64.b64decode(value['base64'], validate=True)}
        for session, value in capture['preparation_outputs'].items()}
    baseline = capture['baseline']
    actual = module.validate_r22_prebuild(inputs, baseline)
    assert actual['actual_R22_prebuild_failure_consumed'] is True
    assert actual['build_attempted'] is False
    cases = []

    def rejects(name, operation):
        try:
            operation()
        except (RuntimeError, ValueError, KeyError, TypeError):
            cases.append(name)
        else:
            raise AssertionError('negative admitted: ' + name)

    def full(name, change):
        modified, changed_baseline = copy.deepcopy(inputs), copy.deepcopy(baseline)
        change(modified, changed_baseline)
        rejects(name, lambda: module.validate_r22_prebuild(modified, changed_baseline))

    full('missing actual terminal', lambda i, b: i.pop('terminal'))
    full('successor cannot add an uncreated producer LOCK', lambda i, b: i.__setitem__('producer_lock', {}))
    full('altered actual terminal body', lambda i, b: i['terminal'].__setitem__('raw', i['terminal']['raw'] + b' '))
    full('rounded original terminal nanoseconds', lambda i, b: i['terminal']['reference']['identity'].__setitem__(7,
         i['terminal']['reference']['identity'][7] + 1))
    full('boolean file size', lambda i, b: i['resource']['reference'].__setitem__('bytes', True))
    full('different original worker', lambda i, b: i['worker']['reference'].__setitem__('sha256', '0' * 64))
    full('manifest inode rebound', lambda i, b: b['manifest']['identity'].__setitem__(1, b['manifest']['identity'][1] + 1))
    full('missing original source lock', lambda i, b: b['locks'].pop())
    full('changed source lock body', lambda i, b: b['locks'][1].__setitem__('body_hex', '303030303030300a'))
    full('missing failed preparation client archive', lambda i, b: i['preparation_outputs'].pop(next(iter(i['preparation_outputs']))))
    full('altered actual preparation capture', lambda i, b: next(iter(i['preparation_outputs'].values())).__setitem__('raw', b''))

    terminal = module.decode(inputs['terminal']['raw'])
    serialized = module.decode(inputs['serialized']['raw'])
    contract = module.decode(inputs['contract']['raw'])
    module.validate_status_history(terminal, serialized, contract)
    module.validate_clients(contract, inputs['preparation_outputs'])

    def status(name, change):
        t, s, c = copy.deepcopy(terminal), copy.deepcopy(serialized), copy.deepcopy(contract)
        change(t, s, c)
        rejects(name, lambda: module.validate_status_history(t, s, c))

    status('unreaped original child', lambda t, s, c: t['original_worker_status_children'][0].__setitem__('actual_child_reaped', False))
    status('missing original child PIDFD', lambda t, s, c: t['original_worker_status_children'][0].__setitem__('original_pidfd_held_until_reaped', False))
    status('false is not child exit zero', lambda t, s, c: t['original_worker_status_children'][0].__setitem__('exit_code', False))
    status('different service manager argv', lambda t, s, c: t['original_worker_status_children'][0]['argv'].remove('--user'))
    status('missing original target observation', lambda t, s, c: s['actual_units'].pop())
    status('original cgroup remains', lambda t, s, c: s['actual_units'][0].__setitem__('both_cgroup_paths_absent', False))
    status('unobserved service MainPID', lambda t, s, c: s['actual_units'][0]['fields'].pop('MainPID'))
    status('status child outside original outer window', lambda t, s, c: t['original_worker_status_children'][0].__setitem__('finished_ns', t['finished_ns'] + 1))

    def client(name, change):
        modified = copy.deepcopy(contract)
        change(modified)
        rejects(name, lambda: module.validate_clients(modified, inputs['preparation_outputs']))

    client('failed preparation rewritten as success', lambda c: c['preparation_clients'][0]['actual_status'].__setitem__('exit_code', 0))
    client('missing failed original preparation', lambda c: c['preparation_clients'].pop(0))
    client('boolean preparation exit zero', lambda c: c['preparation_clients'][2]['actual_status'].__setitem__('exit_code', False))
    client('truncated original terminal capture', lambda c: c['preparation_clients'][0]['actual_status'].__setitem__('bytes_stored', 1))
    client('durable terminal session substituted', lambda c: c['preparation_clients'][0].__setitem__('session_id', 'dpty-' + '0' * 64))
    rejects('duplicate JSON key', lambda: module.decode(b'{"passed":false,"passed":true}'))
    rejects('nonfinite JSON', lambda: module.decode(b'{"value":NaN}'))
    rejects('typed equality refuses boolean zero', lambda: module.same({'n': 0}, {'n': False}, 'typed mismatch'))

    source_bookends = []
    for path, fd, before, original in held:
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), 'rb') as source:
            after = source.read(1024 ** 2 + 1)
        assert after == original and before == f9(os.fstat(fd)) == f9(path.lstat())
        source_bookends.append({'path': str(path), 'bytes': len(original),
            'sha256': hashlib.sha256(original).hexdigest(), 'identity': before})
    report = {'schema': 'p4-r23-actual-r22-prebuild-admission-controls-v1',
        'passed': True, 'actual_positive_cases': 1, 'actual_failure_preserved': True,
        'negative_cases': cases, 'module': source_bookends[0],
        'local_full_input_bookends': source_bookends, 'actual_capture_client': capture['actual_capture_client'],
        'actual_original_host_refs': capture['references'], 'actual_result': actual,
        'host_inputs_read_from_actual_files': True, 'host_metadata_observation_only': True,
        'fresh_live_unit_retirement_tested': False, 'source_locks_acquired': False,
        'successor_resource_admission_tested': False, 'children_started': 0,
        'source_mutations': 0, 'Android_builds': 0, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False}
    output = HERE / 'RESULT.json'
    with output.open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps({'passed': True, 'positive': 1, 'negative': len(cases),
                      'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    finally:
        for _, fd, _, _ in held:
            os.close(fd)
