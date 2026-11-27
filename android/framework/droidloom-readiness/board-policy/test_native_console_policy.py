"""Exact shared console-cache transition and source-contract regressions."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import derive_native_console_policy as console
import derive_native_ldconfig_policy as ldconfig
import compile_shared_kernel_policy as compiler
import verify_original_once as once

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


class OriginalOnceSourceContract(unittest.TestCase):
    """Reject stale console closure pins before expensive linking and again after it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.here = self.root / "android/framework/droidloom-readiness/board-policy"
        for relative in once.SOURCE_PATHS:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE.parents[3] / relative, target)
        self.manifest = self.here / "original-once-source.json"
        shutil.copyfile(HERE / self.manifest.name, self.manifest)
        self.console = self.here / "derive_native_console_policy.py"
        for name in compiler.COMPOSED_FILE_CONTEXT_SOURCES:
            shutil.copyfile(HERE / name, self.here / name)

    def compiler_args(self):
        return ["compile_shared_kernel_policy.py", "--secilc", "/missing/secilc",
                "--sepol-library", "/missing/libsepol.so.2", "--android-cil",
                "/missing/android.cil", "--linux-board-cil", "/missing/board.cil",
                "--output", str(self.root / "must-not-be-produced.policy")]

    def test_current_console_is_in_complete_original_once_closure(self):
        expected = json.loads(self.manifest.read_text())["files"]
        self.assertEqual(once.verify_sources(self.here), expected)
        self.assertEqual(set(expected), set(once.SOURCE_PATHS))
        self.assertEqual(expected["android/framework/droidloom-readiness/board-policy/"
                                  "derive_native_console_policy.py"]["sha256"],
                         hashlib.sha256(self.console.read_bytes()).hexdigest())

    def test_historical_console_pin_reproduces_failure(self):
        contract = json.loads(self.manifest.read_text())
        contract["files"]["android/framework/droidloom-readiness/board-policy/"
                          "derive_native_console_policy.py"] = {
            "bytes": 29713,
            "sha256": "3bcc8eb3139f1819bb20fc1ad895cecf6ba3f0c9f850d93c6cdf8459101e6777"}
        self.manifest.write_text(json.dumps(contract))
        with self.assertRaisesRegex(ValueError, "Changed original-once source: .*derive_native_console_policy"):
            once.verify_sources(self.here)

    def test_changed_bytes_and_changed_length_remain_rejected(self):
        original = self.console.read_bytes()
        for body in (original + b"\n", b"!" + original[1:]):
            with self.subTest(bytes=len(body)):
                self.console.write_bytes(body)
                with self.assertRaisesRegex(ValueError, "Changed original-once source"):
                    once.verify_sources(self.here)

    def test_main_rejects_changed_source_before_compiler_or_work_directory(self):
        self.console.write_bytes(self.console.read_bytes() + b"\n")
        with mock.patch.object(compiler, "__file__", str(self.here / "compile_shared_kernel_policy.py")), \
                mock.patch.object(sys, "argv", self.compiler_args()), \
                mock.patch.object(compiler.subprocess, "run") as external, \
                mock.patch.object(compiler, "policy_work_directory") as workspace:
            with self.assertRaisesRegex(ValueError, "Changed original-once source"):
                compiler.main()
            external.assert_not_called()
            workspace.assert_not_called()
        self.assertFalse((self.root / "must-not-be-produced.policy").exists())

    def test_valid_source_reaches_following_source_check(self):
        class FollowingBoundary(Exception):
            pass
        with mock.patch.object(compiler, "__file__", str(self.here / "compile_shared_kernel_policy.py")), \
                mock.patch.object(sys, "argv", self.compiler_args()), \
                mock.patch.object(compiler, "validate_netplan_trigger_sources",
                                  side_effect=FollowingBoundary) as following:
            with self.assertRaises(FollowingBoundary):
                compiler.main()
            following.assert_called_once_with(self.here)

    def test_post_link_verifier_still_rejects_a_later_source_change(self):
        once.verify_sources(self.here)
        self.console.write_bytes(self.console.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Changed original-once source"):
            once.verify_original_once(None, None, None, None, self.here)


if __name__ == "__main__":
    unittest.main()
