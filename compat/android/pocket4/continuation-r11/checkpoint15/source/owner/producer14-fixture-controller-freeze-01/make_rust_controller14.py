"""Freeze matching compile/ordinary requests only; never dispatch or run Cargo."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'producer13-retirement-controller-freeze-01'
PAIR = ROOT / 'retirement-fixture-repair-source-freeze-14'
OUT = ROOT / 'producer14-fixture-controller-freeze-01'
ACTUAL = ROOT.parent / 'root-recovery-20261104-02/evidence/owner13-compile01/compile-result.json'
REVISION = 'producer14-retirement-fixture-repair01'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01'
PRIOR_REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-drain-r11-build-13-01'
PRIOR_SHA = '9a2cf0087ff99b6834fc2b3a963e03629a14acc21af1a8d67f2b5081bbb22e8e'
PRIOR_INVENTORY = 'bbd03d6760a2ab9e584d8ea3cfc84a8804b4ec0f144742f0e1a51e9f46d061a1'
PAIR_SHA = '6ae91802b992dba1d48c725e99e51a7daade464f4c5006f78575050f759bcccb'


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
    assert len(raw) == 39831 and sha(raw) == PRIOR_SHA
    actual = json.loads(raw)
    assert actual['success'] is True and actual['compile_only'] is True
    assert actual['revision'] == 'producer13-retirement-terminal-drain01'
    assert actual['candidate'] == PRIOR_REMOTE + '/candidate'
    assert actual['all_source_inventory_before_sha256'] == actual['all_source_inventory_after_sha256'] == PRIOR_INVENTORY
    preimage = actual['inputs_before']
    assert preimage == actual['inputs_after'] and len(preimage) == 32
    manifest = (PAIR / 'manifest.json').read_bytes()
    assert sha(manifest) == PAIR_SHA
    for row in json.loads(manifest)['files']:
        body = (PAIR / row['path']).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
    overlays = {}
    for name in ['runtime/droidloom-pressure-relay/src/lib.rs',
                 'runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs']:
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
        text = text.replace('producer11-retirement-cause01', 'producer13-retirement-terminal-drain01')
        text = text.replace('producer11 retained cause01', 'producer13 terminal drain01')
        start = text.index('EXACT_OVERLAY = {')
        end = text.index('BINARIES = ', start)
        text = text[:start] + overlay_constant + text[end:]
        ast.parse(text)
        programs[name] = text
        put(name, text)
        put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                                      fromfile='producer13/' + name, tofile='producer14/' + name)))
    payload = pretty(cfg)
    assert "'''" not in payload and len(payload.encode()) < 512 * 1024
    put('payload.json', payload)
    stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / 'compile-request.json').read_bytes())
    request['stdin'] = stdin
    request['idempotency_key'] = 'p4-producer14-fixture01-compile01-' + sha(stdin.encode())[:16]
    put('compile-request.json', pretty(request))
    put('compile-stdin.py', stdin)
    template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
    assert template['execution_ready'] is False
    template['request_template']['stdin'] = programs['run.py']
    template['request_template']['idempotency_key'] = 'p4-producer14-fixture01-ordinary01-REQUIRES_ACTUAL_SHA16'
    template['requires'] = 'Actual successful producer14-retirement-fixture-repair01 compile-result external SHA and root dispatch'
    template['scope'] = '37 relay/122 supervisor library tests, 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android'
    put('ordinary-run-request-template.json', pretty(template))
    put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('evidence/prior-actual-compile-result.json', raw)
    put('make_rust_controller14.py', Path(__file__).read_bytes())
    negative, unchanged = [], []
    for name, text in programs.items():
        ns = {'__name__': 'local_config_only'}
        exec(compile(text, name, 'exec'), ns)
        assert ns['validate_config'](cfg) == cfg
        assert ns['candidate_input_pins'](cfg) == {
            **preimage, **{p: {'bytes': row['bytes'], 'sha256': row['sha256']} for p, row in overlays.items()}}
        for label, mutate in [
            ('old_revision', lambda v: v.update(revision='producer13-retirement-terminal-drain01')),
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
    put('README.md', """# Producer14 matching compile and ordinary requests

Create-only candidate/target from the actual successful producer13 compile.
All 32 original inputs and the full source inventory are fixed before/after
copying. Exactly lib.rs and lifecycle_bootstrap.rs receive the separately frozen
test-fixture corrections. Their production prefixes are byte-identical. The
pressure codec, lifecycle relay, Android DSO, entry ABI, authority, network and
Main are unchanged. The previous actual producer13 ordinary failure is retained
in the source freeze; it is not an eligible successful ordinary predecessor.

The held-source and own-cgroup gates, CPU1/1GiB/600s compile, four binary targets
and explicit two-library --lib --no-run selection are unchanged. The ordinary
template requires this revision's actual successful compile receipt. It expects
37 relay and 122 supervisor library tests, two original public retirement cases
(1 pass/36 filtered), seven IPC controls, worker context and entry ABI3. Test
counts and the complete ordinary execution functions remain unchanged from13.
These are expectations, not new actual results.

The faulted fixture retains its old invalid-encoding rejection before setting
incomplete=true. The dead-proc fixture captures raw openat errno using the same
held FD, name and flags, then requires exact error preservation by the production
wrapper. The actual original kernel value was ESRCH, not the old ENOENT guess.
No Rust tests or actual Owner runtime have executed for this revision yet.

The operator build contract observes swap usage and own-cgroup memory events.
It does not assert hard MemorySwapMax=0 or whole-invocation resource qualification;
actual producer13 records swap.max=max and whole-invocation qualification false.
Any fresh Android Owner remains separately gated on matching successful ordinary
results, actual artifacts, its own hard resource gates and Root review.
""")
    members = [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'producer14_fixture_controller_freeze01', 'files': members}))
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
