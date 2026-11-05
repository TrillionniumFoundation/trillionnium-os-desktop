#!/usr/bin/env python3
"""Small integrity regressions; all positive gate reviews below are synthetic."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
import update_matrix as matrix
from parse_launcher_inventory import parse_launchers

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text())


class Integrity(unittest.TestCase):
    def setUp(self):
        self.base = load('inputs/launcher-matrix-baseline-20261104.json')
        self.history = load('inputs/historical-readiness-20261104.json')
        self.plans = load('app-gates.json')
        self.progress = load('progress.json')
        self.inv = load('inputs/current-installed-inventory-derived-20261105.json')

    def build(self, reviews=(), identities=()):
        return matrix.build_matrix(self.base, self.history, self.plans, self.progress, self.inv, reviews,
                                   package_identities=identities)

    def identity(self, package, digest, when, kind='read_only', suffix='A'):
        installed = next(r for r in self.inv['installed_packages'] if r['package'] == package)
        result = {**installed, 'id': 'synthetic-identity-' + suffix, 'android_user': 0,
                  'framework_epoch_sha256': self.inv['framework_epoch_sha256'], 'kind': kind,
                  'observed_at_utc': when, '_evidence_verified': True,
                  'apks': [{'split_name': None, 'sha256': digest, 'bytes': 123,
                            'signer_certificate_sha256': ['f' * 64]}],
                  'evidence': [{'path': 'synthetic-only', 'bytes': 0, 'sha256': '0' * 64}]}
        result['_apk_set_sha256'] = matrix.apk_set_hash(result['apks'])
        return result

    def complete_review(self):
        package = 'com.android.camera2'
        installed = next(r for r in self.inv['installed_packages'] if r['package'] == package)
        gates = set(self.plans['common_gates']) | set(self.plans['profiles']['camera']['checks'])
        cutoff = matrix.stamp(self.inv['observed_at_utc'])
        for observation in self.progress['apps']:
            if (observation['package'] == package and observation.get('unpassed_checks')
                    and observation.get('framework_epoch_sha256') == self.inv['framework_epoch_sha256']
                    and observation.get('version_code') == installed['version_code']):
                cutoff = max(cutoff, matrix.stamp(observation.get('observed_at_utc') or observation['reviewed_at_utc']))
        return {'id': 'synthetic-test-only-A', '_evidence_verified': True, 'package': package,
            'scope': 'whole_app_release', 'framework_epoch_sha256': self.inv['framework_epoch_sha256'],
            'version_code': installed['version_code'], 'uid': installed['uid'], 'apk_sha256': 'a' * 64,
            'observed_at_utc': (cutoff + timedelta(seconds=1)).isoformat(),
            'checks': {key: 'passed' for key in gates}, 'all_features_reviewed': True,
            'retained_failures_reconciled': True, 'unresolved_findings': []}

    def test_actual_inventory_and_all_baseline_entries(self):
        raw = (ROOT / 'inputs/launchers.stdout').read_bytes()
        components, metadata, headers = parse_launchers(raw)
        self.assertEqual((len(components), len(metadata), len(headers)), (45, 45, 91))
        self.assertEqual(components, self.inv['launcher_components'])
        result = self.build()
        self.assertEqual((result['tracked_app_count'], result['production_ready_count']), (45, 0))
        self.assertEqual(result['current_installed_package_count'], 186)
        self.assertEqual(result['current_third_party_package_count'], 44)
        self.assertFalse(result['all_apps_production_ready'])
        self.assertTrue(matrix.RETAIN <= {row['package'] for row in result['apps']})

    def test_incomplete_or_corrupt_inputs_cannot_qualify(self):
        with self.assertRaises(ValueError):
            matrix.inventory_data(load('inputs/current-installed-inventory-20261105.json'))
        raw = (ROOT / 'inputs/launchers.stdout').read_bytes()
        bad = [raw.replace(b'45 activities found:', b'44 activities found:', 1),
               raw.replace(b'Activity #1:', b'Activity #0:', 1),
               raw + b'Unknown provider row\n',
               raw.replace(b'preferredOrder=0', b'newUnknownField=0', 1),
               raw.replace(b'com.android.camera2/com.android.camera.CameraLauncher',
                           b'com.android.calendar/.AllInOneActivity', 1)]
        for value in bad:
            with self.subTest(changed=value[:100]), self.assertRaises(ValueError):
                parse_launchers(value)
        self.base['all_apps_production_ready'] = True
        for row in self.base['apps']:
            row['production_ready'] = True
        self.assertEqual(self.build()['production_ready_count'], 0)

    def test_union_retains_absent_fixture_and_new_launcher(self):
        gone, new = 'local.pocket4.fixture', 'example.newapp'
        self.inv['installed_packages'] = [r for r in self.inv['installed_packages'] if r['package'] != gone]
        self.inv['installed_packages'].append({'package': new, 'uid': 11001, 'version_code': 1})
        self.inv['launcher_components'] = [c for c in self.inv['launcher_components'] if not c.startswith(gone + '/')]
        self.inv['launcher_components'].append(new + '/.Main')
        self.inv['launcher_packages'] = sorted(set(self.inv['launcher_packages']) - {gone} | {new})
        self.inv['third_party_packages'] = sorted(set(self.inv['third_party_packages']) - {gone} | {new})
        result = self.build()
        rows = {r['package']: r for r in result['apps']}
        self.assertEqual(result['tracked_app_count'], 46)
        self.assertEqual(rows[gone]['inventory_state'], 'not_installed')
        self.assertEqual(rows[new]['profile'], 'unclassified')
        self.assertEqual(result['new_launcher_packages'], [new])
        self.assertFalse(result['all_apps_production_ready'])

    def test_review_scope_epoch_and_same_version_apk_cannot_mix(self):
        review = self.complete_review()
        instant = matrix.stamp(review['observed_at_utc'])
        identity = self.identity(review['package'], 'a' * 64, (instant - timedelta(seconds=1)).isoformat())
        self.assertEqual(self.build([review], [identity])['production_ready_count'], 1)
        earlier = {**review, 'observed_at_utc': (instant - timedelta(seconds=2)).isoformat()}
        self.assertEqual(self.build([earlier], [identity])['production_ready_count'], 0)
        scoped = {**review, 'scope': 'scoped'}
        with self.assertRaises(ValueError):
            self.build([scoped], [identity])
        stale = {**review, 'framework_epoch_sha256': '0' * 64}
        self.assertEqual(self.build([stale], [identity])['production_ready_count'], 0)
        replaced = {**review, 'id': 'synthetic-test-only-B', 'apk_sha256': 'b' * 64,
                    'scope': 'scoped', 'checks': {'identity': 'passed'},
                    'observed_at_utc': (instant + timedelta(seconds=2)).isoformat()}
        new_identity = self.identity(review['package'], 'b' * 64, (instant + timedelta(seconds=1)).isoformat(),
                                     'package_install', 'B')
        self.assertEqual(self.build([review, replaced], [identity, new_identity])['production_ready_count'], 0)

    def test_install_without_new_review_invalidates_old_binary(self):
        review = self.complete_review()
        after = (matrix.stamp(review['observed_at_utc']) + timedelta(seconds=1)).isoformat()
        installed = self.identity(review['package'], 'b' * 64, after, 'package_install', 'B')
        result = self.build([review], [installed])
        self.assertEqual(result['production_ready_count'], 0)
        row = next(r for r in result['apps'] if r['package'] == review['package'])
        self.assertEqual(row['accepted_reviews'], [])
        self.assertEqual(row['gate_results']['lifecycle'], 'pending')
        self.assertIn('review_apk_differs_from_latest_installed_observation',
                      [r['reason'] for r in result['ignored_reviews']])

    def test_readonly_same_hash_preserves_scope_but_reinstall_does_not(self):
        review = self.complete_review()
        after = (matrix.stamp(review['observed_at_utc']) + timedelta(seconds=1)).isoformat()
        observed = self.identity(review['package'], 'a' * 64, after)
        self.assertEqual(self.build([review], [observed])['production_ready_count'], 1)
        installed = {**observed, 'kind': 'package_install'}
        self.assertEqual(self.build([review], [installed])['production_ready_count'], 0)

    def test_rollback_to_original_bytes_cannot_revive_preinstall_review(self):
        review = self.complete_review()
        instant = matrix.stamp(review['observed_at_utc'])
        identities = [self.identity(review['package'], digest * 64, (instant + timedelta(seconds=offset)).isoformat(),
                                    kind, str(offset)) for digest, offset, kind in
                      [('a', -1, 'read_only'), ('b', 1, 'package_install'), ('a', 2, 'package_install')]]
        self.assertEqual(self.build([review], identities)['production_ready_count'], 0)
        fresh = {**review, 'observed_at_utc': (instant + timedelta(seconds=3)).isoformat()}
        self.assertEqual(self.build([fresh], identities)['production_ready_count'], 1)

    def test_independent_identity_required_and_split_set_must_match(self):
        review = self.complete_review()
        self.assertEqual(self.build([review])['production_ready_count'], 0)
        observed = self.identity(review['package'], 'a' * 64, review['observed_at_utc'])
        observed['apks'].append({'split_name': 'config.x86_64', 'sha256': 'b' * 64,
                                'bytes': 456, 'signer_certificate_sha256': ['f' * 64]})
        observed['_apk_set_sha256'] = matrix.apk_set_hash(observed['apks'])
        self.assertEqual(self.build([review], [observed])['production_ready_count'], 0)
        pinned = {**review, 'apk_set_sha256': observed['_apk_set_sha256']}
        self.assertEqual(self.build([pinned], [observed])['production_ready_count'], 1)
        conflicting = {**observed, 'uid': observed['uid'] + 1}
        self.assertEqual(self.build([pinned], [conflicting])['production_ready_count'], 0)

    def test_identity_evidence_tamper_and_ambiguous_apk_members_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = b'synthetic independent observation\n'
            (root / 'receipt.txt').write_bytes(evidence)
            observed = self.identity('com.android.camera2', 'a' * 64, self.inv['observed_at_utc'])
            observed['evidence'] = [{'path': 'receipt.txt', 'bytes': len(evidence), 'sha256': matrix.sha(evidence)}]
            document = {'schema': 'pocket4-package-identity-observations-v1', 'observations': [observed]}
            def write():
                (root / 'identities.json').write_text(json.dumps(document))
            write()
            self.assertEqual(len(matrix.checked_package_identities(root / 'identities.json')[0]), 1)
            (root / 'receipt.txt').write_bytes(evidence + b'changed')
            with self.assertRaisesRegex(ValueError, 'hash or size differs'):
                matrix.checked_package_identities(root / 'identities.json')
            (root / 'receipt.txt').write_bytes(evidence)
            observed['apks'].append(deepcopy(observed['apks'][0]));write()
            with self.assertRaisesRegex(ValueError, 'duplicate base/split'):
                matrix.checked_package_identities(root / 'identities.json')


if __name__ == '__main__':
    unittest.main(verbosity=2)
