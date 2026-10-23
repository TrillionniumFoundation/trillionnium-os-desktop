"""Host regressions for fresh-build failure and retained-profile boundaries."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_kernel
import import_kernel_artifact as retained
import prepare_inputs
import run_agentd_runtime as gate


class FreshBuildBoundaryTests(unittest.TestCase):
    def arguments(self, root):
        return ["--desktop-source", str(root / "desktop"), "--hepta-source", str(root / "hepta"),
                "--expected-source-review-sha256", "0" * 64,
                "--vdso", str(root / "vdso"), "--output", str(root / "output")]

    def test_disabled_mode_does_not_inspect_or_execute_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(build_kernel, "retain_build") as build, contextlib.redirect_stdout(io.StringIO()) as output:
                code = build_kernel.main(self.arguments(root))
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["executed"])
            build.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_unreviewed_inputs_never_start_build_or_create_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(build_kernel.preparation, "verify_sources") as verify, contextlib.redirect_stdout(io.StringIO()) as output:
                code = build_kernel.main(["--execute", *self.arguments(root)])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output.getvalue())["built"])
            verify.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_failed_execution_retains_failure_without_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def rejected(args, roots, destination, report):
                destination.mkdir()
                report["output_created"] = True
                raise ValueError("ordinary build failed before boot")
            with patch.object(build_kernel, "retain_build", side_effect=rejected), contextlib.redirect_stdout(io.StringIO()):
                code = build_kernel.main(["--execute", *self.arguments(root)])
            self.assertEqual(code, 1)
            result = json.loads((root / "output/build-result.json").read_text())
            self.assertFalse(result["built"])
            self.assertFalse(result["boot_passed"])
            self.assertFalse((root / "output/kernel-build.json").exists())

    def test_retained_build_cannot_be_relabelled_as_current_source_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / "kernel.elf"
            kernel.write_bytes(b"retained-data-only")
            value = {"schema": "hepta.native-original-runtime-build.v1",
                     "sources": copy.deepcopy(retained.RETAINED_SOURCES), "built": True,
                     "source_clean": True, "kernel_profile": "ordinary-os"}
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "reviewed clean ordinary build"):
                prepare_inputs.kernel_receipt(receipt, kernel, gate.sha(receipt))


if __name__ == "__main__":
    unittest.main()
