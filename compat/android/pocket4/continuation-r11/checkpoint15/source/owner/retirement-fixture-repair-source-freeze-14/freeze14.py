"""Freeze only two test-fixture corrections and their original failing evidence."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'retirement-fixture-repair-work-14'
OUT = ROOT / 'retirement-fixture-repair-source-freeze-14'
PRIOR = ROOT / 'retirement-terminal-drain-source-freeze-13'
EVIDENCE = ROOT.parent / 'root-recovery-20261104-02/evidence'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def main():
    assert not OUT.exists(), 'create-only source freeze'
    files = {}

    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode('utf-8')
        assert name not in files
        files[name] = data

    def exact(path, size, digest):
        raw = path.read_bytes()
        assert len(raw) == size and sha(raw) == digest, str(path)
        return raw

    compiled_raw = exact(EVIDENCE / 'owner13-compile01/compile-result.json', 39831,
        '9a2cf0087ff99b6834fc2b3a963e03629a14acc21af1a8d67f2b5081bbb22e8e')
    failed_raw = exact(EVIDENCE / 'owner13-ordinary01/run-result.json', 20203,
        'cc26182f01c5241d6766dfb356263fa6efc7b6499a05684e0447895935ad523e')
    stdout_raw = exact(EVIDENCE / 'owner13-ordinary01/command-02.stdout', 4483,
        '8a8537257b6bea7e1ca04031cf7d5f40143812cd71e6f7d1fdfd5082e911d528')
    compiled, failed = json.loads(compiled_raw), json.loads(failed_raw)
    assert compiled['success'] is True and compiled['compile_only'] is True
    assert compiled['inputs_before'] == compiled['inputs_after'] and len(compiled['inputs_before']) == 32
    assert failed['success'] is False and failed['external_compile_sha256'] == sha(compiled_raw)
    assert len(failed['commands']) == 3
    assert [c['returncode'] for c in failed['commands']] == [0, 0, 101]
    assert all(c['timed_out'] is False for c in failed['commands'])
    assert failed['commands'][2]['stdout_pin']['bytes'] == len(stdout_raw)
    assert failed['commands'][2]['stdout_pin']['sha256'] == sha(stdout_raw)
    assert 'test result: FAILED. 35 passed; 2 failed;' in stdout_raw.decode()
    assert 'rust_tests_passed' not in failed and 'ordinary_ipc_passed' not in failed
    put('evidence/actual-producer13-compile.json', compiled_raw)
    put('evidence/actual-producer13-ordinary-failed.json', failed_raw)
    put('evidence/actual-producer13-relay-command.stdout', stdout_raw)
    prior_manifest = exact(PRIOR / 'manifest.json', 4398,
        'fab7226afa93d372a7ba7d025cd704ae4aba878f9fa5336490af72eca98e6593')
    put('lineage/producer13-source-manifest.json', prior_manifest)
    diffs, reviewed = [], []
    names = ['runtime/droidloom-pressure-relay/src/lib.rs',
             'runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs']
    for name in names:
        before = (WORK / 'preimage' / name).read_bytes()
        after = (WORK / 'candidate' / name).read_bytes()
        assert before == (PRIOR / 'candidate' / name).read_bytes()
        assert {'bytes': len(before), 'sha256': sha(before)} == compiled['inputs_before'][name]
        marker = b'#[cfg(test)]\nmod tests {'
        assert before.count(marker) == after.count(marker) == 1
        before_prod, after_prod = before.split(marker, 1)[0], after.split(marker, 1)[0]
        assert before_prod == after_prod
        put('preimage/' + name, before)
        put('candidate/' + name, after)
        diffs.append(''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
            fromfile='producer13/' + name, tofile='producer14/' + name)))
        reviewed.append({'path': name, 'preimage_bytes': len(before), 'preimage_sha256': sha(before),
            'candidate_bytes': len(after), 'candidate_sha256': sha(after),
            'production_prefix_bytes': len(before_prod), 'production_prefix_sha256': sha(before_prod),
            'production_prefix_exactly_unchanged': True})
    diff = ''.join(diffs).encode()
    assert diff == (WORK / 'source.diff').read_bytes()
    assert len(diff) == 2726 and sha(diff) == '2af0e86d25b4288c5426037d532d95cdda99076afeeefe40f62d45356df21f43'
    put('source.diff', diff)
    audit_name = 'runtime/droidloom-pressure-relay/src/pressure_audit.rs'
    audit = (ROOT / 'producer07-audit-freeze-02/source' / audit_name).read_bytes()
    assert {'bytes': len(audit), 'sha256': sha(audit)} == compiled['inputs_before'][audit_name]
    assert b'self.stop_reason > 6' in audit
    assert b'events.overflow || self.faulted' in audit and b'!self.incomplete' in audit
    put('reference/' + audit_name, audit)
    relay_name = 'runtime/droidloom-pressure-relay/src/lifecycle_relay.rs'
    relay = (PRIOR / 'candidate' / relay_name).read_bytes()
    assert {'bytes': len(relay), 'sha256': sha(relay)} == compiled['inputs_before'][relay_name]
    put('reference/' + relay_name, relay)
    put('source-review.json', pretty({
        'schema': 1, 'scope': 'fixture-only repair after actual producer13 ordinary failure',
        'actual_prior_compile_passed': True, 'actual_prior_ordinary_passed': False,
        'actual_prior_relay_tests': {'passed': 35, 'failed': 2, 'total': 37},
        'actual_prior_original_targeted_tests': [x for x in failed['targeted_public_retirement_controls']],
        'actual_prior_supervisor_and_ipc_executed': False,
        'actual_prior_failure': failed['error'],
        'production_changes': [], 'test_only_changes': reviewed,
        'unchanged_pressure_audit_sha256': sha(audit),
        'unchanged_lifecycle_relay_sha256': sha(relay),
        'faulted_fixture': {
            'exact_cause': 'faulted=true with incomplete=false violates the unchanged codec',
            'stop_reason_zero_is_legal': True,
            'old_invalid_encode_retained_as_negative_assertion': True,
            'new_faulted_fixture_incomplete': True,
            'status_faulted_and_exact_expected_child_exit_unchanged': True},
        'dead_proc_fixture': {
            'actual_prior_kernel_errno': 3, 'old_fixture_assumed_errno': 2,
            'new_expected_errno_from_raw_syscall_on_same_held_procdir': True,
            'raw_name': 'ns/mnt', 'raw_flags': 'O_RDONLY | O_CLOEXEC',
            'vanished_proc_errno_class': ['ENOENT', 'ESRCH'],
            'wrapper_must_preserve_exact_kernel_errno': True,
            'exact_child_exit_and_pidfd_dead_gate_unchanged': True,
            'unexpected_success_fd_closed_before_assertion': True},
        'local_validation': 'bytes, lineage, exact diff and production-prefix equality only',
        'rust_tests_run_here': False, 'revision14_compile_or_ordinary_executed': False,
        'full_owner_or_android_qualified': False,
        'limitations': ['The send-error race branch is not deterministically forced by the existing positive fixture.',
            'Original producer13 failure and Owner11 failure remain unchanged.',
            'Observed zero swap is not a hard swap limit or whole-invocation resource qualification.']
    }))
    put('README.md', '''# Producer14: repair two test-fixture assumptions

The actual producer13 compile succeeded, but its ordinary relay run passed 35
of 37 tests and exited 101. The supervisor library, IPC and ABI commands were
not executed after that failure. The original receipt and full 4,483-byte relay
stdout are retained unchanged here. This package does not reclassify that run.

Both edits are inside `#[cfg(test)] mod tests`. Production code before those
modules, the pressure-audit codec and lifecycle_relay.rs remain byte-identical
to the actual producer13 input. No authority, deadline, pressure threshold,
nonce/scope validation, terminal drain, exact child-exit or poison rule changes.

The faulted terminal fixture previously set `faulted=true` while retaining
`incomplete=false`. The unchanged codec correctly rejects that combination;
`stop_reason=0` is legal and was not the defect. The new test first requires that
old invalid encoding to remain rejected, then sets `incomplete=true` and sends
the same real Rust codec/status through the original owned-child fixture.

The dead-proc fixture assumed ENOENT while Pocket4 returned ESRCH. It now issues
raw SYS_openat with the same held procdir, relative name and O_RDONLY|O_CLOEXEC,
captures that errno before any other operation, requires ENOENT or ESRCH, and
requires the production contextual error to preserve that exact kernel value.
The child must already be exactly reaped and its held pidfd dead. Unexpected
successful raw opens are closed before failing the test.

The expected ordinary suite remains 37 relay and 122 supervisor tests, two
original targeted public retirement tests, seven IPC controls, worker-context
and entry ABI3. No Rust tests or Android runtime were executed while freezing
this source. Matching compile and ordinary execution need a fresh root and
separate actual receipts; no NORMAL13 runtime was prepared or dispatched.
''')
    put('freeze14.py', Path(__file__).read_bytes())
    members = [{'path': name, 'bytes': len(data), 'sha256': sha(data)} for name, data in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'producer14_fixture_only_source_freeze', 'files': members}))
    OUT.mkdir()
    for name, data in files.items():
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
        'source_diff_bytes': len(diff), 'source_diff_sha256': sha(diff)}))


if __name__ == '__main__':
    main()
