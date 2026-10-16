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
CAPTURE_PROFILE = "osdk-native-local-tcp-gdb-capture-v2"


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


@contextmanager
def capture_fixture():
    with fixture() as item:
        item.record["profile_id"] = CAPTURE_PROFILE
        item.sidecar = item.guest / "coverage-capture.json"
        symbol_elf = item.case / "symbols.elf"
        header = bytearray(64)
        header[:7] = b"\x7fELF\x02\x01\x01"
        header[16:20] = b"\x02\x00\x3e\x00"
        symbol_elf.write_bytes(header)
        item.capture = {
            "profile_id": CAPTURE_PROFILE, "passed": True, "finalized": True,
            "gdb_exit_code": 0,
            "guest_record": "guests/guest-001/qemu.json",
            "kernel_sha256": item.record["artifacts"]["-kernel"]["sha256"],
            "serial_sha256": digest(item.serial.read_bytes()),
            "symbol_elf": {"path": str(symbol_elf), "size": len(header), "sha256": digest(header)},
            "breakpoint": {"symbol": "ostd::arch::power::try_poweroff",
                           "resolved_address": "0x8000", "actual_pc": "0x8000"},
            "announcement": {"address": "0x4000", "size": item.raw.stat().st_size},
            "raw": {"path": str(item.raw), "size": item.raw.stat().st_size,
                    "sha256": digest(item.raw.read_bytes())},
            "serial_prefix": {"size": item.serial.stat().st_size,
                              "sha256": digest(item.serial.read_bytes())},
        }
        yield item


def write_capture(item):
    item.sidecar.write_text(json.dumps(item.capture))
    item.record["capture"] = {"raw_exit_code": 0, "timed_out": False,
                              "sidecar": {"path": str(item.sidecar),
                                          "size": item.sidecar.stat().st_size,
                                          "sha256": digest(item.sidecar.read_bytes())}}


def bind_capture(item, source_path=None):
    item.record_path.write_text(json.dumps(item.record))
    return OSDK.coverage_binding(item.case, item.raw, CAPTURE_PROFILE, source_path=source_path)


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

    def test_gdb_capture_binds_sidecar_and_explicit_original_raw_source(self):
        with capture_fixture() as item:
            source = item.case / "generated/coverage.profraw"
            source.parent.mkdir()
            source.write_bytes(item.raw.read_bytes())
            item.capture["raw"]["path"] = str(source)
            write_capture(item)
            result = bind_capture(item, source_path=source)
            self.assertIs(result["passed"], True, result)
            self.assertEqual(result["kernel_sha256"], item.capture["kernel_sha256"])
            self.assertEqual(result["serial_sha256"], item.capture["serial_sha256"])
            self.assertEqual(result["raw_sha256"], item.capture["raw"]["sha256"])

    def test_gdb_capture_requires_successful_finalized_sidecar_and_recorder(self):
        for mutation in ("missing-sidecar", "missing-record", "error", "passed", "finalized",
                         "gdb_exit_code", "recorder-exit", "recorder-timeout"):
            with self.subTest(mutation=mutation), capture_fixture() as item:
                if mutation == "error":
                    item.capture["error"] = "GDB capture failed"
                elif mutation in ("passed", "finalized"):
                    item.capture[mutation] = False
                elif mutation == "gdb_exit_code":
                    item.capture[mutation] = 9
                write_capture(item)
                if mutation == "missing-sidecar":
                    item.sidecar.unlink()
                elif mutation == "missing-record":
                    del item.record["capture"]
                elif mutation == "recorder-exit":
                    item.record["capture"]["raw_exit_code"] = 9
                elif mutation == "recorder-timeout":
                    item.record["capture"]["timed_out"] = True
                self.rejected(bind_capture(item))

    def test_gdb_capture_rejects_wrong_breakpoint_and_guest_announcement(self):
        for field, value in (("symbol", "other::try_poweroff"), ("actual_pc", "0x8001"),
                             ("actual_pc", "0x0"), ("resolved_address", "0x0"),
                             ("address", "0x4001"), ("size", 1)):
            with self.subTest(field=field, value=value), capture_fixture() as item:
                section = "announcement" if field in ("address", "size") else "breakpoint"
                item.capture[section][field] = value
                write_capture(item)
                self.rejected(bind_capture(item))

    def test_gdb_capture_rejects_unrelated_artifacts_and_dump_path(self):
        for section, field, value in (
                (None, "profile_id", PROFILE), (None, "kernel_sha256", "0" * 64),
                (None, "serial_sha256", "0" * 64), (None, "guest_record", "other/qemu.json"),
                ("raw", "sha256", "0" * 64), ("raw", "size", 1),
                ("raw", "path", "/different/coverage.profraw"),
                ("serial_prefix", "sha256", "0" * 64), ("serial_prefix", "size", 1),
                ("symbol_elf", "sha256", "not-a-digest")):
            with self.subTest(section=section, field=field), capture_fixture() as item:
                target = item.capture if section is None else item.capture[section]
                target[field] = value
                write_capture(item)
                self.rejected(bind_capture(item))

    def test_gdb_capture_sidecar_must_match_recorded_size_digest_and_path(self):
        for field, value in (("sha256", "0" * 64), ("size", 1), ("path", "/other/capture.json")):
            with self.subTest(field=field), capture_fixture() as item:
                write_capture(item)
                item.record["capture"]["sidecar"][field] = value
                self.rejected(bind_capture(item))

    def test_gdb_capture_rejects_fatal_panic_even_when_all_serial_bindings_match(self):
        for marker in (b"panicked at fixture.rs:1", b"pan\x1b[31micked\x1b[0m at fixture.rs:1",
                       b"Uncaught\x1b]0;hidden\x07 panic:",
                       b"Uncaught\x1b]0;hidden\x1b\\ panic:"):
            with self.subTest(marker=marker), capture_fixture() as item:
                data = item.serial.read_bytes() + marker + b"\n"
                update_serial(item, data)
                item.capture["serial_sha256"] = digest(data)
                item.capture["serial_prefix"] = {"size": len(data), "sha256": digest(data)}
                write_capture(item)
                result = bind_capture(item)
                self.rejected(result)
                self.assertIn("fatal guest panic", result["error"])


if __name__ == "__main__":
    unittest.main()
