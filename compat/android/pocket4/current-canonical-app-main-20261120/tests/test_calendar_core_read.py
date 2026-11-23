"""Exercise the Calendar core model against real shifted Linux ownership and SQLite."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'bundle/source/system/calendar_model.py'
spec = importlib.util.spec_from_file_location('calendar_core_model', SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


@unittest.skipUnless(os.geteuid() == 0, 'requires fchown of private test files')
class CalendarCoreReadTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / 'calendar.db'
        with closing(sqlite3.connect(self.path)) as db:
            columns = {'Calendars': model.CALENDAR_COLUMNS, 'Events': model.EVENT_COLUMNS,
                       'Instances': model.INSTANCE_COLUMNS, 'EventsRawTimes': ('event_id',)}
            for table in model.TABLES:
                db.execute(f"CREATE TABLE {table} ({','.join(columns.get(table, ('_id',)))})")
            db.commit()
        os.chown(self.path, 110017, 110020)
        self.reads = 0
        self.guard_calls = 0
        self.opened = []
        self.observations = []
        self.change_during_read = False
        self.view = object()
        session = SimpleNamespace(c=SimpleNamespace(mapped_file_info=self.mapped),
                                  flow=SimpleNamespace(view=self.view), guard=self.guard,
                                  target=SimpleNamespace(open_root=self.opened_db), environment={},
                                  root_query=self.query)
        self.reader = model.Model(session, lambda tag, row: self.observations.append((tag, row)))

    def guard(self):
        self.guard_calls += 1

    def opened_db(self, path, flags):
        self.assertEqual((path, flags), (model.DB, os.O_RDONLY | os.O_NOFOLLOW))
        fd = os.open(self.path, flags)
        self.opened.append(fd)
        return fd

    def mapped(self, view, fd, guest_uid):
        # The held Main's 0 -> 100000 mapping is the sole namespace fixture.
        self.assertIs(view, self.view)
        self.assertEqual(guest_uid, 10017)
        return os.fstat(fd), (100000 + guest_uid, 100000 + guest_uid)

    def query(self, label, argv, timeout):
        self.assertEqual((label, timeout), ('calendar-owned-read', 14))
        self.assertEqual(argv, ['/system/bin/env', '-i', '/system/bin/timeout', '-k', '2', '10',
                                '/system/bin/sqlite3', '-readonly', '-json', model.DB,
                                model.observation_sql()])
        statements = argv[-1].split(';')
        self.assertEqual((statements[:2], statements[-2:]),
                         (['PRAGMA query_only=ON', 'BEGIN'], ['ROLLBACK', '']))
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            for statement in statements[:2]:
                db.execute(statement)
            rows = [dict(r) for r in db.execute(statements[2])]
            db.execute(statements[3])
        self.reads += 1
        if self.change_during_read:
            os.chown(self.path, 110017, 110021)
        return {'rc': 0, 'joined': True, 'timed_out': False, 'stdout': json.dumps(rows)}

    def assert_closed(self):
        for fd in self.opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_shifted_provider_reads_and_keeps_the_actual_gid(self):
        value = self.reader.read('baseline')
        self.reader.require_empty(value)
        self.assertEqual(self.reader.birth, model.fp(self.path.stat()))
        self.assertEqual(self.reader.birth['st_gid'], 110020)
        self.assertEqual((self.reads, self.guard_calls, len(self.opened)), (1, 2, 2))
        self.assertEqual(self.observations[0][0], 'owned-read-baseline')
        self.assert_closed()

    def test_raw_android_uid_is_rejected_before_query(self):
        os.chown(self.path, 10017, 110020)
        with self.assertRaisesRegex(RuntimeError, 'CALENDAR_DB_IDENTITY'):
            self.reader.read('wrong-owner')
        self.assertEqual((self.reads, len(self.opened), self.observations), (0, 1, []))
        self.assert_closed()

    def test_gid_change_during_query_is_rejected_before_recording(self):
        self.change_during_read = True
        with self.assertRaisesRegex(RuntimeError, 'DB_CHANGED_DURING_READ'):
            self.reader.read('changed')
        self.assertEqual((self.reads, len(self.opened), self.observations), (1, 2, []))
        self.assert_closed()


if __name__ == '__main__':
    unittest.main()
