"""Preserve exact original controller safety/resource/guest gates across wiring."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
TREE = ast.parse((HERE / 'controller.py').read_bytes())
BASE = json.loads((HERE / 'integration_baseline.json').read_bytes())
DUMP = lambda node: ast.dump(node, include_attributes=False)


class SourceBoundaryTests(unittest.TestCase):
    def test_all_old_guards_except_three_explicit_binding_updates(self):
        actual = collections.Counter(DUMP(n) for n in ast.walk(TREE) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == 'need')
        old = collections.Counter(BASE['all_original_need_AST'])
        self.assertEqual(old - actual, collections.Counter(BASE['three_changed_need_AST']))
        self.assertEqual(actual - old, collections.Counter(BASE['new_or_changed_need_AST']))
        self.assertEqual(sum(old.values()), 272)
        self.assertEqual(sum((old & actual).values()), 269)

    def test_original_authority_retirement_and_guest_parser_functions_unchanged(self):
        functions = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}
        for name, digest in BASE['unchanged_function_AST_sha256'].items():
            with self.subTest(function=name):
                self.assertEqual(hashlib.sha256(DUMP(functions[name]).encode()).hexdigest(), digest)

    def test_original_vm_arguments_resources_and_console_failure_gate_unchanged(self):
        found = collections.defaultdict(list)
        for n in ast.walk(TREE):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                found[n.targets[0].id].append(DUMP(n))
        for name, expected in BASE['unchanged_critical_assignments'].items():
            self.assertIn(expected, found[name])

    def test_helper_complete_source_is_bound(self):
        body = (HERE / 'owned_qmp_gate.py').read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        constants = [n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertIn(digest, constants)
        self.assertIn('p4-systemd-cold-component-native-input-stats-v2', constants)


if __name__ == '__main__':
    unittest.main(verbosity=2)
