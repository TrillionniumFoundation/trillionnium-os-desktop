# SPDX-License-Identifier: MPL-2.0
"""Run the real source verifier against isolated copies, never mutate the tree."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('source_verifier', ROOT/'support/build/verify-source.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
GIT = subprocess.check_output


class SourceInputsTests(unittest.TestCase):
    def check_copy(self, name=None, transform=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for fixed in ['README.md','support/upstream-lock.json']:
                target = root/fixed;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/fixed,target)
            entries = GIT(['git','ls-tree','-rz',verifier.PINNED_TREE],cwd=ROOT).split(b'\0')
            for entry in filter(None,entries):
                _, raw_name = entry.split(b'\t',1)
                relative = raw_name.decode()
                if relative not in verifier.BUILD_INPUTS and not relative.endswith('Cargo.toml'):
                    continue
                target = root/'kernel/asterinas'/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/'kernel/asterinas'/relative,target)
            if name:
                target=root/'kernel/asterinas'/name
                target.write_bytes(transform(target.read_bytes()))
            def original_git(argv, **kwargs):
                return GIT(argv, **{**kwargs,'cwd':ROOT})
            output = io.StringIO()
            with patch.object(verifier,'ROOT',root), patch.object(verifier,'SOURCE',root/'kernel/asterinas'), \
                    patch.object(verifier.subprocess,'check_output',original_git), \
                    patch.object(sys,'argv',['verify-source.py']), contextlib.redirect_stdout(output):
                result=verifier.main()
            return result,json.loads(output.getvalue())

    def test_exact_fixture_declaration_passes_without_a_fake_dependency(self):
        code, report=self.check_copy()
        self.assertEqual(code,0)
        manifest=report['downstream_manifests']['ostd/Cargo.toml']
        self.assertIsNone(manifest['local_dependency'])
        self.assertEqual(manifest['optional_profiles'],['dma-domain-ktest'])

    def test_unlisted_feature_or_dependency_change_is_rejected(self):
        for change in [lambda b:b+b'\nextra-unreviewed = []\n',
                       lambda b:b.replace(b'dma-domain-ktest = []',b'dma-domain-ktest = ["cvm_guest"]'),
                       lambda b:b.replace(b'default = ["cvm_guest"]',b'default = ["dma-domain-ktest"]')]:
            code,report=self.check_copy('ostd/Cargo.toml',change)
            self.assertEqual(code,1)
            self.assertTrue(any(item.startswith('ostd/Cargo.toml:') for item in report['errors']))

    def test_other_manifest_and_lock_remain_exact(self):
        for name in ['kernel/Cargo.toml','Cargo.lock','osdk/Cargo.lock']:
            code,report=self.check_copy(name,lambda b:b+b'\n# unreviewed drift\n')
            self.assertEqual(code,1)
            self.assertTrue(any(item.startswith(name+':') for item in report['errors']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
