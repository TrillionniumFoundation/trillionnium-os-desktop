"""Image-selection/rejection regressions; no kernel or original-owner execution."""

from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import build_original_entry as builder
import native_owner_evidence as oracle
import native_owner_inputs as inputs
import run_native_owner as runner
from test_native_owner_evidence import ELF, NONCE, InertRecords

spec = importlib.util.spec_from_file_location("tested_original_owner_image", ROOT / "support/build/original_owner_image.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class OriginalOwnerImageProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="original-image-profile-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def document(self, name, value):
        path = self.directory / name
        data = (json.dumps(value, sort_keys=True) + "\n").encode()
        path.write_bytes(data)
        return path, hashlib.sha256(data).hexdigest()

    def review(self):
        value = profile.descriptor()
        return {"schema": "hepta.original-owner-image-source-review.v1",
                "desktop": {"head": "ab" * 20, "tree": "cd" * 20},
                "hepta": value["hepta"], "entry": value["entry"],
                "userspace_toolchain": value["userspace_toolchain"],
                "scope": "Schema unit check only; no execution or source snapshot is asserted.",
                "image_profile": profile.PROFILE,
                "image_profile_descriptor_sha256": profile.DESCRIPTOR_SHA256}

    def test_source_review_requires_fixed_image_version_and_original_source(self):
        value = self.review()
        path, digest = self.document("review.json", value)
        self.assertEqual(inputs.review_inputs(path, digest, profile.PROFILE), value)
        for name, changed in (
            ("unreviewed-source", {"hepta": {"head": "01" * 20, "tree": "02" * 20}}),
            ("foreign-profile", {"image_profile": inputs.PROFILE}),
            ("foreign-descriptor", {"image_profile_descriptor_sha256": "00" * 32}),
            ("caller-budget", {"max_file_bytes": 32 * 1024**2}),
        ):
            with self.subTest(name=name):
                candidate = copy.deepcopy(value)
                candidate.update(changed)
                path, digest = self.document(name + ".json", candidate)
                with self.assertRaises(ValueError):
                    inputs.review_inputs(path, digest, profile.PROFILE)

    def test_old_source_review_consumer_rejects_new_schema(self):
        path, digest = self.document("new-review.json", self.review())
        with self.assertRaises(ValueError):
            inputs.review_inputs(path, digest)

    def test_build_receipts_cannot_cross_the_image_profile_boundary(self):
        cases = ((profile.BUILD_SCHEMA, inputs.PROFILE),
                 ("hepta.original-native-entry-build.v1", profile.PROFILE))
        for index, (schema, selected) in enumerate(cases):
            path, digest = self.document(str(index) + ".json", {"schema": schema})
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, "build receipt"):
                inputs.owner_build(path, digest, self.directory / "not-opened.elf", {}, {}, None,
                                   self.directory, selected)

    def test_same_length_unreviewed_data_cannot_pass_digest_admission(self):
        # Inert bytes exercise only the host digest refusal; never executable.
        content = bytes(profile.descriptor()["image"]["file_bytes"])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            profile.inspect_elf(content)
        with self.assertRaisesRegex(ValueError, "unknown"):
            inputs.owner_file_limit("33554432")

    def test_freezer_refuses_an_unrelated_normal_elf_without_source_bytecode(self):
        source = Path(shutil.which("true")).resolve(strict=True)
        cache = ROOT / "support/build/__pycache__"

        def cached_inputs():
            return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in cache.glob("original_owner_image.*")}

        before = cached_inputs()
        output, manifest = self.directory / "owner.elf", self.directory / "owner.json"
        result = subprocess.run(
            [sys.executable, str(ROOT / "support/build/prepare-trusted-image.py"),
             "--profile", profile.PROFILE, "--input", str(source), "--output", str(output),
             "--manifest", str(manifest)], env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            capture_output=True, text=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact file length", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())
        self.assertEqual(cached_inputs(), before)

    def test_new_flag_reaches_osdk_once_and_cannot_mix_with_legacy_selectors(self):
        common = ["make", "--no-print-directory", "-f", str(ROOT / "support/build/minimal.mk"),
                  "CARGO_OSDK=unused-by-flag-inspection", "HEPTA_G2_ORIGINAL_OWNER_A39_V1=1"]
        inspect = ["--eval=show-image-flags:;@printf '%s\\n' '$(CARGO_OSDK_BUILD_ARGS)'", "show-image-flags"]
        result = subprocess.run(common + inspect, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([arg for arg in result.stdout.split() if arg.startswith("--features=")],
                         ["--features=" + profile.PROFILE])
        for old in ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "HEPTA_G2_TRUSTED_DAEMON"):
            with self.subTest(old=old):
                result = subprocess.run(common + [old + "=1"] + inspect,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("select at most one", result.stderr)

    def test_disabled_build_and_runtime_do_not_claim_legacy_or_native_success(self):
        args = ["--desktop-source", str(ROOT), "--desktop-head", "ab" * 20, "--desktop-tree", "cd" * 20,
                "--hepta-source", str(self.directory), "--hepta-head", "ef" * 20, "--hepta-tree", "12" * 20,
                "--entry", "hepta-g2-native-owner", "--toolchain-bin", str(self.directory),
                "--cargo-home", str(self.directory), "--target-cache", str(self.directory),
                "--output", str(self.directory / "not-created"), "--image-profile", profile.PROFILE]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(builder.main(args), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["schema"], profile.BUILD_SCHEMA)
        self.assertFalse(value["image_profile_passed"])
        self.assertFalse(value["legacy_static_profile_passed"])
        self.assertNotIn("static_profile_passed", value)
        self.assertNotIn("limits_changed", value)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(runner.main(["--image-profile", profile.PROFILE]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["schema"], profile.RUNTIME_SCHEMA)
        for key in ("passed", "native_execution_attempted", "whole_guest_peak_verified",
                    "global_memory_reserve", "legacy_static_profile_passed", "g2_complete"):
            self.assertFalse(value[key])
        self.assertFalse((self.directory / "not-created").exists())

    def test_legacy_oracle_rejects_the_new_profile_marker(self):
        # Reuse original inert parser records, never a native-owner receipt.
        records = InertRecords(oracle.SCENARIOS[0])
        raw = profile.kernel_selection_record().encode() + b"\n" + records.raw()
        with self.assertRaisesRegex(ValueError, "unknown kernel G2"):
            oracle.evaluate(raw, 33, False, False, records.scenario, NONCE, ELF)
        with self.assertRaisesRegex(ValueError, "another original ELF"):
            oracle.evaluate(raw, 33, False, False, records.scenario, NONCE, ELF, profile.PROFILE)

    def test_inert_new_profile_records_include_finite_memory_without_legacy_credit(self):
        # This joins parser fixtures only; it does not produce guest evidence.
        from test_native_owner_memory import Lifecycle

        image = profile.descriptor()["image"]
        elf = {"bytes": image["file_bytes"], "sha256": image["sha256"], "entry": ELF["entry"]}
        for scenario in oracle.SCENARIOS:
            with self.subTest(scenario=scenario):
                records = InertRecords(scenario)
                lifecycle = Lifecycle()
                lines = lifecycle.lines[:lifecycle.event]
                original = records.raw().decode().splitlines()
                for index in lifecycle.images:
                    lines[index] = (f"[hepta-g2] trusted initial image committed: bytes={elf['bytes']} "
                                    f"entry={elf['entry']:#x}")
                lines[lifecycle.activation] = original[4]
                lines.insert(1, profile.kernel_selection_record())
                raw = ("\n".join(lines + original[5:]) + "\n").encode()
                result = oracle.evaluate(raw, 33, False, False, scenario, NONCE, elf, profile.PROFILE)
                self.assertTrue(result["passed"])
                self.assertFalse(result["legacy_static_profile_passed"])
                self.assertFalse(result["g2_complete"])
                memory = result["lifecycle_memory"]
                self.assertEqual(len(memory["samples"]), 7)
                self.assertFalse(memory["continuous_peak_verified"])
                self.assertFalse(memory["whole_process_tree_memory_verified"])
                self.assertFalse(memory["global_memory_reserve"])


if __name__ == "__main__":
    unittest.main()
