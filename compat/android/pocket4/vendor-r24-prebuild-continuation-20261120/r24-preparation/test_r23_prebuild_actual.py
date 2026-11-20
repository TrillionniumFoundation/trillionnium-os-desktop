#!/usr/bin/python3
"""Pure local consumption of complete actual R23 and nested R22 raw inputs."""
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
ROOT = HERE.parent
held = []


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        assert stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= 1024**2
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(1024**2 + 1)
        assert len(raw) == before[6] and before == f9(os.fstat(fd)) == f9(path.lstat())
        held.append((path, fd, before, raw))
        return raw
    except BaseException:
        os.close(fd)
        raise


def actual_inputs(module):
    index = json.loads(read(HERE / 'R23-PREBUILD-HELPER-INPUTS.json'))
    inputs = {name: {'reference': index['actual_original_refs'][name], 'raw': read(path)}
              for name, path in index['local_actual_raw_paths'].items()}
    helper_body = read(ROOT / 'r23-preparation/r22_prebuild_admission.py')
    inputs['r22_helper'] = {'reference': module.R22_HELPER_REF, 'raw': helper_body}
    helper = module.load_original_r22(inputs['r22_helper'])
    original_capture = helper.decode(read(ROOT / 'r23-preparation/actual-controls/ACTUAL-INPUT-CAPTURE.json'))
    assert original_capture['all_input_bookends_equal'] is True
    assert original_capture['fresh_lock_ownership_observed'] is False
    paths = {'worker': ROOT / 'r22-preparation/source-r22.py',
             'outer': ROOT / 'r22-preparation/outer-r22.py',
             'contract': ROOT / 'r22-preparation/ACTUAL-CONTRACT.json',
             'bundle': ROOT / 'r22-preparation/ACTUAL-BUNDLE.json',
             'terminal': ROOT / 'r23-preparation/actual-controls/outer-terminal.json',
             'resource': ROOT / 'r23-preparation/actual-controls/outer-resource-probe.json',
             'serialized': ROOT / 'r23-preparation/actual-controls/serialized-heavy-admission.json'}
    nested = {name: {'reference': original_capture['references'][name], 'raw': read(path)}
              for name, path in paths.items()}
    nested['preparation_outputs'] = {
        session: {'reference': value['reference'],
                  'raw': base64.b64decode(value['base64'], validate=True)}
        for session, value in original_capture['preparation_outputs'].items()}
    inputs['r22'] = nested
    contract = helper.decode(inputs['contract']['raw'])
    pages_raw = read(ROOT / 'r23-preparation/CLIENTS-RAW.json')
    assert len(pages_raw) == 107521
    assert hashlib.sha256(pages_raw).hexdigest() == 'a166d2fea7ac6cf187a518641a1c0b725347b574e726a26d7dcb71929961b7ae'
    captures = json.loads(pages_raw)
    outputs = {}
    for original, client in zip(captures, contract['preparation_clients']):
        assert original['name'] == client['name']
        pages = [helper.decode(x.encode()) for x in original['pages_raw']]
        body = bytearray(); cursor = 0
        for page in pages:
            chunk = bytes.fromhex(page['bytes_hex'])
            assert page['session_id'] == client['session_id']
            assert page['status'] == client['actual_status']
            assert page['offset'] == cursor and page['next_offset'] - cursor == len(chunk)
            assert hashlib.sha256(chunk).hexdigest() == page['chunk_sha256']
            body.extend(chunk); cursor = page['next_offset']
        assert cursor == pages[0]['available_end'] == client['stdout']['bytes']
        outputs[client['session_id']] = {'reference': client['stdout'], 'raw': bytes(body)}
    assert len(captures) == len(outputs) == 4
    inputs['preparation_outputs'] = outputs
    return helper, inputs, original_capture['baseline']


def main():
    path = HERE / 'r23_prebuild_admission.py'
    raw = read(path)
    module = types.ModuleType('actual_r24_r23_prebuild_admission')
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    helper, inputs, baseline = actual_inputs(module)
    actual = module.validate_r23_prebuild(inputs, baseline)
    assert actual['actual_R23_prebuild_failure_consumed'] is True
    assert actual['original_status_children_reaped'] == 135
    assert actual['actual_nested_R22_failure']['original_status_children_reaped'] == 132
    assert actual['build_attempted'] is actual['runtime_qualified'] is actual['production_ready'] is False
    cases = []

    def rejects(name, action):
        try:
            action()
        except (RuntimeError, ValueError, KeyError, TypeError):
            cases.append(name)
        else:
            raise AssertionError('negative admitted: ' + name)

    def full(name, change):
        data, b = copy.deepcopy(inputs), copy.deepcopy(baseline)
        change(data, b)
        rejects(name, lambda: module.validate_r23_prebuild(data, b))

    full('missing actual R23 terminal body', lambda d, b: d.pop('terminal'))
    full('new producer LOCK is not an actual historical input', lambda d, b: d.__setitem__('producer_lock', {}))
    full('local resource transfer plus-prefix corruption', lambda d, b: d['resource'].__setitem__('raw', b'+' + d['resource']['raw']))
    full('one original R23 nanosecond changed', lambda d, b: d['terminal']['reference']['identity'].__setitem__(7, d['terminal']['reference']['identity'][7] + 1))
    full('boolean whole-file byte count', lambda d, b: d['resource']['reference'].__setitem__('bytes', True))
    full('different original R23 worker body', lambda d, b: d['worker'].__setitem__('raw', d['worker']['raw'] + b'\n'))
    full('modified helper code rejected before execution', lambda d, b: d['r22_helper'].__setitem__('raw', b'raise AssertionError("must not execute")'))
    full('helper original F9 cannot be rounded', lambda d, b: d['r22_helper']['reference']['identity'].__setitem__(7, d['r22_helper']['reference']['identity'][7] + 1))
    full('missing nested R22 actual terminal', lambda d, b: d['r22'].pop('terminal'))
    full('nested R22 failure body cannot be relabeled', lambda d, b: d['r22']['resource'].__setitem__('raw', d['resource']['raw']))
    full('nested failure pass object cannot replace original raw inputs', lambda d, b: d.__setitem__('r22', actual['actual_nested_R22_failure']))
    full('missing failed original R22 preparation archive', lambda d, b: d['r22']['preparation_outputs'].pop(next(iter(d['r22']['preparation_outputs']))))
    failed = module.CLIENTS[1][1]
    full('missing R23 failed-supervisor archive', lambda d, b: d['preparation_outputs'].pop(failed))
    full('truncated R23 original client archive', lambda d, b: d['preparation_outputs'][failed].__setitem__('raw', b''))
    full('original baseline lock body changes', lambda d, b: b['locks'][0].__setitem__('body_hex', '00'))
    terminal = helper.decode(inputs['terminal']['raw'])
    serialized = helper.decode(inputs['serialized']['raw'])
    contract = helper.decode(inputs['contract']['raw'])
    r22_contract = helper.decode(inputs['r22']['contract']['raw'])

    def status(name, change):
        t, s, c, old = map(copy.deepcopy, (terminal, serialized, contract, r22_contract))
        change(t, s, c, old)
        rejects(name, lambda: module.validate_status_history(helper, t, s, c, old))

    status('missing 135th actual status child', lambda t, s, c, o: t['original_worker_status_children'].pop())
    status('missing original 132nd target', lambda t, s, c, o: o['live_retirement_targets'].pop())
    status('missing added R22 recovery observation', lambda t, s, c, o: s['actual_R22_continuation']['additional_R22_live_retirement_observations'].pop())
    status('original status PIDFD custody absent', lambda t, s, c, o: t['original_worker_status_children'][-1].__setitem__('original_pidfd_held_until_reaped', False))
    status('original status child unreaped', lambda t, s, c, o: t['original_worker_status_children'][-1].__setitem__('actual_child_reaped', False))
    status('false is not child exit zero', lambda t, s, c, o: t['original_worker_status_children'][-1].__setitem__('exit_code', False))
    status('different added target service manager', lambda t, s, c, o: t['original_worker_status_children'][-1]['argv'].remove('--user'))
    status('added retired service MainPID omitted', lambda t, s, c, o: s['actual_R22_continuation']['additional_R22_live_retirement_observations'][-1]['fields'].pop('MainPID'))
    status('added cgroup still present', lambda t, s, c, o: s['actual_R22_continuation']['additional_R22_live_retirement_observations'][-1].__setitem__('both_cgroup_paths_absent', False))
    status('child exceeds original outer window', lambda t, s, c, o: t['original_worker_status_children'][-1].__setitem__('finished_ns', t['finished_ns'] + 1))

    def continuation(name, change):
        value = copy.deepcopy(serialized['actual_R22_continuation'])
        change(value)
        rejects(name, lambda: module.validate_continuation(helper, value, contract, actual['actual_nested_R22_failure']))

    continuation('fabricated nested R22 success', lambda v: v['actual_R22_prebuild_failure_and_original_status_retirement'].__setitem__('build_attempted', True))
    continuation('admission budget renewed to 300 seconds', lambda v: v.__setitem__('same_total_admission_budget_seconds', 300))
    continuation('resource admission reused', lambda v: v.__setitem__('resource_admission_reused', True))
    continuation('actual historical pin deleted', lambda v: v.__setitem__('all_actual_R22_input_pins_preserved', False))
    continuation('predecessor parent inode replaced', lambda v: v['actual_unmaterialized_R22_plan']['parent_identity'].__setitem__(1, 0))

    def client(name, change):
        c = copy.deepcopy(contract); change(c)
        rejects(name, lambda: module.validate_clients(helper, c, inputs['preparation_outputs']))

    client('failed supervisor outcome rewritten as success', lambda c: c['preparation_clients'][1]['actual_status'].__setitem__('exit_code', 0))
    client('boolean preparation exit code zero', lambda c: c['preparation_clients'][0]['actual_status'].__setitem__('exit_code', False))
    client('different original client session', lambda c: c['preparation_clients'][0].__setitem__('session_id', 'dpty-' + '0' * 64))

    bookends = []
    for p, fd, identity, before in held:
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), 'rb') as stream:
            after = stream.read(1024**2 + 1)
        assert before == after and identity == f9(os.fstat(fd)) == f9(p.lstat())
        bookends.append({'path': str(p), 'bytes': len(before),
            'sha256': hashlib.sha256(before).hexdigest(), 'identity': identity})
    report = {'schema': 'p4-r24-actual-r23-prebuild-admission-controls-v1',
        'passed': True, 'actual_positive_cases': 1, 'negative_cases': cases,
        'module': bookends[0], 'local_full_input_bookends': bookends,
        'actual_result': actual,
        'full_actual_R23_originals': 7, 'full_actual_R23_preparation_archives': 4,
        'full_nested_R22_originals': 7, 'full_nested_R22_preparation_archives': 13,
        'actual_original_status_children_consumed': 135,
        'actual_R22_helper_source_unchanged': True,
        'actual_R22_and_R23_failures_preserved': True,
        'host_input_origin': 'Original whole pinned bodies and full terminal pages captured for actual R22/R23; local pure replay only.',
        'new_host_execution': False, 'fresh_live_retirement_tested': False,
        'fresh_resource_admission_tested': False, 'source_locks_acquired': False,
        'children_started': 0, 'source_mutations': 0, 'Android_builds': 0, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False}
    out = HERE / 'R23-PREBUILD-ACTUAL-CONTROLS.json'
    with out.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n')
    body = out.read_bytes()
    print(json.dumps({'passed': True, 'positive': 1, 'negative': len(cases),
                      'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}))


if __name__ == '__main__':
    try:
        main()
    finally:
        for _, fd, _, _ in held:
            os.close(fd)
