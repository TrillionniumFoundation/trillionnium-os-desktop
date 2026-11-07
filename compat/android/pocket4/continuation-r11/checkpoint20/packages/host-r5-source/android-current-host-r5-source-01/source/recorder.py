#!/usr/bin/env python3
"""One explicit Pocket4 business-flow step, bound to a typed current baseline.

Private evidence stays in one flow directory. A launched task is closed only by
an explicit cleanup step, using its successful native receipt and saved scope.
This file is a review candidate; writing it does not deploy or run any action.
"""
import argparse
import ast
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import types

EPOCH_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
APP = '/usr/local/bin/android-app'
APP_SHA = 'eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'
BACKEND = '/usr/local/libexec/android-digitalis-observe-helper'
BACKEND_SHA = '088be6d783e80006645a05b8c5b90cd100d3e38b6f3d4634dd499ab1de7898ae'
TASK_SHA = 'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'
ENGINE_SHA = 'c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d'
PRESENTER_SHA = '47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24'
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
CG = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'
ENV = {'PATH': '/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'UNSAFE_INPUT_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def write_new(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def lock_file(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0, 'UNSAFE_LOCK')
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def load_module(path, expected, name):
    raw = read_regular(path)
    require(digest(raw) == expected, 'SOURCE_PIN_CHANGED:' + name)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def task_functions(path):
    raw = read_regular(path)
    require(digest(raw) == TASK_SHA, 'TASK_SOURCE_CHANGED')
    names = {'parse_stacks', 'exact_leaf', 'wait_for_removal'}
    body = [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef) and node.name in names]
    require({node.name for node in body} == names and len(body) == 3, 'TASK_FUNCTION_SET_CHANGED')
    scope = {'re': re, 'time': time, 'now': now, 'require': require}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), scope)
    return types.SimpleNamespace(**{name: scope[name] for name in names})


def source_contract(expected):
    path = Path(__file__).resolve().with_name('source-manifest.json')
    raw = read_regular(path)
    require(len(raw) <= 131072 and digest(raw) == expected, 'EXTERNAL_ADAPTER_MANIFEST_PIN_REQUIRED')
    manifest = json.loads(raw)
    row = manifest['files']['source_contract.py']
    source = load_module(path.with_name('source_contract.py'), row['sha256'], 'bili_source_contract')
    return source, source.SourceContract(path, expected)


class Flow:
    def __init__(self, args):
        self.source, self.contract = source_contract(args.adapter_manifest_sha256)
        self.current_guard = self.contract.load('current_baseline_guard.py', 'p4_current_baseline_guard')
        require(self.current_guard.BASELINE_SHA == self.source.BASELINE_SHA and
                self.current_guard.QUALIFICATION_SHA == self.source.BASELINE_QUALIFICATION_SHA and
                self.current_guard.MAIN_EPOCH == self.source.MAIN_EPOCH,
                'CURRENT_GUARD_LITERAL_BINDING_CHANGED')
        self.current_guard.current_guard()
        self.binding = None
        self.transport = None
        self._android_mutation = False
        self._private_backend_transport = False
        self.root = args.flow_dir
        if args.operation == 'init':
            self.root.mkdir(mode=0o700)
        info = self.root.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,
                'FLOW_DIRECTORY_MUST_BE_PRIVATE_AND_ROOT_OWNED')
        self.lock = lock_file(self.root / 'flow.lock')
        self.epoch = load_module(args.epoch_module, EPOCH_SHA, 'p4_flow_epoch')
        self.app = load_module(APP, APP_SHA, 'p4_flow_android_app')
        self.tasks = task_functions(args.task_source)
        self.step = None
        self.action_attempted = False
        self.command_index = 0
        if args.operation == 'init':
            require(args.current_baseline == self.current_guard.BASELINE_PATH and
                    args.baseline_sha256 == self.source.BASELINE_SHA,
                    'EXPLICIT_CURRENT_BASELINE_INPUT_REQUIRED')
            raw = self.current_guard.raw_file(args.current_baseline, 4*1024*1024,
                    self.source.BASELINE_SHA, self.current_guard.BASELINE_BYTES)
            qualification_raw = self.current_guard.raw_file(self.current_guard.QUALIFICATION_PATH, 65536,
                    self.source.BASELINE_QUALIFICATION_SHA, self.current_guard.QUALIFICATION_BYTES)
            self.activation = json.loads(raw)  # Compatibility attribute; only the new typed baseline is accepted.
            require(self.activation == self.current_guard.current_baseline(),
                    'CURRENT_BASELINE_DIFFERS_FROM_QUALIFIED_ORIGINAL')
            bound = self.activation['framework_epoch']
            require(self.activation.get('schema') == self.source.BASELINE_SCHEMA and
                    'main_deployed' not in self.activation and self.activation.get('deployment_performed') is False,
                    'CURRENT_BASELINE_IS_NOT_A_DEPLOYMENT_RECEIPT')
            require(self.activation['engine_sha256'] == ENGINE_SHA and
                    self.activation['presenter_sha256'] == PRESENTER_SHA, 'WRONG_BASELINE_ARTIFACTS')
            require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', args.package), 'INVALID_PACKAGE')
            require(re.fullmatch(re.escape(args.package) + r'/[A-Za-z0-9_.$]+', args.component), 'INVALID_COMPONENT')
            self.scope = {'schema':'pocket4-current-recorder-scope-v1',
                          'current_baseline_schema':self.source.BASELINE_SCHEMA,
                          'package': args.package, 'component': args.component,
                          'uid': self.activation['packages'][args.package], 'user': 0,
                          'current_baseline_sha256': digest(raw),
                          'current_baseline_qualification_sha256': digest(qualification_raw),
                          'historical_activation_sha256':self.source.HISTORICAL_ACTIVATION_SHA,
                          'historical_verified_sha256':self.source.HISTORICAL_VERIFIED_SHA,
                          'epoch_sha256': bound['sha256'], 'created_utc': now(),
                          'adapter_manifest_sha256': self.contract.sha256,
                          'recorder_sha256': digest(read_regular(__file__)), 'automatic_retry': False}
            self.guard()
            write_new(self.root / 'baseline.json', raw)
            write_new(self.root / 'baseline-qualification.json', qualification_raw)
            write_new(self.root / 'scope.json', self.scope)
            (self.root / 'steps').mkdir(mode=0o700)
            (self.root / 'reconciliations').mkdir(mode=0o700)
        else:
            self.scope = json.loads(read_regular(self.root / 'scope.json'))
            raw = self.current_guard.raw_file(self.root / 'baseline.json', 4*1024*1024,
                    self.source.BASELINE_SHA, self.current_guard.BASELINE_BYTES)
            self.current_guard.raw_file(self.root / 'baseline-qualification.json', 65536,
                    self.source.BASELINE_QUALIFICATION_SHA, self.current_guard.QUALIFICATION_BYTES)
            require(self.scope.get('current_baseline_sha256') == self.source.BASELINE_SHA and
                    self.scope.get('current_baseline_qualification_sha256') == self.source.BASELINE_QUALIFICATION_SHA,
                    'SAVED_CURRENT_BASELINE_CHANGED')
            require(digest(read_regular(__file__)) == self.scope['recorder_sha256'], 'RECORDER_CHANGED_MID_FLOW')
            self.activation = json.loads(raw)
        self.source.verify_scope(self.scope, self.activation, self.contract)

    def guard(self, attempted=False):
        self.contract.verify()
        self.source.verify_scope(self.scope, self.activation, self.contract)
        self.current_guard.current_guard(self.activation, action_attempted=attempted)
        self.epoch.require_unchanged(self.activation['framework_epoch'], action_attempted=attempted)
        for path, pin in ((APP, APP_SHA), (BACKEND, BACKEND_SHA)):
            require(digest(read_regular(path)) == pin, 'HELPER_CHANGED')
        require(digest(read_regular('/etc/droidloom/cell.json')) == CELL_SHA, 'MAIN_CONFIG_CHANGED')
        for field in ('daemon_process', 'launcher_process', 'presenter_process'):
            identity = self.activation[field]
            require(self.epoch.process_identity(identity['host_pid']) == identity, 'HOST_PROCESS_CHANGED:' + field)
        require({key: (CG / key).read_text().strip() for key in self.activation['limits']} ==
                self.activation['limits'], 'MAIN_LIMITS_CHANGED')
        self.epoch.require_unchanged(self.activation['framework_epoch'], action_attempted=attempted)
        if self.binding is not None:
            self.binding.verify()

    def close(self):
        # The synchronous command path joins every subprocess before return.
        # HeldTarget refuses FD release if a command could not be joined.
        if self.binding is not None:
            self.binding.close()
        # As in the original one-step CLI, flow.lock is held until process exit,
        # including the final durable step result. It is never passed to a child.

    def bind(self):
        if self.binding is not None:
            return self.binding
        module = self.contract.load('main_binding.py', 'bili_main_binding')
        binding = module.MainBinding(contract=self.contract, source=self.source, scope=self.scope,
            activation=self.activation, epoch=self.epoch, app=self.app, guard=lambda: self.guard())
        try:
            write_new(self.step / 'held-main-binding.json', binding.record)
        except BaseException as original:
            try:
                binding.close()
            except BaseException as secondary:
                original.add_note('held binding close: ' + type(secondary).__name__)
            raise
        self.binding = binding
        def record(kind, value):
            write_new(self.step / ('transport-%03d.%s.json' % (value['sequence'], kind)), value)
        def runner(argv, **options):
            require(options['close_fds'] is True and options['stdout'] == subprocess.PIPE and
                    options['stderr'] == subprocess.PIPE, 'HELD_RUNNER_IO_PROTOCOL_CHANGED')
            if self._private_backend_transport:
                # The existing backend crops a screencap in memory before it
                # emits the scoped observation. Do not persist its unscoped
                # frame or intermediate native tree as a new raw log.
                self.action_attempted |= self._android_mutation
                return subprocess.run(argv, **options)
            return self.command(argv, options['timeout'], mutation=self._android_mutation,
                label='Android command', pass_fds=options['pass_fds'], check=False,
                host_env=options['env'])
        self.transport = binding.transport(record=record, runner=runner,
            guard=lambda action_attempted: self.guard(attempted=self.action_attempted))
        return binding

    def begin(self, args, mutation):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.step), 'INVALID_STEP_NAME')
        if mutation and args.operation != 'cleanup':
            for intent in (self.root / 'steps').glob('*/intent.json'):
                prior = json.loads(read_regular(intent))
                if not prior['mutation']:
                    continue
                result = intent.with_name('result.json')
                require(result.exists() and (json.loads(read_regular(result)).get('outcome_unknown') is False or
                        self.reconciled(intent.parent.name)),
                        'PRIOR_ACTION_OUTCOME_UNKNOWN_NO_REPLAY')
        selected = self.root / 'steps' / args.step
        selected.mkdir(mode=0o700)  # Do not claim or finalize an existing/incomplete step.
        self.step = selected
        write_new(self.step / 'intent.json', {'operation': args.operation, 'mutation': mutation,
                  'request': args.request, 'unknown_step': args.unknown_step,
                  'observation_step': args.observation_step, 'postcondition': args.postcondition,
                  'scope': self.scope, 'started_utc': now(), 'automatic_retry': False})
        self.guard()

    def reconciled(self, step_name):
        path = self.root / 'reconciliations' / (step_name + '.json')
        if not path.exists():
            return False
        receipt = json.loads(read_regular(path))
        require(receipt['schema'] == 'pocket4-flow-explicit-reconciliation-v1' and
                receipt['unknown_step'] == step_name and receipt['epoch_sha256'] == self.scope['epoch_sha256'] and
                receipt['scope_sha256'] == digest(read_regular(self.root / 'scope.json')) and
                receipt['original_action_outcome'] == 'unknown_retained' and
                receipt['allows_new_decisions_only'] is True, 'RECONCILIATION_SCOPE_CHANGED')
        for relative, expected in receipt['evidence_sha256'].items():
            rel = Path(relative)
            require(not rel.is_absolute() and '..' not in rel.parts, 'RECONCILIATION_PATH_INVALID')
            require(digest(read_regular(self.root / rel)) == expected, 'RECONCILIATION_EVIDENCE_CHANGED')
        return True

    def saved_step(self, name):
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name), 'INVALID_SAVED_STEP')
        folder = self.root / 'steps' / name
        hashes = {}
        def read(relative):
            path = folder / relative
            raw = read_regular(path)
            hashes[path.relative_to(self.root).as_posix()] = digest(raw)
            return raw
        intent, result = json.loads(read('intent.json')), json.loads(read('result.json'))
        require(intent['scope'] == self.scope and result['epoch_sha256'] == self.scope['epoch_sha256'], 'SAVED_STEP_SCOPE_CHANGED')
        commands = []
        for path in sorted(folder.glob('command-*.intent.json')):
            stem = path.name.removesuffix('.intent.json')
            ci, cr = json.loads(read(stem + '.intent.json')), json.loads(read(stem + '.result.json'))
            stdout, stderr = read(stem + '.stdout'), read(stem + '.stderr')
            require(digest(stdout) == cr['stdout_sha256'] and digest(stderr) == cr['stderr_sha256'], 'SAVED_RAW_COMMAND_CHANGED')
            commands.append((ci, cr, stdout))
        require(bool(commands), 'NO_COMPLETE_ORIGINAL_COMMAND_EVIDENCE')
        if isinstance(intent.get('request'), dict) and intent['request'].get('op') == 'observe':
            png = read('observation.png')
            require(png.startswith(b'\x89PNG\r\n\x1a\n'), 'OBSERVATION_PNG_INVALID')
            png_meta = json.loads(read('observation-png.json'))
            require(png_meta == {'sha256': digest(png), 'bytes': len(png)}, 'OBSERVATION_PNG_RECEIPT_CHANGED')
        return intent, result, commands, hashes

    def reconcile(self, args):
        # A new decision from a later observation; never rewrite or replay the old action.
        unknown, failed, old_commands, old_hashes = self.saved_step(args.unknown_step)
        observed, passed, new_commands, new_hashes = self.saved_step(args.observation_step)
        require(unknown['operation'] == 'ui' and unknown['mutation'] is True and
                unknown['request']['op'] in ('click', 'set-text') and
                failed['action_attempted'] is True and failed['outcome_unknown'] is True,
                'ONLY_COMPLETED_UNKNOWN_UI_ACTION_MAY_BE_RECONCILED')
        require(observed['operation'] == 'ui' and observed['mutation'] is False and
                observed['request']['op'] in ('dump', 'observe') and passed['ok'] is True and
                passed['action_attempted'] is False and passed['outcome_unknown'] is False,
                'FRESH_SUCCESSFUL_READ_ONLY_OBSERVATION_REQUIRED')
        times = [datetime.datetime.fromisoformat(value) for value in
                 (unknown['started_utc'], failed['ended_utc'], observed['started_utc'], passed['ended_utc'], now())]
        require(all(value.tzinfo is not None for value in times) and times == sorted(times), 'RECONCILIATION_SEQUENCE_INVALID')
        def helper_command(commands, operation):
            selected = [(ci, cr, raw) for ci, cr, raw in commands if ci.get('label') == 'Existing android-app CLI']
            require(len(selected) == 1, 'UNIQUE_ORIGINAL_HELPER_COMMAND_REQUIRED')
            ci, cr, raw = selected[0]
            argv = ci['argv']
            require(argv[:5] == [APP, '--interactive-production', operation, '--package', self.scope['package']], 'HELPER_COMMAND_SCOPE_CHANGED')
            return ci, cr, raw
        old_ci, old_cr, _ = helper_command(old_commands, unknown['request']['op'])
        require(old_ci['mutation'] is True and old_cr['spawned'] is True and old_cr['action_attempted'] is True,
                'ORIGINAL_ACTION_RECEIPT_INCOMPLETE')
        new_ci, new_cr, raw = helper_command(new_commands, observed['request']['op'])
        require(new_ci['mutation'] is False and new_cr['returncode'] == 0 and not new_cr['timed_out'] and
                new_cr['error'] is None, 'OBSERVATION_COMMAND_NOT_SUCCESSFUL')
        observation = json.loads(raw)
        require(observation.get('ok') is True and observation.get('outcome_unknown') is not True, 'OBSERVATION_HELPER_UNCERTAIN')
        native = observation if observed['request']['op'] == 'dump' else observation.get('native')
        require(isinstance(native, dict) and native.get('ok') is True and isinstance(native.get('nodes'), list) and
                isinstance(native.get('window_context'), dict), 'NO_ACTUAL_NATIVE_NODE_LIST')
        condition = args.postcondition
        allowed = {'text', 'resource-id', 'content-desc', 'class', 'enabled', 'clickable'}
        require(isinstance(condition, dict) and condition and not set(condition) - allowed, 'INVALID_POSTCONDITION')
        require(any(isinstance(condition.get(k), str) and condition[k] for k in ('text', 'resource-id', 'content-desc')),
                'EXPLICIT_NONEMPTY_NODE_IDENTITY_REQUIRED')
        for key, value in condition.items():
            require(type(value) is (bool if key in ('enabled', 'clickable') else str), 'POSTCONDITION_VALUE_TYPE')
        matching = [node for node in native['nodes'] if isinstance(node, dict) and
                    node.get('package') == self.scope['package'] and node.get('visible') is True and
                    all(node.get(key) == value for key, value in condition.items())]
        require(len(matching) == 1, 'POSTCONDITION_MUST_MATCH_ONE_REAL_VISIBLE_NODE')
        selected = self.selected_task()
        _, roots, _ = self.stacks()
        require(self.tasks.exact_leaf(roots, selected['task'], self.scope['package']), 'RECONCILIATION_TASK_SCOPE_CHANGED')
        self.guard()
        receipt = {'schema': 'pocket4-flow-explicit-reconciliation-v1', 'created_utc': now(),
                   'unknown_step': args.unknown_step, 'observation_step': args.observation_step,
                   'epoch_sha256': self.scope['epoch_sha256'], 'scope_sha256': digest(read_regular(self.root / 'scope.json')),
                   'evidence_sha256': {**old_hashes, **new_hashes}, 'postcondition': condition,
                   'matched_native_node': matching[0],
                   'matched_native_node_sha256': digest(json.dumps(matching[0], sort_keys=True, separators=(',', ':')).encode()),
                   'original_action_outcome': 'unknown_retained', 'allows_new_decisions_only': True,
                   'business_success_verified': False, 'old_action_replayed': False, 'automatic_retry': False}
        write_new(self.root / 'reconciliations' / (args.unknown_step + '.json'), receipt)
        return {'explicit_reconciliation_recorded': True, 'original_action_outcome': 'unknown_retained',
                'continue_from_observation_step': args.observation_step, 'old_action_replayed': False}

    def command(self, argv, timeout, *, mutation=False, label=None, pass_fds=(),
                check=True, host_env=None):
        self.guard()
        require(check or (label == 'Android command' and len(pass_fds) == 7),
                'UNCHECKED_COMMAND_ONLY_FOR_HELD_TRANSPORT')
        self.command_index += 1
        stem = self.step / ('command-%03d' % self.command_index)
        execution = list(argv)
        if label == 'Existing android-app CLI':
            require(not pass_fds and check and argv[:2] == [APP, '--interactive-production'],
                    'EXISTING_CLIENT_ENTRY_CHANGED')
            execution = ['/usr/bin/python3', '-I', str(self.contract.root / 'existing_ui_entry.py'),
                         'client', '--adapter-manifest-sha256', self.contract.sha256,
                         '--flow-dir', str(self.root), '--step', self.step.name,
                         '--command', stem.name, '--', *argv[1:]]
        write_new(str(stem) + '.intent.json', {'argv': argv, 'timeout_seconds': timeout,
                  'execution_argv': execution, 'authority_fds_passed': list(pass_fds),
                  'mutation': mutation, 'label': label, 'started_utc': now(), 'automatic_retry': False})
        started = time.monotonic()
        timed_out = False
        spawned = False
        rc = None
        errors = []
        streams = []
        process = None
        joined = True
        def remember(phase, exc):
            errors.append({'phase': phase, 'exception_type': type(exc).__name__,
                           'errno': getattr(exc, 'errno', None)})
        try:
            stdout = open(str(stem) + '.stdout', 'xb'); streams.append(stdout)
            stderr = open(str(stem) + '.stderr', 'xb'); streams.append(stderr)
            try:
                process = subprocess.Popen(execution, stdout=stdout, stderr=stderr,
                    env=ENV if host_env is None else host_env, start_new_session=True,
                    pass_fds=tuple(pass_fds), close_fds=True)
                spawned = True
                joined = False
                self.action_attempted |= mutation
                try:
                    rc = process.wait(timeout=timeout)
                    joined = True
                except BaseException as exc:
                    timed_out = isinstance(exc, subprocess.TimeoutExpired)
                    remember('command_wait', exc)
                    # Only this newly spawned command session; Binder-launched app outcome remains unknown.
                    try:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                    except BaseException as kill_error:
                        remember('owned_command_group_stop', kill_error)
                    try:
                        rc = process.wait(timeout=5)
                        joined = True
                    except BaseException as join_error:
                        remember('owned_command_join', join_error)
            except BaseException as exc:
                remember('command_spawn_or_wait', exc)
        except BaseException as exc:
            remember('command_output_open', exc)
        finally:
            for stream in streams:
                try:
                    stream.flush(); os.fsync(stream.fileno())
                except BaseException as exc:
                    remember('command_output_sync', exc)
                try:
                    stream.close()
                except BaseException as exc:
                    remember('command_output_close', exc)
        if not joined and self.binding is not None:
            self.binding.target.poison_unjoined_command()
        def observed_output(suffix):
            try:
                return read_regular(str(stem) + suffix)
            except BaseException as exc:
                remember('command_output_read', exc)
                return b''
        out, err = observed_output('.stdout'), observed_output('.stderr')
        receipt = {'ended_utc': now(), 'seconds': time.monotonic() - started, 'returncode': rc,
                   'timed_out': timed_out, 'spawned': spawned, 'error': errors[0] if errors else None,
                   'errors': list(errors), 'owned_command_joined': joined,
                   'stdout_sha256': digest(out), 'stderr_sha256': digest(err),
                   'action_attempted': spawned and mutation, 'automatic_retry': False}
        try:
            write_new(str(stem) + '.result.json', receipt)  # Observe before lease release or post guard.
        except BaseException as exc:
            remember('command_result_record', exc)
        captured = subprocess.CompletedProcess(execution, rc, out, err)
        captured.host_timed_out = timed_out
        captured.recorder_errors = errors
        captured.recorder_spawned = spawned
        captured.recorder_joined = joined
        if not check:
            # BoundArun retains the actual command result first, then separately
            # performs lease release, the mandatory post guard, and secondary errors.
            return captured
        try:
            self.guard(attempted=self.action_attempted)
        except BaseException as exc:
            remember('post_command_guard', exc)
        if timed_out or rc != 0 or errors:
            code = ('COMMAND_TIMED_OUT' if timed_out else 'COMMAND_FAILED' if rc != 0
                    else 'COMMAND_EVIDENCE_OR_POST_GUARD_FAILED')
            failure = RuntimeError(code)
            failure.command_observation = {**receipt, 'errors': errors}
            raise failure
        return out

    def android(self, argv, timeout=20, *, mutation=False):
        self.bind()
        self._android_mutation = mutation
        try:
            return self.transport(argv, timeout)
        finally:
            self._android_mutation = False

    def stacks(self, timeout=20):
        raw = self.android(['/system/bin/cmd', 'activity', 'stack', 'list'], timeout).decode('utf-8', 'strict')
        roots, tasks = self.tasks.parse_stacks(raw)
        return raw, roots, tasks

    def admission(self):
        self.bind()
        raw = self.android(['/system/bin/cmd', 'package', 'list', 'packages', '-U', '--user', '0',
                            self.scope['package']], 8).decode('utf-8', 'strict')
        require(raw.splitlines() == ['package:%s uid:%d' % (self.scope['package'], self.scope['uid'])],
                'HELD_ENTRY_PACKAGE_UID_READBACK_DIFFERS')
        return {'fixed_main_namespace_classpath_uid_data_binding_verified': True,
                'one_read_only_held_package_uid_command_verified': True,
                'ui_or_audio_action_performed': False,
                'action_runner_apk_source_qualified': False,
                'whole_app_production_ready': False}

    def selected_task(self):
        launched = json.loads(read_regular(self.root / 'launch-scope.json'))
        require(launched['epoch_sha256'] == self.scope['epoch_sha256'], 'LAUNCH_EPOCH_CHANGED')
        return launched

    def launch(self):
        lock = lock_file(ACTION_LOCK)
        try:
            return self.launch_locked()
        finally:
            os.close(lock)

    def launch_locked(self):
        require(not (self.root / 'launch-attempted.json').exists(), 'NATIVE_LAUNCH_ALREADY_ATTEMPTED')
        raw, pre_roots, pre_tasks = self.stacks()
        write_new(self.step / 'prelaunch-stacks.txt', raw.encode())
        require(not any(child['component'].split('/')[0] == self.scope['package']
                        for root in pre_roots.values() for child in root['children']),
                'PREEXISTING_BILIBILI_TASK_PRESERVED_NO_LAUNCH')
        write_new(self.root / 'launch-attempted.json', {'step': self.step.name, 'time_utc': now(), 'scope': self.scope})
        argv = ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env',
                'XDG_RUNTIME_DIR=/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
                '/usr/bin/droidloomctl', 'launch', self.scope['package'], '--component', self.scope['component'], '--json']
        returned = self.command(argv, 70, mutation=True, label='One native launch')
        receipt = json.loads(returned)
        require(receipt.get('ok') is True and receipt.get('state') == 'running' and
                receipt.get('host_pid') == self.activation['status']['host_pid'] and
                receipt.get('outcome_unknown') is not True, 'NATIVE_LAUNCH_RECEIPT_UNCERTAIN')
        match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)', receipt.get('launch', ''))
        require(match is not None and int(match[3]) == 0, 'NATIVE_TASK_NOT_IDENTIFIED')
        task = int(match[4])
        _, roots, tasks = self.stacks()
        require(self.tasks.exact_leaf(roots, task, self.scope['package']), 'NATIVE_TASK_NOT_EXACT_LEAF')
        absent = task not in pre_tasks and task not in pre_roots
        require(tasks == pre_tasks | {task}, 'TASK_SET_CHANGED_DURING_LAUNCH')
        scope = {'task': task, 'package': self.scope['package'], 'epoch_sha256': self.scope['epoch_sha256'],
                 'prelaunch_absent': absent, 'cleanup_allowed': absent, 'launch_step': self.step.name,
                 'prelaunch_task_ids': sorted(pre_tasks), 'native_receipt_sha256': digest(returned)}
        write_new(self.root / 'launch-scope.json', scope)
        return {'native_launch_acknowledged': True, 'cleanup_allowed': absent, 'business_success_verified': False}

    def ui(self, request):
        selected = self.selected_task()
        _, roots, _ = self.stacks()
        require(self.tasks.exact_leaf(roots, selected['task'], self.scope['package']), 'FLOW_TASK_SCOPE_CHANGED')
        argv = [APP, '--interactive-production', request['op'], '--package', self.scope['package']]
        allowed = {'op', 'selector', 'value', 'index', 'accessibility_mode', 'method'}
        require(not set(request) - allowed, 'UNSUPPORTED_UI_REQUEST_FIELD')
        require(request['op'] in ('dump', 'find', 'click', 'set-text', 'observe'), 'UNSUPPORTED_UI_OPERATION')
        for key, value in request.get('selector', {}).items():
            require(key in ('text', 'contains', 'id', 'desc', 'class', 'focused', 'editable', 'enabled',
                            'clickable', 'scrollable', 'selected', 'checked'), 'UNSUPPORTED_SELECTOR')
            if type(value) is bool:
                require(key in ('focused', 'editable', 'enabled', 'clickable', 'scrollable', 'selected', 'checked'), 'BOOLEAN_SELECTOR')
                argv += ['--' + ('' if value else 'no-') + key]
            else:
                require(isinstance(value, str), 'STRING_SELECTOR')
                argv += ['--' + key, value]
        for key in ('index', 'accessibility_mode', 'method'):
            if key in request:
                argv += ['--' + key.replace('_', '-'), str(request[key])]
        if request['op'] == 'set-text':
            require(isinstance(request.get('value'), str), 'TEXT_REQUIRED')
            argv += ['--', request['value']]
        if request['op'] == 'observe':
            argv += ['--output', str(self.step / 'observation.png')]
        returned = self.command(argv, 90, mutation=request['op'] in ('click', 'set-text'), label='Existing android-app CLI')
        result = json.loads(returned)
        require(result.get('ok') is True and result.get('outcome_unknown') is not True, 'UI_RESULT_UNCERTAIN')
        if request['op'] == 'observe':
            png = read_regular(self.step / 'observation.png')
            fd = os.open(self.step / 'observation.png', os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            write_new(self.step / 'observation-png.json', {'sha256': digest(png), 'bytes': len(png)})
            require(png.startswith(b'\x89PNG\r\n\x1a\n'), 'OBSERVATION_PNG_INVALID')
        _, roots, _ = self.stacks()
        require(self.tasks.exact_leaf(roots, selected['task'], self.scope['package']), 'POST_ACTION_TASK_SCOPE_CHANGED')
        return {'helper_result_acknowledged': True, 'business_success_verified': False}

    def engine_maps(self):
        bound = self.activation['framework_epoch']['binding']['processes']['init']
        found = []
        for path in Path('/proc').iterdir():
            if not path.name.isdecimal():
                continue
            try:
                if (path / 'cmdline').read_bytes().split(b'\0')[0].decode() != self.scope['package']:
                    continue
                identity = self.epoch.process_identity(int(path.name))
                if identity['namespaces']['pid'] == bound['namespaces']['pid']:
                    found.append(identity)
            except (OSError, UnicodeError):
                continue
        require(len(found) == 1, 'NO_UNIQUE_LIVE_MAIN_APP_PROCESS')
        identity = found[0]
        require(identity['uids'] == [self.scope['uid']] * 4, 'APP_UID_CHANGED')
        require(any(line.startswith('0::/system.slice/droidloomd.service/') for line in identity['cgroup']), 'APP_OUTSIDE_MAIN')
        proc = Path('/proc') / str(identity['host_pid'])
        maps = (proc / 'maps').read_bytes()
        write_new(self.step / 'actual-host-maps.txt', maps)
        engine = proc / 'root/system/lib64/libberberis_arm64.so'
        info = engine.stat()
        engine_hash = digest(engine.read_bytes())
        rows = [line.split(maxsplit=5) for line in maps.decode().splitlines() if 'libberberis_arm64.so' in line]
        write_new(self.step / 'engine-binding-observed.json', {'process': identity, 'engine_sha256': engine_hash,
                  'device': info.st_dev, 'inode': info.st_ino, 'mapping_rows': rows})
        require(engine_hash == ENGINE_SHA and bool(rows), 'ENGINE_NOT_MAPPED_OR_WRONG_BYTES')
        for row in rows:
            require(len(row) == 6 and row[5] == '/system/lib64/libberberis_arm64.so', 'ENGINE_MAPPING_PATH')
            major, minor = (int(part, 16) for part in row[3].split(':'))
            require(os.makedev(major, minor) == info.st_dev and int(row[4]) == info.st_ino, 'ENGINE_MAPPING_INODE')
        final_info = engine.stat()
        require(self.epoch.process_identity(identity['host_pid']) == identity and
                all(getattr(info, key) == getattr(final_info, key)
                    for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')),
                'APP_CHANGED_DURING_MAPS_READ')
        self.guard()
        return {'actual_app_engine_mapping_verified': True, 'engine_sha256': engine_hash, 'translation_business_success_verified': False}

    def cleanup(self):
        selected = self.selected_task()
        if not selected['cleanup_allowed']:
            return {'preexisting_task_preserved': True, 'removal_attempted': False}
        require(not (self.root / 'cleanup-attempted.json').exists(), 'CLEANUP_ALREADY_ATTEMPTED_NO_REPLAY')
        lock = lock_file(ACTION_LOCK)
        try:
            _, roots, tasks = self.stacks()
            task = selected['task']
            if task not in tasks and task not in roots:
                return {'new_task_already_absent': True, 'removal_attempted': False}
            require(self.tasks.exact_leaf(roots, task, self.scope['package']), 'CLEANUP_TASK_SCOPE_CHANGED')
            write_new(self.root / 'cleanup-attempted.json', {'step': self.step.name, 'selected': selected,
                      'time_utc': now(), 'automatic_retry': False})
            self.android(['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)], 20, mutation=True)
            observations = []
            def record(value):
                observations.append(value)
                write_new(self.step / ('cleanup-observation-%02d.json' % len(observations)), value)
            def read_stacks(timeout):
                return self.android(['/system/bin/cmd', 'activity', 'stack', 'list'], timeout).decode('utf-8', 'strict')
            completed = self.tasks.wait_for_removal(read_stacks, task, self.scope['package'], tasks, record)
            self.guard(attempted=True)
            return {'new_leaf_removed_and_verified': True, 'other_tasks_preserved': True, **completed}
        finally:
            os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('init', 'admission', 'launch', 'ui', 'exit-info', 'engine-maps', 'cleanup', 'reconcile'))
    parser.add_argument('--adapter-manifest-sha256', required=True)
    parser.add_argument('--flow-dir', type=Path, required=True)
    parser.add_argument('--step')
    parser.add_argument('--current-baseline', type=Path)
    parser.add_argument('--baseline-sha256')
    parser.add_argument('--package')
    parser.add_argument('--component')
    parser.add_argument('--epoch-module', type=Path, default=Path(__file__).resolve().parent / 'references/framework_epoch.py')
    parser.add_argument('--task-source', type=Path, default=Path(__file__).resolve().parent / 'references/task_scope_baseline.py')
    parser.add_argument('--request', type=json.loads)
    parser.add_argument('--unknown-step')
    parser.add_argument('--observation-step')
    parser.add_argument('--postcondition', type=json.loads)
    args = parser.parse_args()
    require(os.geteuid() == 0, 'ROOT_REQUIRED_FOR_EPOCH_AND_NAMESPACE_READS')
    os.umask(0o077)
    flow = Flow(args)
    if args.operation == 'init':
        flow.close()
        print(json.dumps({'ok': True, 'scope_initialized': True, 'epoch_sha256': flow.scope['epoch_sha256']}))
        return
    require(args.step is not None, 'EXPLICIT_UNIQUE_STEP_REQUIRED')
    require(args.operation != 'ui' or isinstance(args.request, dict), 'UI_REQUEST_OBJECT_REQUIRED')
    mutation = args.operation in ('launch', 'cleanup') or (args.operation == 'ui' and args.request.get('op') in ('click', 'set-text'))
    result = {'ok': False, 'automatic_retry': False, 'action_attempted': False, 'outcome_unknown': False,
              'business_success_verified': False}
    try:
        flow.begin(args, mutation)
        if args.operation == 'admission':
            result.update(flow.admission())
        elif args.operation == 'launch':
            result.update(flow.launch())
        elif args.operation == 'ui':
            result.update(flow.ui(args.request))
        elif args.operation == 'exit-info':
            flow.android(['/system/bin/dumpsys', 'activity', 'exit-info', flow.scope['package']], 20)
            result['read_only_package_exit_info_captured'] = True
        elif args.operation == 'engine-maps':
            result.update(flow.engine_maps())
        elif args.operation == 'reconcile':
            result.update(flow.reconcile(args))
        else:
            result.update(flow.cleanup())
        flow.guard(attempted=flow.action_attempted)
        result['ok'] = True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), outcome_unknown=flow.action_attempted)
        if hasattr(exc, 'command_observation'):
            result['command_observation'] = exc.command_observation
        if hasattr(exc, 'details'):
            result['transport_failure'] = exc.details
    finally:
        try:
            flow.close()
        except BaseException as exc:
            result['ok'] = False
            result['outcome_unknown'] = flow.action_attempted
            if 'error' not in result:
                result.update(error_type=type(exc).__name__, error='HELD_BINDING_RELEASE_FAILED')
            result['release_error_type'] = type(exc).__name__
    result.update(action_attempted=flow.action_attempted, ended_utc=now(), epoch_sha256=flow.scope['epoch_sha256'])
    if flow.step is not None:
        write_new(flow.step / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if not result['ok']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
