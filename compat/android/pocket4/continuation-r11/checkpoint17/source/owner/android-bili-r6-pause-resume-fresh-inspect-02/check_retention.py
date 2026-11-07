#!/usr/bin/env python3
"""Real retired receipt shape through production retention; local exact-path seam."""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    value = types.ModuleType(name);value.__file__ = str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),value.__dict__);return value


base_source = load('frozen_bili_preimage',ROOT/'android-bili-r6-pause-resume-metadata02/owned_navigation.py')
toggle = load('candidate_retention',HERE/'playback_controls.py')
EVIDENCE = ROOT/'root-recovery-20261104-02/evidence/bili-r6-pause-resume-failure-read01'
EXPECTED = 'f4a73707341f1c78e28f41ca618f60f6350ae4803ccfc0e084be07f190d35463'
PINS = {'navigation.json':(231265,'a1689217ec1484171f08fc4962a9fc42f1dfefa365b0b158c50f46aac271f1b6'),
        'navigation-command.json':(1162,'bea6a022a7e7b6184efda5ded8184c4cfa15dfdf7de8e2122adf1328ed2d49b3')}


def main():
    originals = {}
    for name,(size,digest) in PINS.items():
        raw = (EVIDENCE/name).read_bytes()
        assert len(raw) == size and hashlib.sha256(raw).hexdigest() == digest
        originals[name] = raw
    nav = base_source.FLOW/'steps/pause-resume-01/result.json'
    command = base_source.ROOT/'evidence/03-navigate.result.json'
    rows = []
    for mode in ('actual_failed_worker','wrong_worker_nonce','wrong_command_argv','missing_worker',
                 'mismatching_prior_pin','unrequested_phase','bounded_read_error'):
        files = {nav:originals['navigation.json'],command:originals['navigation-command.json']}
        if mode == 'wrong_worker_nonce':
            value = json.loads(files[nav]);value['nonce'] = '0'*32;files[nav] = json.dumps(value).encode()
        if mode == 'wrong_command_argv':
            value = json.loads(files[command]);value['argv'][-1] = '0'*64;files[command] = json.dumps(value).encode()
        if mode == 'missing_worker':files.pop(nav)
        original_error = {'phase':'coordinator','type':'RuntimeError','message':'PRESERVED_FIRST_RUN_CLI_FAILURE'}
        result = {'ok':False,'error':copy.deepcopy(original_error),'secondary_errors':[],
            'launch_worker_requested':False,'navigation_worker_requested':mode != 'unrequested_phase'}
        if mode == 'mismatching_prior_pin':result['navigation_result'] = {'path':str(nav),'bytes':1,'sha256':'0'*64}
        reads = []
        def read(path):
            reads.append(path)
            if mode == 'bounded_read_error' and path == nav:raise RuntimeError('CONTROL_BOUNDED_FILE_ERROR')
            return files[path]
        def remember(value, phase, error):
            value['secondary_errors'].append({'phase':phase,'type':type(error).__name__,'message':str(error)})
            value['ok'] = False
        base = types.SimpleNamespace(**{name:getattr(base_source,name) for name in
            ('FLOW','ROOT','NONCE','BILI','BILI_UID','SELF','UID','R4_MANIFEST','require','sha')})
        base.HERE = base_source.SOURCE
        base.os = types.SimpleNamespace(path=types.SimpleNamespace(lexists=lambda p:p in files))
        base.read = read
        toggle.retain_phase_results(base,types.SimpleNamespace(remember=remember),result,EXPECTED)
        assert result['error'] == original_error and result['ok'] is False
        assert set(reads) <= {nav,command}
        retained = result['retained_phase_results']; commands = result['retained_phase_commands']
        if mode == 'unrequested_phase':assert reads == [] and retained == commands == {}
        else:
            assert ('navigate' in retained) == (mode in ('actual_failed_worker','wrong_command_argv'))
            assert ('navigate' in commands) == (mode != 'wrong_command_argv')
            if 'navigate' in retained:
                assert retained['navigate'] == {'path':str(nav),'bytes':PINS['navigation.json'][0],'sha256':PINS['navigation.json'][1]}
            if 'navigate' in commands:
                assert commands['navigate'] == {'path':str(command),'bytes':PINS['navigation-command.json'][0],'sha256':PINS['navigation-command.json'][1]}
        expected_errors = 0 if mode in ('actual_failed_worker','missing_worker','unrequested_phase') else 1
        assert len(result['secondary_errors']) == expected_errors
        rows.append({'case':mode,'passed':True,'read_count':len(reads),'retained_worker_count':len(retained),
            'retained_command_count':len(commands),'first_error_preserved':True,'secondary_errors':result['secondary_errors']})
    print(json.dumps({'schema':1,'passed':len(rows),'controls':rows,
        'production_retention_function':True,'local_fixed_path_IO_seam':True,'raw_receipt_copied_to_report':False,
        'device_or_UI_actions':0,'actual_failed_receipt_pins':{name:{'bytes':s,'sha256':h} for name,(s,h) in PINS.items()},
        'source_sha256':hashlib.sha256((HERE/'playback_controls.py').read_bytes()).hexdigest()},indent=2)+'\n')
    return 0


if __name__ == '__main__':raise SystemExit(main())
