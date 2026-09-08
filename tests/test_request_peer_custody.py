from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RequestPeerCustodyTests(unittest.TestCase):
    def test_contract_is_bounded_and_non_transferable(self) -> None:
        contract = json.loads((ROOT / "contracts/request-peer-custody.v1.json").read_text())
        self.assertEqual(contract["scope"], "in_process_request_identity_continuity_only")
        self.assertEqual(contract["custody_owners"], 1)
        self.assertEqual(contract["pidfd_duplicates_per_request"], 1)
        self.assertTrue(contract["custody_drop_revokes"])
        self.assertTrue(contract["failure_latches_revocation"])
        self.assertFalse(contract["production_listener_enabled"])
        self.assertFalse(contract["external_effect_authority"])
        self.assertFalse(contract["promotion_authoritative"])
        self.assertFalse(contract["request_ids_can_extend_custody"])

    def test_peer_lease_is_bound_to_kernel_identity_and_liveness(self) -> None:
        source = (ROOT / "crates/hepta-peer-attestation/src/request_lease.rs").read_text()
        for marker in (
            "PeerIdentity",
            "AttestedPeer",
            "ensure_alive",
            "same",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("TcpListener", source)
        self.assertNotIn("UnixListener", source)

    def test_transport_facade_accepts_no_path_or_listener_authority(self) -> None:
        source = (ROOT / "crates/hepta-agent-transport/src/facade.rs").read_text()
        self.assertNotIn("TcpListener", source)
        self.assertNotIn("UnixListener", source)
        self.assertIn("UnixStream", source)


if __name__ == "__main__":
    unittest.main()
