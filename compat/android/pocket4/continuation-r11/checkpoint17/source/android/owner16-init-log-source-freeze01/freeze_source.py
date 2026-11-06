"""Create an immutable paired production-source snapshot, never build or run."""
import difflib
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent
OUT = ROOT / 'android-owner16-init-log-source-freeze01'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pretty(value): return json.dumps(value, sort_keys=True, indent=2) + '\n'


def main():
    assert not OUT.exists()
    files = {}
    def put(path, raw):
        raw = raw.encode() if isinstance(raw, str) else raw
        raw.decode('utf-8')
        assert path not in files
        files[path] = raw
    pins = json.loads((WORK / 'wip02-source-pins.json').read_bytes())['files']
    assert len(pins) == 8
    for name, expected in pins.items():
        raw = (WORK / 'candidate' / name).read_bytes()
        assert {'bytes': len(raw), 'sha256': sha(raw)} == expected
        put('candidate/' + name, raw)
    before = json.loads((WORK / 'preimage-bindings.json').read_bytes())
    for row in before['files']:
        raw = (WORK / 'preimage' / row['path']).read_bytes()
        assert raw == Path(row['source']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        put('preimage/' + row['path'], raw)
    full = ''.join(''.join(difflib.unified_diff(
        files.get('preimage/' + name, b'').decode().splitlines(True),
        files['candidate/' + name].decode().splitlines(True),
        fromfile='a/' + name, tofile='b/' + name)) for name in sorted(pins))
    assert full.encode() == (WORK / 'production-wip02.diff').read_bytes()
    put('production.diff', full)
    put('reviewed-wip01-to-source01.diff', (WORK / 'wip01-to-wip02.diff').read_bytes())
    put('preimage-bindings.json', (WORK / 'preimage-bindings.json').read_bytes())
    put('controls/init_log_controls.c', (WORK / 'controls/init_log_controls.c').read_bytes())
    control = json.loads((WORK / 'local-control02/result.json').read_bytes())
    assert control['success'] is True and len(control['commands']) == 3
    for path, expected in control['source_pins'].items():
        raw = files[path]
        assert len(raw) == expected['bytes'] and sha(raw) == expected['sha256']
    for name in ['result.json', 'syntax.stdout', 'syntax.stderr', 'compile.stdout', 'compile.stderr', 'control.stdout', 'control.stderr']:
        put('local-control02/' + name, (WORK / 'local-control02' / name).read_bytes())
    for row in control['commands']:
        assert row['joined'] and row['returncode'] == 0
        for stream in ('stdout', 'stderr'):
            body = files['local-control02/' + row['label'] + '.' + stream]
            assert len(body) == row[stream]['bytes'] and sha(body) == row[stream]['sha256']
    actual = ROOT / 'root-recovery-20261104-02/evidence/owner15-init-elf-logger-read01/stdout.log'
    raw = actual.read_bytes()
    assert len(raw) == 2104 and sha(raw) == '3806692c551b4039f28985bc4becb5eb78caa8e52e066c3eaf4a176834bb5ad6'
    observed = json.loads(raw)
    assert observed['collection_complete'] and observed['held_fds_closed'] and observed['error'] is None
    put('evidence/exact-init-dynamic-metadata.json', raw)
    host = ROOT / 'root-recovery-20261104-02/evidence/owner15-compile01/compile-result.json'
    host_raw = host.read_bytes()
    assert len(host_raw) == 39999 and sha(host_raw) == '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'
    host_inputs = json.loads(host_raw)['inputs_after']
    assert host_inputs == json.loads(host_raw)['inputs_before'] and len(host_inputs) == 32
    for row in before['files']:
        if row['path'].startswith('runtime/'):
            assert host_inputs[row['path']] == {'bytes': row['bytes'], 'sha256': row['sha256']}
    put('evidence/prior-host-inputs.json', pretty({'receipt_path': str(host), 'bytes': len(host_raw), 'sha256': sha(host_raw), 'inputs': host_inputs}))
    put('validation.json', pretty({'schema': 1,
        'production_files': pins, 'preimages': 7, 'new_Rust_module': 'runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs',
        'old_actual_host_input_count': 32, 'new_expected_host_input_count': 33,
        'actual_local_C_controls': 9, 'actual_local_C_assertions': 187,
        'real_owned_memfd_and_child_exec': True, 'KernelLogger_control_is_explicit_fixture_seam': True,
        'Rust_tests_added_not_executed': 8, 'Rust_compiled': False, 'Android_compiled_or_executed': False,
        'ABI3_wire_bytes_and_original_identity_retirement_gates_changed': False,
        'full_prefix_capacity_bytes': 262144, 'maximum_captured_hex_bytes': 524288,
        'actual_current_init_dynamic_import_only': True, 'actual_definition_library_or_call_ABI_qualified': False,
        'actual_Runtime_marker_required_before_broker': True, 'runtime_execution_ready': False,
        'runtime_consumer_update_required': 'New Owner16 only: 256KiB control response is too small; full hex schema and bounded actor aggregate must be updated and tested before runtime.'}))
    put('README.md', '''# Owner16 paired init diagnostic source

This immutable successor binds seven actual preimages, adds one Rust module,
and leaves the ABI3 five-frame protocol and original process, namespace,
cgroup, authority, Main and retirement predicates intact. It does not modify
the installed Main engine or run an Owner.

The Owner allocates one generation-private 256 KiB anonymous memfd with fixed
grow/shrink/seal bounds. Its independent write-only, nonblocking description
has no reader dependency. The paired constructor receives only FD 202, makes
it CLOEXEC, temporarily supplies ANDROID_FILE__dev_kmsg, and invokes the exact
observed C++ KernelLogger import. It then removes the environment keys and
requires another actual logger-written marker through the cached route.
dladdr must resolve that exact function in an absolute libbase.so object;
the path is recorded by the same logger but does not certify library bytes.
No fallback to a different logger, library scan, global kmsg read, shell,
service restart or identity-gate relaxation exists.

The host admits the logging channel only after the existing live HELLO proof
and both exact nonce markers, before starting the broker. Owner and Session
share one capture object so later attach or worker-start failures cannot drop
the only sink. A single final capture retains at most the observed prefix,
hashes and hex encodes it, and explicitly closes its two FDs. Saturation,
unproven retirement, capture errors and close errors remain explicit. This
is not a complete-stream promise or proof of each pre-exec fork writer's PID.
The diagnostic never changes the lifecycle's first failure or authority.

Local C syntax and nine owned memfd/environment/fd/exec controls passed 187
assertions. Their KernelLogger call is an explicit fixture seam. Eight new
Rust tests are source only until the matching host build and ordinary run;
they include shared ownership failure seams, poisoning, fixed-capacity data,
exec closure, and full 512 KiB hex audit roundtrip without erasing failures.
No local Rust toolchain is available. Android and full Owner are unrun.

The exact current init ELF import was actually read and pinned. Its defining
library build and call ABI remain conditional until a matching runtime sees
the real two-marker prefix. The new Android compile must bind dlfcn.h/libdl
as additional real inputs, keep --no-undefined, and retain the old closure.
The host compile can proceed independently from the actual32-input build15.

Before runtime, its dedicated actor/control/result consumer must accommodate
the explicit maximum prefix (512 KiB hex) without changing generic defaults
or truncating data into success. No executable Owner16 runtime is supplied.
The original Owner15 failure and missing reboot-reason observation remain.
''')
    put('freeze_source.py', Path(__file__).read_bytes())
    put('SOURCE_PINS.json', pretty({'schema': 1, 'kind': 'OWNER16_PAIRED_INIT_LOG_SOURCE_ONLY',
        'files': {path: {'bytes': len(body), 'sha256': sha(body)} for path, body in sorted(files.items())}}))
    OUT.mkdir()
    for path, raw in files.items():
        target = OUT / path; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write(raw)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['SOURCE_PINS.json']),
        'production_diff_bytes': len(files['production.diff']), 'production_diff_sha256': sha(files['production.diff'])}))

if __name__ == '__main__': main()
