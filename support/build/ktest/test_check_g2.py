"""Tampered retained-log tests; inert records never assert kernel execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("g2_core_checker", HERE / "check-g2.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class G2CoreEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.guests = self.root / "aster-core/guests"
        self.guest = self.guests / "guest-0001"
        self.guest.mkdir(parents=True)
        self.project = self.root / "source"
        self.names = [*checker.original.REQUIRED_CORE_TESTS]
        self.names.extend("aster_core::inert::test_" + str(index)
                          for index in range(checker.original.MINIMUM_CORE_TESTS - len(self.names)))
        self.names.extend(checker.G2_REQUIRED_TESTS)
        self.write_serial()
        image = self.root / "ktest-trusted-initial.elf"
        image.write_bytes(b"inert compilation input, never executable")
        image.chmod(0o444)
        lock = self.guests.parent / "generated.Cargo.lock"
        lock.write_bytes(b"inert fixed lock\n")
        lock_sha = checker.digest(lock)
        (self.guests.parent / "osdk-exit-code.txt").write_text("0\n")
        self.environment = {"g2_initial_root": True, "features": ["g2-trusted-daemon"], "ktest_profile": "default",
                            "test_name": None, "vcpus": 1, "toolchain": "nightly-2026-07-21", "git_head": "a" * 40,
                            "git_status": "", "osdk_sha256": "b" * 64,
                            "build_inputs_sha256": {"support/build/ktest/locks/aster-core.Cargo.lock": lock_sha},
                            "ktest_trusted_initial": {"source_path": str(self.root / "original.elf"), "path": str(image),
                                "sha256": checker.digest(image), "bytes": image.stat().st_size, "compilation_input_only": True,
                                "native_entry_execution_claimed": False}}
        self.commands = [{"argv": ["cargo", "+nightly-2026-07-21", "osdk", "test", "--release", "--boot-method=vmm-direct",
            "--grub-boot-protocol=multiboot", "--qemu-exe=" + str(self.project / "support/build/ktest/record-qemu.py"),
            "--kcmd-args=loglevel=error", "--kcmd-args=earlycon", "--kcmd-args=console=ttyS0", "--features=g2-trusted-daemon"],
            "cwd": str(self.project / "kernel/asterinas/kernel/core"), "lock_sha256": lock_sha}]
        self.write_build()

    def write_serial(self, blocks=None, after_summary=()):
        if blocks is None:
            blocks = [(name, " ok") for name in self.names]
        count = len(blocks) + len(after_summary)
        serial = ("[ktest runner] running " + str(count) + " tests in 1 crates\n"
                  + 'running ' + str(count) + ' tests in crate "aster-core"\n'
                  + "".join("test " + name + " ..." + block + "\n" for name, block in blocks)
                  + f"test result: ok. {count} passed; 0 failed; 0 filtered out.\n"
                  + "".join("test " + name + " ..." + block + "\n" for name, block in after_summary)
                  + "[ktest runner] All crates tested.\n")
        (self.guest / "serial.log").write_text(serial)
        bios = "/usr/share/seabios/bios-256k.bin"
        kernel = str(self.root / "inert-kernel.elf")
        argv = ["qemu-system-x86_64", "-kernel", kernel, "-append", "loglevel=error earlycon console=ttyS0",
                "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", bios, "-m", "512M", "-smp", "1",
                "-nodefaults", "-no-user-config", "-no-reboot", "-nographic", "-display", "none", "-monitor", "none",
                "-serial", "chardev:serial", "-chardev", "stdio,id=serial,signal=off,logfile=" + str(self.guest / "serial.log"),
                "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
        self.qemu = {"serial_sha256": hashlib.sha256(serial.encode()).hexdigest(), "raw_exit_code": 33,
                     "timed_out": False, "crate": "aster-core", "ktest_profile": "default", "test_name": None,
                     "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max", "vcpus": 1,
                                 "memory_mib": 512, "network": False, "data_disks": False}, "argv": argv,
                     "artifacts": {option: {"path": path, "sha256": "c" * 64, "size": 100}
                                   for option, path in (("-kernel", kernel), ("-bios", bios))}}
        self.write_qemu()

    def write_qemu(self):
        (self.guest / "qemu.json").write_text(json.dumps(self.qemu))

    def write_build(self):
        (self.root / "environment.json").write_text(json.dumps(self.environment))
        (self.root / "commands.json").write_text(json.dumps(self.commands))

    def test_original_inventory_plus_root_three_and_successor_eleven_complete_tests(self):
        checker.check_build(self.guests)
        result = checker.check_guest(self.guest)
        self.assertEqual(result["passed"], checker.original.MINIMUM_CORE_TESTS + 14)
        self.assertGreaterEqual(result["passed"], 387)
        self.assertEqual(result["required_core_tests"], list(checker.original.REQUIRED_CORE_TESTS))
        self.assertGreaterEqual(len(result["required_core_tests"]), 134)
        self.assertEqual(result["required_g2_process_tests"], list(checker.G2_TESTS))
        self.assertEqual(result["g2_process_tests_exercised"], 3)
        self.assertEqual(result["required_g2_successor_tests"], list(checker.G2_SUCCESSOR_TESTS))
        self.assertEqual(result["g2_successor_tests_exercised"], 11)
        self.assertEqual(result["g2_total_additional_tests_exercised"], 14)
        self.assertFalse(result["actual_native_owner_verified"])
        self.assertFalse(result["g2_complete"])

    def test_all_three_cpu_continuity_tests_remain_mandatory_under_g2(self):
        for name in checker.CONTINUITY_TESTS:
            self.write_serial([(candidate, " ok") for candidate in self.names if candidate != name]
                              + [("aster_core::inert::replacement", " ok")])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "required core"):
                checker.check_guest(self.guest)

    def test_all_five_original_cpu_successor_tests_remain_mandatory_under_g2(self):
        for name in checker.CPU_SUCCESSOR_TESTS:
            self.write_serial([(candidate, " ok") for candidate in self.names if candidate != name]
                              + [("aster_core::inert::replacement", " ok")])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "required core"):
                checker.check_guest(self.guest)

    def test_stale_original_checker_cannot_admit_the_new_g2_inventory(self):
        original_minimum = checker.original.MINIMUM_CORE_TESTS
        original_required = checker.original.REQUIRED_CORE_TESTS
        try:
            for minimum in (365, 368, 372):
                checker.original.MINIMUM_CORE_TESTS = minimum
                with self.subTest(minimum=minimum), self.assertRaisesRegex(ValueError, "373-test core gate"):
                    checker.check_guest(self.guest)
            checker.original.MINIMUM_CORE_TESTS = original_minimum
            # The compatibility guard requires at least 134 names. With the
            # expanded current inventory, dropping one no longer crosses it.
            checker.original.REQUIRED_CORE_TESTS = original_required[:133]
            with self.assertRaisesRegex(ValueError, "373-test core gate"):
                checker.check_guest(self.guest)
            for missing in (*checker.CONTINUITY_TESTS, *checker.CPU_SUCCESSOR_TESTS):
                checker.original.REQUIRED_CORE_TESTS = tuple(
                    "aster_core::inert::replacement" if name == missing else name for name in original_required)
                with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "373-test core gate"):
                    checker.check_guest(self.guest)
        finally:
            checker.original.MINIMUM_CORE_TESTS = original_minimum
            checker.original.REQUIRED_CORE_TESTS = original_required

    def test_all_three_root_tests_remain_individually_required(self):
        for index, name in enumerate(checker.G2_TESTS):
            for replacement in ("aster_core::inert::replacement", checker.G2_TESTS[(index + 1) % 3]):
                self.write_serial([(replacement if candidate == name else candidate, " ok") for candidate in self.names])
                with self.subTest(name=name, replacement=replacement), self.assertRaisesRegex(ValueError, "missing or repeated"):
                    checker.check_guest(self.guest)

    def test_each_successor_test_cannot_be_replaced_by_an_inert_test(self):
        for name in checker.G2_SUCCESSOR_TESTS:
            self.write_serial([("aster_core::inert::replacement" if candidate == name else candidate, " ok")
                               for candidate in self.names])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "missing or repeated"):
                checker.check_guest(self.guest)

    def test_each_successor_test_cannot_be_repeated_even_with_the_same_total(self):
        inert = next(name for name in self.names if name.startswith("aster_core::inert::"))
        for name in checker.G2_SUCCESSOR_TESTS:
            self.write_serial([(candidate, " ok") for candidate in self.names if candidate != inert] + [(name, " ok")])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "missing or repeated"):
                checker.check_guest(self.guest)

    def test_each_successor_test_needs_its_own_terminal_ok_without_soft_skip(self):
        for name in checker.G2_SUCCESSOR_TESTS:
            for block in ("\n [skipped: unsupported]\n ok", "\n diagnostics only", " FAILED"):
                self.write_serial([(candidate, block if candidate == name else " ok") for candidate in self.names])
                with self.subTest(name=name, block=block), self.assertRaisesRegex(ValueError, "terminal ok"):
                    checker.check_guest(self.guest)

    def test_all_g2_test_terminals_must_precede_the_completed_summary(self):
        for name in checker.G2_REQUIRED_TESTS:
            self.write_serial([(candidate, " ok") for candidate in self.names if candidate != name],
                              after_summary=((name, " ok"),))
            with self.subTest(name=name), self.assertRaises(ValueError):
                checker.check_guest(self.guest)

    def test_whole_core_cannot_shrink_below_its_baseline_plus_fourteen(self):
        inert = next(name for name in self.names if name.startswith("aster_core::inert::"))
        self.write_serial([(name, " ok") for name in self.names if name != inert])
        with self.assertRaisesRegex(ValueError, "Root3 and successor11"):
            checker.check_guest(self.guest)

    def test_new_test_must_have_its_own_terminal_ok_and_no_soft_skip(self):
        for block in ("\n [skipped: unsupported] \n ok", "\n diagnostics only", " FAILED"):
            self.write_serial([(name, block if name == checker.G2_TESTS[0] else " ok") for name in self.names])
            with self.subTest(block=block), self.assertRaises(ValueError):
                checker.check_guest(self.guest)

    def test_original_required_test_remains_required(self):
        original_name = next(name for name in checker.original.REQUIRED_CORE_TESTS
                             if name not in (*checker.CONTINUITY_TESTS, *checker.CPU_SUCCESSOR_TESTS))
        self.write_serial([(name, " ok") for name in self.names if name != original_name]
                          + [("aster_core::inert::replacement", " ok")])
        with self.assertRaisesRegex(ValueError, "required core"):
            checker.check_guest(self.guest)

    def test_raw_serial_mutation_and_changed_machine_do_not_pass(self):
        (self.guest / "serial.log").write_bytes((self.guest / "serial.log").read_bytes() + b"tampered\n")
        with self.assertRaises(ValueError): checker.check_guest(self.guest)
        self.write_serial()
        self.qemu["argv"][self.qemu["argv"].index("-smp") + 1] = "2"
        self.write_qemu()
        with self.assertRaises(ValueError): checker.check_guest(self.guest)

    def test_actual_feature_command_filter_and_environment_all_bound(self):
        original_environment, original_commands = copy.deepcopy(self.environment), copy.deepcopy(self.commands)
        for kind in ("feature", "filter", "environment", "smp", "dirty"):
            self.environment, self.commands = copy.deepcopy(original_environment), copy.deepcopy(original_commands)
            if kind == "feature": self.commands[0]["argv"][-1] = "--features=g1d-trusted-control"
            if kind == "filter": self.commands[0]["argv"].insert(-1, "frozen_root")
            if kind == "environment": self.environment["features"] = []
            if kind == "smp": self.environment["vcpus"] = 2
            if kind == "dirty": self.environment["git_status"] = " M source.rs\n"
            self.write_build()
            with self.subTest(kind=kind), self.assertRaises(ValueError): checker.check_build(self.guests)

    def test_changed_compilation_input_or_lock_is_not_accepted(self):
        image = self.root / "ktest-trusted-initial.elf"
        image.chmod(0o600)
        image.write_bytes(b"changed")
        image.chmod(0o444)
        with self.assertRaises(ValueError): checker.check_build(self.guests)

    def test_invalid_g2_cli_combinations_fail_before_build(self):
        run = HERE / "run.py"
        for arguments in (("--crate", "ostd"), ("--permission-attr-smp",), ("--test-name", "frozen_root"), ()):
            process = subprocess.run([sys.executable, "-I", "-B", str(run), "--g2-initial-root", *arguments],
                                     capture_output=True, text=True, timeout=10, check=False)
            with self.subTest(arguments=arguments):
                self.assertEqual(process.returncode, 2)
                self.assertIn("error:", process.stderr)


if __name__ == "__main__":
    unittest.main()
