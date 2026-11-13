#!/usr/bin/env python3
"""Regression controls for contradictory terminals and input/output aliasing."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


def load(name):
    path = Path(__file__).parent / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ci = load('run_ci_tests')
replay = load('replay_capsule')


class GateRegressionTests(unittest.TestCase):
    def test_contradictory_test_terminals_are_rejected(self):
        names = {'android::tests::audio_one', 'android::tests::audio_two'}
        valid = 'running 2 tests\ntest android::tests::audio_one ... ok\ntest android::tests::audio_two ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 90 filtered out; finished in 0.01s\n'
        self.assertEqual(ci.test_terminal(valid, names)['names'], sorted(names))
        bad = [valid + 'test unexpected ... FAILED\n', valid + 'test unexpected ... ignored, unavailable\n',
               valid + 'test android::tests::audio_one ... ok\n', valid + valid.splitlines()[-1] + '\n',
               valid.replace('2 passed', '1 passed'), valid.replace('0 failed', '1 failed'),
               valid.replace('0 ignored', '1 ignored'), valid.replace('running 2 tests', 'running 3 tests'),
               valid.replace('audio_two ... ok', 'audio_two ... ignored'),
               valid.replace('audio_two ... ok', 'audio_other ... ok'),
               valid.replace('audio_two ... ok', 'audio_two ... ok extra')]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                ci.test_terminal(text, names)

    def test_alias_and_input_overwrite_rejected_by_both_writers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'source'
            source.mkdir()
            existing = source / 'input'
            existing.write_text('original')
            alias = root / 'source-alias'
            alias.symlink_to(source, target_is_directory=True)
            for writer in [ci.fresh_destination, replay.fresh_destination]:
                for bad in [source / 'output', existing, alias / 'output']:
                    with self.subTest(writer=writer.__module__, path=bad), self.assertRaises(RuntimeError):
                        writer(bad, [source])
                self.assertEqual(writer(root / 'fresh', [source]), root / 'fresh')
            self.assertEqual(existing.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
