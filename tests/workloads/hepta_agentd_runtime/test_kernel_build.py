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


class OsdkFreezeTests(unittest.TestCase):
    def inputs(self, root):
        tool = root / "installed-cargo-osdk"
        tool.write_bytes(b"inert host fixture, never executable")
        tool.chmod(0o600)
        output = root / "evidence"
        output.mkdir()
        (output / "osdk-build.log").write_bytes(b"controlled original build log\n")
        identity = {"path": str(tool), "sha256": gate.sha(tool), "command": ["cargo", "install", "--locked"],
                    "source": copy.deepcopy(gate.DESKTOP), "local_development_source": True}
        return tool, output, identity

    def test_freeze_retains_binary_exact_log_and_separate_nonqualification_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool, output, identity = self.inputs(root)
            with patch.object(build_kernel.subprocess, "run") as execute:
                frozen = build_kernel.freeze_osdk(tool, output, identity)
            execute.assert_not_called()
            self.assertEqual((output / "source-built-cargo-osdk").read_bytes(), tool.read_bytes())
            self.assertEqual((output / "source-built-cargo-osdk").stat().st_mode & 0o777, 0o444)
            self.assertEqual(frozen["retained_build_log"]["sha256"], gate.sha(output / "osdk-build.log"))
            metadata = json.loads((output / "osdk-freeze.json").read_text())
            self.assertFalse(metadata["build_executed_in_this_copy"])
            self.assertFalse(metadata["kernel_qualification_implied"])
            self.assertEqual(metadata["source"], identity["source"])
            build_kernel.verify_frozen_osdk(output, frozen)
            self.assertFalse((output / "kernel-build.json").exists())

    def test_changed_or_symlink_source_and_missing_exact_log_rejected(self):
        for mode in ("changed", "symlink", "missing-log", "symlink-log", "empty-log"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                tool, output, identity = self.inputs(Path(directory))
                if mode == "changed": tool.write_bytes(b"different")
                if mode == "symlink":
                    alias = tool.with_name("alias")
                    alias.symlink_to(tool)
                    tool = alias
                if mode in ("missing-log", "symlink-log"):
                    (output / "osdk-build.log").unlink()
                    if mode == "symlink-log": (output / "osdk-build.log").symlink_to(tool)
                if mode == "empty-log": (output / "osdk-build.log").write_bytes(b"")
                with self.assertRaises(ValueError): build_kernel.freeze_osdk(tool, output, identity)
                self.assertFalse((output / "osdk-freeze.json").exists())

    def test_existing_or_redirected_output_is_never_overwritten(self):
        for name in ("source-built-cargo-osdk", "osdk-freeze.json"):
            for symlink in (False, True):
                with self.subTest(name=name, symlink=symlink), tempfile.TemporaryDirectory() as directory:
                    tool, output, identity = self.inputs(Path(directory))
                    if symlink: (output / name).symlink_to(tool)
                    else: (output / name).write_bytes(b"existing")
                    original = tool.read_bytes()
                    with self.assertRaises(ValueError): build_kernel.freeze_osdk(tool, output, identity)
                    self.assertEqual(tool.read_bytes(), original)

    def test_any_retained_binary_log_or_receipt_change_is_rejected(self):
        for name in ("source-built-cargo-osdk", "osdk-build.log", "osdk-freeze.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                tool, output, identity = self.inputs(Path(directory))
                frozen = build_kernel.freeze_osdk(tool, output, identity)
                (output / name).chmod(0o600)
                (output / name).write_bytes(b"changed")
                with self.assertRaises(ValueError): build_kernel.verify_frozen_osdk(output, frozen)


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
