"""Create-only Host17 compile packet, derived from the exact actual Host16 chain."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'android-owner16-host-build-freeze02'
SOURCE = ROOT / 'android-owner17-bootstrap-mode-source-freeze01'
OUT = ROOT / 'android-owner17-host-build-freeze01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner16-host-log-compile02/compile-result.json'
REL = 'runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs'
REVISION = 'producer17-owned-bootstrap-modes01'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-bootstrap-mode-r11-build-17-01'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def main():
    assert not OUT.exists()
    old_manifest = json.loads((OLD / 'manifest.json').read_bytes())
    for row in old_manifest['files']:
        body = (OLD / row['path']).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
    source_manifest_raw = (SOURCE / 'SOURCE_PINS.json').read_bytes()
    assert sha(source_manifest_raw) == 'dca55eadb80fe20905f4aadc2420ac89406fb9c019bea97a73e67526b408a845'
    source_manifest = json.loads(source_manifest_raw)
    for name, row in source_manifest['files'].items():
        body = (SOURCE / name).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256']
    actual_raw = ACTUAL.read_bytes()
    assert len(actual_raw) == 49729 and sha(actual_raw) == 'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea'
    actual = json.loads(actual_raw)
    assert actual['success'] and actual['compile_only'] and actual['revision'] == 'producer16-bounded-init-log01'
    assert len(actual['commands']) == 6 and all(r['returncode'] == 0 and not r['timed_out'] for r in actual['commands'])
    assert actual['inputs_before'] == actual['inputs_after'] and len(actual['inputs_before']) == 33
    assert actual['all_source_inventory_before_sha256'] == actual['all_source_inventory_after_sha256']
    old_payload = json.loads((OLD / 'payload.json').read_bytes())
    old_expected = dict(old_payload['preimage'])
    old_expected.update({p: {k: r[k] for k in ['bytes', 'sha256']} for p, r in old_payload['overlays'].items()})
    assert old_expected == actual['inputs_before']
    source_body = (SOURCE / 'candidate' / REL).read_bytes()
    preimage = (SOURCE / 'preimage' / REL).read_bytes()
    assert actual['inputs_before'][REL] == {'bytes': len(preimage), 'sha256': sha(preimage)}
    diff_body = (SOURCE / 'production.diff').read_bytes()
    payload = {'schema': 1, 'revision': REVISION, 'preimage': actual['inputs_before'],
        'overlays': {REL: {'bytes': len(source_body), 'sha256': sha(source_body), 'text': source_body.decode()}},
        'original_diff_sha256': sha(diff_body), 'source_manifest_sha256': sha(source_manifest_raw)}
    payload_body = pretty(payload)
    files = {}
    def put(name, body):
        body = body.encode() if isinstance(body, str) else body
        body.decode('utf-8'); assert name not in files
        files[name] = body
    programs = {}
    unchanged = []
    for name in ['compile.py', 'run.py']:
        old = (OLD / name).read_text()
        text = once(old, "CONTROL_REVISION = 'producer16-bounded-init-log01'", 'CONTROL_REVISION = ' + repr(REVISION))
        text = once(text, "BASE = Path('/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01')",
                    "BASE = Path('/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-02')")
        text = once(text, "OUT = Path('/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-02')",
                    'OUT = Path(' + repr(REMOTE) + ')')
        text = once(text, "PRIOR_RECEIPT_SHA = '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'",
                    'PRIOR_RECEIPT_SHA = ' + repr(sha(actual_raw)))
        text = once(text, "PRIOR_INVENTORY_SHA = 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'",
                    'PRIOR_INVENTORY_SHA = ' + repr(actual['all_source_inventory_before_sha256']))
        text = once(text, "ORIGINAL_DIFF_SHA = 'cf5ba26e0f3efe86b6eec6ed140c8688df4ebc24f043dbdee4a07b94239744ef'",
                    'ORIGINAL_DIFF_SHA = ' + repr(sha(diff_body)))
        begin, end = text.index('EXACT_OVERLAY = {'), text.index('BINARIES = [')
        text = text[:begin] + 'EXACT_OVERLAY = ' + repr({REL: (len(source_body), sha(source_body))}) + '\nNEW_SOURCE_FILES = set()\n' + text[end:]
        text = once(text, '"c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050"', repr(sha(source_manifest_raw)))
        text = once(text, 'len(cfg["preimage"]) == 32', 'len(cfg["preimage"]) == 33')
        text = text.replace('producer15-namespace-child-exit01', 'producer16-bounded-init-log01')
        text = text.replace('producer15 namespace child exit01', 'producer16 bounded init log01')
        text = text.replace('32 original source inputs differ', '33 original source inputs differ')
        text = text.replace('32 inputs changed during compile', '33 inputs changed during compile')
        if name == 'run.py':
            text = once(text, 'else 136\n', 'else 139\n')
            text = once(text, '"droidloom-supervisor": 136}', '"droidloom-supervisor": 139}')
        ast.parse(text)
        before_ast = {n.name: ast.dump(n) for n in ast.parse(old).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        after_ast = {n.name: ast.dump(n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert before_ast.keys() == after_ast.keys()
        allowed = {'validate_config', 'compile_recovery' if name == 'compile.py' else 'ordinary_recovery'}
        for symbol in before_ast:
            if symbol not in allowed:
                assert before_ast[symbol] == after_ast[symbol], (name, symbol)
                unchanged.append(name + ':' + symbol)
        programs[name] = text
        put(name, text)
        put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
            fromfile='actual-host16/' + name, tofile='candidate-host17/' + name)))
    stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload_body.decode() + "'''))\n"
    ast.parse(stdin)
    request = copy.deepcopy(json.loads((OLD / 'compile-request.json').read_bytes()))
    request.update(stdin=stdin, idempotency_key='p4-producer17-bootstrap-modes01-compile01-' + sha(stdin.encode())[:16])
    template = copy.deepcopy(json.loads((OLD / 'ordinary-run-request-template.json').read_bytes()))
    assert template['execution_ready'] is False
    template['request_template'].update(stdin=programs['run.py'],
        idempotency_key='p4-producer17-bootstrap-modes01-ordinary01-REQUIRES_ACTUAL_SHA16')
    template['requires'] = 'Actual successful producer17-owned-bootstrap-modes01 compile-result external SHA and root dispatch'
    template['scope'] = '39 relay/139 supervisor library tests (old136 plus3 FD-mode controls), 2 public retirement tests, 7 IPC, worker-context and entry ABI3; no actual Owner/Android'
    for name, text in programs.items():
        namespace = {'__name__': 'local_source_only'}
        exec(compile(text, name, 'exec'), namespace)
        assert namespace['validate_config'](payload) == payload
        assert namespace['candidate_input_pins'](payload) == {**actual['inputs_before'], REL: {'bytes': len(source_body), 'sha256': sha(source_body)}}
        assert namespace['CARGO'] == '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo'
        assert namespace['DIRECT_TOOL_PINS'] == {p: {k: r[k] for k in ['bytes', 'sha256']} for p, r in actual['direct_toolchain_before'].items()}
        env = namespace['command_env'](Path('/owned-compile-target'))
        assert env['RUSTC'] == namespace['RUSTC'] and env['RUSTDOC'] == namespace['RUSTDOC']
        assert not any(k.startswith('RUSTUP') for k in env) and '/home/alex/.cargo/bin' not in env['PATH']
        assert env['RUSTC_WRAPPER'] == env['RUSTC_WORKSPACE_WRAPPER'] == ''
    put('payload.json', payload_body)
    put('compile-stdin.py', stdin)
    put('compile-request.json', pretty(request))
    put('ordinary-run-request-template.json', pretty(template))
    put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('lineage/actual-host16-compile-result.json', actual_raw)
    put('lineage/host16-build-manifest.json', (OLD / 'manifest.json').read_bytes())
    put('lineage/owner17-source-manifest.json', source_manifest_raw)
    put('make_host_build01.py', Path(__file__).read_bytes())
    put('validation.json', pretty({'schema': 1, 'execution_status': 'NOT_SUBMITTED',
        'prior_actual_compile_bytes': len(actual_raw), 'prior_actual_compile_sha256': sha(actual_raw),
        'source_count': 33, 'changed_source_count': 1, 'new_source_files': [],
        'actual_prior_full_inventory_sha256': actual['all_source_inventory_before_sha256'],
        'new_full_inventory_sha256': 'NOT_KNOWN_UNTIL_ACTUAL_COMPILE',
        'source_manifest_sha256': sha(source_manifest_raw), 'production_diff_sha256': sha(diff_body),
        'exact_config_and_current_input_pins': True, 'unchanged_function_AST': unchanged,
        'direct_Rust193_tool_pins_versions_environment_unchanged': True,
        'resource_guard_original_bytes_unchanged': True, 'expected_compile_commands': 6,
        'expected_ordinary_relay_tests': 39, 'expected_ordinary_supervisor_tests': 139,
        'new_Rust_tests_pending': 3, 'expected_ordinary_commands': 7,
        'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
        'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode()),
        'Rust_compiled_or_tests_executed': False, 'Main_Android_or_generation_started': False}))
    put('README.md', '''# Host17 owned bootstrap mode build-only

One entry.rs overlay is applied to a new isolated copy of the actual Host16
complete source tree. Exact prior compile49729/dad36fe9 and all33 input pins
plus the complete a4b00fa3 inventory are required before copying. The new
full inventory is measured during the build; no predicted value is actual.

Direct observed Rust1.93 cargo/rustc/rustdoc pins, before/after versions,
fresh fixed environment, source/ELF identity checks, first-error handling,
children, CPU1/1GiB/600s and all resource gates are retained. No rustup,
downloads, Main actions, Android build/runtime, mounts or unit changes.
The C16 barrier/ABI3/logger bytes are not rebuilt or modified by this request.

Compile performs four version commands and two locked offline Cargo no-run
commands. Ordinary remains NOT_READY until the real compile receipt SHA.
It retains the39 relay tests, all prior136 supervisor tests and adds3 owned
FD-mode tests for an exact139 total. The two exact retirement controls,
7 IPC cases, worker context and entry ABI3 gates remain unchanged. These
tests do not authorize a root private mount or prove the full LMKD/HWS cause.
''')
    put('manifest.json', pretty({'schema': 1, 'files': [{'path': name, 'bytes': len(body), 'sha256': sha(body)}
        for name, body in sorted(files.items())]}))
    OUT.mkdir()
    for name, body in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True); path.open('xb').write(body)
    print(json.dumps({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
        'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
        'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode()), 'key': request['idempotency_key']}))


if __name__ == '__main__':
    main()
