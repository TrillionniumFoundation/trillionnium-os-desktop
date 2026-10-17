from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "support/android/generate_kernel_source_audit.py"
LOCK_PATH = "support/upstream-lock.json"
EXPECTED_LOCK = {
    "tag": "v0.19.0",
    "commit": "c4b7ed575b7b32773475b194d2ad41fb6d03765b",
    "reuse": "full_kernel_derived",
}


class KernelSourceAuditTests(unittest.TestCase):
    def make_repository(self, parent):
        root = Path(parent) / "source"
        root.mkdir()
        self.git(root, "init", "--initial-branch=main")
        for relative, text in {
            "syscall/futex.rs": "pub fn sys_futex() { /* committed source */ }\n",
            "syscall/prctl.rs": "pub fn sys_prctl() {}\n",
            "security/lsm/modules/mod.rs": "mod commoncap;\n",
            "device/mod.rs": "// No Android device implementation in this fixture.\n",
        }.items():
            path = root / "kernel/asterinas/kernel/core/src" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        lock = root / LOCK_PATH
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"kernel": EXPECTED_LOCK}), encoding="utf-8")
        self.commit(root, "Initial source fixture")
        return root

    def git(self, root, *args):
        return subprocess.check_output(
            ["git", "-C", str(root), "-c", "user.name=A08 source audit fixture",
             "-c", "user.email=a08-fixture@example.invalid", "-c", "commit.gpgsign=false",
             *args], text=True,
        ).strip()

    def commit(self, root, message):
        self.git(root, "add", ".")
        self.git(root, "commit", "-q", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def snapshot(self, root, output, project_ref="HEAD"):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--repo-root", str(root),
             "--project-ref", project_ref, "--output", str(output)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_current_snapshot_is_bound_to_project_commit_and_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--repo-root", str(ROOT), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            commit = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"], text=True
            ).strip()
            self.assertEqual(report["project_commit"], commit)
            self.assertEqual(report["project_tree"], tree)
            self.assertEqual(report["blocking_requirements"], ["binder", "seccomp", "mac"])
            self.assertFalse(report["runtime_android_verified"])
            self.assertFalse(report["booted_android_on_asterinas"])
            self.assertEqual(report["kernel_upstream_lock"]["status"], "matched")
            self.assertEqual(report["kernel_upstream_lock"]["expected"], EXPECTED_LOCK)

    def test_snapshot_records_git_blob_and_content_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            subprocess.run(
                [sys.executable, str(GENERATOR), "--repo-root", str(ROOT), "--output", str(output)],
                capture_output=True,
                check=False,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            rel = "kernel/asterinas/kernel/core/src/syscall/futex.rs"
            blob = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", f"HEAD:{rel}"], text=True
            ).strip()
            self.assertEqual(report["source_files"][rel]["git_blob"], blob)
            content = subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"])
            self.assertEqual(report["source_files"][rel]["bytes"], len(content))

    def test_selected_ref_controls_bytes_and_candidate_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            selected = self.git(root, "rev-parse", "HEAD")
            relative = "kernel/asterinas/kernel/core/src/syscall/futex.rs"
            expected = (root / relative).read_bytes()
            expected_lock = (root / LOCK_PATH).read_bytes()
            (root / relative).write_text("pub fn sys_futex() { changed(); }\n", encoding="utf-8")
            (root / LOCK_PATH).write_text(json.dumps({"kernel": {**EXPECTED_LOCK, "commit": "0" * 40}}), encoding="utf-8")
            binder = root / "kernel/asterinas/kernel/core/src/device/binder.rs"
            binder.write_text("struct BinderDevice;\n", encoding="utf-8")
            self.commit(root, "Different checked-out source and candidate")
            report = self.snapshot(root, Path(tmp) / "snapshot.json", selected)
            self.assertEqual(report["project_commit"], selected)
            self.assertEqual(report["project_tree"], self.git(root, "rev-parse", f"{selected}^{{tree}}"))
            self.assertEqual(report["source_files"][relative]["git_blob"],
                             self.git(root, "rev-parse", f"{selected}:{relative}"))
            self.assertEqual(report["source_files"][relative]["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(report["source_scan"]["binder_matches"], [])
            self.assertEqual(report["source_scan"]["core_rust_file_count"], 4)
            self.assertEqual(report["kernel_upstream_lock"]["status"], "matched")
            self.assertEqual(report["kernel_upstream_lock"]["actual"], EXPECTED_LOCK)
            self.assertEqual(report["source_files"][LOCK_PATH]["git_blob"],
                             self.git(root, "rev-parse", f"{selected}:{LOCK_PATH}"))
            self.assertEqual(report["source_files"][LOCK_PATH]["sha256"],
                             hashlib.sha256(expected_lock).hexdigest())

    def test_dirty_tracked_files_do_not_become_commit_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            relative = "kernel/asterinas/kernel/core/src/syscall/prctl.rs"
            expected = (root / relative).read_bytes()
            (root / relative).write_text("pub fn sys_seccomp() {}\n", encoding="utf-8")
            report = self.snapshot(root, Path(tmp) / "snapshot.json")
            self.assertEqual(report["source_files"][relative]["sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(report["source_scan"]["seccomp_matches"], [])

    def test_untracked_candidate_does_not_become_commit_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            candidate = root / "kernel/asterinas/kernel/core/src/device/binder.rs"
            candidate.write_text("struct BinderDevice;\n", encoding="utf-8")
            report = self.snapshot(root, Path(tmp) / "snapshot.json")
            self.assertEqual(report["source_scan"]["binder_matches"], [])
            self.assertIn("binder", report["blocking_requirements"])

    def test_selected_ref_missing_file_is_not_filled_from_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            selected = self.git(root, "rev-parse", "HEAD")
            relative = "kernel/asterinas/kernel/core/src/syscall/mmap.rs"
            (root / relative).write_text("pub fn sys_mmap() {}\n", encoding="utf-8")
            self.commit(root, "Add source after selected commit")
            report = self.snapshot(root, Path(tmp) / "snapshot.json", selected)
            self.assertIn(relative, report["missing_source_paths"])
            self.assertNotIn(relative, report["source_files"])

    def test_observation_time_is_the_actual_utc_audit_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            before = datetime.now(timezone.utc)
            report = self.snapshot(root, Path(tmp) / "snapshot.json")
            after = datetime.now(timezone.utc)
            self.assertIn(report["observed_date"], {before.date().isoformat(), after.date().isoformat()})
            observed = datetime.fromisoformat(report["observed_at_utc"])
            self.assertEqual(observed.utcoffset().total_seconds(), 0)
            self.assertLessEqual(before, observed)
            self.assertLessEqual(observed, after)

    def test_missing_lock_is_a_source_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repository(tmp)
            (root / LOCK_PATH).unlink()
            self.commit(root, "Remove upstream lock")
            report = self.snapshot(root, Path(tmp) / "snapshot.json")
            self.assertIn("pinned_lock", report["blocking_requirements"])
            self.assertEqual(report["kernel_upstream_lock"]["status"], "missing")
            self.assertIsNone(report["kernel_upstream_lock"]["actual"])
            self.assertNotIn(LOCK_PATH, report["source_files"])

    def test_mismatched_lock_is_a_source_blocker(self):
        for key, wrong_value in (("tag", "v0.18.0"), ("commit", "0" * 40), ("reuse", "partial")):
            with self.subTest(field=key), tempfile.TemporaryDirectory() as tmp:
                root = self.make_repository(tmp)
                actual = {**EXPECTED_LOCK, key: wrong_value}
                (root / LOCK_PATH).write_text(json.dumps({"kernel": actual}), encoding="utf-8")
                self.commit(root, "Change upstream lock")
                report = self.snapshot(root, Path(tmp) / "snapshot.json")
                self.assertIn("pinned_lock", report["blocking_requirements"])
                self.assertEqual(report["kernel_upstream_lock"]["status"], "mismatch")
                self.assertEqual(report["kernel_upstream_lock"]["actual"], actual)
                self.assertEqual(report["source_files"][LOCK_PATH]["git_blob"],
                                 self.git(root, "rev-parse", f"HEAD:{LOCK_PATH}"))

    def test_malformed_lock_is_a_source_blocker(self):
        for content in (b'{"kernel":', b'{"kernel": []}', b'\xff'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                root = self.make_repository(tmp)
                (root / LOCK_PATH).write_bytes(content)
                self.commit(root, "Commit invalid lock data")
                report = self.snapshot(root, Path(tmp) / "snapshot.json")
                self.assertIn("pinned_lock", report["blocking_requirements"])
                self.assertEqual(report["kernel_upstream_lock"]["status"], "invalid")
                self.assertIsNone(report["kernel_upstream_lock"]["actual"])
                self.assertEqual(report["source_files"][LOCK_PATH]["sha256"], hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
