from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_module_documentation_integration_under_test",
    ROOT / "tools/validate_module_documentation.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ModuleDocumentationIntegrationHardeningTests(unittest.TestCase):
    JOBS = (
        "repository-contracts",
        "repository-contracts-prospective-merge",
        "exact-head",
        "prospective-merge",
    )

    @staticmethod
    def workflow(job: str, body: str) -> str:
        return f"name: hostile\n\njobs:\n  {job}:\n{body}"

    def assert_all_jobs(self, body: str, expected: bool) -> None:
        for job in self.JOBS:
            with self.subTest(job=job):
                self.assertEqual(
                    VALIDATOR._job_executes(self.workflow(job, body), job),
                    expected,
                )

    def test_reachable_standalone_inline_invocation_is_accepted(self) -> None:
        self.assert_all_jobs(
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: gate\n"
            "        run: python3 tools/validate_module_documentation.py\n",
            True,
        )

    def test_comment_only_control_is_rejected(self) -> None:
        self.assert_all_jobs(
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: decoy\n"
            "        run: |\n"
            "          # python3 tools/validate_module_documentation.py\n"
            "          printf 'skipped\\n'\n",
            False,
        )

    def test_exit_before_command_block_is_rejected(self) -> None:
        self.assert_all_jobs(
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: unreachable\n"
            "        run: |\n"
            "          exit 0\n"
            "          python3 tools/validate_module_documentation.py\n",
            False,
        )

    def test_disabled_inline_step_after_many_prior_lines_is_rejected(self) -> None:
        padding = "".join(
            f"      - name: padding-{index}\n        run: printf '{index}\\n'\n"
            for index in range(6)
        )
        body = (
            "    runs-on: ubuntu-24.04\n"
            "    timeout-minutes: 20\n"
            "    steps:\n"
            + padding
            + "      - name: disabled gate\n"
            "        run: python3 tools/validate_module_documentation.py\n"
            "        if: false\n"
        )
        self.assert_all_jobs(body, False)

    def test_false_step_guard_after_block_run_is_rejected(self) -> None:
        self.assert_all_jobs(
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: disabled block gate\n"
            "        run: |\n"
            "          python3 tools/validate_module_documentation.py\n"
            "        if: ${{ false }}\n",
            False,
        )

    def test_job_level_false_guard_after_steps_is_rejected(self) -> None:
        self.assert_all_jobs(
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - name: gate\n"
            "        run: python3 tools/validate_module_documentation.py\n"
            "    if: false\n",
            False,
        )


if __name__ == "__main__":
    unittest.main()
