"""Ordinary owned-file, socketpair and child controls; no namespace/service use."""
import array
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("prefix_control", Path(__file__).with_name("full_prefix_control.py"))
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)

def descriptors():
    return {int(name) for name in os.listdir("/proc/self/fd")
            if os.path.exists("/proc/self/fd/" + name)}

class PrefixControls(unittest.TestCase):
    def setUp(self):
        self.before = descriptors()

    def tearDown(self):
        self.assertEqual(descriptors(), self.before, "control leaked an owned descriptor")

    def test_actual_root_credentials_and_empty_rights(self):
        a, b = target.seqpair()
        try:
            target.send(a, b"exact")
            value, rights, peer = target.receive(b, 64, 0, os.getpid())
            self.assertEqual((value, rights, peer), (b"exact", [], os.getpid()))
        finally:
            a.close(); b.close()

    def test_actual_rights_are_new_cloexec_owned_descriptors(self):
        a, b = target.seqpair()
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        owned = []
        try:
            target.send(a, b"capability", (fd,))
            _, owned, _ = target.receive(b, 64, 1, os.getpid())
            self.assertNotEqual(owned[0], fd)
            self.assertTrue(fcntl.fcntl(owned[0], fcntl.F_GETFD) & fcntl.FD_CLOEXEC)
            self.assertEqual(os.fstat(fd), os.fstat(owned[0]))
        finally:
            for copy in owned: os.close(copy)
            os.close(fd); a.close(); b.close()

    def rejection_does_not_leak(self, maximum=64, count=0, expected_peer=None, payload=b"x", copies=1):
        a, b = target.seqpair()
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        try:
            before = descriptors()
            target.send(a, payload, [fd] * copies)
            with self.assertRaises(RuntimeError):
                target.receive(b, maximum, count, expected_peer)
            self.assertEqual(before, descriptors())
        finally:
            os.close(fd); a.close(); b.close()

    def test_unexpected_rights_are_closed(self):
        self.rejection_does_not_leak()

    def test_wrong_exact_peer_closes_received_rights(self):
        self.rejection_does_not_leak(count=1, expected_peer=os.getpid() + 1)

    def test_payload_truncation_closes_received_rights(self):
        self.rejection_does_not_leak(maximum=1, count=1, payload=b"truncated")

    def test_ancillary_truncation_closes_all_delivered_rights(self):
        self.rejection_does_not_leak(count=1, copies=64)

    def test_malformed_credentials_before_rights_still_closes_rights(self):
        a, b = target.seqpair()
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        duplicate = os.dup(fd)
        class Packet:
            def fileno(self): return b.fileno()
            def recvmsg(self, *args):
                b.recv(1)
                return (b"x", [(socket.SOL_SOCKET, socket.SCM_CREDENTIALS, b"bad"),
                    (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [duplicate]).tobytes())], 0, None)
        try:
            a.send(b"x")
            with self.assertRaises(RuntimeError): target.receive(Packet(), 64, 1)
            with self.assertRaises(OSError): os.fstat(duplicate)
        finally:
            os.close(fd); a.close(); b.close()

    def test_unexpected_cmsg_before_rights_still_closes_rights(self):
        a, b = target.seqpair()
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        duplicate = os.dup(fd)
        class Packet:
            def fileno(self): return b.fileno()
            def recvmsg(self, *args):
                b.recv(1)
                return (b"x", [(socket.SOL_SOCKET, 999, b"bad"),
                    (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [duplicate]).tobytes())], 0, None)
        try:
            a.send(b"x")
            with self.assertRaises(RuntimeError): target.receive(Packet(), 64, 1)
            with self.assertRaises(OSError): os.fstat(duplicate)
        finally:
            os.close(fd); a.close(); b.close()

    def test_finite_empty_packet_timeout(self):
        a, b = target.seqpair()
        try:
            with self.assertRaisesRegex(RuntimeError, "finite packet deadline"):
                target.receive(b, 64, 0, timeout=0.01)
        finally:
            a.close(); b.close()

    def test_current_interpreter_is_bound_by_kernel_exe(self):
        digest = hashlib.sha256(Path("/proc/self/exe").read_bytes()).hexdigest()
        fd = target.current_interpreter(digest)
        try:
            self.assertEqual((os.fstat(fd).st_dev, os.fstat(fd).st_ino),
                             (os.stat("/proc/self/exe").st_dev, os.stat("/proc/self/exe").st_ino))
        finally:
            os.close(fd)

    def test_mutated_artifact_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned"
            path.write_bytes(b"old"); path.chmod(0o600)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            path.write_bytes(b"new")
            with self.assertRaises(RuntimeError): target.pinned(path, digest)

    def test_symlink_artifact_rejected_without_following(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "owned"
            original.write_bytes(b"owned"); original.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(original)
            with self.assertRaises(OSError): target.pinned(link, hashlib.sha256(b"owned").hexdigest())

    def test_hardlinked_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "owned"
            original.write_bytes(b"owned"); original.chmod(0o600)
            os.link(original, Path(directory) / "alias")
            with self.assertRaises(RuntimeError): target.pinned(original, hashlib.sha256(b"owned").hexdigest())

    def test_setid_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "owned"
            original.write_bytes(b"owned"); original.chmod(0o4755)
            with self.assertRaises(RuntimeError): target.pinned(original, hashlib.sha256(b"owned").hexdigest(), True)

    def test_real_owned_child_identity_and_exact_retirement(self):
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(30)"])
        fd = os.pidfd_open(child.pid)
        proc = None
        try:
            value, proc = target.identity(fd)
            self.assertEqual(value["pid"], child.pid)
            self.assertEqual(value["parent"], os.getpid())
            target.safe_stop(child, fd)
            self.assertEqual(child.returncode, -signal.SIGTERM)
            self.assertTrue(target.dead(fd))
            with self.assertRaises(RuntimeError): target.identity(fd)
        finally:
            if proc is not None: os.close(proc)
            target.safe_stop(child, fd); os.close(fd)

if __name__ == "__main__":
    unittest.main(verbosity=2)
