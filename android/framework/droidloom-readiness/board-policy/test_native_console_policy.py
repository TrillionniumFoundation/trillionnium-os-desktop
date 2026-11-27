"""Exact shared console-cache transition and source-contract regressions."""
import unittest
from pathlib import Path

import derive_native_console_policy as console
import derive_native_ldconfig_policy as ldconfig

HERE = Path(__file__).resolve().parent
CACHE_TRANSITION = ('(typetransition p4_linux_ldconfig_t '
                    'p4_linux_sysusers_etc_root_t file "ld.so.cache~" '
                    'p4_linux_console_ld_cache_native_config_t)')
INHERITED = ('(typetransition p4_linux_user_executor_t '
             'p4_linux_console_helper_native_bin_t process p4_linux_user_session_t)')


class ConsoleTransitions(unittest.TestCase):
    def complete(self):
        return console._fixed_transitions() | {CACHE_TRANSITION}

    def test_existing_ldconfig_cache_publication_is_required(self):
        lines = self.complete()
        self.assertEqual(console._verify_transitions(lines, []), len(lines))

    def test_cache_edge_matches_existing_normal_producer_and_source_contract(self):
        source = ldconfig.contract(HERE)
        self.assertFalse(source["runtime_qualified"])
        self.assertIn(CACHE_TRANSITION, ldconfig.fixed_transitions())
        self.assertEqual((HERE / "ubuntu-native-ldconfig.cil").read_text().splitlines().count(
            CACHE_TRANSITION), 1)
        self.assertIn({"path": "/etc", "mode": 0o755, "uid": 0, "gid": 0,
                       "type": "p4_linux_sysusers_etc_root_t"}, source["existing_directories"])
        self.assertEqual(source["mutable_outputs"][0], {
            "path": "/etc/ld.so.cache", "temporary": "/etc/ld.so.cache~",
            "type": "p4_linux_console_ld_cache_native_config_t",
            "temporary_mode": 0o600, "published_mode": 0o644,
            "publication": "fsync-close-rename", "fatal": True})

    def test_every_existing_transition_remains_required(self):
        for removed in self.complete():
            with self.subTest(removed=removed):
                with self.assertRaisesRegex(ValueError, "Console transition set differs"):
                    console._verify_transitions(self.complete() - {removed}, [])

    def test_source_parent_class_name_and_result_cannot_change(self):
        changes = [("p4_linux_ldconfig_t", "p4_linux_setup_t"),
                   ("p4_linux_sysusers_etc_root_t", "p4_linux_etc_dir_t"),
                   (" file ", " dir "),
                   ('"ld.so.cache~"', '"ld.so.cache"'),
                   ("p4_linux_console_ld_cache_native_config_t", "p4_linux_console_cache_native_config_t")]
        for old, new in changes:
            with self.subTest(old=old, new=new):
                changed = CACHE_TRANSITION.replace(old, new)
                with self.assertRaisesRegex(ValueError, "Console transition set differs"):
                    console._verify_transitions((self.complete() - {CACHE_TRANSITION}) | {changed}, [])

    def test_sibling_and_unnamed_cache_transitions_remain_rejected(self):
        changes = [CACHE_TRANSITION.replace('"ld.so.cache~"', '"ld.so.cache-extra~"'),
                   CACHE_TRANSITION.replace('"ld.so.cache~" ', ''),
                   CACHE_TRANSITION.replace("p4_linux_sysusers_etc_root_t", "p4_linux_rootdir_t")]
        for added in changes:
            with self.subTest(added=added):
                with self.assertRaisesRegex(ValueError, "Console transition set differs"):
                    console._verify_transitions(self.complete() | {added}, [])

    def test_other_transition_operations_do_not_gain_an_exception(self):
        for operation in ("typechange", "typemember", "roletransition"):
            with self.subTest(operation=operation):
                added = CACHE_TRANSITION.replace("(typetransition ", "(" + operation + " ", 1)
                with self.assertRaisesRegex(ValueError, "Console transition set differs"):
                    console._verify_transitions(self.complete() | {added}, [])

    def test_original_inherited_transition_is_still_exact(self):
        lines = self.complete() | {INHERITED}
        self.assertEqual(console._verify_transitions(lines, [INHERITED]), len(lines))
        with self.assertRaisesRegex(ValueError, "Console transition set differs"):
            console._verify_transitions(self.complete(), [INHERITED])
        with self.assertRaisesRegex(ValueError, "Console transition set differs"):
            console._verify_transitions(lines, [])


if __name__ == "__main__":
    unittest.main()
