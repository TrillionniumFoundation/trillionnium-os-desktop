from pathlib import Path
import ast
import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import traceback
from unittest import mock

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'controller-recovery04-freeze-01'
CONTROL = ROOT / 'producer07-controller-work-02'
SOURCE = ROOT / 'producer07-audit-freeze-02'
OUT = ROOT / 'producer07-controller-local-validation-03'
OUT.mkdir(mode=0o700)
checks = []
texts = {name: (CONTROL / name).read_text() for name in ('compile.py', 'run.py', 'resource_guard.py')}
cfg = json.loads((CONTROL / 'payload.json').read_text())
request = json.loads((CONTROL / 'compile-request.json').read_text())
template = json.loads((CONTROL / 'ordinary-run-request-template.json').read_text())
inputs = json.loads((SOURCE / 'input-manifest.json').read_text())
NEW = 'runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs'
spaces = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(value, reason='control failed'):
    if not value:
        raise AssertionError(reason)


def check(name, function):
    try:
        function()
        checks.append({'name': name, 'passed': True})
    except Exception as error:
        checks.append({'name': name, 'passed': False, 'error': str(error), 'traceback': traceback.format_exc()})


def denied(function):
    try:
        function()
    except (OSError, RuntimeError, ValueError, KeyError):
        return
    raise AssertionError('negative control accepted')


def plan():
    with contextlib.ExitStack() as stack:
        for owner, name in [(os, 'open'), (os, 'killpg'), (Path, 'mkdir'),
                            (subprocess, 'Popen'), (shutil, 'copytree')]:
            stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError('PLAN effect: ' + name)))
        for name in ('compile.py', 'run.py'):
            ns = {'__name__': 'producer07_definition_only_plan'}
            exec(compile(texts[name], name, 'exec'), ns)
            ns['validate_config'](cfg)
            actual = ns['candidate_input_pins'](cfg)
            expected = {r['path']: {'bytes': r['bytes'], 'sha256': r['sha256']} for r in inputs['candidate_inputs']}
            need(actual == expected and len(actual) == 32)
            need(len(ns['json_bytes'](cfg)) < 512 * 1024)
            spaces[name] = ns
        with mock.patch.object(spaces['run.py']['sys'], 'argv', ['run.py']):
            denied(spaces['run.py']['run_from_args'])


def bindings():
    for name, source in texts.items():
        ast.parse(source, filename=name)
    tree = ast.parse(request['stdin'])
    need([ast.dump(n) for n in tree.body[:-1]] == [ast.dump(n) for n in ast.parse(texts['compile.py']).body])
    call = tree.body[-1].value
    need(isinstance(call, ast.Call) and call.func.id == 'compile_recovery')
    embedded = call.args[0]
    need(embedded.func.attr == 'loads')
    need(embedded.args[0].value == (CONTROL / 'payload.json').read_text())
    need(json.loads(embedded.args[0].value) == cfg)
    need(template['execution_ready'] is False)
    need(template['request_template']['stdin'] == texts['run.py'])
    need(request['idempotency_key'] == 'p4-producer07-audit02-compile01-' + sha(request['stdin'].encode())[:16])
    for key in ('host', 'executable', 'args', 'cwd', 'cpu_quota_percent', 'memory_max_bytes', 'nice', 'timeout_seconds'):
        need(request[key] == json.loads((OLD / 'compile-request.json').read_text())[key], key)
        need(template['request_template'][key] == json.loads((OLD / 'ordinary-run-request-template.json').read_text())['request_template'][key], key)
    need(cfg['preimage'] == {r['path']: {'bytes': r['bytes'], 'sha256': r['sha256']} for r in inputs['basis_inputs']})
    need(set(cfg['overlays']) == set(inputs['changed_inputs']))
    for name, row in cfg['overlays'].items():
        raw = (SOURCE / 'source' / name).read_bytes()
        need(row['text'].encode() == raw and row['bytes'] == len(raw) and row['sha256'] == sha(raw))


def unchanged_code():
    guard = (OLD / 'resource_guard.py').read_text()
    need(guard == texts['resource_guard.py'])
    defs = lambda text: {n.name: ast.dump(n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    guarded = defs(guard)
    for name in ('compile.py', 'run.py'):
        old, new = defs((OLD / name).read_text()), defs(texts[name])
        need(all(new[key] == value for key, value in guarded.items()))
        for key in ('read_regular', 'file_pin', 'all_source', 'command_env', 'run_command', 'put'):
            need(old[key] == new[key], key)
        if name == 'run.py':
            for key in ('fd_digest', 'test_summary', 'run_from_args'):
                need(old[key] == new[key], key)
    command_lists = []
    for node in ast.walk(ast.parse(texts['compile.py'])):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'run_command':
            command_lists.append([x.value if isinstance(x, ast.Constant) else x.id for x in node.args[2].elts])
    need(len(command_lists) == 2 and '--lib' in command_lists[1] and '--no-run' in command_lists[1])
    need('--bins' in command_lists[0] and '--lib' not in command_lists[0])
    need(spaces['compile.py']['EXPECTED_TEST_TARGETS'] == {('droidloom_pressure_relay', 'lib'), ('droidloom_supervisor', 'lib')})


check('exact AST/request/payload/source and resource budget bindings', bindings)
check('effect-denied definition-only PLAN and absent actual SHA rejection', plan)
check('unchanged resource, command, held ELF, inventory and explicit lib-selection gates', unchanged_code)
ns = spaces['compile.py']
for label, mutate in [
    ('new module omitted', lambda c: c['overlays'].pop(NEW)),
    ('new module claimed as preimage', lambda c: c['preimage'].__setitem__(NEW, {'bytes': 0, 'sha256': '0' * 64})),
    ('altered new source bytes', lambda c: c['overlays'][NEW].__setitem__('text', c['overlays'][NEW]['text'] + ' ')),
    ('wrong frozen source manifest', lambda c: c.__setitem__('source_manifest_sha256', '0' * 64)),
]:
    def negative(mutate=mutate):
        other = copy.deepcopy(cfg)
        mutate(other)
        denied(lambda: ns['validate_config'](other))
    check(label + ' denied', negative)

compile_fn = next(n for n in ast.parse(texts['compile.py']).body if isinstance(n, ast.FunctionDef) and n.name == 'compile_recovery')
overlay_loop = next(n for n in ast.walk(compile_fn) if isinstance(n, ast.For) and
                    isinstance(n.iter, ast.Call) and isinstance(n.iter.func, ast.Attribute) and
                    isinstance(n.iter.func.value, ast.Subscript) and
                    isinstance(n.iter.func.value.value, ast.Name) and n.iter.func.value.value.id == 'cfg' and
                    isinstance(n.iter.func.value.slice, ast.Constant) and n.iter.func.value.slice.value == 'overlays')
overlay_code = compile(ast.Module(body=[overlay_loop], type_ignores=[]), 'actual-compile-overlay-loop', 'exec')


def actual_overlay():
    with tempfile.TemporaryDirectory(prefix='producer07-overlay-', dir=OUT) as temp:
        root = Path(temp)
        candidate = root / 'candidate'
        # The transport freeze is deliberately mode 0444. This owned test fixture
        # copies exact bytes into writable new files; it predicts no remote mode.
        shutil.copytree(SOURCE / 'baseline-deadline06' / 'source', candidate, copy_function=shutil.copyfile)
        local = dict(ns, CANDIDATE=candidate, OUT=root / 'receipt', cfg=cfg)
        exec(overlay_code, local)
        need(local['inputs'](candidate, local['candidate_input_pins'](cfg)) == local['candidate_input_pins'](cfg))
        saved = list((root / 'receipt' / 'preimage').rglob('*.rs'))
        need(len(saved) == 9)
        for path in saved:
            name = path.relative_to(root / 'receipt' / 'preimage')
            need(path.read_bytes() == (SOURCE / 'baseline-deadline06' / 'source' / name).read_bytes())


check('actual controller overlay loop reconstructs 32 inputs and saves nine exact preimages', actual_overlay)


def new_branch(case):
    with tempfile.TemporaryDirectory(prefix='producer07-new-file-', dir=OUT) as temp:
        root = Path(temp)
        target = root / NEW
        target.parent.mkdir(parents=True)
        other = root / 'unrelated-owned-file'
        other.write_bytes(b'unchanged')
        if case == 'existing': target.write_bytes(b'existing')
        if case == 'leaf_symlink': target.symlink_to(other)
        if case == 'parent_symlink':
            target.parent.rmdir()
            target.parent.symlink_to(root, target_is_directory=True)
        local = dict(ns, CANDIDATE=root, OUT=root / 'receipt',
                     cfg={'overlays': {NEW: cfg['overlays'][NEW]}, 'preimage': cfg['preimage']})
        if case == 'race':
            original = local['plain_input_path']
            def racing(*args, **kwargs):
                path = original(*args, **kwargs)
                path.write_bytes(b'raced')
                return path
            local['plain_input_path'] = racing
        denied(lambda: exec(overlay_code, local))
        need(other.read_bytes() == b'unchanged')
        if case == 'existing': need(target.read_bytes() == b'existing')
        if case == 'race': need(target.read_bytes() == b'raced')


for case in ('existing', 'leaf_symlink', 'parent_symlink', 'race'):
    check('actual new-module branch rejects ' + case, lambda case=case: new_branch(case))


def unknown_create():
    with tempfile.TemporaryDirectory(prefix='producer07-path-', dir=OUT) as temp:
        root = Path(temp)
        denied(lambda: ns['plain_input_path'](root, 'unapproved.rs', must_be_absent=True))
        denied(lambda: ns['plain_input_path'](root, '../unapproved.rs', must_be_absent=True))


check('unknown or parent-traversing create path denied', unknown_create)
report = {'schema': 1, 'revision': 'producer07-audit02', 'scope': 'local controller AST, bindings and owned temporary source files only',
          'passed': all(c['passed'] for c in checks), 'checks': checks, 'check_count': len(checks),
          'compile_controller_sha256': sha(texts['compile.py'].encode()),
          'run_controller_sha256': sha(texts['run.py'].encode()),
          'compile_request_sha256': sha((CONTROL / 'compile-request.json').read_bytes()),
          'rust_or_device_execution': False, 'actual_owner_lifecycle_qualified': False,
          'actual_own_cgroup_sampled': False, 'resource_guard_retested': False, 'owned_source_fixture_modes': 'fresh writable byte copies; no prediction of remote candidate permissions',
          'unchanged_resource_guard_basis': 'actual recovery04 compile and ordinary PASS; same source/AST'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'report_sha256': sha((OUT / 'report.json').read_bytes()),
                  'failures': [c for c in checks if not c['passed']]}))
raise SystemExit(0 if report['passed'] else 1)
