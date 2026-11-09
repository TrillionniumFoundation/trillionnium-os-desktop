#!/usr/bin/env python3
"""Read and freeze the retired SDK source reconcile proof under existing locks."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import time

BASE = Path('/data/pocket4-audio-sdk-closure-20261109-2840-r1')
SHARED = Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1')
spec = importlib.util.spec_from_file_location('support', BASE / 'control/desktop_build_support.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

def main():
    unit = Path('/sys/fs/cgroup/system.slice/p4-audio-sdk-source-20261109-2840-r2.service')
    s.need(os.getuid() == 1000 and not unit.exists(), 'source owner or physical unit retirement differs')
    report, ref = s.read_json(BASE / 'source-reconcile-r2/RESULT.json')
    s.need(ref['sha256'] == '8476ce854447256876ab89ad1ddc7b8552a136a012a149da3dd064d287f20a10', 'source terminal changed')
    s.need(report['state'] == 'SOURCE_RECONCILED_AND_NORMAL_VERIFIED'
           and report['source_commit'] == '557bff5c84eef7eea9af4533ac7391e3ae676d0f'
           and report['source_materialization_verified'] is True
           and report['all_command_children_reaped'] is True
           and report['errors'] == [] and report['signals'] == []
           and report['builds_started'] == 0, 'source terminal not successful')
    job = Path('/home/qian-qi/.local/state/hepta-runtime-mac-worker/jobs/1a1c0a83b12-11c5a-b')
    h = {name: s.read_json(job / (name + '.json')) for name in ('request', 'started', 'exit')}
    terminal = h['exit'][0]
    guards = s.load_module(SHARED / 'control/full-desktop-r11/audio_continuation_control.py')
    guards.validate_raw_exit(terminal, h['request'][0], h['started'][0], expected_exit_code=0,
        expected_at_unix_ms=terminal['at_unix_ms'],
        expected_stream_bytes={k: v['stored'] for k, v in terminal['log_bytes'].items()})
    held = []
    result = {'schema': 'audio-source-sdk-terminal-recheck-v1', 'checked_ns': time.time_ns(),
              'source_result': ref, 'H': {k: v[1] for k, v in h.items()},
              'physical_source_unit_absent': True, 'locks': [], 'original_sdk_files': [],
              'full_build_started': False, 'complete_apex_qualified': False,
              'runtime_qualified': False, 'production_ready': False}
    try:
        for lock in report['locks']:
            path = Path(lock['path'])
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append(fd)
            st = os.fstat(fd)
            s.need(s.identity(st) == lock['identity'] and stat.S_ISREG(st.st_mode)
                   and st.st_uid == 1000 and st.st_nlink == 1
                   and stat.S_IMODE(st.st_mode) == 0o600, 'shared lock identity changed')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            s.need(s.identity(path.lstat()) == lock['identity'], 'shared lock replaced')
            result['locks'].append(dict(lock, nonblocking_exclusive_probe_succeeded=True))
        s.need(not unit.exists(), 'source unit reappeared')
        s.need(not (SHARED / 'work/source-projection.json').exists(), 'active source projection')
        ready, ready_ref = s.read_json(BASE / 'SOURCE_READY.json')
        s.need(ready_ref['sha256'] == 'd238356cfbc68ebf4e31422510023584e4d67ded15332ae12fc98906c17143d7', 'source ready changed')
        manifest_ref, raw = s.pinned(report['materialized_after'], contents=True)
        manifest = json.loads(raw)
        s.need(manifest['source_lock_sha256'] == 'aab71dbce304aba849ac592b5d9cdc2a339cf9208c47faca98f27350c462437d'
               and len(manifest['plan']['projects']) == 430, 'materialized source plan changed')
        result['materialized_after'] = manifest_ref
        result['projects'] = 430
        required = set(ready['required_inputs'])
        s.need(len(required) == 55 and len(report['original_sdk_files']) == 55
               and {x['relative'] for x in report['original_sdk_files']} == required,
               'SDK inputs not the exact complete 55-file closure')
        for item in report['original_sdk_files']:
            actual, raw = s.pinned(item, contents=True)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            s.need(blob == item['git_blob'] == ready['original_blob_ids'][item['relative']], 'original Git blob differs')
            result['original_sdk_files'].append({'relative': item['relative'], 'bytes': actual['bytes'],
                'sha256': actual['sha256'], 'git_blob': blob})
        result['command_evidence'] = []
        for command in report['commands']:
            s.need(command['owned_retirement_complete'] is True and command['errors'] == []
                   and command['lifecycle']['returncode'] == 0, 'normal command proof failed')
            for stream in ('stdout', 'stderr'):
                s.pinned(command[stream])
            result['command_evidence'].append({k: command[k] for k in ('name', 'argv', 'stdout', 'stderr')})
        s.need(not unit.exists(), 'source unit reappeared after checks')
        result['state'] = 'SOURCE_SDK_55_BLOBS_AND_PHYSICAL_RETIREMENT_VERIFIED'
        result['checked_finished_ns'] = time.time_ns()
        out = s.create(BASE / 'source-reconcile-r2/TERMINAL_CHECK.json', result)
        print(json.dumps({'state': result['state'], 'result': out, 'materialized_after': result['materialized_after'],
                          'sdk_files': len(result['original_sdk_files']), 'locks': result['locks'],
                          'H_terminal': terminal, 'production_ready': False}), flush=True)
    finally:
        for fd in reversed(held):
            os.close(fd)

if __name__ == '__main__':
    main()
