"""Focused source and real class-aware file-context boundary regressions."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from derive_native_logind_state_policy import contract, verify_file_contexts

HERE = Path(__file__).resolve().parent


class LogindStateContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = Path(self.tmp.name)
        for name in ("native-logind-state-source.json", "ubuntu-native-file_contexts",
                     "ubuntu-real-root-file_contexts", "linux-service-file_contexts",
                     "linux-initial-calibration-file_contexts"):
            shutil.copyfile(HERE / name, self.here / name)

    def edit(self, fn):
        p = self.here / "native-logind-state-source.json"
        value = json.loads(p.read_text())
        fn(value)
        p.write_text(json.dumps(value))

    def test_normal_contract_and_exact_parent_matcher(self):
        self.assertFalse(contract(self.here)["runtime_qualified"])
        self.assertEqual(verify_file_contexts(self.here, self.here)["selected_and_negative_cases"], 20)

    def test_parent_path_cannot_be_generalized(self):
        self.edit(lambda v: v["parent"].update(path="/var/lib"))
        with self.assertRaisesRegex(ValueError, "one existing directory"):
            contract(self.here)

    def test_normal_unit_and_source_bytes_are_pinned(self):
        self.edit(lambda v: v["source_documents"][0].update(sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "normal roundtrip"):
            contract(self.here)

    def test_precreated_or_relabelled_target_is_not_a_replacement_unit(self):
        self.edit(lambda v: v["state_directory"].update(operation="precreate", fallback_transition=True))
        with self.assertRaisesRegex(ValueError, "unmodified normal unit"):
            contract(self.here)

    def test_parent_alias_cannot_cover_subtree(self):
        p = self.here / "ubuntu-native-file_contexts"
        text = p.read_text().replace(
            "/var/lib/systemd -d u:object_r:p4_linux_systemd_state_parent_t:s0",
            "/var/lib/systemd(/.*)? -d u:object_r:p4_linux_systemd_state_parent_t:s0")
        p.write_text(text)
        with self.assertRaisesRegex(ValueError, "Logind parent alias"):
            verify_file_contexts(self.here, self.here)

    def test_parent_alias_cannot_cover_regular_files(self):
        p = self.here / "ubuntu-native-file_contexts"
        p.write_text(p.read_text().replace(
            "/var/lib/systemd -d u:object_r:p4_linux_systemd_state_parent_t:s0",
            "/var/lib/systemd u:object_r:p4_linux_systemd_state_parent_t:s0"))
        with self.assertRaisesRegex(ValueError, "exact inode class"):
            verify_file_contexts(self.here, self.here)


if __name__ == "__main__":
    unittest.main()
