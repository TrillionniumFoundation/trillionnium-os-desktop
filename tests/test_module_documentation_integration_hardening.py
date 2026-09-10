from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
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

CHECKOUT = (
    "      - name: Check out exact source head\n"
    "        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n"
    "        with:\n"
    "          ref: ${{ github.event.pull_request.head.sha }}\n"
    "          fetch-depth: 2\n"
    "          persist-credentials: false\n"
)
VALIDATOR_STEP = (
    "      - name: Validate module documentation contract\n"
    "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
)


class ModuleDocumentationIntegrationHardeningTests(unittest.TestCase):
    JOBS = (
        "repository-contracts",
        "repository-contracts-prospective-merge",
        "exact-head",
        "prospective-merge",
    )

    @staticmethod
    def workflow(
        job: str,
        *,
        job_fields: str = "",
        before_validator: str = "",
        validator_step: str = VALIDATOR_STEP,
        workflow_fields: str = "",
    ) -> str:
        condition = (
            "    if: github.event_name == 'pull_request'\n"
            if "prospective" in job
            else ""
        )
        return (
            "name: hostile\n"
            f"{workflow_fields}"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            f"  {job}:\n"
            "    runs-on: ubuntu-24.04\n"
            f"{condition}"
            f"{job_fields}"
            "    steps:\n"
            f"{CHECKOUT}"
            f"{before_validator}"
            f"{validator_step}"
        )

    def assert_all_jobs(self, expected: bool, **kwargs: str) -> None:
        for job in self.JOBS:
            with self.subTest(job=job):
                self.assertEqual(
                    VALIDATOR._job_executes(self.workflow(job, **kwargs), job),
                    expected,
                )

    def test_closed_trusted_invocation_is_accepted(self) -> None:
        self.assert_all_jobs(True)

    def test_explicit_false_continue_on_error_is_accepted(self) -> None:
        self.assert_all_jobs(True, job_fields="    continue-on-error: false\n")
        self.assert_all_jobs(
            True,
            validator_step=(
                "      - name: Validate module documentation contract\n"
                "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "        continue-on-error: false\n"
            ),
        )

    def test_comment_only_control_is_rejected(self) -> None:
        self.assert_all_jobs(
            False,
            validator_step=(
                "      - name: decoy\n"
                "        run: |\n"
                "          # /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "          printf 'skipped\\n'\n"
            ),
        )

    def test_exit_before_command_block_is_rejected(self) -> None:
        self.assert_all_jobs(
            False,
            validator_step=(
                "      - name: unreachable\n"
                "        run: |\n"
                "          exit 0\n"
                "          /usr/bin/python3 -I tools/validate_module_documentation.py\n"
            ),
        )

    def test_validator_after_prior_command_is_rejected(self) -> None:
        self.assert_all_jobs(
            False,
            before_validator=(
                "      - name: replace interpreter\n"
                "        run: sudo ln -sf /tmp/fake-python /usr/bin/python3\n"
            ),
        )

    def test_composite_false_job_guards_are_rejected(self) -> None:
        for expression in (
            "${{ false && always() }}",
            "${{ !true }}",
            "${{ 1 == 0 }}",
        ):
            for job in self.JOBS:
                with self.subTest(job=job, expression=expression):
                    if "prospective" in job:
                        text = self.workflow(job).replace(
                            "    if: github.event_name == 'pull_request'\n",
                            f"    if: {expression}\n",
                            1,
                        )
                    else:
                        text = self.workflow(
                            job,
                            job_fields=f"    if: {expression}\n",
                        )
                    self.assertFalse(VALIDATOR._job_executes(text, job))

    def test_any_step_condition_is_rejected(self) -> None:
        for expression in ("${{ always() }}", "${{ false && always() }}", "false"):
            with self.subTest(expression=expression):
                self.assert_all_jobs(
                    False,
                    validator_step=(
                        "      - name: disabled gate\n"
                        "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                        f"        if: {expression}\n"
                    ),
                )

    def test_continue_on_error_true_is_rejected_at_job_and_step(self) -> None:
        self.assert_all_jobs(False, job_fields="    continue-on-error: true\n")
        self.assert_all_jobs(
            False,
            validator_step=(
                "      - name: nonblocking gate\n"
                "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "        continue-on-error: true\n"
            ),
        )

    def test_custom_shell_and_environment_are_rejected(self) -> None:
        self.assert_all_jobs(
            False,
            validator_step=(
                "      - name: custom shell\n"
                "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "        shell: custom-without-placeholder\n"
            ),
        )
        self.assert_all_jobs(
            False,
            validator_step=(
                "      - name: path substitution\n"
                "        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "        env:\n"
                "          PYTHONPATH: attacker-controlled\n"
            ),
        )
        self.assert_all_jobs(
            False,
            workflow_fields=(
                "defaults:\n"
                "  run:\n"
                "    shell: custom-without-placeholder\n"
            ),
        )
        self.assert_all_jobs(
            False,
            workflow_fields=(
                "env:\n"
                "  PYTHONPATH: attacker-controlled\n"
            ),
        )

    def test_unpinned_or_credentialed_checkout_is_rejected(self) -> None:
        for checkout in (
            CHECKOUT.replace(
                "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                "actions/checkout@v4",
            ),
            CHECKOUT.replace("persist-credentials: false", "persist-credentials: true"),
            CHECKOUT.replace("fetch-depth: 2\n", ""),
        ):
            with self.subTest(checkout=checkout):
                for job in self.JOBS:
                    text = self.workflow(job).replace(CHECKOUT, checkout)
                    self.assertFalse(VALIDATOR._job_executes(text, job))

    def test_make_validator_recipe_is_failure_propagating(self) -> None:
        self.assertTrue(
            VALIDATOR._make_target_executes(
                (
                    "validate:\n"
                    "\t@/usr/bin/python3 -I tools/validate_module_documentation.py\n"
                    "\tprintf 'after\\n'\n"
                ),
                "validate",
            )
        )
        for makefile in (
            (
                "validate:\n"
                "\t-/usr/bin/python3 -I tools/validate_module_documentation.py\n"
            ),
            (
                ".IGNORE: validate\n"
                "validate:\n"
                "\t/usr/bin/python3 -I tools/validate_module_documentation.py\n"
            ),
            (
                ".ONESHELL:\n"
                "validate:\n"
                "\t/usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "\ttrue\n"
            ),
            (
                "SHELL := /tmp/custom-shell\n"
                "validate:\n"
                "\t/usr/bin/python3 -I tools/validate_module_documentation.py\n"
            ),
        ):
            with self.subTest(makefile=makefile):
                self.assertFalse(VALIDATOR._make_target_executes(makefile, "validate"))

    def test_real_make_target_propagates_validator_failure(self) -> None:
        self.assertIsNotNone(shutil.which("make"))
        source = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "/usr/bin/python3 -I tools/validate_module_documentation.py",
            source,
        )
        hostile = source.replace(
            "/usr/bin/python3 -I tools/validate_module_documentation.py",
            "/usr/bin/python3 -c 'raise SystemExit(23)'",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            makefile = Path(directory) / "Makefile"
            makefile.write_text(hostile, encoding="utf-8")
            completed = subprocess.run(
                ["make", "-f", str(makefile), "validate"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=30,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("tools/validate_repository.py", completed.stdout)


if __name__ == "__main__":
    unittest.main()
