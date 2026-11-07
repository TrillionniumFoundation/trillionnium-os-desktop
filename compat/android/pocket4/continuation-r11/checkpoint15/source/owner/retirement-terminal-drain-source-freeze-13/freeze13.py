"""Freeze separately reviewable diagnostics12 plus retirement13; never execute Rust."""
import difflib
import hashlib
import json
from pathlib import Path
import re

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent
DIAG = ROOT / 'pinned-io-cause-source-freeze-12'
OUT = ROOT / 'retirement-terminal-drain-source-freeze-13'
NAMES = ['runtime/droidloom-pressure-relay/src/lib.rs',
         'runtime/droidloom-pressure-relay/src/lifecycle_relay.rs',
         'runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def function(text, marker):
    assert text.count(marker) == 1, marker
    start = text.index(marker)
    opening = text.index('{', start)
    level = 1
    for index in range(opening + 1, len(text)):
        level += (text[index] == '{') - (text[index] == '}')
        if level == 0:
            return text[start:index + 1]
    raise AssertionError(marker)


assert not OUT.exists(), 'immutable create-only snapshot'
files = {}
diag_manifest = (DIAG / 'manifest.json').read_bytes()
assert sha(diag_manifest) == '963f7055854ba25ebc4fb9a9cd2dbf1e59d5a4200363d2fa1222003c341b6bfb'
for item in json.loads(diag_manifest)['files']:
    data = (DIAG / item['path']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256']
actual_raw = (DIAG / 'evidence/actual-producer11-compile.json').read_bytes()
actual = json.loads(actual_raw)
assert actual['inputs_before'] == actual['inputs_after'] and len(actual['inputs_after']) == 32
pins, diffs = [], []
for name in NAMES:
    old = (WORK / 'preimage' / name).read_bytes()
    new = (WORK / 'candidate' / name).read_bytes()
    assert {'bytes': len(old), 'sha256': sha(old)} == actual['inputs_after'][name]
    if not name.endswith('lifecycle_bootstrap.rs'):
        assert old == (DIAG / 'preimage' / name).read_bytes()
        assert new == (DIAG / 'candidate' / name).read_bytes()
    files['preimage/' + name] = old
    files['candidate/' + name] = new
    diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                      fromfile='producer11/' + name, tofile='producer13/' + name))
    diffs.append(diff)
    if name.endswith('lifecycle_bootstrap.rs'):
        files['retirement-only.diff'] = diff.encode()
    pins.append({'path': name, 'preimage': {'bytes': len(old), 'sha256': sha(old)},
                 'candidate': {'bytes': len(new), 'sha256': sha(new)}})
files['source.diff'] = ''.join(diffs).encode()
files['diagnostics12.diff'] = (DIAG / 'source.diff').read_bytes()
files['lineage/diagnostics12-manifest.json'] = diag_manifest
files['evidence/actual-producer11-compile.json'] = actual_raw
old = files['preimage/' + NAMES[2]].decode()
new = files['candidate/' + NAMES[2]].decode()
unchanged = []
for marker in ('    fn accept_status(', '    pub fn receive_progress(', 'fn receive_progress_frame(',
               'fn receive_packet(', 'fn send_packet(', 'fn valid_retirement(',
               '    pub fn initialize(', '    pub fn abort_before_initialize(',
               'pub fn run_inherited_lifecycle('):
    before = function(old, marker)
    assert before == function(new, marker), marker
    unchanged.append({'function': marker.strip().split('(')[0], 'text_sha256': sha(before.encode())})
assert function(old, '    fn spawn_with_layout(').replace(
    'retirement_seen: false, joined: false, retired })',
    'retirement_seen: false,\n            retirement_poisoned: false, joined: false, retired })') == function(new, '    fn spawn_with_layout(')
assert function(old, '    pub fn ready_for_init_commit(').replace(
    'self.retirement_requested || self.retirement_seen ||',
    'self.retirement_requested || self.retirement_seen || self.retirement_poisoned ||') == function(new, '    pub fn ready_for_init_commit(')
fixture_raw = (WORK / 'owned-peer-fixture-result.json').read_bytes()
fixture = json.loads(fixture_raw)
prefix = '    const RETIREMENT_PEER: &str = r#"'
script = new.split(prefix, 1)[1].split('"#;', 1)[0]
assert sha(script.encode()) == fixture['script_sha256']
assert len(fixture['actual_cases']) == 5
assert all(case['reaped'] and not case['forced_kill'] and not case['Rust_retire_called'] for case in fixture['actual_cases'])
for name in ('check_owned_peer_fixture.py', 'owned-peer-fixture-result.json'):
    files['controls/' + name] = (WORK / name).read_bytes()
for directory in ('local-fixture-attempt01', 'local-fixture-attempt02', 'local-fixture-attempt03'):
    for path in sorted((WORK / directory).iterdir()):
        assert path.is_file()
        files['evidence/' + directory + '/' + path.name] = path.read_bytes()
old_names, new_names = set(), set()
for name in NAMES:
    old_names.update(re.findall(r'#\[test\]\s*fn\s+(\w+)', files['preimage/' + name].decode()))
    new_names.update(re.findall(r'#\[test\]\s*fn\s+(\w+)', files['candidate/' + name].decode()))
assert old_names <= new_names and len(new_names - old_names) == 7
files['source-review.json'] = pretty({
    'schema': 1, 'revision': 'producer13-retirement-terminal-drain01',
    'preimage_actual_producer11_receipt_sha256': sha(actual_raw),
    'diagnostics12_manifest_sha256': sha(diag_manifest), 'exact_three_inputs': pins,
    'unchanged_protocol_and_authority_function_text': unchanged,
    'only_spawn_change_is_new_poison_field_false': True,
    'only_commit_change_is_reject_poisoned_retirement': True,
    'changes': ['drain existing actual input before a retirement command to an already closed peer',
                'close/send race can complete only through existing full AUDIT/status receiver and exact child exit',
                'otherwise retain the original request error; never retry that request',
                'one original deadline bounds draining, sending and exact child wait',
                'first retirement protocol/I/O error permanently poisons later retire and COMMIT',
                'Ok(false) waiting for exact child remains resumable and conveys no receipt'],
    'new_Rust_tests': sorted(new_names - old_names), 'expected_relay_test_count': 37,
    'expected_supervisor_test_count': 122,
    'Rust_compiled_locally': False, 'Rust_tests_executed': False,
    'exact_embedded_test_peer_script_actual_local_mechanics': {
        'cases': 5, 'report_sha256': sha(fixture_raw), 'script_sha256': fixture['script_sha256'],
        'does_not_execute_Rust_retire_or_bootstrap': True},
    'test_fixture_boundary': 'cfg(test) seeds a post-READY scope and real handles; no leader-origin/bootstrap/PSI/Android qualification',
    'old_Owner11_failed_retirement_not_reclassified': True,
    'boot_ENOENT_relative_name_or_role_still_unresolved': True,
    'Hepta_calls': 0, 'actual_Owner_or_Android_executed': False,
})
files['README.md'] = b'''# Producer13: retained I/O provenance and exact terminal draining

The three preimages are exact producer11 matching-build inputs. The two
diagnostic files are byte-identical to immutable diagnostics12. Their separate
patch preserves the original openat errno, failed relative name/flags, held base
identity and caller role. It does not repair or reinterpret Owner11's unknown
boot ENOENT cause.

The separately reviewable retirement-only patch fixes a concrete public-retire
ordering defect: a broker may already have sent AUDIT and RETIRED and closed.
Sending RETIRE before reading these packets rejects that valid cleanup proof.
The new code drains actual input first through the unchanged receiver. A close
racing a send can only be discharged by the same full AUDIT/nonce/generation/
endpoint/cgroup/budget/flags checks plus the exact owned child's matching exit.
Bare HUP, an exited child or a failed command supplies no retirement evidence.
An unresolved send error remains the primary error. No command is replayed.

All work uses the original bounded deadline. A protocol/I/O retirement failure
sets a permanent poison bit before returning, so a second call cannot consume a
remaining valid tail and turn the original failure into a certificate. COMMIT
also rejects that bit. Ok(false) is only a still-pending wait and can continue.
The old slot is marked retired only where the original exact-child exit gate
already did so. Process-owner, init, cgroup cleanup and new-generation admission
remain separate requirements, with no altered authority checks or fallback.

Seven new Rust tests are expected (three diagnostic, four retirement). The four
retirement tests call the real public LifecycleBroker::retire against private
seqpacket sockets and exact owned Python children. Rust encodes the packets;
the fixed Python script only sends them and optionally waits for an exact
request. Test-only post-READY scope/handle setup does not claim public bootstrap,
leader-origin, native enrollment or Android qualification. Cases include healthy
and faulted already-closed peers, a live peer receiving one command, ten invalid
or missing-proof cases rejected again on a second call, and valid terminal data
while the child is still alive. The old send-first failure is explicitly retained
as a real transport control before successful draining in the positive test.

Local Python mechanics ran five exact embedded-script cases with owned sockets,
sealed input memfds, exact child waits and EOF checks. They do not execute Rust
or certify the production method. Local attempt01 lacked fcntl seal constants
in the default interpreter; attempt02 exposed the test script's inherited
nonblocking socket wait. Both originals remain. The script now sets bounded
timeouts on its two inherited sockets; attempt03 passed under /usr/bin/python3.
The script itself is unchanged by later Rust-only edits, and its hash is checked.

Rust is unavailable locally. Matching compile and the actual 37 relay / 122
supervisor tests, two original public controls (1 pass / 36 filtered), seven IPC,
worker context and ABI3 checks remain required. No device/runtime request is in
this source freeze. Owner11 remains failed with incomplete original retirement
and separately completed outer cleanup. Main, pressure thresholds, RC reload
and all-App production qualification are unchanged.
'''
files['freeze13.py'] = Path(__file__).read_bytes()
for body in files.values():
    body.decode('utf-8')
members = [{'path': name, 'bytes': len(body), 'sha256': sha(body)} for name, body in sorted(files.items())]
files['manifest.json'] = pretty({'schema': 1, 'kind': 'producer13_retirement_terminal_drain_source_freeze', 'files': members})
OUT.mkdir()
for name, body in files.items():
    path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body)
print(json.dumps({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
                  'full_diff': {'bytes': len(files['source.diff']), 'sha256': sha(files['source.diff'])},
                  'retirement_diff': {'bytes': len(files['retirement-only.diff']), 'sha256': sha(files['retirement-only.diff'])},
                  'pins': pins}))
