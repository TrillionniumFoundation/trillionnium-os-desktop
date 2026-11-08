"""Source-only controls for three Pocket4 adapter migrations.

Identity controls execute the actual entry dispatch and exact qualification
comparison, with bootstrap and the final collector explicitly substituted.
Composition controls execute the real inspect-source CLI against a synthetic,
local source-only preparation. No BusinessBaseline, Main, Android or fixture
server is constructed or run. This file needs only Python's standard library.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'source-manifest.json').read_bytes())
LEGACY_COMMON = ROOT / 'tests/fixtures/app_common.r9.py'
CURRENT_COMMON_SHA = '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0'
HOST_REF = {
    'path': '/home/alex/work/pocket4-android-final/qualification/business-support-host-20261108-r1/source-manifest.json',
    'bytes': 1002,
    'sha256': '8cfa9cb05bb7e7768350dbe04acd4cd6421b9f4e8493746aad49b64c37969e70',
}
CONFIG = {
    'quicksearch': {
        'prefix': 'search', 'count': 18,
        'schema': 'pocket4-final-quicksearch-preparation-v1',
        'roles': {'search': 'SEARCH', 'browser': 'BROWSER', 'native-helper': 'NATIVE_HELPER'},
        'old_error': 'ACTUAL_CURRENT_BUSINESS_BASELINE_REQUIRED',
        'new_error': 'ACTUAL_CURRENT_BUSINESS_BASELINE_REQUIRED',
    },
    'settings': {
        'prefix': 'settings', 'count': 17,
        'schema': 'pocket4-final-settings-preparation-v1',
        'roles': {'settings': 'SETTINGS', 'native-helper': 'NATIVE_HELPER'},
        'old_error': 'ACTUAL_CURRENT_BUSINESS_BASELINE_REQUIRED',
        'new_error': 'ACTUAL_CURRENT_BUSINESS_BASELINE_REQUIRED',
    },
    'webview': {
        'prefix': 'webview', 'count': 22,
        'schema': 'pocket4-final-webview-preparation-v1',
        'roles': {'webview-shell': 'TARGET', 'native-helper': 'NATIVE_HELPER'},
        'old_error': 'ACTUAL_R9_BUSINESS_BASELINE_FOR_THESE_TWO_CASES',
        'new_error': 'ACTUAL_HOST_BUSINESS_BASELINE_FOR_THESE_TWO_CASES',
    },
}


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')
    return reference(path)


def load_module(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(Path(path).resolve())
    exec(compile(Path(path).read_bytes(), module.__file__, 'exec'), module.__dict__)
    return module


class BindingControls:
    """Mixin; discovered only through the three concrete TestCase classes."""

    @classmethod
    def setUpClass(cls):
        cls.config = CONFIG[cls.bundle]
        cls.source = ROOT / 'source' / cls.bundle
        selected = [row for row in MANIFEST['production_files'] if row['bundle'] == cls.bundle]
        assert len(selected) == cls.config['count']
        assert {ROOT / row['path'] for row in selected} == set(cls.source.iterdir())
        for row in selected:
            actual = reference(ROOT / row['path'])
            assert (actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256'])
            assert row['path'].endswith('.py')
        for row in json.loads((ROOT / 'tests/fixtures/source-manifest.json').read_bytes())['files']:
            actual = reference(ROOT / row['path'])
            assert (actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256'])
        assert reference(cls.source / 'app_common.py')['sha256'] == CURRENT_COMMON_SHA

    def setUp(self):
        prefix = self.config['prefix']
        self.common = load_module(self.source / 'app_common.py', self.bundle + '_candidate_common')
        self.entry_path = self.source / (prefix + '_entry.py')
        self.entry = load_module(self.entry_path, self.bundle + '_candidate_entry')
        self.profiles = load_module(self.source / (prefix + '_profiles.py'), self.bundle + '_profiles')
        self.assertEqual(self.common.SUPPORT_REF, HOST_REF)

    def identity_dispatch(self, common, entry, entry_path, manifest, role, expected_error=None):
        with tempfile.TemporaryDirectory(prefix='p4-source-identity-') as temporary:
            root = Path(temporary).resolve()
            qualification = write_json(root / 'qualification.json', {'source_manifest': manifest})
            request_value = {'baseline': {'synthetic_source_control': True}, 'qualification': qualification}
            request = write_json(root / 'request.json', request_value)
            output = root / 'collector-output.json'
            source_ref = reference(entry_path)
            packet = {'files': [source_ref]}
            planner = types.SimpleNamespace(named=mock.Mock(return_value=self.profiles))
            collector = mock.Mock(return_value={'synthetic_collector_reached': True})
            argv = [str(entry_path), '--preparation', str(root / 'synthetic-unopened.json'),
                    '--expect-preparation-sha256', '1' * 64, 'identity',
                    '--request', request['path'], '--expect-request-sha256', request['sha256'],
                    '--role', role, '--output', str(output)]
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(entry, 'bootstrap', return_value=(common, packet, {}, planner)))
                stack.enter_context(mock.patch.object(entry.os, 'getuid', return_value=0))
                stack.enter_context(mock.patch.object(entry.os, 'geteuid', return_value=0))
                stack.enter_context(mock.patch.object(common, 'collect_identity', collector))
                stack.enter_context(mock.patch.object(common, 'support', side_effect=AssertionError('No real support load in identity control')))
                stack.enter_context(mock.patch.object(sys, 'argv', argv))
                stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if expected_error:
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        entry.main()
                    collector.assert_not_called()
                else:
                    self.assertEqual(entry.main(), 0)
                    collector.assert_called_once_with(request_value, str(output),
                        getattr(self.profiles, self.config['roles'][role]), source_ref)
                    result = json.loads(stdout.getvalue())
                    self.assertFalse(result['whole_app_business_accepted'])
            self.assertFalse(output.exists(), 'The synthetic collector must not write a runtime receipt')

    def test_original_binding_rejects_current_host_before_collector(self):
        legacy = load_module(LEGACY_COMMON, self.bundle + '_legacy_common')
        original_entry_path = (ROOT / 'tests/fixtures/webview_entry.r1.py'
                               if self.bundle == 'webview' else self.entry_path)
        original_entry = load_module(original_entry_path, self.bundle + '_original_entry')
        role = next(iter(self.config['roles']))
        self.identity_dispatch(legacy, original_entry, original_entry_path, HOST_REF, role, self.config['old_error'])

    def test_candidate_admits_current_host_for_every_identity_role(self):
        for role in self.config['roles']:
            with self.subTest(role=role):
                self.identity_dispatch(self.common, self.entry, self.entry_path, HOST_REF, role)

    def test_candidate_rejects_legacy_clock_and_tampered_manifest(self):
        legacy = load_module(LEGACY_COMMON, self.bundle + '_legacy_reference')
        tampered = {**HOST_REF, 'sha256': '0' * 64}
        cases = {'legacy': legacy.SUPPORT_REF, 'clock': self.common.CLOCK_SUPPORT_REF, 'tampered': tampered}
        for label, supplied in cases.items():
            with self.subTest(manifest=label):
                self.identity_dispatch(self.common, self.entry, self.entry_path, supplied,
                                       next(iter(self.config['roles'])), self.config['new_error'])

    def source_inspection(self, tamper=False):
        with tempfile.TemporaryDirectory(prefix='p4-source-composition-') as temporary:
            root = Path(temporary).resolve()
            local_source = root / 'source'
            shutil.copytree(self.source, local_source)
            packet = {'schema': self.config['schema'], 'code_entrypoints_complete': True,
                      'Android_execution_authorized_by_publication': False,
                      'files': [reference(p) for p in sorted(local_source.iterdir())],
                      'origins': [reference(LEGACY_COMMON)]}
            prep = write_json(root / 'synthetic-source-preparation.json', packet)
            if tamper:
                with (local_source / 'app_common.py').open('ab') as stream:
                    stream.write(b'\n# Deliberate local negative control after pinning.\n')
            entry = local_source / (self.config['prefix'] + '_entry.py')
            command = [sys.executable, '-I', '-B', str(entry), '--preparation', prep['path'],
                       '--expect-preparation-sha256', prep['sha256'], 'inspect-source']
            return subprocess.run(command, text=True, capture_output=True, timeout=15, check=False)

    def test_actual_local_inspect_source_composition_is_inert(self):
        result = self.source_inspection()
        self.assertEqual(result.returncode, 0, result.stderr)
        observation = json.loads(result.stdout)
        self.assertEqual(observation['source_files'], self.config['count'])
        self.assertTrue(observation['source_entrypoints_present'])
        self.assertEqual(observation['Android_UI_actions'], 0)
        self.assertFalse(observation['source_publication_authorizes_Android'])
        self.assertFalse(observation['whole_app_business_accepted'])
        self.assertEqual(result.stderr, '')

    def test_actual_local_bootstrap_rejects_changed_common_pin(self):
        result = self.source_inspection(tamper=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('COMMON_SOURCE_PIN_CHANGED', result.stderr)
        self.assertEqual(result.stdout, '')


class QuickSearchHostBinding(BindingControls, unittest.TestCase):
    bundle = 'quicksearch'


class SettingsHostBinding(BindingControls, unittest.TestCase):
    bundle = 'settings'


class WebViewHostBinding(BindingControls, unittest.TestCase):
    bundle = 'webview'


if __name__ == '__main__':
    unittest.main(verbosity=2)
