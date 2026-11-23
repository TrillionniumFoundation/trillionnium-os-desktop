"""Check both Main callers' generated cleanup requests on a disposable SQLite database."""
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import unittest
from urllib.parse import parse_qs, urlsplit

SOURCE = (Path(__file__).resolve().parents[2]
          / "current-canonical-app-main-20261120/bundle/source")
IDENTITY = ("_id", "account_name", "account_type", "name", "calendar_displayName", "ownerAccount")


def load_model(kind):
    path = SOURCE / kind / "calendar_model.py"
    spec = importlib.util.spec_from_file_location("calendar_" + kind, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bind("4f" * 16) if kind == "calendar-reminder" else module


def request(module):
    model = module.Model(None, None)
    row = dict(_id=23, account_name=module.ACCOUNT, account_type="LOCAL",
               name="droidloom-local-11111111-2222-3333-4444-555555555555",
               calendar_displayName=module.CALENDAR_LABEL, ownerAccount=module.ACCOUNT,
               calendar_access_level=700, visible=1, sync_events=1, calendar_timezone="GMT")
    model.bind_calendar({"calendars": [row]})
    uri, predicate = model.deletion_request()
    return row, urlsplit(uri), predicate


def database(row):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE Calendars (_id INTEGER PRIMARY KEY, account_name TEXT, "
               "account_type TEXT, name TEXT, calendar_displayName TEXT, ownerAccount TEXT)")
    db.execute("CREATE TABLE Events (_id INTEGER PRIMARY KEY, calendar_id INTEGER)")
    values = [row[name] for name in IDENTITY]
    db.execute("INSERT INTO Calendars VALUES (?,?,?,?,?,?)", values)
    values[0] += 1
    db.execute("INSERT INTO Calendars VALUES (?,?,?,?,?,?)", values)
    return db


class CleanupRequests(unittest.TestCase):
    models = {kind: load_model(kind) for kind in ("system", "calendar-reminder")}

    def test_collection_uri_and_owned_empty_row(self):
        for kind, model in self.models.items():
            with self.subTest(caller=kind):
                row, uri, predicate = request(model)
                self.assertEqual((uri.scheme, uri.netloc, uri.path, uri.fragment),
                                 ("content", "com.android.calendar", "/calendars", ""))
                self.assertEqual(parse_qs(uri.query, strict_parsing=True),
                                 {"caller_is_syncadapter": ["true"], "account_name": [model.ACCOUNT],
                                  "account_type": ["LOCAL"]})
                with closing(database(row)) as db:
                    db.execute("INSERT INTO Events VALUES (1, ?)", (row["_id"] + 1,))
                    self.assertEqual(db.execute("DELETE FROM Calendars WHERE " + predicate).rowcount, 1)
                    self.assertEqual(db.execute("SELECT _id FROM Calendars").fetchall(), [(row["_id"] + 1,)])

    def test_entire_identity_rechecked_at_final_delete(self):
        for kind, model in self.models.items():
            row, _, predicate = request(model)
            for field in IDENTITY:
                with self.subTest(caller=kind, field=field), closing(database(row)) as db:
                    self.assertEqual(db.execute("SELECT _id FROM Calendars WHERE " + predicate).fetchall(),
                                     [(row["_id"],)])
                    value = 66 if field == "_id" else "changed"
                    db.execute("UPDATE Calendars SET " + field + "=? WHERE _id=?", (value, row["_id"]))
                    self.assertEqual(db.execute("DELETE FROM Calendars WHERE " + predicate).rowcount, 0)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM Calendars").fetchone(), (2,))

    def test_event_rechecked_at_final_delete(self):
        for kind, model in self.models.items():
            row, _, predicate = request(model)
            with self.subTest(caller=kind), closing(database(row)) as db:
                self.assertEqual(db.execute("SELECT _id FROM Calendars WHERE " + predicate).fetchall(),
                                 [(row["_id"],)])
                db.execute("INSERT INTO Events VALUES (1, ?)", (row["_id"],))
                self.assertEqual(db.execute("DELETE FROM Calendars WHERE " + predicate).rowcount, 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM Events").fetchone(), (1,))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM Calendars").fetchone(), (2,))


if __name__ == "__main__":
    unittest.main()
