#!/usr/bin/env python3
"""Fixed-input acceptance/refusal tests; no compiler, installation or guest."""
from contextlib import redirect_stdout
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


class SourceInputs(unittest.TestCase):
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
        for entry in filter(None, TREE.split(b'\0')):
            metadata, raw_name = entry.split(b'\t', 1)
            name = os.fsdecode(raw_name)
            if name in VERIFY.BUILD_INPUTS or name.endswith('Cargo.toml'):
                target = self.source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(VERIFY.SOURCE / name, target)
                target.chmod(0o755 if metadata.startswith(b'100755 ') else 0o644)

    def check(self):
        output = io.StringIO()
        with mock.patch.object(VERIFY, 'ROOT', self.root), \
                mock.patch.object(VERIFY, 'SOURCE', self.source), \
                mock.patch.object(VERIFY.subprocess, 'check_output', return_value=TREE), \
                mock.patch('sys.argv', ['verify-source.py']), redirect_stdout(output):
            status = VERIFY.main()
        return status, json.loads(output.getvalue())

    def test_exact_derived_host_inputs_are_distinguished_from_upstream(self):
        status, report = self.check()
        self.assertEqual(status, 0, report)
        self.assertEqual(report['checked_files'], 118)
        self.assertEqual(set(report['approved_host_osdk_derivations']),
                         {'osdk/Cargo.toml', 'osdk/Cargo.lock'})
        self.assertEqual(report['input_sha256']['Cargo.lock'],
                         '6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316')

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

    def test_kernel_lock_still_exact_upstream(self):
        self.refuse_change('Cargo.lock')

    def test_kernel_manifest_still_exact_upstream(self):
        self.refuse_change('kernel/core/Cargo.toml')

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
