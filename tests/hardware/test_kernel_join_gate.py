"""CPU-only fixtures for the A01/A05/A06 kernel source prerequisite gate."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "support/vmm"))
import kernel_join_gate as gate


class KernelJoinGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sources = {
            "iommu_dma": """// The page table of all devices is the same.
pub(crate) unsafe fn map(daddr: Daddr, paddr: Paddr) {}
pub(crate) fn unmap(daddr: Daddr) {}
let dev = PciDeviceLocation::zero();
""",
            "iommu_irq": "pub(in crate::arch) fn alloc_irt_entry() {}",
            "guest_mode": "pub struct GuestMode {}",
            "dma_stream": "pub struct DmaStream<T> {}",
            "resource_domain": "pub struct ResourceDomain {}",
        }
        self.write_sources()

    def write_sources(self):
        for name, source in self.sources.items():
            path = self.root / gate.SOURCE_PATHS[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

    def test_checked_out_kernel_sources_are_present_but_not_approved(self):
        # CI uses actual checked-out A01 kernel + A03 host control library.
        # Existence and a source hash are necessary, NEVER a GPU pass.
        checkout_root = pathlib.Path(__file__).resolve().parents[2]
        result = gate.audit(checkout_root)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["passthrough_approved"])
        for name in gate.SOURCE_PATHS:
            self.assertEqual(len(result["source_sha256"][name]), 64, name)
        if result["observations"]["shared_iommu_page_table_source_pattern"]:
            self.assertIn("iommu_shared_device_page_table_detected", result["hard_blockers"])

    def test_pinned_global_page_table_denies_guest_passthrough(self):
        result = gate.audit(self.root)
        self.assertIn("iommu_shared_device_page_table_detected", result["hard_blockers"])
        self.assertIn("iommu_device_scoped_map_unmap_not_found", result["hard_blockers"])
        self.assertFalse(result["passthrough_approved"])
        self.assertFalse(result["asterinas_gpu_verified"])
        self.assertTrue(result["observations"]["ostd_guest_mode_primitive_visible"])
        self.assertTrue(result["observations"]["ostd_dma_stream_primitive_visible"])

    def test_symlink_and_fifo_sources_remain_blocked(self):
        import os
        source = self.root / gate.SOURCE_PATHS["iommu_dma"]
        target = self.root / "real_source.rs"
        source.rename(target)
        source.symlink_to(target)
        result = gate.audit(self.root)
        self.assertIn("required_source_missing_or_unreadable:iommu_dma", result["hard_blockers"])
        source.unlink()
        os.mkfifo(source)
        result = gate.audit(self.root)
        self.assertIn("required_source_missing_or_unreadable:iommu_dma", result["hard_blockers"])

    def test_missing_source_is_explicit_blocker(self):
        (self.root / gate.SOURCE_PATHS["iommu_dma"]).unlink()
        record = gate.audit(self.root)
        self.assertIn("required_source_missing_or_unreadable:iommu_dma", record["hard_blockers"])
        self.assertIsNone(record["source_sha256"]["iommu_dma"])

    def test_future_scoped_functions_remain_hardware_unverified(self):
        self.sources["iommu_dma"] = """pub(crate) unsafe fn map(device: DeviceId, daddr: Daddr, paddr: Paddr) {}
pub(crate) fn unmap(device: DeviceId, daddr: Daddr) {}
"""
        self.write_sources()
        record = gate.audit(self.root)
        self.assertNotIn("iommu_shared_device_page_table_detected", record["hard_blockers"])
        self.assertNotIn("iommu_device_scoped_map_unmap_not_found", record["hard_blockers"])
        self.assertIn("per_iommu_group_dma_irq_isolation_not_hardware_verified", record["hard_blockers"])
        self.assertEqual(record["status"], "blocked")

    def test_fake_scoped_interfaces_in_comments_do_not_pass(self):
        self.sources["iommu_dma"] = (
            "// pub(crate) unsafe fn map(device: DeviceId, daddr: Daddr) {}\n"
            "/* pub(crate) fn unmap(device: DeviceId, daddr: Daddr) {} */\n"
        )
        self.write_sources()
        result = gate.audit(self.root)
        self.assertIn("iommu_device_scoped_map_unmap_not_found", result["hard_blockers"])
        self.assertFalse(result["observations"]["device_scoped_map_signature_visible"])
        self.assertFalse(result["observations"]["device_scoped_unmap_signature_visible"])

    def test_string_literal_cannot_forge_scoped_map_interface(self):
        self.sources["iommu_dma"] = (
            'let fake = "pub(crate) unsafe fn map(device: DeviceId, daddr: Daddr) {}";\n'
            'let fake2 = "pub(crate) fn unmap(device: DeviceId, daddr: Daddr) {}";\n'
        )
        self.write_sources()
        result = gate.audit(self.root)
        self.assertIn("iommu_device_scoped_map_unmap_not_found", result["hard_blockers"])

    def test_untrusted_source_marker_cannot_fake_gpu_pass(self):
        self.sources["iommu_dma"] += "\n// GPU_PASSTHROUGH_SUCCESS=TRUE\n"
        self.write_sources()
        record = gate.audit(self.root)
        self.assertFalse(record["passthrough_approved"])

    def test_zero_bytes_or_missing_guest_mode_blocks(self):
        self.sources["guest_mode"] = ""
        self.write_sources()
        record = gate.audit(self.root)
        self.assertIn("ostd_guest_mode_primitive_missing", record["hard_blockers"])

    def test_source_fingerprint_changes_if_mapping_code_changes(self):
        one = gate.audit(self.root)
        self.sources["iommu_dma"] += "// subsequent upstream review\n"
        self.write_sources()
        two = gate.audit(self.root)
        self.assertNotEqual(one["source_sha256"]["iommu_dma"], two["source_sha256"]["iommu_dma"])


if __name__ == "__main__":
    unittest.main()
