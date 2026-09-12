"""D1-only peer custody and bounded failure diagnostics; no product promotion."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "apps/hepta-agent-portd/examples/hepta-agent-d1-fixture.rs"
GUEST = ROOT / "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance"
HOST = ROOT / "tests/qemu/run-d1-boot-test.sh"
COLLECTOR = ROOT / "tools/collect_d1_guest_failure.sh"


class QualificationCustodySourceTests(unittest.TestCase):
    def test_fixed_trusted_path_replaces_forbidden_cross_uid_executable_read(self) -> None:
        source = EXAMPLE.read_text()
        server = source.split("fn run_server()", 1)[1].split("fn inherited_stream_from_stdin", 1)[0]
        self.assertIn('const QUALIFICATION_PEER_EXECUTABLE: &str = "/usr/libexec/hepta-agent-d1-fixture";', source)
        self.assertIn("hash_trusted_executable(QUALIFICATION_PEER_EXECUTABLE)?", server)
        self.assertIn("attest_with_static_executable_digest(peer, &runtime_policy, &executable)?", server)
        self.assertNotIn("attestor.attest(peer, &runtime_policy)", server)
        self.assertNotIn("env::var", server)

    def test_current_peer_and_deadline_are_rechecked_before_dispatch(self) -> None:
        source = EXAMPLE.read_text()
        handler = source.split("impl BrowserRequestHandler for AttestedFixtureHandler", 1)[1].split("fn inherited_stream", 1)[0]
        peer = handler.index("context.peer != self.peer")
        refresh = handler.index(".refresh_snapshot(self.attestor)")
        invoke = handler.index("self.fixture.handle(context, request)")
        self.assertLess(peer, refresh)
        self.assertLess(refresh, invoke)
        self.assertEqual(handler.count("self.fixture.handle("), 1)
        self.assertIn("context.remaining()?", handler[refresh:invoke])
        server = source.split("fn run_server()", 1)[1].split("/// Private qualification adapter", 1)[0]
        after_response = server.split("let evidence = serve_one", 1)[1]
        self.assertNotIn("refresh_snapshot", after_response)

    def test_product_graph_and_privileges_remain_unchanged(self) -> None:
        product = (ROOT / "apps/hepta-agent-portd/src/main.rs").read_text()
        self.assertNotIn("attest_with_static_executable_digest", product)
        self.assertNotIn("AttestedFixtureHandler", product)
        unit = (ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service").read_text()
        self.assertIn("User=hepta-browserd", unit)
        self.assertIn("CapabilityBoundingSet=\n", unit)
        self.assertIn("AmbientCapabilities=\n", unit)
        self.assertNotIn("CAP_SYS_PTRACE", unit)

    def test_guest_captures_fixed_bounded_journal_before_failure_poweroff(self) -> None:
        source = GUEST.read_text()
        capture = source.split("capture_agent_diagnostics() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("--lines=160", capture)
        self.assertIn("head -c 65536", capture)
        self.assertIn("--kill-after=1s 5s journalctl", capture)
        self.assertIn("-u hepta-agent.service", capture)
        failure = source.split("fail() {", 1)[1].split("\n}", 1)[0]
        self.assertLess(failure.index("capture_agent_diagnostics"), failure.index("poweroff"))
        self.assertIn('"status":"FAIL"', failure)
        self.assertIn("exit 1", failure)

    def test_host_extracts_failure_diagnostics_before_preserving_failure(self) -> None:
        source = HOST.read_text()
        start = source.index("qemu_status=$?")
        collection = source.index("tools/collect_d1_guest_failure.sh", start)
        refusal = source.index('echo "QEMU D1 acceptance exited', start)
        self.assertLess(collection, refusal)
        self.assertIn("|| true", source[collection:refusal])
        self.assertIn("exit 1", source[refusal:])
        self.assertIn("guest reported a D1 acceptance failure", source)

    def test_scripts_remain_syntactically_valid(self) -> None:
        for path in (GUEST, HOST, COLLECTOR):
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)


class BoundedGuestDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.output = self.root / "output"
        self.output.mkdir()
        self.image = self.root / "guest.ext4"
        self.image.write_bytes(b"test-only mock image")
        self.debugfs = self.bin / "debugfs"
        self.log = self.root / "commands"
        self.set_debugfs('printf \'{"status":"FAIL","reason":"test"}\\n\'')
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], COMMAND_LOG=str(self.log))

    def set_debugfs(self, body: str) -> None:
        self.debugfs.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n' + body + '\n')
        self.debugfs.chmod(0o755)

    def run_collector(self, image: Path | None = None, output: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(COLLECTOR), str(image or self.image), str(output or self.output)],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_only_two_fixed_paths_are_exported_as_diagnostics(self) -> None:
        result = self.run_collector()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),
                         ["failure-acceptance.json", "failure-agent-port-journal.txt"])
        commands = self.log.read_text().splitlines()
        self.assertEqual(len(commands), 2)
        self.assertIn("cat /var/lib/trillionnium-d1/acceptance.json", commands[0])
        self.assertIn("cat /var/lib/trillionnium-d1/agent-port-journal.txt", commands[1])
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in self.output.iterdir()))
        self.assertFalse((self.output / "acceptance.json").exists())

    def test_oversize_content_is_discarded_not_mislabelled_as_complete(self) -> None:
        self.set_debugfs("head -c 70000 /dev/zero")
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_exact_size_bound_is_accepted(self) -> None:
        self.set_debugfs("head -c 65536 /dev/zero")
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(len(list(self.output.iterdir())), 2)
        self.assertTrue(all(p.stat().st_size == 65536 for p in self.output.iterdir()))

    def test_empty_or_missing_guest_file_is_omitted(self) -> None:
        self.set_debugfs("exit 0")
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_partial_read_with_failure_is_omitted(self) -> None:
        self.set_debugfs("printf partial; exit 1")
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_current_data_cannot_leave_stale_diagnostics(self) -> None:
        self.run_collector()
        self.assertEqual(len(list(self.output.iterdir())), 2)
        self.set_debugfs("exit 0")
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_collector_does_not_modify_the_image(self) -> None:
        original = self.image.read_bytes()
        self.run_collector()
        self.assertEqual(self.image.read_bytes(), original)
        self.assertNotIn(" -w ", self.log.read_text())

    def test_symlink_image_is_rejected_without_running_debugfs(self) -> None:
        alias = self.root / "alias.ext4"
        alias.symlink_to(self.image)
        self.assertEqual(self.run_collector(image=alias).returncode, 2)
        self.assertFalse(self.log.exists())

    def test_symlink_destination_is_rejected_without_running_debugfs(self) -> None:
        alias = self.root / "alias-output"
        alias.symlink_to(self.output, target_is_directory=True)
        self.assertEqual(self.run_collector(output=alias).returncode, 2)
        self.assertFalse(self.log.exists())

    def test_directory_image_is_rejected(self) -> None:
        self.assertEqual(self.run_collector(image=self.bin).returncode, 2)

    def test_each_debugfs_call_is_time_bounded(self) -> None:
        timeout = self.bin / "timeout"
        timeout.write_text('#!/bin/bash\n[ "$1" = --signal=TERM ] && [ "$2" = --kill-after=1s ] && [ "$3" = 5s ] || exit 99\nexit 124\n')
        timeout.chmod(0o755)
        self.assertEqual(self.run_collector().returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
