#!/usr/bin/env python3
"""Host oracle regressions. Synthetic records are never execution evidence."""
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import prepare_inputs as build
import run_host as host
import run_native as native

NONCE = "a" * 64


def sample():
    def receipt(variant, revision):
        source = {"source_id": "source:v1:" + str(revision) * 64, "revision": 1}
        content = f"Inert store compatibility fixture revision {variant}."
        return {"source": source, "memory": {
            "id": {"memory_id": "memory:v2:" + "a" * 64, "revision": revision},
            "scope": {"scope": "agent_private"}, "content": content,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "verification": "verified",
            "lifecycle": {"state": "active"}, "valid_from_unix_seconds": 100,
            "valid_to_unix_seconds": None, "supersedes_revision": None if revision == 1 else 1,
            "citations": [source]}, "projection": {"generation": revision, "entity_count": 2,
            "relation_count": 1, "node_count": 2, "edge_count": 1,
            **dict.fromkeys(("fact_set_sha256", "input_heads_sha256", "output_sha256", "generation_sha256", "publication_sha256"), "b" * 64)}}
    anchor = {"profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": host.AGENT,
              "schema_digest": "c" * 64, "state_digest": "d" * 64}
    return {"event": "acceptance_pass", "schema": "hepta.original-cognitive-store-process-crash.v1",
            "evidence_class": "legacy_original_store_wal_process_crash_reopen", "checks": host.CHECKS.copy(),
            "agent_id": host.AGENT, "wal_bytes_before_kill": 4096, "killed_signal": 9,
            "seed_receipt": receipt("seed", 1), "seed_anchor": anchor,
            "cas_results": [{"event": "cas_result", "variant": "a", "outcome": "committed", "receipt": receipt("a", 2)},
                            {"event": "cas_result", "variant": "b", "outcome": "conflict"}],
            "final_anchor": {**anchor, "state_digest": "e" * 64}, **dict.fromkeys(host.FALSE_FLAGS, False)}


def encoded(value):
    return json.dumps(value).encode() + b"\n"


def serial(value=None, nonce=NONCE):
    raw = encoded(sample() if value is None else value)
    return b"\n".join([b"TRILLIONNIUM_A01_INIT_BEGIN", f"HEPTA_RUNTIME_BEGIN nonce={nonce}".encode(),
        f"HEPTA_RUNTIME_STDOUT nonce={nonce} hex=".encode() + raw.hex().encode(),
        f"HEPTA_RUNTIME_STDERR nonce={nonce} hex=".encode(),
        f"HEPTA_RUNTIME_CHILD nonce={nonce} kind=exit code=0".encode(),
        f"HEPTA_RUNTIME_HARNESS nonce={nonce} exit=0".encode(), b"TRILLIONNIUM_A01_BOOT_OK", b""])


class StoreOracleTests(unittest.TestCase):
    def rejected(self, value):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            host.validate_record(encoded(value))

    def test_full_record_only_checks_oracle(self):
        self.assertEqual(host.validate_record(encoded(sample()))["checks"], host.CHECKS)

    def test_either_contender_can_win(self):
        value = sample()
        a, b = value["cas_results"]
        b["outcome"], b["receipt"] = "committed", a.pop("receipt")
        b["receipt"]["memory"]["content"] = "Inert store compatibility fixture revision b."
        b["receipt"]["memory"]["content_sha256"] = hashlib.sha256(b["receipt"]["memory"]["content"].encode()).hexdigest()
        a["outcome"] = "conflict"
        host.validate_record(encoded(value))

    def test_missing_reordered_repeated_check_rejected(self):
        for operation in ("missing", "reordered", "repeated"):
            value = sample()
            if operation == "missing": value["checks"].pop()
            if operation == "reordered": value["checks"].reverse()
            if operation == "repeated": value["checks"].append(value["checks"][0])
            with self.subTest(operation=operation): self.rejected(value)

    def test_scope_cannot_be_promoted(self):
        for flag in host.FALSE_FLAGS:
            for bad in (True, None, 0):
                value = sample()
                value[flag] = bad
                with self.subTest(flag=flag, bad=bad): self.rejected(value)

    def test_real_kill_and_live_wal_required(self):
        for key, bad in (("killed_signal", 15), ("killed_signal", True), ("wal_bytes_before_kill", 0), ("wal_bytes_before_kill", True)):
            value = sample()
            value[key] = bad
            with self.subTest(key=key, bad=bad): self.rejected(value)

    def test_two_commits_two_conflicts_and_fabricated_loser_receipt_rejected(self):
        for mode in ("two_commits", "two_conflicts", "loser_receipt"):
            value = sample()
            a, b = value["cas_results"]
            if mode == "two_commits": b.update(outcome="committed", receipt=a["receipt"])
            if mode == "two_conflicts": a["outcome"] = "conflict"
            if mode == "loser_receipt": b["receipt"] = a["receipt"]
            with self.subTest(mode=mode): self.rejected(value)

    def test_memory_identity_citation_content_and_revision_bound(self):
        for mode in ("memory_id", "revision", "citations", "content", "digest", "scope", "supersedes"):
            value = sample()
            memory = value["cas_results"][0]["receipt"]["memory"]
            if mode == "memory_id": memory["id"]["memory_id"] = "memory:v2:" + "f" * 64
            if mode == "revision": memory["id"]["revision"] = True
            if mode == "citations": memory["citations"] = []
            if mode == "content": memory["content"] = "different"
            if mode == "digest": memory["content_sha256"] = "f" * 64
            if mode == "scope": memory["scope"] = {"scope": "shared"}
            if mode == "supersedes": memory["supersedes_revision"] = 0
            with self.subTest(mode=mode): self.rejected(value)

    def test_atomic_kg_counts_hashes_and_generation_required(self):
        for key, bad in (("entity_count", 0), ("relation_count", True), ("output_sha256", "x"), ("generation", 1)):
            value = sample()
            value["cas_results"][0]["receipt"]["projection"][key] = bad
            with self.subTest(key=key): self.rejected(value)

    def test_unchanged_cut_wrong_owner_schema_and_extra_anchor_field_rejected(self):
        for mode in ("unchanged", "owner", "schema", "extra"):
            value = sample()
            anchor = value["final_anchor"]
            if mode == "unchanged": anchor["state_digest"] = value["seed_anchor"]["state_digest"]
            if mode == "owner": anchor["owner_agent_id"] = "other"
            if mode == "schema": anchor["schema_digest"] = "f" * 64
            if mode == "extra": anchor["authority"] = True
            with self.subTest(mode=mode): self.rejected(value)

    def test_duplicate_json_nonfinite_truncated_and_multiple_records_rejected(self):
        raw = encoded(sample())
        for invalid in (raw.rstrip(), raw + raw, raw.replace(b'"killed_signal": 9', b'"killed_signal": 9,"killed_signal":9'),
                        raw.replace(b'"killed_signal": 9', b'"killed_signal": NaN')):
            with self.subTest(raw=invalid[:32]), self.assertRaises(ValueError): host.validate_record(invalid)

    def test_serial_requires_actual_bounded_boot_and_exact_nonce(self):
        native.observe(serial(), 33, False, False, NONCE)
        for code, timed, excessive, nonce in ((1, False, False, NONCE), (33, True, False, NONCE),
                                              (33, False, True, NONCE), (33, False, False, "b" * 64)):
            with self.subTest(code=code, timed=timed, excessive=excessive), self.assertRaises(ValueError):
                native.observe(serial(), code, timed, excessive, nonce)

    def test_serial_exit_markers_cannot_replace_store_receipt(self):
        raw = serial().replace(encoded(sample()).hex().encode(), b"")
        with self.assertRaises(ValueError): native.observe(raw, 33, False, False, NONCE)

    def test_serial_repeated_stream_boot_and_stderr_rejected(self):
        raw = serial()
        for invalid in (raw + b"TRILLIONNIUM_A01_BOOT_OK\n", raw + f"HEPTA_RUNTIME_BEGIN nonce={NONCE}\n".encode(),
                        raw.replace(f"HEPTA_RUNTIME_STDERR nonce={NONCE} hex=".encode(),
                                    f"HEPTA_RUNTIME_STDERR nonce={NONCE} hex=6572726f72".encode())):
            with self.assertRaises(ValueError): native.observe(invalid, 33, False, False, NONCE)


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("gcc") is None:
            raise unittest.SkipTest("gcc is required for the real C emitter regression")
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        source = (Path(__file__).parent / "store_runtime_probe.c").resolve()
        text = '#define main original_launcher_main\n#include ' + json.dumps(str(source)) + '\n#undef main\n'
        text += 'int main(int argc, char **argv) { if (argc != 3) return 2; return emit("STDOUT", argv[1], "' + NONCE + '", strtoul(argv[2], NULL, 10)) == 0 ? 0 : 1; }\n'
        (cls.root / "probe.c").write_text(text)
        cls.binary = cls.root / "probe"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(cls.root / "probe.c"),
                        "-o", str(cls.binary)], check=True, capture_output=True, timeout=30)
        # Asterinas's serial TTY may correctly return a short write. Force
        # 127-byte writes against the same real C emitter to cover that path.
        partial = '#define _GNU_SOURCE\n#include <unistd.h>\nstatic ssize_t short_write(int fd, const void *data, size_t len);\n#define write short_write\n'
        partial += text + '\n#undef write\nstatic ssize_t short_write(int fd, const void *data, size_t len) { return write(fd, data, len > 127 ? 127 : len); }\n'
        (cls.root / "partial.c").write_text(partial)
        cls.partial_binary = cls.root / "partial"
        subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(cls.root / "partial.c"),
                        "-o", str(cls.partial_binary)], check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_record_spanning_multiple_reads_is_one_complete_hex_line(self):
        content = bytes(range(256)) * 33
        source = self.root / "multi-read"
        source.write_bytes(content)
        for binary in (self.binary, self.partial_binary):
            result = subprocess.run([str(binary), str(source), str(len(content))], capture_output=True, timeout=10)
            with self.subTest(binary=binary.name):
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, f"HEPTA_RUNTIME_STDOUT nonce={NONCE} hex=".encode() + content.hex().encode() + b"\n")
                self.assertEqual(result.stderr, b"")

    def test_oversized_file_has_no_partial_record(self):
        source = self.root / "oversized"
        source.write_bytes(b"ordinary bounded diagnostic")
        result = subprocess.run([str(self.binary), str(source), "4"], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")

    def test_store_guest_keeps_warning_logs_and_exact_boot_contract(self):
        argv = native.qemu_argv("qemu", Path("/ordinary-fixture"), 4096)
        boot = argv[argv.index("-append") + 1]
        self.assertIn("loglevel=warn", boot.split())
        self.assertNotIn("loglevel=info", boot.split())
        for boot in ("unknown --", "loglevel=info --", "loglevel=debug --", "loglevel=warn loglevel=warn --",
                     "loglevel=warn loglevel=info --"):
            with self.subTest(boot=boot), mock.patch.object(native.runtime, "qemu_argv", return_value=["qemu", "-append", boot]):
                with self.assertRaises(ValueError): native.qemu_argv("qemu", Path("/ordinary-fixture"), 4096)


class KernelReceiptTests(unittest.TestCase):
    def test_actual_build_source_and_profile_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = root / "kernel"
            kernel.write_bytes(b"bounded kernel bytes")
            receipt = {"schema": "hepta.native-original-runtime-build.v1", "built": True, "source_clean": True,
                       "kernel_profile": "ordinary-os", "build_sources": {"desktop": {"head": "a" * 40, "tree": "b" * 40}},
                       "binary_sha256": {"kernel": host.sha(kernel)}, "commands": [["make", "build"]]}
            path = root / "receipt.json"
            for mode in ("valid", "ktest", "dirty", "wrong_tree", "wrong_kernel"):
                value = copy.deepcopy(receipt)
                if mode == "ktest": value["kernel_profile"] = "ktest"
                if mode == "dirty": value["source_clean"] = False
                if mode == "wrong_tree": value["build_sources"]["desktop"]["tree"] = "c" * 40
                if mode == "wrong_kernel": value["binary_sha256"]["kernel"] = "f" * 64
                path.write_bytes(encoded(value))
                with self.subTest(mode=mode):
                    if mode == "valid": native.kernel_input(kernel, path, host.sha(path), "b" * 40)
                    else:
                        with self.assertRaises(ValueError): native.kernel_input(kernel, path, host.sha(path), "b" * 40)


class PreparationTests(unittest.TestCase):
    def test_dependent_original_package_identity_cannot_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, runner = root / "source", root / "runner"
            (source / "codex-rs").mkdir(parents=True)
            runner.mkdir()
            origin = build.HELPER.UNUSED_PATCH_ORIGIN
            target = {"git": "https://example.invalid/fixed", "rev": "a" * 40}
            omission = {"origin": origin, "package": "unused", "target": target}
            target_source = f'git+{target["git"]}?rev={target["rev"]}#{target["rev"]}'
            original = '\n'.join(['[[package]]', 'name="dependency"', 'version="1.0.0"', 'source="registry+test"', 'checksum="first"',
                                  '[[package]]', 'name="unused"', 'version="1.0.0"', 'source=' + json.dumps(target_source)]) + '\n'
            (source / "codex-rs/Cargo.lock").write_text(original)
            (source / "codex-rs/Cargo.toml").write_text("")
            valid = original.split('[[package]]\nname="unused"')[0] + f'[[package]]\nname="{build.NAME}"\nversion="0.0.0"\n' + '[patch]\n[[patch.unused]]\nname="unused"\nversion="1.0.0"\nsource=' + json.dumps(target_source) + '\n'
            with mock.patch.object(build.HELPER, "runner_patch_omission", return_value=omission):
                for mode in ("valid", "version", "source", "checksum", "root", "active_alias", "missing_unused"):
                    text = valid
                    if mode == "version": text = text.replace('name="dependency"\nversion="1.0.0"', 'name="dependency"\nversion="2.0.0"')
                    if mode == "source": text = text.replace('registry+test', 'registry+different')
                    if mode == "checksum": text = text.replace('checksum="first"', 'checksum="different"')
                    if mode == "root": text = text.replace(build.NAME, "other-root")
                    if mode == "active_alias": text = original + valid[valid.index('[[package]]\nname="' + build.NAME):]
                    if mode == "missing_unused": text = valid.split('[patch]')[0]
                    (runner / "Cargo.lock").write_text(text)
                    with self.subTest(mode=mode):
                        if mode == "valid": build.verify_lock(source, runner)
                        else:
                            with self.assertRaises(ValueError): build.verify_lock(source, runner)


if __name__ == "__main__":
    unittest.main()
