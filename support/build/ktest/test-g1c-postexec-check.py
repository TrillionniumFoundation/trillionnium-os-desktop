#!/usr/bin/env python3
"""Synthetic host regressions for the additional oracle, not kernel evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("g1c_postexec_check", HERE / "check-g1c-postexec.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class SyntheticCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.guest = self.root / "guest-001"
        self.guest.mkdir()
        self.names = list(check.original.REQUIRED_CORE_TESTS) + list(check.REQUIRED_ADDITIONAL_TESTS)
        minimum = check.original.MINIMUM_CORE_TESTS + len(check.REQUIRED_ADDITIONAL_TESTS)
        self.names += [f"aster_core::synthetic_fixture::retained_{i}" for i in range(minimum - len(self.names))]
        self.qemu = {"crate": "aster-core", "raw_exit_code": 33, "timed_out": False,
                     "ktest_profile": check.PROFILE,
                     "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                                 "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False}}
        self.write_guest()

    def write_guest(self, skipped=None, filtered=0):
        lines = [f"[ktest runner] running {len(self.names) + filtered} tests in 1 crates",
                 f'running {len(self.names) + filtered} tests in crate "aster-core"']
        lines += [f"test {name} ... " + ("[skipped: synthetic negative] " if name == skipped else "") + "ok"
                  for name in self.names]
        lines += [f"test result: ok. {len(self.names)} passed; 0 failed; {filtered} filtered out.",
                  "[ktest runner] All crates tested."]
        raw = ("\n".join(lines) + "\n").encode()
        (self.guest / "serial.log").write_bytes(raw)
        self.qemu["serial_sha256"] = hashlib.sha256(raw).hexdigest()
        (self.guest / "qemu.json").write_text(json.dumps(self.qemu))

    def reject(self):
        with self.assertRaises(ValueError):
            check.check_guest(self.guest)

    def test_complete_synthetic_record_preserves_original_and_additional_requirements(self):
        result = check.check_guest(self.guest)
        self.assertEqual(result["required_core_tests"], list(check.original.REQUIRED_CORE_TESTS))
        self.assertEqual(result["required_additional_tests"], list(check.REQUIRED_ADDITIONAL_TESTS))
        self.assertIs(result["native_sealed_launch_qualified"], False)
        self.assertIs(result["g2_qualified"], False)

    def test_missing_original_test_still_fails(self):
        self.names[0] = "aster_core::synthetic_fixture::replacement"
        self.write_guest()
        self.reject()

    def test_each_missing_additional_test_fails_even_with_same_pass_count(self):
        for name in check.REQUIRED_ADDITIONAL_TESTS:
            with self.subTest(name=name):
                index = self.names.index(name)
                self.names[index] = "aster_core::synthetic_fixture::replacement"
                self.write_guest()
                self.reject()
                self.names[index] = name

    def test_duplicated_additional_test_fails(self):
        self.names[-1] = check.REQUIRED_ADDITIONAL_TESTS[0]
        self.write_guest()
        self.reject()

    def test_soft_skipped_additional_test_fails(self):
        self.write_guest(skipped=check.REQUIRED_ADDITIONAL_TESTS[-1])
        self.reject()

    def test_retained_minimum_is_not_replaced_by_only_required_names(self):
        self.names.pop()
        self.write_guest()
        self.reject()

    def test_filtered_full_core_fails(self):
        self.write_guest(filtered=1)
        self.reject()

    def test_wrong_profile_fails(self):
        self.qemu["ktest_profile"] = "default"
        self.write_guest()
        self.reject()

    def test_two_cpu_profile_fails(self):
        self.qemu["profile"]["vcpus"] = 2
        self.write_guest()
        self.reject()

    def test_raw_failure_and_timeout_remain_failures(self):
        self.qemu["raw_exit_code"] = 1
        self.write_guest()
        self.reject()
        self.qemu["raw_exit_code"], self.qemu["timed_out"] = 33, True
        self.write_guest()
        self.reject()

    def test_changed_serial_hash_remains_a_failure(self):
        with (self.guest / "serial.log").open("ab") as stream:
            stream.write(b"changed\n")
        self.reject()

    def write_environment(self):
        # This short ELF-shaped payload tests only the recorded input identity.
        # It is never compiled, loaded, booted, or claimed as a trusted image.
        data = bytearray(64)
        data[:7], data[16:20] = b"\x7fELF\x02\x01\x01", b"\x02\x00\x3e\x00"
        embedded = self.root / "trusted-initial.elf"
        embedded.write_bytes(data)
        embedded.chmod(0o444)
        environment = {"ktest_profile": check.PROFILE, "vcpus": 1, "features": check.FEATURES,
                       "test_name": None, "toolchain": "nightly-2026-07-21", "git_status": "",
                       "git_head": "a" * 40, "source_identity": {"head": "a" * 40, "tree": "b" * 40},
                       "qualification": "kernel-object-tests-only", "native_sealed_launch_qualified": False,
                       "g2_qualified": False, "trusted_initial": {"profile": check.FEATURES[0],
                           "embedded_input": str(embedded), "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()}}
        command = ["cargo", "+nightly-2026-07-21", "osdk", "test", "--release", "--boot-method=vmm-direct",
                   "--grub-boot-protocol=multiboot", "--qemu-exe=" + str(HERE / "record-qemu.py"),
                   "--kcmd-args=loglevel=error", "--kcmd-args=earlycon", "--kcmd-args=console=ttyS0",
                   "--features=g1c-trusted-observe"]
        self.environment = environment
        self.commands = [{"argv": command, "cwd": str(self.root / "kernel/core")}]
        self.environment_path, self.commands_path = self.root / "environment.json", self.root / "commands.json"
        self.save_environment()

    def save_environment(self):
        self.environment_path.write_text(json.dumps(self.environment))
        self.commands_path.write_text(json.dumps(self.commands))

    def test_exact_recorded_feature_and_frozen_input_are_required(self):
        self.write_environment()
        check.check_environment(self.environment_path, self.commands_path)
        self.environment["features"] = []
        self.save_environment()
        with self.assertRaises(ValueError):
            check.check_environment(self.environment_path, self.commands_path)

    def test_command_filter_cannot_be_hidden_by_an_empty_environment_filter(self):
        self.write_environment()
        self.commands[0]["argv"].append("postexec_observe")
        self.save_environment()
        with self.assertRaises(ValueError):
            check.check_environment(self.environment_path, self.commands_path)

    def test_changed_frozen_input_is_rejected(self):
        self.write_environment()
        embedded = self.root / "trusted-initial.elf"
        embedded.chmod(0o644)
        embedded.write_bytes(b"changed")
        embedded.chmod(0o444)
        with self.assertRaises(ValueError):
            check.check_environment(self.environment_path, self.commands_path)

    def test_dirty_or_production_claiming_evidence_is_rejected(self):
        self.write_environment()
        for key, value in (("git_status", " M kernel.rs\n"), ("g2_qualified", True)):
            with self.subTest(key=key):
                previous = self.environment[key]
                self.environment[key] = value
                self.save_environment()
                with self.assertRaises(ValueError):
                    check.check_environment(self.environment_path, self.commands_path)
                self.environment[key] = previous

    def test_runner_rejects_filter_and_smp_before_any_build(self):
        for option in (["--test-name", "postexec_observe"], ["--permission-attr-smp"]):
            result = subprocess.run([sys.executable, "-I", str(HERE / "run.py"),
                                     "--g1c-postexec-observe", "--trusted-initial-elf", "/not-opened", *option],
                                    capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"complete aster-core suite", result.stderr)


if __name__ == "__main__":
    unittest.main()
