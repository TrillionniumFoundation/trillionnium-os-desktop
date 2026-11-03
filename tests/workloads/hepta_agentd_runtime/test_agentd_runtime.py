#!/usr/bin/env python3
"""Host unit regressions only: synthetic records never count as guest evidence."""
import contextlib
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest import mock

import run_agentd_runtime as gate
import prepare_inputs

NONCE = "a" * 64


def fixture_records():
    def phase(spawn, lifecycle, offset, pid):
        return {"event": "phase_observed", "observation": {
            "agent_id": gate.AGENT, "spawn_generation": spawn, "current_generation": spawn + offset,
            "health": {"lifecycle": lifecycle, "process_id": pid, "ready": lifecycle == "running", "fenced": False},
            "capabilities": [{"id": "health"}], "events": [{"lifecycle": "starting", "generation": spawn}],
        }}
    return [
        {"event": "trusted_endpoint", "evidence_class": "original_agentd_probe_in_progress_not_pass",
         "agent_id": gate.AGENT, "spawn_generation": 1, "peer_uid": 0,
         "socket_path": "/state/probe/fleet/agents/" + gate.AGENT + "/run/agentd.sock"},
        phase(1, "starting", 0, 10), phase(1, "running", 1, 10),
        {"event": "ready_window", "hold_seconds": 0}, phase(1, "draining", 2, 10),
        phase(4, "running", 1, 30), phase(4, "running", 1, 30),
        {"event": "acceptance_pass", "evidence_class": "original_agentd_process_readonly_observer",
         "old_spawn": 1, "new_spawn": 4, "checks": gate.EXPECTED_CHECKS.copy(),
         "objective_submission": False, "model_turn": False, "device_effect": False},
    ]


def encoded_records(records=None):
    return b"".join(json.dumps(record).encode() + b"\n" for record in (records or fixture_records()))


def serial(stdout=None, stderr=b"", nonce=NONCE):
    if stdout is None:
        stdout = encoded_records()
    return b"\n".join([
        b"TRILLIONNIUM_A01_INIT_BEGIN",
        f"HEPTA_RUNTIME_BEGIN nonce={nonce}".encode(),
        f"HEPTA_RUNTIME_STDOUT nonce={nonce} hex=".encode() + stdout.hex().encode(),
        f"HEPTA_RUNTIME_STDERR nonce={nonce} hex=".encode() + stderr.hex().encode(),
        f"HEPTA_RUNTIME_CHILD nonce={nonce} kind=exit code=0".encode(),
        f"HEPTA_RUNTIME_HARNESS nonce={nonce} exit=0".encode(),
        b"TRILLIONNIUM_A01_BOOT_OK", b"",
    ])


class LifecycleOracleTests(unittest.TestCase):
    def rejected(self, records):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            gate.validate_records(encoded_records(records))

    def test_complete_original_record_sequence(self):
        result, streams = gate.observe(serial(), 33, False, False, NONCE)
        self.assertEqual((result["old_pid"], result["new_pid"]), (10, 30))
        self.assertEqual(result["checks"], gate.EXPECTED_CHECKS)
        self.assertEqual(streams["stdout"], encoded_records())

    def test_exit_marker_cannot_replace_lifecycle_records(self):
        self.rejected([fixture_records()[0], fixture_records()[-1]])

    def test_missing_reordered_and_repeated_phase_fail(self):
        for variant in ("missing", "reorder", "repeat"):
            records = fixture_records()
            if variant == "missing": records.pop(4)
            if variant == "reorder": records[1], records[2] = records[2], records[1]
            if variant == "repeat": records.insert(2, copy.deepcopy(records[1]))
            with self.subTest(variant=variant): self.rejected(records)

    def test_pid_continuity_and_actual_replacement_required(self):
        for index, pid in ((2, 11), (4, 11), (5, 10), (6, 31)):
            records = fixture_records()
            records[index]["observation"]["health"]["process_id"] = pid
            with self.subTest(index=index): self.rejected(records)

    def test_generation_phase_readiness_and_identity_must_agree(self):
        for key, value in (("current_generation", 99), ("spawn_generation", True), ("agent_id", "different")):
            records = fixture_records()
            records[2]["observation"][key] = value
            with self.subTest(key=key): self.rejected(records)
        for key, value in (("ready", False), ("fenced", True), ("process_id", True), ("lifecycle", "starting")):
            records = fixture_records()
            records[2]["observation"]["health"][key] = value
            with self.subTest(key=key): self.rejected(records)
        for health in ([], None, "bad"):
            records = fixture_records()
            records[2]["observation"]["health"] = health
            with self.subTest(health=health): self.rejected(records)

    def test_generation_restart_and_starting_history_required(self):
        for variant in ("stale", "future_history", "no_history"):
            records = fixture_records()
            if variant == "stale": records[-1]["new_spawn"] = 1
            if variant == "future_history": records[5]["observation"]["events"][0]["generation"] = 5
            if variant == "no_history": records[5]["observation"]["events"] = []
            with self.subTest(variant=variant): self.rejected(records)

    def test_original_no_turn_scope_cannot_escalate(self):
        for flag in ("objective_submission", "model_turn", "device_effect"):
            for value in (True, None, 0):
                records = fixture_records()
                records[-1][flag] = value
                with self.subTest(flag=flag, value=value): self.rejected(records)
        for capability in ("objective.start", "automation.external_effect", "intelligence.canonical_v1"):
            records = fixture_records()
            records[2]["observation"]["capabilities"].append({"id": capability})
            with self.subTest(capability=capability): self.rejected(records)

    def test_only_private_registered_root_and_exact_checks(self):
        for path in ("/tmp/fleet/agentd.sock", "/state/probe/fleet/../../host.sock", "/state/probe/fleet//agentd.sock"):
            records = fixture_records()
            records[0]["socket_path"] = path
            with self.subTest(path=path): self.rejected(records)
        records = fixture_records()
        records[-1]["checks"][-1] = "fake_stop"
        self.rejected(records)

    def test_incomplete_excessive_duplicate_and_nonfinite_json_rejected(self):
        for raw in (encoded_records()[:-1], b"x" * (gate.STDOUT_LIMIT + 1),
                    b'{"event":"trusted_endpoint","event":"acceptance_pass"}\n', b'{"number":NaN}\n', b'[]\n'):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError): gate.validate_records(raw)

    def test_qemu_timeout_signal_and_output_limit_fail(self):
        for code, timeout, excessive in ((0, False, False), (-9, False, False), (33, True, False), (33, False, True)):
            with self.subTest(code=code, timeout=timeout, excessive=excessive), self.assertRaises(ValueError):
                gate.observe(serial(), code, timeout, excessive, NONCE)

    def test_nonce_exit_status_and_extra_markers_fail(self):
        cases = [serial(nonce="b" * 64), serial().replace(b"kind=exit code=0", b"kind=exit code=1"),
                 serial().replace(b"HEPTA_RUNTIME_HARNESS", b"HEPTA_RUNTIME_EXTRA"),
                 serial() + b"HEPTA_RUNTIME_CHILD nonce=forged kind=exit code=0\n",
                 serial() + b"Kernel panic\n", serial(stderr=b"fixture failure\n"),
                 serial().replace(b"TRILLIONNIUM_A01_BOOT_OK", b"not booted")]
        for index, raw in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError): gate.observe(raw, 33, False, False, NONCE)

    def test_nonzero_child_retains_diagnostics_without_passing(self):
        raw = serial(stdout=b"", stderr=b"original-agentd-probe failed: runtime unavailable\n")
        raw = raw.replace(b"kind=exit code=0", b"kind=exit code=1")
        self.assertIn(b"runtime unavailable", gate.captured_streams(raw, NONCE)["stderr"])
        with self.assertRaises(ValueError): gate.observe(raw, 33, False, False, NONCE)


class FrozenInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        binaries = {}
        for name in ("agentd", "fixture", "observer", "kernel"):
            path = self.root / name
            path.write_bytes(("unit-test identity, never executed: " + name).encode())
            binaries[name] = prepare_inputs.identity(path, name)
        receipts = {}
        for name in ("kernel", "userspace"):
            value = {"schema": "hepta.native-original-runtime-build.v1", "sources": gate.SOURCES,
                     "build_sources": {key: gate.SOURCES[key] for key in (["desktop"] if name == "kernel" else gate.SOURCES)},
                     "built": True, "source_clean": True, "commands": [["synthetic-host-unit-test"]],
                     "kernel_profile": "ordinary-os",
                     "binary_sha256": {key: binaries[key]["sha256"] for key in (["kernel"] if name == "kernel" else gate.BINARIES)}}
            path = self.root / (name + ".json")
            gate.save(path, value)
            receipts[name] = prepare_inputs.identity(path, path.name)
        self.value = {"schema": "hepta.native-original-runtime-input.v1", "sources": copy.deepcopy(gate.SOURCES),
                      "kernel_profile": "ordinary-os", "binaries": binaries, "build_receipts": receipts,
                      "source_files": gate.json_value((gate.HERE / "source-review.json").read_bytes())["source_files"]}
        self.manifest = self.root / "input.json"

    def read(self):
        gate.save(self.manifest, self.value)
        return gate.frozen_inputs(self.manifest, gate.sha(self.manifest))

    def test_freeze_binds_each_real_file_identity(self):
        value, files = self.read()
        self.assertEqual(set(files), set(gate.BINARIES) | {"kernel"})
        self.assertEqual(value["sources"], gate.SOURCES)

    def test_source_tree_or_reviewed_blob_drift_fails(self):
        for key in ("head", "tree"):
            value = copy.deepcopy(self.value)
            self.value["sources"]["hepta"][key] = "0" * 40
            with self.subTest(key=key), self.assertRaises(ValueError): self.read()
            self.value = value
        self.value["source_files"][0]["git_blob"] = "0" * 40
        with self.assertRaises(ValueError): self.read()

    def test_kernel_test_profile_is_not_runtime(self):
        self.value["kernel_profile"] = "ktest"
        with self.assertRaises(ValueError): self.read()

    def test_distinct_build_commit_requires_identical_reviewed_tree(self):
        receipt = self.root / "kernel.json"
        value = gate.json_value(receipt.read_bytes())
        value["build_sources"]["desktop"]["head"] = "a" * 40  # Synthetic alternative identity, not a historical build.
        gate.save(receipt, value)
        self.value["build_receipts"]["kernel"] = prepare_inputs.identity(receipt, receipt.name)
        self.read()
        value["build_sources"]["desktop"]["tree"] = "0" * 40
        gate.save(receipt, value)
        self.value["build_receipts"]["kernel"] = prepare_inputs.identity(receipt, receipt.name)
        with self.assertRaises(ValueError): self.read()

    def test_missing_original_fixture_and_receipt_fail(self):
        original = copy.deepcopy(self.value)
        del self.value["binaries"]["fixture"]
        with self.assertRaises(ValueError): self.read()
        self.value = original
        del self.value["build_receipts"]["userspace"]
        with self.assertRaises(ValueError): self.read()

    def test_changed_binary_and_byte_count_fail(self):
        (self.root / "agentd").write_bytes(b"different binary")
        with self.assertRaises(ValueError): self.read()
        self.value["binaries"]["agentd"] = prepare_inputs.identity(self.root / "agentd", "agentd")
        self.value["binaries"]["agentd"]["bytes"] = True
        with self.assertRaises(ValueError): self.read()

    def test_unbuilt_or_mismatched_receipt_fails(self):
        receipt = self.root / "userspace.json"
        value = gate.json_value(receipt.read_bytes())
        value["binary_sha256"]["agentd"] = "0" * 64
        gate.save(receipt, value)
        self.value["build_receipts"]["userspace"] = prepare_inputs.identity(receipt, receipt.name)
        with self.assertRaises(ValueError): self.read()

    def test_traversal_absolute_and_symlink_input_fail(self):
        record = self.value["binaries"]["agentd"].copy()
        for path in ("../agentd", str(self.root / "agentd"), "./agentd", "x//agentd", "x/../agentd"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.input_file(self.root, {**record, "path": path}, 1024)
        (self.root / "alias").symlink_to(self.root / "agentd")
        with self.assertRaises(ValueError): gate.input_file(self.root, {**record, "path": "alias"}, 1024)

    def test_kernel_receipt_rejects_unbuilt_wrong_profile_or_source(self):
        receipt = self.root / "kernel.json"
        original = gate.json_value(receipt.read_bytes())
        for key, value in (("built", False), ("source_clean", False), ("kernel_profile", "ktest"), ("commands", ["not argv"])):
            gate.save(receipt, {**original, key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                prepare_inputs.kernel_receipt(receipt, self.root / "kernel", gate.sha(receipt))


class GuestStagingTests(unittest.TestCase):
    def original_initramfs(self, extra=()):
        fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        entries = [("init", fields, b'#!/bin/sh\nset -eu\necho "TRILLIONNIUM_A01_INIT_BEGIN"\n' + gate.abi.BOOT + b'\n')]
        entries.extend((name, fields.copy(), b"") for name in extra)
        return gzip.compress(gate.cpio_codec.pack(entries), mtime=0)

    def test_initramfs_mounts_separate_payload_and_state(self):
        packed = gate.build_initramfs(self.original_initramfs(), b"unit-test launcher bytes", NONCE)
        entries = gate.cpio_codec.unpack(gzip.decompress(packed))
        init = next(data for name, _, data in entries if name == "init")
        self.assertIn(b"mount -t ext2 -o ro /dev/vda /payload", init)
        self.assertIn(b"mount -t ext2 -o rw /dev/vdb /state", init)
        self.assertIn(b"/bin/agentd-runtime-probe " + NONCE.encode(), init)
        self.assertLess(init.index(b"HEPTA_RUNTIME_HARNESS"), init.index(gate.abi.BOOT))
        self.assertEqual(len(entries), 2)

    def test_existing_state_or_duplicate_init_is_rejected(self):
        for name in ("state", "payload", "lib", "bin/agentd-runtime-probe", "init"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.build_initramfs(self.original_initramfs([name]), b"launcher", NONCE)

    def test_retained_real_initramfs_preserves_original_entries(self):
        path = gate.ROOT / "support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz"
        gate.pinned(path, gate.abi.INITRAMFS_SHA, gate.abi.LIMIT)
        original = gate.cpio_codec.unpack(gzip.decompress(path.read_bytes()))
        changed = gate.cpio_codec.unpack(gzip.decompress(gate.build_initramfs(path.read_bytes(), b"launcher", NONCE)))
        self.assertEqual(len(changed), len(original) + 1)
        self.assertEqual([entry for entry in original if entry[0].lstrip("./") != "init"],
                         [entry for entry in changed[:-1] if entry[0].lstrip("./") != "init"])

    def test_three_real_elf_closures_are_inspected_without_execution(self):
        binaries = {"agentd": Path("/bin/true"), "fixture": Path("/bin/false"), "observer": Path("/usr/bin/env")}
        with tempfile.TemporaryDirectory() as temporary:
            payload = Path(temporary)
            closure = gate.stage_closure(binaries, payload, gate.abi.tool("readelf"),
                                         [Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"), Path("/lib64")])
            self.assertEqual(set(closure["binaries"]), set(gate.BINARIES))
            self.assertIn("ld-linux-x86-64.so.2", closure["libraries"])
            self.assertEqual(gate.sha(payload / "lib64/ld-linux-x86-64.so.2"),
                             closure["libraries"]["ld-linux-x86-64.so.2"]["sha256"])

    def test_qemu_has_no_host_network_or_directory_share(self):
        args = gate.qemu_argv("/usr/bin/qemu-system-x86_64", Path("/tmp/unit-test-only"), 4096)
        self.assertEqual(args[args.index("-nic") + 1], "none")
        self.assertEqual(args[args.index("-smp") + 1], "1")
        drives = [args[index + 1] for index, value in enumerate(args) if value == "-drive"]
        self.assertEqual(len(drives), 2)
        self.assertIn("readonly=on", drives[0])
        self.assertNotIn("readonly=on", drives[1])
        self.assertFalse(any(value in args for value in ("-virtfs", "-fsdev", "-netdev", "-chardev")))

    def test_disabled_mode_creates_nothing_and_never_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            with mock.patch.object(gate.subprocess, "Popen", side_effect=AssertionError("unexpected launch")), \
                 contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(gate.main(["--output", str(output)]), 0)
            result = json.loads(capture.getvalue())
            self.assertFalse(result["executed"])
            self.assertFalse(result["passed"])
            self.assertFalse(result["f1_completed"])
            self.assertFalse(output.exists())


class BuildFailureTests(unittest.TestCase):
    def test_isolated_python_entrypoints_import_without_host_path(self):
        for name in ("prepare_inputs.py", "run_agentd_runtime.py", "import_kernel_artifact.py"):
            result = subprocess.run([sys.executable, "-I", "-B", str(gate.HERE / name), "--help"],
                                    env=gate.abi.ENV, capture_output=True, timeout=10, check=False)
            with self.subTest(name=name): self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_original_lock_and_command_rejections_are_wrapped(self):
        helper = prepare_inputs.original_helper(gate.ROOT)
        for operation in ("prepare_runner", "verify_runner_lock", "bounded_command"):
            with mock.patch.object(helper, operation, side_effect=helper.GateError("build_timeout_or_lock_refused")):
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "build_timeout_or_lock_refused"):
                    prepare_inputs.original_call(helper, operation)

    def test_original_build_failure_retains_structured_terminal_report(self):
        helper = prepare_inputs.original_helper(gate.ROOT)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            def failed_build(args, roots, out, report, source_files, receipt):
                out.mkdir()
                report["output_created"] = True
                with mock.patch.object(helper, "bounded_command", side_effect=helper.GateError("offline dependency missing")):
                    prepare_inputs.original_call(helper, "bounded_command")
            args = ["--execute", "--desktop-source", directory, "--hepta-source", directory,
                    "--kernel", directory + "/kernel", "--kernel-receipt", directory + "/receipt.json",
                    "--expected-kernel-receipt-sha256", "a" * 64, "--cargo", "/bin/false",
                    "--expected-cargo-sha256", "a" * 64, "--rustc", "/bin/false",
                    "--expected-rustc-sha256", "a" * 64, "--cargo-home", directory, "--output", str(output)]
            with mock.patch.object(prepare_inputs, "verify_sources", return_value=[]), \
                 mock.patch.object(prepare_inputs, "kernel_receipt", return_value={}), \
                 mock.patch.object(prepare_inputs, "build", side_effect=failed_build), \
                 contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(prepare_inputs.main(args), 1)
            report = json.loads(capture.getvalue())
            self.assertFalse(report["built"])
            self.assertFalse(report["runtime_executed"])
            self.assertIn("offline dependency missing", report["error"])
            self.assertEqual(json.loads((output / "preparation-result.json").read_text()), report)


if __name__ == "__main__":
    unittest.main()
