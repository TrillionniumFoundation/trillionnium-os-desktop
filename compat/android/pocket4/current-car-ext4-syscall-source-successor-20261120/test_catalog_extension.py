#!/usr/bin/env python3
"""Pure controls for the single explicitly ignored disposable syscall case."""
import ast
import copy
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
if not (HERE / 'verify.py').is_file():
    HERE = HERE / 'packet'
PARENT = HERE.parent / 'current-owned-persistent-data-successor-20261120'
if not PARENT.is_dir():
    # Local source-review layout. The published CI layout uses the fixed sibling.
    PARENT = HERE.parent.parent / 'p4_joint_compile_fix_r2' / 'packet'
CASE = 'production_namespace::tree::tests::persistent_syscalls::privileged_private_persistent_data_syscall_controls'


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


class ExactIgnoredCatalogControls(unittest.TestCase):
    def setUp(self):
        self.parent = json.loads((PARENT / 'EXPECTED-CATALOG.json').read_bytes())
        self.additions = json.loads((HERE / 'NEW-TESTS.json').read_bytes())
        self.ignored = json.loads((HERE / 'NEW-IGNORED.json').read_bytes())
        tree = ast.parse((HERE / 'verify.py').read_bytes())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'complete_catalog']
        self.assertEqual(len(nodes), 1)
        # Compile only the pure catalog function; importing runtime or source
        # constructors is neither necessary nor allowed by these controls.
        self.globals = {'need': need, 'HERE': HERE, 'decode': json.loads,
            'regular': lambda p: json.dumps(self.ignored).encode() if p == HERE / 'NEW-IGNORED.json'
                else (_ for _ in ()).throw(RuntimeError('unexpected control read'))}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(HERE / 'verify.py'), 'exec'), self.globals)

    def call(self):
        return self.globals['complete_catalog'](copy.deepcopy(self.parent), copy.deepcopy(self.additions))

    def test_preserves_every_original_case_and_adds_exactly_one_unexecuted_fixture(self):
        result = self.call()
        expected = json.loads((HERE / 'EXPECTED-CATALOG.json').read_bytes())
        self.assertEqual(result, expected)
        before = {(r['package'], r['target'], n) for r in self.parent for n in r['ignored']}
        after = {(r['package'], r['target'], n) for r in result for n in r['ignored']}
        self.assertEqual(after, before | {('droidloom-supervisor', 'droidloom_supervisor', CASE)})
        self.assertEqual(len(before), 30)
        self.assertEqual(sum(len(r['all']) - len(r['ignored']) for r in result), 1629)
        self.assertNotIn(CASE, {n for r in result for n in set(r['all']) - set(r['ignored'])})

    def test_metadata_cannot_authorize_execution_change_identity_or_use_numeric_booleans(self):
        original = copy.deepcopy(self.ignored)
        variants = [
            {'case': CASE + '_other'}, {'package': 'droidloom-applications'},
            {'target': 'another_target'}, {'execution_authorized_by_this_packet': True},
            {'execution_authorized_by_this_packet': 0}, {'compiled_and_listed_only': 1},
            {'compiled_and_listed_only': False}, {'extra': False},
        ]
        for change in variants:
            with self.subTest(change=change):
                self.ignored = {**original, **change}
                with self.assertRaises(RuntimeError):
                    self.call()

    def test_existing_ignored_or_ordinary_case_cannot_be_hidden_or_replaced(self):
        parent = copy.deepcopy(self.parent)
        target = next(r for r in self.parent if r['package'] == 'droidloom-supervisor' and r['target'] == 'droidloom_supervisor')
        target['all'].append(CASE)
        target['all'].sort()
        with self.assertRaises(RuntimeError):
            self.call()
        self.parent = copy.deepcopy(parent)
        target = next(r for r in self.parent if r['ignored'])
        target['ignored'].pop()
        with self.assertRaises(RuntimeError):
            self.call()
        self.parent = copy.deepcopy(parent)
        self.additions[0]['tests'].pop()
        with self.assertRaises(RuntimeError):
            self.call()


if __name__ == '__main__':
    unittest.main(verbosity=2)
