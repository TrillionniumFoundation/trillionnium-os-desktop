"""A09-only fixture tests of the shell CI gate, never GPU or Rust execution."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'support/vmm/verify.sh'


class VerifyEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a09-gate-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        script = self.root / 'support/vmm/verify.sh'
        script.parent.mkdir(parents=True)
        shutil.copy2(SOURCE, script)
        (self.root / 'README.md').write_bytes(b'')
        suite = self.root / 'tests/hardware'
        suite.mkdir(parents=True)
        (suite / 'test_fixture.py').write_text('import unittest\nclass Fixture(unittest.TestCase):\n    def test_cpu_only(self): self.assertTrue(True)\n', encoding='utf-8')
        crate = self.root / 'support/vmm/device_lifecycle'
        crate.mkdir(parents=True)
        (crate / 'Cargo.lock').write_text('version = 4\n', encoding='utf-8')
        (crate / 'Cargo.toml').write_text('[package]\nname="mock"\nversion="0.1.0"\nedition="2021"\n', encoding='utf-8')
        self.env = os.environ.copy()

    def fake_toolchain(self, cargo_exit=0):
        bin_dir = self.root / 'test-bin'
        bin_dir.mkdir()
        (bin_dir / 'rustc').write_text('#!/bin/sh\nprintf "rustc mock\\n"\n', encoding='utf-8')
        cargo = (bin_dir / 'cargo')
        cargo.write_text('#!/bin/sh\necho "$*" >> "$A09_TEST_CARGO_LOG"\nif [ "$1" = "--version" ]; then exit 0; fi\nexit '+str(cargo_exit)+'\n', encoding='utf-8')
        (bin_dir / 'rustc').chmod(0o755)
        cargo.chmod(0o755)
        self.env['A09_TEST_CARGO_LOG'] = str(self.root / 'invocations.txt')
        self.env['PATH'] = str(bin_dir) + os.pathsep + self.env['PATH']

    def run_gate(self):
        return subprocess.run(['bash', str(self.root / 'support/vmm/verify.sh')], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_missing_rust_fails_closed_after_python(self):
        # Isolate PATH to the commands the shell harness needs, omitting cargo.
        bin_dir = self.root / 'test-bin'
        bin_dir.mkdir()
        for name in ('bash', 'dirname', 'python3'):
            executable = shutil.which(name)
            self.assertIsNotNone(executable)
            (bin_dir / name).symlink_to(executable)
        self.env['PATH'] = str(bin_dir)
        result = self.run_gate()
        self.assertEqual(result.returncode, 2)
        self.assertIn('CPU-only', result.stdout)
        self.assertIn('rustc/cargo unavailable', result.stderr)

    def test_readme_nonempty_rejected_before_tests(self):
        (self.root / 'README.md').write_text('not empty')
        self.fake_toolchain()
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('README.md', result.stderr)
        self.assertNotIn('CPU-only', result.stdout)

    def test_missing_lock_is_failure_not_green(self):
        self.fake_toolchain()
        (self.root / 'support/vmm/device_lifecycle/Cargo.lock').unlink()
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertIn('lockfile absent', result.stderr)

    def test_both_locked_offline_rust_commands_are_required(self):
        self.fake_toolchain()
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = Path(self.env['A09_TEST_CARGO_LOG']).read_text().splitlines()
        tests = [line for line in lines if line.startswith('test ')]
        self.assertEqual(len(tests), 2)
        self.assertTrue(all('--locked' in line and '--offline' in line for line in tests))
        self.assertIn('--all-targets', tests[0])
        self.assertIn('--doc', tests[1])

    def test_rust_failure_propagates_without_reporting_gpu_pass(self):
        self.fake_toolchain(cargo_exit=49)
        result = self.run_gate()
        self.assertEqual(result.returncode, 49)
        self.assertNotIn('A09 PASS', result.stdout)
        self.assertEqual(len([x for x in Path(self.env['A09_TEST_CARGO_LOG']).read_text().splitlines() if x.startswith('test ')]), 1)

    def test_python_failure_stops_before_any_rust(self):
        (self.root / 'tests/hardware/test_fixture.py').write_text('import unittest\nclass Fixture(unittest.TestCase):\n    def test_no(self): self.assertTrue(False)\n')
        self.fake_toolchain()
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Path(self.env['A09_TEST_CARGO_LOG']).exists())


if __name__ == '__main__':
    unittest.main()
