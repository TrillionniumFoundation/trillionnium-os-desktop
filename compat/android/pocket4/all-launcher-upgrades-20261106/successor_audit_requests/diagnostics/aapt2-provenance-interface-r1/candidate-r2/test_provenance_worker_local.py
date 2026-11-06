#!/usr/bin/env python3
"""Local non-root boundary controls only; main() and target tools never run."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("host_proof_under_test", HERE / "prove_existing_aapt2_and_interface.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
reader = worker.frozen_module(worker.READER_SOURCE, worker.READER_SHA, "frozen_inventory_reader_local_control")


def fd_identity():
    values = {}
    for item in os.listdir("/proc/self/fd"):
        try:
            fd = int(item)
            value = os.fstat(fd)
            values[fd] = (value.st_dev, value.st_ino, value.st_mode, os.readlink("/proc/self/fd/" + item))
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno != 9:
                raise
    return values


class HostProofControls(unittest.TestCase):
    def setUp(self):
        self.before = fd_identity()
        self.temp = tempfile.TemporaryDirectory(prefix="pocket4-aapt2-host-proof-owned-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(fd_identity(), self.before)

    def test_exact_source_pin_rejects_changed_embedded_reader(self):
        with self.assertRaisesRegex(RuntimeError, "EMBEDDED_REVIEWED_SOURCE_CHANGED"):
            worker.frozen_module(worker.READER_SOURCE + "\n", worker.READER_SHA, "must_not_execute")

    def test_actual_nonroot_owned_file_rejected_and_all_fds_closed(self):
        self.assertNotEqual(os.geteuid(), 0, "This control intentionally uses actual non-root ownership.")
        path = self.root / "owned-host-file"
        path.write_bytes(b"actual owned fixture; must not become a root host input")
        self.assertEqual(path.stat().st_uid, os.geteuid())
        with self.assertRaisesRegex(RuntimeError, "PINNED_DEPENDENCY_ROOT_OWNER_REQUIRED"):
            worker.BoundFile(reader, str(path), 65536)

    def test_output_constructor_owner_rejection_closes_its_open_fd(self):
        self.assertNotEqual(os.geteuid(), 0)
        original = worker.OUTPUT
        worker.OUTPUT = str(self.root / "new-evidence")
        try:
            with self.assertRaisesRegex(RuntimeError, "ROOT_PRIVATE_NEW_OUTPUT_REQUIRED"):
                worker.EvidenceStore(reader)
        finally:
            worker.OUTPUT = original

    def test_dpkg_continuations_epoch_version_and_duplicate_rejection(self):
        text = b"Package: aapt\nStatus: install ok installed\nArchitecture: amd64\nVersion: 1:10.0.0+r36-1\nDescription: fixture\n continuation remains a continuation\n"
        fields = worker.package_fields(text)
        self.assertEqual(fields["Version"], "1:10.0.0+r36-1")
        self.assertEqual(fields["Description"], "fixture\n continuation remains a continuation")
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE"):
            worker.package_fields(text + b"Package: second\n")
        with self.assertRaisesRegex(RuntimeError, "CONTINUATION_WITHOUT_FIELD"):
            worker.package_fields(b" no preceding field\n")

    def test_loader_path_outside_scope_and_ambiguous_library_rejected(self):
        original = worker.SYSTEM_LIBRARY_ROOTS
        worker.SYSTEM_LIBRARY_ROOTS = (str(self.root),)
        try:
            a, b = self.root / "a", self.root / "b"
            a.mkdir(); b.mkdir()
            (a / "libexample.so.1").write_bytes(b"one controlled fixture")
            self.assertEqual(worker.resolve_dependency("libexample.so.1", [str(a), str(b)]), str(a / "libexample.so.1"))
            (b / "libexample.so.1").write_bytes(b"second distinct controlled fixture")
            with self.assertRaisesRegex(RuntimeError, "ABSENT_OR_AMBIGUOUS"):
                worker.resolve_dependency("libexample.so.1", [str(a), str(b)])
            with self.assertRaisesRegex(RuntimeError, "NO_CWD"):
                worker.search_paths("", str(a))
            with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED_LOADER_EXPANSION"):
                worker.search_paths("$UNREVIEWED", str(a))
            with self.assertRaisesRegex(RuntimeError, "OUTSIDE_REVIEWED"):
                worker.search_paths("/etc", str(a))
            with self.assertRaisesRegex(RuntimeError, "BOUNDED_SONAME"):
                worker.resolve_dependency("../../outside", [str(a)])
        finally:
            worker.SYSTEM_LIBRARY_ROOTS = original


if __name__ == "__main__":
    initial = fd_identity()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HostProofControls))
    final = fd_identity()
    summary = {"schema": "pocket4-aapt2-host-proof-local-boundary-controls-v1", "ok": result.wasSuccessful() and initial == final,
               "tests_run": result.testsRun, "skipped": len(result.skipped), "actual_local_uid": os.geteuid(),
               "open_FD_identity_before": len(initial), "open_FD_identity_after": len(final),
               "full_FD_identity_unchanged": initial == final, "runtime_main_executed": False,
               "remote_calls": 0, "candidate_executions": 0, "Main_reads": 0, "APK_reads": 0,
               "local_root_positive_execution_claimed": False}
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    raise SystemExit(0 if summary["ok"] else 1)
