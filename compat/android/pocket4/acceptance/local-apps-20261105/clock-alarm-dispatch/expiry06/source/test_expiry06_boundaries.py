"""Pure host tests of actual expiry06 methods; Android/native/provider are doubles."""
import copy, hashlib, importlib.util, json, time, types, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

new = load('expiry06_tested', HERE / 'timer_expiry06.py')
core = load('core04_tested', HERE / 'timer_core04.py')
base = types.SimpleNamespace(exact_leaf=lambda roots, task: True)
Flow = new.make_flow(core, base)
UNUSED = -(1 << 63)
BASE = {851: {'display': 0, 'user': 0, 'freeform': False,
    'children': [{'id': 851, 'component': 'home/.Home', 'user': 0}]}}
MAIN = {'display': 0, 'user': 0, 'freeform': True,
    'children': [{'id': 101, 'component': new.PACKAGE + '/.DeskClock', 'user': 0}]}

def state(code):
    return {'ids': [0], 'stopwatch': {}, 'values': {}, 'timers': [{
        'id': 0, 'length_ms': 60000, 'total_length_ms': 0 if code == 3 else 60000,
        'label': None, 'delete_after_use': False, 'state': code,
        'last_start_ms': 123000 if code == 3 else UNUSED,
        'last_wall_ms': 456000 if code == 3 else UNUSED,
        'remaining_ms': -20 if code == 3 else 60000}]}

class NativeError(RuntimeError):
    def __init__(self, unknown):
        super().__init__('WINDOW_CHANGED_NO_ACTION_TAKEN')
        self.details = {'outcome_unknown': unknown, 'automatic_retry': False,
                        'accessibility_mode_restoration_verified': True}

def prepared(reply=None, error=None):
    flow = Flow.__new__(Flow)
    flow.number = 0; flow.effect_pending = flow.close_pending = None
    flow.deadline = time.monotonic() + 100; flow.timer_id = 0; flow.stop_dispatched = False
    flow.alert_task = None; flow.alert_self_finished = []; flow.baseline = copy.deepcopy(BASE)
    flow.r = {'phases': {}, 'owned_timer_id': 0}; flow.owned = [101]; flow.closed = []
    calls = {'native': 0, 'close': 0, 'records': []}
    focus = {'package': new.PACKAGE, 'activity': new.MAIN, 'focused_activity': new.MAIN,
             'window_token': 'abc', 'task': 101, 'verified': True, 'user': 0}
    def native(request):
        calls['native'] += 1
        if error:
            raise error
        return copy.deepcopy(reply or {'ok': True, 'performed': 'click', 'outcome_unknown': False,
            'accessibility_mode_restoration_verified': True,
            'actual_target': {'package': new.PACKAGE, 'resource-id': new.PACKAGE + ':id/fab',
                'class': 'android.widget.ImageButton', 'content-desc': 'Stop',
                'enabled': True, 'clickable': True}})
    sequence = [state(3), state(3), state(4)]
    flow.m = types.SimpleNamespace(read=lambda session: sequence.pop(0) if len(sequence) > 1 else sequence[0],
                                  UNUSED=UNUSED)
    flow.c = types.SimpleNamespace(pending=None, actions=0, observe=lambda *a, **kw: None)
    flow.t = types.SimpleNamespace(owned=(101, {851}), s=types.SimpleNamespace(
        guard=lambda: None, helper=types.SimpleNamespace(ui=native, ControlError=NativeError)),
        ready_focus=lambda **kwargs: copy.deepcopy(focus),
        last_observation={'screenshot': {'scope': {'window_token': 'abc'}}},
        record=lambda label, value: calls['records'].append((label, copy.deepcopy(value))),
        stacks=lambda label: ({**copy.deepcopy(BASE), 101: copy.deepcopy(MAIN)}, {851, 101}),
        close=lambda: calls.__setitem__('close', calls['close'] + 1))
    flow.node = lambda *args: {'resource-id': new.PACKAGE + ':id/fab', 'text': '',
        'content-desc': 'Stop', 'class': 'android.widget.ImageButton', 'package': new.PACKAGE}
    return flow, calls

class Boundaries(unittest.TestCase):
    def test_unknown_stop_blocks_cleanup_and_close(self):
        flow, calls = prepared(error=NativeError(True))
        with self.assertRaises(NativeError): flow.stop('test')
        self.assertIsNotNone(flow.c.pending)
        self.assertIsNotNone(flow.effect_pending)
        flow.cleanup(time.monotonic() + 45)
        with self.assertRaises(RuntimeError): flow.close()
        self.assertEqual((calls['native'], calls['close']), (1, 0))

    def test_explicit_no_input_is_not_replayed(self):
        flow, calls = prepared(error=NativeError(False))
        with self.assertRaises(NativeError): flow.stop('test')
        self.assertIsNone(flow.c.pending); self.assertIsNone(flow.effect_pending)
        with self.assertRaises(RuntimeError): flow.stop('again')
        self.assertEqual(calls['native'], 1)

    def test_ack_only_cannot_clear_reset_effect(self):
        flow, calls = prepared()
        # The actual post-ACK readback throws immediately; no 12-second sleep.
        count = [0]
        def read(session):
            count[0] += 1
            if count[0] >= 3: raise RuntimeError('READBACK_UNAVAILABLE')
            return state(3)
        flow.m.read = read
        with self.assertRaisesRegex(RuntimeError, 'READBACK_UNAVAILABLE'): flow.stop('test')
        self.assertIsNone(flow.c.pending)
        self.assertIsNotNone(flow.effect_pending)
        with self.assertRaises(RuntimeError): flow.close()
        self.assertEqual((calls['native'], calls['close']), (1, 0))

    def test_exact_reset_clears_effect_without_replay(self):
        flow, calls = prepared()
        flow.stop('test')
        self.assertIsNone(flow.c.pending); self.assertIsNone(flow.effect_pending)
        self.assertEqual(flow.r['phases']['stopped-reset'], state(4))
        self.assertEqual(calls['native'], 1)
        self.assertTrue(flow.r['stop_reconciliation']['same_id_reset_verified'])

    def test_wrong_native_target_retains_input(self):
        flow, calls = prepared(reply={'ok': True, 'performed': 'click',
            'accessibility_mode_restoration_verified': True,
            'actual_target': {'package': 'other.app', 'resource-id': new.PACKAGE + ':id/fab'}})
        with self.assertRaisesRegex(RuntimeError, 'ACK_UNKNOWN'): flow.stop('test')
        self.assertIsNotNone(flow.c.pending); self.assertIsNotNone(flow.effect_pending)
        self.assertEqual(calls['native'], 1)

    def test_close_pending_blocks_before_native(self):
        flow, calls = prepared(); flow.close_pending = {'task': 101}
        with self.assertRaises(RuntimeError): flow.stop('test')
        flow.cleanup(time.monotonic() + 45)
        self.assertEqual(calls['native'], 0)

    def test_no_alert_is_observation_not_failure(self):
        flow, calls = prepared(); flow.t.owned = None
        flow.t.stacks = lambda label: (copy.deepcopy(BASE), {851})
        self.assertFalse(flow.claim_alert())
        self.assertFalse(flow.r['new_alert_task_observed'])
        self.assertEqual(calls['native'], 0)

    def test_foreign_extra_task_not_adopted(self):
        flow, calls = prepared(); flow.t.owned = None
        foreign = copy.deepcopy(MAIN); foreign['children'][0]['component'] = 'other.app/.Foreign'
        flow.t.stacks = lambda label: ({**copy.deepcopy(BASE), 101: foreign}, {851, 101})
        with self.assertRaisesRegex(RuntimeError, 'NOT_OWNED'): flow.claim_alert()
        self.assertIsNone(flow.t.owned); self.assertEqual(calls['native'], 0)

    def test_other_timer_or_duration_rejected(self):
        item = state(3); item['ids'] = [0, 1]
        with self.assertRaises(RuntimeError): new.owned_timer(item, 0, 60000)
        item = state(3); item['timers'][0]['length_ms'] = 900000
        with self.assertRaises(RuntimeError): new.owned_timer(item, 0, 60000)

    def test_actual_saved_alarm_record_cannot_qualify_timer(self):
        path = HERE.parent / 'alarm-route04/selected-route04.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '81b12baa291b0d93cf30cb0933949129478fa12448aec6852c7f1b9c5f13af18')
        record = json.loads(raw)['notifications']['fired']['owned_alarm_record']
        projection = ("Current Notification Manager state (filtered to 'com.android.deskclock'):\n"
                      '  Notification List:\n' + record + '\n').encode()
        parsed = new.notification_records(projection)
        self.assertEqual(len(parsed), 1)
        self.assertNotEqual(parsed[0]['key'], new.KEY)
        self.assertFalse(parsed[0]['timer_channel'])

    def test_actual_negative_pause_shape_with_bounded_clock_interval(self):
        # Real historical values, with an explicitly constructed clock interval
        # around their implied pause instant. This is not a new device read.
        path = HERE.parent / 'clock-timer-expiry01-result.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '90617209a0ed0ca29f13872293f1d5ed33e82b1ba8825fc54c9c29b58a6ca7f2')
        phases = json.loads(raw)['phases']
        running = phases['created-running']['timers'][0]
        paused = phases['cleanup-paused']['timers'][0]
        self.assertEqual(paused['remaining_ms'], -42145)
        instant = running['last_start_ms'] + running['remaining_ms'] - paused['remaining_ms']
        proof = new.cleanup_pause_proof(running, paused, instant - 10, instant + 10, UNUSED)
        self.assertEqual(proof['actual_remaining_ms'], -42145)
        with self.assertRaisesRegex(RuntimeError, 'OUTSIDE_EXACT_CLOCK_INTERVAL'):
            new.cleanup_pause_proof(running, paused, instant - 1000, instant - 500, UNUSED)

    def test_false_field_without_actual_controlerror_cannot_clear(self):
        class ForeignError(RuntimeError):
            details = {'outcome_unknown': False, 'automatic_retry': False,
                       'accessibility_mode_restoration_verified': True}
        error = ForeignError('WINDOW_CHANGED_NO_ACTION_TAKEN')
        self.assertFalse(new.no_input_error(error, types.SimpleNamespace(ControlError=NativeError)))

    def test_restoration_missing_does_not_clear(self):
        error = NativeError(False)
        del error.details['accessibility_mode_restoration_verified']
        self.assertFalse(new.no_input_error(error, types.SimpleNamespace(ControlError=NativeError)))

    def test_class_and_label_are_part_of_actual_target_ack(self):
        flow, calls = prepared(reply={'ok': True, 'performed': 'click',
            'accessibility_mode_restoration_verified': True,
            'actual_target': {'package': new.PACKAGE, 'resource-id': new.PACKAGE + ':id/fab',
                'class': 'android.widget.TextView', 'content-desc': 'Start',
                'enabled': True, 'clickable': True}})
        with self.assertRaisesRegex(RuntimeError, 'ACK_UNKNOWN'): flow.stop('test')
        self.assertIsNotNone(flow.c.pending); self.assertIsNotNone(flow.effect_pending)
        self.assertEqual(calls['native'], 1)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries)
    report = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if report.wasSuccessful() else 1)
