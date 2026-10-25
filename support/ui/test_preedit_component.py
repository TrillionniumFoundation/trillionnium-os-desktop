"""Reject empty/misdirected SDK tests and restore disposable locks on failure."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preedit_component as component


def output(names, summary="ok. 4 passed; 0 failed; 0 ignored;"):
    return ("test result: ok. 0 passed; 0 failed; 0 ignored; 7 filtered out;\n"
            + "".join("test " + name + " ... ok\n" for name in names)
            + "test result: " + summary + " 0 measured; 9 filtered out\n")


class PreeditComponentTests(unittest.TestCase):
    def setUp(self):
        self.names = ["window::focus_tests::case_" + str(index) for index in range(4)]

    def test_actual_scope_passes_with_empty_shell_feature_anchor(self):
        checked = component.require_test_results(output(self.names), 4, "window::focus_tests")
        self.assertEqual(checked["passed"], 4)
        self.assertEqual(checked["libtest_summaries"], 2)
        text_names = ["text_input::composition_undo_tests::case_" + str(index) for index in range(35)]
        checked = component.require_test_results(output(text_names, "ok. 35 passed; 0 failed; 0 ignored;"), 35, "text_input::")
        self.assertEqual(checked["passed"], 35)

    def test_zero_missing_failed_and_ignored_results_are_refused(self):
        cases = ["", "test result: ok. 0 passed; 0 failed; 0 ignored;\n",
                 output(self.names, "FAILED. 3 passed; 1 failed; 0 ignored;"),
                 output(self.names, "ok. 3 passed; 0 failed; 1 ignored;")]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                component.require_test_results(text, 4, "window::focus_tests")

    def test_pass_count_from_another_package_or_duplicate_names_is_refused(self):
        for names in (["other_package::case_" + str(index) for index in range(4)],
                      [self.names[0]] * 4, self.names[:3]):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "named widgets scope"):
                component.require_test_results(output(names), 4, "window::focus_tests")

    def test_sdk_commands_use_the_explicit_feature_and_both_real_widget_scopes(self):
        profile = {"sdk_profile": "preedit-callbacks", "cargo_feature": "trill-shell/hepta-native-preedit-sdk"}
        commands = component.sdk_test_commands(profile, ["--locked", "--offline"])
        self.assertEqual([(scope, count) for _name, _command, scope, count in commands],
                         [("window::focus_tests", 4), ("text_input::", 35)])
        for _name, command, _scope, _count in commands:
            self.assertIn("makepad-widgets", command)
            self.assertIn("trill-shell", command)
            self.assertIn(profile["cargo_feature"], command)
            self.assertIn("--locked", command)
            self.assertIn("--offline", command)
        with self.assertRaises(ValueError):
            component.sdk_test_commands({"sdk_profile": "baseline"}, [])

    def check_restore(self, outcome):
        with tempfile.TemporaryDirectory(prefix="trill-component-lock-") as directory:
            root = Path(directory)
            (root / "ui").mkdir()
            lock = root / "ui/Cargo.lock"
            before = b"version = 4\n# exact committed lock bytes\n"
            lock.write_bytes(before)
            try:
                with component.restored_lock(root):
                    lock.write_bytes(b"# transient Cargo-generated SDK path lock\n")
                    outcome(root)
            except (ValueError, InterruptedError):
                pass
            self.assertEqual(lock.read_bytes(), before)
            self.assertFalse(lock.is_symlink())
            if (root / "unrelated").exists():
                self.assertEqual((root / "unrelated").read_bytes(), b"unrelated bytes")
            self.assertFalse((lock.parent / ".Cargo.lock.preedit-restore").exists())

    def test_successful_temporary_lock_resolution_restores_original_bytes(self):
        self.check_restore(lambda _root: None)

    def test_zero_test_rejection_restores_original_lock(self):
        self.check_restore(lambda _root: component.require_test_results(
            "test result: ok. 0 passed; 0 failed; 0 ignored;\n", 4, "window::focus_tests"))

    def test_failed_test_and_signal_interruption_restore_original_lock(self):
        def interrupted(_root):
            raise InterruptedError("synthetic SIGTERM delivered during test wait")
        self.check_restore(interrupted)
        self.check_restore(lambda _root: component.require_test_results(
            output(self.names, "FAILED. 0 passed; 4 failed; 0 ignored;"), 4, "window::focus_tests"))

    def test_restoration_replaces_a_link_without_overwriting_its_target(self):
        def substitute(root):
            target = root / "unrelated"
            target.write_bytes(b"unrelated bytes")
            lock = root / "ui/Cargo.lock"
            lock.unlink()
            lock.symlink_to(target)
        self.check_restore(substitute)


if __name__ == "__main__":
    unittest.main()
