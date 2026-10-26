"""Cross-root source drift must fail before an expensive native build."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("product_dependencies", Path(__file__).with_name("verify_product_dependencies.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ProductDependencies(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in (*guard.MANIFESTS, *guard.LOCKS, guard.SOURCE,
                     "support/ui/linux-preedit-profile.json", "support/ui/linux-text-profile.json",
                     *guard.MIRRORED_FIXTURES.values()):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(guard.ROOT / name, target)

    def test_committed_pair_and_both_locks_agree(self):
        self.assertTrue(guard.verify(self.root)["passed"])

    def test_one_manifest_cannot_select_another_original_owner(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        source = json.loads((self.root / guard.SOURCE).read_text())["commit"]
        path.write_text(path.read_text().replace(source, "a" * 40, 1))
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted|Mixed original Hepta dependency"):
            guard.verify(self.root)

    def test_original_owner_cannot_be_replaced_by_a_path_dependency(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        lines = path.read_text().splitlines()
        lines = ['codex-hepta-memory = { path = "../substitute" }'
                 if line.startswith("codex-hepta-memory =") else line for line in lines]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted"):
            guard.verify(self.root)

    def test_each_lock_rejects_an_old_original_source(self):
        for name in guard.LOCKS:
            with self.subTest(lock=name):
                path = self.root / name
                original = path.read_text()
                source = json.loads((self.root / guard.SOURCE).read_text())["commit"]
                if source in original:
                    changed = original.replace(source, "a" * 40, 1)
                else:
                    # These independent contract roots have no original Hepta
                    # dependency. Introduce an actual foreign source rather
                    # than expecting a no-op string replacement to fail.
                    changed = original + '\n[[package]]\nname = "foreign-original-graph"\nversion = "0.0.0"\nsource = "git+' + guard.REPOSITORY + '?rev=' + "a" * 40 + '#' + "a" * 40 + '"\n'
                path.write_text(changed)
                with self.assertRaisesRegex(ValueError, "Mixed original Hepta sources"):
                    guard.verify(self.root)
                path.write_text(original)

    def test_missing_owner_is_not_an_empty_successful_lock(self):
        (self.root / "services/hepta-session-host/Cargo.lock").write_text("version = 4\n")
        with self.assertRaisesRegex(ValueError, "Original owner packages missing"):
            guard.verify(self.root)

    def test_missing_shared_compiler_is_refused(self):
        path = self.root / guard.SOURCE
        source = json.loads(path.read_text())
        source["files"] = [entry for entry in source["files"] if entry["path"] not in guard.REQUIRED_FILES]
        path.write_text(json.dumps(source))
        with self.assertRaisesRegex(ValueError, "shared literal Notes compiler"):
            guard.verify(self.root)

    def test_preedit_cannot_silently_use_another_companion(self):
        path = self.root / "support/ui/linux-preedit-profile.json"
        profile = json.loads(path.read_text())
        profile["hepta_commit"] = "b" * 40
        path.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, "Preedit profile differs"):
            guard.verify(self.root)

    def test_composer_boundary_and_its_sdk_regression_cannot_be_omitted(self):
        path = self.root / guard.SOURCE
        original = json.loads(path.read_text())
        for name in ("composer_transaction.rs", "composer_transaction_tests.rs"):
            with self.subTest(source=name):
                source = dict(original, files=[entry for entry in original["files"]
                    if Path(entry["path"]).name != name])
                path.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError, "original composer transaction"):
                    guard.verify(self.root)
        path.write_text(json.dumps(original))

    def test_readback_wire_cannot_drift_from_the_original_contract(self):
        name = guard.MIRRORED_FIXTURES["codex-rs/hepta-agentd/tests/fixtures/notes-document-observation-v1.json"]
        path = self.root / name
        path.write_text(path.read_text().replace('"revision": 5', '"revision": 6'))
        with self.assertRaisesRegex(ValueError, "readback wire fixtures differ"):
            guard.verify(self.root)

    def test_model_identity_fixture_cannot_drift(self):
        name = guard.MIRRORED_FIXTURES["codex-rs/hepta-agentd/tests/fixtures/notes-model-v1.json"]
        path = self.root / name
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "readback wire fixtures differ"):
            guard.verify(self.root)

    def test_root_dependency_cannot_be_replaced_by_a_path(self):
        path = self.root / "services/hepta-session-host/Cargo.toml"
        lines = path.read_text().splitlines()
        lines = ['codex-hepta-supervisor = { path = "../substitute", optional = true }'
                 if line.startswith("codex-hepta-supervisor =") else line for line in lines]
        path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "Original owner dependency substituted"):
            guard.verify(self.root)

    def test_original_aws_security_patch_must_be_carried_by_both_roots(self):
        for name in ("ui/Cargo.toml", "services/hepta-session-host/Cargo.toml"):
            path = self.root / name
            original = path.read_text()
            path.write_text("\n".join(line for line in original.splitlines()
                                      if not line.startswith("aws-config =")) + "\n")
            with self.subTest(manifest=name), self.assertRaisesRegex(ValueError, "AWS security patch missing"):
                guard.verify(self.root)
            path.write_text(original)

    def test_common_package_version_cannot_drift_in_one_lock(self):
        path = self.root / "services/hepta-os/Cargo.lock"
        original = path.read_text()
        self.assertIn('name = "serde_json"\nversion = "1.0.154"', original)
        path.write_text(original.replace('name = "serde_json"\nversion = "1.0.154"',
                                         'name = "serde_json"\nversion = "1.0.151"'))
        with self.assertRaisesRegex(ValueError, "Shared package version differs"):
            guard.verify(self.root)

    def test_default_and_prepared_sdk_locks_cannot_be_interchanged(self):
        ordinary = self.root / "ui/Cargo.lock"
        prepared = self.root / "support/ui/preedit-sdk/Cargo.lock"
        ordinary_bytes, prepared_bytes = ordinary.read_bytes(), prepared.read_bytes()
        prepared.write_bytes(ordinary_bytes)
        with self.assertRaisesRegex(ValueError, "Prepared UI lock must resolve"):
            guard.verify(self.root)
        prepared.write_bytes(prepared_bytes)
        ordinary.write_bytes(prepared_bytes)
        with self.assertRaisesRegex(ValueError, "Default UI lock must retain"):
            guard.verify(self.root)


if __name__ == "__main__":
    unittest.main()
