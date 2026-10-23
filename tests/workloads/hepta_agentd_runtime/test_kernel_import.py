#!/usr/bin/env python3
"""Host rejection tests; small synthetic inputs never constitute a CI receipt."""
import contextlib
import copy
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

import import_kernel_artifact as importer
import prepare_inputs


def metadata():
    return {
        "artifacts": [{"id": importer.ARTIFACT_ID, "name": importer.ARTIFACT_NAME,
                       "size_in_bytes": importer.ARCHIVE_BYTES, "digest": "sha256:" + importer.ARCHIVE_SHA256,
                       "workflow_run": {"id": importer.RUN_ID, "head_sha": importer.RETAINED_DESKTOP["head"]}}]
    }, {"id": importer.RUN_ID, "head_sha": importer.RETAINED_DESKTOP["head"], "status": "completed",
        "conclusion": "success", "path": ".github/workflows/a06-kernel.yml",
        "repository": {"full_name": importer.REPOSITORY}}


class MetadataBoundaryTests(unittest.TestCase):
    def test_wrong_artifact_run_source_and_bytes_are_rejected(self):
        artifacts, run = metadata()
        for key, value in (("id", 1), ("size_in_bytes", 1), ("digest", "sha256:" + "0" * 64), ("name", "ktest-unrelated")):
            changed = copy.deepcopy(artifacts)
            changed["artifacts"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): importer.validate_metadata(changed, run)
        for key, value in (("id", 1), ("head_sha", "0" * 40)):
            changed = copy.deepcopy(artifacts)
            changed["artifacts"][0]["workflow_run"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): importer.validate_metadata(changed, run)

    def test_success_label_without_original_completed_run_is_rejected(self):
        artifacts, run = metadata()
        for key, value in (("status", "in_progress"), ("conclusion", "failure"), ("head_sha", "0" * 40),
                           ("path", ".github/workflows/unrelated.yml"), ("repository", None)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                importer.validate_metadata(artifacts, {**run, key: value})

    def test_missing_duplicate_and_nonobject_workflow_run_are_rejected(self):
        artifacts, run = metadata()
        for value in ([], artifacts["artifacts"] * 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                importer.validate_metadata({"artifacts": value}, run)
        artifacts["artifacts"][0]["workflow_run"] = None
        with self.assertRaises(ValueError): importer.validate_metadata(artifacts, run)

    def test_untrusted_archive_never_creates_successful_receipt(self):
        artifacts, run = metadata()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifact-list.json").write_text(json.dumps(artifacts))
            (root / "run.json").write_text(json.dumps(run))
            (root / "not-a-real-artifact.zip").write_bytes(b"synthetic rejection test only")
            output = root / "import"
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                code = importer.main(["--archive", str(root / "not-a-real-artifact.zip"),
                                      "--artifact-metadata", str(root / "artifact-list.json"),
                                      "--run-metadata", str(root / "run.json"),
                                      "--desktop-source", str(root), "--output", str(output)])
            self.assertEqual(code, 1)
            report = json.loads(captured.getvalue())
            self.assertFalse(report["imported"])
            self.assertFalse(report["kernel_built_in_this_import"])
            self.assertFalse(report["guest_executed_in_this_import"])
            self.assertFalse(output.exists())


class RetainedEvidenceBoundaryTests(unittest.TestCase):
    def test_archive_rejects_missing_duplicate_symlink_and_oversize_members(self):
        for variant in ("missing", "duplicate", "symlink", "oversize"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive, warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                name = importer.PREFIX + "result.json"
                if variant == "symlink":
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(entry, "elsewhere")
                elif variant == "duplicate":
                    archive.writestr(name, b"{}")
                    archive.writestr(name, b"{}")
                elif variant == "oversize":
                    archive.writestr(name, b"x" * 33)
            buffer.seek(0)
            with zipfile.ZipFile(buffer) as archive, self.subTest(variant=variant), self.assertRaises(ValueError):
                importer.read_member(archive, "result.json", 32)

    def test_changed_source_snapshot_fails_before_receipt_creation(self):
        before = {"schema": "a06.g1-source-snapshot.v1", **importer.RETAINED_DESKTOP, "files": {}}
        changed = {**before, "tree": "0" * 40}
        raw = {name: json.dumps(value).encode() for name, value in (
            ("source-before.json", before), ("source-after-boot.json", before), ("source-after-guest.json", changed))}
        with self.assertRaisesRegex(ValueError, "snapshots changed"):
            importer.validate_snapshots(raw, {"source_file_count": importer.SOURCE_COUNT})
        with self.assertRaisesRegex(ValueError, "must be an object"):
            importer.validate_snapshots(raw, [])

    def test_ktest_and_failed_build_cannot_be_transcribed_as_ordinary_build(self):
        base = {"schema": "a06.g1-queryabi-product-candidate.v1", "passed": True, "stage": "complete",
                "source_inputs_unchanged": True, "source_head": importer.gate.DESKTOP["head"],
                "source_tree": importer.gate.DESKTOP["tree"], "product_configuration": "ActionChoice::Run; no --cfg ktest",
                "product_wrapper_exit": 0, "product_boot_raw_exit": 33}
        for key, value in (("product_configuration", "ktest"), ("product_wrapper_exit", 1),
                           ("product_boot_raw_exit", 65), ("passed", False), ("stage", "compile")):
            raw = {"result.json": json.dumps({**base, key: value}).encode()}
            with self.subTest(key=key), self.assertRaises(ValueError):
                importer.validate_product(raw, {}, importer.gate.DESKTOP, None, Path("/not-executed"))

    def test_prefetch_requires_explicit_execution(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
            prepare_inputs.main(["--fetch-dependencies", "--desktop-source", "/unused", "--hepta-source", "/unused",
                                 "--kernel", "/unused", "--kernel-receipt", "/unused",
                                 "--expected-kernel-receipt-sha256", "0" * 64])
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
