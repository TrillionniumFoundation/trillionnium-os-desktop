from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import compare_d1_builds  # noqa: E402
import d1_rootfs_manifest  # noqa: E402
import finalize_d1_evidence  # noqa: E402
import prepare_d1_inputs  # noqa: E402
import resolve_debian_snapshot_with_pinned_keys  # noqa: E402
import verify_d1_artifact  # noqa: E402


@contextmanager
def argv(*values: str):
    original = sys.argv
    sys.argv = [original[0], *values]
    try:
        yield
    finally:
        sys.argv = original


class D1RawCliPathSafetyTests(unittest.TestCase):
    """CLI roots are checked lexically before any symlink resolution."""

    def test_rootfs_manifest_rejects_symlink_root_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_root = root / "real-root"
            real_root.mkdir()
            root_alias = root / "root-alias"
            root_alias.symlink_to(real_root, target_is_directory=True)
            output = root / "manifest.json"
            with argv("--root", str(root_alias), "--output", str(output)):
                with self.assertRaises(SystemExit):
                    d1_rootfs_manifest.main()

            output_target = root / "target.json"
            output_target.write_text("sentinel", encoding="utf-8")
            output_alias = root / "output-alias.json"
            output_alias.symlink_to(output_target)
            with argv("--root", str(real_root), "--output", str(output_alias)):
                with self.assertRaises(SystemExit):
                    d1_rootfs_manifest.main()
            self.assertEqual(output_target.read_text(encoding="utf-8"), "sentinel")

    def test_verify_rejects_symlink_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "artifact"
            real.mkdir()
            alias = root / "artifact-alias"
            alias.symlink_to(real, target_is_directory=True)
            with argv(str(alias)):
                with self.assertRaises(SystemExit):
                    verify_d1_artifact.main()

    def test_compare_rejects_symlink_build_root_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            first_alias = root / "first-alias"
            first_alias.symlink_to(first, target_is_directory=True)
            prepared = root / "prepared.json"
            prepared.write_text("{}", encoding="utf-8")
            result = root / "result.json"
            with argv(
                "--first",
                str(first_alias),
                "--second",
                str(second),
                "--prepared-inputs",
                str(prepared),
                "--result",
                str(result),
            ):
                with self.assertRaises(SystemExit):
                    compare_d1_builds.main()

            result_target = root / "result-target.json"
            result_target.write_text("sentinel", encoding="utf-8")
            result_alias = root / "result-alias.json"
            result_alias.symlink_to(result_target)
            with argv(
                "--first",
                str(first),
                "--second",
                str(second),
                "--prepared-inputs",
                str(prepared),
                "--result",
                str(result_alias),
            ):
                with self.assertRaises(SystemExit):
                    compare_d1_builds.main()
            self.assertEqual(
                result_target.read_text(encoding="utf-8"), "sentinel"
            )

    def test_prepare_rejects_symlink_input_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real.json"
            real.write_text("{}", encoding="utf-8")
            selection_alias = root / "selection-alias.json"
            selection_alias.symlink_to(real)
            paths = [root / name for name in ("baseline.json", "d1.json", "requirements.json")]
            for path in paths:
                path.write_text("{}", encoding="utf-8")
            output = root / "prepared"
            with argv(
                "--selection",
                str(selection_alias),
                "--baseline-lock",
                str(paths[0]),
                "--d1-lock",
                str(paths[1]),
                "--requirements",
                str(paths[2]),
                "--output-dir",
                str(output),
            ):
                with self.assertRaises(SystemExit):
                    prepare_d1_inputs.main()

            child_target = root / "sources-target.list"
            child_target.write_text("sentinel", encoding="utf-8")
            child_alias = output / "sources.list"
            output.mkdir()
            child_alias.symlink_to(child_target)
            with self.assertRaises(RuntimeError):
                prepare_d1_inputs._reject_symlink_output(
                    child_alias, "sources list"
                )

            output_target = root / "prepared-target"
            output_target.mkdir()
            output_alias = root / "prepared-alias"
            output_alias.symlink_to(output_target, target_is_directory=True)
            selection = root / "selection.json"
            selection.write_text("{}", encoding="utf-8")
            with argv(
                "--selection",
                str(selection),
                "--baseline-lock",
                str(paths[0]),
                "--d1-lock",
                str(paths[1]),
                "--requirements",
                str(paths[2]),
                "--output-dir",
                str(output_alias),
            ):
                with self.assertRaises(SystemExit):
                    prepare_d1_inputs.main()

    def test_finalize_rejects_symlink_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            output = root / "output"
            repository.mkdir()
            output.mkdir()
            artifact_alias = root / "artifact-alias"
            artifact_alias.symlink_to(output, target_is_directory=True)
            with argv(
                "--repository",
                str(repository),
                "--root",
                str(output),
                "--artifact-root",
                str(artifact_alias),
            ):
                with self.assertRaises(SystemExit):
                    finalize_d1_evidence.main()

    def test_finalize_rejects_symlinked_internal_evidence_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            source = outside / "result.json"
            source.write_text("{}", encoding="utf-8")
            alias = root / "evidence-alias"
            alias.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                finalize_d1_evidence.load_json(alias / "result.json")
            with self.assertRaises(ValueError):
                finalize_d1_evidence.sha256(alias / "result.json")

    def test_finalize_rejects_symlinked_git_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            git_target = root / "git-target"
            git_target.mkdir()
            (repository / ".git").symlink_to(git_target, target_is_directory=True)
            output = root / "output"
            output.mkdir()
            artifact = root / "artifact"
            with argv(
                "--repository",
                str(repository),
                "--root",
                str(output),
                "--artifact-root",
                str(artifact),
            ):
                with self.assertRaises(SystemExit):
                    finalize_d1_evidence.main()

    def test_pinned_resolver_rejects_symlinked_cli_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            requirements_target = root / "requirements.json"
            requirements_target.write_text("{}", encoding="utf-8")
            requirements_alias = root / "requirements-alias.json"
            requirements_alias.symlink_to(requirements_target)
            output = root / "output.json"
            work = root / "work"
            logs = root / "logs"
            with argv(
                "--requirements",
                str(requirements_alias),
                "--output",
                str(output),
                "--work-dir",
                str(work),
                "--logs",
                str(logs),
            ):
                with self.assertRaises((RuntimeError, SystemExit)):
                    resolve_debian_snapshot_with_pinned_keys.main()

            requirements = root / "requirements-real.json"
            requirements.write_text("{}", encoding="utf-8")
            work_target = root / "work-target"
            work_target.mkdir()
            work_alias = root / "work-alias"
            work_alias.symlink_to(work_target, target_is_directory=True)
            with argv(
                "--requirements",
                str(requirements),
                "--output",
                str(output),
                "--work-dir",
                str(work_alias),
                "--logs",
                str(logs),
            ):
                with self.assertRaises((RuntimeError, SystemExit)):
                    resolve_debian_snapshot_with_pinned_keys.main()

    def test_pinned_resolver_rejects_trust_root_path_traversal_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "work"
            destination = work / "trust-roots"
            destination.mkdir(parents=True)
            destination_target = root / "destination-target.asc"
            destination_target.write_text("sentinel", encoding="utf-8")
            destination_alias = destination / "debian-13-archive.asc"
            destination_alias.symlink_to(destination_target)
            requirements = {
                "trust_roots": [
                    {
                        "id": "debian-13-archive",
                        "url": "https://ftp-master.debian.org/keys/archive-key-13.asc",
                        "primary_fingerprint": "A" * 40,
                    }
                ]
            }
            with self.assertRaises(RuntimeError):
                resolve_debian_snapshot_with_pinned_keys.build_keyring(
                    requirements, work
                )

            requirements["trust_roots"][0]["id"] = "../escape"
            with self.assertRaises(RuntimeError):
                resolve_debian_snapshot_with_pinned_keys.build_keyring(
                    requirements, root / "other-work"
                )

    def test_parent_symlink_is_not_erased_by_raw_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            alias_parent = root / "alias-parent"
            alias_parent.symlink_to(real_parent, target_is_directory=True)
            candidate = alias_parent / "child" / "output.json"
            for module in (
                d1_rootfs_manifest,
                compare_d1_builds,
                prepare_d1_inputs,
                verify_d1_artifact,
                finalize_d1_evidence,
            ):
                with self.subTest(module=module.__name__):
                    self.assertTrue(module._has_symlink_component(candidate))


if __name__ == "__main__":
    unittest.main()
