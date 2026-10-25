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
                     "support/ui/linux-preedit-profile.json", *guard.MIRRORED_FIXTURES.values()):
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
                path.write_text(original.replace(source, "a" * 40, 1))
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

    def test_readback_wire_cannot_drift_from_the_original_contract(self):
        for name in guard.MIRRORED_FIXTURES.values():
            path = self.root / name
            path.write_text(path.read_text().replace('"revision": 5', '"revision": 6'))
        with self.assertRaisesRegex(ValueError, "readback wire fixtures differ"):
            guard.verify(self.root)


if __name__ == "__main__":
    unittest.main()
