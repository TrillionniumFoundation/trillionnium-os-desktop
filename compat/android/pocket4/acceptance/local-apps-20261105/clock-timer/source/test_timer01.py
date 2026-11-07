#!/usr/bin/python3 -I
"""Pure boundary cases: never load a device session or dispatch UI."""
from pathlib import Path
import importlib.util
import json
import re

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('read_timer_local', ROOT / 'read_timer.py')
timer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timer)


def xml(ids=(0,), extra=''):
    fields = []
    for ident in ids:
        values = {'state': 2, 'length_ms': 900000, 'total_length_ms': 900000,
                  'last_start_ms': timer.UNUSED, 'last_wall_ms': timer.UNUSED,
                  'remaining_ms': 880000, 'label': '', 'delete_after_use': False}
        for prefix, (name, kind) in timer.FIELDS.items():
            key, value = prefix + str(ident), values[name]
            if kind == 'string':
                fields.append('<string name="' + key + '"></string>')
            else:
                value = str(value).lower()
                fields.append('<' + kind + ' name="' + key + '" value="' + value + '"/>')
    return ('<map><set name="timers_list">' + ''.join('<string>' + str(x) + '</string>' for x in ids)
            + '</set><int name="next_timer_id" value="' + str(max(ids) + 1) + '"/>'
            + ''.join(fields) + extra + '</map>').encode()


def rejects(fn, reason):
    try:
        fn()
    except RuntimeError as exc:
        assert reason in str(exc), (reason, str(exc))
    else:
        raise AssertionError('Expected boundary rejection: ' + reason)


cases = []
value = timer.parse(b'<map><string name="unrelated">unchanged</string></map>')
timer.empty(value); cases.append('empty baseline does not expose unrelated preferences')
value = timer.parse(xml())
item = timer.owned(value, 0, 900000)
assert item['id'] == 0 and item['last_start_ms'] == -(1 << 63)
cases.append('timer id zero and exact signed 64-bit sentinel preserved')
rejects(lambda: timer.parse(b'<map><boolean name="delete_after_use_9" value="false"/></map>'), 'TIMER_ID_SET_REQUIRED')
cases.append('hidden delete_after_use orphan is not treated as empty')
metadata = timer.parse(b'<map><set name="timers_list"/><int name="next_timer_id" value="8"/></map>')
timer.empty(metadata)
assert set(metadata['values']) == {'timers_list', 'next_timer_id'}
cases.append('empty membership and retained allocation counter are preserved as metadata')
rejects(lambda: timer.parse(b'<map><set name="timers_list"/><boolean name="delete_after_use_9" value="false"/></map>'),
        'UNRECOGNIZED_OR_ORPHAN')
cases.append('empty ID set does not hide orphan object fields')
rejects(lambda: timer.parse(xml(extra='<long name="timer_time_left_9" value="5"/>')), 'UNRECOGNIZED_OR_ORPHAN')
cases.append('unlisted timer fields rejected')
rejects(lambda: timer.parse(xml().replace(b'<string>0</string>', b'<string>0</string><string>0</string>')), 'TIMER_IDS_EMPTY_DUPLICATE')
cases.append('duplicate timer IDs rejected')
rejects(lambda: timer.owned(timer.parse(xml((0, 1))), 0, 900000), 'SOLE_OWNED_TIMER')
cases.append('a second timer prevents singleton mutation')
rejects(lambda: timer.owned(value, 0, 120000), 'OWNED_TIMER_FIELDS_CHANGED')
cases.append('same ID with changed length is not owned')
rejects(lambda: timer.empty(timer.parse(xml(extra='<int name="sw_state" value="2"/>'))), 'EMPTY_TIMER_AND_STOPWATCH')
cases.append('nonempty stopwatch prevents creation')
tags = ['timer-tab','reopen-timer-tab','digit-1','digit-5','digit-0','create-start','pause','resume',
        'pause-again','reset','delete','cleanup-pause','cleanup-delete']
assert all(re.fullmatch('[a-z][a-z0-9-]{0,39}', 't20-' + tag) for tag in tags)
cases.append('all request IDs fit the unchanged continuation schema')
print(json.dumps({'tests_passed': len(cases), 'cases': cases, 'device_calls': 0, 'UI_inputs': 0}, indent=2))
