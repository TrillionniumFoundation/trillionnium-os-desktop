"""Host-only source/metadata contracts. No original runner is imported."""
import ast
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

import adapt_cp3a as a

ROOT = Path(__file__).parent


class CP3ASourceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = a.load_bundle(ROOT)
        cls.selected, cls.image, cls.profile = a.metadata_contract(cls.bundle)
        cls.postimages, cls.records = a.build_postimages(cls.bundle)
        cls.cohort = a.make_cohort(cls.bundle, cls.records)

    def rejected(self, reason, function, *args):
        with self.assertRaises(a.AdmissionError) as caught:
            function(*args)
        self.assertEqual(str(caught.exception), reason)

    def test_actual_fixed_source_chain_and_distinct_gallery_candidates(self):
        self.assertEqual(len(self.bundle['sources']), 224)
        self.assertEqual(len(self.records), 23)
        self.assertEqual(len(a.LITERAL_RECIPES), 18)
        self.assertEqual(sum(len(r['edits']) for r in self.records), 42)
        self.assertEqual(self.cohort['full_GSI']['sha256'], a.GSI_SHA)
        delta = self.cohort['gallery_candidate_mismatch']
        self.assertTrue(delta['baseline_matches_current_official_APK'])
        self.assertFalse(delta['modified_candidate_matches_current_official_APK'])
        self.assertNotEqual(delta['historical_modified_DEX']['sha256'], delta['current_official_DEX_metadata']['sha256'])
        self.assertEqual(len(delta['historical_modified_method_metadata']), 2)
        for method in delta['historical_modified_method_metadata']:
            self.assertEqual(len(method['QPR1_preimage_sha256']), 64)
            self.assertEqual(len(method['patched_IR_sha256']), 64)
            self.assertEqual(len(method['patched_source_sha256']), 64)
        a.bookend(ROOT, self.bundle)

    def test_per_package_signer_and_full_image_cannot_be_normalized(self):
        for package in (a.CONTACTS, a.DOCUMENTS):
            with self.subTest(package=package):
                changed = copy.deepcopy(self.bundle)
                row = next(x for x in changed['docs']['CURRENT-SOURCE-STATE.json']['applications'] if x['package'] == package)
                row['unchanged_original_system_record']['signer_certificate_sha256'] = [a.CERT_PLATFORM]
                self.rejected('CURRENT_TARGET_PIN_OR_SIGNER:' + package, a.metadata_contract, changed)
        changed = copy.deepcopy(self.bundle)
        changed['docs']['official-gsi-manifest.json']['profile']['archive_members'][0]['sha256'] = '0' * 64
        self.rejected('STATE_GSI_MANIFEST_CHAIN', a.metadata_contract, changed)

    def test_old_gallery_candidate_or_credit_cannot_be_admitted(self):
        changed = copy.deepcopy(self.bundle)
        row = next(x for x in changed['docs']['CURRENT-SOURCE-STATE.json']['applications'] if x['package'] == a.GALLERY)
        row['unchanged_original_system_record']['apk'].update(bytes=a.GALLERY_MODIFIED[0], sha256=a.GALLERY_MODIFIED[1])
        self.rejected('OFFICIAL_GALLERY_SOURCE_RECEIPT_CHAIN', a.metadata_contract, changed)
        for field in ('old_ART_or_modified_method_credit_transferred', 'current_official_ART_qualified'):
            with self.subTest(field=field):
                cohort = copy.deepcopy(self.cohort); cohort['gallery_candidate_mismatch'][field] = True
                self.rejected('NO_GALLERY_CANDIDATE_OR_ART_CREDIT_TRANSFER', a.validate_cohort, cohort, self.selected)
        changed = copy.deepcopy(self.bundle)
        changed['docs']['official-gallery-source-receipt.json']['zip_members'][0]['sha256'] = a.MODIFIED_DEX[1]
        self.rejected('OFFICIAL_GALLERY_DEX_METADATA', a.metadata_contract, changed)

    def test_missing_providers_and_capex_substitution_fail_closed(self):
        for package, dependencies in a.PROVIDER_DEPENDENCIES.items():
            if not dependencies:
                self.assertEqual(a.require_provider_cohort(self.cohort, package), [])
                self.assertFalse(self.cohort['targets'][package]['runtime_qualified'])
                continue
            self.rejected('CURRENT_PROVIDER_SOURCE_PENDING:' + ','.join(dependencies), a.require_provider_cohort, self.cohort, package)
        changed = copy.deepcopy(self.cohort)
        changed['targets'][a.CAMERA]['provider_dependencies'] = []
        self.rejected('PROVIDER_DEPENDENCY_REMOVAL_FORBIDDEN', a.require_provider_cohort, changed, a.CAMERA)
        changed = copy.deepcopy(self.cohort)
        provider = changed['provider_cohort']['com.android.providers.media.module']
        provider['current_APK'] = provider['current_CAPEX_container_metadata_only']
        self.rejected('UNREVIEWED_PROVIDER_RECORD_NOT_ACCEPTED', a.require_provider_cohort, changed, a.CAMERA)

    def test_exact_postimages_keep_uids_limits_other_apps_and_providers(self):
        for relative, names in a.PROFILE_ASSIGNMENTS.items():
            before = ast.parse(self.bundle['sources'][relative]); after = ast.parse(self.postimages[relative])
            for name, package in names.items():
                profile = a.assignment(after, name)
                self.assertEqual(ast.literal_eval(a.dictionary_value(profile, 'uid')), a.TARGETS[package][6])
                self.assertEqual(ast.literal_eval(a.dictionary_value(profile, 'certificate_sha256')), a.TARGETS[package][5])
                self.assertEqual(ast.literal_eval(a.dictionary_value(profile, 'apks')),
                                 [{'bytes': a.TARGETS[package][2], 'sha256': a.TARGETS[package][3]}])
                self.assertEqual(ast.dump(a.dictionary_value(a.assignment(before, name), 'require_v3')),
                                 ast.dump(a.dictionary_value(profile, 'require_v3')))
        for relative, names in [(a.B + '/system_profiles.py', ['CONTACTS_PROVIDER', 'CALENDAR_PROVIDER', 'NATIVE_HELPER', 'CONTACTS_LIMITS', 'CALENDAR_LIMITS', 'CALENDAR_INSTALL', 'TASK_PROOF', 'ATOMIC_REVIEW']),
                                (a.I + '/app_profiles.py', ['IHG', 'IHG_LIMITS', 'CLOCK_LIMITS', 'CLOCK_HELPER']),
                                (a.P + '/camera_profiles.py', ['PHOTO_LIMITS', 'APP_GATES', 'MEDIA_PROVIDER_APK', 'MEDIA_PROVIDER_BYTES', 'MEDIA_PROVIDER_SHA']),
                                (a.D + '/documents_profiles.py', ['PROVIDER', 'NATIVE_HELPER', 'LIMITS', 'REQUIRED_GATES'])]:
            before = ast.parse(self.bundle['sources'][relative]); after = ast.parse(self.postimages[relative])
            for name in names:
                self.assertEqual(ast.dump(a.assignment(before, name)), ast.dump(a.assignment(after, name)), relative + ':' + name)
        for relative, before in self.bundle['sources'].items():
            for values in a.TARGETS.values():
                if values[1].encode() in before:
                    self.assertNotIn(values[1].encode(), self.postimages[relative])

    def test_gallery_retirement_precedes_every_legacy_entry_action(self):
        for relative, names in a.GALLERY_GUARDS.items():
            original = ast.parse(self.bundle['sources'][relative]); updated = ast.parse(self.postimages[relative])
            for name in names:
                before = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == name)
                after = next(n for n in updated.body if isinstance(n, ast.FunctionDef) and n.name == name)
                start = 1 if isinstance(after.body[0], ast.Expr) and isinstance(after.body[0].value, ast.Constant) and isinstance(after.body[0].value.value, str) else 0
                guard = after.body[start]
                self.assertIsInstance(guard, ast.Raise)
                self.assertIsInstance(guard.exc, ast.Call)
                self.assertEqual(guard.exc.func.id, 'RuntimeError')
                self.assertEqual([n.value for n in guard.exc.args], [a.GALLERY_REJECTION])
                # The complete original function remains byte-semantically the
                # same behind the unconditional rejection; no hidden dispatch.
                del after.body[start]
                self.assertEqual(ast.dump(before, include_attributes=False), ast.dump(after, include_attributes=False))

    def test_only_metadata_route_and_no_fabricated_runtime_binding(self):
        row = a.source_route(self.cohort, a.GALLERY, 'describe_source')
        self.assertEqual(row['source_record']['apk']['sha256'], a.GALLERY_OFFICIAL[1])
        for purpose in ('install', 'verify', 'execute', 'verify_modified_candidate', 'run_historical_case'):
            self.rejected('SOURCE_ADAPTER_HAS_NO_INSTALL_VERIFY_RUNTIME_OR_EXECUTE_MODE', a.source_route, self.cohort, a.GALLERY, purpose)
        for package, field, value in [(a.CLOCK, 'UID', 10063), (a.GALLERY, 'Main', {'pid': 123})]:
            changed = copy.deepcopy(self.cohort); changed['targets'][package]['actual_runtime_bindings'][field] = value
            self.rejected('NO_RUNTIME_BINDING_OR_SOURCE_PROMOTION:' + package, a.validate_cohort, changed, self.selected)
        changed = copy.deepcopy(self.cohort); changed['production_ready'] = True
        self.rejected('SOURCE_ROUTE_CANNOT_PROMOTE_RUNTIME', a.source_route, changed, a.GALLERY, 'describe_source')

    def test_correction_preserves_39_gates_migration_and_32_unimplemented(self):
        plan, readme, changes = a.corrected_preflight(self.bundle, self.cohort)
        old = self.bundle['docs']['preflight-r2-PLAN.json']
        self.assertEqual(len(plan['packages']), 39)
        self.assertEqual(plan['counts']['target_identity_rebinds'], 5)
        self.assertEqual(plan['counts']['finite_prepared_case_packages'], 7)
        self.assertEqual(plan['counts']['Gallery_modified_candidate_mismatches'], 1)
        self.assertEqual(plan['counts']['packages_without_selected_business_executor'], 32)
        self.assertEqual(plan['counts']['current_business_runtime_compatible_packages_qualified'], 0)
        self.assertEqual(plan['required_before_installation'], old['required_before_installation'])
        self.assertEqual(plan['exemptions'], old['exemptions'])
        untouched = 0
        for before, after in zip(old['packages'], plan['packages']):
            self.assertEqual(before['package'], after['package'])
            self.assertEqual(before['common_gate_ids'], after['common_gate_ids'])
            self.assertEqual(before['actual_runtime_bindings'], after['actual_runtime_bindings'])
            self.assertTrue(all(after[field] is False for field in a.RUNTIME_FIELDS))
            if not before['finite_prepared_case_source_exists']:
                untouched += 1
                self.assertEqual(before, after)
        self.assertEqual(untouched, 32)
        self.assertIn(b'historical official baseline APK matches', readme)
        self.assertIn(b'do not establish seven current-compatible runtimes', readme)
        self.assertEqual(sum('document' in row for row in changes), 2)

    def test_input_mutation_symlink_and_output_overwrite_refused(self):
        with tempfile.TemporaryDirectory(prefix='cp3a-metadata-controls-') as temporary:
            root = Path(temporary); (root / 'inputs').mkdir()
            name = 'CURRENT-SOURCE-STATE.json'; original = self.bundle['metadata_raw'][name]
            changed = bytearray(original); changed[0] = ord('[')
            path = root / 'inputs' / name; path.write_bytes(changed)
            self.rejected('INPUT_PIN:inputs/' + name, a.read_fixed, root, 'inputs/' + name, a.PINS[name])
            path.unlink(); path.symlink_to(ROOT / 'inputs' / name)
            with self.assertRaises(OSError):
                a.read_fixed(root, 'inputs/' + name, a.PINS[name])
            output = root / 'result'; manifest = a.materialize(ROOT, output)
            before = {name: (a.f9((output / name).stat()), (output / name).read_bytes()) for name in manifest['outputs']}
            self.rejected('EXCLUSIVE_NEW_OUTPUT_REQUIRED', a.materialize, ROOT, output)
            for name, (identity, body) in before.items():
                self.assertEqual(a.f9((output / name).stat()), identity)
                self.assertEqual((output / name).read_bytes(), body)
                self.assertEqual(a.pin(body), manifest['outputs'][name])


if __name__ == '__main__':
    unittest.main(verbosity=2)
