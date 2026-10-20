"""In-process SDK selection checks. No helper binaries or subprocesses run."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('A01_KTEST_MOCK_RUNNER_SOURCE', HERE / 'run.py'))
SPEC = importlib.util.spec_from_file_location('ktest_sdk_mock_runner', SOURCE)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class SdkIsolationMockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.here = self.project / 'support/build/ktest'
        self.here.mkdir(parents=True)
        self.upstream = self.project / 'kernel/asterinas'
        for crate, path in RUNNER.CRATES.items():
            (self.upstream / path).mkdir(parents=True, exist_ok=True)
            (self.here / 'locks').mkdir(exist_ok=True)
            (self.here / 'locks' / (crate + '.Cargo.lock')).write_text('fixed mock lock\n')
        for relative in ['osdk/src/commands/build/mod.rs']:
            path = self.upstream / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('in-process source metadata only\n')
        for relative in ['verify-source.py', 'record-qemu.py']:
            (self.here.parent / relative).write_text('in-process source metadata only\n')
        self.output = self.root / 'evidence'
        self.output.mkdir()
        self.cargo_home = self.root / 'cargo-home'
        self.private_sdk = self.output / 'osdk/bin/cargo-osdk'
        self.legacy_path = self.cargo_home / 'bin/cargo-osdk'
        self.env = {'PATH': '/usr/bin:/bin', 'CARGO_HOME': str(self.cargo_home),
                    'CARGO_BUILD_JOBS': '2', 'VDSO_LIBRARY_DIR': str(self.root / 'vdso')}
        self.args = SimpleNamespace(skip_osdk_install=False, crate=['ostd'], test_name=None)
        self.calls, self.metadata = [], []
        self.install_code = self.test_code = self.verify_code = 0
        self.private_present, self.private_link, self.private_executable = True, False, True
        real_is_file, real_is_symlink, real_access = Path.is_file, Path.is_symlink, os.access
        real_digest = RUNNER.digest

        def digest(path):
            if path in {self.private_sdk, self.legacy_path, self.root / 'vdso/vdso_x86_64.so'}:
                return hashlib.sha256(b'in-process digest observation').hexdigest()
            return real_digest(path)

        def is_file(path):
            if path == self.private_sdk:
                return self.private_present
            if path == self.legacy_path:
                return True  # Memory-only old-path observation; no SDK file exists.
            return real_is_file(path)

        def is_symlink(path):
            return self.private_link if path == self.private_sdk else real_is_symlink(path)

        def access(path, mode):
            return self.private_executable if Path(path) == self.private_sdk else real_access(path, mode)

        patches = [
            mock.patch.object(RUNNER, 'run', side_effect=self.command),
            mock.patch.object(RUNNER, 'checked_output', side_effect=self.checked),
            mock.patch.object(RUNNER, 'digest', side_effect=digest),
            mock.patch.object(Path, 'is_file', is_file),
            mock.patch.object(Path, 'is_symlink', is_symlink),
            mock.patch.object(RUNNER.os, 'access', side_effect=access),
            mock.patch.object(RUNNER.subprocess, 'Popen', side_effect=AssertionError('no subprocess permitted')),
            mock.patch.object(RUNNER.subprocess, 'run', side_effect=AssertionError('no subprocess permitted')),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def command(self, argv, cwd, env, log):
        argv = list(argv)
        self.calls.append({'argv': argv, 'cwd': str(cwd)})
        if argv[-1].endswith('verify-source.py'):
            log.write_text('{"mock_only": true}\n')
            return self.verify_code
        if 'install' in argv:
            log.write_text('in-process install command observation only\n')
            return self.install_code
        if 'test' in argv and 'osdk' in argv:
            log.write_text('in-process test command observation only\n')
            if not self.test_code:
                crate = env['A01_KTEST_CRATE']
                generated = self.upstream / 'target/osdk' / (crate + '-test-base')
                generated.mkdir(parents=True)
                (generated / 'Cargo.lock').write_text('fixed mock lock\n')
            return self.test_code
        if any(part.endswith('/check.py') for part in argv):
            log.write_text('{"passed": true, "mock_only": true}\n')
            return 0
        raise AssertionError('unexpected in-process command: ' + repr(argv))

    def checked(self, argv, cwd, env, log):
        self.metadata.append(list(argv))
        return 'in-process metadata only\n'

    def invoke(self):
        return RUNNER.run_locked(self.args, self.here, self.project, self.upstream,
                                 self.env, self.cargo_home, self.output)

    def test_private_install_root_and_absolute_sdk_argv(self):
        self.assertEqual(len(self.invoke()), 1)
        install = next(row for row in self.calls if 'install' in row['argv'])
        self.assertEqual(install['argv'][-2:], ['--root', str(self.output / 'osdk')])
        self.assertEqual(install['cwd'], str(self.upstream))
        test = next(row for row in self.calls if 'test' in row['argv'] and 'osdk' in row['argv'])
        self.assertEqual(test['argv'][:3], [str(self.private_sdk), 'osdk', 'test'])
        self.assertNotIn(str(self.legacy_path), test['argv'])
        environment = json.loads((self.output / 'environment.json').read_text())
        self.assertEqual(environment['osdk_executable'], str(self.private_sdk))
        self.assertEqual(environment['osdk_install_root'], str(self.output / 'osdk'))
        self.assertEqual(environment['osdk_source_root'], str(self.upstream.resolve()))
        self.assertFalse(environment['osdk_install_skip_requested'])
        self.assertFalse(environment['osdk_install_skipped'])
        self.assertFalse(self.private_sdk.exists())
        self.assertFalse(self.legacy_path.exists())

    def test_both_crates_share_one_private_install(self):
        self.args.crate = None
        self.assertEqual(len(self.invoke()), 2)
        self.assertEqual(sum('install' in row['argv'] for row in self.calls), 1)
        tests = [row for row in self.calls if 'test' in row['argv'] and 'osdk' in row['argv']]
        self.assertEqual(len(tests), 2)
        self.assertTrue(all(row['argv'][:3] == [str(self.private_sdk), 'osdk', 'test'] for row in tests))

    def test_filtered_name_and_checker_flag_survive(self):
        self.args.test_name = 'module::selected_test'
        self.invoke()
        test = next(row for row in self.calls if 'test' in row['argv'] and 'osdk' in row['argv'])
        self.assertEqual(test['argv'][-1], self.args.test_name)
        self.assertIn('--allow-filtered', self.calls[-1]['argv'])

    def test_install_failure_stops_without_metadata_or_test(self):
        self.install_code = 47
        with self.assertRaisesRegex(SystemExit, 'OSDK installation failed'):
            self.invoke()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.metadata, [])
        self.assertFalse((self.output / 'environment.json').exists())

    def test_missing_private_binary_is_refused(self):
        self.private_present = False
        with self.assertRaisesRegex(SystemExit, 'private.*cargo-osdk'):
            self.invoke()
        self.assertEqual(self.metadata, [])

    def test_linked_private_binary_is_refused(self):
        self.private_link = True
        with self.assertRaisesRegex(SystemExit, 'private.*cargo-osdk'):
            self.invoke()
        self.assertEqual(self.metadata, [])

    def test_nonexecutable_private_binary_is_refused(self):
        self.private_executable = False
        with self.assertRaisesRegex(SystemExit, 'private.*cargo-osdk'):
            self.invoke()
        self.assertEqual(self.metadata, [])

    def test_existing_private_prefix_is_preserved_without_install(self):
        prefix = self.output / 'osdk'
        prefix.mkdir()
        sentinel = prefix / 'keep.txt'
        sentinel.write_text('existing output data\n')
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(sentinel.read_text(), 'existing output data\n')
        self.assertFalse(any('install' in row['argv'] for row in self.calls))

    def test_legacy_skip_option_warns_but_still_installs_fresh_private_sdk(self):
        self.args.skip_osdk_install = True
        self.args.output = self.output
        self.output.rmdir()  # run_main reserves a new evidence directory.
        runner_path = self.here / 'run.py'
        runner_path.write_bytes(SOURCE.read_bytes())
        shutdown = RUNNER.Shutdown()
        with mock.patch.object(RUNNER, '__file__', str(runner_path)), \
                mock.patch.dict(os.environ, self.env, clear=True), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(RUNNER.run_main(self.args, shutdown), self.output)
        self.assertIn('--skip-osdk-install is deprecated and ignored', stderr.getvalue())
        installs = [row for row in self.calls if 'install' in row['argv']]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0], {
            'argv': ['cargo', '+' + RUNNER.TOOLCHAIN, 'install', '--locked',
                     'cargo-osdk', '--path', 'osdk', '--root', str(self.output / 'osdk')],
            'cwd': str(self.upstream),
        })
        tests = [row for row in self.calls if 'test' in row['argv'] and 'osdk' in row['argv']]
        self.assertEqual(len(tests), 1)
        self.assertLess(self.calls.index(installs[0]), self.calls.index(tests[0]))
        self.assertEqual(tests[0]['argv'][:3], [str(self.private_sdk), 'osdk', 'test'])
        self.assertTrue(all(str(self.legacy_path) not in row['argv'] for row in self.calls))
        environment = json.loads((self.output / 'environment.json').read_text())
        self.assertTrue(environment['osdk_install_skip_requested'])
        self.assertFalse(environment['osdk_install_skipped'])
        self.assertEqual(environment['osdk_executable'], str(self.private_sdk))
        self.assertEqual(environment['osdk_install_root'], str(self.output / 'osdk'))
        self.assertEqual(environment['osdk_source_root'], str(self.upstream.resolve()))

    def test_legacy_skip_option_never_falls_back_after_install_or_binary_failure(self):
        self.args.skip_osdk_install = True
        cases = [('install_code', 47, 'OSDK installation failed'),
                 ('private_present', False, 'private.*cargo-osdk'),
                 ('private_link', True, 'private.*cargo-osdk'),
                 ('private_executable', False, 'private.*cargo-osdk')]
        for attribute, value, message in cases:
            with self.subTest(attribute=attribute):
                self.output = self.root / attribute
                self.output.mkdir()
                self.private_sdk = self.output / 'osdk/bin/cargo-osdk'
                self.calls.clear()
                self.metadata.clear()
                previous = getattr(self, attribute)
                setattr(self, attribute, value)
                try:
                    with self.assertRaisesRegex(SystemExit, message):
                        self.invoke()
                finally:
                    setattr(self, attribute, previous)
                self.assertEqual(sum('install' in row['argv'] for row in self.calls), 1)
                self.assertFalse(any('test' in row['argv'] for row in self.calls))
                self.assertTrue(all(str(self.legacy_path) not in row['argv'] for row in self.calls))
                self.assertEqual(self.metadata, [])
                self.assertFalse((self.output / 'environment.json').exists())

    def test_legacy_skip_option_cannot_reuse_an_existing_private_prefix(self):
        self.args.skip_osdk_install = True
        prefix = self.output / 'osdk'
        prefix.mkdir()
        sentinel = prefix / 'keep.txt'
        sentinel.write_text('previous output SDK data\n')
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(sentinel.read_text(), 'previous output SDK data\n')
        self.assertFalse(any('install' in row['argv'] or 'test' in row['argv'] for row in self.calls))

    def test_source_verification_failure_never_reserves_sdk_prefix(self):
        self.verify_code = 1
        with self.assertRaisesRegex(SystemExit, 'source verification failed'):
            self.invoke()
        self.assertFalse((self.output / 'osdk').exists())
        self.assertEqual(len(self.calls), 1)

    def test_test_failure_is_preserved_without_guest_checker(self):
        self.test_code = 101
        with self.assertRaisesRegex(SystemExit, 'OSDK failed \\(101\\)'):
            self.invoke()
        self.assertEqual((self.output / 'ostd/osdk-exit-code.txt').read_text(), '101\n')
        self.assertFalse(any(any(arg.endswith('/check.py') for arg in row['argv']) for row in self.calls))


if __name__ == '__main__':
    unittest.main()
