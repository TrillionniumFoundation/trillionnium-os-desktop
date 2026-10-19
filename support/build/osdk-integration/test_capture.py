"""Verify capture input boundaries without running GDB or a VM."""
import importlib.util
import os
from pathlib import Path
import signal
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("a01_capture", Path(__file__).with_name("capture.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def test_shutdown_during_spawn_waits_until_child_owner_is_published(self):
        original = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        for number in original:
            owner = None
            with capture.interruption_handlers():
                with self.assertRaises(capture.CaptureInterrupted) as interrupted:
                    with capture.publish_child():
                        os.kill(os.getpid(), number)
                        owner = object()
                self.assertIsNotNone(owner)
                self.assertEqual(interrupted.exception.signum, number)
            self.assertEqual({number: signal.getsignal(number) for number in original}, original)

    def test_only_the_exact_original_poweroff_symbol_resolves(self):
        address = capture.resolved_address("1234 T unrelated\nffffffff88001000 T " + capture.SYMBOL + "\n")
        self.assertEqual(address, 0xffffffff88001000)
        for text in ("1234 T unrelated", "0 T " + capture.SYMBOL,
                     "1234 T " + capture.SYMBOL + "\n5678 T " + capture.SYMBOL):
            with self.subTest(text=text), self.assertRaises(ValueError):
                capture.resolved_address(text)

    def test_qemu_wrapped_machine_id_cannot_be_used_as_original_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "symbols"
            header = bytearray(64)
            header[:6] = b"\x7fELF\x02\x01"
            header[18:20] = (62).to_bytes(2, "little")
            path.write_bytes(header)
            capture.verify_symbol_elf(path)
            header[18:20] = (3).to_bytes(2, "little")
            path.write_bytes(header)
            with self.assertRaises(ValueError):
                capture.verify_symbol_elf(path)

    def test_generated_gdb_python_is_syntactically_complete(self):
        settings = {"endpoint": "127.0.0.1:12345", "symbol": capture.SYMBOL,
                    "address": "0xffffffff88001000", "serial": "/owned/serial.log",
                    "raw": "/owned/fresh.profraw", "observations": "/owned/observations.json",
                    "prefix": "/owned/prefix.log"}
        script = capture.gdb_script(settings)
        python = script.split("python\n", 1)[1].rsplit("\nend\n", 1)[0]
        compile(python, "generated-capture.gdb", "exec")
        self.assertIn("gdb.BP_HARDWARE_BREAKPOINT", script)
        self.assertIn('gdb.execute("detach")', script)


if __name__ == "__main__":
    unittest.main()
