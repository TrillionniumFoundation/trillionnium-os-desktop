#!/usr/bin/python3 -I
"""Offline actual expiry02 record and negative controls; no device interaction."""
from pathlib import Path
import ast, hashlib, importlib.util, re, unittest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old, new = load('timer_expiry02'), load('notification_schema02')
RAW = (HERE/'candidate/foreground-timer/saved-expired-notifications.txt').read_bytes()
assert hashlib.sha256(RAW).hexdigest() == '7b116013b3685d1432c1cd644f7ec4482097d1c2ed3439fc8db348aad77cd2b6'
TEXT = RAW.decode()


class ActualDump(unittest.TestCase):
    def test_original_failure_is_reproduced_on_exact_saved_dump(self):
        self.assertEqual(old.active_notifications(TEXT)['active_count'],1)
        self.assertEqual(old.active_notifications(TEXT)['expired_heads_up_count'],0)

    def test_actual_fullscreen_key_is_recognized_without_claiming_visible_ui(self):
        parsed = new.active_notifications(TEXT)
        self.assertTrue(parsed['parsed'])
        self.assertEqual(parsed['active_count'],1)
        self.assertEqual(parsed['expired_heads_up_count'],1)
        self.assertEqual(parsed['records'][0]['uid'],10063)
        self.assertEqual(parsed['records'][0]['user'],0)
        self.assertNotIn('actual_heads_up_window_verified',parsed)

    def test_only_one_regex_literal_changed_in_function(self):
        functions = []
        for name in ('timer_expiry02','notification_schema02'):
            tree = ast.parse((HERE/(name+'.py')).read_text())
            functions.append(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='active_notifications'))
        for item in ast.walk(functions[0]):
            if isinstance(item,ast.Constant) and item.value == r'\bfullScreenIntent=PendingIntent\{':
                item.value = r'\bfullscreenIntent=PendingIntent\{'
        self.assertEqual(ast.dump(functions[0]),ast.dump(functions[1]))

    def test_wrong_uid_rejected(self):
        self.assertFalse(new.active_notifications(TEXT.replace('uid=10063','uid=10163'))['parsed'])

    def test_wrong_user_rejected(self):
        self.assertFalse(new.active_notifications(TEXT.replace('user=UserHandle{0}','user=UserHandle{10}'))['parsed'])

    def test_missing_or_null_intent_not_delivery(self):
        for raw in ('\n'.join(x for x in TEXT.splitlines() if 'fullscreenIntent=' not in x),
                    re.sub(r'^.*fullscreenIntent=.*$', '            fullscreenIntent=null',TEXT,flags=re.M)):
            self.assertEqual(new.active_notifications(raw)['expired_heads_up_count'],0)

    def test_other_channel_not_timer_reminder(self):
        self.assertEqual(new.active_notifications(TEXT.replace('TimerModelNotification','StopwatchNotification'))['expired_heads_up_count'],0)

    def test_history_and_preferences_not_active_delivery(self):
        raw = TEXT.split('  Notification List:',1)[0]+'  Notification List:\n  mArchive=Archive (1 notifications)\n'+TEXT.split('  Notification List:',1)[1]
        self.assertEqual(new.active_notifications(raw)['active_count'],0)
        self.assertEqual(new.active_notifications(raw)['expired_heads_up_count'],0)

    def test_partial_header_and_similarly_named_field_rejected(self):
        self.assertFalse(new.active_notifications(TEXT.replace("filtered to 'com.android.deskclock'","filtered to 'com.other'",1))['parsed'])
        self.assertEqual(new.active_notifications(TEXT.replace('fullscreenIntent=','otherfullscreenIntent='))['expired_heads_up_count'],0)


if __name__ == '__main__':
    unittest.main()
