from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE_SOURCES = (
    "apps/hepta-agent-portd/src/main.rs",
    "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
    "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs",
    "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs",
    "crates/hepta-d3-development/src/sessiond/service.rs",
)
EXPECTED_V2_SCHEMAS = (
    "trillionnium.desktop.d1-agent-fixture-self-check.v2",
    "trillionnium.desktop.d1-agent-server-result.v2",
    "trillionnium.desktop.agent-port-development-result.v2",
    "trillionnium.desktop.agent-portd-result.v2",
    "trillionnium.desktop.agent-portd-self-check.v2",
    "trillionnium.desktop.d3-sessiond-request.v2",
)


class SensitiveIdentityLoggingTests(unittest.TestCase):
    def test_public_evidence_never_serializes_raw_peer_credentials(self) -> None:
        combined = ""
        for relative in PUBLIC_EVIDENCE_SOURCES:
            source = (ROOT / relative).read_text(encoding="utf-8")
            combined += source
            self.assertNotIn('\\"peer_pid\\":{}', source, relative)
            self.assertNotIn('\\"peer_uid\\":{}', source, relative)
            self.assertNotIn('\\"peer_gid\\":{}', source, relative)
            self.assertIn('\\"peer_credentials_verified\\":true', source, relative)
            self.assertIn('\\"peer_identity_redacted\\":true', source, relative)
        for schema in EXPECTED_V2_SCHEMAS:
            self.assertIn(schema, combined)

    def test_public_renderers_accept_only_identity_free_values(self) -> None:
        product = (ROOT / "apps/hepta-agent-portd/src/main.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("fn self_check() -> Result<(), ServiceError>", product)
        self.assertIn("fn self_check_report() -> String", product)
        self.assertIn('println!("{}", self_check_report())', product)
        self.assertNotIn('println!("{report}")', product)

        for relative, renderer in (
            (
                "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
                "server_evidence_json",
            ),
            (
                "crates/hepta-d3-development/src/sessiond/service.rs",
                "evidence_json",
            ),
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("struct PublicServiceEvidence", source, relative)
            self.assertIn(
                f"fn {renderer}(evidence: &PublicServiceEvidence)", source, relative
            )
            self.assertNotIn(
                f"fn {renderer}(evidence: &ServiceEvidence)", source, relative
            )

    def test_service_evidence_cannot_retain_peer_identity(self) -> None:
        source = (ROOT / "crates/hepta-agent-port/src/lib.rs").read_text(
            encoding="utf-8"
        )
        dispatch = source.split("pub struct DispatchContext {", 1)[1].split("}", 1)[0]
        evidence = source.split("pub struct ServiceEvidence {", 1)[1].split("}", 1)[0]
        constructor = source.split("Ok(ServiceEvidence {", 1)[1].split("})", 1)[0]
        self.assertIn("pub peer: PeerIdentity", dispatch)
        self.assertNotIn("peer", evidence)
        self.assertNotRegex(constructor, r"(?m)^\s*peer,\s*$")

    def test_sensitive_actor_assertions_do_not_render_identity_values(self) -> None:
        incarnation = (
            ROOT / "crates/hepta-browser-actor/src/incarnation_tests.rs"
        ).read_text(encoding="utf-8")
        actor = (ROOT / "crates/hepta-browser-actor/src/lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("{outcome:?}", incarnation)
        self.assertNotIn("create failed: {outcome:?}", actor)
        self.assertNotIn("missing session id: {other:?}", actor)
        self.assertNotIn("missing session generation: {other:?}", actor)
        self.assertIn('panic!("create failed")', actor)
        self.assertIn('"stale actor incarnation was admitted"', incarnation)

    def test_identity_derived_failures_have_no_public_log_sink(self) -> None:
        forbidden = {
            "apps/hepta-agent-portd/src/main.rs": (
                "hepta-agent-portd: {error}",
                'eprintln!("hepta-agent-portd:',
            ),
            "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs": (
                "hepta-agent-d1-fixture: request validation failed",
                "hepta-agent-d1-fixture: failed to write result:",
            ),
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs": (
                "hepta-agent-port-developmentd: request validation failed",
            ),
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs": (
                "hepta-agent-port-qualificationd: request validation failed",
            ),
            "crates/hepta-d3-development/src/bin/sessiond.rs": (
                "hepta-agent-port-development-sessiond: request validation failed",
            ),
            "crates/hepta-d3-development/src/sessiond/service.rs": (
                "d3 connection rejected:",
            ),
        }
        for relative, needles in forbidden.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            for needle in needles:
                self.assertNotIn(needle, source, relative)

    def test_attestation_wrappers_cannot_retain_identity_values(self) -> None:
        wrappers = (
            "apps/hepta-agent-portd/src/main.rs",
            "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs",
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs",
        )
        for relative in wrappers:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("Attestation,", source, relative)
            self.assertIn(
                'formatter.write_str("peer attestation failed")', source, relative
            )
            self.assertIn("fn from(_: AttestationError) -> Self", source, relative)
            self.assertNotIn("Attestation(AttestationError)", source, relative)
            self.assertNotIn("Self::Attestation(error)", source, relative)

    def test_cryptographic_fixture_nonces_have_no_literal_helper_input(self) -> None:
        source = (ROOT / "apps/hepta-browserd/src/product_policy.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("fn nonproduction_nonce() -> String", source)
        self.assertIn("let nonce = nonproduction_nonce();", source)
        self.assertIn("nonce: &nonce", source)
        self.assertNotIn("_scenario: &str", source)
        self.assertNotIn("payload_sha256: &str,\n        nonce: &str,", source)
        self.assertNotRegex(source, r'nonce:\s*"[^"\n]+"\.to_owned\(\),')


if __name__ == "__main__":
    unittest.main()
