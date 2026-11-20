#!/usr/bin/env python3
"""Real Git controls for committed eol=crlf with unspecified text.

Only disposable repositories under TemporaryDirectory are written. The
operational AOSP tree, production controllers and Android are never opened.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BASE = HERE / 'baseline/vendor_source_bookends_r18_2331.py'
NEW = HERE / 'vendor_source_bookends_r19_9907.py'
RAW = (HERE / 'fixtures/autogen.bat.working').read_bytes()
LF = RAW.replace(b'\r\n', b'\n')
ACTUAL_ATTRIBUTES = (HERE / 'fixtures/libopus.gitattributes').read_bytes()
REMOTE = 'https://example.invalid/pocket4-crlf-fixture'
ENV = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
ENV.update(LC_ALL='C', GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1',
           GIT_CONFIG_GLOBAL='/dev/null', GIT_ATTR_NOSYSTEM='1',
           GIT_TERMINAL_PROMPT='0')
COMMANDS = []
CASES = []
OBSERVATIONS = []


def blob(body):
    return hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORIGINAL = load(BASE, 'original_crlf_bookend')
HELPER = load(NEW, 'implicit_text_crlf_bookend')


class RealGitControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p4-crlf-control-')
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'source'
        self.checkout = self.source / 'fixture'
        self.checkout.mkdir(parents=True)
        self.leaf = self.checkout / 'autogen.bat'
        self.serial = 0
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.eol', 'lf')
        self.git('remote', 'add', 'origin', REMOTE)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, body=None):
        argv = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
                '-c', 'commit.gpgsign=false', '-C', str(self.checkout), *args]
        run = subprocess.run(argv, input=body, capture_output=True, timeout=15, env=ENV)
        COMMANDS.append({'case': self._testMethodName, 'args': list(args),
                         'returncode': run.returncode,
                         'stdout_bytes': len(run.stdout),
                         'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
                         'stderr_bytes': len(run.stderr),
                         'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        self.assertEqual(run.returncode, 0, repr(args) + ': ' + run.stderr.decode(errors='replace'))
        return run.stdout

    def fixture(self, attributes=ACTUAL_ATTRIBUTES, body=LF, mode='100644', checkout=True):
        self.leaf.write_bytes(body)
        self.leaf.chmod(0o755 if mode == '100755' else 0o644)
        (self.checkout / '.gitattributes').write_bytes(attributes)
        # Raw plumbing fixes the exact committed body without invoking filters
        # even in negative fixtures which intentionally declare other transforms.
        self.oid = self.git('hash-object', '-w', '--stdin', body=body).decode().strip()
        self.assertEqual(self.oid, blob(body))
        self.git('update-index', '--add', '--cacheinfo', mode + ',' + self.oid + ',autogen.bat')
        self.git('add', '--', '.gitattributes')
        self.git('-c', 'user.name=Pocket4 fixture', '-c', 'user.email=p4-fixture@example.invalid',
                 'commit', '-qm', 'fixed CRLF fixture')
        self.commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.mode = mode
        if checkout:
            self.checkout_leaf()
        self.assertEqual(self.git('cat-file', 'blob', self.oid), body)

    def checkout_leaf(self):
        # checkout-index may keep an existing stat-clean LF fixture even with
        # --force. Remove only this owned temporary leaf so Git must actually
        # materialize the committed blob through its checkout conversion.
        self.leaf.unlink()
        self.git('checkout-index', '-u', '-f', '--', 'autogen.bat')

    def observe(self, module=HELPER, guard=lambda: None, environment=None):
        commands = []
        with patch.dict(os.environ, ENV, clear=True):
            with patch.dict(os.environ, environment or {}):
                result = module.observe_blob(self.checkout, 'autogen.bat', self.mode, self.oid,
                    'H', [], time.monotonic() + 15, guard, self.commit, commands)
        return result, commands

    def snapshot(self, module=HELPER):
        self.serial += 1
        project = {'path': 'fixture', 'url': REMOTE, 'commit': self.commit,
                   'purpose': 'committed CRLF conversion control', 'sparse_paths': []}
        with patch.dict(os.environ, ENV, clear=True):
            return module.snapshot(self.source, [project], self.root / f'snapshot-{self.serial}.ndjson',
                                   time.monotonic() + 20, lambda: None)

    def rejected_attributes(self, attributes):
        self.fixture(attributes=attributes, checkout=False)
        self.leaf.write_bytes(RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_actual_libopus_checkout_old_rejects_new_accepts(self):
        self.assertEqual(len(RAW), 377)
        self.assertEqual(len(LF), 364)
        self.assertEqual(hashlib.sha256(RAW).hexdigest(),
                         '8e5832cadb90219c1f99d016b5628ac87af887f52a99270d431e65db71fa20f5')
        self.assertEqual(hashlib.sha256(LF).hexdigest(),
                         'c5ef007085ba5211c188f77b28bceb8ccbe7c044beb9f92227d9fb3bee299146')
        self.assertEqual(blob(LF), 'b7c735b1e6eec97fde785fee89c13f0ba91b0dd8')
        self.fixture()
        self.assertEqual(self.leaf.read_bytes(), RAW)
        self.assertEqual(self.git('status', '--porcelain=v1'), b'')
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf') as original:
            self.observe(ORIGINAL)
        (row, identity), commands = self.observe()
        conversion = row['checkout_conversion']
        self.assertEqual(conversion['attributes']['text'], 'unspecified')
        self.assertEqual(conversion['attributes']['eol'], 'crlf')
        self.assertEqual(conversion['normalized_git_blob'], self.oid)
        self.assertEqual(conversion['CRLF_pairs'], 13)
        self.assertEqual(row['sha256'], hashlib.sha256(RAW).hexdigest())
        self.assertEqual(identity, HELPER.f9(self.leaf.lstat()))
        self.assertFalse(conversion['source_mutated'])
        self.assertFalse(conversion['custom_filters_executed'])
        self.assertTrue(commands[-1]['committed_CRLF_attribute_metadata']['local_info_attributes_absent'])
        first, second = self.snapshot(), self.snapshot()
        self.assertEqual(first['content_sha256'], second['content_sha256'])
        self.assertTrue(first['all_actual_Git_blob_reads_verified'])
        self.assertEqual(self.git('status', '--porcelain=v1'), b'')
        OBSERVATIONS.append({'case': self._testMethodName, 'original_rejection': str(original.exception),
                             'successor_row': row, 'stable_content_sha256': first['content_sha256']})

    def test_explicit_text_crlf_still_passes(self):
        self.fixture(attributes=b'*.bat text eol=crlf\n')
        for module in (ORIGINAL, HELPER):
            (row, _), _ = self.observe(module)
            self.assertEqual(row['checkout_conversion']['attributes']['text'], 'set')

    def test_explicit_unset_other_transform_attributes_still_pass(self):
        self.fixture(attributes=b'*.bat eol=crlf -filter -ident -working-tree-encoding\n')
        (row, _), _ = self.observe()
        attrs = row['checkout_conversion']['attributes']
        self.assertTrue(all(attrs[k] == 'unset' for k in ('filter', 'ident', 'working-tree-encoding')))

    def test_committed_unspecified_text_overrides_autocrlf_and_eol_config(self):
        self.fixture()
        for autocrlf in ('false', 'input', 'true'):
            for eol in ('lf', 'crlf'):
                with self.subTest(autocrlf=autocrlf, eol=eol):
                    self.git('config', 'core.autocrlf', autocrlf)
                    self.git('config', 'core.eol', eol)
                    self.checkout_leaf()
                    self.assertEqual(self.leaf.read_bytes(), RAW)
                    self.assertEqual(self.observe()[0][0]['checkout_conversion']['normalized_git_blob'], self.oid)

    def test_committed_bang_text_is_unspecified_not_unset(self):
        self.fixture(attributes=b'*.bat -text\nautogen.bat !text eol=crlf\n')
        self.assertEqual(self.leaf.read_bytes(), RAW)
        self.assertEqual(self.observe()[0][0]['checkout_conversion']['attributes']['text'], 'unspecified')

    def test_explicit_minus_text_remains_rejected(self):
        self.rejected_attributes(b'*.bat -text eol=crlf\n')

    def test_text_auto_remains_outside_this_equivalence(self):
        self.rejected_attributes(b'*.bat text=auto eol=crlf\n')

    def test_unknown_text_value_remains_rejected(self):
        self.rejected_attributes(b'*.bat text=custom eol=crlf\n')

    def test_missing_committed_eol_remains_rejected(self):
        self.rejected_attributes(b'')

    def test_autocrlf_config_cannot_replace_committed_eol(self):
        self.fixture(attributes=b'')
        self.git('config', 'core.autocrlf', 'true')
        self.checkout_leaf()
        self.assertEqual(self.leaf.read_bytes(), RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_wrong_committed_eol_remains_rejected(self):
        self.rejected_attributes(b'*.bat text eol=lf\n')

    def test_custom_filter_rejected_and_never_executed(self):
        self.fixture(attributes=b'*.bat eol=crlf filter=tripwire\n', checkout=False)
        marker = self.root / 'filter-must-not-run'
        self.git('config', 'filter.tripwire.clean', '/usr/bin/touch ' + str(marker))
        self.git('config', 'filter.tripwire.smudge', '/usr/bin/touch ' + str(marker))
        self.leaf.write_bytes(RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()
        self.assertFalse(marker.exists())

    def test_ident_remains_rejected(self):
        self.rejected_attributes(b'*.bat eol=crlf ident\n')

    def test_working_tree_encoding_remains_rejected(self):
        self.rejected_attributes(b'*.bat eol=crlf working-tree-encoding=UTF-16LE\n')

    def test_one_content_byte_changed_remains_rejected(self):
        self.fixture()
        self.leaf.write_bytes(b'X' + RAW[1:])
        with self.assertRaisesRegex(RuntimeError, 'normalized full source content differs'):
            self.observe()

    def test_mixed_line_endings_remain_rejected(self):
        self.fixture()
        self.leaf.write_bytes(RAW.replace(b'\r\n', b'\n', 1))
        with self.assertRaisesRegex(RuntimeError, 'only uniform CRLF text'):
            self.observe()

    def test_lone_CR_remains_rejected(self):
        self.fixture()
        self.leaf.write_bytes(RAW + b'\r')
        with self.assertRaisesRegex(RuntimeError, 'only uniform CRLF text'):
            self.observe()

    def test_NUL_remains_rejected(self):
        self.fixture(checkout=False)
        self.leaf.write_bytes(RAW + b'\0')
        with self.assertRaisesRegex(RuntimeError, 'only uniform CRLF text'):
            self.observe()

    def test_executable_CRLF_remains_rejected(self):
        self.fixture(mode='100755')
        with self.assertRaisesRegex(RuntimeError, 'bounded non-executable regular text'):
            self.observe()

    def test_local_info_override_remains_rejected(self):
        self.fixture()
        (self.checkout / '.git/info/attributes').write_text('*.bat eol=crlf\n')
        with self.assertRaisesRegex(RuntimeError, 'local info/attributes override'):
            self.observe()

    def test_worktree_attributes_cannot_grant_equivalence(self):
        self.fixture(attributes=b'')
        (self.checkout / '.gitattributes').write_bytes(ACTUAL_ATTRIBUTES)
        self.leaf.write_bytes(RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_staged_attributes_cannot_grant_equivalence(self):
        self.fixture(attributes=b'')
        (self.checkout / '.gitattributes').write_bytes(ACTUAL_ATTRIBUTES)
        self.git('add', '--', '.gitattributes')
        self.leaf.write_bytes(RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()
        with self.assertRaisesRegex(RuntimeError, 'original index differs'):
            self.snapshot()

    def test_external_attributes_file_cannot_grant_equivalence(self):
        self.fixture(attributes=b'')
        attributes = self.root / 'external-attributes'
        attributes.write_bytes(ACTUAL_ATTRIBUTES)
        self.git('config', 'core.attributesFile', str(attributes))
        self.leaf.write_bytes(RAW)
        with self.assertRaisesRegex(RuntimeError, 'only explicit committed text/eol=crlf'):
            self.observe()

    def test_injected_environment_cannot_supply_alternate_attributes(self):
        self.fixture()
        for name, value in (('GIT_ATTR_SOURCE', self.commit), ('GIT_CONFIG_COUNT', '0'),
                            ('GIT_INDEX_FILE', str(self.root / 'alternate-index'))):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, 'no alternate repository, index or injected'):
                    self.observe(environment={name: value})

    def test_attribute_metadata_change_during_observation_is_rejected(self):
        self.fixture()
        changed = []
        def guard():
            if not changed:
                changed.append(True)
                (self.checkout / '.git/info/attributes').write_bytes(ACTUAL_ATTRIBUTES)
        with self.assertRaisesRegex(RuntimeError, 'Git info directory changed|local info/attributes override'):
            self.observe(guard=guard)
        self.assertTrue(changed)

    def test_raw_LF_fast_path_has_no_attribute_query(self):
        self.fixture(attributes=b'')
        (row, _), commands = self.observe()
        self.assertNotIn('checkout_conversion', row)
        self.assertEqual(commands, [])
        self.assertEqual(row['sha256'], hashlib.sha256(LF).hexdigest())

    def test_original_symlink_behavior_is_unchanged(self):
        self.fixture(attributes=b'')
        link = self.checkout / 'link'
        link.symlink_to('autogen.bat')
        oid = blob(b'autogen.bat')
        row, _ = HELPER.observe_blob(self.checkout, 'link', '120000', oid, 'H', [],
                                    time.monotonic() + 5, lambda: None)
        self.assertEqual(row['git_blob'], oid)
        self.assertNotIn('checkout_conversion', row)

    def test_original_sparse_absence_behavior_is_unchanged(self):
        row, identity = HELPER.observe_blob(self.checkout, 'unselected/missing.bat', '100644',
            blob(b'absent\n'), 'S', ['selected'], time.monotonic() + 5, lambda: None)
        self.assertFalse(row['present'])
        self.assertTrue(row['sparse_skip'])
        self.assertIsNone(identity)
        with self.assertRaisesRegex(RuntimeError, 'missing required source body'):
            HELPER.observe_blob(self.checkout, 'selected/missing.bat', '100644',
                blob(b'absent\n'), 'S', ['selected'], time.monotonic() + 5, lambda: None)

    def test_every_other_existing_function_is_unchanged(self):
        def functions(path):
            return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_bytes()).body
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        before, after = functions(BASE), functions(NEW)
        self.assertEqual(set(before), set(after))
        self.assertEqual([k for k in before if before[k] != after[k]], ['committed_crlf_equivalence'])


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
    if arguments.result.exists():
        raise RuntimeError('fresh result path required')
    start = time.time_ns()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealGitControls)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    version = subprocess.run(['/usr/bin/git', '--version'], check=True, capture_output=True,
                             timeout=5, env=ENV).stdout.decode().strip()
    report = {'schema': 'pocket4-implicit-text-crlf-real-git-controls-v1', 'started_ns': start,
              'finished_ns': time.time_ns(), 'git_version': version, 'passed': result.wasSuccessful(),
              'tests_run': result.testsRun, 'cases': CASES, 'observations': OBSERVATIONS,
              'fixture_git_commands': COMMANDS,
              'baseline_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
              'successor_sha256': hashlib.sha256(NEW.read_bytes()).hexdigest(),
              'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'old_test_source_available': False, 'historical_19_controls_rerun': False,
              'temporary_repositories_removed': True, 'operational_source_mutations': 0,
              'remote_commands': 0, 'Android_actions': 0, 'source_restore_executed': False,
              'build_qualified': False, 'runtime_qualified': False, 'production_ready': False}
    with arguments.result.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
                      'result': str(arguments.result), 'successor_sha256': report['successor_sha256']}))
    sys.exit(0 if result.wasSuccessful() else 1)
