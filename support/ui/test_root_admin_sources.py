"""A declared original source profile cannot omit privileged Root callees."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("root_admin_sources", Path(__file__).with_name("root_admin_sources.py"))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class RootAdminSources(unittest.TestCase):
    def test_each_original_critical_input_is_required(self):
        records = [{"path": name} for name in sorted(policy.ROOT_ADMIN_SOURCE_FILES)]
        policy.require_root_admin_sources(records)
        for missing in policy.ROOT_ADMIN_SOURCE_FILES:
            with self.subTest(missing=missing):
                with self.assertRaisesRegex(ValueError, "omits original live Root"):
                    policy.require_root_admin_sources([row for row in records if row["path"] != missing])

    def test_duplicate_paths_cannot_hide_a_missing_identity(self):
        records = [{"path": name} for name in sorted(policy.ROOT_ADMIN_SOURCE_FILES)]
        with self.assertRaisesRegex(ValueError, "Duplicate original source identity"):
            policy.require_root_admin_sources(records + records[:1])


if __name__ == "__main__":
    unittest.main()
