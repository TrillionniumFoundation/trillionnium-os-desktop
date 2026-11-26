"""Focused source and real class-aware file-context boundary regressions."""
import hashlib
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import compile_shared_kernel_policy as compiler
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


    def test_composed_sources_match_normal_package_bytes(self):
        result = compiler.verify_composed_file_contexts(self.here)
        body = b"".join((self.here / name).read_bytes()
                        for name in compiler.COMPOSED_FILE_CONTEXT_SOURCES)
        self.assertEqual(result["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(result["bytes"], len(body))
        self.assertEqual(result["conflicting_exact_specifications"], 0)
        self.assertEqual(result["identical_context_duplicates"], 0)
        self.assertTrue(result["normal_setfiles_required"])
        self.assertFalse(result["runtime_qualified"])

    def test_original_conflict_fails_before_compiler_inputs_are_opened(self):
        p = self.here / "ubuntu-real-root-file_contexts"
        p.write_bytes(p.read_bytes() +
                      b"/var/lib/systemd -d u:object_r:p4_linux_rootdir_t:s0\n")
        arguments = ["compile_shared_kernel_policy.py"]
        for option in ("--secilc", "--sepol-library", "--android-cil",
                       "--linux-board-cil", "--output"):
            arguments.extend((option, "/nonexistent-policy-preflight-input"))
        with mock.patch.object(compiler, "__file__", str(self.here / "compiler.py")), \
                mock.patch("sys.argv", arguments), \
                mock.patch.object(compiler, "compile_policy") as compile_policy:
            with self.assertRaisesRegex(ValueError, "Conflicting composed file-context.*systemd"):
                compiler.main()
            compile_policy.assert_not_called()

    def test_conflict_check_covers_every_composed_source(self):
        names = compiler.COMPOSED_FILE_CONTEXT_SOURCES
        for index in range(1, len(names)):
            with self.subTest(source=names[index]):
                p = self.here / names[index]
                before = p.read_bytes()
                try:
                    p.write_bytes(before +
                                  b"/var/lib/systemd -d u:object_r:p4_linux_rootdir_t:s0\n")
                    with self.assertRaisesRegex(ValueError, "Conflicting composed file-context"):
                        compiler.verify_composed_file_contexts(self.here)
                finally:
                    p.write_bytes(before)

    def test_same_expression_for_a_different_inode_kind_is_preserved(self):
        p = self.here / "ubuntu-real-root-file_contexts"
        p.write_bytes(p.read_bytes() +
                      b"/var/lib/systemd -- u:object_r:p4_linux_native_data_t:s0\n")
        result = compiler.verify_composed_file_contexts(self.here)
        self.assertEqual(result["conflicting_exact_specifications"], 0)
        self.assertEqual(verify_file_contexts(self.here, self.here)["selected_and_negative_cases"], 20)



if __name__ == "__main__":
    unittest.main()
