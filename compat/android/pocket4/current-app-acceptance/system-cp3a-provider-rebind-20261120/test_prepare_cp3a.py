"""Controls on the actual 224-file published source graph; no Main or APK I/O."""
import ast
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('provider_rebind_candidate', HERE / 'prepare_cp3a.py')
candidate = importlib.util.module_from_spec(spec); spec.loader.exec_module(candidate)
REPO = HERE.parents[4]


class ProviderRebindControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.bundle, cls.inputs, cls.raw, cls.identities = candidate.load(REPO.resolve())
        cls.base, cls.base_records = cls.old.build_postimages(cls.bundle)
        cls.post, cls.transform, cls.contract = candidate.build(cls.old, cls.bundle, cls.raw)

    def mutated_source(self, mutate):
        raw = dict(self.raw)
        key = candidate.PROVIDERS + 'current/CURRENT-CP3A-PROVIDER-COHORT.json'
        value = self.old.parse(raw[key]); mutate(value)
        raw[key] = self.old.json_bytes(value)
        with self.assertRaises((ValueError, RuntimeError)):
            candidate.provider_sources(self.old, self.bundle, raw)

    def test_complete_source_and_postimage_scope(self):
        self.assertEqual(len(self.bundle['sources']), 224)
        self.assertEqual(len(self.base), 23)
        self.assertEqual(len(candidate.RECIPES), 11)
        self.assertEqual(len(self.post), 24)
        self.assertEqual(set(self.post), set(self.base) | set(candidate.RECIPES))

    def test_all_functions_and_limits_unchanged_by_provider_rebind(self):
        for name in candidate.RECIPES:
            before = ast.parse(self.base.get(name, self.bundle['sources'][name]))
            after = ast.parse(self.post[name])
            old_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(before)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            new_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(after)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            # Three old inline provider hashes occur inside existing identity
            # calls. Normalize only the four exact approved SHA literals there.
            allowed = {v[3]: v[1] for v in candidate.PINS.values()}
            class RevertHashes(ast.NodeTransformer):
                def visit_Constant(self, node):
                    if isinstance(node.value, str) and node.value in allowed:
                        node.value = allowed[node.value]
                    return node
            after = RevertHashes().visit(after)
            new_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(after)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            self.assertEqual(old_functions, new_functions, name)
            for node in before.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
                    ('LIMIT' in t.id or t.id == 'NATIVE_HELPER') for t in node.targets):
                    target = node.targets[0].id
                    self.assertEqual(ast.dump(node.value, include_attributes=False),
                                     ast.dump(self.old.assignment(after, target), include_attributes=False), name)

    def test_non_provider_postimages_byte_identical(self):
        for name in set(self.base) - set(candidate.RECIPES):
            self.assertEqual(self.base[name], self.post[name], name)

    def test_all_six_gallery_retirement_guards_preserved(self):
        total = 0
        for name, functions in self.old.GALLERY_GUARDS.items():
            self.assertEqual(self.post[name], self.base[name])
            tree = ast.parse(self.post[name])
            for func in functions:
                f = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == func)
                first = f.body[1] if isinstance(f.body[0], ast.Expr) and isinstance(f.body[0].value, ast.Constant) else f.body[0]
                self.assertIsInstance(first, ast.Raise)
                self.assertEqual(first.exc.args[0].value, self.old.GALLERY_REJECTION); total += 1
        self.assertEqual(total, 6)

    def test_old_provider_hashes_and_apex_path_absent_over_full_graph(self):
        for name, original in self.bundle['sources'].items():
            body = self.post.get(name, original)
            for values in candidate.PINS.values():
                self.assertNotIn(values[1].encode(), body, name)
            self.assertNotIn(candidate.MEDIA_OLD.encode(), body, name)

    def test_all_ten_source_identities_have_exact_signers_and_sizes(self):
        bindings = self.contract['bindings']; self.assertEqual(len(bindings), 10)
        for package, binding in bindings.items():
            profile = binding['profile']
            self.assertEqual(profile['package'], package)
            self.assertEqual(len(profile['apks']), 1)
            self.assertEqual(set(profile['apks'][0]), {'bytes', 'sha256'})
            self.assertGreater(profile['apks'][0]['bytes'], 0)
            self.assertRegex(profile['certificate_sha256'], '^[0-9a-f]{64}$')
            self.assertFalse(binding['UID_constraint_is_live_observation'])
            self.assertFalse(binding['runtime_qualified'])
        self.assertIsNone(bindings[candidate.MED]['profile']['uid'])
        self.assertEqual(bindings['com.android.gallery3d']['profile']['uid'], 10064)
        self.assertTrue(bindings['com.android.deskclock']['profile']['require_v3'])

    def test_calendar_historical_install_and_semantics_are_not_rebound(self):
        for root in (candidate.B, candidate.C):
            for name in ('system_factory.py', 'system_plan.py'):
                path = root + '/' + name
                if path in self.bundle['sources']:
                    self.assertNotIn(path, self.post)
            old = ast.parse(self.base[root + '/system_profiles.py'])
            new = ast.parse(self.post[root + '/system_profiles.py'])
            for key in ('CALENDAR_INSTALL', 'ATOMIC_REVIEW', 'TASK_PROOF'):
                self.assertEqual(ast.literal_eval(self.old.assignment(old, key)),
                                 ast.literal_eval(self.old.assignment(new, key)))

    def test_wrong_full_gsi_rejected(self):
        self.mutated_source(lambda c: c['full_GSI'].__setitem__('sha256', '0' * 64))

    def test_unverified_provider_rejected(self):
        self.mutated_source(lambda c: c['provider_cohort'][candidate.CAL].__setitem__('source_identity_verified', False))

    def test_false_actual_uid_rejected(self):
        self.mutated_source(lambda c: c['provider_cohort'][candidate.CON].__setitem__('actual_UID', 10015))

    def test_provider_signer_substitution_rejected(self):
        self.mutated_source(lambda c: c['provider_cohort'][candidate.MED].__setitem__('current_signer',
                             c['provider_cohort'][candidate.CAL]['current_signer']))

    def test_capex_digest_cannot_stand_for_apk(self):
        self.mutated_source(lambda c: c['provider_cohort'][candidate.MED]['current_APK'].__setitem__('sha256',
                             c['provider_cohort'][candidate.MED]['current_CAPEX_container_metadata_only']['sha256']))

    def test_provider_dependency_cannot_be_removed(self):
        self.mutated_source(lambda c: c['targets']['com.android.gallery3d'].__setitem__('provider_dependencies', []))

    def test_false_semantic_promotion_rejected(self):
        self.mutated_source(lambda c: c['provider_cohort'][candidate.CAL].__setitem__('semantic_cleanup_qualified', True))

    def test_false_global_runtime_promotion_rejected(self):
        self.mutated_source(lambda c: c.__setitem__('runtime_qualified', True))

    def test_modified_gallery_dex_rejected(self):
        raw = dict(self.raw); key = candidate.DEX + 'actual/DEX-SOURCE-INVENTORY.json'
        value = self.old.parse(raw[key]); value['dex']['sha256'] = self.old.MODIFIED_DEX[1]
        raw[key] = self.old.json_bytes(value)
        with self.assertRaisesRegex(ValueError, 'official Gallery source'):
            candidate.provider_sources(self.old, self.bundle, raw)

    def test_literal_evaluation_never_executes_runtime_source(self):
        with self.assertRaises((ValueError, RuntimeError)):
            candidate.static_profile(self.old, b"PROFILE={'component':__import__('os').getuid()}\n", 'PROFILE')
        with self.assertRaises(ValueError):
            candidate.static_profile(self.old, b"A=B\nB=A\nPROFILE={'component':A}\n", 'PROFILE')

    def test_no_runtime_credit_and_source_bookends(self):
        for name in candidate.RUNTIME_FALSE:
            self.assertIs(self.contract[name], False)
        self.assertFalse(self.contract['live_custody_producer_qualified'])
        self.assertFalse(self.contract['runtime_bootstrap_preparation_admission_claimed'])
        self.old.bookend(REPO.resolve() / candidate.OLD, self.bundle)
        for name, expected in self.inputs.items():
            _, actual = self.old.read_fixed(REPO.resolve(), name, expected)
            self.assertEqual(actual, self.identities[name])

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'new output only'):
                candidate.materialize(REPO.resolve(), Path(tmp))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--repo-root', type=Path, default=REPO)
    args, remaining = parser.parse_known_args()
    REPO = args.repo_root.resolve()
    unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
