"""Check listener ownership and wrong-endpoint rejection without starting a VM."""
import fcntl
import importlib.util
import os
from pathlib import Path
import socket
import unittest

spec = importlib.util.spec_from_file_location("kernel_qemu_recorder", Path(__file__).resolve().parents[1] / "record-qemu.py")
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


class GdbListenerTests(unittest.TestCase):
    def listener(self, host="127.0.0.1", listen=True):
        original = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(original.close)
        original.bind((host, 0))
        if listen:
            original.listen(1)
        descriptor = fcntl.fcntl(original.fileno(), fcntl.F_DUPFD, 64)
        self.addCleanup(os.close, descriptor)
        return original, descriptor

    def test_owned_listener_is_not_closed_or_rebound_by_argument_adaptation(self):
        listener, descriptor = self.listener()
        port = listener.getsockname()[1]
        inode = os.fstat(descriptor).st_ino
        requested = ["-kernel", "kernel.elf", "-S", "-gdb", f"tcp:127.0.0.1:{port}"]
        actual, inherited, record = recorder.inherit_gdb_listener(requested, str(descriptor))
        self.assertEqual(inherited, (descriptor,))
        self.assertEqual(os.fstat(descriptor).st_ino, inode)
        self.assertEqual(record["address"], ["127.0.0.1", port])
        self.assertEqual(actual[1], "kernel.elf")
        self.assertIn(f"fd={descriptor},server=on,wait=off", actual[-1])
        with socket.socket() as competing:
            with self.assertRaises(OSError):
                competing.bind(listener.getsockname())

    def test_mismatched_endpoint_or_running_guest_request_is_rejected(self):
        listener, descriptor = self.listener()
        endpoint = f"tcp:127.0.0.1:{listener.getsockname()[1]}"
        for args in (["-S", "-gdb", "tcp:127.0.0.1:1"], ["-gdb", endpoint],
                     ["-S", "-gdb", endpoint, "-gdb", endpoint]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                recorder.inherit_gdb_listener(args, descriptor)

    def test_unexpected_address_or_non_listening_socket_is_rejected(self):
        for host, listen in (("127.0.0.2", True), ("127.0.0.1", False)):
            with self.subTest(host=host, listen=listen):
                listener, descriptor = self.listener(host, listen)
                with self.assertRaises(ValueError):
                    recorder.inherit_gdb_listener(["-S", "-gdb", f"tcp:{host}:{listener.getsockname()[1]}"], descriptor)


if __name__ == "__main__":
    unittest.main()
