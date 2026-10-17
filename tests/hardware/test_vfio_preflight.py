"""Fixture tests of read-only VFIO planning; no device opened or changed."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
import vfio_preflight as vfio

GPU = "0000:01:00.0"
AUDIO = "0000:01:00.1"


class VFIOTests(unittest.TestCase):
    def fixture(self, root, group="27", members=(GPU,), drivers=None):
        group_path = root / "sys/kernel/iommu_groups" / group
        (group_path / "devices").mkdir(parents=True)
        for member in members:
            dev = root / "sys/bus/pci/devices" / member
            dev.mkdir(parents=True)
            (dev / "vendor").write_text("0x10de\n")
            (dev / "device").write_text("0x28a0\n")
            (dev / "class").write_text("0x030200\n" if member == GPU else "0x040300\n")
            (dev / "iommu_group").symlink_to(group_path, target_is_directory=True)
            (group_path / "devices" / member).symlink_to(dev, target_is_directory=True)
            if drivers and member in drivers:
                driver_dir = root / "sys/bus/pci/drivers" / drivers[member]
                driver_dir.mkdir(parents=True, exist_ok=True)
                (dev / "driver").symlink_to(driver_dir, target_is_directory=True)

    def inspect(self, root, members=(GPU,), vendor="0x10de", device_id=None):
        return vfio.inspect(root, GPU, members, vendor, device_id)

    def test_missing_device_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            result = self.inspect(Path(d))
        self.assertIn("target_pci_device_missing", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["safe_to_assign"])

    def test_even_isolated_fixture_demands_manual_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, drivers={GPU: "vfio-pci"})
            result = self.inspect(root, device_id="0x28a0")
        self.assertEqual(result["hard_blockers"], [])
        self.assertEqual(result["status"], "manual_review_required")
        self.assertFalse(result["safe_to_assign"])
        self.assertGreater(len(result["unverified_required_gates"]), 0)

    def test_unexpected_audio_function_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, AUDIO))
            result = self.inspect(root)
        self.assertIn("unexpected_or_missing_iommu_group_member", result["hard_blockers"])
        self.assertEqual(result["observed_group_members"], [GPU, AUDIO])

    def test_all_function_allowlist_still_manual_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, AUDIO),
                         drivers={GPU: "vfio-pci", AUDIO: "vfio-pci"})
            result = self.inspect(root, members=(GPU, AUDIO))
        self.assertEqual(result["status"], "manual_review_required")

    def test_bound_gpu_driver_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, drivers={GPU: "nvidia"})
            result = self.inspect(root)
        self.assertIn("device_bound_to_non_vfio_driver", result["hard_blockers"])
        self.assertIn("iommu_peer_bound_to_non_vfio_driver", result["hard_blockers"])

    def test_bound_peer_driver_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, AUDIO), drivers={AUDIO: "snd_hda_intel"})
            result = self.inspect(root, members=(GPU, AUDIO))
        self.assertIn("iommu_peer_bound_to_non_vfio_driver", result["hard_blockers"])

    def test_noiommu_mode_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            unsafe = root / "sys/module/vfio/parameters/enable_unsafe_noiommu_mode"
            unsafe.parent.mkdir(parents=True)
            unsafe.write_text("Y\n")
            result = self.inspect(root)
        self.assertIn("unsafe_noiommu_mode_enabled", result["hard_blockers"])

    def test_pci_vendor_and_device_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            result = self.inspect(root, vendor="0x1002", device_id="0xffff")
        self.assertIn("pci_vendor_mismatch", result["hard_blockers"])
        self.assertIn("pci_device_mismatch", result["hard_blockers"])

    def test_invalid_bdf_and_missing_allowlist_rejected_before_io(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for args in (("../../etc/passwd", [GPU]), (GPU, []), (GPU, [GPU, GPU]),
                         (GPU, ["0000:02:00.0"])):
                with self.assertRaises(ValueError):
                    vfio.inspect(root, args[0], args[1])

    def test_missing_peer_link_blocks_even_if_group_lists_member(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, AUDIO))
            (root / "sys/bus/pci/devices" / AUDIO / "iommu_group").unlink()
            result = self.inspect(root, members=(GPU, AUDIO))
        self.assertIn("iommu_peer_link_inconsistent", result["hard_blockers"])

    def test_uppercase_bdf_matches_canonical_linux_sysfs_and_allowlist(self):
        alpha = "0000:0a:0b.0"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(alpha,), drivers={alpha: "vfio-pci"})
            (root / "sys/bus/pci/devices" / alpha / "class").write_text("0x030200\\n")
            result = vfio.inspect(root, "0000:0A:0B.0", ["0000:0A:0B.0"])
        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(result["requested_bdf"], alpha)
        self.assertEqual(result["expected_group_members"], [alpha])

    def test_unresolved_driver_symlink_is_hard_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            (root / "sys/bus/pci/devices" / GPU / "driver").symlink_to(
                root / "sys/bus/pci/drivers/nonexistent"
            )
            result = self.inspect(root)
        self.assertIn("device_driver_link_unresolvable", result["hard_blockers"])
        self.assertIn("iommu_peer_driver_link_unresolvable", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_unsafe_vfio_interrupt_remapping_override_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            unsafe = root / "sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
            unsafe.parent.mkdir(parents=True)
            unsafe.write_text("Y\n")
            result = self.inspect(root)
        self.assertIn("unsafe_interrupt_remapping_override_enabled", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_disappearing_iommu_group_enumeration_stays_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            broken = root / "sys/kernel/iommu_groups/27/devices"
            real_iterdir = Path.iterdir
            def race(path):
                if path == broken:
                    raise OSError("IOMMU group removed during enumeration")
                return real_iterdir(path)
            with patch.object(Path, "iterdir", race):
                result = self.inspect(root)
        self.assertIn("iommu_group_members_unobservable", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_disappearing_msi_enumeration_stays_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            broken = root / "sys/bus/pci/devices" / GPU / "msi_irqs"
            broken.mkdir()
            real_iterdir = Path.iterdir
            def race(path):
                if path == broken:
                    raise OSError("MSI table removed during enumeration")
                return real_iterdir(path)
            with patch.object(Path, "iterdir", race):
                result = self.inspect(root)
        self.assertIn("msi_irq_enumeration_unobservable", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")


    def test_unbound_target_gpu_never_counts_as_vfio_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            result = self.inspect(root)
        self.assertIn("target_gpu_not_bound_to_vfio", result["hard_blockers"])
        self.assertIn("iommu_peer_unbound_non_bridge", result["hard_blockers"])
        self.assertFalse(result["driver_binding"]["all_group_bound_to_expected"])
        self.assertEqual(result["status"], "blocked")

    def test_unbound_audio_peer_is_not_group_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, AUDIO), drivers={GPU: "vfio-pci"})
            result = self.inspect(root, members=(GPU, AUDIO))
        self.assertIn("iommu_peer_unbound_non_bridge", result["hard_blockers"])
        self.assertFalse(result["driver_binding"]["all_group_bound_to_expected"])

    def test_unbound_bridge_peer_is_not_reported_as_vfio_bound(self):
        bridge = "0000:00:1e.0"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, members=(GPU, bridge), drivers={GPU: "vfio-pci"})
            (root / "sys/bus/pci/devices" / bridge / "class").write_text("0x060400\n")
            result = self.inspect(root, members=(GPU, bridge))
        self.assertEqual(result["status"], "manual_review_required")
        self.assertFalse(result["driver_binding"]["all_group_bound_to_expected"])
        self.assertFalse(result["safe_to_assign"])

    def test_driver_override_cannot_claim_nvidia_as_vfio(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root, drivers={GPU: "nvidia"})
            result = vfio.preflight(root, GPU, (GPU,), expected_driver="nvidia")
        self.assertIn("non_vfio_expected_driver_forbidden", result["hard_blockers"])
        self.assertEqual(result["status"], "blocked")

    def test_fifo_sysfs_attribute_never_blocks(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vendor"
            os.mkfifo(path)
            self.assertIsNone(vfio.text_file(path))

    def test_unbounded_sysfs_fixture_is_not_read_to_completion(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vendor"
            path.write_bytes(b"a" * (vfio.MAX_SYSFS_TEXT_BYTES + 10))
            self.assertIsNone(vfio.text_file(path))


    def test_unreadable_existing_unsafe_mode_setting_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, drivers={GPU: "vfio-pci"})
            setting = root / "sys/module/vfio/parameters/enable_unsafe_noiommu_mode"
            setting.parent.mkdir(parents=True)
            external = root / "dummy-unsafe-setting"
            external.write_text("Y\n")
            setting.symlink_to(external)
            report = self.inspect(root)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("unsafe_noiommu_mode_unobservable", report["hard_blockers"])

    def test_oversized_interrupt_setting_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, drivers={GPU: "vfio-pci"})
            setting = root / "sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
            setting.parent.mkdir(parents=True)
            setting.write_bytes(b"N" * (vfio.MAX_SYSFS_TEXT_BYTES + 1))
            report = self.inspect(root)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("unsafe_interrupt_remapping_setting_unobservable", report["hard_blockers"])

if __name__ == "__main__":
    unittest.main()
