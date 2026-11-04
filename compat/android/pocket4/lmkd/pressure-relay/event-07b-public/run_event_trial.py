#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Single separately coordinated owned-host PSI trial. Never automatically retry."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SOURCE = Path(os.environ.get('P4_EVENT_SOURCE', '/srv/pocket4-relay-source'))
OUTPUT = Path(os.environ.get('P4_EVENT_OUTPUT', '/srv/pocket4-relay-output/unqualified'))
# This historical one-shot key has already been used; never replay it.
ORIGINAL_EXECUTED_KEY = 'p4-r10-relay-event07-pressure-01'
IDEMPOTENCY_KEY = os.environ.get('P4_EVENT_IDEMPOTENCY_KEY', '')
PINS = {
    "Cargo.toml": "a4f31db859cf0606cf174779dfa520ff3ee3efdff229ecb7503f1f7e13756cd6",
    "Cargo.lock": "94876b46af35019567dfce0ea2002a6a5c6d522280d4d8da3b412dc34c5a2f03",
    "src/lib.rs": "063a54453e2062b2094ccf702d26a072e8e2d4518c00144cee90992e39ee97d9",
    "src/psi.rs": "36d5a80c13ef982e3fb0e9cc8a7a055a193ba18b15531a93fd662b9c73d92e4b",
    "src/bin/owned_ipc_controls.rs": "33ba770340d4db205ff52a46c31aacb0e1ee4f7512f1992af8b7e16b73fcd9a0",
    "src/event_fixture.rs": "429361324cbe45b27d897f9ae8e291b7197ae55046de7be131668e86959d4c70",
    "event_guard.py": "df7fa6cee3c39c954fd97bb41c69f42ad1720e453d5f6d25926b8c631c997221",
    "owned_event_fixture.py": "8c15d2ccca80f3f919997717bb937419b151514114efac7da186a9d5ced26cdf",
    "test_event_guard.py": "966bf1e553bcc08905878bbea3608831d22d4df8ac4e4492d0c81657a0d3f328",
    "test_event_orchestrator.py": "53ea08bfe6f8997ec7db1588e31cd8780e50571652628fb3f4e97d55edb6a18d",
    "prior_run_fixture.py": "62243c0841577eaa1cca97deeffd7fcc0ced3d244a0fb83242bb504bd8ba92b8",
    "negative-controls/old_driver.py": "516b55426cb1c708e545bc3fa4a1947a0ca5a22ae89d51a9c5c4eca51c31868e",
    "target/debug/owned-ipc-controls": "ddb2d6319cf6467c44df0ac66995ef22137ccc340d263e22c67049f193435b1d"
}

def save(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())

def main():
    # Publication is not a grant to execute this adapted, unqualified source.
    # Fresh review, actual missing authorities and a separately built/pinned
    # binary are required; the original binary pin below is historical only.
    if not IDEMPOTENCY_KEY or IDEMPOTENCY_KEY == ORIGINAL_EXECUTED_KEY:
        raise RuntimeError('FRESH_REVIEWED_IDEMPOTENCY_KEY_REQUIRED_NO_REPLAY')
    if not SOURCE.is_absolute() or not OUTPUT.is_absolute():
        raise RuntimeError('ABSOLUTE_REVIEWED_PATHS_REQUIRED')
    membership = Path('/proc/self/cgroup').read_text()
    cg = Path('/sys/fs/cgroup') / membership.strip().split('::', 1)[1].lstrip('/')
    assert cg.name.startswith('hepta-runtime-job-')
    limits = {n: (cg / n).read_text().strip() for n in ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')}
    quota, period = map(int, limits['cpu.max'].split())
    assert limits['memory.max'] != 'max' and 0 < int(limits['memory.max']) <= 536870912 and 0 < quota <= period
    original_children = sorted(p.name for p in cg.iterdir() if p.is_dir())
    original_controllers = (cg / 'cgroup.subtree_control').read_text()
    assert not original_controllers.strip()
    OUTPUT.mkdir(mode=0o700)
    result = {'scope': 'one owned host PSI event only; no Android, Main mutation or LMKD killgate',
              'idempotency_key': IDEMPOTENCY_KEY, 'automatic_retry': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'limits_before': limits, 'source_pins': PINS, 'root_driver_dispatched': False}
    rc = 2
    try:
        for relative, expected in PINS.items():
            actual = hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError('INPUT_PIN_CHANGED:' + relative + ':' + actual)
        save(OUTPUT / 'intent.json', result)
        argv = ['/usr/bin/sudo', '-n', '/usr/bin/env', 'PYTHONDONTWRITEBYTECODE=1',
                'P4_EXPECTED_JOB_CGROUP=' + membership, '/usr/bin/python3', '-B',
                str(SOURCE / 'owned_event_fixture.py'),
                str(SOURCE / 'target/debug/owned-ipc-controls'), str(OUTPUT / 'fixture')]
        result['root_driver_dispatched'] = True
        run = subprocess.run(argv, capture_output=True, text=True, timeout=35)
        result.update(rc=run.returncode, stdout=run.stdout, stderr=run.stderr, timed_out=False)
        rc = run.returncode
    except subprocess.TimeoutExpired as error:
        result.update(timed_out=True, owned_cleanup_unknown=True,
                      stdout=error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else error.stdout,
                      stderr=error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr)
    except Exception as error:
        result['failure'] = repr(error)
    finally:
        result['runner_membership_restored'] = Path('/proc/self/cgroup').read_text() == membership
        result['limits_after'] = {n: (cg / n).read_text().strip() for n in limits}
        result['parent_controllers_after'] = (cg / 'cgroup.subtree_control').read_text()
        result['owned_direct_children_after'] = Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().strip()
        result['hierarchy_after'] = sorted(p.name for p in cg.iterdir() if p.is_dir())
        result['runner_scope_restored'] = (result['runner_membership_restored']
            and result['limits_after'] == limits and result['parent_controllers_after'] == original_controllers
            and result['hierarchy_after'] == original_children and result['owned_direct_children_after'] == '')
        if not result['runner_scope_restored']:
            rc = 2
        result['rc'] = rc
        result['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result['result'] = 'PASS' if rc == 0 and not result.get('timed_out') else 'FAIL'
        save(OUTPUT / 'result.json', result)
        print(json.dumps(result, indent=2), flush=True)
    return rc

if __name__ == '__main__':
    sys.exit(main())
