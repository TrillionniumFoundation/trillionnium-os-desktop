"""Exercise the real file-context matcher, without running native services."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from derive_native_sysusers_policy import contract, verify_file_contexts


class NativeSysusersPaths(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.here = self.work / "inputs"
        self.here.mkdir()
        source = Path(__file__).resolve().parent
        for name in ("native-sysusers-source.json", "ubuntu-native-file_contexts",
                     "ubuntu-real-root-file_contexts", "linux-service-file_contexts",
                     "linux-initial-calibration-file_contexts"):
            shutil.copyfile(source / name, self.here / name)

    def test_existing_lock_and_etc_root_keep_class_and_neighbor_boundaries(self):
        report = verify_file_contexts(self.here, self.work)
        self.assertEqual(report["selected_and_negative_cases"], 29)

    def test_regular_lock_alias_cannot_match_a_link_or_directory(self):
        path = self.here / "ubuntu-native-file_contexts"
        text = path.read_text()
        old = r"/etc/\.pwd\.lock -- u:object_r:p4_linux_sysusers_passwd_lock_t:s0"
        self.assertEqual(text.count(old), 1)
        path.write_text(text.replace(old, old.replace(" -- ", " ")))
        with self.assertRaisesRegex(ValueError, "inode class"):
            verify_file_contexts(self.here, self.work)

    def test_lock_alias_cannot_extend_to_an_adjacent_config_file(self):
        path = self.here / "ubuntu-native-file_contexts"
        text = path.read_text()
        old = r"/etc/\.pwd\.lock -- u:object_r:p4_linux_sysusers_passwd_lock_t:s0"
        self.assertEqual(text.count(old), 1)
        path.write_text(text.replace(old, old.replace(r"\.lock --", r"\.lock.* --")))
        with self.assertRaisesRegex(ValueError, "unrelated path"):
            verify_file_contexts(self.here, self.work)

    def test_normal_lock_contract_refuses_body_or_replacement_metadata(self):
        path = self.here / "native-sysusers-source.json"
        original = path.read_bytes()
        for key, replacement in (("bytes", 1), ("nlink", 2), ("mode", 0o666),
                                 ("class", "lnk_file"), ("path", "/etc/passwd")):
            value = json.loads(original)
            value["existing_objects"][1][key] = replacement
            path.write_text(json.dumps(value))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "existing empty lock"):
                contract(self.here)


if __name__ == "__main__":
    unittest.main(verbosity=2)
