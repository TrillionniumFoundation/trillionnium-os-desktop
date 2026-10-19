#!/usr/bin/env python3
"""Pure argument checks for the integration shim; these do not boot guests."""
import importlib.util
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("record_qemu", Path(__file__).with_name("record-qemu.py"))
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)


class ProfileTests(unittest.TestCase):
    def transform(self, arguments):
        return shim.transform_args(arguments, Path("/case/guest-001"), Path("/upstream/work"))

    def test_debug_and_coverage_semantics_survive(self):
        preserved = ["-kernel", "/kernel.elf", "-initrd", "/init.cpio", "-append", "hello world",
                     "-serial", "chardev:mux", "-monitor", "unix:/tmp/monitor,server,nowait",
                     "-chardev", "stdio,id=mux,mux=on,signal=off,logfile=qemu.log",
                     "-chardev", "socket,path=/tmp/gdb,server=on,wait=off,id=gdb0",
                     "-gdb", "chardev:gdb0", "-S", "--no-shutdown"]
        arguments, logs, _ = self.transform(preserved)
        self.assertEqual(arguments[:len(preserved)], preserved)
        self.assertEqual(logs, [Path("/upstream/work/qemu.log")])

    def test_fixed_profile_removes_conflicts_and_pflash(self):
        arguments, _, removed = self.transform([
            "-kernel", "/kernel", "-machine", "pc", "-cpu", "host", "-accel", "kvm",
            "-enable-kvm", "-m", "8G", "-smp", "8", "-bios", "/other", "-vga", "std",
            "-display", "gtk", "-nographic", "-drive", "if=pflash,file=/firmware",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"])
        for option, expected in (("-machine", "q35"), ("-accel", "tcg"), ("-cpu", "max"),
                                 ("-m", "512M"), ("-smp", "1"), ("-display", "none")):
            self.assertEqual(arguments.count(option), 1)
            self.assertEqual(arguments[arguments.index(option) + 1], expected)
        self.assertNotIn("-enable-kvm", arguments)
        self.assertNotIn("-drive", arguments)
        self.assertEqual(sum(item.startswith("isa-debug-exit") for item in arguments), 1)
        self.assertTrue(removed)

    def test_missing_logfile_is_added_without_replacing_stdio_mux(self):
        arguments, logs, _ = self.transform([
            "-kernel", "/kernel", "-chardev", "stdio,id=mux,mux=on,signal=off",
            "-serial", "chardev:mux", "-monitor", "chardev:mux"])
        self.assertIn("stdio,id=mux,mux=on,signal=off,logfile=/case/guest-001/serial.log", arguments)
        self.assertIn("chardev:mux", arguments)
        self.assertEqual(logs, [Path("/case/guest-001/serial.log")])

    def test_fallback_serial_and_debug_exit(self):
        arguments, _, _ = self.transform(["-kernel", "/kernel"])
        self.assertIn("chardev:a01-record-serial", arguments)
        self.assertIn("isa-debug-exit,iobase=0xf4,iosize=0x04", arguments)

    def test_direct_stdio_serial_uses_recorded_chardev(self):
        arguments, _, _ = self.transform(["-kernel", "/kernel", "-serial", "stdio"])
        self.assertEqual(arguments[arguments.index("-serial") + 1], "chardev:a01-record-serial")

    def test_disk_and_network_fail_explicitly(self):
        for bad in (["-drive", "file=disk.img"], ["-netdev", "user,id=net0"],
                    ["-device", "virtio-net-pci,netdev=net0"], ["-cdrom", "kernel.iso"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.transform(["-kernel", "/kernel", *bad])

    def test_missing_or_multiple_kernel_rejected(self):
        for arguments in ([], ["-kernel"], ["-kernel", "a", "-kernel", "b"]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.transform(arguments)

    def test_escaped_logfile_comma(self):
        arguments = ["-kernel", "/kernel", "-chardev", "stdio,id=mux,logfile=logs/a,,b.log"]
        actual, logs, _ = self.transform(arguments)
        self.assertEqual(actual[:len(arguments)], arguments)
        self.assertEqual(logs, [Path("/upstream/work/logs/a,b.log")])

    def test_guest_allocation_preserves_previous_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = shim.reserve_guest(root)
            marker = first / "serial.log"
            marker.write_text("old")
            second = shim.reserve_guest(root)
            self.assertEqual(second.name, "guest-002")
            self.assertEqual(marker.read_text(), "old")

    def test_private_monitor_fd_is_validated_and_owned(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with socket.create_connection(listener.getsockname()) as client:
                peer, _ = listener.accept()
                with peer:
                    inherited_fd = fcntl.fcntl(client.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
                    arguments = ["-chardev", f"socket,id={shim.MONITOR_CHARDEV_ID},fd={inherited_fd},server=off",
                                 "-monitor", "chardev:" + shim.MONITOR_CHARDEV_ID]
                    controls = shim.local_tcp_controls(arguments)
                    owned, metadata = shim.inherit_monitor_socket(arguments, controls)
                    self.assertEqual(metadata["fd"], inherited_fd)
                    self.assertFalse(metadata["listening"])
                    self.assertEqual(metadata["local"], list(client.getsockname()))
                    self.assertEqual(metadata["peer"], list(client.getpeername()))
                    owned.close()
                    with self.assertRaises(OSError):
                        os.fstat(inherited_fd)

    def test_private_monitor_rejects_listener_and_closes_descriptor(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            inherited_fd = fcntl.fcntl(listener.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
            arguments = ["-chardev", f"socket,id={shim.MONITOR_CHARDEV_ID},fd={inherited_fd},server=off",
                         "-monitor", "chardev:" + shim.MONITOR_CHARDEV_ID]
            controls = shim.local_tcp_controls(arguments)
            with self.assertRaisesRegex(ValueError, "not a listener"):
                shim.inherit_monitor_socket(arguments, controls)
            with self.assertRaises(OSError):
                os.fstat(inherited_fd)

    def test_private_monitor_rejects_low_fd_and_non_ascii_number(self):
        for descriptor in ("0", "3", "63", "-64", "+64", "６４", "2147483648"):
            value = f"socket,id={shim.MONITOR_CHARDEV_ID},fd={descriptor},server=off"
            with self.subTest(value=value), self.assertRaises(ValueError):
                shim.local_tcp_controls(["-chardev", value])
        controls = shim.local_tcp_controls([
            "-chardev", f"socket,id={shim.MONITOR_CHARDEV_ID},fd=64,server=off"])
        self.assertEqual(controls[0]["fd"], 64)

    def test_private_monitor_rejects_duplicate_and_bare_fields(self):
        base = f"socket,id={shim.MONITOR_CHARDEV_ID},fd=64,server=off"
        for value in (base + ",server=on", base + ",server=off", base + ",fd=65",
                      base + ",id=other", base + ",wait", base + ",", base + ",nodelay=on",
                      f"socket,id={shim.MONITOR_CHARDEV_ID},fd=64,server",
                      f"socket,id={shim.MONITOR_CHARDEV_ID},fd=64,fd=65"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                shim.local_tcp_controls(["-chardev", value])

    def test_private_monitor_rejects_unrelated_fd_and_ambiguous_reference(self):
        for value in ("socket,id=other,fd=23,server=off",
                      f"socket,id={shim.MONITOR_CHARDEV_ID},fd=23,server=on",
                      f"socket,id={shim.MONITOR_CHARDEV_ID},fd=23,server=off,host=127.0.0.1",
                      f"socket,id={shim.MONITOR_CHARDEV_ID},fd=2,server=off"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                shim.local_tcp_controls(["-chardev", value])
        for references in ([], ["-monitor", "chardev:" + shim.MONITOR_CHARDEV_ID] * 2):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
                inherited_fd = fcntl.fcntl(stream.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
                controls = [{"kind": "monitor", "handoff": "private-connected-inherited-fd", "fd": inherited_fd}]
                with self.subTest(references=references), self.assertRaisesRegex(ValueError, "unique"):
                    shim.inherit_monitor_socket(references, controls)
                with self.assertRaises(OSError):
                    os.fstat(inherited_fd)

    def mock_main(self, timeout=False, raw_exit=0, local_tcp=False, occupied=False, immediate=False):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "case"
            kernel, firmware = Path(temporary) / "kernel", Path(temporary) / "bios"
            kernel.write_bytes(b"fixture kernel")
            firmware.write_bytes(b"fixture BIOS")
            incoming_log = Path(temporary) / "qemu.log"
            incoming_log.write_text("actual captured serial\n")
            process = MagicMock()
            stdout = b"Hello world from guest kernel!\n"
            stderr = b"qemu: socket: Operation not permitted\n"
            process.stdout = io.BytesIO(stdout)
            process.stderr = io.BytesIO(stderr)
            stdout_sink, stderr_sink = io.BytesIO(), io.BytesIO()
            process.returncode = -9 if timeout else raw_exit
            process.wait.side_effect = [subprocess.TimeoutExpired(["qemu"], 2), -9] if timeout else None
            process.pid = 12345
            if local_tcp and not immediate:
                process.wait.side_effect = [subprocess.TimeoutExpired(["qemu"], 0.05), raw_exit]
            process.wait.return_value = raw_exit
            listener = MagicMock()
            listener.fileno.return_value = 71
            if occupied:
                listener.bind.side_effect = OSError(98, "Address already in use")
            context = MagicMock()
            context.__enter__.return_value = process
            argv = ["record-qemu.py", "-kernel", str(kernel), "-chardev",
                    "stdio,id=mux,logfile=" + str(incoming_log), "--no-shutdown"]
            if local_tcp:
                argv += ["-gdb", "tcp:127.0.0.1:23456", "-S"]
            ready = output / "gdb-ready.json"
            popen = MagicMock(return_value=context)
            with patch.dict(os.environ, {"A01_OSDK_CASE_OUTPUT": str(output),
                                         "A01_OSDK_GUEST_TIMEOUT": "2",
                                         "A01_OSDK_GDB_READY": str(ready),
                                         "A01_OSDK_COVERAGE_GDB": "0",
                                         "A01_OSDK_LOCAL_TCP": "1" if local_tcp else "0",
                                         "A01_OSDK_PROFILE": shim.LOCAL_TCP_PROFILE if local_tcp
                                         else "osdk-native-unix-v1"}), \
                    patch.object(shim.sys, "argv", argv), \
                    patch.object(shim, "FIRMWARE", firmware), \
                    patch.object(shim.socket, "socket", return_value=listener), \
                    patch.object(shim.shutil, "which", return_value="/qemu"), \
                    patch.object(shim, "file_record", side_effect=lambda p: {"path": str(p)}), \
                    patch.object(shim.subprocess, "check_output", return_value="QEMU mock"), \
                    patch.object(shim.sys, "stdout", MagicMock(buffer=stdout_sink)), \
                    patch.object(shim.sys, "stderr", MagicMock(buffer=stderr_sink)), \
                    patch.object(shim.subprocess, "Popen", popen):
                status = shim.main()
            guest = output / "guests/guest-001"
            record = json.loads((guest / "qemu.json").read_text())
            if occupied:
                popen.assert_not_called()
                self.assertFalse(ready.exists())
                listener.close.assert_called_once()
                self.assertIn("Address already in use", record["error"])
                return status, record, process
            self.assertEqual((guest / "serial.log").read_text(), incoming_log.read_text())
            self.assertEqual(record["serial_sources"], [str(incoming_log)])
            self.assertIn("--no-shutdown", record["argv"])
            self.assertEqual((guest / "qemu-stdout.log").read_bytes(), stdout)
            self.assertEqual((guest / "qemu-stderr.log").read_bytes(), stderr)
            self.assertEqual(stdout_sink.getvalue(), stdout)
            self.assertEqual(stderr_sink.getvalue(), stderr)
            self.assertEqual(set(record["stream_logs"]), {"stdout", "stderr"})
            if local_tcp:
                listener.bind.assert_called_once_with(("127.0.0.1", 23456))
                listener.listen.assert_called_once_with(1)
                listener.close.assert_called_once()
                self.assertEqual(popen.call_args.kwargs["pass_fds"], (71,))
                self.assertIn("socket,id=a01-gdb0,fd=71,server=on,wait=off", record["argv"])
                self.assertTrue(record["gdb_listener"]["parent_copy_closed_after_spawn"])
                self.assertFalse(record["gdb_listener"]["bind_close_rebind_gap"])
                if immediate:
                    self.assertFalse(ready.exists())
                    self.assertFalse(record["gdb_readiness"]["ready"])
                else:
                    self.assertTrue(ready.is_file())
                    marker = json.loads(ready.read_text())
                    self.assertEqual(marker["qemu_pid"], 12345)
                    self.assertEqual(marker["profile_id"], shim.LOCAL_TCP_PROFILE)
            else:
                self.assertFalse(ready.exists())
                listener.bind.assert_not_called()
                self.assertEqual(record["profile_id"], "osdk-native-unix-v1")
                self.assertEqual(record["control_transport"], "upstream-original")
            return status, record, process

    def test_coverage_monitor_quit_zero_is_not_remapped(self):
        status, record, process = self.mock_main()
        self.assertEqual(status, 0)
        self.assertEqual(record["raw_exit_code"], 0)
        self.assertFalse(record["timed_out"])
        process.kill.assert_not_called()

    def test_timeout_records_real_killed_status(self):
        status, record, process = self.mock_main(timeout=True)
        self.assertEqual(status, 124)
        self.assertEqual(record["raw_exit_code"], -9)
        self.assertTrue(record["timed_out"])
        process.kill.assert_called_once()

    def test_qemu_failure_retains_stderr_and_exit(self):
        status, record, process = self.mock_main(raw_exit=1)
        self.assertEqual(status, 1)
        self.assertEqual(record["raw_exit_code"], 1)
        process.kill.assert_not_called()

    def test_tcp_profile_rejects_nonloopback_controls(self):
        for option in ("-gdb", "-monitor"):
            for endpoint in ("tcp:0.0.0.0:5000", "tcp::5000", "tcp:localhost:5000",
                             "tcp:192.0.2.1:5000", "tcp:127.0.0.1:0", "tcp:127.0.0.1:65536",
                             "unix:/tmp/socket"):
                with self.subTest(option=option, endpoint=endpoint), self.assertRaises(ValueError):
                    shim.local_tcp_controls([option, endpoint])

    def test_tcp_monitor_remains_client_and_arguments_stay_exact(self):
        requested = ["-gdb", "tcp:127.0.0.1:5000", "-monitor", "chardev:mux",
                     "-monitor", "tcp:127.0.0.1:5001,server=off,wait=off"]
        original = list(requested)
        controls = shim.local_tcp_controls(requested)
        self.assertEqual(requested, original)
        self.assertEqual([control["role"] for control in controls], ["server", "client"])
        for suffix in (",server", ",server=on"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                shim.local_tcp_controls(["-monitor", "tcp:127.0.0.1:5001" + suffix])

    def test_tcp_gdb_readiness_follows_inherited_listener_and_survival(self):
        status, record, _process = self.mock_main(raw_exit=33, local_tcp=True)
        self.assertEqual(status, 33)
        self.assertTrue(record["gdb_readiness"]["ready"])
        self.assertEqual(record["control_transport"], "loopback-tcp")

    def test_occupied_tcp_gdb_does_not_start_qemu_or_signal_ready(self):
        status, record, _process = self.mock_main(local_tcp=True, occupied=True)
        self.assertEqual(status, 125)
        self.assertIsNone(record["raw_exit_code"])

    def test_immediate_qemu_failure_does_not_signal_gdb_ready(self):
        status, record, _process = self.mock_main(raw_exit=1, local_tcp=True, immediate=True)
        self.assertEqual(status, 1)
        self.assertEqual(record["gdb_readiness"]["early_exit_code"], 1)

    def test_tee_drains_bounded_chunks_and_preserves_nontext_bytes(self):
        payload = bytes(range(256)) * 1024
        source, sink = io.BytesIO(payload), io.BytesIO()
        errors = []
        with tempfile.TemporaryFile() as destination:
            shim.tee_stream(source, destination, sink, errors)
            destination.seek(0)
            self.assertEqual(destination.read(), payload)
        self.assertEqual(sink.getvalue(), payload)
        self.assertEqual(errors, [])

    def test_forward_failure_does_not_discard_recorded_stderr(self):
        class BrokenSink:
            def write(self, _chunk):
                raise BrokenPipeError("harness closed stderr")

        payload = b"qemu: socket: Operation not permitted\n" * 4096
        errors = []
        with tempfile.TemporaryFile() as destination:
            shim.tee_stream(io.BytesIO(payload), destination, BrokenSink(), errors)
            destination.seek(0)
            self.assertEqual(destination.read(), payload)
        self.assertEqual(len(errors), 1)


class CaptureTests(unittest.TestCase):
    def fixture(self, root):
        raw = root / "coverage.profraw"
        raw.write_bytes(b"data")
        prefix = b"boot\n#### Coverage: 0x1000 4\n"
        serial = root / "serial.log"
        serial.write_bytes(prefix + b"guest finished\n")
        sidecar = root / "coverage-capture.json"
        symbol = {"path": "/original/symbol.elf", "size": 100, "sha256": "b" * 64}
        data = {"passed": True, "profile_id": shim.CAPTURE_PROFILE, "gdb_exit_code": 0,
                "kernel_sha256": "a" * 64, "guest_record": "guests/guest-001/qemu.json",
                "symbol_elf": symbol,
                "breakpoint": {"symbol": "ostd::arch::power::try_poweroff",
                               "resolved_address": "0x2000", "actual_pc": "0x2000"},
                "announcement": {"address": "0x1000", "size": 4}, "raw": shim.file_record(raw),
                "serial_prefix": {"size": len(prefix), "sha256": hashlib.sha256(prefix).hexdigest()}}
        sidecar.write_text(json.dumps(data))
        metadata = {"raw_exit_code": 0, "timed_out": False}
        record = {"raw_exit_code": 33, "artifacts": {"-kernel": {"sha256": "a" * 64}}}
        return metadata, record, sidecar, serial, raw, symbol, data["guest_record"]

    def test_ephemeral_port_is_explicitly_scoped_to_gdb_capture(self):
        endpoint = ["-gdb", "tcp:127.0.0.1:0"]
        with self.assertRaises(ValueError):
            shim.local_tcp_controls(endpoint)
        self.assertEqual(shim.local_tcp_controls(endpoint, allow_gdb_zero=True)[0]["port"], 0)
        with self.assertRaises(ValueError):
            shim.local_tcp_controls(["-monitor", "tcp:127.0.0.1:0"], allow_gdb_zero=True)

    def test_original_symbol_elf_must_be_64_bit_em62(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original.elf"
            header = b"\x7fELF\x02\x01" + bytes(12) + b"\x3e\x00"
            path.write_bytes(header)
            with patch.dict(os.environ, {"A01_OSDK_COVERAGE_SYMBOL_ELF": str(path)}):
                self.assertEqual(shim.coverage_symbol(Path(temporary)), shim.file_record(path))
                path.write_bytes(header[:18] + b"\x03\x00")
                with self.assertRaises(ValueError):
                    shim.coverage_symbol(Path(temporary))

    def test_finalize_binds_guest_raw_symbols_and_final_serial(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments = self.fixture(Path(temporary))
            shim.finalize_capture(*arguments)
            metadata, _, sidecar, serial, *_ = arguments
            finalized = json.loads(sidecar.read_text())
            self.assertTrue(finalized["finalized"])
            self.assertEqual(finalized["serial_sha256"], shim.file_record(serial)["sha256"])
            self.assertEqual(metadata["sidecar"], shim.file_record(sidecar))

    def test_finalize_rejects_tampered_capture_bindings(self):
        mutations = [("kernel_sha256", None, "c" * 64), ("guest_record", None, "another/qemu.json"),
                     ("symbol_elf", "sha256", "c" * 64), ("breakpoint", "actual_pc", "0x2001"),
                     ("raw", "sha256", "c" * 64), ("announcement", "size", 5),
                     ("serial_prefix", "sha256", "c" * 64), ("profile_id", None, shim.LOCAL_TCP_PROFILE),
                     ("gdb_exit_code", None, 1), ("passed", None, False)]
        for outer, inner, value in mutations:
            with self.subTest(field=(outer, inner)), tempfile.TemporaryDirectory() as temporary:
                arguments = self.fixture(Path(temporary))
                sidecar = arguments[2]
                data = json.loads(sidecar.read_text())
                if inner:
                    data[outer][inner] = value
                else:
                    data[outer] = value
                sidecar.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    shim.finalize_capture(*arguments)

    def test_capture_success_preserves_genuine_qemu_33(self):
        qemu, capture = MagicMock(), MagicMock()
        qemu.poll.side_effect = [None, 33]
        capture.poll.side_effect = [None, 0]
        with patch.object(shim.time, "sleep"):
            self.assertEqual(shim.supervise_capture(qemu, capture, 10), (33, False))
        qemu.kill.assert_not_called()

    def test_capture_failure_cancels_qemu_promptly(self):
        qemu, capture = MagicMock(), MagicMock()
        qemu.poll.return_value, capture.poll.return_value = None, 7
        with patch.object(shim, "stop_capture_child") as stop:
            self.assertEqual(shim.supervise_capture(qemu, capture, 10), (125, False))
        stop.assert_called_once_with(capture)
        qemu.kill.assert_called_once()

    def test_qemu_guest_failure_65_is_preserved(self):
        qemu, capture = MagicMock(), MagicMock()
        qemu.poll.return_value, capture.poll.return_value = 65, None
        with patch.object(shim, "stop_capture_child") as stop:
            self.assertEqual(shim.supervise_capture(qemu, capture, 10), (65, False))
        stop.assert_called_once_with(capture)
        qemu.kill.assert_not_called()

    def test_capture_cleanup_only_signals_unreaped_direct_child(self):
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired(["capture"], 1), -9]
        shim.stop_capture_child(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        reaped = MagicMock()
        reaped.poll.return_value = 7
        shim.stop_capture_child(reaped)
        reaped.terminate.assert_not_called()
        reaped.kill.assert_not_called()
        reaped.wait.assert_called_once_with()

    def test_qemu_failure_cancels_capture_promptly(self):
        qemu, capture = MagicMock(), MagicMock()
        qemu.poll.return_value, capture.poll.return_value = 1, None
        with patch.object(shim, "stop_capture_child") as stop:
            self.assertEqual(shim.supervise_capture(qemu, capture, 10), (1, False))
        stop.assert_called_once_with(capture)

    def test_capture_timeout_cancels_both_owned_children(self):
        qemu, capture = MagicMock(), MagicMock()
        qemu.poll.return_value = capture.poll.return_value = None
        with patch.object(shim.time, "monotonic", side_effect=[0, 0, 5]), \
                patch.object(shim, "stop_capture_child") as stop:
            self.assertEqual(shim.supervise_capture(qemu, capture, 1), (124, True))
        stop.assert_called_once_with(capture)
        qemu.kill.assert_called_once()

    def test_v2_recorder_resolves_port_captures_and_finalizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cwd, output = root / "work", root / "case"
            cwd.mkdir()
            symbol = root / "original.elf"
            symbol.write_bytes(b"\x7fELF\x02\x01" + bytes(12) + b"\x3e\x00")
            kernel, firmware, binary = root / "kernel", root / "bios", root / "qemu"
            for path in (kernel, firmware, binary):
                path.write_bytes(path.name.encode())
            serial = cwd / "qemu.log"
            serial.write_bytes(b"boot\n#### Coverage: 0x1000 4\n")
            process = MagicMock(returncode=33, pid=12345)
            process.stdout, process.stderr = io.BytesIO(b"guest\n"), io.BytesIO()
            process.wait.side_effect = subprocess.TimeoutExpired(["qemu"], 0.05)
            context = MagicMock()
            context.__enter__.return_value = process
            listener = MagicMock()
            listener.fileno.return_value = 71
            listener.getsockname.return_value = ("127.0.0.1", 34567)
            arguments = ["record-qemu.py", "-kernel", str(kernel), "-gdb", "tcp:127.0.0.1:0",
                         "-S", "-chardev", "stdio,id=mux,logfile=" + str(serial)]

            def capture(qemu, command, guest, metadata, _timeout):
                self.assertEqual(command[command.index("--endpoint") + 1], "127.0.0.1:34567")
                copied_symbol = Path(command[command.index("--symbol-elf") + 1])
                self.assertNotEqual(copied_symbol, symbol)
                self.assertEqual(copied_symbol.read_bytes(), symbol.read_bytes())
                raw = cwd / "coverage.profraw"
                raw.write_bytes(b"data")
                sidecar = guest / "coverage-capture.json"
                data = {"passed": True, "profile_id": shim.CAPTURE_PROFILE, "gdb_exit_code": 0,
                        "kernel_sha256": shim.file_record(kernel)["sha256"],
                        "guest_record": "guests/guest-001/qemu.json", "symbol_elf": shim.file_record(copied_symbol),
                        "breakpoint": {"symbol": "ostd::arch::power::try_poweroff",
                                       "resolved_address": "0x2000", "actual_pc": "0x2000"},
                        "announcement": {"address": "0x1000", "size": 4}, "raw": shim.file_record(raw),
                        "serial_prefix": {"size": serial.stat().st_size,
                                          "sha256": shim.file_record(serial)["sha256"]}}
                sidecar.write_text(json.dumps(data))
                metadata.update({"raw_exit_code": 0, "timed_out": False})
                return 33, False

            environment = {"A01_OSDK_CASE_OUTPUT": str(output), "A01_OSDK_LOCAL_TCP": "1",
                           "A01_OSDK_PROFILE": shim.CAPTURE_PROFILE, "A01_OSDK_COVERAGE_GDB": "1",
                           "A01_OSDK_COVERAGE_SYMBOL_ELF": str(symbol), "A01_OSDK_GUEST_TIMEOUT": "2",
                           "A01_OSDK_GDB_READY": str(output / "gdb-ready.json")}
            with patch.dict(os.environ, environment), patch.object(shim.sys, "argv", arguments), \
                    patch.object(shim.Path, "cwd", return_value=cwd), patch.object(shim, "FIRMWARE", firmware), \
                    patch.object(shim.socket, "socket", return_value=listener), \
                    patch.object(shim.shutil, "which", return_value=str(binary)), \
                    patch.object(shim.subprocess, "check_output", return_value="QEMU mock"), \
                    patch.object(shim.sys, "stdout", MagicMock(buffer=io.BytesIO())), \
                    patch.object(shim.sys, "stderr", MagicMock(buffer=io.BytesIO())), \
                    patch.object(shim.subprocess, "Popen", return_value=context), \
                    patch.object(shim, "run_capture", side_effect=capture):
                self.assertEqual(shim.main(), 33)
            record = json.loads((output / "guests/guest-001/qemu.json").read_text())
            self.assertEqual(record["gdb_listener"]["requested_port"], 0)
            self.assertEqual(record["gdb_listener"]["port"], 34567)
            self.assertTrue(record["capture"]["finalized"])
            self.assertTrue(any(item.startswith("isa-debug-exit") for item in record["argv"]))
            marker = json.loads((output / "gdb-ready.json").read_text())
            self.assertEqual(marker["endpoint"]["port"], 34567)


if __name__ == "__main__":
    unittest.main()
