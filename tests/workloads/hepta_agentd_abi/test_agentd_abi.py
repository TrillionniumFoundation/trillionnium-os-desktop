"""Host controls only; no Agentd or QEMU process is launched by this suite."""
import contextlib
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_agentd_abi as runner


def serial(nonce="a" * 64, stderr=runner.EXPECTED_ERROR):
    return ("TRILLIONNIUM_A01_INIT_BEGIN\n"
            f"HEPTA_ABI_BEGIN nonce={nonce}\n"
            f"HEPTA_ABI_STDOUT nonce={nonce} hex=\n"
            f"HEPTA_ABI_STDERR nonce={nonce} hex={stderr.hex()}\n"
            f"HEPTA_ABI_CHILD nonce={nonce} kind=exit code=1\n"
            f"HEPTA_ABI_HARNESS nonce={nonce} exit=0\n"
            "TRILLIONNIUM_A01_BOOT_OK\n").encode()


class OracleTests(unittest.TestCase):
    def test_exact_result_and_crlf(self):
        value = serial()
        self.assertTrue(runner.oracle(value, 33, False, "a" * 64))
        self.assertTrue(runner.oracle(value.replace(b"\n", b"\r\n"), 33, False, "a" * 64))
        self.assertEqual(runner.child_observation(value, "a" * 64), {
            "stdout": "", "stderr": runner.EXPECTED_ERROR.decode(), "termination": "kind=exit code=1"})

    def test_process_failures_never_pass(self):
        for code, timed_out in ((0, False), (1, False), (-9, False), (33, True)):
            with self.subTest(code=code, timed_out=timed_out):
                self.assertFalse(runner.oracle(serial(), code, timed_out, "a" * 64))
        for message in (b"code=127", b"kind=signal code=11", b"code=0"):
            raw = serial().replace(b"kind=exit code=1", message)
            self.assertFalse(runner.oracle(raw, 33, False, "a" * 64))

    def test_loader_error_or_unexpected_output_cannot_masquerade_as_main(self):
        for error in (b"HEPTA_FLEET_ROOT is required\n", b"Error: library missing\n", runner.EXPECTED_ERROR + b"extra\n"):
            self.assertFalse(runner.oracle(serial(stderr=error), 33, False, "a" * 64))
        self.assertFalse(runner.oracle(serial().replace(b"STDOUT nonce=" + b"a" * 64 + b" hex=\n",
                                                        b"STDOUT nonce=" + b"a" * 64 + b" hex=78\n"),
                                       33, False, "a" * 64))

    def test_stale_duplicate_reordered_and_missing_evidence_fail(self):
        original = serial()
        for raw in (serial("b" * 64), original + original,
                    original.replace(b"TRILLIONNIUM_A01_BOOT_OK\n", b""),
                    original + b"Kernel panic\n", original + b"HEPTA_ABI_EXTRA invented\n"):
            self.assertFalse(runner.oracle(raw, 33, False, "a" * 64))
        lines = original.splitlines(keepends=True)
        lines[2], lines[3] = lines[3], lines[2]
        self.assertFalse(runner.oracle(b"".join(lines), 33, False, "a" * 64))


class FrozenInputTests(unittest.TestCase):
    def fixture(self, root):
        binary = root / "agentd.elf"
        binary.write_bytes(b"synthetic manifest-test bytes, never executed")
        review = json.loads((runner.HERE / "source-review.json").read_text())
        return {"schema": "hepta.agentd-frozen-input.v1",
                "binary": {"path": binary.name, "sha256": runner.sha(binary), "bytes": binary.stat().st_size},
                "build_source": {"head": "1" * 40, "tree": "2" * 40},
                "published_source": {"head": "3" * 40, "tree": "2" * 40},
                "source_files": [v for v in review["source_files"] if v["path"].endswith(".rs")]}

    def verify(self, root, value):
        path = root / "manifest.json"
        path.write_text(json.dumps(value))
        return runner.frozen_input(path, runner.sha(path))

    def test_same_tree_distinct_commit_identity_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = self.fixture(root)
            actual, binary = self.verify(root, value)
            self.assertEqual(actual, value)
            self.assertEqual(binary, root / "agentd.elf")
            value["published_source"] = None
            self.assertEqual(self.verify(root, value)[0]["published_source"], None)

    def test_wrong_digest_size_source_tree_and_blob_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.fixture(root)
            values = []
            for key, bad in (("sha256", "0" * 64), ("bytes", 1)):
                value = copy.deepcopy(original)
                value["binary"][key] = bad
                values.append(value)
            value = copy.deepcopy(original)
            value["published_source"]["tree"] = "4" * 40
            values.append(value)
            value = copy.deepcopy(original)
            value["source_files"][0]["git_blob"] = "5" * 40
            values.append(value)
            value = copy.deepcopy(original)
            value["source_files"].append(value["source_files"][0])
            values.append(value)
            for value in values:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.verify(root, value)
            manifest = root / "manifest.json"
            self.verify(root, original)
            with self.assertRaises(ValueError):
                runner.frozen_input(manifest, "0" * 64)

    def test_binary_traversal_symlink_and_changed_frozen_file_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = self.fixture(root)
            value = copy.deepcopy(original)
            value["binary"]["path"] = "../agentd.elf"
            with self.assertRaises(ValueError): self.verify(root, value)
            (root / "alias.elf").symlink_to(root / "agentd.elf")
            value["binary"]["path"] = "alias.elf"
            with self.assertRaises(ValueError): self.verify(root, value)
            (root / "agentd.elf").write_bytes(b"changed Cargo output")
            with self.assertRaises(ValueError): self.verify(root, original)


class StagingTests(unittest.TestCase):
    def test_spawned_execution_is_retained_after_collector_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = {"executed": False, "passed": False}
            process = mock.MagicMock()
            process.stdout = object()
            process.poll.return_value = 0
            with mock.patch.object(runner.subprocess, "Popen") as spawn:
                spawn.return_value.__enter__.return_value = process
                with self.assertRaises(ValueError):
                    runner.run_qemu(["not-executed"], Path(tmp), 1, report)
            self.assertTrue(report["executed"])
            self.assertFalse(report["passed"])

    def test_default_disabled_never_calls_executor(self):
        output = io.StringIO()
        with mock.patch.object(runner, "execute", side_effect=AssertionError("unexpected execution")), contextlib.redirect_stdout(output):
            self.assertEqual(runner.main([]), 0)
        value = json.loads(output.getvalue())
        self.assertFalse(value["executed"])
        self.assertFalse(value["passed"])
        self.assertFalse(value["production"])

    def test_actual_elf_closure_is_inspected_without_running_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            info, libs = runner.stage_closure(Path("/bin/true").resolve(), Path(tmp), runner.tool("readelf"),
                [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib64")])
            self.assertEqual(info["interpreter"], "/lib64/ld-linux-x86-64.so.2")
            self.assertIn("libc.so.6", libs)
            self.assertIn("ld-linux-x86-64.so.2", libs)
            for item in libs.values():
                self.assertEqual(runner.sha(Path(tmp) / item["guest_path"].lstrip("/")), item["sha256"])

    def test_actual_initramfs_preserves_boot_and_original_entries(self):
        path = runner.HERE.parents[2] / "support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz"
        runner.pinned(path, runner.INITRAMFS_SHA, runner.LIMIT)
        original = runner.cpio_codec.unpack(gzip.decompress(path.read_bytes()))
        changed = runner.cpio_codec.unpack(gzip.decompress(runner.build_initramfs(path.read_bytes(), b"probe fixture", "a" * 64)))
        self.assertEqual(len(changed), len(original) + 1)
        by_name = {name: (fields, data) for name, fields, data in changed}
        for name, fields, data in original:
            if name.lstrip("./") == "init":
                self.assertEqual(by_name[name][1].count(runner.BOOT), 1)
                self.assertIn(b"mount -t ext2 -o ro /dev/vda /payload", by_name[name][1])
            else:
                self.assertEqual(by_name[name], (fields, data))


if __name__ == "__main__":
    unittest.main()
