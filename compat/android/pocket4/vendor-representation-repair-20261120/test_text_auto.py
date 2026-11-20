#!/usr/bin/python3
"""Real Git controls for all 440 observed checkout representations.

This is a separate successor test packet. Frozen previous helpers and reports
remain unchanged. Only owned temporary repositories are modified; no network,
operational source, Android runtime, production helper or owner file is opened.
"""
import argparse
import ast
import base64
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NEW = HERE / 'vendor_source_bookends_text_auto_9907.py'
BASE = HERE / 'baseline/vendor_source_bookends_r19_9907.py'
FIXTURES = HERE / 'fixtures/actual-conversions.json.gz'
LEGACY_PATH = HERE / 'legacy-test-suite/test_committed_crlf.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load(LEGACY_PATH, 'p4_frozen_crlf29_tests')
HELPER = load(NEW, 'p4_text_auto_successor')
PREVIOUS = load(BASE, 'p4_previous_implicit_text_helper')
legacy.HELPER = HELPER
legacy.NEW = NEW
ENV = dict(legacy.ENV)
ENV['GIT_CONFIG_GLOBAL'] = '/dev/null'
COMMANDS, CASES, REPLAYS, ROOTS = [], [], [], []
DEADLINE = time.monotonic() + 180


def guard():
    if time.monotonic() >= DEADLINE:
        raise RuntimeError('fixed complete fixture deadline')


def run(argv, body=None):
    guard()
    child = subprocess.Popen(argv, stdin=subprocess.PIPE if body is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV,
                             start_new_session=True)
    pidfd = os.pidfd_open(child.pid, 0)
    try:
        try:
            stdout, stderr = child.communicate(body, timeout=min(15, DEADLINE - time.monotonic()))
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=5)
            raise
        assert child.returncode is not None
        try:
            os.killpg(child.pid, 0)
        except ProcessLookupError:
            group_gone = True
        else:
            group_gone = False
        record = {'argv': argv, 'pid': child.pid, 'exit_code': child.returncode,
                  'actual_child_reaped': True, 'original_pidfd_held_until_reaped': True,
                  'process_group_gone': group_gone,
                  'stdout_bytes': len(stdout), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                  'stderr_bytes': len(stderr), 'stderr_sha256': hashlib.sha256(stderr).hexdigest()}
        COMMANDS.append(record)
        assert group_gone and child.returncode == 0, (record, stderr.decode(errors='replace'))
        return stdout
    finally:
        os.close(pidfd)


class RealGitControls(legacy.RealGitControls):
    # These were intentional exclusions in the old packet. Their replacements
    # below require actual Git text identification and exact executable mode.
    test_text_auto_remains_outside_this_equivalence = None
    test_executable_CRLF_remains_rejected = None

    def setUp(self):
        super().setUp()
        ROOTS.append(str(self.root))
        self.addCleanup(self.tmp.cleanup)

    def git(self, *args, body=None):
        return run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                    '-c', 'protocol.allow=never', '-C', str(self.checkout), *args], body)

    def observe(self, module=None, guard=guard, environment=None):
        return super().observe(module=HELPER if module is None else module,
                               guard=guard, environment=environment)

    def snapshot(self, module=None):
        return super().snapshot(module=HELPER if module is None else module)

    def test_auto_normal_git_checkout_old_rejects_new_accepts(self):
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n')
        self.assertEqual(self.leaf.read_bytes(), legacy.RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe(PREVIOUS)
        (row, identity), commands = self.observe()
        self.assertEqual(row['checkout_conversion']['kind'], 'explicit-committed-text-auto-eol-crlf')
        self.assertEqual(row['checkout_conversion']['git_text_auto'], {
            'index_mode': '100644', 'index_blob': self.oid, 'index_stage': 0,
            'index_content': 'lf', 'worktree_content': 'crlf', 'git_builtin_text_identification': True})
        self.assertEqual(identity, HELPER.f9(self.leaf.lstat()))
        self.assertEqual(len(commands), 2)
        self.assertIn('committed_CRLF_attribute_metadata', commands[0])
        self.assertIn('ls-files', commands[1]['args'])
        self.assertEqual(self.git('status', '--porcelain=v1'), b'')

    def test_auto_without_committed_crlf_rule_rejected(self):
        self.fixture(attributes=b'*.bat text=auto\n')
        self.leaf.write_bytes(legacy.RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_auto_binary_without_NUL_must_not_be_normalized(self):
        binary = b'\x01' * 128 + b'a plain line\n' * 2
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n', body=binary)
        self.assertEqual(self.leaf.read_bytes(), binary, 'Git itself must decline binary conversion')
        self.assertNotIn('checkout_conversion', self.observe()[0][0])
        self.leaf.write_bytes(binary.replace(b'\n', b'\r\n'))
        self.assertNotIn(b'\0', self.leaf.read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'text=auto requires exact stage-zero Git LF text'):
            self.observe()

    def test_auto_binary_with_NUL_remains_rejected(self):
        binary = b'with NUL\0\n'
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n', body=binary)
        self.assertEqual(self.leaf.read_bytes(), binary)
        self.leaf.write_bytes(binary.replace(b'\n', b'\r\n'))
        with self.assertRaisesRegex(RuntimeError, 'only uniform CRLF text'):
            self.observe()

    def test_auto_sparse_control_bytes_follow_Git_text_detection(self):
        text = b'a' * 512 + b'\x01\n'
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n', body=text)
        self.assertEqual(self.leaf.read_bytes(), text.replace(b'\n', b'\r\n'))
        self.assertTrue(self.observe()[0][0]['checkout_conversion']['git_text_auto']['git_builtin_text_identification'])

    def test_auto_already_committed_CRLF_keeps_exact_fast_path(self):
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n', body=legacy.RAW)
        self.assertEqual(self.leaf.read_bytes(), legacy.RAW)
        row, commands = self.observe()
        self.assertNotIn('checkout_conversion', row[0])
        self.assertEqual(commands, [])
        self.leaf.write_bytes(legacy.LF)
        with self.assertRaisesRegex(RuntimeError, 'only uniform CRLF text'):
            self.observe()

    def test_auto_wrong_index_blob_cannot_supply_classification(self):
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n')
        other = self.git('hash-object', '-w', '--stdin', body=b'different LF body\n').decode().strip()
        self.git('update-index', '--cacheinfo', '100644,' + other + ',autogen.bat')
        with self.assertRaisesRegex(RuntimeError, 'text=auto requires exact stage-zero Git LF text'):
            self.observe()

    def test_auto_uncommitted_attribute_cannot_override_minus_text(self):
        self.fixture(attributes=b'*.bat -text eol=crlf\n')
        (self.checkout / '.gitattributes').write_bytes(b'*.bat text=auto eol=crlf\n')
        self.leaf.write_bytes(legacy.RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_auto_literal_filename_with_glob_tab_and_newline(self):
        self.fixture(attributes=b'* text=auto eol=crlf\n')
        name = 'special[1]\tline\n.bat'
        self.git('update-index', '--add', '--cacheinfo', '100644,' + self.oid + ',' + name)
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'literal path')
        commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('--literal-pathspecs', 'checkout-index', '-u', '--', name)
        commands = []
        with patch.dict(os.environ, ENV, clear=True):
            row, identity = HELPER.observe_blob(self.checkout, name, '100644', self.oid, 'H', [],
                                                time.monotonic() + 15, guard, commit, commands)
        self.assertEqual(row['sha256'], hashlib.sha256(legacy.RAW).hexdigest())
        self.assertEqual(identity, HELPER.f9((self.checkout / name).lstat()))
        self.assertIn('--literal-pathspecs', commands[-1]['args'])

    def test_existing_attribute_only_gate_cannot_run_new_probe(self):
        with self.assertRaisesRegex(RuntimeError, 'attribute-only query must not execute a content filter'):
            HELPER.git(self.checkout, ['ls-files', '--eol'], time.monotonic() + 5, guard, [],
                       committed_attributes_only=True)

    def test_new_content_identification_gate_cannot_run_filters(self):
        with self.assertRaisesRegex(RuntimeError, 'content-identification query must be the exact read-only Git text probe'):
            HELPER.git(self.checkout, ['cat-file', '--filters', 'HEAD:autogen.bat'],
                       time.monotonic() + 5, guard, [], text_auto_identification_only=True)

    def test_every_other_existing_function_is_unchanged(self):
        def functions(path):
            return {node.name: ast.dump(node) for node in ast.parse(path.read_bytes()).body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        old, new = functions(BASE), functions(NEW)
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual([name for name in old if old[name] != new[name]],
                         ['git', 'committed_crlf_equivalence'])

    def test_committed_executable_CRLF_is_preserved_exactly(self):
        for attributes in (b'*.bat text eol=crlf\n', b'*.bat text=auto eol=crlf\n'):
            with self.subTest(attributes=attributes):
                self.fixture(attributes=attributes, mode='100755')
                self.assertEqual(self.leaf.read_bytes(), legacy.RAW)
                with self.assertRaisesRegex(RuntimeError, 'bounded non-executable regular text'):
                    self.observe(PREVIOUS)
                (row, identity), _ = self.observe()
                self.assertEqual(row['git_mode'], '100755')
                self.assertTrue(identity[2] & 0o111)
                self.assertEqual(row['checkout_conversion']['normalized_git_blob'], self.oid)

    def test_worktree_executable_bit_mismatch_remains_rejected(self):
        self.fixture(attributes=b'*.bat text=auto eol=crlf\n', mode='100755')
        self.leaf.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'committed regular executable mode'):
            self.observe()

    def test_replay_all_440_actual_files_through_real_Git(self):
        compressed = FIXTURES.read_bytes()
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),
                         'f9e00af7c0fff3e580e5f10ea951c11dec278645c48885c975a0344f88d91977')
        fixtures = json.loads(gzip.decompress(compressed))
        source = self.root / 'replay-source'
        source.mkdir()
        projects = []
        observed = Counter()
        for number, project in enumerate(fixtures['projects']):
            guard()
            project_name = 'fixture%02d' % number
            self.checkout = source / project_name
            self.checkout.mkdir()
            self.git('init', '-q', '--initial-branch=main')
            self.git('config', 'core.autocrlf', 'false')
            self.git('config', 'core.eol', 'lf')
            self.git('remote', 'add', 'origin', legacy.REMOTE)
            entries = []
            for attribute in project['attribute_files']:
                entries.append((attribute['path'], attribute['mode'], attribute['oid'],
                                base64.b64decode(attribute['base64'], validate=True)))
            for item in project['files']:
                old = item['original']
                entries.append((old['path'], old['mode'], old['oid'],
                                base64.b64decode(item['committed_base64'], validate=True)))
            self.assertEqual(len(entries), len({entry[0] for entry in entries}))
            index = []
            for path, mode, oid, body in entries:
                HELPER.safe_relative(path)
                self.assertEqual(self.git('hash-object', '-w', '--stdin', body=body).decode().strip(), oid)
                index.append(mode.encode() + b' ' + oid.encode() + b'\t' + path.encode() + b'\0')
            self.git('update-index', '-z', '--index-info', body=b''.join(index))
            self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'actual input bodies')
            revision = self.git('rev-parse', 'HEAD').decode().strip()
            self.git('checkout-index', '--all', '--force', '-u')
            for item in project['files']:
                old = item['original']
                leaf = self.checkout / old['path']
                expected_raw = base64.b64decode(item['committed_base64']).replace(b'\n', b'\r\n')
                self.assertEqual(leaf.read_bytes(), expected_raw)
                self.assertEqual(len(expected_raw), old['bytes'])
                self.assertEqual(hashlib.sha256(expected_raw).hexdigest(), old['sha256'])
                commands = []
                with patch.dict(os.environ, ENV, clear=True):
                    row, identity = HELPER.observe_blob(self.checkout, old['path'], old['mode'], old['oid'],
                            'H', [], time.monotonic() + 15, guard, revision, commands)
                self.assertEqual(row['sha256'], old['sha256'])
                self.assertEqual(row['bytes'], old['bytes'])
                self.assertEqual(row['git_blob'], old['oid'])
                self.assertEqual(row['checkout_conversion']['attributes'], item['attributes'])
                self.assertEqual(identity, HELPER.f9(leaf.lstat()))
                observed[item['attributes']['text']] += 1
                observed[old['mode']] += 1
                REPLAYS.append({'original_project': project['original_project'],
                    'original_commit': project['original_commit'], 'path': old['path'],
                    'mode': old['mode'], 'original_oid': old['oid'], 'bytes': old['bytes'],
                    'sha256': old['sha256'], 'attributes': item['attributes'],
                    'Git_checkout_whole_bytes_equal_actual_working_body': True,
                    'successor_accepted_complete_original_blob_equivalence': True,
                    'actual_bookend_commands': commands})
            self.assertEqual(self.git('status', '--porcelain=v1', '--untracked-files=all'), b'')
            projects.append({'path': project_name, 'url': legacy.REMOTE, 'commit': revision,
                             'purpose': 'exact actual CRLF checkout fixture', 'sparse_paths': []})
        with patch.dict(os.environ, ENV, clear=True):
            snapshot = HELPER.snapshot(source, projects, self.root / 'all440.ndjson', DEADLINE, guard)
        self.assertEqual(len(REPLAYS), 440)
        self.assertEqual(dict(observed), fixtures['counts'])
        self.assertTrue(snapshot['all_actual_Git_blob_reads_verified'])
        self.assertEqual(snapshot['project_count'], 19)


class RecordedResult(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        CASES.append({'name': test._testMethodName, 'passed': True})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        CASES.append({'name': test._testMethodName, 'passed': False, 'failure': str(error[1])})

    def addError(self, test, error):
        super().addError(test, error)
        CASES.append({'name': test._testMethodName, 'passed': False, 'error': str(error[1])})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', required=True, type=Path)
    arguments = parser.parse_args()
    assert not arguments.result.exists(), 'create-only actual result'
    started = time.time_ns()
    git_path = Path('/usr/bin/git')
    before = HELPER.f9(git_path.stat())
    git_body = git_path.read_bytes()
    git_sha = hashlib.sha256(git_body).hexdigest()
    assert before == HELPER.f9(git_path.stat())
    version = run([str(git_path), '--version']).decode().strip()
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RealGitControls))
    assert before == HELPER.f9(git_path.stat()) and hashlib.sha256(git_path.read_bytes()).hexdigest() == git_sha
    assert all(not os.path.lexists(root) for root in ROOTS), 'every owned temporary repository retired'
    report = {'schema': 'p4-text-auto-and-executable-crlf-real-git-controls-v1',
        'started_ns': started, 'finished_ns': time.time_ns(), 'uid': os.getuid(),
        'git_version': version, 'git': {'path': str(git_path), 'bytes': len(git_body),
            'sha256': git_sha, 'identity': before},
        'passed': result.wasSuccessful(), 'tests_run': result.testsRun, 'cases': CASES,
        'actual_fixture_files_replayed': len(REPLAYS), 'actual_fixture_replays': REPLAYS,
        'fixture_git_commands': COMMANDS, 'all_fixture_children_reaped': all(c['actual_child_reaped'] for c in COMMANDS),
        'all_fixture_process_groups_gone': all(c['process_group_gone'] for c in COMMANDS),
        'original_pidfds_held_until_reaped': all(c['original_pidfd_held_until_reaped'] for c in COMMANDS),
        'baseline_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
        'successor_sha256': hashlib.sha256(NEW.read_bytes()).hexdigest(),
        'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'actual_fixture_sha256': hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
        'unchanged_previous_control_cases': 26,
        'static_function_preservation_control_updated_for_exact_new_query_gate': True,
        'previous_auto_and_executable_exclusions_replaced_by_strict_positive_and_negative_controls': True,
        'temporary_repositories_removed': True, 'operational_source_mutations': 0,
        'Android_actions': 0, 'source_restore_executed': False,
        'runtime_qualified': False, 'production_ready': False}
    with arguments.result.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
        'actual_fixture_files_replayed': len(REPLAYS), 'result': str(arguments.result),
        'successor_sha256': report['successor_sha256']}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
