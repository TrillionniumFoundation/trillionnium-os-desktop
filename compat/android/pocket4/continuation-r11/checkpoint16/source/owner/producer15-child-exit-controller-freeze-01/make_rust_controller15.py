"""Freeze matching compile/ordinary requests only; never dispatch or run Cargo."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'producer14-fixture-controller-freeze-01'
PAIR = ROOT / 'namespace-child-exit-source-freeze-15'
OUT = ROOT / 'producer15-child-exit-controller-freeze-01'
ACTUAL = ROOT.parent / 'root-recovery-20261104-02/evidence/owner14-compile01/compile-result.json'
ACTUAL_ORDINARY = ROOT.parent / 'root-recovery-20261104-02/evidence/owner14-ordinary01/run-result.json'
REVISION = 'producer15-namespace-child-exit01'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01'
PRIOR_REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01'
PRIOR_SHA = 'a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6'
PRIOR_INVENTORY = '4660754a78ccc0f78272e1786e1395672af41b7fc30a7e259c21eaf3950b7314'
PAIR_SHA = 'a50606bd1352c885fe98a20733d340b565a87849413f579321e86e40fecc2634'


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
    assert len(raw) == 39898 and sha(raw) == PRIOR_SHA
    actual = json.loads(raw)
    assert actual['success'] is True and actual['compile_only'] is True
    assert actual['revision'] == 'producer14-retirement-fixture-repair01'
    assert actual['candidate'] == PRIOR_REMOTE + '/candidate'
    assert actual['all_source_inventory_before_sha256'] == actual['all_source_inventory_after_sha256'] == PRIOR_INVENTORY
    preimage = actual['inputs_before']
    assert preimage == actual['inputs_after'] and len(preimage) == 32
    ordinary_raw = ACTUAL_ORDINARY.read_bytes()
    assert len(ordinary_raw) == 37063 and sha(ordinary_raw) == 'd38caeef2c821b6136d51967ae5b7799b60e6796e5144ed67540bbde57c2ea91'
    ordinary = json.loads(ordinary_raw)
    assert ordinary['success'] is True and ordinary['revision'] == actual['revision']
    assert ordinary['external_compile_sha256'] == PRIOR_SHA
    assert ordinary['inputs_before'] == ordinary['inputs_after'] == preimage
    assert ordinary['all_source_inventory_before_sha256'] == ordinary['all_source_inventory_after_sha256'] == PRIOR_INVENTORY
    assert ordinary['rust_tests_passed'] == {'droidloom-pressure-relay': 37, 'droidloom-supervisor': 122}
    assert ordinary['ordinary_ipc_passed'] == 7 and ordinary['worker_context_passed'] is True and ordinary['actual_compiled_entry_abi_passed'] is True
    manifest = (PAIR / 'manifest.json').read_bytes()
    assert sha(manifest) == PAIR_SHA
    for row in json.loads(manifest)['files']:
        body = (PAIR / row['path']).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
    overlays = {}
    for name in ['runtime/droidloom-pressure-relay/src/lib.rs',
                 'runtime/droidloom-supervisor/src/development.rs',
                 'runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs',
                 'runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs']:
        old = (PAIR / 'preimage' / name).read_bytes()
        assert {'bytes': len(old), 'sha256': sha(old)} == preimage[name]
        body = (PAIR / 'candidate' / name).read_bytes()
        overlays[name] = {'bytes': len(body), 'sha256': sha(body), 'text': body.decode()}
    old_cfg = json.loads((OLD / 'payload.json').read_bytes())
    cfg = {'schema': 1, 'revision': REVISION, 'preimage': preimage, 'overlays': overlays,
           'original_diff_sha256': sha((PAIR / 'source.diff').read_bytes()),
           'source_manifest_sha256': PAIR_SHA}
    overlay_constant = 'EXACT_OVERLAY = {\n' + ''.join(
        f'    {path!r}: ({row["bytes"]}, {row["sha256"]!r}),\n' for path, row in sorted(overlays.items()))
    overlay_constant += '}\nNEW_SOURCE_FILES = set()\n'
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
        text = text.replace('producer13-retirement-terminal-drain01', 'producer14-retirement-fixture-repair01')
        text = text.replace('producer13 terminal drain01', 'producer14 fixture repair01')
        start = text.index('EXACT_OVERLAY = {')
        end = text.index('BINARIES = ', start)
        text = text[:start] + overlay_constant + text[end:]
        if name == 'run.py':
            text = once(text, 'test_summary(out, 1, 36)', 'test_summary(out, 1, 38)')
            text = once(text, 'expected_count = 37 if key == ("droidloom_pressure_relay", "lib") else 122', 'expected_count = 39 if key == ("droidloom_pressure_relay", "lib") else 128')
            text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 37, "droidloom-supervisor": 122}', 'rust_tests_passed={"droidloom-pressure-relay": 39, "droidloom-supervisor": 128}')
        ast.parse(text)
        programs[name] = text
        put(name, text)
        put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                                      fromfile='producer14/' + name, tofile='producer15/' + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    put('payload.json', payload)
    stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / 'compile-request.json').read_bytes())
    request['stdin'] = stdin
    request['idempotency_key'] = 'p4-producer15-child-exit01-compile01-' + sha(stdin.encode())[:16]
    put('compile-request.json', pretty(request))
    put('compile-stdin.py', stdin)
    template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
    assert template['execution_ready'] is False
    template['request_template']['stdin'] = programs['run.py']
    template['request_template']['idempotency_key'] = 'p4-producer15-child-exit01-ordinary01-REQUIRES_ACTUAL_SHA16'
    template['requires'] = 'Actual successful producer15-namespace-child-exit01 compile-result external SHA and root dispatch'
    template['scope'] = '39 relay/128 supervisor library tests, 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android'
    put('ordinary-run-request-template.json', pretty(template))
    put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('evidence/prior-actual-compile-result.json', raw)
    put('make_rust_controller15.py', Path(__file__).read_bytes())
    put('generator.diff', ''.join(difflib.unified_diff((OLD / 'make_rust_controller14.py').read_text().splitlines(True), Path(__file__).read_text().splitlines(True), fromfile='producer14/make_rust_controller14.py', tofile='producer15/make_rust_controller15.py')))
    put('evidence/prior-actual-ordinary-result.json', ordinary_raw)
    negative, unchanged = [], []
    for name, text in programs.items():
        ns = {'__name__': 'local_config_only'}
        exec(compile(text, name, 'exec'), ns)
        assert ns['validate_config'](cfg) == cfg
        assert ns['candidate_input_pins'](cfg) == {
            **preimage, **{p: {'bytes': row['bytes'], 'sha256': row['sha256']} for p, row in overlays.items()}}
        for label, mutate in [
            ('old_revision', lambda v: v.update(revision='producer14-retirement-fixture-repair01')),
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
    put('README.md', """# Producer15 matching compile and ordinary requests

Create-only candidate/target from actual successful producer14 compilation.
The generator independently verifies producer14's matching 37 relay, 122
supervisor and 7 IPC result; this does not qualify producer15. All 32 inputs,
full source inventory, four binary targets and explicit two-library --lib
--no-run selection remain fixed. Only the four separately frozen source15
candidate files are overlaid. Original producer13/Owner14 failures remain.

Compile uses CPU1/1GiB/600s; ordinary uses CPU1/512MiB/180s and the same held
ELF/source/resource/child-cleanup gates. Ordinary execution stays non-root and
has no Cargo, namespace, Android, pressure or network effect. The complete
source inventory is checked before/after both stages; no old target is reused.

The ordinary template is not executable until the new actual successful
compile result is fully retrieved and its SHA is externally supplied. It
expects 39 relay tests, 128 supervisor tests, two exact public retirement
controls (1 passed/38 filtered each), seven IPC controls, the original worker
context test and actual entry ABI3. These counts are expectations only. Six
supervisor tests exercise actual owned-child wait facts and the production
audit method; two relay tests exercise held pidfd post-error evidence. These
ordinary children are not a full production Owner, broker or Android init.

No prior failure is replaced. No worker retirement, authority, LMKD admission,
namespace, capability, PSI, Stop authorization, network/resource/claim cleanup
predicate is relaxed by these controllers. The resource_guard.py bytes are
identical to14: usage is observed, but hard SwapMax0 and whole-invocation
resource qualification are not claimed. A candidate ordinary PASS would still
not prove first ACTIVE or identify Owner14's original SIGHUP/boot cause.

Main's observed pids.max change remains unresolved. This freeze contains no
Android Owner runtime plan or request and cannot admit through an old Main
fence. Root alone dispatches the reviewed matching requests; this generator
has not dispatched anything. No new Rust result is asserted.
""")
    members = [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'producer15_child_exit_controller_freeze01', 'files': members}))
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
