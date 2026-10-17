"""Adversarial Linux-parent CUDA worker identity checks; no device access."""
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch

import cuda_gemm
from cuda_worker_identity import validate_supervised_cuda_success


PID = 424242
BDF = "0000:01:00.0"


def supervisor_record():
    return {
        "supervisor": "linux_waitid_wnowait_killpg",
        "worker_pid": PID,
        "worker_reaped": True,
        "worker_exit_code": 0,
        "timed_out": False,
        "device_reset_verified": False,
        "effect_result_known": False,
    }


def child_success():
    a, b = cuda_gemm.inputs()
    result = cuda_gemm._base_evidence(
        cuda_gemm.reference(a, b), a, b, 30.0
    )
    result.update(
        status="passed_on_reported_cuda_environment",
        actual_output_sha256=cuda_gemm.digest(cuda_gemm.reference(a, b)),
        device_access_attempted=True,
        device_memory_allocated=True,
        cuda_kernel_launched=True,
        synchronization_completed=True,
        results_copied=True,
        resources_released=True,
        no_cpu_fallback=True,
        device={
            "device_name": "NVIDIA GeForce RTX 4060",
            "device_bdf": "00000000:01:00.0",
            "device_index": 0,
            "compute_capability": "8.9",
            "cuda_driver_api_version": 12040,
            "nvrtc_version": "12.4",
        },
    )
    for stage in result["stages"]:
        result["stages"][stage] = "not_run" if stage == "failure_recovery" else "passed"
    result["execution_provenance"].update(
        process_id=PID,
        process_executable=os.path.realpath(sys.executable),
        kernel_name="Linux",
        kernel_release=platform.release(),
        machine="x86_64",
        execution_layer="linux_worker_cuda_driver_api",
    )
    return result


class WorkerIdentityTests(unittest.TestCase):
    def check(self, child=None, receipt=None, bdf=BDF):
        return validate_supervised_cuda_success(
            child if child is not None else child_success(),
            receipt if receipt is not None else supervisor_record(),
            "RTX 4060", bdf,
        )

    def test_nominal_linux_report_is_only_consistent_not_hardware_attested(self):
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            self.skipTest("A09 reference-host-only x86_64")
        self.assertIsNone(self.check())
        self.assertFalse(child_success()["asterinas_execution_verified"])

    def test_request_without_explicit_bdf_cannot_claim_cuda_success(self):
        with self.assertRaisesRegex(ValueError, "explicit valid target"):
            self.check(bdf="")

    def test_8_digit_domain_is_accepted_without_truncating_identity(self):
        self.assertIsNone(self.check(bdf="00000000:01:00.0"))

    def test_wrong_device_and_high_pci_domain_rejected(self):
        for raw in ("0000:02:00.0", "00010000:01:00.0", "0000:01:20.0"):
            with self.subTest(raw=raw):
                child = child_success()
                child["device"]["device_bdf"] = raw
                with self.assertRaisesRegex(ValueError, "wrong CUDA PCI"):
                    self.check(child)

    def test_lookalike_gpu_models_never_match_rtx4060(self):
        for model in ("RTX 4060 Ti", "RTX 4060 Laptop GPU", "RTX 4070",
                      "Fake NVIDIA GeForce RTX 4060", None):
            with self.subTest(model=model):
                child = child_success()
                child["device"]["device_name"] = model
                with self.assertRaisesRegex(ValueError, "wrong CUDA GPU"):
                    self.check(child)

    def test_invalid_compute_capability_rejected(self):
        child = child_success()
        child["device"]["compute_capability"] = "8.6"
        with self.assertRaisesRegex(ValueError, "compute capability"):
            self.check(child)

    def test_boolean_index_and_driver_version_are_not_integers(self):
        for field in ("device_index", "cuda_driver_api_version"):
            child = child_success()
            child["device"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "driver/NVRTC"):
                self.check(child)

    def test_bad_nvrtc_version_and_out_of_range_index_rejected(self):
        for raw in ("", "NaN", "12.4.0", "0.1", None):
            child = child_success()
            child["device"]["nvrtc_version"] = raw
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "driver/NVRTC"):
                self.check(child)
        child = child_success()
        child["device"]["device_index"] = 64
        with self.assertRaisesRegex(ValueError, "driver/NVRTC"):
            self.check(child)

    def test_wrong_worker_pid_or_boolean_pid_never_qualifies(self):
        for pid in (PID + 1, 0, True):
            receipt = supervisor_record()
            receipt["worker_pid"] = pid
            with self.subTest(pid=pid), self.assertRaisesRegex(ValueError, "supervisor|worker identity"):
                self.check(receipt=receipt)

    def test_unreaped_or_failed_worker_never_qualifies(self):
        for field, value in (
            ("worker_reaped", False), ("worker_exit_code", 1),
            ("worker_exit_code", True), ("timed_out", True),
            ("supervisor", "unverified-linux-pid"),
            ("worker_identity_lost", True),
            ("worker_group_incomplete", True),
            ("worker_group_inspection_failed", True),
            ("unreaped_worker_may_remain", True),
        ):
            record = supervisor_record()
            record[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "supervisor"):
                self.check(receipt=record)

    def test_forged_process_executable_kernel_and_machine_rejected(self):
        for field, value in (
            ("process_id", PID + 5),
            ("process_id", True),
            ("process_executable", "/tmp/forged-executable"),
            ("kernel_release", "test-kernel"),
            ("kernel_name", "Asterinas"),
            ("machine", "arm64"),
            ("execution_layer", "unsupervised_cuda"),
        ):
            child = child_success()
            child["execution_provenance"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Linux worker"):
                self.check(child)

    def test_child_cannot_assert_asterinas_or_reset_authority(self):
        for field in (
            "asterinas_execution_verified", "vmm_passthrough_verified",
            "physical_device_assignment_verified",
            "reset_or_failure_recovery_verified", "failure_recovery_verified",
        ):
            child = child_success()
            child[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "host or reset"):
                self.check(child)

    def test_child_cannot_assert_nonnative_execution_layer(self):
        child = child_success()
        child["execution_provenance"]["physical_device_assignment_verified"] = True
        with self.assertRaisesRegex(ValueError, "host or reset"):
            self.check(child)

    def test_fake_completed_failure_recovery_cannot_qualify(self):
        child = child_success()
        child["stages"]["failure_recovery"] = "passed"
        with self.assertRaisesRegex(ValueError, "recovery stage"):
            self.check(child)

    def test_parent_supervisor_rejects_forged_gpu_success_from_child(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parent.json"
            child = child_success()
            child["device"]["device_name"] = "RTX 4060 Ti"

            def fake_worker(argv, _timeout):
                worker_output = Path(argv[argv.index("--output") + 1])
                worker_output.write_text(json.dumps(child), encoding="utf-8")
                return 0, supervisor_record()

            with patch.object(cuda_gemm, "timeout_available", return_value=True), \
                 patch.object(cuda_gemm.process_supervisor, "run_worker",
                              side_effect=fake_worker), \
                 patch.object(sys, "argv", ["cuda_gemm.py",
                                            "--require-bdf", BDF,
                                            "--output", str(path)]):
                exit_code = cuda_gemm.main()
            evidence = json.loads(path.read_text())
            self.assertEqual(exit_code, 1)
            self.assertEqual(evidence["status"], "failed")
            self.assertIn("wrong CUDA GPU model", evidence["error"])
            self.assertFalse(evidence["asterinas_execution_verified"])

    def test_parent_supervisor_keeps_valid_self_report_below_hardware_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "parent.json"
            child = child_success()

            def fake_worker(argv, _timeout):
                worker_output = Path(argv[argv.index("--output") + 1])
                worker_output.write_text(json.dumps(child), encoding="utf-8")
                return 0, supervisor_record()

            with patch.object(cuda_gemm, "timeout_available", return_value=True), \
                 patch.object(cuda_gemm.process_supervisor, "run_worker",
                              side_effect=fake_worker), \
                 patch.object(sys, "argv", ["cuda_gemm.py",
                                            "--require-bdf", BDF,
                                            "--output", str(path)]):
                exit_code = cuda_gemm.main()
            evidence = json.loads(path.read_text())
            self.assertEqual(exit_code, 0)  # self-reported Linux only
            self.assertEqual(evidence["status"], "passed_on_reported_cuda_environment")
            self.assertFalse(evidence["asterinas_execution_verified"])
            self.assertFalse(evidence["vmm_passthrough_verified"])
            self.assertFalse(evidence["physical_device_assignment_verified"])


if __name__ == "__main__":
    unittest.main()
