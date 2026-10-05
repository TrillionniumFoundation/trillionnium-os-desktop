"""PR merge checkout uses the immutable event object before any source code."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class S07EventCheckoutTests(unittest.TestCase):
    def test_exact_event_checkout_and_pull_only_job_keep_original_live_parent_guard(self):
        path = ROOT / ".github/workflows/s07-servo-retained-node.yml"
        workflow = yaml.load(path.read_bytes(), Loader=yaml.BaseLoader)
        job = workflow["jobs"]["prospective-merge-patch-package"]
        self.assertEqual(job["if"], "${{ github.event_name == 'pull_request' }}")
        checkout = job["steps"][0]
        self.assertEqual(checkout["with"], {
            "ref": "${{ github.sha }}", "fetch-depth": "2", "persist-credentials": "false",
        })
        self.assertEqual(checkout["uses"], "actions/checkout@11d5960a326750d5838078e36cf38b85af677262")
        self.assertNotIn("pull_request.number", checkout["with"]["ref"])
        guard = job["steps"][1]
        self.assertEqual(guard["env"]["CI_SOURCE_ROLE"], "prospective-merge")
        self.assertEqual(guard["run"], "set -euo pipefail\npython3 -B tools/verify_ci_source_identity.py\n")
        lineage = job["steps"][2]
        self.assertEqual(lineage["env"]["EXPECTED_MERGE_SHA"], "${{ github.sha }}")
        for constraint in [
            'test "$(git rev-parse HEAD)" = "$EXPECTED_MERGE_SHA"',
            'test "$(git rev-list --parents -n1 HEAD | awk \'{print NF - 1}\')" -eq 2',
            'test "$(git rev-parse HEAD^1)" = "$EXPECTED_BASE_SHA"',
            'test "$(git rev-parse HEAD^2)" = "$EXPECTED_HEAD_SHA"',
            'test "$live_base" = "$EXPECTED_BASE_SHA"',
            'test "$live_head" = "$EXPECTED_HEAD_SHA"',
        ]:
            self.assertIn(constraint, lineage["run"])


if __name__ == "__main__":
    unittest.main()
