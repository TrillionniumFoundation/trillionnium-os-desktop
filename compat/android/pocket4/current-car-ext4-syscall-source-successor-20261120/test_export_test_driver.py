"""Report and real ELF read controls; no Cargo, ELF execution or namespaces."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('test_driver_export', HERE / 'export_test_driver.py')
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)
CI_SPEC = importlib.util.spec_from_file_location('test_driver_actual_ci', HERE / 'run_ci.py')
CI = importlib.util.module_from_spec(CI_SPEC)
CI_SPEC.loader.exec_module(CI)


class HarnessIdentityControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='test-driver-json-controls-')
        self.addCleanup(temporary.cleanup)
        self.binary = Path(temporary.name).resolve() / 'unexecuted-elf'
        shutil.copyfile(Path(sys.executable).resolve(), self.binary)
        self.binary.chmod(0o700)
        self.actual = CI.elf(self.binary)
        self.good = json.loads(json.dumps({
            'package': EXPORT.KEY[0], 'target': EXPORT.KEY[1], **self.actual}))

    def bound(self, value):
        pin = EXPORT.recorded_harness_pin(value)
        EXPORT.need(CI.elf(self.binary) == pin,
                    'actual original compiler ELF differs from executed CI pin')
        return pin

    def test_actual_elf_json_roundtrip_preserves_all_held_identity_fields(self):
        before = copy.deepcopy(self.good)
        self.assertIs(type(self.actual['identity']), tuple)
        self.assertIs(type(self.good['identity']), list)
        pin = self.bound(self.good)
        self.assertEqual(pin, self.actual)
        self.assertEqual(len(pin['identity']), 9)
        fd = os.open(self.binary, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.assertEqual(CI.VERIFY.f9(os.fstat(fd)), pin['identity'])
            self.assertEqual(CI.VERIFY.f9(self.binary.lstat()), pin['identity'])
            self.assertEqual(CI.elf(self.binary), pin)
        finally:
            os.close(fd)
        self.assertEqual(self.good, before)
        self.assertIs(type(self.good['identity']), list)

    def test_malformed_recorded_identity_is_rejected(self):
        for identity in (None, (), tuple(self.good['identity']), {}, 'not-an-array',
                         [], self.good['identity'][:-1], self.good['identity'] + [0]):
            with self.subTest(identity=identity), self.assertRaises(RuntimeError):
                self.bound({**self.good, 'identity': identity})
        for index in range(9):
            for value in (True, False, -1, 0.0, '0', None):
                bad = copy.deepcopy(self.good)
                bad['identity'][index] = value
                with self.subTest(index=index, value=value), self.assertRaises(RuntimeError):
                    self.bound(bad)

    def test_harness_fields_are_exact_and_typed(self):
        for field in self.good:
            bad = copy.deepcopy(self.good)
            del bad[field]
            with self.subTest(missing=field), self.assertRaises(RuntimeError):
                self.bound(bad)
        with self.assertRaises(RuntimeError):
            self.bound({**self.good, 'extra': 0})
        for field, value in [('package', False), ('target', []), ('path', None),
                             ('bytes', True), ('bytes', 0), ('bytes', -1), ('bytes', 1.0),
                             ('sha256', 0), ('sha256', 'A' * 64), ('sha256', '0' * 63)]:
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                self.bound({**self.good, field: value})

    def test_changed_pin_or_actual_elf_is_rejected(self):
        for index in range(9):
            bad = copy.deepcopy(self.good)
            bad['identity'][index] += 1
            with self.subTest(changed_identity=index), self.assertRaises(RuntimeError):
                self.bound(bad)
        other_sha = ('0' if self.good['sha256'][0] != '0' else '1') + self.good['sha256'][1:]
        for field, value in [('path', str(self.binary) + '-other'),
                             ('bytes', self.good['bytes'] + 1), ('sha256', other_sha)]:
            with self.subTest(changed_field=field), self.assertRaises(RuntimeError):
                self.bound({**self.good, field: value})
        with self.binary.open('ab') as stream:
            stream.write(b'changed after the recorded pin')
        with self.assertRaises(RuntimeError):
            self.bound(self.good)


class ReportControls(unittest.TestCase):
    def setUp(self):
        packet = HERE if (HERE / 'MANIFEST.json').is_file() else HERE / 'packet'
        self.catalog = {(r['package'], r['target']): r for r in json.loads((packet / 'EXPECTED-CATALOG.json').read_text())}
        self.bins = {(r['package'], r['target']): r for r in json.loads((packet / 'EXPECTED-BINS.json').read_text())}
        self.docs = json.loads((packet / 'EXTRA-TARGETS.json').read_text())['doc_targets']
        self.source = json.loads((packet / 'MANIFEST.json').read_text())['source']
        self.head, self.run_id, self.inventory = '1' * 40, 42, '2' * 64
        self.good = {
            'schema': 'p4-native-leaf-complete-source-and-release-ci-v1', 'state': EXPORT.STATE,
            'errors': [], 'github_commit': self.head, 'github_run_id': self.run_id,
            'current_packet_inventory_sha256': self.inventory,
            'source_tree': self.source['tree'], 'source_files': self.source['files'],
            'source_bytes': self.source['bytes'],
            'all_source_bookends_equal': True, 'all_input_packet_bookends_equal': True,
            'doc_test_commands_executed': True,
            'historical_ELFs_reused': False, 'runtime_qualified': False, 'production_ready': False,
            'example_mains_executed': False, 'full_workspace_qualified': False,
            'positive_hardware_branches_inferred': False,
            'fresh_ordinary_passed': sum(len(r['all']) - len(r['ignored']) for r in self.catalog.values()),
            'fresh_test_targets': 49, 'historical_tests_counted_as_fresh': 0,
            'Android_builds': 0, 'Android_starts': 0, 'fresh_example_tests_passed': 9,
            'fresh_doc_tests_passed': 0, 'jobs': 1, 'test_threads': 1,
            'ignored_not_executed': [{'package': p, 'target': t, 'case': name}
                                     for (p, t), r in sorted(self.catalog.items()) for name in r['ignored']],
            'fresh_release_binaries': {key[1]: {} for key in self.bins},
            'fresh_example_binaries': {'first': {}, 'second': {}, 'third': {}},
            'doc_targets_checked': [{'package': r['package'], 'target': r['target'], 'passed_cases': 0}
                                    for r in self.docs],
            'final_descendant_retirement': [], 'started_ns': 1, 'finished_ns': 2,
        }

    def check(self, value):
        EXPORT.check_terminal(value, self.source, self.catalog, self.bins, self.docs,
                              self.head, self.run_id, self.inventory)

    def test_complete_bound_report_is_accepted(self):
        self.check(self.good)

    def test_stale_failure_qualification_and_bool_counts_are_rejected(self):
        mutations = [('state', 'FAILED'), ('errors', ['real compiler error']),
                     ('github_commit', '3' * 40), ('github_run_id', True),
                     ('source_files', False), ('source_tree', '4' * 40),
                     ('current_packet_inventory_sha256', '5' * 64),
                     ('all_source_bookends_equal', 1), ('all_input_packet_bookends_equal', False),
                     ('runtime_qualified', True), ('production_ready', 0),
                     ('jobs', True), ('historical_tests_counted_as_fresh', False),
                     ('fresh_ordinary_passed', self.good['fresh_ordinary_passed'] - 1),
                     ('ignored_not_executed', self.good['ignored_not_executed'][:-1]),
                     ('final_descendant_retirement', [{'pid': 123}])]
        for key, value in mutations:
            with self.subTest(field=key):
                bad = copy.deepcopy(self.good)
                bad[key] = value
                with self.assertRaises(RuntimeError):
                    self.check(bad)

    def test_zero_doc_count_cannot_be_replaced_by_false(self):
        bad = copy.deepcopy(self.good)
        bad['doc_targets_checked'][0]['passed_cases'] = False
        with self.assertRaises(RuntimeError):
            self.check(bad)

    def test_production_artifact_roster_cannot_include_test_driver(self):
        bad = copy.deepcopy(self.good)
        bad['fresh_release_binaries'].pop(next(iter(bad['fresh_release_binaries'])))
        bad['fresh_release_binaries']['droidloom_supervisor-test-driver'] = {}
        with self.assertRaises(RuntimeError):
            self.check(bad)


class CommandControls(unittest.TestCase):
    def setUp(self):
        self.good = {'name': 'target-01-ignored', 'argv': ['/actual/test-harness', '--ignored', '--list'],
                     'exit_code': 0, 'error': None, 'cleanup_errors': [], 'timed_out': False,
                     'actual_child_reaped': True, 'original_pidfd_held_until_reaped': True,
                     'owned_descendants_remaining': 0, 'retired_descendants': [],
                     'pid': 123, 'start_ticks': 456, 'started_ns': 1, 'finished_ns': 2}

    def test_list_only_actual_retired_command_is_accepted(self):
        EXPORT.check_command(self.good)

    def test_execution_or_unknown_retirement_is_rejected(self):
        for field, value in [('argv', ['/actual/test-harness', '--ignored']),
                             ('argv', ['/actual/test-harness', '--exact', EXPORT.CASE]),
                             ('actual_child_reaped', False), ('original_pidfd_held_until_reaped', 1),
                             ('owned_descendants_remaining', 1), ('timed_out', True),
                             ('exit_code', False), ('pid', True),
                             ('retired_descendants', [{'forced': True}])]:
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(self.good)
                bad[field] = value
                with self.assertRaises(RuntimeError):
                    EXPORT.check_command(bad)


if __name__ == '__main__':
    unittest.main()
