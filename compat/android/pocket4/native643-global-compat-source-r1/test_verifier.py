"""Narrow controls for the current Native capsule and CI terminal boundaries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('native_current_verify', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class Controls(unittest.TestCase):
    def test_exact_terminal_and_all_contradictory_counterexamples(self):
        text = 'running 2 tests\ntest a ... ok\ntest b ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 4 filtered out; finished in 0.10s\n'
        self.assertEqual(VERIFY.test_terminal(text, {'a', 'b'}), 2)
        cases = [text + 'test extra ... FAILED\n', text + 'test extra ... ignored\n',
                 text + 'test extra ... ok\n', text + 'test result: FAILED. 0 passed; 1 failed;\n',
                 text + text.splitlines()[-1] + '\n', text.replace('running 2 tests', 'running 3 tests'),
                 text.replace('test b ... ok', 'test a ... ok'), text.replace(' ... ok', ' ... ignored', 1),
                 text.replace(' ... ok', ' ... FAILED', 1), text.rsplit('; finished in', 1)[0],
                 text + 'running incomplete\n']
        for value in cases:
            with self.subTest(log=value), self.assertRaises(RuntimeError):
                VERIFY.test_terminal(value, {'a', 'b'})

    def test_fresh_output_cannot_alias_input_or_existing_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            alias = root / 'alias'
            alias.symlink_to(source, target_is_directory=True)
            exists = root / 'existing'
            exists.write_text('preserved')
            for path in (alias / 'new', source / 'new', exists):
                with self.subTest(path=path), self.assertRaises(RuntimeError):
                    VERIFY.fresh_destination(path, [source])
            self.assertEqual(VERIFY.fresh_destination(root / 'fresh', [source]), root / 'fresh')

    def test_original_blob_mode_membership_and_F9_are_independent_guards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            p = root / 'source.rs'
            raw = b'// original source\n'
            p.write_bytes(raw)
            p.chmod(0o644)
            row = {'path': 'source.rs', 'git_mode': '100644', **VERIFY.digest(raw),
                   'git_blob': VERIFY.hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
            before = VERIFY.source_snapshot(root, [row], 1)
            p.chmod(0o755)
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(root, [row], 1)
            p.chmod(0o644)
            self.assertNotEqual(VERIFY.source_snapshot(root, [row], 1), before)
            (root / 'extra').write_text('not an original')
            with self.assertRaises(RuntimeError):
                VERIFY.source_snapshot(root, [row], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
