#!/usr/bin/env python3
"""One-shot preparation + two separate original recorder CLIs; no UI entry.

Default PLAN performs no device or filesystem action. This source is supplied
as the pinned stdin of a bounded Hepta job. All Android execution is delegated
to the already reviewed recorder's single read-only admission operation.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import subprocess
import tarfile
import time
import traceback
import types

ROOT = Path('/home/alex/work/pocket4-bilibili-readonly-r2-01')
ARCHIVE = Path('/home/alex/work/pocket4-bilibili-held-r2-source-01.tar.gz')
ARCHIVE_SHA = 'ff856ef8c23fde572060917f32e039cdf02923a6d77ee38e87b9c5287501dbfa'
ARCHIVE_BYTES = 108190
TOP = 'recorder-held-r2-freeze-01'
MANIFEST_SHA = '2c2c2a51ec91402a04237738ca5eba840a0d5dad62803e09c8752d691394ab72'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
VERIFIED = ACTIVATION.with_name('activation-verified-01.json')
VERIFIED_SHA = '2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387'
EPOCH_SOURCE = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
EPOCH_SOURCE_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
MAIN_CGROUP = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
PACKAGE, UID = 'tv.danmaku.bili', 10117
COMPONENT = PACKAGE + '/tv.danmaku.bili.MainActivityV2'
STEP = 'readonly-admission-01'
COMMAND = ['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0', PACKAGE]
ENV = {'PATH': '/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path, maximum=1024 * 1024, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= maximum,
                'bounded single-link regular file required: ' + str(path))
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        last = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(all(getattr(first, k) == getattr(last, k) for k in fields) and len(data) == first.st_size,
                'input changed or exceeded bound')
        if expected is not None:
            require(digest(data) == expected, 'input hash changed: ' + str(path))
        return bytes(data)
    finally:
        os.close(fd)


def write_new(path, value, mode=0o600):
    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def module(raw, filename, name):
    value = types.ModuleType(name)
    value.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec'), value.__dict__)
    return value


def main_guard(activation, epoch):
    read(ACTIVATION, expected=ACTIVATION_SHA)
    read(VERIFIED, expected=VERIFIED_SHA)
    read('/etc/droidloom/cell.json', expected=CELL_SHA)
    require(activation['framework_epoch']['sha256'] == EPOCH, 'fixed Main epoch differs')
    epoch.require_unchanged(activation['framework_epoch'])
    for name in ('daemon_process', 'launcher_process', 'presenter_process'):
        identity = activation[name]
        require(epoch.process_identity(identity['host_pid']) == identity, 'Main host process differs: ' + name)
    limits = {name: (MAIN_CGROUP / name).read_text().strip() for name in activation['limits']}
    require(limits == activation['limits'], 'Main resource limits differ')
    epoch.require_unchanged(activation['framework_epoch'])
    return {'Main_epoch_sha256': EPOCH, 'activation_sha256': ACTIVATION_SHA,
            'verified_sha256': VERIFIED_SHA, 'config_sha256': CELL_SHA,
            'three_host_processes_match': True, 'resource_limits_match': True}


def stage_source(archive):
    require(len(archive) == ARCHIVE_BYTES, 'archive byte length')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        members = bundle.getmembers()
        require(len(members) <= 96 and len({m.name for m in members}) == len(members), 'archive members/duplicates')
        files = {}
        for item in members:
            rel = PurePosixPath(item.name)
            require(not rel.is_absolute() and '..' not in rel.parts and rel.parts[0] == TOP and str(rel) == item.name,
                    'unsafe source member')
            require(item.isdir() or item.isfile(), 'source links/special files rejected')
            if item.isfile():
                require(0 < item.size <= 131072, 'source member size')
                files[str(PurePosixPath(*rel.parts[1:]))] = bundle.extractfile(item).read()
        manifest_raw = files['source-manifest.json']
        require(digest(manifest_raw) == MANIFEST_SHA, 'external source manifest mismatch')
        manifest = json.loads(manifest_raw)
        require(manifest['schema'] == 1 and manifest['revision'] == 2 and len(manifest['files']) == 32,
                'source revision or exact payload count')
        require(set(files) == set(manifest['files']) | {'source-manifest.json'}, 'exact archive file closure')
        for name, row in manifest['files'].items():
            require(len(files[name]) == row['bytes'] and digest(files[name]) == row['sha256'], 'payload pin: ' + name)
    source = ROOT / 'source' / TOP
    source.mkdir(mode=0o700, parents=True)
    for name, data in sorted(files.items()):
        path = source / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_new(path, data, 0o444)
    contract_module = module(files['source_contract.py'], source / 'source_contract.py', 'bili_actual_contract')
    contract = contract_module.SourceContract(source / 'source-manifest.json', MANIFEST_SHA)
    contract.verify()
    return source, contract


def run_cli(name, argv, timeout, evidence, guard):
    guard()
    write_new(evidence / (name + '.intent.json'), {'argv': argv, 'timeout_seconds': timeout,
        'separate_process': True, 'automatic_retry': False})
    observed = {'name': name, 'argv': argv, 'spawned': False, 'joined': False, 'timed_out': False,
                'returncode': None, 'secondary_errors': [], 'Main_before': True}
    process = pidfd = None
    primary = None
    streams = []
    try:
        for suffix in ('.stdout', '.stderr'):
            streams.append(open(evidence / (name + suffix), 'xb'))
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                                   env=ENV, close_fds=True)
        observed.update(spawned=True, owned_child_pid=process.pid)
        pidfd = os.pidfd_open(process.pid, 0)
        try:
            observed['returncode'] = process.wait(timeout=timeout)
            observed['joined'] = True
        except BaseException as error:
            observed['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
            raise
    except BaseException as error:
        primary = error
        observed['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if process is not None and not observed['joined']:
            try:
                if process.poll() is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # Exact Popen child, no intervening wait/reaper; no ambient PID selection.
                        process.kill()
                observed['returncode'] = process.wait(timeout=6)
                observed['joined'] = True
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-child-retirement', 'error': repr(error)})
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-pidfd-close', 'error': repr(error)})
        for stream in streams:
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-sync', 'error': repr(error)})
            try:
                stream.close()
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-close', 'error': repr(error)})
        try:
            observed['Main_after'] = guard()
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'Main-after', 'error': repr(error)})
        for suffix in ('.stdout', '.stderr'):
            try:
                data = read(evidence / (name + suffix))
                observed[suffix[1:]] = {'bytes': len(data), 'sha256': digest(data)}
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-read', 'error': repr(error)})
        try:
            write_new(evidence / (name + '.result.json'), observed)
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'phase-result-write', 'error': repr(error)})
            if primary is None:
                primary = error
            else:
                primary.add_note('phase result write: ' + repr(error))
    if primary is not None:
        raise primary
    require(observed['joined'] and observed['returncode'] == 0 and not observed['secondary_errors'],
            name + ' did not complete exactly once with a preserved Main fence')
    return json.loads(read(evidence / (name + '.stdout')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-once', action='store_true')
    args = parser.parse_args()
    if not args.execute_once:
        print(json.dumps({'state': 'PLAN_ONLY', 'root': str(ROOT), 'flow': str(ROOT / 'flow'),
            'archive': str(ARCHIVE), 'archive_sha256': ARCHIVE_SHA, 'source_manifest_sha256': MANIFEST_SHA,
            'operations': ['init', 'admission'], 'command': COMMAND, 'UI_audio_launch_close': False}))
        return 0
    require(os.getuid() == os.geteuid() == 0, 'root-owned readonly operation required')
    os.umask(0o077)
    archive = read(ARCHIVE, expected=ARCHIVE_SHA)
    require(not os.path.lexists(ROOT), 'fresh root required; never retry a partial attempt')
    ROOT.mkdir(mode=0o700)
    evidence = ROOT / 'evidence'
    evidence.mkdir(mode=0o700)
    result = {'schema': 1, 'success': False, 'request': 'pocket4-bilibili-readonly-r2-01',
        'source_manifest_sha256': MANIFEST_SHA, 'archive_sha256': ARCHIVE_SHA,
        'automatic_retry': False, 'UI_audio_launch_close': False, 'whole_app_production_ready': False,
        'secondary_errors': [], 'cli_operations': []}
    activation = epoch = contract = None
    started = time.monotonic()
    try:
        activation = json.loads(read(ACTIVATION, expected=ACTIVATION_SHA))
        verified = json.loads(read(VERIFIED, expected=VERIFIED_SHA))
        require(activation['main_deployed'] is True and verified['main_deployed'] is True and
                verified['framework_epoch_sha256'] == EPOCH, 'existing Main activation not verified')
        epoch = module(read(EPOCH_SOURCE, expected=EPOCH_SOURCE_SHA), EPOCH_SOURCE, 'bili_readonly_epoch')
        guard = lambda: main_guard(activation, epoch)
        result['Main_before'] = guard()
        source, contract = stage_source(archive)
        common = ['/usr/bin/python3', '-I', str(source / 'recorder.py')]
        scoped = ['--adapter-manifest-sha256', MANIFEST_SHA, '--flow-dir', str(ROOT / 'flow')]
        initial = run_cli('01-init', common + ['init', *scoped, '--activation-after', str(ACTIVATION),
            '--activation-sha256', ACTIVATION_SHA, '--package', PACKAGE, '--component', COMPONENT],
            25, evidence, guard)
        require(initial.get('ok') is True and initial.get('scope_initialized') is True and initial.get('epoch_sha256') == EPOCH,
                'init exact stdout not qualified')
        result['cli_operations'].append('init')
        admission = run_cli('02-admission', common + ['admission', *scoped, '--step', STEP], 80, evidence, guard)
        result['cli_operations'].append('admission')
        step = ROOT / 'flow' / 'steps' / STEP
        durable = json.loads(read(step / 'result.json'))
        require(admission == durable and durable.get('ok') is True and durable.get('action_attempted') is False and
                durable.get('outcome_unknown') is False and durable.get('one_read_only_held_package_uid_command_verified') is True and
                durable.get('ui_or_audio_action_performed') is False and durable.get('action_runner_apk_source_qualified') is False and
                durable.get('whole_app_production_ready') is False, 'durable admission scope/result mismatch')
        intents = sorted(step.glob('command-*.intent.json'))
        require(len(intents) == 1 and intents[0].name == 'command-001.intent.json', 'one exact Android command required')
        intent = json.loads(read(intents[0]))
        require(intent['mutation'] is False and intent['label'] == 'Android command' and
                intent['argv'][-len(COMMAND):] == COMMAND and intent['execution_argv'] == intent['argv'],
                'observed command is not the exact readonly UID query')
        receipt = json.loads(read(step / 'command-001.result.json'))
        require(receipt['returncode'] == 0 and receipt['spawned'] and receipt['owned_command_joined'] and
                not receipt['timed_out'] and not receipt['errors'] and receipt['action_attempted'] is False,
                'actual command receipt not complete')
        require(read(step / 'command-001.stdout') == b'package:tv.danmaku.bili uid:10117\n', 'exact UID stdout differs')
        require(not list(step.glob('transport-*.failure.json')), 'transport failure receipt present')
        require((step / 'transport-001.verified-result.json').is_file(), 'held transport final verification absent')
        contract.verify()
        result['admission_result_sha256'] = digest(read(step / 'result.json'))
        result['success'] = True
    except BaseException as error:
        result['primary_error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        if activation is not None and epoch is not None:
            try:
                result['Main_after'] = main_guard(activation, epoch)
            except BaseException as error:
                result['secondary_errors'].append({'stage': 'final-Main-fence', 'error': repr(error)})
        if contract is not None:
            try:
                contract.verify()
                result['source_unchanged'] = True
            except BaseException as error:
                result['secondary_errors'].append({'stage': 'final-source-fence', 'error': repr(error)})
        result['seconds'] = time.monotonic() - started
        result['success'] = bool(result['success'] and not result['secondary_errors'])
        try:
            pin = write_new(ROOT / 'result.json', result)
        except BaseException as error:
            result['success'] = False
            result['result_write_error'] = repr(error)
            pin = None
        print(json.dumps({'success': result['success'], 'result': pin,
            'primary_error': result.get('primary_error'), 'secondary_errors': result['secondary_errors'],
            'result_write_error': result.get('result_write_error'),
            'UI_audio_launch_close': False, 'whole_app_production_ready': False}), flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
