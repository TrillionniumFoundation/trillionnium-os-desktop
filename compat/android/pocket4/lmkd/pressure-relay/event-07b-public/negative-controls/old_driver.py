#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""One admitted job's owned cgroup subtree; one separately authorized PSI event.

This fixture is not a production service. Root is needed only for its exact
job-owned hierarchy/mount-namespace controls. Unknown job members fail closed.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import selectors
import subprocess
import sys
import time
import uuid
from event_guard import MainGuard, GuardFailure, save, scope_sample, owned_guard


def run_event(binary, target, control_membership, output, guardian, pins):
    """One start, one optional arm, no retries, and a saved exact abort frame."""
    env = dict(os.environ, P4_EVENT_TARGET=str(target),
               P4_EVENT_TARGET_ID='%d:%d' % identity(target),
               P4_EVENT_CONTROL_MEMBERSHIP=control_membership)
    run = subprocess.Popen([str(binary), '--psi-event-suite', str(target)], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    retained = {'stdout': bytearray(), 'stderr': bytearray()}
    journals = {}
    selector = selectors.DefaultSelector()
    for name, stream in (('stdout', run.stdout), ('stderr', run.stderr)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
        journals[name] = os.open(output / ('test.' + name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    started = time.monotonic_ns()
    last_health = None
    last_health_start = None
    pressure_start = None
    armed = False
    cancelled = False
    ready = False
    failure = None
    line_buffer = b''
    forced = False
    pidfd = os.pidfd_open(run.pid)

    def cancel(error):
        nonlocal failure, cancelled
        if failure is None:
            failure = {'error': repr(error), 'trigger': getattr(error, 'observation', None),
                       'health_evidence': getattr(error, 'evidence', None),
                       'at_monotonic_ns': time.monotonic_ns(), 'armed': armed}
            try:
                save(output / 'first-stop.json', failure)
            except Exception as persistence_error:
                failure['first_stop_persistence_error'] = repr(persistence_error)
        if not cancelled and run.poll() is None:
            cancelled = True
            try:
                run.stdin.write(b'q'); run.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    try:
        while run.poll() is None or selector.get_map():
            for key, _ in selector.select(0.01):
                data = os.read(key.fd, 16384)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                check(len(retained[key.data]) + len(data) <= 1024 * 1024, 'owned test output exceeds bound')
                retained[key.data].extend(data)
                view = memoryview(data)
                while view:
                    written = os.write(journals[key.data], view)
                    check(written > 0, 'short event journal write')
                    view = view[written:]
                os.fsync(journals[key.data])
                if key.data == 'stdout':
                    line_buffer += data
                    while b'\n' in line_buffer:
                        line, line_buffer = line_buffer.split(b'\n', 1)
                        if line.startswith(b'EVENT_READY '):
                            check(not ready and not armed, 'event fixture attempted a second ready/arm')
                            ready = True
            now = time.monotonic_ns()
            if run.poll() is None and (last_health is None or now - last_health >= 50_000_000 or (ready and not armed and failure is None)):
                try:
                    frame = guardian.sample('event-arm' if ready and not armed else 'event-running')
                    # A slow collection/persistence cycle cannot silently widen
                    # the original 100 ms health-observation contract.
                    if armed and last_health_start is not None and frame['started_monotonic_ns'] - last_health_start >= 100_000_000:
                        raise GuardFailure('HEALTH_CADENCE_EXCEEDED_100MS', 'health-collector',
                                           'sample_start_gap_ns', frame['started_monotonic_ns'] - last_health_start, '<', 100_000_000)
                    last_health_start = frame['started_monotonic_ns']
                    last_health = frame['completed_monotonic_ns']
                    for pin in pins:
                        pin.verify(control_membership)
                    if ready and not armed and failure is None:
                        current = frame['owned_scope']['target']['memory_current']
                        if current > 8 * 1024 * 1024:
                            raise GuardFailure('TARGET_PREARM_NOT_QUIET', 'target', 'memory.current', current, '<=', 8 * 1024 * 1024)
                        save(output / 'arm-intent.json', {'monotonic_ns': time.monotonic_ns(),
                             'health_frame': guardian.index - 1, 'one_arm_only': True,
                             'allocation_max_bytes': 32 * 1024 * 1024, 'pressure_max_ns': 3_000_000_000})
                        guardian.attempted = True
                        armed = True
                        pressure_start = time.monotonic_ns()
                        run.stdin.write(b'a'); run.stdin.flush()
                except Exception as error:
                    cancel(error)
                    last_health = time.monotonic_ns()
            now = time.monotonic_ns()
            if run.poll() is None and pressure_start is not None and now - pressure_start >= 3_000_000_000 and not cancelled:
                cancel(GuardFailure('PRESSURE_PHASE_DEADLINE', 'owned-allocator', 'phase_ns', now - pressure_start, '<', 3_000_000_000))
            if run.poll() is None and now - started >= 8_000_000_000:
                cancel(GuardFailure('OWNED_SUITE_CLEANUP_DEADLINE', 'owned-suite', 'lifetime_ns', now - started, '<', 8_000_000_000))
                # pidfd targets exactly this lifecycle-owned child. Its own
                # children have PDEATHSIG. A forced stop is always failed.
                import signal
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                forced = True
                run.wait(timeout=3)
        run.wait(timeout=1)
    except Exception as error:
        cancel(error)
        if run.poll() is None:
            try:
                run.wait(timeout=2)
            except subprocess.TimeoutExpired:
                import signal
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                forced = True
                run.wait(timeout=3)
    finally:
        # Keep partial output on every error; no unknown task is swept away.
        for name, stream in (('stdout', run.stdout), ('stderr', run.stderr)):
            try:
                while True:
                    data = os.read(stream.fileno(), 16384)
                    if not data:
                        break
                    retained[name].extend(data)
                    view = memoryview(data)
                    while view:
                        n = os.write(journals[name], view)
                        check(n > 0, 'partial event journal write')
                        view = view[n:]
                os.fsync(journals[name])
            except BlockingIOError:
                pass
        selector.close()
        for fd in journals.values():
            os.close(fd)
        os.close(pidfd)
        run.stdin.close(); run.stdout.close(); run.stderr.close()
    stdout = retained['stdout'].decode(errors='replace')
    stderr = retained['stderr'].decode(errors='replace')
    expected_cleanup = ('EVENT_CLEANUP allocator_normal=true witnesses_live_before_stop=true '
                        'worker_joined=true aliases_hup=true monitors_closed=true '
                        'foreground_normal=true protected_normal=true peer_normal=true')
    clean = expected_cleanup in stdout.splitlines()
    passed = (run.returncode == 0 and armed and not forced and failure is None and clean and
              'RESULT PASS mode=owned-host-real-psi-event-only no_android=true no_lmkd_killgate=true' in stdout.splitlines())
    return {'test_rc': run.returncode, 'test_stdout': stdout, 'test_stderr': stderr,
            'armed_exactly_once': armed, 'forced_owned_child_kill': forced,
            'first_stop': failure, 'real_event_and_child_cleanup_pass': passed,
            'owned_child_reaped': run.returncode is not None}


def check(value, message):
    if not value:
        raise RuntimeError(message)


def read_at(fd, name):
    n = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        data = os.read(n, 65537)
        check(len(data) <= 65536, "metadata bound")
        return data.decode()
    finally:
        os.close(n)


def birth(text, pid):
    left, right = text.index("("), text.rindex(")")
    check(int(text[:left].strip()) == pid, "proc PID view mismatch")
    return int(text[right + 1:].split()[19])


class Pin:
    def __init__(self, pid, expected_cgroup):
        self.pid = pid
        self.fd = os.pidfd_open(pid)
        self.proc = os.open(f"/proc/{pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.start = birth(read_at(self.proc, "stat"), pid)
        self.status = tuple(line for line in read_at(self.proc, "status").splitlines() if line.startswith(("Uid:", "Gid:", "NSpid:")))
        self.namespaces = {}
        self.namespace_fds = []
        for name in ("pid", "mnt", "cgroup", "user", "time", "net", "ipc", "uts"):
            fd = os.open("ns/" + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc)
            self.namespace_fds.append(fd)
            self.namespaces[name] = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        self.exe = os.readlink("exe", dir_fd=self.proc)
        self.verify(expected_cgroup)

    def alive(self):
        p = select.poll()
        p.register(self.fd, select.POLLIN)
        return not p.poll(0)

    def verify(self, expected_cgroup):
        check(self.alive(), "pinned job process died")
        check(birth(read_at(self.proc, "stat"), self.pid) == self.start, "job process birth changed")
        status = tuple(line for line in read_at(self.proc, "status").splitlines() if line.startswith(("Uid:", "Gid:", "NSpid:")))
        check(status == self.status and os.readlink("exe", dir_fd=self.proc) == self.exe, "job process credentials/executable changed")
        for name, identity in self.namespaces.items():
            s = os.stat("ns/" + name, dir_fd=self.proc)
            check((s.st_dev, s.st_ino) == identity, "job process namespace changed")
        check(read_at(self.proc, "cgroup") == expected_cgroup, "job process membership changed unexpectedly")
        check(self.alive(), "job process died during verification")

    def close(self):
        for fd in self.namespace_fds:
            os.close(fd)
        os.close(self.proc)
        os.close(self.fd)


def identity(path):
    s = path.stat()
    return (s.st_dev, s.st_ino)


def pids(path):
    return set(map(int, (path / "cgroup.procs").read_text().split()))


def events(path):
    return dict((k, int(v)) for k, v in (line.split() for line in (path / "memory.events").read_text().splitlines()))


def main():
    check(len(sys.argv) == 3 and os.geteuid() == 0, "requires exact owned event binary, new output directory and root")
    binary = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2])
    output.mkdir(mode=0o700)
    expected_membership = os.environ["P4_EXPECTED_JOB_CGROUP"]
    membership = Path("/proc/self/cgroup").read_text()
    check(membership == expected_membership and membership.startswith("0::/"), "not the admitted job")
    relative = membership.strip()[4:]
    check(relative and ".." not in Path(relative).parts, "unsafe job scope")
    job = Path("/sys/fs/cgroup") / relative
    check(job.name.startswith("hepta-runtime-job-"), "scope is not a fresh runtime job")
    job_id = identity(job)
    keys = ("memory.max", "memory.high", "memory.swap.max", "cpu.max", "pids.max")
    original_limits = {k: (job / k).read_text() for k in keys}
    check(original_limits["memory.max"].strip() != "max" and 0 < int(original_limits["memory.max"]) <= 536870912, "memory admission")
    job_cap = int(original_limits["memory.max"])
    check(int((job / "memory.current").read_text()) < job_cap // 2, "job is not quiet enough for registration controls")
    fixture_cap = min(268435456, job_cap)
    check(fixture_cap >= 134217728, "job too small for conservative owned fixture")
    task_cap = min(64, int(original_limits["pids.max"]) if original_limits["pids.max"].strip() != "max" else 64)
    check(task_cap >= 32, "job task budget too small for owned fixture")
    q, period = map(int, original_limits["cpu.max"].split())
    check(0 < q <= period, "CPU admission")
    original_controllers = (job / "cgroup.subtree_control").read_text()
    check(not original_controllers.strip() and (job / "cgroup.type").read_text() == "domain\n", "job not a fresh empty-controller domain")
    controllers = (job / "cgroup.controllers").read_text().split()
    check(set(("cpu", "memory", "pids")) <= set(controllers), "required controllers not delegated")
    original_events = events(job)
    original_local_events = dict((k, int(v)) for k, v in (line.split() for line in (job / 'memory.events.local').read_text().splitlines()))
    original_parent_ns = {n: identity(Path("/proc/self/ns") / n) for n in ("pid", "mnt", "cgroup", "user", "time")}
    original_projection = identity(Path("/sys/fs/cgroup"))
    original_dirs = {p.name: identity(p) for p in job.iterdir() if p.is_dir()}
    original_pids = pids(job)
    check(os.getpid() in original_pids and 1 <= len(original_pids) <= 12, "job membership admission")
    pins = []
    root = job / ("psi-owned-" + uuid.uuid4().hex)
    control, target, sibling = (root / n for n in ("control", "target", "sibling"))
    control_membership = "0::/" + str(control.relative_to("/sys/fs/cgroup")) + "\n"
    moved = []
    created = []
    cleanup = []
    outcome = {"scope": "one owned host PSI event only; no Android/private cell, Main mutation or LMKD killgate", "kernel": os.uname().release, "limits": {k: v.strip() for k, v in original_limits.items()}, "job_member_count": len(original_pids), "test_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "automatic_retry": False}
    code = 2
    guardian = None
    try:
        guardian = MainGuard(Path(__file__).with_name('prior_run_fixture.py'), output)
        guardian.sample('admission-before-owned-hierarchy')
        for pid in sorted(original_pids):
            pins.append(Pin(pid, membership))
        check(pids(job) == original_pids and identity(job) == job_id, "job changed before setup")
        root.mkdir(mode=0o700)
        created.append((root, identity(root)))
        for path in (control, target, sibling):
            path.mkdir(mode=0o700)
            created.append((path, identity(path)))
        # Only these frozen members of this new job move; no name-based lookup.
        for pin in pins:
            pin.verify(membership)
            (control / "cgroup.procs").write_text(str(pin.pid) + "\n")
            moved.append(pin)
            pin.verify(control_membership)
        check(not pids(job) and pids(control) == original_pids, "no-internal-process boundary not achieved")
        (job / "cgroup.subtree_control").write_text("+cpu +memory +pids\n")
        (root / "memory.max").write_text(str(fixture_cap) + "\n")
        (root / "memory.high").write_text("max\n")
        (root / "memory.swap.max").write_text("0\n")
        (root / "cpu.max").write_text(f"{q} {period}\n")
        (root / "pids.max").write_text(str(task_cap) + "\n")
        (root / "cgroup.subtree_control").write_text("+cpu +memory +pids\n")
        for path, cap in ((control, fixture_cap // 2), (target, fixture_cap // 4), (sibling, fixture_cap // 4)):
            check(int((path / "memory.current").read_text()) < cap // 2, "owned leaf budget admission")
            (path / "memory.max").write_text(str(cap) + "\n")
            (path / "memory.high").write_text(str(24 * 1024 * 1024) + '\n' if path == target else 'max\n')
            (path / "memory.swap.max").write_text("0\n")
            (path / "cpu.max").write_text(f"{q} {period}\n")
            (path / "pids.max").write_text("32\n")
        check({k: (job / k).read_text() for k in keys} == original_limits, "parent limits changed")
        before = {name: events(path) for name, path in (("root", root), ("control", control), ("target", target), ("sibling", sibling))}
        paths = dict(job=job, root=root, control=control, target=target, sibling=sibling)
        guardian.bind_owned_scope(paths)
        guardian.sample('admission-after-owned-hierarchy')
        outcome.update(run_event(binary, target, control_membership, output, guardian, pins))
        after = {name: events(path) for name, path in (("root", root), ("control", control), ("target", target), ("sibling", sibling))}
        outcome.update(memory_events_before=before, memory_events_after=after)
        owned_guard(scope_sample(paths, guardian.prior), guardian.scope_baseline)
        guardian.sample('after-event-and-child-retirement')
        check(not pids(target) and not pids(sibling) and pids(control) == original_pids, "owned tests left live tasks")
        code = 0 if outcome['real_event_and_child_cleanup_pass'] else 2
    except Exception as error:
        outcome["failure"] = repr(error)
        outcome['trigger'] = getattr(error, 'observation', None)
        outcome['health_evidence'] = getattr(error, 'evidence', None)
    finally:
        # Run independent legal cleanup steps even after a partial mkdir or
        # member-restore failure. Unknown tasks/generations veto hierarchy edits.
        steps = []
        def attempt(name, function):
            try:
                function()
                steps.append({"step": name, "ok": True})
                return True
            except Exception as error:
                cleanup.append(name + ": " + repr(error))
                steps.append({"step": name, "ok": False})
                return False
        def scope_safe():
            check(identity(job) == job_id, "parent directory generation changed")
            expected_job_dirs = dict(original_dirs)
            for path, expected_id in created:
                if path.parent == job:
                    expected_job_dirs[path.name] = expected_id
            check({p.name: identity(p) for p in job.iterdir() if p.is_dir()} == expected_job_dirs,
                  'unbound job subtree prevents controller restoration')
            for path, expected_id in created:
                check(path.exists() and identity(path) == expected_id, "created directory generation changed")
                expected_children = {child.name: child_id for child, child_id in created if child.parent == path}
                check({p.name: identity(p) for p in path.iterdir() if p.is_dir()} == expected_children,
                      'unbound descendant prevents owned hierarchy cleanup')
                if path == control: check(pids(path) <= original_pids, "unbound task in control leaf")
                else: check(not pids(path), "unknown/live task prevents cleanup")
        safe = attempt("bound hierarchy and member check", scope_safe)
        def disable(path):
            actual = (path / "cgroup.subtree_control").read_text().split()
            check(set(actual) <= {"cpu", "memory", "pids"}, "unexpected controller")
            if actual: (path / "cgroup.subtree_control").write_text(" ".join("-" + c for c in actual) + "\n")
        if safe:
            root_disabled = True
            if any(path == root for path, _ in created):
                root_disabled = attempt("disable owned-root controllers", lambda: disable(root))
            job_disabled = root_disabled and attempt("restore job controller state", lambda: disable(job))
            if job_disabled:
                for index, pin in enumerate(pins):
                    def restore(pin=pin):
                        if pin.alive():
                            actual = read_at(pin.proc, "cgroup")
                            check(actual in (membership, control_membership), "bound member escaped known migration endpoints")
                            pin.verify(actual)
                            if actual == control_membership:
                                (job / "cgroup.procs").write_text(str(pin.pid) + "\n")
                            pin.verify(membership)
                    attempt("restore bound member " + str(index), restore)
                for path, expected_id in reversed(created):
                    def remove(path=path, expected_id=expected_id):
                        check(identity(path) == expected_id and not pids(path), "leaf generation or emptiness changed")
                        path.rmdir()
                    attempt("remove owned " + ("root" if path == root else path.name), remove)
        def verify_final():
            check({k: (job / k).read_text() for k in keys} == original_limits, "parent budgets were not preserved")
            check((job / "cgroup.subtree_control").read_text() == original_controllers, "parent controller state not restored")
            check({p.name: identity(p) for p in job.iterdir() if p.is_dir()} == original_dirs, "owned cgroup subtree remains")
            check(Path("/proc/self/cgroup").read_text() == membership, "fixture parent not restored")
            check({n: identity(Path("/proc/self/ns") / n) for n in original_parent_ns} == original_parent_ns, "fixture parent namespace changed")
            check(identity(Path("/sys/fs/cgroup")) == original_projection, "parent projection changed")
            parent_after = events(job)
            for event in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
                check(parent_after[event] == original_events[event], 'parent max/OOM event changed:' + event)
            local_after = dict((k, int(v)) for k, v in (line.split() for line in (job / 'memory.events.local').read_text().splitlines()))
            check(local_after == original_local_events, 'parent experienced its own pressure')
            outcome['parent_memory_events_before'] = original_events
            outcome['parent_memory_events_after'] = parent_after
            outcome['parent_memory_events_local_unchanged'] = True
            for pin in pins:
                if pin.alive(): pin.verify(membership)
            expected_after = {pin.pid for pin in pins if pin.alive()}
            if not moved:
                # Admission may fail before process pinning or any hierarchy
                # mutation. Do not mistake untouched original members for
                # newly leaked children, and do not move such unpinned tasks.
                expected_after |= original_pids - {pin.pid for pin in pins}
            check(pids(job) == expected_after, "unbound job member remains after restoration")
        final_ok = attempt("verify complete restored parent boundary", verify_final)
        if final_ok and not cleanup:
            outcome["cleanup"] = {"original_members_restored_or_naturally_exited": True, "owned_subtree_empty_and_removed": True, "parent_budget_controller_namespace_projection_preserved": True, "parent_local_events_and_max_oom_unchanged": True}
        if guardian is not None:
            # The hierarchy is now gone; finish only observes the original Main.
            guardian.paths = None
            def final_main():
                guardian.sample('final-after-owned-hierarchy-removal')
                outcome['main_full_boundary_and_formal_epoch_preserved'] = guardian.finish()
            attempt('verify complete formal Main fence', final_main)
        if cleanup: code = 2
        outcome["cleanup_steps"] = steps
        for pin in pins:
            pin.close()
        outcome["cleanup_errors"] = cleanup
        outcome["result"] = "PASS" if code == 0 and not cleanup and "failure" not in outcome else "FAIL"
        save(output / 'result.json', outcome)
        print(json.dumps(outcome, indent=2), flush=True)
    return 0 if outcome["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
