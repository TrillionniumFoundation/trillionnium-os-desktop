"""CPU-only fixtures for the A01/A05/A06 kernel source prerequisite gate."""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/vmm"))
import kernel_join_gate as gate


class KernelJoinGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = {
            "iommu_dma": """
                pub(crate) unsafe fn map(daddr: Daddr, paddr: Paddr) {}
                pub(crate) fn unmap(daddr: Daddr) {}
                let dev = PciDeviceLocation::zero();
                for table in PciDeviceLocation::all() {
                    root.specify_device_page_table(table, page_table.shallow_copy());
                }
            """,
            "iommu_irq": "pub(in crate::arch) fn alloc_irt_entry() {}",
            "guest_mode": "pub struct GuestMode {}",
            "dma_stream": "pub struct DmaStream<T> {}",
            "resource_domain": "pub struct ResourceDomain {}",
            "x86_vm": "pub struct GuestContext {}",
            "x86_vmx": "pub struct VmxGuard {} fn vmxon() {}",
        }
        self.write_sources()

    def write_sources(self):
        for name, source in self.sources.items():
            path = self.root / gate.SOURCE_PATHS[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

    def test_global_page_table_is_blocked_and_non_target_backends_are_observations(self):
        result = gate.audit(self.root)
        self.assertIn("iommu_shared_device_page_table_detected", result["hard_blockers"])
        self.assertIn("iommu_device_scoped_map_unmap_not_found", result["hard_blockers"])
        self.assertNotIn("amd_svm_source_evidence_missing", result["hard_blockers"])
        self.assertNotIn("arm_el2_source_evidence_missing", result["hard_blockers"])
        self.assertFalse(result["observations"]["amd_svm_source_visible"])
        self.assertFalse(result["observations"]["arm_el2_source_visible"])
        self.assertEqual(result["target_arch"], "x86_64")
        self.assertFalse(result["passthrough_approved"])
        self.assertFalse(result["asterinas_gpu_verified"])
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["observations"]["intel_vmx_source_visible"])

    def test_future_scoped_functions_remove_only_the_lexical_iommu_blocker(self):
        self.sources["iommu_dma"] = """
            pub(crate) unsafe fn map(device: DeviceId, daddr: Daddr, paddr: Paddr) {}
            pub(crate) fn unmap(group: IommuGroupId, daddr: Daddr) {}
        """
        self.write_sources()
        result = gate.audit(self.root)
        self.assertNotIn("iommu_shared_device_page_table_detected", result["hard_blockers"])
        self.assertNotIn("iommu_device_scoped_map_unmap_not_found", result["hard_blockers"])
        self.assertTrue(result["observations"]["device_scoped_map_signature_visible"])
        self.assertTrue(result["observations"]["device_scoped_unmap_signature_visible"])
        self.assertIn("per_iommu_group_dma_irq_isolation_not_hardware_verified", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_comments_and_strings_cannot_forge_backend_or_scope_evidence(self):
        self.sources["iommu_dma"] = r'''
            // pub fn map(device: DeviceId, daddr: Daddr, paddr: Paddr) {}
            /* PciDeviceLocation::zero(); fn unmap(group: GroupId, daddr: Daddr) {} */
            pub(crate) unsafe fn map(daddr: Daddr, paddr: Paddr) {}
            pub(crate) fn unmap(daddr: Daddr) {}
            const TEXT: &str = "fn map(device: DeviceId) {} SVM ARM EL2";
        '''
        self.sources["x86_vmx"] = 'const TEXT: &str = "VmxGuard SVM VMCB";'
        self.sources["x86_vm"] = "pub struct GuestContext {}; // EL2"
        self.write_sources()
        result = gate.audit(self.root)
        self.assertFalse(result["observations"]["device_scoped_map_signature_visible"])
        self.assertFalse(result["observations"]["device_scoped_unmap_signature_visible"])
        self.assertFalse(result["observations"]["amd_svm_source_visible"])
        self.assertFalse(result["observations"]["arm_el2_source_visible"])

    def test_future_svm_and_el2_backend_tokens_are_observed_but_not_approved(self):
        self.sources["amd_svm"] = "pub struct Vmcb {} fn vmrun() {}"
        self.sources["arm_el2"] = "pub fn enter_el2() {} const HCR_EL2: u64 = 0;"
        self.write_sources()
        result = gate.audit(self.root)
        self.assertTrue(result["observations"]["amd_svm_source_visible"])
        self.assertTrue(result["observations"]["arm_el2_source_visible"])
        self.assertFalse(result["passthrough_approved"])
        self.assertFalse(result["asterinas_gpu_verified"])
        self.assertIn("hardware_virtualization_execution_not_verified", result["hard_blockers"])

    def test_non_intel_backend_scope_is_checked_only_when_requested(self):
        self.sources["amd_svm"] = "pub struct Vmcb {} fn vmrun() {}"
        self.write_sources()
        result = gate.audit(self.root, "x86_64-amd-svm")
        self.assertNotIn("amd_svm_source_evidence_missing", result["hard_blockers"])
        arm_result = gate.audit(self.root, "aarch64")
        self.assertIn("arm_el2_source_evidence_missing", arm_result["hard_blockers"])

    def test_missing_symlink_fifo_and_oversized_sources_fail_closed(self):
        target = self.root / "outside.rs"
        target.write_text("pub(crate) fn map(device: DeviceId) {}", encoding="utf-8")
        path = self.root / gate.SOURCE_PATHS["iommu_dma"]
        path.unlink()
        path.symlink_to(target)
        result = gate.audit(self.root)
        self.assertFalse(result["source_files"]["iommu_dma"]["present"])
        self.assertIn("required_source_missing_or_unreadable:iommu_dma", result["hard_blockers"])

        path.unlink()
        os.mkfifo(path)
        result = gate.audit(self.root)
        self.assertFalse(result["source_files"]["iommu_dma"]["present"])

        path.unlink()
        with path.open("wb") as stream:
            stream.seek(gate.MAX_SOURCE_BYTES)
            stream.write(b"x")
        result = gate.audit(self.root)
        self.assertFalse(result["source_files"]["iommu_dma"]["present"])

    def test_source_digest_is_bound_to_observed_bytes(self):
        first = gate.audit(self.root)
        digest = first["source_sha256"]["iommu_dma"]
        self.assertEqual(
            digest,
            hashlib.sha256(self.sources["iommu_dma"].encode("utf-8")).hexdigest(),
        )
        self.sources["iommu_dma"] += "\n// later review note\n"
        self.write_sources()
        second = gate.audit(self.root)
        self.assertNotEqual(digest, second["source_sha256"]["iommu_dma"])

    def test_real_checkout_gate_is_always_blocked(self):
        result = gate.audit(Path(__file__).resolve().parents[2])
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["passthrough_approved"])
        self.assertFalse(result["asterinas_gpu_verified"])
        self.assertIn("hardware_virtualization_execution_not_verified", result["hard_blockers"])


if __name__ == "__main__":
    unittest.main()
