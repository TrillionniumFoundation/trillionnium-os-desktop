#!/usr/bin/env python3
"""Pure argument checks for the integration shim; these do not boot guests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
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

    def mock_main(self, timeout=False, raw_exit=0):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "case"
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
            process.wait.return_value = raw_exit
            context = MagicMock()
            context.__enter__.return_value = process
            argv = ["record-qemu.py", "-kernel", "/kernel", "-chardev",
                    "stdio,id=mux,logfile=" + str(incoming_log), "--no-shutdown"]
            with patch.dict(os.environ, {"A01_OSDK_CASE_OUTPUT": str(output),
                                         "A01_OSDK_GUEST_TIMEOUT": "2"}), \
                    patch.object(shim.sys, "argv", argv), \
                    patch.object(shim.shutil, "which", return_value="/qemu"), \
                    patch.object(shim, "file_record", side_effect=lambda p: {"path": str(p)}), \
                    patch.object(shim.subprocess, "check_output", return_value="QEMU mock"), \
                    patch.object(shim.sys, "stdout", MagicMock(buffer=stdout_sink)), \
                    patch.object(shim.sys, "stderr", MagicMock(buffer=stderr_sink)), \
                    patch.object(shim.subprocess, "Popen", return_value=context):
                status = shim.main()
            guest = output / "guests/guest-001"
            record = json.loads((guest / "qemu.json").read_text())
            self.assertEqual((guest / "serial.log").read_text(), incoming_log.read_text())
            self.assertEqual(record["serial_sources"], [str(incoming_log)])
            self.assertIn("--no-shutdown", record["argv"])
            self.assertEqual((guest / "qemu-stdout.log").read_bytes(), stdout)
            self.assertEqual((guest / "qemu-stderr.log").read_bytes(), stderr)
            self.assertEqual(stdout_sink.getvalue(), stdout)
            self.assertEqual(stderr_sink.getvalue(), stderr)
            self.assertEqual(set(record["stream_logs"]), {"stdout", "stderr"})
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


if __name__ == "__main__":
    unittest.main()
