"""Source-only regression controls using the original actual qualification receipts."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('beike_successor_under_test', ROOT / 'override_beike.py')
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, _ = subject.read_inputs(ROOT / 'inputs')
        cls.at = datetime.fromtimestamp(cls.original['transport-cleanup.json']['finished_ns'] / 10**9,
                                        timezone.utc) + timedelta(microseconds=1)

    def setUp(self):
        self.data = copy.deepcopy(self.original)

    def reject(self, mutate):
        mutate(self.data)
        with self.assertRaises((ValueError, KeyError)):
            subject.validate(self.data, self.at)

    def outputs(self):
        return {name: subject.parse(raw) for name, raw in
                subject.generate(self.data, Path('/not-published-control'), self.at).items()}

    def test_actual_source_receipts_select_current_without_runtime_credit(self):
        output = self.outputs()
        registry = output['current-source-inputs.json']
        beike = next(x for x in registry['applications'] if x['package'] == subject.PACKAGE)
        self.assertEqual((beike['version_name'], beike['version_code']), ('3.06.80', 3068010))
        self.assertEqual(beike['input']['sha256'], subject.APK_SHA)
        self.assertEqual(beike['expected_input']['source_receipt'], subject.original_ref('source-receipt.json'))
        self.assertEqual((beike['selected_abi_native_members'], beike['cross_architecture_source_members']), (67, 1))
        state = output['CURRENT-SOURCE-STATE.json']
        self.assertEqual((state['required_count'], state['selected_count']), (39, 42))
        self.assertFalse(state['all_39_latest_qualified'])
        subject.no_credit(output)

    def test_historical_records_and_unrelated_apps_are_exactly_preserved(self):
        output = self.outputs()
        subject.validate_output(self.data, output['current-source-inputs.json'],
                                output['current-source-freshness.json'], output['CURRENT-SOURCE-STATE.json'])
        fresh = next(x for x in output['current-source-freshness.json']['rows'] if x['package'] == subject.PACKAGE)
        old = next(x for x in self.data['base-freshness.json']['rows'] if x['package'] == subject.PACKAGE)
        self.assertEqual(fresh['complete_inputs'][:-1], old['complete_inputs'])
        self.assertEqual(fresh['version_observations'][:-2], old['version_observations'])
        self.assertEqual(self.data, self.original)

    def test_retired_ranges_are_not_required_live_dependencies(self):
        state = self.outputs()['CURRENT-SOURCE-STATE.json']
        deps = state['live_Beike_dependencies']
        self.assertEqual(deps['temporary_download_prefix_or_ranges'], [])
        self.assertFalse(state['historical_range_bodies_required_for_installation'])
        self.assertEqual(deps['final_APK']['path'], str(subject.APK))
        self.assertIn('transport-cleanup.json', deps['qualified_metadata'])
        self.assertTrue(self.data['transport-cleanup.json']['all_selected_temporary_paths_absent'])

    def test_current_identity_requires_exact_version_signer_and_actual_sdk37(self):
        for key, value in (('version_code', 3067100), ('signer_certificate_sha256', ['0' * 64]),
                           ('verification_SDK_range', [36, 36]), ('signature_verified', False),
                           ('tool_exits', {'signature': 1, 'badging': 0, 'manifest': 0})):
            with self.subTest(key=key):
                self.data = copy.deepcopy(self.original)
                self.reject(lambda d: d['source-receipt.json']['identity'].__setitem__(key, value))

    def test_standalone_candidate_cannot_hide_missing_splits(self):
        self.reject(lambda d: d['source-receipt.json']['identity'].__setitem__('uses_splits', ['missing.feature']))

    def test_duplicate_native_or_cross_isa_runtime_promotion_rejected(self):
        self.reject(lambda d: d['NATIVE-PAYLOADS.json'].__setitem__(0, copy.deepcopy(d['NATIVE-PAYLOADS.json'][1])))
        self.data = copy.deepcopy(self.original)
        row = next(x for x in self.data['NATIVE-PAYLOADS.json'] if x['path'] == subject.CROSS['path'])
        row['counted_as_arm64_native_library'] = True
        with self.assertRaises(ValueError):
            subject.validate(self.data, self.at)

    def test_detached_or_failed_source_qualification_rejected(self):
        for mutate in (lambda d: d['native-input.json']['application']['expected_input']['source_receipt'].__setitem__('sha256', '0' * 64),
                       lambda d: d['RESULT.json'].__setitem__('state', 'FAILED'),
                       lambda d: d['SOURCE.json'].__setitem__('distribution', 'publisher_direct'),
                       lambda d: d['SOURCE.json']['download_closure'].__setitem__('all_piece_hashes_checked_from_final_APK', False)):
            self.data = copy.deepcopy(self.original)
            self.reject(mutate)

    def test_listing_must_be_current_and_not_future(self):
        with self.assertRaises(ValueError):
            subject.validate(self.data, self.at + timedelta(hours=24))
        self.reject(lambda d: d['PAGES.json']['requests'][0].__setitem__('observed_utc',
                    (self.at + timedelta(seconds=1)).isoformat()))

    def test_nested_runtime_credit_and_fourth_exemption_rejected(self):
        self.reject(lambda d: d['native-input.json'].__setitem__('production_ready', True))
        self.data = copy.deepcopy(self.original)
        self.reject(lambda d: d['base-state.json']['exemptions'].append({'package': subject.PACKAGE}))

    def test_meituan_migration_and_other_installation_gates_cannot_be_closed(self):
        row = next(x for x in self.data['base-registry.json']['applications'] if x['package'] == subject.MEITUAN)
        row['signer_migration_qualified'] = True
        with self.assertRaises(ValueError):
            subject.validate(self.data, self.at)
        self.data = copy.deepcopy(self.original)
        output = self.outputs()
        state = output['CURRENT-SOURCE-STATE.json']
        state['required_before_installation']['fresh_destination_custody_for_every_selected_APK_and_split'] = 'CLOSED'
        with self.assertRaises(ValueError):
            subject.validate_output(self.data, output['current-source-inputs.json'], output['current-source-freshness.json'], state)

    def test_unrelated_registry_record_or_system_image_change_rejected(self):
        output = self.outputs()
        output['current-source-inputs.json']['applications'][0]['version_name'] = 'invented'
        with self.assertRaises(ValueError):
            subject.validate_output(self.data, output['current-source-inputs.json'],
                                    output['current-source-freshness.json'], output['CURRENT-SOURCE-STATE.json'])
        self.reject(lambda d: d['base-state.json']['full_GSI_dependency'].__setitem__('sha256', '0' * 64))

    def test_original_bytes_and_duplicate_json_keys_are_not_reinterpreted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in subject.PINS:
                raw = (ROOT / 'inputs' / name).read_bytes()
                (directory / name).write_bytes(raw + (b' ' if name == 'candidate.json' else b''))
            with self.assertRaises(ValueError):
                subject.read_inputs(directory)
        with self.assertRaises(ValueError):
            subject.parse(b'{"production_ready":false,"production_ready":true}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
