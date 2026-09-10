from __future__ import annotations

import importlib.util
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "platform/linux/adapters.py"
spec = importlib.util.spec_from_file_location("linux_platform_adapters", MODULE)
assert spec is not None and spec.loader is not None
adapters = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapters
spec.loader.exec_module(adapters)


class LinuxPlatformAdapterTests(unittest.TestCase):
    def test_atomic_file_store_publishes_private_digest_bound_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "receipts").mkdir(mode=0o700)
            store = adapters.AtomicFileStore(root)
            receipt = store.write("receipts/current.bin", b"durable-fact")
            path = root / "receipts/current.bin"
            self.assertEqual(path.read_bytes(), b"durable-fact")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(receipt.bytes_written, len(b"durable-fact"))
            self.assertEqual(len(receipt.sha256), 64)
            self.assertFalse(
                any(item.name.startswith(".hepta-tmp-") for item in path.parent.iterdir())
            )

    def test_atomic_file_store_refuses_traversal_symlink_oversize_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = adapters.AtomicFileStore(root, maximum_bytes=4)
            with self.assertRaises(adapters.PathRefused):
                store.write("../escape", b"x")
            with self.assertRaises(adapters.PathRefused):
                store.write("too-large", b"12345")
            with self.assertRaises(adapters.PathRefused):
                store.write("wrong-mode", b"x", mode=0o644)
            outside = root / "outside"
            outside.mkdir()
            (root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                store.write("link/value", b"x")
            self.assertFalse((outside / "value").exists())

    def test_atomic_file_store_requires_preprovisioned_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = adapters.AtomicFileStore(root)
            with self.assertRaises(FileNotFoundError):
                store.write("missing/value", b"x")
            self.assertFalse((root / "missing").exists())

    def test_bounded_reader_rejects_non_regular_parent_symlink_and_growth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe").mkdir()
            (root / "safe/value").write_bytes(b"ok")
            self.assertEqual(
                adapters.read_bounded_regular_file(root, "safe/value", 2), b"ok"
            )
            (root / "link").symlink_to(root / "safe", target_is_directory=True)
            with self.assertRaises(OSError):
                adapters.read_bounded_regular_file(root, "link/value", 2)
            with self.assertRaises(adapters.PathRefused):
                adapters.read_bounded_regular_file(root, "safe/value", 1)
            with self.assertRaises(adapters.PathRefused):
                adapters.read_bounded_regular_file(root, "safe", 10)

    def test_monotonic_clock_and_entropy_are_bounded(self) -> None:
        clock = adapters.MonotonicClock()
        first = clock.now_ns()
        second = clock.now_ns()
        self.assertGreaterEqual(second, first)
        self.assertGreater(clock.deadline_ns(1), 0)
        with self.assertRaises(adapters.DeadlineExpired):
            clock.deadline_ns(0)
        with mock.patch.object(
            adapters.time, "monotonic_ns", return_value=(1 << 63) - 1
        ):
            with self.assertRaisesRegex(adapters.DeadlineExpired, "overflow"):
                adapters.MonotonicClock().deadline_ns(1)
        with mock.patch.object(adapters.time, "monotonic_ns", return_value=1):
            with self.assertRaisesRegex(adapters.PlatformError, "regressed"):
                adapters.MonotonicClock(_last_ns=2).now_ns()
        value = adapters.OsEntropy.read(32)
        self.assertEqual(len(value), 32)
        self.assertNotEqual(value, bytes(32))
        with self.assertRaises(adapters.PlatformError):
            adapters.OsEntropy.read(0)
        with self.assertRaises(adapters.PlatformError):
            adapters.OsEntropy.read(adapters.MAX_ENTROPY_BYTES + 1)

    def test_process_identity_fixture_requires_uniform_ids_and_one_cgroup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            pid = 4242
            process = proc / str(pid)
            process.mkdir()
            (process / "status").write_text(
                "Uid:\t1000\t1000\t1000\t1000\n"
                "Gid:\t1001\t1001\t1001\t1001\n",
                encoding="utf-8",
            )
            fields = ["S"] * 20
            fields[19] = "987654"
            (process / "stat").write_text(
                f"{pid} (fixture name) {' '.join(fields)}\n", encoding="utf-8"
            )
            (process / "cgroup").write_text(
                "0::/system.slice/hepta-agent.service\n", encoding="utf-8"
            )
            identity = adapters.read_process_identity(pid, proc)
            self.assertEqual(identity.uid, 1000)
            self.assertEqual(identity.gid, 1001)
            self.assertEqual(identity.start_time_ticks, 987654)
            self.assertEqual(identity.systemd_unit, "hepta-agent.service")
            (process / "status").write_text(
                "Uid:\t1000\t0\t1000\t1000\n"
                "Gid:\t1001\t1001\t1001\t1001\n",
                encoding="utf-8",
            )
            with self.assertRaises(adapters.IdentityRefused):
                adapters.read_process_identity(pid, proc)

    def test_process_identity_rejects_duplicate_cgroup_and_unsafe_path(self) -> None:
        for value in (
            "0::/one\n0::/two\n",
            "0::/safe/../escape\n",
            "2:cpu:/legacy\n",
        ):
            with self.subTest(value=value), self.assertRaises(
                adapters.IdentityRefused
            ):
                adapters._parse_cgroup(value)

    def test_https_and_connected_peer_policy_fail_closed(self) -> None:
        target = adapters.validate_external_https("https://example.test/path")
        self.assertEqual(target.origin, "https://example.test")
        for value in (
            "http://example.test/",
            "https://user@example.test/",
            "https://localhost/",
            "https://example.test:99999/",
            "https://example.test\\evil/",
            "https://-bad.example/",
            "https://例子.example/",
            "https://127.0.0.1/",
        ):
            with self.subTest(value=value), self.assertRaises(adapters.NetworkRefused):
                adapters.validate_external_https(value)
        peer, approved = adapters.bind_connected_peer(
            ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"],
            "93.184.216.34",
        )
        self.assertEqual(peer, "93.184.216.34")
        self.assertIn(peer, approved)
        for address in (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "::1",
            "fe80::1",
            "224.0.0.1",
            "0.0.0.0",
        ):
            with self.subTest(address=address), self.assertRaises(
                adapters.NetworkRefused
            ):
                adapters.globally_routable(address)
        with self.assertRaises(adapters.NetworkRefused):
            adapters.bind_connected_peer(["93.184.216.34"], "1.1.1.1")

    def test_redirect_chain_is_bounded_and_each_hop_revalidated(self) -> None:
        chain = adapters.validate_redirect_chain(
            ["https://one.example/", "https://two.example/path"]
        )
        self.assertEqual(len(chain), 2)
        with self.assertRaises(adapters.NetworkRefused):
            adapters.validate_redirect_chain([])
        with self.assertRaises(adapters.NetworkRefused):
            adapters.validate_redirect_chain(
                ["https://example.test/"] * (adapters.MAX_REDIRECTS + 2)
            )
        with self.assertRaises(adapters.NetworkRefused):
            adapters.validate_redirect_chain(
                ["https://example.test/", "http://downgrade.example/"]
            )

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Linux SO_PEERCRED required")
    def test_wayland_endpoint_binds_directory_socket_and_peer_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            os.chmod(runtime, 0o700)
            endpoint = runtime / "wayland-test"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(endpoint))
            server.listen(1)
            accepted: list[socket.socket] = []

            def accept_once() -> None:
                connection, _ = server.accept()
                accepted.append(connection)

            thread = threading.Thread(target=accept_once)
            thread.start()
            client, peer = adapters.connect_wayland_endpoint(
                runtime, "wayland-test", os.getuid(), timeout_seconds=2.0
            )
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(peer.peer_uid, os.getuid())
            client.close()
            for connection in accepted:
                connection.close()
            server.close()

    def test_wayland_endpoint_rejects_unsafe_directory_or_display(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            os.chmod(runtime, 0o755)
            with self.assertRaises(adapters.IdentityRefused):
                adapters.connect_wayland_endpoint(
                    runtime, "wayland-test", os.getuid(), timeout_seconds=0.1
                )
            for display in ("", "../socket", "nested/socket"):
                with self.subTest(display=display), self.assertRaises(
                    adapters.PathRefused
                ):
                    adapters.connect_wayland_endpoint(
                        runtime, display, os.getuid(), timeout_seconds=0.1
                    )
            os.chmod(runtime, 0o700)
            (runtime / "not-a-socket").write_text("x", encoding="utf-8")
            with self.assertRaises(adapters.PathRefused):
                adapters.connect_wayland_endpoint(
                    runtime, "not-a-socket", os.getuid(), timeout_seconds=0.1
                )


    def test_bounded_reader_rejects_fifo_without_blocking_and_reads_procfs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "blocked-fifo")
            child = "\n".join(
                [
                    "from pathlib import Path",
                    "import importlib.util, sys",
                    "spec = importlib.util.spec_from_file_location('s09_fifo_child', sys.argv[1])",
                    "module = importlib.util.module_from_spec(spec)",
                    "sys.modules[spec.name] = module",
                    "spec.loader.exec_module(module)",
                    "try:",
                    "    module.read_bounded_regular_file(Path(sys.argv[2]), 'blocked-fifo', 1)",
                    "except module.PathRefused:",
                    "    raise SystemExit(0)",
                    "raise SystemExit(3)",
                ]
            )
            completed = subprocess.run(
                [sys.executable, "-c", child, str(MODULE), str(root)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2.0,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
        proc = Path("/proc") / str(os.getpid())
        if (proc / "status").exists():
            value = adapters.read_bounded_regular_file(
                proc, "status", adapters.MAX_PROC_STATUS_BYTES
            )
            self.assertIn(b"Uid:", value)

    @unittest.skipUnless(
        hasattr(os, "O_PATH") and hasattr(socket, "SO_PEERCRED"),
        "Linux O_PATH and SO_PEERCRED required",
    )
    def test_wayland_connection_remains_bound_across_endpoint_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            os.chmod(runtime, 0o700)
            endpoint = runtime / "wayland-test"
            original_path = runtime / "wayland-original"
            alternate_path = runtime / "wayland-alternate"
            original_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            alternate_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            original_server.bind(str(endpoint))
            original_server.listen(1)
            alternate_server.bind(str(alternate_path))
            alternate_server.listen(1)
            real_connect = socket.socket.connect
            replaced = False

            def replace_then_connect(client: socket.socket, address: object) -> object:
                nonlocal replaced
                if not replaced:
                    endpoint.rename(original_path)
                    endpoint.symlink_to(alternate_path.name)
                    replaced = True
                return real_connect(client, address)

            with mock.patch.object(socket.socket, "connect", new=replace_then_connect):
                client, peer = adapters.connect_wayland_endpoint(
                    runtime, "wayland-test", os.getuid(), timeout_seconds=2.0
                )
            original_server.settimeout(1.0)
            accepted, _ = original_server.accept()
            alternate_server.settimeout(0.1)
            with self.assertRaises(socket.timeout):
                alternate_server.accept()
            self.assertEqual(peer.endpoint_inode, original_path.stat().st_ino)
            client.close()
            accepted.close()
            original_server.close()
            alternate_server.close()

    @unittest.skipUnless(
        hasattr(os, "O_PATH") and hasattr(socket, "SO_PEERCRED"),
        "Linux O_PATH and SO_PEERCRED required",
    )
    def test_wayland_connection_remains_bound_across_directory_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            runtime = parent / "runtime"
            original_runtime = parent / "runtime-original"
            runtime.mkdir(mode=0o700)
            endpoint = runtime / "wayland-test"
            original_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            alternate_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            original_server.bind(str(endpoint))
            original_server.listen(1)
            real_connect = socket.socket.connect
            replaced = False

            def replace_then_connect(client: socket.socket, address: object) -> object:
                nonlocal replaced
                if not replaced:
                    runtime.rename(original_runtime)
                    runtime.mkdir(mode=0o700)
                    alternate_server.bind(str(runtime / "wayland-test"))
                    alternate_server.listen(1)
                    replaced = True
                return real_connect(client, address)

            with mock.patch.object(socket.socket, "connect", new=replace_then_connect):
                client, peer = adapters.connect_wayland_endpoint(
                    runtime, "wayland-test", os.getuid(), timeout_seconds=2.0
                )
            original_server.settimeout(1.0)
            accepted, _ = original_server.accept()
            alternate_server.settimeout(0.1)
            with self.assertRaises(socket.timeout):
                alternate_server.accept()
            self.assertEqual(
                peer.endpoint_inode,
                (original_runtime / "wayland-test").stat().st_ino,
            )
            self.assertEqual(peer.runtime_inode, original_runtime.stat().st_ino)
            client.close()
            accepted.close()
            original_server.close()
            alternate_server.close()

    def test_literal_url_policy_matches_connected_address_policy(self) -> None:
        for value in ("https://224.0.0.1/", "https://[ff02::1]/"):
            with self.subTest(value=value), self.assertRaises(adapters.NetworkRefused):
                adapters.validate_external_https(value)
        with self.assertRaises(adapters.NetworkRefused):
            adapters.validate_redirect_chain(
                ["https://example.test/", "https://224.0.0.1/"]
            )


if __name__ == "__main__":
    unittest.main()
