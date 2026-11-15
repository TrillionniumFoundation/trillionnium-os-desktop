"""Owned QMP gate with a finite, continuously held two-counter observation.

This source cannot discover or approve its own runtime profile. The caller must
authenticate the sealed profile and original VM custody before invoking it.
No VM creation, shell, process start, stop, retry or arbitrary QMP entry point.
"""
import errno
import hashlib
import json
import os
import re
import select
import socket
import stat
import struct
import time
from pathlib import Path

FRAME_LIMIT = 16384
FRAME_COUNT = 16
TRANSCRIPT_LIMIT = 524288
SAMPLE_LIMIT = 160
QUERY_NS = 250000000
NAMES = ("exits", "io_exits")


class OriginalProcessExited(RuntimeError):
    """An exact original PIDFD exit, never a replaceable numeric PID check."""


def need(value, message):
    if not value:
        raise RuntimeError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate QMP JSON key")
        result[key] = value
    return result


def decode(line):
    need(type(line) is bytes and 0 < len(line) <= FRAME_LIMIT and line.endswith(b"\n"),
         "bounded complete QMP line")
    value = json.loads(line, object_pairs_hook=unique,
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite QMP JSON")))
    need(type(value) is dict, "QMP frame is an object")
    return value


def identity(node):
    return [getattr(node, k) for k in
        ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def uint(value):
    return type(value) is int and 0 <= value < 2**64


def validate_schema(value):
    need(type(value) is list and 1 <= len(value) <= 2, "fixed KVM schema target count")
    targets = set()
    for group in value:
        need(type(group) is dict and set(group) == {"provider", "target", "stats"}
             and group["provider"] == "kvm" and group["target"] in ("vm", "vcpu"),
             "exact KVM schema provider/target/shape")
        need(group["target"] not in targets, "unique KVM schema target")
        targets.add(group["target"])
        rows = group["stats"]
        need(type(rows) is list and 1 <= len(rows) <= 512, "bounded KVM schema descriptors")
        names = set()
        for row in rows:
            need(type(row) is dict and {"name", "type", "exponent"} <= set(row)
                 and set(row) <= {"name", "type", "exponent", "unit", "base", "bucket-size"},
                 "exact documented KVM descriptor keys")
            name = row["name"]
            need(type(name) is str and re.fullmatch("[a-z][a-z0-9_]{0,127}", name)
                 and name not in names, "unique bounded KVM descriptor name")
            names.add(name)
            need(row["type"] in ("cumulative", "instant", "peak", "linear-histogram", "log2-histogram")
                 and type(row["exponent"]) is int and -(2**15) <= row["exponent"] < 2**15,
                 "typed KVM descriptor")
            if "unit" in row:
                need(row["unit"] in ("bytes", "seconds", "cycles", "boolean"), "documented KVM unit")
            if "base" in row:
                need(type(row["base"]) is int and -(2**7) <= row["base"] < 2**7
                     and row["exponent"] != 0, "typed KVM scaling base")
            if "bucket-size" in row:
                need(row["type"] == "linear-histogram" and type(row["bucket-size"]) is int
                     and 0 <= row["bucket-size"] < 2**32, "typed KVM histogram bucket")
        if group["target"] == "vcpu":
            descriptors = {r["name"]: r for r in rows}
            for name in NAMES:
                need(descriptors.get(name) == {"name": name, "type": "cumulative", "exponent": 0},
                     "required dimensionless unscaled cumulative scalar counter: " + name)
    need("vcpu" in targets, "required vCPU KVM schema")
    need(len(canonical(value)) < FRAME_LIMIT - 128, "frozen schema fits original QMP frame budget")


def validate_profile(profile, expected_sha):
    need(sha(expected_sha), "sealed KVM profile SHA required")
    need(type(profile) is dict and set(profile) == {"schema", "qemu", "host", "source_evidence", "expected_schema"}
         and profile["schema"] == "p4-kvm-two-counter-profile-v1", "exact reviewed KVM profile")
    need(hashlib.sha256(canonical(profile)).hexdigest() == expected_sha, "complete frozen KVM profile SHA")
    q = profile["qemu"]
    need(type(q) is dict and set(q) == {"bytes", "sha256", "package"} and type(q["bytes"]) is int
         and 0 < q["bytes"] <= 256 * 1024**2 and sha(q["sha256"])
         and type(q["package"]) is str and 0 < len(q["package"]) <= 256,
         "frozen actual QEMU binary and distribution package")
    h = profile["host"]
    need(type(h) is dict and set(h) == {"release", "version", "boot_id"}
         and all(type(v) is str and 0 < len(v) <= 512 for v in h.values()), "frozen actual host kernel generation")
    s = profile["source_evidence"]
    need(type(s) is dict and set(s) == {"qemu_distribution_source_sha256", "qemu_distribution_patchset_sha256",
         "host_kvm_counter_definitions_sha256"} and all(sha(v) for v in s.values()),
         "independently audited distribution and host KVM source evidence pins")
    validate_schema(profile["expected_schema"])
    return profile


class OwnedStatsSession:
    """No generic command API: exactly the original gate and two fixed queries."""

    def __init__(self, socket_path, pid, pidfd, observer, record, cpu_observer, profile, profile_sha):
        self.profile = validate_profile(profile, profile_sha)
        self.path = Path(socket_path)
        need(self.path.is_absolute() and self.path.name == "qmp.sock" and len(os.fsencode(self.path)) < 108,
             "one fixed owned Unix socket")
        node = self.path.lstat()
        need(stat.S_ISSOCK(node.st_mode) and node.st_uid == node.st_gid == 1000
             and node.st_nlink == 1 and node.st_mode & 0o077 == 0, "private QEMU UID1000 socket only")
        self.socket_identity = identity(node)
        need(type(pid) is int and pid > 1, "original live QEMU PID required")
        self.pid, self.pidfd = pid, pidfd
        self.poll = select.poll()
        self.poll.register(pidfd, select.POLLIN)
        need(not self.poll.poll(0), "original QEMU PIDFD must still be live")
        self.record, self.observer, self.cpu_observer = record, observer, cpu_observer
        self.s = None
        self.pending = bytearray()
        self.pending_since_ns = None
        self.frames = []
        self.wire_bytes = 0
        self.samples = 0
        self.last_sample_end_ns = None
        self.previous = None
        self.cpu_map = None
        self.cpu_fds = []
        self.cont_committed = False
        self.resume_count = 0
        self.terminal_announced = False
        self.closed = False
        self.outstanding = False
        self.failed = False
        self.eof = False
        self.start_result = None
        self.coverage = {"continuous_connection_from_before_cont": True,
                         "completed_to_original_exit": False, "unobserved_reconnect_gaps": 0}
        try:
            self._start()
        except BaseException as error:
            self._abort(error)
            raise

    @staticmethod
    def _now():
        a = time.monotonic_ns()
        wall = time.time_ns()
        return {"monotonic_start_ns": a, "wall_time_ns": wall, "monotonic_end_ns": time.monotonic_ns()}

    def _time_left(self, deadline):
        remaining = deadline - time.monotonic_ns()
        need(remaining > 0, "finite QMP request monotonic deadline")
        return min(5.0, remaining / 1e9)

    def _save_wire(self, direction, raw, before, after):
        self.wire_bytes += len(raw)
        need(self.wire_bytes <= TRANSCRIPT_LIMIT, "finite total raw QMP transcript")
        item = {"direction": direction, "raw_utf8": raw.decode("utf-8", errors="strict"),
                "before": before, "after": after}
        self.frames.append(item)
        self.record({"state": "QMP_STATS_WIRE", "sequence": len(self.frames) - 1,
                     "total_wire_bytes": self.wire_bytes, **item})

    def _guard(self, allow_exited=False):
        need(not self.closed and not self.failed, "active original QMP observation only")
        if not allow_exited:
            if self.poll.poll(0):
                raise OriginalProcessExited("original QEMU PIDFD remained live")
            for row, fd in self.cpu_fds:
                self._task_matches(row, fd)
        need(identity(self.path.lstat()) == self.socket_identity, "owned QMP socket changed")
        peer = struct.unpack("3i", self.s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        need(peer == (self.pid, 1000, 1000), "QMP kernel peer must be original QEMU PID/UID/GID")

    @staticmethod
    def _proc(fd, name):
        stream = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
        try:
            need(stat.S_ISREG(os.fstat(stream).st_mode), "regular held vCPU proc file")
            chunks = bytearray()
            while True:
                part = os.read(stream, 4096)
                if not part:
                    return bytes(chunks).decode("ascii", errors="strict")
                chunks.extend(part)
                need(len(chunks) <= 65536, "bounded held vCPU proc file")
        finally:
            os.close(stream)

    def _task_matches(self, row, fd):
        before = identity(os.fstat(fd))
        first, status, last = self._proc(fd, "stat"), self._proc(fd, "status"), self._proc(fd, "stat")
        need(before == identity(os.fstat(fd)) == row["held_proc_identity"], "same held vCPU proc inode")
        need(first.rsplit(")", 1)[1].split()[19] == last.rsplit(")", 1)[1].split()[19] == row["start_ticks"],
             "same original vCPU birth")
        tgids = [s.split()[1] for s in status.splitlines() if s.startswith("Tgid:")]
        need(tgids == [str(self.pid)] == [str(row["actual_Tgid"])], "vCPU remains in original QEMU group")

    def _bind_tasks(self):
        need(type(self.cpu_map) is list and len(self.cpu_map) == 2, "exact original two-vCPU binding")
        paths, tids, indices = set(), set(), set()
        for row in self.cpu_map:
            need(type(row) is dict and {"tid", "start_ticks", "held_proc_identity", "actual_Tgid", "QMP_cpu_info", "cpu_index"} <= set(row),
                 "original authenticated vCPU mapping fields")
            tid, path = row["tid"], row["QMP_cpu_info"]["qom-path"]
            need(type(tid) is int and 1 < tid < 2**31 and type(path) is str and 0 < len(path) <= 1024
                 and row["QMP_cpu_info"]["thread-id"] == tid
                 and type(row["cpu_index"]) is int and row["cpu_index"] in (0, 1), "exact mapped vCPU identity")
            need(path not in paths and tid not in tids and row["cpu_index"] not in indices, "unique mapped vCPU identities")
            paths.add(path); tids.add(tid); indices.add(row["cpu_index"])
            fd = os.open(f"/proc/{self.pid}/task/{tid}", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.cpu_fds.append((row, fd))
            self._task_matches(row, fd)
        self.paths = tuple(row["QMP_cpu_info"]["qom-path"] for row in sorted(self.cpu_map, key=lambda r: r["cpu_index"]))

    def _recv_frame(self, deadline, nonblocking=False, allow_eof=False):
        while b"\n" not in self.pending:
            if self.pending_since_ns is not None:
                need(time.monotonic_ns() - self.pending_since_ns < QUERY_NS, "finite incomplete QMP frame lifetime")
            if nonblocking and not select.select([self.s], [], [], 0)[0]:
                return None
            self.s.settimeout(self._time_left(deadline))
            before = self._now()
            part = self.s.recv(min(4096, FRAME_LIMIT + 1 - len(self.pending)))
            after = self._now()
            self._time_left(deadline)
            if not part:
                need(allow_eof and not self.pending, "complete QMP stream before EOF")
                self.eof = True
                return None
            if not self.pending:
                self.pending_since_ns = before["monotonic_start_ns"]
                self.frame_before = before
            self.pending.extend(part)
            need(b"\n" in self.pending or len(self.pending) < FRAME_LIMIT, "bounded QMP wire frame")
        line, _, rest = self.pending.partition(b"\n")
        raw = bytes(line + b"\n")
        need(len(raw) <= FRAME_LIMIT, "bounded QMP wire frame")
        before = self.frame_before
        self.pending[:] = rest
        # Bytes following the newline may already have arrived in the same
        # recv. Preserve a conservative earlier receipt boundary for them.
        self.pending_since_ns = before["monotonic_start_ns"] if rest else None
        self._save_wire("receive", raw, before, self._now())
        return decode(raw)

    def _event(self, value, allow_resume=False, terminal=False):
        need(set(value) <= {"event", "data", "timestamp"} and {"event", "timestamp"} <= set(value),
             "exact QMP event envelope")
        stamp = value["timestamp"]
        need(type(stamp) is dict and set(stamp) == {"seconds", "microseconds"}
             and type(stamp["seconds"]) is int and stamp["seconds"] >= 0
             and type(stamp["microseconds"]) is int and 0 <= stamp["microseconds"] < 1000000,
             "typed QMP event timestamp")
        event = value["event"]
        self.record({"state": "QMP_STATS_EVENT", "event": value, "observed": self._now()})
        if event == "RESUME":
            need(allow_resume and self.cont_committed and not self.terminal_announced
                 and self.resume_count == 0 and "data" not in value,
                 "one RESUME associated with original single CONT")
            self.resume_count += 1
        elif event == "SHUTDOWN":
            data = value.get("data")
            need(self.cont_committed and not self.terminal_announced and type(data) is dict
                 and set(data) == {"guest", "reason"} and data["guest"] is True
                 and type(data["reason"]) is str and data["reason"] == "guest-shutdown",
                 "one original guest shutdown after CONT")
            self.terminal_announced = True
            # An announcement is not process exit. Keep the same connection
            # and held descriptors until the caller observes its original
            # PIDFD exit; then drain remaining events and require full EOF.
        else:
            raise RuntimeError("unqualified QMP lifecycle event: " + str(event))

    def _command(self, execute, identifier, deadline, arguments=None, allow_resume=False):
        need(not self.outstanding, "only one outstanding QMP request")
        permitted = {"qmp_capabilities", "query-status", "query-cpus-fast", "query-stats-schemas", "query-stats", "cont"}
        need(execute in permitted, "closed QMP command vocabulary")
        if execute == "cont":
            need(self.cont_committed and identifier == "p4r12-cont-once", "original committed CONT only")
        request = {"execute": execute, "id": identifier}
        if arguments is not None:
            request["arguments"] = arguments
        raw = canonical(request) + b"\r\n"
        need(self.wire_bytes + len(raw) <= TRANSCRIPT_LIMIT, "remaining transcript budget before request")
        self._guard()
        self.outstanding = True
        try:
            before = self._now()
            self.s.settimeout(self._time_left(deadline))
            self.s.sendall(raw)
            self._time_left(deadline)
            self._save_wire("send", raw, before, self._now())
            for _ in range(FRAME_COUNT):
                value = self._recv_frame(deadline)
                if "event" in value:
                    self._event(value, allow_resume=allow_resume)
                    continue
                need(set(value) == {"return", "id"} and value["id"] == identifier,
                     "exact QMP success response ID/shape required")
                self._guard()
                self._time_left(deadline)
                return value["return"]
            raise RuntimeError("finite QMP messages per command")
        except BaseException:
            self.failed = True
            raise
        finally:
            self.outstanding = False

    def _values(self, values):
        need(type(values) is list and len(values) == 2, "exact two vCPU statistics objects")
        result = {}
        for row in values:
            need(type(row) is dict and set(row) == {"provider", "qom-path", "stats"}
                 and row["provider"] == "kvm" and row["qom-path"] in self.paths
                 and row["qom-path"] not in result, "exact unique bound KVM vCPU statistics object")
            need(type(row["stats"]) is list and len(row["stats"]) == 2, "exact two requested counters")
            counters = {}
            for counter in row["stats"]:
                need(type(counter) is dict and set(counter) == {"name", "value"}
                     and counter["name"] in NAMES and counter["name"] not in counters
                     and uint(counter["value"]), "unique scalar uint64 requested counter")
                counters[counter["name"]] = counter["value"]
            need(set(counters) == set(NAMES), "no absent requested counter")
            if self.previous is not None:
                need(all(counters[n] >= self.previous[row["qom-path"]][n] for n in NAMES),
                     "original generation cumulative counters do not regress")
            result[row["qom-path"]] = counters
        need(set(result) == set(self.paths), "no missing mapped vCPU statistics")
        return result

    def _stats(self, identifier, deadline):
        values = self._command("query-stats", identifier, deadline, {"target": "vcpu",
            "providers": [{"provider": "kvm", "names": list(NAMES)}], "vcpus": list(self.paths)})
        result = self._values(values)
        delta = None if self.previous is None else {
            p: {n: result[p][n] - self.previous[p][n] for n in NAMES} for p in self.paths}
        self.previous = result
        return {"values": result, "delta": delta}

    def _start(self):
        deadline = time.monotonic_ns() + 15000000000
        observations = [self.observer()]
        self.custody = observations[0]
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(self._time_left(deadline))
        self.s.connect(str(self.path))
        self._guard()
        greeting = self._recv_frame(deadline)
        need(set(greeting) == {"QMP"} and type(greeting["QMP"]) is dict
             and set(greeting["QMP"]) == {"version", "capabilities"}, "QMP greeting before any command")
        need(greeting["QMP"]["version"].get("package") == self.profile["qemu"]["package"],
             "greeting matches independently pinned QEMU distribution package")
        need(self._command("qmp_capabilities", "p4r12-capabilities", deadline) == {}, "QMP capabilities handshake")
        stopped = self._command("query-status", "p4r12-query-prelaunch", deadline)
        need(type(stopped) is dict and set(stopped) <= {"running", "status", "singlestep"}
             and stopped.get("running") is False and stopped.get("status") == "prelaunch"
             and stopped.get("singlestep", False) is False, "-S must still be prelaunch, not guest code already run")
        cpus = self._command("query-cpus-fast", "p4r3-query-cpus-fast", deadline)
        self.record({"state": "QMP_PAUSED_CPU_QUERY_OBSERVED", "socket_identity": self.socket_identity,
            "SO_PEERCRED": [self.pid, 1000, 1000], "greeting_and_responses": list(self.frames),
            "identity_observations": observations, "prelaunch": stopped, "query_cpus_fast": cpus})
        self.cpu_map = self.cpu_observer(cpus)
        self._bind_tasks()
        schema = self._command("query-stats-schemas", "p4stats-schema-once", deadline, {"provider": "kvm"})
        validate_schema(schema)
        need(canonical(schema) == canonical(self.profile["expected_schema"]), "complete fixed KVM schema profile equality")
        baseline = self._stats("p4stats-baseline-once", deadline)
        self.record({"state": "QMP_STATS_BASELINE", "stats": baseline, "observed": self._now(), "cpu_map": self.cpu_map})
        self._time_left(deadline)
        observations.append(self.observer())
        need(observations[0] == observations[1] and not self.poll.poll(0),
             "same original QEMU custody must revalidate before cont")
        self._guard()
        self._time_left(deadline)
        self.record({"state": "QMP_CONT_REQUEST_COMMITTED_ONCE", "socket_identity": self.socket_identity,
            "SO_PEERCRED": [self.pid, 1000, 1000], "greeting_and_responses": list(self.frames),
            "identity_observations": observations, "prelaunch": stopped, "cpu_index_thread_map": self.cpu_map})
        self.cont_committed = True
        need(self._command("cont", "p4r12-cont-once", deadline, allow_resume=True) == {}, "exact QMP cont acknowledgement")
        self.record({"state": "QMP_CONT_ACKNOWLEDGED_ONCE", "SO_PEERCRED": [self.pid, 1000, 1000],
            "complete_handshake_frames": list(self.frames), "cpu_index_thread_map": self.cpu_map})
        self.start_result = {"prelaunch_before_start": stopped, "SO_PEERCRED": [self.pid, 1000, 1000],
            "QMP_cont_once": True, "cpu_index_thread_map": self.cpu_map, "stats_baseline": baseline}

    def _sample(self, slot, owner_deadline):
        """One query for an already collected original CPU/serial observation."""
        need(not self.terminal_announced, "no new statistics request after guest shutdown")
        need(type(slot) is dict and type(slot.get("sample_index")) is int and 0 <= slot["sample_index"] < SAMPLE_LIMIT,
             "existing finite owner observation slot")
        observed = slot.get("sample")
        need(type(observed) is dict and observed.get("phase") == "running"
             and observed.get("pid") == self.pid
             and observed.get("start_ticks") == self.custody["start_ticks"]
             and observed.get("invocation") == self.custody["InvocationID"],
             "same original owner CPU sample generation")
        need(type(observed.get("tasks")) is list, "original owner task sample")
        tasks = {r["tid"]: r for r in observed["tasks"] if "schedstat_raw" in r}
        for row, _ in self.cpu_fds:
            need(row["tid"] in tasks and tasks[row["tid"]]["start_ticks"] == row["start_ticks"]
                 and tasks[row["tid"]]["held_proc_identity"] == row["held_proc_identity"],
                 "same two vCPU generations in owner observation slot")
        now = time.monotonic_ns()
        need(self.last_sample_end_ns is None or now - self.last_sample_end_ns >= 1000000000,
             "no more than one runtime statistics sample per second")
        need(self.samples < SAMPLE_LIMIT and slot["sample_index"] > getattr(self, "last_slot", -1),
             "unique increasing finite owner slots")
        need(type(owner_deadline) in (int, float) and owner_deadline > time.monotonic(),
             "unchanged finite owner deadline")
        deadline = min(now + QUERY_NS, int(owner_deadline * 1e9))
        before = self._now()
        counters = self._stats("p4stats-slot-" + str(slot["sample_index"]), deadline)
        self._time_left(deadline)
        after = self._now()
        self.samples += 1
        self.last_slot = slot["sample_index"]
        self.last_sample_end_ns = after["monotonic_end_ns"]
        result = {"sample_index": slot["sample_index"], "before": before, "after": after,
                  "counters": counters, "owner_observation": slot}
        self.record({"state": "QMP_STATS_SAMPLE", **result})
        return result

    def sample(self, slot, owner_deadline):
        try:
            return self._sample(slot, owner_deadline)
        except BaseException as error:
            self._abort(error)
            raise

    def drain_events(self, owner_deadline):
        """Bounded, nonblocking event receipt on the original connection."""
        deadline = min(time.monotonic_ns() + QUERY_NS, int(owner_deadline * 1e9))
        try:
            if self.terminal_announced:
                # Do not mistake a legitimate post-SHUTDOWN socket close for
                # process exit; the caller still awaits its original PIDFD.
                return
            # The controller's earlier poll may race with this exact PIDFD.
            # Before reading a new frame, defer only an authenticated exit (or
            # exact proc/socket disappearance together with that exit) to
            # finish(). No response/event parse failure is covered here.
            try:
                self._guard()
            except OriginalProcessExited:
                return
            except OSError as error:
                if error.errno in (errno.ENOENT, errno.ESRCH) and self.poll.poll(0):
                    return
                raise
            for _ in range(FRAME_COUNT):
                value = self._recv_frame(deadline, nonblocking=True, allow_eof=True)
                if value is None:
                    if self.eof:
                        need(bool(self.poll.poll(0)), "EOF only with original process exit or terminal drain")
                    return
                need("event" in value, "no unsolicited response outside an outstanding request")
                self._event(value, allow_resume=self.resume_count == 0)
                if self.terminal_announced:
                    return
            need(not self.pending and not select.select([self.s], [], [], 0)[0], "finite asynchronous QMP event count")
        except BaseException as error:
            self._abort(error)
            raise

    def finish(self):
        """Only the original PIDFD exit permits terminal event/EOF draining."""
        deadline = time.monotonic_ns() + QUERY_NS
        try:
            need(bool(self.poll.poll(0)), "original QEMU PIDFD exit before terminal drain")
            need(not self.failed and not self.closed, "live continuous observation through terminal boundary")
            for _ in range(FRAME_COUNT):
                value = self._recv_frame(deadline, allow_eof=True)
                if value is None and self.eof:
                    self.coverage["completed_to_original_exit"] = True
                    self.record({"state": "QMP_STATS_COMPLETE", "coverage": dict(self.coverage),
                        "runtime_samples": self.samples, "raw_wire_bytes": self.wire_bytes})
                    return dict(self.coverage)
                need("event" in value, "only final events before original EOF")
                self._event(value, allow_resume=self.resume_count == 0, terminal=True)
            raise RuntimeError("finite terminal QMP event count")
        except BaseException:
            self.failed = True
            raise
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        stream, self.s = self.s, None
        held, self.cpu_fds = self.cpu_fds, []
        errors = []
        if stream is not None:
            try:
                stream.close()
            except BaseException as error:
                errors.append(error)
        for _, fd in held:
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        if errors:
            self.failed = True
            raise RuntimeError("owned QMP descriptor close failure(s): " + repr(errors)) from errors[0]

    def _abort(self, error):
        self.failed = True
        try:
            self.close()
        except BaseException as close_error:
            error.add_note("additional owned descriptor cleanup failure: " + repr(close_error))


def start_exact_owned_cpu(socket_path, pid, pidfd, observer, record, cpu_observer, profile, profile_sha):
    return OwnedStatsSession(socket_path, pid, pidfd, observer, record, cpu_observer, profile, profile_sha)
