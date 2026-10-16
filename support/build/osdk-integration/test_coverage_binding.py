"""Bind captured coverage bytes to one recorded guest, without running LLVM or QEMU."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("a01_osdk_coverage_adapter", HERE / "osdk.py")
OSDK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OSDK)
PROFILE = "osdk-native-local-tcp-v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as temporary:
        case = Path(temporary)
        guest = case / "guests/guest-001"
        guest.mkdir(parents=True)
        raw = case / "coverage.profraw"
        raw.write_bytes(b"fixture-profile-raw")
        kernel = case / "kernel.elf"
        kernel.write_bytes(b"fixture-kernel-identity")
        serial = guest / "serial.log"
        serial.write_bytes(b"[kernel] fixture started\n#### Coverage: 0x4000 "
                           + str(raw.stat().st_size).encode() + b"\n")
        record = {
            "profile_id": PROFILE,
            "timed_out": False,
            "raw_exit_code": 33,
            "argv": ["qemu-system-x86_64", "-kernel", str(kernel)],
            "artifacts": {"-kernel": {"path": str(kernel), "size": kernel.stat().st_size,
                                        "sha256": digest(kernel.read_bytes())}},
            "serial_logs": [{"path": str(serial), "size": serial.stat().st_size,
                             "sha256": digest(serial.read_bytes())}],
        }
        yield SimpleNamespace(case=case, guest=guest, raw=raw, serial=serial,
                              record=record, record_path=guest / "qemu.json")


def bind(item):
    item.record_path.write_text(json.dumps(item.record))
    return OSDK.coverage_binding(item.case, item.raw, PROFILE)


def update_serial(item, data):
    item.serial.write_bytes(data)
    item.record["serial_logs"][0].update(size=len(data), sha256=digest(data))


class CoverageBindingTests(unittest.TestCase):
    def rejected(self, result):
        self.assertIs(result["passed"], False)
        self.assertTrue(result.get("error"), result)

    def test_one_guest_binds_kernel_serial_and_announced_raw_size(self):
        with fixture() as item:
            result = bind(item)
            self.assertIs(result["passed"], True, result)
            self.assertEqual(result["guest_record"], "guests/guest-001/qemu.json")
            self.assertEqual(result["kernel_sha256"], item.record["artifacts"]["-kernel"]["sha256"])
            self.assertEqual(result["serial_sha256"], digest(item.serial.read_bytes()))
            self.assertEqual(result["raw_sha256"], digest(item.raw.read_bytes()))
            self.assertEqual(result["announcement"], {"address": "0x4000", "size": item.raw.stat().st_size})

    def test_mutated_serial_cannot_reuse_previous_record(self):
        for mutation in (lambda data: data.replace(b"started", b"changed"),
                         lambda data: data + b"another run\n", lambda data: b""):
            with self.subTest(mutation=mutation), fixture() as item:
                item.serial.write_bytes(mutation(item.serial.read_bytes()))
                self.rejected(bind(item))

    def test_missing_raw_or_size_different_from_guest_is_rejected(self):
        for missing in (False, True):
            with self.subTest(missing=missing), fixture() as item:
                if missing:
                    item.raw.unlink()
                else:
                    item.raw.write_bytes(b"wrong-length")
                self.rejected(bind(item))

    def test_profile_must_identify_this_execution(self):
        with fixture() as item:
            item.record["profile_id"] = "osdk-native-unix-v1"
            self.rejected(bind(item))

    def test_coverage_announcement_is_unique_and_nonzero(self):
        for announcement in (b"", b"#### Coverage: 0x4000 19\n" * 2,
                             b"#### Coverage: 0x0 19\n", b"#### Coverage: 0x4000 0\n",
                             b"prefix #### Coverage: 0x4000 19\n"):
            with self.subTest(announcement=announcement), fixture() as item:
                update_serial(item, b"[kernel] fixture started\n" + announcement)
                self.rejected(bind(item))

    def test_actual_kernel_requires_a_recorded_digest(self):
        for missing_artifact in (False, True):
            with self.subTest(missing_artifact=missing_artifact), fixture() as item:
                if missing_artifact:
                    del item.record["artifacts"]["-kernel"]
                else:
                    del item.record["artifacts"]["-kernel"]["sha256"]
                self.rejected(bind(item))

    def test_guest_record_must_be_unique(self):
        for count in (0, 2):
            with self.subTest(count=count), fixture() as item:
                item.record_path.write_text(json.dumps(item.record))
                if count == 0:
                    item.record_path.unlink()
                else:
                    other = item.case / "guests/guest-002"
                    other.mkdir()
                    (other / "qemu.json").write_text(json.dumps(item.record))
                self.rejected(OSDK.coverage_binding(item.case, item.raw, PROFILE))

    def test_incomplete_or_failed_record_is_rejected(self):
        for failure in ({"timed_out": True}, {"error": "QEMU recorder failed"},
                        {"stream_errors": ["serial write failed"]}):
            with self.subTest(failure=failure), fixture() as item:
                item.record.update(failure)
                self.rejected(bind(item))

    def test_serial_identity_requires_one_matching_snapshot(self):
        for mutation in ("missing", "missing-file", "multiple", "sha256", "size"):
            with self.subTest(mutation=mutation), fixture() as item:
                if mutation == "missing":
                    item.record["serial_logs"] = []
                elif mutation == "missing-file":
                    item.serial.unlink()
                elif mutation == "multiple":
                    item.record["serial_logs"] *= 2
                elif mutation == "sha256":
                    item.record["serial_logs"][0]["sha256"] = "0" * 64
                else:
                    item.record["serial_logs"][0]["size"] += 1
                self.rejected(bind(item))

    def test_failed_osdk_cannot_pass_with_valid_new_coverage_and_llvm(self):
        with fixture() as item:
            workspace = item.case / "generated"
            workspace.mkdir()
            serial = item.serial.read_bytes()
            item.serial.unlink()
            llvm = "/fixture/toolchain/lib/rustlib/x86_64-unknown-linux-gnu/bin/llvm-profdata"
            environment = {"A01_REAL_OSDK": "/fixture/osdk",
                           "A01_REAL_CARGO": "/fixture/toolchain/bin/cargo",
                           "A01_OSDK_CASE_OUTPUT": str(item.case),
                           "A01_OSDK_LOCAL_TCP": "1", "A01_OSDK_PROFILE": PROFILE}
            commands = []

            def run(arguments, **options):
                commands.append(arguments)
                if arguments[0] == environment["A01_REAL_OSDK"]:
                    (workspace / "coverage.profraw").write_bytes(item.raw.read_bytes())
                    item.serial.write_bytes(serial)
                    item.record_path.write_text(json.dumps(item.record))
                    return SimpleNamespace(returncode=9)
                self.assertEqual(arguments[0], llvm)
                self.assertEqual(options["timeout"], 30)
                if arguments[1] == "merge":
                    Path(arguments[-1]).write_bytes(b"fixture-merged-profile")
                else:
                    self.assertEqual(arguments[1], "show")
                    options["stdout"].write(b"Total functions: 7\nMaximum function count: 3\n")
                return SimpleNamespace(returncode=0)

            with patch.dict(OSDK.os.environ, environment, clear=True), \
                    patch.object(OSDK.Path, "cwd", return_value=workspace), \
                    patch.object(OSDK.sys, "argv", ["osdk.py", "osdk", "run", "--coverage"]), \
                    patch.object(OSDK.subprocess, "run", side_effect=run):
                self.assertEqual(OSDK.main(), 9)
            result = json.loads((item.case / "coverage/result.json").read_text())
            self.assertEqual(len(commands), 3)
            self.assertIs(result["source_preexisted"], False)
            self.assertIs(result["guest_binding"]["passed"], True)
            self.assertEqual([step["raw_exit_code"] for step in result["commands"]], [0, 0])
            self.assertEqual((result["total_functions"], result["maximum_function_count"]), (7, 3))
            self.assertIs(result["passed"], False)
            self.assertEqual(result["source_osdk_exit_code"], 9)


if __name__ == "__main__":
    unittest.main()
