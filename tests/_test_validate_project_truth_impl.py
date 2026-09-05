from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_project_truth_under_test",
    ROOT / "tools/validate_project_truth.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"


class ActionReferenceTests(unittest.TestCase):
    def test_accepts_exact_sha_with_matching_quotes_and_comment(self) -> None:
        expected = f"actions/checkout@{CHECKOUT_SHA}"
        lines = [
            f"        uses: {expected}",
            f"        uses : {expected} # reviewed pin",
            f"      - uses: {expected}",
            f"        uses: '{expected}'",
            f'        uses: "{expected}" # reviewed pin',
            f"        'uses': {expected}",
            f'        "uses" : "{expected}" # reviewed pin',
            f"      - 'uses': '{expected}'",
        ]
        for line in lines:
            with self.subTest(line=line):
                self.assertIsNotNone(VALIDATOR.ACTION_KEY.match(line))
                parsed = VALIDATOR.parse_action_uses(line)
                self.assertEqual(VALIDATOR.validate_action_reference(parsed), expected)

    def test_action_scan_skips_shell_text_inside_block_scalars(self) -> None:
        expected = f"actions/checkout@{CHECKOUT_SHA}"
        text = "\n".join(
            [
                "jobs:",
                "  check:",
                "    steps:",
                "      - run: |",
                f"          uses: {expected}",
                "          echo 'not a mapping'",
                f"      - \"uses\": {expected}",
            ]
        )
        lines = VALIDATOR.workflow_action_lines(text)
        self.assertNotIn((5, f"          uses: {expected}"), lines)
        self.assertIn((7, f'      - "uses": {expected}'), lines)

    def test_action_scan_covers_flow_mapping_steps(self) -> None:
        expected = f"actions/checkout@{CHECKOUT_SHA}"
        text = "\n".join(
            [
                "jobs:",
                "  check:",
                "    steps: [{uses: " + expected + ", with: {fetch-depth: 1}}]",
                '      - {"uses": "' + expected + '"}',
            ]
        )
        declarations = [line for _, line in VALIDATOR.workflow_action_lines(text)]
        self.assertEqual(declarations.count("uses:"), 2)
        for declaration in declarations:
            if declaration == "uses:":
                with self.assertRaises(ValueError):
                    VALIDATOR.parse_action_uses(declaration)

    def test_flow_mapping_mutable_ref_is_not_silently_skipped(self) -> None:
        line = "      - {uses: actions/checkout@main}"
        declarations = [line for _, line in VALIDATOR.workflow_action_lines(line)]
        self.assertEqual(declarations, [line, "uses:"])
        with self.assertRaises(ValueError):
            VALIDATOR.parse_action_uses(declarations[-1])

    def test_plain_scalar_apostrophe_does_not_hide_later_flow_action(self) -> None:
        line = "      - {name: don't skip this, uses: actions/checkout@main}"
        declarations = [line for _, line in VALIDATOR.workflow_action_lines(line)]
        self.assertIn("uses:", declarations)

    def test_multiline_flow_mapping_action_is_rejected(self) -> None:
        text = "\n".join(
            [
                "      - {",
                "          name: fixture",
                "          , uses: actions/checkout@main",
                "        }",
            ]
        )
        declarations = [line for _, line in VALIDATOR.workflow_action_lines(text)]
        self.assertIn("uses:", declarations)

    def test_flow_mapping_text_in_comments_and_quoted_scalars_is_ignored(self) -> None:
        expected = f"actions/checkout@{CHECKOUT_SHA}"
        text = "\n".join(
            [
                '  name: "literal {uses: actions/checkout@main}"',
                "  # - {uses: actions/checkout@main}",
                "  run: echo '{uses: actions/checkout@main}'",
                "  description: plain {not-an-action: value}",
                "  note: '{uses: " + expected + "}'",
            ]
        )
        declarations = [
            line
            for _, line in VALIDATOR.workflow_action_lines(text)
            if line.startswith("uses:")
        ]
        self.assertEqual(declarations, [])

    def test_rejects_mismatched_quotes_and_malformed_comments(self) -> None:
        invalid = [
            f"uses: 'actions/checkout@{CHECKOUT_SHA}\"",
            f'uses: "actions/checkout@{CHECKOUT_SHA}\'',
            f"uses: 'actions/checkout@{CHECKOUT_SHA}' trailing",
            f"uses: actions/checkout@{CHECKOUT_SHA} extra",
            "uses:",
        ]
        for line in invalid:
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    VALIDATOR.parse_action_uses(line)

    def test_rejects_mutable_and_invalid_owner_repository_forms(self) -> None:
        invalid = [
            "actions/checkout@main",
            f"actions//checkout@{CHECKOUT_SHA}",
            f"/checkout@{CHECKOUT_SHA}",
            f"actions/checkout/extra@{CHECKOUT_SHA}",
            f"actions/@{CHECKOUT_SHA}",
            f"docker://actions/checkout@{CHECKOUT_SHA}",
            f"actions/checkout@{CHECKOUT_SHA.upper()}",
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VALIDATOR.validate_action_reference(value)

    def test_accepts_safe_local_action_and_rejects_traversal(self) -> None:
        self.assertEqual(
            VALIDATOR.validate_action_reference("./.github/actions/build"),
            "./.github/actions/build",
        )
        for value in ("./../action", "./actions/../action", "./actions//action"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    VALIDATOR.validate_action_reference(value)

    def test_every_checkout_step_disables_persisted_credentials(self) -> None:
        """Read-only workflows must not leave a writable Git credential behind."""

        checkout_count = 0
        for workflow in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
            lines = workflow.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "uses: actions/checkout@" not in line:
                    continue
                checkout_count += 1
                action_indent = len(line) - len(line.lstrip())
                block = [line]
                for following in lines[index + 1 :]:
                    stripped = following.lstrip()
                    indent = len(following) - len(stripped)
                    if indent <= action_indent - 2 and stripped.startswith("- "):
                        break
                    block.append(following)
                step = "\n".join(block)
                self.assertRegex(
                    step,
                    r"(?m)^\s+persist-credentials:\s*false\s*(?:#.*)?$",
                    f"{workflow}:{index + 1} must set persist-credentials=false",
                )
                self.assertNotRegex(
                    step,
                    r"(?m)^\s+persist-credentials:\s*true\s*(?:#.*)?$",
                )
        self.assertGreater(checkout_count, 0)


class CandidateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = {
            "id": "D1-01",
            "branch": "codex/d1-01-current-main",
            "pr": 32,
            "status": "BASE_DRIFT",
            "base_sha": "a" * 40,
            "candidate_head_sha": "b" * 40,
            "claim_ceiling": "candidate_source_no_promoted_runtime_claim",
        }
        self.arguments = {
            "gate_ids": {"D1-01"},
            "status_vocabulary": {"BASE_DRIFT"},
            "gate_status_by_id": {"D1-01": "BASE_DRIFT"},
            "completed": set(),
        }

    def errors(self, candidate: object) -> list[str]:
        return VALIDATOR.candidate_validation_errors(candidate, **self.arguments)

    def test_accepts_complete_candidate_shape(self) -> None:
        self.assertEqual(self.errors(self.candidate), [])

    def test_rejects_unsafe_or_incomplete_provenance(self) -> None:
        malformed = dict(self.candidate)
        malformed.update(
            {
                "branch": "codex/../main",
                "pr": True,
                "base_sha": "not-a-sha",
                "unknown_claim": True,
                "evidence_artifact_digest": "sha256:" + "c" * 64,
            }
        )
        errors = self.errors(malformed)
        self.assertTrue(any("branch" in error for error in errors), errors)
        self.assertTrue(any("PR number" in error for error in errors), errors)
        self.assertTrue(any("base_sha" in error for error in errors), errors)
        self.assertTrue(any("unknown fields" in error for error in errors), errors)
        self.assertTrue(any("evidence identity" in error for error in errors), errors)

    def test_rejects_null_git_or_evidence_digests(self) -> None:
        malformed = dict(self.candidate)
        malformed["base_sha"] = "0" * 40
        malformed["candidate_head_sha"] = "0" * 40
        malformed.update(
            {
                "evidence_artifact_digest": "sha256:" + "0" * 64,
                "evidence_artifact_id": 1,
                "evidence_run_id": 2,
            }
        )
        errors = self.errors(malformed)
        self.assertTrue(any("base_sha" in error for error in errors), errors)
        self.assertTrue(any("candidate_head_sha" in error for error in errors), errors)
        self.assertTrue(any("evidence_artifact_digest" in error for error in errors), errors)

    def test_detects_duplicate_candidate_ids(self) -> None:
        duplicate = dict(self.candidate)
        duplicate["branch"] = "codex/d1-01-second"
        self.assertEqual(
            VALIDATOR.duplicate_candidate_ids([self.candidate, duplicate]),
            ["D1-01"],
        )


class GateContractDependencyTests(unittest.TestCase):
    def test_d2i_contract_dependencies_are_registered(self) -> None:
        import json

        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text(
                encoding="utf-8"
            )
        )
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate_ids = {entry["id"] for entry in registry["gates"]}
        self.assertEqual(
            VALIDATOR.gate_contract_dependency_errors(
                contract,
                gate_ids=gate_ids,
                label="d2i contract",
            ),
            [],
        )

    def test_gate_contract_dependency_checker_rejects_unknown_ids(self) -> None:
        errors = VALIDATOR.gate_contract_dependency_errors(
            {"dependencies": ["D1-01", "D2-01"]},
            gate_ids={"D1-01"},
            label="fixture contract",
        )
        self.assertTrue(any("unregistered gate 'D2-01'" in error for error in errors))


class InvalidationCoverageTests(unittest.TestCase):
    def test_d3_registry_covers_profile_install_and_image_inputs(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D3-01")
        paths = set(gate["invalidation_paths"])
        self.assertIn(".github/workflows/**", paths)
        self.assertIn("manifests/**", paths)
        self.assertIn("tools/**", paths)
        self.assertIn("docs/**", paths)
        self.assertIn("packaging/debian/hepta-agent-portd.install", paths)
        self.assertIn("packaging/debian/image/rootfs-overlay/**", paths)

    def test_segment_glob_supports_recursive_and_filename_patterns(self) -> None:
        self.assertTrue(
            VALIDATOR._invalidation_glob_matches(
                ".github/workflows/ci.yml", ".github/**"
            )
        )
        self.assertTrue(
            VALIDATOR._invalidation_glob_matches(
                "manifests/servo.lock.json", "manifests/servo*.json"
            )
        )
        self.assertFalse(
            VALIDATOR._invalidation_glob_matches(
                "manifests/nested/ci.json", "manifests/*.json"
            )
        )

    def test_unsafe_invalidation_glob_is_rejected(self) -> None:
        for pattern in ("../outside", "/absolute", "!manifests/**", "C:drive/**", "foo\\bar"):
            with self.subTest(pattern=pattern):
                with self.assertRaises(ValueError):
                    VALIDATOR._invalidation_glob_matches("manifests/a.json", pattern)

    def test_coverage_checker_reports_uncovered_machine_input(self) -> None:
        import json

        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(VALIDATOR.invalidation_coverage_errors(registry, root=ROOT), [])
        registry = {"gates": [{"id": "D9-01", "invalidation_paths": ["tools/**"]}]}
        errors = VALIDATOR.invalidation_coverage_errors(registry, root=ROOT)
        self.assertTrue(
            any(".github/workflows" in error or "manifests/" in error for error in errors),
            errors,
        )


class D0A02EvidenceLifecycleTests(unittest.TestCase):
    """Keep historical headed-host evidence below the active claim ceiling."""

    def test_generated_headed_evidence_is_explicitly_stale(self) -> None:
        for relative in (
            "docs/evidence/generated/d0a02-headed-runtime-evidence.json",
            "docs/evidence/generated/d0a02-headed-runtime-result.json",
        ):
            with self.subTest(relative=relative):
                record = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                self.assertEqual(
                    record.get("evidence_lifecycle"),
                    VALIDATOR.D0A02_EVIDENCE_LIFECYCLE,
                )
                self.assertEqual(
                    record.get("stale_reason"),
                    VALIDATOR.D0A02_STALE_REASON,
                )
                promotion = record.get("promotion")
                self.assertIsInstance(promotion, dict)
                assert isinstance(promotion, dict)
                self.assertEqual(promotion.get("evidence_freshness"), "STALE_EVIDENCE")
                self.assertFalse(promotion.get("merge_ready"))
                self.assertEqual(promotion.get("superseded_by_pr"), 33)
                self.assertEqual(promotion.get("stale_reason"), VALIDATOR.D0A02_STALE_REASON)

    def test_manifest_entries_preserve_pr33_claim_ceiling_without_readiness(self) -> None:
        docs = json.loads((ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8"))
        repository = json.loads(
            (ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
        )
        project = json.loads(
            (ROOT / "manifests/project-state.v1.json").read_text(encoding="utf-8")
        )
        checkpoint = next(
            item for item in docs["implementation_checkpoints"] if item.get("id") == "TOS-D0A-02"
        )
        qualification = next(
            item
            for item in repository["qualification_work_packages"]
            if item.get("id") == "D0A-02"
        )
        for entry in (checkpoint, qualification):
            with self.subTest(entry=entry.get("id")):
                self.assertEqual(entry.get("evidence_lifecycle"), VALIDATOR.D0A02_EVIDENCE_LIFECYCLE)
                self.assertFalse(entry.get("merge_ready"))
                self.assertEqual(entry.get("superseded_by_pr"), 33)
                self.assertEqual(entry.get("stale_reason"), VALIDATOR.D0A02_STALE_REASON)

        candidate = next(
            item
            for item in project["source_candidate_work_packages"]
            if item.get("id") == "D0A-02"
        )
        self.assertEqual(candidate.get("pr"), 33)
        self.assertEqual(candidate.get("status"), "MODULE_CLOSED_CANDIDATE")
        self.assertTrue(
            candidate.get("claim_ceiling", "").startswith("headed_host_local_fixture_only")
        )


class StaleEvidenceMetadataTests(unittest.TestCase):
    """Ensure stale freshness cannot erase a gate's source capability claim."""

    EXPECTED_STALE_GATES = {
        "D0A-01",
        "D0A-02",
        "D0C-02",
        "D0C-03",
        "D0C-04",
        "D0C-05",
        "D0C-06",
    }

    def test_gate_registry_records_stale_freshness_separately_from_status(self) -> None:
        registry = json.loads((ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8"))
        gates = {
            entry["id"]: entry
            for entry in registry["gates"]
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }
        stale = {
            gate_id
            for gate_id, entry in gates.items()
            if entry.get("evidence_lifecycle") == VALIDATOR.D0A02_EVIDENCE_LIFECYCLE
        }
        self.assertEqual(stale, self.EXPECTED_STALE_GATES)
        for gate_id in sorted(self.EXPECTED_STALE_GATES):
            entry = gates[gate_id]
            with self.subTest(gate_id=gate_id):
                self.assertEqual(entry.get("evidence_freshness"), "STALE_EVIDENCE")
                self.assertFalse(entry.get("merge_ready"))
                reason = entry.get("stale_reason", "")
                self.assertIn("exact candidate head", reason)
                self.assertRegex(reason, r"(?i)\brerun\b|\brun\b")
                # ``status`` remains the bounded capability outcome; freshness
                # is intentionally represented by the separate fields above.
                self.assertNotEqual(entry.get("status"), "STALE_EVIDENCE")

    def test_stale_rows_and_machine_evidence_match_gate_freshness(self) -> None:
        registry = json.loads((ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8"))
        gate_by_id = {entry["id"]: entry for entry in registry["gates"]}
        docs = json.loads((ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8"))
        repository = json.loads(
            (ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
        )
        rows = []
        rows.extend(docs.get("implementation_checkpoints", []))
        rows.extend(repository.get("host_validated_work_packages", []))
        rows.extend(repository.get("qualification_work_packages", []))
        for row in rows:
            if not isinstance(row, dict) or row.get("evidence_lifecycle") != VALIDATOR.D0A02_EVIDENCE_LIFECYCLE:
                continue
            gate_id = str(row.get("id", "")).replace("TOS-", "")
            with self.subTest(gate_id=gate_id, row_id=row.get("id")):
                self.assertIn(gate_id, gate_by_id)
                self.assertEqual(row.get("evidence_freshness"), "STALE_EVIDENCE")
                self.assertFalse(row.get("merge_ready"))
                self.assertEqual(
                    row.get("stale_reason"), gate_by_id[gate_id].get("stale_reason")
                )
                machine_evidence = row.get("machine_evidence") or row.get("evidence")
                if isinstance(machine_evidence, str) and machine_evidence.startswith(
                    ("evidence/generated/", "docs/evidence/generated/")
                ):
                    generated_path = (
                        ROOT / "docs" / machine_evidence
                        if machine_evidence.startswith("evidence/")
                        else ROOT / machine_evidence
                    )
                    if generated_path.is_file():
                        generated = json.loads(generated_path.read_text(encoding="utf-8"))
                        self.assertEqual(generated.get("evidence_freshness"), "STALE_EVIDENCE")
                        self.assertFalse(generated.get("merge_ready"))
                        self.assertEqual(
                            generated.get("stale_reason"), gate_by_id[gate_id].get("stale_reason")
                        )

    def test_stale_contracts_expose_top_level_freshness_without_erasing_validation(self) -> None:
        contract_paths = {
            "D0C-02": ROOT / "contracts/agent-transport.v1.json",
            "D0C-03": ROOT / "contracts/browser-codec.v1.json",
            "D0C-04": ROOT / "contracts/agent-port-bridge.v1.json",
            "D0C-05": ROOT / "contracts/agent-port-custody.v1.json",
        }
        capability_statuses = {
            "D0C-02": "HOST_VALIDATED_NO_LISTENER",
            "D0C-03": "HOST_VALIDATED_RUST_1_93_NO_DISPATCH",
            "D0C-04": "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR",
            "D0C-05": "HOST_VALIDATED_DEFAULT_DISABLED_NO_PRODUCT_LISTENER",
        }
        for gate_id, path in contract_paths.items():
            with self.subTest(gate_id=gate_id):
                contract = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(contract.get("status"), capability_statuses[gate_id])
                self.assertNotEqual(contract.get("status"), "STALE_EVIDENCE")
                self.assertEqual(
                    contract.get("evidence_lifecycle"),
                    VALIDATOR.D0A02_EVIDENCE_LIFECYCLE,
                )
                self.assertEqual(contract.get("evidence_freshness"), "STALE_EVIDENCE")
                self.assertFalse(contract.get("merge_ready"))
                self.assertIsInstance(contract.get("stale_reason"), str)
                # Nested validation remains the source-capability record; the
                # top-level freshness fields are a synchronized summary.
                validation = contract.get("validation") or contract.get("host_validation")
                self.assertIsInstance(validation, dict)
                assert isinstance(validation, dict)
                self.assertEqual(validation.get("evidence_freshness"), "STALE_EVIDENCE")
                self.assertFalse(validation.get("merge_ready"))

        candidate = json.loads(
            (ROOT / "manifests/d0c04-candidate.json").read_text(encoding="utf-8")
        )
        self.assertEqual(candidate.get("status"), "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR")
        self.assertNotEqual(candidate.get("status"), "STALE_EVIDENCE")
        self.assertEqual(candidate.get("evidence_lifecycle"), VALIDATOR.D0A02_EVIDENCE_LIFECYCLE)
        self.assertEqual(candidate.get("evidence_freshness"), "STALE_EVIDENCE")
        self.assertFalse(candidate.get("merge_ready"))
        self.assertEqual(candidate.get("stale_reason"), candidate["validation"]["stale_reason"])

    def _truth_snapshots(self) -> tuple[dict, dict, dict]:
        gates = json.loads((ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8"))
        docs = json.loads((ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8"))
        repository = json.loads(
            (ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
        )
        return gates, docs, repository

    def test_generic_checker_rejects_partial_stale_gate_metadata(self) -> None:
        gates, docs, repository = self._truth_snapshots()
        gate = next(item for item in gates["gates"] if item["id"] == "D0C-02")
        gate["evidence_freshness"] = "CURRENT"
        errors = VALIDATOR.stale_metadata_errors(gates, docs, repository)
        self.assertTrue(
            any("D0C-02" in error and "STALE_EVIDENCE freshness" in error for error in errors),
            errors,
        )

    def test_generic_checker_rejects_status_used_as_staleness(self) -> None:
        gates, docs, repository = self._truth_snapshots()
        gate = next(item for item in gates["gates"] if item["id"] == "D0C-03")
        gate["status"] = "STALE_EVIDENCE"
        errors = VALIDATOR.stale_metadata_errors(gates, docs, repository)
        self.assertTrue(
            any("D0C-03" in error and "capability status" in error for error in errors),
            errors,
        )

    def test_generic_checker_rejects_row_reason_drift(self) -> None:
        gates, docs, repository = self._truth_snapshots()
        row = next(
            item
            for item in docs["implementation_checkpoints"]
            if item["id"] == "TOS-D0C-04"
        )
        row["stale_reason"] = "tampered reason"
        errors = VALIDATOR.stale_metadata_errors(gates, docs, repository)
        self.assertTrue(
            any("TOS-D0C-04" in error and "stale_reason" in error for error in errors),
            errors,
        )


class ProjectTruthInputSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_root = VALIDATOR.ROOT
        VALIDATOR.ERRORS.clear()

    def tearDown(self) -> None:
        VALIDATOR.ROOT = self.original_root
        VALIDATOR.ERRORS.clear()

    def test_load_json_rejects_symlink_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text('{"trusted": true}', encoding="utf-8")
            link = root / "manifest.json"
            link.symlink_to(outside)
            VALIDATOR.ROOT = root

            self.assertEqual(VALIDATOR.load_json("manifest.json"), {})
            self.assertTrue(
                any("invalid JSON" in error and "symlink" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

            VALIDATOR.ERRORS.clear()
            self.assertEqual(VALIDATOR.load_json("../outside.json"), {})
            self.assertTrue(
                any("invalid JSON" in error and ".." in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def test_workflow_scan_rejects_symlinked_workflow_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            workflows = root / ".github/workflows"
            manifests = root / "manifests"
            workflows.mkdir(parents=True)
            manifests.mkdir()
            outside = Path(directory) / "workflow.yml"
            outside.write_text("jobs: {}\n", encoding="utf-8")
            (workflows / "linked.yml").symlink_to(outside)
            (manifests / "ci-action-pins.v1.json").write_text(
                '{"actions": {}}', encoding="utf-8"
            )
            VALIDATOR.ROOT = root

            VALIDATOR.check_workflow_action_pins()
            self.assertTrue(
                any("cannot be read safely" in error for error in VALIDATOR.ERRORS),
                VALIDATOR.ERRORS,
            )

    def test_reader_rejects_nonregular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            (root / "directory").mkdir()
            VALIDATOR.ROOT = root
            with self.assertRaises(OSError):
                VALIDATOR._read_text_nofollow(root / "directory")


if __name__ == "__main__":
    unittest.main()
