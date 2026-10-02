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
        self.assertEqual(result["registered_modules"], 6)
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

    def test_durable_owner_requires_its_fixed_sixth_registration(self):
        path = self.root / gate.REGISTRY
        original = json.loads(path.read_text())
        for change in ("missing", "duplicate", "requirements", "implementation", "documentation", "contract", "tests"):
            with self.subTest(change=change):
                value = json.loads(json.dumps(original))
                module = next(item for item in value["modules"] if item["id"] == "durable_update_owner")
                if change == "missing":
                    value["modules"].remove(module)
                elif change == "duplicate":
                    module["id"] = "signed_update"
                elif change == "requirements":
                    module[change] = ["G6", "S11"]
                else:
                    module[change] = next(item for item in value["modules"] if item["id"] == "signed_update")[change]
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): gate.validate(self.root, refresh=True)

    def test_egress_cleanup_contract_remains_closed_and_cannot_mint_retry_authority(self):
        path = self.root / "contracts/controlled-egress.v1.json"
        original = path.read_text()
        for field in ("cleanup", "interruption_evidence_scope"):
            with self.subTest(missing=field):
                value = json.loads(original)
                del value["outcome"][field]
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "contract nested object"):
                    gate.validate(self.root, refresh=True)
        for field, replacement in (("cleanup_confirmed_by_caller", True),
                                   ("automatic_retry", True),
                                   ("durable_delivery_or_external_effect_proof", True),
                                   ("automatic_retry", 0)):
            with self.subTest(field=field, replacement=replacement):
                value = json.loads(original)
                value["outcome"][field] = replacement
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "contract"):
                    gate.validate(self.root, refresh=True)
        path.write_text(original)
        gate.validate(self.root)

    def test_durable_owner_profile_closes_every_actual_nested_object_and_leaf(self):
        contract = json.loads((self.root / "contracts/durable-update-owner.v1.json").read_text())
        objects, leaves = {}, {}
        def collect(value, prefix=""):
            for key, item in value.items():
                name = key if not prefix else prefix + "/" + key
                if type(item) is dict:
                    objects[name] = sorted(item)
                    collect(item, name)
                else:
                    leaves[name] = item
        collect(contract)
        profile = gate.CONTRACT_PROFILES["durable_update_owner"]
        self.assertEqual(profile["fields"], sorted(contract))
        self.assertEqual(profile["objects"], objects)
        self.assertEqual(profile["claims"], leaves)

    def test_durable_owner_nested_object_extra_or_missing_fields_cannot_pass(self):
        path = self.root / "contracts/durable-update-owner.v1.json"
        original = path.read_text()
        for name in gate.CONTRACT_PROFILES["durable_update_owner"]["objects"]:
            for change in ("extra", "missing"):
                with self.subTest(name=name, change=change):
                    contract = json.loads(original)
                    target = contract
                    for part in name.split("/"): target = target[part]
                    if change == "extra": target["production_ready"] = True
                    else: del target[next(iter(target))]
                    path.write_text(json.dumps(contract))
                    with self.assertRaisesRegex(ValueError, "contract nested object"):
                        gate.validate(self.root)
        path.write_text(original)

    def test_durable_owner_null_and_false_claims_reject_activation_and_numeric_aliases(self):
        path = self.root / "contracts/durable-update-owner.v1.json"
        original = path.read_text()
        reviewed = gate.CONTRACT_PROFILES["durable_update_owner"]["claims"]
        for name, expected in reviewed.items():
            if expected is not None and expected is not False:
                continue
            for replacement in (({}, True) if expected is None else (True, 0)):
                with self.subTest(name=name, replacement=replacement):
                    contract = json.loads(original)
                    parts = name.split("/")
                    target = contract
                    for part in parts[:-1]: target = target[part]
                    target[parts[-1]] = replacement
                    path.write_text(json.dumps(contract))
                    with self.assertRaisesRegex(ValueError, "contract identity, default or claim"):
                        gate.validate(self.root, refresh=True)
        path.write_text(original)

    def test_durable_owner_transition_artifact_and_status_cannot_be_reinterpreted(self):
        path = self.root / "contracts/durable-update-owner.v1.json"
        original = path.read_text()
        cases = (("status", "PRODUCTION_READY"), ("claim_ceiling", "installed_update_ready"),
                 ("artifacts/dependency", "platform/taskflow.py"),
                 ("history/transitions/boot_policy_armed", ["owner_clean"]),
                 ("history/event_phases/boot_policy_armed", "committed"),
                 ("recovery/marker_binding", "caller_digest_and_status"),
                 ("public_api/DurableUpdateOwner/methods/arm_first_boot", ["caller_health"]))
        for name, replacement in cases:
            with self.subTest(name=name):
                contract = json.loads(original)
                parts = name.split("/")
                target = contract
                for part in parts[:-1]: target = target[part]
                target[parts[-1]] = replacement
                path.write_text(json.dumps(contract))
                with self.assertRaisesRegex(ValueError, "contract identity, default or claim"):
                    gate.validate(self.root)
        path.write_text(original)

    def test_assembly_status_cannot_be_added_to_registry_or_module(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        for target in ("registry", "module", "qualification"):
            with self.subTest(target=target):
                value = json.loads(original)
                if target == "registry": value["status"] = "PRODUCTION_READY"
                elif target == "module":
                    next(item for item in value["modules"] if item["id"] == "durable_update_owner")["status"] = "INSTALLED_READY"
                else: value["qualification_changed"] = True
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): gate.validate(self.root, refresh=True)

    def test_api_refresh_changes_only_signatures_never_profiles_or_qualification(self):
        path = self.root / gate.REGISTRY
        original = json.loads(path.read_text())
        profiles = json.dumps(gate.CONTRACT_PROFILES, sort_keys=True)
        source = self.root / "platform/durable_update_owner.py"
        changed = source.read_text().replace("def confirm_result(self, result: DurableUpdateResult)", "def confirm_result(self, result: DurableUpdateResult, reviewed_argument=None)", 1)
        self.assertNotEqual(changed, source.read_text())
        source.write_text(changed)
        result = gate.validate(self.root, refresh=True)
        updated = json.loads(path.read_text())
        self.assertEqual(result["registered_modules"], 6)
        self.assertIs(result["qualification_changed"], False)
        self.assertEqual(json.dumps(gate.CONTRACT_PROFILES, sort_keys=True), profiles)
        self.assertEqual({key: value for key, value in original.items() if key != "modules"}, {key: value for key, value in updated.items() if key != "modules"})
        for before, after in zip(original["modules"], updated["modules"]):
            self.assertEqual({key: value for key, value in before.items() if key != "source_defined_api"}, {key: value for key, value in after.items() if key != "source_defined_api"})
            if before["id"] != "durable_update_owner": self.assertEqual(before, after)
        self.assertNotEqual(original["modules"][-1]["source_defined_api"], updated["modules"][-1]["source_defined_api"])
        gate.validate(self.root)

    def test_api_refresh_refuses_contract_promotion_before_registry_publication(self):
        path = self.root / gate.REGISTRY
        original = path.read_bytes()
        source = self.root / "platform/durable_update_owner.py"
        source.write_text(source.read_text().replace("def inspect(self)", "def inspect(self, new_parameter=None)", 1))
        contract_path = self.root / "contracts/durable-update-owner.v1.json"
        contract = json.loads(contract_path.read_text())
        contract["status"] = "PRODUCTION_READY"
        contract_path.write_text(json.dumps(contract))
        with self.assertRaisesRegex(ValueError, "contract identity, default or claim"):
            gate.validate(self.root, refresh=True)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".platform-registry-*")), [])

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

    def test_refresh_oversized_output_is_refused_before_publication(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        with self.assertRaisesRegex(ValueError, "before publication"):
            gate.refresh_registry(self.root, original, {"oversized": "x" * gate.MAX_BYTES})
        self.assertEqual(path.read_text(), original)
        self.assertEqual(list(path.parent.glob(".platform-registry-*")), [])

    def test_refresh_entropy_failure_leaks_no_descriptor(self):
        path = self.root / gate.REGISTRY
        original = path.read_text()
        before = len(os.listdir("/proc/self/fd"))
        with patch.object(gate.secrets, "token_hex", side_effect=OSError("entropy unavailable")), self.assertRaises(OSError):
            gate.refresh_registry(self.root, original, json.loads(original))
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
