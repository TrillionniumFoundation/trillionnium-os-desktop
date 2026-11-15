"""Actual Unix-socket/PIDFD tests; fake QMP data never establishes VM fitness."""
import copy
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("p4_qmp", HERE / "owned_qmp_gate.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
SCHEMA = [{"provider": "kvm", "target": "vcpu", "stats": [
    {"name": name, "type": "cumulative", "exponent": 0} for name in q.NAMES]}]
PROFILE = {"schema": "p4-kvm-two-counter-profile-v1",
    "qemu": {"bytes": 1, "sha256": "1" * 64, "package": "test-fixture-not-QEMU"},
    "host": {"release": "fixture", "version": "fixture", "boot_id": "fixture"},
    "source_evidence": {k: "2" * 64 for k in ("qemu_distribution_source_sha256",
        "qemu_distribution_patchset_sha256", "host_kvm_counter_definitions_sha256")},
    "expected_schema": SCHEMA}
PROFILE_SHA = hashlib.sha256(q.canonical(PROFILE)).hexdigest()
PATHS = ["/machine/unattached/device[0]", "/machine/unattached/device[2]"]
TIMINGS = []


def fixture_values(n):
    return [{"provider": "kvm", "qom-path": p, "stats": [
        {"name": "exits", "value": 100 + n}, {"name": "io_exits", "value": 10 + n}]}
        for p in PATHS]


def serve(path, mode, ready, stop, commands):
    workers_stop = threading.Event()
    tids = []
    def worker():
        tids.append(threading.get_native_id())
        workers_stop.wait(3)
    workers = [threading.Thread(target=worker) for _ in range(2)]
    for t in workers:
        t.start()
    while len(tids) != 2:
        time.sleep(.001)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, 0o600)
    server.listen(1)
    server.settimeout(3)
    ready.set()
    try:
        client, _ = server.accept()
        client.settimeout(3)
        def send(obj):
            client.sendall(q.canonical(obj) + b"\r\n")
        def event(name):
            row = {"event": name, "timestamp": {"seconds": 1, "microseconds": 2}}
            if name == "SHUTDOWN":
                row["data"] = {"guest": True, "reason": "guest-shutdown"}
            return row
        send({"QMP": {"version": {"qemu": {"major": 10, "minor": 2, "micro": 1},
              "package": "test-fixture-not-QEMU"}, "capabilities": ["oob"]}})
        pending = b""
        while True:
            while b"\n" not in pending:
                data = client.recv(4096)
                if not data:
                    return
                pending += data
            raw, pending = pending.split(b"\n", 1)
            cmd = json.loads(raw)
            commands.put(cmd)
            name, ident = cmd["execute"], cmd["id"]
            if name == "qmp_capabilities":
                value = {}
            elif name == "query-status":
                value = {"running": False, "status": "prelaunch"}
            elif name == "query-cpus-fast":
                value = [{"cpu-index": i, "thread-id": tids[i], "qom-path": PATHS[i],
                          "target": "x86_64"} for i in range(2)]
            elif name == "query-stats-schemas":
                value = copy.deepcopy(SCHEMA)
                if mode == "wrong_schema":
                    value[0]["stats"][0]["exponent"] = 1
            elif name == "query-stats":
                assert cmd["arguments"] == {"target": "vcpu", "providers": [{"provider": "kvm", "names": ["exits", "io_exits"]}], "vcpus": PATHS}
                runtime = ident != "p4stats-baseline-once"
                value = fixture_values(1 if runtime else 0)
                if runtime:
                    if mode in ("no_reply", "truncated"):
                        if mode == "truncated":
                            client.sendall(b'{"return":')
                        stop.wait(2)
                        return
                    if mode == "oversize":
                        client.sendall(b'{"return":"' + b"x" * 17000 + b'"}\n')
                        return
                    if mode == "duplicate_json":
                        client.sendall(('{"id":' + json.dumps(ident) + ',"return":[],"return":[]}\n').encode())
                        return
                    if mode == "nonfinite":
                        client.sendall(('{"id":' + json.dumps(ident) + ',"return":NaN}\n').encode())
                        return
                    if mode == "stop_event":
                        send(event("STOP"))
                    if mode in ("shutdown_guest_int", "shutdown_guest_float"):
                        bad_event = event("SHUTDOWN")
                        bad_event["data"]["guest"] = 1 if mode == "shutdown_guest_int" else 1.0
                        send(bad_event)
                    if mode == "socket_mode_changed":
                        os.chmod(path, 0o666)
                    if mode == "bool":
                        value[0]["stats"][0]["value"] = True
                    if mode == "negative":
                        value[0]["stats"][0]["value"] = -1
                    if mode == "overflow":
                        value[0]["stats"][0]["value"] = 2**64
                    if mode == "rollback":
                        value[0]["stats"][0]["value"] = 99
                    if mode == "duplicate_qom":
                        value[1]["qom-path"] = PATHS[0]
                    if mode == "wrong_provider":
                        value[0]["provider"] = "cryptodev"
                    if mode == "unknown_counter":
                        value[0]["stats"][0]["name"] = "not_requested"
                    if mode == "duplicate_counter":
                        value[0]["stats"][1]["name"] = "exits"
            elif name == "cont":
                send(event("RESUME"))
                value = {}
            else:
                raise AssertionError(name)
            send({"id": ident, "return": value})
            if ident.startswith("p4stats-slot-"):
                stop.wait(2)
                send(event("SHUTDOWN"))
                if mode == "delayed_shutdown":
                    time.sleep(.4)
                if mode == "shutdown_then_stop":
                    send(event("STOP"))
                return
    except (BrokenPipeError, ConnectionResetError, socket.timeout):
        pass
    finally:
        workers_stop.set()
        for t in workers:
            t.join()
        server.close()


class Fixture:
    def __init__(self, mode="good", bad_birth=False, wrong_pid=False):
        self.root = tempfile.TemporaryDirectory(prefix="p4-qmp-")
        self.path = str(Path(self.root.name) / "qmp.sock")
        ctx = mp.get_context("fork")
        self.ready, self.stop, self.commands = ctx.Event(), ctx.Event(), ctx.Queue()
        self.child = ctx.Process(target=serve, args=(self.path, mode, self.ready, self.stop, self.commands))
        self.child.start()
        if not self.ready.wait(3):
            raise RuntimeError("fixture did not start")
        self.pidfd = os.pidfd_open(self.child.pid)
        self.records = []
        self.session = None
        self.map = None
        self.bad_birth, self.wrong_pid = bad_birth, wrong_pid

    def custody(self):
        return {"pid": self.child.pid, "start_ticks": Path(f"/proc/{self.child.pid}/stat").read_text().rsplit(")", 1)[1].split()[19],
                "InvocationID": "fixture-invocation"}

    def cpu_observer(self, cpus):
        self.map = []
        for row in cpus:
            tid = row["thread-id"]
            p = Path(f"/proc/{self.child.pid}/task/{tid}")
            ticks = (p / "stat").read_text().rsplit(")", 1)[1].split()[19]
            if self.bad_birth:
                ticks = str(int(ticks) + 1)
            self.map.append({"cpu_index": row["cpu-index"], "tid": tid, "start_ticks": ticks,
                "held_proc_identity": q.identity(p.stat()), "actual_Tgid": self.child.pid, "QMP_cpu_info": row})
        return self.map

    def start(self):
        self.session = q.start_exact_owned_cpu(self.path, os.getpid() if self.wrong_pid else self.child.pid,
            self.pidfd, self.custody, self.records.append, self.cpu_observer, PROFILE, PROFILE_SHA)
        return self.session

    def slot(self):
        custody = self.custody()
        return {"sample_index": 2, "sample": {"phase": "running", "pid": self.child.pid,
            "start_ticks": custody["start_ticks"], "invocation": custody["InvocationID"],
            "tasks": [{**r, "schedstat_raw": "1 2 3"} for r in self.map],
            "serial_growth": {"fixture_only": True}}}

    def commands_read(self):
        out = []
        while True:
            try:
                out.append(self.commands.get(timeout=.02))
            except queue.Empty:
                return out

    def close(self):
        if self.session is not None:
            self.session.close()
        self.stop.set()
        self.child.join(3)
        if self.child.is_alive():
            self.child.terminate()
            self.child.join(2)
        assert not self.child.is_alive()
        os.close(self.pidfd)
        self.commands.close()
        self.commands.join_thread()
        self.root.cleanup()


class ActualSocketTests(unittest.TestCase):
    def fixture(self, *args, **kwargs):
        value = Fixture(*args, **kwargs)
        self.addCleanup(value.close)
        return value

    def test_complete_two_cpu_observation_and_terminal_eof(self):
        f = self.fixture()
        s = f.start()
        result = s.sample(f.slot(), time.monotonic() + 2)
        self.assertEqual(result["counters"]["delta"][PATHS[0]], {"exits": 1, "io_exits": 1})
        f.stop.set()
        f.child.join(2)
        self.assertFalse(f.child.is_alive())
        coverage = s.finish()
        self.assertTrue(coverage["completed_to_original_exit"])
        commands = f.commands_read()
        self.assertEqual([c["execute"] for c in commands], ["qmp_capabilities", "query-status", "query-cpus-fast", "query-stats-schemas", "query-stats", "cont", "query-stats"])
        self.assertEqual(s.resume_count, 1)
        self.assertTrue(s.closed)
        wire = [r for r in f.records if r["state"] == "QMP_STATS_WIRE"]
        self.assertTrue(all(r["before"]["monotonic_start_ns"] <= r["after"]["monotonic_end_ns"] for r in wire))
        self.assertLessEqual(sum(len(r["raw_utf8"].encode()) for r in wire), q.TRANSCRIPT_LIMIT)

    def test_peer_pid_failure_sends_no_command(self):
        f = self.fixture(wrong_pid=True)
        with self.assertRaises(RuntimeError):
            f.start()
        self.assertEqual(f.commands_read(), [])

    def test_shutdown_event_before_pidfd_exit_does_not_masquerade_as_exit(self):
        f = self.fixture("delayed_shutdown")
        s = f.start()
        s.sample(f.slot(), time.monotonic() + 2)
        f.stop.set()
        time.sleep(.03)
        self.assertTrue(f.child.is_alive())
        s.drain_events(time.monotonic() + 2)
        self.assertTrue(s.terminal_announced)
        self.assertFalse(s.coverage["completed_to_original_exit"])
        f.child.join(2)
        self.assertFalse(f.child.is_alive())
        self.assertTrue(s.finish()["completed_to_original_exit"])

    def test_changed_task_birth_prevents_stats_and_cont(self):
        f = self.fixture(bad_birth=True)
        with self.assertRaises(RuntimeError):
            f.start()
        self.assertEqual([c["execute"] for c in f.commands_read()], ["qmp_capabilities", "query-status", "query-cpus-fast"])

    def test_wrong_schema_prevents_cont(self):
        f = self.fixture("wrong_schema")
        with self.assertRaises(RuntimeError):
            f.start()
        self.assertNotIn("cont", [c["execute"] for c in f.commands_read()])

    def test_real_socket_timeout_and_partial_frame_are_bounded(self):
        for mode in ("no_reply", "truncated"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                s = f.start()
                before = time.monotonic_ns()
                with self.assertRaises((RuntimeError, TimeoutError)):
                    s.sample(f.slot(), time.monotonic() + 2)
                elapsed = time.monotonic_ns() - before
                TIMINGS.append({"mode": mode, "elapsed_ns": elapsed})
                self.assertLess(elapsed, 750000000)
                self.assertTrue(s.closed)
                self.assertEqual(len([c for c in f.commands_read() if c["execute"] == "cont"]), 1)

    def test_hostile_runtime_frames_fail_closed(self):
        for mode in ("oversize", "duplicate_json", "nonfinite", "stop_event", "socket_mode_changed",
                     "bool", "negative", "overflow", "rollback", "duplicate_qom", "wrong_provider",
                     "unknown_counter", "duplicate_counter", "shutdown_guest_int", "shutdown_guest_float"):
            with self.subTest(mode=mode):
                f = self.fixture(mode)
                s = f.start()
                with self.assertRaises((RuntimeError, ValueError)):
                    s.sample(f.slot(), time.monotonic() + 2)
                self.assertTrue(s.closed)
                self.assertTrue(s.failed)
                self.assertEqual(s.samples, 0)

    def test_unbound_owner_slot_sends_no_runtime_request(self):
        f = self.fixture()
        s = f.start()
        slot = f.slot()
        slot["sample"]["invocation"] = "replacement"
        with self.assertRaises(RuntimeError):
            s.sample(slot, time.monotonic() + 2)
        self.assertEqual(len([c for c in f.commands_read() if c["execute"] == "query-stats"]), 1)
        self.assertTrue(s.closed)

    def test_budget_stops_before_another_request(self):
        f = self.fixture()
        s = f.start()
        s.wire_bytes = q.TRANSCRIPT_LIMIT
        with self.assertRaises(RuntimeError):
            s.sample(f.slot(), time.monotonic() + 2)
        self.assertEqual(len([c for c in f.commands_read() if c["execute"] == "query-stats"]), 1)

    def test_original_pidfd_exit_prevents_runtime_stats(self):
        f = self.fixture()
        s = f.start()
        slot = f.slot()
        f.child.terminate()
        f.child.join(2)
        with self.assertRaises(RuntimeError):
            s.sample(slot, time.monotonic() + 2)
        self.assertTrue(s.closed)

    def test_one_close_error_does_not_leak_other_owned_descriptors(self):
        f = self.fixture()
        s = f.start()
        first, second = [fd for _, fd in s.cpu_fds]
        os.close(first)
        with self.assertRaises(RuntimeError):
            s.close()
        with self.assertRaises(OSError):
            os.fstat(second)
        self.assertTrue(s.closed)
        self.assertEqual(s.cpu_fds, [])
        self.assertIsNone(s.s)

    def test_exit_before_event_drain_preserves_session_for_terminal_validation(self):
        f = self.fixture()
        s = f.start()
        s.sample(f.slot(), time.monotonic() + 2)
        f.stop.set()
        f.child.join(2)
        self.assertFalse(f.child.is_alive())
        s.drain_events(time.monotonic() + 2)
        self.assertFalse(s.closed)
        self.assertFalse(s.failed)
        self.assertTrue(s.finish()["completed_to_original_exit"])

    def test_exit_deferral_does_not_swallow_queued_invalid_event(self):
        f = self.fixture("shutdown_then_stop")
        s = f.start()
        s.sample(f.slot(), time.monotonic() + 2)
        f.stop.set()
        f.child.join(2)
        s.drain_events(time.monotonic() + 2)
        self.assertFalse(s.closed)
        with self.assertRaises(RuntimeError):
            s.finish()
        self.assertTrue(s.closed)
        self.assertTrue(s.failed)


class SchemaTests(unittest.TestCase):
    def test_profile_requires_frozen_hash_and_source_identities(self):
        q.validate_profile(PROFILE, PROFILE_SHA)
        with self.assertRaises(RuntimeError):
            q.validate_profile(PROFILE, "0" * 64)
        bad = copy.deepcopy(PROFILE)
        bad["source_evidence"] = {}
        with self.assertRaises(RuntimeError):
            q.validate_profile(bad, hashlib.sha256(q.canonical(bad)).hexdigest())

    def test_units_and_descriptor_shapes_are_not_inferred(self):
        for extra in ({"unit": "cycles"}, {"exponent": 1}, {"type": "instant"}, {"unknown": 0}, {"exponent": False}):
            with self.subTest(extra=extra):
                bad = copy.deepcopy(SCHEMA)
                bad[0]["stats"][0].update(extra)
                with self.assertRaises(RuntimeError):
                    q.validate_schema(bad)

    def test_duplicate_target_and_counter_names_rejected(self):
        for bad in (SCHEMA * 2, [{"provider": "kvm", "target": "vcpu", "stats": SCHEMA[0]["stats"] * 2}]):
            with self.assertRaises(RuntimeError):
                q.validate_schema(bad)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"schema": "p4-owned-qmp-stats-host-test-v1", "test_methods": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "actual_socket_deadlines": TIMINGS,
        "real_QEMU_VM_launches": 0, "production_ready": False}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
