from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from gate_evidence_envelope import (  # noqa: E402
    REQUIRED_FIELDS,
    SCHEMA,
    _open_artifact,
    build_envelope,
    load_and_validate,
    validate_artifacts_on_disk,
    validate_envelope,
    write_envelope,
)


def sha(char: str) -> str:
    return char * 64


def git(char: str) -> str:
    return char * 40


class GateEvidenceEnvelopeTests(unittest.TestCase):
    def make_valid(self) -> dict[str, object]:
        return build_envelope(
            gate_id="D1-01",
            package_id="d1-debian-qemu-substrate",
            status="PASS",
            evidence_tier="qemu_image",
            base_sha=git("a"),
            candidate_head_sha=git("b"),
            tested_merge_sha=git("c"),
            integrated_main_sha=None,
            tree_sha=git("d"),
            workflow_path=".github/workflows/d1-final-qualification.yml",
            workflow_sha256=sha("e"),
            input_digests={"Cargo.lock": sha("f")},
            runner={"os": "ubuntu-24.04"},
            commands=[{"name": "pipeline", "status": "PASS", "exit_code": 0}],
            artifacts=[{"path": "evidence/result.json", "sha256": sha("1"), "bytes": 1}],
            claim_ceiling={"release": False},
            recorded_at="2026-08-30T09:00:00Z",
            event_name="pull_request",
            ref="refs/pull/32/merge",
            ref_name="32/merge",
            evidence_role="pr_synthetic_merge",
            promotion_authoritative=False,
            tested_sha=git("c"),
            workflow_run_id="123",
            workflow_run_attempt=1,
        )

    def test_d1_envelope_validates_and_matches_contract_required_fields(self) -> None:
        envelope = self.make_valid()
        validate_envelope(
            envelope,
            expected_gate_id="D1-01",
            expected_workflow_path=".github/workflows/d1-final-qualification.yml",
        )
        self.assertEqual(envelope["schema"], SCHEMA)
        self.assertTrue(REQUIRED_FIELDS.issubset(envelope))

    def test_mutations_are_rejected(self) -> None:
        mutations = []
        envelope = self.make_valid()
        missing = deepcopy(envelope)
        del missing["tested_merge_sha"]
        mutations.append(missing)
        wrong_event = deepcopy(envelope)
        wrong_event["ref"] = "refs/heads/main"
        mutations.append(wrong_event)
        unsafe_input = deepcopy(envelope)
        unsafe_input["input_digests"] = {"../escape": sha("2")}
        mutations.append(unsafe_input)
        bad_artifact = deepcopy(envelope)
        bad_artifact["artifacts"][0]["sha256"] = "A" * 64
        mutations.append(bad_artifact)
        missing_bytes = deepcopy(envelope)
        del missing_bytes["artifacts"][0]["bytes"]
        mutations.append(missing_bytes)
        for mutated in mutations:
            with self.assertRaises(ValueError):
                validate_envelope(mutated)

    def test_provenance_core_is_atomic_and_event_bound(self) -> None:
        envelope = self.make_valid()
        for field in (
            "event_name",
            "ref",
            "ref_name",
            "evidence_role",
            "promotion_authoritative",
        ):
            mutated = deepcopy(envelope)
            del mutated[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_envelope(mutated)

        push = deepcopy(envelope)
        push.update(
            {
                "event_name": "push",
                "ref": "refs/heads/main",
                "ref_name": "main",
                "evidence_role": "exact_main_push",
                "promotion_authoritative": True,
                "base_sha": git("a"),
                "candidate_head_sha": git("c"),
                "tested_merge_sha": None,
                "integrated_main_sha": git("c"),
            }
        )
        validate_envelope(push)

        for field, value in (
            ("ref_name", "wrong"),
            ("promotion_authoritative", False),
        ):
            mutated = deepcopy(push)
            mutated[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_envelope(mutated)

        manual = deepcopy(envelope)
        manual.update(
            {
                "event_name": "workflow_dispatch",
                "ref": "refs/heads/feature",
                "ref_name": "wrong",
                "evidence_role": "manual_non_authoritative",
                "promotion_authoritative": False,
            }
        )
        with self.assertRaises(ValueError):
            validate_envelope(manual)

    def test_provenance_run_identity_must_be_complete(self) -> None:
        envelope = self.make_valid()
        del envelope["workflow_run_attempt"]
        with self.assertRaisesRegex(ValueError, "run fields"):
            validate_envelope(envelope)

    def test_del_control_characters_are_rejected(self) -> None:
        for field in ("gate_id", "workflow_path", "event_name"):
            mutated = self.make_valid()
            mutated[field] = str(mutated[field]) + "\x7f"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_envelope(mutated)

        mutated = self.make_valid()
        mutated["artifacts"][0]["path"] = "evidence/\x7fresult.json"
        with self.assertRaises(ValueError):
            validate_envelope(mutated)

    def test_artifact_digest_mutation_is_rejected_on_disk(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "evidence/result.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"x")
            envelope["artifacts"][0]["sha256"] = "1" * 64
            envelope["artifacts"][0]["bytes"] = 1
            with self.assertRaises(ValueError):
                validate_artifacts_on_disk(envelope, root)

    def test_direct_artifact_open_rejects_traversal(self) -> None:
        # Keep the low-level helper fail-closed as well as the envelope-level
        # validator; callers should not be able to escape the evidence root.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / "outside-artifact.txt"
            outside.write_bytes(b"outside")
            try:
                with self.assertRaises(ValueError):
                    _open_artifact(root, "../outside-artifact.txt")
            finally:
                outside.unlink(missing_ok=True)

    def test_artifact_hashing_uses_bounded_stream_reads(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "evidence/result.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"x")
            envelope["artifacts"][0]["sha256"] = hashlib.sha256(b"x").hexdigest()
            envelope["artifacts"][0]["bytes"] = 1
            # A read_bytes implementation would make this test fail; the
            # verifier must hash incrementally from a bounded stream instead.
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError):
                validate_artifacts_on_disk(envelope, root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_artifact_root_and_components_reject_symlinks(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            real_root = parent / "real"
            artifact = real_root / "evidence/result.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"x")
            envelope["artifacts"][0]["sha256"] = hashlib.sha256(b"x").hexdigest()
            envelope["artifacts"][0]["bytes"] = 1

            root_alias = parent / "root-alias"
            root_alias.symlink_to(real_root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe|symlink"):
                validate_artifacts_on_disk(envelope, root_alias)

            nested_alias = real_root / "alias"
            nested_alias.symlink_to(real_root / "evidence", target_is_directory=True)
            envelope["artifacts"][0]["path"] = "alias/result.json"
            with self.assertRaisesRegex(ValueError, "unsafe|symlink"):
                validate_artifacts_on_disk(envelope, real_root)

            final_alias = real_root / "evidence/alias.json"
            final_alias.symlink_to(artifact)
            envelope["artifacts"][0]["path"] = "evidence/alias.json"
            with self.assertRaisesRegex(ValueError, "unsafe|symlink"):
                validate_artifacts_on_disk(envelope, real_root)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_write_envelope_rejects_symlink_destination_and_parent(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            destination = parent / "envelope.json"
            target = parent / "target.json"
            target.write_text("do not replace", encoding="utf-8")
            destination.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                write_envelope(destination, envelope)
            self.assertEqual(target.read_text(encoding="utf-8"), "do not replace")

            real_parent = parent / "real-parent"
            real_parent.mkdir()
            linked_parent = parent / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                write_envelope(linked_parent / "envelope.json", envelope)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_parent_symlink_is_rejected_when_loading_and_with_dotdot(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            real_parent = parent / "real-parent"
            real_parent.mkdir()
            destination = real_parent / "envelope.json"
            write_envelope(destination, envelope)

            linked_parent = parent / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex((ValueError, FileNotFoundError), "unsafe|symlink"):
                load_and_validate(linked_parent / "envelope.json")

            with self.assertRaisesRegex(ValueError, "symlink"):
                write_envelope(linked_parent / ".." / "escape.json", envelope)

    def test_missing_envelope_preserves_file_not_found_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                load_and_validate(Path(temporary) / "missing.json")

    def test_duplicate_json_keys_are_rejected_before_validation(self) -> None:
        envelope = self.make_valid()
        raw = json.dumps(envelope, indent=2, sort_keys=True)
        marker = f'  "status": "{envelope["status"]}",'
        self.assertIn(marker, raw)
        raw = raw.replace(
            marker,
            marker + f'\n  "status": "{envelope["status"]}",',
            1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text(raw + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                load_and_validate(path)

    def test_write_envelope_uses_exclusive_temp_and_atomic_replace(self) -> None:
        envelope = self.make_valid()
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            destination = parent / "envelope.json"
            destination.write_text("old", encoding="utf-8")
            write_envelope(destination, envelope)
            written = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(written["schema"], SCHEMA)
            self.assertFalse(
                any(path.name.startswith(".envelope.json.") for path in parent.iterdir())
            )

    def test_duplicate_command_names_are_rejected(self) -> None:
        envelope = self.make_valid()
        envelope["commands"] = [
            {"name": "pipeline", "status": "PASS", "exit_code": 0},
            {"name": "pipeline", "status": "PASS", "exit_code": 0},
        ]
        with self.assertRaises(ValueError):
            validate_envelope(envelope)

    def test_d1_and_d2i_wiring_is_additive(self) -> None:
        finalizer = (ROOT / "tools/finalize_d1_evidence.py").read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify_d1_artifact.py").read_text(encoding="utf-8")
        d2i = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text(encoding="utf-8")
        self.assertIn("gate-evidence-envelope.json", finalizer)
        self.assertIn("GATE_ENVELOPE_PATH", verifier)
        self.assertIn("gate-evidence-envelope.json", d2i)
        self.assertIn("gate_evidence_envelope", d2i)
        # The specialised receipts remain the canonical gate-specific records.
        self.assertIn("d1-final-qualification.json", finalizer)
        self.assertIn("d2i-integrated-qualification.json", d2i)


if __name__ == "__main__":
    unittest.main()
