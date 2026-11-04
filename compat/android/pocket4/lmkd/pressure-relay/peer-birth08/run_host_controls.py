#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Bounded host-only build and owned peer controls; never starts PSI modes."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def members(cgroup):
    result = {}
    for pid in set((cgroup / 'cgroup.procs').read_text().split()):
        text = Path('/proc', pid, 'stat').read_text()
        assert text[:text.index('(')].strip() == pid
        result[pid] = int(text[text.rindex(')') + 1:].split()[19])
    return result


def main():
    base = Path(sys.argv[1])
    assert base.is_absolute() and not base.exists(), 'refusing overwrite or relative output'
    cargo = os.environ['P4_CARGO']
    assert Path(cargo).is_absolute()
    files = json.load(sys.stdin)
    membership = Path('/proc/self/cgroup').read_text()
    group = Path('/sys/fs/cgroup') / membership.strip().split('::', 1)[1].lstrip('/')
    assert group.name.startswith('hepta-runtime-job-'), 'not a uniquely bounded runtime job'
    names = ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')
    limits = {n: (group / n).read_text().strip() for n in names}
    quota, period = map(int, limits['cpu.max'].split())
    assert limits['memory.max'] != 'max' and 0 < int(limits['memory.max']) <= 536870912 and 0 < quota <= period
    original_members = members(group)
    original_children = sorted(p.name for p in group.iterdir() if p.is_dir())
    original_controllers = (group / 'cgroup.subtree_control').read_text()
    original_events = (group / 'memory.events.local').read_text()
    namespace = os.stat('/proc/self/ns/mnt')
    projection = os.stat('/sys/fs/cgroup')
    original_mount_hash = digest(Path('/proc/self/mountinfo').read_bytes())
    base.mkdir(mode=0o700, parents=True)
    for relative, item in files.items():
        path = Path(relative)
        assert not path.is_absolute() and '..' not in path.parts
        raw = item['text'].encode()
        assert digest(raw) == item['sha256']
        destination = base / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
    env = dict(os.environ)
    env.update(RUSTFLAGS='-Ccodegen-units=1 -Dwarnings', PYTHONDONTWRITEBYTECODE='1')
    env['PATH'] = str(Path(cargo).parent) + ':' + env.get('PATH', '')
    result = {
        'scope': 'host owned peer process birth authentication only; no PSI registration, pressure, cgroup mutation, Android or Main',
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'limits_before': limits, 'source_sha256': {n: item['sha256'] for n, item in files.items()},
        'negative_library_expected_sha256': '063a54453e2062b2094ccf702d26a072e8e2d4518c00144cee90992e39ee97d9',
        'steps': {},
    }
    rc = 2

    def run(name, argv, cwd=base, expected=0):
        try:
            completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=40)
        except subprocess.TimeoutExpired as error:
            result['steps'][name] = {'argv': argv, 'timed_out': True,
                'stdout': error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else error.stdout,
                'stderr': error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr,
                'owned_cleanup_unknown': True}
            raise
        result['steps'][name] = {'argv': argv, 'rc': completed.returncode,
            'expected_rc': expected, 'stdout': completed.stdout, 'stderr': completed.stderr}
        assert completed.returncode == expected, name + ' unexpected result'
        return completed

    def root_argv(binary, *flags):
        return ['/usr/bin/sudo', '-n', '/usr/bin/env', 'P4_EXPECTED_JOB_CGROUP=' + membership, str(binary), *flags]

    try:
        run('candidate-build', [cargo, 'build', '--locked', '--offline', '-j', '1', '--bin', 'owned-ipc-controls'])
        run('candidate-unit', [cargo, 'test', '--locked', '--offline', '-j', '1', '--lib', '--bins'])
        binary = base / 'target/debug/owned-ipc-controls'
        result['candidate_binary_sha256'] = digest(binary.read_bytes())
        run('candidate-ordinary-host', [str(binary)])
        candidate = run('candidate-private-projection', root_argv(binary, '--private-projection'))
        assert 'same-class different owned caller rejected' in candidate.stdout
        assert 'descriptors/socket cleaned, parent namespace/projection/membership unchanged' in candidate.stdout
        negative = base / 'old-library-negative'
        negative.mkdir()
        for relative in ('Cargo.toml', 'Cargo.lock', 'src/lib.rs', 'src/psi.rs', 'src/bin/owned_ipc_controls.rs', 'src/event_fixture.rs'):
            source = base / relative
            if relative == 'src/lib.rs': source = base / 'negative-controls/original-lib.rs'
            if relative == 'src/bin/owned_ipc_controls.rs': source = base / 'negative-controls/old-api-controls.rs'
            target = negative / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        assert digest((negative / 'src/lib.rs').read_bytes()) == result['negative_library_expected_sha256']
        actual_control = (base / 'src/bin/owned_ipc_controls.rs').read_text()
        old_api_control = actual_control.replace('let role = RolePolicy { uid, gid, namespaces, executable, expected_peer: peer_pin };',
                                                 'let role = RolePolicy { uid, gid, namespaces, executable };')
        assert old_api_control != actual_control and (negative / 'src/bin/owned_ipc_controls.rs').read_text() == old_api_control
        result['old_library_negative_test_adaptation'] = 'one RolePolicy initializer removes unavailable expected_peer field; all actual test assertions unchanged'
        run('old-library-build', [cargo, 'build', '--locked', '--offline', '-j', '1', '--bin', 'owned-ipc-controls'], cwd=negative)
        old_binary = negative / 'target/debug/owned-ipc-controls'
        result['old_library_binary_sha256'] = digest(old_binary.read_bytes())
        old = run('old-library-same-class-negative', root_argv(old_binary, '--peer-birth-only'), cwd=negative, expected=2)
        assert 'BIRTH_BINDING_MISSING: same-class different owned process authenticated' in old.stderr
        assert 'shares all ten namespaces' in old.stdout
        assert 'descriptors/socket cleaned, parent namespace/projection/membership unchanged' in old.stdout
        rc = 0
    except Exception as error:
        result['failure'] = repr(error)
    finally:
        try:
            result['membership_preserved'] = Path('/proc/self/cgroup').read_text() == membership
            result['limits_after'] = {n: (group / n).read_text().strip() for n in names}
            result['job_process_generations_preserved'] = members(group) == original_members
            result['remaining_direct_children'] = Path('/proc/self/task', str(os.getpid()), 'children').read_text().strip()
            result['hierarchy_unchanged'] = sorted(p.name for p in group.iterdir() if p.is_dir()) == original_children
            result['controllers_unchanged'] = (group / 'cgroup.subtree_control').read_text() == original_controllers
            result['local_memory_events_unchanged'] = (group / 'memory.events.local').read_text() == original_events
            now_ns, now_projection = os.stat('/proc/self/ns/mnt'), os.stat('/sys/fs/cgroup')
            result['parent_mount_namespace_preserved'] = (now_ns.st_dev, now_ns.st_ino) == (namespace.st_dev, namespace.st_ino)
            result['parent_projection_preserved'] = (now_projection.st_dev, now_projection.st_ino) == (projection.st_dev, projection.st_ino)
            result['parent_mountinfo_unchanged'] = digest(Path('/proc/self/mountinfo').read_bytes()) == original_mount_hash
            result['owned_scope_preserved'] = all(result[n] for n in (
                'membership_preserved', 'job_process_generations_preserved', 'hierarchy_unchanged', 'controllers_unchanged',
                'local_memory_events_unchanged', 'parent_mount_namespace_preserved', 'parent_projection_preserved', 'parent_mountinfo_unchanged'))
            result['owned_scope_preserved'] &= result['limits_after'] == limits and result['remaining_direct_children'] == ''
            if not result['owned_scope_preserved']: rc = 2
        except Exception as error:
            result['finalization_error'] = repr(error); rc = 2
        result.update(rc=rc, result='PASS' if rc == 0 else 'FAIL', finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        save(base / 'result.json', result)
        print(json.dumps(result, indent=2), flush=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
