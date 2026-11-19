"""Adversarial controls for retained official input admission; no APK execution."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_retained_play_set as retained


def fixtures():
    cert = 'a' * 64
    root = '/retained/com.example.app/'
    candidate = {'schema': retained.SCHEMA, 'package': 'com.example.app',
        'version_name': '8.0.0', 'version_code': 800, 'version_code_major': 0,
        'min_sdk_version': 26, 'target_sdk_version': 36,
        'signer_certificate_sha256': [cert], 'selected_abi': 'x86_64', 'apks': [],
        'source': {'distribution': retained.SOURCE_KIND, 'current_delivery_obtained': False,
                   'observed_utc': '2026-11-18T17:44:09Z'}}
    for split in (None, 'config.x86_64', 'config.xxhdpi'):
        name = retained.sets.normalized_name(split)
        candidate['apks'].append({'member': name, 'split_name': split, 'bytes': 1234,
            'sha256': hashlib.sha256(name.encode()).hexdigest(),
            'native_abis': ['x86_64'] if split == 'config.x86_64' else [],
            'retained_path': root + name})
    for key in retained.EVIDENCE_KEYS:
        candidate['source'][key] = {'path': '/evidence/' + key + '.json', 'bytes': 123, 'sha256': 'b' * 64}
    encode = lambda s: base64.urlsafe_b64encode(bytes.fromhex(s)).decode().rstrip('=')
    metadata = {'package': candidate['package'], 'version_name': '8.0.0', 'version_code': 800,
        'source': 'GET_ITEMS', 'restriction': 'UNAVAILABLE_COUNTRY', 'restriction_code': 4,
        'is_free': True, 'offer_type': 1, 'certificate_sets': [
            {'sha1_base64url': encode('c' * 40), 'sha256_base64url': encode(cert)}],
        'certificate_sha1_base64url': []}
    transaction = {'schema': 'pocket4-aurora-official-client-result-v1',
        'finished_utc': candidate['source']['observed_utc'], 'results': [
            {'package': candidate['package'], 'status': 'unavailable', 'reason': 'not_available_free_download'}],
        'transport': {'stopped': None}, 'auth_requests': 0, 'purchase_requests': 0,
        'android_starts': 0, 'installed_apps': 0, 'production_ready': False}
    collection = {'package': candidate['package'], 'source': retained.COLLECTION_SOURCE,
        'installer': 'com.android.vending', 'all_APK_code_paths_stable': True, 'files': [],
        'private_app_data_read': False, 'runtime_qualified_on_final_Android': False, 'production_ready': False}
    app = {'package': candidate['package'], 'source': retained.IDENTITY_SOURCE, 'errors': [],
        'static_identity_signature_qualified': True, 'all_split_package_version_signers_consistent': True,
        'historical_official_signers': [cert], 'observed_split_names': [p['split_name'] for p in candidate['apks']],
        'runtime_qualified': False, 'production_ready': False, 'private_app_data_read': False,
        'base_identity': {'package': candidate['package'], 'versionName': '8.0.0',
                         'versionCode': 800, 'longVersionCode': 800, 'minSdk': 26, 'targetSdk': 36},
        'APK_results': []}
    for pin in candidate['apks']:
        collection['files'].append({'Android_APK_code_path': '/data/app/~~cohort/com.example.app-owned/' + pin['member'],
            'path': pin['retained_path'], 'bytes': pin['bytes'], 'sha256': pin['sha256'],
            'F9': [1, 2, 33152, 1000, 1000, 1, pin['bytes'], 4, 5],
            'Android_SHA_before_and_after_equals_collected_whole_SHA': True})
        app['APK_results'].append({'file': {'path': pin['retained_path'], 'bytes': pin['bytes'], 'sha256': pin['sha256']},
            'actual_split_name': pin['split_name'], 'sameFD_final_SHA_F9_verified': True,
            'signature': {'signature_verified_by_actual_tool': True, 'tool_exit_code': 0,
                          'output_contract_complete': True, 'effective_signer_cert_SHA256': [cert]}})
    history = {'all_static_identity_signatures_qualified': True, 'runtime_qualified': False,
               'production_ready': False, 'apps': [app]}
    return candidate, metadata, transaction, collection, history


class RetainedControls(unittest.TestCase):
    def setUp(self):
        self.c, self.m, self.t, self.col, self.h = fixtures()
        self.now = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)

    def current(self):
        return retained.validate_current(self.c, self.m, self.t, self.now)

    def history(self):
        return retained.validate_history(self.c, self.col, self.h)

    def test_valid_retained_input_preserves_failed_current_download(self):
        retained.validate_candidate(self.c)
        check = self.current()
        self.assertEqual(check['current_metadata_restriction_code'], 4)
        self.assertFalse(check['current_delivery_obtained'])
        self.assertFalse(self.history()['publisher_download_digest_claimed'])

    def test_current_version_code_must_match_even_when_name_matches(self):
        self.m['version_code'] += 1
        with self.assertRaisesRegex(ValueError, 'package/version'): self.current()

    def test_current_version_name_must_match_even_when_code_matches(self):
        self.m['version_name'] = '8.0.1'
        with self.assertRaisesRegex(ValueError, 'package/version'): self.current()

    def test_current_signer_change_rejects_old_official_bytes(self):
        self.m['certificate_sets'][0]['sha256_base64url'] = base64.urlsafe_b64encode(b'\0' * 32).decode().rstrip('=')
        with self.assertRaisesRegex(ValueError, 'signer differs'): self.current()

    def test_wrong_package_rejected(self):
        self.m['package'] = 'com.example.other'
        with self.assertRaisesRegex(ValueError, 'package/version'): self.current()

    def test_country_unavailable_cannot_be_rewritten_to_available(self):
        self.m.update(restriction='AVAILABLE', restriction_code=1)
        with self.assertRaisesRegex(ValueError, 'preserved unchanged'): self.current()

    def test_current_failed_transaction_cannot_be_claimed_as_delivery(self):
        self.t['results'][0]['status'] = 'transport_complete_requires_apk_gate'
        with self.assertRaisesRegex(ValueError, 'failed acquisition'): self.current()

    def test_duplicate_current_package_rejected(self):
        self.t['results'].append(deepcopy(self.t['results'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate current'): self.current()

    def test_expired_and_future_metadata_rejected(self):
        for now in (self.now + timedelta(days=2), self.now - timedelta(days=1)):
            with self.subTest(now=now), self.assertRaisesRegex(ValueError, 'older than 24 hours'):
                retained.validate_current(self.c, self.m, self.t, now)

    def test_transaction_time_cannot_be_relabelled_as_fresh(self):
        self.c['source']['observed_utc'] = '2026-11-19T00:59:00Z'
        with self.assertRaisesRegex(ValueError, 'transaction identity'): self.current()

    def test_even_one_second_future_metadata_is_rejected(self):
        observed = retained.delivery.utc(self.t['finished_utc'])
        with self.assertRaisesRegex(ValueError, 'future-dated'):
            retained.validate_current(self.c, self.m, self.t, observed - timedelta(seconds=1))

    def test_paid_or_account_mutating_record_rejected(self):
        for field in ('auth_requests', 'purchase_requests', 'android_starts', 'installed_apps'):
            with self.subTest(field=field):
                self.t[field] = 1
                with self.assertRaisesRegex(ValueError, 'transaction identity'): self.current()
                self.t[field] = 0

    def test_missing_historical_density_split_rejected(self):
        self.col['files'].pop()
        with self.assertRaisesRegex(ValueError, 'member count'): self.history()

    def test_historical_whole_file_digest_mismatch_rejected(self):
        self.col['files'][0]['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'exact official collection'): self.history()

    def test_non_play_installer_rejected(self):
        self.col['installer'] = 'com.example.mirror'
        with self.assertRaisesRegex(ValueError, 'official code-path'): self.history()

    def test_unstable_original_collection_rejected(self):
        self.col['files'][0]['Android_SHA_before_and_after_equals_collected_whole_SHA'] = False
        with self.assertRaisesRegex(ValueError, 'not stable'): self.history()

    def test_mixed_android_code_path_cohorts_rejected(self):
        self.col['files'][1]['Android_APK_code_path'] = self.col['files'][1]['Android_APK_code_path'].replace('~~cohort', '~~other')
        with self.assertRaisesRegex(ValueError, 'mixes cohorts'): self.history()

    def test_historical_signature_failure_rejected(self):
        self.h['apps'][0]['APK_results'][0]['signature']['tool_exit_code'] = 1
        with self.assertRaisesRegex(ValueError, 'signer is not verified'): self.history()

    def test_unrelated_batch_failure_does_not_erase_qualified_selected_package(self):
        self.h['all_static_identity_signatures_qualified'] = False
        self.h['apps'].append({'package': 'com.example.unrelated', 'static_identity_signature_qualified': False})
        result = self.history()
        self.assertFalse(result['historical_batch_all_static_qualified'])
        self.assertEqual(result['qualification_scope'], 'selected_package_only')

    def test_selected_package_failure_cannot_borrow_batch_success(self):
        self.h['apps'][0]['static_identity_signature_qualified'] = False
        with self.assertRaisesRegex(ValueError, 'identity/signers/split'): self.history()

    def test_historical_release_identity_mismatch_rejected(self):
        self.h['apps'][0]['base_identity']['versionCode'] = 799
        with self.assertRaisesRegex(ValueError, 'base identity'): self.history()

    def test_historical_split_substitution_rejected(self):
        self.h['apps'][0]['APK_results'][1]['actual_split_name'] = 'config.arm64_v8a'
        with self.assertRaisesRegex(ValueError, 'APK pin differs'): self.history()

    def test_non_native_x86_candidate_rejected(self):
        for abi in ('arm64-v8a', 'armeabi-v7a', 'x86'):
            with self.subTest(abi=abi):
                self.c['selected_abi'] = abi
                with self.assertRaisesRegex(ValueError, 'native x86_64'): retained.validate_candidate(self.c)

    def test_undeclared_abi_in_retained_member_rejected(self):
        self.c['apks'][1]['native_abis'] = ['arm64-v8a']
        with self.assertRaisesRegex(ValueError, 'undeclared execution ABI'): retained.validate_candidate(self.c)

    def test_duplicate_or_missing_base_rejected(self):
        self.c['apks'].append(deepcopy(self.c['apks'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicated'): retained.validate_candidate(self.c)

    def test_boolean_version_code_rejected(self):
        self.c['version_code'] = True
        with self.assertRaisesRegex(ValueError, 'version_code'): retained.validate_candidate(self.c)

    def test_new_delivery_claim_rejected(self):
        self.c['source']['current_delivery_obtained'] = True
        with self.assertRaisesRegex(ValueError, 'cannot claim'): retained.validate_candidate(self.c)

    def test_source_pin_cannot_alias_an_apk(self):
        self.c['source']['current_metadata']['path'] = self.c['apks'][0]['retained_path']
        with self.assertRaisesRegex(ValueError, 'paths alias'): retained.validate_candidate(self.c)

    def test_current_delivery_gate_still_requires_available_metadata(self):
        with self.assertRaisesRegex(ValueError, 'does not authorize'):
            retained.delivery.validate_source(self.c, self.m, {}, {})

    def test_tampered_source_pin_fails_before_sdk_or_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for key, value in zip(retained.EVIDENCE_KEYS, (self.col, self.h, self.m, self.t)):
                body = (json.dumps(value) + '\n').encode()
                path = root / (key + '.json')
                path.write_bytes(body)
                self.c['source'][key] = {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
            candidate = root / 'candidate.json'
            raw = json.dumps(self.c).encode()
            candidate.write_bytes(raw)
            (root / 'current_metadata.json').write_bytes(b'{}')
            output = root / 'receipt.json'
            with mock.patch.object(retained.single, 'verify') as sdk:
                with self.assertRaisesRegex(ValueError, 'external pin'):
                    retained.verify_retained(root / 'sdk', candidate, hashlib.sha256(raw).hexdigest(), output)
                sdk.assert_not_called()
            self.assertFalse(output.exists())

    def test_existing_receipt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / 'receipt.json'
            output.write_text('preserved')
            with self.assertRaisesRegex(ValueError, 'new absolute file'):
                retained.verify_retained(root, root / 'candidate.json', 'a' * 64, output)
            self.assertEqual(output.read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()
