"""Host tests only: no Android, ADB, account, APK installation or network."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import types
import unittest

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / 'manifest.json').read_text())

def load(name, raw=None):
    path = ROOT / 'source' / name
    raw = path.read_bytes() if raw is None else raw
    mod = types.ModuleType(name.replace('.', '_'))
    mod.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), mod.__dict__)
    return mod

class CurrentIHGIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = load('app_common.py')
        cls.profile = load('app_profiles.py')
        cls.artifacts = load('ihg_artifacts.py')
        old = (ROOT / 'source/app_profiles.py').read_text()
        for before, after in reversed(MANIFEST['literal_changes']['app_profiles.py']):
            old = old.replace(after, before, 1)
        cls.old_raw = old.encode()
        cls.old = load('app_profiles.py', cls.old_raw)
        cls.current = b'package:com.ihg.apps.android versionCode:50023496 uid:10137\n'
        cls.old_meta = b'package:com.ihg.apps.android versionCode:50023219 uid:10137\n'
        cls.record = [{'bytes': MANIFEST['official_candidate']['bytes'],
            'sha256': MANIFEST['official_candidate']['sha256'],
            'held_file': {'fixture': 'host-only'},
            'stat_file': {'fixture': 'host-only', 'ctime_ns': 0}}]
        cls.target = {'package': 'com.ihg.apps.android', 'uid': 10137,
                      'user': 0, 'version_code': 50023496}

    def test_complete_source_inventory(self):
        rows = MANIFEST['sources']
        self.assertEqual(len(rows), 31)
        self.assertEqual({r['path'] for r in rows},
                         {str(p.relative_to(ROOT)) for p in (ROOT / 'source').iterdir()})
        for row in rows:
            p = ROOT / row['path']
            self.assertFalse(p.is_symlink())
            raw = p.read_bytes()
            self.assertEqual(len(raw), row['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            ast.parse(raw, filename=row['path'])

    def test_29_unchanged_files_and_four_exact_literal_changes(self):
        changed = []
        for row in MANIFEST['sources']:
            raw = (ROOT / row['path']).read_bytes()
            original = MANIFEST['original_sources'][Path(row['path']).name]
            if hashlib.sha256(raw).hexdigest() != original['sha256']:
                changed.append(Path(row['path']).name)
                text = raw.decode()
                for before, after in reversed(MANIFEST['literal_changes'][changed[-1]]):
                    self.assertEqual(text.count(after), 1)
                    text = text.replace(after, before, 1)
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), original['sha256'])
                self.assertEqual(len(text.encode()), original['bytes'])
        self.assertEqual(changed, ['app_profiles.py', 'ihg_artifacts.py'])
        self.assertEqual(sum(map(len, MANIFEST['literal_changes'].values())), 4)

    def test_current_metadata(self):
        self.assertEqual(self.common.package_metadata(self.current, self.profile.IHG), self.target)

    def test_reproduced_old_metadata_guard_failure(self):
        with self.assertRaises(RuntimeError):
            self.common.package_metadata(self.current, self.old.IHG)

    def test_old_and_future_versions_rejected(self):
        for raw in [self.old_meta, self.current.replace(b'50023496', b'50023497')]:
            with self.assertRaises(RuntimeError):
                self.common.package_metadata(raw, self.profile.IHG)

    def test_wrong_uid_rejected(self):
        with self.assertRaises(RuntimeError):
            self.common.package_metadata(self.current.replace(b'10137', b'10138'), self.profile.IHG)

    def test_current_official_artifact(self):
        self.common.validate_artifacts(self.record, self.profile.IHG)

    def test_reproduced_old_artifact_guard_failure(self):
        with self.assertRaises(RuntimeError):
            self.common.validate_artifacts(self.record, self.old.IHG)

    def test_changed_hash_and_size_rejected(self):
        for key, value in [('sha256', '0' * 64), ('bytes', self.record[0]['bytes'] + 1)]:
            altered = copy.deepcopy(self.record)
            altered[0][key] = value
            with self.assertRaises(RuntimeError):
                self.common.validate_artifacts(altered, self.profile.IHG)

    def test_missing_or_extra_apk_rejected(self):
        for rows in [[], self.record * 2]:
            with self.assertRaises(RuntimeError):
                self.common.validate_artifacts(rows, self.profile.IHG)

    def test_artifact_guard_current_identity(self):
        self.artifacts.ArtifactSet(None, {'target': self.target}, None)

    def test_artifact_guard_old_identity_rejected(self):
        with self.assertRaises(RuntimeError):
            self.artifacts.ArtifactSet(None, {'target': {**self.target, 'version_code': 50023219}}, None)

    def test_existing_limits_and_clock_profiles_preserved(self):
        for name in ['CLOCK', 'CLOCK_HELPER', 'CLOCK_LIMITS', 'IHG_LIMITS']:
            self.assertEqual(getattr(self.profile, name), getattr(self.old, name))

    def test_ihg_other_identity_fields_preserved(self):
        self.assertEqual({k: v for k, v in self.profile.IHG.items() if k not in ('version_code', 'apks')},
                         {k: v for k, v in self.old.IHG.items() if k not in ('version_code', 'apks')})

    def test_no_runtime_acceptance_is_claimed(self):
        result = json.loads((ROOT / 'host-result.json').read_text())
        for key in ['runtime_qualified', 'production_ready', 'canonical_selection_changed']:
            self.assertIs(result[key], False)
        for key in ['runtime_accepted', 'Android_actions', 'apps_installed']:
            self.assertEqual(result[key], 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
