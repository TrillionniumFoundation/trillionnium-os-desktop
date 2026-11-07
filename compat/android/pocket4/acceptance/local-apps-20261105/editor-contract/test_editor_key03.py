"""Owned keyboard counterexamples using the retained actual Editor01 observations."""
from pathlib import Path
from types import SimpleNamespace
import copy, importlib.util, json, unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('editor03', HERE / 'editor_ui03.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
actual = json.loads((HERE / 'owned-editor-observations.json').read_text())['selected_observations']
before = actual['after-unicode-0']['value']
fresh = actual['fresh-enter-one-0']['value']
FIELDS = ('package', 'activity', 'window_token', 'display_id', 'window_bounds', 'android_init_host_pid')
NODE = ('resource-id', 'text', 'content-desc', 'class', 'focused', 'editable',
        'package', 'hint', 'bounds_array', 'enabled', 'visible', 'clickable', 'password')

def nodes(value):
    return copy.deepcopy(value.get('native', value)['nodes'])

class KeyboardBoundary(unittest.TestCase):
    def flow(self, mutate=None, unknown=False):
        calls = []
        trial = SimpleNamespace(last_observation=copy.deepcopy(before), owned=(999, {851}),
                                record=lambda *args: None)
        c = SimpleNamespace(nodes=nodes(before), pending=None, actions=0)
        def observe(label, publish=True):
            trial.last_observation = copy.deepcopy(fresh)
            c.nodes = nodes(fresh)
            if mutate and label.startswith('native-before-'):
                mutate(c, trial)
        c.observe = observe
        def dispatch(argv, timeout):
            calls.append(argv)
            if unknown:
                raise RuntimeError('AFTER_DISPATCH_UNKNOWN')
            return b''
        helper = SimpleNamespace(
            capture=lambda request: {'meta': copy.deepcopy(fresh['screenshot'])},
            stable_window=lambda scope: {k: scope[k] for k in FIELDS},
            window_state=lambda *args: copy.deepcopy(fresh['screenshot']['scope']))
        trial.s = SimpleNamespace(helper=helper, android=dispatch, guard=lambda: None)
        trial.ready_focus = lambda _: dict(verified=True,task=999,user=0,focused_activity='.EditorContractActivity',
            **{k:trial.last_observation['screenshot']['scope'][k] for k in ('package','activity','window_token')})
        loop = SimpleNamespace(Continuation=lambda t, pkg: c,
                               node_identity=lambda n: {k: n.get(k) for k in NODE})
        flow = m.Flow(trial, loop, {})
        flow.current = SimpleNamespace(read=lambda *args: {'ready': True})
        value = next(n['text'] for n in c.nodes if n.get('editable') is True)
        return flow, calls, value

    def test_actual_pixel_change_same_native_target_does_not_block_keyboard(self):
        self.assertNotEqual(before['screenshot']['scope_sha256'], fresh['screenshot']['scope_sha256'])
        self.assertEqual(before['screenshot']['context_token'], fresh['screenshot']['context_token'])
        flow, calls, value = self.flow()
        flow.key('one', 'KEYCODE_ENTER', value)
        self.assertEqual(len(calls), 1)
        self.assertEqual(flow.actions, 1)
        self.assertIsNone(flow.c.pending)

    def test_changed_window_activity_display_geometry_or_epoch_rejected(self):
        original = copy.deepcopy(fresh['screenshot'])
        for field, changed in [('window_token', 'foreign'), ('activity', 'foreign.Activity'),
            ('package', 'foreign.package'), ('display_id', 1),
            ('window_bounds', [0, 0, 10, 10]), ('android_init_host_pid', 1)]:
            with self.subTest(field=field):
                altered = copy.deepcopy(original); altered['scope'][field] = changed
                with self.assertRaisesRegex(RuntimeError, 'KEY_WINDOW_CONTEXT_CHANGED'):
                    m.key_context(original, altered)

    def test_context_change_rejected_even_if_window_fields_match(self):
        altered = copy.deepcopy(fresh['screenshot']); altered['context_token'] = 'f' * 64
        with self.assertRaisesRegex(RuntimeError, 'KEY_WINDOW_CONTEXT_CHANGED'):
            m.key_context(fresh['screenshot'], altered)

    def test_focus_loss_extra_editor_and_changed_value_stop_before_dispatch(self):
        def edits(c, trial, kind):
            editor = next(n for n in c.nodes if n.get('editable') is True)
            if kind == 'focus': editor['focused'] = False
            elif kind == 'second': c.nodes.append(copy.deepcopy(editor))
            else: editor['text'] = 'different value'
        for kind in ('focus', 'second', 'text'):
            with self.subTest(kind=kind):
                flow, calls, value = self.flow(lambda c, t: edits(c, t, kind))
                with self.assertRaises(RuntimeError): flow.key('one', 'KEYCODE_ENTER', value)
                self.assertEqual(calls, []); self.assertEqual(flow.actions, 0)
                self.assertIsNone(flow.c.pending)

    def test_unknown_dispatched_key_retained_and_not_replayed(self):
        flow, calls, value = self.flow(unknown=True)
        with self.assertRaisesRegex(RuntimeError, 'AFTER_DISPATCH_UNKNOWN'):
            flow.key('one', 'KEYCODE_ENTER', value)
        self.assertEqual(len(calls), 1); self.assertEqual(flow.actions, 1)
        self.assertEqual(flow.c.pending, 'one')
        with self.assertRaisesRegex(RuntimeError, 'KEY_SCOPE_OR_ACTION_BOUND'):
            flow.key('one', 'KEYCODE_ENTER', value)
        self.assertEqual(len(calls), 1)


    def test_actual_compact_focus_schema_has_no_fabricated_window_fields(self):
        flow, calls, value = self.flow()
        focus = flow.t.ready_focus(False)
        self.assertFalse({'display_id','window_bounds','android_init_host_pid'} & set(focus))
        flow.key('one', 'KEYCODE_ENTER', value)
        self.assertEqual(len(calls), 1)

    def test_final_owned_task_or_native_geometry_change_stops_dispatch(self):
        for kind in ('task', 'native_geometry'):
            with self.subTest(kind=kind):
                flow, calls, value = self.flow()
                if kind == 'task':
                    original = flow.t.ready_focus
                    flow.t.ready_focus = lambda arg: dict(original(arg),task=1000)
                else:
                    original = flow.t.s.helper.window_state
                    flow.t.s.helper.window_state = lambda *args: dict(original(*args),window_bounds=[0,0,10,10])
                with self.assertRaisesRegex(RuntimeError, 'KEY_'):
                    flow.key('one', 'KEYCODE_ENTER', value)
                self.assertEqual(calls, []); self.assertEqual(flow.actions, 0)
                self.assertIsNone(flow.c.pending)

    def test_navigation_outside_owned_editor_contract_is_rejected(self):
        flow, calls, value = self.flow()
        with self.assertRaisesRegex(RuntimeError, 'KEY_SCOPE_OR_ACTION_BOUND'):
            flow.key('one', 'KEYCODE_HOME', value)
        self.assertEqual(calls, [])

if __name__ == '__main__': unittest.main(verbosity=2)
