#!/usr/bin/env python3
"""One normally locked Audio source expansion; no full-build qualification."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import traceback

BASE = Path('/data/pocket4-audio-sdk-closure-20261109-2840-r1')
CONTROL = BASE / 'control'
ROOT = Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1')
WORK = ROOT / 'work'
SOURCE = WORK / 'aosp-source'
RECIPE = BASE / 'recipe'
TOOLS = BASE / 'tools'
RESULT = BASE / 'source-reconcile-r2'
UNIT = 'p4-audio-sdk-source-20261109-2840-r2.service'
OLD_MANIFEST = 'd5049fd23ecff60fedc52562ec4a7856cfb8e2c137d5d569a2f507e692c3ec7e'
OLD_LOCK = '45496b24c055fca9aa1f3fae7bd5c7c3c99cb46721150690645bf5d059159de2'
NEW_LOCK = 'aab71dbce304aba849ac592b5d9cdc2a339cf9208c47faca98f27350c462437d'
spec = importlib.util.spec_from_file_location('desktop_build_support', CONTROL / 'desktop_build_support.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

def environment(fetch=False):
    env = {'HOME': '/home/qian-qi', 'PATH': str(TOOLS) + ':/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_OPTIONAL_LOCKS': '0', 'GIT_CONFIG_COUNT': '2',
           'GIT_CONFIG_KEY_0': 'maintenance.auto', 'GIT_CONFIG_VALUE_0': 'false',
           'GIT_CONFIG_KEY_1': 'gc.auto', 'GIT_CONFIG_VALUE_1': '0'}
    if not fetch:
        env['GIT_NO_LAZY_FETCH'] = '1'
    return env

def budget():
    cg = s.self_cgroup()
    s.need(cg == Path('/sys/fs/cgroup/system.slice') / UNIT, 'unexpected owned source unit')
    row = {k: (cg / k).read_text().strip() for k in
           ('memory.max', 'memory.peak', 'memory.events', 'memory.swap.max', 'memory.swap.current', 'cpu.max')}
    row['affinity'] = sorted(os.sched_getaffinity(0))
    s.need(row['memory.max'] == str(4 * 1024**3) and row['memory.swap.max'] == '0'
           and row['memory.swap.current'] == '0' and row['cpu.max'] == '200000 100000'
           and row['affinity'] == [0, 1], 'source unit resource contract differs')
    return row

def monitor(_):
    s.need(s.disk_free(ROOT) >= 52 * 1024**3, 'reserved shared disk/build budget reached')
    s.need(s.memavailable() >= 5 * 1024**3, 'shared memory reserve reached')

def main():
    report = {'schema': 'audio-original-sdk-normal-reconcile-v1', 'state': 'STARTED',
              'source_commit': '557bff5c84eef7eea9af4533ac7391e3ae676d0f',
              'builds_started': 0, 'source_materialization_verified': False,
              'complete_apex_qualified': False, 'runtime_qualified': False,
              'started_ns': time.time_ns(), 'errors': []}
    RESULT.mkdir(mode=0o700)
    s.create(RESULT / 'STARTED.json', report)
    held = []
    commands = None
    try:
        s.need(os.getuid() == os.geteuid() == 1000, 'source workspace owner required')
        report['budget_before'] = budget()
        s.need(s.memavailable() >= 9 * 1024**3, 'source memory admission reserve unavailable')
        monitor(None)
        locks = [(Path('/data/pocket4-production-build-20261108-8b88.serial.lock'), (2067, 48352)),
                 (WORK / 'package-build.lock', (2067, 1883370)),
                 (WORK / 'aosp-source-update.lock', (2067, 1883371))]
        report['locks'] = []
        for path, expected in locks:
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append(fd)
            st = os.fstat(fd)
            s.need((st.st_dev, st.st_ino) == expected and stat.S_ISREG(st.st_mode)
                   and st.st_uid == 1000 and st.st_nlink == 1
                   and stat.S_IMODE(st.st_mode) == 0o600, 'existing shared lock identity differs')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            s.need(s.identity(st) == s.identity(path.lstat()), 'shared lock replaced')
            report['locks'].append({'path': str(path), 'identity': s.identity(st), 'held_exclusive': True})
        s.need(not (WORK / 'source-projection.json').exists(), 'active/interrupted source projection')
        old = s.file_ref(SOURCE / '.droidloom-source-manifest.json', copy_to=RESULT / 'materialized-before.json')
        s.need(old['sha256'] == OLD_MANIFEST, 'source epoch changed before locked reconcile')
        report['materialized_before'] = old
        prior, prior_ref = s.read_json(ROOT / 'qualification/full-desktop-r11/terminal.json')
        s.need(prior_ref['sha256'] == '9c1143c858f8e45b84a63c82e460eead07d9fc0f803170605844a5b1ea88ba12'
               and prior['input_after_qualified'] is True and prior['owned_retirement_complete'] is True
               and prior['build_success'] is False, 'previous full lacks a retired restored failure')
        report['previous_full'] = prior_ref
        ready, ready_ref = s.read_json(BASE / 'SOURCE_READY.json')
        s.need(ready_ref['sha256'] == 'd238356cfbc68ebf4e31422510023584e4d67ded15332ae12fc98906c17143d7', 'source ready record changed')
        s.need(ready['source_commit'] == report['source_commit'] and ready['new_lock_sha256'] == NEW_LOCK
               and ready['old_lock_sha256'] == OLD_LOCK and ready['focused_tests']['passed'] == 53, 'source repair identity differs')
        report['source_ready'] = ready_ref
        for key in ('target/debug/droidloom-source', 'target/debug/droidloom-update'):
            ref = ready['files'][key]
            actual = s.file_ref(TOOLS / Path(ref['path']).name)
            s.need(all(actual[k] == ref[k] for k in ('bytes', 'sha256')), 'normal tool changed')
        commands = s.OwnedCommands(RESULT / 'commands', CONTROL)
        report['commands'] = commands.records
        def run(name, argv, timeout=1200, fetch=False, cwd=RECIPE):
            return commands.run(name, [str(x) for x in argv], timeout, cwd=cwd, env=environment(fetch), monitor=monitor)
        row = run('recipe-head', ['/usr/bin/git', 'rev-parse', 'HEAD'], 30)
        s.need(s.pinned(row['stdout'], contents=True)[1].decode().strip() == report['source_commit'], 'recipe commit changed')
        row = run('recipe-clean', ['/usr/bin/git', 'status', '--porcelain=v1'], 60)
        s.need(not s.pinned(row['stdout'], contents=True)[1], 'recipe is not clean')
        old_recipe = ROOT / 'recipe-ondeviceintelligence-api-r1'
        run('old-materialized-before', [ROOT / 'tools/ondeviceintelligence-api-r1/droidloom-source',
            'verify-materialized', '--lock', old_recipe / 'android/manifest/audio-bridge-source-lock.json',
            '--output', SOURCE], cwd=old_recipe)
        lock = RECIPE / 'android/manifest/audio-bridge-source-lock.json'
        s.need(s.file_ref(lock)['sha256'] == NEW_LOCK, 'new source lock changed')
        run('new-lock-verify', [TOOLS / 'droidloom-source', 'verify-lock', '--lock', lock], 120)
        report['state'] = 'RECONCILING'
        s.create(RESULT / 'admission.json', report)
        run('normal-reconcile', [TOOLS / 'droidloom-source', 'reconcile', '--lock', lock, '--output', SOURCE], 7200, True)
        run('normal-materialized-after', [TOOLS / 'droidloom-source', 'verify-materialized', '--lock', lock, '--output', SOURCE])
        after = s.file_ref(SOURCE / '.droidloom-source-manifest.json', copy_to=RESULT / 'materialized-after.json')
        manifest = json.loads(s.pinned(after, contents=True)[1])
        s.need(manifest['source_lock_sha256'] == NEW_LOCK and len(manifest['plan']['projects']) == 430,
               'normal reconciler did not publish exact new 430-project plan')
        report['materialized_after'] = after
        report['original_sdk_files'] = []
        sdk = SOURCE / 'prebuilts/sdk'
        for relative in ready['required_inputs']:
            path = sdk / relative
            ref = s.file_ref(path)
            blob = subprocess.check_output(['/usr/bin/git', 'hash-object', '--', str(path)], cwd=sdk, env=environment()).decode().strip()
            s.need(blob == ready['original_blob_ids'][relative], 'original SDK content differs: ' + relative)
            report['original_sdk_files'].append(dict(ref, relative=relative, git_blob=blob))
        s.need(not (WORK / 'source-projection.json').exists(), 'projection appeared during source reconcile')
        report['source_materialization_verified'] = True
        report['state'] = 'SOURCE_RECONCILED_AND_NORMAL_VERIFIED'
    except BaseException as e:
        report['errors'].append({'type': type(e).__name__, 'message': str(e), 'traceback': traceback.format_exc()})
        report['state'] = 'FAILED_SOURCE_RECONCILE'
    finally:
        report['all_command_children_reaped'] = bool(commands is not None and all(r['owned_retirement_complete'] for r in commands.records))
        try:
            report['budget_after'] = budget()
            s.need(all(s.event_counts(report['budget_after']['memory.events']).get(k, 0) == 0 for k in ('oom', 'oom_kill', 'oom_group_kill')), 'source reconcile OOM')
        except BaseException as e:
            report['errors'].append({'stage': 'resource', 'type': type(e).__name__, 'message': str(e)})
        report['signals'] = list(s.CANCELLED)
        if report['errors'] or report['signals'] or not report['all_command_children_reaped']:
            report['state'] = 'FAILED_SOURCE_RECONCILE'
            report['source_materialization_verified'] = False
        report['finished_ns'] = time.time_ns()
        ref = s.create(RESULT / 'RESULT.json', report)
        for fd in reversed(held):
            os.close(fd)
        print(json.dumps({'state': report['state'], 'result': ref, 'errors': report['errors']}), flush=True)
    return 0 if report['source_materialization_verified'] else 1

if __name__ == '__main__':
    s.install_signals()
    raise SystemExit(main())
