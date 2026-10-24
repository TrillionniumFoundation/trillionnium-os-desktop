"""Protocol/namespace negative cases, not Android or production qualification."""

import base64
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from support.android.receiver import build_receiver


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def payload():
    return {
        'schema_version': 1, 'action': 'set_text', 'operation_id': 'original:operation-1',
        'destination_id': 'fixture-only', 'value': '中文输入😀\n第二行', 'expires_elapsed_ms': 105000,
        'observation': {
            'generation': {'boot_id': 'a'},
            'window': {'package': 'com.android.settings'},
            'target': {'resource_id': 'com.android.settings:id/search_src_text'},
        },
    }


def request(value=None, op='organ-set-text'):
    raw = canonical(payload() if value is None else value)
    return {'op': op, 'payload_base64': base64.b64encode(raw).decode(),
            'payload_sha256': hashlib.sha256(raw).hexdigest()}


class BoundReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.output, cls.record = build_receiver.sources(Path(cls.directory.name) / 'candidate')
        loader = importlib.machinery.SourceFileLoader('bound_receiver_fixture', str(cls.output / 'android-digitalis-observe-helper'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.receiver = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.receiver)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_upstream_source_bytes_and_legacy_cli_remain_pinned(self):
        for name, sha in build_receiver.PREIMAGES.items():
            self.assertEqual(build_receiver.sha(build_receiver.ROOT / 'upstream' / name), sha)
        original = (build_receiver.ROOT / 'upstream/android_app.py').read_text()
        generated = (self.output / 'android-digitalis-observe-helper').read_text()
        self.assertEqual(original[original.index('def client():'):], generated[generated.index('def client():'):])

    def test_unknown_fields_and_nonexact_resource_fail_before_discovery(self):
        cases = [
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'editable'},
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'com.android.settings:id/search', 'index': 0},
            {'op': 'organ-observe', 'package': 'com.android.settings', 'resource_id': 'com.other:id/search'},
            {**request(), 'grant': 'caller-claimed-authority'},
        ]
        with patch.object(self.receiver, 'discover') as discover:
            for value in cases:
                with self.subTest(value=value), self.assertRaises(self.receiver.ControlError):
                    self.receiver.dispatch(value)
        discover.assert_not_called()

    def test_same_exact_payload_and_utf8_pass_through_to_receiver(self):
        original = request()
        actual = self.receiver._organ_request(original)
        self.assertEqual(actual['organ']['payload_base64'], original['payload_base64'])
        self.assertEqual(actual['organ']['payload_sha256'], original['payload_sha256'])
        self.assertEqual(actual['value'], payload()['value'])
        self.assertEqual(actual['selector'], {'id': 'com.android.settings:id/search_src_text', 'package': 'com.android.settings'})
        self.assertNotIn('index', actual)

    def test_payload_hash_and_duplicate_json_are_rejected(self):
        changed = request()
        changed['payload_sha256'] = '0' * 64
        duplicate = b'{"action":"set_text","action":"set_text"}'
        cases = [changed, {'op': 'organ-set-text', 'payload_base64': base64.b64encode(duplicate).decode(),
                           'payload_sha256': hashlib.sha256(duplicate).hexdigest()}]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(self.receiver.ControlError):
                self.receiver._organ_request(value)

    def test_noncanonical_floats_boolean_deadline_and_text_bounds_reject(self):
        variants = [('expires_elapsed_ms', True), ('value', '中' * 1366), ('value', 'a\0b'),
                    ('operation_id', 'space is not an operation')]
        for name, value in variants:
            changed = payload()
            changed[name] = value
            with self.subTest(name=name), self.assertRaises(self.receiver.ControlError):
                self.receiver._organ_request(request(changed))
        with self.assertRaises(self.receiver.ControlError):
            self.receiver._organ_json(b'{"extra":NaN}')
        with self.assertRaises(self.receiver.ControlError):
            self.receiver._organ_json(b'{ "extra":1}')

    def test_readback_is_a_find_and_carries_no_text_mutation(self):
        actual = self.receiver._organ_request(request(op='organ-readback'))
        self.assertEqual(actual['op'], 'find')
        self.assertEqual(actual['organ']['mode'], 'readback')
        self.assertNotIn('value', actual)

    def test_generation_change_or_expiry_prevents_runner_submission(self):
        for generation, clock, code in [({'boot_id': 'b'}, 100, 'CELL_GENERATION_CHANGED'),
                                         ({'boot_id': 'a'}, 106, 'ORGAN_DEADLINE_EXCEEDED')]:
            cell = types.SimpleNamespace(generation=generation, deadline=155, run=lambda *a, **k: None, close=lambda: None)
            with patch.object(self.receiver, '_OrganCell', return_value=cell), \
                    patch.object(self.receiver.time, 'clock_gettime', return_value=clock), \
                    patch.object(self.receiver, 'ui') as ui:
                with self.assertRaises(self.receiver.ControlError) as failed:
                    self.receiver.dispatch(request())
            self.assertEqual(str(failed.exception), code)
            ui.assert_not_called()

    def test_helper_cannot_synthesize_receiver_success_or_rebind_operation(self):
        cell = types.SimpleNamespace(generation={'boot_id': 'a'}, deadline=155,
                                     run=lambda *a, **k: None, close=lambda: None)
        good = {'ok': True, 'organ_protocol': 'pocket4-bound-text-v1', 'receiver_generation': cell.generation,
                'operation_id': payload()['operation_id'], 'payload_sha256': request()['payload_sha256']}
        for missing in ('organ_protocol', 'receiver_generation', 'operation_id', 'payload_sha256'):
            reply = copy.deepcopy(good)
            del reply[missing]
            with self.subTest(missing=missing), \
                    patch.object(self.receiver, '_OrganCell', return_value=cell), \
                    patch.object(self.receiver.time, 'clock_gettime', return_value=100), \
                    patch.object(self.receiver, 'ui', return_value=reply):
                with self.assertRaises(self.receiver.ControlError) as failed:
                    self.receiver.dispatch(request())
            self.assertTrue(failed.exception.details['outcome_unknown'])

    def test_namespace_descriptors_pin_original_cell_across_every_command(self):
        generation = {'mount_namespace': 'mnt:[11]', 'pid_namespace': 'pid:[12]'}
        with patch.object(self.receiver, 'discover', return_value=(123, {}, {})) as discover, \
                patch.object(self.receiver, '_organ_generation', return_value=generation), \
                patch.object(self.receiver.os, 'open', side_effect=[21, 22, 23, 24]), \
                patch.object(self.receiver.os, 'readlink', side_effect=['mnt:[11]', 'pid:[12]']), \
                patch.object(self.receiver.os, 'close'), \
                patch.object(self.receiver.time, 'clock_gettime', return_value=100), \
                patch.object(self.receiver.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0, stdout=b'fixed')) as run:
            cell = self.receiver._OrganCell()
            try:
                cell.run(['/system/bin/getprop'])
                cell.run(['/system/bin/getprop'])
            finally:
                cell.close()
        discover.assert_called_once()
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertIn('--mount=/proc/self/fd/21', argv)
            self.assertIn('--pid=/proc/self/fd/22', argv)
            self.assertNotIn('-t', argv)
            self.assertEqual(call.kwargs['pass_fds'], (21, 22, 23, 24))

    def test_expired_cell_budget_never_starts_a_late_instrumentation(self):
        cell = self.receiver._OrganCell.__new__(self.receiver._OrganCell)
        cell.init, cell.env, cell.fds, cell.generation, cell.deadline = 123, {}, {}, {'a': 'b'}, 105
        with patch.object(self.receiver, '_organ_generation', return_value=cell.generation), \
                patch.object(self.receiver.time, 'clock_gettime', return_value=106), \
                patch.object(self.receiver.subprocess, 'run') as run:
            with self.assertRaises(self.receiver.ControlError):
                cell.run(['/system/bin/getprop'])
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
