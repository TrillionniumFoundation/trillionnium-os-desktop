#!/usr/bin/env python3
"""Local interfaces and owned-file controls; no Main preflight or generator run."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


worker = imported('beike_source_preparation', HERE/'prepare_beike_bound_source.py')
generator = imported('real_source_generator_r2', HERE/'generate_successor_sources.py')
NONCE = 'a'*32


def request():
    return {'schema': 'pocket4-beike-bound-qa-source-preparation-v1', 'guard': worker.GUARD,
            'app_scope': {'path': '/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json',
                          'bytes': 57340, 'sha256': '489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4'},
            'generation_nonce': NONCE, 'package': worker.TARGET, 'public_text': '北京',
            'allowed_operations': ['state', 'inspect', 'click', 'set_text'],
            'install_or_signature_evidence': [{'path': '/home/alex/work/owned-test-fixture/evidence.json', 'bytes': 1, 'sha256': '0'*64}],
            'output_root': '/home/alex/work/pocket4-beike-successor-qa-input-20261106-'+NONCE,
            'coordination': {'single_coordinator': True, 'unresolved_native_install_jobs': []}}


def catalog(rows=None, owner=12345):
    return {'ok': True, 'state': 'running', 'host_pid': owner,
            'applications': rows if rows is not None else [{'package': worker.TARGET, 'component': worker.TARGET+'/.ActualObservedFixture'}]}


class Controls(unittest.TestCase):
    def test_exact_beike_policy_and_unsettled_install_rejections(self):
        worker.validate_request(request())
        for key, value in (('package', 'tv.danmaku.bili'), ('public_text', '别的文本'),
                           ('allowed_operations', ['state', 'inspect', 'player_button']),
                           ('coordination', {'single_coordinator': True, 'unresolved_native_install_jobs': ['unknown']})):
            changed = copy.deepcopy(request()); changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                worker.validate_request(changed)
        changed = copy.deepcopy(request()); changed['app_scope']['path'] = worker.BASE+'/initial-app-scope.private.json'
        with self.assertRaises(RuntimeError):
            worker.validate_request(changed)

    def test_catalog_component_is_exact_and_roster_differences_are_preserved(self):
        rows = catalog()['applications'] + [{'package': 'com.example.newentry', 'component': 'com.example.newentry/.Entry'}]
        component, difference = worker.select_catalog(catalog(rows), 12345)
        self.assertEqual(component, worker.TARGET+'/.ActualObservedFixture')
        self.assertEqual(difference['added_packages'], ['com.example.newentry'])
        self.assertEqual(len(difference['missing_packages']), 44)
        self.assertTrue(difference['differences_preserved_without_rewriting_catalog'])

    def test_missing_ambiguous_or_other_owner_catalog_rejected(self):
        for value in (catalog([], 12345), catalog(owner=12346),
                      catalog(catalog()['applications'] + [{'package': worker.TARGET, 'component': worker.TARGET+'/.OtherFixture'}])):
            with self.assertRaises(RuntimeError):
                worker.select_catalog(value, 12345)

    def test_real_pinned_generator_closure_and_request_interface(self):
        for pin, local in ((worker.GENERATOR, HERE/'generate_successor_sources.py'),
                           (worker.GENERATOR_MANIFEST, HERE/'GENERATOR_PINS.json')):
            raw = local.read_bytes()
            self.assertEqual(len(raw), pin['bytes']); self.assertEqual(hashlib.sha256(raw).hexdigest(), pin['sha256'])
        sources = generator.reference_closure(worker.GENERATOR_MANIFEST['sha256'])
        self.assertEqual(len(sources), 31)
        pin = {'path': '/home/alex/work/owned-test-fixture/input.json', 'bytes': 1, 'sha256': '0'*64}
        value = {'schema': 'pocket4-successor-qa-source-request-v1', 'qa_build_input': pin, 'launcher_catalog': pin,
                 'package': worker.TARGET, 'component': worker.TARGET+'/.ActualObservedFixture', 'generation_nonce': NONCE,
                 'public_text': '北京', 'allowed_operations': worker.OPERATIONS,
                 'output_root': '/home/alex/work/pocket4-successor-qa-source-'+NONCE}
        self.assertEqual(generator.validate_request(value), value)

    def test_exact_integer_and_duplicate_input_rejection(self):
        self.assertEqual(worker.parse(b'{"mtime_ns":1793958953453465022}')['mtime_ns'], 1793958953453465022)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(RuntimeError):
                worker.parse(raw)

    def test_owned_bootstrap_descriptor_retirement_without_fake_root(self):
        before = len(os.listdir('/proc/self/fd'))
        with tempfile.TemporaryDirectory(prefix='p4-beike-source-owned-file-') as root:
            path = Path(root)/'owned.bin'; raw = b'owned host fixture only\n'; path.write_bytes(raw)
            pin = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            if os.getuid() == os.geteuid() == 0:
                self.assertEqual(worker.read_root_pin(pin), raw)
                with self.assertRaises(RuntimeError):
                    worker.read_root_pin({**pin, 'sha256': '0'*64})
            else:
                with self.assertRaisesRegex(RuntimeError, 'EXACT_ROOT_OWNED_REGULAR_SOURCE_REQUIRED'):
                    worker.read_root_pin(pin)
        self.assertEqual(len(os.listdir('/proc/self/fd')), before)


if __name__ == '__main__':
    before = len(os.listdir('/proc/self/fd'))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir('/proc/self/fd'))
    print(json.dumps({'schema': 'pocket4-beike-source-preparation-offline-controls-v1', 'ok': result.wasSuccessful() and before == after,
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'caller_uid': os.getuid(), 'caller_euid': os.geteuid(), 'FD_count_before': before, 'FD_count_after': after,
        'actual_generator_closure_files': 31, 'fixture_catalog_is_not_actual_android_evidence': True,
        'runtime_worker_invoked': False, 'generator_generate_invoked': False, 'Main_reads': 0, 'native_commands': 0,
        'namespace_entries': 0, 'builds': 0, 'installs': 0, 'UI_actions': 0}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
