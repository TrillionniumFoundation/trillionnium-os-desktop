"""Actual filesystem/lease regressions; no installed-image or power-loss claim."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s11_custody_tests", ROOT / "platform/update_recovery.py")
assert SPEC is not None and SPEC.loader is not None
s11 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = s11
SPEC.loader.exec_module(s11)


class StateCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "store"
        self.root.mkdir(mode=0o700)
        self.store = s11.AtomicStateStore(self.root)
        self.addCleanup(self.store.close)
        self.store.acquire()

    def test_ancestor_symlink_is_refused(self) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(s11.StateRefused):
            s11.AtomicStateStore(alias / "store")

    def test_noncanonical_and_unbounded_root_paths_are_refused(self) -> None:
        for value in ("relative/store", "/", str(self.root) + "/", str(self.base) + "/./store",
                      str(self.base) + "//store", str(self.base) + "/../store", b"/tmp/store",
                      "/tmp/" + "x" * 4096, "/" + "/".join(["x"] * 65), "/tmp/nu\0ll"):
            with self.subTest(value=str(value)[:80]), self.assertRaises(s11.StateRefused):
                s11.AtomicStateStore(value)

    def test_writable_nonsticky_ancestor_is_refused(self) -> None:
        parent = self.base / "unsafe"
        parent.mkdir(mode=0o777)
        parent.chmod(0o777)
        child = parent / "private"
        child.mkdir(mode=0o700)
        with self.assertRaises(s11.StateRefused):
            s11.AtomicStateStore(child)

    @unittest.skipUnless(os.geteuid() == 0, "requires root to construct foreign ownership")
    def test_foreign_owned_readonly_ancestor_is_refused(self) -> None:
        parent = self.base / "foreign"
        parent.mkdir(mode=0o755)
        child = parent / "private"
        child.mkdir(mode=0o700)
        os.chown(parent, 65534, 65534)
        try:
            with self.assertRaises(s11.StateRefused):
                s11.AtomicStateStore(child)
        finally:
            os.chown(parent, 0, 0)

    def test_root_replacement_permanently_invalidates_existing_handle(self) -> None:
        moved = self.base / "old-store"
        self.root.rename(moved)
        self.root.mkdir(mode=0o700)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {"sequence": 1})
        self.root.rmdir()
        moved.rename(self.root)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {"sequence": 2})
        self.assertFalse((self.root / "state.json").exists())

    def test_directory_mode_drift_is_not_repaired(self) -> None:
        self.root.chmod(0o755)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {})
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)
        self.root.chmod(0o700)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {})

    def test_lock_and_staging_names_cannot_be_written_or_read(self) -> None:
        for name in (".coordinator.lock", ".state.tmp", ".", "..", "state.json/.",
                     "state.json/", "a/../state.json", "", "../x", "/state", "é.json", "a\n", "a\0"):
            with self.subTest(name=name):
                with self.assertRaises(s11.StateRefused):
                    self.store.write(name, {})
                with self.assertRaises(s11.StateRefused):
                    self.store.read(name)
        second = s11.AtomicStateStore(self.root)
        self.addCleanup(second.close)
        with self.assertRaises(s11.CoordinatorBusy):
            second.acquire()

    def test_lock_replacement_invalidates_old_coordinator_before_write(self) -> None:
        lock = self.root / s11.AtomicStateStore.LOCK_NAME
        lock.rename(self.root / ".old-lock")
        lock.touch(mode=0o600)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {})
        self.assertFalse((self.root / "state.json").exists())

    def test_lock_mode_drift_invalidates_writer_without_chmod_repair(self) -> None:
        lock = self.root / s11.AtomicStateStore.LOCK_NAME
        lock.chmod(0o644)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {})
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o644)

    def test_preexisting_nonempty_or_public_lock_is_not_repaired(self) -> None:
        self.store.close()
        lock = self.root / s11.AtomicStateStore.LOCK_NAME
        for content, mode in ((b"not-empty", 0o600), (b"", 0o644)):
            lock.write_bytes(content)
            lock.chmod(mode)
            other = s11.AtomicStateStore(self.root)
            try:
                with self.assertRaises(s11.StateRefused):
                    other.acquire()
                self.assertEqual(lock.read_bytes(), content)
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), mode)
            finally:
                other.close()

    def test_lock_hardlink_is_refused(self) -> None:
        self.store.close()
        lock = self.root / s11.AtomicStateStore.LOCK_NAME
        os.link(lock, self.base / "hardlinked-lock")
        other = s11.AtomicStateStore(self.root)
        try:
            with self.assertRaises(s11.StateRefused):
                other.acquire()
        finally:
            other.close()

    def test_fifo_lock_is_refused_without_blocking(self) -> None:
        self.store.close()
        lock = self.root / s11.AtomicStateStore.LOCK_NAME
        lock.unlink()
        os.mkfifo(lock, 0o600)
        code = '''import importlib.util,sys,pathlib
spec=importlib.util.spec_from_file_location("s11_child",sys.argv[1])
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
s=m.AtomicStateStore(pathlib.Path(sys.argv[2]))
try:
    s.acquire()
except m.StateRefused:
    sys.exit(0)
else:
    sys.exit(3)
finally:
    s.close()
'''
        result = subprocess.run([sys.executable, "-I", "-c", code,
                                 str(ROOT / "platform/update_recovery.py"), str(self.root)],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(stat.S_ISFIFO(lock.stat().st_mode))

    def test_state_symlink_fifo_hardlink_and_public_mode_are_refused(self) -> None:
        leaf = self.root / "state.json"
        outside = self.base / "outside.json"
        outside.write_text('{}')
        outside.chmod(0o600)
        constructors = (
            lambda: leaf.symlink_to(outside),
            lambda: os.mkfifo(leaf, 0o600),
            lambda: os.link(outside, leaf),
            lambda: (leaf.write_text('{}'), leaf.chmod(0o644)),
        )
        for construct in constructors:
            with self.subTest(construct=construct):
                construct()
                with self.assertRaises(s11.RecoveryRequired):
                    self.store.read("state.json")
                with self.assertRaises(s11.StateRefused):
                    self.store.write("state.json", {"replaced": True})
                leaf.unlink()
                self.assertEqual(outside.read_text(), '{}')

    def test_existing_staging_collision_is_preserved(self) -> None:
        value = {"sequence": 1}
        digest = hashlib.sha256(s11._canonical(value)).hexdigest()
        staging = self.root / f".state.json.{os.getpid()}.{digest[:16]}.tmp"
        staging.write_bytes(b"preexisting-forensic-state")
        with self.assertRaises(FileExistsError):
            self.store.write("state.json", value)
        self.assertEqual(staging.read_bytes(), b"preexisting-forensic-state")
        self.assertFalse((self.root / "state.json").exists())

    def test_substituted_staging_inode_is_neither_published_nor_deleted(self) -> None:
        value = {"sequence": 1}
        digest = hashlib.sha256(s11._canonical(value)).hexdigest()
        staging = self.root / f".state.json.{os.getpid()}.{digest[:16]}.tmp"
        def fault(point: str) -> None:
            if point == "after_file_fsync":
                staging.rename(self.root / ".preserved-original")
                staging.write_bytes(b"replacement")
                staging.chmod(0o600)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", value, fault=fault)
        self.assertEqual(staging.read_bytes(), b"replacement")
        self.assertFalse((self.root / "state.json").exists())

    def test_precommit_faults_leave_no_new_state_and_remove_only_owned_temp(self) -> None:
        for cutpoint in ("before_temp_create", "after_temp_create", "after_complete_write", "after_file_fsync"):
            with self.subTest(cutpoint=cutpoint):
                def fault(point: str) -> None:
                    if point == cutpoint:
                        raise OSError("injected userspace fault")
                with self.assertRaises(OSError):
                    self.store.write("state.json", {"sequence": 1}, fault=fault)
                self.assertFalse((self.root / "state.json").exists())
                self.assertEqual([p.name for p in self.root.iterdir()], [s11.AtomicStateStore.LOCK_NAME])

    def test_postcommit_failure_blocks_all_writes_until_exact_reconciliation(self) -> None:
        value = {"phase": "staged", "sequence": 1}
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                raise OSError("userspace fault, not raw power loss")
        with self.assertRaises(s11.PublicationIndeterminate) as caught:
            self.store.write("state.json", value, fault=fault)
        self.assertEqual(self.store.read("state.json"), value)
        for name in ("state.json", "different.json"):
            with self.assertRaises(s11.RecoveryRequired):
                self.store.write(name, {"sequence": 2})
        with self.assertRaises(s11.RecoveryRequired):
            self.store.reconcile_publication("different.json", expected_sha256=caught.exception.digest)
        with self.assertRaises(s11.RecoveryRequired):
            self.store.reconcile_publication("state.json", expected_sha256="0" * 64)
        self.assertEqual(self.store.reconcile_publication("state.json", expected_sha256=caught.exception.digest), value)
        self.store.write("state.json", {"sequence": 2})
        self.assertEqual(self.store.read("state.json"), {"sequence": 2})

    def test_baseexception_after_publication_also_latches_uncertainty(self) -> None:
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                raise KeyboardInterrupt("injected interpreter interruption")
        with self.assertRaises(s11.PublicationIndeterminate):
            self.store.write("state.json", {}, fault=fault)
        with self.assertRaises(s11.RecoveryRequired):
            self.store.write("state.json", {})

    def test_replace_error_is_conservatively_indeterminate_not_blind_retry(self) -> None:
        with patch.object(s11.os, "replace", side_effect=OSError("uncertain publication syscall")):
            with self.assertRaises(s11.PublicationIndeterminate):
                self.store.write("state.json", {})
        with self.assertRaises(s11.RecoveryRequired):
            self.store.write("state.json", {})

    def test_reconciliation_cannot_accept_tampered_bytes(self) -> None:
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                raise OSError("injected")
        with self.assertRaises(s11.PublicationIndeterminate) as caught:
            self.store.write("state.json", {"sequence": 1}, fault=fault)
        (self.root / "state.json").write_bytes(b'{"sequence":9}')
        with self.assertRaises(s11.RecoveryRequired):
            self.store.reconcile_publication("state.json", expected_sha256=caught.exception.digest)
        with self.assertRaises(s11.RecoveryRequired):
            self.store.write("state.json", {})

    def test_reconciliation_sync_failure_keeps_latch(self) -> None:
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                raise OSError("injected")
        with self.assertRaises(s11.PublicationIndeterminate) as caught:
            self.store.write("state.json", {}, fault=fault)
        with patch.object(s11.os, "fsync", side_effect=OSError("sync unavailable")):
            with self.assertRaises(s11.RecoveryRequired):
                self.store.reconcile_publication("state.json", expected_sha256=caught.exception.digest)
        with self.assertRaises(s11.RecoveryRequired):
            self.store.write("state.json", {})
        self.assertEqual(self.store.reconcile_publication("state.json", expected_sha256=caught.exception.digest), {})

    def test_reconciliation_never_writes_replaces_or_unlinks_state(self) -> None:
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                raise OSError("injected")
        with self.assertRaises(s11.PublicationIndeterminate) as caught:
            self.store.write("state.json", {}, fault=fault)
        with patch.object(s11.os, "write", side_effect=AssertionError("must not write")), \
             patch.object(s11.os, "replace", side_effect=AssertionError("must not replace")), \
             patch.object(s11.os, "unlink", side_effect=AssertionError("must not unlink")):
            self.assertEqual(self.store.reconcile_publication("state.json", expected_sha256=caught.exception.digest), {})

    def test_read_refuses_inode_substitution_during_read(self) -> None:
        self.store.write("state.json", {"sequence": 1})
        real_read = os.read
        changed = False
        def replaced_read(fd: int, count: int) -> bytes:
            nonlocal changed
            value = real_read(fd, count)
            if value and not changed:
                changed = True
                (self.root / "state.json").rename(self.root / "retained.json")
                (self.root / "state.json").write_bytes(b'{}')
                (self.root / "state.json").chmod(0o600)
            return value
        with patch.object(s11.os, "read", side_effect=replaced_read):
            with self.assertRaises(s11.RecoveryRequired):
                self.store.read("state.json")

    def test_postreplace_identity_loss_is_indeterminate(self) -> None:
        def fault(point: str) -> None:
            if point == "after_atomic_replace":
                (self.root / s11.AtomicStateStore.LOCK_NAME).chmod(0o644)
        with self.assertRaises(s11.PublicationIndeterminate):
            self.store.write("state.json", {}, fault=fault)
        with self.assertRaises(s11.StateRefused):
            self.store.write("state.json", {})

    def test_read_malformed_deep_or_oversized_state_is_typed(self) -> None:
        leaf = self.root / "state.json"
        for raw in (b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}', b' ' * (s11.MAX_STATE_BYTES + 1)):
            leaf.write_bytes(raw)
            leaf.chmod(0o600)
            with self.assertRaises(s11.RecoveryRequired):
                self.store.read("state.json")

    def test_context_manager_failure_releases_its_descriptors(self) -> None:
        other = s11.AtomicStateStore(self.root)
        with self.assertRaises(s11.CoordinatorBusy):
            with other:
                self.fail("second coordinator entered")
        self.assertIsNone(other._root_fd)
        self.assertIsNone(other._lease_fd)
        other.close()

    def test_close_releases_lock_for_next_coordinator(self) -> None:
        self.store.close()
        self.store.close()
        with s11.AtomicStateStore(self.root) as other:
            other.write("state.json", {"closed": True})
            self.assertEqual(other.read("state.json"), {"closed": True})
        with self.assertRaises(s11.StateRefused):
            other.read("state.json")

    def test_nonobject_and_unserializable_state_are_refused_before_io(self) -> None:
        for value in ([], {"nan": float("nan")}, {"set": set()}):
            with self.assertRaises(s11.StateRefused):
                self.store.write("state.json", value)
        self.assertFalse((self.root / "state.json").exists())

    def test_short_write_is_completed_and_zero_write_refused(self) -> None:
        real_write = os.write
        with patch.object(s11.os, "write", side_effect=lambda fd, data: real_write(fd, data[:2])):
            self.store.write("state.json", {"sequence": 1})
        self.assertEqual(self.store.read("state.json"), {"sequence": 1})
        with patch.object(s11.os, "write", return_value=0):
            with self.assertRaises(s11.StateRefused):
                self.store.write("state.json", {"sequence": 2})
        self.assertEqual(self.store.read("state.json"), {"sequence": 1})

    def test_constructed_state_cannot_bypass_decoder_resource_limits(self) -> None:
        nested = {}
        cursor = nested
        for _ in range(s11.AtomicStateStore.MAX_STATE_DEPTH + 1):
            cursor["child"] = {}
            cursor = cursor["child"]
        cycle = {}
        cycle["self"] = cycle
        cases = (nested, cycle, {"many": [0] * s11.AtomicStateStore.MAX_STATE_ITEMS},
                 {"text": "x" * (s11.AtomicStateStore.MAX_STATE_STRING_BYTES + 1)},
                 {"integer": 1 << 63}, {"float": 1.0}, {1: "integer-key"})
        for value in cases:
            with self.assertRaises(s11.StateRefused):
                self.store.write("state.json", value)
        self.assertFalse((self.root / "state.json").exists())

    def test_decoded_state_uses_the_same_value_budgets(self) -> None:
        for value in ({"integer": 1 << 63}, {"float": 1.0},
                      {"text": "x" * (s11.AtomicStateStore.MAX_STATE_STRING_BYTES + 1)},
                      {"many": [0] * s11.AtomicStateStore.MAX_STATE_ITEMS}):
            leaf = self.root / "state.json"
            leaf.write_text(json.dumps(value))
            leaf.chmod(0o600)
            with self.assertRaises(s11.RecoveryRequired):
                self.store.read("state.json")

    def test_state_value_boundaries_round_trip(self) -> None:
        value = {"text": "x" * s11.AtomicStateStore.MAX_STATE_STRING_BYTES,
                 "integer": s11.AtomicStateStore.MAX_STATE_INTEGER,
                 "negative": -s11.AtomicStateStore.MAX_STATE_INTEGER,
                 "null": None, "enabled": True}
        self.store.write("state.json", value)
        self.assertEqual(self.store.read("state.json"), value)

    def test_actual_child_process_observes_exclusive_lease(self) -> None:
        code = '''import fcntl,os,sys
fd=os.open(sys.argv[1], os.O_RDWR|os.O_NOFOLLOW)
try:
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(0)
else:
    sys.exit(3)
finally:
    os.close(fd)
'''
        result = subprocess.run([sys.executable, "-I", "-c", code,
                                 str(self.root / s11.AtomicStateStore.LOCK_NAME)],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)


class StateCustodyContractTests(unittest.TestCase):
    def test_machine_contract_matches_bounds_and_non_claims(self) -> None:
        path = ROOT / "contracts/s11-state-store-custody.v1.json"
        self.assertFalse(path.is_symlink())
        value = s11._strict_object(path.read_bytes(), s11.MAX_STATE_BYTES)
        self.assertEqual(set(value), {"schema", "source", "tests", "scope", "path", "lease", "state", "publication", "non_claims"})
        self.assertEqual(value["schema"], "trillionnium.desktop.update-state-custody.v1")
        self.assertEqual(value["scope"], "host_filesystem_mechanism_only")
        self.assertEqual(value["path"]["maximum_utf8_bytes"], s11.AtomicStateStore.MAX_PATH_BYTES)
        self.assertEqual(value["path"]["maximum_components"], s11.AtomicStateStore.MAX_PATH_COMPONENTS)
        self.assertEqual(value["lease"]["name"], s11.AtomicStateStore.LOCK_NAME)
        self.assertEqual(value["state"]["maximum_bytes"], s11.MAX_STATE_BYTES)
        self.assertEqual(value["state"]["maximum_depth"], s11.AtomicStateStore.MAX_STATE_DEPTH)
        self.assertEqual(value["state"]["maximum_items_including_keys"], s11.AtomicStateStore.MAX_STATE_ITEMS)
        self.assertEqual(value["state"]["maximum_string_utf8_bytes"], s11.AtomicStateStore.MAX_STATE_STRING_BYTES)
        self.assertEqual(value["state"]["maximum_integer_magnitude"], s11.AtomicStateStore.MAX_STATE_INTEGER)
        self.assertEqual(value["publication"]["pending_latch_scope"], "current_live_handle_only")
        self.assertIs(value["publication"]["reconciliation_rewrites_or_replays"], False)
        self.assertTrue(all(item is False for item in value["non_claims"].values()))

    def test_permanent_workflow_executes_existing_and_new_host_corpus(self) -> None:
        workflow = (ROOT / ".github/workflows/s11-update-recovery.yml").read_text()
        for token in ("python3 -m unittest tests.test_s11_update_recovery -v",
                      "python3 -m unittest tests.test_s11_state_custody -v",
                      "sudo /usr/bin/python3 -I tests/test_s11_state_custody.py -v"):
            self.assertEqual(workflow.count(token), 2)
        self.assertNotIn("    if: github.event_name == 'push'", workflow)
        self.assertNotIn("    paths:", workflow)
        self.assertIn("refs/pull/${{ github.event.pull_request.number }}/merge", workflow)
        self.assertIn("contents: read", workflow)


if __name__ == "__main__":
    unittest.main()
