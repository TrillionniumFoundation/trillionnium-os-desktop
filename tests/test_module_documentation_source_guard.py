"""The source guard is the sole closed exception before the trusted validator."""
from __future__ import annotations

import unittest

from tools import validate_module_documentation as validator


JOBS = ("repository-contracts", "repository-contracts-prospective-merge", "exact-head", "prospective-merge")


def workflow(job: str, guard: str) -> str:
    condition = "    if: github.event_name == 'pull_request'\n" if "prospective" in job else ""
    return ("name: private source shape\npermissions:\n  contents: read\njobs:\n"
            f"  {job}:\n    runs-on: ubuntu-24.04\n{condition}    steps:\n"
            "      - name: Checkout\n"
            f"        uses: {validator.PINNED_CHECKOUT}\n        with:\n"
            "          ref: ${{ github.sha }}\n          fetch-depth: 2\n          persist-credentials: false\n"
            + guard + "      - name: Validate\n        run: /usr/bin/python3 -I tools/validate_module_documentation.py\n")


def source_guard(job: str) -> str:
    role = "prospective-merge" if "prospective" in job else "head"
    fields = [("CI_SOURCE_ROLE", role), ("CI_SOURCE_EVENT", "${{ github.event_name }}"),
              ("CI_SOURCE_REPOSITORY", "${{ github.repository }}"), ("CI_SOURCE_REF", "${{ github.ref }}"),
              ("CI_SOURCE_REF_NAME", "${{ github.ref_name }}"), ("CI_SOURCE_SHA", "${{ github.sha }}"),
              ("CI_SOURCE_PR_NUMBER", "${{ github.event.pull_request.number }}"),
              ("CI_SOURCE_PR_HEAD", "${{ github.event.pull_request.head.sha }}"),
              ("CI_SOURCE_PR_BASE", "${{ github.event.pull_request.base.sha }}"),
              ("CI_SOURCE_BASE_REF", "${{ github.event.pull_request.base.ref }}")]
    return ("      - name: Verify canonical live source role\n        shell: bash\n        env:\n"
            + "".join(f"          {key}: {value}\n" for key, value in fields)
            + "        run: |\n          set -euo pipefail\n          python3 -B tools/verify_ci_source_identity.py\n")


class ClosedSourceGuardTests(unittest.TestCase):
    def test_exact_guard_and_original_validator_shape_pass_in_all_four_jobs(self):
        for job in JOBS:
            with self.subTest(job=job):
                self.assertTrue(validator._job_executes(workflow(job, source_guard(job)), job))
                self.assertTrue(validator._job_executes(workflow(job, ""), job))

    def test_mutated_role_command_fields_skip_or_extra_run_refuse(self):
        for job in JOBS:
            guard = source_guard(job)
            mutants = [guard.replace("python3 -B tools/verify_ci_source_identity.py", "true"),
                       guard.replace("CI_SOURCE_ROLE:", "CI_SOURCE_alias:"),
                       guard.replace("CI_SOURCE_EVENT: ${{ github.event_name }}", "CI_SOURCE_EVENT: workflow_dispatch"),
                       guard.replace("        shell: bash", "        shell: bash\n        if: false"),
                       guard.replace("        shell: bash", "        shell: bash\n        continue-on-error: true"),
                       guard.replace("        env:\n", "        env:\n          PYTHONPATH: /tmp/override\n"),
                       guard.replace("          set -euo pipefail\n", "          exit 0\n          set -euo pipefail\n"),
                       guard + "      - name: prior mutation\n        run: true\n", guard + guard]
            role = "prospective-merge" if "prospective" in job else "head"
            mutants.append(guard.replace(f"CI_SOURCE_ROLE: {role}", "CI_SOURCE_ROLE: event-source"))
            for line in guard.splitlines(keepends=True):
                if "CI_SOURCE_" in line:
                    mutants.extend([guard.replace(line, ""), guard.replace(line, line + line)])
            for mutated in mutants:
                with self.subTest(job=job, mutated=mutated):
                    self.assertFalse(validator._job_executes(workflow(job, mutated), job))

    def test_guard_after_validator_or_second_checkout_refuse(self):
        for job in JOBS:
            guard = source_guard(job)
            text = workflow(job, "") + guard
            self.assertFalse(validator._job_executes(text, job))
            extra = "      - name: later checkout\n        uses: actions/checkout@v4\n"
            self.assertFalse(validator._job_executes(workflow(job, extra + guard), job))


if __name__ == "__main__":
    unittest.main()
