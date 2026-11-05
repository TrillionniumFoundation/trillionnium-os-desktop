"""Pure records plus owned local Python children; never runs journalctl or main."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collect-template.py'))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
BOOT = '981ff371cd724f819be3a862111afdb1'
C.CFG = {'boot_id': '981ff371-cd72-4f81-9be3-a862111afdb1',
         'window_start_us': 100, 'window_end_us': 200, 'owned_pids': [1204580]}


def row(tick, message='init: fixture', **extra):
    d = {'_BOOT_ID': BOOT, '_TRANSPORT': 'kernel', '__MONOTONIC_TIMESTAMP': str(tick), 'MESSAGE': message}
    d.update(extra)
    return (json.dumps(d) + '\n').encode()


def child(code, report):
    fd = os.open(sys.executable, os.O_RDONLY | os.O_CLOEXEC)
    try:
        C.run_journal(fd, [sys.executable, '-I', '-B', '-c', code], report)
    finally:
        os.close(fd)


class Controls(unittest.TestCase):
    def test_exact_boot_transport_time_filter(self):
        for tick, expected in ((99, False), (100, True), (200, True), (201, False)):
            self.assertEqual(C.journal_record(row(tick))[1], expected)
        for extra in ({'_BOOT_ID': '0' * 32}, {'_TRANSPORT': 'stdout'}, {'__MONOTONIC_TIMESTAMP': '-1'}):
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                C.journal_record(row(150, **extra))

    def test_only_named_or_recorded_pid_candidates(self):
        self.assertFalse(C.journal_record(row(150, 'unrelated'))[1])
        self.assertTrue(C.journal_record(row(150, 'cause', SYSLOG_IDENTIFIER='init'))[1])
        self.assertTrue(C.journal_record(row(150, 'cause', SYSLOG_PID='1204580'))[1])
        self.assertFalse(C.journal_record(row(150, 'cause', SYSLOG_PID='7'))[1])

    def test_binary_message_raw_json_preserved(self):
        original = row(150, [105, 110, 105, 116, 58, 255])
        item = C.journal_record(original)
        self.assertTrue(item[1])
        self.assertEqual(base64.b64decode(item[2]['raw_base64'], validate=True), original)
        self.assertEqual(item[2]['raw_sha256'], C.sha(original))

    def test_owned_child_complete_and_reaped(self):
        body = row(99) + row(150) + row(201)
        report = C.new_journal_report()
        child('import os;os.write(1,' + repr(body) + ')', report)
        self.assertTrue(report['child_reaped'])
        self.assertTrue(report['query_drained'])
        self.assertFalse(report['forced_child_kill'])
        self.assertEqual(report['returncode'], 0)
        self.assertEqual(len(report['selected_records']), 1)
        self.assertTrue(report['window_timestamp_bounds_covered'])
        self.assertFalse(report['persistent_journal_completeness_proved'])

    def test_owned_child_timeout_retains_partial_and_exact_join(self):
        report = C.new_journal_report()
        code = 'import os,time;os.write(1,' + repr(row(150)) + ');time.sleep(60)'
        with mock.patch.object(C, 'MAX_READ_SECONDS', 0.2), self.assertRaises(RuntimeError):
            child(code, report)
        self.assertTrue(report['child_reaped'])
        self.assertTrue(report['forced_child_kill'])
        self.assertEqual(report['returncode'], -9)
        self.assertFalse(report['query_drained'])
        self.assertEqual(len(report['selected_records']), 1)

    def test_owned_child_parse_failure_keeps_primary_and_join(self):
        report = C.new_journal_report()
        code = 'import os,time;os.write(1,' + repr(row(150) + b'not-json\n') + ');time.sleep(60)'
        with self.assertRaises(json.JSONDecodeError):
            child(code, report)
        self.assertTrue(report['child_reaped'])
        self.assertFalse(report['query_drained'])
        self.assertEqual(len(report['selected_records']), 1)
        self.assertIn('JSONDecodeError', report['first_error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
