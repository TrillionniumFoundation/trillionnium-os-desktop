"""Closed corrected-owner identity regressions; never native execution evidence."""

from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_original_entry as builder
import native_owner_evidence as oracle
import native_owner_inputs as inputs
import run_native_owner as runner
from test_native_owner_evidence import ELF, NONCE, InertRecords
from test_native_owner_memory import Lifecycle
from test_original_owner_image_profile import profile as profiles

ROOT = Path(__file__).resolve().parents[3]
PROFILE = inputs.PUBLICATION_IMAGE_PROFILE


class PublicationOwnerImageProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="publication-image-profile-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.profile = profiles.select_profile(PROFILE)
        self.original = profiles.descriptor()
        self.value = self.profile.descriptor()

    def document(self, name, value):
        path = self.directory / name
        data = (json.dumps(value, sort_keys=True) + "\n").encode()
        path.write_bytes(data)
        return path, hashlib.sha256(data).hexdigest()

    def review(self):
        return {"schema": "hepta.original-owner-image-source-review.v1",
                "desktop": {"head": "ab" * 20, "tree": "cd" * 20},
                "hepta": self.value["hepta"], "entry": self.value["entry"],
                "userspace_toolchain": self.value["userspace_toolchain"],
                "scope": "Parser fixture only; no source snapshot or execution is asserted.",
                "image_profile": PROFILE,
                "image_profile_descriptor_sha256": self.profile.DESCRIPTOR_SHA256}

    def test_exact_source_and_elf_change_without_capacity_or_legacy_credit(self):
        self.assertEqual(profiles.DESCRIPTOR_SHA256,
                         "138043c29a3d3428fb8b494d6aa40d14b0010f6793a58d1f9ca46892bca5b758")
        self.assertNotEqual(self.value["hepta"], self.original["hepta"])
        self.assertNotEqual(self.value["image"]["sha256"], self.original["image"]["sha256"])
        profiles.require_within_a39_capacities(self.value)
        for key in ("whole_guest_peak_verified", "global_memory_reserve",
                    "native_execution_verified", "production_ready", "g2_complete"):
            self.assertIs(self.value[key], False)
        self.assertIs(self.value["legacy_profile"]["static_profile_passed"], False)

    def test_capacity_growth_and_changed_layout_fail_closed(self):
        for key in ("file_bytes", "mapped_load_bytes", "largest_load_range_bytes"):
            with self.subTest(capacity=key):
                changed = copy.deepcopy(self.value)
                changed["image"][key] = self.original["image"][key] + 1
                with self.assertRaisesRegex(ValueError, "A39 capacity"):
                    profiles.require_within_a39_capacities(changed)
        changes = (
            ("image", "load_segments", 5),
            (None, "roles", self.value["roles"] + ["extra"]),
            (None, "guest_memory_bytes", self.value["guest_memory_bytes"] + 4096),
            ("legacy_profile", "max_file_bytes", self.original["legacy_profile"]["max_file_bytes"] + 1),
            (None, "known_image_verification_and_full_stack_bytes",
             self.value["known_image_verification_and_full_stack_bytes"] + 1),
        )
        for section, key, value in changes:
            with self.subTest(field=key):
                changed = copy.deepcopy(self.value)
                (changed[section] if section else changed)[key] = value
                with self.assertRaises(ValueError):
                    profiles.require_within_a39_capacities(changed)
        for unknown in ("33554432", "../original-owner-image-profile.json", "g2-original-owner-publish-v2"):
            with self.subTest(profile=unknown), self.assertRaisesRegex(ValueError, "unknown"):
                profiles.select_profile(unknown)

    def test_source_review_and_build_binding_cannot_cross_exact_versions(self):
        review = self.review()
        path, digest = self.document("review.json", review)
        self.assertEqual(inputs.review_inputs(path, digest, PROFILE), review)
        with self.assertRaises(ValueError):
            inputs.review_inputs(path, digest, inputs.EXACT_IMAGE_PROFILE)
        changed = copy.deepcopy(review)
        changed["hepta"] = self.original["hepta"]
        path, digest = self.document("old-source.json", changed)
        with self.assertRaisesRegex(ValueError, "source review differs"):
            inputs.review_inputs(path, digest, PROFILE)
        changed = copy.deepcopy(review)
        changed["image_profile_descriptor_sha256"] = profiles.DESCRIPTOR_SHA256
        path, digest = self.document("old-descriptor.json", changed)
        with self.assertRaises(ValueError):
            inputs.review_inputs(path, digest, PROFILE)
        entry = {key: value for key, value in self.value["entry"].items() if key != "sha256"}
        entry["entry_sha256"] = self.value["entry"]["sha256"]
        sources = {"desktop": review["desktop"], "hepta": self.value["hepta"]}
        args = (entry, self.value["cargo_lock_sha256"],
                self.value["userspace_toolchain"]["sha256"],
                self.value["userspace_toolchain"]["channel"])
        self.assertEqual(self.profile.bind_build(sources, *args), self.value)
        with self.assertRaisesRegex(ValueError, "exact original Hepta"):
            self.profile.bind_build({**sources, "hepta": self.original["hepta"]}, *args)
        with self.assertRaisesRegex(ValueError, "reviewed native owner entry"):
            self.profile.bind_build(sources, {**entry, "entry_sha256": "00" * 32}, *args[1:])
        with self.assertRaisesRegex(ValueError, "lock or compiler identity"):
            self.profile.bind_build(sources, entry, "00" * 32, *args[2:])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.profile.inspect_elf(bytes(self.value["image"]["file_bytes"]))

    def test_selected_flag_is_exclusive_and_keeps_the_original_archive_cap(self):
        common = ["make", "--no-print-directory", "-f", str(ROOT / "support/build/minimal.mk"),
                  "CARGO_OSDK=unused-by-flag-inspection", self.profile.KERNEL_FLAG + "=1"]
        inspect = ["--eval=show-image-flags:;@printf '%s\\n' '$(CARGO_OSDK_BUILD_ARGS)'", "show-image-flags"]
        result = subprocess.run(common + inspect, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([arg for arg in result.stdout.split() if arg.startswith("--features=")],
                         ["--features=" + PROFILE])
        for old in ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL",
                    "HEPTA_G2_TRUSTED_DAEMON", "HEPTA_G2_ORIGINAL_OWNER_A39_V1"):
            with self.subTest(selector=old):
                result = subprocess.run(common + [old + "=1"] + inspect,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("select at most one", result.stderr)
        original = runner.original_owner_archive_contract()
        corrected = runner.original_owner_archive_contract(PROFILE)
        self.assertEqual(corrected["maximum_archive_bytes"], original["maximum_archive_bytes"])
        self.assertEqual(corrected["maximum_plan_bytes"], original["maximum_plan_bytes"])
        self.assertEqual(corrected["owner_file_bytes"], self.value["image"]["file_bytes"])
        self.assertEqual(corrected["image_profile"], PROFILE)
        self.assertFalse(corrected["native_execution_verified"])

    def test_disabled_commands_preserve_pending_execution_and_legacy_failure(self):
        args = ["--desktop-source", str(ROOT), "--desktop-head", "ab" * 20, "--desktop-tree", "cd" * 20,
                "--hepta-source", str(self.directory), "--hepta-head", "ef" * 20, "--hepta-tree", "12" * 20,
                "--entry", "hepta-g2-native-owner", "--toolchain-bin", str(self.directory),
                "--cargo-home", str(self.directory), "--target-cache", str(self.directory),
                "--output", str(self.directory / "not-created"), "--image-profile", PROFILE]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(builder.main(args), 0)
        build = json.loads(output.getvalue())
        self.assertEqual(build["image_profile"], PROFILE)
        self.assertFalse(build["image_profile_passed"])
        self.assertFalse(build["legacy_static_profile_passed"])
        self.assertNotIn("static_profile_passed", build)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(runner.main(["--image-profile", PROFILE]), 0)
        run = json.loads(output.getvalue())
        self.assertEqual(run["image_profile"], PROFILE)
        for key in ("passed", "native_execution_attempted", "legacy_static_profile_passed",
                    "whole_guest_peak_verified", "global_memory_reserve", "g2_complete"):
            self.assertFalse(run[key])
        self.assertFalse((self.directory / "not-created").exists())

    def test_inert_records_keep_source_version_and_memory_observation_boundaries(self):
        # These are parser-only records, never receipts for a real guest.
        image = self.value["image"]
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
                lines.insert(1, self.profile.kernel_selection_record())
                raw = ("\n".join(lines + original[5:]) + "\n").encode()
                result = oracle.evaluate(raw, 33, False, False, scenario, NONCE, elf, PROFILE)
                self.assertTrue(result["passed"])
                self.assertFalse(result["legacy_static_profile_passed"])
                self.assertFalse(result["g2_complete"])
                self.assertFalse(result["lifecycle_memory"]["continuous_peak_verified"])
                with self.assertRaises(ValueError):
                    oracle.evaluate(raw, 33, False, False, scenario, NONCE, elf, inputs.EXACT_IMAGE_PROFILE)


if __name__ == "__main__":
    unittest.main()
