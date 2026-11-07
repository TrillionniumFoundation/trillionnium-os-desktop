from pathlib import Path
import ast
import contextlib
import copy
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import traceback
from unittest import mock

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'controller-recovery04-work-01'
RESULT = ROOT / 'recovery04-local-validation-01'
RESULT.mkdir(mode=0o700)
checks = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(name, function):
    try:
        function()
        checks.append({'name': name, 'passed': True})
    except Exception as error:
        checks.append({'name': name, 'passed': False, 'error': str(error),
                       'traceback': traceback.format_exc()})


def need(value, message='control failed'):
    if not value:
        raise AssertionError(message)


def denied(function):
    try:
        function()
    except (RuntimeError, OSError, KeyError, ValueError):
        return
    raise AssertionError('negative control was accepted')


texts = {name: (SOURCE / name).read_text() for name in ('compile.py', 'run.py', 'resource_guard.py')}
cfg = json.loads((SOURCE / 'payload.json').read_text())
request = json.loads((SOURCE / 'compile-request.json').read_text())
template = json.loads((SOURCE / 'ordinary-run-request-template.json').read_text())
prior = json.loads((SOURCE / 'original-producer05-build-result.json').read_bytes())
namespaces = {}


def definition_only_plan():
    # Pre-import modules, then deny every effect boundary used by these
    # controllers. Only definitions and the two pure config/plan functions run.
    with contextlib.ExitStack() as stack:
        for owner, name in [(os, 'open'), (os, 'killpg'), (Path, 'mkdir'),
                            (subprocess, 'Popen'), (shutil, 'copytree')]:
            stack.enter_context(mock.patch.object(owner, name,
                side_effect=AssertionError('unexpected PLAN effect: ' + name)))
        for name in ('compile.py', 'run.py'):
            namespace = {'__name__': 'recovery04_definition_only_plan'}
            exec(compile(texts[name], name, 'exec'), namespace)
            namespace['validate_config'](cfg)
            expected = namespace['candidate_input_pins'](cfg)
            need(len(expected) == 31)
            namespaces[name] = namespace
        with mock.patch.object(namespaces['run.py']['sys'], 'argv', ['run.py']):
            denied(namespaces['run.py']['run_from_args'])


def binding():
    for name, source in texts.items():
        ast.parse(source, filename=name)
    raw = request['stdin']
    tree = ast.parse(raw)
    prefix = ast.parse(texts['compile.py'])
    need([ast.dump(node) for node in tree.body[:-1]] ==
         [ast.dump(node) for node in prefix.body])
    call = tree.body[-1].value
    need(isinstance(call, ast.Call) and call.func.id == 'compile_recovery')
    embedded = call.args[0]
    need(isinstance(embedded, ast.Call) and embedded.func.attr == 'loads')
    need(embedded.args[0].value == (SOURCE / 'payload.json').read_text())
    need(json.loads(embedded.args[0].value) == cfg)
    need(template['execution_ready'] is False)
    need(template['request_template']['stdin'] == texts['run.py'])
    need(request['args'] == ['-I', '-B', '-'] and request['memory_max_bytes'] == 1073741824)
    need(request['cpu_quota_percent'] == 100 and request['nice'] == 10 and request['timeout_seconds'] == 600)
    need(template['request_template']['memory_max_bytes'] == 536870912)
    need(template['request_template']['cpu_quota_percent'] == 100 and
         template['request_template']['timeout_seconds'] == 180)
    need(request['idempotency_key'].endswith(sha(raw.encode())[:16]))
    need(cfg['preimage'] == prior['inputs_before'] == prior['inputs_after'])
    need(sha((SOURCE / 'original-producer05-build-result.json').read_bytes()) ==
         '1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c')
    for name, row in cfg['overlays'].items():
        body = row['text'].encode()
        need(len(body) == row['bytes'] and sha(body) == row['sha256'])
        old = ROOT.parent / 'root-recovery-20261104-02/supervisor/source' / name
        need(body == old.read_bytes())
    guard_ast = ast.parse(texts['resource_guard.py'])
    guard_definitions = {node.name: ast.dump(node) for node in guard_ast.body
                         if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    for name in ('compile.py', 'run.py'):
        actual = {node.name: ast.dump(node) for node in ast.parse(texts[name]).body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        need(all(actual[key] == value for key, value in guard_definitions.items()))


check('AST, exact request/payload/three Rust overlays/31 pin records and identical inlined resource logic', binding)
check('definition-only PLAN and missing ordinary SHA reject before any effect', definition_only_plan)
ns = namespaces['compile.py']
qualify = ns['_resource_qualify']


def snapshots(memory=1073741824):
    before = {'pid': 123, 'cgroup_identity': [30, 444], 'mount_identity': [30, 1],
        'membership': '0::/owned/fixture\n', 'namespaces': {'mnt': [5, 1], 'cgroup': [5, 2]},
        'limits': {'memory.max': memory, 'memory.high': 'max', 'memory.swap.max': 'max',
                   'cpu.max': [100000, 100000], 'pids.max': 'max'},
        'memory_current': 1000, 'memory_peak': 2000,
        'memory_events': {'low': 0, 'high': 0, 'max': 0, 'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
        'started_monotonic_ns': 10, 'completed_monotonic_ns': 20}
    after = copy.deepcopy(before)
    after.update(started_monotonic_ns=30, completed_monotonic_ns=40)
    return before, after


for memory in (1073741824, 536870912):
    check('synthetic expected budget accepted ' + str(memory),
          lambda memory=memory: need(all(v == 0 for v in qualify(*snapshots(memory), memory).values())))

for key in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
    for when in ('before', 'after'):
        def counter_negative(key=key, when=when):
            before, after = snapshots()
            if when == 'before': before['memory_events'][key] = 1
            after['memory_events'][key] = 1
            denied(lambda: qualify(before, after, 1073741824))
        check('nonzero ' + when + ' ' + key + ' denied', counter_negative)

def mutate_case(change):
    before, after = snapshots()
    change(before, after)
    denied(lambda: qualify(before, after, 1073741824))

for name, change in [
    ('memory.max mismatch', lambda b, a: a['limits'].__setitem__('memory.max', 999)),
    ('CPU over one', lambda b, a: a['limits'].__setitem__('cpu.max', [200000, 100000])),
    ('unlimited CPU', lambda b, a: a['limits'].__setitem__('cpu.max', ['max', 100000])),
    ('peak over cap', lambda b, a: a.__setitem__('memory_peak', 1073741825)),
    ('current over cap', lambda b, a: a.__setitem__('memory_current', 1073741825)),
    ('peak reset', lambda b, a: a.__setitem__('memory_peak', 1)),
    ('counter removed', lambda b, a: a['memory_events'].pop('oom')),
    ('counter decreased', lambda b, a: b['memory_events'].__setitem__('high', 1)),
    ('domain identity replaced', lambda b, a: a.__setitem__('cgroup_identity', [30, 445])),
    ('mount identity replaced', lambda b, a: a.__setitem__('mount_identity', [31, 1])),
    ('membership moved', lambda b, a: a.__setitem__('membership', '0::/other\n')),
    ('namespace changed', lambda b, a: a['namespaces'].__setitem__('mnt', [5, 9])),
    ('PID changed', lambda b, a: a.__setitem__('pid', 124)),
    ('limit changed', lambda b, a: a['limits'].__setitem__('memory.high', 5000)),
    ('clock/order invalid', lambda b, a: a.__setitem__('started_monotonic_ns', 1)),
]:
    check(name + ' denied', lambda change=change: mutate_case(change))


def first_failure(fail_finish, fail_close, prior_error):
    class Resource:
        def __init__(self): self.record = {'held_own_cgroup_gate_passed': True}; self.closed = False
        def finish(self):
            if fail_finish: raise OSError('sampling failed')
        def close(self):
            self.closed = True
            if fail_close: raise OSError('close failed')
    resource = Resource()
    report = {'success': prior_error is None}
    if prior_error: report.update(error=prior_error, traceback='original traceback')
    ns['finish_own_resource_gate'](report, resource)
    need(resource.closed)
    if fail_finish or fail_close:
        need(report['success'] is False and resource.record['held_own_cgroup_gate_passed'] is False)
    if prior_error:
        need(report['error'] == prior_error and report['traceback'] == 'original traceback')
        need(report['success'] is False)


for finish, close, error in [(True, False, 'original Cargo failure'),
                             (False, True, 'original test failure'),
                             (True, True, 'original admission failure'),
                             (True, False, None), (False, False, 'old failure')]:
    check('resource first-failure preservation ' + str((finish, close, error)),
          lambda finish=finish, close=close, error=error: first_failure(finish, close, error))


def real_owned_fd_controls():
    before = len(os.listdir('/proc/self/fd'))
    with tempfile.TemporaryDirectory(prefix='deadline-resource-local-') as directory:
        root = Path(directory)
        (root / 'one/two').mkdir(parents=True)
        (root / 'bad').symlink_to(root / 'one', target_is_directory=True)
        (root / 'event').write_text('oom 0\nmax 0\n')
        (root / 'event-link').symlink_to(root / 'event')
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            held = ns['_resource_open_descendant'](root_fd, 'one/two')
            try:
                need(ns['_resource_identity'](held) == [os.stat(root / 'one/two').st_dev,
                                                       os.stat(root / 'one/two').st_ino])
                need(ns['_resource_fstype'](held) != ns['_RESOURCE_CGROUP2_MAGIC'])
            finally: os.close(held)
            denied(lambda: ns['_resource_open_descendant'](root_fd, 'bad/two'))
            denied(lambda: ns['_resource_open_descendant'](root_fd, 'one/../two'))
            need(ns['_resource_read_at'](root_fd, 'event') == 'oom 0\nmax 0')
            denied(lambda: ns['_resource_read_at'](root_fd, 'event-link'))
            denied(lambda: ns['_resource_read_at'](root_fd, 'event', 3))
        finally: os.close(root_fd)
    need(len(os.listdir('/proc/self/fd')) == before, 'owned FD helper leaked descriptors')


check('real owned tempdir nofollow/descendant/bounded read and descriptor cleanup controls', real_owned_fd_controls)
for text in ('0::/\n', '0::/one/../two\n', '0:://one\n', '1:x:/one\n'):
    check('invalid membership rejected ' + repr(text),
          lambda text=text: denied(lambda: ns['_resource_membership'](text)))


# Exercise the exact compiled-artifact selection AST against retained, genuine
# recovery03 Cargo metadata. file_pin is explicitly stubbed: these are parser
# controls, never proof that a new recovery04 ELF exists or has been executed.
ACTUAL = ROOT.parent / 'root-recovery-20261104-02/evidence'
actual_raw = (ACTUAL / 'producer06-recovery03-compile-result.json').read_bytes()
cargo_raw = (ACTUAL / 'producer06-recovery03-command01.stdout').read_bytes()
need(sha(actual_raw) == '6e8745ca1f6cd860c7b1275c176e11c1274c7857365a8969ccc60a3c976a0e71')
need(sha(cargo_raw) == 'ce3ef945f2326380d65c4e4eea0690ee0e5d8f3b69c8984a0c125c8daa3bbdaf')
actual = json.loads(actual_raw)
need(actual['success'] is False and len(actual['commands']) == 2)
need(all(row['returncode'] == 0 for row in actual['commands']))
messages = [json.loads(line) for line in cargo_raw.splitlines() if line.strip()]
lib_messages = [row for row in messages if row.get('reason') == 'compiler-artifact' and
                row.get('profile', {}).get('test') is True and row.get('executable') and
                row.get('target', {}).get('kind') == ['lib'] and
                row.get('target', {}).get('name') in ('droidloom_pressure_relay', 'droidloom_supervisor')]
compile_ast = ast.parse(texts['compile.py'])
function = next(node for node in compile_ast.body if isinstance(node, ast.FunctionDef) and node.name == 'compile_recovery')
try_block = next(node for node in function.body if isinstance(node, ast.Try))
start = next(i for i, node in enumerate(try_block.body) if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == 'tests' for target in node.targets))
finish = next(i for i, node in enumerate(try_block.body) if isinstance(node, ast.Assign) and
              any(isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and
                  target.slice.value == 'compiled_test_artifacts' for target in node.targets))
selector = compile(ast.fix_missing_locations(ast.Module(body=try_block.body[start:finish+1], type_ignores=[])),
                   'actual-recovery04-selector', 'exec')


def select(rows):
    context = dict(ns)
    context.update(TARGET=Path(actual['target']), CANDIDATE=Path(actual['candidate']),
                   test_messages=rows, report={}, file_pin=lambda path, **kwargs: {'path': str(path), 'test_stub': True})
    exec(selector, context)
    return context['report']['compiled_test_artifacts']


def library_scope_binding():
    import re
    need(ns['EXPECTED_TEST_TARGETS'] == {('droidloom_pressure_relay', 'lib'), ('droidloom_supervisor', 'lib')})
    need('"--lib", "--no-run", "--message-format=json"' in texts['compile.py'])
    old_counts = [int(re.search(r'test result: ok\. (\d+) passed;', row['stdout']).group(1)) for row in prior['commands'][:2]]
    need(old_counts == [21, 112])
    need('test_summary(out, 1, 22)' in texts['run.py'])
    need('expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 112' in texts['run.py'])
    need(len(lib_messages) == 2)
    need(sha((SOURCE / 'resource_guard.py').read_bytes()) == '4192389de077c41dc395d9f5b083d10372272c45aacb053697d3c24e94a25961')


check('exact lib selection and 21+2 /112 library counts from pinned old receipt', library_scope_binding)
check('retained real Cargo two-lib metadata accepted by actual selector AST', lambda: need(len(select(lib_messages)) == 2))
check('retained original full Cargo target set still rejected', lambda: denied(lambda: select(messages)))
check('missing selected library rejected', lambda: denied(lambda: select(lib_messages[:1])))
check('duplicate selected library rejected', lambda: denied(lambda: select(lib_messages + lib_messages[:1])))

report = {'schema': 1, 'revision': 'producer06-deadline-recovery04',
          'passed': all(row['passed'] for row in checks), 'checks': checks,
          'count': len(checks), 'source_pins': [
              {'path': name, 'bytes': len(text.encode()), 'sha256': sha(text.encode())}
              for name, text in texts.items()],
          'request_sha256': sha((SOURCE / 'compile-request.json').read_bytes()),
          'resource_policy_snapshots_are_synthetic': True,
          'actual_cgroup_or_remote_device_sampling_performed': False,
          'actual_owned_tempdir_descriptor_controls_performed': True,
          'rust_or_android_execution_performed': False,
          'full_owner_runtime_qualified': False}
with (RESULT / 'report.json').open('x') as stream:
    json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n')
print(json.dumps({'passed': report['passed'], 'checks': len(checks),
                  'failed': [row for row in checks if not row['passed']],
                  'report': str(RESULT / 'report.json'),
                  'sha256': sha((RESULT / 'report.json').read_bytes())}, indent=2))
raise SystemExit(0 if report['passed'] else 1)
