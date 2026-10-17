"""Linux host filesystem adversarial tests, no device access."""
import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/vmm"))
import evidence_output
import probe
import vfio_preflight
import kernel_join_gate
import cuda_gemm


class EvidenceOutputTests(unittest.TestCase):
    def test_fresh_evidence_file_is_private_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            evidence_output.write_evidence_output(path, '{"status":"blocked"}\n')
            self.assertEqual(path.read_text(), '{"status":"blocked"}\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_existing_regular_record_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.json"
            path.write_text("signed previous report", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                evidence_output.write_evidence_output(path, "forged")
            self.assertEqual(path.read_text(), "signed previous report")

    def test_symlink_cannot_overwrite_earlier_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "old.json"
            target.write_text("old", encoding="utf-8")
            alias = root / "new.json"
            alias.symlink_to(target)
            with self.assertRaises(OSError):
                evidence_output.write_evidence_output(alias, "forged")
            self.assertEqual(target.read_text(), "old")
            self.assertTrue(alias.is_symlink())

    def test_hardlink_cannot_replace_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old.json"
            old.write_text("old", encoding="utf-8")
            alias = root / "new.json"
            os.link(old, alias)
            with self.assertRaises(FileExistsError):
                evidence_output.write_evidence_output(alias, "forged")
            self.assertEqual(old.read_text(), "old")

    def test_fifo_refused_without_any_blocking_open(self):
        with tempfile.TemporaryDirectory() as directory:
            pipe = Path(directory) / "fifo"
            os.mkfifo(pipe)
            with self.assertRaises(OSError):
                evidence_output.write_evidence_output(pipe, "forged")
            self.assertTrue(stat.S_ISFIFO(pipe.stat().st_mode))

    def test_stdout_does_not_create_a_file(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            evidence_output.write_evidence_output("-", "{}\n")
        self.assertEqual(buf.getvalue(), "{}\n")

    def test_oversized_payload_fails_before_any_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            with patch.object(evidence_output, "MAX_EVIDENCE_OUTPUT_BYTES", 2):
                with self.assertRaises(ValueError):
                    evidence_output.write_evidence_output(path, "many bytes")
            self.assertFalse(path.exists())

    def test_failed_write_never_returns_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            with patch.object(evidence_output.os, "write", side_effect=OSError("no space")):
                with self.assertRaises(OSError):
                    evidence_output.write_evidence_output(path, "not completed")
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).glob(".a09-evidence-*")), [])

    def test_unicode_payload_is_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "utf8.json"
            evidence_output.write_evidence_output(path, '"显卡"\n')
            self.assertEqual(path.read_bytes(), '"显卡"\n'.encode("utf-8"))

    def test_all_four_entrypoints_refuse_preexisting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / "old-record.json"
            old.write_text("previous immutable observation", encoding="utf-8")
            self.assertEqual(probe.write_evidence_output, evidence_output.write_evidence_output)
            self.assertEqual(vfio_preflight.write_evidence_output, evidence_output.write_evidence_output)
            with patch.object(probe, "snapshot", return_value={"schema": "test"}), \
                 patch.object(sys, "argv", ["probe.py", "--output", str(old)]):
                self.assertEqual(probe.main(), 1)
            with patch.object(vfio_preflight, "preflight",
                              return_value={"status": "blocked", "hard_blockers": []}):
                self.assertEqual(vfio_preflight.main(["--output", str(old)]), 1)
            with self.assertRaises(FileExistsError):
                kernel_join_gate._write_json(old, "{}\n")
            with self.assertRaises(FileExistsError):
                cuda_gemm._write_evidence({"status": "blocked"}, str(old))
            self.assertEqual(old.read_text(), "previous immutable observation")

    def test_fresh_kernel_source_evidence_file_is_created_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            kernel_join_gate._write_json(path, '{"status":"blocked"}\n')
            self.assertEqual(path.read_text(), '{"status":"blocked"}\n')
            with self.assertRaises(FileExistsError):
                kernel_join_gate._write_json(path, '{"status":"review"}\n')

    def test_failed_fsync_never_publishes_final_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            with patch.object(evidence_output.os, "fsync", side_effect=OSError("fsync failed")):
                with self.assertRaises(OSError):
                    evidence_output.write_evidence_output(path, "{}")
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).glob(".a09-evidence-*")), [])

    def test_link_conflict_after_staging_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            original_link = os.link

            def race(src, dst, **kwargs):
                path.write_text("winner", encoding="utf-8")
                return original_link(src, dst, **kwargs)

            with patch.object(evidence_output.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    evidence_output.write_evidence_output(path, "ours")
            self.assertEqual(path.read_text(), "winner")
            self.assertEqual(list(Path(directory).glob(".a09-evidence-*")), [])

    def test_final_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dest = root / "trusted"
            dest.mkdir()
            alias = root / "parent"
            alias.symlink_to(dest, target_is_directory=True)
            with self.assertRaises(OSError):
                evidence_output.write_evidence_output(alias / "forged.json", "{}")
            self.assertFalse((dest / "forged.json").exists())

    def test_competing_writers_create_exactly_one_final_record(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one.json"

            def writer(value):
                try:
                    evidence_output.write_evidence_output(path, str(value))
                    return True
                except FileExistsError:
                    return False

            with ThreadPoolExecutor(max_workers=8) as pool:
                result = list(pool.map(writer, range(12)))
            self.assertEqual(sum(result), 1)
            self.assertIn(path.read_text(), [str(i) for i in range(12)])
            self.assertEqual(list(Path(directory).glob(".a09-evidence-*")), [])

    def test_failed_directory_fsync_reports_uncertain_commit_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            original_fsync = os.fsync

            def fail_directory_only(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("directory durability unknown")
                return original_fsync(fd)

            with patch.object(evidence_output.os, "fsync", side_effect=fail_directory_only):
                with self.assertRaises(OSError):
                    evidence_output.write_evidence_output(path, "{}")
            # Publication can precede a failed directory fsync: do not
            # claim the record is durably committed merely because it exists.
            self.assertEqual(path.read_text(), "{}")



if __name__ == '__main__':
    unittest.main()
