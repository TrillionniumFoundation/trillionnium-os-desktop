"""Stateful source controls; every Android/UI response here is an explicit model.

These tests execute the real Settings policy, transaction state machine and
receipt parser against a stateful fake device and real temporary evidence files.
They do not qualify an Android Main, a Settings installation or an app gate.
"""
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / 'bundle' / 'source' / 'settings'


def load(name):
    spec = importlib.util.spec_from_file_location('settings_test_' + name, SOURCE / name)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


P = load('settings_profiles.py')
R = load('settings_runtime.py')
POLICY = load('settings_policy.py')
I = load('settings_identity.py')
PAGES = load('settings_pages.py')


class Common:
    STACKS = ['/system/bin/cmd', 'activity', 'stack', 'list']

    @staticmethod
    def need(value, code):
        if not value:
            raise RuntimeError(code)

    @staticmethod
    def parse(raw):
        return json.loads(raw)

    @staticmethod
    def regular(path, maximum=2*1024*1024, contents=True):
        raw = Path(path).read_bytes()
        if len(raw) > maximum:
            raise RuntimeError('TEST_EVIDENCE_SIZE')
        ref = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        return (raw, ref) if contents else ref

    @classmethod
    def read_ref(cls, ref):
        raw, actual = cls.regular(ref['path'])
        cls.need(ref == actual, 'TEST_EVIDENCE_PIN_CHANGED')
        return raw

    @classmethod
    def write_new(cls, path, value, mode=0o600):
        raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
        with Path(path).open('xb') as output:
            output.write(raw)
        Path(path).chmod(mode)
        return cls.regular(path, contents=False)

    @staticmethod
    @contextmanager
    def locked(path):
        yield


class DeviceModel:
    """An independent key/value backend with faults at dispatch/readback edges."""
    def __init__(self, original):
        self.settings = {'screen_brightness': '137', 'screen_off_timeout': '600000'}
        if original is not None:
            self.settings['time_12_24'] = original
        self.writes = []
        self.fail_after_mutation = False
        self.stale_once_after_mutation = False
        self.stale_read = None

    def run(self, argv):
        if argv == P.SETTINGS_READ:
            values = self.settings if self.stale_read is None else self.stale_read
            self.stale_read = None
            return ''.join(k + '=' + v + '\n' for k, v in sorted(values.items())).encode()
        self.writes.append(list(argv))
        before = dict(self.settings)
        if argv[3] == 'put':
            self.settings[argv[5]] = argv[6]
            raw = b''
        elif argv[3] == 'delete':
            del self.settings[argv[5]]
            raw = b'Deleted 1 rows\n'
        else:
            raise AssertionError('Unmodeled command was admitted')
        if self.stale_once_after_mutation:
            self.stale_read = before
            self.stale_once_after_mutation = False
        if self.fail_after_mutation:
            raise TimeoutError('MODEL child mutated but retirement is unknown')
        return raw


class FlowModel:
    def __init__(self, common, session, device, root, name='first'):
        self.c = common
        self.session = session
        self.scope_ref = {'model': name}
        self.root = root / name
        self.step = self.root / 'steps' / 'commands'
        self.step.mkdir(parents=True)
        self.phase = 'inspect'
        self.deadline = time.monotonic() + 600
        self.device = device
        self.index = 0
        self.policy = POLICY.Policy(self)
        # The original native launch is modeled explicitly. The real recorder
        # prefix checker still reads and validates its on-disk terminal record.
        self.record(['/model/native-launch'], complete=True)

    def selected_task(self):
        return {'task': 17, 'cleanup_allowed': True, 'prelaunch_absent': True}

    def guard(self):
        self.c.need(time.monotonic() < self.deadline, 'MODEL_LEASE_EXPIRED')

    def record(self, argv, *, complete):
        self.index += 1
        prefix = self.step / ('command-%03d' % self.index)
        self.c.write_new(str(prefix) + '.logical.json', {'argv': argv})
        if complete:
            self.c.write_new(str(prefix) + '.result.json', {
                'host_retirement_proved': True, 'evidence_complete': True,
                'returncode': 0, 'timed_out': False, 'errors': [], 'first_error': None})
        return prefix

    def android(self, argv, timeout=20, *, mutation=False):
        self.guard()
        self.policy.admit(argv, timeout, mutation, False)
        prefix = self.record(argv, complete=False)
        raw = self.device.run(argv)
        self.c.write_new(str(prefix) + '.result.json', {
            'host_retirement_proved': True, 'evidence_complete': True,
            'returncode': 0, 'timed_out': False, 'errors': [], 'first_error': None})
        return raw


class TransactionControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.c = Common()

    def setup_transaction(self, original, *, locale_24=False):
        active = {'case_root': str(self.root), 'lease': {'model': 'lease'},
                  'business_contract': copy.deepcopy(P.BUSINESS_CONTRACT)}
        session = R.Session(self.c, {'model': 'active'}, active, P, None, None)
        session.require_owned_task = lambda flow: ({'task': 17}, {'model': 'claim'})
        device = DeviceModel(original)
        flow = FlowModel(self.c, session, device, self.root)
        state = {'use_24hour': locale_24 if original is None else original == '24',
                 'locale_default': original is None}
        session.prepare_setting(flow, state, {'model': 'actual-observation-fixture'})
        return session, device, flow

    def cleanup_lease(self):
        return patch.object(R, 'validate_lease', return_value={
            'cleanup_deadline_monotonic_ns': time.monotonic_ns() + 120*10**9})

    def test_exact_roundtrip_existing_12_24_and_absent(self):
        for original in ('12', '24', None):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as folder:
                self.root = Path(folder)
                session, device, first = self.setup_transaction(original)
                baseline = dict(device.settings)
                session.write_setting(first)
                changed = session.roundtrip['test_value']
                self.assertEqual(device.settings['time_12_24'], changed)
                second = FlowModel(self.c, session, device, self.root, 'second')
                self.assertEqual(session.read_setting(second), changed)
                session.write_setting(second, restore=True)
                self.assertEqual(device.settings, baseline)
                self.assertEqual(len(device.writes), 2)
                self.assertTrue(session.roundtrip['restore_readback_verified'])
                if original is None:
                    self.assertEqual(device.writes[-1], P.setting_write_argv(None))
                    self.assertNotIn('time_12_24', device.settings)

    def test_known_write_then_content_failure_restores_using_retained_context(self):
        session, device, first = self.setup_transaction(None, locale_24=True)
        before = dict(device.settings)
        session.write_setting(first)
        # The first task was normally removed; its held Main context is retained
        # even when the second Flow constructor fails before dispatch.
        first.phase = 'cleanup'
        with self.cleanup_lease():
            self.assertTrue(session.restore_known_setting(first))
        self.assertEqual(device.settings, before)
        self.assertEqual(len(device.writes), 2)
        self.assertFalse(session.roundtrip['reopen_persistence_verified'])

    def test_known_write_bad_readback_can_restore_without_replaying_write(self):
        session, device, flow = self.setup_transaction('12')
        device.stale_once_after_mutation = True
        with self.assertRaisesRegex(RuntimeError, 'READBACK_MISMATCH'):
            session.write_setting(flow)
        self.assertEqual(device.settings['time_12_24'], '24')
        self.assertIsNone(session.pending_setting)
        with self.cleanup_lease():
            session.restore_known_setting(flow)
        self.assertEqual(device.settings['time_12_24'], '12')
        self.assertEqual(len(device.writes), 2)

    def test_unknown_write_does_not_restore_or_replay(self):
        session, device, flow = self.setup_transaction('12')
        device.fail_after_mutation = True
        with self.assertRaises(TimeoutError):
            session.write_setting(flow)
        self.assertEqual(device.settings['time_12_24'], '24')
        with self.cleanup_lease(), self.assertRaisesRegex(RuntimeError, 'UNKNOWN_EFFECT'):
            session.restore_known_setting(flow)
        self.assertEqual(len(device.writes), 1)
        self.assertIsNotNone(session.pending_setting)

    def test_unknown_restore_cannot_be_retried(self):
        session, device, flow = self.setup_transaction('24')
        session.write_setting(flow)
        device.fail_after_mutation = True
        with self.assertRaises(TimeoutError):
            session.write_setting(flow, restore=True)
        with self.cleanup_lease(), self.assertRaisesRegex(RuntimeError, 'UNKNOWN_EFFECT'):
            session.restore_known_setting(flow)
        self.assertEqual(len(device.writes), 2)
        self.assertFalse(session.roundtrip['restore_readback_verified'])

    def test_unclassified_native_reopen_blocks_setting_restore_even_with_retired_prefix(self):
        session, device, first = self.setup_transaction('12')
        session.write_setting(first)
        second = FlowModel(self.c, session, device, self.root, 'second')
        session.pending_native = second.scope_ref
        # Its host command may have retired; the native semantic claim/stacks
        # have not been accepted, so no setting mutation is allowed afterwards.
        session.recorded_prefix(second)
        with self.cleanup_lease(), self.assertRaisesRegex(RuntimeError, 'UNKNOWN_EFFECT'):
            session.restore_known_setting(second)
        self.assertEqual(len(device.writes), 1)

    def test_unknown_owned_task_removal_blocks_setting_restore(self):
        session, device, flow = self.setup_transaction('12')
        session.write_setting(flow)
        session.cleanup_admission = (flow.scope_ref, 17)
        with self.cleanup_lease(), self.assertRaisesRegex(RuntimeError, 'UNKNOWN_EFFECT'):
            session.restore_known_setting(flow)
        self.assertEqual(len(device.writes), 1)

    def test_external_change_is_preserved_on_apply_and_restore(self):
        session, device, flow = self.setup_transaction(None)
        device.settings['time_12_24'] = '12'
        with self.assertRaisesRegex(RuntimeError, 'NO_OVERWRITE'):
            session.write_setting(flow)
        self.assertEqual(device.writes, [])
        device.settings.pop('time_12_24')
        session.write_setting(flow)
        device.settings['time_12_24'] = '12'
        with self.cleanup_lease(), self.assertRaisesRegex(RuntimeError, 'NO_OVERWRITE'):
            session.restore_known_setting(flow)
        self.assertEqual(device.settings['time_12_24'], '12')
        self.assertEqual(len(device.writes), 1)

    def test_absent_and_literal_null_are_not_conflated(self):
        self.assertIsNone(R.time_format_value(b'screen_brightness=137\n'))
        for raw in (b'time_12_24=null\n', b'time_12_24=12\ntime_12_24=24\n',
                    b'Error: provider unavailable\n', b'screen_brightness=137',
                    b'screen_brightness=137\r\n', b'screen_brightness=137\0\n', b''):
            with self.assertRaises(RuntimeError):
                R.time_format_value(raw)

    def test_restore_requires_previous_own_write_and_replay_refuses(self):
        session, device, flow = self.setup_transaction('12')
        with self.assertRaisesRegex(RuntimeError, 'OWN_PREVIOUS_WRITE'):
            session.write_setting(flow, restore=True)
        session.write_setting(flow)
        with self.assertRaisesRegex(RuntimeError, 'REPLAYED'):
            session.write_setting(flow)
        session.write_setting(flow, restore=True)
        with self.assertRaisesRegex(RuntimeError, 'REPLAYED'):
            session.write_setting(flow, restore=True)
        self.assertEqual(len(device.writes), 2)

    def test_policy_rejects_unowned_other_setting_and_permission_writes(self):
        session, device, flow = self.setup_transaction('12')
        commands = [P.setting_write_argv('24'),
            ['/system/bin/settings', '--user', '0', 'put', 'system', 'screen_brightness', '0'],
            ['/system/bin/pm', 'grant', P.PACKAGE, 'android.permission.CAMERA'],
            ['/system/bin/cmd', 'account', 'remove', '0']]
        for argv in commands:
            with self.subTest(argv=argv), self.assertRaises(RuntimeError):
                flow.policy.admit(argv, 20, True, False)
        self.assertEqual(device.writes, [])


class PermissionAndUIControls(unittest.TestCase):
    c = Common()

    def test_permission_denied_is_a_valid_observed_state_not_an_invitation_to_grant(self):
        before = {'all_permission_rows': ['android.permission.CAMERA: granted=false, flags=[ USER_SET ]']}
        self.assertFalse(I.permission_state(self.c, before, 'android.permission.CAMERA'))
        self.assertFalse(I.permission_result(self.c, b'-1\n'))
        self.assertTrue(I.permission_result(self.c, b'0\n'))
        for raw in (b'granted\n', b'-1\n0\n', b'Error\n', b''):
            with self.assertRaises(RuntimeError): I.permission_result(self.c, raw)

    def test_permission_interface_reads_actual_errors_and_preserves_denial(self):
        before = {'all_permission_rows': ['android.permission.CAMERA: granted=false']}
        replies = {tuple(P.PERMISSION_CHECK): b'-1\n',
                   tuple(P.PERMISSION_ERROR): b'Error: check-permission missing permission argument\n',
                   tuple(P.ACCOUNT_READ): b'User UserInfo{0:Owner:c13}:\n  Accounts: 0\n\n  Active Sessions: 0\n'}
        calls = []
        def android(argv, timeout):
            calls.append((argv, timeout))
            return replies[tuple(argv)]
        flow = types.SimpleNamespace(c=self.c, android=android)
        session = types.SimpleNamespace(profile=P)
        pages = [{'summary': {'page': name}} for name in ('special_access', 'accounts')]
        result = I.verify_permission_interfaces(flow, session, before, pages)
        self.assertFalse(result['granted'])
        self.assertEqual([v[0] for v in calls], [P.PERMISSION_CHECK, P.PERMISSION_ERROR, P.ACCOUNT_READ])
        replies[tuple(P.PERMISSION_CHECK)] = b'0\n'
        with self.assertRaisesRegex(RuntimeError, 'DISAGREE'):
            I.verify_permission_interfaces(flow, session, before, pages)
        replies[tuple(P.PERMISSION_CHECK)] = b'-1\n'
        replies[tuple(P.PERMISSION_ERROR)] = b'Unknown service\n'
        with self.assertRaisesRegex(RuntimeError, 'INPUT_ERROR'):
            I.verify_permission_interfaces(flow, session, before, pages)

    def test_accounts_match_identity_not_session_age_and_detect_data_loss(self):
        raw = (b'User UserInfo{0:Owner:c13}:\n  Accounts: 1\n'
               b'    Account {name=fixture@example.invalid, type=com.example}\n\n'
               b'  Active Sessions: 0\n')
        before = I.accounts(self.c, raw)
        self.assertEqual(before, I.accounts(self.c, raw.replace(b'Sessions: 0', b'Sessions: 2')))
        self.assertNotEqual(before, I.accounts(self.c, raw.replace(b'fixture@', b'other@')))
        self.assertNotIn('example.invalid', json.dumps(before))
        for malformed in (raw.replace(b'Accounts: 1', b'Accounts: 2'),
                          raw.replace(b'Accounts: 1', b'Accounts: 0'), raw + raw,
                          b'Permission Denial: account service\n', raw.rstrip(b'\n')):
            with self.assertRaises(RuntimeError): I.accounts(self.c, malformed)

    @staticmethod
    def switches(use24=False, locale=True):
        base = {'package': P.PACKAGE, 'visible': True, 'enabled': True,
                'password': False, 'editable': False, 'source': 'native_accessibility', 'window_id': 4}
        return [
            {**base, 'text': P.LOCALE_FORMAT_TITLES[0], 'class': 'android.widget.TextView',
             'bounds_array': [10, 100, 200, 130]},
            {**base, 'class': 'android.widget.Switch', 'checked': locale, 'bounds_array': [220, 90, 270, 140]},
            {**base, 'text': P.TIME_FORMAT_TITLES[0], 'class': 'android.widget.TextView',
             'enabled': not locale, 'bounds_array': [10, 200, 200, 230]},
            {**base, 'class': 'android.widget.Switch', 'checked': use24, 'enabled': not locale,
             'bounds_array': [220, 190, 270, 240]}]

    def test_native_switches_read_both_disabled_default_and_explicit_format(self):
        self.assertEqual(PAGES.time_format_state(self.switches(), P),
                         {'use_24hour': False, 'locale_default': True})
        self.assertEqual(PAGES.time_format_state(self.switches(True, False), P),
                         {'use_24hour': True, 'locale_default': False})

    def test_native_switch_ambiguity_wrong_window_and_fake_boolean_refuse(self):
        modifiers = [lambda n: n.append(dict(n[-1])),
                     lambda n: n[-1].update(window_id=5),
                     lambda n: n[-1].update(checked=1),
                     lambda n: n[-1].update(bounds_array=[220, 100, 270, 140]),
                     lambda n: n[-1].update(**{'class': 'android.widget.TextView'}),
                     lambda n: n[2].update(text='Unrelated setting')]
        for change in modifiers:
            nodes = self.switches(); change(nodes)
            with self.assertRaises(RuntimeError): PAGES.time_format_state(nodes, P)

    def test_existing_real_window_and_png_validation_remains_required(self):
        image = Image.new('RGB', (32, 32))
        image.putdata([(0, 0, 0) if n % 2 else (200, 220, 255) for n in range(1024)])
        digest = hashlib.sha256((32).to_bytes(4, 'big')*2 + image.tobytes()).hexdigest()
        stream = io.BytesIO(); image.save(stream, format='PNG'); image.close()
        node = {'package': P.PACKAGE, 'visible': True, 'enabled': True,
                'password': False, 'editable': False}
        packet = {'ok': True, 'native': {'ok': True, 'accessibility_mode_restoration_verified': True,
            'nodes': [{**node, 'text': 'Settings'}, {**node, 'text': 'Model 1', 'clickable': True},
                      {**node, 'text': 'Model 2', 'scrollable': True}]},
            'screenshot': {'scope_width': 32, 'scope_height': 32, 'scope_sha256': digest,
                'scope': {'package': P.PACKAGE, 'activity': P.HOME_ACTIVITY,
                          'android_init_host_pid': 123, 'display_id': 0,
                          'accessibility_mode': 'none', 'window_token': 'a12b'}}}
        self.assertTrue(PAGES.observation(packet, stream.getvalue(), profile=P,
                                         page=None, init_pid=123)['expected_title_observed'])
        packet['screenshot']['scope']['package'] = 'unrelated.application'
        with self.assertRaisesRegex(RuntimeError, 'WINDOW_OR_MAIN_CHANGED'):
            PAGES.observation(packet, stream.getvalue(), profile=P, page=None, init_pid=123)


if __name__ == '__main__':
    unittest.main()
