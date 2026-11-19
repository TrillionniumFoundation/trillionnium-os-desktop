#!/usr/bin/env python3
"""Finite real-Git controls for the R13 cone-list comparison only.

Creates disposable Git repositories below its own TemporaryDirectory. It does
not open the operational AOSP checkout, build a compiler, or start Android.
"""
import argparse
import datetime
import hashlib
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


HERE = Path(__file__).resolve().parent
COMMANDS = []
CASES = []
REMOTE = 'https://example.invalid/pocket4-cone-fixture'
ENV = {**os.environ, 'LC_ALL': 'C', 'GIT_OPTIONAL_LOCKS': '0',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_TERMINAL_PROMPT': '0'}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load(HERE / 'vendor_source_bookends_r13.py', 'cone_successor')
ORIGINAL = load(HERE / 'original/vendor_source_bookends_r12.py', 'cone_original')


def git(directory, *args):
    argv = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
            '-c', 'commit.gpgsign=false', '-C', str(directory), *args]
    row = {'args': list(args), 'started_ns': str(time.time_ns())}
    COMMANDS.append(row)
    child = None
    pidfd = None
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=ENV, start_new_session=True)
        row['pid'] = child.pid
        pidfd = os.pidfd_open(child.pid)
        out, err = child.communicate(timeout=15)
        row.update(exit_code=child.returncode,
                   original_pidfd_held_until_actual_reap=True,
                   stdout_bytes=len(out), stdout_sha256=hashlib.sha256(out).hexdigest(),
                   stderr_bytes=len(err), stderr_sha256=hashlib.sha256(err).hexdigest())
        try:
            os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG)
            row['after_reap_echild'] = False
        except ChildProcessError:
            row['after_reap_echild'] = True
        if child.returncode != 0:
            raise AssertionError('fixture Git failed: ' + repr(args) + ': ' + err.decode())
        return out
    finally:
        if child is not None and child.returncode is None:
            if pidfd is not None:
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            else:
                child.kill()
            child.communicate(timeout=5)
            row['forced_retirement'] = True
        if pidfd is not None:
            os.close(pidfd)
        row['finished_ns'] = str(time.time_ns())


class RealGitConeControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p4-cone-control-')
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'
        self.checkout = self.source / 'fixture'
        self.checkout.mkdir(parents=True)
        files = {
            'Android.bp': b'// root build definition\n',
            'root.txt': b'root file\n',
            'a/Android.bp': b'// selected build definition\n',
            'a/direct.txt': b'direct\n',
            'a/b/deep.txt': b'deep source\n',
            'a/c/other.txt': b'other selected body\n',
            'ab/keep.txt': b'not covered by a\n',
            'lib/source.cc': b'int selected;\n',
            'library/deep/source.cc': b'int sibling;\n',
            'files/prebuilt.bin': b'bounded prebuilt fixture\n',
            'unselected/secret.txt': b'not selected\n',
        }
        for name, body in files.items():
            path = self.checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        git(self.checkout, 'init', '-q', '--initial-branch=main')
        git(self.checkout, 'add', '--all')
        git(self.checkout, '-c', 'user.name=Pocket4 fixture',
            '-c', 'user.email=p4-fixture@example.invalid', 'commit', '-qm', 'fixed fixture')
        git(self.checkout, 'remote', 'add', 'origin', REMOTE)
        self.commit = git(self.checkout, 'rev-parse', 'HEAD').decode().strip()
        self.case_commands_start = len(COMMANDS)
        self.serial = 0

    def tearDown(self):
        self.tmp.cleanup()

    def sparse(self, paths):
        git(self.checkout, 'sparse-checkout', 'set', '--cone', '--skip-checks', '--', *paths)
        return git(self.checkout, 'sparse-checkout', 'list').decode().splitlines()

    def project(self, paths):
        return {'path': 'fixture', 'url': REMOTE, 'commit': self.commit,
                'purpose': 'finite cone-list comparison control', 'sparse_paths': paths}

    def snapshot(self, paths, module=HELPER, project=None):
        self.serial += 1
        return module.snapshot(self.source, [project or self.project(paths)],
                               self.root / ('bookend-%d.ndjson' % self.serial),
                               time.monotonic() + 30, lambda: None)

    def test_real_git_prunes_redundant_descendants_and_original_fails(self):
        requested = ['a/b', 'Android.bp', 'a']
        observed = self.sparse(requested)
        self.assertEqual(observed, ['Android.bp', 'a'])
        self.assertNotEqual(set(requested), set(observed))
        with self.assertRaisesRegex(RuntimeError, 'actual sparse cones differ'):
            self.snapshot(requested, ORIGINAL)
        result = self.snapshot(requested)
        self.assertTrue(result['all_actual_Git_blob_reads_verified'])
        self.assertEqual(result['projects'][0]['project']['sparse_paths'], requested)

    def test_sibling_prefixes_and_file_cones_remain_distinct(self):
        requested = ['library/deep', 'lib', 'files/prebuilt.bin']
        observed = self.sparse(requested)
        self.assertEqual(set(observed), set(requested))
        self.assertEqual(HELPER.canonical_sparse_cones(requested), sorted(requested))
        self.assertTrue(self.snapshot(requested)['all_actual_Git_blob_reads_verified'])

    def test_nested_selection_order_does_not_change_original_plan(self):
        requested = ['a/c', 'ab', 'a/b', 'a']
        self.assertEqual(self.sparse(requested), ['a', 'ab'])
        result = self.snapshot(requested)
        self.assertEqual(result['projects'][0]['project']['sparse_paths'], requested)

    def test_missing_required_cone_rejected(self):
        self.sparse(['a'])
        with self.assertRaisesRegex(RuntimeError, 'actual sparse cones differ'):
            self.snapshot(['a', 'lib'])

    def test_unplanned_broader_parent_rejected(self):
        self.sparse(['a'])
        with self.assertRaisesRegex(RuntimeError, 'actual sparse cones differ'):
            self.snapshot(['a/b'])

    def test_unplanned_unrelated_cone_rejected(self):
        self.sparse(['a', 'unselected'])
        with self.assertRaisesRegex(RuntimeError, 'actual sparse cones differ'):
            self.snapshot(['a'])

    def test_duplicate_plan_still_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'unique ordered sparse paths'):
            self.snapshot(['a', 'a'])

    def test_noncanonical_plan_still_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'canonical relative source path'):
            self.snapshot(['a/../lib'])

    def test_required_body_removal_still_rejected(self):
        self.sparse(['a'])
        (self.checkout / 'a/b/deep.txt').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing required source body'):
            self.snapshot(['a'])

    def test_body_change_still_rejected_against_original_git_blob(self):
        self.sparse(['a'])
        (self.checkout / 'a/b/deep.txt').write_bytes(b'changed body\n')
        with self.assertRaisesRegex(RuntimeError, 'actual source content differs'):
            self.snapshot(['a'])

    def test_index_change_still_rejected_against_original_commit(self):
        self.sparse(['a'])
        (self.checkout / 'a/b/deep.txt').write_bytes(b'changed staged body\n')
        git(self.checkout, 'add', 'a/b/deep.txt')
        with self.assertRaisesRegex(RuntimeError, 'original index differs'):
            self.snapshot(['a'])

    def test_original_commit_still_exact(self):
        self.sparse(['a'])
        project = self.project(['a'])
        project['commit'] = '0' * 40
        with self.assertRaisesRegex(RuntimeError, 'original project tuple'):
            self.snapshot(['a'], project=project)

    def test_original_remote_still_exact(self):
        self.sparse(['a'])
        project = self.project(['a'])
        project['url'] = 'https://example.invalid/different'
        with self.assertRaisesRegex(RuntimeError, 'original project tuple'):
            self.snapshot(['a'], project=project)


class RecordedResult(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        CASES.append({'name': test._testMethodName, 'passed': True})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        CASES.append({'name': test._testMethodName, 'passed': False, 'failure': str(err[1])})

    def addError(self, test, err):
        super().addError(test, err)
        CASES.append({'name': test._testMethodName, 'passed': False, 'error': str(err[1])})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.result.exists():
        raise RuntimeError('fresh result path required')
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealGitConeControls)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    version = subprocess.run(['/usr/bin/git', '--version'], check=True,
                             capture_output=True, timeout=5, env=ENV).stdout.decode().strip()
    payload = {'schema': 'pocket4-real-git-sparse-cone-controls-v1',
               'started_utc': started, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'git_version': version, 'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
               'cases': CASES, 'fixture_git_commands': COMMANDS,
               'original_helper_sha256': hashlib.sha256((HERE / 'original/vendor_source_bookends_r12.py').read_bytes()).hexdigest(),
               'successor_helper_sha256': hashlib.sha256((HERE / 'vendor_source_bookends_r13.py').read_bytes()).hexdigest(),
               'temporary_fixtures_removed': True, 'operational_source_mutations': 0,
               'compilers_started': 0, 'VMs_started': 0, 'runtime_qualified': False, 'production_ready': False}
    with arguments.result.open('x') as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write('\n')
    sys.exit(0 if result.wasSuccessful() else 1)
