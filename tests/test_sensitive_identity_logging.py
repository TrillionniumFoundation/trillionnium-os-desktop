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


if __name__ == "__main__":
    unittest.main()
