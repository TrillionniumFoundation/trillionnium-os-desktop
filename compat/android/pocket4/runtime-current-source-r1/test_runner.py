#!/usr/bin/env python3
"""Small host controls for the CI runner; these do not execute Cargo or Android."""
import copy
import errno
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('tested_current_runner', Path(__file__).with_name('run_ci.py'))
CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CI)


class CatalogAndArtifactControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='current-runner-controls-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.producer = self.root / 'producer'
        self.target = self.root / 'target'
        self.source = self.producer / 'src' / 'main.rs'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('fn main() {}\n')
        (self.target / 'debug' / 'deps').mkdir(parents=True)
        self.binary = self.target / 'debug' / 'deps' / 'example-tests'
        self.binary.write_bytes(b'locator fixture only; never executed\n')
        self.key = ('example', 'example')
        self.package_id = 'path+file://' + str(self.producer) + '#example@0.1.0'
        self.expected = {self.key: {'package': 'example', 'target': 'example', 'kind': ['bin'],
                                  'source_path': 'src/main.rs', 'required_features': [], 'test': True}}
        self.message = {'reason': 'compiler-artifact', 'package_id': self.package_id,
                        'target': {'name': 'example', 'kind': ['bin'], 'src_path': str(self.source),
                                   'required-features': [], 'test': True},
                        'profile': {'test': True}, 'fresh': False, 'executable': str(self.binary)}

    def stream(self, rows):
        return ('\n'.join(json.dumps(row) for row in [*rows, {'reason': 'build-finished', 'success': True}]) + '\n').encode()

    def joined(self, rows):
        return CI.artifacts(self.stream(rows), {self.package_id: 'example'}, self.producer,
                            self.target, self.expected, True)

    def test_complete_catalog_rejects_loss_duplicates_and_wrong_summary(self):
        wanted = ['first', 'second']
        self.assertEqual(CI.catalog(b'first: test\nsecond: test\n\n2 tests, 0 benchmarks\n', wanted), wanted)
        for raw in (b'first: test\n1 test, 0 benchmarks\n',
                    b'first: test\nfirst: test\nsecond: test\n3 tests, 0 benchmarks\n',
                    b'first: test\nsecond: test\nthird: test\n3 tests, 0 benchmarks\n',
                    b'first: test\nsecond: test\n1 test, 0 benchmarks\n'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                CI.catalog(raw, wanted)

    def test_summary_cannot_replace_missing_or_different_actual_test_records(self):
        raw = ('running 2 tests\ntest first ... ok\ntest pending ... ignored, needs real hardware\n\n'
               'test result: ok. 1 passed; 0 failed; 1 ignored; 0 measured; 64 filtered out; finished in 0.01s\n')
        self.assertEqual(CI.VERIFY.test_terminal(raw, ['first'], ['pending'], 64),
                         {'passed': ['first'], 'ignored': ['pending'], 'filtered': 64})
        for bad in (raw.replace('test first ... ok\n', ''), raw.replace('test first', 'test other'),
                    raw.replace('64 filtered', '63 filtered'), raw + raw):
            with self.subTest(raw=bad), self.assertRaises(RuntimeError):
                CI.VERIFY.test_terminal(bad, ['first'], ['pending'], 64)

    def test_artifact_join_rejects_foreign_stale_or_misbound_executables(self):
        self.assertEqual(self.joined([self.message])[self.key]['path'], self.binary)
        wrong = []
        for field, value in [('package_id', 'foreign@0.1.0'), ('fresh', True),
                             ('executable', str(self.target / 'debug' / 'example'))]:
            row = copy.deepcopy(self.message); row[field] = value; wrong.append(row)
        for field, value in [('name', 'other'), ('src_path', str(self.producer / 'other.rs')),
                             ('kind', ['lib']), ('test', False), ('required-features', ['not-selected'])]:
            row = copy.deepcopy(self.message); row['target'][field] = value; wrong.append(row)
        row = copy.deepcopy(self.message); row['profile']['test'] = False; wrong.append(row)
        for row in wrong:
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                self.joined([row])
        for rows in ([], [self.message, self.message]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                self.joined(rows)

    def test_artifact_requires_one_actual_successful_terminal(self):
        raw = self.stream([self.message])
        for bad in (raw.replace(b'"success": true', b'"success": false'),
                    raw + b'{"reason":"build-finished","success":true}\n',
                    raw + json.dumps(self.message).encode() + b'\n'):
            with self.subTest(raw=bad), self.assertRaises(RuntimeError):
                CI.artifacts(bad, {self.package_id: 'example'}, self.producer,
                             self.target, self.expected, True)

    def test_example_artifacts_cannot_reuse_normal_or_test_binaries(self):
        folder = self.target / 'debug' / 'examples'
        folder.mkdir()
        binary = folder / 'example'
        binary.write_bytes(b'example location fixture; never executed\n')
        expected = copy.deepcopy(self.expected)
        expected[self.key].update(kind=['example'], test=False)
        message = copy.deepcopy(self.message)
        message['target'].update(kind=['example'], test=False)
        message.update(executable=str(binary), profile={'test':False})
        def joined(rows):
            return CI.artifacts(self.stream(rows), {self.package_id:'example'}, self.producer,
                                self.target, expected, False, profile_dir='debug/examples')
        self.assertEqual(joined([message])[self.key]['path'], binary)
        for path in (self.target/'release'/'example', self.binary, folder/'example-old'):
            changed = copy.deepcopy(message); changed['executable'] = str(path)
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                joined([changed])
        for changes in ({'fresh':True}, {'profile':{'test':True}}):
            changed = copy.deepcopy(message); changed.update(changes)
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                joined([changed])
        harness = copy.deepcopy(message)
        harness.update(executable=str(folder/'example-0123456789abcdef'), profile={'test':True})
        actual = CI.artifacts(self.stream([harness]), {self.package_id:'example'}, self.producer,
                              self.target, expected, True, profile_dir='debug/examples')
        self.assertEqual(actual[self.key]['path'], folder/'example-0123456789abcdef')
        harness['executable'] = str(binary)
        with self.assertRaises(RuntimeError):
            CI.artifacts(self.stream([harness]), {self.package_id:'example'}, self.producer,
                         self.target, expected, True, profile_dir='debug/examples')

    def test_example_aliases_require_the_original_same_directory_cargo_hash(self):
        # Cargo retains '-' in the public executable, but rustc uses the crate
        # identifier ('_') in its hashed original. Check both actual forms.
        for name in ('example', 'cpu-placement-probe', 'notification-test-server'):
            with self.subTest(target=name), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                folder = Path(tmp)
                normal = folder/name
                normal.write_bytes(b'alias fixture; not an ELF claim\n')
                hashed = folder/(name.replace('-', '_')+'-0123456789abcdef')
                os.link(normal, hashed)
                def ref():
                    return {'path':str(normal),'identity':CI.VERIFY.f9(normal.lstat())}
                self.assertEqual(CI.aliases(ref(), folder, example=True),
                                 sorted(map(str, (normal, hashed))))
                wrong = folder/'unrelated-0123456789abcdef'
                hashed.rename(wrong)
                with self.assertRaises(RuntimeError):
                    CI.aliases(ref(), folder, example=True)
                wrong.rename(hashed)
                outside = self.root/('external-'+name)
                os.link(normal, outside)
                try:
                    with self.assertRaises(RuntimeError):
                        CI.aliases(ref(), folder, example=True)
                finally:
                    outside.unlink()
                if '-' in name:
                    hashed.rename(folder/(name+'-0123456789abcdef'))
                    with self.assertRaises(RuntimeError):
                        CI.aliases(ref(), folder, example=True)

    def test_cargo_aliases_require_every_link_inside_the_actual_profile(self):
        profile = self.target / 'debug'
        normal = profile / 'example'
        normal.write_bytes(b'alias identity fixture; not an ELF claim\n')
        dep = profile / 'deps' / 'example-hash'
        os.link(normal, dep)
        def ref():
            return {'path': str(normal), 'identity': CI.VERIFY.f9(normal.lstat())}
        self.assertEqual(CI.aliases(ref(), profile), sorted(map(str, (normal, dep))))
        external = self.root / 'unaccounted-link'
        os.link(normal, external)
        with self.assertRaises(RuntimeError):
            CI.aliases(ref(), profile)
        external.unlink()
        other = profile / 'other-directory'
        other.mkdir()
        dep.rename(other / dep.name)
        with self.assertRaises(RuntimeError):
            CI.aliases(ref(), profile)


class ActualChildRetirementControls(unittest.TestCase):
    """Inject acquisition faults only; launch, signal, wait and /proc are real."""
    def setUp(self):
        self.assertEqual(CI.owned_children(), set(), 'test starts without an owned process')
        self.temporary = tempfile.TemporaryDirectory(prefix='current-runner-child-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def actual_child(self, fault=None, timeout=0.15, normal=False):
        captured = []
        original_popen = subprocess.Popen
        original_pidfd = os.pidfd_open
        original_read_text = Path.read_text
        descriptors_before = set(os.listdir('/proc/self/fd'))

        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            captured.append(child)
            return child

        def pidfd(pid, *args, **kwargs):
            if fault == 'pidfd' and captured and pid == captured[0].pid:
                raise OSError(errno.EMFILE, 'injected acquisition failure for this real child')
            return original_pidfd(pid, *args, **kwargs)

        def read_text(path, *args, **kwargs):
            if fault == 'procstat' and captured and path == Path('/proc') / str(captured[0].pid) / 'stat':
                raise OSError(errno.EIO, 'injected proc-stat read failure for this real child')
            return original_read_text(path, *args, **kwargs)

        program = "print('real-short-child')" if normal else 'import time; time.sleep(30)'
        began = time.monotonic()
        try:
            with (self.root / 'stdout').open('xb') as out, (self.root / 'stderr').open('xb') as err:
                with mock.patch.object(CI.subprocess, 'Popen', side_effect=launch), \
                     mock.patch.object(CI.os, 'pidfd_open', side_effect=pidfd), \
                     mock.patch.object(Path, 'read_text', new=read_text):
                    result = CI.execute_child([sys.executable, '-I', '-B', '-c', program], self.root,
                                              dict(os.environ), out, err, timeout)
            self.assertEqual(len(captured), 1)
            self.assertEqual(result['pid'], captured[0].pid)
            self.assertIsNotNone(captured[0].returncode)
            self.assertTrue(result['actual_child_reaped'])
            self.assertEqual(result['cleanup_errors'], [])
            self.assertEqual(result['owned_descendants_remaining'], 0)
            self.assertEqual(CI.owned_children(), set())
            self.assertFalse((Path('/proc') / str(captured[0].pid)).exists())
            with self.assertRaises(ChildProcessError):
                os.waitpid(captured[0].pid, os.WNOHANG)
            self.assertEqual(set(os.listdir('/proc/self/fd')), descriptors_before)
            self.assertLess(time.monotonic() - began, 12, 'finite actual-child cleanup')
            return result
        finally:
            # Emergency cleanup after a failed assertion is not pass evidence.
            for child in captured:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=5)

    def test_real_short_child_success_is_reaped_with_original_pidfd(self):
        row = self.actual_child(timeout=5, normal=True)
        self.assertEqual(row['exit_code'], 0)
        self.assertIsNone(row['error'])
        self.assertTrue(row['original_pidfd_held_until_reaped'])
        self.assertEqual((self.root / 'stdout').read_bytes(), b'real-short-child\n')

    def test_timeout_reaps_the_actual_original_child(self):
        row = self.actual_child()
        self.assertTrue(row['timed_out'])
        self.assertEqual(row['error']['type'], 'TimeoutExpired')
        self.assertNotEqual(row['exit_code'], 0)
        self.assertTrue(row['original_pidfd_held_until_reaped'])

    def test_pidfd_acquisition_failure_still_reaps_the_actual_child(self):
        row = self.actual_child(fault='pidfd')
        self.assertEqual(row['error']['type'], 'OSError')
        self.assertFalse(row['original_pidfd_held_until_reaped'])
        self.assertNotEqual(row['exit_code'], 0)

    def test_procstat_failure_closes_original_pidfd_and_reaps_the_actual_child(self):
        row = self.actual_child(fault='procstat')
        self.assertEqual(row['error']['type'], 'OSError')
        self.assertTrue(row['original_pidfd_held_until_reaped'])
        self.assertIsNone(row['start_ticks'])
        self.assertNotEqual(row['exit_code'], 0)


if __name__ == '__main__':
    if sys.platform != 'linux' or not hasattr(os, 'pidfd_open'):
        raise SystemExit('Linux /proc and PIDFD are required; these controls may not be skipped')
    unittest.main(verbosity=2)
