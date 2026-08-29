from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D2IContractTests(unittest.TestCase):
    def test_contract_keeps_candidate_and_promotion_claims_separate(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertEqual(
            contract["status"],
            "IMPLEMENTED_CANDIDATE_REQUIRES_MACHINE_EVIDENCE",
        )
        self.assertTrue(contract["image"]["byte_for_byte_equality_required"])
        self.assertEqual(contract["boot"]["network"], "none")
        self.assertTrue(contract["boot"]["product_agent_port_default_disabled"])
        ceiling = contract["claim_ceiling"]
        self.assertFalse(ceiling["actual_content_process_crash_currently_proven"])
        self.assertFalse(ceiling["release_readiness"])
        self.assertIn(
            "actual_content_process_crash_callback_observed",
            contract["promotion_requires"],
        )
        self.assertIn("exact_main_rerun_after_merge", contract["promotion_requires"])

    def test_guest_runtime_is_networkless_and_unprivileged(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        self.assertIn("User=hepta-desktop", service)
        self.assertIn("PrivateNetwork=yes", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertIn("WAYLAND_DISPLAY=wayland-0", service)
        self.assertIn("HEPTA_D0A02_OUTPUT=/var/lib/trillionnium-d2i", service)

    def test_host_gate_binds_same_image_and_no_network_qemu(self) -> None:
        prepare = (ROOT / "tests/qemu/prepare-d2i-image.sh").read_text()
        boot = (ROOT / "tests/qemu/run-d2i-boot-test.sh").read_text()
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertIn("PASS_DETERMINISTIC_INPUT_INJECTION", prepare)
        self.assertIn("E2FSPROGS_FAKE_TIME", prepare)
        self.assertIn("-nic none", boot)
        self.assertIn("trillionnium-d2i-acceptance.target", boot)
        self.assertIn("cmp -s", workflow)
        self.assertIn("run-d1-pipeline.sh", workflow)
        self.assertIn("run-d2i-boot-test.sh", workflow)
        self.assertIn("actual_content_process_crash_proven", workflow)


if __name__ == "__main__":
    unittest.main()
