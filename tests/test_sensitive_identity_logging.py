from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE_SOURCES = (
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

    def test_sensitive_actor_assertions_do_not_render_identity_values(self) -> None:
        source = (
            ROOT / "crates/hepta-browser-actor/src/incarnation_tests.rs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("{outcome:?}", source)
        self.assertNotIn("assert_ne!(\n        old.session_id", source)
        self.assertNotIn("assert_ne!(ids.borrow()[0], ids.borrow()[1])", source)
        self.assertIn('"stale actor incarnation was admitted"', source)


    def test_public_error_paths_do_not_render_attestation_identity(self) -> None:
        error_wrappers = (
            "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs",
            "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs",
        )
        for relative in error_wrappers:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(
                'Self::Attestation => formatter.write_str("peer attestation failed")',
                source,
                relative,
            )
            self.assertNotIn(
                'peer attestation failed: {error}',
                source,
                relative,
            )

        connection_source = (
            ROOT / "crates/hepta-d3-development/src/sessiond/service.rs"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'Err(_) => eprintln!("d3 connection rejected: request validation failed")',
            connection_source,
        )
        self.assertNotIn("d3 connection rejected: {error}", connection_source)

        process_source = (
            ROOT / "crates/hepta-d3-development/src/bin/sessiond.rs"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'eprintln!("hepta-agent-port-development-sessiond: request validation failed")',
            process_source,
        )
        self.assertNotIn(
            "hepta-agent-port-development-sessiond: {error}",
            process_source,
        )


    def test_process_error_boundaries_emit_only_constant_diagnostics(self) -> None:
        expectations = (
            (
                "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs",
                'eprintln!("hepta-agent-d1-fixture: request validation failed")',
                'hepta-agent-d1-fixture: {error}',
            ),
            (
                "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs",
                'eprintln!("hepta-agent-port-developmentd: request validation failed")',
                'hepta-agent-port-developmentd: {error}',
            ),
            (
                "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs",
                'eprintln!("hepta-agent-port-qualificationd: request validation failed")',
                'hepta-agent-port-qualificationd: {error}',
            ),
        )
        for relative, constant_sink, tainted_sink in expectations:
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(constant_sink, source, relative)
            self.assertNotIn(tainted_sink, source, relative)
            self.assertIn("Attestation,", source, relative)
            self.assertIn("Self::Attestation => None", source, relative)
            self.assertIn("fn from(_: AttestationError) -> Self", source, relative)
            self.assertNotIn("Attestation(AttestationError)", source, relative)
            self.assertNotIn("Self::Attestation(error)", source, relative)


if __name__ == "__main__":
    unittest.main()
