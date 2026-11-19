"""Real published metadata controls; no APK execution or Android access."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import importlib.util

_MODULE_PATH = Path(__file__).resolve().with_name('merge_required39.py')
_MODULE_SPEC = importlib.util.spec_from_file_location('merge_required39', _MODULE_PATH)
m = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(m)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


class SourceMergeControls(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((HERE / 'index-control-fixtures.json').read_text())
        self.args = {name: fixture[name] for name in ('system', 'summary', 'freeze', 'result', 'previous')}
        for name, filename in [('scope', 'release-scope-20261118.json'),
                               ('registry', 'current-source-inputs.json'),
                               ('freshness', 'current-source-freshness.json')]:
            self.args[name] = json.loads((HERE / 'inputs' / filename).read_text())

    def validate(self):
        return m.validate_indices(**self.args)

    def six(self, package='com.bestbuy.android'):
        app = next(x for x in self.args['registry']['applications'] if x['package'] == package)
        values = [json.loads((ROOT / app['proofs'][name]['path']).read_text())
                  for name in ('candidate.json', 'source-receipt.json', 'native-input.json')]
        return [app] + values

    def test_real_39_scope_and_all_six_source_contracts(self):
        apps, systems, old23 = self.validate()
        self.assertEqual((len(apps), len(systems), len(old23)), (30, 10, 23))
        for package in m.SIX:
            m.validate_six(*self.six(package))

    def test_duplicate_application_cannot_fill_omitted_required_input(self):
        apps = self.args['registry']['applications']
        apps[-1] = copy.deepcopy(apps[-2])
        with self.assertRaisesRegex(ValueError, 'duplicate or omitted'):
            self.validate()

    def test_companion_cannot_replace_required_package(self):
        app = self.args['registry']['applications'][0]
        app['required39_member'] = False
        with self.assertRaisesRegex(ValueError, 'membership'):
            self.validate()

    def test_fourth_exemption_rejected(self):
        self.args['scope']['exemptions'].append({'package': m.MEITUAN})
        with self.assertRaisesRegex(ValueError, 'three exemptions'):
            self.validate()

    def test_any_runtime_credit_rejected(self):
        self.args['registry']['applications'][-1]['native_compatibility_qualified'] = True
        with self.assertRaisesRegex(ValueError, 'source-only'):
            self.validate()

    def test_previous23_same_version_different_apk_rejected(self):
        row = next(x for x in self.args['previous']['rows'] if 'expected_input' in x)
        row['expected_input']['apks'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'previous23 APK contract'):
            self.validate()

    def test_freshness_code_disagreement_rejected(self):
        self.args['freshness']['rows'][0]['selected_input_version_code'] += 1
        with self.assertRaisesRegex(ValueError, 'freshness version code'):
            self.validate()

    def test_system10_cannot_be_detached_from_full_gsi(self):
        self.args['system']['original_GSI_APKs_remain_bound_to_full_image_and_its_external_framework_and_native_dependencies'] = False
        with self.assertRaisesRegex(ValueError, 'system image'):
            self.validate()

    def test_different_gsi_cannot_inherit_system_receipts(self):
        self.args['summary']['original_system_image']['sha256'] = '1' * 64
        with self.assertRaisesRegex(ValueError, 'complete GSI'):
            self.validate()

    def test_duplicate_actual_split_identity_rejected(self):
        args = self.six()
        args[2]['identities'][2] = copy.deepcopy(args[2]['identities'][1])
        with self.assertRaisesRegex(ValueError, 'every expected split'):
            m.validate_six(*args)

    def test_unavailable_country_does_not_become_new_delivery(self):
        args = self.six()
        args[2]['current_source_validation']['current_delivery_obtained'] = True
        with self.assertRaisesRegex(ValueError, 'country restriction'):
            m.validate_six(*args)

    def test_retained_historical_expiry_cannot_be_extended(self):
        args = self.six()
        args[2]['current_source_validation']['metadata_revalidation_due_utc'] = '2026-11-20T17:44:09.086253+00:00'
        with self.assertRaisesRegex(ValueError, '24h'):
            m.validate_six(*args)

    def test_meituan_native_fragment_cannot_claim_migration(self):
        args = self.six(m.MEITUAN)
        args[3]['signer_migration_qualified'] = True
        with self.assertRaisesRegex(ValueError, 'Meituan signer migration'):
            m.validate_six(*args)

    def test_actual_signature_failure_cannot_be_hidden_by_source_summary(self):
        args = self.six('com.ss.android.ugc.aweme')
        args[2]['identity']['tool_exits']['signature'] = 1
        with self.assertRaisesRegex(ValueError, 'actual signed SDK37'):
            m.validate_six(*args)

    def test_duplicate_json_and_changed_bytes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            m.parse(b'{"production_ready": false, "production_ready": true}')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'receipt.json'
            path.write_bytes(b'{}')
            ref = {'path': str(path), 'bytes': 2, 'sha256': m.digest(b'{}')}
            m.read(ref)
            path.write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError, 'bytes or F9 changed'):
                m.read(ref)


if __name__ == '__main__':
    unittest.main(verbosity=2)
