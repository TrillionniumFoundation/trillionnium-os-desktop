from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools import validate_platform_mechanisms as gate


class PlatformMechanismInventoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        registry = json.loads((gate.ROOT / gate.REGISTRY).read_text())
        paths = {gate.REGISTRY}
        for module in registry["modules"]:
            paths.update(module[field] for field in ("implementation", "documentation", "contract", "tests"))
        for relative in paths:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(gate.ROOT / relative, destination)

    def test_real_source_registry_has_no_execution_or_qualification_claim(self):
        result = gate.validate(self.root)
        self.assertEqual(result["registered_modules"], 5)
        self.assertIs(result["execution_observed"], False)
        self.assertIs(result["qualification_changed"], False)

    def test_public_argument_change_invalidates_inventory(self):
        source = self.root / "platform/taskflow.py"
        text = source.read_text().replace("def cancel(self, task_id: str)", "def cancel(self, task_id: str, unsafe_override=False)", 1)
        self.assertNotEqual(text, source.read_text())
        source.write_text(text)
        with self.assertRaisesRegex(ValueError, "API inventory drift"):
            gate.validate(self.root)

    def test_new_platform_module_requires_explicit_registration(self):
        (self.root / "platform/unchecked_authority.py").write_text("def mint_authority(): return True\n")
        with self.assertRaisesRegex(ValueError, "unregistered"):
            gate.validate(self.root)

    def test_symlinked_contract_parent_cannot_supply_a_pass(self):
        contracts = self.root / "contracts"
        relocated = self.root / "external-contracts"
        contracts.rename(relocated)
        contracts.symlink_to(relocated, target_is_directory=True)
        with self.assertRaises(ValueError):
            gate.validate(self.root)

    def test_duplicate_registry_members_and_widened_claims_refused(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        path.write_text(original.replace('"qualification_changed": false', '"qualification_changed": false, "qualification_changed": true', 1))
        with self.assertRaises(ValueError):
            gate.validate(self.root)
        value = json.loads(original)
        value["claim_ceiling"] = "production_ready"
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            gate.validate(self.root)

    def test_module_id_and_requirement_cannot_be_reassigned(self):
        path = self.root / gate.REGISTRY
        original = json.loads(path.read_text())
        for field, replacement in (("id", "signed_update"), ("requirements", ["G6", "S11"]),
                                   ("tests", "tests/test_taskflow.py")):
            with self.subTest(field=field):
                value = json.loads(json.dumps(original))
                value["modules"][0][field] = replacement
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    gate.validate(self.root)

    def test_contract_claims_cannot_promote_source_candidate(self):
        for relative, transform in (
            ("contracts/trusted-app-bundle.v1.json", lambda c: c.update(status="PRODUCTION_READY")),
            ("contracts/controlled-egress.v1.json", lambda c: c.update(claim_ceiling="production_ready")),
            ("contracts/s11-update-recovery.v1.json", lambda c: c["non_claims"].update(release_published=True)),
            ("contracts/s11-update-recovery.v1.json", lambda c: c["non_claims"].update(production_ready=True)),
            ("contracts/app-storage.v1.json", lambda c: c.update(installed_engine_storage_enforcement=True)),
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_text()
                value = json.loads(original)
                transform(value)
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "contract"):
                    gate.validate(self.root)
                path.write_text(original)

    def test_class_function_and_method_calling_semantics_are_inventoried(self):
        original = "@dataclass(frozen=True)\nclass Value:\n    key: str\n    def fetch(self): pass\ndef load(): pass\n"
        for changed in (original.replace("frozen=True", "frozen=False"),
                        original.replace("def load", "async def load"),
                        original.replace("def load", "@require_owner\ndef load"),
                        original.replace("def fetch", "async def fetch")):
            with self.subTest(changed=changed):
                self.assertNotEqual(gate.api_inventory(original), gate.api_inventory(changed))
        protocol = "class Store:\n    def __exit__(self, exc_type, exc, tb): pass\n"
        self.assertNotEqual(gate.api_inventory(protocol), gate.api_inventory(protocol.replace("exc, tb", "exc, tb, required_extra")))

    def test_hardlinked_registry_source_is_refused(self):
        source = self.root / "platform/trusted_apps.py"
        os.link(source, self.root / "external-source-alias.py")
        with self.assertRaisesRegex(ValueError, "one link"):
            gate.validate(self.root)

    def test_conditional_public_declarations_are_explicitly_refused(self):
        for source in ("if True:\n    def added(): pass\n", "try:\n    class Added: pass\nexcept Exception: pass\n",
                       "class Value:\n    if True:\n        def added(self): pass\n"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "conditional public"):
                gate.api_inventory(source)
        with self.assertRaisesRegex(ValueError, "nested public classes"):
            gate.api_inventory("class Store:\n    class Nested:\n        def fetch(self): pass\n")

    def test_declared_unittest_free_function_cannot_supply_test_registration(self):
        (self.root / "tests/test_trusted_apps.py").write_text("def test_declared_only(): pass\n")
        with self.assertRaisesRegex(ValueError, "direct unittest.TestCase"):
            gate.validate(self.root)

    def test_refresh_does_not_follow_or_truncate_registry_alias(self):
        path = self.root / gate.REGISTRY
        alias = self.root / "external-registry.json"
        os.link(path, alias)
        original = alias.read_bytes()
        with self.assertRaisesRegex(ValueError, "one link"):
            gate.validate(self.root, refresh=True)
        self.assertEqual(alias.read_bytes(), original)

    def test_refresh_parent_substitution_cannot_report_success(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        actual_sync = os.fsync
        injected = False
        def substitute(descriptor):
            nonlocal injected
            actual_sync(descriptor)
            if not injected:
                injected = True
                (self.root / "manifests").rename(self.root / "detached")
                (self.root / "manifests").mkdir()
                path.write_text(original)
        with patch.object(gate.os, "fsync", substitute), self.assertRaisesRegex(ValueError, "parent custody"):
            gate.validate(self.root, refresh=True)
        self.assertEqual(path.read_text(), original)

    def test_refresh_staged_name_substitution_is_refused_and_preserved(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        actual_sync = os.fsync
        substituted = []
        def substitute(descriptor):
            actual_sync(descriptor)
            if not substituted:
                temporary = next((self.root / "manifests").glob(".platform-registry-*"))
                # Keep the actual original inode alive, so its number cannot be reused.
                temporary.rename(self.root / "detached-staged.json")
                temporary.write_text("substituted")
                substituted.append(temporary)
        with patch.object(gate.os, "fsync", substitute), self.assertRaisesRegex(ValueError, "staged inode custody"):
            gate.validate(self.root, refresh=True)
        self.assertEqual(path.read_text(), original)
        self.assertEqual(substituted[0].read_text(), "substituted")

    def test_refresh_sync_after_replace_requires_uncertainty_report(self):
        actual_sync = os.fsync
        calls = 0
        def refuse_directory(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("directory barrier refused")
            actual_sync(descriptor)
        with patch.object(gate.os, "fsync", refuse_directory), self.assertRaisesRegex(ValueError, "publication uncertain"):
            gate.validate(self.root, refresh=True)


if __name__ == "__main__":
    unittest.main()
