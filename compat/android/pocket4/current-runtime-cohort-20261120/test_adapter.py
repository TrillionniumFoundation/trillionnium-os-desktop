#!/usr/bin/env python3
"""Finite source-chain and catalog controls. These do not execute Cargo or Android."""
import ast
import copy
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('tested_current_cohort_adapter', HERE / 'verify.py')
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def read(path):
    return json.loads(path.read_bytes())


def inventory(root):
    rows = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
            for p in sorted(root.iterdir()) if p.name != 'FILES.sha256']
    raw = ''.join(rows).encode()
    (root / 'FILES.sha256').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class CurrentCatalogControls(unittest.TestCase):
    def setUp(self):
        self.original = read(VERIFY.ORIGINAL / 'EXPECTED-CATALOG.json')
        self.source = read(VERIFY.MATERIALIZATION / 'EXPECTED-CATALOG.json')
        self.apps = read(VERIFY.LEAF / 'EXPECTED-CATALOG.json')
        self.extras = read(HERE / 'EXTRA-TARGETS.json')

    def merge(self):
        return VERIFY.current_catalog(self.original, self.source, self.apps, self.extras)

    def test_full49_catalog_keeps_every_original_name_and_all30_ignored(self):
        current = self.merge()
        self.assertEqual(current, read(HERE / 'EXPECTED-CATALOG.json'))
        self.assertEqual(len(current), 49)
        self.assertEqual(sum(len(row['all']) - len(row['ignored']) for row in current), 1534)
        self.assertEqual(sum(len(row['ignored']) for row in current), 30)
        additions = {}
        for old, new in zip(self.original, current):
            self.assertEqual((old['package'], old['target']), (new['package'], new['target']))
            self.assertEqual(old['ignored'], new['ignored'])
            self.assertLessEqual(set(old['all']), set(new['all']))
            extra = set(new['all']) - set(old['all'])
            if extra:
                additions[(new['package'], new['target'])] = len(extra)
        self.assertEqual(additions, {('droidloom-source', 'droidloom_source'): 6,
                                    ('droidloom-applications', 'droidloom_applications'): 5})

    def test_old_case_loss_or_rename_cannot_be_hidden_by_equal_total(self):
        for cases, package in ((self.source, 'droidloom-source'), (self.apps, 'droidloom-applications')):
            row = next(r for r in cases if r['kind'] == 'lib')
            saved = copy.deepcopy(row)
            old = next(r for r in self.original if r['package'] == package and r['target'] == row['target'])
            for rename in (False, True):
                row['tests'] = [name for name in saved['tests'] if name != old['all'][0]]
                if rename:
                    row['tests'].append('invented_replacement_for_an_original_case')
                    row['tests'].sort()
                with self.subTest(package=package, rename=rename), self.assertRaises(RuntimeError):
                    self.merge()
            row.update(saved)

    def test_changed_ignored_status_or_identity_is_rejected(self):
        self.source[0]['ignored'] = [self.source[0]['tests'][0]]
        with self.assertRaises(RuntimeError):
            self.merge()

    def test_missing_duplicate_or_unrequested_current_target_is_rejected(self):
        saved = copy.deepcopy(self.apps)
        for cases in (saved[:-1], saved + [saved[0]],
                      saved + [{'kind': 'bin', 'target': 'invented', 'tests': [], 'ignored': []}]):
            self.apps = cases
            with self.subTest(cases=len(cases)), self.assertRaises(RuntimeError):
                self.merge()

    def test_only_six_source_and_five_app_additions_are_admitted(self):
        for cases in (self.source, self.apps):
            row = next(r for r in cases if r['kind'] == 'lib')
            row['tests'].append('zz_extra_case_outside_the_authenticated_successor')
            row['tests'].sort()
            with self.assertRaises(RuntimeError):
                self.merge()
            row['tests'].remove('zz_extra_case_outside_the_authenticated_successor')

    def test_original_nine_recipe_cases_are_not_folded_into_ordinary_or_replaced(self):
        recipe = next(r for r in self.source if r['kind'] == 'example')
        recipe['tests'] = recipe['tests'][:-1]
        with self.assertRaises(RuntimeError):
            self.merge()


class FullSourceChainControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='current2352-cohort-controls-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'packet'
        shutil.copytree(HERE, self.root)

    def verify(self, pin=None):
        if pin is None:
            pin = inventory(self.root)
        with mock.patch.object(VERIFY, 'HERE', self.root):
            return VERIFY.verify_capsule(pin)

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

    def patch_runner(self, old, new):
        current = (self.root / 'run_ci.py').read_text()
        self.assertEqual(current.count(old), 1)
        current = current.replace(old, new)
        (self.root / 'run_ci.py').write_text(current)
        original = (VERIFY.ORIGINAL / 'run_ci.py').read_text()
        patch = ''.join(difflib.unified_diff(original.splitlines(True), current.splitlines(True),
                                           fromfile='a/run_ci.py', tofile='b/run_ci.py'))
        (self.root / 'RUNNER.patch').write_text(patch)

    def test_complete_original_capsule_and_both_successors_bind_the_current2352_tree(self):
        verified = self.verify(hashlib.sha256((HERE / 'FILES.sha256').read_bytes()).hexdigest())
        self.assertEqual(VERIFY.BASE.tree_id(verified['rows']), VERIFY.HEAD_TREE)
        self.assertEqual(len(verified['rows']), 2352)
        self.assertEqual(sum(row['bytes'] for row in verified['rows']), 44260146)
        self.assertEqual(verified['source_chain'], VERIFY.SOURCE_CHAIN)

    def test_wrong_external_inventory_and_extra_unlisted_file_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.verify('0' * 64)
        pin = hashlib.sha256((self.root / 'FILES.sha256').read_bytes()).hexdigest()
        (self.root / 'unexpected').write_text('unlisted\n')
        with self.assertRaises(RuntimeError):
            self.verify(pin)

    def test_stale1523_catalog_cannot_pass_with_a_fresh_packet_inventory(self):
        (self.root / 'EXPECTED-CATALOG.json').write_bytes((VERIFY.ORIGINAL / 'EXPECTED-CATALOG.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'current exact49-target catalog differs'):
            self.verify()

    def test_original_targets_examples_updater_split_and_controls_cannot_be_changed(self):
        for name in VERIFY.UNCHANGED_METADATA:
            saved = (self.root / name).read_bytes()
            (self.root / name).write_bytes(saved + b'\n')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'original target/example/control source changed'):
                self.verify()
            (self.root / name).write_bytes(saved)

    def test_changed_shared_parser_gate_is_rejected_even_with_a_matching_replay_patch(self):
        self.patch_runner('def catalog(raw, expected):', 'def catalog(raw, expected):\n    return expected')
        with self.assertRaisesRegex(RuntimeError, 'original shared runner gate changed'):
            self.verify()

    def test_changed_module_budget_or_import_is_rejected_even_with_a_matching_patch(self):
        self.patch_runner('import argparse', 'import argparse\nCOHORT_UNAUTHORIZED_BYPASS = True')
        with self.assertRaisesRegex(RuntimeError, 'original runner import, constant or module entry changed'):
            self.verify()

    def test_reduced_declared_scope_cannot_be_substituted_for_the_full_cohort(self):
        manifest = read(self.root / 'MANIFEST.json')
        manifest['required']['ordinary'] = 1523
        self.write_json('MANIFEST.json', manifest)
        with self.assertRaisesRegex(RuntimeError, 'complete current source and original full-cohort gates required'):
            self.verify()


if __name__ == '__main__':
    unittest.main(verbosity=2)
