"""Synthetic inventory contract tests only; never actual GPU/VM evidence."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/vmm"))
from platform_gate import assess


def candidate():
    return {
        "schema": "a09.readonly-hardware-probe.v1",
        "execution_environment": {"kernel": "Linux"},
        "cpu": {"vendor_id": "GenuineIntel", "vmx_flag": True, "svm_flag": False},
        "iommu": {"dmar_table_present": True, "group_count_visible": 17},
        "pci_devices": [{"vendor_id": "0x10de", "is_accelerator_class": True,
                         "bdf": "0000:01:00.0"}],
    }


class PlatformGateTests(unittest.TestCase):
    def test_complete_synthetic_intel_host_never_auto_approves(self):
        result = assess(candidate())
        self.assertEqual(result["status"], "manual_review_required")
        self.assertFalse(result["passthrough_approved"])
        self.assertFalse(result["asterinas_gpu_verified"])
        self.assertEqual(result["visible_candidate_bdfs"], ["0000:01:00.0"])

    def test_amd_svm_not_substituted_for_intel_vmx(self):
        data = candidate()
        data["cpu"] = {"vendor_id": "AuthenticAMD", "vmx_flag": False, "svm_flag": True}
        result = assess(data)
        self.assertIn("intel_host_not_identified_no_vmx_backend_proof", result["blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_missing_vmx_rejects_even_intel(self):
        data = candidate()
        data["cpu"]["vmx_flag"] = False
        self.assertIn("intel_vmx_not_exposed", assess(data)["blockers"])

    def test_missing_dmar_blocks(self):
        data = candidate()
        data["iommu"]["dmar_table_present"] = False
        self.assertIn("intel_dmar_table_not_visible", assess(data)["blockers"])

    def test_no_iommu_group_blocks(self):
        data = candidate()
        data["iommu"]["group_count_visible"] = 0
        self.assertIn("iommu_group_not_visible", assess(data)["blockers"])

    def test_gpu_not_visible_is_blocker(self):
        data = candidate()
        data["pci_devices"] = []
        self.assertIn("nvidia_accelerator_not_visible", assess(data)["blockers"])

    def test_boolean_iommu_group_count_must_not_be_treated_as_one(self):
        data = candidate()
        data["iommu"]["group_count_visible"] = True
        self.assertIn("iommu_group_not_visible", assess(data)["blockers"])

    def test_missing_fields_fail_closed(self):
        result = assess(None)
        self.assertEqual(result["status"], "blocked")
        self.assertGreaterEqual(len(result["blockers"]), 5)


if __name__ == '__main__':
    unittest.main()
