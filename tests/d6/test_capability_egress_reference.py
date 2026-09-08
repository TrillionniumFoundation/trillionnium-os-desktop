from __future__ import annotations

import base64
import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from capability_egress_reference import (  # noqa: E402
    DecisionLedger,
    PolicyError,
    authorize,
    build_fixture_permit,
    fixture_network_request,
    fixture_network_resource,
    fixture_subject,
    fixture_trust,
    permit_payload,
)
from trusted_app_bundle import ed25519_public_from_seed, ed25519_sign_fixture  # noqa: E402

SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)


class CapabilityEgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import json

        cls.contract = json.loads(
            (ROOT / "contracts/capability-egress.v1.json").read_text()
        )
        cls.subject = fixture_subject()
        cls.public = ed25519_public_from_seed(SEED)
        cls.trust = fixture_trust(cls.public)

    def network_permit(
        self,
        *,
        actions: list[str] | None = None,
        maximum_uses: int = 1,
        constraints: dict | None = None,
        permit_id: str = "permit-network",
    ) -> dict:
        permit, _ = build_fixture_permit(
            seed=SEED,
            subject=self.subject,
            audience="portal:network",
            resource=fixture_network_resource(),
            actions=actions or ["http_request"],
            permit_id=permit_id,
            nonce=f"nonce-{permit_id}",
            maximum_uses=maximum_uses,
            constraints=constraints,
        )
        return permit

    def file_permit(
        self,
        *,
        permit_id: str = "permit-file",
        maximum_uses: int = 1,
    ) -> dict:
        permit, _ = build_fixture_permit(
            seed=SEED,
            subject=self.subject,
            audience="portal:file",
            resource={
                "kind": "opaque_file_handle",
                "handle_id": "file-handle-1",
                "maximum_bytes": 4096,
            },
            actions=["read", "write", "create"],
            permit_id=permit_id,
            nonce=f"nonce-{permit_id}",
            maximum_uses=maximum_uses,
        )
        return permit

    def resign(self, permit: dict) -> None:
        permit["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(SEED, permit_payload(permit))
        ).decode()

    def decision(
        self,
        permits: list[dict] | None = None,
        request: dict | None = None,
        *,
        subject: dict | None = None,
        trust: dict | None = None,
        ledger: DecisionLedger | None = None,
        now_epoch: int = 100,
    ) -> dict:
        return authorize(
            permits or [self.network_permit()],
            request or fixture_network_request(),
            trust or self.trust,
            subject or self.subject,
            self.contract,
            ledger or DecisionLedger(),
            now_epoch=now_epoch,
        )

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(PolicyError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_valid_https_via_controlled_resolver_and_proxy(self) -> None:
        receipt = self.decision()
        self.assertEqual(receipt["decision"], "ADMIT")
        self.assertEqual(receipt["details"]["origin"], "https://example.com:443")
        self.assertEqual(receipt["details"]["proxy_id"], "proxy-fixture")
        self.assertFalse(receipt["details"]["network_access_executed"])

    def test_valid_wss_via_controlled_resolver_and_proxy(self) -> None:
        permit = self.network_permit(actions=["websocket_connect"])
        request = fixture_network_request()
        request.update(
            {
                "action": "websocket_connect",
                "url": "wss://socket.example.com/chat",
                "context": "websocket",
            }
        )
        request["dns"]["query_name"] = "socket.example.com"
        request["transport"]["protocol"] = "websocket"
        request["transport"]["certificate_host"] = "socket.example.com"
        receipt = self.decision([permit], request)
        self.assertEqual(receipt["details"]["action"], "websocket_connect")

    def test_signature_and_unknown_field_tamper_rejected(self) -> None:
        permit = self.network_permit()
        raw = bytearray(base64.b64decode(permit["signature"]["value_base64"]))
        raw[0] ^= 1
        permit["signature"]["value_base64"] = base64.b64encode(raw).decode()
        self.assert_rejected(
            "PERMIT_SIGNATURE_REJECTED", lambda: self.decision([permit])
        )
        extra = self.network_permit()
        extra["ambient"] = True
        self.assert_rejected(
            "PERMIT_FIELD_SET_MISMATCH", lambda: self.decision([extra])
        )

    def test_audience_subject_resource_and_action_binding(self) -> None:
        wrong_audience = self.network_permit()
        wrong_audience["audience"] = "portal:file"
        self.resign(wrong_audience)
        self.assert_rejected(
            "AUDIENCE_MISMATCH", lambda: self.decision([wrong_audience])
        )
        wrong_subject = copy.deepcopy(self.subject)
        wrong_subject["session_id"] = "other-session"
        self.assert_rejected(
            "SUBJECT_MISMATCH",
            lambda: self.decision(subject=wrong_subject),
        )
        request = fixture_network_request()
        request["url"] = "https://other.example/resource"
        request["dns"]["query_name"] = "other.example"
        request["transport"]["certificate_host"] = "other.example"
        self.assert_rejected(
            "NETWORK_ORIGIN_NOT_AUTHORIZED", lambda: self.decision(request=request)
        )
        permit = self.network_permit(actions=["websocket_connect"])
        self.assert_rejected(
            "ACTION_NOT_AUTHORIZED", lambda: self.decision([permit])
        )

    def test_time_lifetime_revocation_and_replay(self) -> None:
        expired = self.network_permit()
        expired["expires_at_epoch"] = 99
        self.resign(expired)
        self.assert_rejected(
            "PERMIT_EXPIRED", lambda: self.decision([expired], now_epoch=100)
        )
        future = self.network_permit()
        future["not_before_epoch"] = 101
        self.resign(future)
        self.assert_rejected(
            "PERMIT_NOT_YET_VALID", lambda: self.decision([future], now_epoch=100)
        )
        long_lived = self.network_permit()
        long_lived["expires_at_epoch"] = 4000
        self.resign(long_lived)
        self.assert_rejected(
            "PERMIT_LIFETIME_TOO_LONG", lambda: self.decision([long_lived])
        )
        revoked_trust = copy.deepcopy(self.trust)
        revoked_trust["issuers"]["fixture-issuer"]["keys"]["fixture-key-1"]["status"] = "revoked"
        self.assert_rejected(
            "ISSUER_KEY_NOT_ACTIVE", lambda: self.decision(trust=revoked_trust)
        )
        revoked_permit_trust = copy.deepcopy(self.trust)
        revoked_permit_trust["revoked_permit_ids"] = ["permit-network"]
        self.assert_rejected(
            "PERMIT_REVOKED", lambda: self.decision(trust=revoked_permit_trust)
        )
        ledger = DecisionLedger()
        permit = self.network_permit(maximum_uses=1)
        self.decision([permit], ledger=ledger)
        self.assert_rejected(
            "PERMIT_REPLAY_LIMIT_REACHED",
            lambda: self.decision([permit], ledger=ledger),
        )

    def test_file_portal_rejects_raw_paths_and_enforces_bytes(self) -> None:
        permit = self.file_permit()
        valid = {
            "kind": "file",
            "action": "write",
            "handle_id": "file-handle-1",
            "bytes": 100,
        }
        receipt = self.decision([permit], valid)
        self.assertEqual(receipt["details"]["handle_id"], "file-handle-1")
        raw_path = dict(valid)
        raw_path["path"] = "/etc/passwd"
        self.assert_rejected(
            "FILE_REQUEST_FIELD_SET_MISMATCH",
            lambda: self.decision([self.file_permit()], raw_path),
        )
        too_large = dict(valid)
        too_large["bytes"] = 4097
        self.assert_rejected(
            "FILE_BYTE_LIMIT_EXCEEDED",
            lambda: self.decision([self.file_permit()], too_large),
        )

    def test_notification_and_audio_are_resource_scoped(self) -> None:
        notification, _ = build_fixture_permit(
            seed=SEED,
            subject=self.subject,
            audience="portal:notification",
            resource={
                "kind": "notification_channel",
                "channel_id": "channel-1",
                "maximum_text_bytes": 128,
            },
            actions=["show"],
            permit_id="permit-notification",
            nonce="nonce-notification",
        )
        notice = {
            "kind": "notification",
            "action": "show",
            "channel_id": "channel-1",
            "title": "Ready",
            "body": "Bound notification",
        }
        self.assertEqual(
            self.decision([notification], notice)["details"]["portal"],
            "notification",
        )
        audio, _ = build_fixture_permit(
            seed=SEED,
            subject=self.subject,
            audience="portal:audio",
            resource={
                "kind": "audio_stream",
                "stream_id": "stream-1",
                "maximum_duration_ms": 1000,
                "maximum_gain_millibel": 0,
            },
            actions=["play"],
            permit_id="permit-audio",
            nonce="nonce-audio",
        )
        request = {
            "kind": "audio",
            "action": "play",
            "stream_id": "stream-1",
            "duration_ms": 100,
            "gain_millibel": -100,
        }
        self.assertEqual(
            self.decision([audio], request)["details"]["portal"], "audio"
        )
        request["gain_millibel"] = 1
        self.assert_rejected(
            "AUDIO_GAIN_LIMIT_EXCEEDED",
            lambda: self.decision([audio], request),
        )

    def test_userinfo_plaintext_external_and_noncanonical_hosts_rejected(self) -> None:
        for url, reason in [
            ("https://user@example.com/", "URL_USERINFO_FORBIDDEN"),
            ("http://example.com/", "SCHEME_NOT_AUTHORIZED"),
            ("file:///etc/passwd", "SCHEME_NOT_AUTHORIZED"),
            ("https://example.com./", "NON_CANONICAL_HOST"),
            ("https://localhost/", "LOCALHOST_NAME_FORBIDDEN"),
        ]:
            request = fixture_network_request()
            request["url"] = url
            self.assert_rejected(
                reason, lambda request=request: self.decision(request=request)
            )

    def test_private_loopback_linklocal_metadata_and_other_non_global_ips_rejected(self) -> None:
        cases = [
            ("10.0.0.1", "PRIVATE_IP_FORBIDDEN"),
            ("127.0.0.1", "LOOPBACK_IP_FORBIDDEN"),
            ("169.254.1.2", "LINK_LOCAL_IP_FORBIDDEN"),
            ("169.254.169.254", "METADATA_IP_FORBIDDEN"),
            ("100.100.100.200", "METADATA_IP_FORBIDDEN"),
            ("0.0.0.0", "UNSPECIFIED_IP_FORBIDDEN"),
            ("224.0.0.1", "MULTICAST_IP_FORBIDDEN"),
            ("240.0.0.1", "RESERVED_IP_FORBIDDEN"),
            ("fc00::1", "PRIVATE_IP_FORBIDDEN"),
            ("::1", "LOOPBACK_IP_FORBIDDEN"),
        ]
        for address, reason in cases:
            request = fixture_network_request()
            request["dns"]["addresses"] = [address]
            request["connection"]["peer_ip"] = address
            self.assert_rejected(
                reason,
                lambda request=request: self.decision(request=request),
            )

    def test_ipv4_mapped_six_to_four_and_teredo_rejected(self) -> None:
        cases = [
            ("::ffff:7f00:1", "IPV4_MAPPED_IPV6_FORBIDDEN"),
            ("2002:7f00:1::", "SIX_TO_FOUR_FORBIDDEN"),
            ("2001:0:4136:e378:8000:63bf:3fff:fdd2", "TEREDO_FORBIDDEN"),
        ]
        for address, reason in cases:
            request = fixture_network_request()
            request["dns"]["addresses"] = [address]
            request["connection"]["peer_ip"] = address
            self.assert_rejected(
                reason,
                lambda request=request: self.decision(request=request),
            )

    def test_dns_bounds_resolver_name_ttl_and_cname_loop(self) -> None:
        request = fixture_network_request()
        request["dns"]["addresses"] = [f"8.8.8.{index}" for index in range(1, 18)]
        self.assert_rejected(
            "DNS_ADDRESS_COUNT_INVALID", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["resolver_id"] = "other-resolver"
        self.assert_rejected(
            "RESOLVER_ID_MISMATCH", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["query_name"] = "other.example"
        self.assert_rejected(
            "DNS_QUERY_NAME_MISMATCH", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["ttl_seconds"] = 301
        self.assert_rejected(
            "DNS_TTL_BOUND_VIOLATION", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["observed_at_epoch"] = 0
        self.assert_rejected(
            "DNS_EVIDENCE_EXPIRED_OR_FUTURE", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["cname_chain"] = [f"c{index}.example.com" for index in range(9)]
        self.assert_rejected(
            "CNAME_DEPTH_EXCEEDED", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["dns"]["cname_chain"] = ["a.example.com", "a.example.com"]
        self.assert_rejected(
            "CNAME_LOOP_REJECTED", lambda: self.decision(request=request)
        )

    def test_connected_peer_rebinding_and_proxy_bypass_rejected(self) -> None:
        request = fixture_network_request()
        request["connection"]["peer_ip"] = "8.8.8.8"
        self.assert_rejected(
            "CONNECTED_PEER_NOT_IN_APPROVED_DNS_SET",
            lambda: self.decision(request=request),
        )
        request = fixture_network_request()
        request["transport"]["direct"] = True
        self.assert_rejected(
            "PROXY_BYPASS_REJECTED", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["transport"]["proxy_id"] = "other-proxy"
        self.assert_rejected(
            "EGRESS_PROXY_MISMATCH", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["connection"]["proxy_id"] = "other-proxy"
        self.assert_rejected(
            "CONNECTION_PROXY_ID_MISMATCH", lambda: self.decision(request=request)
        )

    def test_redirect_reauthorization_budget_and_captive_portal(self) -> None:
        request = fixture_network_request()
        request["response_observation"]["redirect_location"] = "https://other.example/login"
        self.assert_rejected(
            "REDIRECT_DESTINATION_REAUTHORIZATION_REQUIRED",
            lambda: self.decision(request=request),
        )
        request = fixture_network_request()
        request["redirect_count"] = 3
        request["previous_url"] = "https://example.com/previous"
        self.assert_rejected(
            "REDIRECT_BUDGET_EXCEEDED", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["response_observation"]["captive_portal"] = True
        self.assert_rejected(
            "CAPTIVE_PORTAL_REJECTED", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["transport"]["tls_intercepted"] = True
        self.assert_rejected(
            "TLS_INTERCEPTION_REJECTED", lambda: self.decision(request=request)
        )
        request = fixture_network_request()
        request["transport"]["tls_verified"] = False
        self.assert_rejected(
            "TLS_VERIFICATION_REQUIRED", lambda: self.decision(request=request)
        )

    def test_contexts_are_explicit_and_quic_webtransport_are_rejected(self) -> None:
        permit = self.network_permit()
        permit["resource"]["contexts"] = ["top_level"]
        self.resign(permit)
        for context in ["iframe", "worker", "service_worker", "prefetch"]:
            request = fixture_network_request()
            request["context"] = context
            self.assert_rejected(
                "REQUEST_CONTEXT_NOT_AUTHORIZED",
                lambda request=request: self.decision([permit], request),
            )
        for protocol in ["quic", "webtransport"]:
            request = fixture_network_request()
            request["transport"]["protocol"] = protocol
            self.assert_rejected(
                "UNSUPPORTED_TRANSPORT_PROTOCOL",
                lambda request=request: self.decision(request=request),
            )

    def test_download_requires_network_and_file_permit(self) -> None:
        file_request = {
            "kind": "file",
            "action": "write",
            "handle_id": "file-handle-1",
            "bytes": 2048,
        }
        network = self.network_permit(
            actions=["download"],
            constraints={"download_target": file_request},
            permit_id="permit-download-network",
        )
        request = fixture_network_request()
        request["action"] = "download"
        request["context"] = "download"
        self.assert_rejected(
            "DOWNLOAD_REQUIRES_FILE_PERMIT",
            lambda: self.decision([network], request),
        )
        receipt = self.decision([network, self.file_permit()], request)
        self.assertEqual(receipt["details"]["file_handle_id"], "file-handle-1")
        self.assertEqual(len(receipt["permit_ids"]), 2)

    def test_decision_receipt_tamper_is_rejected(self) -> None:
        ledger = DecisionLedger()
        self.decision(ledger=ledger)
        DecisionLedger.verify_receipts(ledger.receipts)
        tampered = copy.deepcopy(ledger.receipts)
        tampered[0]["details"]["connected_peer_ip"] = "8.8.8.8"
        self.assert_rejected(
            "DECISION_RECEIPT_HASH_MISMATCH",
            lambda: DecisionLedger.verify_receipts(tampered),
        )


if __name__ == "__main__":
    unittest.main()
