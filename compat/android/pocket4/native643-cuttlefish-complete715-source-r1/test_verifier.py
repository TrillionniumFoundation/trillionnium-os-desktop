#!/usr/bin/env python3
"""Finite verifier rejection controls; these do not replace the fresh Rust CI."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('native715_control_verify', HERE / 'verify.py')
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)
SPEC_CI = importlib.util.spec_from_file_location('native715_control_ci', HERE / 'run-normal-controls.py')
C = importlib.util.module_from_spec(SPEC_CI)
SPEC_CI.loader.exec_module(C)


class VerificationControls(unittest.TestCase):
    def test_complete_rust_terminal_and_contradictions(self):
        good = 'running 1 test\ntest exact::control ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 7 filtered out; finished in 0.01s\n'
        self.assertEqual(V.test_terminal(good, ['exact::control']), 1)
        bad = [good + 'test foreign ... FAILED\n', good + 'test foreign ... ignored\n',
               good + 'test malformed\n', good + 'running 0 tests\n', good + 'test result: FAILED\n',
               good.replace('0 failed', '1 failed'), good.replace('0 ignored', '1 ignored'),
               good.replace('running 1 test', 'running 2 tests'), good.replace('... ok', '... ignored'),
               good.replace('exact::control', 'foreign::control'), good.split('test result:')[0]]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                V.test_terminal(text, ['exact::control'])

    def test_complete_cargo_terminal_and_contradictions(self):
        terminal = {'reason': 'build-finished', 'success': True}
        good = (json.dumps(terminal) + '\n').encode()
        self.assertEqual(V.successful_cargo_stream(good), [terminal])
        bad = [b'', good + good, good + b'{"reason":"other"}\n',
               good.replace(b'true', b'false'),
               b'{"reason":"compiler-message","message":{"level":"error"}}\n' + good]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                V.successful_cargo_stream(raw)

    def test_duplicate_json_and_unsafe_members(self):
        with self.assertRaises(RuntimeError):
            V.decode(b'{"schema":1,"schema":2}')
        for name in ('../escape', '/absolute', 'nested/.git/config', 'a//b', 'a\\b', 'bad\x00name'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                V.safe(name)

    def test_fresh_output_rejects_input_and_parent_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            inputs = root / 'inputs'
            inputs.mkdir()
            alias = root / 'alias'
            alias.symlink_to(inputs, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                V.fresh_destination(inputs / 'new', [inputs])
            with self.assertRaises(RuntimeError):
                V.fresh_destination(alias / 'new', [])
            with self.assertRaises(RuntimeError):
                V.fresh_destination(inputs, [])
            self.assertEqual(V.fresh_destination(root / 'new', [inputs]), root / 'new')

    def test_complete_root_rejects_extra_directory_and_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            data = b'original source\n'
            source = root / 'source.rs'
            source.write_bytes(data)
            source.chmod(0o644)
            row = {'path': 'source.rs', 'mode': '100644', 'git_blob': V.object_id('blob', data), **V.digest(data)}
            tree = V.tree_id([row])
            before = V.source_snapshot(root, [row], tree)
            self.assertEqual(len(before['files']), 1)
            extra = root / 'untracked-empty'
            extra.mkdir()
            with self.assertRaises(RuntimeError):
                V.source_snapshot(root, [row], tree)
            extra.rmdir()
            source.chmod(0o755)
            with self.assertRaises(RuntimeError):
                V.source_snapshot(root, [row], tree)

    def test_only_root_git_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / '.git').mkdir()
            self.assertEqual(V.member_names(root, skip_root_git=True)[0], set())
            (root / 'nested').mkdir()
            (root / 'nested/.git').mkdir()
            with self.assertRaises(RuntimeError):
                V.member_names(root, skip_root_git=True)

    def test_cargo_links_must_stay_in_current_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / 'target'
            (target / 'debug/deps').mkdir(parents=True)
            binary = target / 'debug/droidloom-update'
            binary.write_bytes(b'\x7fELF' + b'controlled finite identity fixture')
            binary.chmod(0o755)
            alias = target / 'debug/deps/droidloom_update-controlled'
            os.link(binary, alias)
            proof = C.cargo_executable(binary, target, 'droidloom-update')
            self.assertEqual(len(proof['bounded_private_Cargo_aliases']), 2)
            alias.unlink()
            os.link(binary, root / 'outside-target')
            with self.assertRaises(RuntimeError):
                C.cargo_executable(binary, target, 'droidloom-update')

    def test_real_test_catalog_has92_distinct98_executions(self):
        manifest = V.decode(V.regular(HERE / 'manifest.json'))
        tests = V.test_catalogs(manifest)
        self.assertEqual(sum(len(tests[key]) for key in ('pair', 'source', 'permissions', 'journal')), 92)
        self.assertEqual(sum(len(value) for value in tests.values()), 98)


if __name__ == '__main__':
    unittest.main()
