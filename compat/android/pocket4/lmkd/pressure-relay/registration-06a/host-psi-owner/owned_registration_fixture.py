#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""One admitted job's owned cgroup subtree; registration only, never pressure.

This fixture is not a production service. Root is needed only for its exact
job-owned hierarchy/mount-namespace controls. Unknown job members fail closed.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import uuid


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
    check(len(sys.argv) == 2 and os.geteuid() == 0, "requires exact owned test binary and root")
    binary = Path(sys.argv[1]).resolve(strict=True)
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
    outcome = {"scope": "owned host registration/revocation only; no Android/private cell, Main or pressure", "kernel": os.uname().release, "limits": {k: v.strip() for k, v in original_limits.items()}, "job_member_count": len(original_pids), "test_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    code = 2
    try:
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
            (path / "memory.high").write_text("max\n")
            (path / "memory.swap.max").write_text("0\n")
            (path / "cpu.max").write_text(f"{q} {period}\n")
            (path / "pids.max").write_text("32\n")
        check({k: (job / k).read_text() for k in keys} == original_limits, "parent limits changed")
        before = {name: events(path) for name, path in (("root", root), ("control", control), ("target", target), ("sibling", sibling))}
        run = subprocess.Popen([str(binary), "--psi-suite", str(target), str(root), str(sibling)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = run.communicate(timeout=25)
            outcome.update(test_rc=run.returncode, test_stdout=stdout, test_stderr=stderr, timed_out=False)
        except subprocess.TimeoutExpired:
            # Popen owns this unreaped exact child, so its PID cannot be reused.
            # Cancel only that owned test; its peers arm parent-death SIGKILL.
            run.kill()
            stdout, stderr = run.communicate(timeout=5)
            outcome.update(test_rc=run.returncode, test_stdout=stdout, test_stderr=stderr, timed_out=True, cancelled_owned_test=True)
            raise RuntimeError("owned registration test timed out; partial output retained")
        after = {name: events(path) for name, path in (("root", root), ("control", control), ("target", target), ("sibling", sibling))}
        outcome.update(memory_events_before=before, memory_events_after=after)
        check(before == after, "owned resource events changed during no-pressure control")
        check(not pids(target) and not pids(sibling) and pids(control) == original_pids, "owned tests left live tasks")
        code = run.returncode
    except Exception as error:
        outcome["failure"] = repr(error)
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
            for path, expected_id in created:
                check(path.exists() and identity(path) == expected_id, "created directory generation changed")
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
            check(events(job) == original_events, "parent memory event counters changed")
            for pin in pins:
                if pin.alive(): pin.verify(membership)
            check(pids(job) == {pin.pid for pin in pins if pin.alive()}, "unbound job member remains after restoration")
        final_ok = attempt("verify complete restored parent boundary", verify_final)
        if final_ok and not cleanup:
            outcome["cleanup"] = {"original_members_restored_or_naturally_exited": True, "owned_subtree_empty_and_removed": True, "parent_budget_controller_namespace_projection_preserved": True, "parent_memory_events_unchanged": True}
        if cleanup: code = 2
        outcome["cleanup_steps"] = steps
        for pin in pins:
            pin.close()
        outcome["cleanup_errors"] = cleanup
        outcome["result"] = "PASS" if code == 0 and not cleanup and "failure" not in outcome else "FAIL"
        print(json.dumps(outcome, indent=2), flush=True)
    return 0 if outcome["result"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
