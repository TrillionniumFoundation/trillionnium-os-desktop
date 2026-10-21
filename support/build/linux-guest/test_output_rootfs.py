#!/usr/bin/env python3
"""Host-only output/rootfs separation tests; no compiler, VM, or mount."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("A01_LINUX_GUEST_SOURCE", str(HERE / "isolate.py")))
SPEC = importlib.util.spec_from_file_location("a01_linux_guest_output", SOURCE)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def snapshot(root):
    """Include names, types, permissions, bytes, and symlink targets."""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        row = {"mode": stat.S_IMODE(info.st_mode)}
        if path.is_symlink():
            row.update(kind="symlink", target=os.readlink(path))
        elif path.is_dir():
            row["kind"] = "directory"
        else:
            data = path.read_bytes()
            row.update(kind="file", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        result[str(path.relative_to(root))] = row
    return result


class OutputRootfsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-isolate-output-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.rootfs = self.root / "rootfs"
        (self.rootfs / "bin").mkdir(parents=True)
        (self.rootfs / "bin/probe").write_bytes(b"immutable rootfs fixture\n")
        (self.rootfs / "bin/probe").chmod(0o555)
        self.source = self.root / "source"
        reference_path = self.source / "tests/workloads/linux/baselines/linux-debian13-x86_64.json"
        reference_path.parent.mkdir(parents=True)
        reference_path.write_text(json.dumps({"cases": {"probe": {"status": "pass"}}}))
        manifest = self.source / "support/rootfs/manifest-debian13-x86_64.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"host_fixture": true}\n')
        self.inputs = {}
        for name in ("kernel.gz", "initramfs.gz", "firmware.bin", "qemu"):
            path = self.root / name
            path.write_bytes(("host fixture: " + name).encode())
            self.inputs[name] = path

    def argv(self, output, *, rootfs=None):
        return [str(SOURCE), "--a04-source-root", str(self.source),
                "--rootfs", str(rootfs or self.rootfs),
                "--a01-kernel-gz", str(self.inputs["kernel.gz"]),
                "--a01-initramfs", str(self.inputs["initramfs.gz"]),
                "--firmware", str(self.inputs["firmware.bin"]),
                "--qemu", str(self.inputs["qemu"]),
                "--out-dir", str(output), "--jobs", "1", "--timeout", "1"]

    def rejected(self, output, *, rootfs=None):
        before = snapshot(self.rootfs)
        existed = os.path.lexists(output)
        with mock.patch.object(sys, "argv", self.argv(output, rootfs=rootfs)), \
                mock.patch.object(RUNNER, "verified_source") as verified, \
                mock.patch.object(RUNNER, "imported") as imported, \
                mock.patch.object(RUNNER.subprocess, "Popen") as spawned, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as raised:
                RUNNER.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("output directory must be outside the verified rootfs", errors.getvalue())
        verified.assert_not_called()
        imported.assert_not_called()
        spawned.assert_not_called()
        self.assertEqual(snapshot(self.rootfs), before)
        self.assertEqual(os.path.lexists(output), existed)

    def test_direct_child_rejected_before_any_source_or_guest_work(self):
        self.rejected(self.rootfs / "evidence")

    def test_root_itself_is_rejected_without_mutation(self):
        self.rejected(self.rootfs)

    def test_nonexistent_deep_parents_are_not_created(self):
        self.rejected(self.rootfs / "new/nested/evidence")
        self.assertFalse((self.rootfs / "new").exists())

    def test_output_parent_symlink_into_rootfs_is_rejected(self):
        alias = self.root / "rootfs-alias"
        alias.symlink_to(self.rootfs, target_is_directory=True)
        self.rejected(alias / "nested/evidence")
        self.assertTrue(alias.is_symlink())

    def test_rootfs_argument_symlink_is_resolved(self):
        alias = self.root / "rootfs-alias"
        alias.symlink_to(self.rootfs, target_is_directory=True)
        self.rejected(self.rootfs / "evidence", rootfs=alias)

    def test_relative_paths_and_dotdot_cannot_hide_containment(self):
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            self.rejected(Path("rootfs/bin/../evidence"), rootfs=Path("rootfs"))
        finally:
            os.chdir(previous)

    @contextlib.contextmanager
    def host_pipeline(self, output):
        """Exercise real main/threads/files with fixture pack and QEMU APIs."""
        expected = snapshot(self.rootfs)
        events = []
        def sha_file(path):
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        def verify(rootfs, _manifest):
            events.append("verify")
            if snapshot(Path(rootfs)) != expected:
                raise ValueError("host fixture rootfs manifest differs")
        def pack(_original, rootfs, _manifest, _reference, image, inputs):
            events.append("pack")
            if snapshot(Path(rootfs)) != expected:
                raise ValueError("host fixture rootfs manifest differs after output creation")
            image.write_bytes(b"host fixture image")
            inputs.write_text('{"host_fixture": true}\n')
            return {"host_fixture": True}
        def parse(serial, _reference, _manifest, **_kwargs):
            if serial != "host fixture serial\n":
                raise ValueError("unexpected host fixture serial")
            return {"guest_execution_verified": True, "guest_compatibility_passed": True,
                    "cases": {"probe": {"status": "pass"}}}
        guest = SimpleNamespace(sha_file=sha_file,
                                reference_elf_cases=lambda _reference: [("probe", None, None)],
                                pack=pack, parse_serial=parse)
        preflight = mock.Mock(return_value=(b"host fixture kernel", "host fixture QEMU"))
        qemu = SimpleNamespace(guest=guest, preflight=preflight,
                               command_for_qemu=lambda *_args: ["never-executed-host-fixture"])
        capture = SimpleNamespace(verify=verify)
        class FixtureProcess:
            pid = 999999
            returncode = 33
            def poll(self):
                return self.returncode
            def wait(self, timeout=None):
                return self.returncode
        def popen(_argv, *, stdout, **_kwargs):
            events.append("fixture-popen")
            stdout.write(b"host fixture serial\n")
            return FixtureProcess()
        def imported(name, _path):
            return capture if name == "a04_isolated_rootfs" else qemu
        old_umask = os.umask(0o077)
        try:
            with mock.patch.object(sys, "argv", self.argv(output)), \
                    mock.patch.object(RUNNER, "verified_source", return_value={"host_fixture": True}), \
                    mock.patch.object(RUNNER, "imported", side_effect=imported), \
                    mock.patch.object(RUNNER.subprocess, "Popen", side_effect=popen) as spawned, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                yield events, spawned, preflight
        finally:
            os.umask(old_umask)

    def accepted(self, output):
        before = snapshot(self.rootfs)
        with self.host_pipeline(output) as (events, spawned, _preflight):
            status = RUNNER.main()
        self.assertEqual(status, 0)
        self.assertEqual(events, ["verify", "pack", "fixture-popen"])
        spawned.assert_called_once()
        self.assertEqual(snapshot(self.rootfs), before)
        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(summary["selected_case_count"], 1)
        self.assertEqual(summary["matched"], 1)
        self.assertFalse(summary["original_unmodified_suite_passed"])
        self.assertFalse(summary["full_w1_passed"])

    def test_independent_output_can_complete_host_fixture_pipeline(self):
        self.accepted(self.root / "evidence")

    def test_sibling_with_same_text_prefix_is_allowed(self):
        self.accepted(self.root / "rootfs-evidence")

    def test_output_parent_alias_to_independent_directory_is_allowed(self):
        independent = self.root / "independent"
        independent.mkdir()
        alias = self.root / "independent-alias"
        alias.symlink_to(independent, target_is_directory=True)
        self.accepted(alias / "evidence")

    def test_existing_output_remains_rejected_and_unmodified(self):
        output = self.root / "evidence"
        output.mkdir()
        sentinel = output / "keep"
        sentinel.write_bytes(b"existing evidence")
        before = snapshot(self.rootfs)
        with self.host_pipeline(output) as (events, spawned, _preflight):
            with self.assertRaises(SystemExit) as raised:
                RUNNER.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(events, ["verify"])
        spawned.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"existing evidence")
        self.assertEqual(sorted(path.name for path in output.iterdir()), ["keep"])
        self.assertEqual(snapshot(self.rootfs), before)

    def test_dangling_output_symlink_remains_rejected(self):
        target = self.root / "absent-target"
        output = self.root / "output-alias"
        output.symlink_to(target, target_is_directory=True)
        before = snapshot(self.rootfs)
        with self.host_pipeline(output) as (events, spawned, _preflight):
            with self.assertRaises(SystemExit) as raised:
                RUNNER.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(events, ["verify"])
        spawned.assert_not_called()
        self.assertTrue(output.is_symlink())
        self.assertFalse(target.exists())
        self.assertEqual(snapshot(self.rootfs), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
