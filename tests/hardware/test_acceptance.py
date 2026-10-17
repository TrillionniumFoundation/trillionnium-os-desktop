"""Adversarial synthetic cross-kernel evidence tests; never hardware tests."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/vmm"))
import acceptance


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        # Both serial transcripts must independently bind the same VM boot.
        nonce_tag = b"A09_VM_NONCE=" + b"ab" * 16
        self.hostlog = b"ASTERINAS-BOOT-A09-MARKER guest spawned\n" + nonce_tag + b"\n"
        self.guestlog = b"LINUX-GUEST-A09-MARKER CUDA program started\n" + nonce_tag + b"\n"
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
                                        "test": "gemm16_f32",
                                        "dimension": [16, 16, 16],
                                        "input_a_sha256": "0d9121c90b659969a44ca689809ebd3a6579f3f18b6aa5b9de5da1b98a9458ae",
                                        "input_b_sha256": "37ca62264050ddd6b8674649a77ec6047f3aa1a2d87f97858f7f6be38189df74",
                                        "driver_api": "CUDA Driver API",
                                        "compiler": "NVRTC",
                                        "device_access_attempted": True,
                                        "device_memory_allocated": True,
                                        "results_copied": True,
                                        "resources_released": True,
                                        "cuda_kernel_launched": True,
                                        "synchronization_completed": True,
                                        "no_cpu_fallback": True,
                                        "device": {"device_bdf": "0000:03:00.0",
                                                   "device_name": "NVIDIA GeForce RTX 4060",
                                                   "device_index": 0,
                                                   "cuda_driver_api_version": 12040,
                                                   "nvrtc_version": "12.4",
                                                   "compute_capability": "8.9"}}},
        }

    def reasons(self):
        return acceptance.validate(self.host, self.guest, self.hostlog, self.guestlog)

    def test_consistent_synthetic_evidence_never_auto_passes_hardware(self):
        self.assertEqual(self.reasons(), [])  # Eligible for independent review ONLY.

    def test_current_cuda_v2_child_record_remains_review_only(self):
        child = self.guest["gemm"]["child_evidence"]
        child["schema"] = "a09.cuda-gemm.v2"
        child["device_access_attempted"] = True
        child["timeout_enforced"] = True
        self.assertEqual(self.reasons(), [])  # Still unsigned; never automatic acceptance.

    def _write_bundle(self, directory):
        root = Path(directory)
        host_path = root / "host.json"
        guest_path = root / "guest.json"
        host_log = root / "host.serial"
        guest_log = root / "guest.serial"
        host_path.write_text(json.dumps(self.host), encoding="utf-8")
        guest_path.write_text(json.dumps(self.guest), encoding="utf-8")
        host_log.write_bytes(self.hostlog)
        guest_log.write_bytes(self.guestlog)
        return host_path, guest_path, host_log, guest_log

    def test_cli_consistent_bundle_is_review_required_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            host, guest, host_log, guest_log = self._write_bundle(directory)
            output = Path(directory) / "acceptance.json"
            with patch.object(sys, "argv", [
                "acceptance.py", "--host", str(host), "--guest", str(guest),
                "--host-log", str(host_log), "--guest-log", str(guest_log),
                "--output", str(output),
            ]):
                self.assertEqual(acceptance.main(), 3)
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "independent_hardware_review_required")
        self.assertFalse(result["asterinas_gpu_verified"])

    def test_cli_invalid_bundle_is_blocked(self):
        self.host["host_kernel"] = "linux"
        with tempfile.TemporaryDirectory() as directory:
            host, guest, host_log, guest_log = self._write_bundle(directory)
            output = Path(directory) / "blocked.json"
            with patch.object(sys, "argv", [
                "acceptance.py", "--host", str(host), "--guest", str(guest),
                "--host-log", str(host_log), "--guest-log", str(guest_log),
                "--output", str(output),
            ]):
                self.assertEqual(acceptance.main(), 2)
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("not_asterinas_host", result["failed_gates"])

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

    def test_wrong_fixed_input_or_model_contract_invalidates_gpu_evidence(self):
        record = self.guest["gemm"]["child_evidence"]
        cases = {
            "input_a_sha256": "0" * 64,
            "input_b_sha256": "0" * 64,
            "dimension": [32, 16, 16],
            "test": "cpu_only",
            "compiler": "software",
            "driver_api": "fake",
        }
        for field, bad in cases.items():
            with self.subTest(field=field):
                previous = record[field]
                record[field] = bad
                self.assertIn("invalid_cuda_gemm_result", self.reasons())
                record[field] = previous

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
            original_read = os.read
            sizes = []

            def monitored_read(fd, size):
                sizes.append(size)
                if size < 0 or size > acceptance.MAX_RAW_LOG_BYTES + 1:
                    raise AssertionError("unbounded evidence read")
                return original_read(fd, size)

            with patch.object(acceptance.os, "read", monitored_read):
                self.assertEqual(acceptance.bounded_log(path), b"small fixture")
            self.assertEqual(sizes, [acceptance.MAX_RAW_LOG_BYTES + 1])

    def test_symlink_evidence_is_refused_even_when_target_regular(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real.log"
            target.write_bytes(b"legitimate data")
            link = root / "alias.log"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                acceptance.bounded_log(link)
            with self.assertRaises(OSError):
                acceptance.load_json(link)

    def test_output_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("keep", encoding="utf-8")
            link = root / "output.json"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                acceptance.write_output(link, "{}\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_fifo_log_and_manifest_refused_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            pipe = Path(directory) / "fifo"
            os.mkfifo(pipe)
            with self.assertRaises(ValueError):
                acceptance.bounded_log(pipe)
            with self.assertRaises(ValueError):
                acceptance.load_json(pipe)

    def test_duplicate_keys_are_not_valid_host_guest_manifests(self):
        for document in (
            '{"schema":"a","schema":"a"}',
            '{"guest":{"device_bdf":"0000:01:00.0","device_bdf":"0000:02:00.0"}}',
        ):
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "guest.json"
                    path.write_text(document, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                        acceptance.load_json(path)

    def test_nonfinite_json_is_not_valid_device_evidence(self):
        for nonfinite in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=nonfinite):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "guest.json"
                    path.write_text('{"temperature": ' + nonfinite + '}', encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "non-finite JSON"):
                        acceptance.load_json(path)

    def test_regular_small_manifest_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "host.json"
            p.write_text('{"schema": "test", "num": 4}', encoding="utf-8")
            self.assertEqual(acceptance.load_json(p), {"schema": "test", "num": 4})

    def test_oversized_manifest_rejected_by_fstat(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "huge.json"
            with p.open("wb") as target:
                target.seek(acceptance.MAX_MANIFEST_BYTES)
                target.write(b"x")
            with self.assertRaises(ValueError):
                acceptance.load_json(p)

    def test_truncated_file_read_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "host.json"
            p.write_bytes(b'{"schema": "valid"}')
            with patch.object(acceptance.os, "read", return_value=b'{"schema":'):
                with self.assertRaises(ValueError):
                    acceptance.load_json(p)

    def test_equal_length_inplace_rewrite_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guest.log"
            path.write_bytes(b"old-serial-log")
            original_read = os.read

            def mutate_during_read(fd, size):
                payload = original_read(fd, size)
                # Same byte count and same inode; an ordinary size-only check
                # would accept this document despite the concurrent rewrite.
                path.write_bytes(b"new-serial-log")
                record = path.stat()
                os.utime(path, ns=(record.st_atime_ns,
                                   record.st_mtime_ns + 2_000_000_000))
                return payload

            with patch.object(acceptance.os, "read", side_effect=mutate_during_read):
                with self.assertRaisesRegex(ValueError, "mutated"):
                    acceptance.bounded_log(path)

    def test_same_length_manifest_metadata_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guest.json"
            path.write_text('{"valid": true}', encoding="utf-8")
            original_read = os.read

            def update_timestamp_during_read(fd, size):
                payload = original_read(fd, size)
                stat_info = path.stat()
                os.utime(path, ns=(stat_info.st_atime_ns,
                                   stat_info.st_mtime_ns + 2_000_000_000))
                return payload

            with patch.object(acceptance.os, "read",
                              side_effect=update_timestamp_during_read):
                with self.assertRaisesRegex(ValueError, "mutated"):
                    acceptance.load_json(path)

    def test_oversized_raw_log_is_rejected_without_unbounded_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "huge.log"
            with path.open("wb") as output:
                output.seek(acceptance.MAX_RAW_LOG_BYTES)
                output.write(b"x")
            with self.assertRaises(ValueError):
                acceptance.bounded_log(path)

    def test_guest_cpu_only_does_not_count(self):
        self.guest["gemm"]["child_evidence"]["cuda_kernel_launched"] = False
        self.assertIn("invalid_cuda_gemm_result", self.reasons())

    def test_cuda_runtime_metadata_not_a_freeform_attestation(self):
        device = self.guest["gemm"]["child_evidence"]["device"]
        invalids = (
            ("device_index", -1),
            ("device_index", True),
            ("cuda_driver_api_version", 0),
            ("cuda_driver_api_version", False),
            ("nvrtc_version", "garbled"),
            ("compute_capability", "8.6"),
        )
        for field, bad in invalids:
            with self.subTest(field=field, value=bad):
                previous = device[field]
                device[field] = bad
                self.assertIn("cuda_runtime_identity_missing_or_inconsistent", self.reasons())
                device[field] = previous

    def test_forged_child_cuda_bdf_rejected(self):
        self.guest["gemm"]["child_evidence"]["device"]["device_bdf"] = "0000:04:00.0"
        self.assertIn("guest_cuda_pci_identity_mismatch", self.reasons())

    def test_host_and_guest_pci_id_mismatch(self):
        self.guest["device"]["device_id"] = "0xbeef"
        self.assertIn("physical_guest_pci_id_mismatch", self.reasons())

    def test_malformed_raw_log_types_are_rejected_without_exception(self):
        self.hostlog = "not raw bytes"
        self.guestlog = None
        reasons = self.reasons()
        self.assertIn("host_raw_log_missing", reasons)
        self.assertIn("guest_raw_log_missing", reasons)
        self.assertIn("boot_nonce_missing_from_raw_logs", reasons)

    def test_json_nonce_without_host_serial_binding_is_not_reviewable(self):
        original = b"A09_VM_NONCE=" + b"ab" * 16
        self.hostlog = self.hostlog.replace(original, b"")
        self.host["host_boot_log_sha256"] = hashlib.sha256(self.hostlog).hexdigest()
        reasons = self.reasons()
        self.assertIn("boot_nonce_missing_from_raw_logs", reasons)
        self.assertNotIn("host_raw_log_digest_mismatch", reasons)

    def test_json_nonce_without_guest_serial_binding_is_not_reviewable(self):
        original = b"A09_VM_NONCE=" + b"ab" * 16
        self.guestlog = self.guestlog.replace(original, b"")
        self.guest["guest_boot_log_sha256"] = hashlib.sha256(self.guestlog).hexdigest()
        reasons = self.reasons()
        self.assertIn("boot_nonce_missing_from_raw_logs", reasons)
        self.assertNotIn("guest_raw_log_digest_mismatch", reasons)

    def test_wrong_serial_nonce_rejected_even_when_hashes_match(self):
        original = b"A09_VM_NONCE=" + b"ab" * 16
        self.guestlog = self.guestlog.replace(original, b"A09_VM_NONCE=" + b"cd" * 16)
        self.guest["guest_boot_log_sha256"] = hashlib.sha256(self.guestlog).hexdigest()
        self.assertIn("boot_nonce_missing_from_raw_logs", self.reasons())

    def test_equal_non_nvidia_vendor_id_is_not_rtx4060_evidence(self):
        self.host["device"]["vendor_id"] = "0x1234"
        self.guest["device"]["vendor_id"] = "0x1234"
        reasons = self.reasons()
        self.assertIn("nvidia_pci_vendor_not_confirmed", reasons)
        self.assertNotIn("physical_guest_pci_id_mismatch", reasons)

    def test_wrong_gpu_model_variant_rejected_at_cross_layer_gate(self):
        device = self.guest["gemm"]["child_evidence"]["device"]
        for invalid in ("RTX 4060 Ti", "NVIDIA GeForce RTX 4070", 4060, None):
            with self.subTest(invalid=invalid):
                original = device["device_name"]
                device["device_name"] = invalid
                self.assertIn("guest_cuda_gpu_model_not_rtx4060", self.reasons())
                device["device_name"] = original

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


    def test_embedded_nonce_substring_is_not_a_serial_record(self):
        tag = b"A09_VM_NONCE=" + b"ab" * 16
        self.hostlog = self.hostlog.replace(tag + b"\n", b"prefix-" + tag + b"\n")
        self.host["host_boot_log_sha256"] = hashlib.sha256(self.hostlog).hexdigest()
        self.assertIn("boot_nonce_missing_from_raw_logs", self.reasons())

    def test_duplicate_serial_nonce_records_are_not_one_boot(self):
        tag = b"A09_VM_NONCE=" + b"ab" * 16 + b"\n"
        self.guestlog += tag
        self.guest["guest_boot_log_sha256"] = hashlib.sha256(self.guestlog).hexdigest()
        self.assertIn("boot_nonce_missing_from_raw_logs", self.reasons())

    def test_conflicting_serial_nonce_records_are_not_one_boot(self):
        self.guestlog += b"A09_VM_NONCE=" + b"cd" * 16 + b"\n"
        self.guest["guest_boot_log_sha256"] = hashlib.sha256(self.guestlog).hexdigest()
        self.assertIn("boot_nonce_missing_from_raw_logs", self.reasons())

    def test_nonce_record_with_suffix_is_rejected(self):
        tag = b"A09_VM_NONCE=" + b"ab" * 16 + b"\n"
        self.hostlog = self.hostlog.replace(tag, tag[:-1] + b"EXTRA\n")
        self.host["host_boot_log_sha256"] = hashlib.sha256(self.hostlog).hexdigest()
        self.assertIn("boot_nonce_missing_from_raw_logs", self.reasons())

    def test_output_is_immutable_and_existing_file_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "acceptance.json"
            target.write_text("previous-evidence", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                acceptance.write_output(target, "{}\n")
            self.assertEqual(target.read_text(), "previous-evidence")

    def test_output_fifo_is_not_opened_or_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            pipe = Path(directory) / "output"
            os.mkfifo(pipe)
            with self.assertRaises(OSError):
                acceptance.write_output(pipe, "{}\n")

    def test_cuda_8_digit_zero_domain_matches_4_digit_linux_guest_bdf(self):
        self.guest["gemm"]["child_evidence"]["device"]["device_bdf"] = "00000000:03:00.0"
        self.guest["gemm"]["requested_guest_bdf"] = "00000000:03:00.0"
        self.assertEqual(self.reasons(), [])  # Still manual review, never hardware PASS.

    def test_host_bdf_domain_width_normalization_is_not_device_attestation(self):
        self.host["device"]["host_bdf"] = "00000000:05:00.0"
        self.assertEqual(self.reasons(), [])  # Host and guest BDF can differ in VM.

    def test_different_numeric_pci_domain_cannot_alias_guest_gpu(self):
        child = self.guest["gemm"]["child_evidence"]["device"]
        child["device_bdf"] = "00010000:03:00.0"
        self.assertIn("guest_cuda_pci_identity_mismatch", self.reasons())
        child["device_bdf"] = "00000000:03:00.0"
        self.guest["gemm"]["requested_guest_bdf"] = "0001:03:00.0"
        self.assertIn("gemm_target_bdf_mismatch", self.reasons())

    def test_invalid_pci_slot_id_rejected_even_when_repeated(self):
        self.guest["device"]["guest_bdf"] = "0000:03:20.0"
        self.guest["gemm"]["requested_guest_bdf"] = "0000:03:20.0"
        self.guest["gemm"]["child_evidence"]["device"]["device_bdf"] = "0000:03:20.0"
        reasons = self.reasons()
        self.assertIn("guest_pci_bdf_missing", reasons)
        self.assertIn("guest_cuda_pci_identity_mismatch", reasons)



if __name__ == "__main__":
    unittest.main()
