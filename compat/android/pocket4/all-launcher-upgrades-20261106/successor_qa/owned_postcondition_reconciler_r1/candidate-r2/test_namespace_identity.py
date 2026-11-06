#!/usr/bin/env python3
"""Narrow offline identity controls. Fixtures are not Android qualifications."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('postcondition_core_r2', HERE / 'owned_postcondition_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
DIFF = HERE.parent / 'actual-binding-diff-r1/stdout.raw.json'
DIFF_SHA = 'e62b639aa1dc226c27594479a594c8c8188b4ccc60d5bd752396dd399f02e601'
raw_diff = DIFF.read_bytes()
assert len(raw_diff) == 2294 and hashlib.sha256(raw_diff).hexdigest() == DIFF_SHA
actual_diff = json.loads(raw_diff)
assert actual_diff['ok'] is True and actual_diff['difference_count'] == 5


def census():
    rows = {}
    for item in os.listdir('/proc/self/fd'):
        try:
            value = os.fstat(int(item))
            rows[item] = (os.readlink('/proc/self/fd/' + item), value.st_dev, value.st_ino,
                          value.st_mode, value.st_uid, value.st_gid)
        except (FileNotFoundError, ProcessLookupError):
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return rows


def at(value, path):
    parts = path.lstrip('/').split('/')
    for part in parts[:-1]:
        value = value[int(part)] if type(value) is list else value[part]
    return value, parts[-1]


def fixture():
    # Every identity below is deliberately a synthetic local boundary fixture.
    # Only the five mtime pairs come verbatim from the real pinned diff receipt.
    rows = {name: {'device': 4, 'inode': 100 + index, 'mode': stat.S_IFREG | 0o444,
                  'uid': 0, 'gid': 0, 'bytes': 0, 'mtime_ns': 1, 'nlink': 1}
            for index, name in enumerate(core.NAMESPACE_NAMES)}
    ns = {name: name + ':[' + str(row['inode']) + ']' for name, row in rows.items()}
    original = {'schema': 'pocket4-successor-held-binding-r5-v1',
        'held_runtime_r5_sha256': core.HELD_R5_SHA,
        'target': {'init': {'pid': 11, 'start': '123', 'ns': ns}, 'namespaces': rows,
                   'root': {'mtime_ns': 17, 'device': 99, 'inode': 1}},
        'classpath': {'schema': 2, 'main_classpath_read': True,
            'zygote': {'host_pid': 12, 'start_ticks': 124, 'namespaces': dict(ns)},
            'command_mount_namespace': copy.deepcopy(rows['mnt']),
            'zygote_mount_namespace': copy.deepcopy(rows['mnt']),
            'files': [{'path': '/system/framework/fixture.jar', 'mtime_ns': 19, 'sha256': '1' * 64}]},
        'app_directories': {'fixture': {'mtime_ns': 21, 'inode': 22}},
        'fixture_apk': {'mtime_ns': 23, 'sha256': '2' * 64}}
    later = copy.deepcopy(original)
    for delta in actual_diff['differences']:
        owner, key = at(original, delta['path']); owner[key] = delta['before']
        owner, key = at(later, delta['path']); owner[key] = delta['after']
    return original, later


class Controls(unittest.TestCase):
    def test_actual_five_timestamp_pairs_preserved_and_accepted_only_as_observations(self):
        original, later = fixture()
        before = copy.deepcopy((original, later))
        proof = core.compare_held_bindings(original, later)
        self.assertEqual((original, later), before)
        self.assertEqual(len(proof['namespace_mtime_observations']), 8)
        self.assertEqual(proof['namespace_mtime_differences'], [
            {'path': row['path'], 'left_mtime_ns': row['before'], 'right_mtime_ns': row['after']}
            for row in actual_diff['differences']])
        self.assertTrue(proof['all_other_binding_fields_exactly_equal'])
        self.assertFalse(proof['live_namespace_qualification_performed_by_comparison'])

    def test_namespace_inode_device_type_and_process_start_changes_rejected(self):
        original, later = fixture()
        for path in ('/target/namespaces/pid/inode', '/target/namespaces/pid/device',
                     '/target/namespaces/pid/mode', '/target/init/start',
                     '/classpath/zygote/start_ticks'):
            changed = copy.deepcopy(later)
            owner, key = at(changed, path)
            owner[key] = '125' if type(owner[key]) is str else owner[key] + 1
            with self.subTest(path=path), self.assertRaises(core.Rejected):
                core.compare_held_bindings(original, changed)
        changed = copy.deepcopy(later)
        changed['target']['namespaces']['uts']['inode'] = 999
        changed['target']['init']['ns']['uts'] = 'uts:[999]'
        with self.assertRaises(core.Rejected):
            core.compare_held_bindings(original, changed)

    def test_ordinary_file_root_and_app_data_timestamps_stay_exact(self):
        original, later = fixture()
        for path in ('/classpath/files/0/mtime_ns', '/target/root/mtime_ns',
                     '/fixture_apk/mtime_ns', '/app_directories/fixture/mtime_ns'):
            changed = copy.deepcopy(later)
            owner, key = at(changed, path); owner[key] += 1
            with self.subTest(path=path), self.assertRaises(core.Rejected):
                core.compare_held_bindings(original, changed)

    def test_closed_locations_shapes_and_exact_frozen_provenance(self):
        original, later = fixture()
        for operation in ('extra_namespace', 'extra_field', 'wrong_type', 'wrong_producer', 'wrong_pid_link'):
            changed = copy.deepcopy(later)
            if operation == 'extra_namespace':
                changed['target']['namespaces']['user'] = copy.deepcopy(changed['target']['namespaces']['pid'])
            elif operation == 'extra_field':
                changed['target']['namespaces']['pid']['ctime_ns'] = 1
            elif operation == 'wrong_type':
                changed['target']['namespaces']['pid']['mtime_ns'] = True
            elif operation == 'wrong_producer':
                changed['held_runtime_r5_sha256'] = '0' * 64
            else:
                changed['target']['init']['ns']['pid'] = 'mnt:[101]'
            with self.subTest(operation=operation), self.assertRaises(core.Rejected):
                core.compare_held_bindings(original, changed)


if __name__ == '__main__':
    before = census()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = census()
    print(json.dumps({'schema': 'pocket4-namespace-identity-comparison-local-controls-r2',
        'passed': result.wasSuccessful() and before == after, 'cases': result.testsRun,
        'actual_diff_receipt_sha256': DIFF_SHA,
        'synthetic_identity_fixture_with_actual_timestamp_pairs': True,
        'full_private_bundle_validation_run': False, 'Main_actions': 0,
        'whole_process_fd_identities_unchanged': before == after,
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid()}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
