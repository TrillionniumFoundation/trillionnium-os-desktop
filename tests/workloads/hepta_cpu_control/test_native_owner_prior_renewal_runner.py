"""Explicit execution admission checks, with no actual guest fixture."""
import contextlib
import io
import json
import unittest

import run_native_owner_prior_renewal as runner


class PriorRenewalRunnerAdmissionTests(unittest.TestCase):
    def test_disabled_runner_reports_no_native_cycle_or_persistence_qualification(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = runner.main([])
        value = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(value["scenario"], "prior-boot-unknown-renewal-v1")
        for name in ("passed", "native_execution_attempted", "graceful_owner_release_verified",
                     "bounded_renewal_beyond_both_initial_grants_verified", "original_native_owner_cycle_verified",
                     "cross_boot_unknown_preservation_verified", "root_launch_files_verified", "g2_complete"):
            self.assertFalse(value[name], name)

    def test_execution_without_complete_actual_build_inputs_is_rejected_before_io(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_status:
            runner.main(["--execute"])
        self.assertEqual(exit_status.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
