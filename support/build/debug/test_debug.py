#!/usr/bin/env python3
"""Small host-only checks for debug socket ownership and acceptance failures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SPEC = importlib.util.spec_from_file_location("a01_debug", Path(__file__).with_name("run.py"))
DEBUG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEBUG)


class DebugTests(unittest.TestCase):
    def elf_fixture(self, path, code, *, machine=62, kind=2):
        entry, offset = 0xffffffff80001000, 4096
        raw = bytearray(offset + len(code))
        raw[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                               kind, machine, 1, entry, 64, 0, 0, 64, 56, 1, 64, 0, 0)
        raw[64:120] = struct.pack("<IIQQQQQQ", 1, 5, offset, entry, entry,
                                  len(code), len(code), 4096)
        raw[offset:] = code
        path.write_bytes(raw)
        return entry

    def test_entry_binding_uses_executable_load_bytes_and_recorded_boot_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, boot = root / "symbols", root / "boot.elf"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            entry = self.elf_fixture(original, code)
            self.elf_fixture(boot, code, machine=3)
            ready = {"cwd": str(root), "artifacts": {"-kernel": {
                "path": "boot.elf", "size": boot.stat().st_size,
                "sha256": DEBUG.sha256(boot)}}}
            binding = DEBUG.bind_entry_artifacts(original, ready, entry)
            self.assertEqual(binding["expected_bytes"], code.hex())
            self.assertEqual(binding["boot_artifact"]["sha256"], DEBUG.sha256(boot))
            self.assertEqual(binding["symbol_artifact"]["sha256"], DEBUG.sha256(original))
            self.elf_fixture(boot, bytes(reversed(code)), machine=3)
            # Even an updated, internally consistent QEMU record cannot make
            # different symbol/boot instructions pass this binding.
            ready["artifacts"]["-kernel"]["sha256"] = DEBUG.sha256(boot)
            with self.assertRaisesRegex(ValueError, "different Rust entry bytes"):
                DEBUG.bind_entry_artifacts(original, ready, entry)
            self.elf_fixture(boot, code, machine=3)
            with self.assertRaisesRegex(ValueError, "changed after QEMU"):
                DEBUG.bind_entry_artifacts(original, ready, entry)

    def test_entry_binding_rejects_wrong_type_machine_and_truncated_elf(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry.elf"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            for machine, kind in [(3, 2), (62, 1)]:
                entry = self.elf_fixture(path, code, machine=machine, kind=kind)
                with self.subTest(machine=machine, kind=kind), self.assertRaises(ValueError):
                    DEBUG.elf_entry_bytes(path, entry, 62)
            entry = self.elf_fixture(path, code)
            valid = path.read_bytes()
            for broken in [valid[:63], valid[:119], valid[:-1], valid[:4] + b"\x01" + valid[5:]]:
                path.write_bytes(broken)
                with self.subTest(size=len(broken)), self.assertRaises(ValueError):
                    DEBUG.elf_entry_bytes(path, entry, 62)

    def test_listener_stays_reserved_and_survives_explicit_fd_handoff(self):
        with DEBUG.own_listener() as listener:
            self.assertGreaterEqual(listener.fileno(), 64)
            self.assertEqual(listener.getsockname()[0], "127.0.0.1")
            with socket.socket() as competitor:
                with self.assertRaises(OSError):
                    competitor.bind(listener.getsockname())
            command = [sys.executable, "-I", "-c",
                       "import socket,sys,json; s=socket.socket(fileno=int(sys.argv[1])); "
                       "print(json.dumps(s.getsockname()))", str(listener.fileno())]
            copied = subprocess.check_output(command, pass_fds=(listener.fileno(),), timeout=5)
            self.assertEqual(json.loads(copied), list(listener.getsockname()))

    def test_readiness_tolerates_partial_json_without_a_probe_connection(self):
        class LiveDriver:
            def exited(self):
                return False
        with tempfile.TemporaryDirectory() as temporary, DEBUG.own_listener() as listener:
            record = Path(temporary) / "qemu.json"
            record.write_text('{"qemu_pid":')
            expected = {"qemu_pid": os.getpid(), "raw_exit_code": None, "timed_out": False,
                        "gdb_listener": {"fd": listener.fileno(), "address": list(listener.getsockname())}}
            timer = threading.Timer(0.05, lambda: record.write_text(json.dumps(expected)))
            timer.start()
            try:
                self.assertEqual(DEBUG.wait_for_qemu(record, LiveDriver(), listener, 2), expected)
                listener.setblocking(False)
                with self.assertRaises(BlockingIOError):
                    listener.accept()
            finally:
                timer.join()
            expected["raw_exit_code"] = 65
            record.write_text(json.dumps(expected))
            with self.assertRaisesRegex(ValueError, "QEMU exited"):
                DEBUG.wait_for_qemu(record, LiveDriver(), listener, 0.2)

    def test_gdb_requires_matching_rust_pc_success_and_detach(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "gdb.log"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            good = ("A01_GDB_RUST_ENTRY_HIT pc=0xffffffff80001000 entry=0xffffffff80001000\n"
                    "A01_GDB_RUST_ENTRY_BYTES pc=0xffffffff80001000 size=32 bytes=" + code.hex()
                    + "\nA01_GDB_DETACHED\n")
            log.write_text(good)
            address = 0xffffffff80001000
            self.assertTrue(DEBUG.accept_gdb(0, log, address, code)["detached"])
            for status, text in [(1, good), (0, "rip 0xfff0\n"),
                                 (0, good.replace("pc=0xffffffff80001000", "pc=0xfff0")),
                                 (0, good.replace("A01_GDB_DETACHED", "")),
                                 (0, good.replace(code.hex(), "ff" * DEBUG.ENTRY_BYTES)),
                                 (0, good.replace("size=32", "size=16")),
                                 (0, good.replace(code.hex(), code.hex()[:-2])),
                                 (0, good + good)]:
                with self.subTest(status=status, text=text):
                    log.write_text(text)
                    with self.assertRaises(ValueError):
                        DEBUG.accept_gdb(status, log, address, code)

    def test_detach_does_not_make_failed_or_changed_boot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = b"retained boot bytes\n"
            (directory / "serial.log").write_bytes(raw)
            (directory / "run-exit-code.txt").write_text("0\n")
            record = {"raw_exit_code": 33, "timed_out": False,
                      "serial_sha256": hashlib.sha256(raw).hexdigest()}
            (directory / "qemu.json").write_text(json.dumps(record))
            self.assertEqual(DEBUG.accept_boot(0, directory)["raw_qemu_exit"], 33)
            with self.assertRaises(ValueError):
                DEBUG.accept_boot(1, directory)
            (directory / "run-exit-code.txt").write_text("1\n")
            with self.assertRaises(ValueError):
                DEBUG.accept_boot(0, directory)
            (directory / "run-exit-code.txt").write_text("0\n")
            for key, value in [("raw_exit_code", 65), ("timed_out", True), ("serial_sha256", "0" * 64)]:
                broken = dict(record, **{key: value})
                (directory / "qemu.json").write_text(json.dumps(broken))
                with self.assertRaises(ValueError):
                    DEBUG.accept_boot(0, directory)

    def test_exited_leader_does_not_leave_term_ignoring_owned_descendant(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            descendant = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"
            child = ("import subprocess,sys,time; from pathlib import Path; "
                     "p=subprocess.Popen([sys.executable,'-I','-c',sys.argv[1]]); "
                     "Path(sys.argv[2]).write_text(str(p.pid)); time.sleep(.15)")
            with (directory / "child.log").open("w") as log:
                owned = DEBUG.OwnedSession([sys.executable, "-I", "-c", child, descendant,
                                           str(directory / "descendant.pid")],
                                          cwd=directory, env=os.environ.copy(), output=log)
                descriptor = None
                try:
                    deadline = time.monotonic() + 5
                    while not (directory / "descendant.pid").exists():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    descriptor = os.pidfd_open(int((directory / "descendant.pid").read_text()))
                    while not owned.exited():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    poller = select.poll()
                    poller.register(descriptor, select.POLLIN)
                    self.assertFalse(poller.poll(0))
                    self.assertEqual(owned.wait(2), 0)
                    self.assertTrue(poller.poll(2000))
                    self.assertEqual(owned.stop(), 0)  # disarmed after its one reap
                finally:
                    owned.stop()
                    if descriptor is not None:
                        os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
