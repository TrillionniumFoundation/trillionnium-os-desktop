"""Offline controls on actual recorder/client/backend/task functions.

No Main process or Android command is invoked. Namespace authority uses seven
real disposable FDs behind an explicit target seam. Command lifecycle controls
do run and reap one owned local Python child. All task/UI outputs are fixtures.
"""
import ast
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import errno
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]


def load(name, filename):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(Path(filename).read_bytes(), module.__file__, 'exec'), module.__dict__)
    return module


R = load('actual_integrated_recorder', HERE / 'recorder.py')
E = load('actual_existing_ui_entry', HERE / 'existing_ui_entry.py')
M = load('actual_integrated_transport', HERE / 'bound_android_transport.py')
S = load('actual_source_contract', HERE / 'source_contract.py')
B = load('actual_main_binding', HERE / 'main_binding.py')
OLD = load('actual_original_recorder', HERE / 'references/original_recorder.py')
R3 = load('actual_frozen_transport_r3', HERE / 'references/bound_android_transport_r3.py')
TASKS = R.task_functions(HERE / 'references/task_scope_baseline.py')
ENV = {'PATH': '/system/bin:/system/xbin', 'BOOTCLASSPATH': '/apex/owned/a.jar',
    'DEX2OATBOOTCLASSPATH': '/apex/owned/a.jar', 'ANDROID_ROOT': '/system',
    'ANDROID_DATA': '/data', 'ANDROID_ART_ROOT': '/apex/com.android.art'}
PKG = S.PACKAGE


def stacks(*items):
    return ''.join('RootTask id=%d displayId=0 userId=0 mWindowingMode=freeform\n'
                   '  taskId=%d: %s/.Main visible=true userId=0\n' % (task, task, package)
                   for task, package in items)


HOME = stacks((41, 'owned.home'))
BILI = HOME + stacks((42, PKG))


class Target:
    """Explicit namespace seam, never a setns or Main identity substitute."""
    def __init__(self):
        self.expected = {'pid': 41001}
        self.helper_sha256 = M.HELD_HELPER_SHA256
        self.fds = [os.open('/dev/null', os.O_RDONLY | os.O_CLOEXEC) for _ in range(7)]
        self.active = 0
        self.exit_error = False
        self.poisoned = False

    def verify(self):
        if self.poisoned:
            raise RuntimeError('unjoined command')

    @contextmanager
    def entry(self, command):
        self.active += 1
        try:
            yield ['/qualified/held-entry', '--', *command], self.fds
        finally:
            self.active -= 1
            if self.exit_error:
                raise OSError(9, 'owned lease release seam')

    def poison_unjoined_command(self):
        self.poisoned = True

    def close(self):
        assert self.active == 0
        for fd in self.fds:
            os.close(fd)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bili-recorder-local-')
        self.root = Path(self.temp.name)
        self.step = self.root / 'steps' / 'owned-step'
        self.step.mkdir(parents=True, mode=0o700)
        self.target = Target()
        self.guards = []
        self.calls = []
        self.events = []
        self.flow = R.Flow.__new__(R.Flow)
        f = self.flow
        f.root, f.step, f.tasks = self.root, self.step, TASKS
        f.scope = {'package': PKG, 'uid': 10117, 'user': 0, 'component': S.COMPONENT,
                   'epoch_sha256': S.MAIN_EPOCH}
        f.activation = {'status': {'host_pid': 42001}}
        f.action_attempted = False
        f.command_index = 0
        f.binding = None
        f.transport = None
        f.lock = None
        f._android_mutation = False
        f._private_backend_transport = False
        f.guard = lambda attempted=False: self.guards.append(attempted)
        f.contract = types.SimpleNamespace(root=HERE, sha256='a' * 64)
        self.lock_patch = patch.object(R, 'ACTION_LOCK', str(self.root / 'actions.lock'))
        self.lock_patch.start()

    def tearDown(self):
        self.lock_patch.stop()
        self.target.close()
        self.temp.cleanup()

    def transport(self, runner, module=M, record=None):
        def guard(*, action_attempted):
            self.guards.append(action_attempted)
        def journal(kind, value):
            self.events.append((kind, value))
        return module.BoundArun(target=self.target, environment=ENV, guard=guard,
            record=record or journal, epoch_sha256=S.MAIN_EPOCH, init_pid=41001,
            package=PKG, uid=10117, interactive_production=True, runner=runner)

    def attach_fixture_transport(self, output):
        def runner(argv, **options):
            self.calls.append((argv, options))
            return subprocess.CompletedProcess(argv, 0, output, b'')
        self.flow.binding = types.SimpleNamespace(target=self.target)
        self.flow.transport = self.transport(runner)

    def selected(self, allowed=True):
        R.write_new(self.root / 'launch-scope.json', {'task': 42, 'package': PKG,
            'cleanup_allowed': allowed, 'prelaunch_absent': allowed,
            'epoch_sha256': S.MAIN_EPOCH})

    def fixture_android(self, responses, failure=None):
        queue = iter(responses)
        def command(argv, timeout=20, *, mutation=False):
            self.calls.append((argv, timeout, mutation))
            if mutation:
                self.flow.action_attempted = True
                if failure:
                    raise failure
                return b''
            return next(queue).encode()
        self.flow.android = command

    def test_01_reference_bytes_are_exact(self):
        for name, (size, digest) in S.REFERENCE_PINS.items():
            raw = (HERE / name).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (size, digest))

    def test_02_business_and_cleanup_functions_retain_original_ast(self):
        def methods(path):
            tree = ast.parse(path.read_bytes())
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Flow')
            return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        old, new = methods(HERE / 'references/original_recorder.py'), methods(HERE / 'recorder.py')
        for name in ('begin', 'reconciled', 'saved_step', 'reconcile', 'stacks', 'selected_task',
                     'ui', 'cleanup', 'engine_maps'):
            self.assertEqual(ast.dump(old[name]), ast.dump(new[name]), name)
        # This caught the risk of accidentally moving a fence into unreachable code.
        self.assertEqual([ast.dump(n) for n in old['guard'].body],
                         [ast.dump(n) for n in new['guard'].body[2:-1]])

    def test_03_original_android_uses_numeric_target_negative(self):
        f = OLD.Flow.__new__(OLD.Flow)
        f.guard = lambda: None
        f.activation = {'framework_epoch': {'binding': {'processes': {'init': {'host_pid': 41001}}}},
                        'status': {'host_pid': 42001}}
        f.app = types.SimpleNamespace(discover=lambda: (41001, ENV, {'host_pid': 42001}))
        f.command = lambda argv, timeout, **kw: self.calls.append((argv, timeout, kw)) or b'old'
        self.assertEqual(f.android(['/system/bin/cmd', 'activity', 'stack', 'list']), b'old')
        self.assertEqual(self.calls[0][0][:3], ['/usr/bin/nsenter', '-t', '41001'])

    def test_04_actual_new_android_calls_held_transport(self):
        self.attach_fixture_transport(HOME.encode())
        self.assertEqual(self.flow.android(['/system/bin/cmd', 'activity', 'stack', 'list']), HOME.encode())
        argv, options = self.calls[0]
        self.assertNotIn('-t', argv)
        self.assertEqual(options['pass_fds'], tuple(self.target.fds))
        self.assertTrue(options['close_fds'])
        self.assertIn('/system/bin/env', argv)
        self.assertEqual(argv[argv.index('/system/bin/env') + 1], '-i')

    def test_05_real_wait_contract_rejects_r3_short_deadline_negative(self):
        runner = lambda argv, **options: subprocess.CompletedProcess(argv, 0, HOME.encode(), b'')
        old = self.transport(runner, module=R3)
        with self.assertRaisesRegex(R3.TransportError, 'TIMEOUT_INVALID'):
            TASKS.wait_for_removal(lambda timeout: old(['/system/bin/cmd'], timeout).decode(),
                                  42, PKG, {41, 42}, lambda row: None, sleep=lambda seconds: None)

    def test_06_real_wait_contract_accepts_short_deadline_once(self):
        self.attach_fixture_transport(HOME.encode())
        result = TASKS.wait_for_removal(lambda timeout: self.flow.android(['/system/bin/cmd'], timeout).decode(),
            42, PKG, {41, 42}, lambda row: self.events.append(('readback', row)), sleep=lambda seconds: None)
        self.assertEqual(result['task_ids_after'], [41])
        self.assertEqual(len(self.calls), 1)
        argv, options = self.calls[0]
        self.assertGreater(options['timeout'], 0)
        self.assertLessEqual(options['timeout'], 3)
        self.assertEqual(argv[argv.index('/system/bin/timeout') + 3], '1')

    def test_07_timeout_bounds_keep_nonfinite_zero_and_above70_rejected(self):
        for value in (0, -1, float('nan'), float('inf'), 70.0001, True):
            with self.subTest(timeout=repr(value)), self.assertRaises(M.TransportError):
                self.transport(lambda *a, **kw: self.fail('must not run'))(['/system/bin/cmd'], value)

    def test_08_optional_empty_environment_preserved_required_empty_rejected(self):
        values = M.environment_values({**ENV, 'STANDALONE_SYSTEMSERVER_JARS': ''})
        self.assertEqual(values['STANDALONE_SYSTEMSERVER_JARS'], '')
        with self.assertRaises(M.TransportError):
            M.environment_values({**ENV, 'BOOTCLASSPATH': ''})
        with self.assertRaises(M.TransportError):
            M.environment_values({**ENV, 'LD_PRELOAD': '/untrusted.so'})

    def test_09_actual_cleanup_preserves_preexisting_task_without_command(self):
        self.selected(False)
        self.fixture_android([])
        self.assertEqual(self.flow.cleanup(), {'preexisting_task_preserved': True, 'removal_attempted': False})
        self.assertFalse(self.calls)

    def test_10_actual_cleanup_already_absent_sends_no_remove(self):
        self.selected()
        self.fixture_android([HOME])
        self.assertTrue(self.flow.cleanup()['new_task_already_absent'])
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.calls[0][2])

    def test_11_actual_cleanup_wrong_leaf_refuses_mutation(self):
        self.selected()
        self.fixture_android([HOME + stacks((42, 'another.package'))])
        with self.assertRaisesRegex(RuntimeError, 'SCOPE_CHANGED'):
            self.flow.cleanup()
        self.assertFalse(any(row[2] for row in self.calls))
        self.assertFalse((self.root / 'cleanup-attempted.json').exists())

    def test_12_actual_cleanup_removes_once_and_preserves_other_tasks(self):
        self.selected()
        self.fixture_android([BILI, HOME])
        result = self.flow.cleanup()
        self.assertTrue(result['new_leaf_removed_and_verified'])
        self.assertTrue(result['other_tasks_preserved'])
        self.assertEqual([a for a, _, mutation in self.calls if mutation],
                         [['/system/bin/cmd', 'activity', 'stack', 'remove', '42']])
        self.assertLessEqual(self.calls[-1][1], 3)
        self.assertTrue((self.step / 'cleanup-observation-01.json').exists())

    def test_13_actual_cleanup_claim_prevents_second_remove(self):
        self.selected()
        R.write_new(self.root / 'cleanup-attempted.json', {'retained': 'unknown'})
        self.fixture_android([])
        with self.assertRaisesRegex(RuntimeError, 'NO_REPLAY'):
            self.flow.cleanup()
        self.assertFalse(self.calls)

    def test_14_actual_cleanup_other_task_loss_cannot_pass(self):
        self.selected()
        self.fixture_android([BILI, stacks((43, 'different.home'))])
        with self.assertRaisesRegex(RuntimeError, 'OTHER_TASK_SET_CHANGED'):
            self.flow.cleanup()
        self.assertEqual(sum(row[2] for row in self.calls), 1)

    def test_15_actual_cleanup_timeout_preserves_claim_and_never_retries(self):
        self.selected()
        self.fixture_android([BILI], subprocess.TimeoutExpired('<owned remove>', 20))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.flow.cleanup()
        self.assertEqual(sum(row[2] for row in self.calls), 1)
        self.assertTrue((self.root / 'cleanup-attempted.json').exists())
        with self.assertRaisesRegex(RuntimeError, 'NO_REPLAY'):
            self.flow.cleanup()
        self.assertEqual(sum(row[2] for row in self.calls), 1)

    def test_16_native_launch_preexisting_bili_refused_before_claim(self):
        self.fixture_android([BILI])
        self.flow.command = lambda *a, **kw: self.fail('native launch must not run')
        with self.assertRaisesRegex(RuntimeError, 'PREEXISTING_BILIBILI'):
            self.flow.launch()
        self.assertFalse((self.root / 'launch-attempted.json').exists())

    def test_17_native_launch_uses_original_command_and_owns_new_leaf(self):
        self.fixture_android([HOME, BILI])
        def launch(argv, timeout, **options):
            self.calls.append(('native', argv, options))
            return json.dumps({'ok': True, 'state': 'running', 'host_pid': 42001,
                'launch': 'object=10 composer_display=0 android_display=0 task=42'}).encode()
        self.flow.command = launch
        result = self.flow.launch()
        self.assertTrue(result['cleanup_allowed'])
        native = [row for row in self.calls if row[0] == 'native']
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0][1][-5:], ['launch', PKG, '--component', S.COMPONENT, '--json'])
        saved = json.loads((self.root / 'launch-scope.json').read_text())
        self.assertEqual(saved['prelaunch_task_ids'], [41])
        self.assertTrue(saved['prelaunch_absent'])

    def test_18_native_launch_respects_existing_real_action_lock(self):
        lock = R.lock_file(R.ACTION_LOCK)
        try:
            self.flow.stacks = lambda: self.fail('no read/action while busy')
            with self.assertRaises(BlockingIOError):
                self.flow.launch()
        finally:
            os.close(lock)

    def test_19_actual_command_owned_child_rc134_retained_before_guard_error(self):
        def guard(attempted=False):
            self.guards.append(attempted)
            if len(self.guards) > 1:
                raise RuntimeError('injected post guard')
        self.flow.guard = guard
        with self.assertRaisesRegex(RuntimeError, '^COMMAND_FAILED$') as caught:
            self.flow.command(['/usr/bin/python3', '-I', '-c', 'import os; os.write(1,b"owned"); raise SystemExit(134)'],
                              3, mutation=True)
        receipt = json.loads((self.step / 'command-001.result.json').read_text())
        self.assertEqual(receipt['returncode'], 134)
        self.assertTrue(receipt['spawned'] and receipt['owned_command_joined'])
        self.assertEqual((self.step / 'command-001.stdout').read_bytes(), b'owned')
        self.assertEqual(caught.exception.command_observation['returncode'], 134)
        self.assertEqual(caught.exception.command_observation['errors'][-1]['phase'], 'post_command_guard')

    def test_20_actual_command_timeout_owned_child_is_joined(self):
        with self.assertRaisesRegex(RuntimeError, '^COMMAND_TIMED_OUT$'):
            self.flow.command(['/usr/bin/python3', '-I', '-c', 'import time; time.sleep(10)'], .05, mutation=True)
        receipt = json.loads((self.step / 'command-001.result.json').read_text())
        self.assertTrue(receipt['timed_out'] and receipt['owned_command_joined'])
        self.assertEqual(receipt['returncode'], -9)
        self.assertEqual(self.guards, [False, True])

    def test_21_timeout_plus_lease_exit_retains_primary_and_post_guard(self):
        self.target.exit_error = True
        def runner(argv, **options):
            return self.flow.command(['/usr/bin/python3', '-I', '-c', 'import time; time.sleep(10)'],
                .05, label='Android command', mutation=True, pass_fds=options['pass_fds'], check=False)
        with self.assertRaisesRegex(M.TransportTimeout, 'HOST_COMMAND_TIMEOUT') as caught:
            self.transport(runner)(['/system/bin/cmd'], .05)
        self.assertTrue(caught.exception.details['entry_release_failed'])
        self.assertTrue(self.guards[-1])
        self.assertEqual([kind for kind, _ in self.events], ['intent', 'command-result', 'failure'])

    def test_22_rc134_plus_record_failure_retains_status_before_lease_release(self):
        actual_write = R.write_new
        def write(path, value):
            if str(path).endswith('command-001.result.json'):
                raise OSError(errno.ENOSPC, 'owned injected evidence failure')
            return actual_write(path, value)
        def runner(argv, **options):
            return self.flow.command(['/usr/bin/python3', '-I', '-c', 'raise SystemExit(134)'], 3,
                label='Android command', mutation=True, pass_fds=options['pass_fds'], check=False)
        with patch.object(R, 'write_new', write), self.assertRaisesRegex(M.TransportError, '^ANDROID_COMMAND_FAILED$') as caught:
            self.transport(runner)(['/system/bin/cmd'], 3)
        self.assertEqual(caught.exception.details['returncode'], 134)
        self.assertEqual(self.events[1][1]['returncode'], 134)
        self.assertEqual(caught.exception.details['recorder_errors'][0]['phase'], 'command_result_record')
        self.assertTrue(self.guards[-1])

    def test_23_success_plus_record_failure_cannot_pass(self):
        result = subprocess.CompletedProcess(['owned'], 0, b'', b'')
        result.recorder_errors = [{'phase': 'command_result_record', 'errno': 28}]
        with self.assertRaisesRegex(M.TransportError, 'RECORDER_COMMAND_EVIDENCE_FAILED'):
            self.transport(lambda *a, **kw: result)(['/system/bin/cmd'], 3)
        self.assertNotIn('verified-result', [kind for kind, _ in self.events])

    def test_24_source_scope_rejects_other_package_or_epoch(self):
        scope = {**self.flow.scope, 'activation_sha256': S.ACTIVATION_SHA,
            'verified_sha256': S.VERIFIED_SHA, 'adapter_manifest_sha256': 'a'*64,
            'recorder_sha256': 'b'*64}
        contract = types.SimpleNamespace(sha256='a'*64, files={'recorder.py': {'sha256': 'b'*64}})
        activation = {'framework_epoch': {'sha256': S.MAIN_EPOCH}}
        S.verify_scope(scope, activation, contract)
        for change in ({'uid': 10118}, {'package': 'another.app'}, {'epoch_sha256': 'c'*64}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                S.verify_scope({**scope, **change}, activation, contract)

    def test_25_package_uid_parser_retains_only_two_expected_packages(self):
        expected = {PKG: 10117, 'local.pocket4.actions.v2': 10125}
        raw = (PKG+' 10117 0 /data/user/0/x\nlocal.pocket4.actions.v2 10125 0 /data/user/0/y\n'
               'unrelated.private.app 10999 0 /data/user/0/z\n').encode()
        self.assertEqual(B.package_uids(raw, expected), expected)
        with self.assertRaises(RuntimeError):
            B.package_uids(raw + (PKG+' 10117\n').encode(), expected)
        with self.assertRaises(RuntimeError):
            B.package_uids(raw.replace(b'10117', b'10118'), expected)

    def test_26_child_entry_requires_active_parent_and_unfinished_command(self):
        lock = R.lock_file(self.root / 'flow.lock')
        try:
            E.active_command_phase(self.root, self.step, 'command-001')
            R.write_new(self.step / 'command-001.result.json', {'ok': False})
            with self.assertRaisesRegex(RuntimeError, 'CANNOT_BE_REPLAYED'):
                E.active_command_phase(self.root, self.step, 'command-001')
        finally:
            os.close(lock)
        with self.assertRaisesRegex(RuntimeError, 'NOT_ACTIVE'):
            E.active_command_phase(self.root, self.step, 'command-002')

    def test_27_actual_entry_parser_preserves_literal_separator_in_text(self):
        argv = ['entry.py', 'client', '--adapter-manifest-sha256', 'a'*64, '--flow-dir', str(self.root),
                '--step', 'owned-step', '--command', 'command-001', '--', '--interactive-production',
                'set-text', '--package', PKG, '--', '--literal-value']
        captured = []
        with patch.object(sys, 'argv', argv), patch.object(E, 'load_context', lambda args: captured.append(args) or 'ctx'), \
             patch.object(E, 'client', lambda context, args: 0):
            self.assertEqual(E.main(), 0)
        self.assertEqual(captured[0].original_argv[-2:], ['--', '--literal-value'])
        self.assertEqual(captured[0].adapter_manifest_sha256, 'a'*64)

    def test_28_app_and_backend_are_distinct_exact_sources_but_shared_helper_ast(self):
        trees = [ast.parse((HERE / 'references' / name).read_bytes())
                 for name in ('android_app.py', 'android_backend.py')]
        funcs = [{n.name: ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)} for tree in trees]
        self.assertNotEqual(funcs[0]['client'], funcs[1]['client'])
        for name in set(funcs[0]) - {'client'}:
            self.assertEqual(funcs[0][name], funcs[1][name], name)

    def copied_contract(self):
        root = self.root / 'source-copy'
        root.mkdir()
        files = {}
        for name in sorted(S.PRODUCTION_FILES | set(S.REFERENCE_PINS)):
            target = root / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(HERE / name, target)
            raw = target.read_bytes()
            files[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        raw = (json.dumps({'schema': 1, 'artifact': S.ARTIFACT, 'files': files}, sort_keys=True) + '\n').encode()
        (root / 'source-manifest.json').write_bytes(raw)
        module = load('actual_entry_at_copied_path', root / 'existing_ui_entry.py')
        return root, module, hashlib.sha256(raw).hexdigest()

    def test_29_actual_loader_uses_complete_manifest_at_its_real_path(self):
        root, entry, digest = self.copied_contract()
        source, contract = entry.bootstrap(digest)
        self.assertEqual(contract.root, root)
        contract.verify()
        self.assertEqual(contract.load('recorder.py', 'copied_recorder').__file__, str(root / 'recorder.py'))
        with self.assertRaisesRegex(RuntimeError, 'MANIFEST_LOCATION'):
            S.SourceContract(root / 'source-manifest.json', digest)
        with self.assertRaisesRegex(RuntimeError, 'MANIFEST_PIN'):
            entry.bootstrap('0' * 64)

    def test_30_actual_loader_rejects_changed_dependency_and_missing_closure(self):
        root, entry, digest = self.copied_contract()
        original = (root / 'main_binding.py').read_bytes()
        (root / 'main_binding.py').write_bytes(original + b'\n')
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_CHANGED'):
            entry.bootstrap(digest)
        (root / 'main_binding.py').write_bytes(original)
        manifest = json.loads((root / 'source-manifest.json').read_bytes())
        del manifest['files']['references/android_backend.py']
        raw = json.dumps(manifest).encode()
        (root / 'source-manifest.json').write_bytes(raw)
        with self.assertRaisesRegex(RuntimeError, 'CLOSURE_INCOMPLETE'):
            entry.bootstrap(hashlib.sha256(raw).hexdigest())

    def client_context(self, argv):
        def pinned_load(name, module_name):
            return load(module_name, HERE / name)
        return types.SimpleNamespace(recorder=R, source=S, operation=argv[2], mutation=False,
            view=types.SimpleNamespace(guard=lambda: self.guards.append(False)),
            contract=types.SimpleNamespace(root=HERE, sha256='a'*64, load=pinned_load),
            journal=self.step / 'command-001-bound', intent={'argv': argv}, intent_sha256='b'*64)

    def test_31_exact_client_keeps_request_parsing_and_redirects_only_backend_spawn(self):
        argv = [R.APP, '--interactive-production', 'find', '--package', PKG, '--text', 'owned selector']
        c = self.client_context(argv)
        args = types.SimpleNamespace(flow_dir=self.root, step=self.step.name, command='command-001',
                                     original_argv=argv[1:])
        def run(physical, **options):
            self.calls.append((physical, options))
            return subprocess.CompletedProcess(physical, 0, b'{"ok":true}\n', b'')
        sink = io.TextIOWrapper(io.BytesIO(), write_through=True)
        # The only subprocess seam here is the target backend process itself.
        proxy = types.SimpleNamespace(run=run, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired)
        with patch.object(E, 'subprocess', proxy), redirect_stdout(sink):
            self.assertEqual(E.client(c, args), 0)
        self.assertEqual(len(self.calls), 1)
        physical, options = self.calls[0]
        self.assertEqual(physical[:4], ['/usr/bin/python3', '-I', str(HERE/'existing_ui_entry.py'), 'backend'])
        request = json.loads(options['input'])
        self.assertEqual(request['selector'], {'text': 'owned selector', 'package': PKG})
        self.assertEqual(request['package'], PKG)
        saved = json.loads((c.journal / 'client-dispatch.json').read_bytes())
        self.assertEqual(saved['logical_argv'], ['/usr/bin/sudo', '-n', R.BACKEND])
        with self.assertRaises(FileExistsError):
            E.client(c, args)
        self.assertEqual(len(self.calls), 1)

    def test_32_original_client_foreground_authorization_is_still_real(self):
        original = load('actual_client_authorization_control', HERE/'references/android_app.py')
        class PathProxy:
            def __getattr__(self, name): return getattr(os.path, name)
            def exists(self, path): return path == '/run/user/1000/wayland-0'
        class OsProxy:
            path = PathProxy()
            def __getattr__(self, name): return getattr(os, name)
        original.os = OsProxy()
        original.subprocess = types.SimpleNamespace(run=lambda *a, **kw: self.fail('protected UI must not dispatch'))
        sink = io.StringIO()
        with patch.object(sys, 'argv', [R.APP, 'dump', '--package', PKG]), redirect_stderr(sink):
            self.assertEqual(original.client(), 3)
        self.assertEqual(json.loads(sink.getvalue())['error'], 'INTERACTIVE_PRODUCTION_PROTECTED')

    def backend_fixture(self):
        argv = [R.APP, '--interactive-production', 'find', '--package', PKG, '--text', 'owned']
        c = self.client_context(argv)
        c.journal.mkdir()
        raw = (json.dumps({'op': 'find', 'package': PKG, 'selector': {'text': 'owned', 'package': PKG}})+'\n').encode()
        R.write_new(c.journal/'client.claim.json', {'intent_sha256': c.intent_sha256,
                    'adapter_manifest_sha256': c.contract.sha256})
        R.write_new(c.journal/'client-request.json', raw)
        R.write_new(c.journal/'client-dispatch.json', {'request_sha256': S.sha(raw),
                    'parent_intent_sha256': c.intent_sha256})
        original = load('actual_backend_helper_control', HERE/'references/android_backend.py')
        class OsProxy:
            def __getattr__(self, name): return getattr(os, name)
            def open(self, path, *args, **kwargs):
                self_path = str(self_root/'backend-actions.lock')
                if path != '/run/lock/android-digitalis-actions.lock':
                    raise AssertionError('unexpected backend file open')
                return os.open(self_path, *args, **kwargs)
        self_root = self.root
        original.os = OsProxy()
        c.contract.load = lambda name, module_name: original if name == 'references/android_backend.py' else self.fail(name)
        c.view.action_attempted = False
        c.view.android = lambda *a, **kw: self.fail('no actual Android operation in helper seam')
        c.view.close = lambda: None
        return c, original, raw, types.SimpleNamespace(original_argv=[])

    def test_33_exact_backend_helper_retains_actual_action_lock(self):
        c, original, raw, args = self.backend_fixture()
        original.dispatch = lambda request: self.fail('busy original helper must not dispatch')
        lock = os.open(self.root/'backend-actions.lock', os.O_CREAT|os.O_RDWR, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        errors = io.StringIO()
        try:
            with patch.object(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(raw))), redirect_stderr(errors):
                self.assertEqual(E.backend(c, args), 1)
        finally:
            os.close(lock)
        self.assertEqual(json.loads(errors.getvalue())['error'], 'DIGITALIS_BUSY_NO_ACTION_TAKEN')
        self.assertFalse(c.view.action_attempted)

    def test_34_backend_timeout_plus_release_and_record_errors_preserve_primary(self):
        c, original, raw, args = self.backend_fixture()
        def dispatch(request):
            self.calls.append(request)
            raise subprocess.TimeoutExpired('<owned seam>', 3)
        original.dispatch = dispatch
        c.view.close = lambda: (_ for _ in ()).throw(OSError(9, 'owned release seam'))
        actual_write = R.write_new
        def write(path, value):
            if str(path).endswith('backend-result.json'):
                raise OSError(28, 'owned evidence seam')
            return actual_write(path, value)
        errors = io.StringIO()
        with patch.object(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(raw))), \
             patch.object(R, 'write_new', write), redirect_stderr(errors):
            self.assertEqual(E.backend(c, args), 2)
        value = json.loads(errors.getvalue())
        self.assertEqual(value['error'], 'TIMEOUT')
        self.assertEqual(value['held_release_error_type'], 'OSError')
        self.assertEqual(value['result_record_error_type'], 'OSError')
        self.assertEqual(len(self.calls), 1)
        with patch.object(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(raw))), self.assertRaises(FileExistsError):
            E.backend(c, args)
        self.assertEqual(len(self.calls), 1)

    def test_35_backend_success_plus_release_error_never_returns_success(self):
        c, original, raw, args = self.backend_fixture()
        original.dispatch = lambda request: {'ok': True, 'owned_fixture': True}
        c.view.close = lambda: (_ for _ in ()).throw(OSError(9, 'owned release seam'))
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(raw))), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(E.backend(c, args), 1)
        self.assertTrue(json.loads(stdout.getvalue())['ok'])
        self.assertEqual(json.loads(stderr.getvalue())['error'], 'HELD_BINDING_RELEASE_FAILED')
        self.assertEqual(json.loads((c.journal/'backend-result.json').read_text())['returncode'], 1)

    def test_36_backend_intermediate_unscoped_bytes_are_not_written(self):
        f = self.flow
        f._private_backend_transport = True
        private_bytes = b'owned full-frame intermediate bytes which must stay in memory'
        def make_binding(**kwargs):
            return types.SimpleNamespace(target=self.target, record={'scope': 'explicit target seam'},
                close=lambda: None, transport=lambda record, runner, guard: M.BoundArun(
                    target=self.target, environment=ENV, record=record, runner=runner, guard=guard,
                    epoch_sha256=S.MAIN_EPOCH, init_pid=41001, package=PKG, uid=10117,
                    interactive_production=True))
        f.source = f.epoch = f.app = object()
        f.contract = types.SimpleNamespace(load=lambda name, mod: types.SimpleNamespace(MainBinding=make_binding))
        def run(argv, **options):
            self.calls.append((argv, options))
            return subprocess.CompletedProcess(argv, 0, private_bytes, b'')
        with patch.object(R, 'subprocess', types.SimpleNamespace(run=run, PIPE=subprocess.PIPE)):
            self.assertEqual(f.android(['/system/bin/screencap', '-p'], 20), private_bytes)
        files = [path for path in self.step.iterdir() if path.is_file()]
        self.assertFalse(list(self.step.glob('command-*.stdout')))
        self.assertTrue((self.step/'transport-001.command-result.json').is_file())
        self.assertFalse(any(private_bytes in path.read_bytes() for path in files))
        observed = json.loads((self.step/'transport-001.command-result.json').read_bytes())
        self.assertEqual(observed['stdout_sha256'], hashlib.sha256(private_bytes).hexdigest())

    def test_37_original_dispatch_keeps_expected_package_in_native_request(self):
        original = load('actual_backend_dispatch_control', HERE/'references/android_backend.py')
        original.ui = lambda request: self.calls.append(request) or {'ok': True}
        result = original.dispatch({'op': 'find', 'package': PKG,
                                    'selector': {'text': 'owned', 'package': PKG}})
        self.assertTrue(result['ok'])
        self.assertEqual(self.calls[0]['expected_package'], PKG)
        self.assertEqual(self.calls[0]['selector']['package'], PKG)

    def paired_classpath_fixture(self, same_backing):
        held = load('exact_r5_paired_hash_control', HERE/'references/held_runtime_r5.py')
        first, second = self.root/'init-root', self.root/'zygote-root'
        for root in (first, second):
            (root/'apex/owned').mkdir(parents=True)
        one, two = first/'apex/owned/a.jar', second/'apex/owned/a.jar'
        one.write_bytes(b'owned classpath fixture, not an executable jar')
        if same_backing:
            os.link(one, two)
        else:
            two.write_bytes(one.read_bytes())
        root_fd = os.open(first, os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
        ns_fd = os.open('/proc/self/ns/mnt', os.O_RDONLY|os.O_CLOEXEC)
        target = types.SimpleNamespace(expected={'ns': {'pid': 'pid:[owned-fixture]'}},
            root_record=held.fd_record(root_fd), namespaces={'mnt': ns_fd}, verify=lambda: None,
            open_root=lambda path, flags: held.open_in_root(root_fd, path, flags))
        expected = {'host_pid': 41002, 'namespaces': {'pid': 'pid:[owned-fixture]'}}
        class OwnedView:
            def __init__(self, expected, deadline):
                self.proc_fd = -999  # environ below is an explicit proc-input seam.
                self.root_fd = os.open(second, os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC)
                self.root_record = held.fd_record(self.root_fd)
                self.mnt_fd = ns_fd
            def open_root(self, path, flags): return held.open_in_root(self.root_fd, path, flags)
            def verify(self): pass
            def close(self): os.close(self.root_fd)
        held.HeldZygoteRoot = OwnedView
        held.read_at = lambda directory, name, limit, deadline: (
            b'BOOTCLASSPATH=/apex/owned/a.jar\0DEX2OATBOOTCLASSPATH=/apex/owned/a.jar\0')
        try:
            return B.main_classpaths(held, target, {'binding': {'processes': {'zygote64': expected}}},
                types.SimpleNamespace(process_identity=lambda pid: expected), lambda: self.guards.append(False))
        finally:
            os.close(ns_fd); os.close(root_fd)

    def test_38_actual_paired_fd_hash_accepts_same_backing_in_different_roots(self):
        values, receipt = self.paired_classpath_fixture(True)
        self.assertEqual(values['BOOTCLASSPATH'], '/apex/owned/a.jar')
        self.assertTrue(receipt['main_classpath_read'])
        self.assertTrue(receipt['files'][0]['same_backing_verified_by_held_fds'])
        self.assertNotEqual(receipt['root']['inode'], receipt['zygote_root']['inode'])

    def test_39_actual_paired_fd_hash_rejects_equal_bytes_with_different_backing(self):
        with self.assertRaisesRegex(RuntimeError, 'different backing files'):
            self.paired_classpath_fixture(False)

    def test_40_actual_context_loader_joins_exact_physical_and_logical_command(self):
        root, entry, digest = self.copied_contract()
        source, contract = entry.bootstrap(digest)
        # Synthetic activation bytes are explicit inputs; the Main process guard
        # is the only runtime identity seam. Every actual local source is pinned.
        activation = {'framework_epoch': {'sha256': S.MAIN_EPOCH}}
        activation_raw = json.dumps(activation).encode()
        verified_raw = b'{"owned_synthetic_activation":true}\n'
        source.ACTIVATION_SHA, source.VERIFIED_SHA = S.sha(activation_raw), S.sha(verified_raw)
        scope = {**self.flow.scope, 'activation_sha256': source.ACTIVATION_SHA,
            'verified_sha256': source.VERIFIED_SHA, 'adapter_manifest_sha256': digest,
            'recorder_sha256': contract.files['recorder.py']['sha256']}
        os.chmod(self.root/'steps', 0o700)
        R.write_new(self.root/'activation.json', activation_raw)
        R.write_new(self.root/'activation-verified.json', verified_raw)
        R.write_new(self.root/'scope.json', scope)
        R.write_new(self.step/'intent.json', {'scope': scope, 'operation': 'ui',
            'request': {'op': 'dump'}, 'mutation': False})
        logical = [R.APP, '--interactive-production', 'dump', '--package', PKG]
        physical = ['/usr/bin/python3', '-I', str(root/'existing_ui_entry.py'),
            'client', '--adapter-manifest-sha256', digest, '--flow-dir', str(self.root),
            '--step', self.step.name, '--command', 'command-001', '--', *logical[1:]]
        R.write_new(self.step/'command-001.intent.json', {'argv': logical, 'execution_argv': physical,
            'mutation': False, 'label': 'Existing android-app CLI', 'authority_fds_passed': []})
        actual_load = contract.load
        def modules(name, module_name):
            value = actual_load(name, module_name)
            if name == 'recorder.py':
                value.Flow.guard = lambda view, attempted=False: self.guards.append(attempted)
            return value
        contract.load = modules
        args = types.SimpleNamespace(adapter_manifest_sha256=digest, flow_dir=self.root,
            step=self.step.name, command='command-001')
        lock = R.lock_file(self.root/'flow.lock')
        try:
            with patch.object(entry, 'bootstrap', lambda expected: (source, contract)):
                context = entry.load_context(args)
            self.assertEqual(context.operation, 'dump')
            self.assertEqual(context.view.step, self.step/'command-001-bound')
            self.assertTrue(context.view._private_backend_transport)
            self.assertEqual(context.view.app.__file__, str(root/'references/android_app.py'))
            # A changed physical entry is rejected before the process guard seam.
            intent = json.loads((self.step/'command-001.intent.json').read_bytes())
            intent['execution_argv'][2] = '/unrelated/entry.py'
            (self.step/'command-001.intent.json').write_text(json.dumps(intent))
            before = len(self.guards)
            with patch.object(entry, 'bootstrap', lambda expected: (source, contract)), \
                 self.assertRaisesRegex(RuntimeError, 'PHYSICAL_ENTRY_CHANGED'):
                entry.load_context(args)
            self.assertEqual(len(self.guards), before)
        finally:
            os.close(lock)

    def test_41_admission_has_one_readonly_exact_package_uid_command(self):
        self.flow.bind = lambda: None
        responses = [b'package:tv.danmaku.bili uid:10117\n', b'package:tv.danmaku.bili uid:10118\n']
        def android(argv, timeout=20, *, mutation=False):
            self.calls.append((argv, timeout, mutation))
            return responses.pop(0)
        self.flow.android = android
        result = self.flow.admission()
        self.assertTrue(result['one_read_only_held_package_uid_command_verified'])
        self.assertFalse(result['ui_or_audio_action_performed'])
        self.assertFalse(result['action_runner_apk_source_qualified'])
        self.assertEqual(self.calls, [(['/system/bin/cmd', 'package', 'list', 'packages', '-U',
                                      '--user', '0', PKG], 8, False)])
        with self.assertRaisesRegex(RuntimeError, 'UID_READBACK_DIFFERS'):
            self.flow.admission()

    def test_42_binding_release_does_not_unlock_flow_before_final_result(self):
        lock = R.lock_file(self.root/'flow.lock')
        self.flow.lock = lock
        closed = []
        self.flow.binding = types.SimpleNamespace(close=lambda: closed.append(True))
        probe = os.open(self.root/'flow.lock', os.O_RDONLY|os.O_CLOEXEC)
        try:
            self.flow.close()
            self.assertEqual(closed, [True])
            with self.assertRaises(BlockingIOError):
                fcntl.flock(probe, fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:
            os.close(probe); os.close(lock)


if __name__ == '__main__':
    unittest.main(verbosity=2)
