#!/usr/bin/python3 -I
"""Local boundaries for the new expiry state and source-bound alert exception."""
from pathlib import Path
import copy, importlib.util, json, unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('expiry', HERE / 'timer_expiry01.py')
expiry = importlib.util.module_from_spec(spec); spec.loader.exec_module(expiry)


def value():
    return {'ids': [0], 'stopwatch': {}, 'timers': [{'id': 0, 'state': 3,
        'length_ms': 60000, 'total_length_ms': 0, 'remaining_ms': 0,
        'last_start_ms': 999000, 'last_wall_ms': 1793870000000,
        'label': None, 'delete_after_use': False}]}


class Boundaries(unittest.TestCase):
    def test_actual_empty_notification_list_not_channel_preferences(self):
        saved = json.loads((HERE / 'clock-notification-active-list-schema.json').read_text())
        raw = saved['active_list_prefix'] + "  mArchive=Archive (0 notifications)\n    NotificationChannel{mId='TimerModelNotification'}\n"
        actual = expiry.active_notifications(raw)
        self.assertTrue(actual['parsed']); self.assertEqual(actual['active_count'], 0)
        self.assertEqual(actual['expired_heads_up_count'], 0)

    def test_active_notification_requires_uid_and_fullscreen_not_just_channel(self):
        # Synthetic schema fixture, not a claim about actual runtime delivery.
        raw = ("Current Notification Manager state (filtered to 'com.android.deskclock'):\n"
               "  Notification List:\n    NotificationRecord(x: pkg=com.android.deskclock user=UserHandle{0} id=1)\n"
               "      uid=10063\n      Notification(channel=TimerModelNotification)\n"
               "      fullScreenIntent=PendingIntent{test}\n  mArchive=Archive (0 notifications)\n")
        self.assertEqual(expiry.active_notifications(raw)['expired_heads_up_count'], 1)
        self.assertEqual(expiry.active_notifications(raw.replace('fullScreenIntent=PendingIntent{test}', 'fullScreenIntent=null'))['expired_heads_up_count'], 0)
        self.assertFalse(expiry.active_notifications(raw.replace('uid=10063', 'uid=10163'))['parsed'])

    def test_expired_zero_total_is_required(self):
        self.assertEqual(expiry.timer_owned(value(), 0)['state'], 3)
        changed = value(); changed['timers'][0]['total_length_ms'] = 60000
        with self.assertRaises(RuntimeError): expiry.timer_owned(changed, 0)

    def test_foreign_or_multiple_ids_are_never_owned(self):
        changed = value(); changed['ids'] = [1]; changed['timers'][0]['id'] = 1
        with self.assertRaises(RuntimeError): expiry.timer_owned(changed, 0)
        changed = value(); changed['ids'] = [0, 1]; changed['timers'].append(dict(changed['timers'][0], id=1))
        with self.assertRaises(RuntimeError): expiry.timer_owned(changed, 0)

    def test_delete_after_use_and_duration_change_rejected(self):
        for key, wrong in (('delete_after_use', True), ('length_ms', 1000), ('label', 'foreign')):
            changed = value(); changed['timers'][0][key] = wrong
            with self.assertRaises(RuntimeError): expiry.timer_owned(changed, 0)

    def test_fullscreen_exception_is_only_exact_expired_activity(self):
        roots = {1: {'display': 0, 'user': 0, 'freeform': False, 'children': [
            {'id': 900, 'user': 0, 'component': 'com.android.deskclock/.timer.ExpiredTimersActivity'}]}}
        self.assertTrue(expiry.exact_alert(roots, 900))
        for component in ('com.android.deskclock/.DeskClock', 'com.android.deskclock/.alarms.AlarmActivity',
                          'com.android.settings/.Settings'):
            changed = copy.deepcopy(roots); changed[1]['children'][0]['component'] = component
            self.assertFalse(expiry.exact_alert(changed, 900))
        changed = copy.deepcopy(roots); changed[1]['display'] = 1
        self.assertFalse(expiry.exact_alert(changed, 900))

    def test_same_id_duplicate_task_is_not_unique(self):
        child = {'id': 900, 'user': 0, 'component': 'com.android.deskclock/.timer.ExpiredTimersActivity'}
        roots = {i: {'display': 0, 'user': 0, 'children': [dict(child)]} for i in (1, 2)}
        self.assertFalse(expiry.exact_alert(roots, 900))

    def test_unrecognized_notification_header_is_not_empty_success(self):
        self.assertFalse(expiry.active_notifications('')['parsed'])
        self.assertFalse(expiry.active_notifications('Notification List:\n')['parsed'])


if __name__ == '__main__':
    unittest.main()
