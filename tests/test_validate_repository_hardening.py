from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_repository_hardening_under_test",
    ROOT / "tools/validate_repository.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


class ValidateRepositoryHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_root = VALIDATOR.ROOT
        self.original_members = VALIDATOR.EXPECTED_WORKSPACE_MEMBERS
        VALIDATOR.ERRORS.clear()

    def tearDown(self) -> None:
        VALIDATOR.ROOT = self.original_root
        VALIDATOR.EXPECTED_WORKSPACE_MEMBERS = self.original_members
        VALIDATOR.ERRORS.clear()

    def test_checksum_requires_lowercase_64_hex(self) -> None:
        self.assertTrue(VALIDATOR.is_sha256_hex("a" * 64))
        for value in ("A" * 64, "a" * 63, "a" * 65, "g" * 64, None, 1):
            with self.subTest(value=value):
                self.assertFalse(VALIDATOR.is_sha256_hex(value))

    def test_safe_relative_path_rejects_traversal_absolute_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "root"
            base.mkdir()
            outside = Path(directory) / "outside"
            outside.write_text("do not read", encoding="utf-8")
            (base / "redirect").symlink_to(outside)

            for value in ("../outside", "/tmp/outside", "nested/../file", "redirect"):
                with self.subTest(value=value):
                    VALIDATOR.ERRORS.clear()
                    self.assertIsNone(
                        VALIDATOR.safe_relative_path(
                            value, base=base, label="test path"
                        )
                    )
                    self.assertTrue(VALIDATOR.ERRORS, value)

            VALIDATOR.ERRORS.clear()
            self.assertEqual(
                VALIDATOR.safe_relative_path(
                    "nested/file", base=base, label="test path"
                ),
                base / "nested" / "file",
            )
            self.assertEqual(VALIDATOR.ERRORS, [])

    def test_active_plan_cannot_escape_docs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "manifests").mkdir()
            (root / "docs/MANIFEST.json").write_text(
                json.dumps(
                    {
                        "active_plan": "../outside.md",
                        "active_plan_revision": "test",
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifests/repository-state.json").write_text(
                "{}", encoding="utf-8"
            )
            VALIDATOR.ROOT = root
            VALIDATOR.check_plan_and_manifests()
            self.assertTrue(
                any("active_plan" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def _write_lock_fixture(
        self, root: Path, *, allowlist_checksum: str, lock_checksum: str
    ) -> None:
        (root / "manifests").mkdir(parents=True)
        (root / "Cargo.toml").write_text(
            '[workspace]\nmembers = []\ndefault-members = []\n',
            encoding="utf-8",
        )
        (root / "manifests/product-boundary.json").write_text(
            '{"desktop_default_graph": {}}', encoding="utf-8"
        )
        (root / "manifests/cargo-external-allowlist.json").write_text(
            json.dumps(
                {
                    "packages": [
                        {
                            "name": "fixture",
                            "version": "1.0.0",
                            "checksum": allowlist_checksum,
                        }
                    ],
                    "direct_dependencies": {},
                }
            ),
            encoding="utf-8",
        )
        (root / "Cargo.lock").write_text(
            "\n".join(
                [
                    "[[package]]",
                    'name = "fixture"',
                    'version = "1.0.0"',
                    f'source = "{REGISTRY}"',
                    f'checksum = "{lock_checksum}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_allowlist_checksum_shape_is_not_self_consistent_bypassable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_lock_fixture(
                root, allowlist_checksum="A" * 64, lock_checksum="A" * 64
            )
            VALIDATOR.ROOT = root
            VALIDATOR.EXPECTED_WORKSPACE_MEMBERS = []
            VALIDATOR.check_workspace_and_lock()
            self.assertTrue(
                any("allowlist checksum" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )
            self.assertTrue(
                any("Cargo.lock registry checksum" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def test_direct_allowlist_member_must_be_safe_workspace_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_lock_fixture(
                root,
                allowlist_checksum="a" * 64,
                lock_checksum="a" * 64,
            )
            allowlist_path = root / "manifests/cargo-external-allowlist.json"
            allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
            allowlist["direct_dependencies"] = {"../outside": {"fixture": "=1.0.0"}}
            allowlist_path.write_text(json.dumps(allowlist), encoding="utf-8")
            VALIDATOR.ROOT = root
            VALIDATOR.EXPECTED_WORKSPACE_MEMBERS = []
            VALIDATOR.check_workspace_and_lock()
            self.assertTrue(
                any("direct dependency manifest" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def test_workspace_path_dependency_must_remain_under_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            root = sandbox / "repo"
            root.mkdir()
            member_dir = root / "crates/member"
            member_dir.mkdir(parents=True)
            inside = root / "crates/sibling"
            inside.mkdir(parents=True)
            outside = sandbox / "outside"
            outside.mkdir()
            manifest = member_dir / "Cargo.toml"
            manifest.write_text("[package]\nname = 'member'\n", encoding="utf-8")
            VALIDATOR.ROOT = root

            VALIDATOR.ERRORS.clear()
            self.assertEqual(
                VALIDATOR.safe_workspace_dependency_path(
                    "../sibling", manifest_path=manifest, label="test dependency"
                ),
                inside,
            )
            self.assertEqual(VALIDATOR.ERRORS, [])

            VALIDATOR.ERRORS.clear()
            self.assertIsNone(
                VALIDATOR.safe_workspace_dependency_path(
                    "../../../" + outside.name,
                    manifest_path=manifest,
                    label="test dependency",
                )
            )
            self.assertTrue(
                any("escapes" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def test_workspace_path_dependency_rejects_symlinked_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            root = sandbox / "repo"
            root.mkdir()
            member_dir = root / "crates/member"
            member_dir.mkdir(parents=True)
            outside = sandbox / "symlink-target"
            outside.mkdir()
            link = member_dir / "linked"
            link.symlink_to(outside, target_is_directory=True)
            manifest = member_dir / "Cargo.toml"
            manifest.write_text("[package]\nname = 'member'\n", encoding="utf-8")
            VALIDATOR.ROOT = root
            VALIDATOR.ERRORS.clear()
            self.assertIsNone(
                VALIDATOR.safe_workspace_dependency_path(
                    "linked", manifest_path=manifest, label="test dependency"
                )
            )
            self.assertTrue(
                any("symlink" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

            VALIDATOR.ERRORS.clear()
            self.assertIsNone(
                VALIDATOR.safe_workspace_dependency_path(
                    "linked/../member",
                    manifest_path=manifest,
                    label="test dependency",
                )
            )
            self.assertTrue(
                any(
                    token in error
                    for token in ("symlink", "escapes")
                    for error in VALIDATOR.ERRORS
                ),
                VALIDATOR.ERRORS,
            )

    def test_workspace_validator_checks_manifest_path_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            root = sandbox / "repo"
            member_dir = root / "crates/member"
            member_dir.mkdir(parents=True)
            (root / "manifests").mkdir()
            (root / "Cargo.toml").write_text(
                '[workspace]\nmembers = ["crates/member"]\n'
                'default-members = ["crates/member"]\n',
                encoding="utf-8",
            )
            (member_dir / "Cargo.toml").write_text(
                "[package]\nname = 'member'\nversion = '0.1.0'\n\n"
                "[dependencies]\n"
                "escaped = { path = '../../../outside' }\n",
                encoding="utf-8",
            )
            (root / "manifests/product-boundary.json").write_text(
                '{"desktop_default_graph": {}}', encoding="utf-8"
            )
            (root / "manifests/cargo-external-allowlist.json").write_text(
                json.dumps(
                    {
                        "packages": [],
                        "direct_dependencies": {"crates/member": {}},
                    }
                ),
                encoding="utf-8",
            )
            (root / "Cargo.lock").write_text(
                '[[package]]\nname = "member"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            VALIDATOR.ROOT = root
            VALIDATOR.EXPECTED_WORKSPACE_MEMBERS = ["crates/member"]
            VALIDATOR.check_workspace_and_lock()
            self.assertTrue(
                any(
                    "workspace path dependency" in error and "escapes" in error
                    for error in VALIDATOR.ERRORS
                ),
                VALIDATOR.ERRORS,
            )

    def test_loaders_reject_symlinked_and_nonregular_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text('{"trusted": true}', encoding="utf-8")
            link = root / "manifest.json"
            link.symlink_to(outside)
            VALIDATOR.ROOT = root

            self.assertEqual(VALIDATOR.load_json(link), {})
            self.assertTrue(
                any("invalid JSON" in error and "symlink" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )
            VALIDATOR.ERRORS.clear()
            with self.assertRaises(OSError):
                VALIDATOR._read_text_nofollow(root / "manifest.json")
            VALIDATOR.ERRORS.clear()
            (root / "directory").mkdir()
            self.assertEqual(VALIDATOR.load_toml(root / "directory"), {})
            self.assertTrue(
                any("invalid TOML" in error and "regular file" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )


if __name__ == "__main__":
    unittest.main()
