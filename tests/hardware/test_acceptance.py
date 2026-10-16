"""Adversarial synthetic cross-kernel evidence tests; never hardware tests."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/vmm"))
import acceptance


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.hostlog = b"ASTERINAS-BOOT-A09-MARKER guest spawned\n"
        self.guestlog = b"LINUX-GUEST-A09-MARKER CUDA program started\n"
        self.host = {
            "schema": "a09.asterinas-host-vmm-evidence.v1",
            "host_kernel": "asterinas-derived",
            "upstream_pin": acceptance.KERNEL_PIN,
            "host_boot_log_sha256": hashlib.sha256(self.hostlog).hexdigest(),
            "host_boot_marker": "ASTERINAS-BOOT-A09-MARKER",
            "vm": {"backend": "intel-vmx", "host_cpu_vendor": "GenuineIntel",
                   "hardware_virtualization_executed": True, "guest_linux_booted": True,
                   "vm_id": "evidence-test-vm", "boot_nonce": "ab" * 16},
            "device": {"owner": "asterinas-host-vmm", "iommu_group_complete": True,
                       "iommu_dma_translation_enabled": True, "interrupt_remapping_enabled": True,
                       "host_driver_detached_from_prod": False,
                       "device_idle_isolated_lab": True,
                       "DMA_quiescence_on_teardown_verified": True,
                       "no_device_reset_during_test": True,
                       "vendor_id": "0x10de", "device_id": "0x28a0", "host_bdf": "0000:05:00.0"},
        }
        self.guest = {
            "schema": "a09.linux-guest-gpu-evidence.v1",
            "guest_boot_log_sha256": hashlib.sha256(self.guestlog).hexdigest(),
            "guest_boot_marker": "LINUX-GUEST-A09-MARKER",
            "vm": {"vm_id": "evidence-test-vm", "boot_nonce": "ab" * 16},
            "device": {"vendor_id": "0x10de", "device_id": "0x28a0",
                       "guest_bdf": "0000:03:00.0", "nvidia_driver_version": "fixture",
                       "firmware_manifest_sha256": "f" * 64},
            "gemm": {"schema": "a09.cuda-bounded-run.v1",
                     "status": "guest_cuda_reported_pass_not_asterinas_attestation",
                     "requested_guest_bdf": "0000:03:00.0", "child_exit_code": 0,
                     "child_evidence": {"schema": "a09.cuda-gemm.v1",
                                        "status": "passed_on_reported_cuda_environment",
                                        "actual_output_sha256":
                                        "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847",
                                        "expected_output_sha256":
                                        "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847",
                                        "device_access_attempted": True,
                                        "device_memory_allocated": True,
                                        "results_copied": True,
                                        "resources_released": True,
                                        "cuda_kernel_launched": True,
                                        "synchronization_completed": True,
                                        "no_cpu_fallback": True,
                                        "device": {"device_bdf": "0000:03:00.0"}}},
        }

    def reasons(self):
        return acceptance.validate(self.host, self.guest, self.hostlog, self.guestlog)

    def test_consistent_synthetic_evidence_never_auto_passes_hardware(self):
        self.assertEqual(self.reasons(), [])  # Eligible for independent review ONLY.

    def test_malformed_non_string_fields_fail_closed_without_exception(self):
        self.host["vm"]["backend"] = []
        self.host["device"]["host_bdf"] = None
        self.guest["device"]["guest_bdf"] = 5
        self.guest["gemm"]["child_evidence"]["device"]["device_bdf"] = None
        reasons = self.reasons()
        self.assertIn("unknown_vmm_backend", reasons)
        self.assertIn("host_pci_bdf_missing", reasons)
        self.assertIn("guest_pci_bdf_missing", reasons)
        self.assertIn("guest_cuda_pci_identity_mismatch", reasons)

    def test_zero_log_missing(self):
        self.hostlog = b""
        self.assertIn("host_raw_log_missing", self.reasons())

    def test_linux_host_rejected(self):
        self.host["host_kernel"] = "linux"
        self.assertIn("not_asterinas_host", self.reasons())

    def test_wrong_upstream_pin_rejected(self):
        self.host["upstream_pin"] = "e" * 40
        self.assertIn("wrong_asterinas_source_pin", self.reasons())

    def test_vmx_on_amd_cpu_rejected(self):
        self.host["vm"]["host_cpu_vendor"] = "AuthenticAMD"
        self.assertIn("vm_backend_cpu_mismatch", self.reasons())

    def test_no_virtualization_executed_rejected(self):
        self.host["vm"]["hardware_virtualization_executed"] = False
        self.assertIn("vmm_hardware_not_executed", self.reasons())

    def test_dma_and_irq_must_be_proven(self):
        self.host["device"]["iommu_dma_translation_enabled"] = False
        self.host["device"]["interrupt_remapping_enabled"] = False
        self.assertIn("iommu_dma_not_enforced", self.reasons())
        self.assertIn("interrupts_not_isolated", self.reasons())

    def test_missing_gpu_allocation_or_copy_invalidates_success_evidence(self):
        evidence = self.guest["gemm"]["child_evidence"]
        for field in ("device_access_attempted", "device_memory_allocated",
                      "results_copied", "expected_output_sha256"):
            with self.subTest(field=field):
                original = evidence.pop(field)
                self.assertIn("invalid_cuda_gemm_result", self.reasons())
                evidence[field] = original

    def test_bounded_reader_never_requests_unlimited_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guest.log"
            path.write_bytes(b"small fixture")
            original_fdopen = os.fdopen

            class Meter:
                def __init__(self, source):
                    self.source = source

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.source.close()

                def fileno(self):
                    return self.source.fileno()

                def read(self, size=-1):
                    if size < 0 or size > acceptance.MAX_RAW_LOG_BYTES + 1:
                        raise AssertionError("unbounded evidence read")
                    return self.source.read(size)

            def monitored_fdopen(fd, *args, **kwargs):
                return Meter(original_fdopen(fd, *args, **kwargs))

            with patch.object(acceptance.os, "fdopen", monitored_fdopen):
                self.assertEqual(acceptance.bounded_log(path), b"small fixture")

    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "fake-serial.log"
            os.mkfifo(fifo)
            # A regression to Path.open() would block before the fstat().
            # Bound this negative case in a disposable subprocess.
            module_dir = str(Path(acceptance.__file__).resolve().parent)
            command = (
                "import sys\nfrom pathlib import Path\n"
                f"sys.path.insert(0, {module_dir!r})\n"
                "import acceptance\n"
                "try:\n"
                f"    acceptance.bounded_log(Path({str(fifo)!r}))\n"
                "except ValueError:\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(3)\n"
            )
            run = subprocess.run(
                [sys.executable, "-I", "-c", command],
                capture_output=True, text=True, timeout=3,
            )
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_oversized_raw_log_is_rejected_without_unbounded_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge.log"
            with path.open("wb") as output:
                output.seek(acceptance.MAX_RAW_LOG_BYTES)
                output.write(b"x")
            with self.assertRaises(ValueError):
                acceptance.bounded_log(path)

    def test_bounded_json_object_load_and_reject_nonobject(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "valid.json"
            good.write_text('{"schema":"a09.host","marker":"测试"}', encoding="utf-8")
            self.assertEqual(acceptance.load_json(good)["marker"], "测试")
            bad = root / "list.json"
            bad.write_text('[1,2,3]')
            with self.assertRaises(ValueError):
                acceptance.load_json(bad)
            bad.write_bytes(b"\xff")
            with self.assertRaises(UnicodeError):
                acceptance.load_json(bad)

    def test_json_symlink_and_fifo_are_never_trusted_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            external = root / "original.json"
            external.write_text('{"allowed":true}')
            alias = root / "aliased.json"
            alias.symlink_to(external)
            with self.assertRaises(OSError):
                acceptance.load_json(alias)
            fifo = root / "pipe.json"
            os.mkfifo(fifo)
            # O_NONBLOCK must keep this immediate without any FIFO writer.
            with self.assertRaises(ValueError):
                acceptance.load_json(fifo)

    def test_sparse_oversized_json_rejected_without_reading_entire_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            with path.open("wb") as output:
                output.seek(acceptance.MAX_EVIDENCE_JSON_BYTES)
                output.write(b"x")
            with self.assertRaises(ValueError):
                acceptance.load_json(path)

    def test_guest_cpu_only_does_not_count(self):
        self.guest["gemm"]["child_evidence"]["cuda_kernel_launched"] = False
        self.assertIn("invalid_cuda_gemm_result", self.reasons())

    def test_forged_child_cuda_bdf_rejected(self):
        self.guest["gemm"]["child_evidence"]["device"]["device_bdf"] = "0000:04:00.0"
        self.assertIn("guest_cuda_pci_identity_mismatch", self.reasons())

    def test_host_and_guest_pci_id_mismatch(self):
        self.guest["device"]["device_id"] = "0xbeef"
        self.assertIn("physical_guest_pci_id_mismatch", self.reasons())

    def test_cross_vm_replay_rejected(self):
        self.guest["vm"]["boot_nonce"] = "cd" * 16
        self.assertIn("boot_nonce_mismatch", self.reasons())

    def test_wrong_raw_log_digest_rejected(self):
        self.hostlog = b"host Linux instead of Asterinas\n"
        self.assertIn("host_raw_log_digest_mismatch", self.reasons())
        self.assertIn("host_boot_marker_not_in_log", self.reasons())

    def test_no_hardware_dma_recovery_proof_rejected(self):
        self.host["device"]["DMA_quiescence_on_teardown_verified"] = False
        self.assertIn("dma_reclamation_unverified", self.reasons())

    def test_no_production_host_mutation(self):
        self.host["device"]["host_driver_detached_from_prod"] = True
        self.assertIn("production_driver_mutation_forbidden", self.reasons())

    def test_invalid_guest_gpu_firmware_manifest_rejected(self):
        self.guest["device"]["firmware_manifest_sha256"] = None
        self.assertIn("guest_firmware_manifest_not_verified", self.reasons())

    def test_no_guest_kernel_boot_rejected(self):
        self.host["vm"]["guest_linux_booted"] = False
        self.assertIn("linux_guest_not_booted", self.reasons())


if __name__ == "__main__":
    unittest.main()
