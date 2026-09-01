from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "verify_systemd_socket_custody_under_test",
    ROOT / "tools/verify_systemd_socket_custody.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
import validate_d3_development_profile as D3_PROFILE  # noqa: E402


class UnitParserTests(unittest.TestCase):
    def test_repository_units_parse_with_strict_policy_allowlist(self) -> None:
        socket = VALIDATOR.parse_unit(ROOT / "packaging/debian/systemd/hepta-browserd-agent.socket")
        service = VALIDATOR.parse_unit(ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service")
        self.assertIn("Socket", socket)
        self.assertIn("Service", service)

    def test_unknown_directive_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "unsafe.socket"
            path.write_text("[Socket]\nListenDatagram=/tmp/extra.sock\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                VALIDATOR.parse_unit(path)

    def test_duplicate_single_value_directive_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "unsafe.service"
            path.write_text("[Service]\nUser=hepta-browserd\nUser=root\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                VALIDATOR.parse_unit(path)

    def test_syscall_filter_policy_rejects_state_reset(self) -> None:
        filters = [
            "@system-service pidfd_open",
            "",
            "~@mount @raw-io @reboot @swap @privileged @resources @obsolete @debug",
        ]
        with self.assertRaises(AssertionError):
            VALIDATOR.validate_system_call_filters(filters)

    def test_syscall_filter_policy_rejects_inserted_positive_rule(self) -> None:
        filters = [
            "@system-service pidfd_open",
            "@mount",
            "~@mount @raw-io @reboot @swap @privileged @resources @obsolete @debug",
        ]
        with self.assertRaises(AssertionError):
            VALIDATOR.validate_system_call_filters(filters)

    def test_syscall_filter_policy_rejects_duplicate_deny_token(self) -> None:
        filters = [
            "@system-service pidfd_open",
            "~@mount @raw-io @reboot @swap @privileged @resources @obsolete @debug @debug",
        ]
        with self.assertRaises(AssertionError):
            VALIDATOR.validate_system_call_filters(filters)

    def test_syscall_filter_policy_accepts_reviewed_unit(self) -> None:
        service = VALIDATOR.parse_unit(ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service")
        VALIDATOR.validate_system_call_filters(service["Service"]["SystemCallFilter"])

    def test_historical_custody_evidence_is_explicitly_stale(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/agent-port-custody.v1.json").read_text(
                encoding="utf-8"
            )
        )
        evidence = json.loads(
            (ROOT / "docs/evidence/generated/d0c05-rust193-host-result.json").read_text(
                encoding="utf-8"
            )
        )
        docs = json.loads((ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8"))
        state = json.loads(
            (ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
        )
        historical_head = "7be7121b1d2593a0e708ec9ade189ef84ab245da"
        validation = contract["host_validation"]
        self.assertEqual(
            contract["status"], "HOST_VALIDATED_DEFAULT_DISABLED_NO_PRODUCT_LISTENER"
        )
        self.assertEqual(
            contract["evidence_lifecycle"], "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
        )
        self.assertEqual(
            validation["evidence_lifecycle"],
            "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN",
        )
        self.assertEqual(validation["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(validation["merge_ready"])
        self.assertIn(historical_head, validation["stale_reason"])
        self.assertEqual(
            evidence["evidence_lifecycle"], "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
        )
        self.assertEqual(evidence["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(evidence["merge_ready"])
        self.assertIn(historical_head, evidence["stale_reason"])
        self.assertFalse(docs["agent_port_systemd_custody_exact_head_rust_validation"])
        self.assertEqual(
            docs["agent_port_systemd_custody_host_evidence_freshness"],
            "STALE_EVIDENCE",
        )
        docs_row = next(
            row
            for row in docs["implementation_checkpoints"]
            if row["id"] == "TOS-D0C-05"
        )
        state_row = next(
            row
            for row in state["host_validated_work_packages"]
            if row["id"] == "D0C-05"
        )
        for row in (docs_row, state_row):
            self.assertEqual(row["evidence_freshness"], "STALE_EVIDENCE")
            self.assertFalse(row["merge_ready"])
            self.assertIn(historical_head, row["stale_reason"])


class D3DevelopmentProfilePathTests(unittest.TestCase):
    def setUp(self) -> None:
        D3_PROFILE.ERRORS.clear()

    def tearDown(self) -> None:
        D3_PROFILE.ERRORS.clear()

    def test_development_uses_only_its_dedicated_static_attestation(self) -> None:
        manifest = tomllib.loads(
            (ROOT / "apps/hepta-agent-portd/Cargo.toml").read_text(
                encoding="utf-8"
            )
        )
        features = manifest["features"]
        static_feature = "hepta-peer-attestation/qualification-static-attestation"
        development_static = (
            "hepta-peer-attestation/development-static-attestation"
        )
        self.assertNotIn(static_feature, features["development"])
        self.assertNotIn(static_feature, features["fixture"])
        self.assertIn(static_feature, features["d1-qualification"])
        self.assertIn(development_static, features["development"])
        self.assertNotIn(development_static, features["fixture"])
        self.assertNotIn(development_static, features["d1-qualification"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_require_text_rejects_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (real / "source.rs").write_text("trusted marker", encoding="utf-8")
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with mock.patch.object(D3_PROFILE, "ROOT", root):
                self.assertEqual(
                    D3_PROFILE.require_text(linked / "source.rs", "trusted"), ""
                )
            self.assertTrue(any("symlink" in error for error in D3_PROFILE.ERRORS))

    def test_require_text_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "outside.txt").write_text("forged", encoding="utf-8")
            with mock.patch.object(D3_PROFILE, "ROOT", root):
                self.assertEqual(
                    D3_PROFILE.require_text(
                        root / "nested" / ".." / "outside.txt", "forged"
                    ),
                    "",
                )
            self.assertTrue(any(".." in error for error in D3_PROFILE.ERRORS))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_manifest_and_contract_checks_reject_symlink_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_parent = root / "apps/hepta-agent-portd"
            cargo_parent.mkdir(parents=True)
            contract_parent = root / "contracts"
            contract_parent.mkdir()
            cargo_target = root / "cargo-outside.toml"
            cargo_target.write_text("[features]\n", encoding="utf-8")
            contract_target = root / "contract-outside.json"
            contract_target.write_text("{}", encoding="utf-8")
            (cargo_parent / "Cargo.toml").symlink_to(cargo_target)
            (contract_parent / "browser-actor.v1.json").symlink_to(contract_target)
            with mock.patch.object(D3_PROFILE, "ROOT", root):
                D3_PROFILE.check_manifest()
                D3_PROFILE.check_contract()
            symlink_errors = [
                error for error in D3_PROFILE.ERRORS if "symlink" in error
            ]
            self.assertEqual(len(symlink_errors), 2)
            self.assertTrue(
                any("apps/hepta-agent-portd/Cargo.toml" in error for error in symlink_errors)
            )
            self.assertTrue(
                any("contracts/browser-actor.v1.json" in error for error in symlink_errors)
            )


if __name__ == "__main__":
    unittest.main()
