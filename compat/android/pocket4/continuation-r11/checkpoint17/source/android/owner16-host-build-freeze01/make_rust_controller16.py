"""Freeze matching compile/ordinary requests only; never dispatch or run Cargo."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'lmkd-recovery-20261105-01/producer15-child-exit-controller-freeze-01'
PAIR = ROOT / 'android-owner16-init-log-source-freeze01'
OUT = ROOT / 'android-owner16-host-build-freeze01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner15-compile01/compile-result.json'
ACTUAL_ORDINARY = ROOT / 'root-recovery-20261104-02/evidence/owner15-ordinary01/run-result.json'
REVISION = 'producer16-bounded-init-log01'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-01'
PRIOR_REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01'
PRIOR_SHA = '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'
PRIOR_INVENTORY = 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'
PAIR_SHA = 'c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def assignment(text, name, value):
    pattern = re.compile(r'^' + re.escape(name) + r' = [^\n]+$', re.M)
    assert len(pattern.findall(text)) == 1, name
    return pattern.sub(lambda _: name + ' = ' + value, text)


def main():
    assert not OUT.exists(), 'immutable create-only controller snapshot'
    files = {}

    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode('utf-8')
        assert name not in files
        files[name] = data

    raw = ACTUAL.read_bytes()
    assert len(raw) == 39999 and sha(raw) == PRIOR_SHA
    actual = json.loads(raw)
    assert actual['success'] is True and actual['compile_only'] is True
    assert actual['revision'] == 'producer15-namespace-child-exit01'
    assert actual['candidate'] == PRIOR_REMOTE + '/candidate'
    assert actual['all_source_inventory_before_sha256'] == actual['all_source_inventory_after_sha256'] == PRIOR_INVENTORY
    preimage = actual['inputs_before']
    assert preimage == actual['inputs_after'] and len(preimage) == 32
    ordinary_raw = ACTUAL_ORDINARY.read_bytes()
    assert len(ordinary_raw) == 37356 and sha(ordinary_raw) == 'ae364c528e0fca047357b13d91814bd461cc539320e78450a096ed64f889c76e'
    ordinary = json.loads(ordinary_raw)
    assert ordinary['success'] is True and ordinary['revision'] == actual['revision']
    assert ordinary['external_compile_sha256'] == PRIOR_SHA
    assert ordinary['inputs_before'] == ordinary['inputs_after'] == preimage
    assert ordinary['all_source_inventory_before_sha256'] == ordinary['all_source_inventory_after_sha256'] == PRIOR_INVENTORY
    assert ordinary['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 128}
    assert ordinary['ordinary_ipc_passed'] == 7 and ordinary['worker_context_passed'] is True and ordinary['actual_compiled_entry_abi_passed'] is True
    manifest = (PAIR / 'SOURCE_PINS.json').read_bytes()
    assert sha(manifest) == PAIR_SHA
    for name, row in json.loads(manifest)['files'].items():
        body = (PAIR / name).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
    overlays = {}
    for name in sorted(p for p in json.loads((PAIR / 'validation.json').read_bytes())['production_files'] if p.startswith('runtime/')):
        before_path = PAIR / 'preimage' / name
        if before_path.exists():
            old = before_path.read_bytes()
            assert {'bytes': len(old), 'sha256': sha(old)} == preimage[name]
        else:
            assert name == 'runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs' and name not in preimage
        body = (PAIR / 'candidate' / name).read_bytes()
        overlays[name] = {'bytes': len(body), 'sha256': sha(body), 'text': body.decode()}
    old_cfg = json.loads((OLD / 'payload.json').read_bytes())
    cfg = {'schema': 1, 'revision': REVISION, 'preimage': preimage, 'overlays': overlays,
           'original_diff_sha256': sha((PAIR / 'production.diff').read_bytes()),
           'source_manifest_sha256': PAIR_SHA}
    overlay_constant = 'EXACT_OVERLAY = {\n' + ''.join(
        f'    {path!r}: ({row["bytes"]}, {row["sha256"]!r}),\n' for path, row in sorted(overlays.items()))
    overlay_constant += "}\nNEW_SOURCE_FILES = {'runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs'}\n"
    programs = {}
    for name in ('compile.py', 'run.py'):
        old = (OLD / name).read_text()
        text = old
        for key, value in {
            'CONTROL_REVISION': repr(REVISION), 'BASE': f'Path({PRIOR_REMOTE!r})',
            'OUT': f'Path({REMOTE!r})', 'PRIOR_RECEIPT_SHA': repr(PRIOR_SHA),
            'PRIOR_INVENTORY_SHA': repr(PRIOR_INVENTORY), 'ORIGINAL_DIFF_SHA': repr(cfg['original_diff_sha256']),
        }.items():
            text = assignment(text, key, value)
        assert old_cfg['source_manifest_sha256'] in text
        text = text.replace(old_cfg['source_manifest_sha256'], PAIR_SHA)
        text = text.replace('producer14-retirement-fixture-repair01', 'producer15-namespace-child-exit01')
        text = text.replace('producer14 fixture repair01', 'producer15 namespace child exit01')
        start = text.index('EXACT_OVERLAY = {')
        end = text.index('BINARIES = ', start)
        text = text[:start] + overlay_constant + text[end:]
        text = once(text, 'len(set(cfg["preimage"]) | set(cfg["overlays"])) == 32', 'len(set(cfg["preimage"]) | set(cfg["overlays"])) == 33')
        if name == 'run.py':
            text = once(text, 'expected_count = 39 if key == ("droidloom_pressure_relay", "lib") else 128', 'expected_count = 39 if key == ("droidloom_pressure_relay", "lib") else 136')
            text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 39, "droidloom-supervisor": 128}', 'rust_tests_passed={"droidloom-pressure-relay": 39, "droidloom-supervisor": 136}')
        ast.parse(text)
        programs[name] = text
        put(name, text)
        put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                                      fromfile='producer15/' + name, tofile='producer16/' + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    put('payload.json', payload)
    stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / 'compile-request.json').read_bytes())
    request['stdin'] = stdin
    request['idempotency_key'] = 'p4-producer16-init-log01-compile01-' + sha(stdin.encode())[:16]
    put('compile-request.json', pretty(request))
    put('compile-stdin.py', stdin)
    template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
    assert template['execution_ready'] is False
    template['request_template']['stdin'] = programs['run.py']
    template['request_template']['idempotency_key'] = 'p4-producer16-init-log01-ordinary01-REQUIRES_ACTUAL_SHA16'
    template['requires'] = 'Actual successful producer16-bounded-init-log01 compile-result external SHA and root dispatch'
    template['scope'] = '39 relay/136 supervisor library tests, 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android'
    put('ordinary-run-request-template.json', pretty(template))
    put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('evidence/prior-actual-compile-result.json', raw)
    put('make_rust_controller16.py', Path(__file__).read_bytes())
    put('generator.diff', ''.join(difflib.unified_diff((OLD / 'make_rust_controller15.py').read_text().splitlines(True), Path(__file__).read_text().splitlines(True), fromfile='producer15/make_rust_controller15.py', tofile='producer16/make_rust_controller16.py')))
    put('evidence/prior-actual-ordinary-result.json', ordinary_raw)
    negative, unchanged = [], []
    for name, text in programs.items():
        ns = {'__name__': 'local_config_only'}
        exec(compile(text, name, 'exec'), ns)
        assert ns['validate_config'](cfg) == cfg
        assert ns['candidate_input_pins'](cfg) == {
            **preimage, **{p: {'bytes': row['bytes'], 'sha256': row['sha256']} for p, row in overlays.items()}}
        for label, mutate in [
            ('old_revision', lambda v: v.update(revision='producer15-namespace-child-exit01')),
            ('wrong_pair_manifest', lambda v: v.update(source_manifest_sha256='0' * 64)),
            ('missing_overlay', lambda v: v['overlays'].pop(next(iter(overlays)))),
            ('wrong_overlay_bytes', lambda v: v['overlays'][next(iter(overlays))].update(text='old')),
        ]:
            bad = copy.deepcopy(cfg); mutate(bad)
            try:
                ns['validate_config'](bad)
            except RuntimeError:
                negative.append({'controller': name, 'case': label, 'rejected': True})
            else:
                raise AssertionError('bad config accepted')
        old_functions = {n.name: ast.dump(n) for n in ast.parse((OLD / name).read_text()).body
                         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_functions = {n.name: ast.dump(n) for n in ast.parse(text).body
                         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert old_functions.keys() == new_functions.keys()
        for key in old_functions:
            if key not in {'validate_config', 'compile_recovery', 'ordinary_recovery'}:
                assert old_functions[key] == new_functions[key], (name, key)
                unchanged.append(name + ':' + key)
    parsed = ast.parse(stdin)
    call = parsed.body[-1].value
    assert call.func.id == 'compile_recovery' and call.args[0].args[0].value == payload
    assert ast.dump(ast.Module(body=parsed.body[:-1], type_ignores=[])) == ast.dump(ast.parse(programs['compile.py']))
    old_request = json.loads((OLD / 'compile-request.json').read_bytes())
    assert {k: v for k, v in request.items() if k not in {'stdin', 'idempotency_key'}} == {
        k: v for k, v in old_request.items() if k not in {'stdin', 'idempotency_key'}}
    put('validation.json', pretty({'schema': 1, 'execution_status': 'NOT_SUBMITTED',
        'source_pair_manifest_sha256': PAIR_SHA, 'prior_actual_receipt_sha256': PRIOR_SHA,
        'base_input_count': 32, 'overlays': sorted(overlays), 'negative_config_controls': negative,
        'unchanged_function_or_class_AST': unchanged, 'request_argv_resources_and_all_other_keys_unchanged': True,
        'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
        'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode()),
        'actual_Rust_tests_run': False, 'actual_Owner_qualified': False}))
    put('README.md', """# Owner16 matching host compile and ordinary template

Create-only 33-input candidate from the actual successful producer15 build
3327495b… and matching ordinary ae364c… . Five frozen Rust overlays include
four exact preimages and one explicitly absent new init_log module. Original
full-inventory/source/artifact/child/resource gates remain unchanged.

Compile: non-root CPU1/1GiB/600s, four actual bins plus two --lib --no-run
artifacts, offline/locked/jobs1. No test/Android/Owner runtime is executed by
this request. Fresh target only; no original candidate or cache mutation.

The ordinary template remains NOT_READY until this actual compile receipt.
It requires 39 relay and 136 supervisor tests (128 original plus 8 new), the
same two public retirement tests, seven IPC, worker context and entry ABI3.
Eight new tests use owned memfd/ordinary exec and explicit failure seams;
they do not certify an Android KernelLogger or full namespace lifecycle.

The paired C source must be separately compiled with actual added dlfcn/libdl
inputs. Its actual DSO and this actual host build must be bound before any
new runtime. Owner16's dedicated full-prefix response/actor bounds also need
review; no Owner runtime request is contained here. Existing failures and
Main's unchanged original identity/resource gates remain authoritative.
""")
    members = [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'producer16_init_log_controller_freeze01', 'files': members}))
    OUT.mkdir()
    for name, data in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
                  'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
                  'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode()),
                  'key': request['idempotency_key']}))


if __name__ == '__main__':
    main()
