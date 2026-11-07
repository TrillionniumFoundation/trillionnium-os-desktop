"""Bind the already observed direct Rust1.93 toolchain; no execution here."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'android-owner16-host-build-freeze01'
OUT = ROOT / 'android-owner16-host-build-freeze02'
OBS = ROOT / 'root-recovery-20261104-02/evidence/rust193-tools-recheck-read03/result.json'
BUILT = ROOT / 'root-recovery-20261104-02/evidence/typed-ingress-builder466-go5-compile02/result.json'
SYSROOT = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def pretty(value): return json.dumps(value, sort_keys=True, indent=2) + '\n'
def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

def main():
    assert not OUT.exists()
    raw = OBS.read_bytes(); built_raw = BUILT.read_bytes()
    assert len(raw) == 31452 and sha(raw) == '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
    assert len(built_raw) == 98764 and sha(built_raw) == '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab'
    observed = json.loads(raw); built = json.loads(built_raw)
    assert observed['complete'] and observed['all_observed_tool_contents_and_aliases_unchanged_after']
    assert observed['first_error'] is None and observed['secondary_errors'] == []
    assert built['state'] == 'PASS' and built['actual_tool_reobservation']['sha256'] == sha(raw)
    selected = built['actual_toolchain']
    assert selected['repository_version'] == '1.93.0' and selected['rustup_proxy_executed'] is False
    assert built['tool_changes'] == []
    rows = {row['requested_path']: row for row in observed['tools']}
    pins = {}
    for name in ('cargo', 'rustc'):
        path = SYSROOT + '/bin/' + name
        assert selected[name] == path
        row = rows[path]
        assert row['resolved_path'] == path and row['content_read'] and row['error'] is None
        assert row['compilation_admission_fields_equal'] and row['changed_compilation_admission_fields'] == []
        assert row['held_before'] == row['held_after'] == row['resolved_named_after']
        pins[path] = {'bytes': row['bytes'], 'sha256': row['sha256']}
    rd = selected['rustdoc_observed_with_sysroot_closure_this_attempt']
    assert rd['resolved_path'] == rd['requested_path'] == selected['rustdoc'] == SYSROOT + '/bin/rustdoc'
    pins[rd['requested_path']] = {'bytes': rd['bytes'], 'sha256': rd['sha256']}
    versions = {name: selected[key] for name, key in [('cargo', 'cargo_version'), ('rustc', 'rustc_verbose_version')]}
    constants = '\n'.join([
        'RUST_SYSROOT = ' + repr(SYSROOT),
        "RUSTC = RUST_SYSROOT + '/bin/rustc'",
        "RUSTDOC = RUST_SYSROOT + '/bin/rustdoc'",
        'DIRECT_TOOL_PINS = ' + repr(pins),
        'DIRECT_TOOL_VERSIONS = ' + repr(versions),
        'DIRECT_TOOL_OBSERVATION_SHA = ' + repr(sha(raw)),
        'DIRECT_TOOL_ACTUAL_BUILD_SHA = ' + repr(sha(built_raw)),
    ]) + '\n'
    helper = '''def command_env(target):
    # Fresh fixed environment: no ambient rustup selection, wrappers, loader
    # injection or Cargo flags survive. Empty wrapper values also override a
    # same-name Cargo config selection; no doctests are requested.
    return {
        "PATH": RUST_SYSROOT + "/bin:/usr/bin:/bin", "HOME": "/home/alex",
        "CARGO_HOME": "/home/alex/.cargo", "RUSTC": RUSTC, "RUSTDOC": RUSTDOC,
        "LANG": "C", "LC_ALL": "C", "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": "1", "CARGO_INCREMENTAL": "0",
        "CARGO_PROFILE_DEV_DEBUG": "0", "CARGO_PROFILE_TEST_DEBUG": "0",
        "RUST_TEST_THREADS": "1", "CARGO_TARGET_DIR": str(target),
        "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "RUSTFLAGS": "",
        "CARGO_ENCODED_RUSTFLAGS": "", "RUSTDOCFLAGS": "", "CARGO_ENCODED_RUSTDOCFLAGS": "",
        "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER": "/usr/bin/cc",
    }

def direct_tool_pins():
    result = {}
    for name, expected in DIRECT_TOOL_PINS.items():
        path = Path(name)
        need(path.resolve(strict=True) == path, "fixed direct Rust tool acquired an alias")
        before = path.lstat()
        need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and
             before.st_mode & 0o22 == 0, "direct Rust tool owner/mode differs")
        row = file_pin(path, require_elf=True)
        after = path.lstat()
        need(stamp(before) == stamp(after) and row["device"] == after.st_dev and
             row["inode"] == after.st_ino and path.resolve(strict=True) == path,
             "direct Rust tool named/held identity differs")
        need(row["bytes"] == expected["bytes"] and row["sha256"] == expected["sha256"],
             "actual observed direct Rust tool contents differ: " + name)
        result[name] = row
    return result

def direct_tool_versions(report, env):
    rows = {}
    for name, argv in [("cargo", [CARGO, "--version"]), ("rustc", [RUSTC, "-vV"])]:
        out, err = run_command(report, OUT, argv, CANDIDATE, env, 10)
        need(not err and out.decode("utf-8") == DIRECT_TOOL_VERSIONS[name],
             "actual direct Rust version differs: " + name)
        rows[name] = out.decode("utf-8")
    return rows

'''
    files = {}
    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode('utf-8'); assert name not in files
        files[name] = data
    programs = {}
    unchanged = []
    for name in ('compile.py', 'run.py'):
        old = (OLD / name).read_text()
        text = once(old, 'CARGO = "/home/alex/.cargo/bin/cargo"', 'CARGO = ' + repr(SYSROOT + '/bin/cargo') + '\n' + constants)
        text = text.replace('/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-01', '/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-02')
        begin, end = text.index('def command_env(target):'), text.index('def run_command(')
        text = text[:begin] + helper + text[end:]
        if name == 'compile.py':
            text = once(text, '    before = None\n', '    before = None\n    tool_before = None\n')
            text = once(text, '        env = command_env(TARGET)\n', '''        env = command_env(TARGET)
        tool_before = direct_tool_pins()
        report["direct_toolchain_before"] = tool_before
        report["direct_tool_authority"] = {"observation_sha256": DIRECT_TOOL_OBSERVATION_SHA,
            "actual_builder_compile_sha256": DIRECT_TOOL_ACTUAL_BUILD_SHA,
            "rustup_proxy_executed": False, "tool_install_or_update_requested": False,
            "compiler_runtime_libraries_not_rehashed_by_this_narrow_gate": True}
        report["direct_versions_before"] = direct_tool_versions(report, env)
''')
            text = once(text, '"CARGO_HOME", "RUSTUP_HOME"', '"CARGO_HOME", "PATH", "RUSTC", "RUSTDOC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"')
            text = once(text, '    finish_own_resource_gate(report, resources)\n', '''    if tool_before is not None:
        try:
            report["direct_toolchain_after"] = direct_tool_pins()
            need(report["direct_toolchain_after"] == tool_before, "direct Rust tools changed during compilation")
            report["direct_versions_after"] = direct_tool_versions(report, env)
            need(report["direct_versions_before"] == report["direct_versions_after"], "direct Rust version changed during compilation")
        except Exception as failure:
            report["success"] = False
            if "error" not in report:
                report["error"] = type(failure).__name__ + ": " + str(failure)
                report["traceback"] = traceback.format_exc()
            else:
                report.setdefault("failure_collection_errors", []).append("direct tool final check: " + str(failure))
    finish_own_resource_gate(report, resources)
''')
        else:
            text = once(text, '        put(run_dir / "admitted-compile-result.json", raw)', '''        need(actual["direct_tool_authority"]["observation_sha256"] == DIRECT_TOOL_OBSERVATION_SHA and
             actual["direct_tool_authority"]["actual_builder_compile_sha256"] == DIRECT_TOOL_ACTUAL_BUILD_SHA and
             actual["direct_tool_authority"]["rustup_proxy_executed"] is False and
             actual["direct_toolchain_before"] == actual["direct_toolchain_after"] and
             {p: {k: row[k] for k in ("bytes", "sha256")} for p, row in actual["direct_toolchain_before"].items()} == DIRECT_TOOL_PINS and
             actual["direct_versions_before"] == actual["direct_versions_after"] == DIRECT_TOOL_VERSIONS,
             "actual compile direct Rust tool authority differs")
        put(run_dir / "admitted-compile-result.json", raw)''')
        ast.parse(text)
        a = {n.name: ast.dump(n) for n in ast.parse(old).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        b = {n.name: ast.dump(n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for key in a:
            if key not in ('command_env', 'compile_recovery', 'ordinary_recovery'):
                assert a[key] == b[key], (name, key)
                unchanged.append(name + ':' + key)
        programs[name] = text
        put(name, text)
        put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), fromfile='unsubmitted-host16-01/' + name, tofile='direct-host16-02/' + name)))
    payload = (OLD / 'payload.json').read_text()
    stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
    request = json.loads((OLD / 'compile-request.json').read_bytes())
    request.update(stdin=stdin, idempotency_key='p4-producer16-init-log01-compile02-' + sha(stdin.encode())[:16])
    template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
    assert template['execution_ready'] is False
    template['request_template'].update(stdin=programs['run.py'], idempotency_key='p4-producer16-init-log01-ordinary02-REQUIRES_ACTUAL_SHA16')
    put('compile-request.json', pretty(request)); put('compile-stdin.py', stdin)
    put('payload.json', payload); put('ordinary-run-request-template.json', pretty(template))
    put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('evidence/rust193-tools-recheck-read03.json', raw)
    put('evidence/builder466-actual-direct-toolchain.json', pretty({'path': str(BUILT), 'bytes': len(built_raw),
        'sha256': sha(built_raw), 'actual_toolchain': selected, 'state': built['state'], 'tool_changes': built['tool_changes']}))
    put('make_host_build02.py', Path(__file__).read_bytes())
    # Pure environment/pin binding checks. Never execute compile/ordinary here.
    checks = []
    for name, text in programs.items():
        scope = {'__name__': 'local_source_only'}; exec(compile(text, name, 'exec'), scope)
        env = scope['command_env'](Path('/owned-test-target'))
        assert not any(k.startswith('RUSTUP') for k in env)
        assert env['RUSTC'] == SYSROOT + '/bin/rustc' and '/home/alex/.cargo/bin' not in env['PATH'].split(':')
        assert all(env.get(k) == '' for k in ('RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER'))
        assert all(k not in env for k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'RUSTC_BOOTSTRAP'))
        assert scope['validate_config'](json.loads(payload)) == json.loads(payload)
        checks.append({'file': name, 'fresh_direct_environment': True, 'source_payload_unchanged': True})
    put('validation.json', pretty({'schema': 1, 'execution_status': 'NOT_SUBMITTED', 'source_payload_unchanged': True,
        'source33_resource_outputs_and_original_gates_unchanged': True, 'old_freeze01_not_submitted': True,
        'actual_tool_observation_sha256': sha(raw), 'actual_direct_tool_build_sha256': sha(built_raw),
        'tool_pins': pins, 'versions': versions, 'local_only_checks': checks, 'unchanged_function_AST': unchanged,
        'expected_compile_commands': 6, 'Rust_compiled_or_tests_executed': False,
        'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
        'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode())}))
    put('README.md', '''# Host16 direct Rust1.93 build02

Unsubmitted freeze01 remains unchanged. Same33-source payload, original
source inventory, four bins/two library no-run targets, CPU1/1GiB/600s and
original failure/resource/child gates. Only new remote build02 root/key and
direct observed tool selection are introduced. No Main or Owner operation.

Cargo and rustc are the exact Rust1.93 absolute ELF paths from the complete
actual read03; rustdoc was fully observed in actual builder466 compile02.
These three ELF size/hash/named identities are checked before and after.
Actual --version/-vV bytes must match before and after; no rustup is run.
Fresh fixed PATH/RUSTC/RUSTDOC and empty wrapper/flags selections discard
ambient rustup, loader and compiler overrides. No update/download is used.
This narrow added gate does not rehash all compiler runtime libraries; that
broader prior closure is not falsely claimed as repeated by this request.

The two build commands plus four version checks are recorded independently.
A build failure remains first even when final tool checks also fail. Source
and artifact validators are unchanged. Ordinary remains non-executable until
the actual new compile SHA; it checks the retained direct-tool gate without
executing Cargo. Core8 production sources remain the same freeze01.
''')
    put('manifest.json', pretty({'schema': 1, 'files': [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())]}))
    OUT.mkdir()
    for name, data in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(data)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
        'request_bytes': len(files['compile-request.json']), 'request_sha256': sha(files['compile-request.json']),
        'stdin_bytes': len(stdin.encode()), 'stdin_sha256': sha(stdin.encode()), 'key': request['idempotency_key']}))

if __name__ == '__main__': main()
