#!/usr/bin/python3 -I
"""Bounded, read-only parser for actual DeskClock timer preferences."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET

PREFS = '/data/user_de/0/com.android.deskclock/shared_prefs/com.android.deskclock_preferences.xml'
UNUSED = -(1 << 63)
FIELDS = {
    'timer_state_': ('state', 'int'),
    'timer_setup_timet_': ('length_ms', 'long'),
    'timer_original_timet_': ('total_length_ms', 'long'),
    'timer_start_time_': ('last_start_ms', 'long'),
    'timer_wall_clock_time_': ('last_wall_ms', 'long'),
    'timer_time_left_': ('remaining_ms', 'long'),
    'timer_label_': ('label', 'string'),
    'delete_after_use_': ('delete_after_use', 'boolean'),
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def parse(raw):
    tree = ET.fromstring(raw)
    require(tree.tag == 'map', 'CLOCK_PREFERENCES_FORMAT_UNKNOWN')
    entries, timer_values, watch = {}, {}, {}
    for entry in tree:
        key = entry.get('name', '')
        require(key and key not in entries, 'PREFERENCE_NAME_MISSING_OR_DUPLICATE')
        entries[key] = entry
        if key.startswith('sw_'):
            require(entry.tag in ('int', 'long') and re.fullmatch('-?[0-9]+', entry.get('value', '')),
                    'STOPWATCH_VALUE_UNKNOWN')
            watch[key] = int(entry.get('value'))
        if 'timer' in key.lower() or key.startswith('delete_after_use_'):
            timer_values[key] = ET.tostring(entry, encoding='unicode')
    if not timer_values:
        return {'ids': [], 'timers': [], 'values': {}, 'stopwatch': watch}
    metadata = {'timers_list', 'next_timer_id'}
    require('timers_list' in entries or set(timer_values) <= metadata, 'TIMER_ID_SET_REQUIRED')
    require('timers_list' not in entries or entries['timers_list'].tag == 'set', 'TIMER_ID_SET_REQUIRED')
    ids = []
    for item in entries.get('timers_list', ()):
        require(item.tag == 'string' and re.fullmatch('0|[1-9][0-9]*', item.text or ''), 'TIMER_ID_INVALID')
        ids.append(int(item.text))
    require(len(ids) == len(set(ids)) and len(ids) <= 8, 'TIMER_IDS_EMPTY_DUPLICATE_OR_TOO_MANY')
    if 'next_timer_id' in entries:
        require(entries['next_timer_id'].tag == 'int'
            and re.fullmatch('[0-9]+', entries['next_timer_id'].get('value', '')), 'NEXT_TIMER_ID_UNKNOWN')
    if not ids:
        # Empty membership and an allocation counter are metadata, not a timer.
        # Preserve their real bytes in evidence; never delete them to pass a test.
        require(set(timer_values) <= metadata, 'UNRECOGNIZED_OR_ORPHAN_TIMER_PREFERENCE')
        return {'ids': [], 'timers': [], 'values': dict(sorted(timer_values.items())), 'stopwatch': watch}
    require('next_timer_id' in entries, 'NEXT_TIMER_ID_UNKNOWN')
    require(int(entries['next_timer_id'].get('value')) > max(ids), 'NEXT_TIMER_ID_INCONSISTENT')
    expected = {'timers_list', 'next_timer_id'}
    timers = []
    for ident in sorted(ids):
        timer = {'id': ident}
        for prefix, (field, kind) in FIELDS.items():
            key = prefix + str(ident)
            entry = entries.get(key)
            # SharedPreferences.putString(null) removes an optional label.
            if entry is None and kind == 'string':
                timer[field] = None
                continue
            require(entry is not None and entry.tag == kind, 'TIMER_FIELD_MISSING_OR_WRONG_TYPE_' + field)
            expected.add(key)
            if kind in ('int', 'long'):
                require(re.fullmatch('-?[0-9]+', entry.get('value', '')), 'TIMER_NUMBER_UNKNOWN')
                value = int(entry.get('value'))
                require(-(1 << 63) <= value < (1 << 63), 'TIMER_NUMBER_OUT_OF_RANGE')
            elif kind == 'boolean':
                require(entry.get('value') in ('true', 'false'), 'TIMER_BOOLEAN_UNKNOWN')
                value = entry.get('value') == 'true'
            else:
                value = entry.text or ''
                require(len(value.encode()) <= 4096, 'TIMER_LABEL_TOO_LONG')
            timer[field] = value
        require(timer['state'] in (1, 2, 3, 4, 5) and timer['length_ms'] > 0
                and timer['total_length_ms'] >= 0, 'TIMER_STATE_OR_DURATION_UNKNOWN')
        timers.append(timer)
    require(set(timer_values) == expected, 'UNRECOGNIZED_OR_ORPHAN_TIMER_PREFERENCE')
    return {'ids': sorted(ids), 'timers': timers, 'values': dict(sorted(timer_values.items())), 'stopwatch': watch}


def read(session):
    raw, _ = session.target.read_file(PREFS, 1024 * 1024)
    result = parse(raw)
    session.guard()
    return result


def empty(value):
    require(value['ids'] == value['timers'] == []
            and set(value['values']) <= {'timers_list', 'next_timer_id'}
            and value['stopwatch'] == {}, 'EMPTY_TIMER_AND_STOPWATCH_BASELINE_REQUIRED')


def owned(value, ident, duration):
    require(value['ids'] == [ident] and len(value['timers']) == 1 and value['stopwatch'] == {},
            'SOLE_OWNED_TIMER_AND_EMPTY_STOPWATCH_REQUIRED')
    timer = value['timers'][0]
    require(timer['id'] == ident and timer['length_ms'] == timer['total_length_ms'] == duration
            and timer['label'] in ('', None) and timer['delete_after_use'] is False,
            'OWNED_TIMER_FIELDS_CHANGED')
    return timer


if __name__ == '__main__':
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'preference_write_actions': 0}))
