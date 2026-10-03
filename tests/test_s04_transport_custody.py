from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            "Frame",
        ):
            with self.subTest(token=token):
                mutated = root + f"\npub use facade::{token};\n"
                errors = VALIDATOR.validate_transport_sources(
                    mutated, facade, agent, manifest, contract
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_SURFACE_FINDING}:{token}",
                    errors,
                )

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
            self.assertTrue(
                any(error.startswith(VALIDATOR.PUBLIC_API_FINDING + ":") for error in errors),
                errors,
            )

    def test_every_public_api_field_is_type_and_value_bound(self) -> None:
        root, facade, agent, manifest, contract = sources()
        expected = VALIDATOR.EXPECTED_TRANSPORT_PUBLIC_API
        self.assertEqual(contract["public_api"], expected)
        for key, value in expected.items():
            with self.subTest(key=key, mutation="missing"):
                candidate = copy.deepcopy(contract)
                del candidate["public_api"][key]
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:missing:{key}",
                    errors,
                )
            with self.subTest(key=key, mutation="type"):
                candidate = copy.deepcopy(contract)
                candidate["public_api"][key] = 1 if isinstance(value, bool) else False
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertTrue(
                    any(
                        error.startswith(
                            f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:type:{key}:"
                        )
                        for error in errors
                    ),
                    errors,
                )
            with self.subTest(key=key, mutation="value"):
                candidate = copy.deepcopy(contract)
                if isinstance(value, bool):
                    candidate["public_api"][key] = not value
                else:
                    candidate["public_api"][key] = value + "-mutated"
                errors = VALIDATOR.validate_transport_sources(
                    root, facade, agent, manifest, candidate
                )
                self.assertIn(
                    f"{VALIDATOR.PUBLIC_API_FINDING}:agent-transport.public_api:value:{key}",
                    errors,
                )


class S04InputDiagnosticTests(unittest.TestCase):
    CANARY = "CONTROLLED-S04-CREDENTIAL-CANARY-DO-NOT-REPEAT"

    def diagnostic(self):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            result = VALIDATOR.main()
        self.assertEqual(result, 1)
        self.assertNotIn(self.CANARY, stream.getvalue())
        self.assertIn("S04 validation failed", stream.getvalue())
        return stream.getvalue()

    def test_actual_malformed_unit_bytes_fail_without_cli_disclosure(self):
        relative = "packaging/debian/systemd/hepta-browserd-agent.socket"
        original_read = VALIDATOR._read
        with tempfile.TemporaryDirectory(prefix=".s04-diagnostic-", dir=ROOT) as temporary:
            unit = Path(temporary) / "unit"
            unit.write_text("[Unit]\n" + self.CANARY + "\n")
            def read(name):
                if name == relative:
                    return VALIDATOR.read_text_nofollow(unit, label=relative)
                return original_read(name)
            with patch.object(VALIDATOR, "_read", read):
                with self.assertRaises(ValueError) as raised:
                    VALIDATOR._parse_assignments(relative)
                self.assertIn(relative + " at line 2", str(raised.exception))
                self.assertNotIn(self.CANARY, str(raised.exception))
                self.assertIn("source custody, decoding or parsing failed", self.diagnostic())

    def test_actual_missing_file_exception_does_not_echo_input_path(self):
        with tempfile.TemporaryDirectory(prefix="s04-diagnostic-") as temporary:
            path = Path(temporary) / self.CANARY
            def missing():
                return path.read_bytes()
            with patch.object(VALIDATOR, "validate_root", missing):
                self.diagnostic()

    def test_unknown_public_api_key_remains_refused_without_echo(self):
        errors = []
        VALIDATOR._require_exact_typed_object(
            {**VALIDATOR.EXPECTED_TRANSPORT_PUBLIC_API, self.CANARY: "unknown", self.CANARY + "2": "unknown"},
            VALIDATOR.EXPECTED_TRANSPORT_PUBLIC_API, "transport", errors,
        )
        self.assertEqual(errors, [VALIDATOR.PUBLIC_API_FINDING + ":transport:unexpected-field"])
        with patch.object(VALIDATOR, "validate_root", return_value=errors):
            self.assertIn("unexpected-field", self.diagnostic())

    def test_actual_reference_json_hash_value_is_refused_without_echo(self):
        relative = "docs/evidence/generated/d0c02-agent-transport-reference-result.json"
        original_json = VALIDATOR._json
        reference = original_json(relative)
        reference["contract_sha256"] = self.CANARY + "\n\u5bc6\u94a5"
        with tempfile.TemporaryDirectory(prefix=".s04-diagnostic-", dir=ROOT) as temporary:
            path = Path(temporary) / "reference.json"
            path.write_text(json.dumps(reference))
            def load(name):
                if name == relative:
                    return VALIDATOR.load_json_nofollow(path, label=relative)
                return original_json(name)
            with patch.object(VALIDATOR, "_json", load):
                self.assertEqual(VALIDATOR.validate_reference_binding(), [
                    "transport reference result contract_sha256 does not match the current contract"])
                self.assertIn("contract_sha256", self.diagnostic())


if __name__ == "__main__":
    unittest.main()
