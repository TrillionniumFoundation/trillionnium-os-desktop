#!/usr/bin/python3 -I
"""Run the exact existing APP client and backend with only their entry replaced.

This is private to a newly claimed recorder command. There is no independent
UI API: its scope, logical argv, request and once-only dispatch must match that
command's durable intent. The backend's original global action lock remains.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types


def require(value, code):
    if not value:
        raise RuntimeError(code)


def bootstrap(expected):
    root = Path(__file__).resolve().parent
    path = root / 'source-manifest.json'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        require(os.fstat(fd).st_size <= 131072, 'ADAPTER_MANIFEST_TOO_LARGE')
        raw = os.read(fd, 131073)
    finally:
        os.close(fd)
    require(hashlib.sha256(raw).hexdigest() == expected, 'EXTERNAL_ADAPTER_MANIFEST_PIN_REQUIRED')
    row = json.loads(raw)['files']['source_contract.py']
    fd = os.open(root / 'source_contract.py', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        data = os.read(fd, 131073)
    finally:
        os.close(fd)
    require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'],
            'SOURCE_CONTRACT_CHANGED')
    source = types.ModuleType('bili_child_source_contract')
    source.__file__ = str(root / 'source_contract.py')
    exec(compile(data, source.__file__, 'exec'), source.__dict__)
    return source, source.SourceContract(path, expected)


def private_directory(path):
    value = path.lstat()
    require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o077,
            'RECORDER_PRIVATE_DIRECTORY_REQUIRED')


def active_command_phase(root, step, command):
    require(not os.path.lexists(step / 'result.json') and
            not os.path.lexists(step / (command + '.result.json')),
            'COMPLETED_OR_UNKNOWN_COMMAND_CANNOT_BE_REPLAYED')
    fd = os.open(root / 'flow.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.fstat(fd)
        require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_uid == 0,
                'EXISTING_FLOW_LOCK_REQUIRED')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass  # The parent retains the original flow lock across this child.
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            raise RuntimeError('RECORDER_PARENT_FLOW_NOT_ACTIVE')
    finally:
        os.close(fd)


def load_context(args):
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    source, contract = bootstrap(args.adapter_manifest_sha256)
    root = args.flow_dir
    require(root.is_absolute() and root.resolve() == root, 'CANONICAL_FLOW_PATH_REQUIRED')
    private_directory(root)
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.step) and
            re.fullmatch(r'command-[0-9]{3,6}', args.command), 'RECORDER_STEP_OR_COMMAND_INVALID')
    step = root / 'steps' / args.step
    private_directory(root / 'steps'); private_directory(step)
    active_command_phase(root, step, args.command)
    current_guard = source.load_guard()
    source.verify_saved_baseline(root)
    scope = json.loads(source.bounded_file(root / 'scope.json'))
    activation = source.activation()
    source.verify_scope(scope, activation, contract)
    step_intent = json.loads(source.bounded_file(step / 'intent.json'))
    intent_raw = source.bounded_file(step / (args.command + '.intent.json'))
    intent = json.loads(intent_raw)
    require(step_intent['scope'] == scope and step_intent['operation'] == 'ui' and
            isinstance(step_intent['request'], dict), 'ORIGINAL_UI_STEP_REQUIRED')
    operation = step_intent['request'].get('op')
    mutation = operation in ('click', 'set-text')
    require(not mutation, 'MUTATION_REQUIRES_NEW_OWNED_QA_HELPER')
    require(operation in ('dump', 'find', 'click', 'set-text', 'observe') and
            step_intent['mutation'] is mutation and intent['mutation'] is mutation and
            intent['label'] == 'Existing android-app CLI' and
            intent['argv'][:5] == ['/usr/local/bin/android-app', '--interactive-production',
                                  operation, '--package', source.PACKAGE],
            'EXISTING_UI_COMMAND_SCOPE_CHANGED')
    expected_execution = ['/usr/bin/python3', '-I', str(contract.root / 'existing_ui_entry.py'),
        'client', '--adapter-manifest-sha256', contract.sha256, '--flow-dir', str(root),
        '--step', args.step, '--command', args.command, '--', *intent['argv'][1:]]
    require(intent.get('execution_argv') == expected_execution and not intent['authority_fds_passed'],
            'EXISTING_UI_PHYSICAL_ENTRY_CHANGED')
    recorder = contract.load('recorder.py', 'bili_backend_guard_view')
    view = recorder.Flow.__new__(recorder.Flow)
    view.source, view.contract = source, contract
    view.current_guard = current_guard
    view.root, view.scope, view.activation = root, scope, activation
    view.epoch = contract.load('references/framework_epoch.py', 'bili_child_epoch')
    view.app = contract.load('references/android_app.py', 'bili_child_discovery')
    view.binding = view.transport = view.lock = None
    view._android_mutation = False
    view._private_backend_transport = True
    view.action_attempted = False
    view.command_index = 0
    view.step = step / (args.command + '-bound')
    view.guard()
    return types.SimpleNamespace(source=source, contract=contract, recorder=recorder, view=view,
        scope=scope, operation=operation, mutation=mutation, intent=intent,
        intent_sha256=source.sha(intent_raw), journal=view.step)


class ClientBackendRedirect:
    """Intercept exactly the pinned client's single sudo/backend spawn."""
    def __init__(self, context, args):
        self.context, self.args = context, args
        self.called = False

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, argv, **options):
        c, args = self.context, self.args
        require(not self.called and argv == ['/usr/bin/sudo', '-n',
            '/usr/local/libexec/android-digitalis-observe-helper'], 'UNEXPECTED_OR_REPEATED_BACKEND_SPAWN')
        require(set(options) == {'input', 'stdout', 'stderr', 'timeout'} and
            options['stdout'] == subprocess.PIPE and options['stderr'] == subprocess.PIPE and
            options['timeout'] == 180, 'EXISTING_CLIENT_SUBPROCESS_CONTRACT_CHANGED')
        raw = options['input']
        require(isinstance(raw, bytes) and len(raw) <= 65536 and raw.endswith(b'\n'),
                'CLIENT_REQUEST_BOUND_INVALID')
        request = json.loads(raw)
        require(request.get('op') == c.operation and request.get('package') == c.source.PACKAGE,
                'CLIENT_REQUEST_SCOPE_CHANGED')
        self.called = True
        c.recorder.write_new(c.journal / 'client-request.json', raw)
        physical = ['/usr/bin/python3', '-I', str(c.contract.root / 'existing_ui_entry.py'),
            'backend', '--adapter-manifest-sha256', c.contract.sha256,
            '--flow-dir', str(args.flow_dir), '--step', args.step, '--command', args.command]
        c.recorder.write_new(c.journal / 'client-dispatch.json', {'logical_argv': argv,
            'execution_argv': physical, 'request_sha256': c.source.sha(raw),
            'parent_intent_sha256': c.intent_sha256, 'automatic_retry': False})
        c.view.guard()
        return subprocess.run(physical, **options)


def client(context, args):
    c = context
    forwarded = args.original_argv
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    require(forwarded == c.intent['argv'][1:], 'CLIENT_ARGV_DIFFERS_FROM_DURABLE_INTENT')
    c.journal.mkdir(mode=0o700)  # An existing dispatch, including failure, is never adopted.
    c.recorder.write_new(c.journal / 'client.claim.json', {'intent_sha256': c.intent_sha256,
        'adapter_manifest_sha256': c.contract.sha256, 'automatic_retry': False})
    app = c.contract.load('references/android_app.py', 'bili_exact_original_client')
    app.subprocess = ClientBackendRedirect(c, args)
    original_argv = sys.argv
    try:
        sys.argv = c.intent['argv']
        return app.client()  # Retains the original --interactive-production gate and parsing.
    finally:
        sys.argv = original_argv


def backend(context, args):
    c = context
    require(not args.original_argv, 'BACKEND_HAS_NO_DIRECT_UI_ARGV')
    private_directory(c.journal)
    claim = json.loads(c.source.bounded_file(c.journal / 'client.claim.json'))
    require(claim['intent_sha256'] == c.intent_sha256 and
            claim['adapter_manifest_sha256'] == c.contract.sha256, 'CLIENT_CLAIM_CHANGED')
    raw = sys.stdin.buffer.readline(65537)
    require(raw == c.source.bounded_file(c.journal / 'client-request.json', 65536),
            'BACKEND_INPUT_DIFFERS_FROM_ACTUAL_CLIENT')
    dispatch = json.loads(c.source.bounded_file(c.journal / 'client-dispatch.json'))
    require(dispatch['request_sha256'] == c.source.sha(raw) and
            dispatch['parent_intent_sha256'] == c.intent_sha256, 'CLIENT_DISPATCH_CHANGED')
    request = json.loads(raw)
    require(request.get('op') == c.operation and request.get('package') == c.source.PACKAGE,
            'BACKEND_REQUEST_SCOPE_CHANGED')
    c.recorder.write_new(c.journal / 'backend.claim.json', {'request_sha256': c.source.sha(raw),
        'parent_intent_sha256': c.intent_sha256, 'automatic_retry': False})
    original = c.contract.load('references/android_backend.py', 'bili_exact_original_backend')
    original.arun = lambda argv, timeout=30: c.view.android(argv, timeout, mutation=c.mutation)
    # Only this private module receives the already authenticated request stream.
    original.sys = types.SimpleNamespace(stdin=types.SimpleNamespace(buffer=io.BytesIO(raw)),
                                        stdout=sys.stdout, stderr=sys.stderr)
    error = None
    code = 0
    try:
        original.helper()  # Original dispatch and original action flock, unchanged.
    except subprocess.TimeoutExpired:
        code = 2
        error = {'ok': False, 'error': 'TIMEOUT', 'outcome_unknown': True, 'automatic_retry': False}
    except original.ControlError as exc:
        code = 1
        error = {'ok': False, 'error': str(exc), 'automatic_retry': False, **exc.details}
    except BaseException as exc:
        code = 1
        error = {'ok': False, 'error': 'CONTROL_FAILED', 'automatic_retry': False,
                 'exception_type': type(exc).__name__}
    finally:
        try:
            c.view.close()
        except BaseException as exc:
            code = code or 1
            if error is None:
                error = {'ok': False, 'error': 'HELD_BINDING_RELEASE_FAILED', 'automatic_retry': False}
            error['held_release_error_type'] = type(exc).__name__
    try:
        c.recorder.write_new(c.journal / 'backend-result.json', {'returncode': code,
            'error': error, 'action_attempted': c.view.action_attempted,
            'whole_app_production_ready': False, 'automatic_retry': False})
    except BaseException as exc:
        code = code or 1
        if error is None:
            error = {'ok': False, 'error': 'BACKEND_RESULT_RECORD_FAILED', 'automatic_retry': False}
        error['result_record_error_type'] = type(exc).__name__
    if error is not None:
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('client', 'backend'))
    parser.add_argument('--adapter-manifest-sha256', required=True)
    parser.add_argument('--flow-dir', required=True, type=Path)
    parser.add_argument('--step', required=True)
    parser.add_argument('--command', required=True)
    tokens = sys.argv[1:]
    split = tokens.index('--') if '--' in tokens else len(tokens)
    args = parser.parse_args(tokens[:split])
    args.original_argv = tokens[split + 1:] if split < len(tokens) else []
    os.umask(0o077)
    context = load_context(args)
    return client(context, args) if args.mode == 'client' else backend(context, args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.TimeoutExpired:
        print(json.dumps({'ok': False, 'error': 'TIMEOUT', 'outcome_unknown': True,
                          'automatic_retry': False}), file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': 'HELD_UI_ENTRY_FAILED',
            'exception_type': type(exc).__name__, 'automatic_retry': False}), file=sys.stderr)
        raise SystemExit(1)
