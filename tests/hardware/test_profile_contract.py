"""Machine-readable A09 lab gates; planning/contract tests, NOT hardware tests."""
import json
from pathlib import Path
import sys
import unittest

import cuda_gemm

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
from pci_identity import canonical_bdf, matches_target_model


class LabProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.profile = json.loads(
            (root / "support/hardware/rtx4060-lab-profile.json").read_text()
        )

    def test_target_is_unobserved_and_not_prematurely_qualified(self):
        profile = self.profile
        self.assertEqual(profile["selected_route"],
                         "linux_guest_driver_exclusive_gpu_passthrough_on_asterinas_vmm")
        self.assertIn("not_detected", profile["state"])
        self.assertIsNone(profile["target_gpu"]["observed_pci_bdf"])
        self.assertIsNone(profile["target_gpu"]["observed_driver"])
        self.assertIsNone(profile["physical_host"]["cpu"])
        self.assertFalse(profile["physical_host"]["verified_isolated_machine"])
        self.assertTrue(all(value is False for value in profile["gates"].values()))

    def test_fixed_gemm_reference_matches_executable_oracle(self):
        test = self.profile["test"]
        a, b = cuda_gemm.inputs()
        self.assertEqual(test["shape"], [16, 16, 16])
        self.assertEqual(test["reference_sha256"],
                         cuda_gemm.digest(cuda_gemm.reference(a, b)))
        self.assertEqual(test["dtype"], "float32")
        self.assertTrue(test["gpu_execution_required"])

    def test_device_identity_and_supervised_process_policy(self):
        gate = self.profile["device_identity_gate"]
        self.assertTrue(matches_target_model(gate["lab_gpu_model_exact"],
                                             "RTX 4060"))
        for variant in gate["rejects_variant_models"]:
            self.assertFalse(matches_target_model(variant, "RTX 4060"))
        self.assertTrue(gate["pci_bdf_is_explicit_and_required"])
        self.assertEqual(gate["normalized_pci_domain_hex_widths"], [4, 8])
        self.assertEqual(gate["pci_slot_max"], 31)
        self.assertEqual(gate["vendor_cuda_compute_capability"], "8.9")
        self.assertEqual(canonical_bdf("0000:01:00.0"),
                         canonical_bdf("00000000:01:00.0"))
        self.assertEqual(gate["supervised_child_schema"], "a09.cuda-gemm.v2")
        self.assertTrue(gate["guest_linux_kernel_process_provenance_required"])
        self.assertTrue(gate["worker_pid_equals_compute_process_pid"])
        self.assertTrue(gate["all_gemm_and_cleanup_stages_pass_required"])
        self.assertFalse(gate["hardware_verified_by_self_report"])

    def test_safety_and_blocker_ledger_does_not_authorize_hardware(self):
        profile = self.profile
        self.assertTrue(profile["latest_readonly_observation"].endswith(".json"))
        self.assertTrue(profile["hardware_blocker_issue"].endswith("/issues/96"))
        self.assertEqual(profile["safety"]["allowed_environment"],
                         "authorized_idle_disposable_lab_only")
        for field in ("driver_rebind", "firmware_flash", "bios_modify",
                      "prod_reset", "ollama"):
            self.assertFalse(profile["safety"][field])


if __name__ == "__main__":
    unittest.main()
