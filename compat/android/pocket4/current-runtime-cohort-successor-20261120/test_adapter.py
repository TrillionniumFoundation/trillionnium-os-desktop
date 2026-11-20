#!/usr/bin/env python3
"""Preserve all13 parent adapter controls and add four composition controls."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('tested_combined_cohort_adapter', HERE / 'verify.py')
V = importlib.util.module_from_spec(spec); spec.loader.exec_module(V)
parent_test = V.PARENT / 'test_adapter.py'
parent_inventory = dict((name, digest) for digest, name in
                        (line.split('  ', 1) for line in V.regular(V.PARENT / 'FILES.sha256').decode().splitlines()))
if hashlib.sha256(V.regular(parent_test)).hexdigest() != parent_inventory['test_adapter.py']:
    raise RuntimeError('the original13 adapter controls changed')
spec = importlib.util.spec_from_file_location('original2352_adapter_controls', parent_test)
OLD = importlib.util.module_from_spec(spec); spec.loader.exec_module(OLD)
# unittest discovers the unchanged classes under these local aliases.
OriginalCurrentCatalogControls = OLD.CurrentCatalogControls
OriginalFullSourceChainControls = OLD.FullSourceChainControls


class CombinedCatalogControls(unittest.TestCase):
    def setUp(self):
        self.parent = V.decode(V.regular(V.PARENT / 'EXPECTED-CATALOG.json'))
        self.additions = V.decode(V.regular(HERE / 'NEW-TESTS.json'))

    def test_all49_targets_every1534_old_case_and_all30_ignored_are_preserved(self):
        actual = V.current_catalog(self.parent, self.additions)
        self.assertEqual(actual, V.decode(V.regular(HERE / 'EXPECTED-CATALOG.json')))
        self.assertEqual(len(actual), 49)
        self.assertEqual(sum(len(r['all']) - len(r['ignored']) for r in actual), 1558)
        self.assertEqual(sum(len(r['ignored']) for r in actual), 30)
        for before, after in zip(self.parent, actual):
            self.assertEqual((before['package'], before['target']), (after['package'], after['target']))
            self.assertEqual(before['ignored'], after['ignored'])
            self.assertLessEqual(set(before['all']), set(after['all']))

    def test_old_case_loss_rename_ignored_change_or_missing_target_is_rejected(self):
        for kind in ('loss', 'rename', 'ignored', 'target'):
            parent = copy.deepcopy(self.parent)
            row = next(r for r in parent if len(r['all']) > 10)
            if kind == 'loss': row['all'].pop()
            if kind == 'rename': row['all'][-1] += '_renamed'; row['all'].sort()
            if kind == 'ignored': row['ignored'] = sorted(set(row['ignored']) | {row['all'][0]})
            if kind == 'target': parent.pop()
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                V.current_catalog(parent, self.additions)

    def test_only_the24_exact_declared_additions_are_accepted(self):
        for kind in ('omit', 'rename', 'extra', 'duplicate', 'target'):
            extra = copy.deepcopy(self.additions)
            if kind == 'omit': extra[0]['tests'].pop()
            if kind == 'rename': extra[0]['tests'][0] += '_wrong'
            if kind == 'extra': extra[0]['tests'].append('unrequested_extra_case')
            if kind == 'duplicate': extra.append(copy.deepcopy(extra[0]))
            if kind == 'target': extra[0]['target'] = 'unrequested_target'
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                V.current_catalog(self.parent, extra)

    def test_complete_current_source_chain_and_original_runner_gates_replay(self):
        expected = hashlib.sha256(V.regular(HERE / 'FILES.sha256')).hexdigest()
        packet = V.verify_capsule(expected)
        self.assertEqual(V.BASE.tree_id(packet['rows']), V.HEAD_TREE)
        self.assertEqual(len(packet['rows']), 2359)
        self.assertEqual(sum(r['bytes'] for r in packet['rows']), 44743370)
        self.assertFalse(packet['manifest']['production_ready'])
        self.assertFalse(packet['manifest']['runtime_qualified'])
        self.assertFalse(packet['manifest']['fresh_current_rust_run_in_this_packet'])
        self.assertTrue(packet['manifest']['new_cases_source_declared_until_actual_compiled_catalog'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
