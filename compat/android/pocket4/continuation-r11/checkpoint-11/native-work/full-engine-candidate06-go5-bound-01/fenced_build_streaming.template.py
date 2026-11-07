#!/usr/bin/env python3
"""UID1000 outer controller with fixed read-only pre/post Main observations."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

CONTROLLER_SHA = 'b42ee9229dfac7b62bb04472e39568867fc53d695389b2214c8bbfd9e0f83619'
SNAPSHOT_SHA = 'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb'
PREPARATION_SHA = 'ACTUAL_GO5_STREAMING_PREPARATION_SHA_REQUIRED'
ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined06-go5-streaming-01')
FENCE_ROOT = ROOT / 'build-fences-01'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(FENCE_ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def capture(label, source, source_sha):
    wrapper = ('import sys,hashlib;raw=sys.stdin.buffer.read();'
               'assert hashlib.sha256(raw).hexdigest()==' + repr(source_sha) + ';'
               "scope={'__name__':'__main__','__file__':'<pinned-readonly-main-snapshot>'};"
               "exec(compile(raw,'main_snapshot.py','exec'),scope,scope)")
    try:
        result = subprocess.run(['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', '-c', wrapper],
                                input=source, capture_output=True, timeout=25)
        save(label + '.stdout.json', result.stdout)
        save(label + '.stderr.txt', result.stderr)
        require(len(result.stdout) <= 65536 and len(result.stderr) <= 65536, 'snapshot output too large')
        observation = json.loads(result.stdout)
        require(result.returncode == 0 and not result.stderr and observation.get('ok') is True,
                'Main snapshot failed: ' + label)
        return observation
    except subprocess.TimeoutExpired as error:
        save(label + '.timeout.stdout', error.stdout or b'')
        save(label + '.timeout.stderr', error.stderr or b'')
        raise RuntimeError('read-only Main helper timed out: ' + label) from error


def compare(before, after):
    identities = ('activation_sha256', 'epoch_source_sha256', 'framework_epoch_sha256',
                  'cell_sha256', 'host_processes', 'limits', 'main_cgroup', 'main_cgroup_identity')
    changes = [name for name in identities if before[name] != after[name]]
    require(set(before['memory_events']) == set(after['memory_events']), 'Main memory counter schema changed')
    delta = {name: after['memory_events'][name] - value for name, value in before['memory_events'].items()}
    require(all(value >= 0 for value in delta.values()), 'Main memory counters regressed')
    oom_zero = all(delta[name] == 0 for name in ('oom', 'oom_kill', 'oom_group_kill'))
    return {'main_fence_pass': not changes and oom_zero, 'identity_or_limit_changes': changes,
            'main_memory_event_deltas': delta, 'main_oom_delta_zero': oom_zero,
            'main_current_resource_deltas': {name: after['current_resources'][name] - value
                                            for name, value in before['current_resources'].items()},
            'pressure_counter_increases_observed': {name: value for name, value in delta.items()
                                                  if value and name not in ('oom', 'oom_kill', 'oom_group_kill')},
            'unobserved_transient_effects_excluded': False,
            'causal_attribution_of_counter_changes': False,
            'scope': 'Only the pinned pre/post invariants and OOM deltas are gated; full interval absence of interference is not claimed.'}


def run(packet):
    require(len(PREPARATION_SHA) == 64 and all(c in "0123456789abcdef" for c in PREPARATION_SHA),
            "a new actual streaming preparation receipt is required")
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'outer build controller must remain UID1000')
    os.umask(0o077)
    source = packet['controller_source'].encode()
    snapshot = packet['snapshot_source'].encode()
    require(sha(source) == CONTROLLER_SHA and sha(snapshot) == SNAPSHOT_SHA == packet['snapshot_sha256'], 'embedded source changed')
    scope = {'__name__': 'frozen_combined_build', '__file__': '<frozen-combined-build>',
             'VERIFIED_CONTROLLER_SHA256': CONTROLLER_SHA}
    exec(compile(source, 'frozen_combined_build.py', 'exec'), scope, scope)
    scope['no_alias'](ROOT)
    require(sha((ROOT / 'preparation.json').read_bytes()) == PREPARATION_SHA, 'actual preparation changed')
    require(not FENCE_ROOT.exists() and not FENCE_ROOT.is_symlink(), 'fence root already exists; reconcile exact job')
    FENCE_ROOT.mkdir(mode=0o700)
    save('claim.json', {'schema': 1, 'state': 'READONLY_MAIN_FENCE_BEFORE_FULL_BUILD',
                       'controller_sha256': CONTROLLER_SHA, 'preparation_sha256': PREPARATION_SHA,
                       'snapshot_sha256': packet['snapshot_sha256'], 'uid': os.getuid(),
                       'automatic_retry': False, 'Main_actions': 0})
    before = after = assessment = None
    inner_code = None
    failure = None
    attempted = False
    started = time.monotonic()
    def interrupted(signum, frame):
        raise InterruptedError('fenced build received signal ' + str(signum))
    old_term = signal.signal(signal.SIGTERM, interrupted)
    old_int = signal.signal(signal.SIGINT, interrupted)
    try:
        before = capture('before', snapshot, packet['snapshot_sha256'])
        save('before.json', before)
        attempted = True
        inner_code = scope['main'](['--build', '--preparation-sha256', PREPARATION_SHA])
        require(inner_code == 0, 'inner full build failed')
    except BaseException as error:
        failure = repr(error)
    finally:
        # The inner controller has already retired its owned build children.
        # These handlers affect only this process and bound the final read to
        # the helper's own 15-second alarm and caller's 25-second wait.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            after = capture('after', snapshot, packet['snapshot_sha256'])
            save('after.json', after)
            if before is not None:
                assessment = compare(before, after)
                if not assessment['main_fence_pass'] and failure is None:
                    failure = 'Main epoch, activation, identities, limits or OOM fence failed'
        except BaseException as error:
            if failure is None:
                failure = repr(error)
            else:
                failure += '; post-fence: ' + repr(error)
        terminal = {'schema': 1, 'state': 'BUILD_AND_OBSERVED_MAIN_FENCES_PASSED' if failure is None else 'FAILED',
                    'error': failure, 'inner_build_called': attempted, 'inner_returncode': inner_code,
                    'seconds': time.monotonic() - started, 'main_fence_assessment': assessment,
                    'before_observed': before is not None, 'after_observed': after is not None,
                    'Main_actions': 0, 'Android_actions': 0, 'main_unchanged_not_inferred_from_actions': True,
                    'installed': False, 'production_ready': False}
        try:
            save('terminal.json', terminal)
            print(json.dumps({'state': terminal['state'], 'error': failure,
                              'inner_returncode': inner_code, 'main_fence_assessment': assessment,
                              'terminal_sha256': sha((FENCE_ROOT / 'terminal.json').read_bytes())}), flush=True)
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
    return 0 if failure is None else 1


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'new_fence_root': str(FENCE_ROOT),
                          'prepared_sha256': PREPARATION_SHA, 'Main_actions': 0,
                          'build_started': False, 'feature_enabled': False}))
    else:
        try:
            raise SystemExit(run(PACKET))
        except Exception as error:
            print(json.dumps({'state': 'FENCE_ADMISSION_FAILED', 'error': repr(error),
                              'Main_actions': 0, 'production_ready': False}), flush=True)
            raise SystemExit(1)
