#!/usr/bin/env python3
"""Small integrity regressions; all positive gate reviews below are synthetic."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
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

    def build(self, reviews=()):
        return matrix.build_matrix(self.base, self.history, self.plans, self.progress, self.inv, reviews)

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
        package = 'com.android.camera2'
        identity = next(r for r in self.inv['installed_packages'] if r['package'] == package)
        gates = set(self.plans['common_gates']) | set(self.plans['profiles']['camera']['checks'])
        review = {'id': 'synthetic-test-only-A', '_evidence_verified': True, 'package': package,
            'scope': 'whole_app_release', 'framework_epoch_sha256': self.inv['framework_epoch_sha256'],
            'version_code': identity['version_code'], 'uid': identity['uid'], 'apk_sha256': 'a' * 64,
            'observed_at_utc': (matrix.stamp(self.inv['observed_at_utc']) + timedelta(minutes=30)).isoformat(),
            'checks': {key: 'passed' for key in gates}, 'all_features_reviewed': True,
            'retained_failures_reconciled': True, 'unresolved_findings': []}
        self.assertEqual(self.build([review])['production_ready_count'], 1)
        scoped = {**review, 'scope': 'scoped'}
        with self.assertRaises(ValueError):
            self.build([scoped])
        stale = {**review, 'framework_epoch_sha256': '0' * 64}
        self.assertEqual(self.build([stale])['production_ready_count'], 0)
        replaced = {**review, 'id': 'synthetic-test-only-B', 'apk_sha256': 'b' * 64,
                    'scope': 'scoped', 'checks': {'identity': 'passed'},
                    'observed_at_utc': (matrix.stamp(review['observed_at_utc']) + timedelta(seconds=1)).isoformat()}
        self.assertEqual(self.build([review, replaced])['production_ready_count'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
