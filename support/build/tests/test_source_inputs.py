#!/usr/bin/env python3
"""Fixed-input acceptance/refusal tests; no compiler, installation or guest."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

BUILD = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('source_inputs', BUILD / 'verify-source.py')
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)
TREE = subprocess.check_output(['git', 'ls-tree', '-rz', VERIFY.PINNED_TREE], cwd=VERIFY.ROOT)
LOCAL_TREE = subprocess.check_output(
    ['git', 'ls-tree', '-rz', 'HEAD', '--', 'libs/os-control'], cwd=VERIFY.ROOT)


class SourceInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Originals come from the actual pinned Git objects. Approved downstream
        # fixtures come from project HEAD, independently of the derivation code.
        cls.originals, cls.fixtures, cls.selected_entries = {}, {}, []
        downstream = set(VERIFY.DOWNSTREAM_MANIFEST_ADDITIONS) | set(VERIFY.G1C_FEATURE_ADDITIONS) | {'Cargo.lock'}
        for entry in filter(None, TREE.split(b'\0')):
            metadata, raw_name = entry.split(b'\t', 1)
            mode, kind, blob = metadata.decode().split()
            name = os.fsdecode(raw_name)
            if name not in VERIFY.BUILD_INPUTS and not name.endswith('Cargo.toml'):
                continue
            original = subprocess.check_output(['git', 'cat-file', 'blob', blob], cwd=VERIFY.ROOT)
            cls.originals[blob] = original
            if name in downstream:
                content = subprocess.check_output(
                    ['git', 'show', 'HEAD:kernel/asterinas/' + name], cwd=VERIFY.ROOT)
            elif name in VERIFY.APPROVED_HOST_OSDK_INPUTS:
                content = (VERIFY.SOURCE / name).read_bytes()
            else:
                content = original
            cls.fixtures[name] = (mode, blob, content)
            cls.selected_entries.append(entry)
        cls.selected_tree = b'\0'.join(cls.selected_entries) + b'\0'
        cls.local_fixtures = {}
        for entry in filter(None, LOCAL_TREE.split(b'\0')):
            metadata, raw_name = entry.split(b'\t', 1)
            mode, kind, blob = metadata.decode().split()
            name = os.fsdecode(raw_name)
            if name.endswith('.rs') or name.rsplit('/', 1)[-1] in {'Cargo.toml', 'Cargo.lock'}:
                content = subprocess.check_output(['git', 'cat-file', 'blob', blob], cwd=VERIFY.ROOT)
                cls.local_fixtures[name] = (mode, content)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='a01-source-inputs-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'kernel/asterinas'
        (self.root / 'support').mkdir()
        (self.root / 'README.md').write_bytes(b'')
        (self.root / 'support/upstream-lock.json').write_text(json.dumps({'kernel': {
            'commit': VERIFY.PINNED_COMMIT, 'tree': VERIFY.PINNED_TREE,
            'toolchain': VERIFY.PINNED_TOOLCHAIN}}))
        for name, (mode, blob, content) in self.fixtures.items():
            self.write_fixture(self.source / name, mode, content)
        for name, (mode, content) in self.local_fixtures.items():
            self.write_fixture(self.root / name, mode, content)

    @staticmethod
    def write_fixture(target, mode, content):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755 if mode == '100755' else 0o644)

    def check(self, *, pristine=False, tree=None, originals=None, local_tree=None):
        def git_output(command, *, cwd):
            self.assertEqual(cwd, self.root)
            if command == ['git', 'ls-tree', '-rz', VERIFY.PINNED_TREE]:
                return TREE if tree is None else tree
            if command == ['git', 'ls-tree', '-rz', 'HEAD', '--', 'libs/os-control']:
                return LOCAL_TREE if local_tree is None else local_tree
            if command[:3] == ['git', 'cat-file', 'blob'] and len(command) == 4:
                return (self.originals if originals is None else originals)[command[3]]
            raise AssertionError('unexpected Git invocation: ' + repr(command))

        output = io.StringIO()
        argv = ['verify-source.py'] + (['--pristine'] if pristine else [])
        with mock.patch.object(VERIFY, 'ROOT', self.root), \
                mock.patch.object(VERIFY, 'SOURCE', self.source), \
                mock.patch.object(VERIFY.subprocess, 'check_output', side_effect=git_output), \
                mock.patch('sys.argv', argv), redirect_stdout(output):
            status = VERIFY.main()
        return status, json.loads(output.getvalue())

    def test_kernel_and_host_derivations_coexist_with_original_seed_identity(self):
        status, report = self.check()
        self.assertEqual(status, 0, report)
        self.assertEqual(report['checked_files'], 118)
        self.assertEqual(set(report['approved_host_osdk_derivations']),
                         {'osdk/Cargo.toml', 'osdk/Cargo.lock'})
        self.assertEqual(set(report['downstream_manifests']),
                         {'Cargo.toml', 'kernel/Cargo.toml', 'kernel/core/Cargo.toml'})
        lock = report['downstream_locks']['Cargo.lock']
        self.assertEqual(lock['upstream_sha256'],
                         '6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316')
        self.assertEqual(lock['derived_sha256'],
                         'af94d71680ecf3b9631e21c958263d5e41229033214f88dcff858bb14765a666')
        self.assertEqual(report['input_sha256']['Cargo.lock'], lock['derived_sha256'])
        self.assertNotEqual(lock['upstream_sha256'], lock['derived_sha256'])
        local = report['local_dependency_inputs']
        self.assertEqual(set(local), set(self.local_fixtures))
        self.assertIn('libs/os-control/src/resource_state.rs', local)
        self.assertTrue(all(item['matches_head'] for item in local.values()))

    def refuse_change(self, name):
        with (self.source / name).open('ab') as output:
            output.write(b'\n# unapproved input\n')
        status, report = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any(error.startswith(name + ':') for error in report['errors']), report)

    def test_other_host_lock_bytes_refused(self):
        self.refuse_change('osdk/Cargo.lock')

    def test_other_host_manifest_bytes_refused(self):
        self.refuse_change('osdk/Cargo.toml')

    def test_kernel_lock_drift_beyond_exact_approved_insertions_refused(self):
        self.refuse_change('Cargo.lock')

    def test_kernel_manifest_drift_beyond_exact_approved_insertions_refused(self):
        self.refuse_change('kernel/core/Cargo.toml')

    def test_optional_profile_declaration_cannot_be_silently_removed(self):
        path = self.source / 'kernel/Cargo.toml'
        content = path.read_bytes()
        self.assertIn(b'g1c-trusted-observe', content)
        path.write_bytes(b'\n'.join(line for line in content.split(b'\n')
                                    if not line.startswith(b'g1c-trusted-observe')))
        status, report = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any(error.startswith('kernel/Cargo.toml:') for error in report['errors']))

    def test_original_upstream_lock_seed_is_independently_checked(self):
        originals = self.originals.copy()
        blob = self.fixtures['Cargo.lock'][1]
        originals[blob] += b'\n# changed original\n'
        status, report = self.check(originals=originals)
        self.assertEqual(status, 1)
        self.assertIn('Cargo.lock: original upstream root lock seed changed', report['errors'])

    def test_toolchain_still_exact_upstream(self):
        self.refuse_change('rust-toolchain.toml')

    def test_approved_host_lock_symlink_refused(self):
        path = self.source / 'osdk/Cargo.lock'
        original = path.with_suffix('.original')
        path.rename(original)
        path.symlink_to(original)
        self.assertEqual(self.check()[0], 1)

    def test_approved_host_manifest_mode_refused(self):
        (self.source / 'osdk/Cargo.toml').chmod(0o755)
        self.assertEqual(self.check()[0], 1)

    def test_pristine_rejects_all_approved_derivations(self):
        status, report = self.check(pristine=True, tree=self.selected_tree)
        self.assertEqual(status, 1)
        failed = {error.split(':', 1)[0] for error in report['errors']}
        self.assertEqual(failed, {'Cargo.toml', 'Cargo.lock', 'kernel/Cargo.toml',
                                 'kernel/core/Cargo.toml', 'osdk/Cargo.toml', 'osdk/Cargo.lock'})
        self.assertEqual(report['approved_host_osdk_derivations'], {})
        self.assertEqual(report['downstream_locks'], {})
        self.assertEqual(report['local_dependency_inputs'], {})

    def test_pristine_original_inputs_need_no_downstream_crate(self):
        for name, (mode, blob, content) in self.fixtures.items():
            self.write_fixture(self.source / name, mode, self.originals[blob])
        shutil.rmtree(self.root / 'libs')
        status, report = self.check(pristine=True, tree=self.selected_tree)
        self.assertEqual(status, 0, report)
        self.assertEqual(report['checked_files'], 118)

    def test_local_dependency_rust_change_is_recorded_without_freezing_development(self):
        name = 'libs/os-control/src/lib.rs'
        path = self.root / name
        path.write_bytes(path.read_bytes() + b'\n// development change\n')
        status, report = self.check()
        self.assertEqual(status, 0, report)
        item = report['local_dependency_inputs'][name]
        self.assertFalse(item['matches_head'])
        self.assertEqual(item['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertNotEqual(item['head_git_blob'], item['actual_git_blob'])

    def test_local_dependency_manifest_drift_is_refused(self):
        path = self.root / 'libs/os-control/Cargo.toml'
        path.write_bytes(path.read_bytes() + b'\n# new dependency metadata\n')
        status, report = self.check()
        self.assertEqual(status, 1)
        self.assertIn('libs/os-control/Cargo.toml: local dependency build metadata differs from HEAD', report['errors'])

    def test_local_dependency_lock_drift_is_refused(self):
        path = self.root / 'libs/os-control/Cargo.lock'
        path.write_bytes(path.read_bytes() + b'\n# new resolution\n')
        self.assertEqual(self.check()[0], 1)

    def test_local_dependency_missing_source_is_refused(self):
        (self.root / 'libs/os-control/src/lib.rs').unlink()
        status, report = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any(error.startswith('libs/os-control/src/lib.rs:') for error in report['errors']))

    def test_local_dependency_symlink_is_refused(self):
        path = self.root / 'libs/os-control/src/lib.rs'
        original = path.with_suffix('.original')
        path.rename(original)
        path.symlink_to(original)
        self.assertEqual(self.check()[0], 1)

    def test_local_dependency_mode_change_is_refused(self):
        (self.root / 'libs/os-control/src/lib.rs').chmod(0o755)
        self.assertEqual(self.check()[0], 1)

    def test_local_dependency_absent_from_head_is_refused(self):
        status, report = self.check(local_tree=b'')
        self.assertEqual(status, 1)
        self.assertIn('libs/os-control/Cargo.toml: required local dependency input is not tracked in HEAD', report['errors'])

    def test_root_readme_guard_preserved(self):
        (self.root / 'README.md').write_bytes(b'x')
        with self.assertRaisesRegex(SystemExit, 'README must be empty'):
            self.check()

    def test_kernel_source_pin_guard_preserved(self):
        path = self.root / 'support/upstream-lock.json'
        lock = json.loads(path.read_text())
        lock['kernel']['commit'] = '0' * 40
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(SystemExit, 'fixed upstream inputs changed'):
            self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
