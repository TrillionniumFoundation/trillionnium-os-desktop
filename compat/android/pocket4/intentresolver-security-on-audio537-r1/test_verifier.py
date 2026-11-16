"""Counterexamples found during independent review of the capsule verifier."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("security_capsule", Path(__file__).with_name("verify.py"))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
CI_SPEC = importlib.util.spec_from_file_location("security537_ci", Path(__file__).with_name("run_ci.py"))
CI = importlib.util.module_from_spec(CI_SPEC)
CI_SPEC.loader.exec_module(CI)


class VerifierControls(unittest.TestCase):
    def log(self):
        return "\n".join(["running 4 tests"] + ["test " + n + " ... ok" for n in sorted(VERIFY.TESTS)] + [
            "test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 274 filtered out; finished in 0.05s", ""])

    def test_complete_four_test_log_is_accepted(self):
        self.assertEqual(VERIFY.focused_test_log(self.log()), sorted(VERIFY.TESTS))

    def test_extra_failure_ignore_duplicate_or_truncated_terminal_is_rejected(self):
        text = self.log()
        cases = {
            "failed-summary-after-success": text + "test result: FAILED. 0 passed; 1 failed; 0 ignored;\n",
            "extra-failed-test": text + "test other::failure ... FAILED\n",
            "extra-ignored-test": text + "test other::ignored ... ignored\n",
            "extra-passing-test": text + "test other::pass ... ok\n",
            "duplicate-summary": text + text.splitlines()[-1] + "\n",
            "wrong-harness-count": text.replace("running 4 tests", "running 5 tests"),
            "ignored-expected-test": text.replace(" ... ok", " ... ignored", 1),
            "failed-expected-test": text.replace(" ... ok", " ... FAILED", 1),
            "truncated-summary": text.rsplit("; finished in", 1)[0] + "\n",
            "no-summary": "\n".join(text.splitlines()[:-1]),
        }
        for name, log in cases.items():
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                VERIFY.focused_test_log(log)

    def test_output_alias_and_input_tree_and_existing_reports_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            alias = root / "alias"
            alias.symlink_to(source, target_is_directory=True)
            existing = root / "report.json"
            existing.write_text("original\n")
            for path in (alias / "new", source / "new", existing):
                with self.subTest(path=path), self.assertRaises(RuntimeError):
                    VERIFY.fresh_destination(path, [source])
            self.assertEqual(VERIFY.fresh_destination(root / "fresh", [source]), root / "fresh")
            self.assertEqual(existing.read_text(), "original\n")
            self.assertEqual(list(source.iterdir()), [])

    def test_malformed_or_duplicate_harness_records_are_rejected(self):
        text = self.log()
        records = [line for line in text.splitlines() if line.startswith("test ") and not line.startswith("test result:")]
        for bad in (text + "running incomplete\n", text.replace(records[1], records[0]),
                    text + "test result: incomplete\n", text.replace(" ... ok", " ... unknown", 1)):
            with self.subTest(log=bad), self.assertRaises(RuntimeError):
                VERIFY.focused_test_log(bad)

    def test_duplicate_json_keys_and_noncanonical_source_paths_are_rejected(self):
        with self.assertRaises(RuntimeError):
            VERIFY.decode('{"mode":"100644","mode":"100755"}')
        for name in ("../x", "/x", "x//y", "x/./y", "x/.git/index", "x\\y"):
            with self.subTest(path=name), self.assertRaises(RuntimeError):
                VERIFY.safe(name)

    def test_whole_source_members_modes_and_input_F9_are_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "producer"
            source.mkdir()
            (source / ".git").mkdir()
            (source / ".git" / "private-index").write_text("ignored root Git metadata")
            path = source / "input.txt"
            raw = b"fixed original\n"
            path.write_bytes(raw)
            path.chmod(0o644)
            rows = [{"path": "input.txt", "mode": "100644", **VERIFY.digest(raw), "git_blob": VERIFY.object_id("blob", raw)}]
            tree = VERIFY.tree_id(rows)
            before = VERIFY.source_snapshot(source, rows, tree)
            extra = source / "extra-empty-directory"
            extra.mkdir()
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(source, rows, tree)
            extra.rmdir()
            path.chmod(0o664)
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(source, rows, tree)
            path.chmod(0o644)
            self.assertNotEqual(VERIFY.source_snapshot(source, rows, tree), before)
            path.write_bytes(b"changed bytes\n")
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(source, rows, tree)
            path.write_bytes(raw)
            nested = source / "nested" / ".git"
            nested.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(source, rows, tree)

    def test_CI_requires_fresh_separate_target_and_canonical_producer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            producer = root / "producer"
            producer.mkdir()
            alias = root / "alias"
            alias.symlink_to(producer, target_is_directory=True)
            stale = root / "stale-target"
            stale.mkdir()
            cases = [(alias, root / "fresh", root / "report.json"),
                     (producer, stale, root / "report.json"),
                     (producer, producer / "target", root / "report.json"),
                     (producer, root / "target", root / "target" / "report.json")]
            for recipe, target, report in cases:
                with self.subTest(target=target), self.assertRaises(RuntimeError):
                    CI.destinations(recipe, target, report)
            result = CI.destinations(producer, root / "fresh-target", root / "report.json")
            self.assertEqual(result[1], root / "fresh-target")
            self.assertFalse((root / "fresh-target").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
