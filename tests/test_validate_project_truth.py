from __future__ import annotations

import importlib.util
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
