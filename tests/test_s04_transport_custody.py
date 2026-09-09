from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_s04_transport_custody_under_test",
    ROOT / "tools/validate_s04_transport_custody.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def sources() -> tuple[str, str, str, dict[str, object], dict[str, object]]:
    return (
        VALIDATOR._read("crates/hepta-agent-transport/src/lib.rs"),
        VALIDATOR._read("crates/hepta-agent-transport/src/facade.rs"),
        VALIDATOR._read("crates/hepta-agent-port/src/lib.rs"),
        VALIDATOR._toml("crates/hepta-agent-transport/Cargo.toml"),
        VALIDATOR._json("contracts/agent-transport.v1.json"),
    )


class S04TransportCustodyTest(unittest.TestCase):
    def test_source_policy_validator_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/validate_s04_transport_custody.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_request_custody_remains_mechanism_only(self) -> None:
        contract = VALIDATOR._json("contracts/request-peer-custody.v1.json")
        self.assertFalse(contract["browser_actor_integrated"])
        self.assertFalse(contract["production_listener_enabled"])
        self.assertFalse(contract["external_effect_authority"])
        self.assertEqual(contract["custody_owners"], 1)
        self.assertTrue(contract["failure_latches_revocation"])

    def test_changed_mechanisms_do_not_inherit_historical_host_pass(self) -> None:
        for name in (
            "agent-transport.v1.json",
            "agent-port-bridge.v1.json",
            "agent-port-custody.v1.json",
        ):
            with self.subTest(name=name):
                contract = VALIDATOR._json(f"contracts/{name}")
                self.assertEqual(contract["evidence_freshness"], "STALE_EVIDENCE")
                self.assertFalse(contract["merge_ready"])

    def test_transport_reference_binds_exact_contract_bytes(self) -> None:
        self.assertEqual(VALIDATOR.validate_reference_binding(), [])


class PublicApiMutationTest(unittest.TestCase):
    def test_current_public_surface_passes(self) -> None:
        self.assertEqual(VALIDATOR.validate_transport_sources(*sources()), [])

    def test_comment_decoys_do_not_hide_public_nonce_injection(self) -> None:
        root, facade, agent, manifest, contract = sources()
        facade += "\npub fn accept_with_nonce_source() {}\n"
        facade += "// production path has no accept_with_nonce_source\n"
        errors = VALIDATOR.validate_transport_sources(
            root, facade, agent, manifest, contract
        )
        self.assertTrue(any("accept_with_nonce_source" in error for error in errors), errors)

    def test_fixed_nonce_and_raw_frame_exports_are_rejected(self) -> None:
        root, facade, agent, manifest, contract = sources()
        for token in (
            "FixedNonceSource",
            "NonceSource",
            "SessionNonce",
            "FrameKind",
            "pub struct Frame",
        ):
            with self.subTest(token=token):
                mutated = root + f"\npub use facade::{token};\n"
                errors = VALIDATOR.validate_transport_sources(
                    mutated, facade, agent, manifest, contract
                )
                self.assertTrue(any(token in error for error in errors), errors)

    def test_missing_custom_redaction_impl_is_rejected(self) -> None:
        root, facade, agent, manifest, contract = sources()
        mutated = facade.replace(
            "impl fmt::Debug for PeerIdentity",
            "impl fmt::Display for PeerIdentity",
            1,
        )
        mutated += "\n// impl fmt::Debug for PeerIdentity {}\n"
        errors = VALIDATOR.validate_transport_sources(
            root, mutated, agent, manifest, contract
        )
        self.assertTrue(any("PeerIdentity" in error for error in errors), errors)

    def test_handler_text_redaction_cannot_be_replaced_by_comment(self) -> None:
        root, facade, agent, manifest, contract = sources()
        mutated = agent.replace(
            "Self::Handler(_) => formatter.write_str(\"AgentPort handler failed\"),",
            "Self::Handler(message) => write!(formatter, \"{message}\"),",
        )
        mutated += "\n// Self::Handler(_) => formatter.write_str(\"AgentPort handler failed\")\n"
        errors = VALIDATOR.validate_transport_sources(
            root, facade, mutated, manifest, contract
        )
        self.assertTrue(any("handler error formatting" in error for error in errors), errors)

    def test_public_api_contract_is_exact_and_type_strict(self) -> None:
        root, facade, agent, manifest, contract = sources()
        mutations = []

        missing = copy.deepcopy(contract)
        del missing["public_api"]["deterministic_nonce_source_exposed"]
        mutations.append(missing)

        extra = copy.deepcopy(contract)
        extra["public_api"]["unexpected"] = False
        mutations.append(extra)

        wrong_type = copy.deepcopy(contract)
        wrong_type["public_api"]["connected_stream_only"] = 1
        mutations.append(wrong_type)

        widened = copy.deepcopy(contract)
        widened["public_api"]["deterministic_nonce_source_exposed"] = True
        mutations.append(widened)

        for candidate in mutations:
            errors = VALIDATOR.validate_transport_sources(
                root, facade, agent, manifest, candidate
            )
            self.assertTrue(any("public_api" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
