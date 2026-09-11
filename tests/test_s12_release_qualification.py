from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/verify_s12_release_qualification.py"
spec = importlib.util.spec_from_file_location("s12_release_qualification", MODULE)
assert spec is not None and spec.loader is not None
s12 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s12
spec.loader.exec_module(s12)

MAIN_SHA = "1" * 40
TREE_SHA = "2" * 40
ISSUED = 2_000_000
NOW = 2_000_100


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def identity(role: str) -> dict[str, object]:
    index = list(s12.ROLE_NAMES).index(role) + 1
    return {"id": index, "login": f"role-{index}"}


def checkpoints(start: int, end: int) -> list[int]:
    result = list(range(start, end + 1, s12.MAX_CHECKPOINT_GAP_SECONDS))
    if result[-1] != end:
        result.append(end)
    return result


def packet() -> dict[str, object]:
    roles = {role: identity(role) for role in s12.ROLE_NAMES}
    image_sha = sha("release-image")
    normalized_sha = sha("normalized-release-image")
    locked = sha("locked-inputs")
    bom = {
        "model": "hepta-beta-1",
        "revision": "rev-1",
        "firmware_sha256": sha("firmware"),
        "cpu": "x86-64-v3",
        "memory_bytes": 16 * 1024 * 1024 * 1024,
        "storage": "nvme-model-1",
        "gpu": "gpu-model-1",
        "display_edid_sha256": sha("edid"),
        "input_inventory_sha256": sha("input-inventory"),
        "audio": "audio-model-1",
        "network": "network-model-1",
    }
    bom_sha = hashlib.sha256(s12.canonical_json(bom)).hexdigest()
    builders = []
    for role, suffix in (("builder_a", "a"), ("builder_b", "b")):
        actor = roles[role]
        builders.append(
            {
                "role": role,
                "actor_id": actor["id"],
                "actor_login": actor["login"],
                "builder_id": f"builder-{suffix}",
                "runner_id": f"runner-{suffix}",
                "administrative_domain": f"domain-{suffix}",
                "source_sha": MAIN_SHA,
                "source_tree": TREE_SHA,
                "locked_inputs_sha256": locked,
                "image_sha256": image_sha,
                "normalized_image_sha256": normalized_sha,
                "image_bytes": 123_456,
                "build_receipt_sha256": sha(f"builder-{suffix}-receipt"),
                "observed_unix": 1_999_000,
            }
        )
    endurance = []
    for hours, start in ((24, 1_900_000), (72, 1_700_000)):
        end = start + hours * 60 * 60
        actor = roles["endurance_attestor"]
        endurance.append(
            {
                "duration_hours": hours,
                "record_id": f"endurance-{hours}h",
                "attestor_id": actor["id"],
                "attestor_login": actor["login"],
                "image_sha256": image_sha,
                "bom_sha256": bom_sha,
                "start_unix": start,
                "end_unix": end,
                "checkpoints_unix": checkpoints(start, end),
                "terminal_status": "pass",
                "receipt_sha256": sha(f"endurance-{hours}-receipt"),
            }
        )
    power = []
    power_actor = roles["power_attestor"]
    for index, cutpoint in enumerate(sorted(s12.REQUIRED_POWER_CUTPOINTS)):
        power.append(
            {
                "cutpoint": cutpoint,
                "record_id": f"power-{index}",
                "attestor_id": power_actor["id"],
                "attestor_login": power_actor["login"],
                "observed_unix": 1_990_000 + index,
                "image_sha256": image_sha,
                "bom_sha256": bom_sha,
                "method": "non_graceful_power_removal",
                "filesystem_status": "pass",
                "journal_status": "pass",
                "update_reconciliation_status": "pass",
                "receipt_sha256": sha(f"power-{index}-receipt"),
            }
        )
    hardware_actor = roles["hardware_attestor"]
    release_actor = roles["release_attestor"]
    controller_a = roles["key_controller_a"]
    controller_b = roles["key_controller_b"]
    signer = roles["signer"]
    promoter = roles["promoter"]
    publisher = roles["publisher"]
    return {
        "schema": s12.PACKET_SCHEMA,
        "repository": s12.REPOSITORY,
        "issued_unix": ISSUED,
        "attestor": {
            "id": release_actor["id"],
            "login": release_actor["login"],
            "role": "independent_release_attestor",
        },
        "source": {
            "main_sha": MAIN_SHA,
            "tree_sha": TREE_SHA,
            "plan_revision": s12.PLAN_REVISION,
            "locked_inputs_sha256": locked,
        },
        "image": {
            "sha256": image_sha,
            "normalized_sha256": normalized_sha,
            "bytes": 123_456,
            "sbom_sha256": sha("sbom"),
            "license_report_sha256": sha("licenses"),
            "vulnerability_report_sha256": sha("vulnerabilities"),
        },
        "s10": {
            "receipt_sha256": sha("s10-receipt"),
            "image_sha256": image_sha,
            "installed_product_path_passed": True,
            "content_crash_reconstruction_passed": True,
            "stale_reference_rejected": True,
            "no_automatic_replay_passed": True,
        },
        "s11": {
            "receipt_sha256": sha("s11-receipt"),
            "source_image_sha256": sha("previous-image"),
            "target_image_sha256": image_sha,
            "installed_update_recovery_passed": True,
            "restart_cutpoints_passed": True,
            "no_automatic_replay_passed": True,
        },
        "builders": builders,
        "hardware": {
            "attestor_id": hardware_actor["id"],
            "attestor_login": hardware_actor["login"],
            "observed_unix": 1_690_000,
            "image_sha256": image_sha,
            "bom_sha256": bom_sha,
            "bom": bom,
            "secure_boot_observed": True,
            "tpm_or_equivalent_observed": True,
            "results": {name: "pass" for name in s12.REQUIRED_HARDWARE_RESULTS},
            "receipt_sha256": sha("hardware-receipt"),
        },
        "endurance": endurance,
        "power_loss": power,
        "key_custody": {
            "mode": "hsm",
            "key_id": "production-release-key-1",
            "key_fingerprint_sha256": sha("key-fingerprint"),
            "controller_ids": [controller_a["id"], controller_b["id"]],
            "controller_logins": [controller_a["login"], controller_b["login"]],
            "signer_id": signer["id"],
            "signer_login": signer["login"],
            "rotation_drill": {
                "status": "pass",
                "observed_unix": 1_995_000,
                "receipt_sha256": sha("rotation"),
            },
            "revocation_drill": {
                "status": "pass",
                "observed_unix": 1_995_001,
                "receipt_sha256": sha("revocation"),
            },
            "compromised_builder_drill": {
                "status": "pass",
                "observed_unix": 1_995_002,
                "receipt_sha256": sha("compromised-builder"),
            },
        },
        "roles": roles,
        "publication": {
            "environment": "production-publication",
            "protected_environment_verified": True,
            "main_sha": MAIN_SHA,
            "promoter_id": promoter["id"],
            "promoter_login": promoter["login"],
            "publisher_id": publisher["id"],
            "publisher_login": publisher["login"],
            "release_published": False,
        },
    }


def errors(value: dict[str, object], **overrides: object) -> list[str]:
    attestor = value["roles"]["release_attestor"]
    arguments = {
        "current_main_sha": MAIN_SHA,
        "signature_verified": True,
        "public_key_sha256": sha("external-public-key"),
        "expected_attestor_id": attestor["id"],
        "expected_attestor_login": attestor["login"],
        "now_unix": NOW,
    }
    arguments.update(overrides)
    return s12.verify_packet(value, **arguments)


class S12ReleaseQualificationTests(unittest.TestCase):
    def test_valid_packet_is_only_eligible_for_independent_review(self) -> None:
        value = packet()
        self.assertEqual(errors(value), [])
        encoded = s12.canonical_json(value)
        result = s12.qualification_result(encoded, value, [], MAIN_SHA)
        self.assertTrue(result["eligible_for_independent_promotion_review"])
        self.assertFalse(result["release_published_by_this_verifier"])
        self.assertFalse(result["external_facts_created_by_this_verifier"])

    def test_strict_json_rejects_duplicates_bom_non_json_and_non_object(self) -> None:
        for payload in (
            b'{"schema":"x","schema":"y"}',
            b'{"value":NaN}',
            b"\xef\xbb\xbf{}",
            b"[]",
            b"",
        ):
            with self.subTest(payload=payload), self.assertRaises(s12.QualificationError):
                s12.strict_json_bytes(payload)

    def test_two_builders_must_be_independent_and_byte_identical(self) -> None:
        for mutate in (
            lambda value: value["builders"].pop(),
            lambda value: value["builders"][1].__setitem__(
                "administrative_domain", value["builders"][0]["administrative_domain"]
            ),
            lambda value: value["builders"][1].__setitem__(
                "runner_id", value["builders"][0]["runner_id"]
            ),
            lambda value: value["builders"][1].__setitem__(
                "normalized_image_sha256", sha("different")
            ),
            lambda value: value["builders"][1].__setitem__("source_tree", "3" * 40),
        ):
            value = packet()
            mutate(value)
            with self.subTest(value=value):
                self.assertTrue(errors(value))

    def test_all_release_roles_are_identity_separated_and_bound(self) -> None:
        value = packet()
        value["roles"]["publisher"]["id"] = value["roles"]["promoter"]["id"]
        self.assertTrue(any("shared across separated roles" in item for item in errors(value)))
        value = packet()
        value["builders"][0]["actor_id"] = 999
        self.assertTrue(any("not bound to role builder_a" in item for item in errors(value)))
        value = packet()
        attestor = value["roles"]["release_attestor"]
        self.assertTrue(
            errors(value, expected_attestor_id=attestor["id"] + 1)
        )

    def test_hardware_requires_exact_bom_roots_and_complete_results(self) -> None:
        value = packet()
        value["hardware"]["bom"]["gpu"] = "substituted-gpu"
        self.assertTrue(any("BOM digest" in item for item in errors(value)))
        value = packet()
        value["hardware"]["results"].pop("recovery")
        self.assertTrue(any("inventory" in item for item in errors(value)))
        value = packet()
        value["hardware"]["secure_boot_observed"] = False
        value["hardware"]["tpm_or_equivalent_observed"] = False
        self.assertGreaterEqual(len(errors(value)), 2)

    def test_endurance_requires_real_24_and_72_hour_monotonic_records(self) -> None:
        value = packet()
        value["endurance"][1]["duration_hours"] = 24
        self.assertTrue(errors(value))
        value = packet()
        value["endurance"][0]["end_unix"] -= 1
        value["endurance"][0]["checkpoints_unix"][-1] -= 1
        self.assertTrue(any("does not prove 24 hours" in item for item in errors(value)))
        value = packet()
        value["endurance"][1]["checkpoints_unix"][1] += 1_000
        self.assertTrue(any("checkpoint gap" in item for item in errors(value)))
        value = packet()
        value["endurance"][0]["image_sha256"] = sha("other-image")
        self.assertTrue(any("image digest mismatch" in item for item in errors(value)))

    def test_raw_power_loss_requires_all_three_non_graceful_cutpoints(self) -> None:
        value = packet()
        value["power_loss"][0]["method"] = "process_kill"
        self.assertTrue(any("non-graceful" in item for item in errors(value)))
        value = packet()
        value["power_loss"][0]["cutpoint"] = value["power_loss"][1]["cutpoint"]
        self.assertTrue(errors(value))
        value = packet()
        value["power_loss"][2]["journal_status"] = "unknown"
        self.assertTrue(any("journal_status" in item for item in errors(value)))

    def test_key_custody_requires_two_controllers_and_all_drills(self) -> None:
        value = packet()
        value["key_custody"]["mode"] = "online-file"
        self.assertTrue(any("neither offline nor HSM" in item for item in errors(value)))
        value = packet()
        value["key_custody"]["controller_ids"] = [
            value["key_custody"]["controller_ids"][0],
            value["key_custody"]["controller_ids"][0],
        ]
        self.assertTrue(errors(value))
        value = packet()
        value["key_custody"]["revocation_drill"]["status"] = "fail"
        self.assertTrue(any("revocation_drill did not pass" in item for item in errors(value)))

    def test_s10_s11_current_main_and_publication_bindings_are_closed(self) -> None:
        value = packet()
        value["s10"]["installed_product_path_passed"] = False
        self.assertTrue(errors(value))
        value = packet()
        value["s11"]["target_image_sha256"] = sha("wrong-target")
        self.assertTrue(errors(value))
        value = packet()
        self.assertTrue(errors(value, current_main_sha="4" * 40))
        value = packet()
        value["publication"]["protected_environment_verified"] = False
        self.assertTrue(errors(value))
        value = packet()
        value["publication"]["release_published"] = True
        self.assertTrue(any("must precede" in item for item in errors(value)))

    def test_packet_freshness_signature_and_external_trust_root_are_required(self) -> None:
        value = packet()
        self.assertTrue(errors(value, signature_verified=False))
        self.assertTrue(errors(value, public_key_sha256=None))
        self.assertTrue(errors(value, now_unix=ISSUED + s12.MAX_PACKET_AGE_SECONDS + 1))
        value["issued_unix"] = NOW + s12.MAX_CLOCK_SKEW_SECONDS + 1
        self.assertTrue(errors(value))

    def test_detached_signature_verifier_is_exact_and_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            signature = root / "evidence.sig"
            public_key = root / "attestor.pem"
            evidence.write_bytes(s12.canonical_json(packet()))
            signature.write_bytes(b"signature")
            public_key.write_bytes(b"external-public-key")
            digest = hashlib.sha256(public_key.read_bytes()).hexdigest()

            def success(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                command = args[0]
                self.assertEqual(command[0:4], ["openssl", "dgst", "-sha256", "-verify"])
                return subprocess.CompletedProcess(command, 0, "Verified OK\n", "")

            self.assertEqual(
                s12.verify_detached_signature(
                    evidence, signature, public_key, digest, runner=success
                ),
                digest,
            )
            with self.assertRaises(s12.QualificationError):
                s12.verify_detached_signature(
                    evidence, signature, public_key, "0" * 64, runner=success
                )

            def failure(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(args[0], 1, "", "bad signature")

            with self.assertRaises(s12.QualificationError):
                s12.verify_detached_signature(
                    evidence, signature, public_key, digest, runner=failure
                )


if __name__ == "__main__":
    unittest.main()
