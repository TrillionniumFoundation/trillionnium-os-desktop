#!/usr/bin/python3 -I
"""Pure checks for preserving preexisting Clock state and finite decisions."""
from pathlib import Path
import hashlib, json, types

HERE = Path(__file__).resolve().parent
m = types.ModuleType('clock_stopwatch_local_checks'); m.__file__ = str(HERE / 'stopwatch01.py')
exec(compile((HERE / 'stopwatch01.py').read_bytes(), m.__file__, 'exec'), m.__dict__)
checks = []


def read(xml):
    session = types.SimpleNamespace(target=types.SimpleNamespace(read_file=lambda *a: (xml.encode(), {})),
                                    guard=lambda: None)
    return m.read_watch(session)


def rejects(fn):
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError('expected rejection')


def check(name, fn):
    fn(); checks.append({'name': name, 'passed': True})


def empty():
    value = read('<map><int name="last_tab" value="0" /></map>')
    assert value['state'] == value['accumulated_ms'] == value['lap_count'] == 0
    assert value['values'] == {}
check('actual_empty_watch_shape_is_reset_only', empty)


def invalid():
    for xml in ('<map><int name="sw_state" value="9"/></map>',
                '<map><string name="sw_state">0</string></map>',
                '<map><int name="sw_state" value="0"/><int name="sw_state" value="1"/></map>'):
        rejects(lambda: read(xml))
check('unknown_or_duplicate_state_never_defaults_to_reset', invalid)


def original_values():
    for value in ({'state': 1, 'accumulated_ms': 0, 'lap_count': 0},
                  {'state': 2, 'accumulated_ms': 12000, 'lap_count': 0},
                  {'state': 0, 'accumulated_ms': 5, 'lap_count': 0},
                  {'state': 0, 'accumulated_ms': 0, 'lap_count': 1}):
        flow = object.__new__(m.Flow)
        def state(label, expected):
            if value['state'] != expected:
                raise RuntimeError('preexisting')
            return value
        flow.state = state
        flow.launch = lambda *a: (_ for _ in ()).throw(AssertionError('must not launch'))
        rejects(flow.run)
check('preexisting_running_paused_or_laps_zero_launches', original_values)


def ambiguous():
    f = object.__new__(m.Flow)
    base = {'package': m.PACKAGE, 'visible': True, 'enabled': True, 'clickable': True,
            'text': '', 'content-desc': 'Start', 'editable': False, 'password': False}
    f.c = types.SimpleNamespace(nodes=[base, dict(base)])
    rejects(lambda: f.node(('Start',)))
    f.c.nodes = [dict(base, package='com.android.settings')]
    rejects(lambda: f.node(('Start',)))
check('ambiguous_or_foreign_start_sends_no_input', ambiguous)


def tab_parent():
    f = object.__new__(m.Flow)
    base = {'package': m.PACKAGE, 'visible': True, 'enabled': True, 'text': 'Stopwatch'}
    f.c = types.SimpleNamespace(nodes=[dict(base, clickable=False), dict(base, clickable=True)])
    assert f.node(('Stopwatch',), button=False)['clickable'] is True
check('actual_semantic_label_with_one_clickable_parent_is_unique', tab_parent)


def unknown():
    f = object.__new__(m.Flow); f.started = True; f.r = {}
    f.c = types.SimpleNamespace(pending='s02-start')
    f.t = types.SimpleNamespace(owned=(999, set()))
    f.cleanup()
    assert f.r['cleanup']['new_inputs'] == 0 and f.c.pending == 's02-start'
check('unknown_input_not_replayed_or_cleared_for_cleanup', unknown)


def timer_privacy():
    a = read('<map><string name="timer_label_1">private-one</string></map>')
    b = read('<map><string name="timer_label_1">private-two</string></map>')
    assert a['timer_content_sha256'] != b['timer_content_sha256']
    assert 'private' not in json.dumps(a) and 'private' not in json.dumps(b)
check('timer_digest_detects_change_without_returning_labels', timer_privacy)

result = {'UI_actions': 0, 'clock_data_writes': 0, 'checks': checks,
          'source_sha256': hashlib.sha256((HERE / 'stopwatch01.py').read_bytes()).hexdigest()}
(HERE / 'stopwatch01-local-validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
