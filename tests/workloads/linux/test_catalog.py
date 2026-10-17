"""Machine-readable A04 workload contract regressions."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_catalog", HERE / "catalog.py")
catalog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(catalog)


class WorkloadCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog.load_json(catalog.DEFAULT_CATALOG)
        cls.reference = catalog.load_json(catalog.DEFAULT_REFERENCE)

    def test_catalog_matches_every_reference_case_and_required_interfaces(self):
        summary = catalog.validate(self.catalog, self.reference)
        self.assertEqual(summary["catalog_workload_count"], 32)
        self.assertEqual(summary["reference_case_count"], 32)
        self.assertEqual(summary["reference_counts"], {"pass": 31, "fail": 0, "not_run": 1})
        self.assertEqual(summary["workloads_by_class"], {"elf": 28, "python": 3, "rust": 1})
        self.assertTrue(set(summary["required_interfaces"]).issubset(summary["interfaces"]))

    def test_release_facts_are_bound_to_the_pinned_reference(self):
        for item in self.catalog["workloads"]:
            reference = self.reference["cases"][item["id"]]
            if reference["status"] != "pass":
                self.assertEqual(item["id"], "rust_tokio")
                self.assertIn("qualification_blocker", item)
                continue
            facts = reference["facts"]
            self.assertTrue(facts["ok"], item["id"])
            for key in item["release_fact_keys"]:
                self.assertIn(key, facts, item["id"])

    def test_commands_are_argument_vectors_and_do_not_hide_shell_execution(self):
        forbidden = {";", "&&", "||", "|", ">", "`", "$()"}
        placeholders = {"<binary>", "<scratch>", "<report>"}
        for item in self.catalog["workloads"]:
            command = item["command"]
            self.assertIsInstance(command, list)
            self.assertTrue(command, item["id"])
            for token in command:
                self.assertIsInstance(token, str)
                if token not in placeholders:
                    self.assertFalse(any(fragment in token for fragment in forbidden), item["id"])

    def test_catalog_has_no_duplicate_ids_on_disk(self):
        ids = [item["id"] for item in self.catalog["workloads"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
