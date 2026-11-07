"""Create-only source snapshot. No Rust build, process runtime or network."""
import difflib
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK.parent / 'pinned-io-cause-source-freeze-12'
NAMES = ['runtime/droidloom-pressure-relay/src/lib.rs',
         'runtime/droidloom-pressure-relay/src/lifecycle_relay.rs']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


assert not OUT.exists(), 'freeze is immutable and create-only'
files = {}
actual_raw = (WORK / 'evidence/actual-producer11-compile.json').read_bytes()
assert len(actual_raw) == 39822 and sha(actual_raw) == 'a120890b2edeb1bf1adbe150f064987c55661420ac4021dc4d7ac9b023ad6ca6'
actual = json.loads(actual_raw)
assert actual['inputs_before'] == actual['inputs_after'] and len(actual['inputs_after']) == 32
diffs = []
pins = []
for name in NAMES:
    old = (WORK / 'preimage' / name).read_bytes()
    new = (WORK / 'candidate' / name).read_bytes()
    assert actual['inputs_after'][name] == {'bytes': len(old), 'sha256': sha(old)}
    old.decode('utf-8'); new.decode('utf-8')
    files['preimage/' + name] = old
    files['candidate/' + name] = new
    diffs.append(''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                           fromfile='producer11/' + name, tofile='producer12/' + name)))
    pins.append({'path': name, 'preimage': {'bytes': len(old), 'sha256': sha(old)},
                 'candidate': {'bytes': len(new), 'sha256': sha(new)}})
files['source.diff'] = ''.join(diffs).encode()
files['freeze12.py'] = Path(__file__).read_bytes()
files['evidence/actual-producer11-compile.json'] = actual_raw
for name in ('actual-owner11-failed.json', 'actual-owner11-daemon.stderr'):
    files['evidence/' + name] = (WORK / 'evidence' / name).read_bytes()
review_root = WORK.parent / 'owner11-retirement-cause-actual-review-01'
for name in ('check_actual_logs11.py', 'report.json'):
    files['evidence/owner11-actual-review/' + name] = (review_root / name).read_bytes()
files['source-review.json'] = pretty({
    'schema': 1, 'revision': 'producer12-pinned-io-cause01',
    'preimage_matches_actual_producer11_compile_inputs': pins,
    'change_scope': ['openat error retains original errno before optional fstat of the held base',
                     'failure-only relative name and exact flags plus optional held base FileId',
                     'typed static caller role around existing host, authority and LMKD admission calls'],
    'unchanged': ['successful openat path', 'socket receive WouldBlock matching', 'all authority predicates',
                  'steady public cgroup projection validation', 'one-shot admission', 'timeouts',
                  'syscall flags and FD ownership', 'retirement state machine and return outcomes'],
    'expected_new_Rust_controls': ['missing_relative_entry_retains_real_errno_name_and_held_base',
        'relative_error_does_not_follow_a_rejected_symlink',
        'exited_owned_child_retains_exact_proc_base_and_role_without_revival'],
    'Rust_compiler_available_locally': False, 'Rust_tests_executed': False,
    'actual_Android_or_Owner_executed': False, 'boot_root_cause_fixed': False,
    'actual_missing_name_or_base_still_unobserved': True,
    'real_owned_files_socket_or_child_tests_are_matching_build_requirements': True,
    'Hepta_calls': 0, 'source_freeze_only': True,
})
files['README.md'] = b'''# Producer12 retained pinned-I/O failure provenance

This isolated source freeze starts from the exact two producer11 Rust inputs
recorded by the successful actual compile. Owner11 remains an actual failed
first-ACTIVE attempt. Its original retirement is incomplete; the later exact
outer unit cleanup is separately complete.

The actual relay reason is open relative pinned directory / ENOENT. That label
is from open_at, not the separate openat2 public-projection lookup. No path,
process role or ordering with process death was retained in the original
message. This revision preserves the name, unchanged flags, optional identity
of the held base and original errno on an open failure, then adds static role
context at existing validated call boundaries. It does not ignore ENOENT,
retry a PID/path, change credentials, replace a namespace, or permit a grant.

Three Rust tests use real private files, a rejected symlink and an exact owned
child/pidfd/proc FD, respectively. They are source-only here; Rust is unavailable
locally. They must be compiled and executed in a matching candidate. The child
test does not authenticate a peer or claim lifecycle-origin qualification.

The independently identified retirement send-before-drain issue is excluded
from this immutable diagnostic snapshot. A separately reviewable combined
candidate may add that repair, keeping all nonce, scope, AUDIT, flag and exact
broker-exit checks. No device work, Main change or production qualification is
performed by this snapshot.
'''
for body in files.values():
    body.decode('utf-8')
members = [{'path': name, 'bytes': len(body), 'sha256': sha(body)} for name, body in sorted(files.items())]
files['manifest.json'] = pretty({'schema': 1, 'kind': 'producer12_pinned_io_cause_source_freeze', 'files': members})
OUT.mkdir()
for name, body in files.items():
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body)
print(json.dumps({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
                  'diff_bytes': len(files['source.diff']), 'diff_sha256': sha(files['source.diff']), 'pins': pins}))
