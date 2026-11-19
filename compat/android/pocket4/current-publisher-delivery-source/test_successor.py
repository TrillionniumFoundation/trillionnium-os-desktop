"""Finite rejection controls for source replay; no APK or device operations."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('successor_under_test', HERE / 'successor.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SuccessorControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.read = staticmethod(lambda path: (ROOT / path).read_bytes())
        cls.manifest = (HERE / 'MANIFEST.json').read_bytes()
        cls.source = gate.Successor(cls.read, cls.manifest)
        cls.initial = (
            gate.decode(cls.source.bodies[gate.INPUTS]),
            gate.decode(cls.source.bodies[gate.FRESHNESS]),
            gate.decode(cls.source.historical_registry(gate.INPUTS)),
            gate.decode(cls.source.historical_registry(gate.FRESHNESS)),
            cls.source.bodies,
        )

    def setUp(self):
        self.inputs, self.freshness, self.old_inputs, self.old_freshness, self.bodies = copy.deepcopy(self.initial)

    def assess(self):
        return gate.assess(self.inputs, self.freshness, self.old_inputs, self.old_freshness, self.bodies)

    def app(self, package):
        return next(x for x in self.inputs['applications'] if x['package'] == package)

    def change_receipt_with_consistent_pins(self, package, change):
        """Exercise semantics even when a proposed successor updates its digests."""
        app = self.app(package)
        receipt_path = gate.CLOSURE + 'receipts/' + package + '.json'
        receipt = gate.decode(self.bodies[receipt_path])
        change(receipt)
        raw = (json.dumps(receipt, sort_keys=True) + '\n').encode()
        self.bodies[receipt_path] = raw
        for ref in (app['expected_input']['source_receipt'], app['proofs']['source-receipt.json']):
            ref['bytes'], ref['sha256'] = len(raw), gate.sha(raw)
        native_path = gate.CLOSURE + 'native-inputs/' + package + '.json'
        native = gate.decode(self.bodies[native_path])
        native['application']['expected_input'] = copy.deepcopy(app['expected_input'])
        raw = (json.dumps(native, sort_keys=True) + '\n').encode()
        self.bodies[native_path] = raw
        ref = app['proofs']['native-input.json']
        ref['bytes'], ref['sha256'] = len(raw), gate.sha(raw)
        path = gate.CLOSURE + 'SOURCE-INPUT-SUMMARY.json'
        summary = gate.decode(self.bodies[path])
        summary['source_records'][package] = copy.deepcopy(app['proofs'])
        self.bodies[path] = (json.dumps(summary, sort_keys=True) + '\n').encode()

    def test_real_historical_and_current_source_sets_pass_without_runtime_credit(self):
        result = self.assess()
        self.assertEqual(result['current_required_third_party_inputs'], 29)
        self.assertEqual(result['remaining_required_third_party_inputs'], 0)
        self.assertIs(result['activation_requires_fresh_metadata_and_destination_custody'], True)
        for key in ('latest_versions_verified_by_replay', 'installed', 'runtime_qualified',
                    'business_qualified', 'native_compatibility_qualified', 'production_ready'):
            self.assertIs(result[key], False)

    def test_external_successor_definition_cannot_be_replaced(self):
        def changed(path):
            body = self.read(path)
            return body + b' ' if path.endswith('/CURRENT-SUCCESSOR.json') else body
        with self.assertRaisesRegex(ValueError, 'fixed successor'):
            gate.Successor(changed, self.manifest)

    def test_any_current_source_file_byte_change_is_rejected(self):
        path = gate.CLOSURE + 'receipts/com.ss.android.ugc.aweme.json'
        def changed(name):
            return self.read(name) + (b' ' if name == path else b'')
        with self.assertRaisesRegex(ValueError, 'pinned bytes'):
            gate.Successor(changed, self.manifest)

    def test_original_publication_cannot_be_rewritten(self):
        with self.assertRaisesRegex(ValueError, 'original publication'):
            gate.Successor(self.read, self.manifest + b' ')

    def test_original_application_record_cannot_change(self):
        self.inputs['applications'][0]['version_code'] += 1
        with self.assertRaisesRegex(ValueError, 'previous 24'):
            self.assess()

    def test_original_archive_record_cannot_be_removed(self):
        self.inputs['archives'].pop()
        with self.assertRaisesRegex(ValueError, 'custody field'):
            self.assess()

    def test_no_fourth_exemption_or_smaller_required_scope(self):
        for key, value in [('excluded_packages', gate.EXEMPT + ['com.bestbuy.android']),
                           ('required_application_count', 38)]:
            with self.subTest(key=key):
                original = self.inputs['scope'][key]
                self.inputs['scope'][key] = value
                with self.assertRaises(ValueError):
                    self.assess()
                self.inputs['scope'][key] = original

    def test_missing_or_duplicate_current_application_rejected(self):
        for rows in [self.inputs['applications'][:-1], self.inputs['applications'] + [self.inputs['applications'][-1]]]:
            with self.subTest(size=len(rows)):
                original = self.inputs['applications']
                self.inputs['applications'] = rows
                with self.assertRaises(ValueError):
                    self.assess()
                self.inputs['applications'] = original

    def test_source_counts_cannot_contradict_rows(self):
        self.inputs['scope']['current_verified_third_party_source_input_count'] = 30
        with self.assertRaises(ValueError):
            self.assess()

    def test_old_country_failure_observation_cannot_be_erased(self):
        row = next(x for x in self.freshness['rows'] if x['package'] == 'com.bestbuy.android')
        row['source_availability_observations'] = []
        with self.assertRaisesRegex(ValueError, 'historical source observation'):
            self.assess()

    def test_source_status_never_becomes_runtime_credit(self):
        for key in ('installed', 'runtime_qualified', 'business_qualified', 'native_compatibility_qualified', 'production_ready'):
            with self.subTest(key=key):
                self.app('com.ss.android.ugc.aweme')[key] = True
                with self.assertRaisesRegex(ValueError, 'cannot grant'):
                    self.assess()
                self.app('com.ss.android.ugc.aweme')[key] = False

    def test_available_country_relabel_rejected_even_with_updated_receipt_pins(self):
        self.change_receipt_with_consistent_pins('com.bestbuy.android',
            lambda r: r['current_source_validation'].update(current_metadata_restriction='AVAILABLE'))
        with self.assertRaisesRegex(ValueError, 'new available delivery'):
            self.assess()

    def test_new_delivery_claim_rejected_even_with_updated_receipt_pins(self):
        self.change_receipt_with_consistent_pins('com.bestbuy.android',
            lambda r: r.update(current_delivery_obtained=True))
        with self.assertRaisesRegex(ValueError, 'new available delivery'):
            self.assess()

    def test_stale_at_original_publication_rejected(self):
        self.change_receipt_with_consistent_pins('com.bestbuy.android',
            lambda r: r.update(verified_utc='2026-11-20T02:00:00+00:00'))
        with self.assertRaisesRegex(ValueError, 'historical receipt publication'):
            self.assess()

    def test_changed_split_closure_rejected_even_with_updated_receipt_pins(self):
        self.change_receipt_with_consistent_pins('com.bestbuy.android',
            lambda r: r['split_closure'].update(manifest_dependency_closure_verified=False))
        with self.assertRaisesRegex(ValueError, 'split and ZIP'):
            self.assess()

    def test_changed_signer_or_apk_digest_rejected_even_with_updated_receipt_pins(self):
        self.change_receipt_with_consistent_pins('com.bestbuy.android',
            lambda r: r['identities'][0].update(signer_certificate_sha256=['0' * 64]))
        with self.assertRaisesRegex(ValueError, 'package/version/signer'):
            self.assess()

    def test_duplicate_actual_identity_cannot_hide_an_omitted_split(self):
        def duplicate(receipt):
            receipt['identities'][1] = copy.deepcopy(receipt['identities'][0])
        self.change_receipt_with_consistent_pins('com.bestbuy.android', duplicate)
        with self.assertRaisesRegex(ValueError, 'exactly one actual signed identity'):
            self.assess()

    def test_meituan_signer_migration_cannot_be_granted(self):
        row = next(x for x in self.freshness['rows'] if x['package'] == 'com.sankuai.meituan.takeoutnew')
        row['signer_migration_gate']['state'] = 'COMPLETE'
        with self.assertRaisesRegex(ValueError, 'signer migration'):
            self.assess()

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        for value in [b'{"x": 1, "x": 2}', b'{"x": NaN}', b'{"x": Infinity}']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.decode(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
