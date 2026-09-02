from __future__ import annotations

from contextlib import redirect_stderr
from copy import deepcopy
import io
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_d0t03_source_under_test",
    ROOT / "tools/validate_d0t03_source.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class D0T03SourceValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_globals = {
            name: getattr(VALIDATOR, name)
            for name in ("ROOT", "MANIFEST", "CODEOWNERS", "WORKFLOW")
        }
        self.manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture_root = Path(self.temporary.name)
        workflows = self.fixture_root / ".github/workflows"
        workflows.mkdir(parents=True)
        shutil.copy2(
            ROOT / ".github/CODEOWNERS", self.fixture_root / ".github/CODEOWNERS"
        )
        shutil.copy2(
            ROOT / ".github/workflows/d0t03-source-contract.yml",
            workflows / "d0t03-source-contract.yml",
        )
        for relative in self.manifest["main_branch"]["required_workflows"]:
            path = self.fixture_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("name: fixture\n", encoding="utf-8")
        manifest_path = self.fixture_root / "manifests/repository-governance.v1.json"
        manifest_path.parent.mkdir(parents=True)
        self._write_manifest(self.manifest)

        VALIDATOR.ROOT = self.fixture_root
        VALIDATOR.MANIFEST = manifest_path
        VALIDATOR.CODEOWNERS = self.fixture_root / ".github/CODEOWNERS"
        VALIDATOR.WORKFLOW = workflows / "d0t03-source-contract.yml"

    def tearDown(self) -> None:
        for name, value in self.original_globals.items():
            setattr(VALIDATOR, name, value)
        self.temporary.cleanup()

    def _write_manifest(self, value: dict) -> None:
        path = self.fixture_root / "manifests/repository-governance.v1.json"
        path.write_text(json.dumps(value), encoding="utf-8")

    def _assert_rejected(self, value: dict) -> None:
        self._write_manifest(value)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.main()

    def test_current_claims_require_exact_false_field_set(self) -> None:
        missing = deepcopy(self.manifest)
        missing["current_claims"].pop("d0t03_closed")
        self._assert_rejected(missing)

        extra = deepcopy(self.manifest)
        extra["current_claims"]["unexpected"] = False
        self._assert_rejected(extra)

        truthy = deepcopy(self.manifest)
        truthy["current_claims"]["d0t03_closed"] = True
        self._assert_rejected(truthy)

    def test_codeowner_list_requires_safe_distinct_strings(self) -> None:
        for owners in (
            "Tomasrgbsf",
            ["Tomasrgbsf"],
            ["Tomasrgbsf", "Tomasrgbsf"],
            [["Tomasrgbsf"], "ProfHepta"],
            ["Tomasrgbsf", "bad owner"],
        ):
            with self.subTest(owners=owners):
                value = deepcopy(self.manifest)
                value["source_review"]["interim_codeowners"] = owners
                self._assert_rejected(value)

    def test_codeowners_use_exact_tokens_and_resist_last_match_shadowing(self) -> None:
        original = (self.fixture_root / ".github/CODEOWNERS").read_text(
            encoding="utf-8"
        )

        # A substring in a comment or a look-alike username must not satisfy
        # the required owner identity check.
        lookalike = original.replace(
            "@Tomasrgbsf", "@TomasrgbsfEvil"
        ).replace("@ProfHepta", "@ProfHeptaEvil")
        (self.fixture_root / ".github/CODEOWNERS").write_text(
            lookalike + "\n# @Tomasrgbsf @ProfHepta\n", encoding="utf-8"
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.main()

        # GitHub resolves the final matching rule.  A later broad rule with
        # different owners must therefore be rejected rather than silently
        # shadowing the interim pair.
        (self.fixture_root / ".github/CODEOWNERS").write_text(
            original + "\n* @UntrustedOne @UntrustedTwo\n", encoding="utf-8"
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.main()

    def test_codeowners_ignore_inline_comments_but_reject_duplicate_tokens(self) -> None:
        original = (self.fixture_root / ".github/CODEOWNERS").read_text(
            encoding="utf-8"
        )
        (self.fixture_root / ".github/CODEOWNERS").write_text(
            original + "\n/docs/security/ @Tomasrgbsf @ProfHepta # note\n",
            encoding="utf-8",
        )
        self.assertEqual(VALIDATOR.main(), 0)

        (self.fixture_root / ".github/CODEOWNERS").write_text(
            original + "\n/docs/security/ @Tomasrgbsf @Tomasrgbsf\n",
            encoding="utf-8",
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.main()

    def test_required_workflow_paths_are_strict_and_existing(self) -> None:
        unsafe_values = (
            "../outside.yml",
            ".github/workflows/../outside.yml",
            ".github\\workflows\\ci.yml",
            "/tmp/outside.yml",
            "docs/workflow.yml",
            ".github/workflows/missing.yml",
        )
        for unsafe in unsafe_values:
            with self.subTest(unsafe=unsafe):
                value = deepcopy(self.manifest)
                value["main_branch"]["required_workflows"][0] = unsafe
                self._assert_rejected(value)

    def test_required_workflow_symlink_is_rejected(self) -> None:
        outside = self.fixture_root / "outside.yml"
        outside.write_text("name: outside\n", encoding="utf-8")
        link = self.fixture_root / ".github/workflows/link.yml"
        link.symlink_to(outside)
        value = deepcopy(self.manifest)
        value["main_branch"]["required_workflows"][0] = ".github/workflows/link.yml"
        self._assert_rejected(value)

    def test_required_workflow_registry_requires_a_list(self) -> None:
        value = deepcopy(self.manifest)
        value["main_branch"]["required_workflows"] = "not-a-list"
        self._assert_rejected(value)

    def test_governance_contract_workflow_is_required_for_main(self) -> None:
        self.assertIn(
            ".github/workflows/d0t03-source-contract.yml",
            self.manifest["main_branch"]["required_workflows"],
        )

    def test_required_workflow_registry_has_one_implementation_truth(self) -> None:
        implementation_spec = importlib.util.spec_from_file_location(
            "validate_d0t03_source_impl_under_test",
            ROOT / "tools/_validate_d0t03_source_impl.py",
        )
        assert implementation_spec is not None
        assert implementation_spec.loader is not None
        implementation = importlib.util.module_from_spec(implementation_spec)
        implementation_spec.loader.exec_module(implementation)

        expected = frozenset(self.manifest["main_branch"]["required_workflows"])
        self.assertEqual(
            implementation.EXPECTED_REQUIRED_WORKFLOW_REGISTRY,
            expected,
        )
        self.assertEqual(
            VALIDATOR.EXPECTED_REQUIRED_WORKFLOW_REGISTRY,
            expected,
        )

    def test_source_evidence_binds_pull_request_identity(self) -> None:
        workflow = (self.fixture_root / ".github/workflows/d0t03-source-contract.yml").read_text(
            encoding="utf-8"
        )
        for marker in (
            "EVENT_SHA: ${{ github.sha }}",
            "PR_NUMBER: ${{ github.event.pull_request.number || '' }}",
            "PR_BASE_SHA: ${{ github.event.pull_request.base.sha || '' }}",
            "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha || '' }}",
            "'pull_request_number': int(pr_number) if pr_number else None",
            "'base_sha': pr_base_sha or None",
            "'candidate_head_sha': pr_head_sha or None",
            "source evidence checkout does not equal github.sha",
            "pull-request source evidence parents do not match base/head",
            "pull-request source evidence identity is incomplete",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, workflow)

    def test_source_evidence_hashing_rejects_symlink_inputs(self) -> None:
        workflow = (self.fixture_root / ".github/workflows/d0t03-source-contract.yml").read_text(
            encoding="utf-8"
        )
        for marker in (
            "def read_source_bytes(path):",
            "getattr(os, 'O_NOFOLLOW', 0)",
            "symlinked source evidence path",
            "hashlib.sha256(read_source_bytes(path)).hexdigest()",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, workflow)

    def test_d0t03_workflow_strict_model_rejects_trigger_permission_and_action_bypasses(
        self,
    ) -> None:
        path = self.fixture_root / ".github/workflows/d0t03-source-contract.yml"
        original = path.read_text(encoding="utf-8")
        mutations = {
            "flow trigger": original.replace(
                "on:\n  pull_request:\n    branches: [main]\n  push:\n    branches: [main]\n  workflow_dispatch:",
                "on: {workflow_dispatch: null}",
            ),
            "flow write permission": original.replace(
                "permissions:\n  contents: read", "permissions: {contents: write}"
            ),
            "compact mutable action": original.replace(
                "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                "- uses: actions/checkout@main",
            ),
            "omitted executable validators": original.replace(
                "python3 tools/validate_repository.py", "true"
            ).replace(
                "python3 tools/validate_project_truth.py", "true"
            ).replace(
                "python3 tools/validate_d0t03_source.py", "true"
            ).replace(
                "python3 tools/validate_governance_integrity.py", "true"
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                path.write_text(mutated, encoding="utf-8")
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    VALIDATOR.main()
        path.write_text(original, encoding="utf-8")

    def test_governance_source_loaders_reject_symlink_components(self) -> None:
        outside = self.fixture_root / "outside.txt"
        outside.write_text("forged governance content", encoding="utf-8")
        cases = (
            ("MANIFEST", self.fixture_root / "manifests/repository-governance.v1.json"),
            ("CODEOWNERS", self.fixture_root / ".github/CODEOWNERS"),
            (
                "WORKFLOW",
                self.fixture_root / ".github/workflows/d0t03-source-contract.yml",
            ),
        )
        for name, path in cases:
            with self.subTest(name=name):
                backup = path.read_bytes()
                path.unlink()
                path.symlink_to(outside)
                try:
                    with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        VALIDATOR.main()
                finally:
                    path.unlink()
                    path.write_bytes(backup)

    def test_real_source_contract_still_passes(self) -> None:
        self.assertEqual(VALIDATOR.main(), 0)


if __name__ == "__main__":
    unittest.main()
