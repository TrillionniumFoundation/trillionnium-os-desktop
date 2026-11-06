#!/usr/bin/env python3
"""Local negative protocol controls; synthetic fixtures never become receipts."""
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('postcondition_core', HERE / 'owned_postcondition_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
QA_SOURCE = HERE.parent / 'reconstructed/source-generation-r2/helper/qa_contract.py'
qa_raw = QA_SOURCE.read_bytes()
assert hashlib.sha256(qa_raw).hexdigest() == 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e'
qa = types.ModuleType('actual_frozen_qa_contract_for_fixture_controls')
qa.__file__ = str(QA_SOURCE)
exec(compile(qa_raw, str(QA_SOURCE), 'exec'), qa.__dict__)
pub_spec = importlib.util.spec_from_file_location('postcondition_publisher', HERE / 'publish_owned_reconciliation.py')
publisher = importlib.util.module_from_spec(pub_spec)
pub_spec.loader.exec_module(publisher)


def fd_identity():
    rows = {}
    for item in os.listdir('/proc/self/fd'):
        try:
            fd = int(item); row = os.fstat(fd)
            rows[item] = (os.readlink('/proc/self/fd/' + item), row.st_dev, row.st_ino, row.st_mode)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return rows


def fixture_tree(nodes):
    window = {'package': core.PACKAGE, 'display': 0, 'type': 1, 'focused': True}
    copied = []
    for index, changes in enumerate(nodes):
        node = {'package': core.PACKAGE, 'path': '0/' + str(index), 'visible': True,
                'password': False, 'editable': False, 'supports_set_text': False,
                'resource_id': 'com.lianjia.beike:id/fixture_control',
                'resource_id_truncated': False, 'text': 'fixture only', 'text_truncated': False,
                'content_redacted': False, 'class': 'android.widget.TextView', 'class_truncated': False}
        node.update(changes)
        if node['password'] or not node['visible']:
            node.pop('text', None)
            node['content_redacted'] = True
        node['node_sha256'] = qa.sha(qa.canonical(node))
        copied.append(node)
    return {'complete': True, 'traversal': 'visible-non-password-subtrees', 'window': window,
            'window_sha256': qa.sha(qa.canonical(window)), 'observed_elapsed_ms': 100,
            'connection_scoped_window_id': 7, 'nodes': copied,
            'tree_sha256': qa.sha(qa.canonical(copied))}


class Controls(unittest.TestCase):
    def test_node_visibility_password_truncation_and_ambiguity(self):
        expected = {'resource_id': 'com.lianjia.beike:id/fixture_control'}
        proof = core.match_postcondition(qa, fixture_tree([{}]), expected)
        self.assertFalse(proof['business_success_verified'])
        for rows in ([], [{}, {}], [{'visible': False}], [{'password': True}],
                     [{'resource_id_truncated': True}], [{'package': 'tv.danmaku.bili'}]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                core.match_postcondition(qa, fixture_tree(rows), expected)

    def test_hash_binding_of_complete_tree(self):
        tree = fixture_tree([{}]); tree['nodes'][0]['resource_id'] = 'changed'
        with self.assertRaises(RuntimeError):
            core.match_postcondition(qa, tree, {'resource_id': 'changed'})

    def test_raw_command_failure_timeout_unjoined_and_mismatch(self):
        ci = {'label': 'Android command', 'mutation': True, 'automatic_retry': False,
              'timeout_seconds': 20, 'started_utc': '2026-11-06T00:00:00+00:00'}
        cr = {'returncode': 0, 'spawned': True, 'owned_command_joined': True, 'timed_out': False,
              'error': None, 'errors': [], 'action_attempted': True, 'automatic_retry': False,
              'stdout_sha256': core.sha(b'fixture'), 'stderr_sha256': core.sha(b''),
              'seconds': 0.1, 'ended_utc': '2026-11-06T00:00:01+00:00'}
        core.command_success(ci, cr, b'fixture', b'', True, 20)
        for key, value in (('returncode', 1), ('owned_command_joined', False), ('timed_out', True),
                           ('errors', [{'phase': 'fixture-failure'}]), ('stdout_sha256', '0' * 64),
                           ('action_attempted', False), ('seconds', float('nan'))):
            row = dict(cr); row[key] = value
            with self.subTest(key=key), self.assertRaises(core.Rejected):
                core.command_success(ci, row, b'fixture', b'', True, 20)

    def test_legacy_ui_and_case_cannot_enter_new_single_sequence_branch(self):
        scope = {'schema': 'pocket4-successor-recorder-scope-v1', 'package': core.PACKAGE, 'uid': core.UID,
                 'user': 0, 'epoch_sha256': core.MAIN_EPOCH, 'runtime_epoch_sha256': core.RUNTIME_EPOCH,
                 'app_scope_sha256': core.APP_SCOPE, 'adapter_manifest_sha256': core.RECORDER_MANIFEST,
                 'automatic_retry': False}
        launch = {'package': core.PACKAGE, 'task': 876, 'epoch_sha256': core.MAIN_EPOCH,
                  'prelaunch_absent': True, 'cleanup_allowed': True, 'prelaunch_task_ids': [],
                  'native_receipt_sha256': 'a' * 64, 'launch_step': 'fixture-launch'}
        build = {'build_receipt_sha256': core.BUILD_RECEIPT, 'source_manifest_sha256': core.HELPER_MANIFEST,
                 'signer_certificate_sha256': core.SIGNER_SHA, 'self_instrumentation': True,
                 'old_v2_provenance_inherited': False, 'APK': {'sha256': core.APK_SHA, 'bytes': 37008}}
        for operation in ('ui', 'owned-qa-case', 'cleanup', 'launch'):
            intent = {'operation': operation, 'mutation': True, 'scope': scope, 'automatic_retry': False}
            files = {'intent.json': json.dumps(intent).encode(), 'result.json': b'{}'}
            with self.subTest(operation=operation), self.assertRaisesRegex(core.Rejected, 'ONLY_FROZEN_OWNED_QA'):
                core.validate_step(files, adapter=None, qa=None, transport=None, scope=scope,
                    launch=launch, build=build, mutation=True, held_helper_path='/fixture-only', expected_binding={})

    def test_duplicates_nonfinite_and_nonidentity_postconditions(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(core.Rejected):
                core.document(raw)
        for value in ({'enabled': True}, {'resource_id': ''}, {'resource-id': 'old-cli-key'},
                      {'text': 'x', 'enabled': 1}):
            with self.subTest(value=value), self.assertRaises(core.Rejected):
                core.condition(value)

    def test_independent_observation_cannot_precede_action(self):
        action = {'intent': {'mutation': True, 'started_utc': '2026-11-06T00:00:02+00:00'},
                  'result': {'ended_utc': '2026-11-06T00:00:03+00:00'}}
        observed = {'intent': {'mutation': False, 'started_utc': '2026-11-06T00:00:00+00:00'},
                    'result': {'ended_utc': '2026-11-06T00:00:01+00:00'}}
        with self.assertRaisesRegex(core.Rejected, 'STRICT_ACTION_THEN_LATER'):
            core.validate_pair(action, observed, {'text': 'fixture'}, qa=qa,
                now=datetime.datetime(2026, 11, 6, 0, 0, 4, tzinfo=datetime.timezone.utc))

    def test_actual_reviewed_entry_shapes_and_changed_source_rejection(self):
        for role, directory, step in (('action', 'close-entry-popup-r1', 'close-entry-popup-01'),
                                      ('observation', 'inspect-after-close-r2', 'inspect-after-close-02')):
            requested = json.loads((HERE.parent / 'actual' / directory / 'process-request.json').read_bytes())
            argv = publisher.original_adapter_arguments(requested, role)
            self.assertEqual(argv[argv.index('--step') + 1], step)
            self.assertEqual(argv[argv.index('--helper-uid') + 1], '10157')
            changed = copy.deepcopy(requested); changed['args'][5] += '\n# changed source\n'
            with self.assertRaisesRegex(RuntimeError, 'EXACT_REVIEWED_ORIGINAL'):
                publisher.original_adapter_arguments(changed, role)

    def test_real_owned_host_file_noreplace_and_descriptor_closure(self):
        before = fd_identity()
        with tempfile.TemporaryDirectory(prefix='postcondition-commit-fixture-') as temporary:
            path = Path(temporary) / 'fixture-only.bin'
            raw = b'fixture-only; not a Flow reconciliation or Android proof\n'
            row = publisher.commit_envelope(path, raw, 'a' * 32)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(row['sha256'], hashlib.sha256(raw).hexdigest())
            with self.assertRaises(FileExistsError):
                publisher.commit_envelope(path, b'not allowed to replace', 'b' * 32)
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(before, fd_identity())

    def test_actual_nonroot_private_root_rejection_closes_acquired_fd(self):
        self.assertNotEqual(os.geteuid(), 0, 'this local negative control needs actual nonroot ownership')
        before = fd_identity()
        with tempfile.TemporaryDirectory(prefix='postcondition-root-fixture-') as temporary:
            with self.assertRaisesRegex(RuntimeError, 'ROOT_PRIVATE_DIRECTORY'):
                publisher.PinnedRoot(temporary, {}, time.monotonic() + 1)
        self.assertEqual(before, fd_identity())


if __name__ == '__main__':
    before = fd_identity()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = fd_identity()
    print(json.dumps({'schema': 'pocket4-owned-postcondition-local-controls-v1',
        'passed': result.wasSuccessful() and before == after, 'cases': result.testsRun,
        'whole_process_fd_identities_unchanged': before == after,
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'Main_actions': 0,
        'synthetic_fixtures_only': True, 'actual_action_acceptance_tested': False,
        'reconciliation_receipts_written': 0}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
