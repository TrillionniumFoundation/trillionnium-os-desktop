#!/usr/bin/env python3
"""Real optimized-process tamper rejection checks for the offline verifier."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parent


class OptimizedVerifierTamperTests(unittest.TestCase):
    def reject(self, kind):
        with tempfile.TemporaryDirectory(prefix='native600-verifier-tamper-') as directory:
            copy = Path(directory) / 'capsule'
            shutil.copytree(BASE, copy)
            if kind == 'original':
                p = copy / 'ai395_native_controller.r4.py'
                p.write_bytes(p.read_bytes() + b'\n# tamper fixture\n')
                expected = b'capsule file verification failed: ai395_native_controller.r4.py'
            elif kind == 'patch':
                p = copy / 'allocation-observer.patch'
                p.write_bytes(p.read_bytes() + b'\n')
                expected = b'capsule file verification failed: allocation-observer.patch'
            elif kind == 'candidate_sha':
                p = copy / 'manifest.json'
                data = json.loads(p.read_text())
                data['controller_candidate_sha256'] = '0' * 64
                p.write_text(json.dumps(data))
                expected = b'candidate controller SHA-256 differs'
            else:
                raise RuntimeError('unknown tamper case')
            env = dict(os.environ, GIT_DIR='/untrusted/nonexistent/git',
                       GIT_WORK_TREE='/untrusted/nonexistent/worktree', GIT_CONFIG_COUNT='1',
                       GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0='/untrusted/nonexistent')
            run = subprocess.run([sys.executable, '-O', '-B', str(copy / 'verify.py')],
                                 capture_output=True, env=env, timeout=15)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn(expected, run.stderr)
            self.assertNotIn(b'"candidate_hash_verified": true', run.stdout)
            self.assertNotIn(b'"state": "PASS"', run.stdout)

    def test_optimized_verifier_rejects_original_tamper(self):
        self.reject('original')

    def test_optimized_verifier_rejects_patch_or_candidate_sha_tamper(self):
        for kind in ['patch', 'candidate_sha']:
            with self.subTest(kind=kind):
                self.reject(kind)


if __name__ == '__main__':
    unittest.main(verbosity=2)
